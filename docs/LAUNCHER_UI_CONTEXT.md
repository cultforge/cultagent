# CultForge Launcher — Server control UI (fresh spec)

> **Audience:** Anyone designing or building the **Community Launcher** play/control experience.
>
> **Tone:** Like **Aternos** — visual, calm, one-glance status. Not a developer console.
>
> **Technical payloads:** [`LAUNCHER_AGENT_CONTRACT.md`](./LAUNCHER_AGENT_CONTRACT.md) · **API wiring:** [`INTEGRATION.md`](./INTEGRATION.md)

---

## What this document is

The launcher **does not run Minecraft**. It is the remote control for servers that live on a player’s PC, executed by **cf-agent**.

Users should feel like they opened Aternos: big Start, clear Online/Offline, copy join address, tweak difficulty in plain English. **IDs stay available** (for support, binds, and power users) but **never headline the screen** — names and status come first.

---

## Design principles

| Do | Don’t |
|----|--------|
| One hero action per screen (Start / Stop) | Command palette, “type an action” |
| Human status: **Online**, **Starting…**, **Offline**, **Crashed** | `dispatched`, HTTP codes as the main message |
| Settings as **dropdowns and toggles** | `server.properties` dump as the default |
| Console as a **scrollable log** | Terminal as the only way to change difficulty |
| Show **server name + build name** (“Playing Valthera”) | Title the page `srv_1hAMv7…` with no friendly name |
| **IDs in small mono text** with copy — secondary lines | IDs as large headers or the only label on a row |
| Confirm destructive actions in UI (“Stop server?”) | Ask user to type `confirm` |
| Empty states with one clear next step | Dead ends (“bind failed — see logs”) |

**Visual language:** dark card layout, large status pill, teal/green for online, soft red for offline/crashed, purple **Guild** badge, blue **Personal** badge. Match CultForge branding; density closer to Aternos than Crafty admin.

---

## Two layers of status — never fake “offline”

The launcher must track **two independent things**. Mixing them up is misleading and breaks trust — especially now that live API advertises agent WebSocket.

| Layer | What it means | Where to read it (launcher, user JWT) | UI label |
|-------|----------------|----------------------------------------|----------|
| **Agent PC** | Is CultAgent running and reachable? | `GET /v1/agents/{anode}`, `GET …/telemetry`, guild/personal **runtime** snapshots | **PC connected** / **PC offline** (My PCs + Host PC strip only) |
| **Minecraft server** | Is the world process up? | Runtime / workload report / last `server.status` result | **Online** / **Offline** / **Starting…** / **Crashed** (Play list + hero status) |

### Rules (non‑negotiable)

1. **Server Offline ≠ PC offline.** A stopped world on a connected PC is normal — show **Start**, not “open CultAgent”.
2. **Only show “PC offline”** when the API says the agent is unreachable: stale `last_seen`, explicit offline, or command **`expired`** because nothing polled in time. Do **not** infer PC offline from a slow UI refresh or from server `state=stopped`.
3. **Live API has agent WebSocket** (`/v1/agent/ws` in manifest — see below). When cf-agent is connected, commands are **near-instant** after enqueue. Default UX is **“Starting…”** for 1–3s — **not** a blanket “may take 15 seconds” spinner.
4. **15s is poll fallback only** — when the agent has no WS session (or WS dropped). Say **“Connected (standard)”** on My PCs, not “offline”.
5. **Optional polish:** if telemetry exposes transport (`websocket` vs poll), show **“Connected (realtime)”** vs **“Connected (standard)”** on the Host PC strip — never swap that for server Online/Offline.

### Example (correct)

```
Play list:  AdAstra  ● OFFLINE   ← Minecraft stopped; PC may be fine
Server page Host PC: ● Gaming laptop — Connected (realtime)
                     [ START ]   ← enabled; do NOT show PC offline banner
```

### Example (wrong — do not ship)

```
Play list:  AdAstra  ○ OFFLINE
Server page: “This PC is offline”   ← lie when GET /v1/agents/{anode} is online
             [ START disabled ]
```

---

## IDs — quiet, not hidden

CultForge is ID-native (`srv_`, `bld_`, `anode_`, `awlk_`, `upsrv_`). The launcher should **use them in API calls** and **show them in the UI** without turning the product into a database browser.

### Hierarchy

| Layer | What the user sees first |
|-------|---------------------------|
| **Primary** | Server name, build name, Online/Offline, join address |
| **Secondary** | Loader · MC version · scope badge |
| **Tertiary** | Short ID line — small, muted monospace, one tap to copy |
| **Details** | Collapsible **Server details** block — full IDs for support |

