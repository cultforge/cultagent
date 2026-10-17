"""Build provision + manifest install tests."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

import httpx
import pytest

from cultagent.app import CultAgentApp
from cultagent.cache import cache_file_path, clear_agent_cache
from cultagent.cloud.client import CloudError
from cultagent.content.install import install_manifest
from cultagent.content.progress import install_progress
from cultagent.identity import AgentCredentials, utc_now
from cultagent.settings import AgentConfig


@pytest.mark.asyncio
async def test_install_manifest_resolved(tmp_path: Path) -> None:
    # Already present with matching hash → skipped, no network.
    server = tmp_path / "srv"
    server.mkdir()
    mods = server / "mods"
    mods.mkdir()
    jar = mods / "demo.jar"
    jar.write_bytes(b"hello-mod")
    digest = hashlib.sha256(b"hello-mod").hexdigest()
    manifest = {
        "schema_version": 1,
        "build_id": "bld_x",
        "guild_id": "gld_x",
        "mode": "resolved",
        "minecraft_version": "1.20.1",
        "loader": "fabric",
        "files": [
            {
                "path": "mods/demo.jar",
                "urls": ["https://example.invalid/demo.jar"],
                "sha256": digest,
                "size": 9,
                "kind": "mod",
                "env": "both",
                "optional": False,
            }
        ],
        "unresolved": [],
        "warnings": [],
    }
    events: list[dict[str, Any]] = []
    with install_progress(events.append):
        result = await install_manifest(manifest, server)
    assert result["ok"] is True
    assert any(s.get("reason") == "already_present" for s in result["skipped"])
    assert any(e.get("type") == "file_skip" for e in events)
    assert any(e.get("type") == "install_done" for e in events)


@pytest.mark.asyncio
async def test_install_manifest_from_cache(tmp_path: Path) -> None:
    body = b"mod-bytes-123"
    digest = hashlib.sha256(body).hexdigest()
    cache = tmp_path / "cache"
    cached = cache_file_path(cache, sha256=digest)
    cached.parent.mkdir(parents=True)
    cached.write_bytes(body)

    server = tmp_path / "srv"
    manifest = {
        "schema_version": 1,
        "build_id": "bld_y",
        "guild_id": "gld_x",
        "mode": "resolved",
        "minecraft_version": "1.20.1",
        "loader": "fabric",
        "files": [
            {
                "path": "mods/demo.jar",
                "urls": ["https://example.invalid/never-hit.jar"],
                "sha256": digest,
                "size": len(body),
                "kind": "mod",
                "env": "both",
                "optional": False,
            }
        ],
        "unresolved": [],
        "warnings": [],
    }
    result = await install_manifest(manifest, server, cache_dir=cache)
    assert result["ok"] is True
    assert result["installed"][0].get("cached") is True
    assert (server / "mods" / "demo.jar").read_bytes() == body


@pytest.mark.asyncio
async def test_install_manifest_download_writes_cache(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    body = b"downloaded-mod"
    digest = hashlib.sha256(body).hexdigest()
    url = "https://cdn.example.test/mods/demo.jar"

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            content=body,
            headers={"Content-Length": str(len(body))},
        )

    transport = httpx.MockTransport(handler)
    real_async_client = httpx.AsyncClient

    def client_factory(*args: Any, **kwargs: Any) -> httpx.AsyncClient:
        kwargs["transport"] = transport
        return real_async_client(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", client_factory)

    server = tmp_path / "srv"
    cache = tmp_path / "cache"
    events: list[dict[str, Any]] = []
    manifest = {
        "schema_version": 1,
        "build_id": "bld_z",
        "guild_id": "gld_x",
        "mode": "resolved",
        "minecraft_version": "1.20.1",
        "loader": "fabric",
        "files": [
            {
                "path": "mods/demo.jar",
                "urls": [url],
                "sha256": digest,
                "size": len(body),
                "kind": "mod",
                "env": "both",
                "optional": False,
            }
        ],
        "unresolved": [],
        "warnings": [],
    }
    with install_progress(events.append):
        result = await install_manifest(manifest, server, cache_dir=cache)
    assert result["ok"] is True
    assert (server / "mods" / "demo.jar").read_bytes() == body
    assert cache_file_path(cache, sha256=digest).is_file()
    assert any(e.get("type") == "file_progress" for e in events)
    assert any(e.get("type") == "file_done" for e in events)


def test_clear_agent_cache(tmp_path: Path) -> None:
    cache = tmp_path / "cache"
    cache.mkdir()
    blob = cache / "downloads" / "ab" / "abc"
    blob.parent.mkdir(parents=True)
    blob.write_bytes(b"x" * 100)
    summary = clear_agent_cache(cache)
    assert summary["ok"] is True
    assert summary["removed_entries"] >= 1
    assert not blob.exists()


@pytest.mark.asyncio
async def test_builds_list_and_provision_mocked(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = AgentConfig()
    config.agent.data_dir = str(tmp_path / "data")
    app = CultAgentApp(config)
    app.bootstrap_identity()
    identity = app.identity_store.load_identity()
    assert identity is not None
    identity.guild_id = "gld_test"
    app.identity_store.save_identity(identity)
    app.identity_store.save_credentials(
        AgentCredentials(agent_token="cagt_test", issued_at=utc_now())
    )

    async def fake_list(_token: str, *, limit: int = 50) -> dict[str, Any]:
        return {
            "status": True,
            "data": [
                {
                    "id": "bld_1",
                    "name": "Frost Fall",
                    "minecraft_version": "1.20.1",
                    "loader": "fabric",
                    "is_installable": True,
                }
            ],
        }

    async def fake_provision(_token: str, build_id: str, **kwargs: Any) -> dict[str, Any]:
        assert build_id == "bld_1"
        assert kwargs.get("local_server_id")
        return {
            "status": True,
            "data": {
                "workload": {"id": "awl_1", "build_id": "bld_1", "local_server_id": kwargs["local_server_id"]},
                "build": {"id": "bld_1", "name": "Frost Fall", "minecraft_version": "1.20.1", "loader": "fabric"},
                "manifest": {
                    "schema_version": 1,
                    "build_id": "bld_1",
                    "guild_id": "gld_test",
                    "mode": "resolved",
                    "minecraft_version": "1.20.1",
                    "loader": "fabric",
                    "files": [],
                    "unresolved": [],
                    "warnings": ["empty for test"],
                },
            },
        }

    async def fake_report(*_a: Any, **_k: Any) -> dict[str, Any]:
        return {"status": True, "data": []}

    async def fake_manifest(*_a: Any, **_k: Any) -> dict[str, Any]:
        return {
            "status": True,
            "data": {
                "schema_version": 1,
                "build_id": "bld_1",
                "guild_id": "gld_test",
                "mode": "resolved",
                "minecraft_version": "1.20.1",
                "loader": "fabric",
                "files": [],
                "unresolved": [],
                "warnings": ["empty for test"],
            },
        }

    async def fake_install_loader(server_id: str, **kwargs: Any) -> dict[str, Any]:
        record = await app.servers.get(server_id)
        assert record is not None
        # Simulate a ready fabric jar without network
        jar = Path(record.path) / "server.jar"
        jar.write_bytes(b"fake-fabric-server")
        record.executable = "server.jar"
        record.loader = str(kwargs.get("loader") or "fabric")
        record.minecraft_version = str(kwargs.get("version") or "1.20.1")
        record.execution_command = ""
        await app.servers.update_record(record)
        return {
            "server_id": server_id,
            "jar": str(jar),
            "version": record.minecraft_version,
            "loader": record.loader,
            "execution_command": "",
            "metadata": {},
        }

    async def fake_search(*_a: Any, **_k: Any) -> dict[str, Any]:
        raise CloudError("search unavailable", status_code=404)

    async def fake_get_build_manifest(*_a: Any, **_k: Any) -> dict[str, Any]:
        raise CloudError("manifest unavailable", status_code=404)

    async def fake_provision_build(*_a: Any, **_k: Any) -> dict[str, Any]:
        raise CloudError("unified provision unavailable", status_code=404)

    monkeypatch.setattr(app.cloud_client, "search_builds", fake_search)
    monkeypatch.setattr(app.cloud_client, "list_guild_builds", fake_list)
    monkeypatch.setattr(app.cloud_client, "provision_build", fake_provision_build)
    monkeypatch.setattr(app.cloud_client, "provision_from_build", fake_provision)
    monkeypatch.setattr(app.cloud_client, "report_workloads", fake_report)
    monkeypatch.setattr(app.cloud_client, "get_build_manifest", fake_get_build_manifest)
    monkeypatch.setattr(app.cloud_client, "get_guild_build_manifest", fake_manifest)
    monkeypatch.setattr(app.servers, "install_loader", fake_install_loader)

    listed = await app.dispatch("builds.list")
    assert listed["ok"] is True
    assert listed["data"]["builds"][0]["id"] == "bld_1"

    # Empty files → content install may not be ok, but provision + platform still run.
    provisioned = await app.dispatch(
        "builds.provision",
        params={"build_id": "bld_1", "install": True},
    )
    assert provisioned["ok"] is True
    assert provisioned["data"]["local_server_id"]
    assert provisioned["data"]["workload"]["id"] == "awl_1"
    install = provisioned["data"]["install"] or {}
    assert install.get("platform", {}).get("installed") is True
    assert install.get("launch_ready") is True


@pytest.mark.asyncio
async def test_build_install_ensures_platform(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    config = AgentConfig()
    config.agent.data_dir = str(tmp_path / "data")
    app = CultAgentApp(config)
    app.bootstrap_identity()
    identity = app.identity_store.load_identity()
    assert identity is not None
    identity.guild_id = "gld_test"
    app.identity_store.save_identity(identity)
    app.identity_store.save_credentials(
        AgentCredentials(agent_token="cagt_test", issued_at=utc_now())
    )
    record = await app.servers.create(
        "Chamber",
        minecraft_version="1.20.1",
        loader="forge",
        accept_eula=True,
    )

    async def fake_manifest(*_a: Any, **_k: Any) -> dict[str, Any]:
        return {
            "status": True,
            "data": {
                "schema_version": 1,
                "build_id": "bld_forge",
                "mode": "resolved",
                "minecraft_version": "1.20.1",
                "loader": "forge",
                "files": [],
                "unresolved": [],
                "warnings": [],
            },
        }

    called: dict[str, Any] = {}

    async def fake_install_loader(server_id: str, **kwargs: Any) -> dict[str, Any]:
        called.update(kwargs)
        called["server_id"] = server_id
        rec = await app.servers.get(server_id)
        assert rec is not None
        libs = Path(rec.path) / "libraries"
        libs.mkdir(exist_ok=True)
        (libs / "marker").write_text("x", encoding="utf-8")
        rec.execution_command = "java @user_jvm_args.txt @libraries/win_args.txt nogui"
        rec.executable = "server.jar"
        (Path(rec.path) / "server.jar").write_text("# forge marker\n", encoding="utf-8")
        await app.servers.update_record(rec)
        return {
            "server_id": server_id,
            "jar": str(Path(rec.path) / "server.jar"),
            "version": "1.20.1",
            "loader": "forge",
            "execution_command": rec.execution_command,
            "metadata": {"forge_version": "47.4.10"},
        }

    async def fake_get_build_manifest(*_a: Any, **_k: Any) -> dict[str, Any]:
        raise CloudError("unified manifest unavailable", status_code=404)

    monkeypatch.setattr(app.cloud_client, "get_build_manifest", fake_get_build_manifest)
    monkeypatch.setattr(app.cloud_client, "get_guild_build_manifest", fake_manifest)
    monkeypatch.setattr(app.servers, "install_loader", fake_install_loader)

    result = await app.dispatch(
        "builds.provision",
        params={"build_id": "bld_forge", "server_id": record.server_id},
    )
    assert result["ok"] is True
    assert called.get("loader") == "forge"
    assert called.get("version") == "1.20.1"
    assert result["data"]["platform"]["installed"] is True
    assert result["data"]["launch_ready"] is True

    # Second shot should skip platform (already present)
    called.clear()
    result2 = await app.dispatch(
        "builds.provision",
        params={"build_id": "bld_forge", "server_id": record.server_id},
    )
    assert result2["ok"] is True
    assert result2["data"]["platform"]["skipped"] is True
    assert "loader" not in called  # install_loader not called


@pytest.mark.asyncio
async def test_install_manifest_fails_on_required_unresolved(tmp_path: Path) -> None:
    """Pinned builds must not silently skip required unresolved mods."""
    server = tmp_path / "srv"
    manifest = {
        "schema_version": 1,
        "build_id": "bld_bad",
        "mode": "resolved",
        "minecraft_version": "1.20.1",
        "loader": "forge",
        "files": [
            {
                "path": "mods/ok.jar",
                "urls": ["https://example.invalid/ok.jar"],
                "sha256": "abc",
                "kind": "mod",
                "env": "both",
            }
        ],
        "unresolved": [
            {"slug": "missing-mod", "reason": "version_not_found"},
            {"slug": "optional-skip", "reason": "gone", "optional": True},
        ],
        "warnings": [],
    }
    result = await install_manifest(manifest, server)
    assert result["ok"] is False
    assert any("unresolved pinned" in e for e in result["errors"])
    assert any("missing-mod" in e for e in result["errors"])
    assert not (server / "mods").exists()


@pytest.mark.asyncio
async def test_deploy_cloud_manifest_rejects_unresolved(tmp_path: Path) -> None:
    from cultagent.content import BuildService
    from cultagent.settings import ContentSection

    svc = BuildService(ContentSection())
    manifest = {
        "mode": "resolved",
        "files": [
            {
                "path": "mods/a.jar",
                "urls": ["https://example.invalid/a.jar"],
                "sha256": "deadbeef",
            }
        ],
        "unresolved": [{"slug": "broken-pin", "reason": "no_version"}],
    }
    result = await svc.deploy_cloud_manifest(manifest, tmp_path / "srv")
    assert result["ok"] is False
    assert any("unresolved" in e.lower() for e in result["errors"])


@pytest.mark.asyncio
async def test_install_manifest_sha512_already_present(tmp_path: Path) -> None:
    body = b"sha512-mod"
    digest512 = hashlib.sha512(body).hexdigest()
    server = tmp_path / "srv"
    mods = server / "mods"
    mods.mkdir(parents=True)
    (mods / "demo.jar").write_bytes(body)
    manifest = {
        "mode": "resolved",
        "build_id": "bld_h",
        "files": [
            {
                "path": "mods/demo.jar",
                "urls": ["https://example.invalid/demo.jar"],
                "sha512": digest512,
                "kind": "mod",
                "env": "both",
            }
        ],
        "unresolved": [],
    }
    result = await install_manifest(manifest, server)
    assert result["ok"] is True
    assert any(s.get("reason") == "already_present" for s in result["skipped"])
