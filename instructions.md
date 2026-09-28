# Instructions for humans and coding agents

Before installing, integrating, or changing PyRealtime, read the canonical [complete usage guide](docs/LLM_USAGE.md). It is the machine-readable source of truth for installation, API contracts, guardrails, host hooks, examples, and optional capabilities.

Use [docs/QUICKSTARTS.md](docs/QUICKSTARTS.md) for short vanilla JavaScript, React, FastAPI, Django, and Flask integration recipes.

Also follow [ARCHITECTURE.md](ARCHITECTURE.md). Reusable, client-independent processing belongs in PyRealtime. Browser UI, microphone handling, WebRTC client behavior, rendering, and device-local actions belong in the client repository.

When public behavior changes, update `docs/LLM_USAGE.md`, the relevant example, and automated tests in the same change.

For releases and compatibility decisions, also follow [RELEASING.md](RELEASING.md), [CHANGELOG.md](CHANGELOG.md), and [DEPENDENCY_POLICY.md](DEPENDENCY_POLICY.md).

