"""Structured JVM flag parsing / rendering for the panel Tuner GUI."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

_MEM_RE = re.compile(r"^-X(?P<kind>ms|mx)(?P<value>\d+)(?P<unit>[kKmMgG]?)$")
_XX_BOOL_RE = re.compile(r"^-XX:(?P<sign>[+-])(?P<name>[A-Za-z0-9_]+)$")
_XX_EQ_RE = re.compile(r"^-XX:(?P<name>[A-Za-z0-9_]+)=(?P<value>.+)$")
_D_PROP_RE = re.compile(r"^-D(?P<name>[^=]+)=(?P<value>.*)$")

# Flags owned by the structured GUI (everything else lands in "extra").
OWNED_BOOL = {
    "UseG1GC",
    "UseZGC",
    "UseParallelGC",
    "UseSerialGC",
    "UseShenandoahGC",
    "AlwaysPreTouch",
    "DisableExplicitGC",
    "ParallelRefProcEnabled",
    "PerfDisableSharedMem",
    "UseStringDeduplication",
    "UnlockExperimentalVMOptions",
}

OWNED_INT = {
    "MaxGCPauseMillis",
    "G1NewSizePercent",
    "G1MaxNewSizePercent",
    "G1HeapRegionSize",
    "G1ReservePercent",
    "InitiatingHeapOccupancyPercent",
    "MaxTenuringThreshold",
    "SurvivorRatio",
}

OWNED_PROPS = {
    "file.encoding",
    "java.net.preferIPv4Stack",
}

GROUP_LABELS: dict[str, str] = {
    "memory": "Memory",
    "collector": "Garbage collector",
    "g1": "G1 tuning",
    "stability": "Stability & throughput",
    "extra": "Extra flags",
}

FIELD_SCHEMA: dict[str, dict[str, Any]] = {
    "xms": {
        "type": "memory",
        "label": "Initial heap (Xms)",
        "group": "memory",
        "hint": "Starting heap size. Matching Xms and Xmx avoids resize pauses.",
    },
    "xmx": {
        "type": "memory",
        "label": "Max heap (Xmx)",
        "group": "memory",
        "hint": "Leave headroom for the OS and native memory.",
    },
    "lock_heap": {
        "type": "bool",
        "label": "Lock Xms = Xmx",
        "group": "memory",
        "hint": "Recommended for dedicated game servers.",
    },
    "gc": {
        "type": "enum",
        "label": "Collector",
        "group": "collector",
        "options": ["g1", "zgc", "parallel", "serial", "shenandoah", "default"],
        "hint": "G1 is the usual choice for Minecraft. ZGC needs a recent JDK.",
    },
    "MaxGCPauseMillis": {
        "type": "int",
        "label": "Max GC pause (ms)",
        "group": "g1",
        "min": 1,
        "max": 500,
        "hint": "G1 pause target. 200 is a common Minecraft default.",
    },
    "G1NewSizePercent": {
        "type": "int",
        "label": "G1 new size %",
        "group": "g1",
        "min": 0,
        "max": 100,
    },
    "G1MaxNewSizePercent": {
        "type": "int",
        "label": "G1 max new size %",
        "group": "g1",
        "min": 0,
        "max": 100,
    },
    "G1HeapRegionSize": {
        "type": "int",
        "label": "G1 heap region (MB)",
        "group": "g1",
        "min": 1,
        "max": 32,
        "hint": "Power-of-two megabytes. Leave empty for JVM default.",
    },
    "G1ReservePercent": {
        "type": "int",
        "label": "G1 reserve %",
        "group": "g1",
        "min": 0,
        "max": 50,
    },
    "InitiatingHeapOccupancyPercent": {
        "type": "int",
        "label": "Initiating heap occupancy %",
        "group": "g1",
        "min": 0,
        "max": 100,
    },
    "AlwaysPreTouch": {
        "type": "bool",
        "label": "AlwaysPreTouch",
        "group": "stability",
        "hint": "Touch pages at startup for more predictable latency.",
    },
    "DisableExplicitGC": {
        "type": "bool",
        "label": "DisableExplicitGC",
        "group": "stability",
        "hint": "Ignore System.gc() calls from mods/plugins.",
    },
    "ParallelRefProcEnabled": {
        "type": "bool",
        "label": "ParallelRefProcEnabled",
        "group": "stability",
    },
    "PerfDisableSharedMem": {
        "type": "bool",
        "label": "PerfDisableSharedMem",
        "group": "stability",
        "hint": "Avoids hsperfdata writes that can stall on some disks.",
    },
    "UseStringDeduplication": {
        "type": "bool",
        "label": "UseStringDeduplication",
        "group": "stability",
        "hint": "G1-only. Can help on chatty / modded servers.",
    },
    "UnlockExperimentalVMOptions": {
        "type": "bool",
        "label": "UnlockExperimentalVMOptions",
        "group": "stability",
    },
    "file.encoding": {
        "type": "enum",
        "label": "File encoding",
        "group": "stability",
        "options": ["", "UTF-8", "UTF-16"],
    },
    "prefer_ipv4": {
        "type": "bool",
        "label": "Prefer IPv4 stack",
        "group": "stability",
    },
    "extra": {
        "type": "textarea",
        "label": "Extra JVM flags",
        "group": "extra",
        "hint": "Space-separated flags not covered above (kept as-is on save).",
        "placeholder": "-XX:+UseLargePages --add-modules=jdk.incubator.vector",
    },
}

PRESETS: dict[str, dict[str, Any]] = {
    "default": {
        "label": "Default",
        "description": "Simple 1G → 2G heap, no extra GC flags.",
        "values": {
            "xms": "1G",
            "xmx": "2G",
            "lock_heap": "false",
            "gc": "default",
            "extra": "",
        },
    },
    "balanced": {
        "label": "Balanced",
        "description": "Fixed 4G heap + G1 with common stability flags.",
        "values": {
            "xms": "4G",
            "xmx": "4G",
            "lock_heap": "true",
            "gc": "g1",
            "MaxGCPauseMillis": "200",
            "AlwaysPreTouch": "true",
            "DisableExplicitGC": "true",
            "ParallelRefProcEnabled": "true",
            "PerfDisableSharedMem": "true",
            "file.encoding": "UTF-8",
            "extra": "",
        },
    },
    "aikar": {
        "label": "Aikar-style",
        "description": "Popular G1 flags for dedicated Minecraft hosts (8G example).",
        "values": {
            "xms": "8G",
            "xmx": "8G",
            "lock_heap": "true",
            "gc": "g1",
            "MaxGCPauseMillis": "200",
            "G1NewSizePercent": "30",
            "G1MaxNewSizePercent": "40",
            "G1HeapRegionSize": "8",
            "G1ReservePercent": "20",
            "InitiatingHeapOccupancyPercent": "15",
            "AlwaysPreTouch": "true",
            "DisableExplicitGC": "true",
            "ParallelRefProcEnabled": "true",
            "PerfDisableSharedMem": "true",
            "UseStringDeduplication": "true",
            "UnlockExperimentalVMOptions": "true",
            "file.encoding": "UTF-8",
            "extra": (
                "-XX:G1HeapWastePercent=5 "
                "-XX:G1MixedGCCountTarget=4 "
                "-XX:G1MixedGCLiveThresholdPercent=90 "
                "-XX:G1RSetUpdatingPauseTimePercent=5 "
                "-XX:SurvivorRatio=32 "
                "-XX:MaxTenuringThreshold=1 "
                "-XX:+UseFastUnorderedTimeStamps"
            ),
        },
    },
    "low_ram": {
        "label": "Low RAM",
        "description": "Tight 1G heap for small vanilla / light modpacks.",
        "values": {
            "xms": "1G",
            "xmx": "1G",
            "lock_heap": "true",
            "gc": "g1",
            "MaxGCPauseMillis": "200",
            "DisableExplicitGC": "true",
            "PerfDisableSharedMem": "true",
            "file.encoding": "UTF-8",
            "extra": "",
        },
    },
}


def _tokenize(raw: str) -> list[str]:
    return [t for t in (raw or "").split() if t.strip()]


def _parse_memory(token: str) -> tuple[str, str] | None:
    m = _MEM_RE.match(token)
    if not m:
        return None
    unit = (m.group("unit") or "M").upper()
    if unit == "K":
        unit = "K"
    elif unit == "M":
        unit = "M"
    else:
        unit = "G"
    return m.group("kind"), f"{m.group('value')}{unit}"


def parse_jvm_args(raw: str) -> dict[str, str]:
    """Parse a JVM arg string into structured Tuner fields."""
    values: dict[str, str] = {
        "xms": "1G",
        "xmx": "2G",
        "lock_heap": "false",
        "gc": "default",
        "MaxGCPauseMillis": "",
        "G1NewSizePercent": "",
        "G1MaxNewSizePercent": "",
        "G1HeapRegionSize": "",
        "G1ReservePercent": "",
        "InitiatingHeapOccupancyPercent": "",
        "AlwaysPreTouch": "false",
        "DisableExplicitGC": "false",
        "ParallelRefProcEnabled": "false",
        "PerfDisableSharedMem": "false",
        "UseStringDeduplication": "false",
        "UnlockExperimentalVMOptions": "false",
        "file.encoding": "",
        "prefer_ipv4": "false",
        "extra": "",
    }
    extra: list[str] = []
    gc_hits: list[str] = []

    for token in _tokenize(raw):
        mem = _parse_memory(token)
        if mem:
            kind, size = mem
            if kind == "ms":
                values["xms"] = size
            else:
                values["xmx"] = size
            continue

        bm = _XX_BOOL_RE.match(token)
        if bm:
            name = bm.group("name")
            on = bm.group("sign") == "+"
            if name in {
                "UseG1GC",
                "UseZGC",
                "UseParallelGC",
                "UseSerialGC",
                "UseShenandoahGC",
            }:
                if on:
                    mapping = {
                        "UseG1GC": "g1",
                        "UseZGC": "zgc",
                        "UseParallelGC": "parallel",
                        "UseSerialGC": "serial",
                        "UseShenandoahGC": "shenandoah",
                    }
                    gc_hits.append(mapping[name])
                continue
            if name in OWNED_BOOL:
                values[name] = "true" if on else "false"
                continue
            extra.append(token)
            continue

        em = _XX_EQ_RE.match(token)
        if em:
            name = em.group("name")
            val = em.group("value")
            if name == "G1HeapRegionSize":
                # Accept 8m / 8M / 8388608 — store megabytes for the GUI.
                low = val.lower()
                if low.endswith("m"):
                    values[name] = low[:-1]
                elif low.endswith("g"):
                    values[name] = str(int(low[:-1]) * 1024)
                elif val.isdigit():
                    n = int(val)
                    values[name] = str(n // (1024 * 1024) if n >= 1024 * 1024 else n)
                else:
                    values[name] = val
                continue
            if name in OWNED_INT:
                values[name] = val
                continue
            extra.append(token)
            continue

        dm = _D_PROP_RE.match(token)
        if dm:
            name = dm.group("name")
            val = dm.group("value")
            if name == "file.encoding":
                values["file.encoding"] = val
                continue
            if name == "java.net.preferIPv4Stack":
                values["prefer_ipv4"] = "true" if val.lower() == "true" else "false"
                continue
            extra.append(token)
            continue

        extra.append(token)

    if gc_hits:
        values["gc"] = gc_hits[-1]
    values["lock_heap"] = "true" if values["xms"] == values["xmx"] else "false"
    values["extra"] = " ".join(extra)
    return values


def render_jvm_args(values: dict[str, Any]) -> str:
    """Render structured Tuner fields back to a JVM arg string."""
    parts: list[str] = []
    xms = str(values.get("xms") or "1G").strip().upper().replace(" ", "")
    xmx = str(values.get("xmx") or "2G").strip().upper().replace(" ", "")
    if str(values.get("lock_heap", "")).lower() in {"1", "true", "yes", "on"}:
        xmx = xms
    if not re.match(r"^\d+[KMG]$", xms, re.I):
        xms = "1G"
    if not re.match(r"^\d+[KMG]$", xmx, re.I):
        xmx = "2G"
    parts.append(f"-Xms{xms}")
    parts.append(f"-Xmx{xmx}")

    gc = str(values.get("gc") or "default").lower()
    gc_flag = {
        "g1": "-XX:+UseG1GC",
        "zgc": "-XX:+UseZGC",
        "parallel": "-XX:+UseParallelGC",
        "serial": "-XX:+UseSerialGC",
        "shenandoah": "-XX:+UseShenandoahGC",
    }.get(gc)
    if gc_flag:
        parts.append(gc_flag)

    for name in OWNED_INT:
        raw = str(values.get(name) or "").strip()
        if not raw:
            continue
        if name == "G1HeapRegionSize":
            parts.append(f"-XX:G1HeapRegionSize={raw}m")
        else:
            parts.append(f"-XX:{name}={raw}")

    for name in (
        "AlwaysPreTouch",
        "DisableExplicitGC",
        "ParallelRefProcEnabled",
        "PerfDisableSharedMem",
        "UseStringDeduplication",
        "UnlockExperimentalVMOptions",
    ):
        if str(values.get(name, "")).lower() in {"1", "true", "yes", "on"}:
            parts.append(f"-XX:+{name}")

    enc = str(values.get("file.encoding") or "").strip()
    if enc:
        parts.append(f"-Dfile.encoding={enc}")
    if str(values.get("prefer_ipv4", "")).lower() in {"1", "true", "yes", "on"}:
        parts.append("-Djava.net.preferIPv4Stack=true")

    extra = str(values.get("extra") or "").strip()
    if extra:
        parts.extend(_tokenize(extra))

    return " ".join(parts)


def field_schema_payload() -> dict[str, Any]:
    groups_order = ["memory", "collector", "g1", "stability", "extra"]
    by_group: dict[str, list[str]] = {g: [] for g in groups_order}
    for key, meta in FIELD_SCHEMA.items():
        group = str(meta.get("group") or "extra")
        by_group.setdefault(group, []).append(key)
    return {
        "groups": [
            {
                "id": gid,
                "label": GROUP_LABELS.get(gid, gid.title()),
                "keys": by_group.get(gid, []),
            }
            for gid in groups_order
            if by_group.get(gid)
        ],
        "fields": FIELD_SCHEMA,
        "presets": [
            {
                "id": pid,
                "label": meta["label"],
                "description": meta.get("description", ""),
                "values": meta["values"],
            }
            for pid, meta in PRESETS.items()
        ],
    }


def read_user_jvm_args_file(root: Path) -> str | None:
    path = root / "user_jvm_args.txt"
    if not path.is_file():
        return None
    lines: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        lines.append(stripped)
    return " ".join(lines) if lines else ""


def write_user_jvm_args_file(root: Path, jvm_args: str) -> None:
    path = root / "user_jvm_args.txt"
    tokens = _tokenize(jvm_args) or ["-Xms1G", "-Xmx2G"]
    path.write_text("\n".join(tokens) + "\n", encoding="utf-8")


def resolve_jvm_args(record: Any) -> tuple[str, str]:
    """Return (raw_args, source) preferring Forge user_jvm_args.txt when present."""
    root = Path(record.path)
    file_args = read_user_jvm_args_file(root)
    uses_argfile = "@user_jvm_args.txt" in (getattr(record, "execution_command", None) or "")
    if file_args is not None and (uses_argfile or file_args.strip()):
        return file_args, "user_jvm_args.txt"
    return getattr(record, "jvm_args", None) or "-Xms1G -Xmx2G", "catalog"


def apply_jvm_args(record: Any, jvm_args: str) -> Any:
    """Persist JVM args to catalog + Forge argfile when applicable."""
    cleaned = " ".join(_tokenize(jvm_args)) or "-Xms1G -Xmx2G"
    record.jvm_args = cleaned
    root = Path(record.path)
    uses_argfile = "@user_jvm_args.txt" in (getattr(record, "execution_command", None) or "")
    argfile = root / "user_jvm_args.txt"
    if uses_argfile or argfile.is_file():
        write_user_jvm_args_file(root, cleaned)
    return record
