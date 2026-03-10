"""Callback handler used by API requests to collect run metadata and LLM usage."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from langchain_core.callbacks.base import AsyncCallbackHandler
from langchain_core.outputs import LLMResult


class APICallbackHandler(AsyncCallbackHandler):
    def __init__(self):
        super().__init__()
        self.tools_used: List[str] = []
        self.root_run_id: Optional[str] = None
        self.model_id: str = ""
        self.input_tokens: int = 0
        self.output_tokens: int = 0
        self.cache_read_tokens: int = 0
        self.cache_creation_tokens: int = 0

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
        _ = prompts
        self._record_run_id(**kwargs)
        if not self.model_id:
            self.model_id = (
                serialized.get("kwargs", {}).get("model_id", "")
                or serialized.get("kwargs", {}).get("model", "")
                or ""
            )

    async def on_llm_end(self, response: LLMResult, **kwargs: Any) -> None:
        _ = kwargs
        for gen_list in response.generations:
            for gen in gen_list:
                msg = getattr(gen, "message", None)
                if msg is None:
                    continue
                meta: dict = getattr(msg, "usage_metadata", None) or {}
                self.input_tokens += meta.get("input_tokens", 0)
                self.output_tokens += meta.get("output_tokens", 0)
                self.cache_read_tokens += meta.get("cache_read_input_tokens", 0)
                self.cache_creation_tokens += meta.get("cache_creation_input_tokens", 0)
                # Capture model id from response if not yet set
                if not self.model_id:
                    info: dict = getattr(gen, "generation_info", None) or {}
                    self.model_id = info.get("model_id", "") or ""

    async def on_tool_start(self, serialized: Dict[str, Any], input_str: str, **kwargs: Any):
        _ = input_str
        _ = kwargs
        self.tools_used.append(serialized.get("name", "unknown_tool"))
