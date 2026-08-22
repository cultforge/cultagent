import { useCallback, useEffect, useState, type ReactNode } from "react";
import { useOutletContext } from "react-router-dom";
import { Button } from "../components/Button";
import type { ShellOutlet } from "../components/Shell";
import { StatusChip } from "../components/Status";
import {
  cultApi,
  humanizeError,
  type CloudManifestResponse,
  type CloudServiceHealth,
} from "../lib/api";

type Identity = {
  registered?: boolean;
  status?: string;
  cloud_node_id?: string | null;
  node_id?: string | null;
  owner_account_id?: string | null;
  guild_id?: string | null;
  display_name?: string | null;
};

type CloudInfo = {
  api_base?: string;
  poll_interval_seconds?: number;
  realtime_enabled?: boolean;
  transport?: {
    mode?: string;
    connected?: boolean;
    ws_path?: string;
  };
};

const WORKERS = ["api", "auth", "guilds", "invite"] as const;

export function CloudPage() {
  const { setFlash } = useOutletContext<ShellOutlet>();
  const [identity, setIdentity] = useState<Identity>({});
  const [cloud, setCloud] = useState<CloudInfo>({});
  const [services, setServices] = useState<Record<string, CloudServiceHealth>>({});
  const [manifest, setManifest] = useState<CloudManifestResponse | null>(null);
  const [updateOut, setUpdateOut] = useState("");
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);

  const refresh = useCallback(async () => {
    const [status, health, man] = await Promise.all([
      cultApi.status(),
      cultApi.cloudHealth().catch(() => ({ ok: true, services: {} as Record<string, CloudServiceHealth> })),
      cultApi.cloudManifest().catch((e) => ({
        ok: false,
        error: humanizeError(e),
        required_ok: false,
      })),
    ]);
    setIdentity((status.identity as Identity) || {});
    setCloud((status.cloud as CloudInfo) || {});
    setServices(health.services || {});
    setManifest(man);
  }, []);

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
    return () => {
      alive = false;
    };
  }, [refresh, setFlash]);

  async function copyLogin() {
    try {
      await navigator.clipboard.writeText("cf-agent login");
      setFlash({ msg: "Copied: cf-agent login", ok: true });
    } catch {
      setFlash({ msg: "Copy failed", ok: false });
    }
  }

  async function runUpdateCheck() {
    setBusy(true);
    setUpdateOut("Checking…");
    try {
      const res = await cultApi.command("node.update.check");
      setUpdateOut(JSON.stringify(res.data || res, null, 2));
    } catch (e) {
      setUpdateOut(humanizeError(e));
    } finally {
      setBusy(false);
    }
  }

  if (loading) return <p className="text-text-dim">Loading cloud link…</p>;

  const transport = cloud.transport || {};
  const wsLive = transport.mode === "websocket" && transport.connected;
  const bases = manifest?.services || {
    api: cloud.api_base,
    auth: undefined,
    invite: undefined,
    guilds: undefined,
  };

  const rows: Array<[string, ReactNode]> = [
    ["Registered", identity.registered ? "yes" : "no"],
    ["Status", <StatusChip key="st" state={identity.status || "—"} />],
    [
      "Node",
      <span key="n" className="font-mono text-[12px] text-text-dim">
        {identity.cloud_node_id || identity.node_id || "—"}
      </span>,
    ],
    [
      "Owner",
      <span key="o" className="font-mono text-[12px] text-text-dim">
        {identity.owner_account_id || "—"}
      </span>,
    ],
    [
      "Guild",
      <span key="g" className="font-mono text-[12px] text-text-dim">
        {identity.guild_id || "none"}
      </span>,
    ],
    [
      "Transport",
      wsLive ? (
        <span key="t" className="inline-flex items-center gap-2">
          <span className="rounded bg-ok/15 px-1.5 py-0.5 text-[11px] font-medium text-ok">
            websocket
          </span>
          <span className="font-mono text-[11px] text-muted">{transport.ws_path || ""}</span>
        </span>
      ) : (
        <span key="t" className="inline-flex items-center gap-2">
          <span className="rounded bg-card-2 px-1.5 py-0.5 text-[11px] font-medium text-muted">
            https poll
          </span>
          <span className="text-[12px] text-muted">every {cloud.poll_interval_seconds ?? "—"}s</span>
        </span>
      ),
    ],
  ];

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="m-0 text-[22px] font-semibold tracking-tight">Cloud ops</h1>
          <p className="m-0 mt-1.5 text-[13px] text-muted">
            Live CultForge workers — api, auth, invite, guilds. Apex cultforge.com is static.
          </p>
        </div>
        <Button onClick={() => refresh().catch((e) => setFlash({ msg: humanizeError(e), ok: false }))}>
          Refresh
        </Button>
      </div>

      {!identity.registered && (
        <section className="cf-panel border-warn/30 bg-warn/5 p-5">
          <h2 className="m-0 text-[13px] font-semibold text-warn">Not linked</h2>
          <p className="m-0 mt-2 text-[13px] text-text-dim">
            Run{" "}
            <code className="rounded bg-card-2 px-1.5 py-0.5 font-mono text-[12px] text-text">
              cf-agent login
            </code>{" "}
            — opens auth.cultforge.com OAuth (loopback), then auto-approves the device on the API.
            Do not paste JWTs. Do not use apex cultforge.com as an approve UI.
          </p>
          <div className="mt-3">
            <Button variant="primary" onClick={copyLogin}>
              Copy login command
            </Button>
          </div>
        </section>
      )}

      <section className="cf-panel p-5">
        <h2 className="m-0 text-[13px] font-semibold">Worker health</h2>
        <div className="mt-3 grid gap-2 sm:grid-cols-2">
          {WORKERS.map((name) => {
            const info = services[name];
            const base = info?.base || bases[name] || "—";
            const ok = info?.ok === true;
            return (
              <div
                key={name}
                className="rounded-md border border-border bg-card-2/40 px-3 py-3"
              >
                <div className="flex items-center justify-between gap-2">
                  <span className="text-[13px] font-medium capitalize">{name}</span>
                  <span
                    className={[
                      "rounded px-1.5 py-0.5 text-[11px] font-medium",
                      info == null
                        ? "bg-card-2 text-muted"
                        : ok
                          ? "bg-ok/15 text-ok"
                          : "bg-danger/15 text-danger",
                    ].join(" ")}
                  >
                    {info == null ? "—" : ok ? "ok" : "down"}
                  </span>
                </div>
                <div className="mt-1 break-all font-mono text-[11px] text-muted">{base}</div>
                {info?.status_code != null && (
                  <div className="mt-1 text-[11px] text-text-dim">HTTP {info.status_code}</div>
                )}
                {info?.error && (
                  <div className="mt-1 text-[11px] text-danger">{info.error}</div>
                )}
              </div>
            );
          })}
        </div>
      </section>

      <section className="cf-panel p-5">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h2 className="m-0 text-[13px] font-semibold">API manifest</h2>
          {manifest?.required_ok != null && (
            <span
              className={[
                "rounded px-2 py-0.5 text-[11px] font-medium",
                manifest.required_ok ? "bg-ok/15 text-ok" : "bg-danger/15 text-danger",
              ].join(" ")}
            >
              {manifest.required_ok ? "required routes ok" : "missing required routes"}
            </span>
          )}
        </div>
        {manifest?.error && (
          <p className="m-0 mt-2 text-[13px] text-danger">{manifest.error}</p>
        )}
        <dl className="mt-3 grid grid-cols-[8rem_minmax(0,1fr)] gap-x-3 gap-y-2 text-[13px]">
          <dt className="text-muted">API base</dt>
          <dd className="m-0 font-mono text-[12px] text-text-dim">{manifest?.api_base || "—"}</dd>
          <dt className="text-muted">Build id</dt>
          <dd className="m-0 font-mono text-[12px] text-text-dim">{manifest?.build_id || "—"}</dd>
          <dt className="text-muted">Agent routes</dt>
          <dd className="m-0 tabular-nums">{manifest?.agent_route_count ?? "—"}</dd>
          <dt className="text-muted">Realtime WS</dt>
          <dd className="m-0 font-mono text-[12px] text-text-dim">
            {manifest?.realtime_ws || (manifest?.realtime_ready ? "ready" : "—")}
          </dd>
        </dl>
        {!!manifest?.missing_required?.length && (
          <div className="mt-3">
            <div className="text-[12px] text-danger">Missing required</div>
            <ul className="mt-1 list-disc pl-5 font-mono text-[11px] text-text-dim">
              {manifest.missing_required.map((r) => (
                <li key={r}>{r}</li>
              ))}
            </ul>
          </div>
        )}
        {manifest?.note && (
          <p className="m-0 mt-3 text-[12px] text-muted">{manifest.note}</p>
        )}
      </section>

      <section className="cf-panel max-w-2xl p-5">
        <h2 className="m-0 text-[13px] font-semibold">Identity</h2>
        <dl className="mt-4 grid grid-cols-[7rem_minmax(0,1fr)] gap-x-3 gap-y-3 text-[13px]">
          {rows.map(([label, value]) => (
            <div key={label} className="contents">
              <dt className="text-muted">{label}</dt>
              <dd className="m-0 min-w-0 text-text">{value}</dd>
            </div>
          ))}
        </dl>
      </section>

      <section className="cf-panel p-5">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h2 className="m-0 text-[13px] font-semibold">Update check</h2>
            <p className="m-0 mt-1 text-[12px] text-muted">
              Cloud version feed only — does not download or install.
            </p>
          </div>
          <Button disabled={busy} onClick={runUpdateCheck}>
            Check updates
          </Button>
        </div>
        {updateOut && (
          <pre className="mt-3 max-h-[240px] overflow-auto rounded-md border border-border bg-oled p-3 font-mono text-[12px] text-text-dim whitespace-pre-wrap">
            {updateOut}
          </pre>
        )}
      </section>
    </div>
  );
}
