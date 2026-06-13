"""Manual inspection: every (style, palette) theme combination rendering a
failing task with args/kwargs, a long traceback, and downstream tasks.

This is the smallest possible end-to-end check of the email alert rendering
under one of the more painful inputs the formatter is asked to handle — a
deep call stack — across all 9 built-in themes.  Run by hand to eyeball the
result in maildev:

    python tests/manual_tests/manual_themed_tracebacks.py

By default, the script loops over every combination of
``email_style in {classic, modern, compact}``,
``color_palette in {neutral, catppuccin, neobones, slate}`` and
``email_language in {en, es, pt, fr, de, it}`` — 72 pipelines, 72 emails.
Use ``--style``, ``--palette`` and/or ``--language`` to limit to a subset:

    # just the modern + neobones combo in Spanish
    python tests/manual_tests/manual_themed_tracebacks.py --style modern --palette neobones --language es

What this exercises
-------------------
1.  ``risky_step`` is called with both ``args`` and ``kwargs`` so the email
    body shows them filled in (not just the default ``()`` / ``{}``).
2.  ``risky_step`` raises from a deliberately deep call stack
    (``depth 1`` ... ``depth 60``) so the rendered ``<pre class="traceback">``
    block is long — long enough to overflow an inotify line limit, long
    enough to be trimmed by an SMTP server, long enough to be paginated by
    a webmail client.  This is the test that catches "the traceback was
    silently truncated" regressions in the formatter, the SMTP transport,
    or the email client.
3.  ``child_a`` and ``child_b`` are two downstream tasks.  They should
    appear under "Downstream Impact" in the email AND they should never
    be invoked (cascading skip).
4.  All 72 ``(email_style, color_palette, email_language)`` combinations
    are exercised, so every layout (table-based / card / monospace) is
    rendered with every color scheme (blue / red / dark) in every
    supported language.

Prerequisites
-------------
*   maildev running on ``127.0.0.1:1025`` (web UI on 1080).
*   The script connects to ``127.0.0.1`` (not ``localhost``) on purpose:
    on Windows, ``localhost`` often resolves to IPv6 ``::1`` first while
    maildev binds IPv4 only, producing ``WinError 10061``.

Inspect
-------
*   The console output for execution order and per-combo results.
*   The per-task files in ``tests/manual_tests/logs/`` (one per task —
    shared across combos; the last combo's run wins for any given file).
*   The maildev web UI at http://localhost:1080 — 72 messages are expected
    when running all combos, one per (style, palette, language) tuple.
    Flip through them and confirm the traceback is intact and ``child_a``
    / ``child_b`` are listed under "Downstream Impact" (or its translated
    equivalent) in every layout, in every language.
"""

from __future__ import annotations

import os
import sys
import traceback
from typing import Any

# Make the in-tree package importable when the script is run directly.
_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from processes import HTMLSMTPHandler, Process, Task, TaskDependency  # noqa: E402

# --------------------------------------------------------------------------- #
# Constants                                                                   #
# --------------------------------------------------------------------------- #

SMTP_HOST = "127.0.0.1"
SMTP_PORT = 1025
WEB_PORT = 1080
FROM_ADDR = "traceback-canary@enterprise.test"

_STYLES = ("classic", "modern", "compact")
_PALETTES = ("neutral", "catppuccin", "neobones", "slate")
_LANGUAGES = ("en", "es", "pt", "fr", "de", "it")

RECURSION_DEPTH = 60


# --------------------------------------------------------------------------- #
# Maildev wiring                                                              #
# --------------------------------------------------------------------------- #


def _make_mail_handler(
    email_style: str, color_palette: str, email_language: str
) -> HTMLSMTPHandler:
    return HTMLSMTPHandler(
        mailhost=(SMTP_HOST, SMTP_PORT),
        fromaddr=FROM_ADDR,
        toaddrs=[f"{email_style}@{color_palette}.{email_language}"],
        timeout=5,
        email_style=email_style,
        color_palette=color_palette,
        email_language=email_language,
    )


# --------------------------------------------------------------------------- #
# A deliberately deep call stack to produce a long traceback                  #
# --------------------------------------------------------------------------- #


def _deep_call(level: int) -> None:
    if level == 0:
        raise RuntimeError(
            f"deep-call leaf exploded at level=0 (caller chain depth={RECURSION_DEPTH})"
        )
    _deep_call(level - 1)


def risky_step(
    source: str,
    batch_id: int,
    *,
    region: str,
    timeout_seconds: int = 30,
    dry_run: bool = False,
) -> dict[str, Any]:
    """The failing task.  Mixes positional + keyword args, raises from a deep
    call stack so the rendered traceback is long."""
    print(
        f"  [risky_step] source={source!r} batch_id={batch_id} "
        f"region={region!r} timeout_seconds={timeout_seconds} dry_run={dry_run}"
    )
    _deep_call(RECURSION_DEPTH)
    return {"source": source, "batch_id": batch_id}  # unreachable


