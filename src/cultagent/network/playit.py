"""playit.gg agent — official binary install, secret storage, process supervision.

Managed pin: **v0.17.1** (non-deprecated alongside 1.0.X). The 0.17 CLI includes
``claim generate|exchange`` and ``reset``; 1.0.x GitHub builds are daemon-only and
wait for a desktop frontend over IPC.

  playit --secret_path <playit.toml> -l <playit.log> start

Secret format: hex key, raw or ``secret_key = "…"`` in a ``.toml`` file.
"""

from __future__ import annotations

import json
import logging
import os
import platform
import re
import stat
import subprocess
import time
from collections import deque
from pathlib import Path
from typing import Any

import httpx

from cultagent.network.playit_api import (
    PlayitApiError,
    ensure_minecraft_java_tunnel,
    fetch_public_join,
)
from cultagent.network.types import NetworkStatus, TunnelState

logger = logging.getLogger("cultagent.network.playit")

# Prefer 0.17.1 for claim generate/exchange/reset (README: 0.17.1 and 1.0.X).
PLAYIT_RELEASE_REPO = "playit-cloud/playit-agent"
PLAYIT_RELEASE_TAG = "v0.17.1"
GITHUB_TAG = f"https://api.github.com/repos/{PLAYIT_RELEASE_REPO}/releases/tags/{PLAYIT_RELEASE_TAG}"
USER_AGENT = "CultForge-Agent/0.1 (cf-agent; +https://cultforge.com)"

# Official setup entry points (no mock UI).
SETUP_CLAIM_CODE_PAGE = (
    "https://playit.gg/account/setup/wizard/new-account/computer/claim-code"
)
SETUP_SECRET_URL = "https://playit.gg/account/setup/wizard/new-account/docker/docker-name"
CLAIM_URL_PREFIX = "https://playit.gg/claim/"
DOWNLOAD_URL = "https://playit.gg/download"
DOWNLOAD_MAC_URL = "https://playit.gg/download/macos"
AGENTS_URL = "https://playit.gg/account/agents"
SUPPORT_URL = "https://playit.gg/support/"
SUPPORT_LINUX = "https://playit.gg/support/how-to-run-playit-gg-on-linux/"
SUPPORT_LINUX_247 = "https://playit.gg/support/how-to-run-playit-24-7-on-linux/"
SUPPORT_VCRUNTIME = "https://playit.gg/support/vcruntime140-dll-was-not-found/"
SUPPORT_DNS_WINDOWS = "https://playit.gg/support/update-your-dns-server-on-windows/"
SUPPORT_DNS_LINUX = "https://playit.gg/support/update-your-dns-server-on-linux/"
SUPPORT_DNS_MACOS = "https://playit.gg/support/update-your-dns-server-on-macos/"
SUPPORT_MC_UNKNOWN_HOST = "https://playit.gg/support/fixing-unknown-host-in-minecraft-java/"
SUPPORT_MC_TIMEOUT = "https://playit.gg/support/fixing-timeout-errors-with-minecraft/"
SUPPORT_PAPER = "https://playit.gg/support/setup-a-papermc-minecraft-server/"
VC_REDIST_URL = "https://learn.microsoft.com/en-us/cpp/windows/latest-supported-vc-redist"
PLAYIT_SOURCE_URL = "https://github.com/playit-cloud/playit-agent"

# Back-compat aliases
SETUP_CLAIM_URL = CLAIM_URL_PREFIX.rstrip("/")  # base; prefer claim_url_for(code)
SETUP_CLAIM_WIZARD = SETUP_CLAIM_CODE_PAGE

_CLAIM_RE = re.compile(r"https?://(?:www\.)?playit\.gg/\S*claim\S*", re.I)
_CLAIM_CODE_RE = re.compile(r"(?<![0-9a-fA-F])([0-9a-f]{10})(?![0-9a-fA-F])")
_PLY_RE = re.compile(
    r"\b([a-z0-9][-a-z0-9]*\.(?:ply\.gg|playit\.gg|joinmc\.link)(?::\d+)?)\b",
    re.I,
)
_HEX_SECRET_RE = re.compile(r"^[0-9a-fA-F]{32,}$")
_HEX_SECRET_FIND_RE = re.compile(r"(?<![0-9a-fA-F])([0-9a-fA-F]{64})(?![0-9a-fA-F])")
_TOML_SECRET_RE = re.compile(
    r"""secret_key\s*=\s*["']([0-9a-fA-F]{32,})["']""",
    re.I,
)
_ANSI_RE = re.compile(r"\x1b\[[0-9;]*[A-Za-z]|\x1b\].*?(?:\x07|\x1b\\)|\x1b.")

_CREATE_NO_WINDOW = 0x08000000
_CREATE_NEW_PROCESS_GROUP = 0x00000200


def strip_ansi(text: str) -> str:
    return _ANSI_RE.sub("", text or "")


def claim_url_for(code: str) -> str:
    return f"{CLAIM_URL_PREFIX}{code.strip().lower()}"


def parse_claim_code(text: str) -> str | None:
    plain = strip_ansi(text)
    m = _CLAIM_CODE_RE.search(plain)
    return m.group(1).lower() if m else None


