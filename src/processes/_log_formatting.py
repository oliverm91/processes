from __future__ import annotations

import logging
from typing import Any

_LOG_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"


def _task_context_lines(ctx: dict[str, Any]) -> list[tuple[str, str]]:
    """Return ``(label, value)`` pairs describing a task failure context.

    Single source of truth for which fields of ``task_context`` are shown
    in plain-text logs; ``_HTMLEmailFormatter`` renders the same
    ``task_context`` dict into its HTML template independently.
    """
    return [
        ("Function", str(ctx.get("function", "?"))),
        ("Args", repr(ctx.get("args", ()))),
        ("Kwargs", repr(ctx.get("kwargs", {}))),
        ("Downstream impact", ", ".join(ctx.get("downstream_impact", [])) or "-"),
        ("Traced vars location", ctx.get("traced_vars_location") or "-"),
    ]


class _TaskLogFormatter(logging.Formatter):
    """Plain-text formatter for task logfiles.

    Renders the same ``record.task_context`` payload used by
    ``_HTMLEmailFormatter`` as readable text, so the logfile and the
    failure email carry the same information.
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

        lines = [base, ""]
        lines.extend(f"{label}: {value}" for label, value in _task_context_lines(ctx))
        tb_str = ctx.get("traceback_str", "")
        if tb_str:
            lines.append("")
            lines.append(tb_str.rstrip("\n"))
        return "\n".join(lines)
