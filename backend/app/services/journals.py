"""Consulta, creación y edición de revistas."""

from __future__ import annotations

import uuid
from collections import Counter
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import Select, func, or_, select
from sqlalchemy.orm import Session

from app.models import Journal, JournalIssn, Topic, journal_topics
from app.services import normalizers as nz

SORT_COLUMNS = {
    "title": Journal.title,
    "apc": Journal.apc_usd,
    "weeks": Journal.weeks_to_publication,
    "h_index": Journal.h_index,
    "sjr": Journal.sjr,
    "citescore": Journal.citescore,
    "impact_factor": Journal.impact_factor,
    "quality": Journal.quality_cost_index,
    "updated": Journal.updated_at,
}
# Columnas que se vuelven a derivar cuando cambia su texto original.
_WRITABLE = {
    "title",
    "issn_print",
    "issn_electronic",
    "issn_normalized",
    "url",
    "publisher",
    "country",
    "language",
    "keywords",
    "contact_email",
    "access_type",
    "quartile",
    "publindex_category",
    "apc_usd",
    "apc_text",
    "weeks_to_publication",
    "time_text",
    "h_index",
    "sjr",
    "citescore",
    "impact_factor",
    "quality_cost_index",
    "submission_format",
    "article_types",
    "issues_per_year",
    "details",
    "sources",
}


@dataclass
class JournalFilters:
    q: str | None = None
    topics: list[str] = field(default_factory=list)
    quartiles: list[str] = field(default_factory=list)
    access_types: list[str] = field(default_factory=list)
    countries: list[str] = field(default_factory=list)
    languages: list[str] = field(default_factory=list)
    submission_formats: list[str] = field(default_factory=list)
    publindex_categories: list[str] = field(default_factory=list)
    origins: list[str] = field(default_factory=list)
    apc_status: str | None = None
    apc_min: float | None = None
    apc_max: float | None = None
    weeks_max: float | None = None
    h_index_min: int | None = None
    sjr_min: float | None = None
    citescore_min: float | None = None
    impact_factor_min: float | None = None
    quality_min: float | None = None


def apply_filters(stmt: Select, f: JournalFilters) -> Select:
    if f.q:
        for term in nz.search_key(f.q).split():
            stmt = stmt.where(Journal.search_text.contains(term, autoescape=True))
    if f.topics:
        stmt = stmt.where(
            Journal.id.in_(
                select(journal_topics.c.journal_id)
                .join(Topic, Topic.id == journal_topics.c.topic_id)
                .where(Topic.name.in_(f.topics))
            )
        )
    for values, column in (
        (f.quartiles, Journal.quartile),
        (f.access_types, Journal.access_type),
        (f.countries, Journal.country),
        (f.submission_formats, Journal.submission_format),
        (f.publindex_categories, Journal.publindex_category),
        (f.origins, Journal.origin),
    ):
        if values:
            stmt = stmt.where(column.in_(values))
    if f.languages:
        stmt = stmt.where(
            or_(*(Journal.language.contains(v, autoescape=True) for v in f.languages))
        )
    if f.apc_status:
        stmt = stmt.where(Journal.apc_status == f.apc_status)
    if f.apc_min is not None:
        stmt = stmt.where(Journal.apc_usd >= f.apc_min)
    if f.apc_max is not None:
        stmt = stmt.where(Journal.apc_usd <= f.apc_max)
    if f.weeks_max is not None:
        stmt = stmt.where(Journal.weeks_to_publication <= f.weeks_max)
    for value, column in (
        (f.h_index_min, Journal.h_index),
        (f.sjr_min, Journal.sjr),
        (f.citescore_min, Journal.citescore),
        (f.impact_factor_min, Journal.impact_factor),
        (f.quality_min, Journal.quality_cost_index),
    ):
        if value is not None:
            stmt = stmt.where(column >= value)
    return stmt


def list_journals(
    db: Session, f: JournalFilters, sort: str, descending: bool, page: int, page_size: int
) -> tuple[list[Journal], int]:
    filtered = apply_filters(select(Journal), f)
    total = db.scalar(select(func.count()).select_from(filtered.subquery())) or 0
    column = SORT_COLUMNS.get(sort, Journal.title)
    ordering = column.desc() if descending else column.asc()
    # Los nulos siempre al final; ``id`` desempata para que la paginación sea estable.
    stmt = filtered.order_by(ordering.nulls_last(), Journal.id).offset((page - 1) * page_size)
    return list(db.scalars(stmt.limit(page_size))), total


def _counts(db: Session, column) -> list[dict[str, Any]]:
    rows = db.execute(
        select(column, func.count()).where(column.is_not(None)).group_by(column)
    ).all()
    return [
        {"value": str(value), "count": count}
        for value, count in sorted(rows, key=lambda row: (-row[1], str(row[0])))
    ]