def parse_hex_secret(text: str) -> str | None:
    plain = strip_ansi(text)
    toml = _TOML_SECRET_RE.search(plain)
    if toml:
        return toml.group(1).lower()
    m = _HEX_SECRET_FIND_RE.search(plain)
    return m.group(1).lower() if m else None


def _popen_kwargs() -> dict[str, Any]:
    kwargs: dict[str, Any] = {
        "stdin": subprocess.DEVNULL,
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
    }
    if platform.system() == "Windows":
        kwargs["creationflags"] = _CREATE_NO_WINDOW | _CREATE_NEW_PROCESS_GROUP
    else:
        kwargs["start_new_session"] = True
    return kwargs


def _run_playit(
    binary: Path,
    args: list[str],
    *,
    cwd: Path | None = None,
    timeout: float | None = 30,
) -> subprocess.CompletedProcess[str]:
    kwargs: dict[str, Any] = {
        "args": [str(binary), *args],
        "capture_output": True,
        "text": True,
        "encoding": "utf-8",
        "errors": "replace",
        "timeout": timeout,
        "cwd": str(cwd) if cwd else None,
    }
    if platform.system() == "Windows":
        kwargs["creationflags"] = _CREATE_NO_WINDOW
    return subprocess.run(**kwargs)


def platform_asset_name() -> str | None:
    """GitHub release asset for this OS/arch, or None if not published.

    Windows + Linux have official release binaries. macOS currently does not
    (see playit.gg/download/macos and playit-cloud/playit-agent#97) — users
    compile from source or set ``network.playit.binary_path``.
    """
    system = platform.system().lower()
    machine = platform.machine().lower()
    if system == "windows":
        if machine in {"amd64", "x86_64", "x64"}:
            return "playit-windows-x86_64.exe"
        if machine in {"x86", "i386", "i686"}:
            return "playit-windows-x86.exe"
        return "playit-windows-x86_64.exe"
    if system == "linux":
        if machine in {"aarch64", "arm64"}:
            return "playit-linux-aarch64"
        if machine in {"armv7l", "armv7"}:
            return "playit-linux-armv7"
        if machine in {"i386", "i686", "x86"}:
            return "playit-linux-i686"
        return "playit-linux-amd64"
    if system == "darwin":
        return None
    return None


def discover_system_playit() -> Path | None:
    """Find a user/system-installed playit on PATH or common install dirs."""
    import shutil

    for name in ("playit", "playit.exe", "playitd"):
        found = shutil.which(name)
        if found:
            return Path(found)

    system = platform.system().lower()
    candidates: list[Path] = []
    if system == "windows":
        local = Path(os.environ.get("LOCALAPPDATA", ""))
        prog = Path(os.environ.get("ProgramFiles", r"C:\Program Files"))
        candidates.extend(
            [
                local / "playit_gg" / "playit.exe",
                local / "Programs" / "playit" / "playit.exe",
                prog / "playit" / "playit.exe",
                prog / "Developed Methods" / "playit" / "playit.exe",
            ]
        )
    elif system == "linux":
        candidates.extend(
            [
                Path("/usr/bin/playit"),
                Path("/usr/local/bin/playit"),
                Path.home() / ".local" / "bin" / "playit",
            ]
        )
    elif system == "darwin":
        candidates.extend(
            [
                Path("/usr/local/bin/playit"),
                Path("/opt/homebrew/bin/playit"),
                Path.home() / ".cargo" / "bin" / "playit",
            ]
        )
    for path in candidates:
        if path.is_file():
            return path
    return None


