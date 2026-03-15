import { For, Show, type Component } from "solid-js";
import RoomCard from "./RoomCard";
import type { PeerState } from "./types";

interface ActiveRoomsPanelProps {
  roomEntries: Array<[string, PeerState[]]>;
}

const ActiveRoomsPanel: Component<ActiveRoomsPanelProps> = (props) => (
  <div class="flex flex-col rounded-2xl bg-white/[0.02] border border-white/[0.06] overflow-hidden flex-1 min-h-0">
    <div class="flex items-center justify-between px-4 py-3 border-b border-white/[0.06] shrink-0">
      <div class="flex items-center gap-2">
        <div class="w-1.5 h-1.5 rounded-full bg-emerald-400" />
        <span class="text-xs font-semibold tracking-widest text-white/40 uppercase">Active Rooms</span>
      </div>
      <span class="text-[11px] font-mono text-white/20">{props.roomEntries.length} rooms</span>
    </div>
    <div class="flex-1 overflow-y-auto p-4 flex flex-col gap-3 scrollbar-thin scrollbar-thumb-white/10 scrollbar-track-transparent">
      <Show
        when={props.roomEntries.length > 0}
        fallback={
          <div class="flex flex-col items-center justify-center h-full gap-2 text-white/20">
            <svg class="w-7 h-7 opacity-30" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1" d="M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 015.356-1.857M7 20v-2c0-.656.126-1.283.356-1.857m0 0a5.002 5.002 0 019.288 0M15 7a3 3 0 11-6 0 3 3 0 016 0zm6 3a2 2 0 11-4 0 2 2 0 014 0zM7 10a2 2 0 11-4 0 2 2 0 014 0z" />
            </svg>
            <span class="text-sm">No active rooms</span>
          </div>
        }
      >
        <For each={props.roomEntries}>
          {([roomId, peers]) => <RoomCard roomId={roomId} peers={peers} />}
        </For>
      </Show>
    </div>
  </div>
);

export default ActiveRoomsPanel;
