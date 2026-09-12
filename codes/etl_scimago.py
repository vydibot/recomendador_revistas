"""
ETL Scimago JR — Procesamiento de datos de Scimago Journal & Country Rank.

Lee el CSV bronze de Scimago (rankings de revistas colombianas),
normaliza campos, parsea categorías con cuartiles y genera un parquet
limpio en la capa silver.

Entrada:  data/bronze/scimagojr 2025 CO.csv   (~166 filas, 26 columnas, sep=';')
Salida:   data/silver/scimago_clean.parquet
"""

import logging
import re
import sys
from typing import Optional

import pandas as pd
import numpy as np

from config import (
    SCIMAGO_FILE,
    SCIMAGO_SILVER,
    FECHA_CAPTURA,
    CUARTIL_ORD,
)
from normalize import (
    limpiar_issn,
    normalizar_titulo,
    normalizar_pais,
    parsear_decimal_coma,
    hash_registro,
)

# ── Logging ────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s │ %(name)s │ %(levelname)s │ %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("etl_scimago")


# ═══════════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════════

def _parsear_issns(campo_issn: Optional[str]) -> tuple[Optional[str], Optional[str]]:
    """
    Divide el campo Issn de Scimago (puede contener múltiples ISSNs
    separados por ', ') y normaliza cada uno.

    Returns:
        (issn_print, issn_electronic) — el primero y el segundo ISSN
        normalizados.  Si solo hay uno, issn_electronic es None.
    """
    if pd.isna(campo_issn) or not str(campo_issn).strip():
        return None, None

    partes = [p.strip() for p in str(campo_issn).split(",")]
    normalizados = [limpiar_issn(p) for p in partes]

    issn_print = normalizados[0] if len(normalizados) >= 1 else None
    issn_electronic = normalizados[1] if len(normalizados) >= 2 else None

    return issn_print, issn_electronic


_RE_CAT_QUARTILE = re.compile(r"(.+?)\s*\(([Qq][1-4])\)")


def _parsear_categorias(campo_cat: Optional[str]) -> list[tuple[str, str]]:
    """
    Parsea el campo Categories de Scimago.

    Formato esperado: ``"Law (Q1); Sociology and Political Science (Q1)"``

    Returns:
        Lista de tuplas ``(categoria, cuartil)`` — e.g.
        ``[("Law", "Q1"), ("Sociology and Political Science", "Q1")]``
    """
    if pd.isna(campo_cat) or not str(campo_cat).strip():
        return []

    resultados = []
    for entrada in str(campo_cat).split(";"):
        entrada = entrada.strip()
        match = _RE_CAT_QUARTILE.match(entrada)
        if match:
            categoria = match.group(1).strip()
            cuartil = match.group(2).upper()
            resultados.append((categoria, cuartil))
        elif entrada:
            # Categoría sin cuartil explícito
            resultados.append((entrada, None))

    return resultados


def _mejor_cuartil(categorias: list[tuple[str, str]]) -> Optional[str]:
    """Determina el mejor cuartil de una lista de (categoría, cuartil)."""
    cuartiles = [q for _, q in categorias if q in CUARTIL_ORD]
    if not cuartiles:
        return None
    return max(cuartiles, key=lambda q: CUARTIL_ORD.get(q, 0))


def _parsear_areas(campo_areas: Optional[str]) -> list[str]:
    """Divide el campo Areas por '; ' y retorna lista limpia."""
    if pd.isna(campo_areas) or not str(campo_areas).strip():
        return []
    return [a.strip() for a in str(campo_areas).split(";") if a.strip()]


def _bool_yes_no(valor: Optional[str]) -> Optional[bool]:
    """Convierte 'Yes'/'No' a booleano."""
    if pd.isna(valor):
        return None
    v = str(valor).strip().lower()
    if v == "yes":
        return True
    if v == "no":
        return False
    return None


