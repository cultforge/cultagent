import { useCallback, useEffect, useMemo, useState } from "react";
import { useOutletContext, useParams } from "react-router-dom";
import { Button } from "../components/Button";
import type { ServerOutlet } from "../layouts/ServerLayout";
import { cultApi, humanizeError, type FileItem } from "../lib/api";

const IMPORTANT_KIND_ORDER: Record<string, number> = {
  world: 0,
  mods: 1,
  config: 2,
  logs: 3,
  crash: 4,
  libraries: 5,
  packs: 6,
  backup: 7,
};

const NAME_KIND: Record<string, string> = {
  world: "world",
  mods: "mods",
  config: "config",
  configs: "config",
  defaultconfigs: "config",
  logs: "logs",
  "crash-reports": "crash",
  libraries: "libraries",
  resourcepacks: "packs",
  datapacks: "packs",
  shaderpacks: "packs",
  backups: "backup",
};

function resolveKind(item: FileItem): string | null {
  if (!item.is_dir) return null;
  if (item.folder_kind) return item.folder_kind;
  if (item.is_world) return "world";
  return NAME_KIND[item.name.toLowerCase()] || null;
}

function sortFiles(items: FileItem[]): FileItem[] {
  return [...items].sort((a, b) => {
    const aDir = a.is_dir ? 0 : 1;
    const bDir = b.is_dir ? 0 : 1;
    if (aDir !== bDir) return aDir - bDir;
    const aKind = resolveKind(a);
    const bKind = resolveKind(b);
    const aImp = aKind != null ? 0 : 1;
    const bImp = bKind != null ? 0 : 1;
    if (aImp !== bImp) return aImp - bImp;
    if (aKind && bKind) {
      const ao = IMPORTANT_KIND_ORDER[aKind] ?? 50;
      const bo = IMPORTANT_KIND_ORDER[bKind] ?? 50;
      if (ao !== bo) return ao - bo;
    }
    return a.name.localeCompare(b.name, undefined, { sensitivity: "base" });
  });
}

