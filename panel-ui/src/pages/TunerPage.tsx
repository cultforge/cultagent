import { useEffect, useMemo, useState } from "react";
import { useOutletContext, useParams } from "react-router-dom";
import { Button } from "../components/Button";
import type { ServerOutlet } from "../layouts/ServerLayout";
import { cultApi, humanizeError } from "../lib/api";

type FieldDef = {
  type: string;
  label: string;
  options?: string[];
  min?: number;
  max?: number;
  placeholder?: string;
  hint?: string;
  group?: string;
};

type Preset = {
  id: string;
  label: string;
  description?: string;
  values: Record<string, string>;
};

type Schema = {
  groups: Array<{ id: string; label: string; keys: string[] }>;
  fields: Record<string, FieldDef>;
  presets: Preset[];
};

const GC_LABELS: Record<string, string> = {
  g1: "G1GC (recommended)",
  zgc: "ZGC",
  parallel: "Parallel GC",
  serial: "Serial GC",
  shenandoah: "Shenandoah",
  default: "JVM default",
};

function parseBool(v: string | undefined): boolean {
  return ["1", "true", "yes", "on"].includes(String(v ?? "").toLowerCase());
}

function renderDraftPreview(values: Record<string, string>): string {
  const parts: string[] = [];
  let xms = String(values.xms || "1G").trim().toUpperCase().replace(/\s+/g, "");
  let xmx = String(values.xmx || "2G").trim().toUpperCase().replace(/\s+/g, "");
  if (parseBool(values.lock_heap)) xmx = xms;
  if (!/^\d+[KMG]$/i.test(xms)) xms = "1G";
  if (!/^\d+[KMG]$/i.test(xmx)) xmx = "2G";
  parts.push(`-Xms${xms}`, `-Xmx${xmx}`);

  const gcFlag: Record<string, string> = {
    g1: "-XX:+UseG1GC",
    zgc: "-XX:+UseZGC",
    parallel: "-XX:+UseParallelGC",
    serial: "-XX:+UseSerialGC",
    shenandoah: "-XX:+UseShenandoahGC",
  };
  const gc = gcFlag[String(values.gc || "").toLowerCase()];
  if (gc) parts.push(gc);

  const ints = [
    "MaxGCPauseMillis",
    "G1NewSizePercent",
    "G1MaxNewSizePercent",
    "G1HeapRegionSize",
    "G1ReservePercent",
    "InitiatingHeapOccupancyPercent",
  ];
  for (const name of ints) {
    const raw = String(values[name] || "").trim();
    if (!raw) continue;
    parts.push(name === "G1HeapRegionSize" ? `-XX:G1HeapRegionSize=${raw}m` : `-XX:${name}=${raw}`);
  }

  for (const name of [
    "AlwaysPreTouch",
    "DisableExplicitGC",
    "ParallelRefProcEnabled",
    "PerfDisableSharedMem",
    "UseStringDeduplication",
    "UnlockExperimentalVMOptions",
  ]) {
    if (parseBool(values[name])) parts.push(`-XX:+${name}`);
  }

  const enc = String(values["file.encoding"] || "").trim();
  if (enc) parts.push(`-Dfile.encoding=${enc}`);
  if (parseBool(values.prefer_ipv4)) parts.push("-Djava.net.preferIPv4Stack=true");

  const extra = String(values.extra || "").trim();
  if (extra) parts.push(...extra.split(/\s+/).filter(Boolean));
  return parts.join(" ");
}

function MemoryInput({
  value,
  onChange,
}: {
  value: string;
  onChange: (next: string) => void;
}) {
  const m = /^(\d+)\s*([KMGkmg]?)$/.exec(String(value || "").trim());
  const amount = m?.[1] ?? "1";
  const unit = (m?.[2] || "G").toUpperCase();

  return (
    <div className="flex gap-2">
      <input
        type="number"
        min={1}
        value={amount}
        onChange={(e) => onChange(`${e.target.value || "1"}${unit}`)}
        className="w-full rounded-md border border-border bg-oled-elev px-3 py-2 font-mono text-[13px] tabular-nums text-text outline-none focus:border-neon/40"
      />
      <select
        value={unit}
        onChange={(e) => onChange(`${amount}${e.target.value}`)}
        className="w-[4.5rem] rounded-md border border-border bg-oled-elev px-2 py-2 text-[13px] text-text outline-none focus:border-neon/40"
      >
        <option value="G">GB</option>
        <option value="M">MB</option>
      </select>
    </div>
  );
}

