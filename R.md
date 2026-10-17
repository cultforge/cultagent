# cf-agent — what to implement

**Audience:** cf-agent (machine slave)  
**Auth:** agent bearer token (`cagt_…`) only — never user JWT for score / tunnel / runtime  
**API baseline:** cult_core2 head **`w9x0y1z2a3b4`**  
**Formula SoT:** [`docs/SCORE.md`](../docs/SCORE.md)  
**Contract SoT:** [`docs/NEXT_AGENT_CONTRACT.md`](../docs/NEXT_AGENT_CONTRACT.md) §4–§5

Lobby / rankings UI / role catalog are **launcher** work — see [`LAUNCHER.md`](LAUNCHER.md). Agent work below is what still unblocks rankings and clean hosting.

---

## 0. Priority order

1. Primary-aware tunnel (stop 403 spam on standby)  
2. Runtime `server_facet` on every upsert  
3. **Live share** (Aternos-style) — `POST /v1/agent/guild/live` every few seconds  
4. `POST /v1/agent/score/batch` emitter (raw deltas)  
5. Kick / ban command handlers  
6. Install plan: honor **pinned mod versions** from build manifest (no “always latest”)  

---

## 1. API already live (agent must call correctly)

| Area | Behavior |
|------|----------|
| **Primary binding** | One active primary per guild/personal server; first bind becomes primary |
| **Tunnel ACL** | Only **primary** may set/clear tunnel → non-primary **403** |
| **Primary unbind** | Clears tunnel / `address_source` → `configured` |
| **Score ingest** | `POST /v1/agent/score/batch` — raw deltas; API owns SCORE.md |
| **Gates** | Competitive guild batch needs **verified guild** + **this node primary** |
| **Runtime** | `POST /v1/agent/…/runtime` may include `server_facet` (facet honesty vs batches) |
| **Integrity** | Idempotent `batch_id`, clock skew, anti-farm, facet cross-check; no world saves |

Legacy: `POST /v1/agent/guild/stats` (verified required) — prefer score/batch.

---

## 2. Primary-aware tunnel + runtime

- [ ] Know if this node is **primary** for the bound server before tunnel writes; if not, **skip** (no 403 loop)
- [ ] On primary: post tunnel / clear-tunnel / network_mode as today
- [ ] Include **`server_facet`** on every runtime upsert:

```json
"server_facet": {
  "game_mode": "survival",
  "cheats": false,
  "difficulty": "hard",
  "minecraft_version": "1.20.1",
  "loader": "forge",
  "pack_id": "optional"
}
```

- [ ] Keep runtime (state, player_count, TPS, version, facet) synced — rankings/discover metadata come from API

---

## 3. Score batch emitter (required for rankings)

```http
POST /v1/agent/score/batch
Authorization: Bearer cagt_…
```

Emit **raw facts**, never final scores. Sketch:

```json
{
  "schema_version": 1,
  "workload_id": "awlk_…",
  "agent_node_id": "cagn_…",
  "binding": { "guild_id": "gld_…", "guild_server_id": "gms_…" },
  "server_facet": { "game_mode": "survival", "cheats": false, "difficulty": "hard", "minecraft_version": "1.20.1", "loader": "forge" },
  "integrity": {
    "agent_version": "x.y.z",
    "batch_id": "uuid-v4",
    "batch_seq": 42,
    "observed_at": "2026-10-17T12:00:00Z",
    "session_fingerprint": "opaque-stable-per-session"
  },
  "players": [
    {
      "minecraft_uuid": "…",
      "minecraft_name": "Steve",
      "cultforge_user_id": "cf_…",
      "delta": {
        "kills": [{ "victim_type": "minecraft:zombie", "tags": ["hostile"], "count": 3 }],
        "deaths": [{ "cause": "mob", "count": 1 }],
        "advancements": ["minecraft:story/mine_diamond"],
        "playtime_seconds": 1200,
        "exploration": { "biomes_new": 2 }
      }
    }
  ]
}
```

- [ ] Collect deltas from MC process (kills, deaths, advancements, active playtime, exploration)
- [ ] Registry IDs (`modid:name`) + tags — not vanilla-only hardcodes
- [ ] Unique `batch_id`; monotonic `batch_seq`; respect ~64KB payload caps
- [ ] Prefer **primary** for competitive guild ingest
- [ ] On `403 guild_not_verified` / `no_primary_binding`: clear log; keep hosting; do not retry as JWT
- [ ] Personal servers: personal-scoped batches OK; do not expect verified global ladders
- [ ] Exclude AFK from `playtime_seconds` when possible
- [ ] Optional: `POST /v1/agent/guild/events` for UI events

