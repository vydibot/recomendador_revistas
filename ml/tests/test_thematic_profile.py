import numpy as np
import pandas as pd

from recomendador_revistas.models.thematic_profile import (
    ThematicProfile,
    build_journal_corpus,
    build_manuscript_text,
    clean_scientific_text,
    preprocess_text,
    select_alpha,
)


def test_scientific_cleaning_removes_latex_and_equations():
    text = r"A study $x_i^2 + y_i^2$ uses \\textbf{robust} methods and \\alpha."
    cleaned = clean_scientific_text(text)
    assert "alpha" not in cleaned
    assert "x_i" not in cleaned
    assert "robust" in cleaned


def test_preprocess_removes_stopwords_and_returns_lemmas():
    processed = preprocess_text("The studies are evaluating methods", language="en")
    assert "the" not in processed.split()
    assert "studi" in processed.split()
    assert "evaluat" in processed.split()


def test_thematic_profile_fuses_tfidf_and_scibert_scores_without_model():
    gold = pd.DataFrame({
        "issn_normalizado": ["1111-1111", "2222-2222"],
        "texto_espanol": ["salud publica medicina", "economia politica"],
        "texto_ingles": ["public health medicine", "political economy"],
    })
    corpus = build_journal_corpus(gold)
    profile = ThematicProfile(alpha=0.75).fit(corpus)
    scores = profile.score("public health medicine")

    assert scores.tfidf.shape == (2,)
    assert scores.scibert.shape == (2,)
    assert np.allclose(scores.thematic, 0.75 * scores.tfidf + 0.25 * scores.scibert)
    assert profile.recommend("public health medicine", top_k=1).iloc[0]["issn_normalizado"] == "1111-1111"


def test_thematic_profile_validates_alpha():
    try:
        ThematicProfile(alpha=1.1)
    except ValueError:
        pass
    else:
        raise AssertionError("alpha fuera de rango debe producir ValueError")


def test_select_alpha_uses_validation_ranking():
    tfidf = np.array([0.9, 0.4, 0.2])
    scibert = np.array([0.2, 0.8, 0.1])
    assert select_alpha(tfidf, scibert, relevant_indices=[1]) == 0.0


def test_manuscript_input_combines_title_abstract_and_keywords():
    text = build_manuscript_text(
        title="The effects of health policy",
        abstract="This study evaluates public health outcomes.",
        keywords="health, policy, medicine",
        language="en",
    )
    assert "health" in text
    assert "policy" in text
    assert "the" not in text.split()