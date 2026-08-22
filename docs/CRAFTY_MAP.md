# Crafty Controller → CultAgent mapping

Reference tree: clone Crafty 4 into `vendor/crafty-4` (gitignored).

```powershell
git clone --depth 1 https://gitlab.com/crafty-controller/crafty-4.git vendor/crafty-4
```

## What CultAgent reimplements (original code)

| Crafty responsibility | Crafty locus | CultAgent module |
|----------------------|--------------|------------------|
| Process spawn (stdin/stdout pipes) | `app/classes/shared/server.py` `do_generic_start` | `servers/process.py` |
| Stop command → wait → terminate | `stop_server` | `ManagedProcess.stop` |
| Console stdin write | `send_command` | `ManagedProcess.send_command` |
| Virtual terminal buffer | `ServerOutBuf` | `servers/console.py` |
| Java path resolution | `detect_java` / `setup_server_run_command` | `servers/java.py` |
| EULA gate | `start_server` eula check | `servers/eula.py` |
| Multi-server registry | servers DB / helpers | `servers/manager.py` catalog.json |
| Crash detection → restart | `crash_detected` | `app._crash_watch_loop` + `auto_restart` |
| Boot autostart | delayed autostart | `app._auto_start_servers` |
| Vanilla / Paper / Purpur / Folia / Fabric / Quilt / Forge / NeoForge servers | installers | `servers/install.py` (`SERVER_LOADERS`) |
| Mods install/remove | content helpers | `content` + `server.mods.*` |
| Zip backups | backup helpers | `files.BackupManager` |
| Local panel | Crafty web UI | `web/templates` + `web/static` at `http://127.0.0.1:8720/panel/…` |
| Network / tunnels | (Crafty N/A) | Official `playit-cloud/playit-agent` via `network/playit.py` — see `vendor/playit/README.md` |

## Intentionally deferred

- Crafty's local user/role DB (CultForge RBAC is cloud-authoritative)
- **Client** setups (launcher profiles, MultiMC, Prism) — agent is server-only
- Spigot BuildTools / CraftBukkit auto-build (use Paper/Purpur)
- Bedrock / SteamCMD / proxy-only (Velocity/Bungee) as first-class
- Full Crafty-grade backup exclude profiles / schedules
- Import of existing Crafty installs
- Bedrock / SteamCMD / proxy-only (Velocity/Bungee) as first-class (playit tunnels work for Java MC today)
## Rule

Do not copy Crafty source verbatim. Preserve proven *responsibilities* and
replace identity, auth, packaging, and UI with CultForge-native layers.

Cloud/launcher follow-ups (when needed): see `todo/API_LAUNCHER.md`.
