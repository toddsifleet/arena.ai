import { createSignal, Show, type Component } from "solid-js";
import { useNavigate } from "@solidjs/router";
import { createRoom } from "../rtc";

const UUID_RE =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

const LobbyPage: Component = () => {
  const navigate = useNavigate();
  const [input, setInput] = createSignal("");
  const [error, setError] = createSignal<string | null>(null);
  const [creating, setCreating] = createSignal(false);

  const handleCreate = async () => {
    if (creating()) return;
    setError(null);
    setCreating(true);
    try {
      const { roomId } = await createRoom();
      navigate(`/room/${roomId}`);
    } catch {
      setError("Could not create room.");
    } finally {
      setCreating(false);
    }
  };

  const handleJoin = () => {
    const id = input().trim();
    if (!id) return;
    if (!UUID_RE.test(id)) {
      setError("Enter a valid room ID.");
      return;
    }
    setError(null);
    navigate(`/room/${id}`);
  };

  return (
    <div class="min-h-screen bg-black flex items-center justify-center">
      <div class="w-full max-w-xs px-6">
        <div class="text-center mb-12">
          <span class="text-lg font-light tracking-[0.3em] text-white uppercase select-none">
            arena
          </span>
        </div>

        <div class="flex flex-col gap-3">
          <button
            type="button"
            onClick={handleCreate}
            disabled={creating()}
            class="w-full py-3 rounded-xl bg-white text-black text-sm font-medium hover:bg-neutral-100 transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
          >
            {creating() ? "Creating…" : "New room"}
          </button>

          <div class="flex items-center gap-3">
            <div class="flex-1 h-px bg-neutral-800" />
            <span class="text-neutral-600 text-xs">or</span>
            <div class="flex-1 h-px bg-neutral-800" />
          </div>

          <div class="flex gap-2">
            <input
              type="text"
              placeholder="Room ID"
              class="flex-1 rounded-xl bg-neutral-900 border border-neutral-800 px-4 py-3 text-sm text-white placeholder-neutral-600 focus:outline-none focus:border-neutral-600 transition-colors"
              value={input()}
              onInput={(e) => setInput(e.currentTarget.value)}
              onKeyDown={(e) => e.key === "Enter" && handleJoin()}
            />
            <button
              type="button"
              onClick={handleJoin}
              disabled={!input().trim()}
              class="px-5 py-3 rounded-xl bg-neutral-800 text-white text-sm hover:bg-neutral-700 transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
            >
              Join
            </button>
          </div>
        </div>

        <Show when={error()}>
          <p class="mt-4 text-center text-red-400 text-xs">{error()}</p>
        </Show>
        <div class="mt-5 text-center">
          <a href="/dashboard" class="text-xs text-neutral-500 hover:text-neutral-300 transition-colors">
            Open dashboard
          </a>
        </div>
      </div>
    </div>
  );
};

export default LobbyPage;
