import { normalizeState } from "../lib/api";

export function StatusDot({ state }: { state: string }) {
  const s = normalizeState(state);
  const on = s === "running" || s === "online" || s === "starting";
  const err = s === "crashed";
  return (
    <span
      className={[
        "inline-block h-2 w-2 shrink-0 rounded-full",
        on ? "bg-ok" : "",
        err ? "bg-danger" : "",
        !on && !err ? "bg-muted" : "",
      ].join(" ")}
    />
  );
}

export function StatusLabel({ state }: { state: string }) {
  const s = normalizeState(state);
  const running = s === "running" || s === "online";
  return (
    <strong className={running ? "text-ok" : s === "crashed" ? "text-danger" : "text-text"}>
      {running ? "Online" : s}
    </strong>
  );
}

export function StatusChip({ state }: { state: string }) {
  const s = normalizeState(state);
  const running = s === "running" || s === "online" || s === "starting";
  const crashed = s === "crashed";
  const label = running ? (s === "starting" ? "starting" : "online") : s;
  return (
    <span
      className={[
        "inline-flex items-center gap-1.5 rounded-md border px-2 py-0.5 text-[11px] font-medium capitalize",
        running
          ? "border-ok/25 bg-ok/10 text-ok"
          : crashed
            ? "border-danger/25 bg-danger/10 text-danger"
            : "border-border bg-card-2 text-text-dim",
      ].join(" ")}
    >
      <StatusDot state={s} />
      {label}
    </span>
  );
}
