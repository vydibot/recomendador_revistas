"""Servicio del recomendador: carga perezosa/en segundo plano y enriquecimiento con la BD."""

from __future__ import annotations

import logging
import threading
from dataclasses import replace
from typing import Protocol

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.models import Journal
from app.schemas.recommend import (
    JournalSummary,
    ModelInfoOut,
    RecommendedJournal,
    RecommendRequest,
    RecommendResponse,
)
from app.services.journals import journals_by_issn

log = logging.getLogger(__name__)


class RecommenderBackend(Protocol):
    """Contrato mínimo del motor (``JournalRecommender`` lo cumple)."""

    @property
    def info(self): ...
    def warmup(self) -> None: ...
    def recommend(self, **kwargs): ...


class RecommenderService:
    def __init__(self, settings: Settings, engine: RecommenderBackend | None = None) -> None:
        self._settings = settings
        self._engine = engine
        self._error: str | None = None
        self._thread: threading.Thread | None = None
        self._covered: int | None = None

    # -- ciclo de vida ---------------------------------------------------
    def start_loading(self) -> None:
        """Carga el modelo en un hilo para que la API responda desde el primer segundo."""
        if self._engine is not None or not self._settings.recommender_enabled:
            return
        self._thread = threading.Thread(target=self._load, name="recommender-load", daemon=True)
        self._thread.start()

    def _load(self) -> None:
        try:
            from recomendador_revistas.models.recommender import JournalRecommender

            engine = JournalRecommender.load(
                self._settings.ml_artifacts_dir, self._settings.ml_gold_path
            )
            engine.warmup()
            self._engine = engine
            log.info("Recomendador listo: %s revistas", engine.info.journals_covered)
        except Exception as exc:  # noqa: BLE001 - se informa por /health, la API sigue viva
            self._error = f"{type(exc).__name__}: {exc}"
            log.exception("No se pudo cargar el recomendador")

    @property
    def status(self) -> str:
        if self._engine is not None:
            return "ready"
        if not self._settings.recommender_enabled:
            return "disabled"
        if self._error:
            return "error"
        return "loading"

    @property
    def error(self) -> str | None:
        return self._error

    # -- consultas -------------------------------------------------------
    def info(self, db: Session) -> ModelInfoOut:
        if self._engine is None:
            return ModelInfoOut(available=False)
        info = self._engine.info
        total = db.scalar(select(func.count(Journal.id))) or 0
        return ModelInfoOut(
            available=True,
            alpha=info.alpha,
            journals_covered=self._covered_journals(db, info.journals_covered),
            catalog_total=total,
            tfidf_features=info.tfidf_features,
            scibert_model=info.scibert_model,
            quality_weight=info.quality_weight,
        )

    def _covered_journals(self, db: Session, fallback: int) -> int:
        """Revistas distintas cubiertas (varios ISSN del modelo pueden ser una misma revista)."""
        if self._covered is None:
            identifiers = list(getattr(self._engine, "identifiers", []))
            if not identifiers:
                return fallback
            mapped = journals_by_issn(db, identifiers)
            unmapped = [issn for issn in identifiers if issn not in mapped]
            self._covered = len({journal.id for journal in mapped.values()}) + len(unmapped)
        return self._covered

    def recommend(self, db: Session, request: RecommendRequest) -> RecommendResponse:
        if self._engine is None:
            raise RecommenderUnavailableError(self.status, self._error)
        # Varias filas del Gold pueden ser la misma revista (otro año/ISSN): se pide margen
        # al motor y se deja la mejor posición de cada revista.
        raw = self._engine.recommend(
            title=request.title,
            abstract=request.abstract,
            keywords=request.keywords,
            language=request.language,
            priority_order=tuple(request.priority_order),
            top_k=min(request.top_k * 3, 150),
        )
        by_issn = journals_by_issn(db, [item.issn for item in raw])
        seen: set[int] = set()
        results = []
        for item in raw:
            journal = by_issn.get(item.issn)
            if journal is not None:
                if journal.id in seen:
                    continue
                seen.add(journal.id)
            results.append(replace(item, rank=len(results) + 1))
            if len(results) == request.top_k:
                break
        journals = by_issn
        return RecommendResponse(
            model=self.info(db),
            priority_order=list(request.priority_order),
            results=[
                RecommendedJournal(
                    rank=item.rank,
                    issn=item.issn,
                    journal=_summary(journals.get(item.issn)),
                    score_tfidf=item.score_tfidf,
                    score_scibert=item.score_scibert,
                    score_tematico=item.score_tematico,
                    score_calidad_costo=item.score_calidad_costo,
                    score_final=item.score_final,
                )
                for item in results
            ],
        )


class RecommenderUnavailableError(RuntimeError):
    def __init__(self, status: str, error: str | None) -> None:
        super().__init__(status)
        self.status = status
        self.error = error


def _summary(journal: Journal | None) -> JournalSummary | None:
    if journal is None:
        return None
    return JournalSummary(
        id=journal.id,
        title=journal.title,
        url=journal.url,
        country=journal.country,
        access_type=journal.access_type,
        quartile=journal.quartile,
        publindex_category=journal.publindex_category,
        apc_usd=journal.apc_usd,
        apc_status=journal.apc_status,
        weeks_to_publication=journal.weeks_to_publication,
        h_index=journal.h_index,
        topics=[topic.name for topic in journal.topics],
    )
