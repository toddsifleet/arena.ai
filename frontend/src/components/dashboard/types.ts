export type EventItem = {
  id: number;
  type: string;
  data: Record<string, unknown>;
  timestamp: number;
};

export type PeerState = {
  peer_id: string;
  client_id: string;
  connected: boolean;
  last_heartbeat_ago: number | null;
  disconnected_ago: number | null;
};

export type Stats = {
  total_rooms: number;
  connected_peers: number;
  disconnected_peers: number;
  total_peers: number;
};

export type WsStatus = "connecting" | "connected" | "disconnected";

export type Snapshot = {
  type: "SNAPSHOT";
  rooms: Record<string, PeerState[]>;
  stats: Stats;
  events?: EventItem[];
};

export type WsMessage = Snapshot | { type: "EVENT"; event: EventItem };
