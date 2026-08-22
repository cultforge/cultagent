import { useCallback, useEffect, useState } from "react";
import { useOutletContext, useParams } from "react-router-dom";
import { Button } from "../components/Button";
import type { ServerOutlet } from "../layouts/ServerLayout";
import { cultApi, humanizeError, type BackupItem } from "../lib/api";

function fmtSize(n?: number) {
  if (n == null) return "—";
  if (n > 1024 * 1024) return `${(n / (1024 * 1024)).toFixed(1)} MB`;
  if (n > 1024) return `${Math.round(n / 1024)} KB`;
  return `${n} B`;
}

export function BackupsPage() {
  const { serverId = "" } = useParams();
  const { setFlash } = useOutletContext<ServerOutlet>();
  const [items, setItems] = useState<BackupItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    const res = await cultApi.backups(serverId);
    setItems(res.backups || []);
  }, [serverId]);

  useEffect(() => {
    let alive = true;
    (async () => {
      try {
        await load();
      } catch (e) {
        if (alive) setFlash({ msg: humanizeError(e), ok: false });
      } finally {
        if (alive) setLoading(false);
      }
    })();
    return () => {
      alive = false;
    };
  }, [load, setFlash]);

  async function create() {
    setBusy(true);
    try {
      await cultApi.backupCreate(serverId);
      setFlash({ msg: "Backup created", ok: true });
      await load();
    } catch (e) {
      setFlash({ msg: humanizeError(e), ok: false });
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <h2 className="m-0 text-[13px] font-semibold">Backups</h2>
          <p className="m-0 mt-0.5 text-[12px] text-muted">Zip snapshots of this server folder.</p>
        </div>
        <Button variant="primary" disabled={busy} onClick={create}>
          Create backup
        </Button>
      </div>

      {loading ? (
        <p className="text-text-dim">Loading…</p>
      ) : !items.length ? (
        <div className="cf-panel px-6 py-10 text-center text-[13px] text-text-dim">
          No backups yet. Create one before making risky changes.
        </div>
      ) : (
        <div className="cf-panel overflow-hidden">
          <table className="w-full border-collapse text-left text-[13px]">
            <thead className="border-b border-border bg-card-2/50 text-[11px] uppercase tracking-wider text-muted">
              <tr>
                <th className="px-4 py-3 font-medium">Name</th>
                <th className="px-4 py-3 font-medium">Size</th>
                <th className="px-4 py-3 font-medium">Created</th>
              </tr>
            </thead>
            <tbody>
              {items.map((b) => (
                <tr key={b.path} className="border-t border-border/80">
                  <td className="px-4 py-3 font-medium">{b.name}</td>
                  <td className="px-4 py-3 tabular-nums text-text-dim">{fmtSize(b.size)}</td>
                  <td className="px-4 py-3 font-mono text-[12px] text-muted">
                    {b.mtime ? new Date(b.mtime).toLocaleString() : "—"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
