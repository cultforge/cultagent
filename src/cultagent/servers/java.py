"""Java runtime detection (Crafty-inspired, original implementation)."""

from __future__ import annotations

import logging
import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger("cultagent.servers.java")

_VERSION_RE = re.compile(r'version "(?P<ver>[^"]+)"')


@dataclass(frozen=True)
class JavaRuntime:
    path: str
    version: str | None = None

    @property
    def major(self) -> int | None:
        return parse_java_major(self.version)


def parse_java_major(version: str | None) -> int | None:
    """Parse a Java version string into its major release (8, 17, 21, …)."""
    if not version:
        return None
    ver = version.strip()
    if ver.startswith("1."):
        parts = ver.split(".")
        if len(parts) >= 2 and parts[1].isdigit():
            return int(parts[1])
    match = re.match(r"(\d+)", ver)
    return int(match.group(1)) if match else None


def required_java_major(minecraft_version: str | None) -> int:
    """Minimum Java major version for a Minecraft release."""
    if not minecraft_version:
        return 17
    parts = str(minecraft_version).strip().split(".")
    try:
        minor = int(parts[1]) if len(parts) > 1 else 0
    except ValueError:
        return 17
    if minor >= 18:
        return 17
    if minor == 17:
        return 16
    if minor >= 1:
        return 8
    return 17


def java_requirement_message(
    *,
    minecraft_version: str | None,
    found: JavaRuntime | None,
) -> str:
    """Human-readable hint when Java is missing or too old."""
    need = required_java_major(minecraft_version)
    mc = minecraft_version or "this server"
    if found is None:
        return (
            f"Minecraft {mc} requires Java {need}+. "
            "Install Eclipse Temurin 17 or 21, then run "
            "`cf-agent java` or set servers.java_path in config.yaml."
        )
    found_major = found.major
    label = found.version or "unknown"
    return (
        f"Minecraft {mc} requires Java {need}+, but the selected runtime is "
        f"Java {label} ({found.path}). Install a newer JDK and run `cf-agent java`, "
        "or set servers.java_path to the java.exe path."
        + (f" Detected major={found_major}." if found_major is not None else "")
    )


def _probe(path: str) -> JavaRuntime | None:
    try:
        completed = subprocess.run(
            [path, "-version"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    blob = (completed.stderr or "") + (completed.stdout or "")
    match = _VERSION_RE.search(blob)
    version = match.group("ver") if match else None
    return JavaRuntime(path=path, version=version)


def _java_candidate_paths() -> list[str]:
    candidates: list[str] = []
    java_home = os.environ.get("JAVA_HOME", "").strip()
    if java_home:
        bin_name = "java.exe" if os.name == "nt" else "java"
        candidates.append(str(Path(java_home) / "bin" / bin_name))

    which = shutil.which("java")
    if which:
        candidates.append(which)

    search_roots: list[Path] = []
    if os.name == "nt":
        search_roots.extend(
            [
                Path(os.environ.get("ProgramFiles", r"C:\Program Files")),
                Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")),
            ]
        )
        local = os.environ.get("LOCALAPPDATA", "").strip()
        if local:
            search_roots.append(Path(local) / "Programs")

    for root in search_roots:
        if not root.is_dir():
            continue
        for vendor in (
            "Java",
            "Eclipse Adoptium",
            "Microsoft",
            "Zulu",
            "BellSoft",
        ):
            base = root / vendor
            if not base.is_dir():
                continue
            pattern = "**/bin/java.exe" if os.name == "nt" else "**/bin/java"
            for java_bin in base.glob(pattern):
                candidates.append(str(java_bin))

    return candidates


def detect_java(
    preferred: str | None = None,
    *,
    min_major: int | None = None,
) -> JavaRuntime | None:
    """Resolve the best usable java executable.

    Scans explicit path, JAVA_HOME, PATH, and common install locations, then
    returns the highest major version found (optionally filtered by ``min_major``).
    """
    candidates: list[str] = []
    if preferred and preferred.strip():
        candidates.append(preferred.strip())
    candidates.extend(_java_candidate_paths())

    seen: set[str] = set()
    runtimes: list[JavaRuntime] = []
    for candidate in candidates:
        key = os.path.normcase(os.path.abspath(candidate))
        if key in seen:
            continue
        seen.add(key)
        if not Path(candidate).is_file() and shutil.which(candidate) is None:
            continue
        runtime = _probe(candidate)
        if runtime is not None:
            runtimes.append(runtime)

    if not runtimes:
        logger.warning("No Java runtime detected")
        return None

    runtimes.sort(key=lambda r: r.major or 0, reverse=True)
    chosen = runtimes[0]
    if min_major is not None:
        for runtime in runtimes:
            major = runtime.major
            if major is not None and major >= min_major:
                chosen = runtime
                break
        else:
            logger.warning(
                "Java %s at %s is below required %s+",
                chosen.version,
                chosen.path,
                min_major,
            )
            return None

    logger.info("Detected Java %s at %s", chosen.version, chosen.path)
    return chosen
