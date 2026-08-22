import { forwardRef, useMemo } from "react";

export function lineText(line: string | { text?: string }): string {
  if (typeof line === "string") return line;
  return String(line?.text ?? "");
}

type Tone = "default" | "dim" | "info" | "warn" | "error" | "ok" | "chat";

function toneFor(line: string): Tone {
  const low = line.toLowerCase();
  if (/\b(fatal|severe|error|exception|crash|failed)\b/i.test(line)) return "error";
  if (/\b(warn(ing)?)\b/i.test(line) || /\[.*\/warn\]/i.test(line)) return "warn";
  if (/\b(done|started|ready|success)\b/i.test(line) && !/\berror\b/i.test(low)) return "ok";
  if (/\[.*\/info\]/i.test(line) || /\binfo\b/i.test(low)) return "info";
  if (/\[.*\/debug\]/i.test(line) || /\bdebug\b/i.test(low)) return "dim";
  if (/^<\w+>/.test(line) || /\bsays?\b/i.test(line)) return "chat";
  return "default";
}

const TONE_CLASS: Record<Tone, string> = {
  default: "text-text-dim",
  dim: "text-muted",
  info: "text-text-dim",
  warn: "text-warn",
  error: "text-danger",
  ok: "text-ok/90",
  chat: "text-text",
};

type Props = {
  lines: string[];
  empty?: string;
  className?: string;
};

/** Fixed-width console surface — never grows with long lines; severity-tinted rows. */
export const ConsoleLog = forwardRef<HTMLDivElement, Props>(function ConsoleLog(
  { lines, empty = "(no output)", className = "" },
  ref,
) {
  const rows = useMemo(
    () =>
      lines.map((line, i) => ({
        key: `${i}:${line.slice(0, 48)}`,
        text: line,
        tone: toneFor(line),
      })),
    [lines],
  );

  return (
    <div
      ref={ref}
      className={[
        "min-h-0 min-w-0 w-full flex-1 overflow-auto overscroll-contain rounded-md border border-border bg-oled p-3",
        "font-mono text-[12px] leading-relaxed",
        className,
      ].join(" ")}
    >
      {rows.length ? (
        <div className="min-w-0">
          {rows.map((row) => (
            <div
              key={row.key}
              className={[
                "break-all whitespace-pre-wrap [overflow-wrap:anywhere]",
                TONE_CLASS[row.tone],
              ].join(" ")}
            >
              {row.text}
            </div>
          ))}
        </div>
      ) : (
        <div className="text-muted">{empty}</div>
      )}
    </div>
  );
});
