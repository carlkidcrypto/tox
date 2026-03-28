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
    duration_ns = max(0, round(duration * 1_000_000_000))
    if duration_ns < _profile_min_ns():
        return
    suffix = "".join(f" {key}={value!r}" for key, value in fields.items())
    LOGGER.warning("[profile] %s took %d ns%s", name, duration_ns, suffix)


@contextmanager
def profile_block(name: str, **fields: Any) -> Iterator[None]:
    if not profile_enabled():
        yield
        return
    start = time.perf_counter_ns()
    try:
        yield
    finally:
        duration_s = (time.perf_counter_ns() - start) / 1_000_000_000
        profile_log(name, duration_s, **fields)


def _profile_min_ns() -> int:
    raw_ns = os.environ.get("TOX_PROFILE_MIN_NS", "").strip()
    if raw_ns:
        try:
            return max(0, round(float(raw_ns)))
        except ValueError:
            return 0

    raw_us = os.environ.get("TOX_PROFILE_MIN_US", "").strip()
    if raw_us:
        try:
            return max(0, round(float(raw_us) * 1_000))
        except ValueError:
            return 0

    raw = os.environ.get("TOX_PROFILE_MIN_MS", "0").strip()
    if not raw:
        return 0
    try:
        return max(0, round(float(raw) * 1_000_000))
    except ValueError:
        return 0


__all__ = [
    "profile_block",
    "profile_enabled",
    "profile_log",
]