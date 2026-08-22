# Launcher ↔ API ↔ Agent contract

> **Paste this into the Community Launcher Cursor agent.** Stop guessing action names. This is the real cf-agent contract.
>
> You already have user-JWT routes (pair, bind, enqueue). This file tells you **what to put in `action` / `payload`**, **what you GET back**, and **what the agent does on the PC**. You never call agent-token URLs.

---

## UI first — Aternos + Crafty + our dash (read this before any screen)

**If the Control UI is technical, users will bounce.** They are not going to type `server.start`, `anode_…`, `after_seq`, or Minecraft slash commands to change difficulty.

You enqueue JSON **under the hood**. The **screen** must feel like:

| Look at | Steal this |
|---------|------------|
| **Aternos** | Giant Start/Stop. Simple status. Difficulty / gamemode as dropdowns. Player list. “Your server” language. No IDs. |
| **Crafty Controller** | Overview + console log + settings as **forms**. Big action buttons. Meters. Tabs a human understands. |
| **Our dash now** | `http://127.0.0.1:8720/panel/servers/{id}` — Start/Stop in the header, meters, join card, **toggles and dropdowns** for config, console at the bottom. Copy that vibe, remotely. |

### What the user sees vs what you send

| User sees | You send (hidden) |
|-----------|-------------------|
| Green **Start** | `server.start` + ids + `accept_eula` |
| Red **Stop** (confirm dialog: “Stop the server?”) | `server.stop` + `confirm` |
| **Restart** | `server.restart` |
| Difficulty: Peaceful / Easy / Normal / Hard | `server.config.update` `{ "difficulty": "hard" }` |
| Game mode dropdown | `gamemode` |
| MOTD text field | `motd` |
| Max players slider | `max-players` |
| World name picker | `level-name` |
| On/off: Nether, PvP, whitelist… | bool properties |
| Console log (read-only wall) | `server.console.read` / snapshot GET |
| Optional “Send command” for **admins** | `server.console.execute` — **not** the main way to control the server |
| CPU / RAM bars | telemetry / `node.metrics` |
| “Playing Aitheiro” | server/build **name** from GET, not a command |
| “Add to this PC” / “Stop hosting” | bind / unbind — labeled in English |

### Hard rules for the UI

1. **IDs are secondary, not hidden.** Show `srv_`, `bld_`, `anode_` in small mono + copy on list rows and a collapsed **Details** block — never as the page title. No `cagt_` or JWT in UI.
2. **No “type an action” box.** No command palette as the control surface.
3. **Settings = forms**, not a JSON/`server.properties` dump as the default view. Raw editor is Advanced only.
4. **Terminal is a log**, plus a small command bar for people who want `/say`. Everyday stuff (start, difficulty, whitelist) is **buttons and toggles**.
5. **Confirm in the UI** (“Stop server?”) then send `confirm: true`. Don’t make the user type `confirm`.
6. **Queued / starting / online** — human words. Not `state=dispatched` or HTTP 429 soup. **Server Offline** (world stopped) is not **PC offline** (agent unreachable). Only show “PC is offline — open CultAgent on that computer” when `GET /v1/agents/{anode}` / telemetry says the agent is down — never because the Minecraft server is stopped or because you only poll slowly.
7. **Don’t invent workarounds** (paste JWT, run CLI, “enqueue payload”). If bind is missing, a button: **Host this server on my PC**.
8. Match **our current dashboard** layout: header actions, status strip, then console + settings. Guild **Join** page stays simple (Join + who’s hosting). Control is a separate friendly page.

If a mock looks like a developer console, it is wrong. Rebuild it like Aternos with Crafty’s overview, using CultForge styling.

---

## Who talks to whom

```
You (launcher)  --user JWT-->  api.cultforge.com  --queue-->  cf-agent on the PC
                                      ^                            |
                                      |         result + telemetry |
                                      +----------------------------+
```

| Who | Token | Job |
|-----|--------|-----|
| **Launcher** | User JWT | Bind servers. Enqueue commands. Read status/telemetry/results. |
| **API** | — | Stores the queue. Hands commands to the agent. Stores results. |
| **cf-agent** | `cagt_…` (never yours) | Polls (or WS). Runs Minecraft. Posts heartbeat, result, tunnel. |

