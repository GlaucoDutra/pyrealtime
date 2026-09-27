# Architecture boundary

PyRealtime is the reusable application layer. A capability belongs here when it can serve more than one client without depending on a browser DOM, rendering engine, or device UI.

| PyRealtime library/API | Client frontend |
| --- | --- |
| Authentication and authorization | Login and connection controls |
| OpenAI credentials and session creation | WebRTC peer connection and media devices |
| Tool schemas, execution, and permission checks | Rendering and device-local tools, such as avatar animation |
| File validation, extraction, normalization, limits, and chunking | File picker, preview, upload progress, and Realtime event dispatch |
| Stable transport-neutral response models | Presentation and platform-specific state |
| Provider-neutral chat request/response and bounded tool loop | Conversation UI and local history persistence |

Host-owned extension contracts keep product policy out of the core:

- `HostHooks` supplies authorization and lifecycle observers.
- `RateLimiter` can replace the built-in process-local limiter in distributed deployments.
- `UsageSink` receives neutral usage events; pricing, quotas, and billing remain app-specific.
- `AttachmentStore` optionally persists prepared results.
- `VectorStoreResolver` maps an authenticated principal to allowed search stores.
- `ChatBackend` replaces the provider adapter without changing `/v1/chat`.

The reusable browser WebRTC/event implementation lives in the separate `@glaucodutra/pyrealtime-client` package. Its DOM and Three.js reference UI are not part of the Python library.

When adding a feature, put its reusable policy and processing in PyRealtime first. Keep only the platform adapter and interaction layer in the frontend. The server remains authoritative even when the frontend duplicates a cheap validation for immediate feedback.
