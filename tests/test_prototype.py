import asyncio
import importlib

import pytest


@pytest.fixture()
def prototype(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("PYREALTIME_ALLOW_ANONYMOUS", "true")
    module = importlib.import_module("examples.prototype_server")
    module._notes.clear()
    return module


def test_calculate(prototype):
    principal = prototype.Principal(id="test-user")
    assert prototype.calculate({"operation": "multiply", "left": 6, "right": 7}, principal)["result"] == "42"


def test_notes_are_scoped_to_principal(prototype):
    alice = prototype.Principal(id="alice")
    bob = prototype.Principal(id="bob")

    asyncio.run(prototype.remember_note({"text": "Alice's note"}, alice))

    assert asyncio.run(prototype.list_notes({}, alice))["notes"] == ["Alice's note"]
    assert asyncio.run(prototype.list_notes({}, bob))["notes"] == []
