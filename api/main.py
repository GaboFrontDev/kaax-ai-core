"""FastAPI app for the standalone core module."""

from __future__ import annotations

import logging

from fastapi import FastAPI

from api.dependencies import set_session_manager
from api.routers.router import router
from session_manager import SessionManager
from settings import LOG_LEVEL


logger = logging.getLogger(__name__)



def create_app() -> FastAPI:
    logging.basicConfig(
        level=getattr(logging, LOG_LEVEL.upper(), logging.INFO),
        format="%(asctime)s %(name)s[%(process)d] %(levelname)s %(message)s",
    )

    app = FastAPI(
        title="Core API",
        description="Minimal API for building new agents quickly",
        version="0.1.0",
    )

    app.include_router(router)
    app.state.session_manager = SessionManager()

    @app.on_event("startup")
    async def startup_event():
        await app.state.session_manager.start()
        set_session_manager(app.state.session_manager)
        logger.info("Core API started")

    @app.on_event("shutdown")
    async def shutdown_event():
        await app.state.session_manager.stop()
        logger.info("Core API stopped")

    return app


app = create_app()
