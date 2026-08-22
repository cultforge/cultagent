# api.cultforge.com — Cherry-picked remote agent control

> **Paste this entire file** into the **CultForge API / cult_core** Cursor agent.
>
> **Goal:** Let the Community Launcher remotely control a bound Minecraft instance the way the local cf-agent dash does for **a small subset of features** — not a 1:1 clone of `http://127.0.0.1:8720/panel`.
>
> **Companions (do not implement UI here):**
> - cf-agent already **executes** these commands when they appear on `GET /v1/agent/poll`
> - Launcher UI prompt: `docs/LAUNCHER_AGENT_CONTROL_PROMPT.md` (other repo / other agent)
> - Bindings/catalog already shipped: `docs/LAUNCHER_UI_CONTEXT.md`

---

## Plain English (product)

The launcher needs **four** remote things. Not the whole local dash.

| Need | Meaning |
|------|---------|
| **Control the terminal** | See live-ish logs. Type Minecraft commands (`list`, `say`, `op`). |
| **Control the server** | Start / stop / restart the process. |
| **Control world / server settings** | Read and change `server.properties` (difficulty, gamemode, motd, `level-name`, nether, etc.). Not a file browser. Not JVM RAM sliders. |
| **Get metrics** | Is the agent online? CPU/RAM. Server running? Player count. Join address. **What they are playing** (build/server name, e.g. “Aitheiro”). |

**In-game story** (“Arcade died”, “teleported to spawn”) is a **later** slice. Cloud already has guild **events / players / stats** POST routes. cf-agent does **not** parse console for deaths/teleports yet. Do not block v1 on that. See §1.1.

---

## 0. Why this ticket exists

cf-agent’s local dash has: Overview, Terminal, Files, Config, JVM tuner, Backups, Mods, Players, Network.

The launcher **must not** get all of that over the cloud.

What is missing today: a **user-JWT enqueue + result** pipe. The agent already consumes:

```
GET  /v1/agent/poll          → { commands: [{ id, action, payload, actor_user_id }], desired_workloads, poll_interval_seconds }
POST /v1/agent/commands/{id}/result   body { success, result }   (cagt_ token)
GET  /v1/agent/commands/schema
```

The launcher has user JWT (sidecar → `api.cultforge.com`). It **cannot** call `/v1/agent/*`. There is no documented user-JWT route to put a command on that poll queue.

**Your job:** add that pipe, allowlist the cherry-picked actions, persist results so the launcher can poll them, cache a console snapshot, expose metrics/runtime reads. Do **not** proxy the local file browser, JVM tuner, or live WebSocket.

---

## 1. Cherry-pick (implement these, nothing else in v1)

### Ship now (launcher MVP)

| Need | Action / API | Launcher UI |
|------|----------------|-------------|
| Control server | `server.start` / `stop` / `restart` | Buttons |
| Status | `server.status` | Running, players, uptime |
| Terminal logs | `server.console.read` + snapshot GET | Scrolling log |
| Terminal input | `server.console.execute` | Command bar |
| World / server settings | `server.config.read` + `server.config.update` | Properties form (difficulty, gamemode, motd, level-name, …) |
| Metrics | existing telemetry + `GET` runtime; enqueue `node.metrics` if needed | CPU/RAM, agent online |
| What they’re playing | **already on the bound server/build record** (`name`, `build_id`) | “Playing Aitheiro” |
| Install after bind | `builds.provision` | Add server files |
| Map ids | `server.list` | Debug |

### Ship next (v1.1 — same pipe)

| Action | Notes |
|--------|--------|
| `server.mods.list` | Read-only mods |
| `network.status` | playit vs direct + public join |

### 1.1 Player activity feed (not v1)

**Already true without new work:**

- Bound server/build name → “Playing **Aitheiro**”
- Runtime: process up/down, optional player **count**
- Guild dashboard reads: `GET /guilds/{gid}/agents/…` (runtime / players / events **if data exists**)

**Not true today:** cf-agent does **not** scrape logs for “died”, “teleported”, joins/leaves, advancements. The **cloud routes** exist for the agent to POST:

- `POST /v1/agent/guild/players` — roster
- `POST /v1/agent/guild/events` — append-only events (≤50/batch)
- `POST /v1/agent/guild/stats` — uuid stats

Those writers are implemented in the agent **client**, but the control plane **does not parse console → events** yet. A later ticket (cf-agent + API read for launcher) can map lines like:

