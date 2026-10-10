"use client";

// Live frames. Real mode: one WebSocket per tab (WS /ws?token=<jwt>, api.md), opened while at least one
// screen listens and reconnecting with backoff; every frame goes to the in-tab bus (lib/frames.ts).
// Mock mode has no socket: api.ts publishes the frames the server would send.
// `useLiveRefresh` reruns a screen's load on matching frames, and polls every 15 s while no socket is open.
import { useEffect, useRef } from "react";
import { liveSocketUrl } from "./api";
import { publishFrame, subscribeFrames } from "./frames";
import type { WsFrame } from "./types";

export const POLL_MS = 15_000;
const MAX_BACKOFF_MS = 30_000;

let socket: WebSocket | null = null;
let open = false;
let users = 0;
let attempt = 0;
let retry: ReturnType<typeof setTimeout> | null = null;

function isFrame(v: unknown): v is WsFrame {
  return typeof v === "object" && v !== null && typeof (v as { type?: unknown }).type === "string" && "data" in v;
}

function connect(): void {
  if (socket || users === 0) return;
  const url = liveSocketUrl();
  if (!url) return; // mock mode or signed out: polling only
  let ws: WebSocket;
  try {
    ws = new WebSocket(url);
  } catch {
    return;
  }
  socket = ws;
  ws.onopen = () => {
    if (socket !== ws) return;
    attempt = 0;
    open = true;
  };
  ws.onmessage = (e: MessageEvent) => {
    if (socket !== ws) return;
    try {
      const frame: unknown = JSON.parse(String(e.data));
      if (isFrame(frame)) publishFrame(frame);
    } catch {
      /* not JSON (e.g. a pong): ignore */
    }
  };
  ws.onclose = (e: CloseEvent) => {
    if (socket !== ws) return; // a socket we already let go of
    socket = null;
    open = false;
    // 4401 = dead token or disabled account, 4403 = role not allowed: the next REST call handles the session.
    if (users === 0 || e.code === 4401 || e.code === 4403) return;
    const delay = Math.min(MAX_BACKOFF_MS, 1000 * 2 ** attempt);
    attempt += 1;
    retry = setTimeout(() => {
      retry = null;
      connect();
    }, delay);
  };
}

/** Keeps the shared socket open while the caller needs it; the returned function lets go (idempotent). */
export function acquireSocket(): () => void {
  users += 1;
  connect();
  let released = false;
  return () => {
    if (released) return;
    released = true;
    users -= 1;
    if (users > 0) return;
    if (retry) clearTimeout(retry);
    retry = null;
    const ws = socket;
    socket = null;
    open = false;
    ws?.close(1000);
  };
}

export const isSocketOpen = (): boolean => open;

export interface LiveRefreshOptions {
  enabled?: boolean;
  pollMs?: number;
  /** "fallback" (default): poll only while no socket is open. "always": for data no frame announces (stock). */
  poll?: "fallback" | "always";
}

/**
 * Calls `refresh(frame)` on every frame whose type is in `types`, and `refresh()` every `pollMs` while the tab
 * is visible and no socket is open (or always). The latest `refresh` is used, so it needn't be memoized.
 */
export function useLiveRefresh(
  refresh: (frame?: WsFrame) => void,
  types: readonly WsFrame["type"][],
  opts: LiveRefreshOptions = {},
): void {
  const { enabled = true, pollMs = POLL_MS, poll = "fallback" } = opts;
  const latest = useRef(refresh);
  useEffect(() => {
    latest.current = refresh;
  });
  const typesKey = types.join(",");
  useEffect(() => {
    if (!enabled) return;
    const wanted = new Set(typesKey ? typesKey.split(",") : []);
    const release = acquireSocket();
    const off = subscribeFrames((f) => {
      if (wanted.has(f.type)) latest.current(f);
    });
    const timer = setInterval(() => {
      if (document.visibilityState !== "visible") return;
      if (poll === "always" || !isSocketOpen()) latest.current();
    }, pollMs);
    return () => {
      off();
      clearInterval(timer);
      release();
    };
  }, [enabled, pollMs, poll, typesKey]);
}
