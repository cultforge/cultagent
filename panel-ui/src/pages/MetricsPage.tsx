import { useEffect, useState } from "react";
import { useOutletContext } from "react-router-dom";
import { KpiCard, metricTone } from "../components/KpiCard";
import { ProgressBar } from "../components/ProgressBar";
import type { ServerOutlet } from "../layouts/ServerLayout";
import { cultApi, flatMetrics, humanizeError, type FlatMetrics } from "../lib/api";
import { formatUptime, isRunning } from "../lib/servers";

export function MetricsPage() {
  const { setFlash, detail } = useOutletContext<ServerOutlet>();
  const [metrics, setMetrics] = useState<FlatMetrics>({});

  useEffect(() => {
    let alive = true;
    async function tick() {
      try {
        const raw = await cultApi.metrics();
        if (alive) setMetrics(flatMetrics(raw));
      } catch (e) {
        if (alive) setFlash({ msg: humanizeError(e), ok: false });
      }
    }
    tick();
    const t = setInterval(tick, 5000);
    return () => {
      alive = false;
      clearInterval(t);
    };
  }, [setFlash]);

  const status = detail?.status;
  const running = isRunning(status?.state);

  return (
    <div className="space-y-4">
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <KpiCard
          label="Host CPU"
          value={metrics.cpu_percent != null ? `${Math.round(metrics.cpu_percent)}%` : "—"}
          percent={metrics.cpu_percent}
          tone={metricTone(metrics.cpu_percent)}
        />
        <KpiCard
          label="Host memory"
          value={metrics.memory_percent != null ? `${Math.round(metrics.memory_percent)}%` : "—"}
          hint={
            metrics.memory_used_gb != null
              ? `${metrics.memory_used_gb} / ${metrics.memory_total_gb} GB`
              : undefined
          }
          percent={metrics.memory_percent}
          tone={metricTone(metrics.memory_percent)}
        />
        <KpiCard
          label="Disk"
          value={metrics.disk_percent != null ? `${Math.round(metrics.disk_percent)}%` : "—"}
          percent={metrics.disk_percent}
          tone={metricTone(metrics.disk_percent)}
        />
        <KpiCard
          label="Players"
          value={`${status?.players ?? 0}${status?.max_players != null ? ` / ${status.max_players}` : ""}`}
          hint={running ? `Uptime ${formatUptime(status?.uptime_seconds)}` : "Server offline"}
          tone={running ? "ok" : "default"}
        />
      </div>

      <div className="cf-panel p-5">
        <h2 className="m-0 text-[13px] font-semibold">Resource detail</h2>
        <div className="mt-4 space-y-4">
          {(
            [
              ["CPU", metrics.cpu_percent],
              ["Memory", metrics.memory_percent],
              ["Disk", metrics.disk_percent],
            ] as const
          ).map(([label, pct]) => (
            <div key={label}>
              <div className="mb-1.5 flex justify-between text-[12px]">
                <span className="text-muted">{label}</span>
                <span className="tabular-nums text-text-dim">
                  {pct != null ? `${Math.round(pct)}%` : "—"}
                </span>
              </div>
              <ProgressBar percent={pct} />
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
