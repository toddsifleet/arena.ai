import { Show, type Component } from "solid-js";
import type { PeerState } from "./types";
import { elapsedLabel, shortId } from "./utils";

interface PeerChipProps {
  peer: PeerState;
  selected?: boolean;
  onSelect?: (peerId: string) => void;
}

const PeerChip: Component<PeerChipProps> = (props) => (
  <button
    type="button"
    onClick={() => props.onSelect?.(props.peer.peer_id)}
    class={`w-full text-left flex items-center gap-3 rounded-xl border px-3 py-2.5 transition-colors ${
      props.selected
        ? "bg-sky-500/10 border-sky-400/40"
        : "bg-white/[0.04] border-white/[0.06] hover:bg-white/[0.06]"
    }`}
  >
    <span
      class={`shrink-0 w-2 h-2 rounded-full ${props.peer.connected ? "bg-emerald-400 shadow-[0_0_6px_rgba(52,211,153,0.7)]" : "bg-amber-400/60"}`}
    />
    <div class="flex flex-col min-w-0">
      <span class="text-xs font-mono text-white/70 truncate">{shortId(props.peer.peer_id)}&hellip;</span>
      <span class="text-[10px] font-mono text-white/25 truncate">
        client {shortId(props.peer.client_id)}&hellip;
      </span>
    </div>
    <div class="ml-auto shrink-0 text-right">
      <Show
        when={props.peer.connected}
        fallback={
          <div class="flex flex-col items-end">
            <span class="text-[10px] text-amber-400/70">offline</span>
            <span class="text-[10px] text-white/20">{elapsedLabel(props.peer.disconnected_ago)}</span>
          </div>
        }
      >
        <div class="flex flex-col items-end">
          <span class="text-[10px] text-emerald-400/70">online</span>
          <span class="text-[10px] text-white/20">hb {elapsedLabel(props.peer.last_heartbeat_ago)}</span>
        </div>
      </Show>
    </div>
  </button>
);

export default PeerChip;
