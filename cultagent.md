# CULTAGENT.md

## Purpose

This document defines the **Crafty Controller -> CultAgent overhaul**.

CultAgent is the installed cross-platform machine/server agent derived from the Crafty Controller foundation.

The objective is **not** to make a simple Crafty rebrand.

The objective is:

> Use Crafty as the proven local server-management foundation, then transform it into the machine-side execution layer of CultForge.

---

# 1. Product Identity

Proposed installed product name:

## CultForge Agent

Short name:

```text
CultAgent
```

CLI / service name can be:

```text
cf-agent
```

Possible user-facing label:

```text
CultForge Agent
```

The exact executable/service naming may be refined later.

---

# 2. Fundamental Model

CultAgent represents a physical or virtual machine inside CultForge.

```text
CultForge Account
    |
    +-- Agent / Node
          |
          +-- Server A
          +-- Server B
          +-- Server C
```

The agent is installed by the user and registers itself on behalf of the user's CultForge account.

The user should not need to create a separate Crafty account just to manage the server.

---

# 3. Core Architecture

```text
                     CULTFORGE CLOUD
                            |
                     auth.cultforge.com
                            |
                     api.cultforge.com
                            |
                     guilds.cultforge.com
                            |
                            v
                    +---------------+
                    |  CultAgent    |
                    |  Local Agent  |
                    +-------+-------+
                            |
       +--------------------+--------------------+
       |                    |                    |
  Server Manager      Configuration        Network Manager
       |                    |                    |
       |                    |                  playit.gg
       v                    v
 Minecraft / Java       local config
       |
       +-- mods
       +-- worlds
       +-- logs
       +-- backups
```

Crafty provides much of the underlying local server/process/file-management foundation.

CultForge-specific layers are added around/above that foundation.

---

# 4. Cross-Platform Requirement

CultAgent must support:

```text
Windows
Linux
  Debian / Ubuntu
  Generic Linux
macOS
  Intel
  Apple Silicon
```

Target distributions may include:

```text
Windows installer/service
.deb
generic Linux package/binary
macOS installer/application/service
```

The implementation should minimize platform-specific duplication.

---

# 5. What to Preserve from Crafty

Do not rewrite proven Crafty functionality unnecessarily.

Potentially preserve and refactor:

```text
Process management
Server lifecycle management
Console handling
Log handling
File management
Backups
Scheduling
Resource monitoring
Multiple server management
Java/runtime handling
Server configuration access
```

First understand the Crafty source and dependency boundaries.

Only replace components when required for:

- CultForge integration
- security
- architecture
- scalability
- user experience
- cross-platform packaging
- maintainability

---

# 6. What CultForge Adds

CultAgent should add:

```text
CultForge authentication
CultForge account registration
Agent/node identity
Guild association
Role-based control
Information visibility policies
Cloud telemetry
CultForge build awareness
Modrinth integration
Playit.gg integration
CultForge update model
CultForge configuration management
CultForge events
CultForge API communication
```

---

# 7. Installation / Registration Flow

Expected first-run model:

```text
1. User installs CultAgent.
2. CultAgent starts.
3. CultAgent detects that it is not registered.
4. User chooses "Connect CultForge Account".
5. User authenticates through auth.cultforge.com.
6. CultAgent receives an authorized registration flow.
7. CultAgent registers the local machine with api.cultforge.com.
8. User chooses a guild/resource context if required.
9. CultAgent receives an agent identity/credential.
10. Agent begins reporting health/status/metrics.
```

Important:

- CultAgent should not create an independent local identity universe.
- Agent credentials must be revocable.
- Registration belongs to the authenticated CultForge account.
- Any guild association must be authorized by the backend.
- The exact auth and registration protocol must follow the real backend implementation.

---

# 8. Agent Identity

Every CultAgent installation should have a unique agent/node identity.

Conceptual:

```text
node_id = cfnode_...
```

Metadata may include:

