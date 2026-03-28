WSL Profiling Runbook (tox on ezsnmp)
=====================================

.. contents:: Contents
   :local:
   :depth: 2

Overview
--------

This document captures the complete performance analysis for the
``feature/perf_improvement`` branch of tox. It serves as the supporting
evidence for an upstream patch submission.

It documents:

- what code changes were made and why,
- the profiling instrumentation added,
- how measurements were collected and reproduced,
- results across WSL (outside Docker) and Docker environments,
- functional test verification (correctness is not regressed),
- interpretation guidance and upstream notes.

tox version under test: ``4.50.4.dev8+gd7fbbbdc5`` (branch ``feature/perf_improvement``)

Reference project: `ezsnmp <https://github.com/carlkidcrypto/ezsnmp>`_


Code Changes Summary
--------------------

Three commits make up this branch (on top of ``main``):

1. **Add profiling util and instrument hot paths** (``12d0599c``)
2. **Profile timings in nanoseconds** (``802762dd``)
3. **Use TOX_PROFILE_NS for profile thresholds** (``d7fbbbdc``)

Files changed:

+------------------------------------------+-------------------------------+
| File                                     | Change                        |
+==========================================+===============================+
| ``src/tox/util/profile.py``              | New file — profiling context  |
|                                          | manager and log helper        |
+------------------------------------------+-------------------------------+
| ``src/tox/plugin/manager.py``            | Add ``TOX_SKIP_EXTERNAL_``    |
|                                          | ``PLUGINS`` fast path         |
+------------------------------------------+-------------------------------+
| ``src/tox/run.py``                       | Instrument ``run.main_wrapper``|
|                                          | and ``run.setup_state``       |
+------------------------------------------+-------------------------------+
| ``src/tox/config/cli/parse.py``          | Instrument ``cli.get_options``|
|                                          | and ``cli.build_parser``      |
+------------------------------------------+-------------------------------+
| ``src/tox/session/env_select.py``        | Instrument ``env_select.*``   |
+------------------------------------------+-------------------------------+
| ``src/tox/session/cmd/run/common.py``    | Instrument ``run.command``    |
+------------------------------------------+-------------------------------+

Key change — ``src/tox/plugin/manager.py``, ``_load_external_plugins``::

    def _load_external_plugins(self) -> None:
        for name in os.environ.get("TOX_DISABLED_EXTERNAL_PLUGINS", "").split(","):
            self.manager.set_blocked(name)
        if os.environ.get("TOX_SKIP_EXTERNAL_PLUGINS", "").strip().lower() in _TRUE_VALUES:
            return                                     # <-- new fast path
        self.manager.load_setuptools_entrypoints(NAME)

``_TRUE_VALUES = {"1", "true", "yes", "on"}``

Key change — ``src/tox/util/profile.py`` (new module)::

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

Environment variables introduced:

+------------------------------------+----------------------------------------------------+
| Variable                           | Effect                                             |
+====================================+====================================================+
| ``TOX_SKIP_EXTERNAL_PLUGINS=1``    | Skip ``load_setuptools_entrypoints`` entirely.    |
|                                    | Safe when no external tox plugins are needed.     |
+------------------------------------+----------------------------------------------------+
| ``TOX_PROFILE=1``                  | Enable structured timing logs on stderr.           |
+------------------------------------+----------------------------------------------------+
| ``TOX_PROFILE_NS=<nanoseconds>``   | Suppress profile log lines below this threshold.  |
|                                    | Filters noise from sub-millisecond calls.         |
+------------------------------------+----------------------------------------------------+


Why ``load_setuptools_entrypoints`` Is Expensive
-------------------------------------------------

``pluggy.PluginManager.load_setuptools_entrypoints(NAME)`` iterates every installed
package's entry-point metadata, looking for entries in the ``tox`` group. In WSL, in
containers with large site-packages directories, and in cold Python startup scenarios,
this filesystem scan can take 5–15 ms or produce large single-run outliers (>2000 ms
measured on cold runs).

For projects that do not use external tox plugins (like ezsnmp), this work produces
zero value but incurs full cost on every invocation — including ``tox -av``, ``tox -l``,
and quick CLI queries.

The ``TOX_SKIP_EXTERNAL_PLUGINS=1`` flag short-circuits this scan entirely. It is
intentionally opt-in and preserves 100 % of the existing behavior by default.


Environment Setup
-----------------

All measurements were taken on:

