import { useState } from "react";
import { Link, useOutletContext } from "react-router-dom";
import { Button } from "../components/Button";
import { FleetTable } from "../components/FleetTable";
import { PageHeader } from "../components/PageHeader";
import type { ShellOutlet } from "../components/Shell";
import { useFleet } from "../hooks/useFleet";
import { cultApi } from "../lib/api";

export function ServersPage() {
  const { setFlash } = useOutletContext<ShellOutlet>();
  const { rows, loading, refresh } = useFleet(10000);
  const [busyId, setBusyId] = useState<string | null>(null);

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

  return (
    <div className="space-y-4">
      <PageHeader
        title="Servers"
        subtitle="Local Minecraft fleet on this machine."
        actions={
          <Button variant="primary" href="/panel/servers/new">
            New server
          </Button>
        }
      />

      {loading ? (
        <p className="text-text-dim">Loading…</p>
      ) : !rows.length ? (
        <div className="cf-panel p-10 text-center text-[13px] text-text-dim">
          No servers yet.{" "}
          <Link to="/servers/new" className="text-neon">
            Create one
          </Link>{" "}
          or run <code className="font-mono text-xs text-text">cf-agent server-clone ?</code>
        </div>
      ) : (
        <FleetTable rows={rows} busyId={busyId} onAction={act} />
      )}
    </div>
  );
}
