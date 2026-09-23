"""Local PyRealtime prototype with a few safe demonstration tools.

Run only on localhost. The companion frontend launcher enables anonymous access
for a zero-friction local demo; production applications should authenticate users.
"""

from __future__ import annotations

import asyncio
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from pyrealtime import Principal, ServerSettings, ToolRegistry
from pyrealtime.api import create_app

settings = ServerSettings.from_env()
tools = ToolRegistry()
_notes: dict[str, list[str]] = {}
_notes_lock = asyncio.Lock()


@tools.tool(
    name="get_local_time",
    description="Get the current date, time, and timezone from the application server.",
    parameters={"type": "object", "properties": {}, "additionalProperties": False},
)
def get_local_time(_: dict[str, Any], principal: Principal) -> dict[str, Any]:
    now = datetime.now().astimezone()
    return {
        "ok": True,
        "iso_datetime": now.isoformat(timespec="seconds"),
        "timezone": str(now.tzinfo),
        "principal_id": principal.id,
    }


@tools.tool(
    name="calculate",
    description="Perform an exact two-number calculation using add, subtract, multiply, or divide.",
    parameters={
        "type": "object",
        "properties": {
            "operation": {"type": "string", "enum": ["add", "subtract", "multiply", "divide"]},
            "left": {"type": "number"},
            "right": {"type": "number"},
        },
        "required": ["operation", "left", "right"],
        "additionalProperties": False,
    },
)
def calculate(arguments: dict[str, Any], _: Principal) -> dict[str, Any]:
    operation = str(arguments.get("operation", ""))
    try:
        left = Decimal(str(arguments["left"]))
        right = Decimal(str(arguments["right"]))
    except (KeyError, InvalidOperation) as exc:
        raise ValueError("left and right must be valid numbers") from exc

    if operation == "add":
        result = left + right
    elif operation == "subtract":
        result = left - right
    elif operation == "multiply":
        result = left * right
    elif operation == "divide":
        if right == 0:
            raise ValueError("Cannot divide by zero")
        result = left / right
    else:
        raise ValueError("Unsupported operation")
    return {"ok": True, "operation": operation, "result": str(result)}


@tools.tool(
    name="remember_note",
    description="Remember a short note for the current prototype session.",
    parameters={
        "type": "object",
        "properties": {"text": {"type": "string", "minLength": 1, "maxLength": 500}},
        "required": ["text"],
        "additionalProperties": False,
    },
)
async def remember_note(arguments: dict[str, Any], principal: Principal) -> dict[str, Any]:
    text = str(arguments.get("text", "")).strip()
    if not text:
        raise ValueError("Note text cannot be empty")
    if len(text) > 500:
        raise ValueError("Note text cannot exceed 500 characters")
    async with _notes_lock:
        notes = _notes.setdefault(principal.id, [])
        notes.append(text)
        del notes[:-50]
        return {"ok": True, "saved": text, "note_count": len(notes)}


@tools.tool(
    name="list_notes",
    description="List notes remembered during the current prototype session.",
    parameters={"type": "object", "properties": {}, "additionalProperties": False},
)
async def list_notes(_: dict[str, Any], principal: Principal) -> dict[str, Any]:
    async with _notes_lock:
        notes = list(_notes.get(principal.id, []))
    return {"ok": True, "count": len(notes), "notes": notes}


app = create_app(settings, tools=tools)
