# Módulo de Análisis de Texto (NLP)

Este módulo corresponde a la fase futura del sistema de recomendación de revistas científicas, encargada del análisis semántico y temático de artículos o manuscritos propuestos.

## Responsabilidades Diseñadas
1. **Preprocesamiento de Texto**:
   - Limpieza de títulos y resúmenes (abstracts).
   - Lematización, eliminación de stopwords multi-idioma (español, inglés, portugués).
2. **Representación Vectorial y Embeddings**:
   - Modelos densos basados en Transformers científicos (e.g., SciBERT, BioBERT, MiniLM).
   - Generación de vectores de afinidad temática a partir del corpus de revistas indexadas.
3. **Extracción de Entidades y Descriptores**:
   - Mapeo contra tesauros controlados (MeSH, DeCS, UNESCO) y códigos LCC de DOAJ.