### Where to show IDs (and how)

| Place | Show | Style |
|-------|------|--------|
| Play list row | `srv_…` under the name | 11px mono, muted, `[copy]` |
| Server page header | `srv_…` under subtitle | same |
| Server page **Details** (collapsed) | `srv_`, `bld_`, `awlk_`, hosting `anode_` | labeled rows, copy each |
| Discover card footer | `bld_…` or `ubld_…` | tiny mono under Install |
| My PCs row | `anode_…` under PC nickname | tiny mono |
| Host wizard confirm | IDs in fine print only | “Server srv_… on anode_…” |

### Rules

1. **Never drop IDs** — engineers and guild admins need them for Discord/support; always copyable somewhere on the server page.
2. **Never lead with IDs** — if the name is “AdAstra”, that’s the H1; `srv_1hAMv7Fw…` is the whisper under it.
3. **Truncate middle** for long IDs in list rows (`srv_1hAMv7…4n5DWA`); full value in Details + copy payload.
4. **No ID soup** — one tertiary line per card max; full table only in collapsed Details.
5. **Tokens stay hidden** — never show `cagt_`, JWT, or sidecar secrets (IDs yes, credentials no).

### Example tertiary line

```
AdAstra                                    [Guild]
Valthera · Forge 1.20.1
srv_1hAMv7Fw…4n5DWA  ·  bld_R0MmMc9…  [copy]
```

## Where control lives (one picture)

```
Launcher (you)     →  CultForge API  →  cf-agent on someone's PC  →  Minecraft
   friendly UI          queue              runs the server
```

- **Launcher:** bind servers, Start/Stop, settings, join address, read players/logs.
- **cf-agent:** install files, Java, mods, tunnel, full local admin at `127.0.0.1:8720/panel` (optional “Open full panel on this PC” link — not embedded in launcher).

---

## App map (top level)

```
┌─────────────────────────────────────────────────────────┐
│  Play          Discover        My PCs        Account    │
└─────────────────────────────────────────────────────────┘
```

| Tab | Job |
|-----|-----|
| **Play** | Servers you play on or host — guild + personal |
| **Discover** | Browse public modpacks/builds to install |
| **My PCs** | Computers running CultAgent — online/offline |
| **Account** | Login, guilds, settings |

Deep work happens on **one server page** (below). Everything else is navigation into that page.

---

## Play — server list

**Goal:** “Which world am I running?” in under 3 seconds.

```
┌──────────────────────────────────────────────────────────┐
│  Your servers                                            │
├──────────────────────────────────────────────────────────┤
│  ● AdAstra          [Guild]     ONLINE     3 / 20       │
│     Forge · 1.20.1 · Valthera                            │
│     srv_1hAMv7… · bld_R0Mm…                    [copy]    │
│     tissues-offense.tun.ply.gg                           │
│     [ Open ]  [ Copy join ]                              │
├──────────────────────────────────────────────────────────┤
│  ○ My SMP           [Personal]  OFFLINE                  │
│     Paper · 1.21.1                                       │
│     Not hosted — [ Host on my PC ]                       │
└──────────────────────────────────────────────────────────┘
```

Each row shows:

- Status dot + word (**Online** / **Offline** / **Starting…** / **Crashed**)
- **Scope badge:** Guild · Personal · (optional) Local-only
- Loader + Minecraft version + **build name** when known
- **Join address** when online (one line, monospace)
- **IDs** — one muted line (`srv_…`, optional `bld_…`), copy icon
- Primary: **Open** → server control page

Empty state: illustration + **Discover a modpack** or **Create personal server**.

---

## Server control page (core — build this first)

This is the **Aternos server page**. One scroll, no admin jargon.

### Layout (top → bottom)

