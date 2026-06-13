"""
Enterprise-pipeline integration test.

A single 14-task DAG with parallel sibling branches, diamond dependencies and
a final aggregator.  Two independent failures (Task_B3 and Task_C2) are
injected simultaneously.  The test enforces four strict outcomes:

    1. Independent Execution      — every task that does not depend (directly
                                    or transitively) on the failing tasks
                                    runs to 100% completion.
    2. Cascading Skip Control     — all downstream tasks are flagged as
                                    failed without their ``func`` being called.
    3. Data-Driven Logger Payload — failing tasks emit a pure metadata dict
                                    via ``extra={"task_context": ...}``; no
                                    raw HTML fragment is injected into the
                                    log record.
    4. Mocked Alert Validation    — ``HTMLSMTPHandler`` reads the custom
                                    ``error_template.html``, renders the
                                    layout from the pure metadata payload,
                                    and triggers ``.sendmail()`` with a rich
                                    HTML body containing accurate
                                    "Downstream Impact" list items.
"""

from __future__ import annotations

import logging
import os
import re
from collections import defaultdict
from collections.abc import Iterable
from unittest.mock import patch

from processes import HTMLSMTPHandler, Process, Task, TaskDependency

from .log_cleaner import clean_tasks_logs

_CURDIR = os.path.dirname(__file__)

# --------------------------------------------------------------------------- #
# Helpers                                                                     #
# --------------------------------------------------------------------------- #


class _RecordHandler(logging.Handler):
    """Captures every LogRecord emitted on the attached logger."""

    def __init__(self) -> None:
        super().__init__(level=logging.DEBUG)
        self.records: list[logging.LogRecord] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(record)


def _ancestors_of(task_name: str, tasks: Iterable[Task]) -> set[str]:
    """Set of task names that ``task_name`` transitively depends on."""
    by_name = {t.name: t for t in tasks}
    ancestors: set[str] = set()
    stack = [task_name]
    while stack:
        current = stack.pop()
        for d in by_name[current].dependencies:
            if d.task_name not in ancestors:
                ancestors.add(d.task_name)
                stack.append(d.task_name)
    return ancestors


# --------------------------------------------------------------------------- #
# The test                                                                    #
# --------------------------------------------------------------------------- #


