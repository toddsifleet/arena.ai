import { For, Show, type Component } from "solid-js";
import EventRow from "./EventRow";
import type { EventItem } from "./types";

interface EventLogPanelProps {
  events: EventItem[];
  freshEventId: number | null;
  autoScroll: boolean;
  onToggleAutoScroll: () => void;
  setLogRef: (el: HTMLDivElement) => void;
}

const EventLogPanel: Component<EventLogPanelProps> = (props) => (
  <div class="flex flex-col flex-[3] min-w-0 rounded-2xl bg-white/[0.02] border border-white/[0.06] overflow-hidden">
    <div class="flex items-center justify-between px-4 py-3 border-b border-white/[0.06] shrink-0">
      <div class="flex items-center gap-2">
        <div class="w-1.5 h-1.5 rounded-full bg-sky-400" />
        <span class="text-xs font-semibold tracking-widest text-white/40 uppercase">Event Log</span>
      </div>
      <div class="flex items-center gap-3">
        <span class="text-[11px] font-mono text-white/20">newest first · {props.events.length} shown</span>
        <button
          type="button"
          onClick={props.onToggleAutoScroll}
          class={`text-[10px] px-2 py-0.5 rounded border transition-colors ${
            props.autoScroll
              ? "border-sky-500/40 text-sky-400 bg-sky-400/10"
              : "border-white/10 text-white/25 bg-transparent"
          }`}
        >
          {props.autoScroll ? "auto-scroll on" : "auto-scroll off"}
        </button>
      </div>
    </div>

    <div
      ref={props.setLogRef}
      class="flex-1 overflow-y-auto scrollbar-thin scrollbar-thumb-white/10 scrollbar-track-transparent"
    >
      <Show
        when={props.events.length > 0}
        fallback={
          <div class="flex flex-col items-center justify-center h-full gap-3 text-white/20">
            <svg class="w-8 h-8 opacity-30" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
            </svg>
            <span class="text-sm">Waiting for events…</span>
            <span class="text-xs">Create a room or connect a peer to see activity here.</span>
          </div>
        }
      >
        <For each={props.events}>
          {(event) => <EventRow event={event} fresh={props.freshEventId === event.id} />}
        </For>
      </Show>
    </div>
  </div>
);

export default EventLogPanel;
