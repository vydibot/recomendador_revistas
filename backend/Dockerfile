# syntax=docker/dockerfile:1.7
# Contexto de build = raíz del repositorio:  docker build -f backend/Dockerfile .

# ── Etapa 1: dependencias y modelo ──────────────────────────────────────────
FROM python:3.12-slim AS builder
ENV PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1 PYTHONDONTWRITEBYTECODE=1
RUN python -m venv /opt/venv
ENV PATH=/opt/venv/bin:$PATH
WORKDIR /build

# torch en su variante CPU (~200 MB en vez de ~2 GB con CUDA).
RUN pip install --extra-index-url https://download.pytorch.org/whl/cpu "torch>=2.14,<2.15"

# Dependencias de terceros primero (capa cacheable): paquete "vacío" con el pyproject real.
COPY backend/pyproject.toml backend/pyproject.toml
RUN mkdir backend/app && touch backend/app/__init__.py \
    && pip install ./backend \
    && pip uninstall -y recomendador-revistas-backend

# Código propio.
COPY ml ml
COPY backend/app backend/app
RUN pip install --no-deps ./ml ./backend

# SciBERT se descarga en el build: el contenedor funciona sin internet y arranca rápido.
ENV HF_HOME=/opt/hf
RUN python - <<'PY'
from transformers import AutoModel, AutoTokenizer
name = "allenai/scibert_scivocab_uncased"
AutoTokenizer.from_pretrained(name)
AutoModel.from_pretrained(name)
PY

# ── Etapa 2: imagen final ───────────────────────────────────────────────────
FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 \
    PATH=/opt/venv/bin:$PATH \
    HF_HOME=/opt/hf HF_HUB_OFFLINE=1 TOKENIZERS_PARALLELISM=false OMP_NUM_THREADS=4 \
    ENVIRONMENT=production \
    ML_ARTIFACTS_DIR=/opt/ml/thematic_profile \
    ML_GOLD_PATH=/opt/ml/catalogo_maestro_revistas.parquet \
    LIDER_SEED_PATH=/app/seed/lider_journals.json

RUN useradd --system --uid 10001 --create-home app
COPY --from=builder /opt/venv /opt/venv
COPY --from=builder /opt/hf /opt/hf
# Artefactos entrenados + Gold maestro (de solo lectura): lo único del módulo ML que se despliega.
COPY ml/src/recomendador_revistas/models/artifacts/thematic_profile /opt/ml/thematic_profile
COPY ml/src/recomendador_revistas/data/gold/catalogo_maestro_revistas.parquet /opt/ml/catalogo_maestro_revistas.parquet

WORKDIR /app
COPY backend/alembic.ini ./
COPY backend/alembic ./alembic
COPY backend/seed ./seed
COPY backend/entrypoint.sh ./entrypoint.sh
RUN chmod +x entrypoint.sh && chown -R app:app /app
USER app

EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=5s --start-period=120s --retries=5 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=4).status == 200 else 1)"

ENTRYPOINT ["./entrypoint.sh"]
# Un solo worker: el modelo (SciBERT + TF-IDF) vive en memoria (~1.5 GB) y no se duplica.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1", "--proxy-headers", "--forwarded-allow-ips", "*"]
