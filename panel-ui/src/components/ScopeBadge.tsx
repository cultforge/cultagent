import type { ServerRecord } from "../lib/api";
import { scopeBadge } from "../lib/servers";

const STYLES: Record<string, string> = {
  guild:
    "border-violet-400/40 bg-violet-500/15 text-violet-200",
  personal:
    "border-sky-400/40 bg-sky-500/10 text-sky-200",
  local:
    "border-border bg-card-2/80 text-muted",
};

type Props = {
  server: ServerRecord;
  className?: string;
  /** Use longer copy on server detail headers (e.g. "Guild server"). */
  detailed?: boolean;
};

export function ScopeBadge({ server, className = "", detailed = false }: Props) {
  const badge = scopeBadge(server);
  const text =
    detailed && badge.scope === "guild"
      ? "Guild server"
      : detailed && badge.scope === "personal"
        ? "Personal cloud"
        : badge.label;
  return (
    <span
      className={[
        "inline-flex shrink-0 items-center rounded border px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide",
        STYLES[badge.scope] || STYLES.local,
        className,
      ].join(" ")}
    >
      {text}
    </span>
  );
}
