"""File-based prompt loader for the minimal core module."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Dict, Optional

import yaml
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class PromptSchema(BaseModel):
    version: str = Field(pattern=r"^\d+\.\d+\.\d+$")
    prompt: str = Field(min_length=1)


class PromptFactory:
    def __init__(self, prompts_dir: Optional[str] = None):
        self._prompt_cache: Dict[str, str] = {}
        self._prompts_dir = Path(prompts_dir) if prompts_dir else None

    def _get_prompts_dir(self) -> Path:
        if self._prompts_dir:
            return self._prompts_dir
        return Path(__file__).resolve().parent / "prompts"

    def load_prompt(self, name: str) -> str:
        if name in self._prompt_cache:
            return self._prompt_cache[name]

        if not name or not isinstance(name, str):
            raise ValueError("Prompt name must be a non-empty string")

        safe_name = Path(name).name
        if safe_name != name:
            raise ValueError(f"Invalid prompt name '{name}': must be a simple filename")

        prompt_path = self._get_prompts_dir() / f"{safe_name}.yaml"

        if not prompt_path.exists():
            available = sorted([f.stem for f in self._get_prompts_dir().glob("*.yaml")])
            available_text = ", ".join(available) if available else "none"
            raise ValueError(
                f"Prompt '{name}' not found. Available prompts: {available_text}"
            )

        try:
            with prompt_path.open("r", encoding="utf-8") as prompt_file:
                yaml_data = yaml.safe_load(prompt_file)
            model = PromptSchema.model_validate(yaml_data)
            self._prompt_cache[name] = model.prompt
            return model.prompt
        except Exception as exc:  # pylint: disable=broad-except
            logger.error("Failed to load prompt '%s': %s", name, exc)
            raise ValueError(f"Failed to load prompt '{name}': {exc}") from exc
