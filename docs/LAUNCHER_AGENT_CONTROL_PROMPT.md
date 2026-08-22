# Launcher Agent Control UI — Cursor Agent Prompt

> **Paste this entire file** into the Community Launcher Cursor agent when building **remote agent control** surfaces.
>
> **Start here for wiring (not guesses):** [`LAUNCHER_AGENT_CONTRACT.md`](./LAUNCHER_AGENT_CONTRACT.md) — what you SEND, what you GET, real `action` names and payloads. **UI must be Aternos + Crafty + our dash — buttons/toggles, not a command-line for users.**
>
> **Companion docs:**
> - [`LAUNCHER_UI_CONTEXT.md`](./LAUNCHER_UI_CONTEXT.md) — catalog, bindings, personal mode, sidecar routes
> - **This file** — screens / UX (don’t mix guild Join with agent control)
> - [`API_REMOTE_CONTROL_PROMPT.md`](./API_REMOTE_CONTROL_PROMPT.md) — backend enqueue (if API still incomplete)

---

## 0. What you built wrong (read before coding)

The current **Guild Server → Overview** page (e.g. AdAstra) is **not** an agent control interface. It mixes three unrelated concerns into one dashboard:

| What the screenshot shows | Why it is wrong |
|---------------------------|-----------------|
| **Join server** on guild overview | Correct for a **member join** page — keep it there |
| **Start / Restart / Stop** on guild overview | These control the **Minecraft process on the agent PC**. They must enqueue **cloud commands** to a specific **agent node + local server id**, not toggle UI state on a guild metadata page |
| **CONNECTED AGENTS (1)** card | Read-only telemetry is fine here, but it is **not** the control surface |
| **Reachability / Players / Latency** grid | Broker / join-plane reads — **status only**, not controls |
| **Host on this PC** in sidebar | Must open **real control** (local panel or remote command console), not a duplicate overview |
| No scrolling **log output** | Agent exposes `server.console.read` — you must show logs |
| No **command input / shell** | Agent exposes `server.console.execute` — you must show a command bar |
| No **Add server to agent** | User JWT bind flow + optional provision — see §5 |
| No **Remove agent execution** | Unbind + stop workload — see §6 |

**Rule:** A guild server page answers *“Can I join? Who hosts? Is it up?”*  
An agent control page answers *“Run/stop this MC instance, read/send console commands, bind/unbind workloads.”*

Do **not** put lifecycle buttons on the guild overview unless they are wired to the cloud command API (§4).

---

## 1. Three separate surfaces (do not merge)

```
┌─────────────────────────────────────────────────────────────────────────┐
│  A. Guild Server Page          B. Agent Control Page    C. Local Panel │
│  (member / admin metadata)     (remote via cloud)       (same PC only)  │
├─────────────────────────────────────────────────────────────────────────┤
│  Join, address, build,         Per-agent workloads,     Full Crafty UI  │
│  bound agent list (read),      console, start/stop,     Terminal, Files,│
│  reachability, player count    bind/unbind, provision   Config, Mods… │
└─────────────────────────────────────────────────────────────────────────┘
```

| Surface | Route (suggested) | Auth | Runs MC? |
|---------|-------------------|------|----------|
| **A. Guild server** | `/guilds/:gid/servers/:srv` | User JWT via sidecar | No |
| **B. Agent control** | `/agents/:anode` and `/agents/:anode/workloads/:awlk` | User JWT via sidecar | No (sends commands) |
| **C. Local panel** | `http://127.0.0.1:8720/panel/…` | Loopback only | Yes (cf-agent) |

**“Host on this PC”** → If the selected agent is on **this machine** and cf-agent is running, deep-link to **C** (open browser to local panel). Otherwise show **B** (remote control with poll latency).

---

## 2. Reference implementation — cf-agent local panel (copy this UX)

The cf-agent repo already implements the **correct** server control UX at `http://127.0.0.1:8720/panel/`. Mirror these patterns remotely (with poll-based refresh instead of 2s loopback polling).

### 2.1 Server layout (header + actions + tabs)

Each **local server instance** has:

- **Header:** name, `server_id`, live state badge
- **Action bar:** Start | Stop | Restart (contextual on state) + link to full Terminal
- **Stats strip:** players, port, uptime, join address
- **Tabs:** Overview, Terminal, Files, Config, Tuner, Backups, Mods, Metrics, Players

Local tab routes (`panel-ui/src/lib/servers.ts`):