function FolderIcon({ kind }: { kind: string | null }) {
  const common = "h-4 w-4 shrink-0";
  if (kind === "world") {
    return (
      <svg className={`${common} text-neon`} viewBox="0 0 24 24" fill="none" aria-hidden>
        <circle cx="12" cy="12" r="9" stroke="currentColor" strokeWidth="1.6" />
        <path
          d="M3 12h18M12 3c2.5 2.8 3.8 5.8 3.8 9s-1.3 6.2-3.8 9c-2.5-2.8-3.8-5.8-3.8-9S9.5 5.8 12 3z"
          stroke="currentColor"
          strokeWidth="1.4"
        />
      </svg>
    );
  }
  if (kind === "mods") {
    return (
      <svg className={`${common} text-warn`} viewBox="0 0 24 24" fill="none" aria-hidden>
        <rect x="4" y="4" width="7" height="7" rx="1.2" stroke="currentColor" strokeWidth="1.6" />
        <rect x="13" y="4" width="7" height="7" rx="1.2" stroke="currentColor" strokeWidth="1.6" />
        <rect x="4" y="13" width="7" height="7" rx="1.2" stroke="currentColor" strokeWidth="1.6" />
        <rect x="13" y="13" width="7" height="7" rx="1.2" stroke="currentColor" strokeWidth="1.6" />
      </svg>
    );
  }
  if (kind === "config") {
    return (
      <svg className={`${common} text-text-dim`} viewBox="0 0 24 24" fill="none" aria-hidden>
        <circle cx="12" cy="12" r="3" stroke="currentColor" strokeWidth="1.6" />
        <path
          d="M12 3.5v2.2M12 18.3v2.2M3.5 12h2.2M18.3 12h2.2M6.1 6.1l1.6 1.6M16.3 16.3l1.6 1.6M17.9 6.1l-1.6 1.6M7.7 16.3l-1.6 1.6"
          stroke="currentColor"
          strokeWidth="1.5"
          strokeLinecap="round"
        />
      </svg>
    );
  }
  if (kind === "logs" || kind === "crash") {
    return (
      <svg
        className={`${common} ${kind === "crash" ? "text-danger" : "text-muted"}`}
        viewBox="0 0 24 24"
        fill="none"
        aria-hidden
      >
        <path
          d="M7 3.5h7.2L19 8.3V20a1 1 0 0 1-1 1H7a1 1 0 0 1-1-1V4.5a1 1 0 0 1 1-1z"
          stroke="currentColor"
          strokeWidth="1.6"
        />
        <path d="M14 3.8V8h4.2M8.5 12h7M8.5 15.5h7M8.5 19h4.5" stroke="currentColor" strokeWidth="1.4" />
      </svg>
    );
  }
  if (kind === "libraries") {
    return (
      <svg className={`${common} text-muted`} viewBox="0 0 24 24" fill="none" aria-hidden>
        <path d="M5 5.5h5.5v13H5zM13.5 5.5H19v13h-5.5z" stroke="currentColor" strokeWidth="1.6" />
        <path d="M7 8.5h1.5M7 12h1.5M15.5 8.5H17M15.5 12H17" stroke="currentColor" strokeWidth="1.4" />
      </svg>
    );
  }
  if (kind === "packs") {
    return (
      <svg className={`${common} text-text-dim`} viewBox="0 0 24 24" fill="none" aria-hidden>
        <path
          d="M4.5 8.5 12 4.5l7.5 4V16L12 20l-7.5-4V8.5z"
          stroke="currentColor"
          strokeWidth="1.6"
        />
        <path d="M12 12v8M4.5 8.5 12 12l7.5-3.5" stroke="currentColor" strokeWidth="1.4" />
      </svg>
    );
  }
  if (kind === "backup") {
    return (
      <svg className={`${common} text-text-dim`} viewBox="0 0 24 24" fill="none" aria-hidden>
        <path
          d="M7 7a6 6 0 0 1 10.4 2.2M17 17a6 6 0 0 1-10.5-2"
          stroke="currentColor"
          strokeWidth="1.6"
          strokeLinecap="round"
        />
        <path d="M17 5.5V9h-3.5M7 18.5V15h3.5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
      </svg>
    );
  }
  // Generic folder
  return (
    <svg className={`${common} text-muted`} viewBox="0 0 24 24" fill="none" aria-hidden>
      <path
        d="M3.5 8.5A1.5 1.5 0 0 1 5 7h4.2l1.6 1.6H19a1.5 1.5 0 0 1 1.5 1.5v7.4A1.5 1.5 0 0 1 19 19H5a1.5 1.5 0 0 1-1.5-1.5V8.5z"
        stroke="currentColor"
        strokeWidth="1.6"
      />
    </svg>
  );
}

function FileIcon() {
  return (
    <svg className="h-4 w-4 shrink-0 text-muted" viewBox="0 0 24 24" fill="none" aria-hidden>
      <path
        d="M7 3.5h7.2L19 8.3V20a1 1 0 0 1-1 1H7a1 1 0 0 1-1-1V4.5a1 1 0 0 1 1-1z"
        stroke="currentColor"
        strokeWidth="1.6"
      />
      <path d="M14 3.8V8h4.2" stroke="currentColor" strokeWidth="1.5" />
    </svg>
  );
}

function kindBadge(kind: string | null): string | null {
  if (!kind) return null;
  if (kind === "world") return "world";
  if (kind === "mods") return "mods";
  if (kind === "config") return "config";
  if (kind === "crash") return "crash";
  if (kind === "logs") return "logs";
  return null;
}

