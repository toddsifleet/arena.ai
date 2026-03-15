import type { Component } from "solid-js";
import type { WsStatus } from "./types";

interface ConnectionBadgeProps {
  status: WsStatus;
}

const ConnectionBadge: Component<ConnectionBadgeProps> = (props) => {
  const cfg = () => {
    if (props.status === "connected") return { dot: "bg-emerald-400 animate-pulse", text: "text-emerald-400", label: "Live" };
    if (props.status === "connecting") return { dot: "bg-amber-400 animate-pulse", text: "text-amber-400", label: "Connecting…" };
    return { dot: "bg-red-500", text: "text-red-400", label: "Disconnected" };
  };
  return (
    <div class="flex items-center gap-1.5">
      <span class={`w-1.5 h-1.5 rounded-full ${cfg().dot}`} />
      <span class={`text-xs font-medium ${cfg().text}`}>{cfg().label}</span>
    </div>
  );
};

export default ConnectionBadge;
