import { useCallback, useEffect, useState, type FormEvent, type ReactNode } from "react";
import { useOutletContext } from "react-router-dom";
import { Button } from "../components/Button";
import { PageHeader } from "../components/PageHeader";
import { Section } from "../components/Section";
import type { ShellOutlet } from "../components/Shell";
import { Skeleton } from "../components/Skeleton";
import { StatusChip } from "../components/Status";
import { cultApi, humanizeError, type NetworkStatus } from "../lib/api";

function Step({
  done,
  title,
  children,
}: {
  done?: boolean;
  title: string;
  children: ReactNode;
}) {
  return (
    <li className="relative border-b border-border py-5 last:border-b-0 last:pb-0 first:pt-0">
      <div className="mb-2 flex items-center gap-2">
        <span
          className={[
            "inline-flex h-5 w-5 items-center justify-center rounded-full text-[11px] font-semibold",
            done ? "bg-ok/20 text-ok" : "bg-card-2 text-muted",
          ].join(" ")}
        >
          {done ? "✓" : ""}
        </span>
        <h3 className="m-0 text-[14px] font-semibold text-text">{title}</h3>
      </div>
      <div className="pl-7 text-[13px] text-text-dim">{children}</div>
    </li>
  );
}

function Kv({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="grid grid-cols-[7rem_minmax(0,1fr)] gap-x-3 gap-y-1 border-b border-border/70 py-2.5 text-[13px] last:border-b-0">
      <dt className="text-muted">{label}</dt>
      <dd className="m-0 min-w-0 break-all text-text">{children}</dd>
    </div>
  );
}

