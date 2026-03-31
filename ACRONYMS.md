# Acronyms and Abbreviations

This glossary defines the acronyms and common abbreviations used across this codebase (`backend/`, `frontend/`, `README.md`, and `DECISIONS.md`).

## WebRTC and Networking

- **WebRTC** - Web Real-Time Communication. The browser stack that handles real-time voice/video between peers, including codec negotiation, congestion control, encryption, and transport selection. In this app, WebRTC carries media while your backend handles only signaling/presence.
- **P2P** - Peer-to-peer. A direct connection between two clients where media bypasses your application server. This keeps signaling costs low and latency better, but connectivity depends on each network's NAT/firewall behavior.
- **ICE** - Interactive Connectivity Establishment. The negotiation process that gathers possible network routes ("candidates"), exchanges them, and checks which candidate pair can actually pass traffic. ICE prefers direct paths and falls back to relay paths when needed.
- **STUN** - Session Traversal Utilities for NAT. A lightweight protocol a client uses to learn its public-facing IP:port mapping ("server-reflexive" candidate). STUN helps with NAT traversal discovery, but it does not relay media and cannot solve every NAT/firewall scenario.
- **TURN** - Traversal Using Relays around NAT. A relay server used when direct ICE paths fail (for example strict corporate networks, cellular CGNAT, or UDP-blocking firewalls). Unlike STUN, TURN sits in the media path for the entire call, so reliability improves but bandwidth cost scales with usage.
- **NAT** - Network Address Translation. Networking behavior where many devices on private addresses share a smaller set of public addresses. NAT is the core reason WebRTC needs ICE/STUN/TURN, because peers cannot reliably dial private addresses directly.
- **CGNAT** - Carrier-Grade NAT. ISP/mobile-carrier NAT at large scale where many customers share public IPs. In practice this often breaks direct peer reachability for WebRTC, which is why TURN fallback is important for mobile networks.
- **SDP** - Session Description Protocol. The offer/answer text payload exchanged during call setup that describes media capabilities (codecs, directions, fingerprints, ICE params, candidate info). Your signaling channel transports this SDP between peers.
- **DTLS** - Datagram Transport Layer Security. The handshake layer used by WebRTC to authenticate peers and derive encryption keys for media. Think of DTLS as the "key agreement/security setup" stage before protected RTP media flows.
- **SRTP** - Secure Real-time Transport Protocol. The encrypted/authenticated packet format for the actual audio/video stream. WebRTC media is SRTP-protected, with keys derived from the DTLS handshake.
- **SFU** - Selective Forwarding Unit. A server architecture for multiparty calls where clients send media up to a central forwarder instead of pure mesh P2P. It's noted in this project as a future/alternative model for group calling, not required for the current 1:1 scope.

## Transport and Web Protocols

- **UDP** - User Datagram Protocol. Connectionless transport with low overhead and no built-in retransmission guarantees, which makes it ideal for real-time media where timeliness beats perfect delivery. WebRTC prefers UDP for audio/video for lower latency and jitter.
- **TCP** - Transmission Control Protocol. Reliable, ordered transport with retransmission and flow control. Great for signaling/control planes (like WebSocket/HTTP), but usually less ideal than UDP for interactive media because recovery behavior can add delay.
- **TLS** - Transport Layer Security. Cryptographic protocol that secures TCP-based connections (confidentiality, integrity, server identity). In this domain, TLS appears in HTTPS/WSS and in `turns:` endpoints (TURN over TLS).
- **HTTP** - Hypertext Transfer Protocol. Stateless request/response protocol used for your non-realtime API operations. In this project, HTTP is used for room creation/join/list flows and config-style interactions, while realtime signaling moves to WebSocket.
- **REST** - Representational State Transfer. An API design style built around resource-oriented URLs and HTTP semantics (methods, status codes, cache behavior). Here, REST cleanly models room lifecycle operations, while call negotiation messages use the separate WebSocket channel.


