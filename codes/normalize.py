"""
Funciones de normalización, limpieza, imputación y feature engineering.

Módulo transversal para:
- Normalización y validación de ISSN (checksum módulo 11).
- Normalización y similitud de títulos (sin diacríticos, stopwords ni puntuación).
- Normalización de países a códigos ISO 3166-1 alpha-2.
- Manejo de monedas, conversión a USD y Paridad de Poder Adquisitivo (PPP USD).
- Detección de outliers en APC mediante umbral de 3 rangos intercuartílicos (3 * IQR).
- Imputación condicional de APC vía regresión multivariable con fallback a estrato cuartil-disciplina.
- Estandarización de variables continuas (Z-Score y Min-Max [0, 1]).
- Codificación ordinal, contraste Publindex vs Scimago, flags binarios y One-Hot Encoding.
- Hashing y trazabilidad de registros.
"""

import hashlib
import logging
import re
import unicodedata
from typing import Optional, Union

import numpy as np
import pandas as pd

try:
    from unidecode import unidecode
except ImportError:
    def unidecode(text: str) -> str:
        nfkd = unicodedata.normalize("NFKD", text)
        return "".join(c for c in nfkd if not unicodedata.combining(c))

try:
    from rapidfuzz import fuzz
except ImportError:
    fuzz = None

from config import (
    CATEGORIAS_PUBLINDEX,
    CUARTIL_ORD,
    FACTORES_PPP,
    IQR_FACTOR,
    PAISES_ISO,
    PAISES_LMIC,
    TASAS_USD,
    VERSION_PROCESO,
)

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════
# 1. PARSING DE FORMATOS Y NÚMEROS
# ═══════════════════════════════════════════════════════════════════════════

def parsear_numero_es_en(valor: Optional[Union[str, int, float]]) -> Optional[float]:
    """
    Parsea cadenas numéricas reconociendo tanto formato en español (coma decimal)
    como inglés (punto decimal), manejando separadores de miles y espacios.

    Ejemplos:
        '0,914' -> 0.914
        '1.500,50' -> 1500.50
        '1,500.50' -> 1500.50
        '1050' -> 1050.0
    """
    if pd.isna(valor) or valor is None:
        return None
    if isinstance(valor, (int, float)):
        return float(valor)

    s = str(valor).strip()
    if not s or s.lower() in {"nan", "none", "null", "na", ""}:
        return None

    # Eliminar símbolos monetarios o caracteres extraños excepto dígitos, comas, puntos y signos
    s = re.sub(r"[^\d.,\-+]", "", s)
    if not s:
        return None

    # Caso con ambos separadores (punto y coma)
    if "." in s and "," in s:
        if s.rfind(",") > s.rfind("."):
            # Coma es decimal (ej. 1.234,56)
            s = s.replace(".", "").replace(",", ".")
        else:
            # Punto es decimal (ej. 1,234.56)
            s = s.replace(",", "")
    elif "," in s:
        # Solo coma: si tiene exactamente 3 dígitos tras la coma y longitud > 4 podría ser miles,
        # pero en contexto de métricas bibliométricas / APC (0,914 o 1500,0) suele ser decimal.
        partes = s.split(",")
        if len(partes) == 2 and len(partes[1]) in (1, 2, 4, 5, 6):
            s = s.replace(",", ".")
        elif len(partes) == 2 and len(partes[1]) == 3 and len(partes[0]) <= 3 and int(partes[0]) > 0:
            # Podría ser 1,050 (mil cincuenta) o 0,123. Si parte entera es 0 es decimal.
            if partes[0] == "0":
                s = "0." + partes[1]
            else:
                # Comprobar si parece decimal o entero
                s = s.replace(",", ".")
        else:
            s = s.replace(",", ".")

    try:
        return float(s)
    except (ValueError, TypeError):
        return None


def parsear_decimal_coma(valor: Optional[Union[str, int, float]]) -> Optional[float]:
    """Convierte un valor con posible coma decimal a float."""
    return parsear_numero_es_en(valor)


# ═══════════════════════════════════════════════════════════════════════════
# 2. NORMALIZACIÓN Y VALIDACIÓN DE ISSN
# ═══════════════════════════════════════════════════════════════════════════

