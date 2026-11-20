# Revistas científicas · Catálogo y Recomendador

Aplicación web única con dos secciones:

| Sección | Qué hace |
|---|---|
| **Catálogo** (`/catalogo`) | Base de datos de revistas con búsqueda y filtros (tema, cuartil, categoría Publindex, acceso, país, idioma, formato, costo APC, tiempo de publicación, índice H, SJR, CiteScore, Impact Factor, índice calidad-costo). Con contraseña de editor se pueden **editar, añadir, eliminar e importar por CSV**. |
| **Recomendador** (`/recomendador`) | Recibe título, resumen y palabras clave de un manuscrito y ordena las revistas por afinidad temática (TF-IDF + SciBERT) combinada con un índice TOPSIS de calidad-costo según las prioridades del autor. |

El catálogo une el Gold del ETL (Publindex + DOAJ + Scimago + OpenAPC) con el directorio del prototipo LIDER. Detalles y decisiones de datos en [`docs/datos.md`](docs/datos.md).

## Estructura

```
├── backend/            API FastAPI + SQLAlchemy 2 + Alembic (PostgreSQL en prod, SQLite en dev)
├── frontend/           React 19 + Vite + Tailwind 4 + React Router + TanStack Query
├── ml/                 Módulo de datos y modelos (ETL, TF-IDF/SciBERT, TOPSIS, evaluación)
├── deploy/             Compose de producción, Caddy (HTTPS) y scripts del servidor
├── docs/               Arquitectura, despliegue, datos e informe técnico (paper)
├── .github/workflows/  CI (pruebas) y Deploy (imágenes → GHCR → SSH)
├── docker-compose.yml  Stack completo local (mismas imágenes que producción)
└── Makefile            Atajos de desarrollo
```

## Desarrollo local

Requisitos: Python 3.12, Node 22+ (probado con 24/26).

```bash
make setup          # .venv + dependencias de ml, backend y frontend
make dev-backend    # API en :8000 (migra y carga el catálogo; docs en /api/docs)
make dev-frontend   # UI en :5173 (proxy de /api al backend)
```

El modo editor usa `ADMIN_PASSWORD` (por defecto `admin` con `make dev-backend`).
Sin `ADMIN_PASSWORD` la edición queda deshabilitada.

```bash
make test           # pytest de ml y backend + vitest
make lint           # ruff + tsc
make up             # todo en Docker (PostgreSQL + Caddy) en http://localhost:8080
```

## Despliegue

Push a `main` → GitHub Actions ejecuta las pruebas, construye las imágenes, las publica en GHCR y despliega por SSH en tu servidor Linux, que sirve la app con HTTPS automático (Caddy + Let's Encrypt) sobre tu dominio. Guía completa y puesta en marcha del servidor: [`docs/despliegue.md`](docs/despliegue.md).

## Documentación

- [`docs/arquitectura.md`](docs/arquitectura.md) — componentes, flujo de datos, API, seguridad.
- [`docs/despliegue.md`](docs/despliegue.md) — servidor, secretos de GitHub, operación, respaldos, rollback.
- [`docs/datos.md`](docs/datos.md) — cómo se construye el catálogo, limitaciones conocidas del dato y cómo actualizarlo.
- [`ml/README.md`](ml/README.md) — ETL, entrenamiento y evaluación del modelo.
