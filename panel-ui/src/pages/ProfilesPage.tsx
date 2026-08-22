import { useCallback, useEffect, useState } from "react";
import { useOutletContext } from "react-router-dom";
import { Button } from "../components/Button";
import type { ShellOutlet } from "../components/Shell";
import { cultApi, humanizeError, type ServerRecord } from "../lib/api";

type Profile = {
  name: string;
  description?: string;
  keys?: number;
  values?: Record<string, unknown>;
};

const inputCls =
  "mt-1.5 w-full rounded-md border border-border bg-oled-elev px-3 py-2 text-[13px] text-text outline-none focus:border-neon/40";
const labelCls = "block text-[13px] font-medium text-text";

export function ProfilesPage() {
  const { setFlash } = useOutletContext<ShellOutlet>();
  const [servers, setServers] = useState<ServerRecord[]>([]);
  const [profiles, setProfiles] = useState<Profile[]>([]);
  const [captureName, setCaptureName] = useState("");
  const [captureServer, setCaptureServer] = useState("");
  const [applyProfile, setApplyProfile] = useState("");
  const [applyServer, setApplyServer] = useState("");
  const [mode, setMode] = useState("merge");
  const [diffOut, setDiffOut] = useState("");
  const [busy, setBusy] = useState(false);

  const refresh = useCallback(async () => {
    const [srv, listed] = await Promise.all([
      cultApi.servers(),
      cultApi.command("config.profile.list"),
    ]);
    const rows = (srv.servers || []).map((r) => r.server);
    setServers(rows);
    setCaptureServer((prev) => prev || rows[0]?.server_id || "");
    setApplyServer((prev) => prev || rows[0]?.server_id || "");

    const raw = listed.data?.profiles;
    const list: Profile[] = Array.isArray(raw)
      ? raw.map((p) => {
          const row = p as Profile;
          const keys =
            typeof row.keys === "number"
              ? row.keys
              : row.values
                ? Object.keys(row.values).length
                : 0;
          return { ...row, keys };
        })
      : [];
    setProfiles(list);
    setApplyProfile((prev) => prev || list[0]?.name || "");
  }, []);

  useEffect(() => {
    let alive = true;
    (async () => {
      try {
        await refresh();
      } catch (e) {
        if (alive) setFlash({ msg: humanizeError(e), ok: false });
      }
    })();
    return () => {
      alive = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- initial load only
  }, []);

  async function capture(e: React.FormEvent) {
    e.preventDefault();
    if (!captureName.trim() || !captureServer) return;
    setBusy(true);
    try {
      await cultApi.command("config.profile.capture", {
        name: captureName.trim(),
        server_id: captureServer,
      }, captureServer);
      setFlash({ msg: "Profile captured", ok: true });
      setCaptureName("");
      await refresh();
    } catch (err) {
      setFlash({ msg: humanizeError(err), ok: false });
    } finally {
      setBusy(false);
    }
  }

  async function previewDiff() {
    if (!applyProfile || !applyServer) return null;
    const res = await cultApi.command(
      "config.profile.apply",
      {
        name: applyProfile,
        server_id: applyServer,
        mode,
        dry_run: true,
      },
      applyServer,
    );
    const data = res.data || {};
    setDiffOut(JSON.stringify(data.changes || {}, null, 2));
    return data;
  }

  async function apply(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    try {
      const preview = await previewDiff();
      const changes = (preview?.changes as Record<string, unknown>) || {};
      const count = Object.keys(changes).length;
      if (!count) {
        setFlash({ msg: "No changes to apply", ok: true });
        return;
      }
      if (!window.confirm(`Apply ${count} change(s)?`)) return;
      await cultApi.command(
        "config.profile.apply",
        {
          name: applyProfile,
          server_id: applyServer,
          mode,
          confirm: true,
        },
        applyServer,
      );
      setFlash({ msg: "Profile applied", ok: true });
    } catch (err) {
      setFlash({ msg: humanizeError(err), ok: false });
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-5">
      <div>
        <h1 className="m-0 text-[22px] font-semibold tracking-tight">Config profiles</h1>
        <p className="m-0 mt-1.5 text-[13px] text-muted">
          Reusable server.properties snapshots. Diff before apply.
        </p>
      </div>

      <section className="cf-panel max-w-2xl space-y-3 p-5">
        <h2 className="m-0 text-[13px] font-semibold">Capture</h2>
        <form className="space-y-3" onSubmit={capture}>
          <label className={labelCls}>
            Profile name
            <input
              className={inputCls}
              required
              placeholder="production"
              value={captureName}
              onChange={(e) => setCaptureName(e.target.value)}
            />
          </label>
          <label className={labelCls}>
            From server
            <select
              className={inputCls}
              required
              value={captureServer}
              onChange={(e) => setCaptureServer(e.target.value)}
            >
              {servers.length === 0 && <option value="">No servers</option>}
              {servers.map((s) => (
                <option key={s.server_id} value={s.server_id}>
                  {s.name} ({s.server_id})
                </option>
              ))}
            </select>
          </label>
          <Button variant="primary" type="submit" disabled={busy || !servers.length}>
            Capture current properties
          </Button>
        </form>
      </section>

      <section className="cf-panel max-w-2xl space-y-3 p-5">
        <h2 className="m-0 text-[13px] font-semibold">Apply</h2>
        <form className="space-y-3" onSubmit={apply}>
          <label className={labelCls}>
            Profile
            <select
              className={inputCls}
              required
              value={applyProfile}
              onChange={(e) => setApplyProfile(e.target.value)}
            >
              {profiles.length === 0 && <option value="">No profiles yet</option>}
              {profiles.map((p) => (
                <option key={p.name} value={p.name}>
                  {p.name} ({p.keys ?? 0} keys)
                </option>
              ))}
            </select>
          </label>
          <label className={labelCls}>
            Target server
            <select
              className={inputCls}
              required
              value={applyServer}
              onChange={(e) => setApplyServer(e.target.value)}
            >
              {servers.map((s) => (
                <option key={s.server_id} value={s.server_id}>
                  {s.name}
                </option>
              ))}
            </select>
          </label>
          <label className={labelCls}>
            Mode
            <select className={inputCls} value={mode} onChange={(e) => setMode(e.target.value)}>
              <option value="merge">merge</option>
              <option value="replace">replace</option>
            </select>
          </label>
          <div className="flex flex-wrap gap-2">
            <Button
              variant="ghost"
              type="button"
              disabled={busy || !profiles.length}
              onClick={async () => {
                try {
                  await previewDiff();
                } catch (err) {
                  setFlash({ msg: humanizeError(err), ok: false });
                }
              }}
            >
              Preview diff
            </Button>
            <Button variant="primary" type="submit" disabled={busy || !profiles.length}>
              Apply with confirm
            </Button>
          </div>
        </form>
        <pre className="min-h-[3rem] overflow-auto rounded-md border border-border bg-oled p-3 font-mono text-[12px] text-text-dim whitespace-pre-wrap">
          {diffOut || " "}
        </pre>
      </section>

      <section className="cf-panel max-w-2xl p-5">
        <h2 className="m-0 text-[13px] font-semibold">Saved profiles</h2>
        {profiles.length === 0 ? (
          <p className="m-0 mt-3 text-[13px] text-muted">No profiles yet. Capture from a server above.</p>
        ) : (
          <ul className="m-0 mt-3 list-none space-y-2 p-0">
            {profiles.map((p) => (
              <li key={p.name} className="rounded-md border border-border bg-card-2/40 px-3 py-2">
                <div className="text-[13px] font-medium">{p.name}</div>
                <div className="text-[12px] text-muted">{p.keys ?? 0} keys</div>
                {p.description && <div className="mt-0.5 text-[12px] text-muted">{p.description}</div>}
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
