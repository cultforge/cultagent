"""CLI spinner must not mask body exceptions."""

from __future__ import annotations

import pytest

from cultagent.cli.interact import spinner


def test_spinner_propagates_body_exception(monkeypatch: pytest.MonkeyPatch) -> None:
    """Regression: yaspin setup try/except used to catch body errors and
    re-yield → RuntimeError('generator didn't stop after throw()').
    """
    monkeypatch.setattr("sys.stdout.isatty", lambda: True)

    class _FakeYaspin:
        def __init__(self, *args, **kwargs) -> None:
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    import sys
    from types import ModuleType, SimpleNamespace

    fake_yaspin = ModuleType("yaspin")
    fake_yaspin.yaspin = _FakeYaspin  # type: ignore[attr-defined]
    fake_spinners = ModuleType("yaspin.spinners")
    fake_spinners.Spinners = SimpleNamespace(line="line")  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "yaspin", fake_yaspin)
    monkeypatch.setitem(sys.modules, "yaspin.spinners", fake_spinners)

    with pytest.raises(ValueError, match="real-claim-error"):
        with spinner("Registering…"):
            raise ValueError("real-claim-error")
