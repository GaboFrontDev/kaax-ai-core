"""Example tool: echo text."""

from __future__ import annotations

from langchain_core.tools import tool
from pydantic import BaseModel, Field


class EchoInput():
    text: str = Field(..., description="Text to echo back to the user")


# @tool(args_schema=EchoInput)
def echo_tool(text: str) -> str:
    """Return the same text received from the user."""
    return text
