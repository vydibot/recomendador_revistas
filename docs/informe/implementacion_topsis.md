# Informe técnico: implementación de TOPSIS

**Proyecto:** Recomendador de revistas científicas  
**Fecha de revisión:** 28 de octubre de 2026  
**Alcance:** análisis estático del código disponible en el árbol de trabajo actual. El documento describe la implementación, no constituye una validación estadística ni una auditoría de las fuentes originales.

## 1. Resumen ejecutivo

El proyecto utiliza TOPSIS (*Technique for Order Preference by Similarity to Ideal Solution*) para calcular un índice de calidad, costo y eficiencia editorial por revista. El índice es una función multicriterio sobre el catálogo Gold: orienta cada criterio como beneficio o costo, escala sus valores, aplica ponderaciones obtenidas del orden de prioridad de tres dimensiones y mide la distancia euclidiana de cada revista a las soluciones ideal positiva y negativa.

El resultado se guarda como `indice_topsis_calidad_costo`; `indice_calidad_costo` se conserva como alias del mismo valor. Durante la recomendación, el componente TOPSIS se combina en partes iguales con la similitud temática normalizada:

\[
S_{\mathrm{final}}(q,r)=0.5\,\widetilde{S}_{\mathrm{temático}}(q,r)
 +0.5\,CC(r).
\]

La implementación tiene una separación funcional razonable entre cálculo del índice, enriquecimiento ETL y recomendación. Entre sus decisiones explícitas están la prioridad configurable de dimensiones y la exclusión del APC imputado del cálculo. Sin embargo, la lectura del código revela cuatro aspectos importantes para interpretar los resultados:

1. Los pesos Rank-Sum se calculan por dimensión, pero el peso completo de la dimensión se aplica a **cada criterio** que la integra. No se reparte entre los criterios de esa dimensión; por tanto, el efecto agregado no equivale a ponderar tres dimensiones con igual número de variables.
2. Si el catálogo incluye la columna `apc_monto_ppp_usd_real`, una revista sin un valor real de APC queda sin índice TOPSIS (`NaN`), no recibe una puntuación calculada con los demás criterios.
3. Las escalas Min-Max y los ideales se calculan sobre el conjunto recibido en cada llamada. Los resultados dependen del catálogo y de las alternativas incluidas, y no son una escala absoluta e invariable entre versiones.
4. La prueba que debería verificar el tratamiento del APC imputado está anidada dentro de otra función de prueba. `pytest` no la descubre, por lo que esa regla no está cubierta por dicha prueba aunque el cuerpo de la aserción exista.

## 2. Componentes y flujo de datos

### 2.1 Cálculo del índice

La lógica principal está en [`src/recomendador_revistas/analysis/indices.py`](../src/recomendador_revistas/analysis/indices.py). Expone:

- `DIMENSIONS` y `DEFAULT_ORDER`, que definen las tres dimensiones y el orden predeterminado.
- `rank_sum_weights(order)`, que valida que el orden sea una permutación exacta de las dimensiones y devuelve los pesos.
- `topsis_quality_cost_index(dataset, order)`, que copia el DataFrame, prepara criterios y añade las dos columnas de resultado.
- `build_indices(dataset, order)`, que valida que la entrada sea un `pandas.DataFrame` y delega el cálculo.

La copia de entrada evita modificar el objeto recibido por el llamador. Las columnas de criterio son opcionales: se incluyen únicamente si existen en el DataFrame. Esto permite ejecutar el cálculo sobre metadatos parciales, pero también significa que dos catálogos con esquemas distintos pueden obtener índices basados en conjuntos de criterios diferentes.

### 2.2 ETL Gold

En [`src/recomendador_revistas/etl/gold.py`](../src/recomendador_revistas/etl/gold.py), `calcular_features_avanzadas` produce variables requeridas para el índice y finalmente ejecuta `build_indices(df)`.

El ETL:

