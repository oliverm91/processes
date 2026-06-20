"""Task logfile formatting — a domain concern, not a communication channel.

A ``Task`` writes its own diagnostic logfile; on failure it appends the same
structured context (``ErrorData``) the report carries. This lives in the domain
(not in ``comms``) because it is about a task recording what happened, not about
delivering a report to an external destination.
"""

from __future__ import annotations

import logging

from .error_data import ErrorData

_LOG_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"


class _ErrorContextFormatter(logging.Formatter):
    """Base formatter providing typed access to a record's failure context."""

    def _error_data(self, record: logging.LogRecord) -> ErrorData:
        """Extract the failure context from a log record.

        Parameters
        ----------
        record : logging.LogRecord
            The record being formatted. May or may not carry a
            ``task_context`` attribute.

        Returns
        -------
        ErrorData
            Typed view of ``record.task_context``, with defaults filled in
            for any missing fields.
        """
        ctx = getattr(record, "task_context", None) or {}
        return ErrorData(
            task_name=str(ctx.get("task_name", "?")),
            function=str(ctx.get("function", "?")),
            args=ctx.get("args", ()),
            kwargs=ctx.get("kwargs", {}),
            downstream_impact=ctx.get("downstream_impact", []) or [],
            exception=ctx.get("exception", record.getMessage()),
            traceback_str=ctx.get("traceback_str", ""),
            traced_vars=ctx.get("traced_vars", {}) or {},
            traced_vars_location=ctx.get("traced_vars_location", ""),
        )


class _TaskLogfileFormatter(_ErrorContextFormatter):
    """Plain-text formatter for task logfiles.

    On failure, appends the structured failure context (function, args, kwargs,
    downstream impact, traced variables and their location, traceback) as
    readable text.
    """

    def __init__(self) -> None:
        super().__init__(_LOG_FORMAT)

    def format(self, record: logging.LogRecord) -> str:
        """Render a log record as plain text, appending failure context if present.

        Parameters
        ----------
        record : logging.LogRecord
            The record being formatted.

        Returns
        -------
        str
            The formatted log line, with the failure context appended if
            ``record.task_context`` is set.
        """
        if not getattr(record, "task_context", None):
            return super().format(record)

        exc_info, record.exc_info = record.exc_info, None
        try:
            base = super().format(record)
        finally:
            record.exc_info = exc_info

        error = self._error_data(record)
        lines = [
            base,
            "",
            f"Function: {error.function}",
            f"Args: {error.args!r}",
            f"Kwargs: {error.kwargs!r}",
            f"Downstream impact: {', '.join(error.downstream_impact) or '-'}",
            f"Traced vars location: {error.traced_vars_location or '-'}",
        ]
        if error.traced_vars:
            lines.append("Traced vars:")
            lines.extend(f"  {name} = {value}" for name, value in error.traced_vars.items())
        if error.traceback_str:
            lines.append("")
            lines.append(error.traceback_str.rstrip("\n"))
        return "\n".join(lines)
