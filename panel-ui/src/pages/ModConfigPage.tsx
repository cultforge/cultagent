import { useCallback, useEffect, useMemo, useState } from "react";
import { useOutletContext, useParams } from "react-router-dom";
import { Button } from "../components/Button";
import type { ServerOutlet } from "../layouts/ServerLayout";
import { cultApi, humanizeError } from "../lib/api";

type Field = {
  key: string;
  type: string;
  value: unknown;
  label: string;
};

type ConfigFile = { path: string; name: string; suffix: string; size: number };

export function ModConfigPage() {
  const { serverId = "" } = useParams();
  const { setFlash } = useOutletContext<ServerOutlet>();
  const [files, setFiles] = useState<ConfigFile[]>([]);
  const [selected, setSelected] = useState("");
  const [fields, setFields] = useState<Field[]>([]);
  const [raw, setRaw] = useState("");
  const [mode, setMode] = useState<"form" | "raw">("form");
  const [busy, setBusy] = useState(false);
  const [parseError, setParseError] = useState<string | null>(null);

  const loadList = useCallback(async () => {
    const res = await cultApi.modConfigs(serverId);
    setFiles(res.files || []);
  }, [serverId]);

  const loadOne = useCallback(
    async (path: string) => {
      const res = await cultApi.modConfigGet(serverId, path);
      setRaw(res.raw || "");
      setFields((res.fields as Field[]) || []);
      setParseError(res.parse_error || null);
      setMode(res.fields?.length ? "form" : "raw");
    },
    [serverId],
  );

  useEffect(() => {
    loadList().catch((e) => setFlash({ msg: humanizeError(e), ok: false }));
  }, [loadList, setFlash]);

  useEffect(() => {
    if (!selected) return;
    loadOne(selected).catch((e) => setFlash({ msg: humanizeError(e), ok: false }));
  }, [loadOne, selected, setFlash]);

  const values = useMemo(() => {
    const out: Record<string, unknown> = {};
    for (const f of fields) out[f.key] = f.value;
    return out;
  }, [fields]);

  async function save() {
    if (!selected) return;
    setBusy(true);
    try {
      if (mode === "raw") {
        await cultApi.modConfigPut(serverId, selected, { raw });
      } else {
        await cultApi.modConfigPut(serverId, selected, { values });
      }
      setFlash({ msg: "Config saved", ok: true });
      await loadOne(selected);
    } catch (e) {
      setFlash({ msg: humanizeError(e), ok: false });
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="cf-spatial-stage grid gap-4 lg:grid-cols-[240px_1fr]">
      <aside className="cf-panel flex max-h-[70vh] flex-col overflow-hidden p-3">
        <div className="mb-2 flex items-center justify-between">
          <h2 className="m-0 text-[13px] font-semibold">Mod configs</h2>
          <Button variant="ghost" onClick={() => loadList().catch(() => undefined)}>
            Reload
          </Button>
        </div>
        <p className="m-0 mb-2 text-[11px] text-muted">Files under config/</p>
        <ul className="m-0 flex-1 list-none overflow-auto p-0">
          {!files.length && <li className="text-[12px] text-muted">No .toml / .json configs yet.</li>}
          {files.map((f) => (
            <li key={f.path}>
              <button
                type="button"
                className={[
                  "mb-0.5 w-full rounded-md px-2 py-1.5 text-left font-mono text-[12px] transition",
                  selected === f.path
                    ? "bg-card-2 text-neon ring-1 ring-border"
                    : "text-text-dim hover:bg-card-2/60 hover:text-text",
                ].join(" ")}
                onClick={() => setSelected(f.path)}
              >
                {f.name}
              </button>
            </li>
          ))}
        </ul>
      </aside>

      <section className="cf-panel flex min-h-[420px] flex-col p-4">
        {!selected ? (
          <p className="m-0 text-[13px] text-muted">Select a config file to tune options.</p>
        ) : (
          <>
            <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
              <div>
                <h2 className="m-0 font-mono text-[13px] font-semibold">{selected}</h2>
                {parseError && (
                  <p className="m-0 mt-1 text-[11px] text-danger">Parse: {parseError} — raw mode</p>
                )}
              </div>
              <div className="flex gap-2">
                <Button
                  variant={mode === "form" ? "primary" : "ghost"}
                  disabled={!fields.length}
                  onClick={() => setMode("form")}
                >
                  Form
                </Button>
                <Button variant={mode === "raw" ? "primary" : "ghost"} onClick={() => setMode("raw")}>
                  Raw
                </Button>
                <Button variant="primary" disabled={busy} onClick={save}>
                  Save
                </Button>
              </div>
            </div>

            {mode === "raw" ? (
              <textarea
                className="min-h-[360px] flex-1 rounded-md border border-border bg-oled p-3 font-mono text-[12px] text-text"
                value={raw}
                onChange={(e) => setRaw(e.target.value)}
              />
            ) : (
              <div className="grid max-h-[60vh] gap-3 overflow-auto pr-1">
                {fields.map((f) => (
                  <label key={f.key} className="grid gap-1 text-[12px]">
                    <span className="font-mono text-muted">{f.key}</span>
                    {f.type === "bool" ? (
                      <input
                        type="checkbox"
                        checked={Boolean(f.value)}
                        onChange={(e) =>
                          setFields((prev) =>
                            prev.map((x) =>
                              x.key === f.key ? { ...x, value: e.target.checked } : x,
                            ),
                          )
                        }
                      />
                    ) : f.type === "number" ? (
                      <input
                        type="number"
                        className="rounded-md border border-border bg-oled px-2 py-1.5 font-mono"
                        value={Number(f.value)}
                        onChange={(e) =>
                          setFields((prev) =>
                            prev.map((x) =>
                              x.key === f.key
                                ? { ...x, value: e.target.value === "" ? 0 : Number(e.target.value) }
                                : x,
                            ),
                          )
                        }
                      />
                    ) : (
                      <input
                        type="text"
                        className="rounded-md border border-border bg-oled px-2 py-1.5 font-mono"
                        value={String(f.value ?? "")}
                        onChange={(e) =>
                          setFields((prev) =>
                            prev.map((x) =>
                              x.key === f.key ? { ...x, value: e.target.value } : x,
                            ),
                          )
                        }
                      />
                    )}
                  </label>
                ))}
              </div>
            )}
          </>
        )}
      </section>
    </div>
  );
}