```
┌─────────────────────────────────────────────────────────────┐
│  ← Back          AdAstra  [Guild]                             │
│                  Valthera · Forge 1.20.1                      │
│                  srv_1hAMv7Fw…4n5DWA                 [copy]   │
│                                                               │
│     ┌─────────────┐  ┌─────────────┐  ┌─────────────┐        │
│     │   START     │  │   RESTART   │  │    STOP     │        │
│     │  (primary)  │  │             │  │  (confirm)  │        │
│     └─────────────┘  └─────────────┘  └─────────────┘        │
│                                                               │
│  Status: ● ONLINE          Uptime: 2h 14m    Players: 3/20   │
├─────────────────────────────────────────────────────────────┤
│  JOIN                                                         │
│  ┌─────────────────────────────────────────────────────┐     │
│  │  tissues-offense.tun.ply.gg:25565          [ Copy ] │     │
│  └─────────────────────────────────────────────────────┘     │
│  LAN: 192.168.1.7:25565   ·   This PC: localhost:25565       │
├─────────────────────────────────────────────────────────────┤
│  PLAYERS                                      [ Refresh ]     │
│  Steve, Alex, Notch                          (or “No one yet”)│
├─────────────────────────────────────────────────────────────┤
│  WORLD SETTINGS                          (saved on restart) │
│  Difficulty    [ Normal ▼ ]                                   │
│  Game mode     [ Survival ▼ ]                                 │
│  Max players   [────●────] 20                                 │
│  Message (MOTD)[ A server of ice and fire____________ ]       │
│  World name    [ world ▼ ]                                    │
│  [ ] PvP   [ ] Whitelist   [ ] Allow Nether                  │
│                              [ Save settings ]                │
├─────────────────────────────────────────────────────────────┤
│  CONSOLE                                                      │
│  ┌─────────────────────────────────────────────────────┐     │
│  │ [12:01] Done (3.2s)! For help, type "help"           │     │
│  │ [12:02] Steve joined the game                         │     │
│  │ …                                                     │     │
│  └─────────────────────────────────────────────────────┘     │
│  [ Say something… ]  (optional — sends /say or op commands)   │
├─────────────────────────────────────────────────────────────┤
│  HOST PC                                                      │
│  ● Gaming laptop — Online · CPU 12% · RAM 8/16 GB             │
│     anode_abc123…  ·  awlk_xyz789…                   [copy]   │
│  [ Open full panel on this PC ]  (only if user is on that PC)   │
│                                                               │
│  ▼ Server details  (collapsed — expand for full IDs)            │
│     Server   srv_1hAMv7FwYhYbXXt_4n5DWA              [copy]   │
│     Build    bld_R0MmMc9w1ozN7x3LH0o5bA              [copy]   │
│     Workload awlk_VgrJJPIHrFopsTjbXXoHjA             [copy]   │
│     Agent    anode_…                                 [copy]   │
└─────────────────────────────────────────────────────────────┘
```

### Button behavior (user-facing)

| Control | When shown | User feedback |
|---------|------------|---------------|
| **Start** | Offline / stopped | → “Starting…” disable button until online or failed |
| **Stop** | Online / starting | Confirm dialog → “Stopping…” |
| **Restart** | Online | Confirm → brief “Restarting…” |
| **Copy join** | Address known | Toast “Copied!” |
| **Save settings** | Always | “Saved — applies on next start” if server running |
| **Refresh players** | Online | Spinner on row only |

### Status strip (always visible under buttons)

| Show | Source (conceptual) |
|------|---------------------|
| Online / Offline / Starting / Crashed | Server runtime state |
| Player count | Runtime or last console `list` |
| Uptime | Agent status |
| Mod count (optional chip) | Workload / build metadata |

### When the PC is unreachable

**Only** when `GET /v1/agents/{anode}` (or telemetry) shows the agent is **not** online — not when the Minecraft server is simply stopped.

Replace Start with a calm banner:

> **This PC is offline**  
> Open CultForge Agent on that computer and keep it running.

No stack traces. Optional: **Which PC?** → My PCs tab.

If the PC **is** connected but the world is stopped, keep Start enabled and show server status **Offline** — two different pills, two different meanings.

### When the server isn’t hosted yet

> **Not hosted on a PC yet**  
> [ Host on my PC ] → pick online agent → bind flow

### When files aren’t installed

Before first Start:

> **Install required** — Valthera (689 MB, 177 mods)  
> [ Install on PC ] → progress bar from command result  
> Then Start unlocks.

---

## Host on my PC (binding)

Short wizard — not a settings screen.

1. **Pick a computer** — only agents that are online (green dot).
2. **Confirm** — “Host **AdAstra** on **Gaming laptop**?”
3. **Done** — return to server page; Start enabled when install complete.

Copy:

- **Host** / **Stop hosting** (unbind) — never “create binding” or `cagb_`.

Guild agents only see guild servers; personal agents only personal servers (same exclusive rule as today — enforce in API, hide wrong targets in UI).

---

## Discover (catalog)

Fortnite-style browse — cards, not tables.