def child_a() -> str:
    """Cascading-skip target A.  Should never run."""
    print("  [child_a] this should never run — FAILED upstream")
    return "child_a_done"


def child_b() -> str:
    """Cascading-skip target B.  Should never run."""
    print("  [child_b] this should never run — FAILED upstream")
    return "child_b_done"


# --------------------------------------------------------------------------- #
# Build the DAG                                                               #
# --------------------------------------------------------------------------- #


def _log_path(logs_dir: str, name: str) -> str:
    return os.path.join(logs_dir, f"{name}.log")


def build_tasks(
    logs_dir: str, mail_handler: HTMLSMTPHandler
) -> list[Task]:
    dep = TaskDependency
    return [
        Task(
            name="risky_step",
            log_path=_log_path(logs_dir, "risky_step"),
            func=risky_step,
            args=("orders_feed", 4242),
            kwargs={
                "region": "us-east-1",
                "timeout_seconds": 15,
                "dry_run": True,
            },
            html_mail_handler=mail_handler,
        ),
        Task(
            name="child_a",
            log_path=_log_path(logs_dir, "child_a"),
            func=child_a,
            dependencies=[dep("risky_step")],
            html_mail_handler=mail_handler,
        ),
        Task(
            name="child_b",
            log_path=_log_path(logs_dir, "child_b"),
            func=child_b,
            dependencies=[dep("risky_step")],
            html_mail_handler=mail_handler,
        ),
    ]


# --------------------------------------------------------------------------- #
# Per-combo runner                                                            #
# --------------------------------------------------------------------------- #


def _run_one_combo(
    logs_dir: str, email_style: str, color_palette: str, email_language: str
) -> tuple[bool, int]:
    """Run the pipeline once with the given (style, palette, language) handler.

    Returns ``(ok, exit_code)`` — ``ok`` is True iff the post-conditions held.
    """
    print(
        f"\n>>> [style={email_style!r}, "
        f"palette={color_palette!r}, language={email_language!r}]"
    )
    print("-" * 72)

    mail_handler = _make_mail_handler(email_style, color_palette, email_language)
    tasks = build_tasks(logs_dir, mail_handler)
    print(f"tasks: {len(tasks)} (1 root + 2 downstream)")

    try:
        with Process(tasks) as process:
            # Sequential mode: deterministic; mirrors the enterprise script.
            result = process.run(parallel=False)
    except Exception:
        print("Process raised an unexpected exception:")
        traceback.print_exc()
        return False, 2

    print("passed:")
    for name in sorted(result.passed_tasks_results):
        print(f"  + {name}")
    print("failed (includes cascading-skipped):")
    for name in sorted(result.failed_tasks):
        print(f"  - {name}")

    # Strict post-conditions: downstream tasks were never invoked.
    ok = (
        "risky_step" in result.failed_tasks
        and "child_a" in result.failed_tasks
        and "child_b" in result.failed_tasks
        and "risky_step" not in result.passed_tasks_results
        and "child_a" not in result.passed_tasks_results
        and "child_b" not in result.passed_tasks_results
    )
    if not ok:
        print(
            f"  ! post-condition FAILED for "
            f"style={email_style!r}, palette={color_palette!r}, "
            f"language={email_language!r}"
        )
    return ok, 0


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
    if cleared:
        print(f"logs dir:   {logs_dir} (cleared {cleared} stale .log file(s))")
    else:
        print(f"logs dir:   {logs_dir} (empty)")

    styles = _STYLES
    palettes = _PALETTES
    languages = _LANGUAGES
    total = len(styles) * len(palettes) * len(languages)

    print(f"from:              {FROM_ADDR}")
    print("to (per combo):    <email_style>@<color_palette>.<email_language>")
    print(f"recursion depth:   {RECURSION_DEPTH} frames")
    print(
        f"themes to render:  {total} "
        f"(styles={styles}, palettes={palettes}, languages={languages})"
    )
    print("=" * 72)

    failures: list[tuple[str, str, str]] = []
    for style in styles:
        for palette in palettes:
            for language in languages:
                ok, exit_code = _run_one_combo(logs_dir, style, palette, language)
                if exit_code != 0:
                    return exit_code
                if not ok:
                    failures.append((style, palette, language))

    print("=" * 72)
    if failures:
        print(f"FAILED post-conditions for: {failures}")
        return 1

    print(f"All {total} combo(s) completed.")
    print("Per-task logs (shared across combos; last run wins for each file):")
    print(f"  {logs_dir}")
    print(f"Rendered emails ({total} expected when running all combos):")
    print(f"  http://localhost:{WEB_PORT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
