"""Manual end-to-end inspection of a real pipeline run.

This script is **not** picked up by pytest — see ``tests/conftest.py`` and
the ``python_files = "test_*.py"`` setting in ``pytest.ini``.  Run it by
hand to inspect everything the framework emits in one shot:

    *   Per-task console output (which functions fired, in what order).
    *   Per-task log files under ``tests/manual_tests/logs/`` (one ``.log``
        per task — see the ``FileHandler`` attached in ``Task.__init__``).
    *   The HTML email the ``HTMLSMTPHandler`` sends to maildev (open the
        web UI and check the rendered "Downstream Impact" list).

Prerequisites
-------------
You only need **Node.js + maildev** available somewhere on your system
(``npm install -g maildev`` is the usual install).  The script will
launch maildev for you if it isn't already running; if you started it
yourself, the script will detect and reuse it.

    The script connects to ``127.0.0.1`` (not ``localhost``) on purpose:
    on Windows, ``localhost`` often resolves to IPv6 ``::1`` first while
    maildev binds IPv4 only, producing ``WinError 10061`` (connection
    refused).  If your maildev uses a different host/port, edit
    ``SMTP_HOST`` / ``SMTP_PORT`` / ``WEB_PORT`` below.

From the project root, run:

    python tests/manual_tests/manual_pipeline_inspect.py

Use ``--keep-logs`` to preserve any previous ``.log`` files instead of
wiping them at startup.  Use ``--no-start-maildev`` if you want to
manage maildev yourself and have the script only verify it's already
listening.

Then inspect:
  * The console output below for execution order.
  * The per-task files in ``tests/manual_tests/logs/``.
  * The maildev web UI at http://localhost:1080.

Expected outcomes
-----------------
*   Tasks ``A0_ingest_orders``, ``B_validate_orders``, ``C_enrich_with_users``,
    ``E_compute_kpis`` and ``H_archive_run_metadata`` succeed (their
    ``func`` is called exactly once).
*   Tasks ``D_join_inventory`` and ``F_publish_dashboard`` raise (their
    ``func`` is called once and then re-raises).
*   Task ``G_notify_ops`` never runs (cascading skip from
    ``F_publish_dashboard``).
*   Two emails arrive in maildev, one per failure, each with the matching
    "Downstream Impact" entries.

Why sequential mode?
--------------------
maildev's SMTP listener is single-threaded.  When the pipeline runs in
parallel and two tasks fail at the same time, the handler tries to open
two SMTP connections simultaneously; maildev accepts the first and
refuses the second (``ConnectionRefusedError``).  To keep this manual
script deterministic without changing the library, the pipeline runs
in sequential mode here.  The library itself supports both modes — see
the integration test for the parallel path.
"""

from __future__ import annotations

import argparse
import os
import shutil
import socket
import subprocess
import sys
import time
import traceback
from collections.abc import Callable
from typing import Any

# Make the in-tree package importable when the script is run directly.
_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from processes import HTMLSMTPHandler, Process, Task, TaskDependency  # noqa: E402

# --------------------------------------------------------------------------- #
# Maildev wiring                                                              #
# --------------------------------------------------------------------------- #

SMTP_HOST = "127.0.0.1"    # avoid Windows IPv6/localhost resolution quirks
SMTP_PORT = 1025           # maildev's default SMTP port (web UI runs on 1080)
WEB_PORT = 1080            # maildev's default web UI port
FROM_ADDR = "pipeline-alerts@enterprise.test"
TO_ADDRS = ["sre-oncall@enterprise.test"]


def _make_mail_handler() -> HTMLSMTPHandler:
    return HTMLSMTPHandler(
        mailhost=(SMTP_HOST, SMTP_PORT),
        fromaddr=FROM_ADDR,
        toaddrs=TO_ADDRS,
        timeout=5,
    )


# --------------------------------------------------------------------------- #
# Task functions                                                              #
# --------------------------------------------------------------------------- #