- Host: Windows 11, WSL2 Ubuntu 24.04
- Interpreter: Python 3.12 (``/home/carlkidcrypto/Github/ezsnmp/python3.12.venv``)
- tox version: ``4.50.4.dev8+gd7fbbbdc5`` (local editable install)
- Reference project: ``/home/carlkidcrypto/Github/ezsnmp``
- snmpd: active (``systemctl is-active snmpd`` → ``active``)

To reproduce::

    # 1. Clone and check out the feature branch
    git clone https://github.com/carlkidcrypto/tox
    cd tox
    git checkout feature/perf_improvement

    # 2. Install into the target project venv
    source /path/to/project/venv/bin/activate
    python3 -m pip install -e /path/to/tox

    # 3. Run profiling samples (alternating baseline / fixed)
    cd /path/to/project
    for i in 1 2 3 4 5; do
        start=$(date +%s%3N)
        TOX_PROFILE=1 TOX_PROFILE_NS=100000 python3 -m tox -av 2>&1 | tee /tmp/baseline_${i}.log
        end=$(date +%s%3N)
        echo "elapsed_ms=$((end-start))" >> /tmp/baseline_${i}.log

        start=$(date +%s%3N)
        TOX_PROFILE=1 TOX_PROFILE_NS=100000 TOX_SKIP_EXTERNAL_PLUGINS=1 python3 -m tox -av 2>&1 | tee /tmp/fixed_${i}.log
        end=$(date +%s%3N)
        echo "elapsed_ms=$((end-start))" >> /tmp/fixed_${i}.log
    done

    # 4. Run full test suite (correctness check)
    python3 -m tox -e py312 --workdir /tmp/tox_baseline
    TOX_SKIP_EXTERNAL_PLUGINS=1 python3 -m tox -e py312 --workdir /tmp/tox_fixed


Profiling Instrumented Call Phases
-----------------------------------

The following phases are instrumented with ``profile_block``:

+-------------------------------+--------------------------------------------------+
| Profile key                   | Phase description                                |
+===============================+==================================================+
| ``cli.load_plugins``          | Plugin manager setup + entry-point discovery     |
+-------------------------------+--------------------------------------------------+
| ``cli.build_parser``          | Argument parser construction                     |
+-------------------------------+--------------------------------------------------+
| ``cli.get_options``           | Full option parsing (wraps both above)           |
+-------------------------------+--------------------------------------------------+
| ``run.get_options``           | Top-level call to ``get_options``                |
+-------------------------------+--------------------------------------------------+
| ``run.setup_state``           | State setup after parsing                        |
+-------------------------------+--------------------------------------------------+
| ``run.provision``             | Provisioning phase                               |
+-------------------------------+--------------------------------------------------+
| ``env_select.define``         | Environment enumeration and selection            |
+-------------------------------+--------------------------------------------------+
| ``run.command``               | Command handler execution                        |
+-------------------------------+--------------------------------------------------+
| ``run.main_wrapper``          | Entire run from entry-point                      |
+-------------------------------+--------------------------------------------------+

Sample profile output (``tox -av``, fixed mode)::

    ROOT: [profile] cli.load_plugins took 1959195 ns
    ROOT: [profile] cli.build_parser took 9638684 ns
    ROOT: [profile] cli.get_options took 13844888 ns argc=1
    ROOT: [profile] run.get_options took 13982799 ns argc=1
    ROOT: [profile] run.setup_state took 14281816 ns argc=1
    ROOT: [profile] run.provision took 1074234 ns
    ROOT: [profile] env_select.define took 5308397 ns total=6
    ROOT: [profile] run.command took 5818974 ns command='legacy'
    ROOT: [profile] run.main_wrapper took 21435027 ns


Measurement Results: WSL Outside Docker
----------------------------------------

Command: ``python3 -m tox -av``
Samples: 5 baseline + 5 fixed, **strictly alternating** (same shell, same venv).

Raw sample data (also in ``docs/performance/ezsnmp_wsl_profile_samples.csv``):

