"""Entrena el perfil temático TF-IDF + SciBERT sobre el Gold bilingüe."""

import sys
from pathlib import Path

import pandas as pd

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from recomendador_revistas.models.thematic_profile import (  # noqa: E402
    ThematicProfile,
    build_journal_corpus,
)


INPUT = PACKAGE_ROOT / "data" / "gold" / "catalogo_texto_tfidf_scibert_apc_real.csv"
ARTIFACTS = PACKAGE_ROOT / "models" / "artifacts" / "thematic_profile"


def main() -> None:
    gold = pd.read_csv(INPUT, low_memory=False)
    corpus = build_journal_corpus(
        gold,
        language="auto",
        text_columns=("texto_espanol", "texto_ingles"),
    )
    profile = ThematicProfile(
        alpha=0.5,
        language="auto",
        pooling="mean",
        use_scibert=True,
    )
    profile.fit(corpus)
    profile.save(ARTIFACTS)
    print(f"Dataset: {INPUT}")
    print(f"Registros entrenados: {len(corpus)}")
    print(f"Features TF-IDF: {len(profile.vectorizer.vocabulary_)}")
    print(f"Dimensión SciBERT: {profile.embedding_matrix.shape[1]}")
    print(f"Artefactos: {ARTIFACTS}")


if __name__ == "__main__":
    main()