import { useEffect, useState, type ReactNode } from "react";
import { Link, NavLink, Outlet, useMatch } from "react-router-dom";
import { cultApi, flatMetrics, normalizeState } from "../lib/api";
import { useFleet } from "../hooks/useFleet";
import { isRunning } from "../lib/servers";
import { ScopeBadge } from "./ScopeBadge";
import { IconBuilds, IconCloud, IconGrid, IconNetwork, IconProfiles, IconServer, IconSystem } from "./Icons";
import { StatusDot } from "./Status";

function SideNav({
  to,
  external,
  end,
  icon,
  children,
}: {
  to: string;
  external?: boolean;
  end?: boolean;
  icon: ReactNode;
  children: ReactNode;
}) {
  const base =
    "flex items-center gap-2.5 rounded-md px-2.5 py-2 text-[13px] font-medium transition-colors w-full";

  if (external) {
    return (
      <a href={to} className={`${base} text-text-dim hover:bg-card-2 hover:text-text`}>
        <span className="text-muted">{icon}</span>
        <span className="flex-1 text-left">{children}</span>
      </a>
    );
  }

  return (
    <NavLink
      to={to}
      end={end}
      className={({ isActive }) =>
        [
          base,
          isActive
            ? "bg-card-2 text-text ring-1 ring-border"
            : "text-text-dim hover:bg-card-2/70 hover:text-text",
        ].join(" ")
      }
    >
      {({ isActive }) => (
        <>
          <span className={isActive ? "text-neon" : "text-muted"}>{icon}</span>
          <span className="flex flex-1 items-center gap-2 text-left">{children}</span>
        </>
      )}
    </NavLink>
  );
}

function NavGroup({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="mb-4">
      <p className="mb-1 px-2.5 text-[11px] font-medium uppercase tracking-wider text-muted">
        {label}
      </p>
      <div className="flex flex-col gap-0.5">{children}</div>
    </div>
  );
}

