"""
ETL Papers — Extracción de metadatos (título, resumen, palabras clave) desde
los PDFs de artículos ubicados en ``data/bronze/papers/<issn>/``.

Cada carpeta usa el ISSN como nombre; todos los PDFs dentro de ella
pertenecen a esa revista. Algunos PDFs contienen un solo artículo y otros son
el número completo de la revista (varios artículos concatenados en un mismo
archivo). El módulo detecta ambos casos buscando pares de marcadores
Resumen/Abstract seguidos de Palabras clave/Keywords a lo largo del texto
extraído del PDF; cada par cercano en el texto se agrupa como un mismo
artículo, y artículos bilingües generan dos registros (uno por idioma) con el
mismo ``issn_normalizado`` y ``articulo_id``.

Capas:
- Bronze: los PDF originales en ``PAPERS_DIR`` (sin transformación).
- Silver: ``procesar_papers()`` produce un registro por artículo/idioma con
  issn, título, resumen y palabras clave (``PAPERS_SILVER``).
- Gold: ``construir_gold_articulos()`` tokeniza y normaliza cada registro
  (uno por artículo/idioma, ``ARTICULOS_GOLD``); ``construir_gold_revistas()``
  agrega todos los tokens de una revista en una sola bolsa de palabras por
  ISSN (``REVISTA_TOKENS_GOLD``).

Limitación conocida: la segmentación de artículos dentro de un PDF de número
completo y la extracción del título son heurísticas basadas en texto plano
(sin análisis de layout); PDFs escaneados sin texto extraíble no producen
artículos y quedan registrados en el log.
"""

import hashlib
import logging
import re
from pathlib import Path
from typing import Optional

import pandas as pd

try:
    from pypdf import PdfReader
except ImportError:  # pragma: no cover
    PdfReader = None

try:
    import pymupdf as fitz
except ImportError:  # pragma: no cover
    try:
        import fitz
    except ImportError:  # pragma: no cover
        fitz = None

from ...config.settings import (
    ARTICULOS_GOLD,
    ARTICULOS_GOLD_CSV,
    PAPERS_DIR,
    PAPERS_MAX_PAGINAS,
    PAPERS_SILVER,
    PAPERS_SILVER_CSV,
    REVISTA_TOKENS_GOLD,
    REVISTA_TOKENS_GOLD_CSV,
    VERSION_PROCESO,
)
from ...data.normalization import limpiar_issn
from ...models.thematic_profile import preprocess_text

logger = logging.getLogger("etl_papers")

# ── Marcadores de sección (resumen/abstract y palabras clave) ─────────────
_RESUMEN_RE = re.compile(r"\b(resumen|resumo)\b\s*[:\-–]?", re.IGNORECASE)
_ABSTRACT_RE = re.compile(r"\babstract\b\s*[:\-–]?", re.IGNORECASE)
_KEYWORDS_ES_RE = re.compile(r"\b(palabras\s+claves?|descriptores)\b\s*[:\-–]?", re.IGNORECASE)
_KEYWORDS_EN_RE = re.compile(r"\b(key\s*words?|index\s+terms)\b\s*[:\-–]?", re.IGNORECASE)
_STOP_SECTION_RE = re.compile(
    r"\b(introducci[oó]n|introduction|materiales\s+y\s+m[eé]todos|methods?|metodolog[ií]a|resumen|resumo|abstract)\b",
    re.IGNORECASE,
)

VENTANA_KEYWORDS_MAX = 4000       # distancia máxima entre marcador resumen/abstract y sus keywords
VENTANA_TITULO = 900              # caracteres previos al marcador para buscar el título
VENTANA_PALABRAS_CLAVE_MAX = 400  # longitud máxima capturada para palabras clave
GAP_NUEVO_ARTICULO = 6000         # distancia mínima entre marcadores para tratarlos como artículos distintos


