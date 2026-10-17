import { useEffect, useRef, useState } from "react";
import { useOutletContext, useParams } from "react-router-dom";
import { Button } from "../components/Button";
import { ConsoleInput } from "../components/ConsoleInput";
import { ConsoleLog } from "../components/ConsoleLog";
import { useConsoleWs } from "../hooks/useConsoleWs";
import type { ServerOutlet } from "../layouts/ServerLayout";
import { humanizeError } from "../lib/api";

export function TerminalPage() {
  const { serverId = "" } = useParams();
  const { setFlash } = useOutletContext<ServerOutlet>();
  const [cmd, setCmd] = useState("");
  const [sending, setSending] = useState(false);
  const preRef = useRef<HTMLDivElement>(null);
  const { lines, transport, sendCommand, refresh } = useConsoleWs(serverId);

  useEffect(() => {
    const el = preRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [lines]);

  async function send(command: string) {
    setSending(true);
    try {
      await sendCommand(command);
      setCmd("");
    } catch (err) {
      setFlash({ msg: humanizeError(err), ok: false });
    } finally {
      setSending(false);
    }
  }

  return (
    <div className="cf-panel flex h-[min(70vh,640px)] min-w-0 flex-col overflow-hidden p-4">
      <div className="mb-3 flex shrink-0 items-center justify-between gap-3">
        <div>
          <h2 className="m-0 text-[13px] font-semibold">Terminal</h2>
          <p className="m-0 mt-0.5 text-[11px] text-muted">
            Tab completes · ↑ history ·{" "}
            <span className={transport === "ws" ? "text-neon" : "text-muted"}>
              {transport === "ws" ? "live WebSocket" : transport === "poll" ? "HTTP poll fallback" : "connecting…"}
            </span>
          </p>
        </div>
        <Button variant="ghost" onClick={() => refresh().catch(() => undefined)}>
          Refresh
        </Button>
      </div>
      <ConsoleLog
        ref={preRef}
        lines={lines}
        empty="(no output yet — start the server to see logs)"
      />
      <div className="mt-3">
        <ConsoleInput value={cmd} onChange={setCmd} onSubmit={send} disabled={sending} />
      </div>
    </div>
  );
}