| Guild status | Host / tunnel / runtime | Competitive score batch |
|--------------|-------------------------|-------------------------|
| unverified / pending | OK | Rejected |
| verified + primary | OK | Accepted |
| suspended / rejected | OK (ops) | Rejected |

---

## 4. Live share (Aternos-style) — agent → API → launcher

One-shot preferred (also WS `type: "live"` on `/v1/agent/ws`):

```http
POST /v1/agent/guild/live
Authorization: Bearer cagt_…
```

```json
{
  "workload_id": "awlk_…",
  "guild_server_id": "gms_…",
  "reported_state": "running",
  "minecraft_version": "1.20.1",
  "player_count": 2,
  "max_players": 20,
  "tps": 19.8,
  "mspt": 48.0,
  "world": { "name": "world", "dimension": "minecraft:overworld", "time": 12000, "weather": "clear" },
  "server_facet": { "game_mode": "survival", "cheats": false, "difficulty": "hard", "minecraft_version": "1.20.1", "loader": "fabric" },
  "players": [
    {
      "minecraft_uuid": "…",
      "minecraft_name": "Steve",
      "ping_ms": 42,
      "gamemode": "survival",
      "dimension": "minecraft:overworld",
      "health": 20,
      "food": 18,
      "position": { "x": 120.5, "y": 64.0, "z": -33.2, "yaw": 90.0, "pitch": 0.0 },
      "session_stats": {
        "blocks_mined": 120,
        "blocks_placed": 40,
        "distance_m": 850,
        "deaths": 1,
        "kills_mobs": 15,
        "playtime_seconds": 3600
      }
    }
  ],
  "events": [
    { "event_type": "player.join", "minecraft_name": "Steve", "payload": {} }
  ]
}
```

Personal: `POST /v1/agent/personal/servers/{server_id}/live`.

`session_stats` allowlist: `blocks_mined`, `blocks_placed`, `distance_m`, `deaths`, `kills_mobs`, `kills_players`, `playtime_seconds`, `xp_gained`, `items_crafted`.

- [ ] Poll MC every **3–10s** while running; POST live (or WS `live`)
- [ ] Include **coordinates** + dimension + session counters per online player
- [ ] Keep posting when roster empty (`player_count: 0`)
- [ ] Do not put competitive score totals here — use score/batch

API fans out `{ type: "live_share", payload }` to room `guild:{id}:live:{server_id}` (or `personal:{sid}:live`).

---

## 5. Commands to execute

| Action | Notes |
|--------|--------|
| `server.player.kick` | minecraft_name / user_id / reason |
| `server.player.ban` | High-risk; launcher may have confirmed |

- [ ] Implement kick/ban in command runner if missing

---

## 6. Build / pack install — honor version pins

Launcher now pins Modrinth mods with `version` / `version_id`. Install manifests include exact file URLs + hashes; unresolved pins appear in `install_manifest.unresolved`.

- [ ] When installing a guild/personal build: download **manifest `files[]` URLs** as-is — do **not** re-resolve “latest” from Modrinth by slug
- [ ] Prefer `sha256` / `sha512` verify from manifest
- [ ] If `unresolved` non-empty: surface error to user/launcher; do not silently skip required mods
- [ ] Search/install public catalog builds still uses API-resolved plans — agent is the downloader, not the version picker

---

## 7. Hard “do not” (agent)

- Do not compute SCORE.md points and POST finals  
- Do not upload world saves / `saves/**`  
- Do not overwrite another server’s tunnel without primary  
- Do not use launcher JWT for score / tunnel / runtime  
- Do not re-fetch “latest” Modrinth when a pinned version is in the install plan  

---

## 8. Acceptance checklist

- [ ] Standby node: zero tunnel 403 spam  
- [ ] Runtime always carries `server_facet`  
- [ ] Live share posts with coords + session_stats; launcher sees updates  
- [ ] Score batches land on verified+primary guilds; rankings move  
- [ ] Kick/ban commands work from launcher enqueue  
- [ ] Pack install matches pinned jars; bad pins fail visibly  

---

## 9. Related

| Doc | Use |
|-----|-----|
| [`LAUNCHER.md`](LAUNCHER.md) | Launcher dump (UI, lobby, roles, share, build pins) |
| [`LOBBY.md`](LOBBY.md) | Lobby REST (launcher-only) |
| [`docs/SCORE.md`](../docs/SCORE.md) | Formulas (API-side) |
| [`docs/NEXT_AGENT_CONTRACT.md`](../docs/NEXT_AGENT_CONTRACT.md) | Full roles + score contract |
| [`docs/CHECKLIST_0.2.4.md`](../docs/CHECKLIST_0.2.4.md) | API checklist |

**Note:** GuildMaster seed includes `agent.*` + `lobby.*`. Catalog for humans: `GET /v1/guilds/permissions` (launcher role UI).
