"""Evalúa similitud de una revista Gold contra el resto del catálogo."""

import argparse
import json
import sys
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from recomendador_revistas.models.thematic_profile import ThematicProfile  # noqa: E402


ARTIFACTS = PACKAGE_ROOT / "models" / "artifacts" / "thematic_profile"
GOLD = PACKAGE_ROOT / "data" / "gold" / "catalogo_texto_tfidf_scibert_apc_real.csv"


def load_profile() -> ThematicProfile:
    metadata = json.loads((ARTIFACTS / "metadata.json").read_text())
    profile = ThematicProfile(
        alpha=float(metadata["alpha"]),
        language=metadata["language"],
        pooling=metadata["pooling"],
        scibert_model=metadata["scibert_model"],
        use_scibert=bool(metadata.get("use_scibert", True)),
    )
    profile.vectorizer = joblib.load(ARTIFACTS / "tfidf_vectorizer.joblib")
    profile.tfidf_matrix = joblib.load(ARTIFACTS / "tfidf_matrix.joblib")
    profile.embedding_matrix = np.load(ARTIFACTS / "scibert_embeddings.npy")
    profile.identifiers = pd.read_csv(ARTIFACTS / "journal_ids.csv")["issn_normalizado"].astype(str).tolist()
    return profile


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--issn", required=True, help="ISSN normalizado de la revista objetivo")
    parser.add_argument("--top-k", type=int, default=10)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    gold = pd.read_csv(GOLD, low_memory=False)
    profile = load_profile()
    result = profile.compare_journal(args.issn, metadata=gold, top_k=args.top_k)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        result.to_csv(args.output, index=False)
        print(f"Resultado guardado en: {args.output}")
    else:
        print(result.to_string(index=False))


if __name__ == "__main__":
    main()