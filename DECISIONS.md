# Decisions

## Transport choice: WebSocket + REST

Signaling for WebRTC needs a way to relay short-lived messages (offer, answer, ICE candidates) between two browsers that don't yet have a direct connection. The three realistic options:

| Transport | Latency | Bidirectional | Connection cost | Complexity |
|-----------|---------|---------------|-----------------|------------|
| WebSocket | Low | Yes | 1 TCP conn/peer | Low |
| SSE + POST | Low | Simulated (two channels) | 1 SSE + N POSTs | Medium |
| Long-polling | Variable | Simulated | Repeated HTTP | High |

WebSocket wins because signaling is inherently bidirectional (server sends ICE candidates to client *and* client sends them to server), low-latency matters during call setup, and a single persistent connection doubles as a heartbeat/presence channel. SSE could work but forces the client into a split-brain model (one channel for reads, POST for writes) with no real upside. Long-polling adds latency and complexity for no benefit.

REST handles room creation, join, and peer listing -- operations that are request/response shaped and benefit from HTTP semantics (status codes, caching headers, easy curl debugging).

## Why PeerJS compatibility

PeerJS is a thin wrapper around the browser's `RTCPeerConnection` API. It abstracts ICE handling, offer/answer exchange, and media stream management into a simple `peer.call(remotePeerId, stream)` API.

The alternative was to write raw WebRTC signaling from scratch: manually creating `RTCPeerConnection`, handling `onicecandidate`, exchanging SDP via custom messages, managing ICE restart, etc. That's a lot of boilerplate with no added value for a 1:1 product. PeerJS buys us a working call in ~30 lines of client code.

The cost is that PeerJS expects a specific signaling protocol (OPEN, HEARTBEAT, OFFER, ANSWER, CANDIDATE message types with `src`/`dst` fields). Our backend implements only the subset needed for 1:1 -- about 80 lines of WebSocket handler code. If we needed SFU (selective forwarding unit) for group calls, PeerJS wouldn't be the right choice, but for 1:1 it's a good tradeoff.

## Architecture

```
Browser A                    Backend                     Browser B
   |                           |                            |
   |-- POST /rooms ----------->|                            |
   |<-- { room_id } ---------- |                            |
   |                           |                            |
   |-- GET /rooms/{id}/join -->|                            |
   |<-- { peer_id, ... } ------|                            |
   |                           |                            |
   |== WebSocket /peerjs =====>|<==== WebSocket /peerjs ====|
   |<-- OPEN -----------------|                            |
   |                           |-- OPEN ------------------>|
   |                           |                            |
   |-- OFFER { dst: B } ----->|-- OFFER { src: A } ------>|
   |<-- ANSWER { src: B } ----|<-- ANSWER { dst: A } -----|
   |<-- CANDIDATE ------------|<-- CANDIDATE -------------|
   |                           |                            |
   |========= P2P media (DTLS-SRTP over ICE) =============|
```

Media never touches the signaling server. After the WebRTC connection is established, audio/video flows directly between browsers (or through a TURN relay if needed -- see below).

## What breaks at 10k rooms/day

### The math

10k rooms/day with 2 peers each = 20k join operations/day. If average call duration is 10 minutes, peak concurrent rooms (assuming uniform distribution across 8 working hours) is roughly `10,000 / (8 * 60 / 10) ≈ 208` concurrent rooms, so ~416 concurrent WebSocket connections.

This is trivially handled by a single process. A Python asyncio process can manage tens of thousands of concurrent WebSocket connections with minimal CPU (signaling messages are tiny JSON payloads, ~200 bytes each, exchanged a handful of times per call setup).

### What actually breaks

**State durability.** The in-memory registry means a deploy or crash wipes all active rooms. Every connected user would need to rejoin. At 208 concurrent rooms, this disrupts ~400 people mid-call. Fix: persist room/peer state in Redis. The registry interface already abstracts this -- swap the dict-based implementation for Redis-backed calls.

**Horizontal scaling.** Two instances have separate memory. If peer A hits instance 1 and peer B hits instance 2, signaling messages can't be forwarded. There are two broad approaches: a pub/sub layer (Redis pub/sub, NATS) so any instance can relay to any other, or deterministic routing so both peers in a room always land on the same instance. At scale, deterministic routing via a consistent hash ring is the stronger choice -- see below.

