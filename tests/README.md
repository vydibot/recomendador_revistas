# Tests

Las pruebas nuevas deben organizarse por componente:

- `tests/etl/`: contratos Bronze, Silver y Gold.
- `tests/models/test_tfidf.py`: TF-IDF y similitud de coseno.
- `tests/models/test_scibert.py`: embeddings y recuperación semántica.
- `tests/analysis/`: APC e índices.
- `tests/evaluation/`: métricas y protocolos.

Las pruebas existentes permanecen temporalmente en `codes/tests/` durante la
migración.