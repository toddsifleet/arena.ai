import type { Component } from "solid-js";
import ConnectionBadge from "./ConnectionBadge";
import type { WsStatus } from "./types";

interface DashboardHeaderProps {
  totalEventsSeen: number;
  wsStatus: WsStatus;
}

const DashboardHeader: Component<DashboardHeaderProps> = (props) => (
  <header class="flex items-center justify-between px-6 py-4 border-b border-white/[0.06] shrink-0">
    <div class="flex items-center gap-4">
      <span class="text-sm font-light tracking-[0.3em] text-white/50 uppercase select-none">
        arena
      </span>
      <span class="text-white/20 text-xs">›</span>
      <span class="text-sm font-medium text-white/80 tracking-wide">Dashboard</span>
    </div>
    <div class="flex items-center gap-6">
      <span class="text-xs text-white/25 font-mono">{props.totalEventsSeen} events logged</span>
      <ConnectionBadge status={props.wsStatus} />
    </div>
  </header>
);

export default DashboardHeader;
