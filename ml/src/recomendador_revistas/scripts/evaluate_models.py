"""Evalúa rankings Top-N usando ISSN relevantes, por ejemplo la revista de publicación.

Cuando el CSV proviene de ``articulos_tokens.csv``, las métricas
son una evaluación débil de recuperación de la revista donde se publicó cada
paper, no una valoración experta de todas las recomendaciones posibles.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from recomendador_revistas.evaluation.ranking_metrics import evaluate_recommendations  # noqa: E402
from recomendador_revistas.models.thematic_profile import (  # noqa: E402
    ThematicProfile,
    build_manuscript_text,
    build_paper_journal_corpus,
)

REPORTS = PACKAGE_ROOT / "reports"


def _normalize_eval_text_columns(df: pd.DataFrame) -> pd.DataFrame:
    renamed = df.rename(columns={
        "articulo_id": "manuscrito_id",
        "issn_relacionado": "issn_normalizado",
    })
    required = {"manuscrito_id", "titulo", "resumen", "palabras_clave", "issn_normalizado"}
    missing = required - set(renamed.columns)
    if missing:
        raise ValueError(f"Faltan columnas en evaluación: {sorted(missing)}")
    for column in ("titulo", "resumen", "palabras_clave"):
        normalized = renamed[column].fillna("").astype(str).str.replace("--", " ", regex=False)
        renamed[column] = normalized
    return renamed


def _split_ids(ids: list[str], test_size: float, seed: int) -> tuple[set[str], set[str]]:
    rng = np.random.default_rng(seed)
    ids_array = np.array(ids)
    rng.shuffle(ids_array)
    n_test = max(1, int(round(len(ids_array) * test_size)))
    test_ids = set(ids_array[:n_test].tolist())
    train_ids = set(ids_array[n_test:].tolist())
    return train_ids, test_ids


def _group_queries(df: pd.DataFrame) -> pd.DataFrame:
    grouped = (
        df.groupby("manuscrito_id", as_index=False)
        .agg({
            "titulo": "first",
            "resumen": "first",
            "palabras_clave": "first",
            "issn_normalizado": lambda x: sorted(set(map(str, x))),
        })
        .rename(columns={"issn_normalizado": "relevantes"})
    )
    return grouped


def _score_queries(
    profile: ThematicProfile,
    queries: pd.DataFrame,
    progress_label: str = "consultas",
) -> tuple[list[list[str]], list[list[str]], list[list[str]]]:
    ranked_tfidf = []
    ranked_scibert = []
    ranked_fused = []
    total = len(queries)
    report_every = max(1, total // 20)
    for position, (_, row) in enumerate(queries.iterrows(), start=1):
        manuscript = build_manuscript_text(
            row["titulo"],
            row["resumen"],
            row["palabras_clave"],
            language="auto",
        )
        scores = profile.score(manuscript)
        order_tfidf = np.argsort(-scores.tfidf)
        order_scibert = np.argsort(-scores.scibert)
        order_fused = np.argsort(-scores.thematic)
        ranked_tfidf.append([profile.identifiers[i] for i in order_tfidf])
        ranked_scibert.append([profile.identifiers[i] for i in order_scibert])
        ranked_fused.append([profile.identifiers[i] for i in order_fused])
        if position == 1 or position == total or position % report_every == 0:
            percentage = 100.0 * position / total if total else 100.0
            print(
                f"[evaluacion] {progress_label}: {position}/{total} ({percentage:.1f}%)",
                flush=True,
            )
    return ranked_tfidf, ranked_scibert, ranked_fused


def _select_alpha(train_queries: pd.DataFrame, profile: ThematicProfile, ks=(10,), candidates=np.linspace(0, 1, 11)) -> float:
    best_alpha = 0.5
    best_score = -1.0
    for alpha in candidates:
        profile.alpha = float(alpha)
        print(f"[evaluacion] ajustando alpha={alpha:.3f}", flush=True)
        _, _, ranked = _score_queries(profile, train_queries, progress_label=f"alpha={alpha:.3f}")
        metrics = evaluate_recommendations(
            rankings=ranked,
            relevant_sets=[set(items) for items in train_queries["relevantes"]],
            ks=ks,
        )
        score = metrics[f"ndcg@{ks[0]}"]
        if score > best_score:
            best_score = score
            best_alpha = float(alpha)
    profile.alpha = best_alpha
    return best_alpha


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evaluation-csv", type=Path, required=True)
    parser.add_argument("--test-size", type=float, default=0.2)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--ks", type=str, default="5,10,20")
    parser.add_argument("--alpha-grid", type=str, default="0.0,0.1,0.2,0.3,0.4,0.5,0.6,0.7,0.8,0.9,1.0")
    parser.add_argument("--output-json", type=Path, default=REPORTS / "model_eval_topn.json")
    args = parser.parse_args()

    print(f"[evaluacion] cargando dataset: {args.evaluation_csv}", flush=True)
    eval_df = _normalize_eval_text_columns(pd.read_csv(args.evaluation_csv, low_memory=False))
    query_df = _group_queries(eval_df)
    print(f"[evaluacion] consultas agrupadas: {len(query_df)} manuscritos", flush=True)

    train_ids, test_ids = _split_ids(query_df["manuscrito_id"].astype(str).tolist(), args.test_size, args.seed)
    train_queries = query_df[query_df["manuscrito_id"].astype(str).isin(train_ids)].reset_index(drop=True)
    test_queries = query_df[query_df["manuscrito_id"].astype(str).isin(test_ids)].reset_index(drop=True)
    print(
        f"[evaluacion] split: train={len(train_queries)}, test={len(test_queries)}",
        flush=True,
    )

    train_papers = eval_df[eval_df["manuscrito_id"].astype(str).isin(train_ids)].copy()
    print("[evaluacion] construyendo perfiles de revista con papers de train...", flush=True)
    corpus = build_paper_journal_corpus(train_papers)
    print(f"[evaluacion] perfiles construidos: {len(corpus)} revistas", flush=True)
    print("[evaluacion] ajustando perfil TF-IDF/SciBERT...", flush=True)
    profile = ThematicProfile(alpha=0.5, language="auto", pooling="mean", use_scibert=True).fit(corpus)
    print(f"[evaluacion] perfil ajustado en dispositivo: {profile.scibert_device}", flush=True)

    alpha_candidates = [float(x.strip()) for x in args.alpha_grid.split(",") if x.strip()]
    best_alpha = _select_alpha(train_queries, profile, ks=(10,), candidates=alpha_candidates)

    print("[evaluacion] evaluando conjunto de prueba...", flush=True)
    ranked_tfidf, ranked_scibert, ranked_fused = _score_queries(
        profile,
        test_queries,
        progress_label="test",
    )
    relevant_sets = [set(items) for items in test_queries["relevantes"]]
    ks = tuple(int(x.strip()) for x in args.ks.split(",") if x.strip())

    tfidf_metrics = evaluate_recommendations(ranked_tfidf, relevant_sets, ks=ks)
    scibert_metrics = evaluate_recommendations(ranked_scibert, relevant_sets, ks=ks)
    fused_metrics = evaluate_recommendations(ranked_fused, relevant_sets, ks=ks)

    payload = {
        "dataset": str(args.evaluation_csv),
        "journal_corpus": "papers_train_agrupados_por_issn",
        "ground_truth": "revista_de_publicacion" if "articulos_tokens" in args.evaluation_csv.name else "issn_relevante_declarado",
        "train_queries": int(len(train_queries)),
        "test_queries": int(len(test_queries)),
        "test_size": float(args.test_size),
        "alpha_candidates": alpha_candidates,
        "best_alpha": best_alpha,
        "tfidf": tfidf_metrics,
        "scibert": scibert_metrics,
        "fused": fused_metrics,
    }

    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print("[evaluacion] métricas calculadas", flush=True)
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    print(f"Reporte guardado en: {args.output_json}")


if __name__ == "__main__":
    main()
