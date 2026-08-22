export type ServerRecord = {
  server_id: string;
  name: string;
  path: string;
  minecraft_version?: string | null;
  loader?: string | null;
  port: number;
  auto_start?: boolean;
  auto_restart?: boolean;
  crash_detection?: boolean;
  build_id?: string | null;
  executable?: string;
  execution_command?: string;
  jvm_args?: string;
  metadata?: Record<string, unknown>;
  scope?: "guild" | "personal" | "local";
  scope_label?: string;
};

export type ServerStatus = {
  server_id: string;
  name: string;
  state: string;
  players?: number;
  max_players?: number | null;
  pid?: number | null;
  exit_code?: number | null;
  uptime_seconds?: number | null;
  version?: string | null;
  loader?: string | null;
};

export type JoinInfo = {
  port: number;
  localhost: string;
  lan?: string | null;
  lan_ip?: string | null;
  public?: string | null;
  public_join?: string | null;
  claim_url?: string | null;
  provider?: string;
  primary: string;
};

export type FlatMetrics = {
  cpu_percent?: number | null;
  memory_percent?: number | null;
  memory_used_gb?: number | null;
  memory_total_gb?: number | null;
  disk_percent?: number | null;
};

export type ServerDetail = {
  ok: boolean;
  server: ServerRecord;
  status: ServerStatus;
  join?: JoinInfo;
  uptime_label?: string;
  mod_count?: number;
};

export type NetworkStatus = {
  active?: string;
  provider?: string;
  status?: string;
  target?: string;
  public_join?: string | null;
  public_endpoint?: string | null;
  details?: {
    has_secret?: boolean;
    binary?: string | null;
    socket_path?: string | null;
    tunnel_count?: number | null;
    last_error?: string | null;
    claim_code?: string | null;
    claim_url?: string | null;
    setup_url?: string | null;
    setup_claim_url?: string | null;
    setup_secret_url?: string | null;
    agents_url?: string | null;
    download_url?: string | null;
    support_url?: string | null;
    release_pin?: string | null;
    platform?: {
      platform?: string;
      install_methods?: string[];
      notes?: string[];
      apt_snippet?: string;
    };
    [key: string]: unknown;
  };
  [key: string]: unknown;
};

export type GuildBuild = {
  id?: string;
  build_id?: string;
  name?: string;
  display_name?: string;
  tagline?: string;
  description?: string;
  loader?: string;
  minecraft_version?: string;
  version?: string;
  guild_id?: string;
  [key: string]: unknown;
};

export type CommandResult = {
  ok?: boolean;
  error?: string;
  data?: Record<string, unknown>;
  command?: string;
};

export type FileItem = {
  name: string;
  path: string;
  is_dir: boolean;
  is_world?: boolean;
  folder_kind?: string | null;
  size?: number | null;
};

export type WorldItem = {
  name: string;
  path?: string;
  has_level_dat?: boolean;
  size?: number;
  pending?: boolean;
};

export type BackupItem = {
  name: string;
  path: string;
  size?: number;
  mtime?: string;
};

export type ModItem = {
  name?: string;
  file?: string;
  filename?: string;
  enabled?: boolean;
  [key: string]: unknown;
};

async function api<T = unknown>(path: string, opts: RequestInit = {}): Promise<T> {
  const res = await fetch(path, {
    headers: { "Content-Type": "application/json", ...(opts.headers || {}) },
    ...opts,
  });
  let data: Record<string, unknown> = {};
  try {
    data = (await res.json()) as Record<string, unknown>;
  } catch {
    data = {};
  }
  if (!res.ok) {
    const msg =
      data.error ||
      data.detail ||
      (data.data && typeof data.data === "object" && (data.data as { error?: string }).error) ||
      res.statusText;
    const err = new Error(typeof msg === "string" ? msg : JSON.stringify(msg)) as Error & {
      status?: number;
    };
    err.status = res.status;
    throw err;
  }
  return data as T;
}