```
Arcade joined the game
Arcade was slain by Zombie
Arcade teleported to …
```

into `events[]` with `type`, `player`, `at`. Until then, launcher must **not** fake a kill-feed.

### Explicitly out of scope (reject enqueue with 400)

- `server.mods.install` / `remove` / `update` / `resolve`
- `server.backup.create` / `restore`
- `server.remove` (disk wipe)
- `playit.setup` / `playit.secret` / `playit.reset` / `playit.claim.wait`
- `sidecar.*`
- `config.profile.*`
- file browser, JVM tuner, world-folder create (local panel only)

Users who need Files / Tuner use **local panel** (`127.0.0.1:8720`) via “Host on this PC”.

---

## 2. Auth model (do not mix tokens)

| Client | Token | May |
|--------|--------|-----|
| Launcher / sidecar | User JWT (`sKEY`) | Enqueue, read command status, read console snapshot, bind/unbind (already exists) |
| cf-agent | `cagt_…` | Poll, report result, heartbeat, telemetry, tunnel |

Never accept user JWT on `/v1/agent/*`. Never put `cagt_` in launcher responses.

**Who may enqueue against `anode_…`:**

1. Node **owner** (`owner_id` on the agent node)
2. If node is guild-attached (`guild_id = gld_…`): guild **owner / admin** (or existing `agent.command` permission if you have one)
3. **Not** random guild members
4. Personal-mode node (`guild_id` null): **owner only**

**Resource check:** payload `local_server_id` / `workload_id` / `guild_server_id` / `personal_server_id` must match an **active binding** (`cagb_…`) on that node. Reject 404/403 if unbound.

---

## 3. Routes to add (user JWT)

Add to `GET https://api.cultforge.com/manifest.json`. Sidecar will proxy the same paths.

Suggested (adjust prefix to match existing `/v1/agents/…` style):

```
POST /v1/agents/{node_id}/commands
GET  /v1/agents/{node_id}/commands/{command_id}
GET  /v1/agents/{node_id}/commands?limit=&status=

GET  /v1/agents/{node_id}/workloads/{workload_id}/console
```

Guild-scoped aliases are OK if you already nest under `/v1/guilds/{gld}/agents/{anode}/…` — then **also** support personal nodes (no guild) on `/v1/agents/{anode}/…`.

### 3.1 `POST /v1/agents/{node_id}/commands`

Enqueue one command onto that node’s poll queue.

**Request**

```json
{
  "action": "server.start",
  "workload_id": "awlk_…",
  "local_server_id": "srv_e5107f0f5a9d",
  "payload": {
    "accept_eula": true
  },
  "confirm": true
}
```

| Field | Required | Notes |
|-------|----------|--------|
| `action` | yes | Must be in v1 allowlist (§1) |
| `workload_id` | yes if bound | `awlk_…` from binding |
| `local_server_id` | yes for `server.*` | Agent `resource_id`; often same as `srv_…` |
| `payload` | no | Merged into poll payload |
| `confirm` | high-risk | `true` required for stop/restart/provision/config.update |

**High-risk (require `confirm: true`):** `server.stop`, `server.restart`, `server.config.update`, `builds.provision`

**Server stamps onto the poll command (do not trust client for these):**

```json
{
  "id": "cmd_…",
  "action": "server.start",
  "actor_user_id": "usr_…",
  "payload": {
    "local_server_id": "srv_e5107f0f5a9d",
    "server_id": "srv_e5107f0f5a9d",
    "workload_id": "awlk_…",
    "accept_eula": true
  }
}
```

cf-agent resolves `resource_id` as:

```
payload.server_id  |  payload.resource_id  |  payload.local_server_id
```

Always set **`server_id` and `local_server_id` to the same local id**.

**Response `201`**

```json
{
  "status": true,
  "data": {
    "id": "cmd_…",
    "node_id": "anode_…",
    "action": "server.start",
    "state": "queued",
    "created_at": "2026-08-17T…",
    "poll_hint_seconds": 15
  }
}
```

States: `queued` → `dispatched` (handed to poll) → `succeeded` | `failed` | `expired`

TTL: expire `queued` after **120s** if the agent never polls (offline). Return `expired` so the launcher can show “agent offline”.

**Errors**

| HTTP | When |
|------|------|
| 400 | Unknown action, missing `local_server_id`, missing `confirm` on high-risk |
| 401 | No/invalid user JWT |
| 403 | Not owner/admin; personal vs guild mismatch |
| 404 | Unknown node, no binding, workload not on this node |
| 409 | Duplicate in-flight same action+workload (optional; nice to have) |
| 429 | Rate limit |