def _normalizar_texto_extraido(texto: str) -> str:
    """Corrige artefactos frecuentes sin destruir saltos de línea útiles."""
    texto = texto.replace("\u00ad", "")
    texto = texto.translate(str.maketrans({
        "ﬁ": "fi", "ﬂ": "fl", "ﬀ": "ff", "ﬃ": "ffi", "ﬄ": "ffl",
    }))
    texto = re.sub(r"(?<=\w)-\s*\n\s*(?=\w)", "", texto)
    texto = re.sub(r"[ \t]+", " ", texto)
    texto = re.sub(r"\n{3,}", "\n\n", texto)
    return texto.strip()


def _extraer_con_pypdf(ruta: Path, max_paginas: int) -> str:
    """Extrae primero preservando layout y usa modo plano como fallback."""
    if PdfReader is None:
        return ""
    reader = PdfReader(str(ruta), strict=False)
    limite = min(len(reader.pages), max_paginas)
    textos = []
    for i in range(limite):
        try:
            try:
                pagina = reader.pages[i].extract_text(extraction_mode="layout") or ""
            except (TypeError, ValueError):
                pagina = reader.pages[i].extract_text() or ""
            textos.append(_normalizar_texto_extraido(pagina))
        except Exception as error:
            logger.debug("Página %d de %s no pudo extraerse: %s", i, ruta.name, error)
    return "\f".join(textos)


def _extraer_con_ocr(ruta: Path, max_paginas: int) -> str:
    """Aplica OCR opcional a PDFs escaneados cuando el entorno lo permite."""
    if fitz is None:
        return ""
    try:
        import pytesseract
        from PIL import Image
    except ImportError:
        return ""
    try:
        documento = fitz.open(str(ruta))
        textos = []
        for pagina in documento[:max_paginas]:
            pixmap = pagina.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
            imagen = Image.frombytes("RGB", [pixmap.width, pixmap.height], pixmap.samples)
            textos.append(_normalizar_texto_extraido(
                pytesseract.image_to_string(imagen, lang="spa+eng")
            ))
        return "\f".join(textos)
    except Exception as error:
        logger.warning("  OCR no disponible para %s: %s", ruta.name, error)
        return ""


def _extraer_con_pymupdf(ruta: Path, max_paginas: int) -> str:
    """Extrae la capa textual nativa como segundo fallback de bajo costo."""
    if fitz is None:
        return ""
    try:
        documento = fitz.open(str(ruta))
        textos = [
            _normalizar_texto_extraido(pagina.get_text("text") or "")
            for pagina in documento[:max_paginas]
        ]
        return "\f".join(textos)
    except Exception as error:
        logger.debug("PyMuPDF no pudo extraer %s: %s", ruta.name, error)
        return ""


def _extraer_texto_pdf(ruta: Path, max_paginas: int = PAPERS_MAX_PAGINAS) -> str:
    """Extrae texto nativo y activa OCR solo para PDFs sin capa textual."""
    if PdfReader is None:
        raise ImportError("pypdf no está instalado; agréguelo a las dependencias del proyecto")
    pymupdf_text = _extraer_con_pymupdf(ruta, max_paginas)
    if len(re.sub(r"\s+", "", pymupdf_text)) >= 200:
        return pymupdf_text

    try:
        texto = _extraer_con_pypdf(ruta, max_paginas)
    except Exception as error:
        logger.warning("  ✗ No se pudo extraer texto nativo de %s: %s", ruta.name, error)
        texto = ""
    if len(re.sub(r"\s+", "", texto)) >= 200:
        return texto

    ocr = _extraer_con_ocr(ruta, max_paginas)
    if len(re.sub(r"\s+", "", ocr)) > len(re.sub(r"\s+", "", pymupdf_text)):
        logger.info("  %s: extracción OCR activada", ruta.name)
        return ocr
    return pymupdf_text or texto


