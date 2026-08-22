import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useOutletContext, useSearchParams } from "react-router-dom";
import { Button } from "../components/Button";
import type { ShellOutlet } from "../components/Shell";
import {
  cultApi,
  humanizeError,
  type GuildBuild,
  type GuildServerRow,
} from "../lib/api";

type PathId = "scratch" | "clone" | "build";

const LOADERS: Array<{ id: string; label: string; hint: string }> = [
  { id: "paper", label: "Paper", hint: "Plugins · recommended" },
  { id: "purpur", label: "Purpur", hint: "Paper fork · extras" },
  { id: "folia", label: "Folia", hint: "Regionized multithreading" },
  { id: "vanilla", label: "Vanilla", hint: "Stock Mojang server" },
  { id: "fabric", label: "Fabric", hint: "Lightweight mods" },
  { id: "quilt", label: "Quilt", hint: "Fabric-compatible mods" },
  { id: "forge", label: "Forge", hint: "Classic mod ecosystem" },
  { id: "neoforge", label: "NeoForge", hint: "Modern Forge fork" },
];

const MC_VERSIONS = ["1.21.4", "1.21.1", "1.20.4", "1.20.1", "1.19.2"];

const JVM_PRESETS = [
  { id: "", label: "Default (catalog)" },
  { id: "low_ram", label: "Low RAM" },
  { id: "balanced", label: "Balanced" },
  { id: "aikar", label: "Aikar-style" },
];

const inputCls =
  "mt-1.5 w-full rounded-md border border-border bg-oled-elev px-3 py-2 text-[13px] text-text outline-none focus:border-neon/40";
const labelCls = "block text-[13px] font-medium text-text";

function guildServerId(row: GuildServerRow): string {
  return String(row.id || row.server_id || "");
}

function guildServerName(row: GuildServerRow): string {
  return String(row.name || row.display_name || guildServerId(row) || "unnamed");
}

function buildIdOf(b: GuildBuild): string {
  return String(b.id || b.build_id || "");
}

function buildNameOf(b: GuildBuild): string {
  return String(b.name || b.display_name || "Untitled build");
}

