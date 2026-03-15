# MiniRTC Arena.ai Interview

A one-to-one (1:1) calling demo app: create or join a room by URL, then start an audio/video call with one other person. Media is peer-to-peer via WebRTC; the backend handles only signaling and room presence.

## What's in this repo

- **Backend** (Python / FastAPI) -- signaling server with room creation/join, WebSocket signaling (PeerJS-compatible), presence, heartbeat, and reconnect handling. State is in-memory; no database required.
- **Frontend** (SolidJS / Vite) -- create or join a room, PeerJS-based call UI with join/leave, mute/unmute, connection status, and error handling.

# Preview

You can view a preview [here](https://arena-ai-tws.netlify.app/).  
Password: `jobinterview`.
I deployed the backend to Railway and the frontend to Netlify.

## Run locally

### Backend

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
make serve
```

Server starts at `http://localhost:9000`.

| Endpoint                     | Description                                  |
| ---------------------------- | -------------------------------------------- |
| `GET /health`                | Health check                                 |
| `POST /rooms`                | Create a room (returns `room_id`)            |
| `GET /rooms/{room_id}/join`  | Join a room (returns `peer_id`, `client_id`) |
| `GET /rooms/{room_id}/peers` | List peers in a room                         |
| `WS /peerjs?id={peer_id}`    | Signaling WebSocket                          |

### Frontend

NOTE: Requires Node 20+.
IMPORTANT: update `netlify.toml` to proxy API requests to localhost.

```bash
cd frontend
npm install
netlify dev
```

Open `http://localhost:3000`. Create a room, then open the room URL in a second tab or device. Click "Join call" in both tabs to start the call.
Open `http://localhost:3000/dashboard` for the live room/event dashboard.

### Tests

```bash
cd backend
source .venv/bin/activate
pytest -v        # or: make test
```

```bash
cd frontend
npm run test:run
```

### Backend Makefile

A `Makefile` lives in `backend/` with shortcuts for common tasks (run from `backend/`):

| Target           | Description                 |
| ---------------- | --------------------------- |
| `make install`   | Install Python dependencies |
| `make lint`      | Run ruff linter             |
| `make format`    | Run ruff formatter          |
| `make typecheck` | Run mypy                    |
| `make check`     | lint + typecheck            |
| `make test`      | Run pytest                  |

## Architecture

```
┌─────────────┐          REST + WebSocket          ┌─────────────┐
│  Browser A  │◄──────────────────────────────────►│   FastAPI   │
│  (PeerJS)   │          /rooms, /peerjs           │  Signaling  │
└──────┬──────┘                                    │   Server    │
       │                                           └──────┬──────┘
       │         P2P media (DTLS-SRTP over ICE)    |      │
       │◄───────────────────────────────────-─────►│      │
       │                                           │      │
┌──────┴──────┐          REST + WebSocket          │      │
│  Browser B  │◄───────────────────────────────────┘      │
│  (PeerJS)   │          /rooms, /peerjs                  │
└─────────────┘                                           │
                                                     In-memory
                                                     Registry
```

The signaling server is stateless from a compute perspective -- it routes JSON messages between WebSocket connections. All audio/video flows directly between browsers (or via a TURN relay, which is separate infrastructure).

## What was skipped

- **Database** -- rooms and peers are in-memory only (single instance).
- **Authentication** -- room IDs are unguessable UUIDs. No user accounts.
- **Recording / group calls / chat** -- out of scope for 1:1 MVP.

See [DECISIONS.md](DECISIONS.md) for tradeoffs, scaling analysis, and a deeper look at the technologies involved.
See [TIMELINE.md](TIMELINE.md) for an outline of how I spent my time while working on this.
