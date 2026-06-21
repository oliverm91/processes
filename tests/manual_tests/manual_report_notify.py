"""Manual inspection: a mixed DAG whose ProcessExecutionReport is delivered by
email via SMTP, exercising every traced-variables configuration in one run.

Tasks no longer send per-task alerts; notification is delegated entirely to the
**report** path — ``ProcessExecutionReport.notify`` rendering the whole run as a
single HTML email and sending it to maildev. The traced-vars frame filter is now
configured per ``Task`` (capture-time), which feeds both the report and the
per-task logfile.

Run by hand and eyeball the result in maildev:

    python tests/manual_tests/manual_report_notify.py

What this exercises
-------------------
Tasks (independent and dependent):

*   ``load_config``    — independent, **succeeds** (produces config).
*   ``transform``      — **dependent** on ``load_config`` (consumes its result),
                         **succeeds** — a downstream task that *does* run.
*   ``fetch_orders``   — independent, **fails** from a frame holding several
                         rich local variables → **WITH traced variables**, using
                         the **default** frame filter.
*   ``decode_payload`` — independent, **fails** inside the stdlib ``json``
                         parser, with a **CUSTOM** ``traced_vars_frame_filter``
                         (``"json"``) so the traced variables come from json's
                         internal frame instead of the task frame.
*   ``noop_validate``  — independent, **fails** immediately with no locals bound
                         → **WITHOUT traced variables** (empty section).
*   ``aggregate``      — **dependent** on ``fetch_orders``, therefore
                         **cascade-skipped** (never runs) → appears under
                         "Downstream Impact".

Report delivery (the point of the script):

The single finished report is delivered once per combination of the full
delivery matrix — **2 languages x 4 palettes x 3 content styles x 2 only_errors
modes = 48 emails** — each sent to a distinct recipient whose local-part encodes
the combination (``report-<lang>-<palette>-<style>-<mode>``):

*   languages   — ``en`` and ``es``.
*   palettes    — ``neutral``, ``catppuccin``, ``neobones``, ``slate``.
*   styles      — the 3 ``ReportContent`` presets: ``full`` (traceback +
                  traced vars), ``trace`` (traceback only), ``min`` (neither).
*   modes       — ``all`` (``only_errors=False``, whole report) and ``errors``
                  (``only_errors=True``, errored entries only).

So a single run demonstrates, side by side: every language, every palette,
with/without traced variables and tracebacks, and whole-report vs errors-only.

Prerequisites
-------------
*   maildev running on ``127.0.0.1:1025`` (web UI on 1080).
*   The script connects to ``127.0.0.1`` (not ``localhost``) on purpose: on
    Windows, ``localhost`` often resolves to IPv6 ``::1`` first while maildev
    binds IPv4 only, producing ``WinError 10061``.

Inspect
-------
*   The console output for execution order and the per-task outcome table.
*   The maildev web UI at http://localhost:1080. Expected: **48 messages**, one
    per matrix combination, addressed to
    ``report-<lang>-<palette>-<style>-<mode>@inspect.test``. Filter by recipient
    to compare any axis in isolation — e.g. the same combo in ``en`` vs ``es``,
    or ``full`` vs ``min`` style, or ``all`` vs ``errors`` mode. The ``errors``
    messages also confirm ``decode_payload``'s traced variables differ from
    ``fetch_orders``' (custom vs default frame filter).
*   The per-task logfiles in ``tests/manual_tests/logs/``.
"""

from __future__ import annotations

import itertools
import json
import os
import sys
import traceback
from typing import Any

# Make the in-tree package importable when the script is run directly.
_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from processes import (  # noqa: E402
    EmailChannel,
    HTMLEmailStyle,
    Process,
    ProcessExecutionReport,
    ReportContent,
    SMTPConfig,
    Task,
    TaskDependency,
)

# --------------------------------------------------------------------------- #
# Constants                                                                   #
# --------------------------------------------------------------------------- #

SMTP_HOST = "127.0.0.1"
SMTP_PORT = 1025
WEB_PORT = 1080
FROM_ADDR = "report-canary@enterprise.test"

REPORT_TO_DOMAIN = "inspect.test"

