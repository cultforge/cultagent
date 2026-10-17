import { useCallback, useEffect, useRef, useState } from "react";
import { lineText } from "../components/ConsoleLog";

type WsMsg = {
  type?: string;
  lines?: unknown[];
  next_seq?: number;
  ok?: boolean;
  error?: string;
  command?: string;
  state?: string;
};

function wsUrl(serverId: string): string {
  const proto = location.protocol === "https:" ? "wss" : "ws";
  return `${proto}://${location.host}/ws/servers/${encodeURIComponent(serverId)}/console`;
}

/**
 * Near-zero-latency console: prefer WebSocket push; HTTP poll fallback.
 */
export function useConsoleWs(serverId: string) {
  const [lines, setLines] = useState<string[]>([]);
  const [transport, setTransport] = useState<"ws" | "poll" | "offline">("offline");
  const wsRef = useRef<WebSocket | null>(null);
  const afterSeq = useRef(0);
  const pollTimer = useRef<number | null>(null);

  const appendLines = useCallback((raw: unknown[]) => {
    const texts = raw
      .map((item) => lineText(item as string | { text?: string }))
      .filter(Boolean) as string[];
    if (!texts.length) return;
    setLines((prev) => {
      const next = prev.concat(texts);
      return next.length > 4000 ? next.slice(-3500) : next;
    });
    for (const item of raw) {
      if (item && typeof item === "object" && "seq" in item) {
        const seq = Number((item as { seq?: number }).seq);
        if (!Number.isNaN(seq)) afterSeq.current = Math.max(afterSeq.current, seq);
      }
    }
  }, []);

  const pollOnce = useCallback(async () => {
    if (!serverId) return;
    try {
      const res = await fetch(
        `/v1/servers/${encodeURIComponent(serverId)}/console?after_seq=${afterSeq.current}&limit=300`,
      );
      const data = await res.json();
      const payload = data.data || data;
      appendLines(payload.lines || []);
      if (payload.next_seq != null) {
        afterSeq.current = Math.max(afterSeq.current, Number(payload.next_seq));
      }
    } catch {
      /* ignore */
    }
  }, [appendLines, serverId]);

  const stopPoll = useCallback(() => {
    if (pollTimer.current != null) {
      window.clearInterval(pollTimer.current);
      pollTimer.current = null;
    }
  }, []);

  const startPoll = useCallback(() => {
    if (pollTimer.current != null) return;
    setTransport("poll");
    void pollOnce();
    pollTimer.current = window.setInterval(() => {
      void pollOnce();
    }, 1500);
  }, [pollOnce]);

  const sendCommand = useCallback(async (command: string) => {
    const ws = wsRef.current;
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({ type: "command", command }));
      return;
    }
    await fetch(`/v1/servers/${encodeURIComponent(serverId)}/console`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ command }),
    });
    await pollOnce();
  }, [pollOnce, serverId]);

  const sendControl = useCallback(
    async (action: "start" | "stop" | "restart") => {
      const ws = wsRef.current;
      if (ws && ws.readyState === WebSocket.OPEN && action === "start") {
        ws.send(JSON.stringify({ type: "control", action: "start", accept_eula: true }));
        return;
      }
      await fetch(`/v1/servers/${encodeURIComponent(serverId)}/${action}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: action === "start" ? JSON.stringify({ accept_eula: true }) : "{}",
      });
    },
    [serverId],
  );

  useEffect(() => {
    if (!serverId) return;
    let closed = false;
    afterSeq.current = 0;
    setLines([]);

    const connect = () => {
      if (closed) return;
      let ws: WebSocket;
      try {
        ws = new WebSocket(wsUrl(serverId));
      } catch {
        startPoll();
        return;
      }
      wsRef.current = ws;
      ws.onopen = () => {
        if (closed) return;
        setTransport("ws");
        stopPoll();
      };
      ws.onmessage = (ev) => {
        let msg: WsMsg;
        try {
          msg = JSON.parse(String(ev.data));
        } catch {
          return;
        }
        if (msg.type === "snapshot" || msg.type === "lines") {
          appendLines(msg.lines || []);
          if (msg.next_seq != null) {
            afterSeq.current = Math.max(afterSeq.current, Number(msg.next_seq));
          }
        }
      };
      ws.onclose = () => {
        wsRef.current = null;
        if (!closed) startPoll();
      };
      ws.onerror = () => {
        try {
          ws.close();
        } catch {
          /* ignore */
        }
      };
    };

    connect();
    return () => {
      closed = true;
      stopPoll();
      try {
        wsRef.current?.close();
      } catch {
        /* ignore */
      }
      wsRef.current = null;
    };
  }, [appendLines, serverId, startPoll, stopPoll]);

  return { lines, transport, sendCommand, sendControl, refresh: pollOnce };
}
