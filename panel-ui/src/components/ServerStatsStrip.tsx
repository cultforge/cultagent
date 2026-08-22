import type { ReactNode } from "react";
import { normalizeState, type JoinInfo, type ServerRecord, type ServerStatus } from "../lib/api";
import { formatUptime, isRunning } from "../lib/servers";
import { StatusChip } from "./Status";

type Props = {
  server: ServerRecord;
  status: ServerStatus;
  join?: JoinInfo | null;
  uptimeLabel?: string;
  modCount?: number;
};

function Stat({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="min-w-[7.5rem]">
      <div className="text-[11px] font-medium uppercase tracking-wider text-muted">{label}</div>
      <div className="mt-1 text-[13px] text-text">{children}</div>
    </div>
  );
}

export function ServerStatsStrip({ server, status, join, uptimeLabel, modCount }: Props) {
  const state = normalizeState(status.state);
  const running = isRunning(state);

  return (
    <section className="cf-panel px-5 py-4">
      <div className="flex flex-wrap items-start gap-x-8 gap-y-4">
        <Stat label="Status">
          <StatusChip state={state} />
        </Stat>
        <Stat label="Uptime">
          {running ? uptimeLabel || formatUptime(status.uptime_seconds) : "—"}
        </Stat>
        <Stat label="Players">
          <span className="tabular-nums">
            {status.players ?? 0}
            {status.max_players != null ? ` / ${status.max_players}` : ""}
          </span>
        </Stat>
        <Stat label="Type">
          {server.loader || "—"}
          {server.minecraft_version ? (
            <span className="text-text-dim"> · {server.minecraft_version}</span>
          ) : null}
        </Stat>
        <Stat label="Port">
          <span className="font-mono">:{server.port}</span>
          {join?.provider ? <span className="text-muted"> · {join.provider}</span> : null}
        </Stat>
        {modCount != null && (
          <Stat label="Mods">
            <span className="tabular-nums">{modCount}</span>
          </Stat>
        )}
        <Stat label="PID">
          <span className="font-mono tabular-nums">{status.pid ?? "—"}</span>
        </Stat>
      </div>
    </section>
  );
}