```
/panel/servers/{local_id}           → Overview (metrics + mini console)
/panel/servers/{local_id}/console   → Full terminal
/panel/servers/{local_id}/files     → File browser
/panel/servers/{local_id}/config    → server.properties editor
…
```

**Launcher remote control minimum (MVP):** Overview actions + **full console tab equivalent**. Files/Config/Mods can link out to local panel when on same PC.

### 2.2 Console / logs / command shell (required on agent control page)

Local panel **Overview** embeds a live console (`ServerOverviewPage.tsx`):

- Poll `GET /v1/servers/{local_id}/console?limit=120` every ~4s
- Scrollable `<pre>` log area (newest at bottom)
- Command input with Tab completion + ↑/↓ history (`ConsoleInput.tsx` + `mcCommands.ts`)
- Submit → `POST /v1/servers/{local_id}/console` body `{ "command": "say hello" }`

Local **Terminal** tab is the same console at larger height (~70vh), poll every ~2.5s.

Those intervals are **loopback REST on the same PC**. Remote launcher must **not** copy them onto `POST /v1/agents/{anode}/commands`. Remote log refresh is a **GET snapshot** (or one `server.console.read` every 15–20s). See `LAUNCHER_AGENT_CONTRACT.md` Cadence.

**Remote launcher must provide the same two elements:**

1. **Log viewport** — scrolling, monospace, auto-scroll to bottom on new lines
2. **Command shell** — single-line input, Enter to send, optional Tab suggestions for vanilla commands

Without both, the page is **not** agent control.

### 2.3 Start / Stop / Restart buttons (required)

Local panel wires buttons to:

```
POST /v1/servers/{local_id}/start    body { "accept_eula": true }
POST /v1/servers/{local_id}/stop     body {}
POST /v1/servers/{local_id}/restart  body {}
```

These dispatch agent commands `server.start`, `server.stop`, `server.restart` on the **local server id** (e.g. `srv_e5107f0f5a9d`).

Button rules (`ServerActions.tsx`):

- **Running** → show Stop (danger) + Restart
- **Stopped** → show Start (primary)
- Disable all while a request is in flight; refresh status after each action

---

## 3. ID model — map cloud records to controllable resources

| ID | Example | Used for |
|----|---------|----------|
| `anode_…` | Agent node | Which PC runs cf-agent |
| `cagb_…` | Binding | User attached server ↔ agent |
| `awlk_…` | Workload | Cloud execution slot on agent |
| `srv_…` | Guild server | Cloud catalog record |
| `upsrv_…` | Personal server | User-owned cloud record |
| **Local server id** | Often same as `srv_…` on disk | **All control commands target this** |

Agent poll commands resolve `resource_id` from payload fields (in order):

```
payload.server_id  |  payload.resource_id  |  payload.local_server_id
```

**UI must show and store `local_server_id`** on each workload row (from bindings/workload reports). Start/Stop/Console commands **fail** if this id is missing or stale.

Binding response shape (from `LAUNCHER_UI_CONTEXT.md`):

```json
{
  "id": "cagb_…",
  "node_id": "anode_…",
  "workload_id": "awlk_…",
  "guild_server_id": "srv_…",
  "scope": "guild"
}
```

---

## 4. Remote control path (launcher → API → agent poll)

cf-agent does **not** accept user JWT. Execution flow:

```
Launcher (user JWT)
    → Sidecar client.exe
        → api.cultforge.com  (enqueue command for anode_…)
            → cf-agent poll GET /v1/agent/poll (~15s)
                → agent.dispatch(action, params, resource_id)
                    → POST /v1/agent/commands/{cmd_id}/result
```

Agent capabilities (`src/cultagent/constants.py` — `COMMANDS`):

| Action | Purpose |
|--------|---------|
| `server.start` | Start MC process |
| `server.stop` | Stop MC process |
| `server.restart` | Restart MC process |
| `server.console.read` | Fetch log lines (`after_seq`, `limit`) |
| `server.console.execute` | Send one console command (`command` string) |
| `server.status` | Process state, players |
| `server.list` | All local instances on agent |
| `builds.provision` | Install build to disk |
| `server.clone` | Create local dir from guild server row |
| `server.remove` | Remove local server instance |
| `agent.bindings.list` | Agent-side binding cache |
| `agent.servers.list` | Agent-side server catalog |

Poll command shape (agent expects):

```json
{
  "id": "cmd_…",
  "action": "server.console.execute",
  "payload": {
    "local_server_id": "srv_e5107f0f5a9d",
    "command": "list"
  },
  "actor_user_id": "usr_…"
}
```

