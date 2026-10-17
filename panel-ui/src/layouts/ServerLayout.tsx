import { useCallback, useEffect, useState } from "react";
import { Link, Outlet, useOutletContext, useParams } from "react-router-dom";
import { cultApi, humanizeError, type ServerDetail } from "../lib/api";
import type { ShellOutlet } from "../components/Shell";
import { ScopeBadge } from "../components/ScopeBadge";
import { PageHeader } from "../components/PageHeader";
import { ServerActions } from "../components/ServerActions";
import { ServerStatsStrip } from "../components/ServerStatsStrip";
import { ServerTabs } from "../components/ServerTabs";
import { runServerAction } from "../lib/actionLatency";

export type ServerOutlet = ShellOutlet & {
  detail: ServerDetail | null;
  refresh: () => Promise<void>;
  busy: boolean;
  setBusy: (v: boolean) => void;
};

export function ServerLayout() {
  const { serverId = "" } = useParams();
  const { setFlash } = useOutletContext<ShellOutlet>();
  const [detail, setDetail] = useState<ServerDetail | null>(null);
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async () => {
    const d = await cultApi.server(serverId);
    setDetail(d);
  }, [serverId]);

  useEffect(() => {
    let alive = true;
    (async () => {
      try {
        await refresh();
      } catch (e) {
        if (alive) setFlash({ msg: humanizeError(e), ok: false });
      } finally {
        if (alive) setLoading(false);
      }
    })();
    const t = setInterval(() => {
      refresh().catch(() => undefined);
    }, 5000);
    return () => {
      alive = false;
      clearInterval(t);
    };
  }, [refresh, setFlash]);

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

  if (loading && !detail) {
    return <p className="text-text-dim">Loading…</p>;
  }
  if (!detail?.server) {
    return <p className="text-danger">Server not found.</p>;
  }

  const { server, status, join, uptime_label, mod_count } = detail;

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2 text-[13px] text-text-dim">
        <Link to="/servers" className="hover:text-neon">
          Servers
        </Link>
        <span className="text-muted">/</span>
        <span className="truncate text-text">{server.name}</span>
      </div>

      <PageHeader
        title={
          <span className="inline-flex flex-wrap items-center gap-2">
            {server.name}
            <ScopeBadge server={server} detailed />
          </span>
        }
        subtitle={<span className="font-mono text-[12px] text-muted">{server.server_id}</span>}
        actions={
          <ServerActions
            state={status.state}
            busy={busy}
            onAction={act}
            extra={
              <Link
                to={`/servers/${serverId}/console`}
                className="inline-flex items-center rounded-md border border-border px-3 py-1.5 text-[13px] text-text-dim transition hover:border-border-soft hover:text-text"
              >
                Terminal
              </Link>
            }
          />
        }
      />

      <ServerStatsStrip
        server={server}
        status={status}
        join={join}
        uptimeLabel={uptime_label}
        modCount={mod_count}
      />

      <ServerTabs serverId={serverId} />

      <Outlet context={{ setFlash, detail, refresh, busy, setBusy } as ServerOutlet} />
    </div>
  );
}
