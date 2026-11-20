"""Punto de entrada de la API."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import auth, health, journals, recommend
from app.core.config import Settings, get_settings
from app.services.recommender import RecommenderService

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


def create_app(
    settings: Settings | None = None, recommender: RecommenderService | None = None
) -> FastAPI:
    settings = settings or get_settings()
    service = recommender or RecommenderService(settings)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        service.start_loading()
        yield

    app = FastAPI(
        title="Recomendador de Revistas — API",
        version="0.1.0",
        lifespan=lifespan,
        docs_url="/api/docs",
        openapi_url="/api/openapi.json",
        redoc_url=None,
    )
    app.state.recommender = service
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["GET", "POST", "PATCH", "DELETE"],
        allow_headers=["Authorization", "Content-Type"],
    )
    for router in (health.router, auth.router, journals.router, recommend.router):
        app.include_router(router, prefix="/api")
    return app


app = create_app()