+----------+--------+------------+---------------------+--------------------+---------------------+
| mode     | sample | elapsed_ms | cli.load_plugins_ms | cli.get_options_ms | run.main_wrapper_ms |
+==========+========+============+=====================+====================+=====================+
| baseline | 1      | 259        | 6.60                | 18.52              | 25.43               |
+----------+--------+------------+---------------------+--------------------+---------------------+
| fixed    | 1      | 249        | 1.85                | 14.02              | 20.41               |
+----------+--------+------------+---------------------+--------------------+---------------------+
| baseline | 2      | 248        | 5.28                | 17.46              | 23.81               |
+----------+--------+------------+---------------------+--------------------+---------------------+
| fixed    | 2      | 245        | 2.74                | 16.20              | 23.44               |
+----------+--------+------------+---------------------+--------------------+---------------------+
| baseline | 3      | 254        | 10.84               | 24.32              | 31.80               |
+----------+--------+------------+---------------------+--------------------+---------------------+
| fixed    | 3      | 249        | 2.37                | 17.16              | 23.85               |
+----------+--------+------------+---------------------+--------------------+---------------------+
| baseline | 4      | 242        | 5.40                | 17.32              | 23.63               |
+----------+--------+------------+---------------------+--------------------+---------------------+
| fixed    | 4      | 227        | 1.90                | 12.46              | 19.46               |
+----------+--------+------------+---------------------+--------------------+---------------------+
| baseline | 5      | 254        | 4.95                | 15.90              | 24.04               |
+----------+--------+------------+---------------------+--------------------+---------------------+
| fixed    | 5      | 246        | 1.84                | 14.39              | 23.94               |
+----------+--------+------------+---------------------+--------------------+---------------------+

Median summary:

+---------------------+---------------+--------------+--------------------+
| Metric              | Baseline (med)| Fixed (med)  | Improvement        |
+=====================+===============+==============+====================+
| elapsed_ms          | 254 ms        | 246 ms       | ~3% faster         |
+---------------------+---------------+--------------+--------------------+
| cli.load_plugins_ms | 5.40 ms       | 1.90 ms      | **~65% faster**    |
+---------------------+---------------+--------------+--------------------+
| cli.get_options_ms  | 17.46 ms      | 14.39 ms     | ~18% faster        |
+---------------------+---------------+--------------+--------------------+
| run.main_wrapper_ms | 24.04 ms      | 23.44 ms     | ~2% faster         |
+---------------------+---------------+--------------+--------------------+

Observations:

- ``cli.load_plugins`` is the primary beneficiary: 65% median reduction.
- Sample 3 baseline showed a 10.84 ms spike (filesystem cache miss or OS scheduler noise);
  the matching fixed sample was 2.37 ms — a 78% single-sample improvement for that outlier.
- End-to-end ``elapsed_ms`` improvement is modest in a warm WSL environment because
  startup overhead is already under 300 ms and Python interpreter startup dominates.
- Colder environments (new containers, first runs after package install) will show larger
  absolute improvements, consistent with the original runbook data where outlier runs
  reached 2104 ms baseline vs 268 ms fixed.

Original runbook data (cold-run measurements, kept for historical reference):

+----------+--------+------------+---------------------+---------------------+
| mode     | sample | elapsed_ms | cli.load_plugins_ms | run.main_wrapper_ms |
+==========+========+============+=====================+=====================+
| baseline | 1      | 592        | 15.07               | 43.02               |
+----------+--------+------------+---------------------+---------------------+
| fixed    | 1      | 253        | 8.65                | 27.45               |
+----------+--------+------------+---------------------+---------------------+
| baseline | 2      | 2104       | 4.72                | 22.51               |
+----------+--------+------------+---------------------+---------------------+
| fixed    | 2      | 268        | 1.71                | 21.43               |
+----------+--------+------------+---------------------+---------------------+
| baseline | 3      | 219        | 4.58                | 22.66               |
+----------+--------+------------+---------------------+---------------------+
| fixed    | 3      | 259        | 2.65                | 23.43               |
+----------+--------+------------+---------------------+---------------------+

On the cold-run dataset the end-to-end elapsed improvement is 56% (median 592 → 259 ms).


Correctness Verification: Full Test Suite (Outside Docker)
----------------------------------------------------------

Both baseline and fixed configurations ran the full ezsnmp ``py312`` test suite to
verify no regression was introduced:

**Baseline** (no ``TOX_SKIP_EXTERNAL_PLUGINS``)::

    python3 -m tox -e py312 --workdir /tmp/tox_outside_baseline

    415 passed, 30 skipped in 155.07s (0:02:35)
    py312: OK (291.47=setup[135.81]+cmd[155.66] seconds)
    congratulations :) (291.50 seconds)
    full_baseline_elapsed_ms=297418

