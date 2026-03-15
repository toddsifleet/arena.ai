/**
 * MiniRTC: signaling config and small helpers. PeerJS connects to our FastAPI backend.
 */

const fallback = {
  host: "localhost",
  port: 9000,
  path: "/",
  secure: false,
};

function parseApiUrl(url: string): { host: string; port: number; path: string; secure: boolean } {
  try {
    const u = new URL(url);
    return {
      host: u.hostname,
      port: u.port ? parseInt(u.port, 10) : u.protocol === "https:" ? 443 : 80,
      // PeerJS appends "peerjs" internally, so keep base path at "/".
      path: u.pathname.replace(/\/$/, "") || "/",
      secure: u.protocol === "https:",
    };
  } catch {
    return fallback;
  }
}

export function getSignalingConfig(): { host: string; port: number; path: string; secure: boolean } {
  const raw = import.meta.env.VITE_API_URL as string | undefined;
  if (raw) return parseApiUrl(raw);
  return fallback;
}

const API_BASE = import.meta.env.VITE_API_URL || "http://localhost:9000";

export async function createRoom(): Promise<{ roomId: string }> {
  const r = await fetch(`${API_BASE}/rooms`, { method: "POST" });
  if (!r.ok) throw new Error("Failed to create room");
  const data = await r.json();
  return { roomId: data.room_id };
}

export async function joinRoom(
  roomId: string,
  clientId?: string | null
): Promise<{ roomId: string; peerId: string; clientId: string }> {
  const url = new URL(`${API_BASE}/rooms/${encodeURIComponent(roomId)}/join`);
  if (clientId) url.searchParams.set("client_id", clientId);
  const r = await fetch(url.toString());
  if (r.status === 403) throw new Error("room_full");
  if (r.status === 404) throw new Error("room_not_found");
  if (r.status === 400 || r.status === 422) throw new Error("invalid_room_id");
  if (r.status === 409) throw new Error("already_connected");
  if (!r.ok) throw new Error("Failed to join room");
  const data = await r.json();
  return {
    roomId: data.room_id,
    peerId: data.peer_id,
    clientId: data.client_id,
  };
}

export type PeerInRoom = { id: string; client_id: string; connected: boolean };

export async function getPeersInRoom(roomId: string): Promise<PeerInRoom[]> {
  const r = await fetch(`${API_BASE}/rooms/${encodeURIComponent(roomId)}/peers`);
  if (!r.ok) throw new Error("Failed to list peers");
  const data = await r.json();
  return data.peers ?? [];
}

export type ConnectionStatus = "idle" | "connecting" | "connected" | "disconnected" | "error";

export type PresenceKind = "joined" | "left" | "disconnected" | "reconnected";

export function getPresenceWsUrl(roomId: string): string {
  const raw = (import.meta.env.VITE_API_URL as string | undefined) || "http://localhost:9000";
  const wsBase = raw.replace(/^http/, "ws");
  return `${wsBase}/rooms/${encodeURIComponent(roomId)}/presence`;
}
