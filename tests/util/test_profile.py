from __future__ import annotations

import logging

from _pytest.logging import LogCaptureFixture

from tox.pytest import MonkeyPatch
from tox.util.profile import profile_block, profile_enabled, profile_log


def test_profile_enabled(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setenv("TOX_PROFILE", "1")
    assert profile_enabled() is True


def test_profile_disabled(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.delenv("TOX_PROFILE", raising=False)
    assert profile_enabled() is False


def test_profile_log(monkeypatch: MonkeyPatch, caplog: LogCaptureFixture) -> None:
    monkeypatch.setenv("TOX_PROFILE", "1")
    caplog.set_level(logging.WARNING)

    profile_log("demo", 0.01, env="py")

    assert len(caplog.records) == 1
    message = caplog.records[0].getMessage()
    assert "[profile] demo took" in message
    assert "env='py'" in message


def test_profile_log_respects_threshold(monkeypatch: MonkeyPatch, caplog: LogCaptureFixture) -> None:
    monkeypatch.setenv("TOX_PROFILE", "1")
    monkeypatch.setenv("TOX_PROFILE_MIN_MS", "20")
    caplog.set_level(logging.WARNING)

    profile_log("short", 0.005)

    assert not caplog.records


def test_profile_block(monkeypatch: MonkeyPatch, caplog: LogCaptureFixture) -> None:
    monkeypatch.setenv("TOX_PROFILE", "1")
    caplog.set_level(logging.WARNING)

    with profile_block("wrap", stage="setup"):
        pass

    assert len(caplog.records) == 1
    message = caplog.records[0].getMessage()
    assert "[profile] wrap took" in message
    assert "stage='setup'" in message