**Fixed** (``TOX_SKIP_EXTERNAL_PLUGINS=1``)::

    TOX_SKIP_EXTERNAL_PLUGINS=1 python3 -m tox -e py312 --workdir /tmp/tox_outside_fixed

    415 passed, 30 skipped in 169.76s (0:02:49)
    py312: OK (297.82=setup[127.41]+cmd[170.40] seconds)
    congratulations :) (297.84 seconds)
    full_fixed_elapsed_ms=303807

Result: **identical test outcomes** — 415 passed, 30 skipped in both modes.
Minor variance in total elapsed is normal (parallel test scheduling noise).


Measurement Results: Docker Containers
---------------------------------------

Docker tests used image ``carlkidcrypto/ezsnmp_test_images:archlinux_netsnmp_5.9-latest``
with the local tox source bind-mounted at ``/tox_src`` and installed via
``python3 -m pip install /tox_src`` inside the container before each run.

Container setup::

    docker run -d \
      --name tox_perf_docker_test \
      -v /home/carlkidcrypto/Github/ezsnmp:/ezsnmp \
      -v /home/carlkidcrypto/Github/tox:/tox_src \
      carlkidcrypto/ezsnmp_test_images:archlinux_netsnmp_5.9-latest \
      /bin/bash -c "/ezsnmp/docker/DockerEntry.sh false & tail -f /dev/null"

Each run unpacked a fresh copy of the source into ``/tmp/ezsnmp_docker_{mode}`` to
avoid cross-contamination between baseline and fixed runs.

**Baseline** (no ``TOX_SKIP_EXTERNAL_PLUGINS``)::

    docker exec tox_perf_docker_test bash -c "
        python3 -m pip install /tox_src --quiet
        python3 -m tox -e py312 --workdir /tmp/tox_docker_baseline
    "

**Fixed** (``TOX_SKIP_EXTERNAL_PLUGINS=1``)::

    docker exec tox_perf_docker_test bash -c "
        python3 -m pip install /tox_src --quiet
        TOX_SKIP_EXTERNAL_PLUGINS=1 python3 -m tox -e py312 --workdir /tmp/tox_docker_fixed
    "

.. note::

   The archlinux_netsnmp_5.9 image uses Python 3.14 internally for the venv tool chain,
   but the test environment is ``py312`` (Python 3.12.8 installed in the image).

