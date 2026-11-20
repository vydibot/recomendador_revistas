"""Esquemas de entrada/salida de la API de revistas."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

_STRING_LIMITS = {
    "title": 500,
    "url": 1000,
    "publisher": 500,
    "country": 120,
    "language": 200,
    "contact_email": 320,
    "apc_text": 200,
    "time_text": 100,
    "submission_format": 120,
    "article_types": 200,
    "issues_per_year": 100,
}


class JournalBase(BaseModel):
    """Campos editables de una revista (todos opcionales; ``title`` lo exige Create)."""

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    title: str | None = Field(default=None, max_length=500)
    issn_print: str | None = Field(default=None, max_length=9)
    issn_electronic: str | None = Field(default=None, max_length=9)
    url: str | None = Field(default=None, max_length=1000)
    publisher: str | None = Field(default=None, max_length=500)
    country: str | None = Field(default=None, max_length=120)
    language: str | None = Field(default=None, max_length=200)
    keywords: str | None = Field(default=None, max_length=4000)
    contact_email: str | None = Field(default=None, max_length=320)
    access_type: str | None = Field(default=None, max_length=32)
    quartile: str | None = Field(default=None, pattern=r"^Q[1-4]$")
    publindex_category: str | None = Field(default=None, pattern=r"^(A1|A2|B|C)$")
    apc_usd: float | None = Field(default=None, ge=0, le=1_000_000)
    apc_text: str | None = Field(default=None, max_length=200)
    weeks_to_publication: float | None = Field(default=None, ge=0, le=1_000)
    time_text: str | None = Field(default=None, max_length=100)
    h_index: int | None = Field(default=None, ge=0, le=10_000)
    sjr: float | None = Field(default=None, ge=0, le=1_000)
    citescore: float | None = Field(default=None, ge=0, le=1_000)
    impact_factor: float | None = Field(default=None, ge=0, le=1_000)
    submission_format: str | None = Field(default=None, max_length=120)
    article_types: str | None = Field(default=None, max_length=200)
    issues_per_year: str | None = Field(default=None, max_length=100)
    topics: list[str] | None = Field(default=None, max_length=30)

    @field_validator("*", mode="before")
    @classmethod
    def _blank_to_none(cls, value: Any) -> Any:
        return None if isinstance(value, str) and not value.strip() else value

    @field_validator("topics")
    @classmethod
    def _clean_topics(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return None
        seen: dict[str, str] = {}
        for item in value:
            name = " ".join(str(item).split())[:120]
            if name:
                seen.setdefault(name.lower(), name)
        return list(seen.values())

    @field_validator("contact_email")
    @classmethod
    def _check_email(cls, value: str | None) -> str | None:
        if value is not None and "@" not in value:
            raise ValueError("Correo inválido")
        return value


class JournalCreate(JournalBase):
    title: str = Field(min_length=1, max_length=500)


class JournalUpdate(JournalBase):
    """PATCH: solo se modifican los campos enviados."""

    title: str | None = Field(default=None, min_length=1, max_length=500)


class JournalListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    origin: str
    title: str
    issn_print: str | None
    issn_electronic: str | None
    issn_normalized: str | None
    url: str | None
    publisher: str | None
    country: str | None
    language: str | None
    access_type: str | None
    quartile: str | None
    publindex_category: str | None
    apc_usd: float | None
    apc_text: str | None
    apc_status: str
    weeks_to_publication: float | None
    time_text: str | None
    h_index: int | None
    sjr: float | None
    citescore: float | None
    impact_factor: float | None
    quality_cost_index: float | None
    submission_format: str | None
    article_types: str | None
    issues_per_year: str | None
    topics: list[str]
    locally_modified: bool

    @field_validator("topics", mode="before")
    @classmethod
    def _topic_names(cls, value: Any) -> list[str]:
        return [getattr(item, "name", item) for item in (value or [])]


class JournalDetail(JournalListItem):
    keywords: str | None
    contact_email: str | None
    sources: list[str]
    details: dict[str, Any]
    created_at: datetime
    updated_at: datetime


class JournalPage(BaseModel):
    items: list[JournalListItem]
    total: int
    page: int
    page_size: int


class FacetValue(BaseModel):
    value: str
    count: int


class Facets(BaseModel):
    topics: list[FacetValue]
    quartiles: list[FacetValue]
    access_types: list[FacetValue]
    countries: list[FacetValue]
    languages: list[FacetValue]
    submission_formats: list[FacetValue]
    publindex_categories: list[FacetValue]
    origins: list[FacetValue]
    apc_statuses: list[FacetValue]
    total: int
    max_apc_usd: float | None
    max_weeks: float | None
    max_h_index: int | None


class ImportReport(BaseModel):
    dry_run: bool
    mode: str
    rows: int
    created: int
    updated: int
    skipped: int
    invalid: int
    duplicates: list[str]
    errors: list[str]
