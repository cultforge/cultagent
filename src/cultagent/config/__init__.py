"""Structured config + reusable profiles."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field


class ConfigProfile(BaseModel):
    name: str
    description: str = ""
    values: dict[str, Any] = Field(default_factory=dict)
    # Optional metadata for UI / apply targeting
    tags: list[str] = Field(default_factory=list)


# server.properties-oriented structured groups (UI mapping).
STRUCTURED_GROUPS: dict[str, list[str]] = {
    "gameplay": [
        "motd",
        "difficulty",
        "gamemode",
        "hardcore",
        "pvp",
        "force-gamemode",
        "spawn-monsters",
        "spawn-animals",
        "spawn-npcs",
        "allow-flight",
    ],
    "world": [
        "level-name",
        "level-seed",
        "level-type",
        "generate-structures",
        "max-world-size",
        "spawn-protection",
        "allow-nether",
        "enable-command-block",
    ],
    "network": [
        "server-port",
        "server-ip",
        "network-compression-threshold",
        "prevent-proxy-connections",
        "enable-status",
        "enable-query",
        "enable-rcon",
    ],
    "performance": [
        "view-distance",
        "simulation-distance",
        "max-tick-time",
        "entity-broadcast-range-percentage",
        "max-players",
    ],
    "security": [
        "online-mode",
        "white-list",
        "enforce-whitelist",
        "op-permission-level",
        "function-permission-level",
        "hide-online-players",
    ],
}

# GUI field metadata for panel forms (type drives control widget).
FIELD_SCHEMA: dict[str, dict[str, Any]] = {
    "motd": {"type": "text", "label": "Message of the day", "placeholder": "A Minecraft Server"},
    "difficulty": {
        "type": "enum",
        "label": "Difficulty",
        "options": ["peaceful", "easy", "normal", "hard"],
    },
    "gamemode": {
        "type": "enum",
        "label": "Default gamemode",
        "options": ["survival", "creative", "adventure", "spectator"],
    },
    "hardcore": {"type": "bool", "label": "Hardcore"},
    "pvp": {"type": "bool", "label": "PvP"},
    "force-gamemode": {"type": "bool", "label": "Force gamemode on join"},
    "spawn-monsters": {"type": "bool", "label": "Spawn monsters"},
    "spawn-animals": {"type": "bool", "label": "Spawn animals"},
    "spawn-npcs": {"type": "bool", "label": "Spawn villagers / NPCs"},
    "allow-flight": {"type": "bool", "label": "Allow flight"},
    "level-name": {
        "type": "world",
        "label": "Active world",
        "placeholder": "world",
    },
    "level-seed": {"type": "text", "label": "Seed", "placeholder": "Leave empty for random"},
    "level-type": {
        "type": "enum",
        "label": "Level type",
        "options": [
            "minecraft:normal",
            "minecraft:flat",
            "minecraft:large_biomes",
            "minecraft:amplified",
            "default",
            "flat",
        ],
    },
    "generate-structures": {"type": "bool", "label": "Generate structures"},
    "max-world-size": {"type": "int", "label": "Max world size", "min": 1, "max": 29999984},
    "spawn-protection": {"type": "int", "label": "Spawn protection", "min": 0, "max": 100},
    "allow-nether": {"type": "bool", "label": "Allow Nether"},
    "enable-command-block": {"type": "bool", "label": "Enable command blocks"},
    "server-port": {"type": "int", "label": "Server port", "min": 1, "max": 65535},
    "server-ip": {"type": "text", "label": "Bind IP", "placeholder": "0.0.0.0 or blank"},
    "online-mode": {
        "type": "bool",
        "label": "Online mode",
        "help": "Require Microsoft / Mojang login (recommended on). Off = offline/cracked names.",
    },
    "network-compression-threshold": {"type": "int", "label": "Network compression", "min": -1, "max": 1024},
    "prevent-proxy-connections": {"type": "bool", "label": "Prevent proxy connections"},
    "enable-status": {"type": "bool", "label": "Enable status ping"},
    "enable-query": {"type": "bool", "label": "Enable query"},
    "enable-rcon": {"type": "bool", "label": "Enable RCON"},
    "view-distance": {"type": "int", "label": "View distance", "min": 2, "max": 32},
    "simulation-distance": {"type": "int", "label": "Simulation distance", "min": 2, "max": 32},
    "max-tick-time": {"type": "int", "label": "Max tick time (ms)", "min": -1},
    "entity-broadcast-range-percentage": {
        "type": "int",
        "label": "Entity broadcast range %",
        "min": 10,
        "max": 1000,
    },
    "max-players": {"type": "int", "label": "Max players", "min": 1, "max": 1000},
    "white-list": {"type": "bool", "label": "Whitelist enabled"},
    "enforce-whitelist": {"type": "bool", "label": "Enforce whitelist"},
    "op-permission-level": {"type": "int", "label": "OP permission level", "min": 1, "max": 4},
    "function-permission-level": {
        "type": "int",
        "label": "Function permission level",
        "min": 1,
        "max": 4,
    },
    "hide-online-players": {"type": "bool", "label": "Hide online players"},
}

GROUP_LABELS: dict[str, str] = {
    "gameplay": "Gameplay",
    "world": "World",
    "network": "Network",
    "performance": "Performance",
    "security": "Security",
    "other": "Other",
}


def _safe_name(name: str) -> str:
    safe = "".join(c for c in name if c.isalnum() or c in ("-", "_", " ")).strip()
    safe = re.sub(r"\s+", "-", safe)
    if not safe:
        raise ValueError("invalid profile name")
    return safe


class ProfileStore:
    def __init__(self, profiles_dir: Path) -> None:
        self.profiles_dir = profiles_dir
        self.profiles_dir.mkdir(parents=True, exist_ok=True)

    def _path(self, name: str) -> Path:
        return self.profiles_dir / f"{_safe_name(name)}.json"

    def list_profiles(self) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for path in sorted(self.profiles_dir.glob("*.json")):
            try:
                profile = ConfigProfile.model_validate_json(path.read_text(encoding="utf-8"))
                out.append(
                    {
                        "name": profile.name,
                        "description": profile.description,
                        "keys": len(profile.values),
                        "tags": profile.tags,
                    }
                )
            except Exception:  # noqa: BLE001
                out.append({"name": path.stem, "description": "(invalid)", "keys": 0, "tags": []})
        return out

    def load(self, name: str) -> ConfigProfile:
        path = self._path(name)
        if not path.is_file():
            raise FileNotFoundError(name)
        return ConfigProfile.model_validate_json(path.read_text(encoding="utf-8"))

    def save(self, profile: ConfigProfile) -> ConfigProfile:
        profile.name = _safe_name(profile.name)
        path = self._path(profile.name)
        path.write_text(profile.model_dump_json(indent=2), encoding="utf-8")
        return profile

    def delete(self, name: str) -> None:
        path = self._path(name)
        if not path.is_file():
            raise FileNotFoundError(name)
        path.unlink()

    def capture(self, name: str, properties: dict[str, Any], *, description: str = "") -> ConfigProfile:
        profile = ConfigProfile(
            name=name,
            description=description or f"Captured profile ({len(properties)} keys)",
            values={str(k): str(v) for k, v in properties.items()},
        )
        return self.save(profile)

    def diff(self, current: dict[str, Any], profile: ConfigProfile) -> dict[str, Any]:
        changes: dict[str, Any] = {}
        for key, new_value in profile.values.items():
            old = current.get(key)
            if str(old) != str(new_value):
                changes[key] = {"from": old, "to": new_value}
        return changes

    def apply(
        self,
        current: dict[str, Any],
        profile: ConfigProfile,
        *,
        mode: str = "merge",
    ) -> dict[str, Any]:
        """Return new properties dict. mode=merge keeps unknown keys; replace uses profile only."""
        if mode == "replace":
            return {str(k): str(v) for k, v in profile.values.items()}
        merged = dict(current)
        for key, value in profile.values.items():
            merged[str(key)] = str(value)
        return merged


def parse_server_properties(text: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        out[key.strip()] = value.strip()
    return out


def render_server_properties(values: dict[str, Any]) -> str:
    lines = [f"{key}={values[key]}" for key in sorted(values)]
    return "\n".join(lines) + "\n"


def structured_view(properties: dict[str, str]) -> dict[str, dict[str, str]]:
    view: dict[str, dict[str, str]] = {group: {} for group in STRUCTURED_GROUPS}
    known = {key for keys in STRUCTURED_GROUPS.values() for key in keys}
    for group, keys in STRUCTURED_GROUPS.items():
        for key in keys:
            if key in properties:
                view[group][key] = properties[key]
    view["other"] = {k: v for k, v in properties.items() if k not in known}
    return view


def field_schema_payload() -> dict[str, Any]:
    from cultagent.config.property_help import PROPERTY_HELP

    fields: dict[str, Any] = {}
    for key, meta in FIELD_SCHEMA.items():
        merged = dict(meta)
        help_meta = PROPERTY_HELP.get(key, {})
        for hk in ("help", "help_full", "options_help"):
            if hk in help_meta:
                merged[hk] = help_meta[hk]
        fields[key] = merged
    # Extra keys (often land in "Other properties") with type + docs
    for key, help_meta in PROPERTY_HELP.items():
        if key in fields:
            continue
        entry: dict[str, Any] = {
            "type": help_meta.get("type", "text"),
            "label": help_meta.get("label", key),
        }
        for hk in ("help", "help_full", "options_help", "options", "min", "max", "placeholder"):
            if hk in help_meta:
                entry[hk] = help_meta[hk]
        fields[key] = entry
    return {
        "groups": [
            {
                "id": group_id,
                "label": GROUP_LABELS.get(group_id, group_id.title()),
                "keys": keys,
            }
            for group_id, keys in STRUCTURED_GROUPS.items()
        ],
        "fields": fields,
        "group_labels": GROUP_LABELS,
    }