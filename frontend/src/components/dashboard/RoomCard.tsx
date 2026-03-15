import { For, type Component } from "solid-js";
import PeerChip from "./PeerChip";
import type { PeerState } from "./types";

interface RoomCardProps {
  roomId: string;
  peers: PeerState[];
}

const RoomCard: Component<RoomCardProps> = (props) => {
  const connected = () => props.peers.filter((p) => p.connected).length;
  return (
    <div class="rounded-2xl bg-white/[0.03] border border-white/[0.06] p-4 flex flex-col gap-3">
      <div class="flex items-center gap-2">
        <div class="w-2 h-2 rounded-full bg-white/20" />
        <span class="text-xs font-mono text-white/50 truncate">{props.roomId}</span>
        <span class="ml-auto text-[10px] text-white/20">
          {connected()}/{props.peers.length} online
        </span>
      </div>
      <div class="flex flex-col gap-1.5">
        <For each={props.peers} fallback={<span class="text-[11px] text-white/20 italic">no peers</span>}>
          {(peer) => <PeerChip peer={peer} />}
        </For>
      </div>
    </div>
  );
};

export default RoomCard;
