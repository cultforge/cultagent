# Integration: API, Agent, and Launcher

> **Ship reference** — how the three layers talk. Paste into launcher or API agents when wiring remote control.
>
> **Detailed contracts:** [`LAUNCHER_AGENT_CONTRACT.md`](LAUNCHER_AGENT_CONTRACT.md) (exact payloads), [`API_REMOTE_CONTROL_PROMPT.md`](API_REMOTE_CONTROL_PROMPT.md) (API ticket), [`LAUNCHER_UI_CONTEXT.md`](LAUNCHER_UI_CONTEXT.md) (launcher screens).
>
> **Ranking / competitive scores (0.2.4 track):** [`AGENT_RANKING_0.2.4.md`](AGENT_RANKING_0.2.4.md) — **cf-agent → API only**; launcher is UI. Verified guild + primary binding gate.

---

## 1. Architecture

```
Community Launcher          api.cultforge.com              cf-agent (user PC)
(user JWT via sidecar)  -->  queue + bindings + catalog  <--  agent token cagt_…
        |                            |                              |
        |  POST …/commands           |  GET /v1/agent/poll          |
        |  GET …/commands/{id}       |  POST …/commands/{id}/result |
        |  bind / unbind             |  heartbeat, telemetry        |
        +----------------------------+------------------------------+
```

| Layer | Auth | Base URL | Role |
|-------|------|----------|------|
| **Launcher** | User JWT (`sKEY` via sidecar) | `https://api.cultforge.com` | Bind servers, enqueue work, read status/join addresses |
| **API** | Validates JWT / `cagt_` | `https://api.cultforge.com` | Queue, bindings, catalog, persist command results |
| **cf-agent** | `cagt_…` bearer | Direct to API + local disk | Poll (or WS), execute Minecraft, post results |

**Route source of truth:** `GET https://api.cultforge.com/manifest.json`  
**Local dev override:** `http://localhost:8071` (cult_core2 checkout only)

The launcher **never** holds or calls with `cagt_` tokens. The agent **never** accepts user JWT for control-plane calls.

---

## 2. API ↔ Agent (control plane)

The agent runs a loop while `cf-agent run` (or as a service). Default tick ~15s (`poll_interval_seconds` in config and poll response).

### 2.1 Registration

Preferred: `cf-agent login` → browser OAuth on `auth.cultforge.com` → device approve → agent stores `anode_…` + `cagt_…`.

| Step | Endpoint | Auth |
|------|----------|------|
| Start device login | `POST /v1/agents/device/start` | none |
| Approve device | `POST /v1/agents/device/approve` | user JWT |
| Poll approval | `POST /v1/agents/device/token` | none |

After registration the control plane starts automatically.

### 2.2 Agent → API (each tick)

| Call | Purpose |
|------|---------|
| `GET /v1/agent/bindings` | Active bindings for this node |
| `GET /v1/agent/servers` | Bound servers + effective join addresses |
| `POST /v1/agent/heartbeat` | Online, version, capabilities |
| `GET /v1/agent/poll` | **Pull queued commands + desired workloads** |
| `POST /v1/agent/commands/{id}/result` | Report success/failure + result payload |
| `POST /v1/agent/telemetry` | Host + Minecraft metrics |
| `POST /v1/agent/workloads/report` | Workload state sync |
| `POST /v1/agent/score/batch` | Competitive raw deltas (verified guild + primary; see [`AGENT_RANKING_0.2.4.md`](AGENT_RANKING_0.2.4.md)) |

Guild scope (`node.guild_id` set): tunnel/runtime via `/v1/agent/guild/…`  
Personal scope (`guild_id` null): `/v1/agent/personal/servers/{upsrv}/tunnel|runtime`

### 2.3 Poll response

```json
{
  "data": {
    "poll_interval_seconds": 15,
    "commands": [
      {
        "id": "cmd_abc",
        "action": "server.start",
        "payload": {
          "server_id": "srv_e5107f0f5a9d",
          "local_server_id": "srv_e5107f0f5a9d",
          "accept_eula": true
        },
        "actor_user_id": "usr_…"
      }
    ],
    "desired_workloads": [
      {
        "id": "awlk_…",
        "local_server_id": "srv_…",
        "desired_state": "running"
      }
    ]
  }
}
```

### 2.4 Command execution (agent-side)

1. Dedupe by `command_id`
2. `normalize_action()` — e.g. `builds.install` → `builds.provision`, `server.command` → `server.console.execute`
3. Resolve `resource_id` from `payload.local_server_id` / `server_id` / binding lookup
4. `app.dispatch(action, params, actor_id, resource_id)` — local handler runs (start process, read console, install build, …)
5. `POST /v1/agent/commands/{id}/result` with `{ "success": true, "result": { … } }`