def ingest_orders(
    feed: str,
    batch_size: int = 500,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Pull raw orders from the source feed.  Always succeeds."""
    print(f"  [ingest_orders] feed={feed!r} batch_size={batch_size} dry_run={dry_run}")
    return {
        "feed": feed,
        "rows": [
            {"order_id": "O-1001", "user_id": "U-7",  "sku": "SKU-A", "amount": 49.90},
            {"order_id": "O-1002", "user_id": "U-12", "sku": "SKU-B", "amount": 12.00},
            {"order_id": "O-1003", "user_id": "U-7",  "sku": "SKU-C", "amount":  3.50},
        ],
        "batch_size": batch_size,
        "dry_run": dry_run,
    }


def validate_orders(
    schema_version: str,
    payload: dict[str, Any] | None = None,
    strict: bool = True,
) -> dict[str, Any]:
    """Validate the ingested batch against the schema.  Uses kwarg injection."""
    rows = (payload or {}).get("rows", [])
    print(f"  [validate_orders] schema={schema_version} rows={len(rows)} strict={strict}")
    if not rows:
        raise ValueError("empty payload — schema validation cannot proceed")
    return {
        "schema_version": schema_version,
        "row_count": len(rows),
        "strict": strict,
    }


def enrich_with_users(
    users_source: str,
    payload: dict[str, Any] | None = None,
    timeout: int = 10,
) -> dict[str, Any]:
    """Join each order with its user record.  Uses positional injection."""
    rows = (payload or {}).get("rows", [])
    print(f"  [enrich_with_users] source={users_source} rows={len(rows)} timeout={timeout}s")
    return {
        "enriched_rows": [
            {**row, "user_email": f"user{row['user_id']}@example.test"}
            for row in rows
        ],
        "timeout": timeout,
    }


def join_inventory(
    warehouse: str,
    payload: dict[str, Any] | None = None,
    strategy: str = "inner",
) -> dict[str, Any]:
    """Join with inventory levels.  **Fails** — simulates a missing SKU map."""
    rows = (payload or {}).get("enriched_rows", [])
    print(f"  [join_inventory] warehouse={warehouse} rows={len(rows)} strategy={strategy}")
    raise RuntimeError(
        f"missing SKU mapping for warehouse={warehouse!r} (strategy={strategy})"
    )


def compute_kpis(
    window: str,
    validated: dict[str, Any] | None = None,
    currency: str = "USD",
) -> dict[str, Any]:
    """Aggregate KPIs from the validated + enriched chain.  Uses kwarg injection."""
    row_count = (validated or {}).get("row_count", 0)
    print(f"  [compute_kpis] window={window} rows={row_count} currency={currency}")
    return {
        "window": window,
        "kpi_rows": row_count,
        "currency": currency,
        "gmv": 65.40,
    }


def publish_dashboard(
    audience: str,
    kpis: dict[str, Any] | None = None,
    cache_ttl: int = 60,
) -> dict[str, Any]:
    """Push KPIs to the dashboard.  **Fails** — service unreachable."""
    print(f"  [publish_dashboard] audience={audience} cache_ttl={cache_ttl}s")
    raise ConnectionError(
        f"dashboard service unreachable (audience={audience!r}, cache_ttl={cache_ttl})"
    )


def notify_ops(*_args: Any, **_kwargs: Any) -> str:
    """Post a message to the ops channel.  Cascading-skip target."""
    print("  [notify_ops] this should never run — FAILED upstream")
    return "ops-notified"


def archive_run_metadata(
    destination: str,
    retention_days: int = 30,
) -> str:
    """Archive the run manifest.  Runs in parallel with publish_dashboard."""
    print(
        f"  [archive_run_metadata] destination={destination} "
        f"retention_days={retention_days}"
    )
    return f"archived://{destination}?retention={retention_days}d"


# --------------------------------------------------------------------------- #
# Build the DAG                                                              #
# --------------------------------------------------------------------------- #


def _log_path(logs_dir: str, name: str) -> str:
    return os.path.join(logs_dir, f"{name}.log")


def build_tasks(logs_dir: str, mail_handler: HTMLSMTPHandler) -> list[Task]:
    dep = TaskDependency

    def _task(
        name: str,
        func: Callable[..., Any],
        args: tuple[Any, ...] = (),
        kwargs: dict[str, Any] | None = None,
        deps: list[TaskDependency] | None = None,
    ) -> Task:
        return Task(
            name=name,
            log_path=_log_path(logs_dir, name),
            func=func,
            args=args,
            kwargs=kwargs or {},
            dependencies=deps or [],
            html_mail_handler=mail_handler,
        )

    return [
        # Root
        _task(
            "A0_ingest_orders",
            ingest_orders,
            args=("orders_feed",),
            kwargs={"batch_size": 1000, "dry_run": False},
        ),
        # Validation branch (kwarg injection)
        _task(
            "B_validate_orders",
            validate_orders,
            args=("v2",),
            kwargs={"strict": True},
            deps=[
                dep(
                    "A0_ingest_orders",
                    use_result_as_additional_kwargs=True,
                    additional_kwarg_name="payload",
                ),
            ],
        ),
        # Enrichment branch (positional injection)
        _task(
            "C_enrich_with_users",
            enrich_with_users,
            args=("users_api",),
            kwargs={"timeout": 30},
            deps=[
                dep(
                    "A0_ingest_orders",
                    use_result_as_additional_args=True,
                ),
            ],
        ),
        # Inventory join (positional injection) — **FAILS**
        _task(
            "D_join_inventory",
            join_inventory,
            args=("warehouse_eu",),
            kwargs={"strategy": "outer"},
            deps=[
                dep(
                    "C_enrich_with_users",
                    use_result_as_additional_args=True,
                ),
            ],
        ),
        # KPI aggregation (kwarg injection from B, deps on B and C)
        _task(
            "E_compute_kpis",
            compute_kpis,
            args=("daily",),
            kwargs={"currency": "USD"},
            deps=[
                dep(
                    "B_validate_orders",
                    use_result_as_additional_kwargs=True,
                    additional_kwarg_name="validated",
                ),
                dep("C_enrich_with_users"),
            ],
        ),
        # Dashboard publish (positional injection) — **FAILS**
        _task(
            "F_publish_dashboard",
            publish_dashboard,
            args=("executive",),
            kwargs={"cache_ttl": 60},
            deps=[
                dep(
                    "E_compute_kpis",
                    use_result_as_additional_args=True,
                ),
            ],
        ),
        # Ops notification — **SKIPPED** (F failed)
        _task(
            "G_notify_ops",
            notify_ops,
            kwargs={"channel": "#ops-firehose"},
            deps=[dep("F_publish_dashboard")],
        ),
        # Audit archive — runs in parallel with F, independent of failures
        _task(
            "H_archive_run_metadata",
            archive_run_metadata,
            args=("s3://audit-lake/",),
            kwargs={"retention_days": 90},
            deps=[dep("E_compute_kpis")],
        ),
    ]


# --------------------------------------------------------------------------- #
# Entry point                                                                 #
# --------------------------------------------------------------------------- #


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--keep-logs",
        action="store_true",
        help="preserve any previous .log files in the logs dir "
        "(default: wipe them at startup so each run is a fresh inspection).",
    )
    parser.add_argument(
        "--no-start-maildev",
        action="store_true",
        help="do not try to launch maildev; only verify that the SMTP "
        "listener is already up.  Use this if you want to manage "
        "maildev yourself.",
    )
    args = parser.parse_args()

    here = os.path.dirname(os.path.abspath(__file__))
    logs_dir = os.path.join(here, "logs")
    os.makedirs(logs_dir, exist_ok=True)

    if not args.keep_logs:
        cleared = 0
        for name in os.listdir(logs_dir):
            if name.endswith(".log"):
                os.remove(os.path.join(logs_dir, name))
                cleared += 1
        if cleared:
            print(f"logs dir:   {logs_dir} (cleared {cleared} stale .log file(s))")
        else:
            print(f"logs dir:   {logs_dir} (empty)")
    else:
        print(f"logs dir:   {logs_dir} (keeping existing files — --keep-logs)")

    print(f"recipients: {TO_ADDRS}")

    mail_handler = _make_mail_handler()
    tasks = build_tasks(logs_dir, mail_handler)
    print(f"tasks:      {len(tasks)}")
    print("-" * 72)

    exit_code = 0
    try:
        with Process(tasks) as process:
            # Sequential mode: maildev's SMTP listener is single-threaded,
            # so concurrent connections from parallel failures race and the
            # second one is refused.  See the module docstring.
            result = process.run(parallel=False)
    except Exception:
        print("Process raised an unexpected exception:")
        traceback.print_exc()
        exit_code = 2
    else:
        print("-" * 72)
        print("passed:")
        for name in sorted(result.passed_tasks_results):
            print(f"  + {name}")
        print("failed (includes cascading-skipped):")
        for name in sorted(result.failed_tasks):
            print(f"  - {name}")

    if exit_code == 0:
        print("-" * 72)
        print(f"Inspect the per-task logs in:\n  {logs_dir}")
        print(f"And the rendered email at:\n  http://localhost:{WEB_PORT}")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
