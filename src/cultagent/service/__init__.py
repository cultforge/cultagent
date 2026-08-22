"""Service install helpers (Windows / systemd / launchd)."""

from __future__ import annotations

import platform
from pathlib import Path
from textwrap import dedent


def _looks_like_windows_path(path: Path | str) -> bool:
    text = str(path)
    return text.lower().endswith(".exe") or "\\" in text or (len(text) >= 2 and text[1] == ":")


def _resolve_cf_agent(python_exe: Path) -> Path:
    """Prefer the cf-agent console script next to the interpreter."""
    name = "cf-agent.exe" if platform.system() == "Windows" else "cf-agent"
    candidate = python_exe.parent / name
    return candidate if candidate.is_file() else python_exe


def systemd_paths(python_exe: Path, working_dir: Path) -> tuple[str, str, bool]:
    """Return (exec_start, working_directory, used_placeholders).

    systemd units are Linux-only. Never embed Windows paths.
    """
    if platform.system() != "Linux" or _looks_like_windows_path(python_exe) or _looks_like_windows_path(
        working_dir
    ):
        return (
            "/opt/cultagent/.venv/bin/cf-agent run",
            "/opt/cultagent",
            True,
        )

    cf_agent = python_exe.parent / "cf-agent"
    if cf_agent.is_file():
        exec_start = f"{cf_agent.resolve()} run"
    else:
        exec_start = f"{python_exe.resolve()} -m cultagent run"
    return exec_start, str(working_dir.resolve()), False


def systemd_unit(python_exe: Path, working_dir: Path) -> str:
    exec_start, workdir, placeholders = systemd_paths(python_exe, working_dir)
    header = ""
    if placeholders:
        header = (
            "# Template for Linux hosts - edit ExecStart / WorkingDirectory for your install.\n"
            "# Generated on a non-Linux machine (Windows paths are never written into units).\n"
            "#\n"
        )
    return header + dedent(
        f"""\
        [Unit]
        Description=CultForge Agent
        After=network-online.target
        Wants=network-online.target

        [Service]
        Type=simple
        WorkingDirectory={workdir}
        ExecStart={exec_start}
        Restart=on-failure
        RestartSec=5

        [Install]
        WantedBy=multi-user.target
        """
    )


def launchd_plist(python_exe: Path, working_dir: Path, label: str = "com.cultforge.agent") -> str:
    """macOS launchd plist. Never embeds Windows paths."""
    use_template = platform.system() != "Darwin" or _looks_like_windows_path(python_exe)

    if use_template:
        workdir = "/usr/local/var/cultagent"
        args = ["/usr/local/bin/cf-agent", "run"]
    else:
        workdir = str(working_dir.resolve())
        cf_agent = python_exe.parent / "cf-agent"
        if cf_agent.is_file():
            args = [str(cf_agent.resolve()), "run"]
        else:
            args = [str(python_exe.resolve()), "-m", "cultagent", "run"]

    args_xml = "\n".join(f"            <string>{a}</string>" for a in args)
    body = dedent(
        f"""\
        <?xml version="1.0" encoding="UTF-8"?>
        <!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
          "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
        <plist version="1.0">
        <dict>
          <key>Label</key>
          <string>{label}</string>
          <key>ProgramArguments</key>
          <array>
        {args_xml}
          </array>
          <key>WorkingDirectory</key>
          <string>{workdir}</string>
          <key>RunAtLoad</key>
          <true/>
          <key>KeepAlive</key>
          <true/>
        </dict>
        </plist>
        """
    )
    if use_template:
        return (
            "<!-- Template for macOS - edit ProgramArguments / WorkingDirectory -->\n"
            "<!-- Generated off-macOS: Windows paths are never written into plists. -->\n"
            + body
        )
    return body