def build_facets(db: Session) -> dict[str, Any]:
    topic_rows = db.execute(
        select(Topic.name, func.count(journal_topics.c.journal_id))
        .join(journal_topics, journal_topics.c.topic_id == Topic.id)
        .group_by(Topic.name)
    ).all()
    languages: Counter[str] = Counter()
    for (text,) in db.execute(select(Journal.language).where(Journal.language.is_not(None))):
        languages.update(part.strip() for part in text.split(",") if part.strip())
    return {
        "topics": [
            {"value": name, "count": count}
            for name, count in sorted(topic_rows, key=lambda row: (-row[1], row[0]))
        ],
        "quartiles": sorted(_counts(db, Journal.quartile), key=lambda item: item["value"]),
        "access_types": _counts(db, Journal.access_type),
        "countries": _counts(db, Journal.country),
        "languages": [{"value": k, "count": v} for k, v in languages.most_common()],
        "submission_formats": _counts(db, Journal.submission_format),
        "publindex_categories": sorted(
            _counts(db, Journal.publindex_category), key=lambda item: item["value"]
        ),
        "origins": _counts(db, Journal.origin),
        "apc_statuses": _counts(db, Journal.apc_status),
        "total": db.scalar(select(func.count()).select_from(Journal)) or 0,
        "max_apc_usd": db.scalar(select(func.max(Journal.apc_usd))),
        "max_weeks": db.scalar(select(func.max(Journal.weeks_to_publication))),
        "max_h_index": db.scalar(select(func.max(Journal.h_index))),
    }


def find_issn_duplicates(
    db: Session, issns: list[str | None], exclude_id: int | None = None
) -> list[Journal]:
    wanted = [issn for issn in issns if issn]
    if not wanted:
        return []
    stmt = select(Journal).where(
        Journal.id.in_(select(JournalIssn.journal_id).where(JournalIssn.issn.in_(wanted)))
    )
    if exclude_id is not None:
        stmt = stmt.where(Journal.id != exclude_id)
    return list(db.scalars(stmt))


def journals_by_issn(db: Session, issns: list[str]) -> dict[str, Journal]:
    """Revista que corresponde a cada ISSN (cualquiera de los asociados a la revista)."""
    if not issns:
        return {}
    rows = db.execute(
        select(JournalIssn.issn, Journal)
        .join(Journal, Journal.id == JournalIssn.journal_id)
        .where(JournalIssn.issn.in_(issns))
        .order_by(Journal.origin.desc(), Journal.id)  # ``etl`` gana ante duplicados
    )
    found: dict[str, Journal] = {}
    for issn, journal in rows:
        found.setdefault(issn, journal)
    return found


def _sync_issns(journal: Journal, extra: list[str]) -> None:
    wanted = {
        issn
        for issn in (journal.issn_print, journal.issn_electronic, journal.issn_normalized, *extra)
        if issn
    }
    current = {item.issn: item for item in journal.issns}
    for issn, item in current.items():
        if issn not in wanted:
            journal.issns.remove(item)
    for issn in sorted(wanted - current.keys()):
        journal.issns.append(JournalIssn(issn=issn))


def _resolve_topics(db: Session, names: list[str]) -> list[Topic]:
    if not names:
        return []
    wanted = {name.lower() for name in names}
    existing = {
        t.name.lower(): t
        for t in db.scalars(select(Topic).where(func.lower(Topic.name).in_(wanted)))
    }
    resolved: list[Topic] = []
    for name in names:
        topic = existing.get(name.lower())
        if topic is None:
            topic = Topic(name=name)
            db.add(topic)
            existing[name.lower()] = topic
        resolved.append(topic)
    return resolved


def apply_values(
    db: Session,
    journal: Journal,
    values: dict[str, Any],
    *,
    reparse_text: bool = True,
) -> Journal:
    """Asigna ``values`` y recalcula los campos derivados.

    Si llega un texto libre (``apc_text``/``time_text``) sin su valor numérico,
    el número se obtiene parseando el texto; así el usuario puede seguir
    escribiendo ``"~USD 2300"`` y el filtro por precio lo entiende.
    """
    for key, value in values.items():
        if key in _WRITABLE:
            setattr(journal, key, value)
    if reparse_text:
        if "apc_usd" not in values and "apc_text" in values:
            journal.apc_usd = nz.parse_apc(journal.apc_text)
        if "weeks_to_publication" not in values and "time_text" in values:
            journal.weeks_to_publication = nz.parse_weeks(journal.time_text)
    if "topics" in values and values["topics"] is not None:
        journal.topics = _resolve_topics(db, values["topics"])
    if journal.issn_normalized is None:
        journal.issn_normalized = journal.issn_electronic or journal.issn_print
    _sync_issns(journal, values.get("issn_aliases") or [item.issn for item in journal.issns])
    journal.apc_status = nz.apc_status(journal.apc_usd)
    journal.search_text = nz.search_key(
        journal.title,
        journal.issn_print,
        journal.issn_electronic,
        journal.publisher,
        journal.keywords,
        journal.country,
        " ".join(topic.name for topic in journal.topics),
    )
    return journal


def create_journal(db: Session, values: dict[str, Any], origin: str = "manual") -> Journal:
    journal = Journal(
        origin=origin, source_key=f"{origin}:{uuid.uuid4().hex}", sources=[origin], details={}
    )
    db.add(journal)
    apply_values(db, journal, values)
    journal.locally_modified = True
    db.commit()
    return journal


def update_journal(db: Session, journal: Journal, values: dict[str, Any]) -> Journal:
    apply_values(db, journal, values)
    journal.locally_modified = True
    db.commit()
    return journal