export function NewServerPage() {
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const { setFlash } = useOutletContext<ShellOutlet>();

  const initialPath = (params.get("path") as PathId | null) || null;
  const [path, setPath] = useState<PathId | null>(initialPath);
  const [step, setStep] = useState(initialPath ? 1 : 0);
  const [busy, setBusy] = useState(false);

  // Scratch
  const [form, setForm] = useState({
    name: "",
    port: 25565,
    minecraft_version: "1.20.1",
    loader: "paper",
    download: true,
    accept_eula: true,
    start_now: true,
    auto_start: false,
    jvm_preset: "",
  });
  const [javaOk, setJavaOk] = useState<boolean | null>(null);
  const [javaLabel, setJavaLabel] = useState("");

  // Clone
  const [guildServers, setGuildServers] = useState<GuildServerRow[]>([]);
  const [guildWarning, setGuildWarning] = useState<string | null>(null);
  const [guildNeedsLogin, setGuildNeedsLogin] = useState(false);
  const [guildQuery, setGuildQuery] = useState("");
  const [pickedGuild, setPickedGuild] = useState<string>("");
  const [cloneName, setCloneName] = useState("");
  const [clonePort, setClonePort] = useState(25565);
  const [cloneDownload, setCloneDownload] = useState(true);
  const [cloneEula, setCloneEula] = useState(true);

  // Build
  const [builds, setBuilds] = useState<GuildBuild[]>([]);
  const [buildWarning, setBuildWarning] = useState<string | null>(null);
  const [buildNeedsLogin, setBuildNeedsLogin] = useState(false);
  const [buildQuery, setBuildQuery] = useState("");
  const [pickedBuild, setPickedBuild] = useState<string>("");
  const [buildName, setBuildName] = useState("");
  const [includeOptional, setIncludeOptional] = useState(false);
  const [desiredState, setDesiredState] = useState<"stopped" | "running">("stopped");

  useEffect(() => {
    const p = params.get("path") as PathId | null;
    if (p === "scratch" || p === "clone" || p === "build") {
      setPath(p);
      setStep(1);
    }
  }, [params]);

  useEffect(() => {
    if (path !== "scratch") return;
    let alive = true;
    cultApi
      .dashboard()
      .then((d) => {
        if (!alive) return;
        setJavaOk(Boolean(d.java?.ok));
        setJavaLabel(
          d.java?.ok
            ? `${d.java.version || "Java"} · ${d.java.path || ""}`
            : "Java not detected — install a JDK before starting",
        );
      })
      .catch(() => {
        if (alive) setJavaOk(null);
      });
    return () => {
      alive = false;
    };
  }, [path]);

  useEffect(() => {
    if (path !== "clone") return;
    let alive = true;
    cultApi.guildServers().then((res) => {
      if (!alive) return;
      setGuildServers(res.servers);
      setGuildWarning(res.warning || null);
      setGuildNeedsLogin(Boolean(res.needs_login));
      if (res.servers[0] && !pickedGuild) {
        setPickedGuild(guildServerId(res.servers[0]));
      }
    });
    return () => {
      alive = false;
    };
  }, [path, pickedGuild]);

  useEffect(() => {
    if (path !== "build") return;
    let alive = true;
    cultApi.builds().then((res) => {
      if (!alive) return;
      setBuilds(res.builds || []);
      setBuildWarning(res.warning || null);
      setBuildNeedsLogin(Boolean(res.needs_login));
      if (res.builds?.[0] && !pickedBuild) {
        setPickedBuild(buildIdOf(res.builds[0]));
      }
    });
    return () => {
      alive = false;
    };
  }, [path, pickedBuild]);

  const filteredGuild = useMemo(() => {
    const q = guildQuery.trim().toLowerCase();
    if (!q) return guildServers;
    return guildServers.filter((s) => {
      const hay = [guildServerName(s), guildServerId(s), s.loader, s.minecraft_version, s.build_id]
        .filter(Boolean)
        .join(" ")
        .toLowerCase();
      return hay.includes(q);
    });
  }, [guildServers, guildQuery]);

  const filteredBuilds = useMemo(() => {
    const q = buildQuery.trim().toLowerCase();
    if (!q) return builds;
    return builds.filter((b) => {
      const hay = [buildNameOf(b), buildIdOf(b), b.loader, b.minecraft_version, b.tagline]
        .filter(Boolean)
        .join(" ")
        .toLowerCase();
      return hay.includes(q);
    });
  }, [builds, buildQuery]);

  const scratchSteps = ["Name", "Platform", "Install"] as const;
  const canContinueScratch = useMemo(() => {
    if (step === 1) return form.name.trim().length > 0;
    return true;
  }, [form.name, step]);

  function setField<K extends keyof typeof form>(key: K, value: (typeof form)[K]) {
    setForm((prev) => ({ ...prev, [key]: value }));
  }

  function choosePath(next: PathId) {
    setPath(next);
    setStep(1);
  }

  async function submitScratch() {
    setBusy(true);
    try {
      const res = await cultApi.createServer({
        name: form.name.trim(),
        port: form.port,
        minecraft_version: form.minecraft_version.trim() || null,
        loader: form.loader,
        download: form.download,
        accept_eula: form.accept_eula,
        auto_start: form.auto_start,
      });
      const sid = res.data?.server_id;
      if (!sid) throw new Error("Server created but id missing");

      if (form.jvm_preset) {
        try {
          await cultApi.jvmSavePreset(sid, form.jvm_preset);
        } catch {
          /* non-fatal */
        }
      }

      if (form.start_now) {
        try {
          await cultApi.action(sid, "start");
          setFlash({ msg: "Server created — starting…", ok: true });
        } catch (e) {
          setFlash({
            msg: `Created, but start failed: ${humanizeError(e)}`,
            ok: false,
          });
          navigate(`/servers/${sid}`);
          return;
        }
      } else {
        setFlash({ msg: "Server created", ok: true });
      }
      navigate(`/servers/${sid}`);
    } catch (e) {
      setFlash({ msg: humanizeError(e), ok: false });
    } finally {
      setBusy(false);
    }
  }

  async function submitClone() {
    if (!pickedGuild) {
      setFlash({ msg: "Pick a guild server", ok: false });
      return;
    }
    setBusy(true);
    try {
      const res = await cultApi.cloneServer({
        guild_server_id: pickedGuild,
        name: cloneName.trim() || undefined,
        port: clonePort,
        download: cloneDownload,
        accept_eula: cloneEula,
      });
      const sid = String(res.data?.local_server_id || "");
      if (!sid) throw new Error("Clone succeeded but local_server_id missing");
      setFlash({ msg: "Guild server cloned", ok: true });
      navigate(`/servers/${sid}`);
    } catch (e) {
      setFlash({ msg: humanizeError(e), ok: false });
    } finally {
      setBusy(false);
    }
  }

  async function submitBuild() {
    if (!pickedBuild) {
      setFlash({ msg: "Pick a guild build", ok: false });
      return;
    }
    setBusy(true);
    try {
      const res = await cultApi.provisionBuild({
        build_id: pickedBuild,
        display_name: buildName.trim() || undefined,
        include_optional: includeOptional,
        desired_state: desiredState,
        create_local_server: true,
        install: true,
      });
      const sid = String(res.data?.local_server_id || "");
      if (!sid) throw new Error("Provision finished but local_server_id missing");
      setFlash({ msg: "Build provisioned", ok: true });
      navigate(`/servers/${sid}`);
    } catch (e) {
      setFlash({ msg: humanizeError(e), ok: false });
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="mx-auto max-w-2xl space-y-5">
      <div>
        <h1 className="m-0 text-[22px] font-semibold tracking-tight">Create your server</h1>
        <p className="m-0 mt-1.5 text-[13px] text-muted">
          Scratch install, clone a guild catalog server, or deploy a published build — same arsenal
          as <code className="font-mono text-[11px]">cf-agent</code>.
        </p>
      </div>

      {/* Path picker */}
      {(step === 0 || path === null) && (
        <div className="grid gap-3 sm:grid-cols-3">
          {(
            [
              {
                id: "scratch" as const,
                title: "Scratch",
                body: "Paper / Fabric / Forge and friends. Local installer.",
              },
              {
                id: "clone" as const,
                title: "Clone guild",
                body: "Git-style clone from your guild catalog.",
              },
              {
                id: "build" as const,
                title: "Deploy build",
                body: "Provision a published guild pack onto this host.",
              },
            ] as const
          ).map((card) => (
            <button
              key={card.id}
              type="button"
              onClick={() => choosePath(card.id)}
              className="cf-panel p-4 text-left transition hover:border-neon/35"
            >
              <div className="text-[14px] font-semibold">{card.title}</div>
              <p className="m-0 mt-1.5 text-[12px] leading-snug text-muted">{card.body}</p>
            </button>
          ))}
        </div>
      )}

      {path && (
        <div className="flex flex-wrap items-center gap-2 text-[12px] text-muted">
          <button
            type="button"
            className="text-neon hover:underline"
            onClick={() => {
              setPath(null);
              setStep(0);
            }}
          >
            Change path
          </button>
          <span>·</span>
          <span className="capitalize text-text-dim">{path}</span>
        </div>
      )}

      {/* Scratch wizard */}
      {path === "scratch" && (
        <>
          <ol className="m-0 flex list-none gap-2 p-0">
            {scratchSteps.map((label, i) => {
              const idx = i + 1;
              return (
                <li
                  key={label}
                  className={[
                    "flex-1 rounded-md border px-3 py-2 text-center text-[12px] font-medium",
                    step === idx
                      ? "border-neon/40 bg-neon/10 text-neon"
                      : step > idx
                        ? "border-border bg-card-2 text-text-dim"
                        : "border-border text-muted",
                  ].join(" ")}
                >
                  {idx}. {label}
                </li>
              );
            })}
          </ol>

          <section className="cf-panel space-y-4 p-5">
            {step === 1 && (
              <>
                <h2 className="m-0 text-[15px] font-semibold">Name your world</h2>
                <label className={labelCls}>
                  Display name
                  <input
                    className={inputCls}
                    value={form.name}
                    placeholder="My Survival Server"
                    autoComplete="off"
                    onChange={(e) => setField("name", e.target.value)}
                  />
                </label>
                <label className={labelCls}>
                  Port
                  <input
                    className={`${inputCls} font-mono`}
                    type="number"
                    min={1}
                    max={65535}
                    value={form.port}
                    onChange={(e) => setField("port", Number(e.target.value) || 25565)}
                  />
                </label>
              </>
            )}

            {step === 2 && (
              <>
                <h2 className="m-0 text-[15px] font-semibold">Pick a platform</h2>
                <div className="grid gap-2 sm:grid-cols-2">
                  {LOADERS.map((l) => (
                    <button
                      key={l.id}
                      type="button"
                      onClick={() => setField("loader", l.id)}
                      className={[
                        "rounded-md border px-3 py-2.5 text-left transition",
                        form.loader === l.id
                          ? "border-neon/40 bg-neon/10"
                          : "border-border bg-card-2/40 hover:border-border-soft",
                      ].join(" ")}
                    >
                      <div className="text-[13px] font-medium">{l.label}</div>
                      <div className="mt-0.5 text-[11px] text-muted">{l.hint}</div>
                    </button>
                  ))}
                </div>
                <div>
                  <div className={labelCls}>Minecraft version</div>
                  <div className="mt-2 flex flex-wrap gap-1.5">
                    {MC_VERSIONS.map((v) => (
                      <button
                        key={v}
                        type="button"
                        onClick={() => setField("minecraft_version", v)}
                        className={[
                          "rounded-md border px-2.5 py-1 font-mono text-[12px]",
                          form.minecraft_version === v
                            ? "border-neon/40 bg-neon/10 text-neon"
                            : "border-border text-text-dim hover:border-border-soft",
                        ].join(" ")}
                      >
                        {v}
                      </button>
                    ))}
                  </div>
                  <input
                    className={`${inputCls} mt-2 font-mono`}
                    value={form.minecraft_version}
                    placeholder="custom e.g. 1.21.3"
                    onChange={(e) => setField("minecraft_version", e.target.value)}
                  />
                </div>
              </>
            )}

            {step === 3 && (
              <>
                <h2 className="m-0 text-[15px] font-semibold">Install &amp; start</h2>
                {javaOk != null && (
                  <div
                    className={[
                      "rounded-md border px-3 py-2 text-[12px]",
                      javaOk
                        ? "border-ok/30 bg-ok/10 text-ok"
                        : "border-warn/30 bg-warn/10 text-warn",
                    ].join(" ")}
                  >
                    {javaLabel}
                  </div>
                )}
                {(
                  [
                    ["download", "Download server files now"],
                    ["accept_eula", "Accept Minecraft EULA"],
                    ["start_now", "Start when ready"],
                    ["auto_start", "Auto-start with CultAgent"],
                  ] as const
                ).map(([key, label]) => (
                  <label key={key} className="flex items-center gap-2.5 text-[13px] text-text">
                    <input
                      type="checkbox"
                      checked={form[key]}
                      onChange={(e) => setField(key, e.target.checked)}
                      className="accent-[var(--neon,#39ff14)]"
                    />
                    {label}
                  </label>
                ))}
                <label className={labelCls}>
                  JVM preset (optional)
                  <select
                    className={inputCls}
                    value={form.jvm_preset}
                    onChange={(e) => setField("jvm_preset", e.target.value)}
                  >
                    {JVM_PRESETS.map((p) => (
                      <option key={p.id || "none"} value={p.id}>
                        {p.label}
                      </option>
                    ))}
                  </select>
                </label>
              </>
            )}

            <div className="flex flex-wrap gap-2 pt-1">
              {step > 1 ? (
                <Button variant="ghost" disabled={busy} onClick={() => setStep((s) => s - 1)}>
                  Back
                </Button>
              ) : (
                <Button variant="ghost" disabled={busy} onClick={() => { setPath(null); setStep(0); }}>
                  Cancel
                </Button>
              )}
              {step < 3 ? (
                <Button
                  variant="primary"
                  disabled={!canContinueScratch || busy}
                  onClick={() => setStep((s) => s + 1)}
                >
                  Continue
                </Button>
              ) : (
                <Button variant="primary" size="xl" disabled={busy} onClick={submitScratch}>
                  {busy ? "Creating…" : "Create server"}
                </Button>
              )}
            </div>
          </section>
        </>
      )}

      {/* Clone */}
      {path === "clone" && (
        <section className="cf-panel space-y-4 p-5">
          <h2 className="m-0 text-[15px] font-semibold">Clone guild server</h2>
          {(guildWarning || guildNeedsLogin) && (
            <div className="rounded-md border border-warn/30 bg-warn/10 px-3 py-2 text-[13px] text-warn">
              {guildWarning || "Login required"}
              {guildNeedsLogin && (
                <div className="mt-1 font-mono text-[12px] text-text-dim">cf-agent login</div>
              )}
            </div>
          )}
          <input
            className={inputCls}
            value={guildQuery}
            onChange={(e) => setGuildQuery(e.target.value)}
            placeholder="Search guild servers…"
          />
          <div className="max-h-[280px] space-y-1 overflow-y-auto">
            {filteredGuild.map((s) => {
              const id = guildServerId(s);
              return (
                <button
                  key={id}
                  type="button"
                  onClick={() => setPickedGuild(id)}
                  className={[
                    "flex w-full items-start justify-between gap-2 rounded-md border px-3 py-2 text-left",
                    pickedGuild === id
                      ? "border-neon/40 bg-neon/10"
                      : "border-border bg-card-2/30 hover:border-border-soft",
                  ].join(" ")}
                >
                  <div>
                    <div className="text-[13px] font-medium">{guildServerName(s)}</div>
                    <div className="mt-0.5 font-mono text-[11px] text-muted">{id}</div>
                  </div>
                  <div className="text-[11px] text-muted">
                    {s.loader || "—"}
                    {s.minecraft_version ? ` · ${s.minecraft_version}` : ""}
                  </div>
                </button>
              );
            })}
            {!filteredGuild.length && !guildWarning && (
              <p className="m-0 text-[13px] text-muted">No guild servers found.</p>
            )}
          </div>
          <label className={labelCls}>
            Local name (optional)
            <input
              className={inputCls}
              value={cloneName}
              onChange={(e) => setCloneName(e.target.value)}
              placeholder="Keep guild name"
            />
          </label>
          <label className={labelCls}>
            Port
            <input
              className={`${inputCls} font-mono`}
              type="number"
              value={clonePort}
              onChange={(e) => setClonePort(Number(e.target.value) || 25565)}
            />
          </label>
          <label className="flex items-center gap-2.5 text-[13px]">
            <input
              type="checkbox"
              checked={cloneDownload}
              onChange={(e) => setCloneDownload(e.target.checked)}
            />
            Download / install platform files
          </label>
          <label className="flex items-center gap-2.5 text-[13px]">
            <input
              type="checkbox"
              checked={cloneEula}
              onChange={(e) => setCloneEula(e.target.checked)}
            />
            Accept Minecraft EULA
          </label>
          <div className="flex flex-wrap gap-2">
            <Button variant="ghost" onClick={() => { setPath(null); setStep(0); }}>
              Back
            </Button>
            <Button
              variant="primary"
              disabled={busy || !pickedGuild}
              onClick={submitClone}
            >
              {busy ? "Cloning…" : "Clone server"}
            </Button>
          </div>
        </section>
      )}

      {/* Build */}
      {path === "build" && (
        <section className="cf-panel space-y-4 p-5">
          <h2 className="m-0 text-[15px] font-semibold">Deploy guild build</h2>
          {(buildWarning || buildNeedsLogin) && (
            <div className="rounded-md border border-warn/30 bg-warn/10 px-3 py-2 text-[13px] text-warn">
              {buildWarning || "Login required"}
              {buildNeedsLogin && (
                <div className="mt-1 font-mono text-[12px] text-text-dim">cf-agent login</div>
              )}
            </div>
          )}
          <input
            className={inputCls}
            value={buildQuery}
            onChange={(e) => setBuildQuery(e.target.value)}
            placeholder="Search builds…"
          />
          <div className="max-h-[280px] space-y-1 overflow-y-auto">
            {filteredBuilds.map((b) => {
              const id = buildIdOf(b);
              return (
                <button
                  key={id}
                  type="button"
                  onClick={() => setPickedBuild(id)}
                  className={[
                    "flex w-full items-start justify-between gap-2 rounded-md border px-3 py-2 text-left",
                    pickedBuild === id
                      ? "border-neon/40 bg-neon/10"
                      : "border-border bg-card-2/30 hover:border-border-soft",
                  ].join(" ")}
                >
                  <div>
                    <div className="text-[13px] font-medium">{buildNameOf(b)}</div>
                    {b.tagline && (
                      <div className="mt-0.5 line-clamp-1 text-[11px] text-muted">
                        {String(b.tagline)}
                      </div>
                    )}
                  </div>
                  <div className="shrink-0 text-[11px] capitalize text-muted">
                    {b.loader || "pack"}
                    {b.minecraft_version ? ` · ${b.minecraft_version}` : ""}
                  </div>
                </button>
              );
            })}
            {!filteredBuilds.length && !buildWarning && (
              <p className="m-0 text-[13px] text-muted">
                No builds. Browse{" "}
                <Link to="/builds" className="text-neon">
                  Builds
                </Link>
                .
              </p>
            )}
          </div>
          <label className={labelCls}>
            Display name (optional)
            <input
              className={inputCls}
              value={buildName}
              onChange={(e) => setBuildName(e.target.value)}
              placeholder="Use build name"
            />
          </label>
          <label className="flex items-center gap-2.5 text-[13px]">
            <input
              type="checkbox"
              checked={includeOptional}
              onChange={(e) => setIncludeOptional(e.target.checked)}
            />
            Include optional content
          </label>
          <label className={labelCls}>
            Desired state
            <select
              className={inputCls}
              value={desiredState}
              onChange={(e) => setDesiredState(e.target.value as "stopped" | "running")}
            >
              <option value="stopped">stopped</option>
              <option value="running">running</option>
            </select>
          </label>
          <div className="flex flex-wrap gap-2">
            <Button variant="ghost" onClick={() => { setPath(null); setStep(0); }}>
              Back
            </Button>
            <Button
              variant="primary"
              disabled={busy || !pickedBuild}
              onClick={submitBuild}
            >
              {busy ? "Provisioning…" : "Provision build"}
            </Button>
          </div>
        </section>
      )}
    </div>
  );
}
