"""Autenticación de administrador: contraseña única + token JWT firmado."""

import hmac
import time
from collections import defaultdict, deque
from datetime import UTC, datetime, timedelta

import jwt

from app.core.config import Settings

_ALGORITHM = "HS256"


def verify_password(candidate: str, settings: Settings) -> bool:
    if not settings.admin_password:
        return False
    return hmac.compare_digest(candidate.encode(), settings.admin_password.encode())


def create_token(settings: Settings) -> tuple[str, int]:
    expires = timedelta(minutes=settings.token_ttl_minutes)
    payload = {"sub": "admin", "exp": datetime.now(UTC) + expires}
    return jwt.encode(payload, settings.secret_key, algorithm=_ALGORITHM), int(
        expires.total_seconds()
    )


def decode_token(token: str, settings: Settings) -> bool:
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[_ALGORITHM])
    except jwt.PyJWTError:
        return False
    return payload.get("sub") == "admin"


class LoginThrottle:
    """Limita intentos fallidos de login por IP (ventana deslizante en memoria)."""

    def __init__(self, max_failures: int = 5, window_seconds: int = 60) -> None:
        self.max_failures = max_failures
        self.window = window_seconds
        self._failures: dict[str, deque[float]] = defaultdict(deque)

    def _prune(self, key: str) -> deque[float]:
        events = self._failures[key]
        cutoff = time.monotonic() - self.window
        while events and events[0] < cutoff:
            events.popleft()
        return events

    def blocked(self, key: str) -> bool:
        return len(self._prune(key)) >= self.max_failures

    def register_failure(self, key: str) -> None:
        self._prune(key).append(time.monotonic())

    def reset(self, key: str) -> None:
        self._failures.pop(key, None)
