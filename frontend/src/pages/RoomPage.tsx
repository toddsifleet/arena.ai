import {
  createEffect,
  onCleanup,
  onMount,
  Show,
  type Component,
} from "solid-js";
import { createStore } from "solid-js/store";
import { Peer } from "peerjs";
import type { MediaConnection } from "peerjs";
import { useParams, useNavigate } from "@solidjs/router";
import { joinRoom, getSignalingConfig, getPresenceWsUrl } from "../rtc";
import { useClient } from "../context/ClientContext";
import VideoGrid from "../components/VideoGrid";
import ControlButton from "../components/ControlButton";

const RoomPage: Component = () => {
  const params = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { clientId, persistClientId } = useClient();

  const [peerState, setPeerState] = createStore<{
    id: string | null;
    instance: Peer | null;
    ready: boolean;
    otherId: string | null;
    disconnected: boolean;
    pendingIceRestart: boolean;
  }>({ id: null, instance: null, ready: false, otherId: null, disconnected: false, pendingIceRestart: false });

  const [media, setMedia] = createStore<{
    local: MediaStream | null;
    remote: MediaStream | null;
    active: MediaConnection | null;
    pendingIncoming: MediaConnection | null;
  }>({ local: null, remote: null, active: null, pendingIncoming: null });

  const [ui, setUi] = createStore({
    muted: false,
    videoOff: false,
    error: null as string | null,
    joining: true,
    copied: false,
  });

  onMount(() => {
    const initMedia = async () => {
      try {
        const stream = await navigator.mediaDevices.getUserMedia({ video: true, audio: true });
        setMedia("local", stream);
      } catch {
        try {
          // Audio is required; video is optional, so retry without camera.
          const audioOnly = await navigator.mediaDevices.getUserMedia({ video: false, audio: true });
          setMedia("local", audioOnly);
          setUi("videoOff", true);
        } catch {
          setUi("error", "Microphone access denied");
        }
      }
    };

    onCleanup(() => {
      media.local?.getTracks().forEach((t) => t.stop());
      media.active?.close();
      media.pendingIncoming?.close();
    });

    const initRoom = async () => {
      try {
        const { peerId: p, clientId: c } = await joinRoom(params.id, clientId());
        persistClientId(c);
        setPeerState("id", p);
        setUi("joining", false);
      } catch (e) {
        const msg =
          (e as Error).message === "already_connected"
            ? "Already open in another tab."
            : (e as Error).message === "room_not_found"
            ? "Room not found."
            : (e as Error).message === "room_full"
            ? "Room is full."
            : "Could not join room.";
        setUi("error", msg);
        setUi("joining", false);
      }
    };

    void initMedia();
    void initRoom();
  });

  // Attach event handlers to an established MediaConnection (outgoing or incoming).
  const bindCall = (conn: MediaConnection) => {
    conn.on("stream", (s) => setMedia("remote", s));
    conn.on("close", () => {
      setMedia("remote", null);
      setMedia("active", null);
      setPeerState("pendingIceRestart", false);
      setPeerState("disconnected", true);
    });

    // Monitor ICE connection state so we can attempt a restart on network
    // changes (e.g. WiFi → cellular) without tearing down the full call.
    // 'disconnected' is transient — the browser retries for ~5 s before
    // escalating to 'failed'. We set a flag here; the actual restartIce()
    // call is deferred until we know the remote peer's signaling is back up.
    const pc = conn.peerConnection;
    pc.addEventListener("iceconnectionstatechange", () => {
      const s = pc.iceConnectionState;
      if (s === "disconnected") {
        setPeerState("pendingIceRestart", true);
      } else if (s === "connected" || s === "completed") {
        setPeerState("pendingIceRestart", false);
      }
      // 'failed': PeerJS closes the MediaConnection → conn.on("close") fires.
    });

    setMedia("active", conn);
  };

  // Attempt an ICE restart on the active call if conditions are met.
  // Only the caller (lower peer ID) initiates — same tiebreak rule as the
  // original call — so both sides don't restart simultaneously.
  const tryIceRestart = () => {
    const { active, } = media;
    const { id: myId, otherId, pendingIceRestart } = peerState;
    if (!pendingIceRestart || !active || !myId || !otherId) return;
    if (myId >= otherId) return;
    active.peerConnection.restartIce();
    setPeerState("pendingIceRestart", false);
  };

  createEffect(() => {
    const pid = peerState.id;
    if (!pid) return;

    const cfg = getSignalingConfig();

    // STUN is always included. TURN is optional: set VITE_TURN_URL (+ USERNAME /
    // CREDENTIAL) to enable it. Without TURN the app still works on most
    // networks, but calls between peers on cellular CGNAT or strict firewalls
    // will silently fail at the media layer even though signaling succeeds —
    // the WebSocket (TCP) connects fine, but WebRTC media (UDP) gets blocked.
    const iceServers: RTCIceServer[] = [{ urls: "stun:stun.l.google.com:19302" }];
    // VITE_TURN_URLS accepts a comma-separated list of TURN URLs so that
    // providers like Xirsys can supply multiple transport options (UDP, TCP,
    // TLS) in a single credential entry. The browser tries them in order and
    // picks the first one that works.
    const turnUrls = import.meta.env.VITE_TURN_URLS as string | undefined;
    if (turnUrls) {
      iceServers.push({
        urls: turnUrls.split(",").map((u) => u.trim()),
        username: import.meta.env.VITE_TURN_USERNAME as string | undefined,
        credential: import.meta.env.VITE_TURN_CREDENTIAL as string | undefined,
      });
    }

    const p = new Peer(pid, {
      host: cfg.host,
      port: cfg.port,
      path: cfg.path,
      secure: cfg.secure,
      config: { iceServers },
      debug: 1,
    });
    setPeerState("instance", p);

    p.on("open", () => {
      setPeerState("ready", true);
      // If our own signaling WS dropped and just reconnected while an ICE
      // restart was pending, attempt it now.
      tryIceRestart();
    });
    p.on("disconnected", () => {
      setPeerState("ready", false);
      // Reconnect the signaling WebSocket after a transient network change
      // (e.g. WiFi → cellular). Without this call the peer stays disconnected
      // indefinitely and the backend eventually evicts it.
      if (!p.destroyed) p.reconnect();
    });
    p.on("close", () => setPeerState("ready", false));
    p.on("error", () => setUi("error", (prev) => prev || "Connection error"));

    onCleanup(() => {
      p.destroy();
      setPeerState("instance", null);
      setPeerState("ready", false);
    });
  });

  // Answer incoming calls automatically
  createEffect(() => {
    const p = peerState.instance;
    if (!p) return;

    const onCall = (incoming: MediaConnection) => {
      const stream = media.local;
      if (!stream) {
        // First-time permission prompts can delay local media; answer once ready.
        if (media.pendingIncoming && media.pendingIncoming !== incoming) {
          media.pendingIncoming.close();
        }
        setMedia("pendingIncoming", incoming);
        return;
      }
      incoming.answer(stream);
      bindCall(incoming);
    };

    p.on("call", onCall);
    onCleanup(() => p.off("call", onCall));
  });

  // If a call arrived before local media was available, answer it once ready.
  createEffect(() => {
    const { pendingIncoming } = media;
    const stream = media.local;
    if (!pendingIncoming || !stream || media.active) return;
    pendingIncoming.answer(stream);
    bindCall(pendingIncoming);
    setMedia("pendingIncoming", null);
  });

  // Presence WebSocket: discover existing peers on connect and receive live join/leave events.
  // The WebSocket is reconnected with exponential backoff so that a transient network
  // change (the same one that drops the signaling connection) doesn't permanently
  // prevent the client from learning when the remote peer comes back.
  createEffect(() => {
    const pid = peerState.id;
    if (!pid) return;

    let ws: WebSocket | null = null;
    let retryDelay = 1_000;
    let retryTimer: ReturnType<typeof setTimeout> | undefined;
    let dead = false;

    const connect = () => {
      if (dead) return;
      ws = new WebSocket(getPresenceWsUrl(params.id));

      ws.onopen = () => {
        retryDelay = 1_000; // reset backoff after a successful connection
      };

      ws.onmessage = (evt) => {
        try {
          const msg = JSON.parse(evt.data as string) as {
            type: string;
            payload: { kind: string; peer_id: string };
          };
          if (msg.type !== "PRESENCE") return;
          const { kind, peer_id: who } = msg.payload;
          if (who === pid) return; // ignore our own events
          if (kind === "disconnected" || kind === "left") {
            setPeerState("otherId", null);
            media.active?.close();
            setMedia("active", null);
            setMedia("remote", null);
            setPeerState("disconnected", true);
          } else if (kind === "joined" || kind === "reconnected") {
            setPeerState("otherId", who);
            setPeerState("disconnected", false);
            // Remote peer's signaling is back up — if an ICE restart was pending
            // (our peerConnection is still alive but ICE went disconnected during
            // the network switch), trigger it now so the call resumes without a
            // full teardown.
            tryIceRestart();
          }
        } catch {
          // ignore malformed messages
        }
      };

      ws.onclose = () => {
        if (dead) return;
        retryTimer = setTimeout(() => {
          retryDelay = Math.min(retryDelay * 2, 30_000);
          connect();
        }, retryDelay);
      };
    };

    connect();

    onCleanup(() => {
      dead = true;
      clearTimeout(retryTimer);
      ws?.close();
    });
  });

  // Auto-call: lower peer ID initiates to prevent double-call
  createEffect(() => {
    const { instance: p, id: myId, otherId, ready } = peerState;
    const { local: stream, active } = media;

    if (!p || !otherId || !stream || !ready || active) return;
    if (!myId || myId >= otherId) return;

    const c = p.call(otherId, stream);
    bindCall(c);
  });

  const toggleMute = () => {
    if (!media.local) return;
    const next = !ui.muted;
    media.local.getAudioTracks().forEach((t) => (t.enabled = !next));
    setUi("muted", next);
  };

  const toggleVideo = () => {
    if (!media.local) return;
    const next = !ui.videoOff;
    media.local.getVideoTracks().forEach((t) => (t.enabled = !next));
    setUi("videoOff", next);
  };

  const handleLeave = () => {
    media.active?.close();
    media.local?.getTracks().forEach((t) => t.stop());
    peerState.instance?.destroy();
    navigate("/");
  };

  let copiedTimer: ReturnType<typeof setTimeout> | undefined;
  onCleanup(() => clearTimeout(copiedTimer));

  const copyRoomLink = async () => {
    const url = `${window.location.origin}/room/${params.id}`;
    try {
      await navigator.clipboard.writeText(url);
      setUi("copied", true);
      clearTimeout(copiedTimer);
      copiedTimer = setTimeout(() => setUi("copied", false), 2000);
    } catch {
      // ignore clipboard errors
    }
  };

  const connectionStatus = () => {
    if (ui.error) return "Error";
    if (media.remote) return "Connected";
    if (peerState.disconnected) return "Waiting";
    if (!peerState.ready) return "Connecting";
    return "Ready";
  };

  return (
    <Show
      when={!ui.joining}
      fallback={
        <div class="min-h-screen bg-black flex items-center justify-center">
          <span class="text-neutral-600 text-sm">Joining…</span>
        </div>
      }
    >
      <Show
        when={peerState.id}
        fallback={
          <div class="min-h-screen bg-black flex items-center justify-center">
            <div class="text-center space-y-4">
              <p class="text-red-400 text-sm">{ui.error}</p>
              <button
                type="button"
                onClick={() => navigate("/")}
                class="text-neutral-600 hover:text-white text-sm transition-colors"
              >
                ← Back
              </button>
            </div>
          </div>
        }
      >
        <div class="h-screen bg-black flex flex-col overflow-hidden">
          <div class="flex-1 min-h-0 p-3">
            <VideoGrid
              localStream={media.local}
              remoteStream={media.remote}
              peerDisconnected={peerState.disconnected}
              roomId={params.id}
              onCopyLink={copyRoomLink}
              copied={ui.copied}
            />
          </div>

          <div class="h-16 flex items-center justify-between px-5 border-t border-neutral-900">
            <button
              type="button"
              onClick={copyRoomLink}
              class="font-mono text-xs text-neutral-700 hover:text-neutral-400 transition-colors truncate max-w-[140px]"
              title="Copy room link"
            >
              {ui.copied ? "Copied!" : params.id}
            </button>

            <div class="flex items-center gap-2">
              <ControlButton
                active={ui.muted}
                onClick={toggleMute}
                label={ui.muted ? "Unmute" : "Mute"}
                danger={ui.muted}
              />
              <ControlButton
                active={ui.videoOff}
                onClick={toggleVideo}
                label={ui.videoOff ? "Cam on" : "Cam off"}
                danger={ui.videoOff}
              />
              <button
                type="button"
                onClick={handleLeave}
                class="rounded-full bg-red-600 hover:bg-red-500 text-white px-5 h-9 text-xs font-medium transition-colors ml-1"
              >
                Leave
              </button>
            </div>

            <div class="w-[140px] text-right">
              <span class="text-[11px] uppercase tracking-wide text-neutral-500">
                {connectionStatus()}
              </span>
            </div>
          </div>
        </div>
      </Show>
    </Show>
  );
};

export default RoomPage;
