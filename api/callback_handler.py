"""Callback handler used by API requests to collect run metadata."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from langchain_core.callbacks.base import AsyncCallbackHandler


class APICallbackHandler(AsyncCallbackHandler):
    def __init__(self):
        super().__init__()
        self.tools_used: List[str] = []
        self.root_run_id: Optional[str] = None

    def _record_run_id(self, **kwargs: Any) -> None:
        run_id = kwargs.get("run_id")
        if run_id and self.root_run_id is None:
            self.root_run_id = str(run_id)

    async def on_chain_start(
        self,
        serialized: Dict[str, Any],
        inputs: Dict[str, Any],
        **kwargs: Any,
    ):
        _ = serialized
        _ = inputs
        self._record_run_id(**kwargs)

    async def on_llm_start(self, serialized: Dict[str, Any], prompts: List[str], **kwargs: Any):
        _ = serialized
        _ = prompts
        self._record_run_id(**kwargs)

    async def on_tool_start(self, serialized: Dict[str, Any], input_str: str, **kwargs: Any):
        _ = input_str
        _ = kwargs
        self.tools_used.append(serialized.get("name", "unknown_tool"))
