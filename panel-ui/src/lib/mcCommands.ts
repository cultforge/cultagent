/** Vanilla / Forge-style console command suggestions (no leading slash). */

export type McCommand = {
  name: string;
  usage: string;
  summary: string;
  args?: string[];
};

export const MC_COMMANDS: McCommand[] = [
  { name: "help", usage: "help [command]", summary: "List commands or help for one", args: [] },
  { name: "list", usage: "list", summary: "Show online players" },
  { name: "say", usage: "say <message>", summary: "Broadcast a server message", args: ["<message>"] },
  { name: "tell", usage: "tell <player> <message>", summary: "Private message a player", args: ["<player>", "<message>"] },
  { name: "msg", usage: "msg <player> <message>", summary: "Alias of tell", args: ["<player>", "<message>"] },
  { name: "stop", usage: "stop", summary: "Save and stop the server" },
  { name: "save-all", usage: "save-all [flush]", summary: "Force a world save", args: ["flush"] },
  { name: "save-on", usage: "save-on", summary: "Enable automatic saving" },
  { name: "save-off", usage: "save-off", summary: "Disable automatic saving" },
  { name: "reload", usage: "reload", summary: "Reload datapacks / functions" },
  { name: "op", usage: "op <player>", summary: "Grant operator", args: ["<player>"] },
  { name: "deop", usage: "deop <player>", summary: "Revoke operator", args: ["<player>"] },
  { name: "kick", usage: "kick <player> [reason]", summary: "Kick a player", args: ["<player>", "[reason]"] },
  { name: "ban", usage: "ban <player> [reason]", summary: "Ban a player", args: ["<player>", "[reason]"] },
  { name: "ban-ip", usage: "ban-ip <address|player> [reason]", summary: "Ban an IP", args: ["<address|player>"] },
  { name: "pardon", usage: "pardon <player>", summary: "Unban a player", args: ["<player>"] },
  { name: "pardon-ip", usage: "pardon-ip <address>", summary: "Unban an IP", args: ["<address>"] },
  { name: "banlist", usage: "banlist [players|ips]", summary: "Show ban list", args: ["players", "ips"] },
  { name: "whitelist", usage: "whitelist <on|off|list|add|remove|reload>", summary: "Manage whitelist", args: ["on", "off", "list", "add", "remove", "reload"] },
  { name: "gamemode", usage: "gamemode <mode> [player]", summary: "Set gamemode", args: ["survival", "creative", "adventure", "spectator", "<player>"] },
  { name: "defaultgamemode", usage: "defaultgamemode <mode>", summary: "Default join gamemode", args: ["survival", "creative", "adventure", "spectator"] },
  { name: "difficulty", usage: "difficulty <peaceful|easy|normal|hard>", summary: "Set difficulty", args: ["peaceful", "easy", "normal", "hard"] },
  { name: "time", usage: "time <set|add|query> …", summary: "Control world time", args: ["set", "add", "query", "day", "night", "noon", "midnight"] },
  { name: "weather", usage: "weather <clear|rain|thunder> [seconds]", summary: "Set weather", args: ["clear", "rain", "thunder"] },
  { name: "tp", usage: "tp <targets> …", summary: "Teleport entities/players", args: ["<player>", "<x>", "<y>", "<z>"] },
  { name: "teleport", usage: "teleport <targets> …", summary: "Alias of tp" },
  { name: "give", usage: "give <player> <item> [count]", summary: "Give items", args: ["<player>", "<item>", "[count]"] },
  { name: "clear", usage: "clear [player] [item] [count]", summary: "Clear inventory" },
  { name: "kill", usage: "kill [targets]", summary: "Kill entities/players", args: ["@a", "@e", "@p", "@s"] },
  { name: "effect", usage: "effect <give|clear> …", summary: "Apply/clear potion effects", args: ["give", "clear"] },
  { name: "enchant", usage: "enchant <player> <enchantment> [level]", summary: "Enchant held item" },
  { name: "xp", usage: "xp <add|set|query> …", summary: "Manage experience", args: ["add", "set", "query"] },
  { name: "experience", usage: "experience <add|set|query> …", summary: "Alias of xp" },
  { name: "gamerule", usage: "gamerule <rule> [value]", summary: "Get/set a game rule", args: ["keepInventory", "doDaylightCycle", "doMobSpawning", "mobGriefing", "true", "false"] },
  { name: "seed", usage: "seed", summary: "Show world seed" },
  { name: "setworldspawn", usage: "setworldspawn [<pos>]", summary: "Set world spawn" },
  { name: "spawnpoint", usage: "spawnpoint [player] [<pos>]", summary: "Set player spawn" },
  { name: "setblock", usage: "setblock <pos> <block>", summary: "Place a block" },
  { name: "fill", usage: "fill <from> <to> <block>", summary: "Fill a region" },
  { name: "clone", usage: "clone <begin> <end> <destination>", summary: "Clone blocks" },
  { name: "summon", usage: "summon <entity> [<pos>]", summary: "Summon an entity" },
  { name: "locate", usage: "locate <structure|biome|poi> <id>", summary: "Find nearest feature", args: ["structure", "biome", "poi"] },
  { name: "spreadplayers", usage: "spreadplayers <x> <z> …", summary: "Scatter entities" },
  { name: "worldborder", usage: "worldborder <subcommand> …", summary: "Manage world border", args: ["get", "set", "add", "center", "damage", "warning"] },
  { name: "bossbar", usage: "bossbar <subcommand> …", summary: "Manage boss bars", args: ["add", "remove", "list", "set", "get"] },
  { name: "scoreboard", usage: "scoreboard <objectives|players|…>", summary: "Scoreboard system", args: ["objectives", "players", "players list"] },
  { name: "team", usage: "team <subcommand> …", summary: "Manage teams", args: ["list", "add", "remove", "join", "leave"] },
  { name: "title", usage: "title <player> <title|subtitle|…>", summary: "Show titles", args: ["title", "subtitle", "actionbar", "clear", "times"] },
  { name: "playsound", usage: "playsound <sound> <source> <targets>", summary: "Play a sound" },
  { name: "particle", usage: "particle <name> …", summary: "Spawn particles" },
  { name: "function", usage: "function <name>", summary: "Run a datapack function" },
  { name: "datapack", usage: "datapack <list|enable|disable>", summary: "Manage datapacks", args: ["list", "enable", "disable"] },
  { name: "recipe", usage: "recipe <give|take> …", summary: "Unlock/take recipes", args: ["give", "take"] },
  { name: "advancement", usage: "advancement <grant|revoke> …", summary: "Manage advancements", args: ["grant", "revoke"] },
  { name: "attribute", usage: "attribute <target> <attribute> …", summary: "Query/modify attributes" },
  { name: "item", usage: "item <replace|modify> …", summary: "Modify item slots", args: ["replace", "modify"] },
  { name: "loot", usage: "loot <give|insert|spawn|replace> …", summary: "Generate loot tables" },
  { name: "data", usage: "data <get|merge|modify|remove> …", summary: "NBT data commands", args: ["get", "merge", "modify", "remove"] },
  { name: "execute", usage: "execute … run <command>", summary: "Conditional command runner" },
  { name: "forge", usage: "forge <subcommand>", summary: "Forge mod loader commands (if available)", args: ["tps", "track", "entity", "generate"] },
  { name: "forge tps", usage: "forge tps", summary: "Show ticks per second (Forge)" },
];

