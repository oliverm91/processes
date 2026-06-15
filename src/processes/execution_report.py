from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from ._error_data import ErrorData
from .task import TaskStatus

if TYPE_CHECKING:
    from .process import Process, ProcessResult


@dataclass(frozen=True)
class TaskReportEntry:
    """Per-task entry in a :class:`ProcessExecutionReport`.

    Attributes
    ----------
    name : str
        The task's name.
    function : str
        Name of the function the task runs.
    args : tuple[Any, ...]
        Positional arguments the task was constructed with.
    kwargs : dict[str, Any]
        Keyword arguments the task was constructed with.
    status : TaskStatus
        Outcome of the task: ``SUCCESS``, ``ERRORED``, or ``SKIPPED``.
    elapsed_seconds : float
        Wall-clock time spent running the task across all attempts. ``0.0``
        for skipped tasks.
    attempts : int
        Number of attempts actually executed. ``0`` for skipped tasks.
    result : Any | None
        The task's return value if ``status`` is ``SUCCESS``, else ``None``.
    error : ErrorData | None
        Structured failure context if ``status`` is ``ERRORED``, else ``None``.
    """

    name: str
    function: str
    args: tuple[Any, ...]
    kwargs: dict[str, Any]
    status: TaskStatus
    elapsed_seconds: float
    attempts: int
    result: Any | None = None
    error: ErrorData | None = None


@dataclass(frozen=True)
class ProcessExecutionReport:
    """Per-task breakdown of a finished :meth:`Process.run` call.

    Attributes
    ----------
    entries : dict[str, TaskReportEntry]
        Mapping of task name to its report entry, ordered the same way as
        ``process.tasks`` (topological order).
    """

    entries: dict[str, TaskReportEntry] = field(default_factory=dict)

    def _filter(self, status: TaskStatus) -> dict[str, TaskReportEntry]:
        return {name: entry for name, entry in self.entries.items() if entry.status == status}

    @property
    def successes(self) -> dict[str, TaskReportEntry]:
        """Entries for tasks whose status is ``SUCCESS``."""
        return self._filter(TaskStatus.SUCCESS)

    @property
    def errored(self) -> dict[str, TaskReportEntry]:
        """Entries for tasks whose status is ``ERRORED``."""
        return self._filter(TaskStatus.ERRORED)

    @property
    def skipped(self) -> dict[str, TaskReportEntry]:
        """Entries for tasks whose status is ``SKIPPED``."""
        return self._filter(TaskStatus.SKIPPED)

    @classmethod
    def from_result(cls, process: Process, process_result: ProcessResult) -> ProcessExecutionReport:
        """Build a report from a finished process run.

        Parameters
        ----------
        process : Process
            The process that was run. Used for task definitions (name,
            function, args, kwargs) and topological ordering.
        process_result : ProcessResult
            The result returned by :meth:`Process.run`.

        Returns
        -------
        ProcessExecutionReport
            One entry per task in ``process.tasks``, in topological order.
        """
        entries: dict[str, TaskReportEntry] = {}
        for task in process.tasks:
            if task.name in process_result.skipped_tasks:
                entries[task.name] = TaskReportEntry(
                    name=task.name,
                    function=task.func.__name__,
                    args=task.args,
                    kwargs=task.kwargs,
                    status=TaskStatus.SKIPPED,
                    elapsed_seconds=0.0,
                    attempts=0,
                )
            elif task.name in process_result.passed_tasks_results:
                passed = process_result.passed_tasks_results[task.name]
                entries[task.name] = TaskReportEntry(
                    name=task.name,
                    function=task.func.__name__,
                    args=task.args,
                    kwargs=task.kwargs,
                    status=TaskStatus.SUCCESS,
                    elapsed_seconds=passed.elapsed_seconds,
                    attempts=passed.attempts,
                    result=passed.result,
                )
            else:
                failed = process_result.failed_tasks_results[task.name]
                entries[task.name] = TaskReportEntry(
                    name=task.name,
                    function=task.func.__name__,
                    args=task.args,
                    kwargs=task.kwargs,
                    status=TaskStatus.ERRORED,
                    elapsed_seconds=failed.elapsed_seconds,
                    attempts=failed.attempts,
                    error=failed.error_data,
                )
        return cls(entries)
