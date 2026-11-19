from recomendador_revistas.evaluation.ranking_metrics import (
    accuracy_at_k,
    average_precision,
    evaluate_recommendations,
    f1_at_k,
    ndcg_at_k,
    precision_at_k,
    recall_at_k,
    reciprocal_rank,
)


def test_basic_topk_metrics():
    ranked = ["B", "A", "C", "D"]
    relevant = {"A", "C"}

    assert precision_at_k(ranked, relevant, 2) == 0.5
    assert recall_at_k(ranked, relevant, 2) == 0.5
    assert f1_at_k(ranked, relevant, 2) == 0.5
    assert accuracy_at_k(ranked, relevant, 1) == 0.0
    assert accuracy_at_k(ranked, relevant, 2) == 1.0


def test_map_mrr_and_ndcg():
    ranked = ["B", "A", "C", "D"]
    relevant = {"A", "C"}
    rel_map = {"A": 3.0, "C": 2.0}

    assert round(average_precision(ranked, relevant), 4) == 0.5833
    assert reciprocal_rank(ranked, relevant) == 0.5
    assert 0 < ndcg_at_k(ranked, rel_map, 3) <= 1.0


def test_aggregate_evaluation():
    rankings = [
        ["A", "B", "C"],
        ["C", "B", "A"],
    ]
    relevant_sets = [
        {"A"},
        {"B"},
    ]
    report = evaluate_recommendations(rankings, relevant_sets, ks=(1, 2))

    assert report["queries"] == 2.0
    assert "precision@1" in report
    assert "recall@2" in report
    assert "f1@2" in report
    assert "accuracy@1" in report
    assert "ndcg@2" in report
    assert "map" in report
    assert "mrr" in report