```text
node_id
owner/account id
guild id
platform
architecture
agent version
capabilities
status
last_seen
```

Do not hardcode schema names until verified against the backend.

---

# 9. Local Responsibilities

CultAgent owns machine-local operations.

Examples:

```text
Start Minecraft
Stop Minecraft
Restart Minecraft
Send console command
Read logs
Write configuration
Manage local files
Create backups
Restore backups
Install/update local content
Run/manage playit agent
Collect local metrics
Inspect Java/runtime
```

Cloud services should issue authorized instructions; CultAgent performs the actual local operation.

---

# 10. Server Management

The UI should manage multiple Minecraft server instances.

Example:

```text
Servers
  |
  +-- Frost Fall #1
  +-- Development
  +-- Event Server
```

Each server may expose:

```text
Status
Version
Loader
Players
TPS
MSPT
Console
Logs
Configuration
Mods
Resource packs
Datapacks
World
Backups
Network
```

---

# 11. Configuration Management

CultAgent should provide both:

1. Structured configuration UI.
2. Raw file editing for advanced users.

Example structured editor:

```text
Gameplay
  Difficulty
  Game Mode
  Hardcore
  Cheats

World
  Seed
  Level Type
  Structures

Network
  Server Port
  Online Mode
  Compression

Performance
  View Distance
  Simulation Distance
```

Underlying files remain the real server configuration.

Examples:

```text
server.properties
Forge configs
Mod configs
JVM arguments
Whitelist
Ops
Bans
```

---

# 12. Configuration Profiles

Support reusable configuration profiles.

Example:

```text
Profiles
  Development
  Production
  Event
  Testing
```

A profile can apply values across supported configuration systems.

Example:

```text
Frost Fall Event
  Difficulty = Hard
  View Distance = 12
  Simulation Distance = 10
  PVP = Enabled
  Keep Inventory = Disabled
```

The actual implementation should preserve safe merge/overwrite behavior and provide a clear diff before destructive changes.

## Agent CLI (implemented)

```text
cf-agent profiles [name]
cf-agent profile-capture <name> [server_id]
cf-agent profile-apply <name> [server_id] [--mode merge|replace] [--diff] [--yes]
cf-agent profile-delete <name> [--yes]
```

Panel: `/panel/profiles` (capture / preview diff / apply with confirm).
Server config tab shows structured groups + raw `server.properties`.

Commands: `config.profile.list|show|save|delete|capture|diff|apply`.

---

# 13. Modrinth Integration

Modrinth must be integrated as a content provider.

Principle:

> Modrinth is a source of content. CultForge owns the managed build definition.

Supported concepts:

```text
Mods
Resource packs
Datapacks
Shaders / other supported project types
```

Store source metadata:

```text
source = modrinth
project_id
version_id
hash/checksum
compatibility metadata
dependencies
license/origin metadata
```

## Agent CLI (implemented)

```text
cf-agent mods [server_id] [--search <query>] [--info <slug>] [--versions <slug>]
cf-agent mod-install <slug> [server_id] [--version-id] [--deps]
cf-agent mod-remove <filename> [server_id]
cf-agent mod-update [filename] --server … [--slug] [--deps]
```

Rich views by default; add `--dump-json path.json` to write the raw payload.

Install behavior:

- Filters versions by loader + Minecraft version
- Compatibility check (`server_side`, loaders, game versions, incompat flags)
- Verifies Modrinth `sha512` / `sha1` when provided
- Places files by project type (`mods/`, `resourcepacks/`, …)
- Writes `.cultagent-modrinth.json` index for update/list metadata
- `--deps` installs required Modrinth dependencies (best-effort)

Panel: server Mods tab supports search + install + remove.

---

# 14. Mod Dependency / Compatibility Handling

CultAgent should resolve or validate:

```text
Minecraft version
Loader
Mod version
Dependencies
```

Example:

```text
Minecraft 1.20.1
Forge 47.x

Mod A
  requires Mod B
  requires Mod C
```

