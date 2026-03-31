import { Show, createMemo, type Component } from "solid-js";
import type { EventItem, PeerState } from "./types";
import { formatTime, shortId } from "./utils";

interface MediaFlowPanelProps {
  selectedRoomId: string | null;
  selectedPeerId: string | null;
  roomPeers: PeerState[];
  events: EventItem[];
}

function isFlowEvent(type: string): boolean {
  return type === "signal.offer" || type === "signal.answer" || type === "signal.candidate";
}

type ParsedCandidate = {
  protocol: string;
  ip: string;
  port: string;
  type: string;
  relatedAddress?: string;
  relatedPort?: string;
};

function parseIceCandidate(candidate: string | undefined): ParsedCandidate | null {
  if (!candidate) return null;
  const parts = candidate.trim().split(/\s+/);
  if (parts.length < 8 || !parts[0].startsWith("candidate:")) return null;

  const parsed: ParsedCandidate = {
    protocol: parts[2] ?? "",
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

const MediaFlowPanel: Component<MediaFlowPanelProps> = (props) => {
  const roomEvents = createMemo(() =>
    props.events.filter(
      (event) => event.data.room_id === props.selectedRoomId && isFlowEvent(event.type),
    ),
  );

  const peerIds = createMemo(() => {
    const known = props.roomPeers.map((peer) => peer.peer_id);
    if (known.length >= 2) return known.slice(0, 2);

    for (const event of roomEvents()) {
      const src = typeof event.data.src === "string" ? event.data.src : null;
      const dst = typeof event.data.dst === "string" ? event.data.dst : null;
      if (src && !known.includes(src)) known.push(src);
      if (dst && !known.includes(dst)) known.push(dst);
      if (known.length >= 2) break;
    }
    return known.slice(0, 2);
  });

  const leftPeerId = createMemo(() => peerIds()[0] ?? null);
  const rightPeerId = createMemo(() => peerIds()[1] ?? null);

  const leftToRightEvents = createMemo(() => {
    const left = leftPeerId();
    const right = rightPeerId();
    if (!left || !right) return [];
    return roomEvents().filter((event) => event.data.src === left && event.data.dst === right);
  });

  const rightToLeftEvents = createMemo(() => {
    const left = leftPeerId();
    const right = rightPeerId();
    if (!left || !right) return [];
    return roomEvents().filter((event) => event.data.src === right && event.data.dst === left);
  });

  const lastLeftToRight = createMemo(() => leftToRightEvents()[0] ?? null);
  const lastRightToLeft = createMemo(() => rightToLeftEvents()[0] ?? null);
  const leftToRightCandidates = createMemo(() =>
    leftToRightEvents()
      .filter((event) => event.type === "signal.candidate")
      .map((event) => ({
        event,
        parsed: parseIceCandidate(
          typeof event.data.candidate === "string" ? (event.data.candidate as string) : undefined,
        ),
      }))
      .filter((item): item is { event: EventItem; parsed: ParsedCandidate } => Boolean(item.parsed)),
  );
  const rightToLeftCandidates = createMemo(() =>
    rightToLeftEvents()
      .filter((event) => event.type === "signal.candidate")
      .map((event) => ({
        event,
        parsed: parseIceCandidate(
          typeof event.data.candidate === "string" ? (event.data.candidate as string) : undefined,
        ),
      }))
      .filter((item): item is { event: EventItem; parsed: ParsedCandidate } => Boolean(item.parsed)),
  );

  const latestLeftToRightCandidate = createMemo(() => leftToRightCandidates()[0] ?? null);
  const latestRightToLeftCandidate = createMemo(() => rightToLeftCandidates()[0] ?? null);
  const leftToRightUsesTurn = createMemo(() =>
    leftToRightCandidates().some((item) => item.parsed.type.toLowerCase() === "relay"),
  );
  const rightToLeftUsesTurn = createMemo(() =>
    rightToLeftCandidates().some((item) => item.parsed.type.toLowerCase() === "relay"),
  );
  const roomUsesTurn = createMemo(() => leftToRightUsesTurn() || rightToLeftUsesTurn());
  const selectedSide = createMemo(() => {
    const selected = props.selectedPeerId;
    if (!selected) return null;
    if (selected === leftPeerId()) return "left";
    if (selected === rightPeerId()) return "right";
    return null;
  });

  return (
    <div class="flex flex-col rounded-2xl bg-white/[0.02] border border-white/[0.06] overflow-hidden min-h-0">
      <div class="flex items-center justify-between px-4 py-3 border-b border-white/[0.06] shrink-0">
        <div class="flex items-center gap-2">
          <div class="w-1.5 h-1.5 rounded-full bg-cyan-400" />
          <span class="text-xs font-semibold tracking-widest text-white/40 uppercase">Media Traffic Path</span>
        </div>
        <Show when={props.selectedRoomId}>
          <span class="text-[11px] font-mono text-white/25">{shortId(props.selectedRoomId ?? "")}</span>
        </Show>
      </div>

      <div class="flex-1 p-4 min-h-0 overflow-y-auto scrollbar-thin scrollbar-thumb-white/10 scrollbar-track-transparent">
        <Show
          when={props.selectedRoomId}
          fallback={
            <div class="h-full flex flex-col items-center justify-center gap-2 text-white/20">
              <span class="text-sm">Select a peer in Active Rooms</span>
              <span class="text-xs text-white/15">Traffic flow for that room appears here.</span>
            </div>
          }
        >
          <Show
            when={leftPeerId() && rightPeerId()}
            fallback={
              <div class="h-full flex flex-col items-center justify-center gap-2 text-white/20">
                <span class="text-sm">Waiting for two peers</span>
                <span class="text-xs text-white/15">Flow renders once both endpoints are known.</span>
              </div>
            }
          >
            <div class="h-full grid grid-cols-[1fr_auto_1fr] items-center gap-3">
              <div
                class={
                  `rounded-xl border px-3 py-2 ${selectedSide() === "left" ? "border-cyan-300/60 bg-cyan-400/10" : "border-white/[0.08] bg-white/[0.03]"}`
                }
              >
                <div class="text-[10px] uppercase tracking-wider text-white/35">peer_1</div>
                <div class="text-xs font-mono text-white/80 break-all">{leftPeerId()}</div>
              </div>

              <div class="w-[220px] max-w-full">
                <svg viewBox="0 0 220 92" class="w-full h-[92px]">
                  <defs>
                    <marker id="arrow-right" markerWidth="8" markerHeight="8" refX="6" refY="4" orient="auto">
                      <path d="M0,0 L8,4 L0,8 z" fill="rgba(56, 189, 248, 0.9)" />
                    </marker>
                    <marker id="arrow-left" markerWidth="8" markerHeight="8" refX="2" refY="4" orient="auto">
                      <path d="M8,0 L0,4 L8,8 z" fill="rgba(167, 139, 250, 0.9)" />
                    </marker>
                  </defs>
                  <line x1="28" y1="25" x2="192" y2="25" stroke="rgba(56, 189, 248, 0.65)" stroke-width="2.4" marker-end="url(#arrow-right)" />
                  <line x1="192" y1="67" x2="28" y2="67" stroke="rgba(167, 139, 250, 0.65)" stroke-width="2.4" marker-end="url(#arrow-left)" />
                  <text x="110" y="16" text-anchor="middle" class="fill-cyan-200 text-[9px] font-mono">
                    {leftToRightEvents().length} events
                  </text>
                  <text x="110" y="58" text-anchor="middle" class="fill-violet-200 text-[9px] font-mono">
                    {rightToLeftEvents().length} events
                  </text>
                </svg>
                <div class="grid grid-cols-2 gap-2 text-[10px] font-mono">
                  <div class="rounded-md border border-cyan-400/20 bg-cyan-400/5 px-2 py-1">
                    <div class="text-cyan-200/80">peer_1 -&gt; peer_2</div>
                    <div class="text-white/45">
                      {lastLeftToRight() ? formatTime(lastLeftToRight()!.timestamp) : "no traffic"}
                    </div>
                  </div>
                  <div class="rounded-md border border-violet-400/20 bg-violet-400/5 px-2 py-1">
                    <div class="text-violet-200/80">peer_2 -&gt; peer_1</div>
                    <div class="text-white/45">
                      {lastRightToLeft() ? formatTime(lastRightToLeft()!.timestamp) : "no traffic"}
                    </div>
                  </div>
                </div>
                <div class="mt-2 rounded-md border border-white/[0.08] bg-black/20 px-2 py-1 text-[10px] font-mono flex items-center justify-between">
                  <span class="text-white/40">TURN involved</span>
                  <span class={roomUsesTurn() ? "text-amber-300" : "text-emerald-300"}>
                    {roomUsesTurn() ? "yes (relay seen)" : "no relay observed"}
                  </span>
                </div>
              </div>

              <div
                class={
                  `rounded-xl border px-3 py-2 ${selectedSide() === "right" ? "border-violet-300/60 bg-violet-400/10" : "border-white/[0.08] bg-white/[0.03]"}`
                }
              >
                <div class="text-[10px] uppercase tracking-wider text-white/35">peer_2</div>
                <div class="text-xs font-mono text-white/80 break-all">{rightPeerId()}</div>
              </div>
            </div>

            <div class="mt-3 grid grid-cols-2 gap-3">
              <div class="rounded-lg border border-cyan-400/20 bg-cyan-400/5 p-2 text-[10px] font-mono">
                <div class="flex items-center justify-between mb-1">
                  <span class="text-cyan-200/90">peer_1 -&gt; peer_2 path</span>
                  <span class={leftToRightUsesTurn() ? "text-amber-300" : "text-emerald-300"}>
                    {leftToRightUsesTurn() ? "TURN relay" : "direct candidate"}
                  </span>
                </div>
                <Show
                  when={latestLeftToRightCandidate()}
                  fallback={<div class="text-white/45">No candidate details seen yet.</div>}
                >
                  {(item) => (
                    <div class="grid grid-cols-[72px_1fr] gap-y-1 gap-x-2">
                      <span class="text-white/35">type</span>
                      <span class="text-white/80">{item().parsed.type || "-"}</span>
                      <span class="text-white/35">protocol</span>
                      <span class="text-white/80">{item().parsed.protocol || "-"}</span>
                      <span class="text-white/35">address</span>
                      <span class="text-white/80 break-all">
                        {item().parsed.ip}:{item().parsed.port}
                      </span>
                      <span class="text-white/35">related</span>
                      <span class="text-white/70 break-all">
                        {item().parsed.relatedAddress
                          ? `${item().parsed.relatedAddress}:${item().parsed.relatedPort ?? "-"}`
                          : "-"}
                      </span>
                      <span class="text-white/35">last event</span>
                      <span class="text-white/55">{formatTime(item().event.timestamp)}</span>
                    </div>
                  )}
                </Show>
              </div>

              <div class="rounded-lg border border-violet-400/20 bg-violet-400/5 p-2 text-[10px] font-mono">
                <div class="flex items-center justify-between mb-1">
                  <span class="text-violet-200/90">peer_2 -&gt; peer_1 path</span>
                  <span class={rightToLeftUsesTurn() ? "text-amber-300" : "text-emerald-300"}>
                    {rightToLeftUsesTurn() ? "TURN relay" : "direct candidate"}
                  </span>
                </div>
                <Show
                  when={latestRightToLeftCandidate()}
                  fallback={<div class="text-white/45">No candidate details seen yet.</div>}
                >
                  {(item) => (
                    <div class="grid grid-cols-[72px_1fr] gap-y-1 gap-x-2">
                      <span class="text-white/35">type</span>
                      <span class="text-white/80">{item().parsed.type || "-"}</span>
                      <span class="text-white/35">protocol</span>
                      <span class="text-white/80">{item().parsed.protocol || "-"}</span>
                      <span class="text-white/35">address</span>
                      <span class="text-white/80 break-all">
                        {item().parsed.ip}:{item().parsed.port}
                      </span>
                      <span class="text-white/35">related</span>
                      <span class="text-white/70 break-all">
                        {item().parsed.relatedAddress
                          ? `${item().parsed.relatedAddress}:${item().parsed.relatedPort ?? "-"}`
                          : "-"}
                      </span>
                      <span class="text-white/35">last event</span>
                      <span class="text-white/55">{formatTime(item().event.timestamp)}</span>
                    </div>
                  )}
                </Show>
              </div>
            </div>
          </Show>
        </Show>
      </div>
    </div>
  );
};

export default MediaFlowPanel;
