from __future__ import annotations

import json
import warnings
from dataclasses import dataclass, field, fields, is_dataclass
from enum import Enum
from typing import TYPE_CHECKING, Any

from .error_data import ErrorData
from .task_types import TaskResult, TaskStatus

if TYPE_CHECKING:
    from .comms.base import ReportChannel
    from .process import Process


def _json_default(obj: Any) -> Any:
    """``json.dumps`` fallback that keeps :meth:`ProcessExecutionReport.to_json` lossless.

    Called only for values JSON cannot serialize natively. Dataclasses become
    field dicts, enums their ``value``, sets/bytes a JSON-native form, and any
    other object its ``repr()`` — so no field is dropped and serialization never
    raises on exotic ``args``/``kwargs``/``result`` values. The trade-off is that
    such ``repr``-rendered values are textual and not round-trippable back into
    live Python objects.
    """
    if is_dataclass(obj) and not isinstance(obj, type):
        return {f.name: getattr(obj, f.name) for f in fields(obj)}
    if isinstance(obj, Enum):
        return obj.value
    if isinstance(obj, (set, frozenset)):
        return list(obj)
    if isinstance(obj, (bytes, bytearray)):
        return bytes(obj).decode("utf-8", errors="replace")
    return repr(obj)


@dataclass(frozen=True, slots=True)
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


@dataclass(frozen=True, slots=True)
class ProcessExecutionReport:
    """Per-task breakdown of a finished :meth:`Process.run` call.

    Attributes
    ----------
    entries : dict[str, TaskReportEntry]
        Mapping of task name to its report entry, ordered the same way as
        ``process.tasks`` (topological order).
    process_name : str
        Name of the process the report came from (``""`` if unnamed). Used to
        label notifications such as the email subject.
    """

    entries: dict[str, TaskReportEntry] = field(default_factory=dict)
    process_name: str = ""

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
    def from_results(
        cls, process: Process, results: dict[str, TaskResult]
    ) -> ProcessExecutionReport:
        """Build a report from a finished process run.

        Parameters
        ----------
        process : Process
            The process that was run. Used for task definitions (name,
            function, args, kwargs) and topological ordering.
        results : dict[str, TaskResult]
            One ``TaskResult`` per task, keyed by task name, as produced by
            :class:`~processes.process.ProcessRunner`.

        Returns
        -------
        ProcessExecutionReport
            One entry per task in ``process.tasks``, in topological order.
        """
        entries: dict[str, TaskReportEntry] = {}
        for task in process.tasks:
            res = results[task.name]
            entries[task.name] = TaskReportEntry(
                name=task.name,
                function=task.func.__name__,
                args=task.args,
                kwargs=task.kwargs,
                status=res.status,
                elapsed_seconds=res.elapsed_seconds,
                attempts=res.attempts,
                result=res.result if res.worked else None,
                error=res.error_data if res.status == TaskStatus.ERRORED else None,
            )
        return cls(entries, process.name)

    def to_json(self, *, indent: int | None = None, **dumps_kwargs: Any) -> str:
        """Serialize the whole report to a JSON string without dropping any field.

        Every entry and every field is included. Values that are not natively
        JSON-serializable are rendered faithfully rather than omitted:
        ``TaskStatus`` as its string value, the nested ``ErrorData`` as an
        object, and any arbitrary object appearing in ``args``, ``kwargs`` or
        ``result`` via ``repr()``. The content is therefore lossless, though
        ``repr``-rendered objects are not round-trippable into live objects.

        Parameters
        ----------
        indent : int, optional
            Forwarded to ``json.dumps`` for pretty-printing. ``None`` (default)
            produces a compact single line.
        **dumps_kwargs : Any
            Forwarded to ``json.dumps`` (e.g. ``sort_keys=True``). Any
            ``default`` is ignored so the lossless fallback always applies.

        Returns
        -------
        str
            A JSON object ``{"entries": {<name>: {...}, ...}}`` with entries in
            topological order.
        """
        dumps_kwargs.pop("default", None)
        return json.dumps(self, default=_json_default, indent=indent, **dumps_kwargs)

    def notify(
        self,
        *channels: ReportChannel,
        only_errors: bool = False,
        tasks: list[str] | None = None,
        show_warnings: bool = True,
    ) -> None:
        """Deliver the report through each channel, in order.

        Each channel renders and sends the report itself (email, webhook, ...).
        What detail is included is configured per channel (see ``ReportContent``).
        If a channel raises, the exception is caught so the remaining channels
        still receive the report; a ``UserWarning`` is emitted when
        ``show_warnings`` is ``True``.

        Parameters
        ----------
        *channels : ReportChannel
            Channels to deliver the report to. No-op if none are given.
        only_errors : bool
            When ``True``, each channel restricts the payload to tasks whose
            status is ``ERRORED`` (see :attr:`errored`). Defaults to ``False``.
        tasks : list[str], optional
            Restrict the report to these task names, compared case-insensitively.
            ``None`` (default) includes every task; an empty list includes none.
            Combines with ``only_errors`` — both filters apply.
        show_warnings : bool
            Emit a ``UserWarning`` when a channel fails. Defaults to ``True``.
        """
        report = self if tasks is None else self._for_tasks(tasks)
        if only_errors and all(v.status != TaskStatus.ERRORED for v in self.entries.values()):
            return
        for channel in channels:
            try:
                channel.send_report(report, errors_only=only_errors)
            except Exception as exc:
                if show_warnings:
                    warnings.warn(
                        f"{type(channel).__name__} failed to send report: {exc}",
                        stacklevel=2,
                    )

    def _for_tasks(self, tasks: list[str]) -> ProcessExecutionReport:
        """A copy of this report restricted to ``tasks`` (case-insensitive names)."""
        wanted = {name.lower() for name in tasks}
        return ProcessExecutionReport(
            {name: entry for name, entry in self.entries.items() if name.lower() in wanted},
            self.process_name,
        )
