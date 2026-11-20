"""Convierte los campos de texto libre de las fuentes en valores filtrables.

El prototipo LIDER guarda cosas como ``"~USD 2310 | CHF 1800"``, ``"3–6 meses"``
o ``"Q2/Q1"``. Aquí se parsean a números/categorías manteniendo siempre el
texto original aparte para mostrarlo.
"""

from __future__ import annotations

import math
import re
import unicodedata

WEEKS_PER_MONTH = 4.345

# Tasas de referencia a USD (solo monedas presentes en las fuentes del catálogo).
USD_RATES = {
    "USD": 1.0,
    "US$": 1.0,
    "$": 1.0,
    "EUR": 1.08,
    "€": 1.08,
    "GBP": 1.27,
    "£": 1.27,
    "CHF": 1.13,
    "CAD": 0.74,
    "AUD": 0.65,
    "JPY": 0.0067,
    "CNY": 0.14,
    "COP": 0.00024,
    "BRL": 0.20,
    "MXN": 0.058,
}

COUNTRY_ALIASES = {
    "usa": "Estados Unidos",
    "us": "Estados Unidos",
    "eeuu": "Estados Unidos",
    "ee.uu.": "Estados Unidos",
    "united states": "Estados Unidos",
    "estados unidos": "Estados Unidos",
    "uk": "Reino Unido",
    "united kingdom": "Reino Unido",
    "gran bretana": "Reino Unido",
    "corea": "Corea del Sur",
    "south korea": "Corea del Sur",
    "netherlands": "Países Bajos",
    "holanda": "Países Bajos",
    "paises bajos": "Países Bajos",
    "switzerland": "Suiza",
    "germany": "Alemania",
    "spain": "España",
    "china": "China",
    "brazil": "Brasil",
    "mexico": "México",
    "colombia": "Colombia",
}

SUBMISSION_FORMATS = (
    "MDPI",
    "Elsevier",
    "Springer",
    "IEEE",
    "ACM",
    "Wiley",
    "Nature",
    "Taylor & Francis",
    "World Scientific",
    "INFORMS",
    "Emerald",
    "SciOpen",
    "Oxford",
    "Frontiers",
    "SAGE",
)

# Palabras clave (sin tildes, minúsculas) -> tema, para etiquetar revistas sin temas.
TOPIC_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("Inteligencia Artificial", ("artificial intelligence", "intelligen", " ai ", "cognitive")),
    (
        "Aprendizaje Automático",
        ("machine learning", "machine intelligence", "neural", "deep learning", "learning"),
    ),
    ("Ciencias de la Computación", ("computer", "computing", "computational", "software")),
    ("Redes y Telecomunicaciones", ("network", "telecommunication", "communication", "wireless")),
    ("Internet de las Cosas (IoT)", ("internet of things", "iot", "cyber-physical")),
    ("Ciberseguridad y Privacidad", ("security", "privacy", "cyber", "forensic", "trust")),
    ("Big Data y Datos", ("big data", "data science", "data mining", "database", "data ")),
    ("Computación en la Nube", ("cloud", "edge computing", "distributed", "grid")),
    ("Sistemas Inteligentes y Control", ("control", "fuzzy", "systems", "automation")),
    ("Electrónica y Microprocesadores", ("electronic", "circuits", "vlsi", "microprocessor")),
    ("Agronomía y Agricultura", ("agricultur", "agronom", "crop", "farming", "precision ag")),
    ("Sostenibilidad y Medio Ambiente", ("sustainab", "environment", "energy", "green", "climate")),
    ("Multimedia y Sistemas Digitales", ("multimedia", "image", "video", "graphics", "vision")),
    ("Sistemas de Información", ("information", "management", "informatics")),
    ("Comercio Electrónico", ("commerce", "e-business", "electronic commerce")),
    ("Robótica y Automatización", ("robot", "automation", "mechatronic")),
    ("Blockchain y Criptografía", ("blockchain", "cryptograph", "ledger")),
    ("Matemáticas Computacionales", ("mathematic", "algorithm", "optimization")),
    ("Redes de Sensores", ("sensor",)),
    ("Redes Sociales", ("social",)),
)


def strip_accents(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text)
    return "".join(char for char in decomposed if not unicodedata.combining(char))


def search_key(*parts: object) -> str:
    """Texto minúsculas y sin tildes para búsquedas insensibles a acentos."""
    joined = " ".join(str(part) for part in parts if part)
    return re.sub(r"\s+", " ", strip_accents(joined).lower()).strip()


def clean(value: object) -> str | None:
    """Texto recortado; ``None`` para vacío y marcadores tipo N/A."""
    if value is None:
        return None
    if isinstance(value, float) and math.isnan(value):
        return None
    text = str(value).strip()
    if not text or text.lower() in {"n/a", "na", "nan", "none", "null", "-", "—", "no disponible"}:
        return None
    return text


def normalize_issn(value: object) -> str | None:
    text = clean(value)
    if not text:
        return None
    match = re.search(r"(\d{4})-?(\d{3}[\dXx])", text)
    return f"{match.group(1)}-{match.group(2).upper()}" if match else None