**You never:** heartbeat, poll, command result, tunnel write, `cagt_` tokens, `127.0.0.1:8720` except an optional “Open local panel” link.

**Speed:** Live manifest advertises **`/v1/agent/ws`** — treat WebSocket as the **default** production path. Enqueue over HTTP; API pushes `{ type: "command", … }` on the socket; cf-agent runs in ~1–3s. If WS is down, cf-agent **polls every ~15s** — then “may take up to 15 seconds” is honest. Local dash console on the same PC is always live: `ws://127.0.0.1:8720/ws/servers/{id}/console`. Launcher: **“Starting…”** while command pending; **“PC offline”** only when the agent node is actually unreachable (not when the server is stopped).

---

## One button, start to finish

Example: **Start**

1. You already have a **binding**: `anode_…` + `awlk_…` + `local_server_id` (often same as `srv_…`).
2. `POST /v1/agents/{anode}/commands` with the JSON below.
3. API returns `command_id`, state `queued`.
4. Agent wakes, runs `server.start` on that local id, posts result.
5. You `GET /v1/agents/{anode}/commands/{command_id}` until `succeeded` / `failed` / `expired`.
6. Refresh runtime / server status for the UI.

High-risk actions may come back `needs_confirm`. Then `POST …/commands/{id}/confirm` (your existing route). Also send `"confirm": true` in the payload for those actions.

---

## IDs (use all of these; don’t mix them up)

| ID | Looks like | You use it for |
|----|------------|----------------|
| Node | `anode_…` | Path: `/v1/agents/{id}/…` |
| Binding | `cagb_…` | Bind / unbind |
| Workload | `awlk_…` | Enqueue `workload_id` (API finds the box+server) |
| Guild server | `srv_…` | Cloud catalog / often the **local** folder id too |
| Personal server | `upsrv_…` | Personal catalog |
| Local server | `srv_…` or similar | **What cf-agent actually starts** |

Every `server.*` command **must** put the local id in the payload as **both**:

```json
"server_id": "srv_e5107f0f5a9d",
"local_server_id": "srv_e5107f0f5a9d"
```

cf-agent looks for `server_id` **or** `resource_id` **or** `local_server_id`. If all missing, start/stop/console **fail**.

`workload_id` is for the **API**. The agent process does not need it to start Minecraft.

---

## What you SEND — command table (copy these)

`POST /v1/agents/{node_id}/commands`

```json
{
  "action": "server.start",
  "workload_id": "awlk_…",
  "payload": { }
}
```

Use **exactly** these `action` strings. Do not invent `node.power`, `mc.start`, etc.

### Control the server

| UI | `action` | `payload` | Confirm? |
|----|----------|-----------|----------|
| Start | `server.start` | `server_id`, `local_server_id`, `accept_eula: true` | no |
| Stop | `server.stop` | ids only | **yes** |
| Restart | `server.restart` | ids only | **yes** |
| Refresh state | `server.status` | ids only | no |

### Control the terminal

| UI | `action` | `payload` | Confirm? |
|----|----------|-----------|----------|
| Load / refresh logs | `server.console.read` | ids + `after_seq` (int, default `0`) + `limit` (default `200`) | no |
| Send a line | `server.console.execute` | ids + `command`: `"list"` (or `line`) | no |

`command` is a **Minecraft console** line (`list`, `say hi`, `op Steve`). Not a Windows/PowerShell shell. Strip a leading `/`. Max ~200 chars.

Prefer: **`GET /v1/agents/{anode}/telemetry`** and render `consoles` for the matching `server_id` (refreshed with telemetry ~5–15s). If API has `GET …/workloads/{awlk}/console`, use that. Only enqueue `server.console.read` when those snapshots are empty/stale. Don’t enqueue a read every 2s (you’ll hit 429).

**Activity HUD (same telemetry):** render `activity.lines` on My PCs / Host PC — same friendly sentences as the agent terminal (`kind`: ok/warn/err/info/work).

