"""Experimento opcional de aprendizaje siamés inspirado en DistilBertAims.

Este módulo no se importa durante la ETL. Requiere el extra ``nlp`` y recibe
pares manuscrito-revista con etiquetas binarias de relevancia.
"""

from __future__ import annotations

from typing import Sequence

import numpy as np


class SiameseSciBertExperiment:
    """Entrenamiento contrastivo opcional sobre un encoder SciBERT congelable."""

    def __init__(self, model_name: str = "allenai/scibert_scivocab_uncased") -> None:
        self.model_name = model_name
        self.tokenizer = None
        self.encoder = None
        self.torch = None

    def _load(self) -> None:
        try:
            import torch
            from transformers import AutoModel, AutoTokenizer
        except ImportError as error:
            raise ImportError(
                "El experimento siamés requiere: pip install -e '.[dev,nlp]'"
            ) from error
        self.torch = torch
        self.tokenizer = AutoTokenizer.from_pretrained(self.model_name)
        self.encoder = AutoModel.from_pretrained(self.model_name)

    def fit(
        self,
        manuscript_texts: Sequence[str],
        journal_texts: Sequence[str],
        labels: Sequence[float],
        epochs: int = 1,
        learning_rate: float = 2e-5,
    ) -> "SiameseSciBertExperiment":
        """Ajusta el encoder con pérdida MSE sobre similitud coseno."""
        if not (len(manuscript_texts) == len(journal_texts) == len(labels)):
            raise ValueError("Los textos y labels deben tener la misma longitud")
        self._load()
        torch = self.torch
        optimizer = torch.optim.AdamW(self.encoder.parameters(), lr=learning_rate)
        self.encoder.train()
        for _ in range(epochs):
            for manuscript, journal, label in zip(manuscript_texts, journal_texts, labels):
                left = self._encode(manuscript)
                right = self._encode(journal)
                similarity = torch.nn.functional.cosine_similarity(left, right)
                target = torch.tensor(float(label), dtype=similarity.dtype)
                loss = (similarity - target).pow(2).mean()
                optimizer.zero_grad()
                loss.backward()
                optimizer.step()
        self.encoder.eval()
        return self

    def score(self, manuscript: str, journal: str) -> float:
        """Calcula similitud coseno después del entrenamiento o carga del encoder."""
        if self.encoder is None:
            self._load()
        with self.torch.no_grad():
            return float(self.torch.nn.functional.cosine_similarity(
                self._encode(manuscript), self._encode(journal)
            ).item())

    def _encode(self, text: str):
        batch = self.tokenizer(
            text,
            return_tensors="pt",
            truncation=True,
            max_length=512,
        )
        output = self.encoder(**batch).last_hidden_state
        mask = batch["attention_mask"].unsqueeze(-1)
        return (output * mask).sum(dim=1) / mask.sum(dim=1).clamp(min=1)