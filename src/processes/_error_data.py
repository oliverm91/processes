from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class _ErrorData:
    """Typed view of a task failure, extracted from ``record.task_context``.

    Attributes
    ----------
    task_name : str
        Name of the task that failed. Defaults to ``"?"``.
    function : str
        Name of the function that was executing. Defaults to ``"?"``.
    args : tuple[Any, ...]
        Positional arguments the function was called with. Defaults to ``()``.
    kwargs : dict[str, Any]
        Keyword arguments the function was called with. Defaults to ``{}``.
    downstream_impact : list[str]
        Names of tasks skipped as a result of this failure. Defaults to ``[]``.
    exception : str
        String representation of the raised exception. Defaults to ``""``.
    traceback_str : str
        Full formatted traceback. Defaults to ``""``.
    traced_vars : str
        Rendered local variables of the traced frame. Defaults to ``""``.
    traced_vars_location : str
        ``"filename:lineno"`` of the traced frame. Defaults to ``""``.
    """

    task_name: str = "?"
    function: str = "?"
    args: tuple[Any, ...] = ()
    kwargs: dict[str, Any] = field(default_factory=dict)
    downstream_impact: list[str] = field(default_factory=list)
    exception: str = ""
    traceback_str: str = ""
    traced_vars: str = ""
    traced_vars_location: str = ""


class _ErrorContextFormatter(logging.Formatter):
    """Base formatter providing typed access to a record's failure context."""

    def _error_data(self, record: logging.LogRecord) -> _ErrorData:
        """Extract the failure context from a log record.

        Parameters
        ----------
        record : logging.LogRecord
            The record being formatted. May or may not carry a
            ``task_context`` attribute.

        Returns
        -------
        _ErrorData
            Typed view of ``record.task_context``, with defaults filled in
            for any missing fields.
        """
        ctx = getattr(record, "task_context", None) or {}
        return _ErrorData(
            task_name=str(ctx.get("task_name", "?")),
            function=str(ctx.get("function", "?")),
            args=ctx.get("args", ()),
            kwargs=ctx.get("kwargs", {}),
            downstream_impact=ctx.get("downstream_impact", []) or [],
            exception=ctx.get("exception", record.getMessage()),
            traceback_str=ctx.get("traceback_str", ""),
            traced_vars=ctx.get("traced_vars", ""),
            traced_vars_location=ctx.get("traced_vars_location", ""),
        )
