"""Métricas de ranking Top-N para recomendación de revistas."""

from __future__ import annotations

import math
from typing import Iterable, Sequence


def precision_at_k(ranked_ids: Sequence[str], relevant_ids: set[str], k: int) -> float:
    top = list(ranked_ids[:k])
    if k <= 0:
        raise ValueError("k debe ser positivo")
    if not top:
        return 0.0
    hits = sum(1 for item in top if item in relevant_ids)
    return hits / float(k)


def recall_at_k(ranked_ids: Sequence[str], relevant_ids: set[str], k: int) -> float:
    if k <= 0:
        raise ValueError("k debe ser positivo")
    if not relevant_ids:
        return 0.0
    top = list(ranked_ids[:k])
    hits = sum(1 for item in top if item in relevant_ids)
    return hits / float(len(relevant_ids))


def f1_at_k(ranked_ids: Sequence[str], relevant_ids: set[str], k: int) -> float:
    p = precision_at_k(ranked_ids, relevant_ids, k)
    r = recall_at_k(ranked_ids, relevant_ids, k)
    return 0.0 if (p + r) == 0 else 2.0 * p * r / (p + r)


def accuracy_at_k(ranked_ids: Sequence[str], relevant_ids: set[str], k: int) -> float:
    if k <= 0:
        raise ValueError("k debe ser positivo")
    top = set(ranked_ids[:k])
    return 1.0 if top.intersection(relevant_ids) else 0.0


def average_precision(ranked_ids: Sequence[str], relevant_ids: set[str]) -> float:
    if not relevant_ids:
        return 0.0
    hit_count = 0
    precision_sum = 0.0
    for idx, item in enumerate(ranked_ids, start=1):
        if item in relevant_ids:
            hit_count += 1
            precision_sum += hit_count / idx
    return precision_sum / len(relevant_ids)


def reciprocal_rank(ranked_ids: Sequence[str], relevant_ids: set[str]) -> float:
    for idx, item in enumerate(ranked_ids, start=1):
        if item in relevant_ids:
            return 1.0 / idx
    return 0.0


def dcg_at_k(ranked_ids: Sequence[str], relevance_map: dict[str, float], k: int) -> float:
    if k <= 0:
        raise ValueError("k debe ser positivo")
    score = 0.0
    for i, item in enumerate(ranked_ids[:k], start=1):
        rel = float(relevance_map.get(item, 0.0))
        if rel > 0:
            score += (2.0**rel - 1.0) / math.log2(i + 1.0)
    return score


def ndcg_at_k(ranked_ids: Sequence[str], relevance_map: dict[str, float], k: int) -> float:
    dcg = dcg_at_k(ranked_ids, relevance_map, k)
    ideal = sorted(relevance_map.values(), reverse=True)[:k]
    idcg = 0.0
    for i, rel in enumerate(ideal, start=1):
        idcg += (2.0**float(rel) - 1.0) / math.log2(i + 1.0)
    return 0.0 if idcg == 0 else dcg / idcg


def evaluate_recommendations(
    rankings: Iterable[Sequence[str]],
    relevant_sets: Iterable[set[str]],
    ks: Sequence[int] = (5, 10, 20),
    relevance_maps: Iterable[dict[str, float]] | None = None,
) -> dict[str, float]:
    """Agrega métricas Top-N para múltiples consultas/manuscritos."""
    rankings_list = list(rankings)
    relevant_list = list(relevant_sets)
    if len(rankings_list) != len(relevant_list):
        raise ValueError("rankings y relevant_sets deben tener la misma longitud")

    if relevance_maps is None:
        relevance_list = [{item: 1.0 for item in relevant} for relevant in relevant_list]
    else:
        relevance_list = list(relevance_maps)
        if len(relevance_list) != len(rankings_list):
            raise ValueError("relevance_maps debe tener la misma longitud que rankings")

    n = len(rankings_list)
    if n == 0:
        return {"queries": 0.0}

    metrics: dict[str, float] = {"queries": float(n)}
    ap_values = []
    rr_values = []

    for k in ks:
        p_vals, r_vals, f1_vals, a_vals, ndcg_vals = [], [], [], [], []
        for ranking, relevant, rel_map in zip(rankings_list, relevant_list, relevance_list):
            p_vals.append(precision_at_k(ranking, relevant, k))
            r_vals.append(recall_at_k(ranking, relevant, k))
            f1_vals.append(f1_at_k(ranking, relevant, k))
            a_vals.append(accuracy_at_k(ranking, relevant, k))
            ndcg_vals.append(ndcg_at_k(ranking, rel_map, k))
        metrics[f"precision@{k}"] = float(sum(p_vals) / n)
        metrics[f"recall@{k}"] = float(sum(r_vals) / n)
        metrics[f"f1@{k}"] = float(sum(f1_vals) / n)
        metrics[f"accuracy@{k}"] = float(sum(a_vals) / n)
        metrics[f"ndcg@{k}"] = float(sum(ndcg_vals) / n)

    for ranking, relevant in zip(rankings_list, relevant_list):
        ap_values.append(average_precision(ranking, relevant))
        rr_values.append(reciprocal_rank(ranking, relevant))

    metrics["map"] = float(sum(ap_values) / n)
    metrics["mrr"] = float(sum(rr_values) / n)
    return metrics
