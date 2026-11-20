"""Traduce registros de cada fuente (LIDER, Gold del ETL) al modelo ``Journal``."""

from __future__ import annotations

import math
import re
from collections.abc import Iterable
from typing import Any

import pandas as pd

from app.services import normalizers as nz

LANGUAGE_ES = {
    "english": "Inglés",
    "spanish": "Español",
    "portuguese": "Portugués",
    "french": "Francés",
    "german": "Alemán",
    "italian": "Italiano",
    "catalan": "Catalán",
    "chinese": "Chino",
    "russian": "Ruso",
}

LIDER_MACRO_AREA = "Ingeniería y Tecnología"
_LIDER_COLUMNS = (
    "Nombre",
    "Indexación",
    "Link",
    "Formato que recibe",
    "ISSN Electrónico",
    "ISSN Impreso",
    "Formato necesario para publicar",
    "Acceso",
    "Costo",
    "Idioma",
    "Cuantas revistas/articulos al año",
    "Ubicación",
    "Correo",
    "Cuanto demora en publicar?",
    "Índice H",
    "CiteScore",
    "Impact Factor",
)
LIDER_REQUIRED_COLUMNS = ("Nombre",)
LIDER_COLUMNS = _LIDER_COLUMNS


def _py(value: Any) -> Any:
    """Convierte escalares numpy/pandas a tipos JSON-serializables (NaN -> None)."""
    if value is None or value is pd.NA or value is pd.NaT:
        return None
    if hasattr(value, "item") and getattr(value, "ndim", 1) == 0:
        value = value.item()
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if isinstance(value, (list, tuple)) or hasattr(value, "tolist"):
        return [_py(item) for item in (value.tolist() if hasattr(value, "tolist") else value)]
    return value


def _is_nan(value: Any) -> bool:
    return value is None or (isinstance(value, float) and math.isnan(value)) or value is pd.NA


def is_valid_lider_record(record: dict[str, Any]) -> bool:
    """El prototipo trae filas basura (p. ej. ``Nombre = "500"``): sin letras no es revista."""
    name = nz.clean(record.get("Nombre"))
    return bool(name and re.search(r"[A-Za-zÁÉÍÓÚáéíóúÑñ]", name))


def from_lider(record: dict[str, Any]) -> dict[str, Any]:
    title = nz.clean(record.get("Nombre")) or ""
    apc_text = nz.clean(record.get("Costo"))
    time_text = nz.clean(record.get("Cuanto demora en publicar?"))
    quartile_raw = nz.clean(record.get("Indexación"))
    link = nz.clean(record.get("Link"))
    # El prototipo guardó títulos de página en vez de URLs (p. ej. "IEEE Xplore: ..."):
    # solo se publica como enlace lo que realmente es una URL.
    url = link if link and re.match(r"https?://\S+$", link, re.IGNORECASE) else None
    topics = [t for t in (record.get("Temas") or []) if isinstance(t, str)] or nz.infer_topics(
        title
    )
    return {
        "origin": "lider",
        "source_key": f"lider:{nz.search_key(title)}",
        "sources": ["lider"],
        "title": title,
        "issn_print": nz.normalize_issn(record.get("ISSN Impreso")),
        "issn_electronic": nz.normalize_issn(record.get("ISSN Electrónico")),
        "url": url,
        "country": nz.normalize_country(record.get("Ubicación")),
        "language": nz.clean(record.get("Idioma")),
        "contact_email": nz.clean(record.get("Correo")),
        "access_type": nz.normalize_access(record.get("Acceso")),
        "quartile": nz.normalize_quartile(quartile_raw),
        "apc_usd": nz.parse_apc(apc_text),
        "apc_text": apc_text,
        "weeks_to_publication": nz.parse_weeks(time_text),
        "time_text": time_text,
        "h_index": nz.parse_int(record.get("Índice H")),
        "citescore": nz.parse_number(record.get("CiteScore")),
        "impact_factor": nz.parse_number(record.get("Impact Factor")),
        "submission_format": nz.normalize_submission_format(
            record.get("Formato necesario para publicar")
        ),
        "article_types": nz.clean(record.get("Formato que recibe")),
        "issues_per_year": nz.clean(record.get("Cuantas revistas/articulos al año")),
        "topics": topics,
        "details": {
            "indexacion_original": quartile_raw,
            **({"enlace_original": link} if link and url is None else {}),
        },
    }


def _filled(values: dict[str, Any]) -> int:
    return sum(1 for value in values.values() if value not in (None, "", [], {}))


