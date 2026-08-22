import { useEffect, useState } from "react";
import { useOutletContext } from "react-router-dom";
import { Button } from "../components/Button";
import type { ShellOutlet } from "../components/Shell";
import { cultApi, flatMetrics, humanizeError, type FlatMetrics } from "../lib/api";

function Meter({ value }: { value: number | null | undefined }) {
  const v = Math.max(0, Math.min(100, Number(value ?? 0)));
  const tone = v >= 85 ? "bg-danger" : v >= 65 ? "bg-warn" : "bg-neon";
  return (
    <div className="mt-3 h-1.5 overflow-hidden rounded-full bg-card-2">
      <div className={`h-full rounded-full ${tone}`} style={{ width: `${v}%` }} />
    </div>
  );
}

export function SystemPage() {
  const { setFlash } = useOutletContext<ShellOutlet>();
  const [metrics, setMetrics] = useState<FlatMetrics>({});
  const [raw, setRaw] = useState<Record<string, unknown> | null>(null);
  const [doctor, setDoctor] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let alive = true;
    (async () => {
      try {
        const res = await cultApi.metrics();
        if (!alive) return;
        setRaw(res);
        setMetrics(flatMetrics(res));
      } catch (e) {
        if (alive) setFlash({ msg: humanizeError(e), ok: false });
      }
    })();
    return () => {
      alive = false;
    };
  }, [setFlash]);

  async function runDoctor() {
    setBusy(true);
    setDoctor("Running…");
    try {
      const res = await cultApi.command("node.doctor");
      setDoctor(JSON.stringify(res.data || res, null, 2));
    } catch (e) {
      setDoctor(humanizeError(e));
    } finally {
      setBusy(false);
    }
  }

  const cards = [
    {
      label: "CPU",
      value: metrics.cpu_percent != null ? `${Math.round(metrics.cpu_percent)}%` : "—",
      meter: metrics.cpu_percent,
      sub: null as string | null,
    },
    {
      label: "Memory",
      value: metrics.memory_percent != null ? `${Math.round(metrics.memory_percent)}%` : "—",
      meter: metrics.memory_percent,
      sub:
        metrics.memory_used_gb != null && metrics.memory_total_gb != null
          ? `${metrics.memory_used_gb} / ${metrics.memory_total_gb} GB`
          : null,
    },
    {
      label: "Disk",
      value: metrics.disk_percent != null ? `${Math.round(metrics.disk_percent)}%` : "—",
      meter: metrics.disk_percent,
      sub: null,
    },
  ];

  return (
    <div className="space-y-5">
      <div>
        <h1 className="m-0 text-[22px] font-semibold tracking-tight">System</h1>
        <p className="m-0 mt-1.5 text-[13px] text-muted">Host metrics for this CultAgent machine.</p>
      </div>

      <div className="grid gap-3 sm:grid-cols-3">
        {cards.map((c) => (
          <div key={c.label} className="cf-panel p-4">
            <div className="text-[11px] uppercase tracking-wider text-muted">{c.label}</div>
            <div className="mt-1 text-[28px] font-semibold tabular-nums tracking-tight">{c.value}</div>
            {c.sub && <div className="mt-0.5 text-[12px] text-muted">{c.sub}</div>}
            <Meter value={c.meter} />
          </div>
        ))}
      </div>

      <section className="cf-panel p-5">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h2 className="m-0 text-[13px] font-semibold">Doctor</h2>
            <p className="m-0 mt-1 text-[12px] text-muted">
              Local hardening checks (loopback bind, Java, identity, data dirs).
            </p>
          </div>
          <Button disabled={busy} onClick={runDoctor}>
            Run doctor
          </Button>
        </div>
        {doctor && (
          <pre className="mt-4 max-h-[320px] overflow-auto rounded-md border border-border bg-oled p-3 font-mono text-[12px] text-text-dim whitespace-pre-wrap">
            {doctor}
          </pre>
        )}
      </section>

      <section className="cf-panel p-5">
        <h2 className="m-0 text-[13px] font-semibold">Raw metrics</h2>
        <pre className="mt-3 max-h-[360px] overflow-auto rounded-md border border-border bg-oled p-3 font-mono text-[12px] text-text-dim whitespace-pre-wrap">
          {raw ? JSON.stringify(raw, null, 2) : "Loading…"}
        </pre>
      </section>
    </div>
  );
}
