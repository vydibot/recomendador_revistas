# Recomendador de revistas

Pipeline ETL medallion para consolidar Publindex, DOAJ, Scimago, OpenAPC y el registro Facts de pagos APC.

La estructura profesional se encuentra en `src/recomendador_revistas/`.
La arquitectura separa ETL, modelos TF-IDF, SciBERT, análisis APC/índices y
evaluación. Consulta `docs/architecture.md` para el mapa del repositorio.

## Instalacion

```bash
python -m venv .venv
.venv/bin/python -m pip install -e ".[dev]"
```

Para instalar también las dependencias opcionales de modelos NLP:

```bash
.venv/bin/python -m pip install -e ".[dev,nlp]"
```

El pipeline requiere `pyarrow` para escribir y leer Parquet.

## Ejecucion

Desde la raiz del proyecto:

```bash
.venv/bin/python src/recomendador_revistas/scripts/run_pipeline.py
.venv/bin/python src/recomendador_revistas/scripts/run_pipeline.py validate
.venv/bin/python -m pytest -q
.venv/bin/python src/recomendador_revistas/scripts/report_apc.py
```

Las fuentes Bronze, Silver y Gold se conservan dentro de
`src/recomendador_revistas/data/`. Los logs y reportes se generan dentro de
`src/recomendador_revistas/logs/` y `src/recomendador_revistas/reports/`.
OpenAPC y Facts son opcionales:
si el archivo no existe o contiene una respuesta HTML/HTTP, se registra como
las fuentes no disponibles y no bloquean el catálogo con las otras fuentes. Cuando
ambos son válidos, OpenAPC tiene precedencia sobre Facts y ambos tienen
precedencia sobre APC declarados de DOAJ.
La tabla de tasas y cobertura de monedas se genera en
`src/recomendador_revistas/reports/tabla_conversion_monedas.csv`.

## Capas

- Bronze: archivos descargados sin transformación y validación SHA-256 en
  `src/recomendador_revistas/logs/bronze_validation.json`.
- Silver: datos tipados y normalizados por fuente.
- Gold: catálogo maestro, features y `merge_log.csv`.

Las reglas y el esquema están en `docs/normalization_rules.md` y
`docs/diccionario_datos.md`.

## Artículos (bronze/papers)

`src/recomendador_revistas/data/bronze/papers/<issn>/` contiene los PDF de
cada revista (algunos son un solo artículo, otros el número completo). La
etapa `papers` (no incluida en la ejecución por defecto por su duración)
extrae texto y metadatos:

```bash
.venv/bin/python src/recomendador_revistas/scripts/run_pipeline.py papers
```

- Silver: `data/silver/articulos_papers.parquet` — un registro por
  artículo/idioma (`issn_normalizado`, `titulo`, `resumen`, `palabras_clave`).
  Los artículos bilingües generan dos registros con el mismo `issn` y
  `articulo_id`, uno por idioma.
- Gold: `data/gold/articulos_tokens.parquet` — un registro por artículo con
  `titulo_normalizado`, `resumen_normalizado`, `palabras_clave_normalizadas`
  y `tokens_normalizados` (sin LaTeX, ecuaciones, `--`, tildes, stopwords y
  con lematización ligera). `data/gold/revistas_tokens.parquet` — una bolsa
  de tokens agregada por ISSN con todos sus artículos.
- `data/gold/articulos_tokens.csv` — dataset de artículos con las columnas
  originales `articulo_id`, `titulo`, `resumen`, `palabras_clave` e
  `issn_normalizado`, además de sus campos normalizados. El ISSN es la revista
  donde se publicó el paper y se usa como positivo automático: las métricas
  miden recuperación de la revista de publicación, no relevancia experta
  exhaustiva. Puede pasarse directamente a `evaluate_models.py`.

La segmentación de artículos dentro de un PDF de número completo y la
extracción de título son heurísticas basadas en marcadores
Resumen/Abstract + Palabras clave/Keywords. El extractor primero intenta
preservar el layout del PDF, corrige palabras partidas entre líneas y usa OCR
opcional para PDFs escaneados. Para activar OCR instala
`.venv/bin/python -m pip install -e ".[pdf]"` y asegúrate de tener el binario
Tesseract disponible en el sistema.

Flujo recomendado completo:

```bash
# 1. Validar fuentes Bronze y ejecutar ETL editorial
.venv/bin/python src/recomendador_revistas/scripts/run_pipeline.py validate
.venv/bin/python src/recomendador_revistas/scripts/run_pipeline.py

# 2. Leer PDFs Bronze y reconstruir Silver/Gold de artículos
.venv/bin/python src/recomendador_revistas/scripts/run_pipeline.py papers

# 3. Evaluar sin fuga: alpha se selecciona en validación separada;
#    la rejilla incluye 1.0 como baseline puro TF-IDF
.venv/bin/python src/recomendador_revistas/scripts/evaluate_models.py \
  --evaluation-csv src/recomendador_revistas/data/gold/articulos_tokens.csv \
  --test-size 0.2 --seed 42 \
  --alpha-grid 0.0,0.1,0.2,0.3,0.4,0.5,0.6,0.7,0.8,0.9,1.0 \
  --output-json src/recomendador_revistas/reports/model_eval_topn.json

# 4. Entrenar el artefacto final con alpha validado
.venv/bin/python src/recomendador_revistas/scripts/train_thematic_profile.py

# 5. Recomendar revistas usando título, resumen, keywords y prioridades
.venv/bin/python src/recomendador_revistas/scripts/evaluate_manuscript.py \
  --title "Título del manuscrito" \
  --abstract "Resumen del manuscrito" \
  --keywords "palabra clave 1, palabra clave 2" \
  --language es \
  --priority-order impacto,eficiencia,flujo \
  --top-k 10 \
  --output src/recomendador_revistas/reports/sugerencia_manuscrito.csv

# 6. Compilar el paper corregido
latexmk -pdf -interaction=nonstopmode -halt-on-error \
  -outdir=informe/build informe/paper.tex
```

La evaluación informa `train_queries=1510`, `alpha_fit_queries=1208`,
`alpha_validation_queries=302`, `test_queries=377` y el número real de perfiles
candidatos. La prueba no se usa para seleccionar `alpha`; los perfiles de
validación se ajustan solo con los artículos del subconjunto de ajuste.

El reporte APC escribe `src/recomendador_revistas/reports/apc_quality_summary.json` con los porcentajes
de imputación, `reports/apc_missing_by_row.csv` con los faltantes de cada fila y
`reports/missing_by_variable.csv` con el porcentaje de faltantes de cada
variable del catálogo Gold.