def platform_profile() -> dict[str, Any]:
    """Cross-platform install + support guidance (Windows / Linux / macOS)."""
    system = platform.system()
    machine = platform.machine()
    asset = platform_asset_name()
    base = {
        "os": system,
        "arch": machine,
        "asset": asset,
        "managed_download": asset is not None,
        "support_hub": SUPPORT_URL,
        "setup_claim_url": CLAIM_URL_PREFIX.rstrip("/"),
        "setup_claim_code_page": SETUP_CLAIM_CODE_PAGE,
        "setup_secret_url": SETUP_SECRET_URL,
        "agents_url": AGENTS_URL,
        "download_url": DOWNLOAD_URL,
        "mc_unknown_host": SUPPORT_MC_UNKNOWN_HOST,
        "mc_timeout": SUPPORT_MC_TIMEOUT,
        "paper_guide": SUPPORT_PAPER,
    }
    if system == "Windows":
        return {
            **base,
            "platform": "windows",
            "install_methods": [
                "cf-agent playit-setup (GitHub release binary + claim wizard)",
                "winget install DevelopedMethods.playit",
                f"Installer from {DOWNLOAD_URL}",
            ],
            "notes": [
                "If playit fails with VCRUNTIME140.dll missing, install the MS VC++ redistributable.",
                "CultAgent uses a private named pipe (\\\\.\\pipe\\cultagent-playit) so it won't fight the desktop app.",
            ],
            "docs": {
                "vcruntime": SUPPORT_VCRUNTIME,
                "vc_redist": VC_REDIST_URL,
                "dns": SUPPORT_DNS_WINDOWS,
                "download": DOWNLOAD_URL,
            },
        }
    if system == "Linux":
        return {
            **base,
            "platform": "linux",
            "install_methods": [
                "cf-agent playit-setup (GitHub release binary + claim wizard)",
                "apt: playit-cloud PPA then `sudo apt install playit` "
                f"(see {SUPPORT_LINUX})",
                "systemd 24/7: systemctl enable --now playit "
                f"(see {SUPPORT_LINUX_247})",
            ],
            "notes": [
                "Prefer CultAgent-managed binary + playit.toml for guild hosts.",
                "If you use distro systemd playit, point binary_path at /usr/bin/playit "
                "or keep CultAgent's isolated socket under the data dir.",
            ],
            "docs": {
                "linux_install": SUPPORT_LINUX,
                "linux_247": SUPPORT_LINUX_247,
                "dns": SUPPORT_DNS_LINUX,
                "download": DOWNLOAD_URL,
            },
            "apt_snippet": (
                "curl -SsL https://playit-cloud.github.io/ppa/key.gpg | "
                "gpg --dearmor | sudo tee /etc/apt/trusted.gpg.d/playit.gpg >/dev/null\n"
                'echo "deb [signed-by=/etc/apt/trusted.gpg.d/playit.gpg] '
                'https://playit-cloud.github.io/ppa/data ./" | '
                "sudo tee /etc/apt/sources.list.d/playit-cloud.list\n"
                "sudo apt update && sudo apt install playit"
            ),
        }
    if system == "Darwin":
        return {
            **base,
            "platform": "macos",
            "install_methods": [
                f"No official GitHub binary yet — see {DOWNLOAD_MAC_URL}",
                f"Compile from source: {PLAYIT_SOURCE_URL}",
                "Or run playit via Docker with SECRET_KEY, then set binary_path if needed",
                "After building, set network.playit.binary_path to the playit binary",
            ],
            "notes": [
                "playit.gg documents macOS as compile-from-source until official builds ship.",
                "CultAgent still manages secret (playit.toml), start/stop, and join address once binary_path is set.",
            ],
            "docs": {
                "macos_download": DOWNLOAD_MAC_URL,
                "source": PLAYIT_SOURCE_URL,
                "dns": SUPPORT_DNS_MACOS,
                "support": SUPPORT_URL,
            },
            "download_url": DOWNLOAD_MAC_URL,
        }
    return {
        **base,
        "platform": "unknown",
        "install_methods": [f"See {SUPPORT_URL}"],
        "notes": [f"Unsupported OS for managed download: {system}"],
        "docs": {"support": SUPPORT_URL},
    }

def normalize_secret(raw: str) -> str:
    """Accept pasted hex key or playit.toml fragment; return bare hex secret."""
    text = (raw or "").strip()
    if not text:
        raise ValueError("secret key is empty")
    low = text.lower()
    if "playit.gg/claim" in low or low.startswith("http://") or low.startswith("https://"):
        raise ValueError(
            "That looks like a claim URL, not the secret. "
            "Keep the claim page open and let cf-agent finish waiting "
            "(playit-setup runs `claim exchange`). "
            f"Only paste a long hex key — see {SETUP_SECRET_URL}"
        )
    # pasted toml
    m = _TOML_SECRET_RE.search(text)
    if m:
        text = m.group(1)
    # strip quotes / whitespace
    text = text.strip().strip("\"'")
    if text.lower().startswith("secret_key"):
        raise ValueError("could not parse secret_key from input")
    # bare 10-char claim code is also not a secret
    if _CLAIM_CODE_RE.fullmatch(text.lower()):
        raise ValueError(
            "That looks like a claim code, not the hex secret. "
            "Approve the claim in your browser while playit-setup waits."
        )
    if not _HEX_SECRET_RE.match(text):
        raise ValueError(
            "playit secret must be a hex key from playit.gg setup "
            f"(see {SETUP_SECRET_URL})"
        )
    return text.lower()


def default_socket_path(root: Path) -> str:
    """IPC path so CultAgent's playit does not collide with the desktop app."""
    if platform.system() == "Windows":
        return r"\\.\pipe\cultagent-playit"
    return str((root / "playit.sock").resolve())


