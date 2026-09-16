"""Compara un manuscrito contra las revistas Gold entrenadas."""

import argparse
import sys
from pathlib import Path

import pandas as pd

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from recomendador_revistas.models.thematic_profile import (  # noqa: E402
    build_manuscript_text,
)
from recomendador_revistas.scripts.evaluate_journal import (  # noqa: E402
    GOLD,
    load_profile,
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--title", required=True, help="Título del manuscrito")
    parser.add_argument("--abstract", required=True, help="Resumen del manuscrito")
    parser.add_argument("--keywords", required=True, help="Palabras clave separadas por comas")
    parser.add_argument("--language", choices=["auto", "es", "en"], default="auto")
    parser.add_argument("--top-k", type=int, default=10)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    manuscript = build_manuscript_text(
        title=args.title,
        abstract=args.abstract,
        keywords=args.keywords,
        language=args.language,
    )
    profile = load_profile()
    scores = profile.score(manuscript)
    order = scores.thematic.argsort()[::-1][:args.top_k]
    gold = pd.read_csv(GOLD, low_memory=False)
    result = pd.DataFrame({
        "issn_normalizado": [profile.identifiers[index] for index in order],
        "score_tfidf": scores.tfidf[order],
        "score_scibert": scores.scibert[order],
        "score_tematico": scores.thematic[order],
    })
    metadata = gold.drop_duplicates("issn_normalizado").set_index("issn_normalizado")
    columns = [
        column for column in (
            "apc_monto_usd", "apc_tipo", "cuartil_sjr_ord", "h_index",
            "indice_calidad_costo",
        ) if column in metadata.columns
    ]
    if columns:
        result = result.join(metadata[columns], on="issn_normalizado")
    print(f"Input normalizado: {manuscript}")
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        result.to_csv(args.output, index=False)
        print(f"Resultado guardado en: {args.output}")
    else:
        print(result.to_string(index=False))


if __name__ == "__main__":
    main()