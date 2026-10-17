# NEW 0.2.4 — Agent / ranking contract delta

**Status:** design dump + agent WIP (package remains **0.2.3**; releases on brakes).  
**Baseline:** shipped cf-agent **0.2.3**.  
**Sources of truth (API/formula):** `NEXT_AGENT_CONTRACT.md`, `SCORE.md` in cult_core2 (when present). This file records **what changed in the design** so cultagent implementation can track against it.

---

## Verdict locked in

| Question | Answer |
|----------|--------|
| Implement scoring on guild-connected servers + ranking system? | **Yes** |
| Data path for competitive stats? | **cf-agent → API only** (launcher = UI) |
| Who may feed competitive boards? | **Platform-verified guilds** with stats-eligible primary-bound servers |
| Scope beyond guilds? | **Yes** — server, guild, **global individual**, **global guild** ladders |
| Identity systems? | **Tiers · Titles · Achievements** kept **separate** |
| cultsdk / APIs / guild services? | **Yes** — API/guilds own formulas; agent emits raw deltas |

---

## What was already in the contract (kept)

- Roles: API control plane · launcher JWT · cf-agent slave token  
- P0/P1 ownership + **primary binding** + tunnel exclusivity  
- Agent reports raw **deltas**, API owns formula  
- Facet axes: game mode / cheats / difficulty / pack / version  
- Score batch sketch + guild/personal ranking endpoints  
- Security: agent ≠ user session; no world saves  

---

## Newly specified for 0.2.4

### 1. Verified-guild gate

- `Guild.verification_status`: `unverified | pending | verified | rejected | suspended`  
- Platform **admin** approves verification  
- Competitive ingest only when guild is `verified` and server is **stats eligible** (primary cf-agent binding)  
- Unverified guilds: host/tunnel/runtime OK; **no** competitive boards / tiers / global standings  

### 2. Ranking scopes

| Ladder | Competitive pool |
|--------|------------------|
| Per server | Eligible world |
| Guild members | Verified guild aggregate |
| Global players | Across verified guild servers |
| Global guilds | Verified guilds as entities |
| Personal boards | Local / optional; **not** mixed into verified global |

### 3. Agent sync + ingest shape

- Batches carry `agent_node_id`, binding ids, facet, and **integrity** (`batch_id`, `batch_seq`, `session_fingerprint`, …)  
- Primary agent keeps hosted server **runtime/facet/tunnel** rows synced on the API  
- Launcher never posts score facts  

### 4. Anti-cheat / integrity

- Auth + verified gate + binding  
- Idempotent batches; rate/size limits; clock skew  
- Facet cross-check vs runtime; cheats-on → separate ladder  
- AFK/farm diminishers + spike **quarantine** ledger (API-side)  
- Full accept/reject audit  

### 5. Tiers / Titles / Featured achievements

| System | Role |
|--------|------|
| **Tier** | Percentile band S+…E + min activity |
| **Title** | Predicate-earned identity (active title + inventory) |
| **Achievements** | Unlocks + dynamic rarity; player features **3–5** on profile |

Display hierarchy: `SCORE → TIER → RANK` and `ACHIEVEMENTS → TITLES → FEATURED`.

### 6. API surface additions

- Admin: `POST /v1/admin/guilds/{id}/verify`  
- Agent: `POST /v1/agent/score/batch` (+ optional `/events`) with verified gate  
- Rankings: `/v1/rankings/players`, `/v1/rankings/guilds` + existing guild/personal  
- Profile: `/v1/profile/{id}/card`, featured + active-title PATCH, achievements/titles catalogs  

### 7. Service placement

| Piece | Where |
|-------|--------|
| Ingest, ledger, integrity, scoring engine | **cult-api** |
| Guild verify + guild rollups / guild ranking routes | **cult-guilds** + admin |
| Shared formula package | cultsdk (API-side) |
| **cf-agent** | Emit raw score batches + facet on runtime; never invent scores |
| Launcher | Read boards + profile; featured/title selection only |

### 8. Implementation order

```text
P0  FIX-AGENT ownership leak
P1  Primary + tunnel exclusivity
P2  Personal ACL / kick
P3  Guild verification + stats_eligible   ← gate before score
P4  Score batch + ledger + server/guild facet boards
P5  Global boards + anti-cheat quarantine
P6  Tiers / titles / achievements / featured card
P7  Discover + richer personal hosting
```

---

## Agent progress (this repo)

| Phase | Agent status | Notes |
|-------|--------------|-------|
| P0–P1 tunnel stomping / foreign bindings | **done** (0.2.3) | Bindings drop foreign `node_id`; tunnel only when hosting |
| P1 Primary binding awareness | **WIP** | `is_primary` / `stats_eligible` helpers; competitive publish gated |
| P3 Verified gate | **API** | Agent treats 403 as non-fatal (hosting OK) |
| P4 Score batch emit | **WIP** | `POST /v1/agent/score/batch` + legacy `guild/stats` fallback |
| P5–P6 | **API / launcher** | Agent does not compute tiers/titles |

### Agent endpoints used

- `POST /v1/agent/score/batch` (preferred competitive ingest)
- `POST /v1/agent/guild/stats` (legacy fallback; API requires verified guild)
- Existing guild runtime/tunnel/players/events

---

## Explicit non-goals (agent)

- Letting launcher invent or correct competitive scores  
- Mixing unverified or personal-only play into verified **global** ladders  
- Collapsing tiers/titles/achievements into a single “badge points” field on the agent  
- Shipping a **0.2.4** binary until release brakes are lifted  

---

## Release brakes

GitHub Actions `release-binaries.yml` is **workflow_dispatch only** (no auto publish on `v*` tags) until ranking track is ready to ship as **0.2.4**.
