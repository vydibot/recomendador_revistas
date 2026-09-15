"""Modelo TF-IDF para recuperación basada en contenido."""


class TfidfCosineRecommender:
    """Contrato del recomendador TF-IDF con similitud de coseno."""

    def fit(self, documents):
        raise NotImplementedError

    def recommend(self, query, top_k: int = 10):
        raise NotImplementedError