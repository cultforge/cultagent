import { useCallback, useEffect, useMemo, useState } from "react";
import { useOutletContext, useParams } from "react-router-dom";
import { Button } from "../components/Button";
import type { ServerOutlet } from "../layouts/ServerLayout";
import { cultApi, humanizeError, type ModItem } from "../lib/api";

export function ModsPage() {
  const { serverId = "" } = useParams();
  const { setFlash } = useOutletContext<ServerOutlet>();
  const [mods, setMods] = useState<ModItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [resolving, setResolving] = useState(false);
  const [query, setQuery] = useState("");

  const loadMods = useCallback(async () => {
    const res = await cultApi.mods(serverId);
    const list = res.data?.mods || res.mods || [];
    setMods(Array.isArray(list) ? list : []);
  }, [serverId]);

  useEffect(() => {
    let alive = true;
    (async () => {
      try {
        await loadMods();
      } catch (e) {
        if (alive) setFlash({ msg: humanizeError(e), ok: false });
      } finally {
        if (alive) setLoading(false);
      }
    })();
    return () => {
      alive = false;
    };
  }, [loadMods, setFlash]);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return mods;
    return mods.filter((m) => {
      const name = String(m.name || m.file || m.filename || "");
      return name.toLowerCase().includes(q);
    });
  }, [mods, query]);

  async function resolveDeps() {
    if (!serverId || resolving) return;
    setResolving(true);
    try {
      const res = await cultApi.command("server.mods.resolve", {}, serverId);
      const data = (res.data || res) as {
        added_count?: number;
        disabled_count?: number;
        failed?: unknown[];
        errors?: unknown[];
        ok?: boolean;
      };
      const added = Number(data.added_count || 0);
      const disabled = Number(data.disabled_count || 0);
      const failed = Array.isArray(data.failed) ? data.failed.length : 0;
      const errors = Array.isArray(data.errors) ? data.errors.length : 0;
      const ok = data.ok !== false && failed === 0 && errors === 0;
      setFlash({
        msg: ok
          ? `Resolved dependencies — added ${added} libraries, disabled ${disabled} client-only jars. Restart the Minecraft server.`
          : `Resolve finished with gaps — added ${added}, disabled ${disabled}, ${failed + errors} failed. Check logs, then retry.`,
        ok,
      });
      await loadMods();
    } catch (e) {
      setFlash({ msg: humanizeError(e), ok: false });
    } finally {
      setResolving(false);
    }
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h2 className="m-0 text-[13px] font-semibold">Mods</h2>
          <p className="m-0 mt-0.5 text-[12px] text-muted">
            {mods.length} jars in this server’s mods folder. Resolve reads the latest
            Forge crash report / latest.log (“mod X requires Y”) and installs those
            libraries from Modrinth.
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Filter mods…"
            className="w-56 rounded-md border border-border bg-card px-3 py-1.5 text-[13px] outline-none focus:border-neon/40"
          />
          <Button variant="primary" disabled={resolving || loading} onClick={() => void resolveDeps()}>
            {resolving ? "Resolving…" : "Resolve dependencies"}
          </Button>
        </div>
      </div>

      {loading ? (
        <p className="text-text-dim">Loading…</p>
      ) : !mods.length ? (
        <div className="cf-panel px-6 py-10 text-center text-[13px] text-text-dim">
          No mods found. Install via guild builds or drop jars into the mods folder.
        </div>
      ) : (
        <div className="grid gap-2 sm:grid-cols-2 xl:grid-cols-3">
          {filtered.map((m, i) => {
            const name = String(m.name || m.file || m.filename || `mod-${i}`);
            const enabled = m.enabled !== false;
            return (
              <div key={name + i} className="cf-panel px-4 py-3">
                <div className="truncate text-[13px] font-medium text-text">{name}</div>
                <div className="mt-1 text-[11px] text-muted">
                  {enabled ? "Installed" : "Disabled (client-only)"}
                  {m.slug ? ` · ${String(m.slug)}` : ""}
                  {m.version_number ? ` ${String(m.version_number)}` : ""}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