**Launcher enqueue route:** Check live manifest (`GET https://api.cultforge.com/manifest.json`) for user-JWT routes under `/v1/agents/{node_id}/commands` or guild-scoped equivalents. Until wired, show **“Command queued”** UX with poll-interval disclaimer (~15s) and surface command results from the API when available.

**Do not** call agent-token routes (`/v1/agent/poll`, `/v1/agent/*` writes) from the launcher.

### 4.1 Read-only status (while building command enqueue)

Use existing guild dashboard **reads** (sidecar proxies):

```
GET /guilds/{gid}/agents/…   → runtime, players, events
```

These are **telemetry only** — they do not replace console logs. Prefer `server.console.read` via command enqueue for log tail; use events stream for structured audit if exposed.

### 4.2 Same-machine shortcut

When launcher detects local cf-agent (health check `GET http://127.0.0.1:8720/health`):

- Offer **“Open local panel”** → `http://127.0.0.1:8720/panel/servers/{local_id}/console`
- Optional: proxy loopback REST through a trusted local bridge (future) — **not** required for MVP if cloud commands work

---

## 5. Add server to agent (bind + provision)

**“Add server”** is a **multi-step flow**, not a single button on guild overview.

### Guild scope

1. User picks **guild server** (`srv_…`) and **agent** (`anode_…`) — agent must be guild-attached
2. `POST /guilds/{gld}/servers/{srv}/agents/{anode}/bind` (user JWT via sidecar)
3. Agent polls bindings → creates/updates workload `awlk_…`
4. If no local files yet: enqueue `builds.provision` or `server.clone` with `guild_server_id`
5. Optionally enqueue `server.start` after provision completes
6. Show workload row on **Agent control page** with console + actions

### Personal scope

1. User picks **personal server** (`upsrv_…`) and **personal agent** (`anode_…` where `guild_id == null`)
2. `POST /me/servers/{upsrv}/agents/{anode}/bind`
3. Same provision/start sequence

**UI placement:** “Add server” button on **Agent detail page** (`/agents/:anode`), not buried in guild server overview.

---

## 6. Remove agent execution (unbind + stop)

**“Remove from agent”** / **“Stop hosting on this PC”**:

1. Confirm dialog — explain MC will stop and tunnel may drop
2. Enqueue `server.stop` for `local_server_id` (best-effort)
3. `DELETE …/bind` (guild or personal unbind route — see `LAUNCHER_UI_CONTEXT.md` §4.4)
4. Optionally enqueue `server.remove` if user wants local files deleted (high risk — require `confirm=true` if API supports it)
5. Refresh bindings list; guild server page returns to “no agent bound”

Do **not** only hide the UI card — must call unbind API.

---

## 7. Page specs to implement

### 7.1 Guild Server Page (keep, but fix)

**Route:** `/guilds/:gid/servers/:srv` (or existing Servers nav)

| Section | Content | Interactive? |
|---------|---------|--------------|
| Header | Name, description, offline/online badge | — |
| Primary CTA | **Join server** (effective address from join API) | Yes |
| Metadata table | Address, region, build, version, listing status | Read-only |
| Hosting | Bound agent(s) names + online badge | Read-only |
| Reachability | Broker/tunnel status | Read-only |
| **Manage** link | → Agent control page for bound `anode_…` | Yes (if permitted) |

**Remove or disable** Start/Stop/Restart here unless fully wired to §4 command enqueue.

### 7.2 Agent Detail Page (build this — the missing page)

**Route:** `/agents/:anode`

| Section | Content |
|---------|-----------|
| Header | Agent name, platform, version, **Personal / Guild** badge, online/offline |
| Workloads table | Each binding: cloud server name, `awlk_…`, `local_server_id`, state, players |
| Row actions | Open console, Start, Stop, Restart, Unbind |
| **Add server** | Bind guild or personal server (scope-aware) |
| Bindings panel | List `cagb_…` with revoke/unbind |

### 7.3 Workload Console Page (build this — logs + shell)

**Route:** `/agents/:anode/workloads/:awlk` or `/agents/:anode/servers/:local_id/console`

| Section | Content |
|---------|-----------|
| Header | Server name + state + Start/Stop/Restart |
| **Console log** | Poll `server.console.read` — show last N lines, auto-scroll |
| **Command input** | Send `server.console.execute` on Enter |
| Sidebar links | Config/Files → “Open local panel” when agent is local |
| Breadcrumb | Agents → {agent name} → {server name} |

