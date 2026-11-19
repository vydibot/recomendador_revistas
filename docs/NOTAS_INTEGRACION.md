# Notas de trabajo (temporal; se elimina al terminar)

## Decisiones del usuario
- Servidor con IP pública + dominio propio -> Caddy (HTTPS automático), deploy GH Actions: build -> GHCR -> SSH.
- Catálogo = Gold ETL actual (906) + LIDER data.json (119 válidas; se omite fila "500").
- Recomendador = modelo actual (247 revistas, alpha 0.8, TF-IDF + SciBERT). Todas las 247 tienen metadata TOPSIS.

## Estructura destino
- ml/ (paquete recomendador_revistas: src/, tests/, pyproject, README)  [HECHO: git mv]
- docs/informe/ (paper)  [HECHO: mv]
- backend/ FastAPI + SQLAlchemy 2 + Alembic + Postgres 18 (SQLite en dev)
- frontend/ React 19 + Vite 8 + Tailwind 4 + react-router 8 (de LIDER APP)
- deploy/ (docker-compose.prod.yml, caddy/Caddyfile, scripts/{deploy,backup-db,bootstrap-server}.sh)
- .github/workflows/{ci.yml, deploy.yml}; docker-compose.yml (dev); Makefile; .env.example

## Hallazgos de datos (reportar al usuario)
- Gold: 186 revistas comparten registro Scimago con otra (163 sourceid para 337 filas); 378 comparten registro DOAJ;
  324 de 380 "APC observado" tienen tiene_apc=False en DOAJ. Causa: cruce difuso WRatio>=85 (0 cruces ISSN con OpenAPC/Facts).
- LIDER: 6 pares con ISSN repetido; 2327-4697 asignado a 2 revistas IEEE distintas; fila basura "500".
- Perfiles 2145-8553 y 0120-0283 tienen scores idénticos (posible corpus duplicado).

## Pendiente
1. backend (código, migración, seed, CLI) -> verificar con SQLite y Postgres
2. ThematicProfile.load() en ml + evaluate_journal usa load
3. frontend (migrar UI, 2 páginas) -> npm install, typecheck, build
4. Docker + compose + Caddy -> build y prueba e2e local
5. CI/CD workflows + docs + README raíz + ml/README rutas
