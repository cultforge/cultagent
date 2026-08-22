import { useEffect, useId, useMemo, useRef, useState, type FormEvent, type KeyboardEvent } from "react";
import { Button } from "./Button";
import { completeConsole, suggestConsole, type Suggestion } from "../lib/mcCommands";

type Props = {
  value: string;
  onChange: (next: string) => void;
  onSubmit: (command: string) => void | Promise<void>;
  disabled?: boolean;
  placeholder?: string;
};

export function ConsoleInput({
  value,
  onChange,
  onSubmit,
  disabled,
  placeholder = "Type a command — Tab to complete…",
}: Props) {
  const listId = useId();
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(0);
  const [history, setHistory] = useState<string[]>([]);
  const [histIdx, setHistIdx] = useState(-1);
  const wrapRef = useRef<HTMLFormElement>(null);

  const suggestions = useMemo(() => suggestConsole(value, 10), [value]);

  useEffect(() => {
    setActive(0);
  }, [value]);

  useEffect(() => {
    function onDoc(e: MouseEvent) {
      if (!wrapRef.current?.contains(e.target as Node)) setOpen(false);
    }
    document.addEventListener("mousedown", onDoc);
    return () => document.removeEventListener("mousedown", onDoc);
  }, []);

  function applySuggestion(s: Suggestion) {
    onChange(s.insert);
    setOpen(true);
    setActive(0);
  }

  async function submit(e?: FormEvent) {
    e?.preventDefault();
    const command = value.trim().replace(/^\//, "");
    if (!command || disabled) return;
    setHistory((h) => [command, ...h.filter((x) => x !== command)].slice(0, 40));
    setHistIdx(-1);
    setOpen(false);
    await onSubmit(command);
  }

  function onKeyDown(e: KeyboardEvent<HTMLInputElement>) {
    if (e.key === "Tab") {
      e.preventDefault();
      if (suggestions.length) {
        const s = suggestions[Math.min(active, suggestions.length - 1)];
        applySuggestion(s);
        return;
      }
      const done = completeConsole(value);
      if (done) onChange(done);
      return;
    }
    if (e.key === "ArrowDown" && open && suggestions.length) {
      e.preventDefault();
      setActive((i) => (i + 1) % suggestions.length);
      return;
    }
    if (e.key === "ArrowUp" && open && suggestions.length && histIdx < 0) {
      e.preventDefault();
      setActive((i) => (i - 1 + suggestions.length) % suggestions.length);
      return;
    }
    if (e.key === "ArrowUp" && !open && history.length) {
      e.preventDefault();
      const next = Math.min(histIdx + 1, history.length - 1);
      setHistIdx(next);
      onChange(history[next] || "");
      return;
    }
    if (e.key === "ArrowDown" && histIdx >= 0) {
      e.preventDefault();
      const next = histIdx - 1;
      setHistIdx(next);
      onChange(next < 0 ? "" : history[next] || "");
      return;
    }
    if (e.key === "Escape") {
      setOpen(false);
      return;
    }
    if (e.key === "Enter" && open && suggestions.length && e.shiftKey) {
      e.preventDefault();
      applySuggestion(suggestions[Math.min(active, suggestions.length - 1)]);
    }
  }

  return (
    <form className="relative flex shrink-0 gap-2" onSubmit={submit} ref={wrapRef}>
      {open && suggestions.length > 0 && (
        <ul
          id={listId}
          role="listbox"
          className="absolute bottom-full left-0 right-14 z-20 mb-1 max-h-56 overflow-auto rounded-md border border-border bg-oled-elev py-1 shadow-lg"
        >
          {suggestions.map((s, i) => (
            <li key={`${s.insert}-${i}`} role="option" aria-selected={i === active}>
              <button
                type="button"
                onMouseDown={(ev) => {
                  ev.preventDefault();
                  applySuggestion(s);
                }}
                className={[
                  "flex w-full items-start gap-2 px-3 py-1.5 text-left font-mono text-[12px]",
                  i === active ? "bg-neon/15 text-text" : "text-text-dim hover:bg-card-2",
                ].join(" ")}
              >
                <span className="min-w-0 flex-1">
                  <span className="text-text">{s.label}</span>
                  <span className="mt-0.5 block truncate text-[11px] text-muted">{s.detail}</span>
                </span>
                <span className="shrink-0 text-[10px] uppercase tracking-wide text-muted">
                  {s.kind === "arg" ? "arg" : "cmd"}
                </span>
              </button>
            </li>
          ))}
          <li className="border-t border-border px-3 py-1 text-[10px] text-muted">
            Tab complete · ↑↓ select · Enter send
          </li>
        </ul>
      )}
      <input
        value={value}
        onChange={(e) => {
          onChange(e.target.value);
          setOpen(true);
          setHistIdx(-1);
        }}
        onFocus={() => setOpen(true)}
        onKeyDown={onKeyDown}
        disabled={disabled}
        placeholder={placeholder}
        autoComplete="off"
        spellCheck={false}
        role="combobox"
        aria-expanded={open && suggestions.length > 0}
        aria-controls={listId}
        aria-autocomplete="list"
        className="min-w-0 flex-1 rounded-md border border-border bg-oled-elev px-3 py-2 font-mono text-[13px] text-text outline-none focus:border-neon/40"
      />
      <Button type="submit" variant="primary" disabled={disabled || !value.trim()}>
        Send
      </Button>
    </form>
  );
}
