from __future__ import annotations

import logging

from ._error_data import _ErrorContextFormatter

_LOG_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"


class _TaskLogFormatter(_ErrorContextFormatter):
    """Plain-text formatter for task logfiles.

    On failure, appends the same failure context shown in the HTML email
    (function, args, kwargs, downstream impact, traced-vars location,
    traceback) as readable text.
    """

    def __init__(self) -> None:
        super().__init__(_LOG_FORMAT)

    def format(self, record: logging.LogRecord) -> str:
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
        if error.traceback_str:
            lines.append("")
            lines.append(error.traceback_str.rstrip("\n"))
        return "\n".join(lines)