def windows_winsw_xml(python_exe: Path, working_dir: Path, *, service_id: str = "CultAgent") -> str:
    """WinSW service XML using real Windows paths (correct on this OS)."""
    agent = _resolve_cf_agent(python_exe).resolve()
    work = working_dir.resolve()
    if agent.name.lower().startswith("python"):
        executable = str(agent)
        arguments = "-m cultagent run"
    else:
        executable = str(agent)
        arguments = "run"
    log_dir = work / "logs"
    return dedent(
        f"""\
        <!-- WinSW config: https://github.com/winsw/winsw
             1. Download WinSW-x64.exe as CultAgent.exe next to this XML (CultAgent.xml)
             2. CultAgent.exe install
             3. CultAgent.exe start
        -->
        <service>
          <id>{service_id}</id>
          <name>CultForge Agent</name>
          <description>CultForge machine-side Minecraft agent (local panel + cloud poll)</description>
          <executable>{executable}</executable>
          <arguments>{arguments}</arguments>
          <workingdirectory>{work}</workingdirectory>
          <logpath>{log_dir}</logpath>
          <log mode="roll-by-size">
            <sizeThreshold>10240</sizeThreshold>
            <keepFiles>8</keepFiles>
          </log>
          <onfailure action="restart" delay="5 sec"/>
          <startmode>Automatic</startmode>
        </service>
        """
    )


def windows_nssm_script(python_exe: Path, working_dir: Path, *, service_name: str = "CultAgent") -> str:
    """PowerShell snippet to install via NSSM (https://nssm.cc/)."""
    agent = _resolve_cf_agent(python_exe).resolve()
    work = working_dir.resolve()
    if agent.name.lower().startswith("python"):
        app = str(agent)
        app_params = "-m cultagent run"
    else:
        app = str(agent)
        app_params = "run"
    return dedent(
        f"""\
        # Requires NSSM on PATH: https://nssm.cc/download
        # Run elevated PowerShell:

        $name = "{service_name}"
        $app  = "{app}"
        $dir  = "{work}"

        nssm install $name $app {app_params}
        nssm set $name AppDirectory $dir
        nssm set $name AppStdout "$dir\\logs\\service.out.log"
        nssm set $name AppStderr "$dir\\logs\\service.err.log"
        nssm set $name AppRotateFiles 1
        nssm set $name Start SERVICE_AUTO_START
        New-Item -ItemType Directory -Force -Path "$dir\\logs" | Out-Null
        nssm start $name

        # Remove later:
        #   nssm stop $name; nssm remove $name confirm
        """
    )


def windows_schtasks_script(python_exe: Path, working_dir: Path, *, task_name: str = "CultForgeAgent") -> str:
    """Fallback: logon scheduled task (no third-party service wrapper)."""
    agent = _resolve_cf_agent(python_exe).resolve()
    work = working_dir.resolve()
    if agent.name.lower().startswith("python"):
        tr = f'"{agent}" -m cultagent run'
    else:
        tr = f'"{agent}" run'
    return dedent(
        f"""\
        # Scheduled task (runs at logon for the current user). Run in elevated PowerShell:

        $task = "{task_name}"
        $dir  = "{work}"
        $tr   = '{tr}'

        New-Item -ItemType Directory -Force -Path "$dir\\logs" | Out-Null
        schtasks /Create /F /TN $task /SC ONLOGON /RL HIGHEST /TR $tr /WD $dir

        # Start now:
        #   schtasks /Run /TN $task
        # Remove:
        #   schtasks /Delete /F /TN $task
        """
    )


def windows_service_bundle(python_exe: Path, working_dir: Path) -> str:
    """Combined Windows background-run helpers."""
    return "\n".join(
        [
            "# === CultForge Agent - Windows service helpers ===",
            "# Prefer WinSW or NSSM for a real Windows service.",
            "",
            "# --- WinSW XML (save as CultAgent.xml next to WinSW renamed CultAgent.exe) ---",
            windows_winsw_xml(python_exe, working_dir).rstrip(),
            "",
            "# --- NSSM PowerShell ---",
            windows_nssm_script(python_exe, working_dir).rstrip(),
            "",
            "# --- schtasks fallback ---",
            windows_schtasks_script(python_exe, working_dir).rstrip(),
            "",
        ]
    )


def windows_service_notes() -> str:
    return (
        "Windows: use `cf-agent service windows` for WinSW XML + NSSM + schtasks helpers. "
        "`service systemd` / `service launchd` emit Linux/macOS templates only (no Windows paths)."
    )


def service_hint() -> str:
    system = platform.system()
    if system == "Linux":
        return "Generate a unit with `cf-agent service systemd` and install under /etc/systemd/system/"
    if system == "Darwin":
        return "Generate a plist with `cf-agent service launchd` and load via launchctl"
    if system == "Windows":
        return windows_service_notes()
    return f"Unsupported platform for service helpers: {system}"
