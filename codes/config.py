"""
Configuración central del pipeline ETL — Recomendador de Revistas.

Define rutas, constantes y parámetros compartidos por todos los módulos.
"""

from pathlib import Path
from datetime import date

# ── Rutas del proyecto ──────────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"

BRONZE_DIR = DATA_DIR / "bronze"
SILVER_DIR = DATA_DIR / "silver"
GOLD_DIR = DATA_DIR / "gold"

LOGS_DIR = PROJECT_ROOT / "logs"
DOCS_DIR = PROJECT_ROOT / "docs"

# Crear directorios si no existen
for d in [SILVER_DIR, GOLD_DIR, LOGS_DIR, DOCS_DIR]:
    d.mkdir(parents=True, exist_ok=True)

# ── Archivos bronze ────────────────────────────────────────────────────────
PUBLINDEX_FILE = BRONZE_DIR / "Revistas_Indexadas,_Índice_Nacional_Publindex_20260910.csv"
DOAJ_FILE = BRONZE_DIR / "doaj_journalcsv_20260812_2320_utf8.csv"
SCIMAGO_FILE = BRONZE_DIR / "scimagojr 2025 CO.csv"
OPENAPC_FILE = BRONZE_DIR / "apc_de.csv"

# ── Archivos silver ────────────────────────────────────────────────────────
PUBLINDEX_SILVER = SILVER_DIR / "publindex_clean.parquet"
DOAJ_SILVER = SILVER_DIR / "doaj_clean.parquet"
SCIMAGO_SILVER = SILVER_DIR / "scimago_clean.parquet"
OPENAPC_SILVER = SILVER_DIR / "openapc_clean.parquet"
MERGE_LOG = SILVER_DIR / "merge_log.csv"

# ── Archivos gold ──────────────────────────────────────────────────────────
CATALOGO_GOLD = GOLD_DIR / "catalogo_maestro_revistas.parquet"
FEATURES_GOLD = GOLD_DIR / "features_modelo.parquet"

# ── Parámetros del pipeline ────────────────────────────────────────────────
FECHA_CAPTURA = date.today().isoformat()

# Precedencia de fuentes ante conflictos (mayor índice = mayor precedencia)
PRECEDENCIA_FUENTES = {
    "openapc": 1,
    "doaj": 2,
    "scimago": 3,
    "publindex": 4,
}

# Categorías Publindex (orden jerárquico)
CATEGORIAS_PUBLINDEX = {"A1": 4, "A2": 3, "B": 2, "C": 1}

# Mapeo de cuartiles a valor numérico ordinal
CUARTIL_ORD = {"Q1": 4, "Q2": 3, "Q3": 2, "Q4": 1}

# Umbral de fuzzy matching para títulos (0-100)
FUZZY_THRESHOLD = 85

# Outliers APC: factor IQR
IQR_FACTOR = 1.5

# Rango razonable de APC (USD) para validación rápida
APC_MIN_USD = 0
APC_MAX_USD = 15_000

# Mapeo de países comunes a ISO 3166-1 alpha-2
PAISES_ISO = {
    "colombia": "CO",
    "brazil": "BR",
    "brasil": "BR",
    "mexico": "MX",
    "méxico": "MX",
    "argentina": "AR",
    "chile": "CL",
    "peru": "PE",
    "perú": "PE",
    "spain": "ES",
    "españa": "ES",
    "united states": "US",
    "united kingdom": "GB",
    "germany": "DE",
    "france": "FR",
    "italy": "IT",
    "netherlands": "NL",
    "switzerland": "CH",
    "portugal": "PT",
    "ecuador": "EC",
    "venezuela": "VE",
    "cuba": "CU",
    "costa rica": "CR",
    "uruguay": "UY",
    "paraguay": "PY",
    "bolivia": "BO",
    "panama": "PA",
    "panamá": "PA",
    "guatemala": "GT",
    "honduras": "HN",
    "el salvador": "SV",
    "nicaragua": "NI",
    "dominican republic": "DO",
    "república dominicana": "DO",
    "puerto rico": "PR",
    "canada": "CA",
    "australia": "AU",
    "china": "CN",
    "japan": "JP",
    "south korea": "KR",
    "india": "IN",
    "russia": "RU",
    "turkey": "TR",
    "iran": "IR",
    "egypt": "EG",
    "south africa": "ZA",
    "nigeria": "NG",
    "kenya": "KE",
    "slovenia": "SI",
    "croatia": "HR",
    "czech republic": "CZ",
    "poland": "PL",
    "romania": "RO",
    "hungary": "HU",
    "austria": "AT",
    "sweden": "SE",
    "norway": "NO",
    "denmark": "DK",
    "finland": "FI",
    "ireland": "IE",
    "belgium": "BE",
    "new zealand": "NZ",
    "singapore": "SG",
    "malaysia": "MY",
    "thailand": "TH",
    "indonesia": "ID",
    "philippines": "PH",
    "pakistan": "PK",
    "bangladesh": "BD",
    "sri lanka": "LK",
    "taiwan": "TW",
    "hong kong": "HK",
    "saudi arabia": "SA",
    "united arab emirates": "AE",
    "israel": "IL",
    "ukraine": "UA",
    "greece": "GR",
    "bulgaria": "BG",
    "serbia": "RS",
    "slovakia": "SK",
    "lithuania": "LT",
    "latvia": "LV",
    "estonia": "EE",
    "iceland": "IS",
    "luxembourg": "LU",
    "malta": "MT",
    "cyprus": "CY",
}

# Tasas de conversión de monedas a USD (referencia aproximada 2025/2026)
# En producción se usaría una API; aquí se incluyen valores de referencia.
TASAS_USD = {
    "USD": 1.0,
    "EUR": 1.08,
    "GBP": 1.27,
    "CHF": 1.13,
    "JPY": 0.0067,
    "CAD": 0.74,
    "AUD": 0.65,
    "BRL": 0.20,
    "MXN": 0.058,
    "COP": 0.00024,
    "ARS": 0.0011,
    "CLP": 0.0011,
    "PEN": 0.27,
    "CZK": 0.046,
    "PLN": 0.26,
    "SEK": 0.096,
    "NOK": 0.094,
    "DKK": 0.145,
    "HUF": 0.0028,
    "RON": 0.22,
    "TRY": 0.031,
    "ZAR": 0.055,
    "INR": 0.012,
    "CNY": 0.14,
    "KRW": 0.00075,
    "SGD": 0.74,
    "MYR": 0.22,
    "THB": 0.029,
    "IDR": 0.000063,
    "PHP": 0.018,
    "EGP": 0.021,
    "NGN": 0.00065,
    "KES": 0.0078,
    "RUB": 0.011,
    "UAH": 0.027,
    "SAR": 0.27,
    "AED": 0.27,
    "ILS": 0.28,
    "NZD": 0.61,
    "TWD": 0.032,
    "HKD": 0.13,
    "PKR": 0.0036,
    "BDT": 0.0091,
    "LKR": 0.0034,
    "BGN": 0.55,
    "RSD": 0.0092,
    "HRK": 0.14,  # pre-euro
    "ISK": 0.0073,
}