export function NetworkPage() {
  const { setFlash } = useOutletContext<ShellOutlet>();
  const [network, setNetwork] = useState<NetworkStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState<string | null>(null);
  const [secret, setSecret] = useState("");

  const refresh = useCallback(async () => {
    const res = await cultApi.network();
    setNetwork(res.network || null);
  }, []);

  useEffect(() => {
    let alive = true;
    (async () => {
      try {
        await refresh();
      } catch (e) {
        if (alive) setFlash({ msg: humanizeError(e), ok: false });
      } finally {
        if (alive) setLoading(false);
      }
    })();
    return () => {
      alive = false;
    };
  }, [refresh, setFlash]);

  async function run(
    key: string,
    fn: () => Promise<void>,
    opts?: { reload?: boolean },
  ) {
    setBusy(key);
    try {
      await fn();
      if (opts?.reload !== false) await refresh();
    } catch (e) {
      setFlash({ msg: humanizeError(e), ok: false });
    } finally {
      setBusy(null);
    }
  }

  if (loading) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-8 w-40" />
        <div className="grid gap-4 lg:grid-cols-2">
          <Skeleton className="h-64 w-full" />
          <Skeleton className="h-64 w-full" />
        </div>
      </div>
    );
  }

  const d = (network?.details || {}) as NonNullable<NetworkStatus["details"]>;
  const plat = d.platform || {};
  const hasSecret = Boolean(d.has_secret);
  const hasBinary = Boolean(d.binary);
  const publicJoin = network?.public_join || network?.public_endpoint || null;
  const provider = network?.active || network?.provider || "direct";
  const status = network?.status || "—";
  const setupUrl =
    d.setup_url ||
    d.setup_claim_url ||
    "https://playit.gg/account/setup/wizard/new-account/computer/claim-code";
  const secretUrl =
    d.setup_secret_url ||
    "https://playit.gg/account/setup/wizard/new-account/docker/docker-name";
  const agentsUrl = d.agents_url || "https://playit.gg/account/agents";
  const downloadUrl = d.download_url || "https://playit.gg/download";
  const supportUrl = d.support_url || "https://playit.gg/support/";
  const port = String(network?.target || "127.0.0.1:25565").split(":").pop() || "25565";
  const onlineish =
    status === "running" || status === "online" || status === "active" || Boolean(publicJoin);

  const setupSteps = [
    { label: "Binary", done: hasBinary },
    { label: "Secret", done: hasSecret },
    { label: "Tunnel", done: Boolean(publicJoin || d.tunnel_count) },
    { label: "Live", done: onlineish && provider === "playit" },
  ];
  const setupDone = setupSteps.filter((s) => s.done).length;

  async function copyPublic() {
    if (!publicJoin) return;
    try {
      await navigator.clipboard.writeText(publicJoin);
      setFlash({ msg: "Public join copied", ok: true });
    } catch {
      setFlash({ msg: "Copy failed", ok: false });
    }
  }

  async function saveSecret(e: FormEvent) {
    e.preventDefault();
    const value = secret.trim();
    if (!value) {
      setFlash({ msg: "Paste a secret key first", ok: false });
      return;
    }
    await run("secret", async () => {
      await cultApi.command("playit.secret", { secret: value });
      setSecret("");
      setFlash({ msg: "Secret saved on this machine", ok: true });
    });
  }

  return (
    <div className="space-y-6">
      <PageHeader
        title="Network"
        subtitle="Official playit.gg agent for this host. Secrets stay on this machine."
        actions={
          <div className="flex flex-wrap gap-2">
            <Button href={supportUrl} variant="ghost">
              Support
            </Button>
            <Button href={agentsUrl} variant="ghost">
              Agents
            </Button>
            <Button href={downloadUrl} variant="ghost">
              Download
            </Button>
          </div>
        }
      />

      <div className="flex flex-wrap gap-2">
        <StatusChip state={onlineish ? "online" : status === "error" ? "crashed" : "stopped"} />
        <span className="rounded-md border border-border bg-card-2 px-2 py-0.5 text-[11px] font-medium capitalize text-text-dim">
          {provider}
        </span>
        {plat.platform && (
          <span className="rounded-md border border-border bg-card-2 px-2 py-0.5 text-[11px] font-medium text-text-dim">
            {plat.platform}
          </span>
        )}
        {d.release_pin && (
          <span className="rounded-md border border-border bg-card-2 px-2 py-0.5 font-mono text-[11px] text-muted">
            {d.release_pin}
          </span>
        )}
      </div>

      <div className="cf-panel p-4">
        <div className="mb-2 flex items-center justify-between text-[12px]">
          <span className="font-medium text-text">Setup progress</span>
          <span className="tabular-nums text-muted">
            {setupDone}/{setupSteps.length}
          </span>
        </div>
        <div className="mb-3 h-1.5 overflow-hidden rounded-full bg-border">
          <div
            className="h-full rounded-full bg-neon transition-all"
            style={{ width: `${(setupDone / setupSteps.length) * 100}%` }}
          />
        </div>
        <div className="flex flex-wrap gap-2">
          {setupSteps.map((s) => (
            <span
              key={s.label}
              className={[
                "rounded-md border px-2.5 py-1 text-[11px] font-medium",
                s.done
                  ? "border-ok/30 bg-ok/10 text-ok"
                  : "border-border bg-card-2 text-muted",
              ].join(" ")}
            >
              {s.done ? "✓ " : ""}
              {s.label}
            </span>
          ))}
        </div>
      </div>

      <div className="grid gap-4 lg:grid-cols-[0.95fr_1.15fr]">
        <section className="cf-panel p-5">
          <h2 className="m-0 text-[13px] font-semibold">Status</h2>
          <dl className="mt-2 m-0">
            <Kv label="Provider">{provider}</Kv>
            <Kv label="Status">{status}</Kv>
            <Kv label="Target">
              <span className="font-mono text-[12px]">{network?.target || "—"}</span>
            </Kv>
            <Kv label="Public join">
              <span className="font-mono text-[12px] text-neon">{publicJoin || "—"}</span>
            </Kv>
            <Kv label="Secret">{hasSecret ? "set (playit.toml)" : "missing"}</Kv>
            <Kv label="Binary">
              <span className="font-mono text-[12px]">{d.binary || "not installed"}</span>
            </Kv>
            <Kv label="IPC">
              <span className="font-mono text-[12px]">{d.socket_path || "—"}</span>
            </Kv>
            {d.tunnel_count != null && <Kv label="Tunnels">{d.tunnel_count}</Kv>}
            {d.last_error && (
              <Kv label="Last error">
                <span className="text-danger">{d.last_error}</span>
              </Kv>
            )}
          </dl>
          {publicJoin && (
            <Button className="mt-4 w-full" variant="primary" onClick={copyPublic}>
              Copy public join
            </Button>
          )}
        </section>

        <section className="cf-panel p-5">
          <h2 className="m-0 text-[13px] font-semibold">Play online</h2>
          <ol className="m-0 mt-2 list-none p-0">
            <Step done={hasBinary} title="1. Set up playit">
              <p className="m-0 mb-3 leading-relaxed">
                {plat.platform === "macos" ? (
                  <>
                    macOS has no GitHub release binary yet. Compile from source or use Docker, then
                    set <code className="font-mono text-[12px] text-text">network.playit.binary_path</code>.
                  </>
                ) : plat.platform === "linux" ? (
                  <>Downloads the official binary, then opens the computer claim-code wizard.</>
                ) : (
                  <>
                    Downloads the official Windows/Linux release, then opens the claim-code wizard.
                  </>
                )}
              </p>
              <div className="flex flex-wrap gap-2">
                <Button
                  disabled={busy === "setup"}
                  onClick={() =>
                    run("setup", async () => {
                      const res = await cultApi.command("playit.setup", {
                        force: false,
                        open_browser: false,
                        wait_exchange: false,
                      });
                      const data = res.data || {};
                      const url = String(
                        data.claim_url || data.setup_url || setupUrl,
                      );
                      if (data.claim_code) {
                        setFlash({
                          msg: `Claim code ${data.claim_code} — finish claim in the browser`,
                          ok: true,
                        });
                      } else {
                        setFlash({ msg: "playit ready — finish claim in the browser", ok: true });
                      }
                      window.open(url, "_blank", "noopener");
                    })
                  }
                >
                  {hasBinary ? "Refresh setup / claim" : "Set up playit"}
                </Button>
                {d.claim_code && (
                  <Button
                    variant="primary"
                    disabled={busy === "claim"}
                    onClick={() =>
                      run("claim", async () => {
                        setFlash({
                          msg: "Waiting for claim approval… keep the browser tab open",
                          ok: true,
                        });
                        const res = await cultApi.command("playit.claim.wait", {
                          claim_code: d.claim_code,
                          timeout: 300,
                        });
                        const data = res.data || {};
                        if (data.has_secret || res.ok) {
                          setFlash({ msg: "Claim complete — secret stored", ok: true });
                        } else {
                          setFlash({
                            msg: String(data.error || "Claim not finished yet — retry"),
                            ok: false,
                          });
                        }
                      })
                    }
                  >
                    Finish claim
                  </Button>
                )}
                <Button
                  variant="danger"
                  disabled={busy === "reset"}
                  onClick={() => {
                    if (!confirm("Stop playit and clear the stored secret on this machine?")) return;
                    run("reset", async () => {
                      await cultApi.command("playit.reset", {});
                      setFlash({ msg: "playit reset — secret cleared", ok: true });
                    });
                  }}
                >
                  Reset
                </Button>
              </div>
              {d.claim_code && (
                <p className="mt-3 m-0 text-[12px]">
                  Claim code{" "}
                  <code className="font-mono text-text">{d.claim_code}</code>
                  {d.claim_url && (
                    <>
                      {" · "}
                      <a href={d.claim_url} target="_blank" rel="noopener noreferrer">
                        open claim link
                      </a>
                    </>
                  )}
                </p>
              )}
            </Step>

            <Step done={hasSecret} title="2. Paste hex agent secret">
              <p className="m-0 mb-3 leading-relaxed">
                After approving the claim, paste the hex key here (or use the{" "}
                <a href={secretUrl} target="_blank" rel="noopener noreferrer">
                  docker/secret page
                </a>
                ). Stored as <code className="font-mono text-[12px] text-text">playit.toml</code> only
                on this PC.
              </p>
              <form className="flex flex-wrap gap-2" onSubmit={saveSecret}>
                <input
                  type="password"
                  autoComplete="off"
                  value={secret}
                  onChange={(e) => setSecret(e.target.value)}
                  placeholder={
                    hasSecret ? "•••• already set — paste hex to replace" : "paste hex secret key"
                  }
                  className="min-w-[16rem] flex-1 rounded-md border border-border bg-oled-elev px-3 py-2 font-mono text-[13px] text-text outline-none focus:border-neon/40"
                />
                <Button type="submit" disabled={busy === "secret"}>
                  Save secret
                </Button>
              </form>
            </Step>

            <Step done={Boolean(publicJoin || d.tunnel_count)} title="3. Minecraft Java tunnel">
              <p className="m-0 mb-3 leading-relaxed">
                Creates a tunnel to{" "}
                <code className="font-mono text-[12px] text-text">127.0.0.1:{port}</code> via the
                playit API.
              </p>
              <Button
                disabled={busy === "tunnel"}
                onClick={() =>
                  run("tunnel", async () => {
                    const res = await cultApi.command("playit.tunnel.ensure", {});
                    const data = res.data || {};
                    if (data.public_endpoint) {
                      setFlash({ msg: `Tunnel ready: ${data.public_endpoint}`, ok: true });
                    } else {
                      setFlash({ msg: "Tunnel ensured — public address pending", ok: true });
                    }
                  })
                }
              >
                Ensure Minecraft tunnel
              </Button>
            </Step>

            <Step title="4. Start agent">
              <p className="m-0 mb-3 leading-relaxed">
                Starts the official playit binary and ensures the tunnel above.
              </p>
              <div className="flex flex-wrap gap-2">
                <Button
                  variant="primary"
                  disabled={busy === "start"}
                  onClick={() =>
                    run("start", async () => {
                      await cultApi.command("network.use", { provider: "playit" });
                      const res = await cultApi.command("playit.start", {});
                      const data = res.data || {};
                      const pub =
                        data.public_endpoint ||
                        (data.tunnel &&
                          typeof data.tunnel === "object" &&
                          (data.tunnel as { public_endpoint?: string }).public_endpoint);
                      if (pub) setFlash({ msg: `playit up — join ${pub}`, ok: true });
                      else if (data.tunnel_error)
                        setFlash({ msg: String(data.tunnel_error), ok: false });
                      else setFlash({ msg: "playit starting", ok: true });
                    })
                  }
                >
                  Use playit & start
                </Button>
                <Button
                  variant="danger"
                  disabled={busy === "stop"}
                  onClick={() =>
                    run("stop", async () => {
                      await cultApi.command("playit.stop", {});
                      setFlash({ msg: "playit stopped", ok: true });
                    })
                  }
                >
                  Stop playit
                </Button>
                <Button
                  variant="ghost"
                  disabled={busy === "direct"}
                  onClick={() =>
                    run("direct", async () => {
                      await cultApi.command("network.use", { provider: "direct" });
                      setFlash({ msg: "Using direct / LAN", ok: true });
                    })
                  }
                >
                  Direct / LAN only
                </Button>
              </div>
            </Step>
          </ol>
        </section>
      </div>

      {(plat.install_methods?.length || plat.notes?.length || plat.apt_snippet) && (
        <Section title={`Platform notes · ${plat.platform || "host"}`}>
          <div className="cf-panel p-5 text-[13px] text-text-dim">
            {plat.install_methods && plat.install_methods.length > 0 && (
              <ul className="m-0 list-disc space-y-1 pl-5">
                {plat.install_methods.map((m) => (
                  <li key={m}>{m}</li>
                ))}
              </ul>
            )}
            {plat.notes && plat.notes.length > 0 && (
              <ul className="mt-3 m-0 list-disc space-y-1 pl-5">
                {plat.notes.map((n) => (
                  <li key={n}>{n}</li>
                ))}
              </ul>
            )}
            {plat.apt_snippet && (
              <pre className="mt-4 overflow-auto rounded-md border border-border bg-oled p-3 font-mono text-[12px] text-text">
                {plat.apt_snippet}
              </pre>
            )}
          </div>
        </Section>
      )}
    </div>
  );
}