**Rate limits (per user + node):**

- `server.console.execute`: 30 / minute
- `server.console.read`: 20 / minute (launcher should prefer snapshot GET)
- lifecycle (`start/stop/restart`): 10 / minute
- `builds.provision`: 5 / hour / node

### 3.2 `GET /v1/agents/{node_id}/commands/{command_id}`

Return enqueue row + agent result after `POST /v1/agent/commands/{id}/result`.

```json
{
  "status": true,
  "data": {
    "id": "cmd_…",
    "action": "server.console.execute",
    "state": "succeeded",
    "success": true,
    "result": { "ok": true, "data": { } },
    "error": null,
    "created_at": "…",
    "completed_at": "…"
  }
}
```

`result` is whatever cf-agent posted (already `{ ok, data?, error? }`). Pass through; do not invent a second schema.

When the agent reports, set `state` from `success`.

### 3.3 Console snapshot (do this — do not make the launcher enqueue a read every 2s)

`GET /v1/agents/{node_id}/workloads/{workload_id}/console`

```json
{
  "status": true,
  "data": {
    "local_server_id": "srv_…",
    "updated_at": "2026-08-17T…",
    "after_seq": 1842,
    "lines": [
      { "seq": 1840, "text": "[Server thread/INFO]: Done (3.2s)!" },
      { "seq": 1841, "text": "[Server thread/INFO]: Starting Minecraft server" }
    ]
  }
}
```

**How to fill it (pick one, implement at least A):**

**A (minimum):** When agent result for `server.console.read` arrives, copy `result.data.lines` + seq onto this snapshot.

**B (better):** Accept an optional console tail on existing `POST /v1/agent/telemetry` or `POST /v1/agent/guild/events` if the payload already has room. Do not block v1 on a cf-agent change.

Launcher loop:

1. `GET …/console` every 3–5s (no agent wake-up)
2. If snapshot older than 20s **and** agent heartbeat is online → enqueue **one** `server.console.read` (`after_seq`, `limit: 200`)
3. Command input → enqueue `server.console.execute` then one `server.console.read`

cf-agent `server.console.read` params: `after_seq` (int, default 0), `limit` (int, default 200).  
`server.console.execute` params: `command` or `line` (string).

---

## 4. Wire into existing poll (do not break cf-agent)

`GET /v1/agent/poll` must keep returning:

```json
{
  "status": true,
  "data": {
    "commands": [ /* queued rows, max ~10 per poll */ ],
    "desired_workloads": [ … existing … ],
    "poll_interval_seconds": 15,
    "pending_confirms": 0
  }
}
```

Each command **exactly**:

```json
{
  "id": "cmd_…",
  "action": "server.console.execute",
  "payload": { },
  "actor_user_id": "usr_…"
}
```

Action aliases cf-agent already maps (you may send either):

| Alias | Canonical |
|-------|-----------|
| `server.command` | `server.console.execute` |
| `config.edit` | `server.config.update` |
| `agent.ping` | `node.status` |

Prefer **canonical** names from §1.

After a successful poll that included a command, mark it `dispatched` so it is not delivered twice. If the agent never reports result within 90s, mark `expired`.

Existing `POST /v1/agent/commands/{command_id}/result` stays **agent-token only**. On receive, update the user-visible command row.

If you already have a CAGL / `CultAgentCommandProfile` on `GET /v1/agent/commands/schema`, add the v1 allowlist there so the agent and launcher agree.

---

## 5. Payload cookbook (copy these)

`resource` = `local_server_id` (required). Also set `payload.server_id` to the same value.

**Start**

```json
{ "action": "server.start", "payload": { "accept_eula": true } }
```

**Stop / restart** — empty payload + `confirm: true`

**Status** — empty payload

**Console read**

```json
{ "action": "server.console.read", "payload": { "after_seq": 0, "limit": 200 } }
```

**Console execute**

```json
{ "action": "server.console.execute", "payload": { "command": "list" } }
```

Strip a leading `/` if present. Max length **200** chars. Reject empty.

**Provision** (after bind, files missing)

```json
{
  "action": "builds.provision",
  "confirm": true,
  "payload": {
    "build_id": "bld_…",
    "local_server_id": "srv_…"
  }
}
```

Use the bound server’s `build_id` from guild/personal server record. Do not let the client provision an arbitrary build onto someone else’s workload.

