"""Minimal FastAPI proxy for a deployed A2A agent (Agent Runtime, agents-cli 1.1.0+).

The browser talks ONLY to this proxy (same origin, no CORS, no GCP creds in the
browser). The proxy authenticates with Application Default Credentials and
forwards chat to the deployed agent over the A2A protocol, returning replies as
structured parts the chat UI knows how to show:

  * {"kind": "text", "text": ...}  -> a normal chat bubble
  * {"kind": "a2ui", "data": ...}  -> one A2UI message (beginRendering /
    surfaceUpdate); static/index.html renders these as a card.

Why A2A: agents-cli 1.1.0 (GA) deploys ADK agents to Agent Runtime as A2A agents
and no longer registers the reasoning-engine operation schema the old
`agent_engines.get(...).stream_query()` path relied on (operation_schemas() comes
back empty). The container serves the A2A protocol over the Agent Engine HTTP
passthrough, so this proxy fetches the agent's card and sends messages with the
a2a-sdk client (the same path `agents-cli run --mode a2a` uses). This works for
both A2A and plain ADK 1.1.0 deployments (the container serves A2A either way).

Run:
  pip install -r requirements.txt
  export AGENT_ENGINE_RESOURCE_NAME="projects/.../locations/.../reasoningEngines/..."
  export AGENT_DIRECTORY="app"   # your agent's app directory (agents-cli-manifest.yaml)
  python main.py                 # -> http://localhost:8080
"""

import os
import uuid

import google.auth
import google.auth.transport.requests
import httpx
from a2a.client import ClientConfig, ClientFactory
from a2a.types import (
    AgentCard,
    FilePart,
    Message,
    Part,
    Role,
    TaskArtifactUpdateEvent,
    TextPart,
    TransportProtocol,
)
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

RESOURCE = os.environ.get(
    "AGENT_ENGINE_RESOURCE_NAME",
    "projects/841209747148/locations/us-east1/reasoningEngines/8832185590901374976",
)
# The agent's app directory (matches agent_directory in agents-cli-manifest.yaml).
AGENT_DIRECTORY = os.environ.get("AGENT_DIRECTORY", "app")
# Location is embedded in the resource name: projects/<p>/locations/<loc>/reasoningEngines/<id>.
LOCATION = RESOURCE.split("/locations/")[1].split("/")[0]

# A2A endpoint for an Agent Runtime deployment, via the Agent Engine HTTP
# passthrough. The card lives at the well-known path under this base.
A2A_BASE = (
    f"https://{LOCATION}-aiplatform.googleapis.com/reasoningEngines/v1/"
    f"{RESOURCE}/api/a2a/{AGENT_DIRECTORY}"
)
A2A_CARD_URL = f"{A2A_BASE}/.well-known/agent-card.json"

# The agent tags its A2UI data parts with this mime type.
_A2UI_MIME = "application/json+a2ui"

# One set of ADC credentials, refreshed per request (access tokens expire ~1h).
_creds, _ = google.auth.default(
    scopes=["https://www.googleapis.com/auth/cloud-platform"]
)


def _auth_headers() -> dict[str, str]:
    _creds.refresh(google.auth.transport.requests.Request())
    return {
        "Authorization": f"Bearer {_creds.token}",
        "Content-Type": "application/json",
    }


app = FastAPI()


@app.exception_handler(Exception)
async def _json_errors(request: Request, exc: Exception):
    # Always return JSON so the browser never receives a plain-text 500 page
    # (which shows up in the chat as "Unexpected token 'I', "Internal S"... is
    # not valid JSON"). Any server-side failure now surfaces as a readable
    # message in the chat bubble instead.
    return JSONResponse(
        status_code=200,
        content={
            "parts": [{"kind": "text", "text": f"Error: {type(exc).__name__}: {exc}"}]
        },
    )


# Reuse ONE A2A context per user so the agent remembers the conversation.
_contexts: dict[str, str] = {}
# Cache the agent card after the first fetch.
_card: AgentCard | None = None


async def _get_card(client: httpx.AsyncClient) -> AgentCard:
    global _card
    if _card is None:
        resp = await client.get(A2A_CARD_URL)
        resp.raise_for_status()
        card = AgentCard(**resp.json())
        # Agent Runtime does not serve a public card URL, so point the client at
        # the passthrough base for message sends.
        card.url = A2A_BASE
        _card = card
    return _card


def _extract_parts(parts: list) -> list[dict]:
    """Turn A2A response parts into structured parts for the chat UI.

    Text parts pass through as {"kind": "text"}. A2UI data parts (tagged
    application/json+a2ui) become {"kind": "a2ui", "data": <message>} so the UI
    renders the card; each data part is one A2UI message (beginRendering or
    surfaceUpdate).
    """
    out: list[dict] = []
    for p in parts:
        root = getattr(p, "root", p)
        if isinstance(root, TextPart) and getattr(root, "text", None):
            out.append({"kind": "text", "text": root.text})
        elif getattr(root, "data", None) is not None:
            raw_data = root.data
            meta = getattr(root, "metadata", None) or {}
            mime = meta.get("mimeType") if isinstance(meta, dict) else None
            # Check if raw_data is an envelope: {'kind': 'data', 'metadata': {'mimeType': ...}, 'data': {...}}
            if isinstance(raw_data, dict) and "data" in raw_data and "metadata" in raw_data:
                inner_meta = raw_data.get("metadata") or {}
                mime = inner_meta.get("mimeType") or mime
                raw_data = raw_data.get("data")
            if mime == _A2UI_MIME:
                out.append({"kind": "a2ui", "data": raw_data})
            elif isinstance(raw_data, dict) and any(k in raw_data for k in ("beginRendering", "surfaceUpdate", "dataModelUpdate")):
                out.append({"kind": "a2ui", "data": raw_data})
        elif isinstance(root, FilePart):
            uri = getattr(getattr(root, "file", None), "uri", None)
            if uri:
                out.append({"kind": "text", "text": uri})
    return out


