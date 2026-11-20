# Guía paso a paso: desplegar la app en tu servidor

Esta guía complementa [despliegue.md](despliegue.md). Los pasos marcados **[SERVIDOR]** se hacen conectado al servidor, **[TU PC]** en tu equipo y **[GITHUB]** en la web del repositorio.

Al final, cada `git push` a `main` prueba, construye y despliega la app sola.

---

## 0. Antes de empezar

| Necesitas | Detalle |
|---|---|
| Servidor Linux | Debian/Ubuntu, 2+ vCPU, **4 GB de RAM mínimo**, 10 GB de disco, acceso `sudo` |
| IP pública | Si es dinámica, usa un servicio DDNS |
| Dominio | Con un registro **A** hacia la IP del servidor (ej. `revistas.midominio.com`) |
| Puertos | **80 y 443** abiertos en el firewall del servidor y en el router (reenvío de puertos a la IP del servidor). El 22 (SSH) debe ser accesible desde internet para GitHub Actions |

Comprueba el DNS antes de seguir. Desde tu PC:

```bash
dig +short revistas.midominio.com     # debe devolver la IP pública de tu servidor
```

---

## 1. [SERVIDOR] Entrar y descargar el repositorio

```bash
ssh TU_USUARIO@IP_DEL_SERVIDOR
sudo apt update && sudo apt install -y git
git clone https://github.com/vydibot/recomendador_revistas.git
cd recomendador_revistas
```

Si el repositorio es privado, GitHub pedirá usuario y un *Personal Access Token* como contraseña. Otra opción es copiar solo el script desde tu PC:

```bash
scp deploy/scripts/bootstrap-server.sh TU_USUARIO@IP:~
```

## 2. [SERVIDOR] Preparar el servidor (una sola vez)

```bash
sudo ./deploy/scripts/bootstrap-server.sh
```

Ejecútalo **desde el archivo**, no con `curl ... | sudo bash`. El script hace preguntas y no puede leer tus respuestas si recibe el script por la tubería.