```
[ Search modpacks…                    ]  [ Fabric ] [ Forge ] [ 1.20 ]

┌─────────────┐  ┌─────────────┐  ┌─────────────┐
│  [art]      │  │  [art]      │  │  [art]      │
│  Valthera   │  │  Cobblemon  │  │  …          │
│  Forge 1.20 │  │  Fabric …   │  │             │
│  bld_R0Mm…  │  │  bld_abc…   │  │             │
│  [ Install ]│  │  [ Install ]│  │             │
└─────────────┘  └─────────────┘  └─────────────┘
```

Install flow: pick build → pick **online PC** → install progress → open server page.

---

## My PCs

List CultAgent nodes the user owns.

```
Gaming laptop     ● Online     Last seen: now
  anode_abc123…                           [copy]
  Hosting: AdAstra
  [ Open server ]

Old desktop       ○ Offline    Last seen: 2 days ago
  anode_def456…                           [copy]
  [ Learn how to start agent ]
```

Optional: download / login help links. No **token** display (`cagt_`, JWT).

---

## Controls checklist — everything the launcher must expose

These are the **required** remote controls (v1). Each maps to one agent action behind the scenes.

### Server power

| UI | Required |
|----|----------|
| Start | ✓ |
| Stop (with confirm) | ✓ |
| Restart (with confirm) | ✓ |
| Live status (online/offline/crashed/starting) | ✓ |

### Join

| UI | Required |
|----|----------|
| Primary join address + copy | ✓ |
| Secondary: LAN / localhost hints when API provides | ✓ |

### Players

| UI | Required |
|----|----------|
| Player list or count | ✓ |
| Refresh (manual; no 1s polling) | ✓ |

### World settings (forms — not raw files)

| UI | Required |
|----|----------|
| Difficulty | ✓ |
| Game mode | ✓ |
| Max players | ✓ |
| MOTD | ✓ |
| World name (level) | ✓ |
| Common toggles: PvP, whitelist, nether, etc. | ✓ (as many as `server.config.read` exposes in structured form) |
| Save with confirm | ✓ |

### Console

| UI | Required |
|----|----------|
| Scrollable log (auto-refresh ~15–20s or API snapshot) | ✓ |
| Optional single-line “send command” for admins | ✓ (secondary; not primary control) |

### Host / install

| UI | Required |
|----|----------|
| Bind server to PC | ✓ |
| Unbind / stop hosting | ✓ |
| Install modpack/build on PC | ✓ |
| Install progress / failed message in plain English | ✓ |

### Host health (lightweight)

| UI | Required |
|----|----------|
| PC online/offline | ✓ |
| Optional: CPU / RAM bars for the agent PC | ✓ (on demand, not spammy) |

---

## Explicitly NOT in the launcher (local panel only)

Keep a link **“Open full panel on this PC”** when the user is on the hosting machine. Do not rebuild these remotely:

| Feature | Why |
|---------|-----|
| File browser | Local loopback only |
| JVM / memory tuner | Local only |
| Mod install/remove/search | Local only |
| Backups restore | Local only |
| Playit secret / tunnel setup wizards | Agent + local panel |
| Server delete / wipe disk | Local only |

Guild members use the launcher to **play and basic ops**; owners use the local panel for surgery.

---

## Polling & speed (UX rules)

**Default assumption on production (`api.cultforge.com`):** agent WebSocket is advertised; cf-agent connects when `realtime_enabled` (default). Treat realtime as the normal path.

| Situation | What the user sees |
|-----------|-------------------|
| Command sent, agent on WS (normal) | Button spinner **1–3s**, then status updates |
| Command sent, poll-only fallback | “Starting… may take up to 15 seconds” — **only** when you know WS is down |
| Agent truly offline (API) | **“PC offline”** on Host PC / My PCs — don’t spin forever on Start |
| Server stopped, agent online | **“Offline”** on server pill + **Start** enabled — **not** PC offline |
| Console | Prefer `GET /v1/agents/{anode}/telemetry` → `consoles[]`; refresh **5–15s**; append by `seq`. Fallback enqueue `server.console.read` only if empty |
| Activity (agent HUD) | Same telemetry → `activity.lines` on Host PC / My PCs — match `cf-agent run` feed |

Never hammer the API with status/console commands every second — the agent will throttle (429) and the PC can **look** offline even when it isn’t. That is a launcher bug, not user error.

Never show **PC offline** just because status didn’t update within 15s while the agent heartbeat is fresh.

### Activity + console from telemetry (Phase 1)

On the **server page** (Host PC strip + Console block) and **My PCs**:

1. Poll `GET /v1/agents/{anode}/telemetry` every **5–15s** (not 1s).
2. Render `activity.lines` as a short feed (timestamp + kind mark + text) — same content as the agent Activity HUD.
3. Render `consoles` entry matching this server’s `server_id` as the console log; track `seq` so you append, don’t flash-replace blindly.
4. Do **not** enqueue `server.console.read` on a timer while telemetry consoles are present.