**Read caching:** `server.status` and `server.console.read` are coalesced ~8s to protect the agent from launcher spam.

**429 backoff:** On rate limit, agent pauses heartbeat/telemetry and doubles backoff up to 120s. Poll still runs.

### 2.5 WebSocket (optional acceleration)

When manifest advertises a WS endpoint, agent connects with `Authorization: Bearer cagt_…`. API may push `{ "type": "command", … }` for near-instant delivery. **Poll remains the fallback** — never disable poll because WS exists.

### 2.6 Bindings (agent reads only)

Only the launcher (user JWT) creates bindings. Each tick the agent refreshes:

```json
{
  "id": "cagb_…",
  "node_id": "anode_…",
  "scope": "guild|personal",
  "guild_server_id": "srv_…",
  "personal_server_id": null,
  "workload_id": "awlk_…",
  "local_server_id": "srv_…"
}
```

The agent materializes a **local catalog row** using the cloud server ID as the local ID so launcher payloads like `srv_…` resolve on disk.

Bind ≠ install. Binding wires catalog metadata; `builds.provision` / `server.start` handle files and process.

---

## 3. Launcher ↔ API (remote control)

The launcher talks to **user-JWT routes only** (typically proxied by the sidecar to `api.cultforge.com`).

### 3.1 What the launcher owns

| Responsibility | API pattern |
|----------------|-------------|
| Login / session | Sidecar auth |
| Browse catalog | `GET /v1/builds/discover` |
| CRUD personal servers | `/v1/me/servers/*` |
| List agents, online state | `GET /v1/agents/{anode}` |
| Activity HUD + console tails | `GET /v1/agents/{anode}/telemetry` → `metrics.activity` / `metrics.consoles` |
| **Create/delete bindings** | See bind routes below |
| **Enqueue remote commands** | `POST /v1/agents/{anode}/commands` |
| Poll command outcome | `GET /v1/agents/{anode}/commands/{command_id}` |
| Read join address | Server GET (`effective_address`, runtime) |
| Console snapshot (preferred) | `GET /v1/agents/{anode}/workloads/{awlk}/console` |

**Bind routes (launcher only):**

```
POST   /v1/guilds/{gld}/servers/{srv}/agents/{anode}/bind
DELETE /v1/guilds/{gld}/servers/{srv}/agents/{anode}/bind
POST   /v1/me/servers/{upsrv}/agents/{anode}/bind
DELETE /v1/me/servers/{upsrv}/agents/{anode}/bind
GET    /v1/agents/{anode}/bindings
```

### 3.2 Enqueue a command

```http
POST /v1/agents/{anode}/commands
Authorization: Bearer <user JWT>
Content-Type: application/json

{
  "action": "server.start",
  "workload_id": "awlk_…",
  "payload": {
    "server_id": "srv_e5107f0f5a9d",
    "local_server_id": "srv_e5107f0f5a9d",
    "accept_eula": true
  }
}
```

Response: `{ "command_id": "cmd_…", "state": "queued" }`

Poll until `succeeded` | `failed` | `expired`:

```http
GET /v1/agents/{anode}/commands/{command_id}
```

High-risk actions need confirm in payload and/or `POST …/commands/{id}/confirm`:  
`server.stop`, `server.restart`, `server.config.update`, `builds.provision`.

### 3.3 Allowed actions (v1 remote control)

| UI | `action` | Notes |
|----|----------|-------|
| Start | `server.start` | Include `accept_eula: true` |
| Stop / Restart | `server.stop` / `server.restart` | Confirm |
| Status | `server.status` | Do not poll at 1 Hz |
| Console log | `server.console.read` | Prefer snapshot GET; 15–20s cadence |
| Console input | `server.console.execute` | Minecraft line, not shell |
| Settings read/write | `server.config.read` / `server.config.update` | Update: confirm |
| Install build | `builds.provision` | Confirm; or rely on auto-install on start |
| Host metrics | `node.metrics` | On demand |
| List locals | `server.list` | Debug |

**Always include both** `server_id` and `local_server_id` in server-scoped payloads (same value when bound).

**Action aliases** the agent accepts (legacy names): see `ACTION_ALIASES` in `src/cultagent/cloud/registration.py`.

### 3.4 What the launcher must NOT do

- Call `/v1/agent/*` (agent-token routes)
- Store or expose `cagt_…`
- Heartbeat, poll, or post command results
- Reimplement binding refresh or tunnel writes
- Enqueue `server.status` / `server.console.read` faster than ~15s (causes 429 backoff)

### 3.5 Latency expectations

