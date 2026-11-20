from app.core.config import Settings
from app.main import create_app
from app.services.recommender import RecommenderService
from tests.conftest import make_journal

PAYLOAD = {
    "title": "Aprendizaje profundo aplicado a cultivos",
    "abstract": "Entrenamos una red neuronal para clasificar imágenes de hojas.",
    "keywords": "deep learning, agricultura",
}


def test_health(client):
    body = client.get("/api/health").json()
    assert body["status"] == "ok" and body["database"] == "ok" and body["recommender"] == "ready"


def test_recommend_enriches_with_catalog(client, db):
    make_journal(db, title="Journal of ML", issn_electronic="1111-1111", quartile="Q1")
    body = client.post("/api/recommend", json={**PAYLOAD, "top_k": 2}).json()
    assert [r["rank"] for r in body["results"]] == [1, 2]
    first, second = body["results"]
    assert first["journal"]["title"] == "Journal of ML" and first["journal"]["quartile"] == "Q1"
    assert second["journal"] is None and second["score_calidad_costo"] is None
    assert body["model"]["available"] and body["model"]["journals_covered"] == 2
    assert body["priority_order"] == ["impacto", "eficiencia", "flujo"]


def test_recommend_forwards_options(client, fake_engine):
    client.post(
        "/api/recommend",
        json={
            **PAYLOAD,
            "priority_order": ["flujo", "impacto", "eficiencia"],
            "language": "es",
            "top_k": 5,
        },
    )
    call = fake_engine.calls[-1]
    assert call["priority_order"] == ("flujo", "impacto", "eficiencia")
    assert call["language"] == "es"
    assert call["top_k"] == 15  # margen x3 para colapsar filas repetidas de una revista


def test_recommend_validation(client):
    assert client.post("/api/recommend", json={"title": "corto"}).status_code == 422
    assert client.post("/api/recommend", json={**PAYLOAD, "top_k": 0}).status_code == 422
    assert client.post("/api/recommend", json={**PAYLOAD, "top_k": 500}).status_code == 422
    assert (
        client.post("/api/recommend", json={**PAYLOAD, "priority_order": ["impacto"]}).status_code
        == 422
    )
    dup = {**PAYLOAD, "priority_order": ["impacto", "impacto", "flujo"]}
    assert client.post("/api/recommend", json=dup).status_code == 422
    assert (
        client.post("/api/recommend", json={**PAYLOAD, "abstract": "x" * 10_001}).status_code == 422
    )


def test_model_info(client, db):
    make_journal(db, title="A")
    info = client.get("/api/recommend/model").json()
    assert info["available"] and info["catalog_total"] == 1 and info["alpha"] == 0.8


def test_unavailable_while_loading():
    settings = Settings(environment="test", database_url="sqlite://", recommender_enabled=True)
    service = RecommenderService(settings)  # sin motor: aún "cargando"
    app = create_app(settings, service)
    from fastapi.testclient import TestClient

    with TestClient(app) as test_client:
        assert test_client.get("/api/recommend/model").json() == {
            "available": False,
            "alpha": None,
            "journals_covered": None,
            "catalog_total": None,
            "tfidf_features": None,
            "scibert_model": None,
            "quality_weight": None,
        }
        res = test_client.post("/api/recommend", json=PAYLOAD)
        assert res.status_code == 503


def test_recommend_collapses_issns_of_the_same_journal(client, db, fake_engine):
    from app.services import journals as service
    from tests.conftest import FakeRec

    journal = make_journal(db, title="Revista Doble", issn_electronic="1111-1111")
    service.update_journal(db, journal, {"issn_print": "2222-2222"})
    other = make_journal(db, title="Otra", issn_electronic="3333-3333")
    fake_engine.recommend = lambda **_: [  # noqa: ARG005
        FakeRec(1, "1111-1111"),
        FakeRec(2, "2222-2222"),
        FakeRec(3, "3333-3333"),
    ]
    body = client.post("/api/recommend", json={**PAYLOAD, "top_k": 3}).json()
    assert [r["journal"]["id"] for r in body["results"]] == [journal.id, other.id]
    assert [r["rank"] for r in body["results"]] == [1, 2]