If activity/consoles are missing from the GET response, the API filter may be stripping them — see API handoff in `todo/API_LAUNCHER.md`. Until fixed, fall back to rare `server.console.read` for console only.

---

## Scope badges (guild / personal / local)

Show on **Play list** and **server page header**:

| Badge | Meaning |
|-------|---------|
| **Guild** | Guild cloud server, bound to a guild agent |
| **Personal** | Your own `upsrv_` server |
| **Local** | Only on this PC, not cloud-linked (rare in launcher) |

Colors: guild = purple, personal = blue, local = gray. Badge is human-readable; pair with `srv_` / `upsrv_` on the tertiary ID line, not inside the badge text.

---

## ID reference (for labels in Details)

| Prefix | User-facing label in Details |
|--------|------------------------------|
| `srv_` | Server |
| `upsrv_` | Personal server |
| `bld_` / `ubld_` | Build |
| `anode_` | Agent / PC |
| `awlk_` | Workload (hosting slot) |
| `cagb_` | Binding (Host PC section, optional) |
| `gld_` | Guild (guild server pages only) |

Use these labels in the collapsed Details block — not as navigation titles.

## Screen priority (build order)

1. **Server control page** — Start/Stop, join, status, console tail  
2. **Play list** — rows + badges + open  
3. **Host on my PC** — bind wizard  
4. **World settings** — form block on server page  
5. **My PCs** — agent online state  
6. **Discover** — catalog + install  
7. **Players** — list/count  

---

## For engineers (hidden wiring)

| User control | Agent action | Notes |
|--------------|--------------|-------|
| Start | `server.start` | Include accept EULA |
| Stop | `server.stop` | UI confirm + payload confirm |
| Restart | `server.restart` | Confirm |
| Status refresh | Prefer API GET runtime; else `server.status` | Rare |
| Console log | Prefer telemetry `consoles[]`; else API snapshot; else `server.console.read` | 5–15s cadence |
| Activity feed | Prefer telemetry `activity.lines` | Host PC / My PCs |
| Send console line | `server.console.execute` | Minecraft lines only |
| Load settings | `server.config.read` | Populate form |
| Save settings | `server.config.update` | Confirm |
| Install build | `builds.provision` | Confirm; show progress |
| PC metrics | `node.metrics` | On demand |
| Bind / unbind | User JWT bind routes | Not an agent command |

Full JSON shapes: [`LAUNCHER_AGENT_CONTRACT.md`](./LAUNCHER_AGENT_CONTRACT.md).

---

## Success criteria

The launcher UI is done when a non-technical player can:

1. See their guild server and whether it’s **online**
2. **Start** or **stop** it without knowing what an agent is
3. **Copy join** and play
4. Change **difficulty / gamemode / MOTD** without opening a terminal
5. Skim the **console** when something breaks
6. **Host** a catalog server on their PC in a guided flow
7. **Copy a server ID** from Details when asking for help on Discord — without hunting in devtools

It should feel like Aternos with a **small mono footer** on each card, not like a JSON debugger.

---

## Live API capabilities (manifest)

Source of truth: `GET https://api.cultforge.com/manifest.json` (or `cf-agent cloud-manifest` locally).

**Checked:** `v2026.08.22-lin` (2026-08-22)

| Capability | Live value | Launcher impact |
|------------|------------|-----------------|
| Agent WebSocket | **`/v1/agent/ws`** (in manifest `&` metadata: `realtime`, `agent_ws`, `capabilities`) | cf-agent auto-connects; commands push in ~1s after enqueue |
| HTTPS poll fallback | `/v1/agent/poll` | Always available; ~15s cadence when WS absent |
| Command enqueue | `POST /v1/agents/{anode}/commands` | Start/Stop/Restart |
| Agent online / telemetry | `GET /v1/agents/{anode}`, `GET …/telemetry` | **PC connected** — do not guess offline |
| Guild runtime | `GET /v1/guilds/{gld}/agents/runtime` | Server online, players, join address |
| Required agent routes | All `REQUIRED_AGENT_ROUTES` present | cf-agent health OK |

**Note:** WS path is advertised in manifest **`&`** metadata even when it is not duplicated in the flat route table. cf-agent discovers it via `discover_agent_ws()` — launcher should assume **realtime is production-ready**, not “coming soon”.

Re-check manifest after API deploys; do not hard-code “poll only” UX in the launcher.
