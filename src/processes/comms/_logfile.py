from __future__ import annotations

import logging

from ._error_context import _ErrorContextFormatter

_LOG_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"


class _TaskLogfileFormatter(_ErrorContextFormatter):
    """Plain-text formatter for task logfiles.

    On failure, appends the same failure context shown in the HTML email
    (function, args, kwargs, downstream impact, traced variables and their
    location, traceback) as readable text.
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