1. Detecta valores atípicos de APC como parte del procesamiento de datos.
2. Construye `apc_monto_usd_real` a partir de montos cuyo tipo es `observado` o `declarado`; los valores imputados no se conservan en esa variable.
3. Calcula `apc_monto_ppp_usd_real` a partir del APC real y el país.
4. Deriva la rapidez editorial (`editorial_rapida`) y `ratio_citas_docs`.
5. Escala ciertas columnas continuas para producir, entre otras, `sjr_score_minmax`, `h_index_minmax` y `semanas_pub_minmax`.
6. Calcula TOPSIS y devuelve el catálogo enriquecido.

En la misma función existe un cálculo previo de una fórmula distinta para `indice_calidad_costo`, basada en SJR y APC. Sin embargo, `build_indices` asigna después `indice_calidad_costo` al resultado TOPSIS. En el catálogo final, por tanto, el valor de esa columna corresponde al alias del TOPSIS; no conserva el resultado intermedio de la fórmula previa.

### 2.3 Integración con recomendaciones

`ThematicProfile.recommend` y `ThematicProfile.compare_journal`, en [`src/recomendador_revistas/models/thematic_profile.py`](../src/recomendador_revistas/models/thematic_profile.py), calculan el índice desde los metadatos recibidos y relacionan las puntuaciones con los identificadores ISSN del perfil temático. Si no se entrega metadata, la recomendación se ordena solo por score temático.

Cuando sí se entrega:

1. Se calcula TOPSIS sobre el DataFrame completo recibido como `metadata`.
2. Se eliminan ISSN duplicados para crear la correspondencia con los scores.
3. Se normaliza el score temático con Min-Max sobre los perfiles del modelo; si su rango es cero, todos reciben 0.5.
4. Se promedian con coeficientes fijos de 0.5 el score temático normalizado y el TOPSIS.
5. Se ordena descendentemente el score final.

La interfaz de línea de comandos [`src/recomendador_revistas/scripts/evaluate_manuscript.py`](../src/recomendador_revistas/scripts/evaluate_manuscript.py) recibe `--priority-order` (por defecto `impacto,eficiencia,flujo`) y lo pasa al modelo. El índice puede, por tanto, variar por preferencias, pero el peso de la rama TOPSIS frente a la temática permanece fijo en 50/50.

## 3. Criterios implementados

Los criterios se definen en `_CRITERIA`. La tabla indica la dirección con la que se orienta cada variable antes de construir las soluciones ideales:

| Dimensión | Criterio | Dirección | Interpretación operativa |
|---|---|---:|---|
| Impacto | `sjr_score_minmax` | Beneficio | Mayor SJR es preferido. |
| Impacto | `h_index_minmax` | Beneficio | Mayor H-index es preferido. |
| Impacto | `cuartil_sjr_ord` | Beneficio | Mayor valor ordinal del cuartil es preferido. |
| Flujo | `total_citas_3y` | Beneficio | Más citas en tres años es preferido. |
| Flujo | `citas_por_doc_2y` | Beneficio | Mayor tasa de citas por documento es preferida. |
| Flujo | `ratio_citas_docs` | Beneficio | Mayor razón de citas/documentos es preferida. |
| Flujo | `total_docs_3y` | Costo | Menor volumen de documentos es preferido por esta codificación. |
| Eficiencia | `editorial_rapida` | Beneficio | El indicador verdadero se trata como mejor que falso. |
| Eficiencia | `semanas_pub_minmax` | Costo | Menos semanas de publicación es preferido. |
| Eficiencia | `semanas_submission_publicacion` | Costo | Menos semanas es preferido. |
| Eficiencia | `apc_monto_ppp_usd_real` | Costo | Menor costo ajustado por paridad de poder adquisitivo es preferido. |

El código contempla como máximo once criterios, aunque el total efectivo es el número de columnas de esa lista que existen en los metadatos. `apc_monto_ppp_usd_real` es la medida de costo utilizada; no se usa el valor PPP que pueda incluir imputaciones.

## 4. Algoritmo y fórmulas

### 4.1 Pesos Rank-Sum

Para un orden de prioridad con \(m=3\) dimensiones, a la dimensión en posición \(r_j\) se le asigna:

\[
w_j = \frac{m-r_j+1}{\sum_{k=1}^{m}(m-r_k+1)}.
\]

En el orden predeterminado impacto–eficiencia–flujo, el resultado es:

