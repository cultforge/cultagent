import { useEffect, useMemo, useState } from "react";
import { Link, useOutletContext } from "react-router-dom";
import { Button } from "../components/Button";
import { FleetTable } from "../components/FleetTable";
import { JoinCard } from "../components/JoinCard";
import { KpiCard, metricTone } from "../components/KpiCard";
import { PageHeader } from "../components/PageHeader";
import { ScopeBadge } from "../components/ScopeBadge";
import { Section } from "../components/Section";
import type { ShellOutlet } from "../components/Shell";
import { DashboardSkeleton } from "../components/Skeleton";
import { StatusChip } from "../components/Status";
import { useFleet } from "../hooks/useFleet";
import {
  cultApi,
  normalizeState,
  type CloudServiceHealth,
  type DashboardResponse,
  type JoinInfo,
} from "../lib/api";
import { fleetStats, formatUptime, isRunning } from "../lib/servers";
import { IconCpu, IconNetwork, IconPlus, IconServer, IconUsers } from "../components/Icons";

const WORKERS = ["api", "auth", "guilds", "invite"] as const;

function WorkerPill({ name, info }: { name: string; info?: CloudServiceHealth }) {
  const ok = info?.ok === true;
  const known = info != null;
  return (
    <span
      className={[
        "inline-flex items-center gap-1.5 rounded-md border px-2 py-0.5 text-[11px] font-medium",
        !known
          ? "border-border text-muted"
          : ok
            ? "border-ok/30 bg-ok/10 text-ok"
            : "border-danger/30 bg-danger/10 text-danger",
      ].join(" ")}
      title={info?.base || info?.error || name}
    >
      <span
        className={[
          "h-1.5 w-1.5 rounded-full",
          !known ? "bg-muted" : ok ? "bg-ok" : "bg-danger",
        ].join(" ")}
      />
      {name}
    </span>
  );
}