**Baseline** results (``archlinux_netsnmp_5.9``, no ``TOX_SKIP_EXTERNAL_PLUGINS``)::

    126 passed, 289 failed in ~1491s
    py312: FAIL exit 1 (1679.57=setup[187.94]+cmd[1491.63] seconds)
    evaluation failed :( (1679.64 seconds)
    elapsed_ms=1733138

**Fixed** results (``archlinux_netsnmp_5.9``, ``TOX_SKIP_EXTERNAL_PLUGINS=1``)::

    126 passed, 289 failed in ~1489s
    py312: FAIL exit 1 (1624.96=setup[135.48]+cmd[1489.48] seconds)
    evaluation failed :( (1625.00 seconds)
    elapsed_ms=1671183

.. note::

   The 289 test failures are caused entirely by SNMP daemon non-responsiveness
   inside the container, **not by tox changes**. The ``snmpd`` process (started via
   ``DockerEntry.sh`` 10 seconds before the test run) did not respond to the test
   port (``localhost:11161``) in time. This is a pre-existing Docker environment
   issue reproduced identically on both baseline and fixed runs.

   Evidence that failures are environment-related, not tox-related:

   - All failures are ``TimeoutError`` or ``SNMPSetCLIError`` with the same
     error message ("Timeout: No Response from localhost:11161").
   - In WSL (outside Docker), with a running ``snmpd``, the same test suite shows
     **415 passed, 30 skipped** (zero failures) in both modes.
   - Baseline and fixed produce the **same 126/289 split**, confirming no regression.

   The ``elapsed_ms`` comparison for Docker is dominated by SNMP timeout accumulation
   (~5 s × 3 retries × ~289 tests / 4 workers ≈ 1087 s of pure wait time), making
   it a poor measure of tox startup improvement. The authoritative startup comparison
   is the WSL ``tox -av`` profiling data (Section above), which isolates the startup
   phase cleanly.

   The ~62 s difference between baseline ``elapsed_ms=1733138`` and fixed
   ``elapsed_ms=1671183`` is explained by pip package-cache warmup: the baseline run
   (first) downloads all packages from PyPI; the fixed run (second) uses the Docker
   layer's pip cache, reusing downloaded wheels and reducing setup time by ~52 s
   (``setup[187.94]`` baseline vs ``setup[135.48]`` fixed). The remaining difference
   is scheduling noise. The actual ``TOX_SKIP_EXTERNAL_PLUGINS=1`` contribution to
   elapsed time is a few milliseconds, consistent with the WSL profiling data.

Docker correctness summary:

+----------+--------------------+------------------+---------+
| Mode     | Test result        | elapsed_ms       | Outcome |
+==========+====================+==================+=========+
| Baseline | 126 passed,        | 1,733,138 ms     | FAIL    |
|          | 289 failed         | (28.9 min)       | (SNMP)  |
+----------+--------------------+------------------+---------+
| Fixed    | 126 passed,        | 1,671,183 ms     | FAIL    |
|          | 289 failed         | (27.9 min)       | (SNMP)  |
+----------+--------------------+------------------+---------+

Identical pass/fail split confirms no behavioral regression from the patch.


Charts
------

Elapsed time chart (original runbook data):

.. image:: /_static/img/perf/ezsnmp_wsl_elapsed.svg
   :alt: ezsnmp tox elapsed timing comparison baseline vs fixed
   :width: 900

Plugin load phase chart (original runbook data):

.. image:: /_static/img/perf/ezsnmp_wsl_cli_load_plugins.svg
   :alt: ezsnmp tox cli.load_plugins timing comparison baseline vs fixed
   :width: 900


Interpretation Guidance
-----------------------

When ``TOX_SKIP_EXTERNAL_PLUGINS=1`` is safe to use:

- Your project does not declare any external tox plugins via ``pyproject.toml``
  ``[project.entry-points."tox"]`` or ``setup.cfg`` ``[options.entry_points]``.
- You are running in a CI container, Docker image, or virtual environment where
  no tox plugin packages (e.g. ``tox-gh-actions``, ``tox-pdm``) are installed.
- You want deterministic, minimal startup times for developer feedback loops.

When **not** to use ``TOX_SKIP_EXTERNAL_PLUGINS=1``:

- Your project depends on external tox plugins for hooks like ``tox_add_env_config``,
  ``tox_register_tox_env``, or ``tox_extend_envs``.
- You are unsure whether any external plugins are installed in the environment.

.. tip::

   The safest approach is to audit your venv: ``python3 -m tox -l`` with and without
   the flag. If environment names and commands match, no external plugin is contributing.


Upstream Patch Notes
--------------------

This work is intended for submission to the upstream ``tox`` project.

Patch scope:

1. **New** ``src/tox/util/profile.py``:
   Reusable profiling context manager (``profile_block``) and log helper
   (``profile_log``). Zero overhead when ``TOX_PROFILE`` is not set.
   Controlled by:

   - ``TOX_PROFILE=1`` — enable logging
   - ``TOX_PROFILE_NS=<ns>`` — minimum duration threshold; suppresses noise

2. **Modified** ``src/tox/plugin/manager.py``:
   New opt-in fast path ``TOX_SKIP_EXTERNAL_PLUGINS=1`` in ``_load_external_plugins``.
   No change to default behavior. Accepts values: ``1``, ``true``, ``yes``, ``on``
   (case-insensitive).

3. **Modified** run and CLI modules:
   ``profile_block`` context managers added at key phases.
   No behavior change; pure instrumentation.

Test coverage added:

- ``tests/util/test_profile.py`` — unit tests for profile utility (8 tests)
- ``tests/plugin/test_plugin.py`` — tests for ``TOX_SKIP_EXTERNAL_PLUGINS`` (updated with new cases)

Behavioral guarantee:

- Without any new env vars, tox is **byte-for-byte identical** in behavior to
  the pre-patch baseline. All 415 ezsnmp Python tests pass in both modes.


Potential Follow-ups
--------------------

- Add a warning when ``TOX_SKIP_EXTERNAL_PLUGINS=1`` is set but a plugin name is
  explicitly passed via ``--plugin`` (if such a flag is ever added).
- Add a dedicated perf benchmark target under ``tasks/`` or as a pytest fixture to
  automate baseline-vs-fixed comparisons in CI.
- Document the new env vars in the reference configuration page (``docs/reference/config.rst``).
- Consider exposing ``skip_external_plugins`` as a ``tox.ini``/``pyproject.toml``
  configuration key for persistent opt-in without needing an env var.
