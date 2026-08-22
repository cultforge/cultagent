"""Help text for Minecraft server.properties keys (short hover + markdown full)."""

from __future__ import annotations

from typing import Any

# help: one-line hover tip.
# help_full: markdown body (shown on click; UI prepends current value).
# options_help: optional map of value -> what that choice does.
PROPERTY_HELP: dict[str, dict[str, Any]] = {
    "motd": {
        "help": "Server list subtitle shown under the server name.",
        "help_full": """## Message of the day (MOTD)

Shown in the multiplayer server list under the server name.

### Effects
- Players see this **before** joining.
- Supports legacy `§` color/formatting codes.
- Very long MOTDs (roughly **over 59 characters**) can make some clients show a communication error.

### Tips
- Keep it short and readable.
- Restart is **not** required for MOTD on most setups — reconnect the server list to refresh.
""",
    },
    "difficulty": {
        "help": "World difficulty (damage, hunger, mobs).",
        "options_help": {
            "peaceful": "No hostile mobs; hunger does not deplete health.",
            "easy": "Weaker mobs, milder hunger damage.",
            "normal": "Standard survival challenge.",
            "hard": "Stronger mobs; hunger can kill; more punishing.",
        },
        "help_full": """## Difficulty

Controls combat threat, hunger behavior, and related survival pressure.

### What changes
- **Hostile mob damage** and armor effectiveness feel
- **Hunger** drain and whether starvation can kill
- Some mob behaviors (e.g. spiders / zombies on harder settings)

### Options
- **peaceful** — No hostiles; hunger won't kill.
- **easy** — Softer mobs and hunger.
- **normal** — Default balanced survival.
- **hard** — Highest pressure; starvation can kill.

### Notes
- Can also be changed in-game with `/difficulty`.
- Does **not** by itself enable Hardcore (see `hardcore`).
""",
    },
    "gamemode": {
        "help": "Default mode for new players.",
        "options_help": {
            "survival": "Mine, craft, fight — health and hunger matter.",
            "creative": "Fly, infinite blocks, instant break.",
            "adventure": "Survival-like but limited block breaking/placing.",
            "spectator": "Fly through blocks; cannot interact.",
        },
        "help_full": """## Default gamemode

Mode assigned to players when they join as new (and when `force-gamemode` is on).

### Options
- **survival** — Standard play.
- **creative** — Build freely with flight and infinite items.
- **adventure** — Map/minigame mode; block interaction restricted.
- **spectator** — Observe only.

### Interaction with other settings
- If **force-gamemode=true**, everyone is reset to this mode on every join.
- If **force-gamemode=false**, returning players keep the mode they left in.
""",
    },
    "hardcore": {
        "help": "Hardcore worlds (spectator on death).",
        "options_help": {
            "true": "Death → spectator (hardcore rules).",
            "false": "Normal respawn rules.",
        },
        "help_full": """## Hardcore

### Effects when **true**
- On death, the player becomes a **spectator**.
- Intended as a one-life / high-stakes world style.

### Caveats
- Best set when the world is **first created**.
- Flipping this on an existing world may not fully convert everything the way a fresh hardcore world would.

### Related
- Often paired with **difficulty=hard**, but they are separate settings.
""",
    },
    "pvp": {
        "help": "Allow players to damage each other.",
        "options_help": {
            "true": "Players can hurt other players.",
            "false": "Player-vs-player damage disabled.",
        },
        "help_full": """## PvP

### Effects
- **true** — Players can deal damage to each other (melee, projectiles, etc.).
- **false** — Direct player damage is blocked (friendly servers / co-op builds).

### Notes
- On some newer vanilla versions this overlaps with the `pvp` **game rule**.
- Environmental damage (lava, fall) is unaffected.
""",
    },
    "force-gamemode": {
        "help": "Always set players to the default gamemode on join.",
        "options_help": {
            "true": "Every join resets to `gamemode`.",
            "false": "Players keep the mode they left in.",
        },
        "help_full": """## Force gamemode

### Effects
- **true** — On join, set the player to the server `gamemode` value.
- **false** — Remember and restore each player's previous mode.

### When to use
- Mini-games / hubs that must always start in adventure/survival.
- Leave **false** for normal survival servers where ops switch modes.
""",
    },
    "spawn-monsters": {
        "help": "Allow hostile mob spawning.",
        "options_help": {
            "true": "Hostiles can spawn naturally.",
            "false": "Natural hostile spawning disabled.",
        },
        "help_full": """## Spawn monsters

Controls natural **hostile** mob spawning (zombies, creepers, etc.).

### Effects
- **false** — Much safer nights; farms that need hostiles break.
- **true** — Normal survival threat.

Spawners / commands may still create mobs depending on version and rules.
""",
    },
    "spawn-animals": {
        "help": "Allow passive animal spawning.",
        "options_help": {
            "true": "Cows, pigs, sheep, etc. can spawn.",
            "false": "Natural animal spawning off.",
        },
        "help_full": """## Spawn animals

### Effects
- **true** — Passive animals spawn in valid biomes/light.
- **false** — No natural animal spawns (breeding existing animals may still work).
""",
    },
    "spawn-npcs": {
        "help": "Allow villager / NPC spawning.",
        "options_help": {
            "true": "Villagers / NPCs can spawn.",
            "false": "Natural NPC spawning disabled.",
        },
        "help_full": """## Spawn NPCs

Affects natural spawning of villagers and similar NPCs.

Useful for controlled RPG maps; disable if you only want hand-placed NPCs.
""",
    },
    "allow-flight": {
        "help": "Allow survival flight mods without kick.",
        "options_help": {
            "true": "Fly mods allowed in Survival.",
            "false": "Long airborne Survival players get kicked (anti-fly).",
        },
        "help_full": """## Allow flight

### Effects
- **false** — Server kicks Survival players who stay airborne too long (anti-cheat style).
- **true** — Permits fly mods in Survival.

### Important
- **Creative flight is unaffected.**
- Enabling this makes griefing with fly hacks easier — only enable for trusted players/modpacks that need it.
""",
    },
    "level-name": {
        "help": "World folder name to load.",
        "help_full": """## Active world (`level-name`)

Directory under the server root used as the **overworld**.

### Effects of changing it
- Next start loads (or generates) that folder.
- Old world stays on disk unless you delete it.
- Nether/End usually live as dimensions under that world (or sibling folders on older layouts).

### Requirements
- **Restart required** after changing.
- Prefer simple folder names (no `\\` `/` weird characters).
""",
    },
    "level-seed": {
        "help": "World seed (blank = random).",
        "help_full": """## Level seed

### Effects
- Used only when **generating a new world**.
- Blank → random seed.
- Changing seed on an **existing** world does nothing until you use a new `level-name`.
""",
    },
    "level-type": {
        "help": "World generation preset.",
        "options_help": {
            "minecraft:normal": "Standard terrain.",
            "minecraft:flat": "Superflat (customize via generator-settings).",
            "minecraft:large_biomes": "Same as normal with huge biomes.",
            "minecraft:amplified": "Extreme height variation.",
            "default": "Legacy alias for normal.",
            "flat": "Legacy alias for flat.",
        },
        "help_full": """## Level type

Worldgen preset for **new** worlds only.

### Common options
- **minecraft:normal** — Hills, oceans, caves — default survival.
- **minecraft:flat** — Flat world; use `generator-settings` for layers.
- **minecraft:large_biomes** — Bigger biomes.
- **minecraft:amplified** — Dramatic vertical terrain.

Changing this mid-world does not rebuild already generated chunks.
""",
    },
    "generate-structures": {
        "help": "Generate villages, strongholds, etc.",
        "options_help": {
            "true": "Structures generate in new chunks.",
            "false": "Most structures skipped (dungeons may still appear).",
        },
        "help_full": """## Generate structures

### Effects
- **true** — Villages, strongholds, monuments, etc. can generate.
- **false** — Most structures skipped in newly generated chunks.

Dungeons may still appear even when false.
""",
    },
    "max-world-size": {
        "help": "World border radius from center (blocks).",
        "help_full": """## Max world size

Hard ceiling for how far the **world border** can be set from center (1–29999984).

### Effects
- Protects against absurd border sizes.
- Setting higher than the engine allows has no extra effect.
""",
    },
    "spawn-protection": {
        "help": "Blocks non-ops from building near spawn.",
        "help_full": """## Spawn protection

Radius-style protection around world spawn for non-ops.

### How size works
- Value `x` protects a square of side **2x+1** centered on spawn.
- **0** disables protection.
- If there are **no ops**, protection is effectively disabled.

### Effects
- Non-ops cannot place/break in the protected area.
- Ops can still build.
""",
    },
    "allow-nether": {
        "type": "bool",
        "label": "Allow Nether",
        "help": "Allow travel to the Nether.",
        "options_help": {
            "true": "Nether portals work.",
            "false": "Players cannot enter the Nether via portals.",
        },
        "help_full": """## Allow Nether

### Effects
- **true** — Portals take players to the Nether.
- **false** — Portal travel blocked.

### Version note
- Newer vanilla may prefer the `allowEnteringNetherUsingPortals` game rule.
- Forge **1.20.1** servers commonly still honor this property.
""",
    },
    "enable-command-block": {
        "type": "bool",
        "label": "Enable command blocks",
        "help": "Allow command blocks to run.",
        "options_help": {
            "true": "Command blocks execute.",
            "false": "Command blocks do nothing.",
        },
        "help_full": """## Enable command blocks

### Effects
- **true** — Impulse/chain/repeating command blocks run.
- **false** — Placed command blocks are inert.

### Safety
- Leave **false** unless you need adventure maps / automation.
- Misconfigured command blocks can lag or grief a world.
""",
    },
    "server-port": {
        "help": "TCP port players connect to.",
        "help_full": """## Server port

TCP listen port (default **25565**).

### Effects
- Players must use this port (or your tunnel/proxy must forward to it).
- Must be free on the host; conflict = bind failure on start.
""",
    },
    "server-ip": {
        "help": "Bind address (blank = all interfaces).",
        "help_full": """## Bind IP

### Effects
- **Blank** — Listen on all interfaces (usual / recommended).
- Specific IP — Bind only that NIC/address.

Leave blank unless you know you need a restricted bind.
""",
    },
    "online-mode": {
        "help": "Verify Microsoft / Mojang accounts.",
        "options_help": {
            "true": "Only legitimate accounts (recommended).",
            "false": "Offline/cracked — any name can join.",
        },
        "help_full": """## Online mode

### Effects
- **true** — Auth with Microsoft/Mojang. Required for public internet servers.
- **false** — No auth (“cracked”). Anyone can impersonate names.

### Risks of **false**
- Impersonation, ban evasion, insecure ops.
- Only for LAN / fully trusted offline setups.
""",
    },
    "network-compression-threshold": {
        "help": "Compress packets larger than this (bytes).",
        "help_full": """## Network compression threshold

### Values
- **-1** — Disable compression.
- **0** — Compress everything.
- **256** (default) — Compress packets ≥ 256 bytes.

### Effects
- Lower → more CPU, sometimes less bandwidth.
- Very low values can **hurt** performance (overhead > savings).
""",
    },
    "prevent-proxy-connections": {
        "help": "Kick if ISP/AS mismatches Mojang auth.",
        "options_help": {
            "true": "Stricter anti-proxy checks.",
            "false": "Allow VPN/proxy-ish paths (default).",
        },
        "help_full": """## Prevent proxy connections

Compares connecting network metadata with Mojang auth data.

### Effects
- **true** — May block VPNs/proxies; can false-positive odd ISPs.
- **false** — Normal connections allowed.
""",
    },
    "enable-status": {
        "help": "Reply to server-list pings.",
        "options_help": {
            "true": "Server appears online in multiplayer list.",
            "false": "Looks offline but may still accept joins.",
        },
        "help_full": """## Enable status

### Effects
- **true** — MOTD/player count respond to pings.
- **false** — List shows offline-ish; direct connect can still work.
""",
    },
    "enable-query": {
        "help": "Enable GameSpy4 query protocol.",
        "options_help": {
            "true": "External tools can query the server (UDP).",
            "false": "Query disabled.",
        },
        "help_full": """## Enable query

Turns on the query protocol used by some server lists/tools.

Uses `query.port` (UDP). Leave off unless a tool needs it.
""",
    },
    "enable-rcon": {
        "help": "Remote console over TCP.",
        "options_help": {
            "true": "RCON listener enabled (set password!).",
            "false": "RCON off (safer default).",
        },
        "help_full": """## Enable RCON

Remote console protocol — **not encrypted**.

### Effects / risks
- Exposes console commands over TCP (`rcon.port`).
- Password travels in cleartext — firewall to localhost / trusted LAN only.
- Blank `rcon.password` prevents RCON from starting even if enabled.
""",
    },
    "view-distance": {
        "help": "Chunks sent to each player (radius).",
        "help_full": """## View distance

How many chunks of terrain the server sends around each player.

### Effects
- **Higher** — prettier horizon, more RAM/CPU/network.
- **Lower** — better TPS on heavy modpacks.

Typical comfortable range: **6–12** depending on hardware and mods.
""",
    },
    "simulation-distance": {
        "help": "Chunks where entities are ticked.",
        "help_full": """## Simulation distance

Radius where entities/redstone-like simulation stays active.

### Effects
- Outside this radius, entities are **not** ticked (farms pause).
- Lowering this is one of the best lag fixes for busy servers.
""",
    },
    "max-tick-time": {
        "help": "Watchdog kill threshold (ms).",
        "help_full": """## Max tick time

Watchdog: if a single tick takes longer than this many ms, the server is force-stopped.

### Values
- **60000** — default (60s).
- **-1** — disable watchdog (can hang forever on deadlock).

Useful for crash-loop diagnosis; risky to disable permanently.
""",
    },
    "entity-broadcast-range-percentage": {
        "help": "How far entities are sent to clients.",
        "help_full": """## Entity broadcast range %

Scales how far entities are networked to players.

### Effects
- **100** — normal.
- **50** — entities appear from closer only (less network/CPU).
- Above 100 — farther tracking (heavier).
""",
    },
    "max-players": {
        "help": "Maximum concurrent players.",
        "help_full": """## Max players

Hard cap on simultaneous connections.

### Effects
- Extra join attempts are rejected when full.
- Extremely large values can break the client player list UI.
""",
    },
    "white-list": {
        "help": "Only allow whitelisted players.",
        "options_help": {
            "true": "Only whitelist.json (and ops) can join.",
            "false": "Anyone who passes online-mode can join.",
        },
        "help_full": """## Whitelist enabled

### Effects
- **true** — Non-listed players cannot connect (ops are always allowed).
- **false** — Open to authenticated players (subject to online-mode).

Pair with **enforce-whitelist** to kick people removed while online.
""",
    },
    "enforce-whitelist": {
        "help": "Kick players removed from the whitelist.",
        "options_help": {
            "true": "Reload kicks non-whitelisted online players.",
            "false": "Already-online players may stay until reconnect.",
        },
        "help_full": """## Enforce whitelist

### Effects
- With whitelist on + enforce on: after reload, anyone not listed is kicked.
- Without enforce: removing someone may not kick them until they reconnect.
""",
    },
    "op-permission-level": {
        "help": "Default OP power (1–4).",
        "options_help": {
            "1": "Moderation basics.",
            "2": "Game mechanics / command blocks-ish.",
            "3": "Player management (kick/ban-ish).",
            "4": "Full server management including stop.",
        },
        "help_full": """## OP permission level

Default permission level granted by `/op`.

### Levels (summary)
1. Bypass spawn protection moderation basics  
2. Command blocks / game mechanics  
3. Player management  
4. Server management (`stop`, etc.)

Higher = more power — use the lowest that still works.
""",
    },
    "function-permission-level": {
        "help": "Permission level for datapack functions.",
        "help_full": """## Function permission level

Permission level used when **datapack functions** run commands (1–4).

Higher lets functions run more privileged commands — keep tight on public servers.
""",
    },
    "hide-online-players": {
        "help": "Hide player list in status pings.",
        "options_help": {
            "true": "Status/query won't reveal who is online.",
            "false": "Player sample may appear in server list.",
        },
        "help_full": """## Hide online players

### Effects
- **true** — Privacy: multiplayer list/query won't show names.
- **false** — Clients may see a sample of online players.
""",
    },
    "accepts-transfers": {
        "type": "bool",
        "label": "Accept transfers",
        "help": "Allow incoming transfer packets.",
        "options_help": {
            "true": "Server can approve transfers from other servers.",
            "false": "Transfer packets disconnect the player.",
        },
        "help_full": """## Accepts transfers

Controls whether transfer packets from other servers are accepted.

Leave **false** unless you run a multi-server transfer network.
""",
    },
    "broadcast-console-to-ops": {
        "type": "bool",
        "label": "Broadcast console to ops",
        "help": "Send console output to online ops.",
        "options_help": {
            "true": "Ops see console command output in-game.",
            "false": "Console output stays on the server console.",
        },
        "help_full": """## Broadcast console to ops

When **true**, output from console-run commands is also shown to online operators.
""",
    },
    "broadcast-rcon-to-ops": {
        "type": "bool",
        "label": "Broadcast RCON to ops",
        "help": "Send RCON output to online ops.",
        "options_help": {
            "true": "Ops see RCON command output.",
            "false": "RCON output stays on the RCON session.",
        },
        "help_full": """## Broadcast RCON to ops

When **true**, RCON command output is mirrored to online operators.
""",
    },
    "bug-report-link": {
        "type": "text",
        "label": "Bug report link",
        "help": "URL shown as the bug-report server link.",
        "help_full": """## Bug report link

Optional URL sent to clients as a bug-report link. Empty disables it.
""",
    },
    "enable-jmx-monitoring": {
        "type": "bool",
        "label": "Enable JMX monitoring",
        "help": "Expose tick-time JMX MBeans.",
        "options_help": {
            "true": "Publish tick timing MBeans (needs JVM JMX flags for remote).",
            "false": "No JMX tick beans.",
        },
        "help_full": """## Enable JMX monitoring

Exposes `averageTickTime` / `tickTimes` MBeans for profilers.

Remote JMX also needs JVM management flags — do not expose publicly.
""",
    },
    "enforce-secure-profile": {
        "type": "bool",
        "label": "Enforce secure profile",
        "help": "Require Mojang-signed player keys.",
        "options_help": {
            "true": "Require signed keys; enables chat reporting.",
            "false": "Unsigned chat; clients may warn on join.",
        },
        "help_full": """## Enforce secure profile

### Effects
- **true** — Players need Mojang-signed keys. Enables modern chat reporting.
- **false** — Chat stays unsigned; some clients warn when connecting.

Recommended **true** for public authenticated servers.
""",
    },
    "generator-settings": {
        "type": "text",
        "label": "Generator settings",
        "help": "Extra worldgen JSON (e.g. flat).",
        "help_full": """## Generator settings

JSON/blob consumed by certain `level-type`s (especially **flat**).

Usually `{}` for normal worlds. Only matters when generating a new world.
""",
    },
    "initial-disabled-packs": {
        "type": "text",
        "label": "Initial disabled packs",
        "help": "Datapacks to leave off on new worlds.",
        "help_full": """## Initial disabled packs

Comma-separated datapack IDs that should **not** auto-enable on first world create.
""",
    },
    "initial-enabled-packs": {
        "type": "text",
        "label": "Initial enabled packs",
        "help": "Datapacks enabled on new worlds.",
        "help_full": """## Initial enabled packs

Comma-separated datapacks enabled for new worlds (default `vanilla`).

Feature packs must be listed explicitly.
""",
    },
    "log-ips": {
        "type": "bool",
        "label": "Log IP addresses",
        "help": "Show client IPs in console/logs.",
        "options_help": {
            "true": "Connection logs include IPs.",
            "false": "IPs omitted (more private logs).",
        },
        "help_full": """## Log IPs

### Effects
- **true** — Join/leave style messages include addresses.
- **false** — Better privacy when sharing logs.
""",
    },
    "max-chained-neighbor-updates": {
        "type": "int",
        "label": "Max chained neighbor updates",
        "help": "Limit consecutive block neighbor updates.",
        "help_full": """## Max chained neighbor updates

Caps how far a chain of block neighbor updates can go (redstone storms, etc.).

Negative values disable the limit. Lower values can prevent freezes from pathological contraptions.
""",
    },
    "player-idle-timeout": {
        "type": "int",
        "label": "Player idle timeout (min)",
        "help": "Kick idle players after N minutes.",
        "help_full": """## Player idle timeout

Minutes of idling before kick. **0** = never.

Movement, chat, inventory actions reset the timer.
""",
    },
    "query.port": {
        "type": "int",
        "label": "Query port",
        "help": "UDP port for enable-query.",
        "help_full": """## Query port

UDP port used when `enable-query=true` (default 25565).
""",
    },
    "rate-limit": {
        "type": "int",
        "label": "Packet rate limit",
        "help": "Max packets before kick (0 = off).",
        "help_full": """## Rate limit

Maximum packets a player can send before kick. **0** disables.

Helps against some packet spam; tune carefully to avoid false kicks.
""",
    },
    "rcon.password": {
        "type": "text",
        "label": "RCON password",
        "help": "Password for remote console.",
        "help_full": """## RCON password

Required if RCON is enabled. Blank password blocks RCON start as a safeguard.

Treat like a root password — never commit it or share logs containing it.
""",
    },
    "rcon.port": {
        "type": "int",
        "label": "RCON port",
        "help": "TCP port for RCON.",
        "help_full": """## RCON port

TCP port for RCON (default **25575**). Firewall tightly; traffic is unencrypted.
""",
    },
    "require-resource-pack": {
        "type": "bool",
        "label": "Require resource pack",
        "help": "Kick players who decline the pack.",
        "options_help": {
            "true": "Must accept the server pack to play.",
            "false": "Pack is optional.",
        },
        "help_full": """## Require resource pack

When **true** (and a pack URL is set), declining the download disconnects the player.
""",
    },
    "resource-pack": {
        "type": "text",
        "label": "Resource pack URL",
        "help": "Direct download URL for the pack.",
        "help_full": """## Resource pack URL

Direct HTTP(S) URL for the server resource pack. Empty disables the prompt.

Pair with `resource-pack-sha1` for integrity checks. Packs have a size limit (~250 MiB classically).
""",
    },
    "resource-pack-prompt": {
        "type": "text",
        "label": "Resource pack prompt",
        "help": "Custom message on the pack prompt.",
        "help_full": """## Resource pack prompt

Custom chat-component JSON shown when requiring a pack. Blank uses the default message.
""",
    },
    "resource-pack-sha1": {
        "type": "text",
        "label": "Resource pack SHA-1",
        "help": "Integrity hash for the pack.",
        "help_full": """## Resource pack SHA-1

Lowercase hex SHA-1 of the pack file. Clients verify the download against this hash.
""",
    },
    "sync-chunk-writes": {
        "type": "bool",
        "label": "Sync chunk writes",
        "help": "Flush chunks synchronously (safer, slower).",
        "options_help": {
            "true": "Safer against crash corruption; more disk wait.",
            "false": "Faster I/O; slightly higher corruption risk on hard kills.",
        },
        "help_full": """## Sync chunk writes

### Effects
- **true** — Synchronous flushes reduce post-crash corruption risk.
- **false** — Faster disk path; riskier on abrupt kills.
""",
    },
    "use-native-transport": {
        "type": "bool",
        "label": "Use native transport",
        "help": "Linux optimized networking.",
        "options_help": {
            "true": "Use optimized native transport (Linux).",
            "false": "Disable native optimizations.",
        },
        "help_full": """## Use native transport

On Linux, enables optimized packet I/O. Leave **true** unless debugging network issues.
""",
    },
    "enable-code-of-conduct": {
        "type": "bool",
        "label": "Enable code of conduct",
        "help": "Show code-of-conduct files to players.",
        "options_help": {
            "true": "Show matching language CoC on join.",
            "false": "No CoC prompt.",
        },
        "help_full": """## Enable code of conduct

When enabled, the server looks for language files under a `codeofconduct` folder and shows the matching text to players.
""",
    },
    "region-file-compression": {
        "type": "text",
        "label": "Region file compression",
        "help": "Chunk compression algorithm.",
        "options_help": {
            "deflate": "Default zlib-style compression.",
            "lz4": "Faster compression (where supported).",
            "none": "No compression (large disk use).",
        },
        "help_full": """## Region file compression

Algorithm for region chunk storage: `deflate`, `lz4`, or `none`.

Existing chunks are **not** automatically recompressed when you change this.
""",
    },
}


def help_for(key: str) -> dict[str, Any]:
    return dict(PROPERTY_HELP.get(key, {}))