def limpiar_issn(valor: Optional[str]) -> Optional[str]:
    """
    Normaliza un ISSN a formato estándar XXXX-XXXX con mayúsculas.
    Elimina prefijos ('ISSN:', 'eISSN:', 'E-ISSN:'), espacios y guiones redundantes.
    Retorna None si el valor es nulo o no contiene exactamente 8 caracteres alfanuméricos válidos.
    """
    if pd.isna(valor) or not valor:
        return None

    s = str(valor).strip().upper()
    for prefijo in ["ISSN:", "EISSN:", "E-ISSN:", "ISSN", "EISSN", "P-ISSN:", "P-ISSN"]:
        s = s.replace(prefijo, "")

    limpio = re.sub(r"[^0-9X]", "", s)
    if len(limpio) != 8:
        return None

    return f"{limpio[:4]}-{limpio[4:]}"


def validar_issn_checksum(issn: Optional[str]) -> bool:
    """
    Valida el dígito de control de un ISSN según el algoritmo módulo 11 de la ISO 3297.
    """
    if not issn:
        return False

    limpio = issn.replace("-", "").strip().upper()
    if len(limpio) != 8:
        return False

    pesos = [8, 7, 6, 5, 4, 3, 2]
    try:
        suma = sum(int(d) * p for d, p in zip(limpio[:7], pesos))
    except ValueError:
        return False

    ultimo = limpio[7]
    check = 10 if ultimo == "X" else int(ultimo) if ultimo.isdigit() else -1
    return (suma + check) % 11 == 0


def obtener_issn_canonico(
    issn_print: Optional[str],
    issn_electronic: Optional[str],
    issn_linking: Optional[str] = None,
) -> Optional[str]:
    """
    Retorna un ISSN canónico siguiendo el orden de precedencia estándar:
    ISSN-L (linking) > ISSN impreso > ISSN electrónico.
    """
    for issn in [issn_linking, issn_print, issn_electronic]:
        normalizado = limpiar_issn(issn)
        if normalizado:
            return normalizado
    return None


# ═══════════════════════════════════════════════════════════════════════════
# 3. NORMALIZACIÓN Y SIMILITUD DE TÍTULOS
# ═══════════════════════════════════════════════════════════════════════════

_STOPWORDS_TITULO = {
    "revista", "de", "del", "la", "las", "los", "el", "en", "y", "e",
    "journal", "of", "the", "and", "for", "in", "on", "a", "an",
    "international", "review", "annals", "proceedings", "bulletin",
    "research", "studies", "transactions", "cuadernos", "boletin",
    "acta", "actas",
}


def normalizar_titulo(titulo: Optional[str]) -> Optional[str]:
    """
    Normaliza el título de una revista para comparación y cruce:
    - Conversión a minúsculas
    - Remoción de caracteres diacríticos (acentos, tildes, diéresis)
    - Remoción de puntuación y símbolos no alfanuméricos
    - Remoción de stopwords editoriales comunes
    - Colapso de espacios múltiples
    """
    if pd.isna(titulo) or not titulo:
        return None

    t = str(titulo).strip().lower()
    t = unidecode(t)
    t = re.sub(r"[^\w\s]", " ", t)
    palabras = [p for p in t.split() if p not in _STOPWORDS_TITULO and len(p) > 0]
    resultado = " ".join(palabras).strip()
    return resultado if resultado else None


def similitud_titulos(titulo_a: Optional[str], titulo_b: Optional[str]) -> float:
    """
    Calcula la similitud entre dos títulos normalizados en escala 0-100.
    """
    if not titulo_a or not titulo_b:
        return 0.0

    a = normalizar_titulo(titulo_a)
    b = normalizar_titulo(titulo_b)
    if not a or not b:
        return 0.0
    if a == b:
        return 100.0

    if fuzz is not None:
        return float(fuzz.WRatio(a, b))

    # Fallback mediante Jaccard token overlap
    set_a = set(a.split())
    set_b = set(b.split())
    if not set_a or not set_b:
        return 0.0
    interseccion = set_a & set_b
    union = set_a | set_b
    return 100.0 * len(interseccion) / len(union)