El script hace lo siguiente:
- Instala Docker, si falta.
- Añade tu usuario al grupo `docker`.
- Crea `/opt/recomendador` con `scripts/`, `caddy/` y `backups/`.
- Te pregunta el **dominio** y el **correo** (Let's Encrypt).
- Genera `/opt/recomendador/.env` con `POSTGRES_PASSWORD`, `SECRET_KEY` y `ADMIN_PASSWORD` aleatorios.
- Programa un respaldo diario de la base a las 03:15.
- Abre los puertos 22, 80 y 443 en `ufw`, si está instalado.

**Anota la contraseña de editor** que imprime. También queda en `.env`.

Después, cierra la sesión SSH y vuelve a entrar. Así el grupo `docker` se aplica a tu sesión:

```bash
exit
ssh TU_USUARIO@IP_DEL_SERVIDOR
docker ps          # debe funcionar SIN sudo
```

Revisa el archivo generado:

```bash
cat /opt/recomendador/.env
```

Debe tener estas variables: `DOMAIN`, `ACME_EMAIL`, `POSTGRES_PASSWORD`, `SECRET_KEY`, `ADMIN_PASSWORD`, `IMAGE_PREFIX` e `IMAGE_TAG`. `IMAGE_PREFIX` dirá `pendiente` hasta el primer despliegue, y eso es normal.

Si tienes `ufw` instalado pero apagado, actívalo **después** de confirmar que el 22 está permitido:

```bash
sudo ufw status
sudo ufw enable
```

## 3. [TU PC] Crear la llave SSH para GitHub Actions

Usa una llave **solo para despliegue**, distinta de la tuya personal.

```bash
ssh-keygen -t ed25519 -f deploy_key -N ""
ssh-copy-id -i deploy_key.pub TU_USUARIO@IP_DEL_SERVIDOR
ssh-keyscan IP_DEL_SERVIDOR > known_hosts.txt     # si tu SSH no usa el 22: ssh-keyscan -p PUERTO IP
```

Si el servidor no acepta contraseña por SSH, `ssh-copy-id` falla. En ese caso, pega el contenido de `deploy_key.pub` como una línea nueva en `~/.ssh/authorized_keys` del servidor.

Prueba que la llave funciona **antes** de configurar GitHub:

```bash
ssh -i deploy_key TU_USUARIO@IP_DEL_SERVIDOR 'docker ps && ls /opt/recomendador'
```

Debe mostrar la lista de contenedores, vacía, y la carpeta, sin pedir contraseña.

## 4. [GITHUB] Configurar el environment y los secretos

En `https://github.com/vydibot/recomendador_revistas`:

1. **Settings → Environments → New environment** con el nombre exacto `production`. Opcional: marca *Required reviewers* para aprobar cada despliegue a mano.
2. **Settings → Secrets and variables → Actions → New repository secret**, uno por uno:

| Nombre (exacto) | Valor |
|---|---|
| `SSH_HOST` | IP o dominio del servidor |
| `SSH_USER` | `TU_USUARIO` (el mismo con el que hiciste el bootstrap) |
| `SSH_PRIVATE_KEY` | contenido **completo** de `deploy_key`, incluidas las líneas `-----BEGIN/END...` |
| `SSH_KNOWN_HOSTS` | contenido de `known_hosts.txt` |
| `SSH_PORT` | solo si no usas el 22 |

Después borra la llave privada de tu PC, o guárdala en un gestor de contraseñas:

```bash
shred -u deploy_key
```

## 5. [GITHUB] Lanzar el primer despliegue

- Opción A: *Actions → Deploy → Run workflow* sobre `main`.
- Opción B: `git push origin main`.

Verás estas fases:
1. **CI**: tests, tipos y build de las imágenes. Tarda unos minutos.
2. **Publicar imágenes**: las sube a GHCR.
3. **Desplegar en el servidor**:
   - *Validar secretos*: falla indicando cuál falta, si hay alguno sin crear.
   - *Subir configuración*: copia `deploy/` a `/opt/recomendador`.
   - *Desplegar*: ejecuta `deploy.sh`. **El primer arranque tarda varios minutos**, hasta 7: carga el modelo y siembra la base.
   - *Verificar el sitio público*: consulta `https://TU_DOMINIO/api/health`.

## 6. [SERVIDOR] Verificar

```bash
cd /opt/recomendador
docker compose -f docker-compose.prod.yml ps            # 4 servicios "Up"; backend y db "healthy"
docker compose -f docker-compose.prod.yml logs --tail=50 backend
docker compose -f docker-compose.prod.yml logs caddy | grep -i certificate
curl -s https://TU_DOMINIO/api/health
```

Abre `https://TU_DOMINIO` en el navegador. Si dice "El modelo se está cargando", espera 30–60 s.

En los logs del backend busca la línea del seed: `seed etl: creadas=… actualizadas=…`.

---

## Después del primer despliegue

| Quiero… | Hago… |
|---|---|
| Publicar cambios | `git push origin main`. Todo es automático |
| Ver logs | `docker compose -f docker-compose.prod.yml logs -f backend` en `/opt/recomendador` |
| Volver a una versión anterior | `IMAGE_PREFIX=ghcr.io/vydibot/recomendador_revistas IMAGE_TAG=<sha> ./scripts/deploy.sh` |
| Respaldo manual | `./scripts/backup-db.sh`. Los archivos quedan en `backups/` |
| Cambiar la contraseña de editor | Editar `ADMIN_PASSWORD` en `.env` y ejecutar `docker compose -f docker-compose.prod.yml up -d backend` |

El rollback automático existe. Si la versión nueva no queda sana, `deploy.sh` vuelve a la anterior y el workflow termina en rojo.

## Problemas frecuentes

| Síntoma | Qué revisar |
|---|---|
| *Validar secretos* falla | Falta ese secreto en GitHub, o está en otro repositorio o environment |
| `Permission denied (publickey)` | La llave pública no está en `~/.ssh/authorized_keys` del servidor, o `SSH_USER` no coincide |
| `Host key verification failed` | `SSH_KNOWN_HOSTS` mal copiado, o falta `-p PUERTO` en `ssh-keyscan` |
| `permission denied ... docker.sock` | Tu usuario no está en el grupo `docker`. Ejecuta `sudo usermod -aG docker $USER` y vuelve a entrar |
| Backend "not healthy" | `logs backend`. Con menos de 4 GB de RAM el modelo no carga |
| `password authentication failed` | Cambiaste `POSTGRES_PASSWORD` después de crear la base. Ver la explicación del volumen `pgdata` |
| Caddy no emite el certificado | El DNS no apunta a la IP, el 80 o el 443 están cerrados, o `DOMAIN` está mal escrito. Mira `logs caddy` |
| El workflow falla solo en *Verificar el sitio público* | La app corre pero el HTTPS aún no responde. Revisa DNS y certificado |

## Variante sin dominio (pruebas)

En `/opt/recomendador/.env` pon `DOMAIN=:80`. La app queda en `http://IP_DEL_SERVIDOR`, sin HTTPS. El último paso del workflow fallará, porque comprueba `https://`, pero la app funcionará igual. `ACME_EMAIL` sigue siendo obligatorio, aunque no se use.
