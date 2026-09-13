# Módulo de Recomendación

Este módulo corresponde a la fase futura del sistema encargada del motor de recomendación híbrido de revistas científicas.

## Responsabilidades Diseñadas
1. **Filtrado Basado en Contenido**:
   - Similitud coseno entre embeddings de manuscritos y descriptores temáticos de revistas.
2. **Optimización Multi-Objetivo / Multi-Criterio**:
   - Ponderación de impacto bibliométrico (SJR, cuartil Q1-Q4, Publindex A1-C).
   - Restricciones económicas y de asequibilidad (APC en USD y PPP USD, acceso diamante).
   - Requisitos de tiempo editorial (semanas entre sumisión y publicación).
   - Preferencias de licencias abiertas (CC BY, CC BY-NC) y revisión por pares abierta.
3. **Explicabilidad**:
   - Generación de justificaciones transparentes de recomendación para los autores.