# The delivery matrix: every combination is sent as its own email so each can be
# eyeballed side by side in maildev. The recipient local-part encodes the combo
# (language-palette-style-mode) so the messages are trivially distinguishable.
LANGUAGES = ("en", "es")
PALETTES = ("neutral", "catppuccin", "neobones", "slate")

# The 3 design "styles": content-verbosity presets built on ReportContent.
CONTENT_STYLES: dict[str, ReportContent] = {
    "full": ReportContent(show_traceback=True, show_traced_vars=True),
    "trace": ReportContent(show_traceback=True, show_traced_vars=False),
    "min": ReportContent(show_traceback=False, show_traced_vars=False),
}

# only_errors False (whole report) and True (errored entries only).
ERROR_MODES = {"all": False, "errors": True}


def _smtp(toaddr: str) -> SMTPConfig:
    return SMTPConfig(
        mailhost=(SMTP_HOST, SMTP_PORT),
        fromaddr=FROM_ADDR,
        toaddrs=[toaddr],
        timeout=5,
    )


# --------------------------------------------------------------------------- #
# Task functions                                                              #
# --------------------------------------------------------------------------- #


def load_config() -> dict[str, Any]:
    """Independent root task — succeeds and feeds ``transform``."""
    print("  [load_config] loading configuration ...")
    return {"region": "us-east-1", "batch_size": 500}


def transform(config: dict[str, Any]) -> str:
    """Dependent task — runs because its upstream succeeded."""
    print(f"  [transform] transforming with config={config} ...")
    return f"transformed::{config['region']}"


def fetch_orders(source: str, batch_id: int, *, region: str) -> list[int]:
    """Fails from a frame rich in local variables.

    With the default frame filter, *these* user locals (``endpoint``,
    ``attempt``, ``page_token``, ``collected``) are the ones traced.
    """
    endpoint = f"https://api.internal/{region}/orders"
    attempt = 3
    page_token = "p_98f3a2c"
    collected: list[int] = [101, 102, 103]
    print(f"  [fetch_orders] source={source!r} batch_id={batch_id} region={region!r}")
    raise ConnectionError(
        f"upstream {endpoint!r} refused the connection after {attempt} attempts "
        f"(page_token={page_token}, collected so far={collected})"
    )


def decode_payload(raw: str) -> Any:
    """Fails inside the stdlib ``json`` parser.

    Paired with ``traced_vars_frame_filter='json'`` the traced variables are
    captured from json's internal frame, not from this task frame.
    """
    print(f"  [decode_payload] decoding {raw!r} ...")
    return json.loads(raw)  # malformed input -> JSONDecodeError raised inside json/


def noop_validate() -> None:
    """Fails immediately with no local variables bound — the traced-variables
    section is empty (the 'without traced variables' case)."""
    print("  [noop_validate] validating ...")
    raise ValueError("validation rule 'non_empty' violated")


def aggregate(*_args: Any, **_kwargs: Any) -> str:
    """Downstream of ``fetch_orders`` — must be cascade-skipped, never run."""
    print("  [aggregate] this should never run — FAILED upstream")
    return "aggregated"


# --------------------------------------------------------------------------- #
# Build the DAG                                                               #
# --------------------------------------------------------------------------- #


def _log_path(logs_dir: str, name: str) -> str:
    return os.path.join(logs_dir, f"{name}.log")


