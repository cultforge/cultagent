import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";
import { Link, useOutletContext } from "react-router-dom";
import { Button } from "../components/Button";
import { ConsoleInput } from "../components/ConsoleInput";
import { ConsoleLog, lineText } from "../components/ConsoleLog";
import { JoinCard } from "../components/JoinCard";
import { MeterCard } from "../components/MeterCard";
import type { ServerOutlet } from "../layouts/ServerLayout";
import { cultApi, flatMetrics, type FlatMetrics } from "../lib/api";

export function ServerOverviewPage() {
  const { setFlash, detail, refresh } = useOutletContext<ServerOutlet>();
  const [metrics, setMetrics] = useState<FlatMetrics>({});
  const [lines, setLines] = useState<string[]>([]);
  const [cmd, setCmd] = useState("");
  const consoleRef = useRef<HTMLDivElement>(null);
  const serverId = detail?.server.server_id || "";

  const loadConsole = useCallback(async () => {
    if (!serverId) return;
    const [m, cons] = await Promise.all([
      cultApi.metrics().catch(() => null),
      cultApi.consoleRead(serverId, 120).catch(() => null),
    ]);
    setMetrics(flatMetrics(m));
    const raw = cons?.data?.lines || [];
    setLines(raw.map(lineText).filter(Boolean));
  }, [serverId]);

  useEffect(() => {
    loadConsole().catch(() => undefined);
    const t = setInterval(() => {
      loadConsole().catch(() => undefined);
    }, 4000);
    return () => clearInterval(t);
  }, [loadConsole]);

  useEffect(() => {
    const el = consoleRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [lines]);

  async function sendCmd(command: string) {
    if (!command || !serverId) return;
    try {
      await cultApi.consoleSend(serverId, command);
      setCmd("");
      await Promise.all([loadConsole(), refresh()]);
    } catch (err) {
      setFlash({ msg: err instanceof Error ? err.message : String(err), ok: false });
    }
  }

  const [activeWorld, setActiveWorld] = useState<string | null>(null);

  useEffect(() => {
    if (!serverId) return;
    let alive = true;
    cultApi
      .configGet(serverId)
      .then((res) => {
        if (!alive) return;
        setActiveWorld(res.active_world || res.properties?.["level-name"] || null);
      })
      .catch(() => undefined);
    return () => {
      alive = false;
    };
  }, [serverId]);

  if (!detail?.server) return null;

  const { server, join, mod_count } = detail;

  const infoRows: Array<[string, ReactNode]> = [
    ["Type", server.loader || "—"],
    ["Version", server.minecraft_version || "—"],
    ["World", activeWorld ? <span className="font-mono">{activeWorld}</span> : "—"],
    ["Mods", mod_count ?? "—"],
    ["Auto-start", server.auto_start ? "yes" : "no"],
    ["Crash restart", server.auto_restart ? "yes" : "no"],
    [
      "Path",
      <span key="path" className="break-all font-mono text-[12px] text-text-dim">
        {server.path}
      </span>,
    ],
    [
      "ID",
      <span key="id" className="font-mono text-[12px]">
        {server.server_id}
      </span>,
    ],
  ];

  const players = detail.players || [];

  return (
    <div className="cf-spatial-stage space-y-4">
      <div className="cf-spatial-hero grid gap-3 lg:grid-cols-[1.25fr_0.85fr]">
        <div className="grid gap-3 sm:grid-cols-3">
          <MeterCard
            label="Host CPU"
            value={metrics.cpu_percent != null ? `${Math.round(metrics.cpu_percent)}%` : "—"}
            percent={metrics.cpu_percent}
          />
          <MeterCard
            label="Host RAM"
            value={metrics.memory_percent != null ? `${Math.round(metrics.memory_percent)}%` : "—"}
            sub={
              metrics.memory_used_gb != null
                ? `${metrics.memory_used_gb} / ${metrics.memory_total_gb} GB`
                : undefined
            }
            percent={metrics.memory_percent}
          />
          <MeterCard
            label="Disk"
            value={metrics.disk_percent != null ? `${Math.round(metrics.disk_percent)}%` : "—"}
            percent={metrics.disk_percent}
          />
        </div>
        <JoinCard
          join={join}
          port={server.port}
          onCopied={(ok) => setFlash({ msg: ok ? "Address copied" : "Copy failed", ok })}
        />
      </div>

      <div className="grid min-w-0 gap-4 lg:grid-cols-[minmax(200px,0.7fr)_minmax(240px,0.9fr)_minmax(0,1.4fr)]">
        <div className="cf-panel cf-spatial-rail min-w-0 p-4">
          <h2 className="m-0 text-[13px] font-medium">Players</h2>
          <p className="m-0 mt-1 text-[11px] text-muted">Live roster</p>
          {!players.length ? (
            <p className="mt-3 text-[12px] text-muted">None online</p>
          ) : (
            <ul className="mt-3 m-0 list-none space-y-1.5 p-0">
              {players.map((p) => {
                const name = p.minecraft_name || p.name || "?";
                return (
                  <li
                    key={name}
                    className="rounded-md border border-border/80 bg-card-2/30 px-2 py-1.5 text-[12px]"
                  >
                    <span className="font-medium">{name}</span>
                  </li>
                );
              })}
            </ul>
          )}
          <Link
            to={`/servers/${serverId}/admin`}
            className="mt-3 inline-block text-[12px] text-text-dim hover:text-neon"
          >
            Manage →
          </Link>
        </div>

        <div className="cf-panel min-w-0 p-5">
          <h2 className="m-0 text-[13px] font-medium">Server information</h2>
          <dl className="mt-3 grid grid-cols-[6.5rem_minmax(0,1fr)] gap-x-3 gap-y-2.5 text-[13px]">
            {infoRows.map(([label, value]) => (
              <div key={label} className="contents">
                <dt className="self-start text-muted">{label}</dt>
                <dd className="m-0 min-w-0 text-text">{value}</dd>
              </div>
            ))}
          </dl>
          <div className="mt-4 flex flex-wrap gap-2">
            <Button href={`/panel/servers/${serverId}/config`}>Config</Button>
            <Button href={`/panel/servers/${serverId}/mod-config`}>Mod cfg</Button>
            <Button href={`/panel/servers/${serverId}/tuner`}>Tuner</Button>
            <Button href={`/panel/servers/${serverId}/mods`}>Mods</Button>
          </div>
        </div>

        <div className="cf-panel cf-spatial-console flex h-[360px] min-w-0 flex-col overflow-hidden p-5">
          <div className="flex shrink-0 items-center justify-between gap-2">
            <h2 className="m-0 text-[13px] font-medium">Console dock</h2>
            <Link
              to={`/servers/${serverId}/console`}
              className="text-[12px] text-text-dim hover:text-neon"
            >
              Full terminal
            </Link>
          </div>
          <ConsoleLog ref={consoleRef} lines={lines} className="mt-3" />
          <div className="mt-3">
            <ConsoleInput value={cmd} onChange={setCmd} onSubmit={sendCmd} />
          </div>
        </div>
      </div>
    </div>
  );
}