export function humanizeError(err: unknown): string {
  const msg = err instanceof Error ? err.message : String(err);
  const status = err && typeof err === "object" && "status" in err ? Number((err as { status?: number }).status) : 0;
  if (status === 404 || /^not found$/i.test(msg.trim())) {
    return "Panel API route missing — restart the local panel (cf-agent / panel process) so /v1 routes load.";
  }
  if (/not registered|login/i.test(msg)) {
    return "Agent not logged in — run cf-agent login, then refresh.";
  }
  return msg;
}

export function normalizeState(state: unknown): string {
  if (state == null) return "unknown";
  const s = String(state);
  if (s.includes(".")) {
    const tail = s.split(".").pop() || s;
    return tail.toLowerCase();
  }
  return s.toLowerCase();
}

export function flatMetrics(raw: Record<string, unknown> | null): FlatMetrics {
  const system = (raw?.system as Record<string, unknown>) || {};
  const ram = (system.ram as Record<string, unknown>) || {};
  const disk = (system.disk as Record<string, unknown>) || {};
  return {
    cpu_percent: system.cpu_percent as number | null | undefined,
    memory_percent: ram.percent as number | null | undefined,
    memory_used_gb:
      ram.total != null
        ? Math.round(
            ((Number(ram.total) - Number(ram.available || 0)) / 1024 ** 3) * 100,
          ) / 100
        : null,
    memory_total_gb:
      ram.total != null ? Math.round((Number(ram.total) / 1024 ** 3) * 100) / 100 : null,
    disk_percent: disk.percent as number | null | undefined,
  };
}

export type CloudServiceHealth = {
  ok?: boolean;
  status_code?: number;
  base?: string;
  error?: string;
};

export type CloudHealthResponse = {
  ok: boolean;
  services: Record<string, CloudServiceHealth>;
  warning?: string;
};

export type CloudManifestResponse = {
  ok: boolean;
  error?: string;
  api_base?: string;
  build_id?: string | null;
  services?: Record<string, string | null | undefined>;
  agent_route_count?: number;
  agent_routes?: string[];
  required_ok?: boolean;
  missing_required?: string[];
  realtime_ws?: string | null;
  realtime_ready?: boolean;
  note?: string;
};

export type DashboardResponse = {
  ok: boolean;
  status?: Record<string, unknown>;
  cloud_health?: Record<string, CloudServiceHealth> | null;
  cloud_warning?: string | null;
  guild?: {
    attached?: boolean;
    guild_id?: string | null;
    server_count?: number;
    warning?: string | null;
    needs_login?: boolean;
  };
  builds?: {
    count?: number;
    warning?: string | null;
    needs_login?: boolean;
  };
  java?: {
    ok?: boolean;
    path?: string | null;
    version?: string | null;
  };
  local_server_count?: number;
};

export type GuildServerRow = {
  id?: string;
  server_id?: string;
  name?: string;
  display_name?: string;
  build_id?: string | null;
  minecraft_version?: string | null;
  loader?: string | null;
  [key: string]: unknown;
};

