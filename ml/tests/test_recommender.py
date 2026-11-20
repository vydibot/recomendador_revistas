"""Pruebas del recomendador servible (JournalRecommender) con un corpus mínimo."""

import numpy as np
import pandas as pd
import pytest

from recomendador_revistas.models import JournalRecommender, ThematicProfile
from recomendador_revistas.models.thematic_profile import fuse_with_quality


def _metadata() -> pd.DataFrame:
    return pd.DataFrame({
        "issn_normalizado": ["1111-1111", "2222-2222", "3333-3333"],
        "sjr_score_minmax": [0.9, 0.5, 0.1],
        "h_index_minmax": [0.8, 0.5, 0.2],
        "cuartil_sjr_ord": [4, 3, 1],
        "apc_monto_ppp_usd_real": [100.0, 500.0, 2000.0],
    })


@pytest.fixture(scope="module")
def recommender() -> JournalRecommender:
    corpus = pd.DataFrame({
        "issn_normalizado": ["1111-1111", "2222-2222", "3333-3333"],
        "texto_modelo": [
            "machine learning neural network deep learning classification",
            "soil agriculture crop irrigation fertilizer yield",
            "constitutional law court legal rights judicial",
        ],
    })
    profile = ThematicProfile(alpha=1.0, use_scibert=False).fit(corpus)
    return JournalRecommender(profile, _metadata())


def test_recommend_ranks_matching_topic_first(recommender):
    result = recommender.recommend(
        title="Deep learning for crop yield",
        abstract="We train a neural network classification model.",
        keywords="machine learning, deep learning",
        top_k=3,
    )
    assert [item.rank for item in result] == [1, 2, 3]
    assert result[0].issn == "1111-1111"
    assert all(item.score_final is not None for item in result)


def test_top_k_and_priority_order_are_validated(recommender):
    with pytest.raises(ValueError):
        recommender.recommend("a b c", top_k=0)
    with pytest.raises(ValueError):
        recommender.recommend("a b c", priority_order=("impacto", "impacto", "flujo"))
    with pytest.raises(ValueError):
        recommender.recommend("", "", "")


def test_keywords_accept_list(recommender):
    result = recommender.recommend("neural network", keywords=["deep learning", "classification"], top_k=1)
    assert len(result) == 1


def test_info_reports_coverage(recommender):
    info = recommender.info
    assert info.journals_covered == 3
    assert info.quality_weight == 0.5


def test_missing_quality_goes_last_and_is_none():
    thematic = np.array([0.9, 0.1, 0.5])
    quality = np.array([np.nan, 0.8, 0.2])
    final = fuse_with_quality(thematic, quality)
    assert np.isnan(final[0])
    assert list(np.argsort(-final)[:2]) == [2, 1] or list(np.argsort(-final)[:2]) == [1, 2]
    assert np.argsort(-final)[-1] == 0
