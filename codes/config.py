"""
Configuración central del pipeline ETL y Procesamiento — Recomendador de Revistas.

Define rutas, constantes, tablas de conversión de divisas, factores PPP,
codificaciones ordinales y parámetros compartidos por todos los módulos.
"""

from pathlib import Path
from datetime import date

# ── Versión y Trazabilidad del Proceso ─────────────────────────────────────
VERSION_PROCESO = "1.0.0"
FECHA_CAPTURA = date.today().isoformat()

# ── Rutas del proyecto ──────────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"

BRONZE_DIR = DATA_DIR / "bronze"
SILVER_DIR = DATA_DIR / "silver"
GOLD_DIR = DATA_DIR / "gold"

LOGS_DIR = PROJECT_ROOT / "logs"
DOCS_DIR = PROJECT_ROOT / "docs"
REPORTS_DIR = PROJECT_ROOT / "reports"

# Crear directorios si no existen
for d in [SILVER_DIR, GOLD_DIR, LOGS_DIR, DOCS_DIR, REPORTS_DIR]:
    d.mkdir(parents=True, exist_ok=True)

# ── Archivos bronze ────────────────────────────────────────────────────────
PUBLINDEX_FILE = BRONZE_DIR / "Revistas_Indexadas,_Índice_Nacional_Publindex_20260910.csv"
DOAJ_FILE = BRONZE_DIR / "doaj_journalcsv_20260812_2320_utf8.csv"
SCIMAGO_FILE = BRONZE_DIR / "scimagojr 2025 CO.csv"
OPENAPC_FILE = BRONZE_DIR / "open_apc.csv"
FACTS_FILE = BRONZE_DIR / "facts.csv"

# ── Archivos silver ────────────────────────────────────────────────────────
PUBLINDEX_SILVER = SILVER_DIR / "publindex_clean.parquet"
DOAJ_SILVER = SILVER_DIR / "doaj_clean.parquet"
SCIMAGO_SILVER = SILVER_DIR / "scimago_clean.parquet"
OPENAPC_SILVER = SILVER_DIR / "openapc_clean.parquet"
FACTS_SILVER = SILVER_DIR / "facts_clean.parquet"
MERGE_LOG = SILVER_DIR / "merge_log.csv"

# ── Archivos gold ──────────────────────────────────────────────────────────
CATALOGO_GOLD = GOLD_DIR / "catalogo_maestro_revistas.parquet"
CATALOGO_GOLD_CSV = GOLD_DIR / "catalogo_maestro_revistas.csv"
FEATURES_GOLD = GOLD_DIR / "features_modelo.parquet"
MONEDAS_CONVERSION_REPORT = REPORTS_DIR / "tabla_conversion_monedas.csv"

# ── Precedencia de fuentes ante conflictos ────────────────────────────────
# (Mayor valor = mayor prioridad)
PRECEDENCIA_FUENTES = {
    "openapc": 4,   # Precedencia máxima para pagos observados de APC
    "publindex": 3, # Precedencia para datos nacionales colombianos
    "scimago": 2,   # Precedencia para métricas bibliométricas internacionales
    "doaj": 1,      # Precedencia para datos editoriales y de acceso abierto
}

# ── Codificación Ordinal ──────────────────────────────────────────────────
# Categorías Publindex: A1=4, A2=3, B=2, C=1
CATEGORIAS_PUBLINDEX = {
    "A1": 4,
    "A2": 3,
    "B": 2,
    "C": 1,
}

# Cuartiles Scimago SJR: Q1=4, Q2=3, Q3=2, Q4=1
CUARTIL_ORD = {
    "Q1": 4,
    "Q2": 3,
    "Q3": 2,
    "Q4": 1,
}

# ── Umbrales y Parámetros Estadísticos ────────────────────────────────────
# Umbral de fuzzy matching para títulos (0-100)
FUZZY_THRESHOLD = 85

# Outliers APC: factor de 3 rangos intercuartílicos (3 * IQR) según especificación 8.1.2
IQR_FACTOR = 3.0

# Rango referencial de APC (USD) para validación de consistencia
APC_MIN_USD = 0.0
APC_MAX_USD = 15_000.0

# ── Factores de Paridad de Poder Adquisitivo (PPP) ────────────────────────
# Factor de conversión PPP relativo a USD (referencia Banco Mundial / OCDE).
# Representa el multiplicador o nivel de nivelación de precios para análisis de asequibilidad.
# apc_ppp_usd = apc_usd / factor_ppp
FACTORES_PPP = {
    "CO": 0.38,  # Colombia (precios ~38% de EE.UU.)
    "BR": 0.45,  # Brasil
    "MX": 0.48,  # México
    "AR": 0.35,  # Argentina
    "CL": 0.60,  # Chile
    "PE": 0.42,  # Perú
    "ES": 0.78,  # España
    "US": 1.00,  # Estados Unidos
    "GB": 0.95,  # Reino Unido
    "DE": 0.88,  # Alemania
    "NL": 0.92,  # Países Bajos
    "CH": 1.25,  # Suiza
    "FR": 0.89,  # Francia
    "IT": 0.80,  # Italia
    "PT": 0.68,  # Portugal
    "CA": 0.90,  # Canadá
    "AU": 0.93,  # Australia
    "CN": 0.52,  # China
    "IN": 0.28,  # India
    "ZA": 0.44,  # Sudáfrica
    "DEFAULT": 1.00,
}

