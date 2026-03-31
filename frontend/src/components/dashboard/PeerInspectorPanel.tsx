import { For, Show, type Component } from "solid-js";
import type { EventItem, PeerState } from "./types";
import { elapsedLabel, formatTime, shortId } from "./utils";

interface PeerInspectorPanelProps {
  selectedRoomId: string | null;
  selectedPeer: PeerState | null;
  events: EventItem[];
}

type ParsedCandidate = {
  foundation: string;
  component: string;
  protocol: string;
  priority: string;
  ip: string;
  port: string;
  type: string;
  relatedAddress?: string;
  relatedPort?: string;
};

function stringify(value: unknown): string {
  if (value === null || value === undefined) return "null";
  if (typeof value === "string") return value;
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return String(value);
  }
}

function parseIceCandidate(candidate: string | undefined): ParsedCandidate | null {
  if (!candidate) return null;
  const parts = candidate.trim().split(/\s+/);
  if (parts.length < 8 || !parts[0].startsWith("candidate:")) return null;

  const parsed: ParsedCandidate = {
    foundation: parts[0].replace("candidate:", ""),
    component: parts[1] ?? "",
    protocol: parts[2] ?? "",
    priority: parts[3] ?? "",
    ip: parts[4] ?? "",
    port: parts[5] ?? "",
    type: "",
  };

  const typeIdx = parts.indexOf("typ");
  if (typeIdx >= 0 && parts[typeIdx + 1]) parsed.type = parts[typeIdx + 1];

  const raddrIdx = parts.indexOf("raddr");
  if (raddrIdx >= 0 && parts[raddrIdx + 1]) parsed.relatedAddress = parts[raddrIdx + 1];

  const rportIdx = parts.indexOf("rport");
  if (rportIdx >= 0 && parts[rportIdx + 1]) parsed.relatedPort = parts[rportIdx + 1];

  return parsed;
}