def dedupe_lider(rows: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """Una fila por nombre normalizado, conservando la más completa."""
    best: dict[str, dict[str, Any]] = {}
    for row in rows:
        key = row["source_key"]
        if key not in best or _filled(row) > _filled(best[key]):
            best[key] = row
    return list(best.values())


def _flag(value: Any) -> bool | None:
    """Booleano de Python (o ``None``) desde bool/np.bool_/NA: ``is True`` falla con numpy."""
    if _is_nan(value):
        return None
    return bool(value)


def _gold_languages(raw: Any) -> str | None:
    text = nz.clean(raw)
    if not text:
        return None
    names = [part.strip() for part in text.split(",") if part.strip()]
    return ", ".join(LANGUAGE_ES.get(name.lower(), name) for name in names)


def _gold_access(row: pd.Series) -> str | None:
    if _flag(row.get("is_hybrid")):
        return "Híbrido"
    if any(_flag(row.get(column)) for column in ("open_access", "indexada_doaj", "oa_diamond")):
        return "Open Access"
    if _flag(row.get("open_access")) is False:
        return "Suscripción"
    return None


def _gold_topics(row: pd.Series) -> list[str]:
    topics: list[str] = []
    for column in ("gran_area", "area_conocimiento"):
        value = nz.clean(row.get(column))
        if value and value.lower() != "no registra" and value not in topics:
            topics.append(value)
    return topics or ["Sin clasificar"]


def from_gold_row(
    row: pd.Series, aliases: list[str] | None = None, history: list[dict[str, Any]] | None = None
) -> dict[str, Any]:
    """Una fila de ``catalogo_maestro_revistas`` al modelo del catálogo."""
    issn = nz.normalize_issn(row.get("issn_normalizado"))
    apc_real = row.get("apc_monto_usd_real")
    if not _is_nan(apc_real):
        apc_usd: float | None = round(float(apc_real), 2)
    elif _flag(row.get("tiene_apc")) is False:
        apc_usd = 0.0
    else:
        apc_usd = None

    original_amount, original_currency = (
        row.get("apc_monto_original"),
        row.get("apc_moneda_original"),
    )
    apc_text = (
        f"{original_amount:g} {original_currency}"
        if not _is_nan(original_amount) and not _is_nan(original_currency)
        else None
    )
    weeks = row.get("semanas_pub")
    weeks = None if _is_nan(weeks) else float(weeks)
    h_index = row.get("h_index")
    quality = row.get("indice_topsis_calidad_costo")
    sjr = row.get("sjr_score")

    details_keys = (
        "anio_clasificacion",
        "region",
        "departamento",
        "municipio",
        "especialidad",
        "institucion_editora_1",
        "editorial",
        "licencia",
        "tipo_revision",
        "tiene_apc",
        "apc_tipo",
        "indexada_doaj",
        "oa_diamond",
        "politica_exencion",
        "cobertura",
        "categorias",
        "areas",
        "total_docs_3y",
        "total_citas_3y",
        "citas_por_doc_2y",
        "rank",
        "url",
        "pais_editorial",
    )
    details = {key: _py(row.get(key)) for key in details_keys if key in row.index}
    details["doaj_url"] = details.pop("url", None)
    if history:
        details["clasificaciones_previas"] = history
    return {
        "origin": "etl",
        "source_key": issn or f"etl:{nz.search_key(row.get('titulo'))}",
        "sources": [str(item) for item in _py(row.get("_fuentes")) or []],
        "title": nz.clean(row.get("titulo")) or "Sin título",
        "issn_print": nz.normalize_issn(row.get("issn_print")),
        "issn_electronic": nz.normalize_issn(row.get("issn_electronic")),
        "issn_normalized": issn,
        "issn_aliases": aliases or [],
        "url": nz.clean(row.get("url_revista")),
        "publisher": nz.clean(row.get("institucion_editora_1")) or nz.clean(row.get("editorial")),
        "country": nz.normalize_country(row.get("pais")),
        "language": _gold_languages(row.get("idiomas")),
        "keywords": nz.clean(row.get("palabras_clave")),
        "access_type": _gold_access(row),
        "quartile": nz.normalize_quartile(row.get("cuartil_sjr")),
        "publindex_category": nz.clean(row.get("categoria_publindex")),
        "apc_usd": apc_usd,
        "apc_text": apc_text,
        "weeks_to_publication": weeks,
        "time_text": f"{weeks:g} semanas" if weeks is not None else None,
        "h_index": None if _is_nan(h_index) else int(h_index),
        "sjr": None if _is_nan(sjr) else float(sjr),
        "quality_cost_index": None if _is_nan(quality) else round(float(quality), 4),
        "topics": _gold_topics(row),
        "details": details,
    }


def collapse_gold(frame: pd.DataFrame) -> list[dict[str, Any]]:
    """Una revista por ``id_revista_publindex``.

    El Gold trae una fila por (revista, año de clasificación/ISSN): 906 filas son 650
    revistas. Se conserva la clasificación más reciente y se guardan los demás ISSN como
    alias (el recomendador identifica revistas por ISSN) junto al historial de categorías.
    """
    ordered = frame.sort_values("anio_clasificacion", ascending=False, na_position="last")
    rows: list[dict[str, Any]] = []
    has_id = ordered["id_revista_publindex"].notna()
    for _, row in ordered[~has_id].iterrows():
        rows.append(from_gold_row(row))
    for _, group in ordered[has_id].groupby("id_revista_publindex", sort=False):
        latest = group.iloc[0]
        aliases = {
            issn
            for column in ("issn_normalizado", "issn_print", "issn_electronic")
            for issn in group[column].map(nz.normalize_issn).dropna()
        }
        history = [
            {
                "anio": _py(item.get("anio_clasificacion")),
                "categoria": nz.clean(item.get("categoria_publindex")),
            }
            for _, item in group.iloc[1:].iterrows()
        ]
        rows.append(from_gold_row(latest, sorted(aliases), history))
    return rows
