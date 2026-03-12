"""Dependency container for core API objects."""

from __future__ import annotations

from fastapi import Request

from api.agent_service import AgentService
from session_manager import SessionManager


from client_config import ClientConfig

_session_manager: SessionManager | None = None
_agent_service: AgentService | None = None
_client_config: ClientConfig | None = None


def set_client_config(config: ClientConfig) -> None:
    global _client_config
    _client_config = config


def get_client_config() -> ClientConfig | None:
    return _client_config


def set_session_manager(session_mgr: SessionManager) -> None:
    global _session_manager, _agent_service
    _session_manager = session_mgr
    _agent_service = AgentService(session_mgr, client_config=_client_config)


def get_session_manager(request: Request) -> SessionManager:
    """FastAPI dependency for the active session manager."""
    return request.app.state.session_manager


def get_session_manager_from_cache() -> SessionManager:
    """Fallback getter for non-request contexts (tests/scripts)."""
    if _session_manager is None:
        raise RuntimeError("Session manager not initialized")
    return _session_manager


def get_agent_service(request: Request) -> AgentService:
    """FastAPI dependency for a request-scoped agent service."""
    return AgentService(request.app.state.session_manager, client_config=_client_config)


def get_agent_service_from_cache() -> AgentService:
    """Fallback getter for non-request contexts (tests/scripts)."""
    if _agent_service is None:
        raise RuntimeError("Agent service not initialized")
    return _agent_service
