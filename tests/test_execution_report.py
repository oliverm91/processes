"""Tests for ``ProcessExecutionReport`` as returned by ``Process.run()``.

Covers status classification (success / errored / skipped), the data carried
by each ``TaskReportEntry`` (result, error, elapsed_seconds, attempts), entry
ordering, and the ``successes``/``errored``/``skipped`` filter accessors —
for both sequential and parallel execution.
"""

from __future__ import annotations

from processes import (
    ErrorData,
    Process,
    Task,
    TaskDependency,
    TaskStatus,
)

from .base_test import BaseTest


class TestProcessExecutionReport(BaseTest):
    def _build_process(self) -> tuple[Process, Task, Task, Task]:
        def load() -> str:
            return "data"

        def apply(_data: str) -> None:
            raise ValueError("apply failed")

        def notify() -> None:
            pass

        load_task = Task("load", load, self._log("report_load.log"))
        apply_task = Task(
            "apply",
            apply,
            self._log("report_apply.log"),
            dependencies=[TaskDependency("load", use_result_as_additional_args=True)],
        )
        notify_task = Task(
            "notify",
            notify,
            self._log("report_notify.log"),
            dependencies=[TaskDependency("apply")],
        )

        process = Process([load_task, apply_task, notify_task])
        return process, load_task, apply_task, notify_task

    def test_sequential_report_classifies_each_task(self) -> None:
        process, load_task, apply_task, notify_task = self._build_process()
        with process:
            report = process.run(parallel=False)

        assert list(report.entries) == ["load", "apply", "notify"]

        load_entry = report.entries["load"]
        assert load_entry.status == TaskStatus.SUCCESS
        assert load_entry.result == "data"
        assert load_entry.error is None
        assert load_entry.attempts == 1
        assert load_entry.elapsed_seconds >= 0.0
        assert load_entry.function == "load"
        assert load_entry.args == ()
        assert load_entry.kwargs == {}

        apply_entry = report.entries["apply"]
        assert apply_entry.status == TaskStatus.ERRORED
        assert apply_entry.result is None
        assert isinstance(apply_entry.error, ErrorData)
        assert apply_entry.error.task_name == "apply"
        assert apply_entry.error.exception == "apply failed"
        assert apply_entry.attempts == 1

        notify_entry = report.entries["notify"]
        assert notify_entry.status == TaskStatus.SKIPPED
        assert notify_entry.result is None
        assert notify_entry.error is None
        assert notify_entry.attempts == 0
        assert notify_entry.elapsed_seconds == 0.0

        self._close_handlers(load_task, apply_task, notify_task)

    def test_filter_accessors_partition_entries(self) -> None:
        process, load_task, apply_task, notify_task = self._build_process()
        with process:
            report = process.run(parallel=False)

        assert set(report.successes) == {"load"}
        assert set(report.errored) == {"apply"}
        assert set(report.skipped) == {"notify"}

        self._close_handlers(load_task, apply_task, notify_task)

    def test_parallel_report_classifies_each_task(self) -> None:
        process, load_task, apply_task, notify_task = self._build_process()
        with process:
            report = process.run(parallel=True, max_workers=4)

        assert report.entries["load"].status == TaskStatus.SUCCESS
        assert report.entries["apply"].status == TaskStatus.ERRORED
        assert report.entries["notify"].status == TaskStatus.SKIPPED

        self._close_handlers(load_task, apply_task, notify_task)

    def test_all_success_report_has_no_errored_or_skipped(self) -> None:
        def step() -> int:
            return 42

        task = Task("step", step, self._log("report_all_success.log"))
        process = Process([task])
        with process:
            report = process.run(parallel=False)

        assert report.entries["step"].status == TaskStatus.SUCCESS
        assert report.entries["step"].result == 42
        assert report.errored == {}
        assert report.skipped == {}

        self._close_handlers(task)
