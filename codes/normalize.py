"""
Funciones de normalización compartidas por todos los módulos ETL.

Incluye: normalización de ISSN, títulos, países, monedas y detección de outliers.
"""

import re
import hashlib
import logging
import unicodedata
from typing import Optional

import pandas as pd
import numpy as np

try:
    from unidecode import unidecode
except ImportError:
    # Fallback sin unidecode: solo removemos diacríticos con unicodedata
    def unidecode(text: str) -> str:
        nfkd = unicodedata.normalize("NFKD", text)
        return "".join(c for c in nfkd if not unicodedata.combining(c))

try:
    from rapidfuzz import fuzz
except ImportError:
    fuzz = None

from config import PAISES_ISO, TASAS_USD, IQR_FACTOR

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════
# ISSN
# ═══════════════════════════════════════════════════════════════════════════

def limpiar_issn(valor: Optional[str]) -> Optional[str]:
    """
    Normaliza un ISSN a formato XXXX-XXXX.

    Elimina prefijos ('ISSN:', 'eISSN:'), espacios y guiones extra.
    Retorna None si el valor es nulo o no tiene 8 caracteres válidos.
    """
    if pd.isna(valor) or not valor:
        return None

    valor = str(valor).strip().upper()
    # Eliminar prefijos comunes
    for prefijo in ["ISSN:", "EISSN:", "ISSN", "EISSN", "E-ISSN:"]:
        valor = valor.replace(prefijo, "")

    # Quedarnos solo con dígitos y X
    limpio = re.sub(r"[^0-9X]", "", valor)

    if len(limpio) != 8:
        return None

    return f"{limpio[:4]}-{limpio[4:]}"


def validar_issn_checksum(issn: Optional[str]) -> bool:
    """
    Valida el dígito de control de un ISSN (módulo 11).

    El ISSN tiene 8 caracteres. Los primeros 7 son dígitos y el 8.° puede
    ser un dígito o 'X' (que vale 10).
    """
    if not issn:
        return False

    limpio = issn.replace("-", "")
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
    Retorna un ISSN canónico siguiendo la prioridad:
    ISSN-L > ISSN-print > ISSN-electronic.
    """
    for issn in [issn_linking, issn_print, issn_electronic]:
        normalizado = limpiar_issn(issn)
        if normalizado:
            return normalizado
    return None


# ═══════════════════════════════════════════════════════════════════════════
# TÍTULOS
# ═══════════════════════════════════════════════════════════════════════════

# Artículos y stopwords editoriales a remover
_STOPWORDS_TITULO = {
    "revista", "de", "del", "la", "las", "los", "el", "en", "y",
    "journal", "of", "the", "and", "for", "in", "on", "a", "an",
    "international", "review", "annals", "proceedings", "bulletin",
    "research", "studies", "transactions",
}


def normalizar_titulo(titulo: Optional[str]) -> Optional[str]:
    """
    Normaliza un título de revista para comparación:
    - Minúsculas
    - Remueve diacríticos
    - Remueve puntuación
    - Remueve stopwords editoriales
    - Espacios simples
    """
    if pd.isna(titulo) or not titulo:
        return None

    t = str(titulo).strip().lower()
    t = unidecode(t)
    t = re.sub(r"[^\w\s]", " ", t)
    palabras = [p for p in t.split() if p not in _STOPWORDS_TITULO]
    resultado = " ".join(palabras).strip()
    return resultado if resultado else None


def similitud_titulos(titulo_a: Optional[str], titulo_b: Optional[str]) -> float:
    """
    Calcula la similitud entre dos títulos normalizados usando Jaro-Winkler.
    Retorna un valor entre 0 y 100.
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
        return fuzz.WRatio(a, b)

    # Fallback simple: coincidencia de tokens
    set_a = set(a.split())
    set_b = set(b.split())
    if not set_a or not set_b:
        return 0.0
    interseccion = set_a & set_b
    return 100.0 * len(interseccion) / max(len(set_a), len(set_b))


# ═══════════════════════════════════════════════════════════════════════════
# PAÍSES
# ═══════════════════════════════════════════════════════════════════════════

def normalizar_pais(pais: Optional[str]) -> Optional[str]:
    """
    Convierte un nombre de país a código ISO 3166-1 alpha-2.
    """
    if pd.isna(pais) or not pais:
        return None

    clave = str(pais).strip().lower()
    clave = unidecode(clave)

    # Si ya es un código de 2 letras
    if len(clave) == 2 and clave.upper() in {v for v in PAISES_ISO.values()}:
        return clave.upper()

    return PAISES_ISO.get(clave, clave.upper()[:2] if len(clave) == 2 else None)


# ═══════════════════════════════════════════════════════════════════════════
# MONEDAS Y APC
# ═══════════════════════════════════════════════════════════════════════════

def parsear_apc_doaj(apc_amount_str: Optional[str]) -> tuple[Optional[float], Optional[str]]:
    """
    Parsea el campo 'APC amount' de DOAJ que puede tener formatos como:
    - "1500 USD"
    - "1000 EUR"
    - "USD 500"
    - "1500"
    - Vacío o NaN

    Retorna (monto, moneda).
    """
    if pd.isna(apc_amount_str) or not apc_amount_str:
        return None, None

    texto = str(apc_amount_str).strip()

    # Buscar patrón numérico
    numeros = re.findall(r"[\d.,]+", texto)
    letras = re.findall(r"[A-Z]{3}", texto.upper())

    monto = None
    moneda = None

    if numeros:
        # Tomar el primer número, limpiar separadores de miles
        num_str = numeros[0].replace(",", "")
        try:
            monto = float(num_str)
        except ValueError:
            pass

    if letras:
        moneda = letras[0]

    return monto, moneda


