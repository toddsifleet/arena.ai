import {
  createEffect,
  createSignal,
  onCleanup,
  onMount,
  Show,
  type Component,
} from "solid-js";
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

  const [peerId, setPeerId] = createSignal<string | null>(null);
  const [peer, setPeer] = createSignal<Peer | null>(null);
  const [peerReady, setPeerReady] = createSignal(false);
  const [localStream, setLocalStream] = createSignal<MediaStream | null>(null);
  const [remoteStream, setRemoteStream] = createSignal<MediaStream | null>(null);
  const [activeCall, setActiveCall] = createSignal<MediaConnection | null>(null);
  const [pendingIncomingCall, setPendingIncomingCall] = createSignal<MediaConnection | null>(null);
  const [otherPeerId, setOtherPeerId] = createSignal<string | null>(null);
  const [muted, setMuted] = createSignal(false);
  const [videoOff, setVideoOff] = createSignal(false);
  const [peerDisconnected, setPeerDisconnected] = createSignal(false);
  const [error, setError] = createSignal<string | null>(null);
  const [joining, setJoining] = createSignal(true);
  const [copied, setCopied] = createSignal(false);

  onMount(() => {
    const initMedia = async () => {
      try {
        const stream = await navigator.mediaDevices.getUserMedia({ video: true, audio: true });
        setLocalStream(stream);
      } catch {
        try {
          // Audio is required; video is optional, so retry without camera.
          const audioOnly = await navigator.mediaDevices.getUserMedia({
            video: false,
            audio: true,
          });
          setLocalStream(audioOnly);
          setVideoOff(true);
        } catch {
          setError("Microphone access denied");
        }
      }
    };

    onCleanup(() => {
      localStream()?.getTracks().forEach((t) => t.stop());
      activeCall()?.close();
      pendingIncomingCall()?.close();
    });

    const initRoom = async () => {
      try {
        const { peerId: p, clientId: c } = await joinRoom(params.id, clientId());
        persistClientId(c);
        setPeerId(p);
        setJoining(false);
      } catch (e) {
        const msg =
          (e as Error).message === "already_connected"
            ? "Already open in another tab."
            : (e as Error).message === "room_not_found"
            ? "Room not found."
            : (e as Error).message === "room_full"
            ? "Room is full."
            : "Could not join room.";
        setError(msg);
        setJoining(false);
      }
    };

    void initMedia();
    void initRoom();
  });

  createEffect(() => {
    const pid = peerId();
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
    setPeer(p);

    p.on("open", () => setPeerReady(true));
    p.on("disconnected", () => {
      setPeerReady(false);
      // Reconnect the signaling WebSocket after a transient network change
      // (e.g. WiFi → cellular). Without this call the peer stays disconnected
      // indefinitely and the backend eventually evicts it.
      if (!p.destroyed) p.reconnect();
    });
    p.on("close", () => setPeerReady(false));
    p.on("error", () => setError((prev) => prev || "Connection error"));

    onCleanup(() => {
      p.destroy();
      setPeer(null);
      setPeerReady(false);
    });
  });

  // Answer incoming calls automatically
  createEffect(() => {
    const p = peer();
    if (!p) return;

    const bindCall = (call: MediaConnection) => {
      call.on("stream", setRemoteStream);
      call.on("close", () => {
        setRemoteStream(null);
        setActiveCall(null);
        if (pendingIncomingCall() === call) {
          setPendingIncomingCall(null);
        }
        setPeerDisconnected(true);
      });
      setActiveCall(call);
    };

    const onCall = (incoming: MediaConnection) => {
      const stream = localStream();
      if (!stream) {
        // First-time permission prompts can delay local media; answer once ready.
        const pending = pendingIncomingCall();
        if (pending && pending !== incoming) {
          pending.close();
        }
        setPendingIncomingCall(incoming);
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
    const incoming = pendingIncomingCall();
    const stream = localStream();
    if (!incoming || !stream || activeCall()) return;
    incoming.answer(stream);
    incoming.on("stream", setRemoteStream);
    incoming.on("close", () => {
      setRemoteStream(null);
      setActiveCall(null);
      if (pendingIncomingCall() === incoming) {
        setPendingIncomingCall(null);
      }
      setPeerDisconnected(true);
    });
    setActiveCall(incoming);
    setPendingIncomingCall(null);
  });

  // Presence WebSocket: discover existing peers on connect and receive live join/leave events.
  // The WebSocket is reconnected with exponential backoff so that a transient network
  // change (the same one that drops the signaling connection) doesn't permanently
  // prevent the client from learning when the remote peer comes back.
  createEffect(() => {
    const pid = peerId();
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
            setOtherPeerId(null);
            activeCall()?.close();
            setActiveCall(null);
            setRemoteStream(null);
            setPeerDisconnected(true);
          } else if (kind === "joined" || kind === "reconnected") {
            setOtherPeerId(who);
            setPeerDisconnected(false);
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
    const p = peer();
    const other = otherPeerId();
    const stream = localStream();
    const ready = peerReady();
    const existingCall = activeCall();

    if (!p || !other || !stream || !ready || existingCall) return;

    const myId = peerId();
    if (!myId || myId >= other) return;

    const c = p.call(other, stream);
    setActiveCall(c);
    c.on("stream", setRemoteStream);
    c.on("close", () => {
      setRemoteStream(null);
      setActiveCall(null);
      setPeerDisconnected(true);
    });
  });

  const toggleMute = () => {
    const ls = localStream();
    if (!ls) return;
    const next = !muted();
    ls.getAudioTracks().forEach((t) => (t.enabled = !next));
    setMuted(next);
  };

  const toggleVideo = () => {
    const ls = localStream();
    if (!ls) return;
    const next = !videoOff();
    ls.getVideoTracks().forEach((t) => (t.enabled = !next));
    setVideoOff(next);
  };

  const handleLeave = () => {
    activeCall()?.close();
    localStream()?.getTracks().forEach((t) => t.stop());
    peer()?.destroy();
    navigate("/");
  };

  let copiedTimer: ReturnType<typeof setTimeout> | undefined;
  onCleanup(() => clearTimeout(copiedTimer));

  const copyRoomLink = async () => {
    const url = `${window.location.origin}/room/${params.id}`;
    try {
      await navigator.clipboard.writeText(url);
      setCopied(true);
      clearTimeout(copiedTimer);
      copiedTimer = setTimeout(() => setCopied(false), 2000);
    } catch {
      // ignore clipboard errors
    }
  };

  const connectionStatus = () => {
    if (error()) return "Error";
    if (remoteStream()) return "Connected";
    if (peerDisconnected()) return "Waiting";
    if (!peerReady()) return "Connecting";
    return "Ready";
  };

  return (
    <Show
      when={!joining()}
      fallback={
        <div class="min-h-screen bg-black flex items-center justify-center">
          <span class="text-neutral-600 text-sm">Joining…</span>
        </div>
      }
    >
      <Show
        when={peerId()}
        fallback={
          <div class="min-h-screen bg-black flex items-center justify-center">
            <div class="text-center space-y-4">
              <p class="text-red-400 text-sm">{error()}</p>
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
              localStream={localStream()}
              remoteStream={remoteStream()}
              peerDisconnected={peerDisconnected()}
              roomId={params.id}
              onCopyLink={copyRoomLink}
              copied={copied()}
            />
          </div>

          <div class="h-16 flex items-center justify-between px-5 border-t border-neutral-900">
            <button
              type="button"
              onClick={copyRoomLink}
              class="font-mono text-xs text-neutral-700 hover:text-neutral-400 transition-colors truncate max-w-[140px]"
              title="Copy room link"
            >
              {copied() ? "Copied!" : params.id}
            </button>

            <div class="flex items-center gap-2">
              <ControlButton
                active={muted()}
                onClick={toggleMute}
                label={muted() ? "Unmute" : "Mute"}
                danger={muted()}
              />
              <ControlButton
                active={videoOff()}
                onClick={toggleVideo}
                label={videoOff() ? "Cam on" : "Cam off"}
                danger={videoOff()}
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
