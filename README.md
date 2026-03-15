# MiniRTC

A one-to-one (1:1) calling product: create or join a room by URL, then start an audio/video call with one other person. Media is peer-to-peer via WebRTC; the backend handles only signaling and room presence.

## What's in this repo

- **Backend** (Python / FastAPI) -- signaling server with room creation/join, WebSocket signaling (PeerJS-compatible), presence, heartbeat, and reconnect handling. State is in-memory; no database required.
- **Frontend** (SolidJS / Vite) -- create or join a room, PeerJS-based call UI with join/leave, mute/unmute, connection status, and error handling.

## Run locally

### Backend

```bash
cd backend
python -m venv .venv
source .venv/bin/activate   # or .venv\Scripts\activate on Windows
pip install -r requirements.txt
python run.py
```

Server starts at `http://localhost:9000`.

| Endpoint | Description |
|----------|-------------|
| `GET /health` | Health check |
| `POST /rooms` | Create a room (returns `room_id`) |
| `GET /rooms/{room_id}/join` | Join a room (returns `peer_id`, `client_id`) |
| `GET /rooms/{room_id}/peers` | List peers in a room |
| `WS /peerjs?id={peer_id}` | Signaling WebSocket |

### Frontend

Requires Node 20+.

```bash
cd frontend
npm install
npm run dev
```

Open `http://localhost:3000`. Create a room, then open the room URL in a second tab or device. Click "Join call" in both tabs to start the call.
Open `http://localhost:3000/dashboard` for the live room/event dashboard.

Set `VITE_API_URL` if the backend is hosted elsewhere (e.g. `VITE_API_URL=https://my-backend.example.com`).

### Tests

```bash
cd backend
source .venv/bin/activate
pytest -v
```

```bash
cd frontend
npm run test:run
```

Backend + frontend tests cover:
- **Registry unit tests** -- room lifecycle, join/reconnect logic, peer state management
- **HTTP endpoint tests** -- room CRUD, error cases (full, not found, invalid ID)
- **WebSocket integration tests** -- signaling open, presence events, offer/answer forwarding
- **Frontend behavior tests** -- lobby validation and room creation flow

### Docker Compose

```bash
docker compose up --build
```

This starts backend on `http://localhost:9000` and frontend on `http://localhost:3000`.

## Architecture

```
┌─────────────┐          REST + WebSocket          ┌─────────────┐
│  Browser A  │◄──────────────────────────────────►│   FastAPI   │
│  (PeerJS)   │          /rooms, /peerjs           │  Signaling  │
└──────┬──────┘                                    │   Server    │
       │                                           └──────┬──────┘
       │         P2P media (DTLS-SRTP over ICE)           │
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

## Deploy

- Deployment guide and platform config files are in `DEPLOY.md`.

## What was skipped

- **Database** -- rooms and peers are in-memory only (single instance).
- **TURN server** -- relies on STUN for NAT traversal. Works for most networks; symmetric NAT needs TURN (see [DECISIONS.md](DECISIONS.md)).
- **Authentication** -- room IDs are unguessable UUIDs. No user accounts.
- **Recording / group calls / chat** -- out of scope for 1:1 MVP.

See [DECISIONS.md](DECISIONS.md) for tradeoffs, scaling analysis, and a deeper look at the technologies involved.
