import { createEffect, createSignal, Show, type Component } from "solid-js";

interface Props {
  localStream: MediaStream | null;
  remoteStream: MediaStream | null;
  peerDisconnected: boolean;
  roomId: string;
  onCopyLink: () => void;
  copied: boolean;
}

const VideoGrid: Component<Props> = (props) => {
  const [localWaitEl, setLocalWaitEl] = createSignal<HTMLVideoElement | null>(null);
  const [localPipEl, setLocalPipEl] = createSignal<HTMLVideoElement | null>(null);
  const [remoteEl, setRemoteEl] = createSignal<HTMLVideoElement | null>(null);

  createEffect(() => {
    const el = localWaitEl();
    if (el) el.srcObject = props.localStream ?? null;
  });

  createEffect(() => {
    const el = localPipEl();
    if (el) el.srcObject = props.localStream ?? null;
  });

  createEffect(() => {
    const el = remoteEl();
    if (el) el.srcObject = props.remoteStream ?? null;
  });

  return (
    <Show
      when={props.remoteStream}
      fallback={
        <div class="w-full h-full rounded-2xl bg-neutral-950 flex flex-col items-center justify-center gap-5">
          <div class="w-56 rounded-xl overflow-hidden shadow-2xl bg-neutral-900">
            <Show
              when={props.localStream}
              fallback={
                <div class="aspect-video flex items-center justify-center">
                  <span class="text-neutral-700 text-xs">No camera</span>
                </div>
              }
            >
              <div class="aspect-[4/3]">
                <video
                  autoplay
                  muted
                  playsinline
                  ref={setLocalWaitEl}
                  class="w-full h-full object-cover"
                />
              </div>
            </Show>
          </div>

          <Show
            when={props.peerDisconnected}
            fallback={
              <div class="text-center space-y-2">
                <p class="text-neutral-600 text-xs">Waiting for someone to join</p>
                <button
                  type="button"
                  onClick={props.onCopyLink}
                  class="font-mono text-xs text-neutral-500 hover:text-neutral-300 transition-colors border border-neutral-800 hover:border-neutral-600 rounded-lg px-3 py-1.5"
                >
                  {props.copied ? "Link copied!" : "Copy invite link"}
                </button>
              </div>
            }
          >
            <div class="text-center space-y-1.5 px-6 py-4 rounded-2xl bg-neutral-900/60 border border-neutral-800">
              <p class="text-white text-sm font-medium">The other person left</p>
              <p class="text-neutral-500 text-xs">Waiting in case they come back…</p>
            </div>
          </Show>
        </div>
      }
    >
      {/* In-call state — remote fills the tile, local is PIP */}
      <div class="relative w-full h-full rounded-2xl overflow-hidden bg-neutral-950">
        <video
          autoplay
          playsinline
          ref={setRemoteEl}
          class="w-full h-full object-cover"
        />
        <div class="absolute bottom-3 right-3 w-28 rounded-xl overflow-hidden shadow-xl border border-white/5">
          <div class="aspect-video bg-neutral-900">
            <Show when={props.localStream}>
              <video
                autoplay
                muted
                playsinline
                ref={setLocalPipEl}
                class="w-full h-full object-cover"
              />
            </Show>
          </div>
        </div>
      </div>
    </Show>
  );
};

export default VideoGrid;
