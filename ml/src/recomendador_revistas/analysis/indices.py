"""Índices bibliométricos y de relación calidad-costo.

El índice de calidad-costo se calcula con TOPSIS. La interfaz solo necesita
recibir el orden de las tres dimensiones; ``rank_sum_weights`` convierte ese
orden en pesos reproducibles que suman uno.
"""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np
import pandas as pd


DIMENSIONS = ("impacto", "eficiencia", "flujo")
DEFAULT_ORDER = DIMENSIONS

_CRITERIA = {
    "impacto": (
        ("sjr_score_minmax", True),
        ("h_index_minmax", True),
        ("cuartil_sjr_ord", True),
    ),
    "flujo": (
        ("total_citas_3y", True),
        ("citas_por_doc_2y", True),
        ("ratio_citas_docs", True),
        ("total_docs_3y", False),
    ),
    "eficiencia": (
        ("editorial_rapida", True),
        ("semanas_pub_minmax", False),
        ("semanas_submission_publicacion", False),
        ("apc_monto_ppp_usd", False),
    ),
}


def rank_sum_weights(order: Sequence[str] = DEFAULT_ORDER) -> dict[str, float]:
    """Convierte un orden de prioridad en pesos Rank-Sum que suman uno."""
    if len(order) != len(DIMENSIONS) or set(order) != set(DIMENSIONS):
        raise ValueError(f"order debe ser una permutación de {DIMENSIONS}")
    ranks = {dimension: position + 1 for position, dimension in enumerate(order)}
    denominator = sum(len(DIMENSIONS) - rank + 1 for rank in ranks.values())
    return {
        dimension: (len(DIMENSIONS) - rank + 1) / denominator
        for dimension, rank in ranks.items()
    }


def _minmax(values: pd.Series) -> pd.Series:
    numeric = pd.to_numeric(values, errors="coerce").astype("float64")
    if numeric.notna().sum() == 0:
        return pd.Series(0.0, index=values.index)
    filled = numeric.fillna(numeric.median())
    spread = filled.max() - filled.min()
    return pd.Series(0.0, index=values.index) if spread == 0 else (filled - filled.min()) / spread


def topsis_quality_cost_index(
    dataset: pd.DataFrame,
    order: Sequence[str] = DEFAULT_ORDER,
) -> pd.DataFrame:
    """Añade el coeficiente TOPSIS de calidad-costo-eficiencia.

    Los criterios se normalizan antes de ponderar. Los criterios de beneficio
    buscan el máximo y los de fricción/costo el mínimo. Solo se usan columnas
    presentes en el dataset, por lo que el catálogo puede tener cobertura
    parcial sin romper el pipeline.
    """
    weights = rank_sum_weights(order)
    result = dataset.copy()
    criteria: list[tuple[str, str, bool]] = []
    for dimension in DIMENSIONS:
        for column, benefit in _CRITERIA[dimension]:
            if column in result.columns:
                criteria.append((dimension, column, benefit))
    if not criteria:
        result["indice_topsis_calidad_costo"] = 0.0
        result["indice_calidad_costo"] = 0.0
        return result

    matrix = []
    for dimension, column, benefit in criteria:
        normalized = _minmax(result[column])
        if not benefit:
            normalized = 1.0 - normalized
        matrix.append(normalized.to_numpy(dtype=float) * weights[dimension])
    weighted = np.column_stack(matrix)
    positive = weighted.max(axis=0)
    negative = weighted.min(axis=0)
    distance_positive = np.linalg.norm(weighted - positive, axis=1)
    distance_negative = np.linalg.norm(weighted - negative, axis=1)
    denominator = distance_positive + distance_negative
    score = np.divide(
        distance_negative,
        denominator,
        out=np.full(len(result), 0.5, dtype=float),
        where=denominator > 0,
    )
    result["indice_topsis_calidad_costo"] = np.clip(score, 0.0, 1.0)
    result["indice_calidad_costo"] = result["indice_topsis_calidad_costo"]
    return result


def build_indices(dataset: pd.DataFrame, order: Sequence[str] = DEFAULT_ORDER) -> pd.DataFrame:
    """Punto de entrada para calcular índices del catálogo Gold."""
    if not isinstance(dataset, pd.DataFrame):
        raise TypeError("dataset debe ser un pandas.DataFrame")
    return topsis_quality_cost_index(dataset, order=order)