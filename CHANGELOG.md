# Changelog

All notable changes follow [Keep a Changelog](https://keepachangelog.com/) and Semantic Versioning.

## [0.3.0] - 2026-09-28

### Added

- `pyrealtime init` safe starter generator with auth, `HostHooks`, a tool, pinned dependencies, and `.env.example`.
- `pyrealtime doctor` for Python, dependency, configuration, API, OpenAI model-access, and CORS checks without displaying secrets.
- Explicit `DemoChatBackend`, `create_demo_app`, and `pyrealtime demo` no-key path with Realtime disabled.
- Copy-paste vanilla JavaScript, React, FastAPI, Django, and Flask integration guides using released artifacts and stable API contracts.
- `AppClient.chat()` for typed Python consumption of the provider-neutral chat contract.

## [0.2.1] - 2026-09-27

### Added

- Provider-neutral `POST /v1/chat` request, response, tool-call, usage, and error schemas.
- Bounded OpenAI Responses adapter with application-tool authorization, timeouts, result limits, and tool-round limits.
- `mount_py_realtime` for existing ASGI/FastAPI hosts.
- Wheel-installed `pyrealtime-example` with local shared-key and production JWKS authentication paths.
- Clean-wheel consumer checks on Python 3.10–3.13 covering health, auth, chat, tools, errors, and limits.

### Changed

- Default Realtime gateway calls no longer require child-ASGI lifespan propagation when mounted.
- README and canonical usage documentation now define the drop-in contract and identify GitHub artifacts as the supported installation path while PyPI is pending.
- Direct tool execution now enforces the configured tool timeout.

## [0.2.0] - 2026-09-27

### Added

- Configurable session, tool-call, and file-preparation rate limits and body-size limits.
- Request IDs, safe structured JSON access logs, typed authorization/lifecycle hooks, and usage sinks.
- Shared-secret and JWKS JWT authentication adapters.
- Optional attachment persistence and per-principal vector-store resolution contracts.
- A second JWT-authenticated host example and portability integration tests.
- Python 3.10–3.13 CI, wheel/sdist validation, and tag-driven GitHub/PyPI release automation.

### Changed

- Distribution name is now `pyrealtime-ai`; the Python import remains `pyrealtime`.

## [0.1.0] - 2026-09-23

- Initial source-checkout prototype.

[0.2.0]: https://github.com/GlaucoDutra/pyrealtime/releases/tag/v0.2.0
[0.3.0]: https://github.com/GlaucoDutra/pyrealtime/releases/tag/v0.3.0
[0.2.1]: https://github.com/GlaucoDutra/pyrealtime/releases/tag/v0.2.1
[0.1.0]: https://github.com/GlaucoDutra/pyrealtime/tree/e63dc8d
