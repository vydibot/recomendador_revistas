from fastapi import APIRouter
from sqlalchemy import text

from app.api.deps import DbSession, RecommenderDep

router = APIRouter(tags=["salud"])


@router.get("/health")
def health(db: DbSession, recommender: RecommenderDep) -> dict:
    """Estado del servicio; la BD debe responder, el recomendador puede estar cargando."""
    db.execute(text("SELECT 1"))
    return {"status": "ok", "database": "ok", "recommender": recommender.status}
