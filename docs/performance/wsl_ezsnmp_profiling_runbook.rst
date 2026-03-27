WSL Profiling Runbook (tox on ezsnmp)
====================================

Goal
----

This runbook captures a reproducible workflow to profile tox startup and command dispatch
inside WSL, using ezsnmp as the target project.

It documents:

- how measurements were collected,
- where raw data is stored,
- what optimization was applied,
- how to rerun and compare baseline vs fixed.

Scope
-----

This benchmark measures tox command startup and environment selection overhead for:

- command: ``python3 -m tox -av``
- location: ``/home/carlkidcrypto/Github/ezsnmp``
- interpreter: ``/home/carlkidcrypto/Github/ezsnmp/python3.12.venv/bin/python3``

Why this command:

- it is fast to execute,
- it isolates startup and discovery cost,
- it does not include full test runtime noise.

Optimization Under Test
-----------------------

A new opt-in fast path was added in tox plugin loading:

- baseline mode: normal behavior (external entry-point discovery enabled)
- fixed mode: set ``TOX_SKIP_EXTERNAL_PLUGINS=1`` to skip external entry-point discovery

This is intentionally opt-in so default behavior and compatibility are unchanged.

Measurement Procedure
---------------------

1. Activate the ezsnmp venv in WSL::

    source /home/carlkidcrypto/Github/ezsnmp/python3.12.venv/bin/activate

2. Ensure local tox source is installed in that venv::

    python3 -m pip install -e /home/carlkidcrypto/Github/tox

3. Run baseline sample::

    start=$(date +%s%3N)
    TOX_PROFILE=1 TOX_PROFILE_MIN_MS=1 python3 -m tox -av 2>&1 | tee /tmp/ezsnmp_tox_profile_baseline.log
    end=$(date +%s%3N)
    echo "elapsed_ms=$((end-start))" | tee -a /tmp/ezsnmp_tox_profile_baseline.log

4. Run fixed sample::

    start=$(date +%s%3N)
    TOX_PROFILE=1 TOX_PROFILE_MIN_MS=1 TOX_SKIP_EXTERNAL_PLUGINS=1 python3 -m tox -av 2>&1 | tee /tmp/ezsnmp_tox_profile_fixed.log
    end=$(date +%s%3N)
    echo "elapsed_ms=$((end-start))" | tee -a /tmp/ezsnmp_tox_profile_fixed.log

5. Repeat multiple times and alternate baseline/fixed runs.

Notes for better signal quality:

- Keep the same shell and venv for all samples.
- Avoid heavy host activity during sampling.
- Use median across samples, not just a single run.

Collected Data
--------------

Raw sample table is stored in:

- ``docs/performance/ezsnmp_wsl_profile_samples.csv``

Summary table:

+----------+--------+------------+---------------------+----------------------+
| mode     | sample | elapsed_ms | cli.load_plugins_ms | run.main_wrapper_ms  |
+==========+========+============+=====================+======================+
| baseline | 1      | 592        | 15.07               | 43.02                |
+----------+--------+------------+---------------------+----------------------+
| fixed    | 1      | 253        | 8.65                | 27.45                |
+----------+--------+------------+---------------------+----------------------+
| baseline | 2      | 2104       | 4.72                | 22.51                |
+----------+--------+------------+---------------------+----------------------+
| fixed    | 2      | 268        | 1.71                | 21.43                |
+----------+--------+------------+---------------------+----------------------+
| baseline | 3      | 219        | 4.58                | 22.66                |
+----------+--------+------------+---------------------+----------------------+
| fixed    | 3      | 259        | 2.65                | 23.43                |
+----------+--------+------------+---------------------+----------------------+

Quick read:

- Plugin discovery time dropped in all 3 samples.
- End-to-end elapsed time improved strongly on cold/outlier runs.
- Warm runs are close and can be noisy in either direction.

Median deltas from the dataset:

- elapsed_ms median: baseline 592 ms -> fixed 259 ms (about 56.3% faster)
- cli.load_plugins_ms median: baseline 4.72 ms -> fixed 2.65 ms (about 43.9% faster)

Charts
------

Elapsed time chart:

.. image:: /_static/img/perf/ezsnmp_wsl_elapsed.svg
   :alt: ezsnmp tox elapsed timing comparison baseline vs fixed
   :width: 900

Plugin load phase chart:

.. image:: /_static/img/perf/ezsnmp_wsl_cli_load_plugins.svg
   :alt: ezsnmp tox cli.load_plugins timing comparison baseline vs fixed
   :width: 900

Interpretation Guidance
-----------------------

Use this decision framework:

- If your workload relies on external tox plugins, keep default behavior.
- If your workload does not use external tox plugins, use ``TOX_SKIP_EXTERNAL_PLUGINS=1``.
- For container and WSL environments with slow filesystem or package metadata scans,
  this flag reduces avoidable startup work.

Potential Follow-ups
--------------------

- Add a warning when ``TOX_SKIP_EXTERNAL_PLUGINS=1`` and an external plugin is explicitly requested.
- Add a dedicated perf micro-benchmark target under ``tests`` or ``tasks`` to automate this comparison.
- Add docs that list when skipping external plugin discovery is safe.
