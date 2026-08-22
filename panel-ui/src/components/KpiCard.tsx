import type { ReactNode } from "react";
import { ProgressBar } from "./ProgressBar";

type Tone = "default" | "ok" | "warn" | "danger";

const valueTone: Record<Tone, string> = {
  default: "text-text",
  ok: "text-ok",
  warn: "text-warn",
  danger: "text-danger",
};

export function KpiCard({
  label,
  value,
  hint,
  percent,
  tone = "default",
  icon,
}: {
  label: string;
  value: ReactNode;
  hint?: ReactNode;
  percent?: number | null;
  tone?: Tone;
  icon?: ReactNode;
}) {
  return (
    <div className="cf-panel group relative overflow-hidden p-4 transition-colors hover:border-border-soft">
      <div className="flex items-start justify-between gap-2">
        <div className="text-[11px] font-medium uppercase tracking-wider text-muted">
          {label}
        </div>
        {icon ? <span className="text-muted opacity-70">{icon}</span> : null}
      </div>
      <div
        className={`mt-1.5 text-[1.65rem] font-semibold leading-none tracking-tight tabular-nums ${valueTone[tone]}`}
      >
        {value}
      </div>
      {hint != null && (
        <div className="mt-1.5 text-[12px] leading-snug text-text-dim">{hint}</div>
      )}
      {percent != null && (
        <div className="mt-3">
          <ProgressBar percent={percent} />
        </div>
      )}
    </div>
  );
}

export function metricTone(percent: number | null | undefined): Tone {
  if (percent == null) return "default";
  if (percent >= 90) return "danger";
  if (percent >= 75) return "warn";
  return "ok";
}
