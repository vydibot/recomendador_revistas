"""Ajusta el perfil temático sobre artículos Gold agrupados por ISSN."""

import argparse
import sys
from pathlib import Path

import pandas as pd

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from recomendador_revistas.models.thematic_profile import (  # noqa: E402
    ThematicProfile,
    build_paper_journal_corpus,
)
from recomendador_revistas.scripts.evaluate_models import (  # noqa: E402
    _group_queries,
    _normalize_eval_text_columns,
    _select_alpha,
    _split_ids,
)


INPUT = PACKAGE_ROOT / "data" / "gold" / "articulos_tokens.csv"
ARTIFACTS = PACKAGE_ROOT / "models" / "artifacts" / "thematic_profile"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--test-size", type=float, default=0.2)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument(
        "--alpha-grid",
        default="0.0,0.1,0.2,0.3,0.4,0.5,0.6,0.7,0.8,0.9,1.0",
    )
    args = parser.parse_args()

    gold = pd.read_csv(INPUT, low_memory=False)
    eval_gold = _normalize_eval_text_columns(gold.copy())
    queries = _group_queries(eval_gold)
    train_ids, _ = _split_ids(
        queries["manuscrito_id"].astype(str).tolist(), args.test_size, args.seed
    )
    train_queries = queries[queries["manuscrito_id"].astype(str).isin(train_ids)].reset_index(drop=True)
    train_gold = gold[gold["articulo_id"].astype(str).isin(train_ids)].copy()
    train_corpus = build_paper_journal_corpus(train_gold)
    profile = ThematicProfile(
        alpha=0.5,
        language="auto",
        pooling="mean",
        use_scibert=True,
    ).fit(train_corpus)
    alpha_candidates = [float(value.strip()) for value in args.alpha_grid.split(",") if value.strip()]
    best_alpha = _select_alpha(train_queries, profile, ks=(10,), candidates=alpha_candidates)

    # Alpha se selecciona sin tocar el conjunto reservado y luego se refitea
    # el vectorizador y SciBERT sobre todo el corpus disponible.
    corpus = build_paper_journal_corpus(gold)
    profile.alpha = best_alpha
    profile.fit(corpus)
    profile.save(ARTIFACTS)
    print(f"Dataset: {INPUT}")
    print(f"Registros entrenados: {len(corpus)}")
    print(f"Features TF-IDF: {len(profile.vectorizer.vocabulary_)}")
    print(f"Dimensión SciBERT: {profile.embedding_matrix.shape[1]}")
    print(f"Dispositivo SciBERT: {profile.scibert_device}")
    print(f"Alpha seleccionado: {best_alpha:.3f}")
    print(f"Artefactos: {ARTIFACTS}")


if __name__ == "__main__":
    main()