export type Suggestion = {
  insert: string;
  label: string;
  detail: string;
  kind: "command" | "arg";
};

export function suggestConsole(input: string, limit = 12): Suggestion[] {
  const raw = input.replace(/^\//, "");
  const parts = raw.split(/\s+/);
  const trailingSpace = /\s$/.test(input);
  const head = (parts[0] || "").toLowerCase();

  // Completing first token
  if (parts.length <= 1 && !trailingSpace) {
    return MC_COMMANDS.filter((c) => c.name.startsWith(head) || c.name.includes(head))
      .slice(0, limit)
      .map((c) => ({
        insert: c.name,
        label: c.name,
        detail: c.summary,
        kind: "command" as const,
      }));
  }

  const cmd = MC_COMMANDS.find((c) => c.name === head || c.name.startsWith(head + " "));
  // Multi-word command names like "forge tps"
  const multi = MC_COMMANDS.filter((c) => c.name.includes(" ") && raw.toLowerCase().startsWith(c.name.split(" ")[0]));
  if (!cmd && multi.length && parts.length === 1 && trailingSpace) {
    return multi
      .slice(0, limit)
      .map((c) => ({
        insert: c.name,
        label: c.name,
        detail: c.summary,
        kind: "command" as const,
      }));
  }

  const match =
    MC_COMMANDS.find((c) => c.name === head) ||
    MC_COMMANDS.find((c) => raw.toLowerCase().startsWith(c.name) && c.name.includes(" "));

  if (!match?.args?.length) {
    // Still show usage hint for exact command
    if (match) {
      return [
        {
          insert: raw.trimEnd(),
          label: match.usage,
          detail: match.summary,
          kind: "command",
        },
      ];
    }
    return MC_COMMANDS.filter((c) => c.name.startsWith(head))
      .slice(0, limit)
      .map((c) => ({
        insert: c.name,
        label: c.name,
        detail: c.summary,
        kind: "command" as const,
      }));
  }

  const argToken = trailingSpace ? "" : (parts[parts.length - 1] || "").toLowerCase();
  const prefix = trailingSpace
    ? raw.trimEnd() + " "
    : raw.slice(0, Math.max(0, raw.length - argToken.length));

  return match.args
    .filter((a) => a.toLowerCase().startsWith(argToken) || a.toLowerCase().includes(argToken))
    .slice(0, limit)
    .map((a) => ({
      insert: `${prefix}${a}`.replace(/\s+/g, " ").trim(),
      label: a,
      detail: match.usage,
      kind: "arg" as const,
    }));
}

export function completeConsole(input: string): string | null {
  const suggestions = suggestConsole(input, 1);
  if (!suggestions.length) return null;
  return suggestions[0].insert;
}