**Latency UX:** Show “Remote control — updates every ~15s” when using poll path; spinner on command send until result returns.

### 7.4 Host on this PC (sidebar item)

When user opens **Host on this PC** from a guild server context:

1. Resolve bound `anode_…` for this server
2. If local agent health OK → open `127.0.0.1:8720/panel/servers/{local_id}/console`
3. Else → navigate to **§7.3** remote console for that workload

---

## 8. Wireframe (agent control — target layout)

```
┌──────────────────────────────────────────────────────────────────┐
│  ← Agents    DESKTOP-QDN36QP    [GUILD]    ● online    v0.1.0   │
├──────────────────────────────────────────────────────────────────┤
│  Workloads (2)                              [ + Add server ]     │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │ AdAstra  srv_e510…  ● running  0/20 players               │  │
│  │ [Console] [Stop] [Restart]                    [ Unbind ]  │  │
│  └────────────────────────────────────────────────────────────┘  │
├──────────────────────────────────────────────────────────────────┤
│  Console — AdAstra                                               │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │ [12:01:02] [Server thread/INFO]: Done (3.2s)!             │  │
│  │ [12:01:02] [Server thread/INFO]: Starting Minecraft server│  │
│  │ … (scrollable log) …                                       │  │
│  └────────────────────────────────────────────────────────────┘  │
│  > list________________________________________ [Send]           │
│  Remote control · ~15s refresh · Tab completes vanilla commands  │
└──────────────────────────────────────────────────────────────────┘
```

---

## 9. Anti-patterns (explicit do-not list)

1. **Do not** show Start/Stop/Restart as decorative buttons that only change local React state
2. **Do not** use guild broker “Unreachable” as proxy for “server stopped” — different systems
3. **Do not** put console/logs only on a future tab that was never built — MVP requires log + input on agent control
4. **Do not** conflate **Join** (client connects to MC) with **Start** (agent launches JAR)
5. **Do not** store or display `cagt_…` agent tokens in launcher
6. **Do not** call `/v1/agent/*` write routes with user JWT
7. **Do not** offer guild-server bind UI on personal agents (scope enforced — 400/403)
8. **Do not** rebuild Files/Config/JVM tuner in launcher for v1 — link to local panel

---

## 10. Verification checklist

- [ ] Guild server overview has **Join** + read-only hosting info; lifecycle buttons removed or wired to cloud commands
- [ ] **Agent detail page** lists workloads with `local_server_id`
- [ ] **Console page** shows scrolling logs via `server.console.read`
- [ ] **Command input** sends `server.console.execute` and appends/refreshes output
- [ ] Start/Stop/Restart enqueue correct actions with `local_server_id`
- [ ] **Add server** runs bind (+ provision when needed)
- [ ] **Unbind** calls DELETE bind route + stops workload
- [ ] **Host on this PC** opens local panel when cf-agent is on same machine
- [ ] Poll latency disclaimer shown for remote control
- [ ] Personal vs Guild scope respected on bind UI

---

## 11. Source files in cf-agent repo (read for behavior, do not copy backend)

| File | Why |
|------|-----|
| `panel-ui/src/layouts/ServerLayout.tsx` | Header + Start/Stop/Restart wiring |
| `panel-ui/src/pages/ServerOverviewPage.tsx` | Mini console on overview |
| `panel-ui/src/pages/TerminalPage.tsx` | Full terminal poll loop |
| `panel-ui/src/components/ConsoleInput.tsx` | Command shell UX |
| `panel-ui/src/components/ServerActions.tsx` | Button visibility rules |
| `panel-ui/src/lib/api.ts` | Local REST paths (`/v1/servers/…`) |
| `src/cultagent/constants.py` | `COMMANDS` list |
| `src/cultagent/cloud/control_plane.py` | How poll commands execute |
| `docs/LAUNCHER_UI_CONTEXT.md` | Bind/unbind sidecar routes |

---

## 12. One-paragraph summary for the agent

Build **two pages**, not one: (1) **Guild server** = join + metadata + who hosts; (2) **Agent control** = workloads with **live logs**, **command shell**, **Start/Stop/Restart**, **Add server** (bind/provision), and **Remove execution** (unbind/stop). Copy the cf-agent local panel console UX from `127.0.0.1:8720/panel`. Wire actions through **user JWT → sidecar → cloud command enqueue → agent poll**, targeting `local_server_id` on each workload. “Host on this PC” opens the real local panel when cf-agent runs on the same machine.
