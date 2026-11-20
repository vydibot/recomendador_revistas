#!/usr/bin/env bash
# Volcado comprimido de PostgreSQL con rotación (14 días). Restaurar:
#   gunzip -c backups/recomendador-AAAAMMDD-HHMM.sql.gz | docker compose -f docker-compose.prod.yml exec -T db psql -U recomendador recomendador
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p backups
out="backups/recomendador-$(date +%Y%m%d-%H%M).sql.gz"
docker compose -f docker-compose.prod.yml exec -T db pg_dump -U recomendador --clean --if-exists recomendador | gzip > "$out"
[[ -s "$out" ]] || { echo "Respaldo vacío, descartado"; rm -f "$out"; exit 1; }
find backups -name 'recomendador-*.sql.gz' -mtime +14 -delete
echo "$(date -Is) respaldo creado: $out"
