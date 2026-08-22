import { useCallback, useEffect, useState } from "react";
import { cultApi, flatMetrics, type FlatMetrics } from "../lib/api";
import type { FleetRow } from "../lib/servers";

export function useFleet(pollMs = 8000) {
  const [rows, setRows] = useState<FleetRow[]>([]);
  const [metrics, setMetrics] = useState<FlatMetrics>({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    const [list, m] = await Promise.all([
      cultApi.servers(),
      cultApi.metrics().catch(() => null),
    ]);
    setRows(list.servers || []);
    setMetrics(flatMetrics(m));
    setError(null);
  }, []);

  useEffect(() => {
    let alive = true;
    (async () => {
      try {
        await refresh();
      } catch (e) {
        if (alive) setError(e instanceof Error ? e.message : String(e));
      } finally {
        if (alive) setLoading(false);
      }
    })();
    const t = setInterval(() => {
      refresh().catch(() => undefined);
    }, pollMs);
    return () => {
      alive = false;
      clearInterval(t);
    };
  }, [pollMs, refresh]);

  return { rows, metrics, loading, error, refresh };
}
