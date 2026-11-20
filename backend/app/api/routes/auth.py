from fastapi import APIRouter, HTTPException, Request, status

from app.api.deps import AdminDep, SettingsDep
from app.core.security import LoginThrottle, create_token, verify_password
from app.schemas.auth import LoginRequest, TokenResponse

router = APIRouter(prefix="/auth", tags=["autenticación"])
_throttle = LoginThrottle()


def _client_key(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


@router.post("/login", response_model=TokenResponse)
def login(body: LoginRequest, request: Request, settings: SettingsDep) -> TokenResponse:
    if not settings.admin_password:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, "Edición deshabilitada en el servidor"
        )
    key = _client_key(request)
    if _throttle.blocked(key):
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS, "Demasiados intentos; espera un minuto"
        )
    if not verify_password(body.password, settings):
        _throttle.register_failure(key)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Contraseña incorrecta")
    _throttle.reset(key)
    token, expires_in = create_token(settings)
    return TokenResponse(access_token=token, expires_in=expires_in)


@router.get("/me", dependencies=[AdminDep])
def me() -> dict:
    return {"role": "admin"}
