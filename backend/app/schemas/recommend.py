from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

Dimension = Literal["impacto", "eficiencia", "flujo"]


class RecommendRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    title: str = Field(default="", max_length=500)
    abstract: str = Field(default="", max_length=10_000)
    keywords: str = Field(default="", max_length=2_000)
    language: Literal["auto", "es", "en"] = "auto"
    # Orden de prioridad de las dimensiones del TOPSIS (de mayor a menor).
    priority_order: list[Dimension] = Field(default=["impacto", "eficiencia", "flujo"])
    top_k: int = Field(default=10, ge=1, le=50)

    @field_validator("priority_order")
    @classmethod
    def _permutation(cls, value: list[str]) -> list[str]:
        if sorted(value) != ["eficiencia", "flujo", "impacto"]:
            raise ValueError("priority_order debe contener impacto, eficiencia y flujo una vez")
        return value

    @model_validator(mode="after")
    def _has_text(self) -> "RecommendRequest":
        if len(f"{self.title}{self.abstract}{self.keywords}".strip()) < 20:
            raise ValueError("Ingresa al menos título, resumen o palabras clave (20+ caracteres)")
        return self


class JournalSummary(BaseModel):
    id: int
    title: str
    url: str | None
    country: str | None
    access_type: str | None
    quartile: str | None
    publindex_category: str | None
    apc_usd: float | None
    apc_status: str
    weeks_to_publication: float | None
    h_index: int | None
    topics: list[str]


class RecommendedJournal(BaseModel):
    rank: int
    issn: str
    journal: JournalSummary | None
    score_tfidf: float | None
    score_scibert: float | None
    score_tematico: float | None
    score_calidad_costo: float | None
    score_final: float | None


class ModelInfoOut(BaseModel):
    available: bool
    alpha: float | None = None
    journals_covered: int | None = None
    catalog_total: int | None = None
    tfidf_features: int | None = None
    scibert_model: str | None = None
    quality_weight: float | None = None


class RecommendResponse(BaseModel):
    model: ModelInfoOut
    priority_order: list[str]
    results: list[RecommendedJournal]
