# Compatibility and dependency policy

- Supported Python versions: 3.10 through 3.13. Every pull request runs the full suite on each version.
- Releases use Semantic Versioning. Public symbols documented in `docs/LLM_USAGE.md` are stable within a major version.
- OpenAI API payloads may gain additive fields in minor releases. Breaking route, callback, or model changes require a major release.
- Direct runtime dependencies use bounded major versions. Dependabot proposes updates weekly; CI and integration tests gate merges.
- Security updates may be released outside the normal cadence. Applications should pin a PyRealtime release, while allowing patch updates of its transitive dependencies through a lock file.
- Pydantic is a core dependency because the provider-neutral chat schemas are public package models. Optional extras isolate FastAPI/Uvicorn, file parsers, and JWT cryptography.
