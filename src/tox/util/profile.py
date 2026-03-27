from __future__ import annotations

import logging
import os
import time
from contextlib import contextmanager
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Iterator

LOGGER = logging.getLogger(__name__)
_ENABLED_VALUES = {"1", "true", "yes", "on"}


def profile_enabled() -> bool:
    value = os.environ.get("TOX_PROFILE", "").strip().lower()
    return value in _ENABLED_VALUES


def profile_log(name: str, duration: float, **fields: Any) -> None:
    if not profile_enabled():
        return
    min_ms = _profile_min_ms()
    duration_ms = duration * 1000
    if duration_ms < min_ms:
        return
    suffix = "".join(f" {key}={value!r}" for key, value in fields.items())
    LOGGER.warning("[profile] %s took %.2f ms%s", name, duration_ms, suffix)


@contextmanager
def profile_block(name: str, **fields: Any) -> Iterator[None]:
    if not profile_enabled():
        yield
        return
    start = time.monotonic()
    try:
        yield
    finally:
        profile_log(name, time.monotonic() - start, **fields)


def _profile_min_ms() -> float:
    raw = os.environ.get("TOX_PROFILE_MIN_MS", "0").strip()
    if not raw:
        return 0.0
    try:
        return max(0.0, float(raw))
    except ValueError:
        return 0.0


__all__ = [
    "profile_block",
    "profile_enabled",
    "profile_log",
]