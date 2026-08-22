# API / Launcher follow-ups

> **Launcher UI spec (Aternos-style, fresh):** see [`docs/LAUNCHER_UI_CONTEXT.md`](../docs/LAUNCHER_UI_CONTEXT.md) — product/design handoff for the Community Launcher.
>
> **Exact command payloads:** [`docs/LAUNCHER_AGENT_CONTRACT.md`](../docs/LAUNCHER_AGENT_CONTRACT.md)
>
> **API ↔ agent matrix:** [`docs/INTEGRATION.md`](../docs/INTEGRATION.md) §3.6

CultAgent implements machine-side execution; the launcher implements user JWT flows via sidecar.

## Agent-side (done in cf-agent)

- Bindings poll + scope-aware tunnel/runtime (`/v1/agent/bindings`, `/v1/agent/servers`)
- Unified build catalog client (`/v1/agent/builds/search`, manifest, provision) with guild fallback
- Personal mode routes (`/v1/agent/personal/servers/{id}/tunnel|runtime`)
- CLI: `cf-agent agent-servers` (add `--bindings` for raw cache), `cf-agent builds --q …`
- **Activity HUD + console → telemetry (Phase 1):** `POST /v1/agent/telemetry` embeds `metrics.activity` + `metrics.consoles` (see INTEGRATION §3.6)
- **Guild presence (live manifest):** console → `POST /v1/agent/guild/players` + `…/events`; `player_count` on guild/personal runtime (INTEGRATION §3.7)

## Launcher-side (Community Launcher — not this repo)

See **`docs/LAUNCHER_UI_CONTEXT.md`** for the Aternos-style screen spec and control checklist. Payloads: **`docs/LAUNCHER_AGENT_CONTRACT.md`**.

**Phase 1 read path:** poll `GET /v1/agents/{anode}/telemetry` every 5–15s; render `activity.lines` + matching `consoles[]`. Do not timer-enqueue `server.console.read` while consoles are present.

## Phase 2 — API activity routes (cult_core / API)

Unblock / ship when ready:

| Priority | Item | Notes |
|----------|------|--------|
| **P0** | Passthrough `activity` + `consoles` on `GET /v1/agents/{anode}/telemetry` | `get_filtered_telemetry` must not strip these keys — otherwise Phase 1 launcher UI is empty |
| P1 | `POST /v1/agent/activity` (`cagt_`) | Append-only batch ≤50: `{ lines: [{ ts, kind, text, source }] }` with `source` = `agent` \| `console` |
| P1 | `GET /v1/agents/{anode}/activity` (user JWT) | Recent lines; `?after_ts=` / `?limit=` |
| P2 | `GET /v1/agents/{anode}/workloads/{awlk}/console` | Snapshot by `seq` (preferred over enqueue) |

Keep **`POST /v1/agent/guild/events`** for gameplay (`player.joined`, deaths, etc.) — do **not** overload it with HUD Activity lines.

**Agent follow-up (after routes appear in manifest):** discover `/v1/agent/activity`, flush bridge batches (debounced 1–2s), fall back to telemetry embed if missing. Do not add to `REQUIRED_AGENT_ROUTES` until live and stable.

## Legacy notes (local agent only)

These work on the agent + existing API `CANONICAL_ACTIONS`:

- `server.*` lifecycle, console, config
- `server.mods.*`, `server.backup.*`
- Device login / poll / heartbeat

## Agent local surfaces

- Dashboard: `http://127.0.0.1:8720/panel/…` while `cf-agent run`
- REST wrappers under `/v1/servers/…` (loopback panel)

## Explicitly out of scope for agent installers

- Minecraft **clients** / launcher instances
- Bedrock dedicated / proxies-only until scheduled
