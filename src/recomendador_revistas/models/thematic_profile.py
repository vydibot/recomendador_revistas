"""Módulo A: perfil temático de manuscritos y revistas.

Implementa el flujo:

1. Limpieza de LaTeX, ecuaciones y comandos.
2. Tokenización, stopwords y lematización ligera reproducible.
3. Representación TF-IDF.
4. Embeddings SciBERT opcionales mediante promedio de tokens o CLS.
5. Similitud coseno y fusión ``alpha * TF-IDF + (1-alpha) * SciBERT``.

El corpus de revistas puede construirse directamente desde el Gold textual
existente usando ``texto_espanol`` y ``texto_ingles``; no se incorporan URLs ni
campos de enlaces al perfil temático.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Literal, Sequence

import numpy as np
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity


LANGUAGE = Literal["es", "en", "auto"]
POOLING = Literal["mean", "cls"]

_LATEX_COMMAND = re.compile(r"\\[a-zA-Z]+\s*")
_LATEX_DELIMITER = re.compile(r"\$\$.*?\$\$|\\\(.*?\\\)|\\\[.*?\\\]", re.DOTALL)
_INLINE_MATH = re.compile(r"\$(?:[^$]|\\\$)+\$")
_DISPLAY_MATH = re.compile(r"\b(?:equation|align|gather|math)\*?\b.*?\b(?:end)\b", re.DOTALL | re.IGNORECASE)
_NON_WORD = re.compile(r"[^\w\s-]", re.UNICODE)
_SPACE = re.compile(r"\s+")

_STOPWORDS_ES = {
    "a", "al", "con", "de", "del", "el", "en", "es", "la", "las",
    "lo", "los", "para", "por", "que", "se", "su", "un", "una", "y",
}
_STOPWORDS_EN = {
    "a", "an", "and", "are", "as", "at", "be", "by", "for", "from",
    "in", "is", "it", "of", "on", "or", "that", "the", "this", "to",
    "was", "were", "with",
}


def clean_scientific_text(text: object) -> str:
    """Elimina comandos LaTeX, ecuaciones, símbolos y espacios redundantes."""
    if text is None or pd.isna(text):
        return ""
    value = str(text)
    value = _DISPLAY_MATH.sub(" ", value)
    value = _LATEX_DELIMITER.sub(" ", value)
    value = _INLINE_MATH.sub(" ", value)
    value = _LATEX_COMMAND.sub(" ", value)
    value = value.replace("{", " ").replace("}", " ")
    value = _NON_WORD.sub(" ", value.lower())
    return _SPACE.sub(" ", value).strip()


def _lemma_token(token: str, language: LANGUAGE) -> str:
    """Lematización determinista ligera cuando no hay modelo lingüístico.

    La función conserva términos científicos y aplica solo reglas seguras para
    flexiones frecuentes; no inventa raíces para tokens cortos o técnicos.
    """
    if len(token) <= 4 or any(character.isdigit() for character in token):
        return token
    if language == "es":
        for suffix in ("amientos", "imientos", "aciones", "mente", "ando", "iendo", "es", "os", "as"):
            if token.endswith(suffix) and len(token) - len(suffix) >= 4:
                return token[: -len(suffix)]
    if language == "en":
        for suffix in ("ization", "ations", "ingly", "edly", "ing", "ed", "es", "s"):
            if token.endswith(suffix) and len(token) - len(suffix) >= 4:
                return token[: -len(suffix)]
    return token


def preprocess_text(text: object, language: LANGUAGE = "auto") -> str:
    """Tokeniza, filtra stopwords y lematiza un texto científico."""
    cleaned = clean_scientific_text(text)
    if not cleaned:
        return ""
    stopwords = _STOPWORDS_ES | _STOPWORDS_EN if language == "auto" else (
        _STOPWORDS_ES if language == "es" else _STOPWORDS_EN
    )
    tokens = [
        _lemma_token(token, language if language != "auto" else "auto")
        for token in cleaned.split()
        if token not in stopwords and len(token) > 1
    ]
    return " ".join(tokens)


def build_journal_corpus(
    gold: pd.DataFrame,
    language: LANGUAGE = "auto",
    text_columns: Sequence[str] = ("texto_espanol", "texto_ingles"),
) -> pd.DataFrame:
    """Prepara el corpus Gold textual conservando el ISSN como identificador."""
    if "issn_normalizado" not in gold.columns:
        raise ValueError("El dataset Gold requiere issn_normalizado")
    available = [column for column in text_columns if column in gold.columns]
    if not available:
        raise ValueError(f"No se encontraron columnas textuales: {text_columns}")
    corpus = gold[["issn_normalizado", *available]].copy()
    corpus["texto_modelo"] = corpus[available].fillna("").astype(str).agg(" ".join, axis=1)
    corpus["texto_modelo"] = corpus["texto_modelo"].map(
        lambda value: preprocess_text(value, language)
    )
    return corpus[["issn_normalizado", "texto_modelo"]]


def build_manuscript_text(
    title: object = "",
    abstract: object = "",
    keywords: object = "",
    language: LANGUAGE = "auto",
) -> str:
    """Construye el input normalizado del manuscrito para ambos modelos."""
    fields = [title, abstract, keywords]
    raw_text = " ".join(
        str(field).strip() for field in fields
        if field is not None and not pd.isna(field) and str(field).strip()
    )
    return preprocess_text(raw_text, language)


@dataclass
class ThematicScores:
    """Resultados comparables de las dos representaciones."""

    tfidf: np.ndarray
    scibert: np.ndarray
    thematic: np.ndarray


def select_alpha(
    tfidf_scores: np.ndarray,
    scibert_scores: np.ndarray,
    relevant_indices: Sequence[int],
    candidates: Iterable[float] = np.linspace(0.0, 1.0, 11),
) -> float:
    """Selecciona ``alpha`` maximizando MRR sobre un conjunto de validación.

    ``relevant_indices`` contiene los índices de revistas relevantes para una
    consulta. En caso de empate se prefiere el alpha menor, favoreciendo la
    representación contextual cuando ambas rinden igual.
    """
    tfidf = np.asarray(tfidf_scores, dtype=float)
    scibert = np.asarray(scibert_scores, dtype=float)
    relevant = set(int(index) for index in relevant_indices)
    if tfidf.shape != scibert.shape or tfidf.ndim != 1:
        raise ValueError("Los scores TF-IDF y SciBERT deben ser vectores del mismo tamaño")
    if not relevant or not relevant.issubset(range(len(tfidf))):
        raise ValueError("relevant_indices debe contener índices válidos y no estar vacío")

    best_alpha = None
    best_mrr = -1.0
    for alpha in candidates:
        alpha = float(alpha)
        if not 0.0 <= alpha <= 1.0:
            raise ValueError("Cada alpha candidato debe estar entre 0 y 1")
        fused = alpha * tfidf + (1.0 - alpha) * scibert
        ranking = np.argsort(-fused)
        reciprocal_rank = next(
            (1.0 / (position + 1) for position, index in enumerate(ranking) if index in relevant),
            0.0,
        )
        if reciprocal_rank > best_mrr:
            best_alpha = alpha
            best_mrr = reciprocal_rank
    return float(best_alpha)


class ThematicProfile:
    """Perfil temático TF-IDF + SciBERT con fusión ajustable por alpha."""

    def __init__(
        self,
        alpha: float = 0.5,
        language: LANGUAGE = "auto",
        pooling: POOLING = "mean",
        scibert_model: str = "allenai/scibert_scivocab_uncased",
        use_scibert: bool = False,
    ) -> None:
        if not 0.0 <= alpha <= 1.0:
            raise ValueError("alpha debe estar entre 0 y 1")
        if pooling not in {"mean", "cls"}:
            raise ValueError("pooling debe ser 'mean' o 'cls'")
        self.alpha = alpha
        self.language = language
        self.pooling = pooling
        self.scibert_model = scibert_model
        self.use_scibert = use_scibert
        self.vectorizer: TfidfVectorizer | None = None
        self.tfidf_matrix = None
        self.embedding_matrix: np.ndarray | None = None
        self.identifiers: list[str] = []
        self._tokenizer = None
        self._encoder = None

    def fit(self, corpus: pd.DataFrame) -> "ThematicProfile":
        """Ajusta TF-IDF y, si está disponible, SciBERT sobre un corpus Gold."""
        if not {"issn_normalizado", "texto_modelo"}.issubset(corpus.columns):
            raise ValueError("El corpus requiere issn_normalizado y texto_modelo")
        documents = corpus["texto_modelo"].fillna("").map(
            lambda value: preprocess_text(value, self.language)
        ).tolist()
        self.identifiers = corpus["issn_normalizado"].astype(str).tolist()
        self.vectorizer = TfidfVectorizer(token_pattern=r"(?u)\b\w[\w-]+\b")
        self.tfidf_matrix = self.vectorizer.fit_transform(documents)
        self.embedding_matrix = (
            self._encode_documents(documents)
            if self.use_scibert
            else np.zeros((len(documents), 1), dtype=np.float32)
        )
        return self

    def _encode_documents(self, documents: Sequence[str]) -> np.ndarray:
        """Codifica documentos con SciBERT; devuelve ceros si no está instalado."""
        if self._encoder is None:
            try:
                from transformers import AutoModel, AutoTokenizer
                import torch
            except ImportError:
                return np.zeros((len(documents), 1), dtype=np.float32)
            self._tokenizer = AutoTokenizer.from_pretrained(self.scibert_model)
            self._encoder = AutoModel.from_pretrained(self.scibert_model)
            self._encoder.eval()
            self._torch = torch
        vectors = []
        with self._torch.no_grad():
            for document in documents:
                batch = self._tokenizer(
                    document,
                    return_tensors="pt",
                    truncation=True,
                    max_length=512,
                )
                output = self._encoder(**batch).last_hidden_state
                if self.pooling == "cls":
                    vector = output[:, 0, :]
                else:
                    mask = batch["attention_mask"].unsqueeze(-1)
                    vector = (output * mask).sum(dim=1) / mask.sum(dim=1).clamp(min=1)
                vectors.append(vector.cpu().numpy()[0])
        return np.asarray(vectors, dtype=np.float32)

    def score(self, manuscript: object) -> ThematicScores:
        """Calcula similitud TF-IDF, SciBERT y la ecuación de fusión."""
        if self.vectorizer is None or self.tfidf_matrix is None:
            raise RuntimeError("Debe ejecutar fit(corpus) antes de score")
        document = preprocess_text(manuscript, self.language)
        tfidf_score = cosine_similarity(
            self.vectorizer.transform([document]), self.tfidf_matrix
        )[0]
        query_embedding = (
            self._encode_documents([document])
            if self.use_scibert
            else np.zeros((1, 1), dtype=np.float32)
        )
        if self.embedding_matrix is None or self.embedding_matrix.shape[1] == 1:
            scibert_score = np.zeros(len(self.identifiers), dtype=float)
        else:
            scibert_score = cosine_similarity(query_embedding, self.embedding_matrix)[0]
        thematic = self.alpha * tfidf_score + (1.0 - self.alpha) * scibert_score
        return ThematicScores(tfidf_score, scibert_score, thematic)

    def recommend(self, manuscript: object, top_k: int = 10) -> pd.DataFrame:
        """Devuelve revistas ordenadas por la similitud temática fusionada."""
        if top_k < 1:
            raise ValueError("top_k debe ser positivo")
        scores = self.score(manuscript)
        order = np.argsort(-scores.thematic)[:top_k]
        return pd.DataFrame({
            "issn_normalizado": [self.identifiers[index] for index in order],
            "score_tfidf": scores.tfidf[order],
            "score_scibert": scores.scibert[order],
            "score_tematico": scores.thematic[order],
        })

    def compare_journal(
        self,
        issn: str,
        metadata: pd.DataFrame | None = None,
        top_k: int = 10,
        exclude_self: bool = True,
    ) -> pd.DataFrame:
        """Compara una revista Gold contra las demás usando artefactos entrenados."""
        if self.tfidf_matrix is None or self.embedding_matrix is None:
            raise RuntimeError("Debe ejecutar fit(corpus) antes de compare_journal")
        if issn not in self.identifiers:
            raise KeyError(f"ISSN no encontrado en el corpus: {issn}")
        if top_k < 1:
            raise ValueError("top_k debe ser positivo")

        index = self.identifiers.index(issn)
        tfidf_scores = cosine_similarity(self.tfidf_matrix[index], self.tfidf_matrix)[0]
        if self.embedding_matrix.shape[1] == 1:
            scibert_scores = np.zeros(len(self.identifiers), dtype=float)
        else:
            scibert_scores = cosine_similarity(
                self.embedding_matrix[index:index + 1], self.embedding_matrix
            )[0]
        thematic_scores = self.alpha * tfidf_scores + (1.0 - self.alpha) * scibert_scores
        order = np.argsort(-thematic_scores)
        if exclude_self:
            order = order[order != index]
        order = order[:top_k]

        result = pd.DataFrame({
            "issn_normalizado": [self.identifiers[position] for position in order],
            "score_tfidf": tfidf_scores[order],
            "score_scibert": scibert_scores[order],
            "score_tematico": thematic_scores[order],
        })
        if metadata is not None and "issn_normalizado" in metadata.columns:
            extra = metadata.drop_duplicates("issn_normalizado").set_index("issn_normalizado")
            columns = [
                column for column in (
                    "titulo", "apc_monto_usd", "apc_tipo", "cuartil_sjr_ord",
                    "h_index", "indice_calidad_costo",
                ) if column in extra.columns
            ]
            if columns:
                result = result.join(extra[columns], on="issn_normalizado")
        return result

    def save(self, output_dir: str | Path) -> None:
        """Guarda vectorizador, matriz TF-IDF, embeddings e identificadores."""
        if self.vectorizer is None or self.tfidf_matrix is None:
            raise RuntimeError("Debe ejecutar fit(corpus) antes de save")
        import joblib

        output = Path(output_dir)
        output.mkdir(parents=True, exist_ok=True)
        joblib.dump(self.vectorizer, output / "tfidf_vectorizer.joblib")
        joblib.dump(self.tfidf_matrix, output / "tfidf_matrix.joblib")
        np.save(output / "scibert_embeddings.npy", self.embedding_matrix)
        pd.Series(self.identifiers, name="issn_normalizado").to_csv(
            output / "journal_ids.csv", index=False
        )
        pd.Series(
            {
                "alpha": self.alpha,
                "language": self.language,
                "pooling": self.pooling,
                "use_scibert": self.use_scibert,
                "scibert_model": self.scibert_model,
                "documents": len(self.identifiers),
                "tfidf_features": len(self.vectorizer.vocabulary_),
                "scibert_dimension": int(self.embedding_matrix.shape[1]),
            },
            name="value",
        ).to_json(output / "metadata.json", indent=2)