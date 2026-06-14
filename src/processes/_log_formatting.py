from __future__ import annotations

import logging

_LOG_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"


class _TaskLogFormatter(logging.Formatter):
    """Plain-text formatter for task logfiles.

    On failure, appends the same ``record.task_context`` fields shown in
    the HTML failure email (function, args, kwargs, downstream impact,
    traced-vars location, traceback) as readable text.
    """

    def __init__(self) -> None:
        super().__init__(_LOG_FORMAT)

    def format(self, record: logging.LogRecord) -> str:
        ctx = getattr(record, "task_context", None)
        if not ctx:
            return super().format(record)

        exc_info, record.exc_info = record.exc_info, None
        try:
            base = super().format(record)
        finally:
            record.exc_info = exc_info

        lines = [
            base,
            "",
            f"Function: {ctx.get('function', '?')}",
            f"Args: {ctx.get('args', ())!r}",
            f"Kwargs: {ctx.get('kwargs', {})!r}",
            f"Downstream impact: {', '.join(ctx.get('downstream_impact', [])) or '-'}",
            f"Traced vars location: {ctx.get('traced_vars_location') or '-'}",
        ]
        tb_str = ctx.get("traceback_str", "")
        if tb_str:
            lines.append("")
            lines.append(tb_str.rstrip("\n"))
        return "\n".join(lines)
