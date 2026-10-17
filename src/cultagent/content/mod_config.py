"""Scan and edit Minecraft mod config files (config/*.toml and simple JSON)."""

from __future__ import annotations

import json
import tomllib
from pathlib import Path
from typing import Any


def list_mod_config_files(server_root: str | Path) -> list[dict[str, Any]]:
    root = Path(server_root).resolve()
    cfg = root / "config"
    out: list[dict[str, Any]] = []
    if not cfg.is_dir():
        return out
    for path in sorted(cfg.rglob("*")):
        if not path.is_file():
            continue
        if path.suffix.lower() not in {".toml", ".json", ".properties"}:
            continue
        rel = path.relative_to(root).as_posix()
        out.append(
            {
                "path": rel,
                "name": path.name,
                "suffix": path.suffix.lower(),
                "size": path.stat().st_size,
            }
        )
    return out[:200]


def _flatten(obj: Any, prefix: str = "") -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if isinstance(obj, dict):
        for key, val in obj.items():
            path = f"{prefix}.{key}" if prefix else str(key)
            if isinstance(val, dict):
                rows.extend(_flatten(val, path))
            elif isinstance(val, list):
                rows.append(
                    {
                        "key": path,
                        "type": "json",
                        "value": json.dumps(val),
                        "label": path.split(".")[-1],
                    }
                )
            elif isinstance(val, bool):
                rows.append({"key": path, "type": "bool", "value": val, "label": path.split(".")[-1]})
            elif isinstance(val, (int, float)) and not isinstance(val, bool):
                rows.append(
                    {
                        "key": path,
                        "type": "number",
                        "value": val,
                        "label": path.split(".")[-1],
                    }
                )
            elif val is None:
                rows.append({"key": path, "type": "text", "value": "", "label": path.split(".")[-1]})
            else:
                rows.append(
                    {
                        "key": path,
                        "type": "text",
                        "value": str(val),
                        "label": path.split(".")[-1],
                    }
                )
    return rows


def _set_path(root: dict[str, Any], dotted: str, value: Any) -> None:
    parts = dotted.split(".")
    cur: Any = root
    for part in parts[:-1]:
        nxt = cur.get(part)
        if not isinstance(nxt, dict):
            nxt = {}
            cur[part] = nxt
        cur = nxt
    cur[parts[-1]] = value


def _dump_toml(obj: Any, indent: int = 0) -> str:
    """Minimal TOML writer for nested dicts of scalars/lists."""
    lines: list[str] = []
    tables: list[tuple[str, dict[str, Any]]] = []

    def fmt(val: Any) -> str:
        if isinstance(val, bool):
            return "true" if val else "false"
        if isinstance(val, (int, float)):
            return str(val)
        if isinstance(val, list):
            return "[" + ", ".join(fmt(v) for v in val) + "]"
        text = str(val).replace("\\", "\\\\").replace('"', '\\"')
        return f'"{text}"'

    if not isinstance(obj, dict):
        return ""
    for key, val in obj.items():
        if isinstance(val, dict):
            tables.append((key, val))
        else:
            lines.append(f"{key} = {fmt(val)}")
    for key, table in tables:
        lines.append("")
        lines.append(f"[{key}]")
        for sk, sv in table.items():
            if isinstance(sv, dict):
                # one nested level only in this simple writer
                lines.append("")
                lines.append(f"[{key}.{sk}]")
                for ssk, ssv in sv.items():
                    if not isinstance(ssv, dict):
                        lines.append(f"{ssk} = {fmt(ssv)}")
            else:
                lines.append(f"{sk} = {fmt(sv)}")
    return "\n".join(lines).rstrip() + "\n"


def read_mod_config(server_root: str | Path, rel: str) -> dict[str, Any]:
    root = Path(server_root).resolve()
    path = (root / rel).resolve()
    if not str(path).startswith(str(root)):
        raise PermissionError("path escapes server directory")
    if not path.is_file():
        raise FileNotFoundError(rel)
    raw = path.read_text(encoding="utf-8", errors="replace")
    fields: list[dict[str, Any]] = []
    parsed: Any = None
    suffix = path.suffix.lower()
    try:
        if suffix == ".toml":
            parsed = tomllib.loads(raw)
            fields = _flatten(parsed)
        elif suffix == ".json":
            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                fields = _flatten(parsed)
        elif suffix == ".properties":
            props: dict[str, str] = {}
            for line in raw.splitlines():
                s = line.strip()
                if not s or s.startswith("#") or "=" not in s:
                    continue
                k, _, v = s.partition("=")
                props[k.strip()] = v.strip()
                fields.append(
                    {
                        "key": k.strip(),
                        "type": "text",
                        "value": v.strip(),
                        "label": k.strip(),
                    }
                )
            parsed = props
    except Exception as exc:  # noqa: BLE001
        return {
            "path": rel,
            "raw": raw,
            "fields": [],
            "parse_error": str(exc),
            "ok": True,
        }
    return {
        "path": rel,
        "raw": raw,
        "fields": fields,
        "ok": True,
        "suffix": suffix,
    }


def write_mod_config(
    server_root: str | Path,
    rel: str,
    *,
    raw: str | None = None,
    values: dict[str, Any] | None = None,
) -> dict[str, Any]:
    root = Path(server_root).resolve()
    path = (root / rel).resolve()
    if not str(path).startswith(str(root)):
        raise PermissionError("path escapes server directory")
    if not path.is_file() and raw is None:
        raise FileNotFoundError(rel)
    suffix = path.suffix.lower()
    text: str
    if raw is not None and values is None:
        text = raw
    elif values is not None and suffix in {".toml", ".json"}:
        base: dict[str, Any] = {}
        if path.is_file():
            existing = path.read_text(encoding="utf-8", errors="replace")
            try:
                if suffix == ".toml":
                    base = tomllib.loads(existing)
                else:
                    loaded = json.loads(existing)
                    base = loaded if isinstance(loaded, dict) else {}
            except Exception:  # noqa: BLE001
                base = {}
        for key, val in values.items():
            _set_path(base, str(key), val)
        text = json.dumps(base, indent=2) + "\n" if suffix == ".json" else _dump_toml(base)
    elif values is not None and suffix == ".properties":
        lines: list[str] = []
        if path.is_file():
            for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
                s = line.strip()
                if not s or s.startswith("#") or "=" not in s:
                    lines.append(line)
                    continue
                k, _, _ = s.partition("=")
                key = k.strip()
                if key in values:
                    lines.append(f"{key}={values[key]}")
                else:
                    lines.append(line)
        for key, val in values.items():
            if not any(ln.startswith(f"{key}=") for ln in lines):
                lines.append(f"{key}={val}")
        text = "\n".join(lines).rstrip() + "\n"
    else:
        text = raw if raw is not None else path.read_text(encoding="utf-8", errors="replace")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return read_mod_config(root, rel)