def _buscar_anclas(texto: str) -> list[dict]:
    """Encuentra marcadores resumen/abstract que tienen un bloque de palabras clave cercano."""
    anclas = []
    for marcador_re, idioma in [(_RESUMEN_RE, "es"), (_ABSTRACT_RE, "en")]:
        for m in marcador_re.finditer(texto):
            ventana = texto[m.end(): m.end() + VENTANA_KEYWORDS_MAX]
            kw_re = _KEYWORDS_ES_RE if idioma == "es" else _KEYWORDS_EN_RE
            kw_match = kw_re.search(ventana)
            if not kw_match:
                # Respaldo: aceptar el marcador de keywords del otro idioma (resúmenes mixtos).
                kw_match = (_KEYWORDS_EN_RE if idioma == "es" else _KEYWORDS_ES_RE).search(ventana)
            if not kw_match:
                continue
            anclas.append({
                "idioma": idioma,
                "inicio_marcador": m.start(),
                "inicio_resumen": m.end(),
                "fin_resumen": m.end() + kw_match.start(),
                "inicio_keywords": m.end() + kw_match.end(),
            })
    anclas.sort(key=lambda a: a["inicio_marcador"])
    return anclas


def _agrupar_en_articulos(anclas: list[dict]) -> list[list[dict]]:
    """Agrupa anclas cercanas en el texto (mismo artículo, distinto idioma) en clusters."""
    if not anclas:
        return []
    clusters = [[anclas[0]]]
    for ancla in anclas[1:]:
        anterior = clusters[-1][-1]
        if ancla["inicio_marcador"] - anterior["inicio_marcador"] < GAP_NUEVO_ARTICULO:
            clusters[-1].append(ancla)
        else:
            clusters.append([ancla])
    return clusters


def _lineas_repetidas(texto: str, min_ocurrencias: int = 3) -> set[str]:
    """Detecta líneas que se repiten en varias páginas (encabezados/pies de
    página del PDF) para excluirlas de la búsqueda del título."""
    contador: dict[str, int] = {}
    for pagina in texto.split("\f"):
        vistas = set()
        for linea in pagina.split("\n"):
            l = linea.strip()
            if l and l not in vistas:
                contador[l] = contador.get(l, 0) + 1
                vistas.add(l)
    return {l for l, c in contador.items() if c >= min_ocurrencias}


def _extraer_titulo(texto: str, inicio_marcador: int, repetidas: set[str]) -> Optional[str]:
    """Heurística: toma la línea más temprana y sustancial antes del marcador
    resumen/abstract dentro de la ventana (el título suele preceder a autores
    y afiliaciones, que quedan justo antes del marcador), descartando líneas
    repetidas en el documento (encabezados/pies de página)."""
    ventana = texto[max(0, inicio_marcador - VENTANA_TITULO): inicio_marcador]
    lineas = [l.strip() for l in re.split(r"[\n\f]+", ventana) if l.strip()]
    candidatas = [
        l for l in lineas
        if 15 <= len(l) <= 220 and "@" not in l and sum(c.isdigit() for c in l) < 6
        and l not in repetidas
    ]
    if candidatas:
        return candidatas[0]
    lineas_no_repetidas = [l for l in lineas if l not in repetidas]
    return lineas_no_repetidas[0] if lineas_no_repetidas else (lineas[0] if lineas else None)


def _limpiar_palabras_clave(texto: str) -> Optional[str]:
    texto = texto.strip()
    if not texto:
        return None
    corte = _STOP_SECTION_RE.search(texto)
    if corte:
        texto = texto[: corte.start()]
    texto = texto[:VENTANA_PALABRAS_CLAVE_MAX]
    texto = re.sub(r"\s+", " ", texto).strip(" .;:-–")
    return texto or None


def _limpiar_resumen(texto: str) -> Optional[str]:
    texto = re.sub(r"\s+", " ", texto).strip(" .;:-–")
    return texto or None