class PlayitAgent:
    """Manage the official playit binary under the CultAgent data directory."""

    def __init__(
        self,
        root: Path,
        *,
        target_host: str = "127.0.0.1",
        target_port: int = 25565,
        binary_override: str = "",
        auto_start: bool = False,
        enabled: bool = False,
    ) -> None:
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.target_host = target_host
        self.target_port = int(target_port)
        self.binary_override = binary_override.strip()
        self.auto_start = auto_start
        self.enabled = enabled

        self.secret_path = self.root / "playit.toml"
        self.legacy_secret_path = self.root / "secret.key"
        self.state_path = self.root / "state.json"
        self.log_path = self.root / "playit.log"
        self.bin_dir = self.root / "bin"
        self.bin_dir.mkdir(parents=True, exist_ok=True)
        self.socket_path = default_socket_path(self.root)

        self._pid: int | None = None
        self._lines: deque[str] = deque(maxlen=400)
        self._claim_url: str | None = None
        self._claim_code: str | None = None
        self._public_hints: list[str] = []
        self._last_error: str | None = None
        self._started_at: float | None = None
        self._tunnel_count: int | None = None
        self._cli_kind: str | None = None
        self._public_join: str | None = None
        self._public_join_checked_at: float = 0.0

        state = self.load_state()
        if isinstance(state.get("pid"), int):
            self._pid = int(state["pid"])
        if state.get("public_endpoint"):
            self._public_join = str(state["public_endpoint"])
        elif state.get("public_join"):
            self._public_join = str(state["public_join"])
    @property
    def target(self) -> str:
        return f"{self.target_host}:{self.target_port}"

    def binary_path(self) -> Path | None:
        if self.binary_override:
            p = Path(self.binary_override)
            return p if p.is_file() else None
        preferred = platform_asset_name()
        if preferred:
            candidate = self.bin_dir / preferred
            if candidate.is_file():
                return candidate
        for path in sorted(self.bin_dir.glob("playit*")):
            if path.is_file():
                return path
        return discover_system_playit()

    def supports_claim_cli(self, binary: Path | None = None) -> bool:
        path = binary or self.binary_path()
        if path is None:
            return False
        if self._cli_kind == "claim":
            return True
        if self._cli_kind == "daemon":
            return False
        try:
            result = _run_playit(path, ["claim", "--help"], timeout=12)
            out = (result.stdout or "") + (result.stderr or "")
            ok = "generate" in out.lower()
            self._cli_kind = "claim" if ok else "daemon"
            return ok
        except Exception:  # noqa: BLE001
            self._cli_kind = "daemon"
            return False

    def has_secret(self) -> bool:
        return self.read_secret() is not None

    def read_secret(self) -> str | None:
        for path in (self.secret_path, self.legacy_secret_path):
            if not path.is_file() or path.stat().st_size == 0:
                continue
            try:
                return normalize_secret(path.read_text(encoding="utf-8"))
            except ValueError:
                continue
        return None

    def write_secret(self, secret: str) -> None:
        hex_key = normalize_secret(secret)
        content = f'secret_key = "{hex_key}"\n'
        self.secret_path.write_text(content, encoding="utf-8")
        try:
            os.chmod(self.secret_path, stat.S_IRUSR | stat.S_IWUSR)
        except OSError:
            pass
        if self.legacy_secret_path.is_file():
            try:
                self.legacy_secret_path.unlink()
            except OSError:
                pass

    def clear_secret(self) -> None:
        for path in (self.secret_path, self.legacy_secret_path):
            if path.is_file():
                path.unlink()

    def _save_state(self, **extra: Any) -> None:
        payload = {
            **self.load_state(),
            "enabled": self.enabled,
            "auto_start": self.auto_start,
            "target_host": self.target_host,
            "target_port": self.target_port,
            "binary_override": self.binary_override,
            "updated_at": time.time(),
            **extra,
        }
        self.state_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    def load_state(self) -> dict[str, Any]:
        if not self.state_path.is_file():
            return {}
        try:
            data = json.loads(self.state_path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except Exception:  # noqa: BLE001
            return {}

    async def install(self, *, force: bool = False, pin_tag: bool = True) -> dict[str, Any]:
        """Download pinned playit release (0.17.1 — claim CLI)."""
        profile = platform_profile()
        asset = platform_asset_name()
        if not asset:
            system_bin = discover_system_playit()
            raise RuntimeError(
                f"No managed playit release binary for {profile['os']}/{profile['arch']}. "
                + (
                    f"Found system binary at {system_bin} — set network.playit.binary_path. "
                    if system_bin
                    else ""
                )
                + " ".join(profile.get("install_methods") or [])
                + f" Support: {SUPPORT_URL}"
            )
        dest = self.bin_dir / asset
        if dest.is_file() and not force and self.supports_claim_cli(dest):
            return {
                "ok": True,
                "path": str(dest),
                "asset": asset,
                "downloaded": False,
                "note": "already installed (claim CLI)",
                "tag": PLAYIT_RELEASE_TAG,
                "vendor": PLAYIT_RELEASE_REPO,
                "platform": profile,
            }
        # Re-download if force, missing, or daemon-only 1.0.x without claim.
        if dest.is_file() and (force or not self.supports_claim_cli(dest)):
            # Stop first so Windows can overwrite the binary.
            await self.stop()
            try:
                dest.unlink()
            except OSError as exc:
                raise RuntimeError(
                    f"Cannot replace playit binary (still locked): {exc}. "
                    "Run: cf-agent playit-reset  then retry playit-setup --force"
                ) from exc

        async with httpx.AsyncClient(timeout=120.0, follow_redirects=True) as client:
            meta = (
                await client.get(
                    GITHUB_TAG,
                    headers={"Accept": "application/vnd.github+json", "User-Agent": USER_AGENT},
                )
            ).raise_for_status().json()
            assets = meta.get("assets") or []
            match = next((a for a in assets if a.get("name") == asset), None)
            if not match or not match.get("browser_download_url"):
                raise RuntimeError(f"Release asset not found: {asset} ({meta.get('tag_name')})")
            url = str(match["browser_download_url"])
            async with client.stream("GET", url, headers={"User-Agent": USER_AGENT}) as resp:
                resp.raise_for_status()
                dest.parent.mkdir(parents=True, exist_ok=True)
                with dest.open("wb") as fh:
                    async for chunk in resp.aiter_bytes():
                        fh.write(chunk)

        try:
            os.chmod(dest, dest.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
        except OSError:
            pass

        self._cli_kind = None
        self._save_state(installed_asset=asset, tag=meta.get("tag_name"))
        return {
            "ok": True,
            "path": str(dest),
            "asset": asset,
            "tag": meta.get("tag_name"),
            "downloaded": True,
            "size": dest.stat().st_size,
            "vendor": PLAYIT_RELEASE_REPO,
            "download_page": DOWNLOAD_URL,
            "platform": profile,
        }

    def generate_claim_code(self) -> dict[str, str]:
        binary = self.binary_path()
        if binary is None:
            raise RuntimeError("playit binary missing — run playit-setup first")
        if not self.supports_claim_cli(binary):
            raise RuntimeError(
                "This playit binary has no `claim` CLI (daemon-only 1.0.x). "
                "Run: cf-agent playit-setup --force  to install v0.17.1"
            )
        result = _run_playit(binary, ["claim", "generate"], cwd=self.root, timeout=20)
        raw = (result.stdout or "") + (result.stderr or "")
        code = parse_claim_code(raw)
        if not code:
            raise RuntimeError("playit claim generate did not return a claim code")
        url = claim_url_for(code)
        self._claim_code = code
        self._claim_url = url
        self._save_state(claim_code=code, claim_url=url)
        return {"claim_code": code, "claim_url": url}

    async def setup(
        self,
        *,
        force: bool = False,
        open_browser: bool = True,
        wait_exchange: bool = True,
        exchange_timeout: float = 300,
    ) -> dict[str, Any]:
        """Download binary, generate claim code, open claim URL, wait for exchange.

        The playit.gg claim page shows "Waiting for agent…" until ``claim exchange``
        runs for the same code — that is the agent side, not a pasted secret.
        """
        import asyncio

        profile = platform_profile()
        if platform_asset_name():
            install_result = await self.install(force=force)
        else:
            binary = self.binary_path()
            if binary is None:
                raise RuntimeError(
                    f"No managed playit binary for {profile['os']}/{profile['arch']}. "
                    + " ".join(profile.get("install_methods") or [])
                )
            install_result = {
                "ok": True,
                "path": str(binary),
                "downloaded": False,
                "note": "using existing binary_path / PATH binary",
                "platform": profile,
            }

        claim: dict[str, str] | None = None
        try:
            claim = self.generate_claim_code()
        except Exception as exc:  # noqa: BLE001
            logger.warning("claim generate failed: %s", exc)
            claim = None

        setup_url = claim["claim_url"] if claim else SETUP_CLAIM_CODE_PAGE
        opened = False
        if open_browser:
            import webbrowser

            try:
                opened = bool(webbrowser.open(setup_url, new=2))
            except Exception as exc:  # noqa: BLE001
                logger.warning("could not open claim browser: %s", exc)

        exchanged = False
        exchange_error: str | None = None
        if wait_exchange and claim:
            try:
                secret = await asyncio.to_thread(
                    self.exchange_claim,
                    claim["claim_code"],
                    timeout=exchange_timeout,
                )
                if secret:
                    self.write_secret(secret)
                    exchanged = True
                else:
                    exchange_error = "claim exchange finished without a secret (timeout?)"
            except Exception as exc:  # noqa: BLE001
                exchange_error = str(exc)
                logger.warning("claim exchange failed: %s", exc)

        self._save_state(
            setup_url=setup_url,
            browser_opened=opened,
            claim_code=(claim or {}).get("claim_code"),
            claim_url=(claim or {}).get("claim_url"),
        )
        next_steps: list[str] = []
        if exchanged:
            next_steps = [
                "Claim complete — secret stored",
                "cf-agent playit-start  (auto-creates Minecraft Java tunnel)",
            ]
        elif claim:
            next_steps = [
                f"Claim code: {claim['claim_code']}",
                f"Keep open: {claim['claim_url']}",
                "The page waits for the agent — run: cf-agent playit-claim",
                "Do NOT paste the claim URL as a secret",
            ]
        else:
            next_steps = [
                f"Open {SETUP_SECRET_URL} for a docker-style hex secret",
                "cf-agent playit-secret",
                "cf-agent playit-start",
            ]
        return {
            **install_result,
            "ok": True,
            "setup_url": setup_url,
            "claim_code": (claim or {}).get("claim_code"),
            "claim_url": (claim or {}).get("claim_url"),
            "secret_wizard_url": SETUP_SECRET_URL,
            "agents_url": AGENTS_URL,
            "browser_opened": opened,
            "has_secret": self.has_secret(),
            "claim_exchanged": exchanged,
            "exchange_error": exchange_error,
            "next_steps": next_steps,
        }

    def _harvest_secret_files(self) -> str | None:
        """Read secret from CultAgent path or playit's default LocalAppData path."""
        candidates = [self.secret_path, self.legacy_secret_path]
        local = os.environ.get("LOCALAPPDATA") or os.environ.get("HOME") or ""
        if local:
            candidates.append(Path(local) / "playit_gg" / "playit.toml")
        for path in candidates:
            if not path.is_file() or path.stat().st_size == 0:
                continue
            try:
                return normalize_secret(path.read_text(encoding="utf-8"))
            except ValueError:
                continue
        return None

    def exchange_claim(self, code: str, *, timeout: float = 300) -> str | None:
        """Run ``playit claim exchange`` — this is what the claim page waits for."""
        binary = self.binary_path()
        if binary is None:
            raise RuntimeError("playit binary missing")
        code = code.strip().lower()
        wait_sec = max(1, int(timeout))
        raw = ""
        try:
            result = _run_playit(
                binary,
                ["claim", "exchange", "--wait", str(wait_sec), code],
                cwd=self.root,
                timeout=timeout + 20,
            )
            raw = (result.stdout or "") + (result.stderr or "")
        except subprocess.TimeoutExpired as exc:
            if exc.stdout:
                raw += (
                    exc.stdout
                    if isinstance(exc.stdout, str)
                    else exc.stdout.decode("utf-8", errors="replace")
                )
            if exc.stderr:
                raw += (
                    exc.stderr
                    if isinstance(exc.stderr, str)
                    else exc.stderr.decode("utf-8", errors="replace")
                )
        secret = parse_hex_secret(raw) or self._harvest_secret_files()
        return secret

    async def wait_claim(
        self,
        code: str | None = None,
        *,
        timeout: float = 300,
    ) -> dict[str, Any]:
        """Resume waiting for an existing claim code (browser already open)."""
        import asyncio

        code = (code or self._claim_code or self.load_state().get("claim_code") or "").strip()
        if not code:
            raise RuntimeError(
                "No claim code — run cf-agent playit-setup first "
                "(generates a code and opens the claim page)"
            )
        url = claim_url_for(code)
        self._claim_code = code
        self._claim_url = url
        secret = await asyncio.to_thread(self.exchange_claim, code, timeout=timeout)
        if not secret:
            return {
                "ok": False,
                "claim_code": code,
                "claim_url": url,
                "has_secret": self.has_secret(),
                "error": "claim not completed yet — keep the browser tab open and retry",
            }
        self.write_secret(secret)
        self._save_state(claim_code=code, claim_url=url)
        return {
            "ok": True,
            "claim_code": code,
            "claim_url": url,
            "has_secret": True,
            "claim_exchanged": True,
        }

    def is_running(self) -> bool:
        pid = self._pid
        if pid is None:
            st = self.load_state().get("pid")
            if isinstance(st, int):
                pid = st
                self._pid = pid
        if not pid:
            return False
        try:
            import psutil

            proc = psutil.Process(int(pid))
            if not proc.is_running() or proc.status() == psutil.STATUS_ZOMBIE:
                return False
            name = (proc.name() or "").lower()
            return "playit" in name
        except Exception:  # noqa: BLE001
            return False

    def _launch_args(self, *, secret: str) -> list[str]:
        binary = self.binary_path()
        assert binary is not None
        self.write_secret(secret)
        if self.supports_claim_cli(binary):
            # 0.17.x: underscore flags + start subcommand
            return [
                "--secret_path",
                str(self.secret_path),
                "-l",
                str(self.log_path),
                "start",
            ]
        # 1.0.x daemon flags
        return [
            "--secret-path",
            str(self.secret_path),
            "-l",
            str(self.log_path),
            "--socket-path",
            self.socket_path,
        ]

    def _remember_public_join(self, address: str | None, **extra: Any) -> None:
        if not address:
            return
        addr = str(address).strip()
        if not addr:
            return
        self._public_join = addr
        self._public_join_checked_at = time.time()
        if addr not in self._public_hints:
            self._public_hints.append(addr)
            if len(self._public_hints) > 8:
                self._public_hints = self._public_hints[-8:]
        self._save_state(public_join=addr, public_endpoint=addr, **extra)

    async def refresh_public_join(self, *, force: bool = False, max_age: float = 45.0) -> str | None:
        """Pull public join from playit API and cache it for status / panel."""
        if self._public_join and not force:
            age = time.time() - self._public_join_checked_at
            if age < max_age:
                return self._public_join
        secret = self.read_secret()
        if not secret:
            return self._public_join
        try:
            info = await fetch_public_join(secret)
        except Exception as exc:  # noqa: BLE001
            logger.debug("public join refresh failed: %s", exc)
            return self._public_join or (self.load_state().get("public_join") or self.load_state().get("public_endpoint"))
        public = info.get("public_join") or info.get("public_endpoint")
        if info.get("tunnel_count") is not None:
            self._tunnel_count = int(info["tunnel_count"])
        if public:
            self._remember_public_join(
                str(public),
                tunnel_id=info.get("tunnel_id"),
                tunnel_count=info.get("tunnel_count"),
            )
        else:
            self._public_join_checked_at = time.time()
        return self._public_join

    async def ensure_minecraft_tunnel(self, *, wait_seconds: float = 8.0) -> dict[str, Any]:
        """Create or fix Minecraft Java tunnel via playit API → target_host:target_port."""
        secret = self.read_secret()
        if not secret:
            raise RuntimeError(
                "playit secret missing — run cf-agent playit-setup first"
            )
        try:
            result = await ensure_minecraft_java_tunnel(
                secret,
                host=self.target_host,
                port=self.target_port,
                wait_seconds=wait_seconds,
            )
        except PlayitApiError as exc:
            raise RuntimeError(f"playit tunnel API: {exc}") from exc
        public = result.get("public_endpoint") or result.get("public_join")
        if public:
            self._remember_public_join(
                str(public),
                tunnel_id=result.get("tunnel_id"),
                tunnel_count=result.get("tunnel_count"),
            )
        elif result.get("tunnel_count") is not None:
            self._tunnel_count = int(result["tunnel_count"])
            self._save_state(
                tunnel_id=result.get("tunnel_id"),
                tunnel_count=result.get("tunnel_count"),
            )
        result["public_join"] = self._public_join
        result["public_endpoint"] = self._public_join
        return result
    async def start(self, *, ensure_tunnel: bool = True) -> dict[str, Any]:
        if self.is_running():
            out: dict[str, Any] = {
                "ok": True,
                "already_running": True,
                **(await self.status_dict()),
            }
            if ensure_tunnel:
                try:
                    tunnel = await self.ensure_minecraft_tunnel()
                    out["tunnel"] = tunnel
                    if tunnel.get("public_endpoint"):
                        out["public_endpoint"] = tunnel["public_endpoint"]
                except Exception as exc:  # noqa: BLE001
                    out["tunnel_error"] = str(exc)
                    logger.warning("playit tunnel ensure failed: %s", exc)
            return out

        binary = self.binary_path()
        if binary is None:
            raise RuntimeError("playit binary missing — run playit-setup first")
        secret = self.read_secret()
        if not secret:
            raise RuntimeError(
                "playit secret missing — run cf-agent playit-setup (claim code), "
                f"or paste a hex key from {SETUP_SECRET_URL}"
            )

        tunnel_info: dict[str, Any] | None = None
        tunnel_error: str | None = None
        if ensure_tunnel:
            try:
                tunnel_info = await self.ensure_minecraft_tunnel()
            except Exception as exc:  # noqa: BLE001
                tunnel_error = str(exc)
                logger.warning("playit tunnel ensure failed: %s", exc)

        self._lines.clear()
        self._claim_url = None
        self._last_error = None
        try:
            self.log_path.write_text("", encoding="utf-8")
        except OSError:
            pass

        args = [str(binary), *self._launch_args(secret=secret)]
        env = {
            k: v
            for k, v in os.environ.items()
            if k not in {"SECRET_KEY", "PLAYIT_SECRET_KEY"}
        }
        popen = subprocess.Popen(  # noqa: S603 — managed vendor binary
            args,
            cwd=str(self.root),
            env=env,
            **_popen_kwargs(),
        )
        # Detach: do not keep pipe transports (avoids Windows asyncio ResourceWarning).
        self._pid = popen.pid
        self._started_at = time.time()
        self.enabled = True
        self._save_state(pid=self._pid, socket_path=self.socket_path)
        logger.info("playit started pid=%s target=%s", self._pid, self.target)
        # Give process a moment; status scrapes log file.
        time.sleep(0.6)
        status = await self.status_dict()
        out = {"ok": True, "pid": self._pid, **status}
        if tunnel_info is not None:
            out["tunnel"] = tunnel_info
            if tunnel_info.get("public_endpoint"):
                out["public_endpoint"] = tunnel_info["public_endpoint"]
        if tunnel_error:
            out["tunnel_error"] = tunnel_error
        return out

    def _kill_pid(self, pid: int) -> bool:
        try:
            import psutil

            proc = psutil.Process(pid)
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except psutil.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=3)
            return True
        except Exception:  # noqa: BLE001
            return False

    def _kill_named_playit(self) -> list[int]:
        killed: list[int] = []
        try:
            import psutil

            binary = self.binary_path()
            for proc in psutil.process_iter(["pid", "name", "exe"]):
                try:
                    name = (proc.info.get("name") or "").lower()
                    if "playit" not in name:
                        continue
                    exe = proc.info.get("exe") or ""
                    if binary and exe and Path(exe).resolve() != binary.resolve():
                        # Only kill our managed binary / obvious playit agents
                        if "cultagent" not in exe.lower() and "cultforge" not in exe.lower():
                            if binary.name.lower() not in Path(exe).name.lower():
                                continue
                    pid = int(proc.info["pid"])
                    if self._kill_pid(pid):
                        killed.append(pid)
                except (psutil.NoSuchProcess, psutil.AccessDenied, TypeError, ValueError):
                    continue
        except Exception:  # noqa: BLE001
            logger.debug("playit process scan failed", exc_info=True)
        return killed

    async def stop(self) -> dict[str, Any]:
        pid = self._pid or self.load_state().get("pid")
        stopped = False
        killed_pids: list[int] = []
        if isinstance(pid, int) and self._kill_pid(pid):
            stopped = True
            killed_pids.append(pid)
        # Also clear orphans locking the binary.
        for extra in self._kill_named_playit():
            if extra not in killed_pids:
                killed_pids.append(extra)
                stopped = True
        self._pid = None
        self._started_at = None
        self._save_state(pid=None)
        return {
            "ok": True,
            "stopped": stopped,
            "pids": killed_pids,
            "note": None if stopped else "not running",
        }

    async def restart(self) -> dict[str, Any]:
        await self.stop()
        return await self.start()

    async def reset(self) -> dict[str, Any]:
        """Stop playit and clear stored secrets / claim state."""
        stop = await self.stop()
        had_secret = self.has_secret()
        self.clear_secret()
        # Drop claim leftovers from state but keep install metadata.
        self._claim_code = None
        self._claim_url = None
        self._last_error = None
        self._public_join = None
        self._public_join_checked_at = 0.0
        self._public_hints = []
        self._tunnel_count = None
        self.enabled = False
        self._save_state(
            pid=None,
            claim_code=None,
            claim_url=None,
            public_join=None,
            public_endpoint=None,
            tunnel_id=None,
            tunnel_count=None,
            reset_at=time.time(),
            enabled=False,
        )
        return {
            "ok": True,
            "stopped": stop.get("stopped"),
            "pids": stop.get("pids") or [],
            "secret_cleared": had_secret,
            "secret_path": str(self.secret_path),
        }

    def _ingest_line(self, line: str) -> None:
        low = line.lower()
        m = _CLAIM_RE.search(line)
        if m:
            self._claim_url = m.group(0).rstrip(").,]")
        code = parse_claim_code(line)
        if code:
            self._claim_code = code
            self._claim_url = claim_url_for(code)
        for hit in _PLY_RE.findall(line):
            if hit not in self._public_hints:
                self._public_hints.append(hit)
                if len(self._public_hints) > 8:
                    self._public_hints = self._public_hints[-8:]
            if not self._public_join:
                self._public_join = hit
                self._public_join_checked_at = time.time()
        tm = re.search(r"(\d+)\s+tunnels?", low)
        if tm:
            try:
                self._tunnel_count = int(tm.group(1))
            except ValueError:
                pass
        if any(
            tok in low
            for tok in (
                "error",
                "failed",
                "unable to connect",
                "invalidagentkey",
                "invalid secret",
                "no longer valid",
                "vcruntime",
            )
        ):
            self._last_error = line[:240]
            if "vcruntime" in low:
                self._last_error = (
                    f"{line[:160]} — see {SUPPORT_VCRUNTIME} / {VC_REDIST_URL}"
                )

    def recent_logs(self, *, limit: int = 80) -> list[str]:
        if self._lines:
            return list(self._lines)[-limit:]
        if self.log_path.is_file():
            try:
                lines = self.log_path.read_text(encoding="utf-8", errors="replace").splitlines()
                return lines[-limit:]
            except OSError:
                pass
        return []

    async def status_dict(self, *, refresh_join: bool = True) -> dict[str, Any]:
        for line in self.recent_logs(limit=120):
            self._ingest_line(line)

        if refresh_join and self.has_secret():
            await self.refresh_public_join(force=not bool(self._public_join))

        running = self.is_running()
        public = self._public_join
        if not public and self._public_hints:
            public = self._public_hints[-1]
        if not public:
            st = self.load_state()
            public = st.get("public_join") or st.get("public_endpoint")
            if public:
                self._public_join = str(public)
                public = self._public_join
        if running:
            if self._last_error and (
                "no longer valid" in (self._last_error or "").lower()
                or "invalidagentkey" in (self._last_error or "").lower()
            ):
                state = TunnelState.ERROR
            elif public or (self._tunnel_count and self._tunnel_count > 0):
                state = TunnelState.ONLINE
            else:
                state = TunnelState.CONNECTING
        else:
            state = TunnelState.OFFLINE

        profile = platform_profile()
        pid = self._pid if running else None
        return {
            "provider": "playit",
            "status": state.value,
            "target": self.target,
            "public_endpoint": public,
            "public_join": public,
            "latency_ms": None,
            "details": {
                "enabled": self.enabled,
                "running": running,
                "pid": pid,
                "has_secret": self.has_secret(),
                "binary": str(self.binary_path()) if self.binary_path() else None,
                "claim_code": self._claim_code or self.load_state().get("claim_code"),
                "claim_url": self._claim_url or self.load_state().get("claim_url"),
                "public_hints": list(self._public_hints),
                "public_join": public,
                "tunnel_count": self._tunnel_count,
                "auto_start": self.auto_start,
                "started_at": self._started_at,
                "last_error": self._last_error,
                "secret_path": str(self.secret_path),
                "socket_path": self.socket_path,
                "log_path": str(self.log_path),
                "setup_url": self._claim_url
                or self.load_state().get("claim_url")
                or SETUP_CLAIM_CODE_PAGE,
                "setup_claim_url": CLAIM_URL_PREFIX.rstrip("/"),
                "setup_secret_url": SETUP_SECRET_URL,
                "agents_url": AGENTS_URL,
                "download_url": profile.get("download_url") or DOWNLOAD_URL,
                "support_url": SUPPORT_URL,
                "vendor": PLAYIT_RELEASE_REPO,
                "release_pin": PLAYIT_RELEASE_TAG,
                "stub": False,
                "launch": "detached-cli",
                "platform": profile,
            },
        }

    async def as_network_status(self) -> NetworkStatus:
        raw = await self.status_dict()
        return NetworkStatus(
            provider="playit",
            status=TunnelState(raw["status"]),
            target=raw.get("target"),
            public_endpoint=raw.get("public_endpoint") or raw.get("public_join"),
            latency_ms=raw.get("latency_ms"),
            details=raw.get("details") or {},
        )


