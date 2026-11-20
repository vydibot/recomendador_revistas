# Despliegue en tu servidor Linux

Esquema: **GitHub Actions → imágenes en GHCR → SSH al servidor → `docker compose`**. El servidor necesita IP pública, un dominio apuntándole y los puertos 80 y 443 abiertos. Todo lo demás lo hace el pipeline.

## Requisitos del servidor

- Debian/Ubuntu con acceso `sudo`. Recomendado: 2+ vCPU, **4 GB de RAM** (el modelo usa ~1,5 GB; el backend tiene límite de 3 GB) y 10 GB de disco.
- Docker Engine con el plugin Compose v2 (el script de preparación lo instala si falta).
- Dominio con registro **A** hacia la IP pública (si tu IP es dinámica, usa DDNS). Puertos **80/443** abiertos en firewall y router; Let's Encrypt valida por el 80.

## Puesta en marcha (una sola vez)

1. **Preparar el servidor** (como root o con sudo). Pide dominio y correo, genera los secretos en `/opt/recomendador/.env` y programa el respaldo diario:

   ```bash
   sudo ./deploy/scripts/bootstrap-server.sh      # desde una copia del repo, o con curl al archivo raw
   ```

   Anota la contraseña de editor que imprime (también queda en `.env`).

2. **Llave SSH dedicada** para GitHub Actions (en tu equipo):

   ```bash
   ssh-keygen -t ed25519 -f deploy_key -N ""
   ssh-copy-id -i deploy_key.pub <usuario>@<ip-del-servidor>
   ssh-keyscan <ip-del-servidor>      # salida → secreto SSH_KNOWN_HOSTS
   ```

3. **Secretos en GitHub** (*Settings → Secrets and variables → Actions*; el job usa el *environment* `production`, créalo en *Settings → Environments* y, si quieres, exige aprobación manual):

   | Secreto | Valor |
   |---|---|
   | `SSH_HOST` | IP o dominio del servidor |
   | `SSH_USER` | usuario con permisos de Docker (el de `bootstrap-server.sh`) |
   | `SSH_PRIVATE_KEY` | contenido de `deploy_key` |
   | `SSH_KNOWN_HOSTS` | salida de `ssh-keyscan` |
   | `SSH_PORT` | opcional, si no es 22 |

4. **Primer despliegue**: `git push origin main` (o *Actions → Deploy → Run workflow*). El primer arranque tarda más (siembra la BD y carga el modelo); Caddy obtiene el certificado en el primer acceso HTTPS.

Al terminar, `https://<tu-dominio>` sirve la app. El pipeline falla (y el servidor vuelve solo a la versión anterior) si el backend no queda saludable.

## Qué hace cada ejecución de *Deploy*

1. **CI**: pytest de `ml` y `backend` (con migraciones y seed sobre PostgreSQL real), tipos y pruebas del frontend, build de ambas imágenes.
2. **Publicar**: `ghcr.io/<owner>/<repo>/{backend,frontend}` con etiquetas `:<sha>` y `:latest`.
3. **Desplegar**: copia `deploy/` al servidor, ejecuta `scripts/deploy.sh` (pull → `up -d` → espera salud → limpia imágenes; **rollback automático** si falla) y comprueba `https://<dominio>/api/health`.

Las imágenes de GHCR de un repositorio privado son privadas: `deploy.sh` se autentica con el `GITHUB_TOKEN` del propio job (no hay que guardar ningún otro token).

## Operación

```bash
cd /opt/recomendador
docker compose -f docker-compose.prod.yml ps
docker compose -f docker-compose.prod.yml logs -f backend
./scripts/backup-db.sh                       # respaldo manual (el cron lo hace a diario, 14 días)
```

- **Restaurar** un respaldo:
  `gunzip -c backups/recomendador-AAAAMMDD-HHMM.sql.gz | docker compose -f docker-compose.prod.yml exec -T db psql -U recomendador recomendador`
- **Volver a una versión**: `IMAGE_PREFIX=ghcr.io/<owner>/<repo> IMAGE_TAG=<sha-anterior> ./scripts/deploy.sh`.
- **Cambiar la contraseña de editor**: editar `ADMIN_PASSWORD` en `.env` y `docker compose -f docker-compose.prod.yml up -d backend`.
- Los datos persisten en los volúmenes `pgdata` (BD) y `caddy_data` (certificados). `docker compose down` no los borra; `down -v` sí.

## Actualizar el catálogo con un ETL nuevo

1. Ejecuta el ETL en `ml/` (genera `data/gold/catalogo_maestro_revistas.parquet`) y, si cambió el corpus de artículos, reentrena (`train_thematic_profile.py`).
2. Haz commit de los parquet y artefactos y push a `main`. En el arranque del nuevo contenedor el *seed* añade las revistas nuevas, actualiza las existentes **salvo las editadas a mano** y retira las que desaparecieron del Gold.

## Problemas frecuentes

| Síntoma | Causa probable |
|---|---|
| Caddy no emite el certificado | DNS no apunta aún a la IP, 80/443 cerrados o el dominio de `.env` mal escrito (`docker compose logs caddy`) |
| *Deploy* falla en "Desplegar" con "not healthy" | Revisa `logs backend`; con poca RAM el modelo no carga. Mínimo 4 GB |
| `Permission denied` al correr docker por SSH | El usuario de `SSH_USER` no está en el grupo `docker` |
| La UI dice "El modelo se está cargando" | Normal los primeros ~30–60 s tras cada reinicio |