def build_tasks(logs_dir: str) -> list[Task]:
    """A 6-task DAG: 2 independent successes/deps, 3 independent failures with
    distinct traced-vars configs, and 1 cascade-skipped dependent.

    The traced-vars frame filter is configured per ``Task`` (capture-time), not
    per channel: ``decode_payload`` pins capture to the stdlib ``json`` frame,
    the others use the default outermost-user-frame selection.
    """
    dep = TaskDependency

    return [
        # Independent success → feeds a dependent task.
        Task(
            name="load_config",
            log_path=_log_path(logs_dir, "load_config"),
            func=load_config,
        ),
        # Dependent success — consumes load_config's result.
        Task(
            name="transform",
            log_path=_log_path(logs_dir, "transform"),
            func=transform,
            dependencies=[dep("load_config", use_result_as_additional_args=True)],
        ),
        # Independent failure WITH rich traced variables, DEFAULT frame filter.
        Task(
            name="fetch_orders",
            log_path=_log_path(logs_dir, "fetch_orders"),
            func=fetch_orders,
            args=("orders_feed", 4242),
            kwargs={"region": "us-east-1"},
        ),
        # Independent failure with a CUSTOM frame filter ('json').
        Task(
            name="decode_payload",
            log_path=_log_path(logs_dir, "decode_payload"),
            func=decode_payload,
            args=('{"id": 1, "ok"',),  # malformed JSON
            traced_vars_frame_filter="json",
        ),
        # Independent failure WITHOUT traced variables (no locals), default filter.
        Task(
            name="noop_validate",
            log_path=_log_path(logs_dir, "noop_validate"),
            func=noop_validate,
        ),
        # Dependent on a failing task → cascade-skipped, never runs.
        Task(
            name="aggregate",
            log_path=_log_path(logs_dir, "aggregate"),
            func=aggregate,
            dependencies=[dep("fetch_orders")],
        ),
    ]


# --------------------------------------------------------------------------- #
# Report delivery                                                             #
# --------------------------------------------------------------------------- #


def deliver_reports(report: ProcessExecutionReport) -> int:
    """Send the report once per combination in the full delivery matrix.

    Iterates every (language x palette x content-style x only_errors) combo —
    2 x 4 x 3 x 2 = 48 emails — each to a distinct recipient encoding the combo,
    so maildev shows them all side by side. Returns the number of emails sent.
    """
    combos = list(
        itertools.product(
            LANGUAGES, PALETTES, CONTENT_STYLES.items(), ERROR_MODES.items()
        )
    )
    print(f"\ndelivering {len(combos)} reports via SMTP ...")
    for i, (lang, palette, (style, content), (mode, only_errors)) in enumerate(combos, 1):
        toaddr = f"report-{lang}-{palette}-{style}-{mode}@{REPORT_TO_DOMAIN}"
        channel = EmailChannel(
            _smtp(toaddr),
            HTMLEmailStyle(palette=palette, language=lang),
            content=content,
        )
        report.notify(channel, only_errors=only_errors)
        print(f"  [{i:2d}/{len(combos)}] -> {toaddr}")
    return len(combos)


# --------------------------------------------------------------------------- #
# Entry point                                                                 #
# --------------------------------------------------------------------------- #


def main() -> int:
    here = os.path.dirname(os.path.abspath(__file__))
    logs_dir = os.path.join(here, "logs")
    os.makedirs(logs_dir, exist_ok=True)

    cleared = 0
    for name in os.listdir(logs_dir):
        if name.endswith(".log"):
            os.remove(os.path.join(logs_dir, name))
            cleared += 1
    print(f"logs dir:   {logs_dir} (cleared {cleared} stale .log file(s))")
    print(f"from:       {FROM_ADDR}")
    print(f"smtp:       {SMTP_HOST}:{SMTP_PORT}   web: http://localhost:{WEB_PORT}")
    print("=" * 72)

    tasks = build_tasks(logs_dir)
    print(f"tasks: {len(tasks)} (2 independent + dependent successes, 3 failures, 1 skipped)")

    try:
        with Process(tasks) as process:
            report = process.run(parallel=False)
            print("\noutcome:")
            for name, entry in report.entries.items():
                print(f"  {entry.status.value:8s}  {name}")
            sent = deliver_reports(report)
    except Exception:
        print("Process raised an unexpected exception:")
        traceback.print_exc()
        return 2

    print("=" * 72)
    print(f"Expected in maildev (http://localhost:{WEB_PORT}): {sent} emails")
    print(f"  matrix: {len(LANGUAGES)} languages x {len(PALETTES)} palettes x "
          f"{len(CONTENT_STYLES)} styles x {len(ERROR_MODES)} only_errors modes")
    print(f"  recipients: report-<lang>-<palette>-<style>-<mode>@{REPORT_TO_DOMAIN}")
    print("Compare across the matrix: language, palette, traced-variables/traceback")
    print("sections (style), and whole-report vs errors-only (mode).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
