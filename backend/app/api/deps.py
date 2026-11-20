from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.security import decode_token
from app.db.session import get_db
from app.services.recommender import RecommenderService

DbSession = Annotated[Session, Depends(get_db)]
SettingsDep = Annotated[Settings, Depends(get_settings)]
_bearer = HTTPBearer(auto_error=False)


def get_recommender(request: Request) -> RecommenderService:
    return request.app.state.recommender


RecommenderDep = Annotated[RecommenderService, Depends(get_recommender)]


def require_admin(
    settings: SettingsDep,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> None:
    if not settings.admin_password:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, "Edición deshabilitada en el servidor"
        )
    if credentials is None or not decode_token(credentials.credentials, settings):
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "Credenciales requeridas",
            headers={"WWW-Authenticate": "Bearer"},
        )


AdminDep = Depends(require_admin)
