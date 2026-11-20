from fastapi import APIRouter, HTTPException, status

from app.api.deps import DbSession, RecommenderDep
from app.schemas.recommend import ModelInfoOut, RecommendRequest, RecommendResponse
from app.services.recommender import RecommenderUnavailableError

router = APIRouter(prefix="/recommend", tags=["recomendador"])


@router.get("/model", response_model=ModelInfoOut)
def model_info(db: DbSession, recommender: RecommenderDep) -> ModelInfoOut:
    return recommender.info(db)


@router.post("", response_model=RecommendResponse)
def recommend(
    body: RecommendRequest, db: DbSession, recommender: RecommenderDep
) -> RecommendResponse:
    try:
        return recommender.recommend(db, body)
    except RecommenderUnavailableError as exc:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="El recomendador no está disponible"
            + (
                " (cargando el modelo, reintenta en unos segundos)"
                if exc.status == "loading"
                else ""
            ),
        ) from exc
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
