# PyRealtime copy-paste integrations

These examples use released artifacts and the stable PyRealtime HTTP contract. Keep OpenAI keys on the Python server. Browser examples receive only a user token issued by the host application.

## Vanilla JavaScript: chat over HTTP

This needs no SDK or bundler:

```html
<form id="chat"><input id="message"><button>Send</button></form>
<pre id="answer"></pre>
<script type="module">
  const apiUrl = "http://127.0.0.1:8000/ai";
  const accessToken = "local-development-token"; // Replace with the signed-in user's token.
  const history = [];

  document.querySelector("#chat").addEventListener("submit", async (event) => {
    event.preventDefault();
    const message = document.querySelector("#message").value;
    const response = await fetch(`${apiUrl}/v1/chat`, {
      method: "POST",
      headers: { "Authorization": `Bearer ${accessToken}`, "Content-Type": "application/json" },
      body: JSON.stringify({ message, history }),
    });
    const body = await response.json();
    if (!response.ok) throw new Error(`${body.error?.code ?? "request_failed"}: ${body.error?.message ?? "Unknown error"}`);
    history.push({ role: "user", content: message }, body.message);
    document.querySelector("#answer").textContent = body.message.content;
  });
</script>
```

The backend bounds history, but the client should also keep only the recent messages it needs.

## Vanilla JavaScript with Vite: Realtime client

The browser client is released as an immutable GitHub tarball. npm registry publication is pending.

```bash
npm install --save-exact https://github.com/GlaucoDutra/pyrealtime-web/releases/download/v0.2.0/glaucodutra-pyrealtime-client-0.2.0.tgz
```

```js
import { BackendClient, RealtimeClient, ToolRouter } from "@glaucodutra/pyrealtime-client";

const backend = new BackendClient({
  apiUrl: "http://127.0.0.1:8000/ai",
  accessToken: "user-token-from-your-login",
});
const realtime = new RealtimeClient(backend, new ToolRouter(backend), {
  onTranscript: (role, text, final) => {
    if (final) console.log(role, text);
  },
});

await realtime.connect({ useMicrophone: false }); // Does not request microphone permission.
realtime.sendText("Hello");
```

Use `connect({ useMicrophone: true, microphoneDeviceId })` only after a user gesture when voice is wanted.

## React: small Realtime component

Install the same pinned browser-client tarball, then:

```tsx
import { useEffect, useRef, useState } from "react";
import { BackendClient, RealtimeClient, ToolRouter } from "@glaucodutra/pyrealtime-client";

export function PyRealtimeChat({ apiUrl, token }: { apiUrl: string; token: string }) {
  const client = useRef<RealtimeClient | null>(null);
  const [lines, setLines] = useState<string[]>([]);

  useEffect(() => () => { void client.current?.disconnect(); }, []);

  async function connect() {
    const backend = new BackendClient({ apiUrl, accessToken: token });
    client.current = new RealtimeClient(backend, new ToolRouter(backend), {
      onTranscript: (role, text, final) => final && setLines(value => [...value, `${role}: ${text}`]),
    });
    await client.current.connect({ useMicrophone: false });
  }

  return <>
    <button onClick={connect}>Connect text chat</button>
    <button onClick={() => client.current?.sendText("Hello")}>Send hello</button>
    <pre>{lines.join("\n")}</pre>
  </>;
}
```

The component receives a user token; never put `OPENAI_API_KEY` or a production shared application key in React environment variables.

## FastAPI: mount in the existing app

```python
from fastapi import FastAPI, HTTPException, Request
from pyrealtime import HostHooks, Principal, ServerSettings, ToolRegistry
from pyrealtime.api import mount_py_realtime

app = FastAPI()
tools = ToolRegistry()

async def authenticate(request: Request) -> Principal:
    user = await sessions.verify(request.headers.get("authorization", ""))
    if user is None:
        raise HTTPException(401, "Invalid session")
    return Principal(id=str(user.id), claims={"roles": user.roles})

async def authorize(principal, action):
    return action.action != "tool.execute" or action.resource in principal.claims.get("allowed_tools", [])

mount_py_realtime(app, ServerSettings.from_env(), path="/ai", tools=tools,
                  authenticate=authenticate, host=HostHooks(authorize=authorize))
```

## Django ASGI: compose both applications

Create `ai_asgi.py` next to the Django ASGI module:

```python
from starlette.applications import Starlette
from starlette.routing import Mount
from myproject.asgi import application as django_app
from pyrealtime import ServerSettings, ToolRegistry
from pyrealtime.api import create_app

ai_app = create_app(ServerSettings.from_env(), tools=ToolRegistry(), authenticate=verify_request)
application = Starlette(routes=[Mount("/ai", ai_app), Mount("/", django_app)])
```

Point the ASGI server at `ai_asgi:application`. `verify_request` should validate the same session/JWT used by Django and return a PyRealtime `Principal`.

## Flask/WSGI: run the API as a sidecar

Keep Flask unchanged and run PyRealtime as a separate ASGI process:

```python
# ai_api.py
from pyrealtime import ServerSettings, ToolRegistry
from pyrealtime.api import create_app

app = create_app(ServerSettings.from_env(), tools=ToolRegistry(), authenticate=verify_flask_token)
```

```bash
uvicorn ai_api:app --host 127.0.0.1 --port 8001
```

Route `/ai/*` to port 8001 at the reverse proxy and strip the `/ai` prefix. This avoids unsafe in-process ASGI/WSGI lifecycle mixing. The host authentication callback can validate the same signed token used by Flask.

## Before production

- Replace `APP_API_KEY` with per-user authentication.
- Authorize every sensitive tool against the authenticated `Principal`.
- Configure exact HTTPS CORS origins.
- Inject a shared `RateLimiter` for multiple processes.
- Run `pyrealtime doctor --api-url https://your-api.example/ai --origin https://your-app.example`.
