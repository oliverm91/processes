from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class ErrorData:
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
    traced_vars : dict[str, str]
        Mapping of local variable names to ``repr(value)`` for the traced
        frame. Defaults to ``{}``.
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
    traced_vars: dict[str, str] = field(default_factory=dict)
    traced_vars_location: str = ""