**Live manifest (`v2026.08.22-lin`):** `realtime.agent_ws` = `/v1/agent/ws`. cf-agent auto-connects when `realtime_enabled` (default). Poll (`/v1/agent/poll`) remains fallback.

| Path | Typical latency |
|------|-----------------|
| WS push + connected agent (**default on live API**) | ~1–3s after enqueue |
| Poll-only agent (WS down) | Up to ~15s before command runs |
| Local panel on same PC | Live: `http://127.0.0.1:8720/panel/…` |

**Two status layers for the launcher UI:**

| Signal | Source | User-facing |
|--------|--------|-------------|
| Agent PC reachable | `GET /v1/agents/{anode}`, telemetry, runtime freshness | PC connected / PC offline |
| Minecraft server running | Guild/personal runtime, workload report | Online / Offline / Starting / Crashed |

Do **not** show “PC offline” when only the server is stopped. Do **not** default to 15s copy when WS is live — that reads as broken/offline. Show “Starting…” while a command is pending; “PC offline” only when the agent node is actually unreachable (`expired` command, stale heartbeat, explicit offline).

### 3.6 Activity HUD + console (Phase 1 — telemetry)

cf-agent embeds the same friendly **Activity** feed as `cf-agent run`, plus Minecraft **console tails**, in every telemetry upsert:

```http
GET /v1/agents/{anode}/telemetry
Authorization: Bearer <user JWT>
```

Look for (under the stored metrics snapshot):

```json
{
  "activity": {
    "schema_version": 1,
    "lines": [
      {"ts": "2026-08-22T16:48:25Z", "kind": "ok|warn|err|info|work", "text": "Connected to CultForge realtime"}
    ]
  },
  "consoles": [
    {
      "server_id": "srv_…",
      "seq": 1234,
      "lines": [{"seq": 1230, "ts": "…", "text": "[12:01] Done (3.2s)!"}]
    }
  ],
  "presence": [
    {
      "server_id": "srv_…",
      "player_count": 2,
      "players": [{"name": "Steve", "minecraft_name": "Steve"}]
    }
  ]
}
```

| Field | Cap | Cadence |
|-------|-----|---------|
| `activity.lines` | last 40 | Refresh with telemetry (~5–15s) |
| `consoles[]` | ≤3 running servers, ≤50 lines each | Same; do **not** also enqueue `server.console.read` on a timer |
| `presence` | online roster snapshot | Same tick; also pushed to guild routes below |

### 3.7 Guild players + events (live manifest)

cf-agent now fulfills the live API guild presence routes each control-plane tick:

| Agent write | Route |
|-------------|--------|
| Replace roster | `POST /v1/agent/guild/players` |
| Append join/leave/death/advancement | `POST /v1/agent/guild/events` |
| `player_count` on runtime | `POST /v1/agent/guild/runtime` |

Source: console parse (`joined/left the game`, deaths, advancements) + periodic `list`. Launcher/guild UI should prefer `GET /v1/guilds/{gld}/agents/players` and `…/events` (user JWT) over inventing a kill-feed.

**API note:** if `get_filtered_telemetry` strips unknown keys, pass through `activity`, `consoles`, and `presence`. Until then, dedicated `POST /v1/agent/activity` + `GET /v1/agents/{anode}/activity` are Phase 2 — see [`todo/API_LAUNCHER.md`](../todo/API_LAUNCHER.md).

---

## 4. End-to-end flows

### A. Personal server hosting

1. User creates `upsrv_…` in launcher
2. User binds personal agent: `POST /v1/me/servers/{upsrv}/agents/{anode}/bind`
3. Agent polls bindings → creates local catalog row
4. Launcher enqueues `server.start`
5. Agent executes → posts tunnel to `/v1/agent/personal/servers/{upsrv}/tunnel`
6. Launcher reads `effective_address` for Join UI

### B. Remote Start button

```
Launcher  POST /v1/agents/{anode}/commands  { action: server.start, … }
    →  API queues cmd_abc
    →  Agent poll picks up cmd_abc
    →  Agent dispatches server.start locally
    →  Agent POST …/commands/cmd_abc/result { success: true }
    →  Launcher GET …/commands/cmd_abc  → state: succeeded
    →  Launcher GET runtime / server row for UI refresh
```

### C. Catalog install

1. User picks build in Discover
2. User selects online bound agent
3. Launcher enqueues `builds.provision` with `build_id`
4. Agent fetches manifest from `/v1/agent/builds/{id}/manifest`, installs files
5. Launcher shows progress via command result + workload state

---

## 5. Responsibility matrix

