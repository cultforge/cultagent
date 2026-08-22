import { normalizeState, type ServerRecord, type ServerStatus } from "./api";

export type FleetRow = { server: ServerRecord; status: ServerStatus };

export function scopeBadge(server: ServerRecord): { scope: string; label: string } {
  const scope = server.scope || inferScope(server);
  const label =
    server.scope_label ||
    (scope === "guild" ? "Guild" : scope === "personal" ? "Personal" : "Local");
  return { scope, label };
}

function inferScope(server: ServerRecord): string {
  const meta = server.metadata || {};
  if (meta.scope === "guild" || meta.guild_server_id || meta.cloned_from === "guild") {
    return "guild";
  }
  if (meta.scope === "personal" || meta.personal_server_id || server.server_id.startsWith("upsrv_")) {
    return "personal";
  }
  return "local";
}

export function isRunning(state: unknown): boolean {
  const s = normalizeState(state);
  return s === "running" || s === "online" || s === "starting";
}

export function isCrashed(state: unknown): boolean {
  return normalizeState(state) === "crashed";
}

export function fleetStats(rows: FleetRow[]) {
  let online = 0;
  let offline = 0;
  let crashed = 0;
  let players = 0;
  let maxPlayers = 0;
  for (const { status } of rows) {
    const s = normalizeState(status.state);
    if (s === "running" || s === "online" || s === "starting") online += 1;
    else if (s === "crashed") crashed += 1;
    else offline += 1;
    players += Number(status.players || 0);
    maxPlayers += Number(status.max_players || 0);
  }
  return { total: rows.length, online, offline, crashed, players, maxPlayers };
}

export function formatUptime(seconds: number | null | undefined): string {
  if (seconds == null || Number.isNaN(seconds)) return "—";
  const s = Math.max(0, Math.floor(seconds));
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const sec = s % 60;
  if (h > 0) return `${h}h ${m}m`;
  if (m > 0) return `${m}m ${sec}s`;
  return `${sec}s`;
}

export const SERVER_TABS = [
  { id: "overview", label: "Overview", path: (id: string) => `/servers/${id}` },
  { id: "console", label: "Terminal", path: (id: string) => `/servers/${id}/console` },
  { id: "files", label: "Files", path: (id: string) => `/servers/${id}/files` },
  { id: "config", label: "Config", path: (id: string) => `/servers/${id}/config` },
  { id: "tuner", label: "Tuner", path: (id: string) => `/servers/${id}/tuner` },
  { id: "backups", label: "Backups", path: (id: string) => `/servers/${id}/backups` },
  { id: "mods", label: "Mods", path: (id: string) => `/servers/${id}/mods` },
  { id: "metrics", label: "Metrics", path: (id: string) => `/servers/${id}/metrics` },
  { id: "admin", label: "Players", path: (id: string) => `/servers/${id}/admin` },
] as const;

export type ServerTabId = (typeof SERVER_TABS)[number]["id"];

export function tabFromPath(pathname: string): ServerTabId {
  const parts = pathname.split("/").filter(Boolean);
  const idx = parts.indexOf("servers");
  const tab = idx >= 0 ? parts[idx + 2] : undefined;
  const known = SERVER_TABS.find((t) => t.id === tab);
  return known?.id ?? "overview";
}