function Toggle({
  on,
  label,
  onChange,
}: {
  on: boolean;
  label: string;
  onChange: (next: boolean) => void;
}) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={on}
      onClick={() => onChange(!on)}
      className={[
        "relative h-7 w-12 shrink-0 rounded-full border transition",
        on ? "border-neon/50 bg-neon/30" : "border-border bg-card-2",
      ].join(" ")}
    >
      <span
        className={[
          "absolute top-0.5 h-5 w-5 rounded-full transition",
          on ? "left-6 bg-neon" : "left-0.5 bg-muted",
        ].join(" ")}
      />
      <span className="sr-only">{label}</span>
    </button>
  );
}

function FieldControl({
  fieldKey,
  def,
  value,
  onChange,
}: {
  fieldKey: string;
  def: FieldDef;
  value: string;
  onChange: (next: string) => void;
}) {
  const inputCls =
    "w-full rounded-md border border-border bg-oled-elev px-3 py-2 text-[13px] text-text outline-none focus:border-neon/40";

  if (def.type === "memory") {
    return <MemoryInput value={value} onChange={onChange} />;
  }

  if (def.type === "bool") {
    return (
      <Toggle on={parseBool(value)} label={def.label} onChange={(v) => onChange(v ? "true" : "false")} />
    );
  }

  if (def.type === "enum" && def.options?.length) {
    const opts = def.options;
    return (
      <select
        value={value || opts[0]}
        onChange={(e) => onChange(e.target.value)}
        className={inputCls}
      >
        {opts.map((o) => (
          <option key={o || "__empty"} value={o}>
            {fieldKey === "gc" ? GC_LABELS[o] || o || "(unset)" : o || "(unset)"}
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
        placeholder="auto"
        onChange={(e) => onChange(e.target.value)}
        className={`${inputCls} font-mono tabular-nums`}
      />
    );
  }

  if (def.type === "textarea") {
    return (
      <textarea
        value={value}
        placeholder={def.placeholder}
        rows={3}
        spellCheck={false}
        onChange={(e) => onChange(e.target.value)}
        className={`${inputCls} min-h-[72px] resize-y font-mono text-[12px] leading-relaxed`}
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

export function TunerPage() {
  const { serverId = "" } = useParams();
  const { setFlash } = useOutletContext<ServerOutlet>();
  const [schema, setSchema] = useState<Schema | null>(null);
  const [saved, setSaved] = useState<Record<string, string>>({});
  const [draft, setDraft] = useState<Record<string, string>>({});
  const [rawPreview, setRawPreview] = useState("");
  const [source, setSource] = useState("catalog");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [showRaw, setShowRaw] = useState(false);
  const [rawEdit, setRawEdit] = useState("");

  useEffect(() => {
    let alive = true;
    (async () => {
      try {
        const res = await cultApi.jvmGet(serverId);
        if (!alive) return;
        const values = res.values || {};
        setSaved(values);
        setDraft({ ...values });
        setRawPreview(res.raw || "");
        setRawEdit(res.raw || "");
        setSource(res.source || "catalog");
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

  const dirty = useMemo(() => {
    const keys = new Set([...Object.keys(saved), ...Object.keys(draft)]);
    return [...keys].some((k) => String(draft[k] ?? "") !== String(saved[k] ?? ""));
  }, [draft, saved]);

  function setField(key: string, value: string) {
    setDraft((prev) => {
      const next = { ...prev, [key]: value };
      if (key === "xms" && parseBool(prev.lock_heap)) next.xmx = value;
      if (key === "lock_heap" && parseBool(value)) next.xmx = next.xms || prev.xms || "1G";
      if (key === "xmx" && parseBool(prev.lock_heap)) next.xms = value;
      return next;
    });
  }

  async function saveValues(values: Record<string, string>) {
    setSaving(true);
    try {
      const res = await cultApi.jvmSaveValues(serverId, values);
      const next = res.values || values;
      setSaved(next);
      setDraft({ ...next });
      setRawPreview(res.raw || "");
      setRawEdit(res.raw || "");
      setSource(res.source || source);
      setFlash({ msg: "JVM flags saved — restart the server to apply", ok: true });
    } catch (e) {
      setFlash({ msg: humanizeError(e), ok: false });
    } finally {
      setSaving(false);
    }
  }

  async function saveRaw() {
    setSaving(true);
    try {
      const res = await cultApi.jvmSaveRaw(serverId, rawEdit);
      const next = res.values || {};
      setSaved(next);
      setDraft({ ...next });
      setRawPreview(res.raw || rawEdit);
      setRawEdit(res.raw || rawEdit);
      setSource(res.source || source);
      setFlash({ msg: "Raw JVM flags saved — restart the server to apply", ok: true });
    } catch (e) {
      setFlash({ msg: humanizeError(e), ok: false });
    } finally {
      setSaving(false);
    }
  }

  function applyPreset(preset: Preset) {
    setDraft((prev) => ({ ...prev, ...preset.values }));
  }

  if (loading) return <p className="text-text-dim">Loading JVM tuner…</p>;

  const groups = schema?.groups || [];
  const fields = schema?.fields || {};
  const presets = schema?.presets || [];

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="m-0 text-[15px] font-semibold">JVM tuner</h2>
          <p className="m-0 mt-0.5 text-[12px] text-muted">
            Fine-tune heap and GC flags with controls — no raw editing required.
            {source === "user_jvm_args.txt" && (
              <span className="ml-2 text-text-dim">Synced to user_jvm_args.txt</span>
            )}
            {dirty && <span className="ml-2 text-warn">Unsaved changes</span>}
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button variant="ghost" disabled={!dirty || saving} onClick={() => setDraft({ ...saved })}>
            Reset
          </Button>
          <Button variant="ghost" onClick={() => setShowRaw((v) => !v)}>
            {showRaw ? "Hide raw" : "Advanced raw"}
          </Button>
          <Button variant="primary" disabled={saving || !dirty} onClick={() => saveValues(draft)}>
            Save flags
          </Button>
        </div>
      </div>

      {presets.length > 0 && (
        <section className="cf-panel p-4">
          <h3 className="m-0 text-[13px] font-semibold">Presets</h3>
          <p className="m-0 mt-1 text-[12px] text-muted">
            Apply a starting point, then tweak. Save when ready.
          </p>
          <div className="mt-3 grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
            {presets.map((p) => (
              <button
                key={p.id}
                type="button"
                onClick={() => applyPreset(p)}
                className="rounded-md border border-border bg-card-2/50 px-3 py-3 text-left transition hover:border-neon/35 hover:bg-card-2"
              >
                <div className="text-[13px] font-medium text-text">{p.label}</div>
                <div className="mt-1 text-[11px] leading-snug text-muted">{p.description}</div>
              </button>
            ))}
          </div>
        </section>
      )}

      {groups.map((group) => (
        <section key={group.id} className="cf-panel overflow-hidden">
          <div className="border-b border-border bg-card-2/40 px-4 py-3">
            <h3 className="m-0 text-[13px] font-semibold">{group.label}</h3>
          </div>
          <div className="divide-y divide-border/80">
            {group.keys.map((key) => {
              const def = fields[key] || { type: "text", label: key };
              const value = draft[key] ?? "";
              const wide = def.type === "textarea";
              return (
                <div
                  key={key}
                  className={[
                    "flex gap-3 px-4 py-3",
                    wide ? "flex-col" : "flex-wrap items-center justify-between sm:flex-nowrap",
                  ].join(" ")}
                >
                  <div className="min-w-0 flex-1">
                    <div className="text-[13px] font-medium text-text">{def.label}</div>
                    {def.hint && (
                      <div className="mt-0.5 text-[11px] leading-snug text-muted">{def.hint}</div>
                    )}
                  </div>
                  <div className={wide ? "w-full" : "w-full sm:w-[min(280px,100%)]"}>
                    <FieldControl
                      fieldKey={key}
                      def={def}
                      value={value}
                      onChange={(next) => setField(key, next)}
                    />
                  </div>
                </div>
              );
            })}
          </div>
        </section>
      ))}

      <section className="cf-panel p-4">
        <h3 className="m-0 text-[13px] font-semibold">Live preview</h3>
        <pre className="mt-3 overflow-auto rounded-md border border-border bg-oled p-3 font-mono text-[12px] leading-relaxed text-text-dim whitespace-pre-wrap">
          {renderDraftPreview(draft) || rawPreview || "—"}
        </pre>
        <p className="m-0 mt-2 text-[11px] text-muted">
          Restart the Minecraft process after saving for new flags to take effect.
        </p>
      </section>

      {showRaw && (
        <section className="cf-panel p-4">
          <div className="mb-3 flex items-center justify-between gap-2">
            <div>
              <h3 className="m-0 text-[13px] font-semibold">Raw JVM args</h3>
              <p className="m-0 mt-0.5 text-[12px] text-muted">
                Escape hatch for flags the GUI does not map yet.
              </p>
            </div>
            <Button variant="primary" disabled={saving} onClick={saveRaw}>
              Save raw
            </Button>
          </div>
          <textarea
            value={rawEdit}
            onChange={(e) => setRawEdit(e.target.value)}
            spellCheck={false}
            className="min-h-[140px] w-full resize-y rounded-md border border-border bg-oled p-3 font-mono text-[12px] leading-relaxed text-text outline-none focus:border-neon/40"
          />
        </section>
      )}
    </div>
  );
}
