"""Configuración de la aplicación (variables de entorno / archivo .env)."""

from functools import lru_cache
from pathlib import Path

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[2]
REPO_ROOT = BACKEND_DIR.parent
_ML_PACKAGE = REPO_ROOT / "ml" / "src" / "recomendador_revistas"

_INSECURE_SECRET = "dev-insecure-secret-change-me"  # noqa: S105


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    environment: str = "development"  # development | production | test

    # Base de datos: SQLite en desarrollo, PostgreSQL en producción.
    database_url: str = f"sqlite:///{BACKEND_DIR / 'dev.db'}"

    # Seguridad (solo escritura del catálogo requiere autenticación).
    secret_key: str = _INSECURE_SECRET
    admin_password: str = ""  # vacío => las rutas de escritura quedan deshabilitadas
    token_ttl_minutes: int = 480
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:5173"])

    # Datos y modelo.
    ml_artifacts_dir: Path = _ML_PACKAGE / "models" / "artifacts" / "thematic_profile"
    ml_gold_path: Path = _ML_PACKAGE / "data" / "gold" / "catalogo_maestro_revistas.parquet"
    lider_seed_path: Path = BACKEND_DIR / "seed" / "lider_journals.json"
    seed_on_start: bool = True
    recommender_enabled: bool = True

    # Límites de entrada del recomendador (protegen la CPU del servidor).
    recommend_max_chars: int = 12_000
    max_upload_bytes: int = 5 * 1024 * 1024

    @model_validator(mode="after")
    def _check_production(self) -> "Settings":
        if self.environment == "production":
            if self.secret_key == _INSECURE_SECRET or len(self.secret_key) < 32:
                raise ValueError("SECRET_KEY debe tener >= 32 caracteres en producción")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