# ═══════════════════════════════════════════════════════════════════════════
# 4. NORMALIZACIÓN DE PAÍSES
# ═══════════════════════════════════════════════════════════════════════════

def normalizar_pais(pais: Optional[str]) -> Optional[str]:
    """
    Convierte el nombre o abreviatura de un país a código ISO 3166-1 alpha-2 en mayúsculas.
    """
    if pd.isna(pais) or not pais:
        return None

    clave = str(pais).strip().lower()
    clave = unidecode(clave)

    # Si ya es un código de 2 letras ISO válido
    if len(clave) == 2 and clave.upper() in set(PAISES_ISO.values()):
        return clave.upper()

    if clave in PAISES_ISO:
        return PAISES_ISO[clave]

    return clave.upper()[:2] if len(clave) == 2 else None


# ═══════════════════════════════════════════════════════════════════════════
# 5. MANEJO DE MONEDAS, USD Y PPP (ASEQUIBILIDAD)
# ═══════════════════════════════════════════════════════════════════════════

def parsear_apc_doaj(apc_amount_str: Optional[str]) -> tuple[Optional[float], Optional[str]]:
    """
    Extrae monto y código de divisa del campo de texto de APC en DOAJ.
    Retorna (monto, codigo_moneda).
    """
    if pd.isna(apc_amount_str) or not apc_amount_str:
        return None, None

    texto = str(apc_amount_str).strip()
    # Buscar patrones de divisa de 3 letras (USD, EUR, GBP, COP, BRL, etc.)
    letras = re.findall(r"\b[A-Z]{3}\b", texto.upper())
    moneda = letras[0] if letras else None

    # Extraer parte numérica
    num_match = re.findall(r"[\d.,]+", texto)
    monto = None
    if num_match:
        monto = parsear_numero_es_en(num_match[0])

    # Si no se detectó divisa pero hay monto, asignar USD por defecto si contiene '$'
    if not moneda and "$" in texto:
        moneda = "USD"

    return monto, moneda


def convertir_a_usd(monto: Optional[float], moneda: Optional[str]) -> tuple[Optional[float], Optional[float]]:
    """
    Convierte un monto en moneda local a USD según la tabla de tasas de cambio.
    Retorna tupla (monto_usd, tasa_utilizada).
    """
    if monto is None or pd.isna(monto):
        return None, None

    if moneda is None or pd.isna(moneda):
        # Si no hay moneda especificada pero hay monto, asumimos USD con tasa 1.0
        return round(float(monto), 2), 1.0

    moneda_clean = str(moneda).strip().upper()
    tasa = TASAS_USD.get(moneda_clean)
    if tasa is None:
        logger.warning("Moneda '%s' no encontrada en tabla de tasas de cambio", moneda_clean)
        return None, None

    monto_usd = round(float(monto) * tasa, 2)
    return monto_usd, tasa


def convertir_a_ppp_usd(monto_usd: Optional[float], pais_iso: Optional[str]) -> Optional[float]:
    """
    Transforma un monto en USD a su equivalente en Paridad de Poder Adquisitivo (PPP USD).
    Permite evaluar la asequibilidad relativa del APC según el nivel de precios del país editor:
        apc_ppp_usd = monto_usd / factor_ppp
    """
    if monto_usd is None or pd.isna(monto_usd):
        return None

    if not pais_iso or pd.isna(pais_iso):
        factor = FACTORES_PPP.get("DEFAULT", 1.0)
    else:
        pais_clean = str(pais_iso).strip().upper()
        factor = FACTORES_PPP.get(pais_clean, FACTORES_PPP.get("DEFAULT", 1.0))

    if factor <= 0:
        factor = 1.0

    return round(float(monto_usd) / factor, 2)


# ═══════════════════════════════════════════════════════════════════════════
# 6. DETECCIÓN DE OUTLIERS DE APC (3 * IQR)
# ═══════════════════════════════════════════════════════════════════════════

