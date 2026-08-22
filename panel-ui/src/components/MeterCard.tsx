import type { ReactNode } from "react";

type Props = {
  label: string;
  value: ReactNode;
  sub?: ReactNode;
  percent?: number | null;
};

export function MeterCard({ label, value, sub, percent }: Props) {
  const pct = Math.max(0, Math.min(100, Number(percent ?? 0)));
  return (
    <div className="cf-panel p-4">
      <h2 className="m-0 text-[11px] font-medium uppercase tracking-wider text-muted">{label}</h2>
      <div className="mt-1 text-xl font-semibold tracking-tight tabular-nums text-text">{value}</div>
      {sub != null && <div className="mt-0.5 text-[12px] text-text-dim">{sub}</div>}
      {percent != null && (
        <div className="mt-3 h-1 overflow-hidden rounded-full bg-border">
          <span
            className="block h-full rounded-full bg-neon/80 transition-all duration-500"
            style={{ width: `${pct}%` }}
          />
        </div>
      )}
    </div>
  );
}
