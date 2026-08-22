import { useEffect, useMemo, useState } from "react";
import { useOutletContext, useParams } from "react-router-dom";
import { Button } from "../components/Button";
import { SimpleMarkdown } from "../components/SimpleMarkdown";
import type { ServerOutlet } from "../layouts/ServerLayout";
import { cultApi, humanizeError, type WorldItem } from "../lib/api";

type FieldDef = {
  type: string;
  label: string;
  options?: string[];
  min?: number;
  max?: number;
  placeholder?: string;
  help?: string;
  help_full?: string;
  options_help?: Record<string, string>;
};

type Schema = {
  groups: Array<{ id: string; label: string; keys: string[] }>;
  fields: Record<string, FieldDef>;
};

function parseBool(v: string | undefined): boolean {
  return String(v ?? "").toLowerCase() === "true";
}

function isBoolValue(v: string | undefined): boolean {
  const s = String(v ?? "").toLowerCase();
  return s === "true" || s === "false";
}

function humanizeKey(key: string): string {
  return key
    .replace(/[._]/g, " ")
    .replace(/\b\w/g, (c) => c.toUpperCase());
}

function inferFieldDef(
  key: string,
  value: string,
  fields: Record<string, FieldDef>,
): FieldDef {
  const known = fields[key];
  if (known) {
    if (known.type === "text" && isBoolValue(value)) {
      return { ...known, type: "bool" };
    }
    return known;
  }
  if (isBoolValue(value)) {
    return { type: "bool", label: humanizeKey(key) };
  }
  if (value !== "" && /^-?\d+$/.test(value)) {
    return { type: "int", label: humanizeKey(key) };
  }
  return { type: "text", label: humanizeKey(key) };
}

