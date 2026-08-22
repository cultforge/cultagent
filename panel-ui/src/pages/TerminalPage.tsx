import { useCallback, useEffect, useRef, useState } from "react";
import { useOutletContext, useParams } from "react-router-dom";
import { Button } from "../components/Button";
import { ConsoleInput } from "../components/ConsoleInput";
import { ConsoleLog, lineText } from "../components/ConsoleLog";
import type { ServerOutlet } from "../layouts/ServerLayout";
import { cultApi, humanizeError } from "../lib/api";

export function TerminalPage() {
  const { serverId = "" } = useParams();
  const { setFlash } = useOutletContext<ServerOutlet>();
  const [lines, setLines] = useState<string[]>([]);
  const [cmd, setCmd] = useState("");
  const [sending, setSending] = useState(false);
  const preRef = useRef<HTMLDivElement>(null);

  const load = useCallback(async () => {
    const cons = await cultApi.consoleRead(serverId, 250);
    const raw = cons?.data?.lines || [];
    setLines(raw.map(lineText).filter(Boolean));
  }, [serverId]);

  useEffect(() => {
    load().catch((e) => setFlash({ msg: humanizeError(e), ok: false }));
    const t = setInterval(() => {
      load().catch(() => undefined);
    }, 2500);
    return () => clearInterval(t);
  }, [load, setFlash]);

  useEffect(() => {
    const el = preRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [lines]);

  async function send(command: string) {
    setSending(true);
    try {
      await cultApi.consoleSend(serverId, command);
      setCmd("");
      await load();
    } catch (err) {
      setFlash({ msg: humanizeError(err), ok: false });
    } finally {
      setSending(false);
    }
  }

  return (
    <div className="cf-panel flex h-[min(70vh,640px)] min-w-0 flex-col overflow-hidden p-4">
      <div className="mb-3 flex shrink-0 items-center justify-between">
        <div>
          <h2 className="m-0 text-[13px] font-semibold">Terminal</h2>
          <p className="m-0 mt-0.5 text-[11px] text-muted">
            Tab completes like the in-game console · ↑ history
          </p>
        </div>
        <Button variant="ghost" onClick={() => load().catch(() => undefined)}>
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
