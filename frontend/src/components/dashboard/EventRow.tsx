import type { Component } from "solid-js";
import type { EventItem } from "./types";
import { eventStyle, formatTime, renderEventData } from "./utils";

interface EventRowProps {
  event: EventItem;
  fresh: boolean;
}

const EventRow: Component<EventRowProps> = (props) => {
  const style = () => eventStyle(props.event.type);
  return (
    <div
      class={`flex items-start gap-3 px-4 py-2.5 border-b border-white/[0.04] transition-colors duration-700 ${props.fresh ? "bg-white/[0.04]" : ""}`}
    >
      <span class="mt-0.5 shrink-0 text-[11px] font-mono text-white/20 w-20 text-right">
        {formatTime(props.event.timestamp)}
      </span>
      <span class={`mt-1.5 shrink-0 w-1.5 h-1.5 rounded-full ${style().dot}`} />
      <span class={`shrink-0 text-[10px] font-semibold tracking-wider px-1.5 py-0.5 rounded ${style().badge}`}>
        {style().label}
      </span>
      <span class="text-[11px] font-mono text-white/35 truncate leading-relaxed">
        {renderEventData(props.event.data)}
      </span>
      <span class="ml-auto shrink-0 text-[10px] font-mono text-white/15">#{props.event.id}</span>
    </div>
  );
};

export default EventRow;