def detectar_outliers_apc(
    df: pd.DataFrame,
    columna_apc: str = "apc_monto_usd",
    iqr_factor: float = IQR_FACTOR,
    grupo_cols: Optional[list[str]] = None,
) -> pd.Series:
    """
    Detecta cobros de APC atípicos mediante el umbral de 3 rangos intercuartílicos (3 * IQR)
    según la especificación de la Sección 8.1.2.

    Retorna una Serie booleana donde True indica un valor atípico extremo.
    """
    if columna_apc not in df.columns:
        return pd.Series(False, index=df.index)

    resultado = pd.Series(False, index=df.index)
    valores = df[columna_apc]

    if grupo_cols and all(c in df.columns for c in grupo_cols):
        for _, grupo in df.groupby(grupo_cols, dropna=False):
            vals = grupo[columna_apc].dropna()
            if len(vals) < 5:
                continue
            q1 = vals.quantile(0.25)
            q3 = vals.quantile(0.75)
            iqr = q3 - q1
            if iqr == 0:
                continue
            lower = max(0.0, q1 - iqr_factor * iqr)
            upper = q3 + iqr_factor * iqr
            mask = (valores.loc[grupo.index] < lower) | (valores.loc[grupo.index] > upper)
            resultado.loc[grupo.index] = mask
    else:
        vals = valores.dropna()
        if len(vals) >= 5:
            q1 = vals.quantile(0.25)
            q3 = vals.quantile(0.75)
            iqr = q3 - q1
            lower = max(0.0, q1 - iqr_factor * iqr)
            upper = q3 + iqr_factor * iqr
            resultado = (valores < lower) | (valores > upper)

    return resultado.fillna(False)


# ═══════════════════════════════════════════════════════════════════════════
# 7. IMPUTACIÓN CONDICIONAL DE APC (REGRESIÓN & ESTRATOS)
# ═══════════════════════════════════════════════════════════════════════════

def calcular_concentracion_mercado(df: pd.DataFrame, col_editorial: str = "editorial") -> pd.Series:
    """
    Calcula la cuota de mercado / concentración por editorial (proporción de revistas).
    """
    if col_editorial not in df.columns:
        return pd.Series(0.0, index=df.index)

    conteos = df[col_editorial].fillna("Desconocida").value_counts(normalize=True)
    return df[col_editorial].fillna("Desconocida").map(conteos).fillna(0.0)