---

## Cadence — do not treat enqueue as a heartbeat

The agent polls ~every 15s (or gets a WS push). **You** enqueue over HTTP. Enqueue is a **button press**, not a 1-second UI loop.

| UI need | Do this | Do not |
|---------|---------|--------|
| Is the PC online? | `GET /v1/agents/{anode}` / telemetry | Enqueue `server.status` every 1s |
| Players / “Playing …” | `GET` guild runtime / players / server row | Enqueue `node.metrics` on a timer |
| Console log | Prefer `GET …/telemetry` → `consoles[]` (Phase 1); else `GET` console snapshot if API has it; else **one** `server.console.read` every **15–20s** | Enqueue `server.console.read` + `server.status` every 1s |
| Activity HUD | Prefer `GET …/telemetry` → `activity.lines` | Invent status text; treat missing activity as PC offline |
| Start | Enqueue `server.start` **once** (`accept_eula: true`) | Re-fire Start while `queued` / `dispatched` |
| After Start | Poll **that** `command_id`, then GET runtime | Also spam status+console while waiting |
| Install | Enqueue `builds.provision` if you know files are missing; otherwise Start now auto-installs when a `build_id` is on the bound server | Start 3 times because the first result was “missing jar” from an old agent |

If you burst enqueue, the API 429s **the agent** (`Too many connection attempts`) and the PC looks offline. Agent now coalesces duplicate status/console reads (~8s) and backs off on 429 — that is a safety net, not permission to poll at 1Hz.

### Server & world settings

| UI | `action` | `payload` | Confirm? |
|----|----------|-----------|----------|
| Load form | `server.config.read` | ids only | no |
| Save form | `server.config.update` | ids + `values`: `{ "difficulty": "hard", "gamemode": "survival", "motd": "Aitheiro", "level-name": "world" }` | **yes** |

`values` / `properties` = `server.properties` keys only. Not JVM, not files, not world uploads. `level-name` picks which world folder the **next start** uses.

### Metrics & install

| UI | `action` | `payload` | Confirm? |
|----|----------|-----------|----------|
| On-demand host metrics | `node.metrics` | `{}` (no server id) | no |
| Agent ping | `node.status` | `{}` | no |
| List local instances | `server.list` | `{}` | no |
| Install build onto the box | `builds.provision` | `build_id` (`bld_…` / `ubld_…`) | **yes** |

### Confirm list (don’t guess)

Need confirm: `server.stop`, `server.restart`, `server.config.update`, `builds.provision`.

Do **not** enqueue from the launcher: file browser, JVM tuner, `server.mods.install`, backups, `playit.secret`, `server.remove`.

---

## Copy-paste bodies

**Start**

```json
{
  "action": "server.start",
  "workload_id": "awlk_…",
  "payload": {
    "server_id": "srv_…",
    "local_server_id": "srv_…",
    "accept_eula": true
  }
}
```

**Stop** (same ids; add confirm)

```json
{
  "action": "server.stop",
  "workload_id": "awlk_…",
  "payload": {
    "server_id": "srv_…",
    "local_server_id": "srv_…",
    "confirm": true
  }
}
```

**Console execute**

```json
{
  "action": "server.console.execute",
  "workload_id": "awlk_…",
  "payload": {
    "server_id": "srv_…",
    "local_server_id": "srv_…",
    "command": "list"
  }
}
```

**Console read**

```json
{
  "action": "server.console.read",
  "workload_id": "awlk_…",
  "payload": {
    "server_id": "srv_…",
    "local_server_id": "srv_…",
    "after_seq": 0,
    "limit": 200
  }
}
```

**Settings save**

```json
{
  "action": "server.config.update",
  "workload_id": "awlk_…",
  "payload": {
    "server_id": "srv_…",
    "local_server_id": "srv_…",
    "confirm": true,
    "values": {
      "difficulty": "hard",
      "gamemode": "survival",
      "motd": "Aitheiro",
      "level-name": "world",
      "max-players": "20"
    }
  }
}
```

---

## What you GET BACK (without pretending to be the agent)

### After enqueue

`GET /v1/agents/{anode}/commands/{id}`