def parse_number(value: object) -> float | None:
    text = clean(value)
    if text is None:
        return None
    match = re.search(r"-?\d+(?:[.,]\d+)?", text.replace(" ", ""))
    return float(match.group(0).replace(",", ".")) if match else None


def parse_int(value: object) -> int | None:
    number = parse_number(value)
    return int(round(number)) if number is not None else None


_AMOUNT = re.compile(
    r"(?P<cur>USD|US\$|EUR|GBP|CHF|CAD|AUD|JPY|CNY|COP|BRL|MXN|€|£|\$)?\s*"
    r"(?P<lo>\d[\d.,]*)(?:\s*[-–—]\s*(?P<hi>\d[\d.,]*))?\s*(?P<cur2>USD|EUR|GBP|CHF)?",
    re.IGNORECASE,
)
_FREE = re.compile(r"\b(gratis|gratuito|free|sin costo|no apc|sin apc|diamond|diamante)\b", re.I)


def _amount(raw: str) -> float:
    cleaned = raw.strip(".,")
    if re.fullmatch(r"\d{1,3}(?:[.,]\d{3})+", cleaned):  # 1,500 / 1.500 -> miles
        return float(re.sub(r"[.,]", "", cleaned))
    return float(cleaned.replace(",", "."))


def parse_apc(value: object) -> float | None:
    """Monto representativo en USD de un texto de costo; ``None`` si no hay dato.

    Con varias monedas (``"USD 2310 | CHF 1800"``) usa la primera. Un rango
    (``"USD 175-1450"``) devuelve su punto medio.
    """
    text = clean(value)
    if text is None:
        return None
    if _FREE.search(text):
        return 0.0
    for segment in re.split(r"[|;]", text):
        match = _AMOUNT.search(segment)
        if not match or not match.group("lo"):
            continue
        try:
            low = _amount(match.group("lo"))
            high = _amount(match.group("hi")) if match.group("hi") else low
        except ValueError:
            continue
        currency = (match.group("cur") or match.group("cur2") or "USD").upper()
        rate = USD_RATES.get(currency)
        if rate is None:
            continue
        return round((low + high) / 2 * rate, 2)
    return None


_DURATION = re.compile(
    r"(?P<lo>\d+(?:[.,]\d+)?)\s*(?:[-–—a]\s*(?P<hi>\d+(?:[.,]\d+)?))?\s*"
    r"(?P<unit>mes(?:es)?|month[s]?|semana[s]?|week[s]?|d[ií]a[s]?|day[s]?)",
    re.IGNORECASE,
)


def parse_weeks(value: object) -> float | None:
    """Convierte ``"3–6 meses"`` / ``"8 semanas"`` / ``"45 días"`` a semanas."""
    text = clean(value)
    if text is None:
        return None
    match = _DURATION.search(strip_accents(text))
    if not match:
        return None
    low = float(match.group("lo").replace(",", "."))
    high = float(match.group("hi").replace(",", ".")) if match.group("hi") else low
    unit = match.group("unit").lower()
    factor = (
        WEEKS_PER_MONTH
        if unit.startswith(("mes", "month"))
        else (1.0 if unit.startswith(("sem", "week")) else 1 / 7)
    )
    return round((low + high) / 2 * factor, 1)


def normalize_quartile(value: object) -> str | None:
    """El mejor cuartil mencionado (``"Q2/Q1"`` -> ``"Q1"``)."""
    text = clean(value)
    if not text:
        return None
    found = re.findall(r"Q\s*([1-4])", text, re.IGNORECASE)
    return f"Q{min(int(item) for item in found)}" if found else None


def normalize_access(value: object) -> str | None:
    text = clean(value)
    if not text:
        return None
    key = strip_accents(text).lower()
    if "hibrid" in key or "hybrid" in key:
        return "Híbrido"
    if re.search(r"open|abiert|diamond|diamante|\boa\b", key):
        return "Open Access"
    if any(word in key for word in ("suscrip", "subscri", "cerrad", "closed", "pago")):
        return "Suscripción"
    return text


def normalize_country(value: object) -> str | None:
    text = clean(value)
    if not text:
        return None
    first = re.split(r"[/;,]", text)[0].strip()
    alias = COUNTRY_ALIASES.get(strip_accents(first).lower())
    return alias or first


def normalize_submission_format(value: object) -> str | None:
    """Reduce ``"Elsevier (Editorial Manager, APA)"`` a la editorial ``Elsevier``."""
    text = clean(value)
    if not text:
        return None
    lowered = text.lower()
    hits = [
        (lowered.find(name.lower()), name) for name in SUBMISSION_FORMATS if name.lower() in lowered
    ]
    return min(hits)[1] if hits else text


def apc_status(apc_usd: float | None) -> str:
    if apc_usd is None:
        return "desconocido"
    return "sin_costo" if apc_usd <= 0 else "con_costo"


def infer_topics(title: str) -> list[str]:
    """Temas probables a partir del nombre de la revista (editable por el usuario)."""
    key = f" {search_key(title)} "
    topics = [topic for topic, words in TOPIC_RULES if any(word in key for word in words)]
    return topics[:4] or ["Ingeniería General"]