def test_complex_dag_dual_independent_failures() -> None:
    """Enterprise-pipeline integration test (14-task DAG, dual failures)."""

    clean_tasks_logs()

    try:
        # ----------------------------------------------------------------- #
        # 1.  Build the DAG.                                                #
        #                                                                   #
        #   Branch A — independent diamond (9 tasks total in independent    #
        #              set when B & C fail):                                #
        #       A0 -> A1, A2 -> A3                                          #
        #                                                                   #
        #   Branch B — diamond with mid-failure:                            #
        #       B0 -> B1, B2 -> B3 (FAIL) -> B4 (SKIPPED)                   #
        #                                                                   #
        #   Branch C — linear trunk with mid-failure:                       #
        #       C0 -> C1 -> C2 (FAIL) -> C3 (SKIPPED)                       #
        #                                                                   #
        #   Final aggregator:                                               #
        #       D <- A3, B4, C3  (SKIPPED — depends transitively on both   #
        #                          failures through B4 and C3)              #
        # ----------------------------------------------------------------- #
        call_counts: dict[str, int] = defaultdict(int)

        def make_func(name: str, fail: bool):
            def _func(*args, **kwargs):
                call_counts[name] += 1
                if fail:
                    raise RuntimeError(f"Planned enterprise failure in {name}")
                return f"payload_{name}"

            _func.__name__ = f"func_{name}"
            return _func

        mail_handler = HTMLSMTPHandler(
            mailhost=("smtp.enterprise.test", 25),
            fromaddr="pipeline-alerts@enterprise.test",
            toaddrs=["sre-oncall@enterprise.test"],
        )

        def make_task(name: str, deps, fail: bool = False) -> Task:
            return Task(
                name=name,
                log_path=os.path.join(_CURDIR, f"{name}.log"),
                func=make_func(name, fail=fail),
                dependencies=deps,
                html_mail_handler=mail_handler,
            )

        dep = TaskDependency

        tasks = [
            # Branch A
            make_task("A0", deps=[]),
            make_task("A1", deps=[dep("A0")]),
            make_task("A2", deps=[dep("A0")]),
            make_task("A3", deps=[dep("A1"), dep("A2")]),
            # Branch B
            make_task("B0", deps=[]),
            make_task("B1", deps=[dep("B0")]),
            make_task("B2", deps=[dep("B0")]),
            make_task("B3", deps=[dep("B1"), dep("B2")], fail=True),
            make_task("B4", deps=[dep("B3")]),
            # Branch C
            make_task("C0", deps=[]),
            make_task("C1", deps=[dep("C0")]),
            make_task("C2", deps=[dep("C1")], fail=True),
            make_task("C3", deps=[dep("C2")]),
            # Aggregator
            make_task("D", deps=[dep("A3"), dep("B4"), dep("C3")]),
        ]

        failing_task_names = {"B3", "C2"}
        skipped_task_names = {"B4", "C3", "D"}
        expected_failed = failing_task_names | skipped_task_names
        independent_task_names = {t.name for t in tasks} - expected_failed

        assert len(tasks) == 14, "DAG must have at least 10+ tasks (got 14)"

        # ----------------------------------------------------------------- #
        # 3.  Attach a record-capture handler to every failing task's       #
        #     logger so we can inspect the exact LogRecord emitted by       #
        #     ``logger.exception``.                                         #
        # ----------------------------------------------------------------- #
        recorders: dict[str, _RecordHandler] = {}
        for t in tasks:
            if t.name in failing_task_names:
                rec = _RecordHandler()
                t.logger.addHandler(rec)
                recorders[t.name] = rec

        # ----------------------------------------------------------------- #
        # 4.  Run the pipeline with ``smtplib.SMTP`` patched.               #
        # ----------------------------------------------------------------- #
        with patch("processes.html_logging.smtplib.SMTP") as mock_smtp_class:
            with Process(tasks) as process:
                result = process.run(parallel=True, max_workers=4)

        # ----------------------------------------------------------------- #
        # 5.  OUTCOME #1 — Independent Execution                            #
        # ----------------------------------------------------------------- #
        assert independent_task_names == {"A0", "A1", "A2", "A3", "B0", "B1", "B2", "C0", "C1"}

        for name in independent_task_names:
            assert call_counts[name] == 1, (
                f"Independent task {name} did not execute exactly once (got {call_counts[name]})"
            )
            assert name in result.passed_tasks_results, (
                f"Independent task {name} missing from passed_results"
            )
            assert result.passed_tasks_results[name].worked is True
            assert result.passed_tasks_results[name].result == f"payload_{name}"
            assert result.passed_tasks_results[name].exception is None

        # The 14 tasks split cleanly: 9 independent, 2 failed, 3 skipped.
        assert len(result.passed_tasks_results) == len(independent_task_names)
        assert len(result.failed_tasks) == len(expected_failed)

        # ----------------------------------------------------------------- #
        # 6.  OUTCOME #2 — Cascading Skip Control                           #
        # ----------------------------------------------------------------- #
        for name in failing_task_names:
            # The failing task's func IS called exactly once (and then raises).
            assert call_counts[name] == 1, (
                f"Failing task {name} func called {call_counts[name]} times (expected 1)"
            )
        for name in skipped_task_names:
            # Skipped tasks must NEVER have their func invoked.
            assert call_counts[name] == 0, (
                f"Skipped task {name} func was called {call_counts[name]} times — must be 0"
            )
        # The runner marks every failing + skipped task as failed.
        assert result.failed_tasks == expected_failed
        # And no skipped task is in passed_results.
        for name in skipped_task_names:
            assert name not in result.passed_tasks_results

        # ----------------------------------------------------------------- #
        # 7.  OUTCOME #3 — Data-Driven Logger Payload                       #
        # ----------------------------------------------------------------- #
        for name in failing_task_names:
            rec = recorders[name]
            error_records = [r for r in rec.records if r.levelno == logging.ERROR]
            assert len(error_records) == 1, (
                f"Task {name} should emit exactly one ERROR record, got {len(error_records)}"
            )
            record = error_records[0]

            # The new contract: a pure dict via extra={"task_context": ...}.
            assert hasattr(record, "task_context"), (
                f"Task {name} record is missing 'task_context' extra "
                f"(the raw-dict payload contract is broken)"
            )
            # The old contract: raw HTML fragment in 'post_traceback_html_body'.
            # Must be gone — no HTML sneaks through the log record.
            assert not hasattr(record, "post_traceback_html_body"), (
                f"Task {name} record still carries raw HTML fragment in "
                f"'post_traceback_html_body' — payloads must be pure metadata"
            )

            ctx = record.task_context
            assert isinstance(ctx, dict), f"task_context must be a dict, got {type(ctx)}"

            # Pure-metadata keys: framework-agnostic, no HTML.
            assert set(ctx.keys()) == {
                "task_name",
                "function",
                "args",
                "kwargs",
                "downstream_impact",
            }
            assert ctx["task_name"] == name
            assert ctx["function"] == f"func_{name}"
            assert ctx["args"] == ()
            assert ctx["kwargs"] == {}
            assert isinstance(ctx["downstream_impact"], list)
            # The downstream list must be the *exact* set of tasks that get
            # skipped because of this particular failure.
            expected_downstream = {n for n in skipped_task_names if name in _ancestors_of(n, tasks)}
            assert set(ctx["downstream_impact"]) == expected_downstream

            # And no HTML markup anywhere in the metadata.
            serialized = repr(ctx)
            assert "<" not in serialized and ">" not in serialized, (
                f"Task {name} task_context contains HTML markers: {serialized}"
            )

        # ----------------------------------------------------------------- #
        # 8.  OUTCOME #4 — Mocked Alert Validation                          #
        # ----------------------------------------------------------------- #
        # SMTP was constructed exactly once per failure.
        assert mock_smtp_class.call_count == len(failing_task_names), (
            f"smtplib.SMTP should be instantiated {len(failing_task_names)} times, "
            f"got {mock_smtp_class.call_count}"
        )
        for c in mock_smtp_class.call_args_list:
            # Regression: ``HTMLSMTPHandler.emit()`` must unpack
            # ``self.mailhost`` (a tuple) before passing the host to
            # ``smtplib.SMTP`` — otherwise real SMTP servers reject the
            # connection with ``getaddrinfo() argument 1 must be string or None``.
            assert isinstance(c.args[0], str), (
                f"smtplib.SMTP host arg must be a string, got {type(c.args[0]).__name__}: "
                f"{c.args[0]!r}"
            )
            assert c.args[0] == "smtp.enterprise.test"
            assert c.args[1] == 25

        smtp_instance = mock_smtp_class.return_value
        sendmail_calls = smtp_instance.sendmail.call_args_list
        assert len(sendmail_calls) == len(failing_task_names), (
            f"sendmail should fire {len(failing_task_names)} times, got {len(sendmail_calls)}"
        )

        # Each email body must:
        #   - carry the headers (From / To / Subject / Date)
        #   - contain "Downstream Impact"
        #   - include the per-failure <li>{downstream}</li> entries
        #   - prove the *custom* template was read (the unique marker)
        for call in sendmail_calls:
            fromaddr, toaddrs, msg = call.args

            # Headers + envelope.
            assert fromaddr == "pipeline-alerts@enterprise.test"
            assert toaddrs == ["sre-oncall@enterprise.test"]
            assert "From: pipeline-alerts@enterprise.test" in msg
            assert "To: sre-oncall@enterprise.test" in msg
            assert "Subject: Error in task " in msg
            assert "MIME-Version: 1.0" in msg
            assert "Content-Type: text/html" in msg

            # Identify which failing task this email is for.
            match = re.search(r"Pipeline Failure: (\w+)", msg)
            assert match is not None, "Email body missing per-task failure heading"
            failing = match.group(1)
            assert failing in failing_task_names
            assert f"Subject: Error in task {failing}" in msg, (
                f"Subject should be 'Error in task {failing}'"
            )

            # The bundled default theme (classic + neutral) was rendered.
            assert "--accent: #2563eb" in msg, (
                "Default 'neutral' palette marker missing from email body — "
                "formatter did not load the bundled theme"
            )
            assert 'class="card"' in msg, (
                "Default 'modern' style marker missing from email body — "
                "formatter did not load the bundled theme"
            )

            # Rich, well-formed HTML body.
            assert 'class="header"' in msg, (
                "Email body missing the modern 'header' wrapper around the failure heading"
            )
            assert "Pipeline Failure:" in msg, "Email body missing the per-task failure heading"
            assert "<h2>Downstream Impact</h2>" in msg, (
                "Email body missing 'Downstream Impact' heading"
            )
            assert "<ul" in msg and "</ul>" in msg, "Email body missing <ul> list"

            # Accurate per-failure downstream impact entries.
            expected_downstream = sorted(
                n for n in skipped_task_names if failing in _ancestors_of(n, tasks)
            )
            for ds in expected_downstream:
                assert f"<li>{ds}</li>" in msg, (
                    f"Email for {failing} is missing downstream impact entry for {ds!r}"
                )
            # No spurious entries from the *other* failure branch.
            other_branch_downstream = sorted(
                n for n in skipped_task_names if failing not in _ancestors_of(n, tasks)
            )
            for ds in other_branch_downstream:
                assert f"<li>{ds}</li>" not in msg, (
                    f"Email for {failing} incorrectly lists downstream entry "
                    f"for {ds!r} from the other failure branch"
                )

            # The pure-metadata payload drove the body (function/args/exception
            # surfaced from task_context, not from any embedded HTML fragment).
            assert f"func_{failing}" in msg, "Function name missing from email body"
            assert "Planned enterprise failure" in msg, "Exception text missing from email body"

        # SMTP cleanup was called for every connection.
        assert smtp_instance.quit.call_count == len(failing_task_names)
    finally:
        clean_tasks_logs()
