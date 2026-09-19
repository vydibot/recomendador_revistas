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
  `tokens_normalizados` (título + resumen + palabras clave tokenizados,
  sin stopwords, lematizados). `data/gold/revistas_tokens.parquet` — una
  bolsa de tokens agregada por ISSN con todos sus artículos.

La segmentación de artículos dentro de un PDF de número completo y la
extracción de título son heurísticas basadas en texto plano (marcadores
Resumen/Abstract + Palabras clave/Keywords); PDFs escaneados sin texto
extraíble no producen artículos.

El reporte APC escribe `src/recomendador_revistas/reports/apc_quality_summary.json` con los porcentajes
de imputación, `reports/apc_missing_by_row.csv` con los faltantes de cada fila y
`reports/missing_by_variable.csv` con el porcentaje de faltantes de cada
variable del catálogo Gold.
