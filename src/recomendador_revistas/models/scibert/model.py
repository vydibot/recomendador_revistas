"""Modelo SciBERT para representación semántica científica."""


class SciBertRecommender:
    """Contrato del recomendador basado en embeddings SciBERT."""

    def fit(self, documents):
        raise NotImplementedError

    def recommend(self, query, top_k: int = 10):
        raise NotImplementedError