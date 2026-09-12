# Reglas de normalizacion

## ISSN

Los prefijos `ISSN`, `EISSN` y `E-ISSN`, espacios y guiones se eliminan para
validar ocho caracteres. El valor canónico se vuelve a escribir como
`XXXX-XXXX`. El enlace prioriza ISSN-L, luego ISSN de impresión y finalmente
electrónico. El checksum se valida con módulo 11 y los registros sin ISSN
utilizable no participan en deduplicación por ISSN.

## Titulos y paises

Los títulos se convierten a minúsculas, se eliminan diacríticos, puntuación y
stopwords editoriales. Los países se convierten a ISO 3166-1 alpha-2 cuando
existe un mapeo conocido.

## APC y precedencia

DOAJ aporta APC declarado. OpenAPC aporta pagos observados y reemplaza el
monto declarado cuando existe coincidencia por ISSN. Los valores sin dato se
imputan por editorial, área + cuartil, área y finalmente mediana global; el
método queda en `apc_metodo_imputacion`. Los outliers se marcan con IQR y no se
eliminan.

## Trazabilidad

Cada capa añade `_fuente`, `_fecha_captura`, `_estado_calidad` y
`_hash_registro`. Las coincidencias de los merges quedan en
`data/silver/merge_log.csv`.
