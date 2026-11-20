# Datos del catálogo

## De dónde sale

| Origen | Fuente | Revistas | Notas |
|---|---|---|---|
| `etl` | `ml/.../data/gold/catalogo_maestro_revistas.parquet` | 663 | Publindex + DOAJ + Scimago + OpenAPC/Facts |
| `lider` | `backend/seed/lider_journals.json` (prototipo LIDER APP) | 116 | Directorio internacional (MDPI, Elsevier, IEEE, Springer…) |
| `manual` | Altas desde la web o importación CSV | — | Se conservan siempre; se pueden eliminar |

**Total al desplegar: 779 revistas.**

### Por qué no son ~3000

El ETL actual deja **906 filas** en el Gold, no ~3000. Esas 906 filas son **650 revistas distintas (+13 sin identificador)**: el Gold trae una fila por *(revista, año de clasificación/ISSN)* y 243 revistas aparecen dos veces. La web las consolida por `id_revista_publindex` (se queda con la clasificación más reciente, guarda los ISSN restantes como alias y el historial de categorías en `details.clasificaciones_previas`); de ahí 663 revistas del ETL.

DOAJ, Scimago y OpenAPC solo **enriquecen** las revistas de Publindex; no se incorporan las que no están en Publindex (DOAJ completo tiene ~23 000). Ampliar el catálogo a ~3000 exige cambiar el ETL para tomar la unión de fuentes con un filtro (país, idioma o área) y volver a generar el Gold; el *seed* absorbe el resultado sin más cambios.

## Cómo se normaliza (`backend/app/services/mappers.py`, `normalizers.py`)

| Campo | ETL (Gold) | LIDER (texto libre) |
|---|---|---|
| Costo APC (USD) | `apc_monto_usd_real`; si no hay y DOAJ dice `tiene_apc=False` → 0; si no, desconocido | `"~USD 2310 \| CHF 1800"` → 2310 (primera moneda); rangos → punto medio; `"~USD"` vacío → desconocido |
| Tiempo (semanas) | `semanas_pub` | `"3–6 meses"` → 19,6 sem (punto medio, 4,345 sem/mes) |
| Cuartil | `cuartil_sjr` | `"Q2/Q1"` → Q1 (el mejor mencionado) |
| Acceso | híbrido → *Híbrido*; open access / DOAJ / diamante → *Open Access*; `open_access=False` → *Suscripción* | `Híbrido` / `Open Access` |
| País | `pais` de Publindex (excluye "No disponible") | `Ubicación` normalizada (`USA` → Estados Unidos, `China/Elsevier` → China) |
| Idioma | `idiomas` de DOAJ traducido al español | `Idioma` |
| Formato para publicar | — (el Gold no lo tiene) | editorial reducida a su nombre (`"Elsevier (Editorial Manager, APA)"` → Elsevier) |
| Temas | `gran_area` + `area_conocimiento` | inferidos del nombre con reglas de palabras clave + «Ingeniería y Tecnología»; editables en la interfaz |

El texto original (`apc_text`, `time_text`, indexación) se conserva para mostrarlo tal cual.

## Limitaciones conocidas del dato (heredadas, no introducidas por la web)

Detectadas al integrar; conviene corregirlas en el ETL:

1. **Cruces difusos con DOAJ/Scimago (WRatio ≥ 85)**: 186 filas del Gold comparten registro Scimago con otra y 378 comparten registro DOAJ; hay 0 cruces por ISSN con OpenAPC/Facts. Efecto visible: algunos campos (editorial de DOAJ, ISSN electrónico, idioma, acceso) pueden pertenecer a *otra* revista. Por eso la web muestra como editorial la institución de Publindex y como país el de Publindex.
2. **APC observado vs. DOAJ**: 324 de las 380 revistas con APC observado figuran con `tiene_apc=False` en DOAJ (consecuencia directa del punto anterior). Se prioriza el monto observado.
3. **Vacíos**: 437 de las 663 revistas del ETL no tienen cuartil SJR (no están en Scimago) y 38 no tienen dato de costo (`apc_status = desconocido`); 333 figuran «sin costo».
4. **LIDER**: 1 fila basura (`"Nombre": "500"`) descartada; nombres repetidos fusionados; 6 pares con ISSN repetido y el ISSN 2327-4697 asignado a dos revistas IEEE distintas (se conservan ambas; la web avisa al editar); **44 «enlaces» eran títulos de página, no URLs** (p. ej. «IEEE Xplore: …»): no se muestran como enlace y el texto queda en `details.enlace_original`.
5. **Modelo**: los perfiles de 247 ISSN son 218 revistas distintas. Los perfiles `2145-8553` y `0120-0283` obtienen scores idénticos (posible corpus duplicado).

## Cómo se actualiza

- **Datos nuevos del ETL** → ver `docs/despliegue.md` («Actualizar el catálogo con un ETL nuevo»).
- **Cambios manuales en la web**: marcan la revista como `locally_modified`; el *seed* no la sobrescribe. Para que una corrección vuelva a depender del ETL, hay que restaurarla desde la BD (`UPDATE journals SET locally_modified = false WHERE id = …`) y relanzar el seed.
- **Las ediciones web no alimentan al recomendador**: el modelo usa las métricas del Gold (ver `docs/arquitectura.md`).