The system should identify incompatible selections before installation when feasible.

Prefer deterministic/pinned versions over blindly installing latest content.

Implemented on Modrinth install path: refuse versions that do not match loader/MC
or mark `server_side=unsupported`; surface required deps and optionally install
them with `--deps`. CultForge build manifests remain the deterministic pin source
for guild recipes.

---

# 15. CultForge Build Integration

CultAgent should understand CultForge Builds.

Conceptual build:

```text
Build
  |
  +-- Minecraft
  +-- Loader
  +-- Mods
  +-- Resource packs
  +-- Datapacks
  +-- Shaders (where applicable)
  +-- Config
  +-- Dependencies
```

The build definition should ideally be usable by:

```text
CultForge Launcher
CultAgent
```

This enables client/server synchronization and reproducible deployment.

## Agent CLI (implemented)

```text
cf-agent builds [--q …] [--loader …] [--mc …]
cf-agent build-manifest <build_id>
cf-agent build --new --build <build_id> [--name …] [--optional] [--no-install]
cf-agent build [server_id] [--build <build_id>] [--optional]
cf-agent --clear-cache
```

Rich views by default. `build` shows a transfer progress
bar (bytes, speed, ETA) while downloading. `--clear-cache` wipes the agent
download cache under the data dir. Add `--dump-json path.json` on these (and other
Rich CLI commands) to also write the raw JSON payload to a file.

`build-manifest` shows mode, installability, file counts by kind, env/optional
flags, sha256 short hashes, unresolved entries, and compatibility notes — not a
raw JSON dump.

Panel: `/panel/builds` lists guild builds available to this agent.

## Install behavior

- Manifest modes: `resolved` | `pack` (pending/empty → not installable)
- File `kind` maps bare filenames into `mods/`, `resourcepacks/`, `datapacks/`,
  `shaderpacks/`, `config/`
- `env=client` files are skipped on servers; optional files need `--optional`
- sha256 verified when present; already-matching files are skipped
- Optional `config` map writes text/JSON into the server directory
- Pack mode can extract `_pack/*.zip` with exclude globs

Modrinth remains a **content provider** for ad-hoc mod install/remove/update —
CultForge owns the managed build definition.

---

# 16. Playit.gg Integration

Playit.gg is a first-class network integration.

Do not implement this as merely:

```text
Start playit process
```

Instead provide a network manager abstraction.

```text
Network Manager
   |
   +-- playit.gg
   +-- Direct port
   +-- future providers
```

Playit functionality should include, where supported:

```text
agent/tunnel detection
connection state
target port
public address
tunnel mapping
restart/reconnect
diagnostics
configuration
```

## Agent CLI (implemented)

```text
cf-agent network
cf-agent network-use playit|direct
cf-agent playit-setup [--force] [--no-browser]
cf-agent playit-reset
cf-agent playit-secret --file secret.txt
cf-agent playit-start
cf-agent playit-stop
cf-agent playit-logs
```

Rich status by default; `--dump-json path.json` writes the raw payload (never includes
the secret key itself).

### Flow

```text
playit-setup
   → download official playit-cloud/playit-agent **v0.17.1** (claim CLI) into <data_dir>/playit/bin/
   → run `playit claim generate` → show claim code
   → open https://playit.gg/claim/<code>
   → wait for claim exchange (or playit-claim)
playit-reset
   -> stop agent + clear playit.toml secret
playit-secret
   → store hex key as <data_dir>/playit/playit.toml  (secret_key = "…")
playit-start
   → playit API: ensure Minecraft Java tunnel → 127.0.0.1:<server port>
   → detached official CLI: playit --secret_path playit.toml -l playit.log start
   → join via *.tun.ply.gg from status / CLI
```

