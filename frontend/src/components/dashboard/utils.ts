import type { EventItem } from "./types";

type EventStyle = { dot: string; badge: string; label: string };

export function formatTime(ts: number): string {
  return new Date(ts * 1000).toLocaleTimeString([], {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
  });
}

export function shortId(id: string): string {
  return id.slice(0, 8);
}

export function elapsedLabel(secs: number | null | undefined): string {
  if (secs === null || secs === undefined) return "—";
  if (secs < 2) return "<1s ago";
  if (secs < 60) return `${Math.round(secs)}s ago`;
  return `${Math.round(secs / 60)}m ago`;
}

export function eventStyle(type: string): EventStyle {
  if (type === "room.created") return { dot: "bg-emerald-400", badge: "text-emerald-400 bg-emerald-400/10", label: "ROOM CREATED" };
  if (type === "room.destroyed") return { dot: "bg-red-500", badge: "text-red-400 bg-red-400/10", label: "ROOM DESTROYED" };
  if (type === "peer.joined") return { dot: "bg-emerald-400", badge: "text-emerald-300 bg-emerald-400/10", label: "PEER JOINED" };
  if (type === "peer.reconnected") return { dot: "bg-cyan-400", badge: "text-cyan-300 bg-cyan-400/10", label: "RECONNECTED" };
  if (type === "peer.left") return { dot: "bg-red-400", badge: "text-red-300 bg-red-400/10", label: "PEER LEFT" };
  if (type === "peer.disconnected") return { dot: "bg-amber-400", badge: "text-amber-300 bg-amber-400/10", label: "DISCONNECTED" };
  if (type === "peer.evicted") return { dot: "bg-orange-500", badge: "text-orange-300 bg-orange-400/10", label: "EVICTED" };
  if (type === "peer.evicted_stale") return { dot: "bg-orange-600", badge: "text-orange-300 bg-orange-500/10", label: "EVICTED STALE" };
  if (type === "ws.connected") return { dot: "bg-sky-400", badge: "text-sky-300 bg-sky-400/10", label: "WS CONNECTED" };
  if (type === "ws.disconnected") return { dot: "bg-slate-400", badge: "text-slate-300 bg-slate-400/10", label: "WS DROPPED" };
  if (type === "signal.offer") return { dot: "bg-violet-400", badge: "text-violet-300 bg-violet-400/10", label: "OFFER" };
  if (type === "signal.answer") return { dot: "bg-purple-400", badge: "text-purple-300 bg-purple-400/10", label: "ANSWER" };
  if (type === "signal.candidate") return { dot: "bg-indigo-400", badge: "text-indigo-300 bg-indigo-400/10", label: "ICE CANDIDATE" };
  return { dot: "bg-slate-500", badge: "text-slate-400 bg-slate-500/10", label: type.toUpperCase() };
}

export function renderEventData(data: EventItem["data"]): string {
  const parts: string[] = [];
  if (data.room_id) parts.push(`room=${shortId(data.room_id as string)}`);
  if (data.peer_id) parts.push(`peer=${shortId(data.peer_id as string)}`);
  if (data.client_id) parts.push(`client=${shortId(data.client_id as string)}`);
  if (data.src) parts.push(`src=${shortId(data.src as string)}`);
  if (data.dst) parts.push(`dst=${shortId(data.dst as string)}`);
  if (data.reason) parts.push(`reason=${data.reason}`);
  if (data.reconnected !== undefined) parts.push(`reconnected=${data.reconnected}`);
  return parts.join("  ·  ");
}
