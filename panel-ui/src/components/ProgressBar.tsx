type Props = {
  percent?: number | null;
  tone?: "neon" | "ok" | "warn" | "danger" | "auto";
  className?: string;
};

function toneFor(percent: number, tone: NonNullable<Props["tone"]>) {
  if (tone !== "auto") return tone;
  if (percent >= 90) return "danger";
  if (percent >= 75) return "warn";
  return "neon";
}

const fills: Record<string, string> = {
  neon: "bg-neon/80",
  ok: "bg-ok",
  warn: "bg-warn",
  danger: "bg-danger",
};

export function ProgressBar({ percent, tone = "auto", className = "" }: Props) {
  const p = Math.max(0, Math.min(100, Number(percent ?? 0)));
  const t = toneFor(p, tone);
  return (
    <div className={`h-1 w-full overflow-hidden rounded-full bg-border ${className}`}>
      <div
        className={`h-full rounded-full transition-all duration-500 ${fills[t]}`}
        style={{ width: `${p}%` }}
      />
    </div>
  );
}
