# Módulo de Recomendación

Este módulo corresponde a la fase futura del sistema encargada del motor de recomendación híbrido de revistas científicas.

## Módulo A: Perfil Temático

La implementación está en `thematic_profile.py` y cubre la sección 8.2.1:

- Limpieza de ecuaciones, delimitadores y comandos LaTeX.
- Tokenización, eliminación de stopwords y lematización reproducible.
- Vectores TF-IDF para manuscritos y textos Gold de revistas.
- Embeddings SciBERT opcionales con pooling `mean` o `cls`.
- Similitud coseno y fusión:
   `score = alpha * score_tfidf + (1 - alpha) * score_scibert`.
- Selección de `alpha` mediante `select_alpha` sobre un conjunto de validación.

Ejemplo:

```python
import pandas as pd

from recomendador_revistas.models.thematic_profile import (
      ThematicProfile,
      build_journal_corpus,
)

gold = pd.read_parquet("src/recomendador_revistas/data/gold/catalogo_texto_tfidf_scibert.parquet")
corpus = build_journal_corpus(gold)
profile = ThematicProfile(alpha=0.5, pooling="mean").fit(corpus)
recommendations = profile.recommend("manuscript title, abstract and keywords", top_k=10)
```

Para activar SciBERT:

```bash
.venv/bin/python -m pip install -e ".[dev,nlp]"
```

Sin ese extra, el módulo sigue funcionando con TF-IDF y devuelve `score_scibert`
igual a cero de forma explícita.

Evaluación Top-N:

```bash
.venv/bin/python src/recomendador_revistas/scripts/evaluate_models.py \
  --evaluation-csv src/recomendador_revistas/data/evaluation/manuscripts_relevance_template.csv \
  --test-size 0.2 \
  --ks 5,10,20
```

El script calcula Precision@K, Recall@K, F1@K, Accuracy@K, NDCG@K, MAP y MRR,
y ajusta `alpha` por validación en entrenamiento.

## Responsabilidades diseñadas
1. **Filtrado Basado en Contenido**:
   - Similitud coseno entre embeddings de manuscritos y descriptores temáticos de revistas.
2. **Optimización Multi-Objetivo / Multi-Criterio**:
   - Ponderación de impacto bibliométrico (SJR, cuartil Q1-Q4, Publindex A1-C).
   - Restricciones económicas y de asequibilidad (APC en USD y PPP USD, acceso diamante).
   - Requisitos de tiempo editorial (semanas entre sumisión y publicación).
   - Preferencias de licencias abiertas (CC BY, CC BY-NC) y revisión por pares abierta.
3. **Explicabilidad**:
   - Generación de justificaciones transparentes de recomendación para los autores.

