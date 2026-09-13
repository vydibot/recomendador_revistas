# Recomendador de revistas

Pipeline ETL medallion para consolidar Publindex, DOAJ, Scimago, OpenAPC y el registro Facts de pagos APC.

## Instalacion

```bash
python -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
```

El pipeline requiere `pyarrow` para escribir y leer Parquet.

## Ejecucion

Desde la raiz del proyecto:

```bash
.venv/bin/python codes/pipeline.py
.venv/bin/python codes/pipeline.py validate
.venv/bin/python -m pytest -q codes/tests
.venv/bin/python codes/report_apc_gold.py
```

Las capas se escriben en `data/silver/` y `data/gold`. OpenAPC y Facts son opcionales:
si el archivo no existe o contiene una respuesta HTML/HTTP, se registra como
las fuentes no disponibles y no bloquean el catálogo con las otras fuentes. Cuando
ambos son válidos, OpenAPC tiene precedencia sobre Facts y ambos tienen
precedencia sobre APC declarados de DOAJ.
La tabla de tasas y cobertura de monedas se genera en
`reports/tabla_conversion_monedas.csv`.

## Capas

- Bronze: archivos descargados sin transformación y validación SHA-256 en
  `logs/bronze_validation.json`.
- Silver: datos tipados y normalizados por fuente.
- Gold: catálogo maestro, features y `merge_log.csv`.

Las reglas y el esquema están en `docs/normalization_rules.md` y
`docs/diccionario_datos.md`.

El reporte APC escribe `reports/apc_quality_summary.json` con los porcentajes
de imputación, `reports/apc_missing_by_row.csv` con los faltantes de cada fila y
`reports/missing_by_variable.csv` con el porcentaje de faltantes de cada
variable del catálogo Gold.
