"""FastAPI app for the standalone core module."""

from __future__ import annotations

import asyncio
import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import Response
from starlette.middleware.base import BaseHTTPMiddleware

from api.dependencies import set_session_manager
from api.routers.router import router
from session_manager import SessionManager
from settings import LOG_LEVEL


logger = logging.getLogger(__name__)

_HANGUP_TWIML = (
    '<?xml version="1.0" encoding="UTF-8"?>'
    "<Response><Hangup/></Response>"
)


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

    class VoiceRequestLogger(BaseHTTPMiddleware):
        async def dispatch(self, request: Request, call_next):
            if request.url.path.startswith("/webhooks/voice") or request.url.path.startswith("/audio"):
                import time as _time
                t0 = _time.perf_counter()
                logger.info(">>> REQUEST %s %s", request.method, request.url.path)
                response = await call_next(request)
                logger.info("<<< RESPONSE %s %s status=%d t=%.2fs",
                    request.method, request.url.path, response.status_code,
                    _time.perf_counter() - t0)
                return response
            return await call_next(request)

    app.add_middleware(VoiceRequestLogger)
    app.include_router(router)
    app.state.session_manager = SessionManager()

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(request: Request, exc: RequestValidationError):
        """
        FastAPI returns 422 JSON by default when a Form field is missing.
        Twilio interprets that as "application error occurred".
        For voice webhooks return a bare <Hangup/> TwiML instead.
        """
        path = request.url.path
        if path.startswith("/webhooks/voice"):
            # Log the raw body so we can see exactly what Twilio sent
            body = await request.body()
            logger.error(
                "voice_webhook_validation_error path=%s errors=%s body=%s",
                path,
                exc.errors(),
                body.decode("utf-8", errors="replace")[:500],
            )
            return Response(content=_HANGUP_TWIML, media_type="application/xml")
        raise exc

    @app.on_event("startup")
    async def startup_event():
        await app.state.session_manager.start()
        set_session_manager(app.state.session_manager)
        from infra.follow_up.scheduler import run_scheduler
        from infra.follow_up.digest_scheduler import run_digest_scheduler
        app.state.follow_up_task = asyncio.create_task(run_scheduler())
        app.state.digest_task = asyncio.create_task(run_digest_scheduler())
        logger.info("Core API started")

    @app.on_event("shutdown")
    async def shutdown_event():
        for attr in ("follow_up_task", "digest_task"):
            task = getattr(app.state, attr, None)
            if task:
                task.cancel()
        await app.state.session_manager.stop()
        logger.info("Core API stopped")

    return app


app = create_app()
