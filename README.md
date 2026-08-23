# CultForge Agent (CultAgent)

Cross-platform machine-side execution layer for CultForge, built to overhaul a
Crafty Controller foundation rather than rebrand it.

See [`cultagent.md`](cultagent.md) for product architecture and phases.
Cloud contracts: CultForge `CONTEXT.md` / `agents.py` (pairing + poll).

## Status

**Crafty process/content parity (agent-side)** — crash auto-restart, boot
`auto_start`, **server** installers for vanilla / paper / purpur / folia /
fabric / quilt / forge / neoforge, Modrinth mods install/remove/update, zip
backups + confirmed restore. (Agent sets up **servers**, not clients.)

**Local panel (Crafty-major + Aternos Play)** — while `cf-agent run`, open
`http://127.0.0.1:8720/panel/dashboard` (loopback only). Dashboard is Start/Stop
+ join address; server pages are Crafty-style admin (terminal, files, backups).
Create wizard: name → platform → install. Network page: playit Play-online
wizard. Advanced: builds / profiles / cloud / system.

**Builds** — `cf-agent builds` (list or `--q` search), `build-manifest`,
`build --new` / `build <server>` (Rich progress with speed/ETA); panel at `/panel/builds`.
`cf-agent --clear-cache` clears the download cache. Rich CLI output;
`--dump-json FILE` for raw JSON.
writes the raw payload when you need it.

**Modrinth** — content provider only (`mods --search` / `mod-install` / …).
CultForge builds remain the managed recipe source of truth.

**Network** — `direct` or official **playit.gg agent** (`playit-setup` /
`playit-secret` / `playit-start`). Launches real `playit-cloud/playit-agent`
with `--secret-path` / `-l` / `--socket-path`. Panel `/panel/network`. See
`vendor/playit/README.md`. Secrets stay in the agent data dir as `playit.toml`.

**Profiles / Chloe / hardening** — `profiles` + panel `/panel/profiles`;
`sidecar-issue` + `POST /v1/sidecar/command` (Chloe role, no privilege bypass);
`doctor` + `update-check`; JSON responses redact secrets.

**Cloud** — login/poll receive remote commands; realtime auto-switches to
WebSocket when `api…/manifest.json` advertises it.

## Quick start

```powershell
cd g:\CultForge\library\pYThON\cultserve\0.1
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
cf-agent init
cf-agent java
```

### Register with CultForge

```powershell
cf-agent login
```

Opens **`auth.cultforge.com`** in your browser (Google by default). After you
sign in, the CLI approves the agent on **`api.cultforge.com`** and stores
`cagt_…` — no JWT paste.

```powershell
cf-agent login --provider github
cf-agent login --provider discord
cf-agent login --guild-id gld_…
```

Automation / headless:

```powershell
cf-agent login --jwt <USER_SESSION_JWT>
cf-agent register --code ABCD2345
cf-agent cloud-manifest
cf-agent run
```

Local advanced panel (Crafty-like options): open
`http://127.0.0.1:8720/panel/dashboard` while the agent is running.

### Guild builds (Option A)

Requires agent registered **and** attached to a guild on the API:

```powershell
cf-agent builds
cf-agent build --new --build <build_id>
cf-agent build <server_id> --build <build_id>
cf-agent --clear-cache
cf-agent exec server.mods.list --resource <server_id>
```

`build --new` creates a cloud workload + local server directory, then installs
the CultForge install manifest (resolved Modrinth/direct URLs, sha256 verify).

## Layout

```text
src/cultagent/
  app.py              # runtime + control-plane / crash-watch loops
  api/                # loopback HTTP management API
  cli/                # cf-agent CLI
  identity/           # local + cloud node ids, cagt_ token store
  cloud/              # client, pairing/register, poll control plane
  commands/           # controlled capability surface
  servers/            # registry + process/console/java/eula/install
  network/            # direct | playit.gg abstraction
  content/            # Modrinth + CultForge builds
  config/             # structured server.properties + profiles
  metrics/            # local system/minecraft/network metrics
  files/              # file + backup managers
  rbac/               # visibility + local auth helpers
  audit/              # privileged operation trail
  service/            # systemd / launchd templates
```

## Configuration

Copy `config.example.yaml` or run `cf-agent init`.

**Cloud endpoints** are the live worker subdomains (apex is static). Discover
agent routes with `cf-agent cloud-manifest` (`GET api…/manifest.json`).