export function FilesPage() {
  const { serverId = "" } = useParams();
  const { setFlash } = useOutletContext<ServerOutlet>();
  const [path, setPath] = useState(".");
  const [items, setItems] = useState<FileItem[]>([]);
  const [preview, setPreview] = useState<{ path: string; content: string } | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  const load = useCallback(
    async (rel: string) => {
      setLoading(true);
      try {
        const res = await cultApi.files(serverId, rel);
        setItems(res.items || []);
        setPath(rel);
        setPreview(null);
      } catch (e) {
        setFlash({ msg: humanizeError(e), ok: false });
      } finally {
        setLoading(false);
      }
    },
    [serverId, setFlash],
  );

  useEffect(() => {
    load(".");
  }, [load]);

  const sorted = useMemo(() => sortFiles(items), [items]);

  async function openItem(item: FileItem) {
    if (item.is_dir) {
      await load(item.path);
      return;
    }
    try {
      const res = await cultApi.fileRead(serverId, item.path);
      setPreview({ path: item.path, content: res.content || "" });
    } catch (e) {
      setFlash({ msg: humanizeError(e), ok: false });
    }
  }

  function parentPath(rel: string) {
    if (!rel || rel === ".") return ".";
    const parts = rel.replace(/\\/g, "/").split("/").filter(Boolean);
    parts.pop();
    return parts.length ? parts.join("/") : ".";
  }

  async function savePreview() {
    if (!preview) return;
    setSaving(true);
    try {
      await cultApi.fileWrite(serverId, preview.path, preview.content);
      setFlash({ msg: "File saved", ok: true });
    } catch (e) {
      setFlash({ msg: humanizeError(e), ok: false });
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="grid gap-4 lg:grid-cols-[minmax(240px,0.9fr)_1.3fr]">
      <div className="cf-panel p-4">
        <div className="mb-3 flex items-center justify-between gap-2">
          <div>
            <h2 className="m-0 text-[13px] font-semibold">Files</h2>
            <p className="m-0 mt-0.5 font-mono text-[11px] text-muted">{path}</p>
          </div>
          <Button variant="ghost" disabled={path === "."} onClick={() => load(parentPath(path))}>
            Up
          </Button>
        </div>
        {loading ? (
          <p className="text-[13px] text-text-dim">Loading…</p>
        ) : (
          <ul className="m-0 max-h-[520px] list-none space-y-0.5 overflow-auto p-0">
            {sorted.map((item) => {
              const kind = resolveKind(item);
              const badge = kindBadge(kind);
              const important = kind != null;
              return (
                <li key={item.path}>
                  <button
                    type="button"
                    onClick={() => openItem(item)}
                    className={[
                      "flex w-full items-center justify-between gap-2 rounded-md px-2.5 py-2 text-left text-[13px] text-text transition hover:bg-card-2",
                      important ? "bg-card-2/40" : "",
                      kind === "world" ? "ring-1 ring-inset ring-neon/20" : "",
                    ].join(" ")}
                  >
                    <span className="flex min-w-0 items-center gap-2 truncate">
                      {item.is_dir ? <FolderIcon kind={kind} /> : <FileIcon />}
                      <span className="truncate">{item.name}</span>
                      {badge && (
                        <span className="shrink-0 rounded border border-border bg-oled-elev px-1.5 py-0.5 text-[10px] uppercase tracking-wide text-muted">
                          {badge}
                        </span>
                      )}
                    </span>
                    {!item.is_dir && item.size != null && (
                      <span className="shrink-0 font-mono text-[11px] text-muted">
                        {item.size > 1024
                          ? `${Math.round(item.size / 1024)} KB`
                          : `${item.size} B`}
                      </span>
                    )}
                  </button>
                </li>
              );
            })}
            {!sorted.length && (
              <li className="px-2 py-4 text-[13px] text-muted">Empty folder</li>
            )}
          </ul>
        )}
      </div>

      <div className="cf-panel flex min-h-[420px] flex-col p-4">
        {preview ? (
          <>
            <div className="mb-3 flex items-center justify-between gap-2">
              <h2 className="m-0 truncate font-mono text-[12px] text-text-dim">{preview.path}</h2>
              <Button variant="primary" disabled={saving} onClick={savePreview}>
                Save
              </Button>
            </div>
            <textarea
              value={preview.content}
              onChange={(e) => setPreview({ ...preview, content: e.target.value })}
              className="min-h-0 flex-1 resize-none rounded-md border border-border bg-oled p-3 font-mono text-[12px] text-text outline-none focus:border-neon/40"
            />
          </>
        ) : (
          <div className="flex flex-1 items-center justify-center text-[13px] text-muted">
            Select a file to preview and edit
          </div>
        )}
      </div>
    </div>
  );
}