| Field | Meaning |
|-------|---------|
| `state` | `queued` → `dispatched` → `succeeded` / `failed` / `expired` |
| `result` | Pass-through from the agent. Shape: `{ "ok": true/false, "command": "server.start", "data": {…}, "error": null }` |

**`data` for common actions**

| Action | `result.data` you show |
|--------|------------------------|
| `server.status` | `state`: `stopped` \| `starting` \| `running` \| `stopping` \| `crashed`; `players`, `max_players`, `uptime_seconds`, `pid` |
| `server.console.read` | `lines`: `[{ "seq", "ts", "text" }]`, plus `seq` / `next_seq` |
| `server.console.execute` | ok / error (new log lines come from a following **read**) |
| `server.config.read` | `properties` (key/value), optional `structured`, `raw` |
| `server.config.update` | `properties` (merged) |
| `node.metrics` | `system.cpu_percent`, `system.ram`, `system.disk` — Minecraft TPS is often **null** today |
| `server.list` | `servers[]` with `server_id`, `name`, `path`, … |

### Reads you already have (don’t enqueue for these)

| Want | Where |
|------|--------|
| Agent online? | `GET /v1/agents/{id}` / telemetry |
| Workloads / bindings | `GET` those resources |
| Join address / tunnel | guild or personal **server GET** (`connect` / `effective_address`) |
| **“Playing Aitheiro”** | Bound **server name** or **build name** — not a live game event |
| Player **count** / runtime | Guild `GET …/agents/…` runtime (if present) |
| Guild events / players | Guild GETs — **may be empty**. Agent does **not** currently post “died” / “teleported” |

### What the agent posts (you only **read** the stored copy)

Agent (not you) writes: heartbeat, telemetry, command **result**, workload report, tunnel/runtime. If your UI shows CPU or online, that’s from those stored reads — you did not POST them.

---

## How the agent actually runs (enough to design UI)

1. User installs **cf-agent** on a PC and logs in. Node appears in `GET /v1/agents`.
2. You **bind** a guild/personal server to that node → `awlk_…`.
3. While `cf-agent run` is up, every ~15s it: heartbeat, pull bindings, **poll commands**, report workloads, post telemetry/tunnel.
4. If the API advertises WebSocket, same commands arrive as `{ "type": "command", "id", "action", "payload", "actor_user_id" }`. You still only enqueue; you don’t speak that WS.
5. Local dash `http://127.0.0.1:8720/panel` is the **same PC** full UI (files, JVM, live console). Optional “Host on this PC” = open that URL. It is **not** your sidecar API.

If bind exists but `local_server_id` is missing, enqueue `server.list` (or provision) before start.

---

## Add / remove hosting (not a fake command)

| Want | You call |
|------|----------|
| Add this server to this PC | Existing **bind** — agent creates a local catalog row with that cloud id (no jar yet). Enqueue `builds.provision` if files aren’t on disk. |
| Stop hosting | Enqueue `server.stop`, then existing **unbind** |

---

## Do not

- Invent actions. If it’s not in the table above, don’t send it.
- Call `/v1/agent/*` (agent token).
- Treat 429 as “wrong action” — slow down console reads.
- Show a kill-feed from guesses. Empty events ≠ deaths.
- Put Start/Stop only on a guild **Join** page. Control lives on the **agent / workload** page, wired to this enqueue.
- Ship a **developer** control UI (IDs, action names, JSON, “type a command” as the product). Users get Aternos-simple + Crafty overview + our current dash.

---

## Smoke check

1. Bind AdAstra (`srv_…`) to an online `anode_…`.
2. Enqueue `server.status` with both ids → result `data.state`.
3. Enqueue `server.start` → wait succeeded → status `running` or `starting`.
4. Enqueue `server.console.execute` `{ "command": "list" }` then `server.console.read`.
5. Enqueue `server.config.read` → show `properties`.
6. Offline node → command `expired`; UI says agent offline.

That’s the whole remote control surface for v1: **terminal, power, settings, metrics, playing &lt;build name&gt;** — shown as a **simple controller**, not a CLI.
