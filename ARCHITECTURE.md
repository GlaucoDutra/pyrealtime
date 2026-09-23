# Architecture boundary

PyRealtime is the reusable application layer. A capability belongs here when it can serve more than one client without depending on a browser DOM, rendering engine, or device UI.

| PyRealtime library/API | Client frontend |
| --- | --- |
| Authentication and authorization | Login and connection controls |
| OpenAI credentials and session creation | WebRTC peer connection and media devices |
| Tool schemas, execution, and permission checks | Rendering and device-local tools, such as avatar animation |
| File validation, extraction, normalization, limits, and chunking | File picker, preview, upload progress, and Realtime event dispatch |
| Stable transport-neutral response models | Presentation and platform-specific state |

When adding a feature, put its reusable policy and processing in PyRealtime first. Keep only the platform adapter and interaction layer in the frontend. The server remains authoritative even when the frontend duplicates a cheap validation for immediate feedback.
