"""``Task.run`` must never propagate.

A failure while resolving dependency arguments (before any attempt runs) has to
become an ``ERRORED`` result, just like a failure inside the task's function.
This previously crashed sequential execution while parallel execution swallowed
it, an asymmetry these tests pin down.
"""

from __future__ import annotations

from typing import Any

from processes import Process, Task, TaskDependency, TaskStatus

from .base_test import BaseTest


def _boom(_executing_process: Any) -> Any:
    raise RuntimeError("resolve blew up")


class TestResolveArgsFailure(BaseTest):
    def test_run_wraps_resolution_failure(self) -> None:
        """A failure in ``_resolve_args`` yields ``ERRORED`` (attempts=0), not a raise."""
        task = Task("t", lambda: 1, self._log("resolve.log"))
        task._resolve_args = _boom  # type: ignore[method-assign]
        try:
            result = task.run(executing_process=None)
        finally:
            self._close_handlers(task)

        assert not result.worked
        assert result.status == TaskStatus.ERRORED
        assert isinstance(result.exception, RuntimeError)
        assert result.attempts == 0

    def test_sequential_process_survives_resolution_failure(self) -> None:
        """Sequential ``Process.run`` does not crash when a task's args fail to resolve."""
        producer = Task("producer", lambda: 1, self._log("producer.log"))
        consumer = Task(
            "consumer",
            lambda x: x,
            self._log("consumer.log"),
            dependencies=[TaskDependency("producer", use_result_as_additional_args=True)],
        )
        consumer._resolve_args = _boom  # type: ignore[method-assign]

        with Process([producer, consumer]) as process:
            report = process.run(parallel=False)

        assert report.entries["producer"].status == TaskStatus.SUCCESS
        assert report.entries["consumer"].status == TaskStatus.ERRORED
