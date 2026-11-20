#!/bin/sh
# Migra el esquema y carga/actualiza el catálogo antes de levantar la API.
set -eu

alembic upgrade head
if [ "${SEED_ON_START:-true}" = "true" ]; then
    python -m app.cli seed
fi
exec "$@"
