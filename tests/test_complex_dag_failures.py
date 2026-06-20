"""
Enterprise-pipeline integration test.

A single 14-task DAG with parallel sibling branches, diamond dependencies and
a final aggregator.  Two independent failures (Task_B3 and Task_C2) are
injected simultaneously.  The test enforces three strict outcomes:

    1. Independent Execution      — every task that does not depend (directly
                                    or transitively) on the failing tasks
                                    runs to 100% completion.
    2. Cascading Skip Control     — all downstream tasks are flagged as
                                    failed without their ``func`` being called.
    3. Data-Driven Logger Payload — failing tasks emit a pure metadata dict
                                    via ``extra={"task_context": ...}``; no
                                    raw HTML fragment is injected into the
                                    log record.
"""

from __future__ import annotations

import logging
import os
from collections import defaultdict
from collections.abc import Iterable

from processes import Process, Task, TaskDependency

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

        def make_task(name: str, deps, fail: bool = False) -> Task:
            return Task(
                name=name,
                log_path=os.path.join(self._CURDIR, f"{name}.log"),
                func=make_func(name, fail=fail),
                dependencies=deps,
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

        with Process(tasks) as process:
            result = process.run(parallel=True, max_workers=4)

        # OUTCOME #1 — Independent Execution
        assert independent_task_names == {"A0", "A1", "A2", "A3", "B0", "B1", "B2", "C0", "C1"}

        for name in independent_task_names:
            assert call_counts[name] == 1, (
                f"Independent task {name} did not execute exactly once (got {call_counts[name]})"
            )
            assert name in result.successes, f"Independent task {name} missing from successes"
            assert result.successes[name].result == f"payload_{name}"
            assert result.successes[name].error is None

        assert len(result.successes) == len(independent_task_names)
        assert len(result.errored) + len(result.skipped) == len(expected_failed)
        assert set(result.errored) == failing_task_names, (
            f"errored entries should be exactly the two tasks whose func raised, "
            f"got {set(result.errored)}"
        )
        assert set(result.skipped) == skipped_task_names, (
            f"skipped entries should be the three cascade-skipped tasks, got {set(result.skipped)}"
        )
        assert set(result.errored).isdisjoint(result.skipped), (
            "errored and skipped entries must be disjoint"
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
        assert set(result.errored) | set(result.skipped) == expected_failed
        for name in skipped_task_names:
            assert name not in result.successes

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
