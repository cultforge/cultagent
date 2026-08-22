"""Server scope classification (guild / personal / local)."""

from __future__ import annotations

from cultagent.servers.models import ServerRecord
from cultagent.servers.scope import server_scope, server_scope_label


def test_guild_clone_scope() -> None:
    record = ServerRecord(
        server_id="srv_abc",
        name="Aitheiro",
        path="/tmp/srv",
        metadata={"scope": "guild", "guild_server_id": "srv_abc", "cloned_from": "guild"},
    )
    assert server_scope(record) == "guild"
    assert server_scope_label(record) == "Guild"


def test_personal_bound_scope() -> None:
    record = ServerRecord(
        server_id="upsrv_xyz",
        name="My SMP",
        path="/tmp/upsrv",
        metadata={"scope": "personal", "personal_server_id": "upsrv_xyz"},
    )
    assert server_scope(record) == "personal"
    assert server_scope_label(record) == "Personal"


def test_local_only_scope() -> None:
    record = ServerRecord(
        server_id="local_1",
        name="Test",
        path="/tmp/test",
    )
    assert server_scope(record) == "local"
    assert server_scope_label(record) == "Local"