const PeerInspectorPanel: Component<PeerInspectorPanelProps> = (props) => {
  const peerId = () => props.selectedPeer?.peer_id ?? "";

  const relatedEvents = () =>
    props.events.filter((event) => {
      const eventRoom = event.data.room_id;
      if (props.selectedRoomId && eventRoom && eventRoom !== props.selectedRoomId) return false;
      return (
        event.data.peer_id === peerId() ||
        event.data.src === peerId() ||
        event.data.dst === peerId()
      );
    });

  const candidateEvents = () =>
    relatedEvents().filter((event) => event.type === "signal.candidate");

  const eventCounts = () => {
    const counts: Record<string, number> = {};
    for (const event of relatedEvents()) {
      counts[event.type] = (counts[event.type] ?? 0) + 1;
    }
    return Object.entries(counts).sort((a, b) => b[1] - a[1]);
  };

  return (
    <div class="flex flex-col rounded-2xl bg-white/[0.02] border border-white/[0.06] overflow-hidden flex-1 min-h-0">
      <div class="flex items-center justify-between px-4 py-3 border-b border-white/[0.06] shrink-0">
        <div class="flex items-center gap-2">
          <div class="w-1.5 h-1.5 rounded-full bg-indigo-400" />
          <span class="text-xs font-semibold tracking-widest text-white/40 uppercase">Peer Inspector</span>
        </div>
        <Show when={props.selectedPeer}>
          <span class="text-[11px] font-mono text-white/20">
            {candidateEvents().length} ICE events
          </span>
        </Show>
      </div>

      <div class="flex-1 overflow-y-auto p-4 flex flex-col gap-4 scrollbar-thin scrollbar-thumb-white/10 scrollbar-track-transparent">
        <Show
          when={props.selectedPeer}
          fallback={
            <div class="flex flex-col items-center justify-center h-full gap-2 text-white/20">
              <span class="text-sm">Select a peer from Active Rooms</span>
              <span class="text-xs text-white/15">Full event-level details will appear here.</span>
            </div>
          }
        >
          <div class="rounded-xl bg-white/[0.03] border border-white/[0.06] p-3 flex flex-col gap-2">
            <div class="text-[11px] text-white/25 uppercase tracking-wider">Identity</div>
            <div class="grid grid-cols-[90px_1fr] gap-x-2 gap-y-1 text-xs font-mono">
              <span class="text-white/30">room</span>
              <span class="text-white/70 break-all">{props.selectedRoomId}</span>
              <span class="text-white/30">peer</span>
              <span class="text-white/70 break-all">{props.selectedPeer?.peer_id}</span>
              <span class="text-white/30">client</span>
              <span class="text-white/70 break-all">{props.selectedPeer?.client_id}</span>
              <span class="text-white/30">status</span>
              <span class={props.selectedPeer?.connected ? "text-emerald-300" : "text-amber-300"}>
                {props.selectedPeer?.connected ? "connected" : "disconnected"}
              </span>
              <span class="text-white/30">heartbeat</span>
              <span class="text-white/60">{elapsedLabel(props.selectedPeer?.last_heartbeat_ago)}</span>
              <span class="text-white/30">offline</span>
              <span class="text-white/60">{elapsedLabel(props.selectedPeer?.disconnected_ago)}</span>
            </div>
          </div>

          <div class="rounded-xl bg-white/[0.03] border border-white/[0.06] p-3 flex flex-col gap-2">
            <div class="flex items-center justify-between">
              <div class="text-[11px] text-white/25 uppercase tracking-wider">Event Breakdown</div>
              <div class="text-[11px] font-mono text-white/20">{relatedEvents().length} total</div>
            </div>
            <Show
              when={eventCounts().length > 0}
              fallback={<div class="text-xs text-white/30">No events found for this peer.</div>}
            >
              <div class="flex flex-wrap gap-2">
                <For each={eventCounts()}>
                  {([type, count]) => (
                    <span class="text-[10px] font-mono px-2 py-1 rounded bg-white/[0.05] border border-white/[0.06]">
                      <span class="text-white/30">{type}</span> <span class="text-white/70">{count}</span>
                    </span>
                  )}
                </For>
              </div>
            </Show>
          </div>

          <div class="rounded-xl bg-white/[0.03] border border-white/[0.06] p-3 flex flex-col gap-2">
            <div class="flex items-center justify-between">
              <div class="text-[11px] text-white/25 uppercase tracking-wider">ICE Candidates</div>
              <div class="text-[11px] font-mono text-white/20">{candidateEvents().length} seen</div>
            </div>
            <Show
              when={candidateEvents().length > 0}
              fallback={<div class="text-xs text-white/30">No candidate events recorded for this peer yet.</div>}
            >
              <div class="flex flex-col gap-2">
                <For each={candidateEvents()}>
                  {(event) => (
                    <div class="rounded-lg border border-white/[0.06] bg-black/20 p-2">
                      <div class="flex items-center gap-2 text-[10px] font-mono mb-1">
                        <span class="text-white/30">{formatTime(event.timestamp)}</span>
                        <span class="text-indigo-300">#{event.id}</span>
                        <span class="text-white/20">
                          {event.data.src === peerId() ? "outbound" : "inbound"}
                        </span>
                        <span class="text-white/45">
                          {shortId(String(event.data.src ?? ""))} -&gt; {shortId(String(event.data.dst ?? ""))}
                        </span>
                      </div>
                      <Show when={parseIceCandidate(event.data.candidate as string | undefined)}>
                        {(parsed) => (
                          <div class="grid grid-cols-2 gap-1 text-[10px] font-mono mb-2">
                            <span class="text-white/30">ip</span>
                            <span class="text-emerald-300 break-all">{parsed().ip}</span>
                            <span class="text-white/30">port</span>
                            <span class="text-white/55">{parsed().port}</span>
                            <span class="text-white/30">protocol</span>
                            <span class="text-white/55">{parsed().protocol}</span>
                            <span class="text-white/30">type</span>
                            <span class="text-white/55">{parsed().type || "-"}</span>
                            <Show when={parsed().relatedAddress}>
                              <>
                                <span class="text-white/30">raddr</span>
                                <span class="text-white/55 break-all">{parsed().relatedAddress}</span>
                              </>
                            </Show>
                            <Show when={parsed().relatedPort}>
                              <>
                                <span class="text-white/30">rport</span>
                                <span class="text-white/55">{parsed().relatedPort}</span>
                              </>
                            </Show>
                          </div>
                        )}
                      </Show>
                      <pre class="text-[10px] font-mono text-white/55 whitespace-pre-wrap break-all">
                        {stringify(event.data)}
                      </pre>
                    </div>
                  )}
                </For>
              </div>
            </Show>
          </div>

          <div class="rounded-xl bg-white/[0.03] border border-white/[0.06] p-3 flex flex-col gap-2 min-h-40">
            <div class="text-[11px] text-white/25 uppercase tracking-wider">Full Related Events</div>
            <div class="flex flex-col gap-2">
              <For each={relatedEvents()}>
                {(event) => (
                  <div class="rounded-lg border border-white/[0.06] bg-black/20 p-2">
                    <div class="flex items-center gap-2 text-[10px] font-mono mb-1">
                      <span class="text-white/30">{formatTime(event.timestamp)}</span>
                      <span class="text-sky-300">{event.type}</span>
                      <span class="text-white/20 ml-auto">#{event.id}</span>
                    </div>
                    <pre class="text-[10px] font-mono text-white/55 whitespace-pre-wrap break-all">
                      {stringify(event.data)}
                    </pre>
                  </div>
                )}
              </For>
            </div>
          </div>
        </Show>
      </div>
    </div>
  );
};

export default PeerInspectorPanel;
