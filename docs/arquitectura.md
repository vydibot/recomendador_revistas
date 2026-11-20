# Arquitectura

```
Internet ──443──▶ Caddy ──/api/*──▶ backend (FastAPI, 1 worker) ──▶ PostgreSQL (volumen persistente)
                    │                    │
                    └──── /* ──▶ frontend (nginx, estáticos)      └─▶ JournalRecommender (en memoria)
                                                                        ├─ perfil TF-IDF + SciBERT (artefactos joblib/npy)
                                                                        └─ Gold maestro → TOPSIS (6 órdenes precalculados)
```

| Componente | Tecnología | Responsabilidad |
|---|---|---|
| Proxy | Caddy 2 | HTTPS automático, cabeceras de seguridad, enruta `/api` y el resto |
| Frontend | React 19, Vite, Tailwind 4, React Router, TanStack Query | Dos páginas (catálogo y recomendador); el estado de filtros vive en la URL |
| Backend | FastAPI, SQLAlchemy 2, Alembic, Pydantic 2 | API REST, autenticación de editor, semilla de datos, servicio del modelo |
| BD | PostgreSQL 17 (SQLite en desarrollo) | Catálogo editable y persistente |
| ML | `ml/` (paquete `recomendador_revistas`) | ETL medallion, entrenamiento y evaluación; el backend solo **carga** el modelo |

## Flujo de datos

1. El ETL (`ml/`) produce el Gold `catalogo_maestro_revistas.parquet` y el entrenamiento los artefactos de `models/artifacts/thematic_profile/`. Ambos están versionados en git y se copian a la imagen del backend.
2. Al arrancar, el contenedor ejecuta `alembic upgrade head` y `python -m app.cli seed`. El *seed* es idempotente: crea revistas nuevas, actualiza las existentes y **no toca las que un editor modificó a mano** (`locally_modified`). Las filas que ya no existen en la fuente y nunca se editaron se retiran.
3. El catálogo editable vive en la BD; el recomendador mantiene su propia copia de las métricas (Gold) para el TOPSIS. **Editar un campo en la web no cambia el ranking del recomendador** (sí cambia lo que se muestra de cada resultado). Para que una corrección afecte al modelo hay que reflejarla en el ETL y reentrenar.

## Modelo de datos

`journals` (una fila por revista) · `topics` + `journal_topics` (temas, N:M) · `journal_issns` (todos los ISSN de una revista: permite resolver cualquiera de ellos, p. ej. los que usa el modelo).

Los campos de texto libre del prototipo se conservan (`apc_text`, `time_text`) junto a su valor numérico filtrable (`apc_usd`, `weeks_to_publication`). Si se edita solo el texto, el servidor lo vuelve a interpretar (`"~USD 2300 | CHF 1800"` → 2300; `"3–6 meses"` → 19,6 semanas).

## API (`/api/docs` documenta todo en Swagger)

| Método | Ruta | Acceso |
|---|---|---|
| GET | `/api/health` | público |
| GET | `/api/journals` — filtros: `q`, `topic`, `quartile`, `publindex`, `access`, `country`, `language`, `format`, `origin`, `apc_status`, `apc_min/max`, `weeks_max`, `h_index_min`, `sjr_min`, `citescore_min`, `impact_factor_min`, `quality_min`; `sort`, `order`, `page`, `page_size` | público |
| GET | `/api/journals/facets` — valores y conteos para armar los filtros | público |
| GET | `/api/journals/{id}` | público |
| POST/PATCH/DELETE | `/api/journals[/{id}]` — avisa con 409 si el ISSN ya existe (`?force=true` para continuar); DELETE solo para revistas manuales | editor |
| POST | `/api/journals/import?mode=skip\|update\|add&dry_run=true\|false` (CSV, formato LIDER) | editor |
| POST | `/api/auth/login` · GET `/api/auth/me` | — / editor |
| GET | `/api/recommend/model` — cobertura y parámetros del modelo | público |
| POST | `/api/recommend` — `{title, abstract, keywords, language, priority_order, top_k}` | público |

## Recomendador

- Texto del manuscrito → mismo preprocesamiento que en el entrenamiento → similitud coseno contra los perfiles: `α·TF-IDF + (1-α)·SciBERT` (α = 0,8 según validación).
- Puntaje final = 50 % afinidad (min-max) + 50 % índice TOPSIS de calidad-costo; el orden de las tres dimensiones (impacto, eficiencia, flujo) lo elige el usuario y fija los pesos Rank-Sum.
- `JournalRecommender` precalcula el TOPSIS de los 6 órdenes posibles al cargar; una consulta cuesta una codificación SciBERT (~0,2 s en CPU).
- Cobertura: solo las revistas con perfil entrenado (con artículos en `bronze/papers`). `/api/recommend/model` informa cuántas son y la página lo muestra.
- El modelo carga en un hilo al arrancar; mientras tanto `/api/health` informa `recommender: loading` y `/api/recommend` responde 503 (la UI reintenta sola).

## Seguridad

- Lectura y recomendador públicos; **toda escritura** exige un token JWT (HS256, 8 h) obtenido con `ADMIN_PASSWORD`. Sin esa variable, la escritura está deshabilitada.
- Login con límite de 5 intentos fallidos por minuto y por IP.
- En producción la app se niega a arrancar con `SECRET_KEY` débil (< 32 caracteres) o por defecto.
- Entradas validadas con Pydantic (`extra=forbid`, longitudes máximas); la búsqueda y los filtros usan consultas parametrizadas; CSV limitado a 5 MB / 5000 filas.
- Backend y BD no publican puertos; solo Caddy (80/443). Contenedor del backend como usuario no root; frontend con sistema de archivos de solo lectura.
- Los artefactos del modelo se deserializan con `joblib` (pickle): únicamente cargan los generados por este repositorio.

## Decisiones que conviene conocer

- **1 worker de uvicorn**: el modelo ocupa ~1,5 GB en memoria; varios workers lo duplicarían. La concurrencia de lecturas la aguanta de sobra; las consultas al recomendador se serializan con un candado (cada una dura décimas de segundo).
- **Eliminar** solo está permitido para revistas agregadas manualmente: las del ETL/LIDER reaparecerían en el siguiente *seed*. Se editan.
- Las tipografías se empaquetan en el frontend (sin Google Fonts) para no depender de terceros en tiempo de ejecución.
