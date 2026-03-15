import type { Component } from "solid-js";
import StatCard from "./StatCard";

interface DashboardStatsRowProps {
  totalRooms: number;
  connectedPeers: number;
  disconnectedPeers: number;
  eventsBuffered: number;
  maxEvents: number;
}

const DashboardStatsRow: Component<DashboardStatsRowProps> = (props) => (
  <div class="grid grid-cols-2 sm:grid-cols-4 gap-3 px-6 pt-5 pb-4 shrink-0">
    <StatCard label="Active Rooms" value={props.totalRooms} accent="text-white" />
    <StatCard
      label="Connected"
      value={props.connectedPeers}
      accent="text-emerald-400"
      sublabel="peers with active WebSocket"
    />
    <StatCard
      label="Reconnecting"
      value={props.disconnectedPeers}
      accent="text-amber-400"
      sublabel="within grace window"
    />
    <StatCard
      label="Events Buffered"
      value={props.eventsBuffered}
      accent="text-sky-400"
      sublabel={`max ${props.maxEvents} in memory`}
    />
  </div>
);

export default DashboardStatsRow;
