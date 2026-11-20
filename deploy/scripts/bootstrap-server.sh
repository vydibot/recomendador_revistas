#!/usr/bin/env bash
# Prepara un servidor Linux (Debian/Ubuntu) NUEVO una sola vez. Ejecutar como root o con sudo:
#   curl -fsSL https://raw.githubusercontent.com/<usuario>/<repo>/main/deploy/scripts/bootstrap-server.sh | sudo bash
# o, si ya tienes el repositorio:  sudo ./bootstrap-server.sh
#
# Variables opcionales: APP_DIR (por defecto /opt/recomendador), DEPLOY_USER (usuario que usará GitHub Actions).
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/recomendador}"
DEPLOY_USER="${DEPLOY_USER:-${SUDO_USER:-deploy}}"

[[ $EUID -eq 0 ]] || { echo "Ejecuta como root (sudo)."; exit 1; }

if ! command -v docker >/dev/null; then
  echo "→ Instalando Docker"
  curl -fsSL https://get.docker.com | sh
fi
docker compose version >/dev/null || { echo "Falta el plugin docker compose v2"; exit 1; }

id "$DEPLOY_USER" >/dev/null 2>&1 || useradd --create-home --shell /bin/bash "$DEPLOY_USER"
usermod -aG docker "$DEPLOY_USER"

mkdir -p "$APP_DIR"/{scripts,caddy,backups}
chown -R "$DEPLOY_USER":"$DEPLOY_USER" "$APP_DIR"

ENV_FILE="$APP_DIR/.env"
if [[ ! -f "$ENV_FILE" ]]; then
  read -rp "Dominio (ya apuntando a la IP de este servidor, p. ej. revistas.midominio.com): " DOMAIN
  read -rp "Correo para Let's Encrypt: " ACME_EMAIL
  ADMIN_PASSWORD="$(openssl rand -base64 18 | tr -d '/+=' | cut -c1-20)"
  cat > "$ENV_FILE" <<EOF
DOMAIN=$DOMAIN
ACME_EMAIL=$ACME_EMAIL
POSTGRES_PASSWORD=$(openssl rand -hex 24)
SECRET_KEY=$(openssl rand -hex 32)
ADMIN_PASSWORD=$ADMIN_PASSWORD
IMAGE_PREFIX=pendiente
IMAGE_TAG=latest
EOF
  chmod 600 "$ENV_FILE"
  chown "$DEPLOY_USER":"$DEPLOY_USER" "$ENV_FILE"
  echo
  echo "✓ $ENV_FILE creado. Contraseña del modo editor: $ADMIN_PASSWORD  (guárdala; cámbiala en .env si quieres)"
else
  echo "• $ENV_FILE ya existe, no se modifica."
fi

# Copia de seguridad diaria de la base de datos (03:15), conservando 14 días.
CRON_LINE="15 3 * * * $APP_DIR/scripts/backup-db.sh >> $APP_DIR/backups/backup.log 2>&1"
( crontab -u "$DEPLOY_USER" -l 2>/dev/null | grep -v backup-db.sh || true; echo "$CRON_LINE" ) | crontab -u "$DEPLOY_USER" -

if command -v ufw >/dev/null; then
  ufw allow 22/tcp >/dev/null; ufw allow 80/tcp >/dev/null; ufw allow 443 >/dev/null
  echo "• ufw: permitidos 22, 80 y 443 (actívalo con 'ufw enable' si aún no lo está)."
fi

cat <<EOF

Siguientes pasos
  1. DNS: registro A de tu dominio -> IP pública de este servidor. Puertos 80 y 443 abiertos en el router/firewall.
  2. Clave SSH para GitHub Actions (en tu equipo):  ssh-keygen -t ed25519 -f deploy_key -N ""
       ssh-copy-id -i deploy_key.pub $DEPLOY_USER@<ip-del-servidor>
  3. Secretos del repositorio en GitHub (Settings > Secrets and variables > Actions):
       SSH_HOST         IP o dominio del servidor
       SSH_USER         $DEPLOY_USER
       SSH_PRIVATE_KEY  contenido de deploy_key
       SSH_KNOWN_HOSTS  salida de:  ssh-keyscan -p <puerto> <ip-del-servidor>
       (opcional) SSH_PORT  si no es 22
  4. Haz push a main: el workflow 'Deploy' construye, publica y despliega solo.
EOF
