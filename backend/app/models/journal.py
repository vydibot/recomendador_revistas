"""Modelo relacional del catálogo de revistas."""

from datetime import UTC, datetime

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Table,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


def _utcnow() -> datetime:
    return datetime.now(UTC)


journal_topics = Table(
    "journal_topics",
    Base.metadata,
    Column("journal_id", ForeignKey("journals.id", ondelete="CASCADE"), primary_key=True),
    Column("topic_id", ForeignKey("topics.id", ondelete="CASCADE"), primary_key=True),
)


class Topic(Base):
    __tablename__ = "topics"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120), unique=True, index=True)


class JournalIssn(Base):
    """Todos los ISSN conocidos de una revista (impreso, electrónico y alternos del ETL)."""

    __tablename__ = "journal_issns"

    journal_id: Mapped[int] = mapped_column(
        ForeignKey("journals.id", ondelete="CASCADE"), primary_key=True
    )
    issn: Mapped[str] = mapped_column(String(9), primary_key=True, index=True)


class Journal(Base):
    """Una revista, venga del ETL (Gold), del prototipo LIDER o creada a mano.

    Los campos numéricos (APC, semanas, scores) son los filtrables; los textos
    originales (``apc_text``, ``time_text``) se conservan para mostrarlos tal
    como los capturó la fuente.
    """

    __tablename__ = "journals"
    __table_args__ = (
        UniqueConstraint("origin", "source_key", name="uq_journal_origin_source_key"),
        Index("ix_journals_issn_normalized", "issn_normalized"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    # Procedencia: ``etl`` (Gold), ``lider`` (prototipo) o ``manual``.
    origin: Mapped[str] = mapped_column(String(16), index=True)
    source_key: Mapped[str] = mapped_column(String(200))
    sources: Mapped[list] = mapped_column(JSON, default=list)
    # True si un usuario editó el registro: el seed ya no lo sobrescribe.
    locally_modified: Mapped[bool] = mapped_column(Boolean, default=False)

    title: Mapped[str] = mapped_column(String(500), index=True)
    issn_print: Mapped[str | None] = mapped_column(String(9))
    issn_electronic: Mapped[str | None] = mapped_column(String(9))
    # ISSN con el que el recomendador identifica la revista (Gold).
    issn_normalized: Mapped[str | None] = mapped_column(String(9))
    url: Mapped[str | None] = mapped_column(String(1000))
    publisher: Mapped[str | None] = mapped_column(String(500))
    country: Mapped[str | None] = mapped_column(String(120), index=True)
    language: Mapped[str | None] = mapped_column(String(200))
    keywords: Mapped[str | None] = mapped_column(Text)
    contact_email: Mapped[str | None] = mapped_column(String(320))

    access_type: Mapped[str | None] = mapped_column(String(32), index=True)
    quartile: Mapped[str | None] = mapped_column(String(2), index=True)
    publindex_category: Mapped[str | None] = mapped_column(String(2), index=True)

    apc_usd: Mapped[float | None] = mapped_column(Float, index=True)
    apc_text: Mapped[str | None] = mapped_column(String(200))
    # ``sin_costo`` | ``con_costo`` | ``desconocido`` (derivado de apc_usd).
    apc_status: Mapped[str] = mapped_column(String(16), default="desconocido", index=True)
    weeks_to_publication: Mapped[float | None] = mapped_column(Float, index=True)
    time_text: Mapped[str | None] = mapped_column(String(100))

    h_index: Mapped[int | None] = mapped_column(Integer)
    sjr: Mapped[float | None] = mapped_column(Float)
    citescore: Mapped[float | None] = mapped_column(Float)
    impact_factor: Mapped[float | None] = mapped_column(Float)
    quality_cost_index: Mapped[float | None] = mapped_column(Float)

    submission_format: Mapped[str | None] = mapped_column(String(120), index=True)
    article_types: Mapped[str | None] = mapped_column(String(200))
    issues_per_year: Mapped[str | None] = mapped_column(String(100))

    # Texto normalizado (sin tildes, minúsculas) para búsqueda insensible a acentos.
    search_text: Mapped[str] = mapped_column(Text, default="")
    details: Mapped[dict] = mapped_column(JSON, default=dict)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )

    issns: Mapped[list[JournalIssn]] = relationship(
        cascade="all, delete-orphan", lazy="selectin", passive_deletes=True
    )
    topics: Mapped[list[Topic]] = relationship(
        secondary=journal_topics, lazy="selectin", order_by=Topic.name
    )
