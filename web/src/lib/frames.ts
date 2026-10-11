// In-tab bus for live frames. The WebSocket client (lib/live.ts) publishes server frames here; mock mode
// publishes the frames the server would send, so every screen refreshes the same way in both modes.
import type { WsFrame } from "./types";

type Listener = (frame: WsFrame) => void;
const listeners = new Set<Listener>();

export function subscribeFrames(fn: Listener): () => void {
  listeners.add(fn);
  return () => {
    listeners.delete(fn);
  };
}

export function publishFrame(frame: WsFrame): void {
  for (const fn of [...listeners]) {
    try {
      fn(frame);
    } catch {
      /* one failing listener must not stop the others */
    }
  }
}