def imputar_apc(
    df: pd.DataFrame,
    col_apc: str = "apc_monto_usd",
    col_editorial: str = "editorial",
    col_area: str = "gran_area",
    col_cuartil: str = "cuartil_sjr",
    col_hibrido: str = "is_hybrid",
) -> pd.DataFrame:
    """
    Imputación condicional de APC faltantes según la Sección 8.1.2:
    1. Ensayo de modelo de regresión multivariable con:
       - Cuartil SJR (ordinal)
       - Concentración de mercado editorial / cuota de mercado
       - Modelo híbrido vs gold
       - Disciplina / Gran Área
    2. Evaluación de estabilidad del modelo (predicciones consistentes >= 0, R^2 o datos suficientes).
    3. Si el modelo no resulta estable, se aplica la mediana por estrato cuartil-disciplina.
    4. Fallbacks jerárquicos por disciplina o cuartil si faltan estratos.
    5. Asignación de la variable binaria 'apc_imputado' (distingue observado/declarado vs imputado).
    """
    df = df.copy()

    # Inicializar columnas de control
    if "apc_imputado" not in df.columns:
        df["apc_imputado"] = df[col_apc].isna()
    else:
        df["apc_imputado"] = df["apc_imputado"].fillna(df[col_apc].isna()).astype(bool)

    if "apc_tipo" not in df.columns:
        df["apc_tipo"] = np.where(df[col_apc].notna(), "declarado", "imputado")
    else:
        tipo_por_defecto = pd.Series(
            np.where(df[col_apc].notna(), "declarado", "imputado"),
            index=df.index,
        )
        df["apc_tipo"] = df["apc_tipo"].fillna(tipo_por_defecto)

    if "apc_metodo_imputacion" not in df.columns:
        df["apc_metodo_imputacion"] = None

    faltantes = df[col_apc].isna()
    if not faltantes.any():
        logger.info("No hay valores de APC faltantes para imputar.")
        return df

    logger.info("Iniciando imputación condicional de APC para %d registros faltantes...", faltantes.sum())

    # Preparar variables predictoras
    cuartil_num = df[col_cuartil].map(CUARTIL_ORD).fillna(2.0) if col_cuartil in df.columns else pd.Series(2.0, index=df.index)
    concentracion = calcular_concentracion_mercado(df, col_editorial)
    hibrido_num = (
        df[col_hibrido].fillna(False).astype(float)
        if col_hibrido in df.columns
        else pd.Series(0.0, index=df.index)
    )

    # Intentar regresión si hay suficientes datos observados (> 15 registros con APC)
    observados_mask = df[col_apc].notna() & (df[col_apc] > 0)
    modelo_estable = False

    if observados_mask.sum() >= 15:
        try:
            # Construir matriz de diseño X
            X_df = pd.DataFrame({
                "cuartil": cuartil_num,
                "concentracion": concentracion,
                "hibrido": hibrido_num,
            }, index=df.index)

            # Agregar dummies de gran área si existe
            if col_area in df.columns:
                area_dummies = pd.get_dummies(df[col_area].fillna("Otra"), prefix="area", drop_first=True, dtype=float)
                X_df = pd.concat([X_df, area_dummies], axis=1)

            X_train = X_df.loc[observados_mask].values
            y_train = df.loc[observados_mask, col_apc].values

            # Añadir columna de sesgo (intercepto)
            X_train_bias = np.c_[np.ones(X_train.shape[0]), X_train]
            X_pred_bias = np.c_[np.ones(X_df.shape[0]), X_df.values]

            # Regresión Ridge regularizada (lambda = 1.0) para garantizar estabilidad numérica
            alpha = 1.0
            I = np.eye(X_train_bias.shape[1])
            I[0, 0] = 0.0  # No regularizar el intercepto
            beta = np.linalg.solve(X_train_bias.T @ X_train_bias + alpha * I, X_train_bias.T @ y_train)

            # Predicciones
            preds = X_pred_bias @ beta

            # Validar estabilidad: predicciones razonables (> 0 y < 20,000 USD)
            preds_faltantes = preds[faltantes]
            if (preds_faltantes > 0).all() and (preds_faltantes < 20_000).all():
                df.loc[faltantes, col_apc] = np.round(preds[faltantes], 2)
                df.loc[faltantes, "apc_imputado"] = True
                df.loc[faltantes, "apc_tipo"] = "imputado"
                df.loc[faltantes, "apc_metodo_imputacion"] = "regresion_condicional"
                modelo_estable = True
                logger.info("Imputación por regresión condicional completada con éxito.")
        except Exception as e:
            logger.warning("Modelo de regresión no convergió o inestable: %s. Aplicando fallback.", e)
            modelo_estable = False

    # Fallback estratificado si la regresión no fue estable o faltan registros
    faltantes = df[col_apc].isna()
    if faltantes.any():
        logger.info("Aplicando imputación por estrato cuartil-disciplina...")

        # Nivel 1: Mediana por estrato (cuartil + disciplina)
        if col_cuartil in df.columns and col_area in df.columns:
            medianas_estrato = df.groupby([col_cuartil, col_area])[col_apc].transform("median")
            mask = faltantes & medianas_estrato.notna() & (medianas_estrato > 0)
            df.loc[mask, col_apc] = medianas_estrato[mask]
            df.loc[mask, "apc_imputado"] = True
            df.loc[mask, "apc_tipo"] = "imputado"
            df.loc[mask, "apc_metodo_imputacion"] = "mediana_estrato_cuartil_disciplina"
            faltantes = df[col_apc].isna()

        # Nivel 2: Mediana por disciplina
        if col_area in df.columns and faltantes.any():
            medianas_area = df.groupby(col_area)[col_apc].transform("median")
            mask = faltantes & medianas_area.notna() & (medianas_area > 0)
            df.loc[mask, col_apc] = medianas_area[mask]
            df.loc[mask, "apc_imputado"] = True
            df.loc[mask, "apc_tipo"] = "imputado"
            df.loc[mask, "apc_metodo_imputacion"] = "mediana_disciplina"
            faltantes = df[col_apc].isna()

        # Nivel 3: Mediana por cuartil
        if col_cuartil in df.columns and faltantes.any():
            medianas_cuartil = df.groupby(col_cuartil)[col_apc].transform("median")
            mask = faltantes & medianas_cuartil.notna() & (medianas_cuartil > 0)
            df.loc[mask, col_apc] = medianas_cuartil[mask]
            df.loc[mask, "apc_imputado"] = True
            df.loc[mask, "apc_tipo"] = "imputado"
            df.loc[mask, "apc_metodo_imputacion"] = "mediana_cuartil"
            faltantes = df[col_apc].isna()

        # Nivel 4: Mediana por editorial
        if col_editorial in df.columns and faltantes.any():
            medianas_ed = df.groupby(col_editorial)[col_apc].transform("median")
            mask = faltantes & medianas_ed.notna() & (medianas_ed > 0)
            df.loc[mask, col_apc] = medianas_ed[mask]
            df.loc[mask, "apc_imputado"] = True
            df.loc[mask, "apc_tipo"] = "imputado"
            df.loc[mask, "apc_metodo_imputacion"] = "mediana_editorial"
            faltantes = df[col_apc].isna()

    return df