Claim codes come from the playit binary (`claim generate`). CultAgent prints the
code and opens [`https://playit.gg/claim/<code>`](https://playit.gg/claim/) —
not the empty claim-code form page.

Secret keys are hex strings from the claim / docker secret wizards
([claim](https://playit.gg/claim/),
[docker secret](https://playit.gg/account/setup/wizard/new-account/docker/docker-name)).
CultAgent does not mock tunnels or invent public addresses.

See `vendor/playit/README.md` for vendor/docs mapping.
```

Config (`config.yaml`):

```yaml
network:
  default_provider: "direct"   # or playit
  playit:
    enabled: false
    auto_start: false
    target_host: "127.0.0.1"
    target_port: 25565
    binary_path: ""            # optional override
```

Panel: `/panel/network` (no secrets exposed).

Secrets must follow CultForge visibility/RBAC policies — the secret key must never
be returned to unauthorized clients or the local panel JSON.

Cross-platform notes (see [playit.gg support](https://playit.gg/support/) and
`vendor/playit/README.md`):

```text
Windows  — managed GitHub binary; winget; fix VCRUNTIME140 via support doc
Linux    — managed GitHub binary; apt PPA; systemd 24/7 guide
macOS    — no GitHub asset yet; compile from source / binary_path; download/macos
```

Example UI:

```text
Network
  Provider: playit.gg
  Status: Online
  Target: localhost:25565
  Public Endpoint: <public endpoint>
  Latency: <latency>

  [Restart Tunnel]
  [Configure]
```

---

# 17. Server Networking

CultAgent should be able to map:

```text
Minecraft server
    |
    v
local port
    |
    v
network provider
    |
    v
public endpoint
```

Do not expose management interfaces publicly unless explicitly required and secured.

---

# 18. Metrics Collection

CultAgent collects metrics locally.

System metrics:

```text
CPU
RAM
Disk
Network
OS
Architecture
```

Minecraft metrics:

```text
TPS
MSPT
Players
Entity count
Chunk information
Server state
```

Network metrics:

```text
playit state
latency
tunnel state
endpoint state
```

Telemetry must be filtered and transmitted according to CultForge backend authorization/visibility policy.

---

# 19. Real-Time Communication

CultAgent should maintain a secure outbound connection to CultForge where required.

Conceptual:

```text
CultAgent
   |
   +-- HTTPS poll (v1 default)
   +-- WebSocket / real-time channel (when API advertises it)
   |
   v
api.cultforge.com
```

## Local panel console (implemented)

The loopback panel streams Minecraft console over WebSocket:

```text
ws://127.0.0.1:8720/ws/servers/{server_id}/console
```

HTTP `GET/POST /v1/servers/{server_id}/console` remains as a fallback if the
socket drops.

## Cloud transport auto-switch (implemented)

Today `api.cultforge.com` may only expose HTTPS agent routes (`/v1/agent/poll`,
heartbeat, telemetry, …). CultAgent still runs correctly on **HTTPS poll**.

When the API later advertises an agent WebSocket, the agent **automatically
switches** without a config change (as long as `cloud.realtime_enabled` is true,
the default).

### Discovery

Source of truth: `GET {api_base}/manifest.json` (same as `cf-agent cloud-manifest`).

The agent looks for, in order:

1. Manifest `&` metadata hints, e.g.:
   - `agent_ws`, `agent_websocket`, `realtime_ws`, `ws_path`
   - `realtime.agent_ws` / `realtime.ws`
   - `capabilities.agent_websocket` (path or `true`)
2. Known candidate routes present in the route table:
   - `/v1/agent/ws`
   - `/v1/agent/realtime`
   - `/v1/agent/realtime/ws`
   - `/v1/agents/ws`
   - `/v1/agents/realtime`
3. Any other agent URI containing `ws`, `websocket`, or `realtime`

URL join: `https://api…` + `/v1/agent/ws` → `wss://api…/v1/agent/ws`.

### Behavior

```text
on start (+ every ~5 minutes)
   |
   v
discover agent WS in manifest.json?
   |
   +-- no  --> HTTPS poll (heartbeat / poll / telemetry)
   |
   +-- yes --> connect wss://… with Authorization: Bearer <agent token>
                 |
                 +-- success --> mode=websocket (commands over WS;
                 |              light HTTP heartbeat/telemetry still OK)
                 |
                 +-- fail / drop --> fall back to HTTPS poll; retry later
```

Friendly run HUD messages:

```text
Cloud linked (polling — no WebSocket yet)
Cloud WebSocket available — switching...
Connected to CultForge realtime
Realtime dropped — back to polling
```

Disable auto-upgrade with:

```yaml
cloud:
  realtime_enabled: false
```

### Expected WS message shapes (forward-compatible)

Server → agent:

```text
{ "type": "command", "id": "...", "action": "...", "payload": {} }
{ "type": "ping" }
{ "type": "desired_workloads", "desired_workloads": [ ... ] }
```

Agent → server:

```text
{ "type": "hello", "agent_version": "...", "node_id": "...", "capabilities": [...] }
{ "type": "pong" }
{ "type": "telemetry", "metrics": { ... } }
```

Exact event names/protocol must stay aligned with the CultForge backend when the
socket is shipped. Until then, poll remains the production path.

Potential real-time events (once the cloud channel exists):

```text
agent.status
agent.metrics
server.status
server.metrics
console.output
player.join
player.leave
network.status
task.progress
update.available
```

---

# 20. Command Model

The Agent should expose controlled capabilities rather than arbitrary remote execution by default.

Conceptual commands:

```text
server.list
server.status
server.start
server.stop
server.restart

server.console.read
server.console.execute

server.config.read
server.config.update

server.mods.list
server.mods.install
server.mods.remove
server.mods.update

server.backup.create
server.backup.restore

node.status
node.metrics

network.status
network.restart
```

Each command must be authorized and resource-scoped.

---

# 21. RBAC in the Agent

CultAgent must respect the CultForge authorization system.

Permissions should answer both:

```text
Can this user perform this action?
Can this user see this information?
```

Example:

```text
Owner
  Everything

Admin
  Server control
  Config
  Backups
  Metrics

Moderator
  Basic server actions
  Player management
  Limited metrics

Player
  Read-only public information
```

Do not duplicate the authoritative role system locally unless necessary for temporary/offline behavior.

## Local defense-in-depth (implemented)

- Cloud control-plane commands remain authoritative (no local denials invented).
- Authorized sidecars use `POST /v1/sidecar/command` with a Bearer token; local role templates (`chloe`, `player`, `moderator`, `admin`, `owner`) are enforced only on that path (`enforce_local`).
- High-risk commands require `confirm=true` for sidecar actors.
- `VisibilityFilter` classifies fields and always redacts SECRET-class keys from JSON responses.

---

# 22. Resource Scoping

Permissions should be tied to resources.

Example:

```text
Moderator
  -> server.restart
      -> Frost Fall #1
```

rather than:

```text
Moderator
  -> server.restart
      -> every server
```

A guild can have multiple agents and servers with different access boundaries.

---

# 23. Information Filtering

CultAgent should avoid exposing unauthorized information to a connected client.

Potential information levels:

```text
PUBLIC
INTERNAL
RESTRICTED
SENSITIVE
SECRET
```

CultAgent must never return or display secrets simply because a local API endpoint exists.

The backend filters what a client is allowed to receive; the agent also enforces sensitive local operations.

---

# 24. Files / Backups

Preserve/improve Crafty's file and backup capabilities.

Required concepts:

```text
File manager
Upload/download where authorized
Directory navigation
Configuration editing
Backup creation
Backup listing
Backup restore
Retention/scheduling
```

High-risk operations should use confirmation and authorization.

---

# 25. Server Lifecycle

CultAgent should manage:

```text
Create
Install
Start
Stop
Restart
Update
Backup
Restore
Delete
```

A higher-level server creation workflow can combine:

```text
1. Create server
2. Select Minecraft version
3. Select loader
4. Select CultForge Build
5. Resolve content
6. Apply configuration
7. Configure networking
8. Register resource
9. Start
10. Verify health
```

---

# 26. CultForge Build Deployment

A build deployment can be deterministic.

Example:

```text
Build manifest
  |
  +-- verify Minecraft version
  +-- verify loader
  +-- resolve mods
  +-- verify checksums
  +-- install files
  +-- apply configs
  +-- configure server
  +-- configure network
  +-- start
  +-- health check
```

Do not silently overwrite user data without backups or an explicit policy.

---

# 27. Chloe Integration

Chloe is a **sidecar/client**, not the central orchestrator.

Correct model:

```text
Chloe
   |
   v
CultForge API
   |
   v
CultAgent
```

Chloe can:

```text
read status
inspect metrics
inspect logs
query Modrinth
plan changes
request approval
perform authorized actions
verify outcomes
```

Chloe cannot bypass CultForge authorization.

CultAgent should not grant Chloe privileged local access merely because she is an AI.

## Local sidecar hook (implemented)

```text
cf-agent sidecar-issue [chloe] [--role chloe]
cf-agent sidecar-list
cf-agent sidecar-revoke <name>
```

- Token stored under the agent data dir; shown once at issue time.
- Default actor id: `cf_CH0E0001` (CultForge Chloe bot).
- Local role `chloe` is read-heavy (status, metrics, console read, builds list/manifest, Modrinth query, profile list/show) — not stop/restart/secret/config write.
- Call `POST http://127.0.0.1:8720/v1/sidecar/command` with `Authorization: Bearer <token>`.

Preferred path remains: Chloe → CultForge API → agent. Local sidecar is for authorized loopback tooling only.

---

# 28. Agentic Workflows

Chloe or another future client may request multi-step tasks.

Example:

```text
"Prepare Frost Fall for tomorrow."
```

Possible workflow:

```text
inspect server
inspect build
inspect mods
inspect compatibility
inspect disk
create backup
inspect network
generate plan
request approval for risky changes
apply changes
restart if necessary
verify health
report result
```

CultAgent's role is to expose reliable, auditable capabilities for such workflows.

---

# 29. Auditability

Important operations should be traceable.

Log:

```text
Who requested it
Which resource
Which operation
When
Result
Failure reason
```

Especially for:

```text
permission changes
config edits
mod changes
backup restore
world deletion
network changes
arbitrary console commands
```

Do not log secrets.

---

# 30. UI Direction

The resulting UI should feel CultForge-native rather than visually identical to Crafty.

Desired conceptual areas:

```text
Dashboard
Servers
Builds
Mods
Configuration
Files
Backups
Network
Metrics
Guild / Access
Agent Settings
```

The actual UI framework can reuse or replace Crafty's existing UI depending on the source architecture.

## Local panel (implemented)

Crafty-major control surface with an Aternos-simple Play path:

```text
Dashboard
  Empty → Create your server CTA
  Has servers → big Start/Stop + Join address (LAN / playit)
  Host metrics + fleet list (Crafty)

Servers / Create
  3-step wizard: name → platform → install (EULA, download, start)

Server admin (Crafty)
  Overview · Terminal · Files · Config · Backups · Mods · Metrics · Admin

Network
  Play online wizard: playit-setup → claim wizard → paste secret → start → public address

Advanced
  Builds · Profiles · Cloud · System
```

Loopback only: `http://127.0.0.1:8720/panel/dashboard`.

---

# 31. Installer / Service Expectations

CultAgent should be installable and manageable like a native service.

Windows:

```text
installer
background service
automatic startup
uninstall
update
```

Linux:

```text
package/binary
systemd service
automatic startup
update
```

macOS:

```text
installer/application
launchd service where appropriate
automatic startup
update
```

The installer should not assume a Python environment exists.

The final runtime dependencies should be packaged or explicitly managed.

---

# 32. Update System

CultAgent should support controlled updates.

Potential flow:

```text
CultForge API
   |
   v
update metadata
   |
   v
Agent
   |
   +-- verify package/checksum
   +-- download
   +-- apply update
   +-- restart service
   +-- report result
```

Use signed/verified artifacts where supported.

Never blindly execute arbitrary downloaded update code.

---

# 33. Security Principles

1. Never trust the frontend as an authorization boundary.
2. Never reuse the user's main credential as a permanent agent secret.
3. Keep agent credentials revocable.
4. Minimize exposed ports.
5. Prefer outbound secure connections.
6. Never return secrets to unauthorized clients.
7. Validate every remote command.
8. Scope operations to explicit resources.
9. Log privileged actions without leaking secrets.
10. Require confirmation for destructive/high-risk operations.
11. Treat downloaded mods/builds/update packages as untrusted until verified.
12. Preserve existing Crafty security guarantees unless intentionally replacing them with something stronger.

---

# 34. Development Strategy

Do not perform a blind rewrite.

Recommended order:

```text
Phase 1
Understand Crafty architecture and process boundaries

Phase 2
Stabilize the fork

Phase 3
Introduce CultAgent identity/registration

Phase 4
Integrate CultForge API/auth/guild context

Phase 5
Implement cloud telemetry + real-time communication

Phase 6
Add CultForge build/content system

Phase 7
Add Modrinth

Phase 8
Add playit.gg/network manager

Phase 9
Implement structured configuration system ← done (profiles CLI + panel)

Phase 10
Implement RBAC/visibility integration ← done (sidecar enforce + secret redact)

Phase 11
Integrate Chloe as an authorized sidecar client ← done (token + role)

Phase 12
Replace/refine UI and installers ← done (Crafty-major + Aternos Play panel; service helpers)

Phase 13
Harden security, update system, auditability and packaging ← done (doctor, update-check, redact)
```

---

# 35. What NOT to Do

Do not:

- turn CultAgent into a standalone cloud platform
- create a separate account system
- create a second guild system
- make Chloe the central orchestrator
- allow Chloe to bypass permissions
- expose all node metrics to all users
- send all secrets to the frontend
- hard-code current API routes without inspection
- rewrite Crafty subsystems without understanding their responsibilities
- make Modrinth the source of truth for CultForge builds
- make playit.gg the only networking abstraction
- expose management ports unnecessarily

---

# 36. Target Product Definition

CultAgent is:

> **The cross-platform machine-side execution and management agent of the CultForge ecosystem, based on an overhauled Crafty Controller foundation.**

It provides:

```text
Minecraft server management
Process management
Configuration management
File and backup management
Metrics
Modrinth content management
Playit.gg networking
CultForge build deployment
Cloud registration
Guild-aware authorization
Secure telemetry
Remote operations
```

While CultForge Cloud remains responsible for:

```text
Identity
Authentication
Guilds
Roles
Permissions
Invites
Cloud state
API contracts
Cross-device/account relationships
```

And Chloe remains:

```text
An optional intelligent sidecar/client
that can use authorized CultForge capabilities
and behave agentically when useful.
```

---

# 37. Final Mental Model

```text
                        CULTFORGE
                           |
              +------------+------------+
              |            |            |
             Auth         API         Guilds
              |            |            |
              +------------+------------+
                           |
                      CultAgent
                           |
       +-------------------+-------------------+
       |                   |                   |
    Minecraft           Modrinth           playit.gg
      Servers             Content             Network
       |
   configs / worlds / files / backups / logs

              Chloe
                 |
                 +---- authorized API client
                 |
                 +---- optional agentic behavior
```

CultAgent is the **local execution layer**.

CultForge is the **cloud control/identity ecosystem**.

Chloe is the **optional intelligent sidecar**.

Crafty is the **foundation being overhauled**, not the final product identity.