def _safe_int(valor) -> Optional[int]:
    """Convierte a entero de forma segura, manejando NaN y strings."""
    if pd.isna(valor):
        return None
    try:
        return int(float(str(valor).replace(",", ".")))
    except (ValueError, TypeError):
        return None


# ═══════════════════════════════════════════════════════════════════════════
# Pipeline principal
# ═══════════════════════════════════════════════════════════════════════════

def procesar_scimago() -> pd.DataFrame:
    """
    Procesa el CSV bronze de Scimago JR y retorna un DataFrame limpio.

    Pasos:
        1. Lectura del CSV con delimitador `;`
        2. Parsing de ISSNs (print / electronic)
        3. Normalización de título
        4. Conversión de campos numéricos (coma decimal → float)
        5. Conversión de campos enteros
        6. Parsing de categorías con cuartiles
        7. Parsing de áreas temáticas
        8. Conversión de booleanos (Open Access)
        9. Normalización de país a ISO
       10. Renombramiento de columnas
       11. Deduplicación por ISSN normalizado
       12. Adición de metadatos de trazabilidad

    Returns:
        DataFrame listo para guardar como parquet.
    """
    # ── 1. Lectura ─────────────────────────────────────────────────────────
    logger.info("Leyendo CSV bronze: %s", SCIMAGO_FILE)

    df = pd.read_csv(
        SCIMAGO_FILE,
        sep=";",
        encoding="utf-8",
        dtype=str,            # leer todo como string para control total
        keep_default_na=True,
    )

    filas_entrada = len(df)
    logger.info("Filas leídas: %d | Columnas: %d", filas_entrada, len(df.columns))

    # Eliminar columna Publisher duplicada (Scimago repite Publisher en col 6 y 23)
    # pandas las renombra automáticamente a 'Publisher' y 'Publisher.1'
    if "Publisher.1" in df.columns:
        df = df.drop(columns=["Publisher.1"])
        logger.info("Columna Publisher duplicada eliminada (Publisher.1)")

    # ── 2. Parsing de ISSNs ────────────────────────────────────────────────
    logger.info("Parseando ISSNs...")
    issn_parsed = df["Issn"].apply(_parsear_issns)
    df["issn_print"] = issn_parsed.apply(lambda x: x[0])
    df["issn_electronic"] = issn_parsed.apply(lambda x: x[1])
    df["issn_normalizado"] = df["issn_print"].combine_first(df["issn_electronic"])

    issns_nulos = df["issn_normalizado"].isna().sum()
    logger.info(
        "ISSNs: print=%d | electronic=%d | normalizado nulos=%d",
        df["issn_print"].notna().sum(),
        df["issn_electronic"].notna().sum(),
        issns_nulos,
    )

    # ── 3. Normalización de título ─────────────────────────────────────────
    logger.info("Normalizando títulos...")
    df["titulo_normalizado"] = df["Title"].apply(normalizar_titulo)

    titulos_nulos = df["titulo_normalizado"].isna().sum()
    logger.info("Títulos normalizados: nulos=%d", titulos_nulos)

    # ── 4. Campos numéricos con coma decimal ───────────────────────────────
    logger.info("Convirtiendo campos numéricos (coma decimal)...")
    columnas_decimal = {
        "SJR": "sjr_score",
        "Citations / Doc. (2years)": "citas_por_doc_2y",
        "Ref. / Doc.": "refs_por_doc",
        "%Female": "pct_female_raw",
    }
    for col_orig, col_nuevo in columnas_decimal.items():
        df[col_nuevo] = df[col_orig].apply(parsear_decimal_coma)
        nulos = df[col_nuevo].isna().sum()
        logger.info("  %s → %s: nulos=%d", col_orig, col_nuevo, nulos)

    # ── 5. Campos enteros ──────────────────────────────────────────────────
    logger.info("Convirtiendo campos enteros...")
    columnas_enteras = {
        "Rank": "rank_scimago",
        "H index": "h_index",
        "Total Docs. (2025)": "total_docs",
        "Total Docs. (3years)": "total_docs_3y",
        "Total Refs.": "total_refs",
        "Total Citations (3years)": "total_citas_3y",
        "Citable Docs. (3years)": "docs_citables_3y",
        "Overton": "overton",
    }
    for col_orig, col_nuevo in columnas_enteras.items():
        df[col_nuevo] = df[col_orig].apply(_safe_int)
        nulos = df[col_nuevo].isna().sum()
        logger.info("  %s → %s: nulos=%d", col_orig, col_nuevo, nulos)

    # ── 6. Parsing de categorías y cuartil ─────────────────────────────────
    logger.info("Parseando categorías Scimago...")
    df["categorias_parsed"] = df["Categories"].apply(_parsear_categorias)
    df["mejor_cuartil"] = df["categorias_parsed"].apply(_mejor_cuartil)

    # Usar el mejor cuartil del campo parseado; fallback a SJR Best Quartile
    df["cuartil_sjr"] = df["mejor_cuartil"].combine_first(
        df["SJR Best Quartile"].str.strip().str.upper()
    )
    df["cuartil_sjr_ord"] = df["cuartil_sjr"].map(CUARTIL_ORD)

    # Convertir lista de tuplas a formato serializable para parquet
    df["categorias_scimago"] = df["categorias_parsed"].apply(
        lambda cats: "; ".join(f"{c} ({q})" if q else c for c, q in cats) if cats else None
    )

    cuartiles_nulos = df["cuartil_sjr"].isna().sum()
    logger.info(
        "Cuartiles: distribución=%s | nulos=%d",
        df["cuartil_sjr"].value_counts().to_dict(),
        cuartiles_nulos,
    )

    # ── 7. Parsing de áreas ────────────────────────────────────────────────
    logger.info("Parseando áreas temáticas...")
    df["areas_parsed"] = df["Areas"].apply(_parsear_areas)
    df["areas_scimago"] = df["areas_parsed"].apply(
        lambda areas: "; ".join(areas) if areas else None
    )

    # ── 8. Booleanos (Open Access) ─────────────────────────────────────────
    logger.info("Convirtiendo campos booleanos...")
    df["open_access"] = df["Open Access"].apply(_bool_yes_no)
    df["oa_diamond"] = df["Open Access Diamond"].apply(_bool_yes_no)

    oa_true = df["open_access"].sum()
    diamond_true = df["oa_diamond"].sum()
    logger.info("Open Access: yes=%d | Diamond OA: yes=%d", oa_true, diamond_true)

    # ── 9. %Female a proporción decimal ────────────────────────────────────
    logger.info("Convirtiendo %%Female a proporción decimal...")
    df["pct_female"] = df["pct_female_raw"].apply(
        lambda x: x / 100.0 if pd.notna(x) and x > 1 else x
    )

    # ── 10. País ISO ───────────────────────────────────────────────────────
    logger.info("Normalizando país...")
    df["pais_iso"] = df["Country"].apply(normalizar_pais)

    # ── 11. Renombramiento y selección de columnas ─────────────────────────
    logger.info("Renombrando columnas...")
    columnas_finales = {
        "rank_scimago": "rank_scimago",
        "Sourceid": "sourceid",
        "Title": "titulo",
        "Type": "tipo_publicacion",
        "issn_print": "issn_print",
        "issn_electronic": "issn_electronic",
        "issn_normalizado": "issn_normalizado",
        "titulo_normalizado": "titulo_normalizado",
        "Publisher": "editorial",
        "open_access": "open_access",
        "oa_diamond": "oa_diamond",
        "sjr_score": "sjr_score",
        "cuartil_sjr": "cuartil_sjr",
        "cuartil_sjr_ord": "cuartil_sjr_ord",
        "h_index": "h_index",
        "total_docs": "total_docs",
        "total_docs_3y": "total_docs_3y",
        "total_refs": "total_refs",
        "total_citas_3y": "total_citas_3y",
        "docs_citables_3y": "docs_citables_3y",
        "citas_por_doc_2y": "citas_por_doc_2y",
        "refs_por_doc": "refs_por_doc",
        "pct_female": "pct_female",
        "overton": "overton",
        "pais_iso": "pais_iso",
        "Region": "region",
        "Coverage": "cobertura",
        "categorias_scimago": "categorias_scimago",
        "areas_scimago": "areas_scimago",
    }

    # Seleccionar y renombrar
    df_clean = df[list(columnas_finales.keys())].rename(columns=columnas_finales)

    # ── 12. Deduplicación ──────────────────────────────────────────────────
    antes_dedup = len(df_clean)
    df_clean = df_clean.drop_duplicates(subset=["issn_normalizado"], keep="first")
    # También eliminar filas sin ISSN normalizado (no son enlazables)
    sin_issn = df_clean["issn_normalizado"].isna().sum()
    despues_dedup = len(df_clean)
    logger.info(
        "Deduplicación por issn_normalizado: %d → %d filas (-%d duplicados, %d sin ISSN)",
        antes_dedup,
        despues_dedup,
        antes_dedup - despues_dedup,
        sin_issn,
    )

    # ── 13. Metadatos de trazabilidad ──────────────────────────────────────
    logger.info("Agregando metadatos de trazabilidad...")
    df_clean["_fuente"] = "scimago"
    df_clean["_fecha_captura"] = FECHA_CAPTURA
    df_clean["_estado_calidad"] = "normalizado"
    df_clean["_hash_registro"] = df_clean.apply(hash_registro, axis=1)

    # ── 14. Resumen final ──────────────────────────────────────────────────
    logger.info("═" * 60)
    logger.info("RESUMEN ETL SCIMAGO")
    logger.info("═" * 60)
    logger.info("  Filas entrada (bronze) : %d", filas_entrada)
    logger.info("  Filas salida  (silver) : %d", len(df_clean))
    logger.info("  Columnas               : %d", len(df_clean.columns))
    logger.info("  ISSNs nulos            : %d", df_clean["issn_normalizado"].isna().sum())
    logger.info("  Títulos nulos          : %d", df_clean["titulo_normalizado"].isna().sum())
    logger.info("  SJR nulos              : %d", df_clean["sjr_score"].isna().sum())
    logger.info("  Cuartil nulos          : %d", df_clean["cuartil_sjr"].isna().sum())
    logger.info(
        "  Open Access            : %d / %d",
        df_clean["open_access"].sum(),
        len(df_clean),
    )
    logger.info(
        "  Diamond OA             : %d / %d",
        df_clean["oa_diamond"].sum(),
        len(df_clean),
    )
    logger.info(
        "  Cuartiles              : %s",
        df_clean["cuartil_sjr"].value_counts().to_dict(),
    )
    logger.info(
        "  Áreas únicas           : %d",
        df_clean["areas_scimago"].nunique(),
    )
    logger.info("═" * 60)

    # El orquestador importa y llama esta función directamente; guardar aquí
    # evita que Scimago solo se escriba cuando se ejecuta este módulo como CLI.
    SCIMAGO_SILVER.parent.mkdir(parents=True, exist_ok=True)
    df_clean.to_parquet(SCIMAGO_SILVER, index=False, engine="pyarrow")
    logger.info("Parquet Scimago guardado: %s", SCIMAGO_SILVER)

    return df_clean


# ═══════════════════════════════════════════════════════════════════════════
# Punto de entrada
# ═══════════════════════════════════════════════════════════════════════════

def main() -> None:
    """Ejecuta el pipeline ETL de Scimago y guarda el resultado en parquet."""
    logger.info("Iniciando ETL Scimago...")

    df = procesar_scimago()

    # Guardar parquet
    SCIMAGO_SILVER.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(SCIMAGO_SILVER, index=False, engine="pyarrow")
    logger.info("Parquet guardado: %s (%d filas)", SCIMAGO_SILVER, len(df))

    logger.info("ETL Scimago completado exitosamente.")


if __name__ == "__main__":
    main()