export const cultApi = {
  status: () => api<Record<string, unknown>>("/v1/status"),
  metrics: () => api<Record<string, unknown>>("/v1/metrics"),
  dashboard: () => api<DashboardResponse>("/v1/dashboard"),
  cloudHealth: () => api<CloudHealthResponse>("/v1/cloud/health"),
  cloudManifest: () => api<CloudManifestResponse>("/v1/cloud/manifest"),
  command: (command: string, params: Record<string, unknown> = {}, resourceId?: string) =>
    api<CommandResult>("/v1/command", {
      method: "POST",
      body: JSON.stringify({
        command,
        params,
        ...(resourceId ? { resource_id: resourceId } : {}),
      }),
    }),

  async guildServers(): Promise<{
    ok: boolean;
    servers: GuildServerRow[];
    warning?: string;
    needs_login?: boolean;
  }> {
    try {
      const res = await cultApi.command("guild.servers.list", { limit: 100 });
      if (!res.ok) {
        const err = humanizeError(new Error(String(res.error || "guild list failed")));
        return {
          ok: true,
          servers: [],
          warning: err,
          needs_login: /login|registered/i.test(err),
        };
      }
      const raw = res.data?.servers;
      const servers = Array.isArray(raw) ? (raw as GuildServerRow[]) : [];
      return { ok: true, servers };
    } catch (e) {
      const err = humanizeError(e);
      return {
        ok: true,
        servers: [],
        warning: err,
        needs_login: /login|registered/i.test(err),
      };
    }
  },

  cloneServer: (params: {
    guild_server_id: string;
    name?: string;
    port?: number;
    download?: boolean;
    accept_eula?: boolean;
  }) =>
    cultApi.command("server.clone", params as Record<string, unknown>).then((res) => {
      if (!res.ok) throw new Error(String(res.error || "clone failed"));
      return res;
    }),

  provisionBuild: (params: {
    build_id: string;
    display_name?: string;
    include_optional?: boolean;
    desired_state?: string;
    create_local_server?: boolean;
    install?: boolean;
    network_mode?: string;
  }) =>
    cultApi.command("builds.provision", params as Record<string, unknown>).then((res) => {
      if (!res.ok) throw new Error(String(res.error || "provision failed"));
      return res;
    }),

  createServer: (body: {
    name: string;
    minecraft_version?: string | null;
    loader?: string;
    port?: number;
    download?: boolean;
    accept_eula?: boolean;
    auto_start?: boolean;
  }) =>
    api<{ ok: boolean; data?: ServerRecord }>("/v1/servers", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  async network(): Promise<{ ok: boolean; network: NetworkStatus }> {
    try {
      return await api<{ ok: boolean; network: NetworkStatus }>("/v1/network");
    } catch (e) {
      const status = e && typeof e === "object" && "status" in e ? Number((e as { status?: number }).status) : 0;
      if (status === 404) {
        const res = await cultApi.command("network.status");
        return { ok: true, network: (res.data || {}) as NetworkStatus };
      }
      throw e;
    }
  },

  async builds(): Promise<{
    ok: boolean;
    builds: GuildBuild[];
    warning?: string;
    needs_login?: boolean;
  }> {
    try {
      return await api<{
        ok: boolean;
        builds: GuildBuild[];
        warning?: string;
        needs_login?: boolean;
      }>("/v1/builds");
    } catch (e) {
      const status = e && typeof e === "object" && "status" in e ? Number((e as { status?: number }).status) : 0;
      if (status === 404) {
        try {
          const res = await cultApi.command("builds.list");
          const raw = res.data?.builds;
          const builds = Array.isArray(raw) ? (raw as GuildBuild[]) : [];
          return { ok: true, builds };
        } catch (inner) {
          return {
            ok: true,
            builds: [],
            warning: humanizeError(inner),
            needs_login: /login|registered/i.test(humanizeError(inner)),
          };
        }
      }
      throw e;
    }
  },

  servers: () =>
    api<{ ok: boolean; servers?: Array<{ server: ServerRecord; status: ServerStatus }> }>(
      "/v1/servers",
    ),
  server: (id: string) => api<ServerDetail>(`/v1/servers/${id}`),
  action: (id: string, act: "start" | "stop" | "restart") =>
    api(`/v1/servers/${id}/${act}`, {
      method: "POST",
      body: act === "start" ? JSON.stringify({ accept_eula: true }) : "{}",
    }),
  consoleRead: (id: string, limit = 80) =>
    api<{ ok: boolean; data?: { lines?: Array<string | { text?: string }> } }>(
      `/v1/servers/${id}/console?limit=${limit}`,
    ),
  consoleSend: (id: string, command: string) =>
    api(`/v1/servers/${id}/console`, {
      method: "POST",
      body: JSON.stringify({ command }),
    }),
  files: (id: string, path = ".") =>
    api<{ ok: boolean; items?: FileItem[]; error?: string }>(
      `/v1/servers/${id}/files?path=${encodeURIComponent(path)}`,
    ),
  fileRead: (id: string, path: string) =>
    api<{ ok: boolean; content?: string }>(
      `/v1/servers/${id}/files/content?path=${encodeURIComponent(path)}`,
    ),
  fileWrite: (id: string, path: string, content: string) =>
    api(`/v1/servers/${id}/files/content`, {
      method: "PUT",
      body: JSON.stringify({ path, content }),
    }),
  configGet: (id: string) =>
    api<{
      ok: boolean;
      raw?: string;
      properties?: Record<string, string>;
      structured?: Record<string, Record<string, string>>;
      worlds?: WorldItem[];
      active_world?: string;
      schema?: {
        groups: Array<{ id: string; label: string; keys: string[] }>;
        fields: Record<
          string,
          {
            type: string;
            label: string;
            options?: string[];
            min?: number;
            max?: number;
            placeholder?: string;
            help?: string;
            help_full?: string;
            options_help?: Record<string, string>;
          }
        >;
      };
    }>(`/v1/servers/${id}/config`),
  worldsGet: (id: string) =>
    api<{
      ok: boolean;
      worlds?: WorldItem[];
      active_world?: string;
      properties?: Record<string, string>;
      error?: string;
    }>(`/v1/servers/${id}/worlds`),
  worldsSelect: (
    id: string,
    body: { level_name: string; create_folder?: boolean },
  ) =>
    api<{
      ok: boolean;
      worlds?: WorldItem[];
      active_world?: string;
      error?: string;
    }>(`/v1/servers/${id}/worlds`, {
      method: "PUT",
      body: JSON.stringify(body),
    }),
  configSave: (id: string, raw: string) =>
    api(`/v1/servers/${id}/config`, {
      method: "PUT",
      body: JSON.stringify({ raw }),
    }),
  configSaveValues: (id: string, values: Record<string, string>) =>
    api<{
      ok: boolean;
      properties?: Record<string, string>;
      structured?: Record<string, Record<string, string>>;
      raw?: string;
      worlds?: WorldItem[];
      active_world?: string;
      message?: string;
      restarted?: boolean;
      needs_restart?: string[];
      applied_keys?: string[];
      live?: Record<string, unknown>;
    }>(`/v1/servers/${id}/config`, {
      method: "PUT",
      body: JSON.stringify({ values }),
    }),
  jvmGet: (id: string) =>
    api<{
      ok: boolean;
      raw?: string;
      source?: string;
      values?: Record<string, string>;
      preview?: string;
      schema?: {
        groups: Array<{ id: string; label: string; keys: string[] }>;
        fields: Record<
          string,
          {
            type: string;
            label: string;
            options?: string[];
            min?: number;
            max?: number;
            placeholder?: string;
            hint?: string;
          }
        >;
        presets: Array<{
          id: string;
          label: string;
          description?: string;
          values: Record<string, string>;
        }>;
      };
    }>(`/v1/servers/${id}/jvm`),
  jvmSaveValues: (id: string, values: Record<string, string>) =>
    api<{
      ok: boolean;
      raw?: string;
      source?: string;
      values?: Record<string, string>;
      preview?: string;
    }>(`/v1/servers/${id}/jvm`, {
      method: "PUT",
      body: JSON.stringify({ values }),
    }),
  jvmSaveRaw: (id: string, raw: string) =>
    api<{
      ok: boolean;
      raw?: string;
      source?: string;
      values?: Record<string, string>;
      preview?: string;
    }>(`/v1/servers/${id}/jvm`, {
      method: "PUT",
      body: JSON.stringify({ raw }),
    }),
  jvmSavePreset: (id: string, preset: string) =>
    api<{
      ok: boolean;
      raw?: string;
      source?: string;
      values?: Record<string, string>;
      preview?: string;
    }>(`/v1/servers/${id}/jvm`, {
      method: "PUT",
      body: JSON.stringify({ preset }),
    }),
  backups: (id: string) =>
    api<{ ok: boolean; backups?: BackupItem[] }>(`/v1/servers/${id}/backups`),
  backupCreate: (id: string) =>
    api(`/v1/servers/${id}/backups`, { method: "POST", body: "{}" }),
  mods: (id: string) =>
    api<{ ok: boolean; data?: { mods?: ModItem[] }; mods?: ModItem[] }>(
      `/v1/servers/${id}/mods`,
    ),
  acceptEula: (id: string) =>
    api(`/v1/servers/${id}/eula`, { method: "POST", body: "{}" }),
};
