from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import Settings, get_settings
from app.db.base import Base
from app.db.session import get_db
from app.main import create_app
from app.services import journals as service
from app.services.recommender import RecommenderService

ADMIN_PASSWORD = "clave-de-prueba"


@dataclass
class FakeRec:
    rank: int
    issn: str
    score_tfidf: float | None = 0.4
    score_scibert: float | None = 0.6
    score_tematico: float | None = 0.5
    score_calidad_costo: float | None = 0.3
    score_final: float | None = 0.4


@dataclass
class FakeInfo:
    alpha: float = 0.8
    journals_covered: int = 2
    tfidf_features: int = 100
    scibert_model: str = "fake/scibert"
    quality_weight: float = 0.5


class FakeEngine:
    info = FakeInfo()
    identifiers = ["1111-1111", "9999-9999"]
    calls: list[dict]

    def __init__(self) -> None:
        self.calls = []

    def warmup(self) -> None:
        return None

    def recommend(self, **kwargs):
        self.calls.append(kwargs)
        if not kwargs["title"] and not kwargs["abstract"] and not kwargs["keywords"]:
            raise ValueError("El manuscrito no contiene texto utilizable")
        return [FakeRec(1, "1111-1111"), FakeRec(2, "9999-9999", score_calidad_costo=None)]


@pytest.fixture
def settings() -> Settings:
    return Settings(
        environment="test",
        database_url="sqlite://",
        admin_password=ADMIN_PASSWORD,
        secret_key="x" * 40,
        recommender_enabled=False,
        seed_on_start=False,
    )


@pytest.fixture
def session_factory() -> Iterator[sessionmaker[Session]]:
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    yield sessionmaker(bind=engine, expire_on_commit=False)
    engine.dispose()


@pytest.fixture
def db(session_factory) -> Iterator[Session]:
    with session_factory() as session:
        yield session


@pytest.fixture
def fake_engine() -> FakeEngine:
    return FakeEngine()


@pytest.fixture
def client(settings, session_factory, fake_engine) -> Iterator[TestClient]:
    recommender = RecommenderService(settings, engine=fake_engine)
    app = create_app(settings, recommender)

    def _db() -> Iterator[Session]:
        with session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_settings] = lambda: settings
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def auth(client) -> dict[str, str]:
    token = client.post("/api/auth/login", json={"password": ADMIN_PASSWORD}).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def make_journal(db: Session, **values) -> service.Journal:
    values.setdefault("title", "Revista de prueba")
    return service.create_journal(db, values)


@pytest.fixture
def catalog(db) -> list:
    """Cuatro revistas con datos variados para probar filtros y orden."""
    return [
        make_journal(
            db,
            title="Journal of Machine Learning",
            issn_electronic="1111-1111",
            quartile="Q1",
            access_type="Open Access",
            country="Estados Unidos",
            apc_usd=0.0,
            weeks_to_publication=8,
            h_index=120,
            topics=["Aprendizaje Automático"],
            language="Inglés",
            submission_format="MDPI",
        ),
        make_journal(
            db,
            title="Revista Colombiana de Agronomía",
            issn_print="2222-2222",
            quartile="Q3",
            publindex_category="A2",
            access_type="Híbrido",
            country="Colombia",
            apc_usd=500.0,
            weeks_to_publication=20,
            h_index=15,
            topics=["Agronomía y Agricultura"],
            language="Español, Inglés",
        ),
        make_journal(
            db,
            title="Ciberseguridad Aplicada",
            issn_electronic="3333-3333",
            quartile="Q2",
            access_type="Open Access",
            country="España",
            apc_usd=2500.0,
            weeks_to_publication=30,
            topics=["Ciberseguridad y Privacidad", "Aprendizaje Automático"],
            language="Español",
            submission_format="Springer",
        ),
        make_journal(db, title="Sin Datos", topics=[]),
    ]
