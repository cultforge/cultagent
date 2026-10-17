import { useState } from "react";
import { useOutletContext, useParams } from "react-router-dom";
import { Button } from "../components/Button";
import { StatusChip } from "../components/Status";
import type { ServerOutlet } from "../layouts/ServerLayout";
import { cultApi, humanizeError, type LivePlayer } from "../lib/api";
import { runServerAction } from "../lib/actionLatency";

export function AdminPage() {
  const { serverId = "" } = useParams();
  const { setFlash, detail, refresh, busy, setBusy } = useOutletContext<ServerOutlet>();
  const [eulaBusy, setEulaBusy] = useState(false);
  const [playerBusy, setPlayerBusy] = useState<string | null>(null);
  const server = detail?.server;
  const status = detail?.status;
  const players: LivePlayer[] = detail?.players || [];

  async function act(action: "start" | "stop" | "restart") {
    setBusy(true);
    try {
      await runServerAction(action, () => cultApi.action(serverId, action));
      setFlash({
        msg: action === "start" ? "Starting…" : `${action} requested`,
        ok: true,
      });
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

  async function playerAction(kind: "kick" | "ban", name: string) {
    setPlayerBusy(`${kind}:${name}`);
    try {
      const cmd = kind === "kick" ? `kick ${name}` : `ban ${name}`;
      await cultApi.consoleSend(serverId, cmd);
      setFlash({ msg: `${kind} ${name}`, ok: true });
      await refresh();
    } catch (e) {
      setFlash({ msg: humanizeError(e), ok: false });
    } finally {
      setPlayerBusy(null);
    }
  }

  if (!server || !status) return null;

  const launch =
    server.execution_command ||
    `java ${server.jvm_args || "-Xms1G -Xmx2G"} -jar ${server.executable || "server.jar"} nogui`;

  return (
    <div className="cf-spatial-stage space-y-4">
      <div className="cf-panel p-5">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h2 className="m-0 text-[13px] font-semibold">Controls</h2>
            <p className="m-0 mt-1 text-[12px] text-muted">
              Start is immediate · stop/restart briefly delayed to avoid mis-clicks
            </p>
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
        <h2 className="m-0 text-[13px] font-semibold">Online players</h2>
        <p className="m-0 mt-1 text-[12px] text-muted">
          Roster from console presence · kick/ban via server console
        </p>
        {!players.length ? (
          <p className="mt-3 text-[13px] text-muted">No players online (or server not running).</p>
        ) : (
          <ul className="mt-3 m-0 list-none space-y-2 p-0">
            {players.map((p) => {
              const name = p.minecraft_name || p.name || "?";
              return (
                <li
                  key={name}
                  className="flex flex-wrap items-center justify-between gap-2 rounded-md border border-border bg-card-2/40 px-3 py-2"
                >
                  <div>
                    <span className="font-medium">{name}</span>
                    {p.session_stats?.deaths != null && (
                      <span className="ml-2 text-[11px] text-muted">
                        deaths {p.session_stats.deaths}
                      </span>
                    )}
                  </div>
                  <div className="flex gap-2">
                    <Button
                      disabled={playerBusy != null}
                      onClick={() => playerAction("kick", name)}
                    >
                      Kick
                    </Button>
                    <Button
                      variant="danger"
                      disabled={playerBusy != null}
                      onClick={() => playerAction("ban", name)}
                    >
                      Ban
                    </Button>
                  </div>
                </li>
              );
            })}
          </ul>
        )}
      </div>

      <div className="cf-panel p-5">
        <h2 className="m-0 text-[13px] font-semibold">Launch command</h2>
        <pre className="mt-3 overflow-auto rounded-md border border-border bg-oled p-3 font-mono text-[12px] text-text-dim whitespace-pre-wrap">
          {launch}
        </pre>
      </div>

      <div className="grid gap-3 sm:grid-cols-2">
        <div className="cf-panel p-4">
          <h3 className="m-0 text-[12px] font-semibold text-muted">Port</h3>
          <p className="m-0 mt-1 font-mono text-[18px]">{server.port}</p>
        </div>
        <div className="cf-panel p-4">
          <h3 className="m-0 text-[12px] font-semibold text-muted">Path</h3>
          <p className="m-0 mt-1 break-all font-mono text-[12px] text-text-dim">{server.path}</p>
        </div>
      </div>
    </div>
  );
}