def extraer_articulos_pdf(ruta: Path, issn: str) -> list[dict]:
    """Extrae uno o más artículos (uno por idioma detectado) de un PDF."""
    texto = _extraer_texto_pdf(ruta)
    if not texto.strip():
        return []

    clusters = _agrupar_en_articulos(_buscar_anclas(texto))
    repetidas = _lineas_repetidas(texto)

    if not clusters:
        # Sin marcadores detectables: registro de respaldo con el inicio del texto.
        cuerpo = re.sub(r"\s+", " ", texto[:4000]).strip()
        if len(cuerpo) < 200:
            return []
        titulo = ruta.stem.replace("+", " ").replace("_", " ").strip()
        return [{
            "issn_normalizado": issn,
            "archivo": ruta.name,
            "articulo_id": f"{ruta.stem}_0",
            "idioma": "desconocido",
            "titulo": titulo or None,
            "resumen": cuerpo[:1500],
            "palabras_clave": None,
            "extraccion": "respaldo_sin_marcadores",
        }]

    registros = []
    for idx, cluster in enumerate(clusters):
        for ancla in cluster:
            resumen = _limpiar_resumen(texto[ancla["inicio_resumen"]: ancla["fin_resumen"]])
            if not resumen or len(resumen) < 40:
                continue
            palabras_clave = _limpiar_palabras_clave(
                texto[ancla["inicio_keywords"]: ancla["inicio_keywords"] + VENTANA_PALABRAS_CLAVE_MAX]
            )
            titulo = _extraer_titulo(texto, ancla["inicio_marcador"], repetidas)
            registros.append({
                "issn_normalizado": issn,
                "archivo": ruta.name,
                "articulo_id": f"{ruta.stem}_{idx}",
                "idioma": ancla["idioma"],
                "titulo": titulo,
                "resumen": resumen,
                "palabras_clave": palabras_clave,
                "extraccion": "marcadores",
            })
    return registros


def normalizar_papers(df: pd.DataFrame) -> pd.DataFrame:
    """Normaliza título, resumen y keywords una sola vez para la capa Silver."""
    df = df.copy()
    columnas_normalizadas = {
        "titulo": "titulo_normalizado",
        "resumen": "resumen_normalizado",
        "palabras_clave": "palabras_clave_normalizadas",
    }
    for campo, columna in columnas_normalizadas.items():
        df[columna] = df.apply(
            lambda fila: preprocess_text(
                fila.get(campo),
                language=fila.get("idioma") if fila.get("idioma") in ("es", "en") else "auto",
            ),
            axis=1,
        )
    df["texto_modelo"] = df[
        ["titulo_normalizado", "resumen_normalizado", "palabras_clave_normalizadas"]
    ].agg(" ".join, axis=1).str.replace(r"\s+", " ", regex=True).str.strip()
    return df


def procesar_papers(carpetas: Optional[list[str]] = None) -> pd.DataFrame:
    """Recorre ``PAPERS_DIR/<issn>/*.pdf`` y construye la capa Silver de artículos."""
    if not PAPERS_DIR.exists():
        logger.warning("No existe el directorio de papers: %s", PAPERS_DIR)
        return pd.DataFrame()

    carpetas_issn = sorted(p for p in PAPERS_DIR.iterdir() if p.is_dir())
    if carpetas:
        objetivo = set(carpetas)
        carpetas_issn = [p for p in carpetas_issn if p.name in objetivo]

    registros = []
    total_pdfs = 0
    for carpeta in carpetas_issn:
        issn = limpiar_issn(carpeta.name) or carpeta.name
        for pdf in sorted(carpeta.glob("*.pdf")):
            total_pdfs += 1
            try:
                articulos = extraer_articulos_pdf(pdf, issn)
                registros.extend(articulos)
                logger.info("  %s/%s: %d artículo(s) extraído(s)", carpeta.name, pdf.name, len(articulos))
            except Exception as e:
                logger.error("  ✗ Error procesando %s/%s: %s", carpeta.name, pdf.name, e, exc_info=True)

    if not registros:
        logger.warning("No se extrajo ningún artículo de %d PDFs revisados", total_pdfs)
        return pd.DataFrame()

    df = normalizar_papers(pd.DataFrame(registros))
    df["version_proceso"] = VERSION_PROCESO
    df["hash_articulo"] = df.apply(
        lambda r: hashlib.sha256(
            f"{r['issn_normalizado']}|{r['archivo']}|{r['articulo_id']}|{r['idioma']}".encode("utf-8")
        ).hexdigest()[:16],
        axis=1,
    )
    df = df.drop_duplicates(subset=["issn_normalizado", "archivo", "articulo_id", "idioma"])

    PAPERS_SILVER.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(PAPERS_SILVER, index=False)
    df.to_csv(PAPERS_SILVER_CSV, index=False, encoding="utf-8")
    logger.info("Silver papers: %d registros de %d PDFs -> %s", len(df), total_pdfs, PAPERS_SILVER)
    return df


