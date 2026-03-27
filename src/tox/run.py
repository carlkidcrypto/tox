"""Main entry point for tox."""

from __future__ import annotations

import faulthandler
import logging
import os
import sys
import time
from typing import TYPE_CHECKING

from tox.config.cli.parse import get_options
from tox.report import HandledError, ToxHandler
from tox.session.state import State
from tox.util.profile import profile_block

if TYPE_CHECKING:
    from collections.abc import Sequence


def run(args: Sequence[str] | None = None) -> None:
    try:
        with ToxHandler.patch_thread():
            with profile_block("run.main_wrapper"):
                result = main(sys.argv[1:] if args is None else args)
    except Exception as exception:
        if isinstance(exception, HandledError):
            logging.error("%s| %s", type(exception).__name__, exception)  # noqa: TRY400
            result = -2
        else:
            raise
    except KeyboardInterrupt:
        result = -2
    finally:
        if "_TOX_SHOW_THREAD" in os.environ:  # pragma: no cover
            import threading  # pragma: no cover  # noqa: PLC0415

            for thread in threading.enumerate():  # pragma: no cover
                print(thread)  # pragma: no cover  # noqa: T201
    raise SystemExit(result)


def main(args: Sequence[str]) -> int:
    with profile_block("run.setup_state", argc=len(args)):
        state = setup_state(args)
    from tox.provision import provision  # noqa: PLC0415

    with profile_block("run.provision"):
        result = provision(state)
    if result is not False:
        return result
    handler = state._options.cmd_handlers[state.conf.options.command]  # noqa: SLF001
    with profile_block("run.command", command=state.conf.options.command):
        return handler(state)


def setup_state(args: Sequence[str]) -> State:
    """Setup the state object of this run."""
    start = time.monotonic()
    # parse CLI arguments
    with profile_block("run.get_options", argc=len(args)):
        options = get_options(*args)
    options.parsed.start = start
    if options.parsed.exit_and_dump_after:
        faulthandler.dump_traceback_later(timeout=options.parsed.exit_and_dump_after, exit=True)  # pragma: no cover
    # build tox environment config objects
    with profile_block("run.state_init"):
        return State(options, args)