### Thought Exercise: Scaling to 1M concurrent rooms with a hash ring

At 1M concurrent rooms with 2 peers each, we have 2M WebSocket connections. A single Python asyncio process can comfortably hold ~50k idle WebSocket connections (signaling is bursty -- a few messages at call setup, then near-silence). That puts us at roughly **40 nodes** to serve the full load.

The routing layer (a lightweight reverse proxy or the load balancer itself) hashes `room_id` to a position on a consistent hash ring and forwards both the REST join and the WebSocket upgrade to the node that owns that segment. Both peers in a room always hit the same process, so signaling stays node-local -- no cross-node message bus, no shared state.

```
         ┌─────────┐
         │  Client  │
         └────┬─────┘
              │  room_id
         ┌────▼─────┐
         │  Router   │  hash(room_id) → ring position → node
         └────┬─────┘
     ┌────────┼────────┐
     ▼        ▼        ▼
  Node A   Node B   Node C ...
  (rooms    (rooms    (rooms
   0-99)   100-199)  200-299)
```

**Why a hash ring instead of plain mod-N hashing.** With `hash(room_id) % N`, adding or removing a node remaps nearly every room. A consistent hash ring remaps only ~1/N of rooms when the ring changes. At 1M rooms across 40 nodes, scaling to 41 nodes displaces ~25k rooms (~2.5%) instead of rehashing all of them.

**Virtual nodes** prevent hotspots. Each physical node gets multiple positions on the ring (e.g. 150 vnodes per node), which smooths out the distribution. Without vnodes, hash clustering can leave one node with 3x the load of another.

**Benefits at scale:**

- **No shared state.** Each node owns its rooms entirely in-process. No Redis, no pub/sub, no distributed locking. This eliminates an entire failure domain and keeps per-message latency at microseconds instead of the milliseconds a Redis round-trip would add.
- **Linear cost scaling.** Need 2x capacity? Add nodes. Cost grows linearly with rooms, not quadratically (which is what happens with a full-mesh pub/sub where every node must be able to reach every other node).
- **Isolated blast radius.** A node crash only affects ~1/N of rooms. Clients on the failed node reconnect; the router hashes them to the new ring owner. The reconnect grace period already built into the registry gives the client a window to re-establish the WebSocket without losing their room slot.
- **Graceful deploys.** Drain a node by removing it from the ring. Its ~1/N rooms get redistributed. Clients reconnect automatically. Rolling deploys touch one node at a time with minimal user disruption.

**What you'd still need beyond the ring:**

- A **service registry** (Consul, etcd, or even DNS) so the router knows which nodes are alive and where they sit on the ring.
- A **room creation routing decision**: `POST /rooms` can go to any node; the response includes `room_id`, and all subsequent requests for that room get routed by the hash. Alternatively, the router picks the target node first and forwards the creation there.
- **Health checks and ring rebalancing** so that when a node dies, the router updates the ring within seconds. The reconnect grace window (currently 10s) is the budget for this.

**Abuse.** No rate limiting or authentication. A bad actor could create thousands of rooms or hold WebSocket connections open. Fix: rate limit room creation per IP, require a short-lived token to open a WebSocket, cap connections per client.

## Keeping costs sane

Signaling is cheap. The server does almost no work: accept WebSocket, forward a few JSON messages, close. At 10k rooms/day, bandwidth is negligible (<1 GB/day of signaling traffic). A $5/month VPS handles this easily.

The expensive part is TURN (see below). Strategies:

