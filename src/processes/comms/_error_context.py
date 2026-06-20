from __future__ import annotations

import logging

from ..error_data import ErrorData


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