\[
w_{\text{impacto}}=\frac{3}{6}=0.5,\quad
w_{\text{eficiencia}}=\frac{2}{6}\approx0.3333,\quad
w_{\text{flujo}}=\frac{1}{6}\approx0.1667.
\]

La validación de `rank_sum_weights` rechaza órdenes con longitud distinta de tres, dimensiones ausentes, repetidas o desconocidas mediante `ValueError`.

### 4.2 Normalización y dirección

Para cada criterio incluido, `_minmax` convierte valores a tipo numérico; los valores no convertibles pasan a faltantes. Con datos disponibles, escala usando el mínimo y el máximo de la serie:

\[
x'_{ij}=\frac{x_{ij}-\min_i(x_{ij})}{\max_i(x_{ij})-\min_i(x_{ij})}.
\]

Los criterios de beneficio mantienen esa dirección. Los criterios de costo/fricción se invierten con \(1-x'_{ij}\), de modo que un valor alto siempre representa una alternativa favorable. Las columnas que ya llevan sufijo `_minmax` vuelven a entrar en `_minmax`; la función no da por hecho que la columna esté previamente escalada.

El tratamiento de faltantes general es la mediana de la columna antes del escalamiento. Si no hay ningún dato numérico, `_minmax` devuelve ceros para criterios ordinarios. Si el rango es cero, también devuelve ceros; en columnas de APC mantiene los faltantes como faltantes.

### 4.3 Matriz ponderada e ideales

Cada columna normalizada se multiplica por el peso de su dimensión:

\[
v_{ij}=x'_{ij}\,w_{d(j)},
\]

donde \(d(j)\) identifica la dimensión del criterio \(j\). En cada columna, la solución ideal positiva toma el máximo y la negativa el mínimo:

\[
A^+_j=\max_i(v_{ij}),\qquad A^-_j=\min_i(v_{ij}).
\]

Al haber orientado todos los criterios para que más sea mejor, esta operación implementa los ideales en la dirección esperada. Las distancias por alternativa son las euclidianas:

\[
D_i^+=\sqrt{\sum_j(v_{ij}-A_j^+)^2},\qquad
D_i^-=\sqrt{\sum_j(v_{ij}-A_j^-)^2}.
\]

### 4.4 Coeficiente de cercanía

El índice calculado es:

\[
CC_i=\frac{D_i^-}{D_i^+ + D_i^-}.
\]

El resultado se limita a \([0,1]\) con `numpy.clip`. Cuando la suma de distancias es cero, el código asigna 0.5. Si no existe ningún criterio reconocible, no ejecuta el cálculo geométrico y asigna 0.0 a ambos nombres de índice.

## 5. Datos faltantes y APC real

El APC tiene una política de faltantes diferente al resto de criterios:

- Se normaliza sin imputar mediana.
- Si la columna de APC real está presente, `eligible` se marca falso para cualquier fila donde su valor normalizado sea faltante.
- Aunque posteriormente se rellena ese valor con cero para poder formar la matriz, la puntuación de las filas inelegibles se sobrescribe como `NaN`.
- Si la columna de APC real no existe en el DataFrame, no se añade como criterio y su ausencia no excluye filas.

Así, la columna presente con faltantes y la columna ausente tienen semánticas distintas. En el primer caso, los registros sin APC quedan sin TOPSIS; en el segundo, el TOPSIS se calcula con los criterios restantes. El modelo temático no filtra explícitamente las filas con `NaN` antes de calcular `score_final`: la puntuación final de esas revistas también queda faltante y el ordenamiento las desplaza al final en el orden usual de NumPy, aunque pueden seguir apareciendo si se solicita un \(k\) que alcance esas filas.

Esta decisión evita presentar un costo inventado como observado, pero hace que el índice sea, en la práctica, un score de cobertura parcial: las revistas con información de costo pueden ser comparadas mediante TOPSIS mientras otras no reciben índice. La ausencia de APC no debe interpretarse como costo cero ni como prueba de que publicar sea gratis.

## 6. Hallazgos técnicos y consecuencias

### 6.1 El peso de dimensión se replica en cada criterio

`rank_sum_weights` devuelve pesos de dimensiones; durante la construcción de `weighted`, el código multiplica cada criterio por el peso completo de su dimensión. No divide ese peso por el número de criterios disponibles de la dimensión. El diseño anunciado como tres prioridades no se traduce literalmente en tres pesos agregados: las dimensiones con más variables introducen más coordenadas en la distancia euclidiana y pueden tener más influencia conjunta.

La diferencia se acentúa si cambia la cobertura del catálogo, porque el número de columnas disponibles puede cambiar por dimensión. No es necesariamente un error matemático si se pretende que cada atributo sea un criterio separado con ese coeficiente; sí es una diferencia sustantiva respecto de la interpretación habitual de que el usuario asigna un peso total a cada dimensión. La documentación y la implementación deberían definir explícitamente cuál de estas dos interpretaciones se desea.

### 6.2 Criterios potencialmente redundantes

La definición contiene varios indicadores que pueden estar correlacionados o derivarse de los mismos datos:

- `editorial_rapida` se deriva del umbral de semanas y aparece junto con `semanas_pub_minmax` y `semanas_submission_publicacion`.
- `ratio_citas_docs` se construye a partir de citas y documentos cuando ambas columnas están disponibles; también coexiste con `citas_por_doc_2y`.
- SJR, H-index y cuartil describen facetas relacionadas de impacto.

La distancia euclidiana no modela dependencia entre criterios. Por ello, variables correlacionadas pueden representar repetidamente una característica y darle más influencia efectiva. El código no calcula correlaciones, no elimina redundancia y no aplica pesos por criterio independientes.

### 6.3 Cambios de catálogo alteran el valor del índice

Cada llamada recalcula mínimos, máximos, medianas e ideales desde el DataFrame recibido. Añadir o retirar revistas, cambiar valores extremos o modificar la disponibilidad de criterios puede cambiar:

- el valor normalizado de las revistas;
- los ideales positivo y negativo;
- el coeficiente TOPSIS de una misma revista;
- el orden final de recomendaciones.

Por tanto, el score sirve como comparación relativa al conjunto evaluado, no como una magnitud absoluta comparable sin recalibración entre snapshots.

### 6.4 Dirección de `total_docs_3y`

La codificación considera `total_docs_3y` como costo, por lo que premia un volumen documental menor, aun cuando la dimensión se denomina “flujo”. El código implementa esa preferencia de manera inequívoca; el significado de negocio y su compatibilidad con el objetivo editorial deben validarse con usuarios expertos antes de tratarlo como una preferencia normativa.

### 6.5 Faltantes de criterios no económicos

Los criterios distintos de APC se imputan con la mediana de la columna. Si una columna está enteramente vacía se convierte a cero; para un criterio de costo, la inversión posterior puede convertir ese cero normalizado en el valor favorable máximo. Una cobertura de datos muy incompleta puede así producir un valor con apariencia válida que depende de la regla de relleno y no de observaciones para esa revista.

### 6.6 Manejo de empates y resultado constante

Si todas las alternativas son idénticas en los criterios incluidos, ambas distancias son cero y el resultado es 0.5 para cada una. Si no hay criterios disponibles, el índice vale 0.0. Son casos distintos, aunque ambos generan scores sin diferenciación; quien consuma el índice debe conservar la distinción entre “cálculo degenerado” y “sin criterios”.

## 7. Pruebas y verificabilidad

La prueba pertinente se encuentra en [`tests/test_pipeline.py`](../tests/test_pipeline.py) con el nombre `test_topsis_ignores_imputed_apc_values`. Su fixture verifica que un APC imputado no determine el índice y que la fila sin APC real reciba `NaN`. No obstante, la definición está indentada dentro de `test_continuous_scaling_zscore_minmax`, por lo que pytest no la registra como caso independiente. La recolección de `tests/test_pipeline.py` produce 17 pruebas y no incluye `test_topsis_ignores_imputed_apc_values`.

La implementación de `indices.py` no tiene, en el conjunto revisado, pruebas descubiertas que cubran directamente:

- los pesos de las seis permutaciones posibles;
- el rechazo de órdenes inválidos;
- la orientación de costos y beneficios;
- columnas ausentes, totalmente nulas o constantes;
- la imputación por mediana de criterios no APC;
- el tratamiento de `NaN` en el score final de la recomendación;
- la diferencia entre calcular ideales sobre el catálogo completo y sobre el conjunto de candidatos.

Este informe no modifica el código ni ejecuta una suite completa; la observación de descubrimiento se basa en la recolección de pruebas de `tests/test_pipeline.py`.

## 8. Interpretación correcta de la puntuación

Un score TOPSIS alto significa que, con respecto al conjunto de datos y a los criterios efectivamente disponibles en esa ejecución, la revista está más cerca de la alternativa ideal construida por los máximos observados y más lejos de la alternativa anti-ideal. No significa, por sí solo, que:

- la revista tenga calidad editorial validada externamente;
- el APC publicado sea necesariamente el costo total para una persona autora;
- una revista sin APC registrado sea gratuita;
- la puntuación sea comparable entre catálogos o fechas distintos;
- el orden sea robusto a cambios de criterios, datos, pesos o cobertura.

El score final tampoco es una selección multicriterio TOPSIS pura: es la media aritmética de TOPSIS y del score temático reescalado sobre las revistas del perfil. Esa elección da el mismo peso final a ambas ramas, independientemente de la confianza o cobertura de cada una.

## 9. Recomendaciones de mejora

En orden de prioridad:

1. **Formalizar los pesos.** Decidir si el orden del usuario pondera dimensiones o cada variable individual. Si son pesos de dimensión, agregar cada dimensión en una escala comparable o repartir su peso entre sus criterios activos; documentar y probar el comportamiento cuando falte una columna.
2. **Reparar y ampliar pruebas.** Desanidar la prueba del APC y añadir casos unitarios pequeños con resultados esperados para Rank-Sum, sentido de criterios, valores constantes, faltantes, ausencia de la columna APC y catálogo sin criterios.
3. **Hacer explícita la elegibilidad.** Definir si APC ausente debe excluir la recomendación, producir un score TOPSIS parcial o activar una rama sin criterio económico. Informar al consumidor de la decisión y de la cobertura.
4. **Controlar redundancia.** Revisar la asociación entre los indicadores de eficiencia editorial y entre medidas de impacto/flujo; justificar su inclusión conjunta o reducir duplicaciones.
5. **Precisar la dirección del volumen documental.** Validar si minimizar `total_docs_3y` representa la preferencia deseada.
6. **Estabilizar comparaciones entre ejecuciones.** Versionar snapshot, criterios, pesos y población de referencia; guardar la configuración usada junto con los scores. Si se necesitan comparaciones temporales, fijar límites e ideales de referencia en vez de recalcularlos sin control.
7. **Evitar scores engañosos por ausencia.** Diferenciar resultado calculado, resultado no elegible y fallback sin criterios mediante estado/razón, en vez de depender solamente de valores numéricos o `NaN`.
8. **Validar con decisores.** Realizar análisis de sensibilidad por orden de prioridades y cobertura de APC, y validar preferencias y resultados con investigadores/editoriales. La implementación actual es una herramienta de apoyo configurable, no una medida de calidad validada por juicio experto.

## 10. Referencias de implementación

- Cálculo, criterios, normalización, pesos e ideales: [`src/recomendador_revistas/analysis/indices.py`](../src/recomendador_revistas/analysis/indices.py).
- Preparación Gold y llamada al índice: [`src/recomendador_revistas/etl/gold.py`](../src/recomendador_revistas/etl/gold.py).
- Mezcla con score temático y ordenación: [`src/recomendador_revistas/models/thematic_profile.py`](../src/recomendador_revistas/models/thematic_profile.py).
- Parámetro de prioridades de usuario: [`src/recomendador_revistas/scripts/evaluate_manuscript.py`](../src/recomendador_revistas/scripts/evaluate_manuscript.py).
- Prueba del tratamiento del APC: [`tests/test_pipeline.py`](../tests/test_pipeline.py).
- Descripción metodológica existente en el manuscrito: [`informe/paper.tex`](./paper.tex).
