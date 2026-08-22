import { useState } from "react";
import { useOutletContext, useParams } from "react-router-dom";
import { Button } from "../components/Button";
import { StatusChip } from "../components/Status";
import type { ServerOutlet } from "../layouts/ServerLayout";
import { cultApi, humanizeError } from "../lib/api";

export function AdminPage() {
  const { serverId = "" } = useParams();
  const { setFlash, detail, refresh, busy, setBusy } = useOutletContext<ServerOutlet>();
  const [eulaBusy, setEulaBusy] = useState(false);
  const server = detail?.server;
  const status = detail?.status;

  async function act(action: "start" | "stop" | "restart") {
    setBusy(true);
    try {
      await cultApi.action(serverId, action);
      setFlash({ msg: `${action} requested`, ok: true });
      await refresh();
    } catch (e) {
      setFlash({ msg: humanizeError(e), ok: false });
    } finally {
      setBusy(false);
    }
  }

  async function acceptEula() {
    setEulaBusy(true);
    try {
      await cultApi.acceptEula(serverId);
      setFlash({ msg: "EULA accepted", ok: true });
    } catch (e) {
      setFlash({ msg: humanizeError(e), ok: false });
    } finally {
      setEulaBusy(false);
    }
  }

  if (!server || !status) return null;

  const launch =
    server.execution_command ||
    `java ${server.jvm_args || "-Xms1G -Xmx2G"} -jar ${server.executable || "server.jar"} nogui`;

  return (
    <div className="space-y-4">
      <div className="cf-panel p-5">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h2 className="m-0 text-[13px] font-semibold">Controls</h2>
            <p className="m-0 mt-1 text-[12px] text-muted">Process and EULA actions for this instance.</p>
          </div>
          <StatusChip state={status.state} />
        </div>
        <div className="mt-4 flex flex-wrap gap-2">
          <Button variant="primary" disabled={busy} onClick={() => act("start")}>
            Start
          </Button>
          <Button variant="danger" disabled={busy} onClick={() => act("stop")}>
            Stop
          </Button>
          <Button disabled={busy} onClick={() => act("restart")}>
            Restart
          </Button>
          <Button disabled={eulaBusy} onClick={acceptEula}>
            Accept EULA
          </Button>
        </div>
      </div>

      <div className="cf-panel p-5">
        <h2 className="m-0 text-[13px] font-semibold">Launch command</h2>
        <pre className="mt-3 overflow-auto rounded-md border border-border bg-oled p-3 font-mono text-[12px] text-text-dim whitespace-pre-wrap">
          {launch}
        </pre>
      </div>

      <div className="grid gap-3 sm:grid-cols-2">
        <div className="cf-panel p-4">
          <div className="text-[11px] uppercase tracking-wider text-muted">Path</div>
          <div className="mt-1 break-all font-mono text-[12px] text-text-dim">{server.path}</div>
        </div>
        <div className="cf-panel p-4">
          <div className="text-[11px] uppercase tracking-wider text-muted">Port / PID</div>
          <div className="mt-1 font-mono text-[13px] text-text">
            :{server.port} · {status.pid ?? "—"}
          </div>
        </div>
        <div className="cf-panel p-4">
          <div className="text-[11px] uppercase tracking-wider text-muted">Auto-start</div>
          <div className="mt-1 text-[13px]">{server.auto_start ? "Enabled" : "Disabled"}</div>
        </div>
        <div className="cf-panel p-4">
          <div className="text-[11px] uppercase tracking-wider text-muted">Crash restart</div>
          <div className="mt-1 text-[13px]">{server.auto_restart ? "Enabled" : "Disabled"}</div>
        </div>
      </div>
    </div>
  );
}
