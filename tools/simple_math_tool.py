"""Example tool: basic arithmetic operations."""

from __future__ import annotations

from typing import Literal

from langchain_core.tools import tool
from pydantic import BaseModel, Field


class SimpleMathInput(BaseModel):
    a: float = Field(..., description="First numeric operand")
    b: float = Field(..., description="Second numeric operand")
    operation: Literal["add", "subtract", "multiply", "divide"] = Field(
        default="add",
        description="Arithmetic operation to execute",
    )


@tool(args_schema=SimpleMathInput)
def simple_math_tool(a: float, b: float, operation: str = "add") -> dict:
    """Perform a basic arithmetic operation and return the result."""
    if operation == "add":
        result = a + b
    elif operation == "subtract":
        result = a - b
    elif operation == "multiply":
        result = a * b
    elif operation == "divide":
        if b == 0:
            return {"error": "Cannot divide by zero."}
        result = a / b
    else:
        return {"error": f"Unsupported operation: {operation}"}

    return {"operation": operation, "a": a, "b": b, "result": result}