export function Shell() {
  const matchNested = useMatch({ path: "/servers/:serverId/*", end: false });
  const matchExact = useMatch("/servers/:serverId");
  const serverId = matchNested?.params.serverId || matchExact?.params.serverId;
  const [menuOpen, setMenuOpen] = useState(false);
  const { rows } = useFleet(12000);
  const [host, setHost] = useState({
    name: "node",
    status: "…",
    cpu: null as number | null,
    mem: null as number | null,
  });
  const [flash, setFlash] = useState<{ msg: string; ok: boolean } | null>(null);

  useEffect(() => {
    let alive = true;
    async function refresh() {
      try {
        const [s, metricsRaw] = await Promise.all([
          cultApi.status(),
          cultApi.metrics().catch(() => null),
        ]);
        if (!alive) return;
        const id = (s.identity as Record<string, unknown>) || {};
        const m = flatMetrics(metricsRaw);
        setHost({
          name: String(id.display_name || "node"),
          status: normalizeState(id.status || "?"),
          cpu: m.cpu_percent ?? null,
          mem: m.memory_percent ?? null,
        });
      } catch {
        if (alive) setHost((h) => ({ ...h, status: "offline" }));
      }
    }
    refresh();
    const t = setInterval(refresh, 8000);
    return () => {
      alive = false;
      clearInterval(t);
    };
  }, []);

  useEffect(() => {
    if (!flash) return;
    const t = setTimeout(() => setFlash(null), 2800);
    return () => clearTimeout(t);
  }, [flash]);

  useEffect(() => {
    setMenuOpen(false);
  }, [serverId]);

  const online =
    host.status === "online" || host.status === "registered" || host.status === "active";
  const onlineCount = rows.filter((r) => isRunning(r.status.state)).length;

  return (
    <div className="flex min-h-full bg-oled">
      <button
        type="button"
        className="fixed left-3 top-3 z-50 rounded-md border border-border bg-card px-2.5 py-1.5 text-xs font-medium text-text-dim shadow-sm lg:hidden"
        onClick={() => setMenuOpen((v) => !v)}
      >
        Menu
      </button>
      {menuOpen && (
        <button
          type="button"
          className="fixed inset-0 z-30 bg-black/70 lg:hidden"
          aria-label="Close menu"
          onClick={() => setMenuOpen(false)}
        />
      )}

      <aside
        className={[
          "z-40 flex w-[240px] shrink-0 flex-col border-r border-border bg-oled-elev",
          "fixed inset-y-0 left-0 lg:static lg:translate-x-0",
          menuOpen ? "translate-x-0" : "-translate-x-full lg:translate-x-0",
        ].join(" ")}
      >
        <div className="flex h-14 items-center gap-2.5 border-b border-border px-4">
          <Link to="/dashboard" className="flex items-center gap-2.5 text-text hover:text-text">
            <img src="/static/img/logo-disc.png" alt="" className="h-6 w-6 object-contain" />
            <span className="text-[15px] font-semibold tracking-tight">
              Cult<span className="text-neon">Forge</span>
            </span>
          </Link>
        </div>

        <nav className="flex-1 overflow-y-auto p-3">
          <NavGroup label="Operations">
            <SideNav to="/dashboard" end icon={<IconGrid size={16} />}>
              Dashboard
            </SideNav>
            <SideNav to="/servers" end icon={<IconServer size={16} />}>
              Servers
              {rows.length > 0 && (
                <span className="ml-auto rounded bg-card-2 px-1.5 py-0.5 text-[10px] font-medium tabular-nums text-muted">
                  {onlineCount}/{rows.length}
                </span>
              )}
            </SideNav>
          </NavGroup>
          <NavGroup label="Infrastructure">
            <SideNav to="/network" icon={<IconNetwork size={16} />}>
              Network
            </SideNav>
            <SideNav to="/builds" icon={<IconBuilds size={16} />}>
              Builds
            </SideNav>
            <SideNav to="/system" icon={<IconSystem size={16} />}>
              System
            </SideNav>
            <SideNav to="/cloud" icon={<IconCloud size={16} />}>
              Cloud
            </SideNav>
            <SideNav to="/profiles" icon={<IconProfiles size={16} />}>
              Profiles
            </SideNav>
          </NavGroup>

          {rows.length > 0 && (
            <NavGroup label="Fleet">
              {rows.slice(0, 10).map(({ server, status }) => (
                <NavLink
                  key={server.server_id}
                  to={`/servers/${server.server_id}`}
                  className={({ isActive }) =>
                    [
                      "flex items-center gap-2 rounded-md px-2.5 py-1.5 text-[13px] transition-colors",
                      isActive
                        ? "bg-card-2 text-text ring-1 ring-border"
                        : "text-text-dim hover:bg-card-2/70 hover:text-text",
                    ].join(" ")
                  }
                >
                  <StatusDot state={status.state} />
                  <span className="min-w-0 flex-1 truncate">{server.name}</span>
                  <ScopeBadge server={server} className="hidden xl:inline-flex" />
                </NavLink>
              ))}
            </NavGroup>
          )}
        </nav>

        <div className="border-t border-border p-3">
          <Link
            to="/servers/new"
            className="flex items-center justify-center rounded-md bg-neon/90 px-3 py-2 text-[13px] font-semibold text-black transition hover:bg-neon"
          >
            New server
          </Link>
        </div>
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex h-14 shrink-0 items-center gap-4 border-b border-border bg-oled-elev/90 px-4 backdrop-blur-sm lg:px-6">
          <div className="flex min-w-0 items-center gap-2 text-[13px]">
            <span
              className={[
                "inline-flex h-2 w-2 shrink-0 rounded-full",
                online ? "bg-ok" : "bg-danger",
              ].join(" ")}
              title={host.status}
            />
            <span className="truncate font-medium text-text">{host.name}</span>
            <span className="hidden text-muted sm:inline">· {host.status}</span>
          </div>
          <div className="ml-auto flex items-center gap-4 font-mono text-[12px] text-muted">
            {host.cpu != null && (
              <span className="hidden sm:inline">
                CPU <span className="text-text-dim">{Math.round(host.cpu)}%</span>
              </span>
            )}
            {host.mem != null && (
              <span className="hidden sm:inline">
                MEM <span className="text-text-dim">{Math.round(host.mem)}%</span>
              </span>
            )}
            <span className="rounded-md border border-border bg-card px-2 py-1 text-[11px] uppercase tracking-wide">
              Live
            </span>
          </div>
        </header>

        <main className="min-h-0 flex-1 overflow-auto px-4 py-5 lg:px-8 lg:py-7">
          <div className="mx-auto max-w-[1120px]">
            {flash && (
              <div
                className={[
                  "mb-5 rounded-md border px-3.5 py-2.5 text-[13px]",
                  flash.ok
                    ? "border-ok/30 bg-ok/10 text-ok"
                    : "border-danger/30 bg-danger/10 text-danger",
                ].join(" ")}
                role="status"
              >
                {flash.msg}
              </div>
            )}
            <Outlet context={{ setFlash }} />
          </div>
        </main>
      </div>
    </div>
  );
}

export type ShellOutlet = {
  setFlash: (f: { msg: string; ok: boolean } | null) => void;
};
