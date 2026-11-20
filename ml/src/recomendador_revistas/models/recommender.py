"""Recomendador listo para servir (API): perfil entrenado + TOPSIS en caché.

``ThematicProfile.recommend`` recalcula el TOPSIS sobre todo el catálogo en cada
consulta. Aquí el índice calidad-costo se precalcula una sola vez por cada
orden de prioridades posible (3! = 6) y la consulta solo hace similitud coseno,
por lo que la latencia queda dominada por la codificación SciBERT del texto.
"""

from __future__ import annotations

import itertools
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

import numpy as np
import pandas as pd

from ..analysis.indices import DEFAULT_ORDER, DIMENSIONS
from .thematic_profile import (
    ThematicProfile,
    build_manuscript_text,
    fuse_with_quality,
    quality_scores_for,
)


@dataclass(frozen=True)
class Recommendation:
    """Una revista sugerida con sus scores (``None`` cuando no hay dato)."""

    rank: int
    issn: str
    score_tfidf: float | None
    score_scibert: float | None
    score_tematico: float | None
    score_calidad_costo: float | None
    score_final: float | None


@dataclass(frozen=True)
class ModelInfo:
    """Metadatos del modelo cargado, útiles para mostrar su cobertura."""

    alpha: float
    journals_covered: int
    tfidf_features: int
    scibert_model: str
    quality_weight: float
    priority_dimensions: tuple[str, ...]


def _finite_or_none(value: float) -> float | None:
    value = float(value)
    return value if np.isfinite(value) else None


class JournalRecommender:
    """Combina un :class:`ThematicProfile` entrenado con el índice TOPSIS."""

    QUALITY_WEIGHT = 0.5

    def __init__(self, profile: ThematicProfile, metadata: pd.DataFrame) -> None:
        if not profile.identifiers:
            raise ValueError("El perfil no tiene revistas; ejecute fit() o load()")
        self.profile = profile
        self._quality = {
            order: quality_scores_for(profile.identifiers, metadata, order)
            for order in itertools.permutations(DIMENSIONS)
        }
        # El encoder de SciBERT (torch) no se comparte entre hilos sin cuidado.
        self._lock = threading.Lock()

    @classmethod
    def load(cls, artifacts_dir: str | Path, gold_path: str | Path) -> "JournalRecommender":
        """Carga artefactos entrenados y el Gold maestro (parquet o CSV)."""
        gold_path = Path(gold_path)
        gold = (
            pd.read_parquet(gold_path)
            if gold_path.suffix == ".parquet"
            else pd.read_csv(gold_path, low_memory=False)
        )
        return cls(ThematicProfile.load(artifacts_dir), gold)

    @property
    def info(self) -> ModelInfo:
        vectorizer = self.profile.vectorizer
        return ModelInfo(
            alpha=self.profile.alpha,
            journals_covered=len(self.profile.identifiers),
            tfidf_features=len(vectorizer.vocabulary_) if vectorizer is not None else 0,
            scibert_model=self.profile.scibert_model,
            quality_weight=self.QUALITY_WEIGHT,
            priority_dimensions=tuple(DIMENSIONS),
        )

    @property
    def identifiers(self) -> list[str]:
        return list(self.profile.identifiers)

    def warmup(self) -> None:
        """Fuerza la carga de SciBERT para que la primera consulta no la pague."""
        self.recommend("warmup", "warmup", "warmup", top_k=1)

    def recommend(
        self,
        title: str = "",
        abstract: str = "",
        keywords: str | Sequence[str] = "",
        language: str = "auto",
        priority_order: Sequence[str] = DEFAULT_ORDER,
        top_k: int = 10,
    ) -> list[Recommendation]:
        """Ordena las revistas cubiertas por 0.5·temático + 0.5·calidad-costo."""
        if top_k < 1:
            raise ValueError("top_k debe ser positivo")
        order = tuple(priority_order)
        if order not in self._quality:
            raise ValueError(f"priority_order debe ser una permutación de {DIMENSIONS}")
        if not isinstance(keywords, str):
            keywords = ", ".join(str(item) for item in keywords)

        manuscript = build_manuscript_text(title, abstract, keywords, language=language)
        if not manuscript:
            raise ValueError("El manuscrito no contiene texto utilizable")
        with self._lock:
            scores = self.profile.score(manuscript)

        quality = self._quality[order]
        final = fuse_with_quality(scores.thematic, quality, self.QUALITY_WEIGHT)
        # NaN (revista sin dato de costo) queda al final del ranking.
        ranking = np.argsort(-final)[:top_k]
        return [
            Recommendation(
                rank=position + 1,
                issn=self.profile.identifiers[index],
                score_tfidf=_finite_or_none(scores.tfidf[index]),
                score_scibert=_finite_or_none(scores.scibert[index]),
                score_tematico=_finite_or_none(scores.thematic[index]),
                score_calidad_costo=_finite_or_none(quality[index]),
                score_final=_finite_or_none(final[index]),
            )
            for position, index in enumerate(ranking)
        ]
