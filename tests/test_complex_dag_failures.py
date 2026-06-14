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
    4. Mocked Alert Validation    — the internal email handler renders the
                                    layout from the pure metadata payload
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

from processes import EmailChannel, Process, SMTPConfig, Task, TaskDependency

from .base_test import BaseTest


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


class TestComplexDagFailures(BaseTest):
    def test_complex_dag_dual_independent_failures(self) -> None:
        """Enterprise-pipeline integration test (14-task DAG, dual failures)."""
        call_counts: dict[str, int] = defaultdict(int)

        def make_func(name: str, fail: bool):
            def _func(*args, **kwargs):
                call_counts[name] += 1
                if fail:
                    raise RuntimeError(f"Planned enterprise failure in {name}")
                return f"payload_{name}"

            _func.__name__ = f"func_{name}"
            return _func

        smtp_config = SMTPConfig(
            mailhost=("smtp.enterprise.test", 25),
            fromaddr="pipeline-alerts@enterprise.test",
            toaddrs=["sre-oncall@enterprise.test"],
        )

        def make_task(name: str, deps, fail: bool = False) -> Task:
            return Task(
                name=name,
                log_path=os.path.join(self._CURDIR, f"{name}.log"),
                func=make_func(name, fail=fail),
                dependencies=deps,
                channels=[EmailChannel(smtp_config)],
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

        recorders: dict[str, _RecordHandler] = {}
        for t in tasks:
            if t.name in failing_task_names:
                rec = _RecordHandler()
                t.logger.addHandler(rec)
                recorders[t.name] = rec

        with patch("processes._email_internals.smtplib.SMTP") as mock_smtp_class:
            with Process(tasks) as process:
                result = process.run(parallel=True, max_workers=4)

        # OUTCOME #1 — Independent Execution
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

        assert len(result.passed_tasks_results) == len(independent_task_names)
        assert len(result.failed_tasks) == len(expected_failed)
        assert result.errored_tasks == failing_task_names, (
            f"errored_tasks should be exactly the two tasks whose func raised, "
            f"got {result.errored_tasks}"
        )
        assert result.skipped_tasks == skipped_task_names, (
            f"skipped_tasks should be the three cascade-skipped tasks, got {result.skipped_tasks}"
        )
        assert result.errored_tasks.isdisjoint(result.skipped_tasks), (
            "errored_tasks and skipped_tasks must be disjoint"
        )

        # OUTCOME #2 — Cascading Skip Control
        for name in failing_task_names:
            assert call_counts[name] == 1, (
                f"Failing task {name} func called {call_counts[name]} times (expected 1)"
            )
        for name in skipped_task_names:
            assert call_counts[name] == 0, (
                f"Skipped task {name} func was called {call_counts[name]} times — must be 0"
            )
        assert result.failed_tasks == expected_failed
        for name in skipped_task_names:
            assert name not in result.passed_tasks_results

        # OUTCOME #3 — Data-Driven Logger Payload
        for name in failing_task_names:
            rec = recorders[name]
            error_records = [r for r in rec.records if r.levelno == logging.ERROR]
            assert len(error_records) == 1, (
                f"Task {name} should emit exactly one ERROR record, got {len(error_records)}"
            )
            record = error_records[0]

            assert hasattr(record, "task_context"), (
                f"Task {name} record is missing 'task_context' extra "
                f"(the raw-dict payload contract is broken)"
            )
            assert not hasattr(record, "post_traceback_html_body"), (
                f"Task {name} record still carries raw HTML fragment in "
                f"'post_traceback_html_body' — payloads must be pure metadata"
            )

            ctx = record.task_context
            assert isinstance(ctx, dict), f"task_context must be a dict, got {type(ctx)}"
            assert set(ctx.keys()) == {
                "task_name",
                "function",
                "args",
                "kwargs",
                "downstream_impact",
                "exception",
                "traceback_str",
                "traced_vars",
                "traced_vars_location",
            }
            assert ctx["task_name"] == name
            assert ctx["function"] == f"func_{name}"
            assert ctx["args"] == ()
            assert ctx["kwargs"] == {}
            assert isinstance(ctx["downstream_impact"], list)
            expected_downstream = {n for n in skipped_task_names if name in _ancestors_of(n, tasks)}
            assert set(ctx["downstream_impact"]) == expected_downstream

            assert isinstance(ctx["traced_vars"], dict), (
                f"Task {name} task_context['traced_vars'] must be a plain "
                f"{{name: repr(value)}} dict, got {type(ctx['traced_vars'])}"
            )

            serialized = repr(ctx)
            for entity in ("&lt;", "&gt;", "&amp;", "&#x27;", "&quot;"):
                assert entity not in serialized, (
                    f"Task {name} task_context contains an HTML entity ({entity}): {serialized}"
                )

        # OUTCOME #4 — Mocked Alert Validation
        assert mock_smtp_class.call_count == len(failing_task_names), (
            f"smtplib.SMTP should be instantiated {len(failing_task_names)} times, "
            f"got {mock_smtp_class.call_count}"
        )
        for c in mock_smtp_class.call_args_list:
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

        for call in sendmail_calls:
            fromaddr, toaddrs, msg = call.args

            assert fromaddr == "pipeline-alerts@enterprise.test"
            assert toaddrs == ["sre-oncall@enterprise.test"]
            assert "From: pipeline-alerts@enterprise.test" in msg
            assert "To: sre-oncall@enterprise.test" in msg
            assert "Subject: Error in task " in msg
            assert "MIME-Version: 1.0" in msg
            assert "Content-Type: text/html" in msg

            match = re.search(r"Pipeline Failure: (\w+)", msg)
            assert match is not None, "Email body missing per-task failure heading"
            failing = match.group(1)
            assert failing in failing_task_names
            assert f"Subject: Error in task {failing}" in msg, (
                f"Subject should be 'Error in task {failing}'"
            )

            assert "--accent: #2563eb" in msg, (
                "Default 'neutral' palette marker missing from email body — "
                "formatter did not load the bundled theme"
            )
            assert 'class="card"' in msg, (
                "Default 'modern' style marker missing from email body — "
                "formatter did not load the bundled theme"
            )
            assert 'class="header"' in msg, (
                "Email body missing the modern 'header' wrapper around the failure heading"
            )
            assert "Pipeline Failure:" in msg, "Email body missing the per-task failure heading"
            assert "<h2>Downstream Impact</h2>" in msg, (
                "Email body missing 'Downstream Impact' heading"
            )
            assert "<ul" in msg and "</ul>" in msg, "Email body missing <ul> list"

            expected_downstream = sorted(
                n for n in skipped_task_names if failing in _ancestors_of(n, tasks)
            )
            for ds in expected_downstream:
                assert f"<li>{ds}</li>" in msg, (
                    f"Email for {failing} is missing downstream impact entry for {ds!r}"
                )
            other_branch_downstream = sorted(
                n for n in skipped_task_names if failing not in _ancestors_of(n, tasks)
            )
            for ds in other_branch_downstream:
                assert f"<li>{ds}</li>" not in msg, (
                    f"Email for {failing} incorrectly lists downstream entry "
                    f"for {ds!r} from the other failure branch"
                )

            assert f"func_{failing}" in msg, "Function name missing from email body"
            assert "Planned enterprise failure" in msg, "Exception text missing from email body"

        assert smtp_instance.quit.call_count == len(failing_task_names)