export function DashboardPage() {
  const { setFlash } = useOutletContext<ShellOutlet>();
  const { rows, metrics, loading, error, refresh } = useFleet(8000);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [join, setJoin] = useState<JoinInfo | null>(null);
  const [query, setQuery] = useState("");
  const [focusId, setFocusId] = useState<string | null>(null);
  const [dash, setDash] = useState<DashboardResponse | null>(null);

  useEffect(() => {
    if (error) setFlash({ msg: error, ok: false });
  }, [error, setFlash]);

  useEffect(() => {
    let alive = true;
    (async () => {
      try {
        const d = await cultApi.dashboard();
        if (alive) setDash(d);
      } catch {
        if (alive) setDash(null);
      }
    })();
    const t = setInterval(() => {
      cultApi
        .dashboard()
        .then((d) => {
          if (alive) setDash(d);
        })
        .catch(() => undefined);
    }, 20000);
    return () => {
      alive = false;
      clearInterval(t);
    };
  }, []);

  useEffect(() => {
    if (!rows.length) {
      setFocusId(null);
      return;
    }
    if (!focusId || !rows.some((r) => r.server.server_id === focusId)) {
      setFocusId(rows[0].server.server_id);
    }
  }, [rows, focusId]);

  const primary = rows.find((r) => r.server.server_id === focusId) || rows[0];

  useEffect(() => {
    const id = primary?.server.server_id;
    if (!id) {
      setJoin(null);
      return;
    }
    let alive = true;
    cultApi
      .server(id)
      .then((d) => {
        if (alive) setJoin(d.join || null);
      })
      .catch(() => {
        if (alive) setJoin(null);
      });
    return () => {
      alive = false;
    };
  }, [primary?.server.server_id]);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return rows;
    return rows.filter(({ server, status }) => {
      const hay = [
        server.name,
        server.server_id,
        server.loader,
        server.minecraft_version,
        String(server.port),
        normalizeState(status.state),
      ]
        .filter(Boolean)
        .join(" ")
        .toLowerCase();
      return hay.includes(q);
    });
  }, [rows, query]);

  async function act(id: string, action: "start" | "stop" | "restart") {
    setBusyId(id);
    try {
      await cultApi.action(id, action);
      setFlash({ msg: `${action} requested`, ok: true });
      await refresh();
    } catch (e) {
      setFlash({ msg: e instanceof Error ? e.message : String(e), ok: false });
    } finally {
      setBusyId(null);
    }
  }

  async function copyLogin() {
    try {
      await navigator.clipboard.writeText("cf-agent login");
      setFlash({ msg: "Copied: cf-agent login", ok: true });
    } catch {
      setFlash({ msg: "Copy failed", ok: false });
    }
  }

  if (loading) {
    return <DashboardSkeleton />;
  }

  const identity =
    (dash?.status?.identity as Record<string, unknown> | undefined) || {};
  const registered = Boolean(identity.registered);
  const guildId = (identity.guild_id as string | null | undefined) || null;
  const nodeStatus = String(identity.status || "—");
  const services = dash?.cloud_health || {};
  const needsLogin =
    !registered ||
    Boolean(dash?.guild?.needs_login) ||
    Boolean(dash?.builds?.needs_login);

  const cultForgeStrip = (
    <section className="cf-panel space-y-4 p-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="text-[11px] font-medium uppercase tracking-wider text-muted">
            CultForge
          </div>
          <div className="mt-1 flex flex-wrap items-center gap-2">
            <StatusChip state={nodeStatus} />
            <span className="text-[13px] text-text-dim">
              {registered ? "Linked" : "Local only"}
              {guildId ? (
                <>
                  {" · guild "}
                  <span className="font-mono text-[12px] text-text">{guildId}</span>
                </>
              ) : (
                " · no guild"
              )}
            </span>
          </div>
        </div>
        <div className="flex flex-wrap gap-1.5">
          {WORKERS.map((w) => (
            <WorkerPill key={w} name={w} info={services[w]} />
          ))}
        </div>
      </div>

      {dash?.cloud_warning && (
        <p className="m-0 text-[12px] text-warn">{dash.cloud_warning}</p>
      )}

      <div className="grid gap-2 sm:grid-cols-3">
        <div className="rounded-md border border-border bg-card-2/40 px-3 py-2">
          <div className="text-[11px] text-muted">Local fleet</div>
          <div className="mt-0.5 text-[18px] font-semibold tabular-nums">
            {dash?.local_server_count ?? rows.length}
          </div>
        </div>
        <div className="rounded-md border border-border bg-card-2/40 px-3 py-2">
          <div className="text-[11px] text-muted">Guild servers</div>
          <div className="mt-0.5 text-[18px] font-semibold tabular-nums">
            {dash?.guild?.server_count ?? "—"}
          </div>
        </div>
        <div className="rounded-md border border-border bg-card-2/40 px-3 py-2">
          <div className="text-[11px] text-muted">Guild builds</div>
          <div className="mt-0.5 text-[18px] font-semibold tabular-nums">
            {dash?.builds?.count ?? "—"}
          </div>
        </div>
      </div>

      {needsLogin && (
        <div className="flex flex-wrap items-center justify-between gap-3 rounded-md border border-warn/30 bg-warn/10 px-3 py-2.5 text-[13px] text-warn">
          <span>
            Sign in with CultForge to clone guild servers and deploy builds.{" "}
            <code className="rounded bg-card-2 px-1.5 py-0.5 font-mono text-[12px] text-text">
              cf-agent login
            </code>
          </span>
          <div className="flex gap-2">
            <Button variant="ghost" onClick={copyLogin}>
              Copy command
            </Button>
            <Button href="/panel/cloud">Cloud</Button>
          </div>
        </div>
      )}

      <div className="flex flex-wrap gap-2 border-t border-border pt-3">
        <Button variant="primary" href="/panel/servers/new">
          New server
        </Button>
        <Button href="/panel/servers/new?path=clone">Clone guild</Button>
        <Button href="/panel/servers/new?path=build">Deploy build</Button>
        <Button href="/panel/builds" variant="ghost">
          Builds
        </Button>
        <Button href="/panel/network" variant="ghost">
          Network
        </Button>
        <Button href="/panel/system" variant="ghost">
          System
        </Button>
        <Button href="/panel/cloud" variant="ghost">
          Cloud ops
        </Button>
      </div>
    </section>
  );

  if (!rows.length) {
    return (
      <div className="space-y-5">
        <PageHeader
          title="Dashboard"
          subtitle="Local fleet plus CultForge guild catalog on this host."
        />
        {cultForgeStrip}
        <div className="cf-panel px-8 py-10 text-center">
          <div className="mx-auto mb-4 flex h-12 w-12 items-center justify-center rounded-full border border-border bg-card-2 text-neon">
            <IconPlus size={22} />
          </div>
          <h2 className="m-0 text-lg font-semibold">Create your first server</h2>
          <p className="mx-auto mt-2 max-w-md text-[13px] leading-relaxed text-text-dim">
            Scratch-install a loader, clone a guild catalog server, or deploy a published build —
            then start it and share the join address.
          </p>
          <div className="mt-6 flex flex-wrap justify-center gap-2">
            <Button variant="primary" href="/panel/servers/new?path=scratch">
              Scratch install
            </Button>
            <Button href="/panel/servers/new?path=clone">Clone guild server</Button>
            <Button href="/panel/servers/new?path=build">Deploy build</Button>
          </div>
        </div>
      </div>
    );
  }

  const stats = fleetStats(rows);
  const state = normalizeState(primary.status.state);
  const running = isRunning(state);
  const crashed = rows.filter((r) => normalizeState(r.status.state) === "crashed");
  const cpuTone = metricTone(metrics.cpu_percent);
  const memTone = metricTone(metrics.memory_percent);
  const diskTone = metricTone(metrics.disk_percent);

  return (
    <div className="space-y-6">
      <PageHeader
        title="Dashboard"
        subtitle="CultForge cloud link and this host’s Minecraft fleet."
        actions={
          <div className="flex flex-wrap gap-2">
            <Button href="/panel/network" variant="ghost">
              Network
            </Button>
            <Button variant="primary" href="/panel/servers/new">
              New server
            </Button>
          </div>
        }
      />

      {cultForgeStrip}

      {crashed.length > 0 && (
        <div
          className="flex flex-wrap items-center justify-between gap-3 rounded-md border border-danger/30 bg-danger/10 px-4 py-3 text-[13px] text-danger"
          role="alert"
        >
          <span>
            <strong className="font-semibold">
              {crashed.length} server{crashed.length === 1 ? "" : "s"} crashed
            </strong>
            {" — "}
            {crashed.map((c) => c.server.name).join(", ")}
          </span>
          <Button
            variant="danger"
            disabled={busyId != null}
            onClick={() => act(crashed[0].server.server_id, "start")}
          >
            Restart {crashed[0].server.name}
          </Button>
        </div>
      )}

      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <KpiCard
          label="CPU"
          value={metrics.cpu_percent != null ? `${Math.round(metrics.cpu_percent)}%` : "—"}
          hint={
            metrics.cpu_percent == null
              ? "Waiting for host metrics"
              : metrics.cpu_percent >= 90
                ? "High load"
                : "Host processor"
          }
          percent={metrics.cpu_percent}
          tone={cpuTone}
          icon={<IconCpu size={16} />}
        />
        <KpiCard
          label="Memory"
          value={metrics.memory_percent != null ? `${Math.round(metrics.memory_percent)}%` : "—"}
          hint={
            metrics.memory_used_gb != null
              ? `${metrics.memory_used_gb} / ${metrics.memory_total_gb} GB used`
              : "Host RAM"
          }
          percent={metrics.memory_percent}
          tone={memTone}
        />
        <KpiCard
          label="Disk"
          value={metrics.disk_percent != null ? `${Math.round(metrics.disk_percent)}%` : "—"}
          hint={diskTone === "danger" ? "Running low on space" : "Agent volume"}
          percent={metrics.disk_percent}
          tone={diskTone}
        />
        <KpiCard
          label="Fleet"
          value={`${stats.online}/${stats.total}`}
          hint={
            <span className="inline-flex flex-wrap items-center gap-x-2 gap-y-1">
              <span className="inline-flex items-center gap-1">
                <IconUsers size={12} /> {stats.players} players
              </span>
              <span>·</span>
              <span>{stats.offline} offline</span>
              {stats.crashed > 0 && (
                <>
                  <span>·</span>
                  <span className="text-danger">{stats.crashed} crashed</span>
                </>
              )}
            </span>
          }
          tone={stats.crashed > 0 ? "danger" : stats.online > 0 ? "ok" : "default"}
          icon={<IconServer size={16} />}
        />
      </div>

      <div className="grid gap-4 lg:grid-cols-[minmax(0,1.45fr)_minmax(280px,0.85fr)]">
        <section className="cf-panel p-5">
          <div className="mb-4 flex flex-wrap items-center justify-between gap-2">
            <div className="text-[11px] font-medium uppercase tracking-wider text-muted">
              Focused server
            </div>
            {rows.length > 1 && (
              <select
                value={primary.server.server_id}
                onChange={(e) => setFocusId(e.target.value)}
                className="rounded-md border border-border bg-card-2 px-2.5 py-1.5 text-[12px] text-text outline-none focus:border-neon/40"
                aria-label="Select focused server"
              >
                {rows.map(({ server }) => (
                  <option key={server.server_id} value={server.server_id}>
                    {server.name}
                  </option>
                ))}
              </select>
            )}
          </div>

          <div className="flex flex-wrap items-start justify-between gap-4">
            <div className="min-w-0">
              <div className="flex flex-wrap items-center gap-2.5">
                <h2 className="m-0 truncate text-xl font-semibold tracking-tight">
                  {primary.server.name}
                </h2>
                <ScopeBadge server={primary.server} detailed />
                <StatusChip state={state} />
              </div>
              <p className="mt-1.5 text-[13px] text-text-dim">
                {primary.server.loader || "unknown loader"}
                {primary.server.minecraft_version ? ` · MC ${primary.server.minecraft_version}` : ""}
                {" · "}
                <span className="font-mono">:{primary.server.port}</span>
              </p>
            </div>
            <div className="flex flex-wrap gap-2">
              {running ? (
                <>
                  <Button
                    variant="danger"
                    disabled={busyId === primary.server.server_id}
                    onClick={() => act(primary.server.server_id, "stop")}
                  >
                    Stop
                  </Button>
                  <Button
                    disabled={busyId === primary.server.server_id}
                    onClick={() => act(primary.server.server_id, "restart")}
                  >
                    Restart
                  </Button>
                </>
              ) : (
                <Button
                  variant="primary"
                  disabled={busyId === primary.server.server_id}
                  onClick={() => act(primary.server.server_id, "start")}
                >
                  Start
                </Button>
              )}
              <Button href={`/panel/servers/${primary.server.server_id}`}>Manage</Button>
              <Button
                href={`/panel/servers/${primary.server.server_id}/console`}
                variant="ghost"
              >
                Terminal
              </Button>
            </div>
          </div>

          <div className="mt-5 grid grid-cols-2 gap-3 border-t border-border pt-4 sm:grid-cols-4">
            {(
              [
                [
                  "Players",
                  `${primary.status.players ?? 0}${
                    primary.status.max_players != null ? ` / ${primary.status.max_players}` : ""
                  }`,
                ],
                ["Uptime", running ? formatUptime(primary.status.uptime_seconds) : "—"],
                ["PID", primary.status.pid != null ? String(primary.status.pid) : "—"],
                ["Auto-start", primary.server.auto_start ? "On" : "Off"],
              ] as const
            ).map(([label, value]) => (
              <div key={label}>
                <div className="text-[11px] text-muted">{label}</div>
                <div className="mt-0.5 text-[13px] font-medium tabular-nums text-text">{value}</div>
              </div>
            ))}
          </div>

          <div className="mt-4 flex flex-wrap gap-2 border-t border-border pt-4">
            <Button href={`/panel/servers/${primary.server.server_id}/files`} variant="ghost">
              Files
            </Button>
            <Button href={`/panel/servers/${primary.server.server_id}/backups`} variant="ghost">
              Backups
            </Button>
            <Button href={`/panel/servers/${primary.server.server_id}/mods`} variant="ghost">
              Mods
            </Button>
            <Button href="/panel/network" variant="ghost">
              <IconNetwork size={14} /> Public join
            </Button>
          </div>
        </section>

        <JoinCard
          join={join}
          port={primary.server.port}
          onCopied={(ok) => setFlash({ msg: ok ? "Address copied" : "Copy failed", ok })}
        />
      </div>

      <Section
        title="Fleet"
        description="Start, stop, and open any local server from here."
        action={
          <Link to="/servers" className="text-[12px] text-text-dim hover:text-neon">
            Full list
          </Link>
        }
      >
        <div className="mb-3">
          <label className="sr-only" htmlFor="fleet-search">
            Search servers
          </label>
          <input
            id="fleet-search"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search by name, loader, port, or status…"
            className="w-full max-w-md rounded-md border border-border bg-card px-3 py-2 text-[13px] text-text outline-none placeholder:text-muted focus:border-neon/40"
          />
        </div>
        {filtered.length === 0 ? (
          <div className="cf-panel px-4 py-8 text-center text-[13px] text-text-dim">
            No servers match “{query}”.
          </div>
        ) : (
          <FleetTable
            rows={filtered}
            busyId={busyId}
            onAction={act}
            onSelect={(id) => setFocusId(id)}
            selectedId={primary.server.server_id}
          />
        )}
      </Section>
    </div>
  );
}