def convertir_a_usd(monto: Optional[float], moneda: Optional[str]) -> Optional[float]:
    """
    Convierte un monto en moneda local a USD usando tasas de referencia.
    """
    if monto is None or pd.isna(monto):
        return None

    if moneda is None or pd.isna(moneda):
        return None

    moneda = str(moneda).strip().upper()
    tasa = TASAS_USD.get(moneda)

    if tasa is None:
        logger.warning(f"Moneda no reconocida: {moneda}")
        return None

    return round(monto * tasa, 2)


def detectar_outliers_apc(
    df: pd.DataFrame,
    columna_apc: str = "apc_monto_usd",
    grupo_cols: Optional[list[str]] = None,
) -> pd.Series:
    """
    Detecta outliers en APC usando IQR segmentado por grupo.

    Retorna una Serie booleana (True = outlier).
    Si no hay suficientes datos en un grupo, usa los límites globales.
    """
    resultado = pd.Series(False, index=df.index)
    valores = df[columna_apc]

    if grupo_cols and all(c in df.columns for c in grupo_cols):
        for _, grupo in df.groupby(grupo_cols, dropna=False):
            vals = grupo[columna_apc].dropna()
            if len(vals) < 5:
                continue  # grupo muy pequeño, no marcar
            q1 = vals.quantile(0.25)
            q3 = vals.quantile(0.75)
            iqr = q3 - q1
            lower = q1 - IQR_FACTOR * iqr
            upper = q3 + IQR_FACTOR * iqr
            mask = (valores.loc[grupo.index] < lower) | (valores.loc[grupo.index] > upper)
            resultado.loc[grupo.index] = mask
    else:
        # Global
        vals = valores.dropna()
        if len(vals) >= 5:
            q1 = vals.quantile(0.25)
            q3 = vals.quantile(0.75)
            iqr = q3 - q1
            lower = q1 - IQR_FACTOR * iqr
            upper = q3 + IQR_FACTOR * iqr
            resultado = (valores < lower) | (valores > upper)

    return resultado.fillna(False)


def imputar_apc(
    df: pd.DataFrame,
    col_apc: str = "apc_monto_usd",
    col_editorial: str = "editorial",
    col_area: str = "gran_area",
    col_cuartil: str = "cuartil_sjr",
) -> pd.DataFrame:
    """
    Imputación condicional jerárquica de APC:
    1. Mediana por editorial
    2. Mediana por área temática + cuartil
    3. Mediana por área temática
    4. Mediana global

    Marca los valores imputados en 'apc_tipo' = 'imputado'
    y registra el método en 'apc_metodo_imputacion'.
    """
    df = df.copy()

    if "apc_tipo" not in df.columns:
        df["apc_tipo"] = np.where(df[col_apc].notna(), "declarado", None)

    if "apc_metodo_imputacion" not in df.columns:
        df["apc_metodo_imputacion"] = None

    faltantes = df[col_apc].isna()

    # Nivel 1: por editorial
    if col_editorial in df.columns:
        medianas_ed = df.groupby(col_editorial)[col_apc].transform("median")
        mask = faltantes & medianas_ed.notna()
        df.loc[mask, col_apc] = medianas_ed[mask]
        df.loc[mask, "apc_tipo"] = "imputado"
        df.loc[mask, "apc_metodo_imputacion"] = "mediana_editorial"
        faltantes = df[col_apc].isna()

    # Nivel 2: por área + cuartil
    if col_area in df.columns and col_cuartil in df.columns:
        cols_grupo = [col_area, col_cuartil]
        medianas_ac = df.groupby(cols_grupo)[col_apc].transform("median")
        mask = faltantes & medianas_ac.notna()
        df.loc[mask, col_apc] = medianas_ac[mask]
        df.loc[mask, "apc_tipo"] = "imputado"
        df.loc[mask, "apc_metodo_imputacion"] = "mediana_area_cuartil"
        faltantes = df[col_apc].isna()

    # Nivel 3: por área
    if col_area in df.columns:
        medianas_a = df.groupby(col_area)[col_apc].transform("median")
        mask = faltantes & medianas_a.notna()
        df.loc[mask, col_apc] = medianas_a[mask]
        df.loc[mask, "apc_tipo"] = "imputado"
        df.loc[mask, "apc_metodo_imputacion"] = "mediana_area"
        faltantes = df[col_apc].isna()

    # Nivel 4: global
    mediana_global = df[col_apc].median()
    if pd.notna(mediana_global):
        mask = faltantes
        df.loc[mask, col_apc] = mediana_global
        df.loc[mask, "apc_tipo"] = "imputado"
        df.loc[mask, "apc_metodo_imputacion"] = "mediana_global"

    return df


# ═══════════════════════════════════════════════════════════════════════════
# HASHING Y TRAZABILIDAD
# ═══════════════════════════════════════════════════════════════════════════

def hash_registro(row: pd.Series) -> str:
    """Genera un hash SHA-256 de un registro para detección de cambios."""
    contenido = "|".join(str(v) for v in row.values)
    return hashlib.sha256(contenido.encode("utf-8")).hexdigest()[:16]


def parsear_decimal_coma(valor: Optional[str]) -> Optional[float]:
    """Convierte un string con coma decimal ('0,914') a float."""
    if pd.isna(valor) or not valor:
        return None
    try:
        return float(str(valor).replace(",", "."))
    except (ValueError, TypeError):
        return None