# ═══════════════════════════════════════════════════════════════════════════
# 8. ESTANDARIZACIÓN Y ESCALAMIENTO (Z-SCORE & MIN-MAX)
# ═══════════════════════════════════════════════════════════════════════════

def estandarizar_zscore(
    df: pd.DataFrame,
    columnas: list[str],
    sufijo: str = "_zscore",
) -> pd.DataFrame:
    """
    Estandariza columnas continuas mediante Z-score: Z = (x - media) / std.
    Requerido para análisis de componentes principales (PCA), distancias y clustering.
    """
    df = df.copy()
    for col in columnas:
        if col in df.columns:
            s = pd.to_numeric(df[col], errors="coerce")
            media = s.mean()
            std = s.std()
            if pd.notna(std) and std > 0:
                df[f"{col}{sufijo}"] = ((s - media) / std).round(4)
            else:
                df[f"{col}{sufijo}"] = 0.0
    return df


def escalar_minmax(
    df: pd.DataFrame,
    columnas: list[str],
    sufijo: str = "_minmax",
) -> pd.DataFrame:
    """
    Escala columnas continuas al intervalo cerrado [0, 1]: X_norm = (x - min) / (max - min).
    Requerido para visualización, dashboards y puntajes interpretables.
    """
    df = df.copy()
    for col in columnas:
        if col in df.columns:
            s = pd.to_numeric(df[col], errors="coerce")
            min_val = s.min()
            max_val = s.max()
            if pd.notna(min_val) and pd.notna(max_val) and max_val > min_val:
                df[f"{col}{sufijo}"] = ((s - min_val) / (max_val - min_val)).round(4)
            else:
                df[f"{col}{sufijo}"] = 0.0
    return df


# ═══════════════════════════════════════════════════════════════════════════
# 9. VARIABLES BINARIAS, ORDINALES Y ONE-HOT ENCODING
# ═══════════════════════════════════════════════════════════════════════════

