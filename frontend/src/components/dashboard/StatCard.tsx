import { Show, type Component } from "solid-js";

interface StatCardProps {
  label: string;
  value: number | string;
  accent: string;
  sublabel?: string;
}

const StatCard: Component<StatCardProps> = (props) => (
  <div class="flex flex-col gap-1 rounded-2xl bg-white/[0.03] border border-white/[0.06] px-5 py-4">
    <span class={`text-3xl font-semibold tabular-nums ${props.accent}`}>{props.value}</span>
    <span class="text-xs font-medium tracking-widest text-white/30 uppercase">{props.label}</span>
    <Show when={props.sublabel}>
      <span class="text-[11px] text-white/20">{props.sublabel}</span>
    </Show>
  </div>
);

export default StatCard;
