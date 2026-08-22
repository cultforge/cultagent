import { Link } from "react-router-dom";
import { normalizeState } from "../lib/api";
import { formatUptime, isRunning, type FleetRow } from "../lib/servers";
import { Button } from "./Button";
import { ScopeBadge } from "./ScopeBadge";
import { StatusChip } from "./Status";

type Props = {
  rows: FleetRow[];
  busyId?: string | null;
  onAction: (id: string, action: "start" | "stop" | "restart") => void;
  onSelect?: (id: string) => void;
  selectedId?: string | null;
};

export function FleetTable({ rows, busyId, onAction, onSelect, selectedId }: Props) {
  return (
    <>
      <div className="cf-panel hidden overflow-hidden md:block">
        <table className="w-full border-collapse text-left text-[13px]">
          <thead className="border-b border-border bg-card-2/50 text-[11px] uppercase tracking-wider text-muted">
            <tr>
              <th className="px-4 py-3 font-medium">Server</th>
              <th className="px-4 py-3 font-medium">Status</th>
              <th className="px-4 py-3 font-medium">Players</th>
              <th className="px-4 py-3 font-medium">Uptime</th>
              <th className="px-4 py-3 font-medium">Port</th>
              <th className="px-4 py-3 font-medium text-right">Actions</th>
            </tr>
          </thead>
          <tbody>
            {rows.map(({ server, status }) => {
              const state = normalizeState(status.state);
              const running = isRunning(state);
              const busy = busyId === server.server_id;
              const selected = selectedId === server.server_id;
              return (
                <tr
                  key={server.server_id}
                  className={[
                    "border-t border-border/80 transition",
                    selected ? "bg-neon/5" : "hover:bg-card-2/40",
                  ].join(" ")}
                >
                  <td className="px-4 py-3">
                    <button
                      type="button"
                      className="text-left font-medium text-text hover:text-neon"
                      onClick={() => onSelect?.(server.server_id)}
                    >
                      {server.name}
                    </button>
                    <div className="mt-0.5 flex flex-wrap items-center gap-1.5 text-[12px] text-muted">
                      <ScopeBadge server={server} />
                      <span>
                        {server.loader || "—"}
                        {server.minecraft_version ? ` · ${server.minecraft_version}` : ""}
                      </span>
                    </div>
                  </td>
                  <td className="px-4 py-3">
                    <StatusChip state={state} />
                  </td>
                  <td className="px-4 py-3 tabular-nums text-text-dim">
                    {status.players ?? 0}
                    {status.max_players != null ? ` / ${status.max_players}` : ""}
                  </td>
                  <td className="px-4 py-3 tabular-nums text-text-dim">
                    {running ? formatUptime(status.uptime_seconds) : "—"}
                  </td>
                  <td className="px-4 py-3 font-mono text-text-dim">:{server.port}</td>
                  <td className="px-4 py-3">
                    <div className="flex justify-end gap-1.5">
                      {running ? (
                        <>
                          <Button
                            variant="danger"
                            disabled={busy}
                            onClick={() => onAction(server.server_id, "stop")}
                          >
                            Stop
                          </Button>
                          <Button
                            disabled={busy}
                            onClick={() => onAction(server.server_id, "restart")}
                          >
                            Restart
                          </Button>
                        </>
                      ) : (
                        <Button
                          variant="primary"
                          disabled={busy}
                          onClick={() => onAction(server.server_id, "start")}
                        >
                          Start
                        </Button>
                      )}
                      <Button href={`/panel/servers/${server.server_id}`}>Open</Button>
                    </div>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      <div className="space-y-2 md:hidden">
        {rows.map(({ server, status }) => {
          const state = normalizeState(status.state);
          const running = isRunning(state);
          const busy = busyId === server.server_id;
          const selected = selectedId === server.server_id;
          return (
            <div
              key={server.server_id}
              className={[
                "cf-panel p-4",
                selected ? "border-neon/30" : "",
              ].join(" ")}
            >
              <button
                type="button"
                className="flex w-full items-start justify-between gap-3 text-left"
                onClick={() => onSelect?.(server.server_id)}
              >
                <div className="min-w-0">
                  <div className="font-medium text-text">{server.name}</div>
                  <p className="m-0 mt-1 flex flex-wrap items-center gap-1.5 text-[12px] text-muted">
                    <ScopeBadge server={server} />
                    <span>
                      {server.loader || "—"} · :{server.port}
                    </span>
                  </p>
                </div>
                <StatusChip state={state} />
              </button>
              <div className="mt-3 flex flex-wrap gap-2">
                {running ? (
                  <>
                    <Button
                      variant="danger"
                      disabled={busy}
                      onClick={() => onAction(server.server_id, "stop")}
                    >
                      Stop
                    </Button>
                    <Button
                      disabled={busy}
                      onClick={() => onAction(server.server_id, "restart")}
                    >
                      Restart
                    </Button>
                  </>
                ) : (
                  <Button
                    variant="primary"
                    disabled={busy}
                    onClick={() => onAction(server.server_id, "start")}
                  >
                    Start
                  </Button>
                )}
                <Link
                  to={`/servers/${server.server_id}`}
                  className="inline-flex items-center rounded-md border border-border bg-card-2 px-3 py-1.5 text-[13px] text-text"
                >
                  Open
                </Link>
              </div>
            </div>
          );
        })}
      </div>
    </>
  );
}