| Service | Live (default) | Local override |
|---------|----------------|----------------|
| API | `https://api.cultforge.com` | `http://localhost:8071` |
| Auth | `https://auth.cultforge.com` | `http://localhost:8072` |
| Invite | `https://invite.cultforge.com` | `http://localhost:8073` |
| Guilds | `https://guilds.cultforge.com` | `http://localhost:8074` |

| Variable | Purpose |
|----------|---------|
| `CULTAGENT_CONFIG` | Absolute path to config.yaml |
| `CULTAGENT_DATA_DIR` | Agent data directory |
| `CULTAGENT_AUTH_BASE` | Auth base (default: `https://auth.cultforge.com`) |
| `CULTAGENT_API_BASE` | API base (default: `https://api.cultforge.com`) |
| `CULTAGENT_INVITE_BASE` | Invite base (default: `https://invite.cultforge.com`) |
| `CULTAGENT_GUILDS_BASE` | Guilds base (default: `https://guilds.cultforge.com`) |
| `CULTAGENT_LOG_LEVEL` | Logging level |

## Development phases

1. Understand Crafty boundaries
2. Stabilize fork / process foundation
3. CultAgent identity/registration ← **done (pairing + JWT)**
4. CultForge API poll/heartbeat/telemetry ← **done**
5. Richer realtime (local WS console + cloud auto-switch when API advertises WS)
6. Builds / content ← **done** (list, rich manifest, provision, install, panel)
7. Modrinth ← **done** (search/info/versions, install/remove/update, deps, panel)
8. playit.gg network manager ← **done** (install, secret, start/stop, status, panel)
9. Structured configuration ← **done** (profiles capture/diff/apply, panel)
10. RBAC/visibility ← **done** (cloud-authoritative; sidecar local enforce + secret redact)
11. Chloe as authorized sidecar ← **done** (`sidecar-issue`, `/v1/sidecar/command`)
12. UI + installers ← **done** (Crafty-major panel + Aternos Play path; service helpers)
13. Hardening / updates / packaging ← **done** (`doctor`, `update-check`, response redaction)

## Release binaries (Windows / macOS / Linux)

Version **0.2.1**. Ship a onefile CLI via **Nuitka**; artifacts land on **GitHub Releases**. `latest.json` carries `version` / `hash` / `filelink` per platform:

```json
{
  "version": "0.2.1",
  "hash": "sha256:…",
  "filelink": "https://github.com/cultforge/cultagent/releases/download/v0.2.1/cf-agent-0.2.1-windows-amd64.exe",
  "platforms": { "windows-amd64": { "version": "…", "hash": "…", "filelink": "…" } }
}
```

### Local build (this OS)

```powershell
pip install -e ".[release]"
python scripts/build_release.py
# → dist/cf-agent-0.2.1-<platform>.*
# → dist/latest.json
```

Point `filelink` at a GitHub Release tag:

```powershell
$env:CULTAGENT_RELEASE_BASE_URL = "https://github.com/cultforge/cultagent/releases/download/v0.2.1"
python scripts/build_release.py
```

### CI (all platforms)

[`.github/workflows/release-binaries.yml`](.github/workflows/release-binaries.yml):

- matrix: Windows amd64, Linux amd64, macOS arm64 + amd64  
- **pytest** on each runner, then **Nuitka** onefile build, then binary smoke (`--help` / `doctor`)  
- merges `latest.json` with GitHub Release asset URLs  
- tag `v*` → creates a **GitHub Release** with all binaries + `latest.json`  
- PRs touching agent/build paths run the same test + compile matrix (no release upload)

Also mirror `latest.json` to `https://api.cultforge.com/static/agent/latest.json` if you want `cf-agent update-check` without hitting GitHub.

Example schema: [`packaging/latest.example.json`](packaging/latest.example.json).

### Panel acceptance checklist

- [ ] Empty host → Dashboard shows Create server CTA
- [ ] Create wizard → install + optional start → Overview with join address
- [ ] Start/Stop from Dashboard Play hero; copy join address
- [ ] Server rail: Terminal / Files / Config / Backups work
- [ ] Network → Set up playit → claim wizard → paste secret → start → public/claim shown (secret never displayed)
- [ ] Advanced nav: Builds, Profiles, Cloud, System still reachable
## Tests

```powershell
pytest
```
