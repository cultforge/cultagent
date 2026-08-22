"""Browser OAuth against auth.cultforge.com via loopback callback (launcher-style)."""

from __future__ import annotations

import asyncio
import logging
import threading
import urllib.parse
import webbrowser
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any

logger = logging.getLogger("cultagent.cloud.browser_auth")

DEFAULT_OAUTH_PROVIDERS = ("google", "github", "discord", "microsoft")

_SUCCESS_HTML = """<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"><title>CultForge Agent</title>
<style>
  body{font-family:system-ui,sans-serif;background:#0B0D10;color:#F3F5F7;
       display:flex;min-height:100vh;align-items:center;justify-content:center;margin:0}
  .box{max-width:28rem;padding:2rem;text-align:center}
  h1{font-size:1.25rem;margin:0 0 .5rem}
  p{color:#9AA3B2;margin:0}
</style></head>
<body><div class="box">
  <h1>Signed in</h1>
  <p>Return to the terminal — CultAgent will finish linking this machine.</p>
</div></body></html>
"""

_FAIL_HTML = """<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"><title>CultForge Agent</title>
<style>
  body{font-family:system-ui,sans-serif;background:#0B0D10;color:#F3F5F7;
       display:flex;min-height:100vh;align-items:center;justify-content:center;margin:0}
  .box{max-width:28rem;padding:2rem;text-align:center}
  h1{font-size:1.25rem;margin:0 0 .5rem;color:#f87171}
  p{color:#9AA3B2;margin:0}
</style></head>
<body><div class="box">
  <h1>Sign-in failed</h1>
  <p>Close this tab and run <code>cf-agent login</code> again.</p>
</div></body></html>
"""


@dataclass
class BrowserAuthResult:
    token: str
    message: str = ""
    provider: str = ""
    email: str = ""
    name: str = ""


class BrowserAuthError(RuntimeError):
    pass


def _truthy(value: str | None) -> bool:
    return (value or "").strip().lower() in {"1", "true", "yes", "on"}


async def capture_oauth_session(
    *,
    auth_base: str,
    provider: str = "google",
    open_browser: bool = True,
    timeout_seconds: float = 300.0,
) -> BrowserAuthResult:
    """Open auth.*/v1/oauth and capture the session JWT on 127.0.0.1.

    Mirrors the launcher: OAuth verify redirects to redirect_uri with
    ``?status=…&token=…`` query params. The token is never printed.
    """
    provider = (provider or "google").strip().lower()
    if provider not in DEFAULT_OAUTH_PROVIDERS:
        raise BrowserAuthError(
            f"Unsupported provider {provider!r}; use one of {', '.join(DEFAULT_OAUTH_PROVIDERS)}"
        )

    result_box: dict[str, Any] = {"done": asyncio.Event(), "result": None, "error": None}
    loop = asyncio.get_running_loop()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: Any) -> None:  # noqa: A003
            logger.debug("oauth callback: " + format, *args)

        def do_GET(self) -> None:  # noqa: N802
            parsed = urllib.parse.urlparse(self.path)
            if parsed.path not in ("/callback", "/"):
                self.send_response(404)
                self.end_headers()
                return
            qs = urllib.parse.parse_qs(parsed.query)
            status_ok = _truthy((qs.get("status") or ["false"])[0])
            token = (qs.get("token") or [""])[0].strip()
            message = (qs.get("message") or [""])[0]
            email = (qs.get("email") or [""])[0]
            name = (qs.get("name") or [""])[0]
            prov = (qs.get("provider") or [provider])[0]

            # Signup tokens are not app sessions — user must finish onboarding first.
            if status_ok and token and message.strip().lower() == "oauth verified":
                result_box["error"] = (
                    "This CultForge account is not finished signing up yet. "
                    "Complete signup in the CultForge launcher, then run cf-agent login again."
                )
                body = _FAIL_HTML.encode("utf-8")
            elif status_ok and token:
                result_box["result"] = BrowserAuthResult(
                    token=token,
                    message=message,
                    provider=prov,
                    email=email,
                    name=name,
                )
                body = _SUCCESS_HTML.encode("utf-8")
            else:
                result_box["error"] = message or "OAuth callback missing session token"
                body = _FAIL_HTML.encode("utf-8")

            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            loop.call_soon_threadsafe(result_box["done"].set)

    server = HTTPServer(("127.0.0.1", 0), Handler)
    port = int(server.server_address[1])
    callback = f"http://127.0.0.1:{port}/callback"
    auth_url = (
        f"{auth_base.rstrip('/')}/v1/oauth"
        f"?provider={urllib.parse.quote(provider)}"
        f"&redirect_uri={urllib.parse.quote(callback, safe='')}"
    )

    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        if open_browser:
            try:
                webbrowser.open(auth_url)
            except Exception:  # noqa: BLE001
                logger.debug("Could not open browser", exc_info=True)

        try:
            await asyncio.wait_for(result_box["done"].wait(), timeout=timeout_seconds)
        except asyncio.TimeoutError as exc:
            raise BrowserAuthError(
                "Timed out waiting for browser sign-in. Run cf-agent login again."
            ) from exc

        if result_box["error"]:
            raise BrowserAuthError(str(result_box["error"]))
        result = result_box["result"]
        if not isinstance(result, BrowserAuthResult) or not result.token:
            raise BrowserAuthError("Browser sign-in did not return a session token.")
        return result
    finally:
        server.shutdown()
        thread.join(timeout=2.0)
