import type { Component } from "solid-js";

interface SystemInfoCardProps {
  maxEvents: number;
}

const SystemInfoCard: Component<SystemInfoCardProps> = (props) => (
  <div class="rounded-2xl bg-white/[0.02] border border-white/[0.06] px-5 py-4 shrink-0">
    <div class="flex items-center gap-2 mb-3">
      <div class="w-1.5 h-1.5 rounded-full bg-violet-400" />
      <span class="text-xs font-semibold tracking-widest text-white/40 uppercase">System</span>
    </div>
    <div class="grid grid-cols-2 gap-y-2 text-xs">
      <span class="text-white/30">Heartbeat interval</span>
      <span class="font-mono text-white/50 text-right">5s</span>
      <span class="text-white/30">Heartbeat timeout</span>
      <span class="font-mono text-white/50 text-right">15s</span>
      <span class="text-white/30">Reconnect grace</span>
      <span class="font-mono text-white/50 text-right">30s</span>
      <span class="text-white/30">Max peers / room</span>
      <span class="font-mono text-white/50 text-right">2</span>
      <span class="text-white/30">Event buffer</span>
      <span class="font-mono text-white/50 text-right">{props.maxEvents} events</span>
    </div>
  </div>
);

export default SystemInfoCard;
