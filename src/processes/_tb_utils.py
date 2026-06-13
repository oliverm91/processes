from __future__ import annotations

import html
import os
import sys
import traceback
from typing import Any


def _is_library_path(filename: str) -> bool:
    """Return True if ``filename`` lives inside a library or stdlib."""
    if "site-packages" in filename:
        return True
    if ".venv" in filename:
        return True
    base_prefix = getattr(sys, "base_prefix", "")
    if base_prefix:
        try:
            if os.path.commonpath(
                [os.path.abspath(filename), os.path.abspath(base_prefix)]
            ) == os.path.abspath(base_prefix):
                return True
        except ValueError:
            return False
    return False


def _iter_tb(exc_tb: Any) -> Any:
    tb = exc_tb
    while tb is not None:
        yield tb
        tb = tb.tb_next


def _resolve_target_tb(exc_tb: Any, frame_filter: str | None) -> Any:
    """Return the traceback frame to use for local-variable capture.

    With ``frame_filter=None``, picks the last non-library frame.
    With a filter string, picks the last frame whose filename contains it.
    Falls back to the innermost frame when nothing matches.
    """
    frames = list(_iter_tb(exc_tb))
    if not frames:
        return None
    if frame_filter is None:
        matches = [tb for tb in frames if not _is_library_path(tb.tb_frame.f_code.co_filename)]
    else:
        matches = [tb for tb in frames if frame_filter in tb.tb_frame.f_code.co_filename]
    return matches[-1] if matches else frames[-1]


def _build_traced_vars_html(exc_tb: Any, frame_filter: str | None) -> str:
    """Return HTML-escaped ``name = repr(value)`` lines for the target frame's locals."""
    target = _resolve_target_tb(exc_tb, frame_filter)
    if target is None:
        return ""
    frame = target.tb_frame
    lines: list[str] = []
    for name, value in frame.f_locals.items():
        try:
            rendered = repr(value)
        except Exception as exc:
            rendered = f"<unreprable: {type(exc).__name__}: {exc}>"
        lines.append(f"{name} = {rendered}")
    return "\n".join(html.escape(line, quote=True) for line in lines)


def _build_traced_vars_location(exc_tb: Any, frame_filter: str | None) -> str:
    """Return ``"filename:lineno"`` for the target frame, or empty string."""
    target = _resolve_target_tb(exc_tb, frame_filter)
    if target is None:
        return ""
    frame = target.tb_frame
    return f"{frame.f_code.co_filename}:{frame.f_lineno}"


def _format_traceback(exc: BaseException) -> str:
    """Return the full traceback of *exc* as a single string."""
    return "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
