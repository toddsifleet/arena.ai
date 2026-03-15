import {
  createSignal,
  createEffect,
  onCleanup,
  type Component,
} from "solid-js";
import ActiveRoomsPanel from "../components/dashboard/ActiveRoomsPanel";
import DashboardHeader from "../components/dashboard/DashboardHeader";
import DashboardStatsRow from "../components/dashboard/DashboardStatsRow";
import EventLogPanel from "../components/dashboard/EventLogPanel";
import SystemInfoCard from "../components/dashboard/SystemInfoCard";
import type { EventItem, PeerState, Stats, WsMessage, WsStatus } from "../components/dashboard/types";

const WS_BASE = (import.meta.env.VITE_WEBSOCKET_URL as string | undefined) || "http://localhost:9000";

function getDashboardWsUrl(): string {
  return WS_BASE.replace(/^http/, "ws") + "/dashboard/stream";
}

const MAX_EVENTS = 200;

const DashboardPage: Component = () => {
  const [events, setEvents] = createSignal<EventItem[]>([]);
  const [rooms, setRooms] = createSignal<Record<string, PeerState[]>>({});
  const [stats, setStats] = createSignal<Stats>({
    total_rooms: 0,
    connected_peers: 0,
    disconnected_peers: 0,
    total_peers: 0,
  });
  const [wsStatus, setWsStatus] = createSignal<WsStatus>("connecting");
  const [freshEventId, setFreshEventId] = createSignal<number | null>(null);
  const [totalEventsSeen, setTotalEventsSeen] = createSignal(0);
  const [autoScroll, setAutoScroll] = createSignal(true);

  let logRef: HTMLDivElement | undefined;
  let ws: WebSocket | null = null;
  let reconnectTimer: ReturnType<typeof setTimeout> | null = null;

  function applyEventToRooms(ev: EventItem) {
    const d = ev.data;
    const roomId = d.room_id as string | undefined;
    const peerId = d.peer_id as string | undefined;

    setRooms((prev) => {
      // Shallow-clone the top-level map so SolidJS detects the change
      const next = { ...prev };

      if (ev.type === "room.created" && roomId) {
        next[roomId] = [];

      } else if (ev.type === "room.destroyed" && roomId) {
        delete next[roomId];

      } else if ((ev.type === "peer.joined" || ev.type === "peer.reconnected") && roomId && peerId) {
        const existing = next[roomId] ?? [];
        const alreadyThere = existing.some((p) => p.peer_id === peerId);
        if (!alreadyThere) {
          next[roomId] = [
            ...existing,
            {
              peer_id: peerId,
              client_id: (d.client_id as string) ?? "",
              connected: false,      // ws.connected will flip this immediately after
              last_heartbeat_ago: null,
              disconnected_ago: null,
            },
          ];
        }

      } else if (ev.type === "ws.connected" && roomId && peerId) {
        if (next[roomId]) {
          next[roomId] = next[roomId].map((p) =>
            p.peer_id === peerId
              ? { ...p, connected: true, disconnected_ago: null }
              : p
          );
        }

      } else if (ev.type === "ws.disconnected" && roomId && peerId) {
        if (next[roomId]) {
          next[roomId] = next[roomId].map((p) =>
            p.peer_id === peerId ? { ...p, connected: false } : p
          );
        }

      } else if (
        (ev.type === "peer.left" ||
          ev.type === "peer.evicted" ||
          ev.type === "peer.evicted_stale") &&
        roomId &&
        peerId
      ) {
        if (next[roomId]) {
          const filtered = next[roomId].filter((p) => p.peer_id !== peerId);
          if (filtered.length === 0) {
            // room.destroyed event will arrive right after, but proactively remove it
            delete next[roomId];
          } else {
            next[roomId] = filtered;
          }
        }
      }

      return next;
    });

    // Keep stats in sync (SNAPSHOT will reconcile precisely every 3s)
    setStats((prev) => {
      if (ev.type === "room.created") return { ...prev, total_rooms: prev.total_rooms + 1 };
      if (ev.type === "room.destroyed") return { ...prev, total_rooms: Math.max(0, prev.total_rooms - 1) };
      if (ev.type === "ws.connected") return { ...prev, connected_peers: prev.connected_peers + 1, disconnected_peers: Math.max(0, prev.disconnected_peers - 1) };
      if (ev.type === "ws.disconnected") return { ...prev, connected_peers: Math.max(0, prev.connected_peers - 1), disconnected_peers: prev.disconnected_peers + 1 };
      if (ev.type === "peer.joined") return { ...prev, total_peers: prev.total_peers + 1 };
      if (ev.type === "peer.left" || ev.type === "peer.evicted" || ev.type === "peer.evicted_stale") return { ...prev, total_peers: Math.max(0, prev.total_peers - 1) };
      return prev;
    });
  }

  function connect() {
    setWsStatus("connecting");
    ws = new WebSocket(getDashboardWsUrl());

    ws.onopen = () => setWsStatus("connected");

    ws.onmessage = (e) => {
      let msg: WsMessage;
      try { msg = JSON.parse(e.data); } catch { return; }

      if (msg.type === "SNAPSHOT") {
        // Full reconcile — always trust the snapshot for rooms/stats
        setRooms(msg.rooms ?? {});
        setStats(msg.stats ?? stats());
        if (msg.events) {
          setEvents(msg.events.slice().reverse());
          setTotalEventsSeen(msg.events.length);
        }
      } else if (msg.type === "EVENT") {
        const ev = msg.event;

        setFreshEventId(ev.id);
        setTotalEventsSeen((n) => n + 1);
        setEvents((prev) => {
          const next = [ev, ...prev];
          return next.length > MAX_EVENTS ? next.slice(0, MAX_EVENTS) : next;
        });
        setTimeout(() => setFreshEventId((id) => (id === ev.id ? null : id)), 1200);

        // Apply event to rooms state immediately (no waiting for next snapshot)
        applyEventToRooms(ev);
      }
    };

    ws.onclose = () => {
      setWsStatus("disconnected");
      reconnectTimer = setTimeout(connect, 3000);
    };
    ws.onerror = () => ws?.close();
  }

  connect();
  onCleanup(() => {
    if (reconnectTimer) clearTimeout(reconnectTimer);
    ws?.close();
  });

  createEffect(() => {
    events(); // track
    if (autoScroll() && logRef) {
      logRef.scrollTop = 0;
    }
  });

  const roomEntries = () => Object.entries(rooms());
  const totalRooms = () => stats().total_rooms;
  const connectedPeers = () => stats().connected_peers;
  const disconnectedPeers = () => stats().disconnected_peers;

  return (
    <div class="min-h-screen bg-[#080808] text-white font-sans flex flex-col">
      <DashboardHeader totalEventsSeen={totalEventsSeen()} wsStatus={wsStatus()} />

      <DashboardStatsRow
        totalRooms={totalRooms()}
        connectedPeers={connectedPeers()}
        disconnectedPeers={disconnectedPeers()}
        eventsBuffered={events().length}
        maxEvents={MAX_EVENTS}
      />

      <div class="flex flex-1 gap-4 px-6 pb-6 min-h-0 overflow-hidden">
        <EventLogPanel
          events={events()}
          freshEventId={freshEventId()}
          autoScroll={autoScroll()}
          onToggleAutoScroll={() => setAutoScroll((v) => !v)}
          setLogRef={(el) => {
            logRef = el;
          }}
        />

        <div class="flex flex-col flex-[2] min-w-0 gap-4 overflow-hidden">
          <ActiveRoomsPanel roomEntries={roomEntries()} />
          <SystemInfoCard maxEvents={MAX_EVENTS} />
        </div>
      </div>
    </div>
  );
};

export default DashboardPage;
