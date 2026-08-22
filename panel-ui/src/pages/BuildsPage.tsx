import { useEffect, useMemo, useState } from "react";
import { useOutletContext } from "react-router-dom";
import { Button } from "../components/Button";
import { PageHeader } from "../components/PageHeader";
import type { ShellOutlet } from "../components/Shell";
import { Skeleton } from "../components/Skeleton";
import { cultApi, humanizeError, type GuildBuild } from "../lib/api";

function buildId(b: GuildBuild): string {
  return String(b.id || b.build_id || "");
}

function buildName(b: GuildBuild): string {
  return String(b.name || b.display_name || "Untitled build");
}

export function BuildsPage() {
  const { setFlash } = useOutletContext<ShellOutlet>();
  const [builds, setBuilds] = useState<GuildBuild[]>([]);
  const [loading, setLoading] = useState(true);
  const [warning, setWarning] = useState<string | null>(null);
  const [needsLogin, setNeedsLogin] = useState(false);
  const [query, setQuery] = useState("");
  const [busyId, setBusyId] = useState<string | null>(null);
  const [selected, setSelected] = useState<GuildBuild | null>(null);

  async function load() {
    setLoading(true);
    try {
      const res = await cultApi.builds();
      setBuilds(res.builds || []);
      setWarning(res.warning || null);
      setNeedsLogin(Boolean(res.needs_login));
    } catch (e) {
      setWarning(humanizeError(e));
      setBuilds([]);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
  }, []);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return builds;
    return builds.filter((b) => {
      const hay = [buildName(b), buildId(b), b.loader, b.minecraft_version, b.tagline, b.version]
        .filter(Boolean)
        .join(" ")
        .toLowerCase();
      return hay.includes(q);
    });
  }, [builds, query]);

  async function copyId(id: string) {
    try {
      await navigator.clipboard.writeText(id);
      setFlash({ msg: "Build ID copied", ok: true });
    } catch {
      setFlash({ msg: "Copy failed", ok: false });
    }
  }

  async function install(b: GuildBuild) {
    const id = buildId(b);
    if (!id) return;
    setBusyId(id);
    try {
      await cultApi.command("builds.install", {
        build_id: id,
        include_optional: false,
      });
      setFlash({ msg: `Install started for ${buildName(b)}`, ok: true });
    } catch (e) {
      setFlash({ msg: humanizeError(e), ok: false });
    } finally {
      setBusyId(null);
    }
  }

  if (loading) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-8 w-48" />
        <div className="grid gap-3 sm:grid-cols-2">
          <Skeleton className="h-40 w-full" />
          <Skeleton className="h-40 w-full" />
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <PageHeader
        title="Guild builds"
        subtitle="Published packs from your CultForge guild — install onto this agent."
        actions={
          <div className="flex gap-2">
            <input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search builds…"
              className="w-48 rounded-md border border-border bg-card px-3 py-1.5 text-[13px] outline-none focus:border-neon/40 sm:w-56"
            />
            <Button onClick={() => load()}>Refresh</Button>
          </div>
        }
      />

      {warning && (
        <div className="rounded-md border border-warn/30 bg-warn/10 px-4 py-3 text-[13px] text-warn">
          <strong className="font-semibold">Couldn’t load some builds.</strong> {warning}
          {needsLogin && (
            <div className="mt-2 font-mono text-[12px] text-text-dim">cf-agent login</div>
          )}
        </div>
      )}

      {!builds.length ? (
        <div className="cf-panel px-8 py-12 text-center">
          <h2 className="m-0 text-lg font-semibold">No guild builds yet</h2>
          <p className="mx-auto mt-2 max-w-md text-[13px] text-text-dim">
            Log in with a guild that publishes builds, or clone a server from the CLI.
          </p>
          <div className="mt-5 flex flex-wrap justify-center gap-2">
            <Button onClick={() => load()} variant="primary">
              Try again
            </Button>
            <Button href="/panel/servers/new">Create local server</Button>
          </div>
        </div>
      ) : (
        <div className="grid gap-4 lg:grid-cols-[1.1fr_0.9fr]">
          <div className="grid gap-3 sm:grid-cols-2">
            {filtered.map((b) => {
              const id = buildId(b);
              const active = selected && buildId(selected) === id;
              return (
                <button
                  key={id || buildName(b)}
                  type="button"
                  onClick={() => setSelected(b)}
                  className={[
                    "cf-panel p-4 text-left transition hover:border-border-soft",
                    active ? "border-neon/40 ring-1 ring-neon/30" : "",
                  ].join(" ")}
                >
                  <div className="flex items-start justify-between gap-2">
                    <h3 className="m-0 text-[15px] font-semibold text-text">{buildName(b)}</h3>
                    <span className="shrink-0 rounded-md bg-card-2 px-2 py-0.5 text-[11px] capitalize text-text-dim">
                      {b.loader || "pack"}
                    </span>
                  </div>
                  {b.tagline && (
                    <p className="mt-2 line-clamp-2 text-[12px] leading-relaxed text-text-dim">
                      {String(b.tagline)}
                    </p>
                  )}
                  <div className="mt-3 flex flex-wrap gap-2 text-[11px] text-muted">
                    <span>MC {b.minecraft_version || b.version || "—"}</span>
                    {id && <span className="font-mono">{id.slice(0, 12)}…</span>}
                  </div>
                </button>
              );
            })}
            {!filtered.length && (
              <div className="cf-panel col-span-full px-4 py-8 text-center text-[13px] text-muted">
                No builds match “{query}”.
              </div>
            )}
          </div>

          <aside className="cf-panel sticky top-4 h-fit p-5">
            {selected ? (
              <>
                <h2 className="m-0 text-lg font-semibold">{buildName(selected)}</h2>
                <p className="mt-1 text-[12px] text-muted">
                  {selected.loader || "—"} · MC {selected.minecraft_version || selected.version || "—"}
                </p>
                {selected.tagline && (
                  <p className="mt-3 text-[13px] leading-relaxed text-text-dim">
                    {String(selected.tagline)}
                  </p>
                )}
                <div className="mt-4 space-y-2 border-t border-border pt-4 text-[12px]">
                  <div className="flex justify-between gap-2">
                    <span className="text-muted">Build ID</span>
                    <span className="font-mono text-text-dim">{buildId(selected) || "—"}</span>
                  </div>
                  {selected.guild_id && (
                    <div className="flex justify-between gap-2">
                      <span className="text-muted">Guild</span>
                      <span className="font-mono text-text-dim">{String(selected.guild_id)}</span>
                    </div>
                  )}
                </div>
                <div className="mt-5 flex flex-wrap gap-2">
                  <Button
                    variant="primary"
                    disabled={!buildId(selected) || busyId === buildId(selected)}
                    onClick={() => install(selected)}
                  >
                    Install content
                  </Button>
                  <Button
                    disabled={!buildId(selected)}
                    onClick={() => copyId(buildId(selected))}
                  >
                    Copy ID
                  </Button>
                </div>
                <p className="mt-4 text-[11px] leading-relaxed text-muted">
                  Install pulls mods/content into a local server. For a full clone flow use{" "}
                  <code className="text-text-dim">cf-agent server-clone ?</code>.
                </p>
              </>
            ) : (
              <p className="m-0 text-[13px] text-muted">Select a build to see details and actions.</p>
            )}
          </aside>
        </div>
      )}
    </div>
  );
}