def construir_gold_articulos(silver: Optional[pd.DataFrame] = None) -> pd.DataFrame:
    """Gold: un registro por artículo/idioma con título y tokens normalizados."""
    if silver is None:
        if not PAPERS_SILVER.exists():
            logger.warning("No existe silver de papers: %s", PAPERS_SILVER)
            return pd.DataFrame()
        silver = pd.read_parquet(PAPERS_SILVER)

    filas = []
    for _, fila in silver.iterrows():
        idioma = fila.get("idioma")
        normalizados = {
            campo: fila.get(f"{campo}_normalizado")
            for campo in ("titulo", "resumen", "palabras_clave")
        }
        if not any(normalizados.values()):
            lang_token = idioma if idioma in ("es", "en") else "auto"
            for campo in normalizados:
                normalizados[campo] = preprocess_text(fila.get(campo), language=lang_token)
        tokens = " ".join(str(valor) for valor in normalizados.values() if valor and not pd.isna(valor))
        filas.append({
            "issn_normalizado": fila["issn_normalizado"],
            "articulo_id": fila["articulo_id"],
            "archivo": fila["archivo"],
            "idioma": idioma,
            "titulo": fila.get("titulo"),
            "resumen": fila.get("resumen"),
            "palabras_clave": fila.get("palabras_clave"),
            "titulo_normalizado": normalizados["titulo"] or "",
            "resumen_normalizado": normalizados["resumen"] or "",
            "palabras_clave_normalizadas": normalizados["palabras_clave"] or "",
            "tokens_normalizados": tokens,
            "num_tokens": len(tokens.split()) if tokens else 0,
        })

    gold = pd.DataFrame(filas)
    gold = gold[gold["num_tokens"] > 0].reset_index(drop=True)

    ARTICULOS_GOLD.parent.mkdir(parents=True, exist_ok=True)
    gold.to_parquet(ARTICULOS_GOLD, index=False)
    gold.to_csv(ARTICULOS_GOLD_CSV, index=False, encoding="utf-8")
    logger.info("Gold artículos: %d registros -> %s", len(gold), ARTICULOS_GOLD)
    return gold


def construir_gold_revistas(gold_articulos: Optional[pd.DataFrame] = None) -> pd.DataFrame:
    """Gold: agrega todos los tokens normalizados de los artículos de cada revista (por ISSN)."""
    if gold_articulos is None:
        if not ARTICULOS_GOLD.exists():
            logger.warning("No existe gold de artículos: %s", ARTICULOS_GOLD)
            return pd.DataFrame()
        gold_articulos = pd.read_parquet(ARTICULOS_GOLD)

    filas = []
    for issn, grupo in gold_articulos.groupby("issn_normalizado"):
        tokens_totales = " ".join(t for t in grupo["tokens_normalizados"] if t)
        tokens_unicos = set(tokens_totales.split())
        filas.append({
            "issn_normalizado": issn,
            "num_articulos_procesados": len(grupo),
            "idiomas_detectados": ",".join(sorted(grupo["idioma"].dropna().unique())),
            "tokens_normalizados": tokens_totales,
            "num_tokens_unicos": len(tokens_unicos),
        })

    gold = pd.DataFrame(filas)
    REVISTA_TOKENS_GOLD.parent.mkdir(parents=True, exist_ok=True)
    gold.to_parquet(REVISTA_TOKENS_GOLD, index=False)
    gold.to_csv(REVISTA_TOKENS_GOLD_CSV, index=False, encoding="utf-8")
    logger.info("Gold revistas (tokens): %d revistas -> %s", len(gold), REVISTA_TOKENS_GOLD)
    return gold
