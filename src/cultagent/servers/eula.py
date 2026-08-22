"""EULA helpers for Minecraft Java servers."""

from __future__ import annotations

from pathlib import Path

EULA_FILE = "eula.txt"


def eula_path(server_dir: Path) -> Path:
    return server_dir / EULA_FILE


def is_eula_accepted(server_dir: Path) -> bool:
    path = eula_path(server_dir)
    if not path.is_file():
        return False
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        cleaned = line.strip().lower().replace(" ", "")
        if cleaned.startswith("#"):
            continue
        if cleaned == "eula=true":
            return True
    return False


def write_eula(server_dir: Path, *, accepted: bool) -> Path:
    path = eula_path(server_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    value = "true" if accepted else "false"
    path.write_text(
        "#By changing the setting below to TRUE you are indicating your agreement "
        "to our EULA (https://aka.ms/MinecraftEULA).\n"
        f"eula={value}\n",
        encoding="utf-8",
    )
    return path