def calcular_variables_binarias(df: pd.DataFrame) -> pd.DataFrame:
    """
    Genera las variables binarias requeridas en la Sección 8.1.2:
    - exencion_apc_lmic: Exención de APC para países de ingresos bajos o medios.
    - oa_diamond: Acceso diamante (acceso abierto sin cobro de APC).
    - revision_abierta: Revisión por pares abierta (Open Peer Review).
    - indexada_doaj: Indexación verificada en DOAJ.
    - es_colombiana: Revista con país de origen Colombia (CO).
    """
    df = df.copy()

    # 1. Acceso Diamante (OA sin APC)
    tiene_apc = df["tiene_apc"].fillna(False) if "tiene_apc" in df.columns else pd.Series(False, index=df.index)
    oa = df["open_access"].fillna(False) if "open_access" in df.columns else pd.Series(False, index=df.index)
    oa_prev = df["oa_diamond"].fillna(False) if "oa_diamond" in df.columns else pd.Series(False, index=df.index)
    apc_monto = pd.to_numeric(df["apc_monto_usd"], errors="coerce").fillna(0.0) if "apc_monto_usd" in df.columns else pd.Series(0.0, index=df.index)
    df["oa_diamond"] = (oa | oa_prev) & (~tiene_apc | (apc_monto == 0))

    # 2. Exención de APC para países LMIC
    politica_exencion = df["politica_exencion"].fillna(False) if "politica_exencion" in df.columns else pd.Series(False, index=df.index)
    pais_iso = df["pais_iso"].fillna("") if "pais_iso" in df.columns else pd.Series("", index=df.index)
    df["exencion_apc_lmic"] = politica_exencion | pais_iso.isin(PAISES_LMIC)

    # 3. Revisión abierta (Open Peer Review)
    tipo_rev = df["tipo_revision"].fillna("").astype(str).str.lower() if "tipo_revision" in df.columns else pd.Series("", index=df.index)
    df["revision_abierta"] = tipo_rev.str.contains("open", regex=False) | tipo_rev.str.contains("abierta", regex=False)

    # 4. Indexación en DOAJ
    if "_fuentes" in df.columns:
        df["indexada_doaj"] = df["_fuentes"].apply(
            lambda f: "doaj" in f if isinstance(f, (list, set)) else ("doaj" in str(f).lower())
        )
    elif "url_doaj" in df.columns:
        df["indexada_doaj"] = df["url_doaj"].notna()
    else:
        df["indexada_doaj"] = False

    # 5. Revista Colombiana
    df["es_colombiana"] = pais_iso == "CO"

    return df


def codificar_ordinal_y_contraste(df: pd.DataFrame) -> pd.DataFrame:
    """
    Codifica cuartiles SJR y categorías Publindex como atributos ordinales:
        Q1=4, Q2=3, Q3=2, Q4=1
        A1=4, A2=3, B=2, C=1
    Calcula además la brecha/contraste entre la categoría nacional y el cuartil internacional.
    """
    df = df.copy()

    if "cuartil_sjr" in df.columns:
        df["cuartil_sjr_ord"] = df["cuartil_sjr"].map(CUARTIL_ORD).fillna(0).astype(int)

    if "categoria_publindex" in df.columns:
        df["categoria_publindex_ord"] = (
            df["categoria_publindex"].map(CATEGORIAS_PUBLINDEX).fillna(0).astype(int)
        )

    # Contraste / Brecha entre Publindex y Scimago
    if "categoria_publindex_ord" in df.columns and "cuartil_sjr_ord" in df.columns:
        df["brecha_publindex_sjr"] = df["categoria_publindex_ord"] - df["cuartil_sjr_ord"]
        df["contraste_publindex_cuartil"] = np.where(
            (df["categoria_publindex_ord"] > 0) & (df["cuartil_sjr_ord"] > 0),
            df["categoria_publindex_ord"] / df["cuartil_sjr_ord"],
            np.nan,
        )

    return df


def codificar_one_hot(
    df: pd.DataFrame,
    columnas: list[str] = ["pais_iso", "gran_area", "licencia"],
    prefijos: Optional[list[str]] = None,
) -> pd.DataFrame:
    """
    Genera codificación One-Hot para las variables categóricas especificadas (país, disciplina, licencia).
    """
    cols_existentes = [c for c in columnas if c in df.columns]
    if not cols_existentes:
        return df

    return pd.get_dummies(
        df,
        columns=cols_existentes,
        prefix=prefijos if prefijos else cols_existentes,
        dummy_na=False,
        drop_first=False,
        dtype=int,
    )


# ═══════════════════════════════════════════════════════════════════════════
# 10. TRAZABILIDAD Y HASHING
# ═══════════════════════════════════════════════════════════════════════════

def hash_registro(row: pd.Series) -> str:
    """Genera un hash SHA-256 truncado a 16 caracteres de un registro para detección de cambios."""
    contenido = "|".join(str(v) for v in row.values if not str(v).startswith("_hash"))
    return hashlib.sha256(contenido.encode("utf-8")).hexdigest()[:16]