- **Measure first.** Most calls succeed without TURN (STUN-only). Instrument the client to report whether TURN was used, and only scale TURN capacity based on actual need.
- **Time-limited TURN credentials.** Generate short-lived TURN credentials (via TURN REST API / `coturn`'s `--lt-cred-mech`) so credentials can't be reused for abuse.
- **Bandwidth caps.** Configure TURN to limit per-session bandwidth and total server bandwidth. Audio-only 1:1 calls use ~100 kbps; video adds ~1-2 Mbps. Set limits accordingly.
- **Provider pricing.** If self-hosting coturn is too much ops overhead, Twilio's Network Traversal Service charges ~$0.0004/min for TURN relay. At 10k rooms/day averaging 10 minutes, worst case (all calls use TURN) is ~$40/day. In practice, <20% of calls need TURN, so ~$8/day.

## NAT traversal in production

### How WebRTC connectivity works

1. **ICE (Interactive Connectivity Establishment)** gathers candidate addresses for each peer: local IPs, server-reflexive (public IP discovered via STUN), and relay (TURN).
2. Candidates are exchanged via signaling and tested pairwise for connectivity.
3. The best working pair is selected. Direct (host or server-reflexive) is preferred; TURN relay is the fallback.
4. Once connected, media is encrypted with **DTLS-SRTP** -- the browser enforces this regardless of the transport path.

### What we have today

Only Google's public STUN server (`stun.l.google.com:19302`) for server-reflexive candidates. This works when both peers can reach each other after NAT hole-punching — covers most home networks and many mobile carriers. TURN is opt-in via the `VITE_TURN_URL` / `VITE_TURN_USERNAME` / `VITE_TURN_CREDENTIAL` environment variables (see README); without them the app falls back to STUN-only.

### What fails without TURN

- **Symmetric NAT** (common in corporate networks): each outbound connection gets a different external port, so the remote peer's STUN-derived address doesn't work.
- **Strict firewalls** that block UDP entirely.
- **Carrier-grade NAT (CGNAT)**: the subscriber shares a public IP with thousands of other devices. The STUN reflexive candidate is either unreachable or maps to a port that the carrier's NAT won't forward.

**Confirmed in testing:** T-Mobile and Verizon both use CGNAT on their LTE/5G networks. Calls between two peers where either side is on cellular (T-Mobile or Verizon) failed 100% of the time with STUN-only. The same devices connected successfully over WiFi. This is expected — STUN resolves a server-reflexive address, but CGNAT means that address is not routable back to the device. A TURN relay is required for these networks.

The signaling WebSocket (TCP/443) works fine on both carriers regardless of CGNAT — it's the WebRTC media layer (UDP) that gets blocked. This is why the call can appear "connected" in the UI (PeerJS open, presence events flowing) while audio/video never starts.

Empirically, ~10–15% of real-world WebRTC calls need TURN relay to connect. For U.S. mobile users specifically, that number is higher.

### Running with TURN (demo / development)

For testing without provisioning your own server, the `openrelay.metered.ca` free public TURN server works:

```
VITE_TURN_URLS=turn:openrelay.metered.ca:80
VITE_TURN_USERNAME=openrelay
VITE_TURN_CREDENTIAL=openrelay
```

This is rate-limited and should not be used in production.

### What I'd do in production

1. **Run coturn** on a small VM with a public IP. coturn is the standard open-source TURN server (~10 min to deploy). Configure it with time-limited credentials (TURN REST API pattern) so the signaling server generates fresh credentials per call.
2. **Pass ICE servers from the server** as part of the `/rooms/{id}/join` response rather than baking them into the frontend build. This lets credentials rotate server-side without a redeploy, and keeps secrets off the client until they're needed.
3. **Monitor relay usage** to decide when to add TURN capacity or switch to a managed provider (Twilio Network Traversal Service charges ~$0.0004/min; at 10k rooms/day averaging 10 min and ~20% needing TURN, that's ~$8/day).

## Technologies at play

| Technology | What it does |
|-----------|-------------|
| **WebRTC** | Browser API for peer-to-peer audio/video. Handles codec negotiation, encryption, NAT traversal, and adaptive bitrate. |
| **SDP (Session Description Protocol)** | Text format describing media capabilities (codecs, ports, ICE candidates). Exchanged as "offer" and "answer" during call setup. |
| **ICE** | Protocol for discovering and testing network paths between peers. Gathers candidates from STUN/TURN and performs connectivity checks. |
| **STUN** | Lightweight protocol to discover your public IP and port. Used to generate "server-reflexive" ICE candidates. No media flows through it. |
| **TURN** | Relay server that forwards media when direct connection fails. Media flows *through* the TURN server, so it has real bandwidth cost. |
| **DTLS-SRTP** | Encryption layer for WebRTC media. DTLS negotiates keys; SRTP encrypts audio/video packets. Mandatory in all browsers -- even TURN-relayed media is end-to-end encrypted between peers. |
| **PeerJS** | Client library wrapping WebRTC. Abstracts offer/answer/ICE exchange behind a simple `call()` / `answer()` API, communicating with a signaling server over WebSocket. |
| **FastAPI** | Python async web framework. Handles both REST endpoints and WebSocket connections in the same process on a single event loop. |
