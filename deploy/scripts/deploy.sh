#!/usr/bin/env bash
# Despliega una versión en el servidor: descarga imágenes, reinicia el stack y verifica salud.
# Si la versión nueva no queda sana, vuelve automáticamente a la anterior.
#
# Uso:  IMAGE_PREFIX=ghcr.io/usuario/repo IMAGE_TAG=<sha> ./deploy.sh
#       (opcional) GHCR_USER y GHCR_TOKEN para autenticarse en GHCR si las imágenes son privadas.
set -euo pipefail

cd "$(dirname "$0")/.."
COMPOSE=(docker compose -f docker-compose.prod.yml)
ENV_FILE=".env"
HEALTH_TIMEOUT="${HEALTH_TIMEOUT:-420}"   # el primer arranque descarga/carga el modelo y siembra la BD

[[ -f "$ENV_FILE" ]] || { echo "Falta $ENV_FILE (ejecuta scripts/bootstrap-server.sh primero)"; exit 1; }
: "${IMAGE_PREFIX:?define IMAGE_PREFIX (p. ej. ghcr.io/usuario/repo)}"
: "${IMAGE_TAG:?define IMAGE_TAG}"

set_env() {  # set_env CLAVE VALOR  -> reemplaza o agrega la línea en .env
  if grep -q "^$1=" "$ENV_FILE"; then sed -i "s|^$1=.*|$1=$2|" "$ENV_FILE"; else echo "$1=$2" >> "$ENV_FILE"; fi
}

previous_tag="$(grep '^IMAGE_TAG=' "$ENV_FILE" | cut -d= -f2- || true)"

if [[ -n "${GHCR_TOKEN:-}" ]]; then
  echo "$GHCR_TOKEN" | docker login ghcr.io -u "${GHCR_USER:?define GHCR_USER}" --password-stdin >/dev/null
fi

wait_healthy() {
  local deadline=$((SECONDS + HEALTH_TIMEOUT)) cid status
  while (( SECONDS < deadline )); do
    cid="$("${COMPOSE[@]}" ps -q backend || true)"
    status="$([[ -n "$cid" ]] && docker inspect -f '{{.State.Health.Status}}' "$cid" 2>/dev/null || echo starting)"
    [[ "$status" == "healthy" ]] && return 0
    [[ "$status" == "unhealthy" ]] && return 1
    sleep 5
  done
  return 1
}

apply() {  # apply TAG
  set_env IMAGE_PREFIX "$IMAGE_PREFIX"
  set_env IMAGE_TAG "$1"
  export IMAGE_PREFIX IMAGE_TAG="$1"
  "${COMPOSE[@]}" pull --quiet
  "${COMPOSE[@]}" up -d --remove-orphans
}

echo "→ Desplegando $IMAGE_PREFIX @ $IMAGE_TAG (anterior: ${previous_tag:-ninguna})"
apply "$IMAGE_TAG"

if wait_healthy; then
  echo "✓ Backend saludable"
  docker image prune -f >/dev/null
  "${COMPOSE[@]}" ps
  exit 0
fi

echo "✗ La versión $IMAGE_TAG no quedó saludable. Logs del backend:"
"${COMPOSE[@]}" logs --tail=60 backend || true
if [[ -n "$previous_tag" && "$previous_tag" != "$IMAGE_TAG" ]]; then
  echo "↺ Volviendo a $previous_tag"
  apply "$previous_tag"
  wait_healthy && echo "Rollback completado" || echo "El rollback tampoco quedó sano: revisa manualmente"
fi
exit 1