| Task | Launcher | API | cf-agent |
|------|----------|-----|----------|
| User auth | yes | validates | device login only |
| Bind/unbind | yes | stores | reads cache |
| Enqueue commands | yes | queues | consumes poll |
| Execute Minecraft | no | no | yes |
| Heartbeat / telemetry | no | stores | posts |
| Tunnel / runtime write | no | stores | posts (bound only) |
| Full file/JVM/mods admin | link to local panel | no | `127.0.0.1:8720/panel` |
| Build catalog browse | yes | serves | search via agent token when on-box |

---

## 6. CLI reference (merged commands)

Old names still work as **hidden aliases** for scripts.

| Use this | Instead of |
|----------|------------|
| `cf-agent builds --q …` | `builds-search` |
| `cf-agent agent-servers` | `guild-servers` |
| `cf-agent agent-servers --bindings` | `agent-bindings` |
| `cf-agent build --new --build <id>` | `build-provision` |
| `cf-agent build <server> --build <id>` | `build-install` |
| `cf-agent playit-start` | `playit-tunnel` |
| `cf-agent playit-reset` | `reset playit` |
| `cf-agent profiles <name>` | `profile-show` |
| `cf-agent profile-apply <name> --diff` | `profile-diff` |
| `cf-agent mods --search …` | `modrinth-search` |
| `cf-agent mods --info <slug>` | `modrinth-info` |
| `cf-agent mods --versions <slug>` | `modrinth-versions` |

Local debugging without launcher: `cf-agent exec <action> --params '{…}'`.

---

## 8. Verification checklist

**Agent (on user PC):**

```powershell
cf-agent login
cf-agent run
cf-agent agent-servers
cf-agent builds --q survival
cf-agent cloud-manifest
```

**Launcher:**

- [ ] Bind flow creates `cagb_…` and shows join address after agent tick
- [ ] Start enqueues once; UI polls command_id, not status every second
- [ ] Stop shows confirm, sends `confirm: true`
- [ ] Offline agent shows friendly message, not raw 429

**API (cult_core):**

- [ ] User-JWT `POST /v1/agents/{anode}/commands` lands on agent poll queue
- [ ] Results persisted for launcher GET
- [ ] Console snapshot cache for workload reads (see API_REMOTE_CONTROL_PROMPT.md)

---

## 9. Local dashboard vs launcher remote UI

**Do not expose `http://127.0.0.1:8720/panel` through the cloud API.**

The local CultAgent panel is loopback-only on purpose. It has no user auth, full file/JVM access, and direct process control. Tunneling it through `api.cultforge.com` would be a security hole.

| Need | Local user on the PC | Remote launcher user |
|------|----------------------|----------------------|
| Full admin (files, JVM, backups) | `http://127.0.0.1:8720/panel/…` | Not available remotely (by design) |
| Start / stop / console / settings | Local panel or CLI | Launcher UI via **command queue** (§3) |
| Server list + status | `GET /v1/servers` on loopback panel API | `GET /v1/agents/{anode}/…` + runtime reads |
| Join address | Panel join card | Server GET (`effective_address`) |
| Metrics strip | `GET /v1/dashboard` on loopback | Telemetry + `node.metrics` enqueue |

The loopback panel already exposes JSON mirrors (`GET /v1/dashboard`, `GET /v1/servers`) for the React SPA on the same machine. The **launcher** should build its own friendly UI and read/write through **user-JWT cloud routes** — not proxy the local HTML.

Optional UX on the same PC: an "Open local panel" link that opens `127.0.0.1:8720` in the browser. That is a convenience link, not API integration.

### Server scope labels (local panel)

Guild-bound and personal-bound servers show a badge in the local dashboard:

| Scope | Label | When |
|-------|-------|------|
| `guild` | **Guild** / **Guild server** | Cloned from guild catalog or bound `srv_…` |
| `personal` | **Personal** | Bound `upsrv_…` |
| `local` | (no badge) | Scratch-created local server |

Each server row in `GET /v1/servers` includes `scope` and `scope_label` for the SPA.

---

## 10. Related docs

| Doc | Audience |
|-----|----------|
| [`LAUNCHER_AGENT_CONTRACT.md`](LAUNCHER_AGENT_CONTRACT.md) | Launcher — exact payloads, UI rules |
| [`API_REMOTE_CONTROL_PROMPT.md`](API_REMOTE_CONTROL_PROMPT.md) | API team — enqueue + snapshot implementation |
| [`LAUNCHER_UI_CONTEXT.md`](LAUNCHER_UI_CONTEXT.md) | Launcher — screens, sidecar routes, IDs |
| [`LAUNCHER_AGENT_CONTROL_PROMPT.md`](LAUNCHER_AGENT_CONTROL_PROMPT.md) | Launcher — control UI mock guidance |