function formatBytes(n: number | undefined): string {
  if (n == null || n <= 0) return "";
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${Math.round(n / 1024)} KB`;
  return `${(n / (1024 * 1024)).toFixed(1)} MB`;
}

function selectedOptionBlurb(def: FieldDef, value: string): string | null {
  const v = String(value ?? "");
  if (!v && v !== "0") return null;
  const fromMap = def.options_help?.[v] || def.options_help?.[v.toLowerCase()];
  if (fromMap) return fromMap;
  if (def.type === "bool") {
    return parseBool(v)
      ? "Currently enabled (true)."
      : "Currently disabled (false).";
  }
  if (def.type === "enum" || def.options?.length) {
    return `Currently set to “${v}”.`;
  }
  if (v) return `Current value: ${v}`;
  return null;
}

function buildHelpMarkdown(def: FieldDef, value: string, propKey: string): string {
  const parts: string[] = [];
  const display = value === "" ? "(empty)" : value;
  parts.push(`## ${def.label}`);
  parts.push("");
  parts.push(`**Property:** \`${propKey}\``);
  parts.push("");
  parts.push(`**Current value:** \`${display}\``);

  const selected = selectedOptionBlurb(def, value);
  if (selected) {
    parts.push("");
    parts.push(`> **Selected option:** ${selected}`);
  }

  if (def.help_full) {
    parts.push("");
    // Avoid duplicating a leading H2 if help_full already starts with #
    const body = def.help_full.trim().replace(/^##[^\n]*\n+/, "");
    parts.push(body);
  } else if (def.help) {
    parts.push("");
    parts.push(def.help);
  }

  const optHelp = def.options_help;
  if (optHelp && Object.keys(optHelp).length) {
    // Only append a compact option table if help_full didn't already include ### Options
    if (!def.help_full?.includes("### Options") && !def.help_full?.includes("## Options")) {
      parts.push("");
      parts.push("### Options");
      for (const [k, desc] of Object.entries(optHelp)) {
        const mark = String(value) === k ? " ← **selected**" : "";
        parts.push(`- **\`${k}\`** — ${desc}${mark}`);
      }
    } else {
      // Still highlight selection at the end
      parts.push("");
      parts.push("### Your selection");
      const desc = optHelp[value] || optHelp[value.toLowerCase()] || "Custom / undocumented value.";
      parts.push(`- **\`${display}\`** — ${desc}`);
    }
  }

  parts.push("");
  parts.push("---");
  parts.push("*Most `server.properties` changes need a **server restart** to apply.*");
  return parts.join("\n");
}

function HelpMark({
  label,
  propKey,
  def,
  value,
}: {
  label: string;
  propKey: string;
  def: FieldDef;
  value: string;
}) {
  const [open, setOpen] = useState(false);
  const basic = def.help || def.help_full;
  if (!basic && !def.options_help) return null;

  const selected = selectedOptionBlurb(def, value);
  const hover = [
    basic?.split("\n")[0]?.replace(/^#+\s*/, "") || label,
    selected ? `Selected: ${value || "(empty)"} — ${selected}` : value ? `Selected: ${value}` : null,
    "Click for full details",
  ]
    .filter(Boolean)
    .join("\n");

  const markdown = buildHelpMarkdown(def, value, propKey);

  return (
    <>
      <button
        type="button"
        title={hover}
        aria-label={`Help: ${label}`}
        onClick={(e) => {
          e.preventDefault();
          e.stopPropagation();
          setOpen(true);
        }}
        className="inline-flex h-4 w-4 shrink-0 items-center justify-center rounded-full border border-border text-[10px] font-semibold leading-none text-muted transition hover:border-neon/40 hover:text-neon"
      >
        ?
      </button>
      {open && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4"
          role="dialog"
          aria-modal="true"
          aria-label={`${label} help`}
          onClick={() => setOpen(false)}
        >
          <div
            className="cf-panel flex max-h-[85vh] w-full max-w-lg flex-col overflow-hidden p-5 shadow-xl"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="mb-3 flex shrink-0 items-start justify-between gap-3">
              <div>
                <h3 className="m-0 text-[15px] font-semibold text-text">{label}</h3>
                <p className="m-0 mt-1 font-mono text-[11px] text-muted">
                  {propKey}
                  {value !== "" && (
                    <>
                      {" "}
                      · <span className="text-neon">{value}</span>
                    </>
                  )}
                </p>
              </div>
              <Button variant="ghost" onClick={() => setOpen(false)}>
                Close
              </Button>
            </div>
            <div className="min-h-0 flex-1 overflow-auto pr-1">
              <SimpleMarkdown source={markdown} />
            </div>
          </div>
        </div>
      )}
    </>
  );
}

function FieldControl({
  def,
  value,
  onChange,
  worlds,
}: {
  def: FieldDef;
  value: string;
  onChange: (next: string) => void;
  worlds?: WorldItem[];
}) {
  const inputCls =
    "w-full rounded-md border border-border bg-oled-elev px-3 py-2 text-[13px] text-text outline-none focus:border-neon/40";

  if (def.type === "world") {
    const names = worlds?.map((w) => w.name) || [];
    const opts =
      value && !names.includes(value) ? [value, ...names] : names.length ? names : [value || "world"];
    return (
      <div className="space-y-2">
        <select
          value={opts.includes(value) ? value : opts[0]}
          onChange={(e) => onChange(e.target.value)}
          className={inputCls}
        >
          {opts.map((o) => {
            const meta = worlds?.find((w) => w.name === o);
            const bits = [
              meta?.has_level_dat === false ? "new" : null,
              meta?.pending ? "pending" : null,
              formatBytes(meta?.size) || null,
            ].filter(Boolean);
            return (
              <option key={o} value={o}>
                {o}
                {bits.length ? ` (${bits.join(", ")})` : ""}
              </option>
            );
          })}
        </select>
        <input
          type="text"
          value={value}
          placeholder={def.placeholder || "new-world-name"}
          onChange={(e) => onChange(e.target.value.trim())}
          className={`${inputCls} font-mono text-[12px]`}
          aria-label="World folder name"
        />
        <p className="m-0 text-[11px] text-muted">
          Pick an existing folder or type a new name. Restart required after changing.
        </p>
      </div>
    );
  }

  if (def.type === "bool") {
    const on = parseBool(value);
    return (
      <button
        type="button"
        role="switch"
        aria-checked={on}
        onClick={() => onChange(on ? "false" : "true")}
        className={[
          "relative h-7 w-12 shrink-0 rounded-full border transition",
          on ? "border-neon/50 bg-neon/30" : "border-border bg-card-2",
        ].join(" ")}
      >
        <span
          className={[
            "absolute top-0.5 h-5 w-5 rounded-full bg-text transition",
            on ? "left-6 bg-neon" : "left-0.5 bg-muted",
          ].join(" ")}
        />
        <span className="sr-only">{def.label}</span>
      </button>
    );
  }

  if (def.type === "enum" && def.options?.length) {
    const opts = def.options.includes(value) || !value ? def.options : [value, ...def.options];
    return (
      <select
        value={value || opts[0]}
        onChange={(e) => onChange(e.target.value)}
        className={inputCls}
      >
        {opts.map((o) => (
          <option key={o} value={o}>
            {o}
          </option>
        ))}
      </select>
    );
  }

  if (def.type === "int") {
    return (
      <input
        type="number"
        value={value}
        min={def.min}
        max={def.max}
        onChange={(e) => onChange(e.target.value)}
        className={`${inputCls} font-mono tabular-nums`}
      />
    );
  }

  return (
    <input
      type="text"
      value={value}
      placeholder={def.placeholder}
      onChange={(e) => onChange(e.target.value)}
      className={inputCls}
    />
  );
}

function SettingRow({
  propKey,
  def,
  value,
  onChange,
  worlds,
}: {
  propKey: string;
  def: FieldDef;
  value: string;
  onChange: (next: string) => void;
  worlds?: WorldItem[];
}) {
  return (
    <div className="flex flex-wrap items-center justify-between gap-3 px-4 py-3 sm:flex-nowrap">
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-1.5">
          <span className="text-[13px] font-medium text-text">{def.label}</span>
          <HelpMark label={def.label} propKey={propKey} def={def} value={value} />
        </div>
        <div className="mt-0.5 font-mono text-[11px] text-muted">{propKey}</div>
        {selectedOptionBlurb(def, value) && (
          <div className="mt-1 text-[11px] text-muted line-clamp-2">
            {selectedOptionBlurb(def, value)}
          </div>
        )}
      </div>
      <div
        className={[
          "w-full sm:w-[min(280px,100%)]",
          def.type === "bool" ? "flex sm:justify-end" : "",
        ].join(" ")}
      >
        <FieldControl def={def} value={value} onChange={onChange} worlds={worlds} />
      </div>
    </div>
  );
}

export function ConfigPage() {
  const { serverId = "" } = useParams();
  const { setFlash } = useOutletContext<ServerOutlet>();
  const [properties, setProperties] = useState<Record<string, string>>({});
  const [draft, setDraft] = useState<Record<string, string>>({});
  const [schema, setSchema] = useState<Schema | null>(null);
  const [worlds, setWorlds] = useState<WorldItem[]>([]);
  const [raw, setRaw] = useState("");
  const [showRaw, setShowRaw] = useState(false);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [newWorldName, setNewWorldName] = useState("");

  useEffect(() => {
    let alive = true;
    (async () => {
      try {
        const res = await cultApi.configGet(serverId);
        if (!alive) return;
        const props = res.properties || {};
        setProperties(props);
        setDraft({ ...props });
        setRaw(res.raw || "");
        setWorlds(res.worlds || []);
        if (res.schema) setSchema(res.schema as Schema);
      } catch (e) {
        if (alive) setFlash({ msg: humanizeError(e), ok: false });
      } finally {
        if (alive) setLoading(false);
      }
    })();
    return () => {
      alive = false;
    };
  }, [serverId, setFlash]);

  const dirtyKeys = useMemo(() => {
    const keys = new Set([...Object.keys(properties), ...Object.keys(draft)]);
    return [...keys].filter((k) => String(draft[k] ?? "") !== String(properties[k] ?? ""));
  }, [draft, properties]);

  const activeWorld = draft["level-name"] || properties["level-name"] || "world";

  function setField(key: string, value: string) {
    setDraft((prev) => ({ ...prev, [key]: value }));
  }

  async function saveGui() {
    if (!dirtyKeys.length) {
      setFlash({ msg: "No changes to save", ok: true });
      return;
    }
    setSaving(true);
    try {
      const values: Record<string, string> = {};
      for (const k of dirtyKeys) values[k] = String(draft[k] ?? "");
      const res = await cultApi.configSaveValues(serverId, values);
      const next = res.properties || { ...properties, ...values };
      setProperties(next);
      setDraft({ ...next });
      if (res.raw) setRaw(res.raw);
      if (res.worlds) setWorlds(res.worlds);
      setFlash({
        msg:
          res.message ||
          (res.restarted
            ? "Saved and restarted so settings take effect"
            : `Saved ${dirtyKeys.length} setting${dirtyKeys.length === 1 ? "" : "s"}`),
        ok: true,
      });
    } catch (e) {
      setFlash({ msg: humanizeError(e), ok: false });
    } finally {
      setSaving(false);
    }
  }

  async function saveRaw() {
    setSaving(true);
    try {
      await cultApi.configSave(serverId, raw);
      const res = await cultApi.configGet(serverId);
      const props = res.properties || {};
      setProperties(props);
      setDraft({ ...props });
      setRaw(res.raw || raw);
      setWorlds(res.worlds || []);
      setFlash({
        msg: "Raw server.properties saved (server restarts if it was running)",
        ok: true,
      });
    } catch (e) {
      setFlash({ msg: humanizeError(e), ok: false });
    } finally {
      setSaving(false);
    }
  }

  async function createAndSelectWorld() {
    const name = newWorldName.trim();
    if (!name) {
      setFlash({ msg: "Enter a world name", ok: false });
      return;
    }
    setSaving(true);
    try {
      const res = await cultApi.worldsSelect(serverId, {
        level_name: name,
        create_folder: true,
      });
      setWorlds(res.worlds || []);
      const next = { ...draft, "level-name": res.active_world || name };
      setDraft(next);
      setProperties({ ...properties, "level-name": res.active_world || name });
      setNewWorldName("");
      setFlash({
        msg: `World “${res.active_world || name}” selected. Restart the server to load it.`,
        ok: true,
      });
    } catch (e) {
      setFlash({ msg: humanizeError(e), ok: false });
    } finally {
      setSaving(false);
    }
  }

  function resetDraft() {
    setDraft({ ...properties });
  }

  if (loading) return <p className="text-text-dim">Loading settings…</p>;

  const groups = schema?.groups || [];
  const fields = schema?.fields || {};
  const knownKeys = new Set(groups.flatMap((g) => g.keys));
  const otherKeys = Object.keys(draft)
    .filter((k) => !knownKeys.has(k))
    .sort();

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="m-0 text-[15px] font-semibold">Server settings</h2>
          <p className="m-0 mt-0.5 text-[12px] text-muted">
            Active world:{" "}
            <span className="font-mono text-text">{activeWorld}</span>
            {dirtyKeys.length > 0 && (
              <span className="ml-2 text-warn">{dirtyKeys.length} unsaved</span>
            )}
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button variant="ghost" disabled={!dirtyKeys.length || saving} onClick={resetDraft}>
            Reset
          </Button>
          <Button variant="ghost" onClick={() => setShowRaw((v) => !v)}>
            {showRaw ? "Hide raw" : "Advanced raw"}
          </Button>
          <Button variant="primary" disabled={saving || !dirtyKeys.length} onClick={saveGui}>
            Save changes
          </Button>
        </div>
      </div>

      <section className="cf-panel overflow-hidden">
        <div className="border-b border-border bg-card-2/40 px-4 py-3">
          <h3 className="m-0 text-[13px] font-semibold">Choose world</h3>
          <p className="m-0 mt-0.5 text-[12px] text-muted">
            Select which folder loads as the overworld (`level-name`). Restart after changing.
          </p>
        </div>
        <div className="space-y-3 p-4">
          {worlds.length > 0 ? (
            <div className="grid gap-2 sm:grid-cols-2">
              {worlds.map((w) => {
                const selected = activeWorld === w.name;
                return (
                  <button
                    key={w.name}
                    type="button"
                    onClick={() => setField("level-name", w.name)}
                    className={[
                      "rounded-md border px-3 py-3 text-left transition",
                      selected
                        ? "border-neon/50 bg-neon/10"
                        : "border-border bg-oled-elev hover:border-border-hi",
                    ].join(" ")}
                  >
                    <div className="flex items-center justify-between gap-2">
                      <span className="font-mono text-[13px] font-medium">{w.name}</span>
                      {selected && (
                        <span className="text-[10px] uppercase tracking-wide text-neon">active</span>
                      )}
                    </div>
                    <div className="mt-1 text-[11px] text-muted">
                      {w.has_level_dat === false
                        ? "Empty / not generated yet"
                        : formatBytes(w.size) || "World folder"}
                    </div>
                  </button>
                );
              })}
            </div>
          ) : (
            <p className="m-0 text-[13px] text-muted">
              No world folders found yet. Create one below — the server will generate it on start.
            </p>
          )}
          <div className="flex flex-wrap gap-2">
            <input
              type="text"
              value={newWorldName}
              onChange={(e) => setNewWorldName(e.target.value)}
              placeholder="new-world-name"
              className="min-w-[180px] flex-1 rounded-md border border-border bg-oled-elev px-3 py-2 font-mono text-[13px] text-text outline-none focus:border-neon/40"
            />
            <Button variant="ghost" disabled={saving || !newWorldName.trim()} onClick={createAndSelectWorld}>
              Create & select
            </Button>
          </div>
        </div>
      </section>

      {groups.map((group) => (
        <section key={group.id} className="cf-panel overflow-hidden">
          <div className="border-b border-border bg-card-2/40 px-4 py-3">
            <h3 className="m-0 text-[13px] font-semibold">{group.label}</h3>
          </div>
          <div className="divide-y divide-border/80">
            {group.keys.map((key) => {
              const value = draft[key] ?? properties[key] ?? "";
              const def = inferFieldDef(key, value, fields);
              return (
                <SettingRow
                  key={key}
                  propKey={key}
                  def={def}
                  value={value}
                  onChange={(next) => setField(key, next)}
                  worlds={worlds}
                />
              );
            })}
          </div>
        </section>
      ))}

      {otherKeys.length > 0 && (
        <section className="cf-panel overflow-hidden">
          <div className="border-b border-border bg-card-2/40 px-4 py-3">
            <h3 className="m-0 text-[13px] font-semibold">Other properties</h3>
          </div>
          <div className="divide-y divide-border/80">
            {otherKeys.map((key) => {
              const value = draft[key] ?? "";
              const def = inferFieldDef(key, value, fields);
              return (
                <SettingRow
                  key={key}
                  propKey={key}
                  def={def}
                  value={value}
                  onChange={(next) => setField(key, next)}
                  worlds={worlds}
                />
              );
            })}
          </div>
        </section>
      )}

      {showRaw && (
        <section className="cf-panel p-4">
          <div className="mb-3 flex items-center justify-between gap-2">
            <div>
              <h3 className="m-0 text-[13px] font-semibold">Raw server.properties</h3>
              <p className="m-0 mt-0.5 text-[12px] text-muted">
                Direct file edit — use when you need keys not shown above.
              </p>
            </div>
            <Button variant="primary" disabled={saving} onClick={saveRaw}>
              Save raw
            </Button>
          </div>
          <textarea
            value={raw}
            onChange={(e) => setRaw(e.target.value)}
            spellCheck={false}
            className="min-h-[320px] w-full resize-y rounded-md border border-border bg-oled p-3 font-mono text-[12px] leading-relaxed text-text outline-none focus:border-neon/40"
          />
        </section>
      )}
    </div>
  );
}