**Config read** — empty payload (`server.config.read`)

**Config update** (world / server settings — `server.properties` keys only)

```json
{
  "action": "server.config.update",
  "confirm": true,
  "payload": {
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

Allow only known `server.properties` keys. Reject path traversal, JVM flags, and file contents. Changing `level-name` selects which world folder the next start uses; it does not upload a world.

**Metrics** — enqueue `node.metrics` if you need an on-demand snapshot; prefer existing `POST /v1/agent/telemetry` reads for the launcher.

**List** — `server.list`, no `local_server_id` required (node-scoped). Owner/admin only.

---

## 6. What already exists (do not rebuild)

| Feature | Status |
|---------|--------|
| Bind / unbind | User JWT `POST/DELETE …/bind` — keep as “add/remove execution” |
| Agent heartbeat / online | `POST /v1/agent/heartbeat` |
| Runtime / players / events **reads** | Guild dashboard `GET /guilds/{gid}/agents/…` — status only |
| Tunnel/runtime **writes** | Agent-only `/v1/agent/guild/*` and `/v1/agent/personal/*` |
| Local dash Files / Config editor / JVM / Worlds | Loopback `127.0.0.1:8720` — out of scope |

“Remove agent execution” = existing **unbind** + enqueue `server.stop` (stop first, then DELETE bind). API may offer a convenience `POST …/unbind` that does both later; not required for v1 if launcher can call two endpoints.

---

## 7. Security

1. Allowlist actions. Unknown action → 400, do not queue.
2. Binding-scoped. No command against a server this node does not host.
3. Redact secrets in stored `result` (`secret`, `token`, `cagt_`, `playit.toml`, absolute paths optional to strip).
4. Audit log: `actor_user_id`, `node_id`, `action`, `workload_id`, `command_id`.
5. Console execute is **not** a host shell. It is a Minecraft server console line. Still rate-limit; still require binding + admin.
6. Do not stream arbitrary files through this API.

---

## 8. Manifest / sidecar

Add the new routes to `manifest.json` with stable command IDs, e.g.:

| ID | Method / path |
|----|----------------|
| `agents.commands.create` | `POST /v1/agents/{node_id}/commands` |
| `agents.commands.get` | `GET /v1/agents/{node_id}/commands/{command_id}` |
| `agents.commands.list` | `GET /v1/agents/{node_id}/commands` |
| `agents.workload.console` | `GET /v1/agents/{node_id}/workloads/{workload_id}/console` |

Live default: `https://api.cultforge.com` (not apex `cultforge.com`). Local override only if the user is on cult_core2 localhost `8071`.

---

## 9. Acceptance tests

- [ ] Owner JWT enqueues `server.start` on bound personal/guild workload → next agent poll includes the command with `actor_user_id` and `local_server_id`
- [ ] Agent `POST …/result` → `GET …/commands/{id}` shows `succeeded` + pass-through `result`
- [ ] Unbound workload → 404/403, nothing queued
- [ ] Guild member (non-admin) → 403
- [ ] `server.config.update` with `confirm: true` and `values` → queued; without `confirm` → 400
- [ ] `server.mods.install` from user JWT → 400 allowlist
- [ ] `server.stop` without `confirm: true` → 400
- [ ] Offline agent: command `expired` after TTL; launcher can show “agent offline”
- [ ] `GET …/console` returns last `server.console.read` snapshot
- [ ] Personal node (no `guild_id`) works without requiring a guild path
- [ ] Existing bind/unbind/heartbeat/poll tests still pass
- [ ] Manifest lists the four new routes

---

## 10. One-paragraph summary

Do **not** clone the local Crafty dash onto `api.cultforge.com`. Add a **user-JWT command queue** that feeds the existing agent poll for **terminal, start/stop, server.properties, metrics**. Persist results. Cache a **console snapshot**. “Playing Aitheiro” comes from the bound build/server name. Kill-feed (died / teleported) is **not** v1. Files, JVM, mod installs, playit secrets stay on the local panel. Bind/unbind already add/remove execution — enqueue `server.stop` before unbind.

---

## 11. cf-agent consumer contract (already shipped — match this)

Poll command execution: `src/cultagent/cloud/control_plane.py` `_execute_command`.  
Canonical actions: `src/cultagent/constants.py` `COMMANDS`.  
Result POST: `/v1/agent/commands/{command_id}/result` body `{ "success": bool, "result": object }`.
