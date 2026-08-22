# CultForge panel UI (React + Tailwind)

Crafty-inspired local controller UI (shell, dashboard fleet, server overview) with CultForge OLED/neon theme and `/v1` APIs. Built assets are served by the Python panel at `/panel/…`.

UX patterns adapted from [Crafty 4](https://gitlab.com/crafty-controller/crafty-4) (`vendor/crafty-4/app/frontend`) — host summary, actionable server list, stats strip + tabs — without copying Crafty templates/JS.

## Develop

```powershell
cd panel-ui
npm install
npm run dev
```

Vite proxies `/v1` and `/static` to `http://127.0.0.1:8720` (run the local panel).

## Build (commit output)

```powershell
cd panel-ui
npm run build
```

Writes to `src/cultagent/web/static/spa/`. Open `http://127.0.0.1:8720/panel/dashboard`.

Deep tabs (Terminal, Files, Config, Backups, Mods, Metrics, Players) and Network/Builds still use Jinja pages.