# ── Países de Ingresos Bajos y Medios (LMIC - Low and Middle Income) ──────
# Clasificación Banco Mundial para políticas de exención de APC (waivers)
PAISES_LMIC = {
    "AF", "AL", "DZ", "AO", "AR", "AM", "AZ", "BD", "BY", "BZ", "BJ", "BT",
    "BO", "BA", "BW", "BR", "BG", "BF", "BI", "CV", "KH", "CM", "CF", "TD",
    "CN", "CO", "KM", "CG", "CD", "CR", "CI", "CU", "DJ", "DM", "DO", "EC",
    "EG", "SV", "GQ", "ER", "ET", "FJ", "GA", "GM", "GE", "GH", "GD", "GT",
    "GN", "GW", "GY", "HT", "HN", "IN", "ID", "IR", "IQ", "JM", "JO", "KZ",
    "KE", "KI", "KP", "XK", "KG", "LA", "LB", "LS", "LR", "LY", "MG", "MW",
    "MY", "MV", "ML", "MH", "MR", "MU", "MX", "FM", "MD", "MN", "ME", "MA",
    "MZ", "MM", "NA", "NP", "NI", "NE", "NG", "MK", "PK", "PW", "PA", "PG",
    "PY", "PE", "PH", "RU", "RW", "WS", "ST", "SN", "RS", "SL", "SB", "SO",
    "ZA", "SS", "LK", "LC", "VC", "SD", "SR", "SY", "TJ", "TZ", "TH", "TL",
    "TG", "TO", "TN", "TR", "TM", "TV", "UG", "UA", "UZ", "VU", "VE", "VN",
    "PS", "YE", "ZM", "ZW",
}

# ── Mapeo de países comunes a ISO 3166-1 alpha-2 ───────────────────────────
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
    "united states of america": "US",
    "usa": "US",
    "united kingdom": "GB",
    "uk": "GB",
    "germany": "DE",
    "alemania": "DE",
    "france": "FR",
    "francia": "FR",
    "italy": "IT",
    "italia": "IT",
    "netherlands": "NL",
    "países bajos": "NL",
    "paises bajos": "NL",
    "switzerland": "CH",
    "suiza": "CH",
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
    "republica dominicana": "DO",
    "puerto rico": "PR",
    "canada": "CA",
    "canadá": "CA",
    "australia": "AU",
    "china": "CN",
    "japan": "JP",
    "japón": "JP",
    "south korea": "KR",
    "corea del sur": "KR",
    "india": "IN",
    "russia": "RU",
    "rusia": "RU",
    "turkey": "TR",
    "turquía": "TR",
    "iran": "IR",
    "irán": "IR",
    "egypt": "EG",
    "egipto": "EG",
    "south africa": "ZA",
    "sudáfrica": "ZA",
    "nigeria": "NG",
    "kenya": "KE",
    "slovenia": "SI",
    "eslovenia": "SI",
    "croatia": "HR",
    "croacia": "HR",
    "czech republic": "CZ",
    "república checa": "CZ",
    "republica checa": "CZ",
    "poland": "PL",
    "polonia": "PL",
    "romania": "RO",
    "rumanía": "RO",
    "hungary": "HU",
    "hungría": "HU",
    "austria": "AT",
    "sweden": "SE",
    "suecia": "SE",
    "norway": "NO",
    "noruega": "NO",
    "denmark": "DK",
    "dinamarca": "DK",
    "finland": "FI",
    "finlandia": "FI",
    "ireland": "IE",
    "irlanda": "IE",
    "belgium": "BE",
    "bélgica": "BE",
    "new zealand": "NZ",
    "nueva zelanda": "NZ",
    "singapore": "SG",
    "singapur": "SG",
    "malaysia": "MY",
    "malasia": "MY",
    "thailand": "TH",
    "tailandia": "TH",
    "indonesia": "ID",
    "philippines": "PH",
    "filipinas": "PH",
    "pakistan": "PK",
    "pakistán": "PK",
    "bangladesh": "BD",
    "sri lanka": "LK",
    "taiwan": "TW",
    "taiwán": "TW",
    "hong kong": "HK",
    "saudi arabia": "SA",
    "arabia saudita": "SA",
    "united arab emirates": "AE",
    "emiratos árabes unidos": "AE",
    "israel": "IL",
    "ukraine": "UA",
    "ucrania": "UA",
    "greece": "GR",
    "grecia": "GR",
    "bulgaria": "BG",
    "serbia": "RS",
    "slovakia": "SK",
    "eslovaquia": "SK",
    "lithuania": "LT",
    "lituania": "LT",
    "latvia": "LV",
    "letonia": "LV",
    "estonia": "EE",
    "iceland": "IS",
    "islandia": "IS",
    "luxembourg": "LU",
    "luxemburgo": "LU",
    "malta": "MT",
    "cyprus": "CY",
    "chipre": "CY",
}

# ── Tasas de conversión de monedas a USD ───────────────────────────────────
# Tasas de cambio de referencia para estandarización monetaria
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
    "HRK": 0.14,
    "ISK": 0.0073,
    "YER": 0.0040,
    "IRR": 0.0000238,
    "SYP": 0.0000769,
    "XOF": 0.00164,
    "IQD": 0.000763,
    "KZT": 0.00210,
    "NPR": 0.00750,
    "VND": 0.0000380,
    "MAD": 0.1000,
    "LYD": 0.2000,
    "GHS": 0.0670,
    "MNT": 0.000290,
    "KPW": 0.00111,
    "UGX": 0.000270,
    "XAF": 0.00164,
}