@app.post("/chat")
async def chat(req: Request):
    body = await req.json()
    message = body.get("message", "")
    user_id = body.get("user_id") or "web-user"
    parts: list[dict] = []

    async with httpx.AsyncClient(headers=_auth_headers(), timeout=120) as client:
        card = await _get_card(client)
        factory = ClientFactory(
            ClientConfig(
                supported_transports=[
                    TransportProtocol.jsonrpc,
                    TransportProtocol.http_json,
                ],
                httpx_client=client,
            )
        )
        a2a_client = factory.create(card)

        msg = Message(
            message_id=str(uuid.uuid4()),
            role=Role.user,
            parts=[Part(root=TextPart(text=message))],
            context_id=_contexts.get(user_id),
        )

        last_task = None
        got_artifact_update = False
        async for event in a2a_client.send_message(msg):
            if not isinstance(event, tuple):
                continue
            task, update = event
            if task is not None:
                last_task = task
                if getattr(task, "context_id", None):
                    _contexts[user_id] = task.context_id
            if isinstance(update, TaskArtifactUpdateEvent):
                got_artifact_update = True
                parts.extend(_extract_parts(update.artifact.parts))

        # Non-streaming fallback: pull parts from the final task's artifacts.
        if not got_artifact_update and last_task is not None:
            for artifact in getattr(last_task, "artifacts", None) or []:
                parts.extend(_extract_parts(artifact.parts))

    if not parts:
        # The turn produced no text or UI (e.g. the agent only ran tools, or a
        # tool stalled). Be honest rather than silent.
        parts = [{"kind": "text", "text": "(The agent didn't return a reply.)"}]
    return JSONResponse({"parts": parts})


@app.get("/api/viewpoints")
async def get_viewpoints():
    """Provides viewpoint markers with coordinates and elevations for the interactive map."""
    project_id = "qwiklabs-gcp-04-d19134fd9a80"
    viewpoints = []

    try:
        from google.cloud import firestore

        db = firestore.Client(project=project_id)
        docs = db.collection("viewpoints").stream()
        for doc in docs:
            data = doc.to_dict()
            doc_id = doc.id
            lat = data.get("latitude")
            lng = data.get("longitude")

            # Fallback default coordinates if not set on the doc
            if lat is None or lng is None:
                coord_map = {
                    "mount-tamalpais-east-peak": (37.9235, -122.5965),
                    "hawk-hill-marin-headlands": (37.8282, -122.4996),
                    "twin-peaks-san-francisco": (37.7544, -122.4477),
                    "pacifica-sweeney-ridge": (37.6083, -122.4497),
                }
                lat, lng = coord_map.get(doc_id, (37.7749, -122.4194))

            opt_min = data.get("optimal_inversion_min_ft")
            opt_max = data.get("optimal_inversion_max_ft")
            opt_range = f"{opt_min:,}ft - {opt_max:,}ft" if opt_min and opt_max else "Varies"

            viewpoints.append({
                "id": doc_id,
                "name": data.get("name", doc_id),
                "lat": float(lat),
                "lng": float(lng),
                "elevation_ft": data.get("elevation_ft", 0),
                "optimal_range": opt_range,
                "region": data.get("region", "California"),
                "rating": data.get("fog_wave_rating", "Recommended"),
                "desc": data.get("description", ""),
            })
    except Exception as exc:
        print(f"Error loading viewpoints from Firestore: {exc}")

    if not viewpoints:
        viewpoints = [
            {
                "id": "mount-tamalpais-east-peak",
                "name": "Mount Tamalpais - East Peak & Ridgecrest",
                "lat": 37.9235,
                "lng": -122.5965,
                "elevation_ft": 2571,
                "optimal_range": "1,200ft - 2,200ft",
                "region": "Marin County",
                "rating": "World Class",
                "desc": "Famous for cascading fog waterfalls over Ridgecrest Blvd into the Pacific.",
            },
            {
                "id": "hawk-hill-marin-headlands",
                "name": "Hawk Hill - Marin Headlands",
                "lat": 37.8282,
                "lng": -122.4996,
                "elevation_ft": 920,
                "optimal_range": "500ft - 900ft",
                "region": "Marin County",
                "rating": "Iconic",
                "desc": "Golden Gate Bridge spires emerging from swirling marine layer.",
            },
            {
                "id": "twin-peaks-san-francisco",
                "name": "Twin Peaks (Christmas Tree Point)",
                "lat": 37.7544,
                "lng": -122.4477,
                "elevation_ft": 922,
                "optimal_range": "400ft - 800ft",
                "region": "San Francisco",
                "rating": "High",
                "desc": "Fog pouring over the crest toward downtown SF skyline.",
            },
            {
                "id": "pacifica-sweeney-ridge",
                "name": "Sweeney Ridge Trailhead",
                "lat": 37.6083,
                "lng": -122.4497,
                "elevation_ft": 1200,
                "optimal_range": "600ft - 1,100ft",
                "region": "Pacifica / San Mateo",
                "rating": "High",
                "desc": "High coastal ridge where Spanish explorers first sighted SF Bay; dramatic ocean fog cascades.",
            },
        ]
    return JSONResponse({"viewpoints": viewpoints})


# Serve the chat UI (keep this mount last so /chat wins).
app.mount("/", StaticFiles(directory="static", html=True), name="static")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
