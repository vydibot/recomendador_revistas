# Diccionario de datos

| Campo | Tipo | Descripcion | Fuentes |
|---|---|---|---|
| `issn_normalizado` | string | ISSN canónico usado como clave de enlace | Todas |
| `titulo` | string | Título de la revista | Publindex, DOAJ, Scimago |
| `pais_iso` | string | País ISO 3166-1 alpha-2 | Todas |
| `categoria_publindex` | string | Categoría A1, A2, B o C | Publindex |
| `cuartil_sjr` | string | Mejor cuartil Q1-Q4 | Scimago |
| `sjr_score` | float | Indicador SJR | Scimago |
| `h_index` | integer | Índice H | Scimago |
| `tiene_apc` | boolean | La revista declara APC | DOAJ |
| `apc_monto` | float | Monto original de APC | DOAJ, OpenAPC |
| `apc_moneda` | string | Código ISO 4217 | DOAJ, OpenAPC |
| `apc_monto_usd` | float | APC convertido a USD | Derivado |
| `apc_tipo` | enum | `observado`, `declarado` o `imputado` | Derivado |
| `_fuentes` | list[string] | Fuentes que contribuyeron al registro | Derivado |
| `_estado_calidad` | enum | Estado de la capa medallion | Derivado |
| `_hash_registro` | string | Hash de trazabilidad | Derivado |

Los campos no disponibles en una fuente se conservan como nulos; el catálogo
Gold no inventa valores bibliométricos ni editoriales.
