"""Pure task value types with no dependency on the communication layer.

``TaskStatus``, ``TaskResult`` and ``TaskDependency`` are leaf domain types:
they import only the standard library and :class:`~processes.error_data.ErrorData`
(itself a leaf). Keeping them here — rather than in ``task.py``, which imports the
notification channels — lets the communication renderers import ``TaskStatus``
directly without creating an import cycle.
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from .error_data import ErrorData


class TaskStatus(Enum):
    """Outcome of a task within a process execution.

    Attributes
    ----------
    PENDING
        The task has not been executed yet.
    SUCCESS
        The task ran and its function returned without raising.
    ERRORED
        The task ran and its function raised an exception (after exhausting
        retries, if any).
    SKIPPED
        The task never ran because an upstream dependency failed.
    """

    PENDING = "pending"
    SUCCESS = "success"
    ERRORED = "errored"
    SKIPPED = "skipped"


class TaskResult:
    """
    Container for the result of a task execution.

    Holds the outcome of running a task, including its status, return value,
    and any exception that occurred.

    Attributes
    ----------
    status : TaskStatus
        Outcome of the task: ``PENDING``, ``SUCCESS``, ``ERRORED``, or ``SKIPPED``.
    worked : bool
        True if ``status`` is ``SUCCESS``, False otherwise.
    result : Any
        The return value of the task's function if execution succeeded, None if failed.
    exception : Exception | None
        The exception object if execution failed, None if successful.
    error_data : ErrorData | None
        Structured failure context (function, args, kwargs, traceback, traced
        variables, downstream impact) when execution failed; None if the task
        succeeded.
    elapsed_seconds : float
        Wall-clock time spent running the task across all attempts, in
        seconds. Defaults to ``0.0``.
    attempts : int
        Number of attempts actually executed (1 or more if the task ran,
        0 if it never ran). Defaults to ``0``.
    """

    def __init__(
        self,
        status: TaskStatus,
        result: Any,
        exception: Exception | None,
        error_data: ErrorData | None = None,
        elapsed_seconds: float = 0.0,
        attempts: int = 0,
    ):
        self.status = status
        self.result = result
        self.exception = exception
        self.error_data = error_data
        self.elapsed_seconds = elapsed_seconds
        self.attempts = attempts

    @property
    def worked(self) -> bool:
        """True if the task executed successfully, False otherwise."""
        return self.status == TaskStatus.SUCCESS

    @classmethod
    def pending(cls) -> TaskResult:
        """Build the placeholder result for a task that has not run yet."""
        return cls(TaskStatus.PENDING, None, None)

    @classmethod
    def skipped(cls) -> TaskResult:
        """Build the result for a task skipped after an upstream dependency failed."""
        return cls(TaskStatus.SKIPPED, None, None)

    @classmethod
    def success(cls, result: Any, *, elapsed_seconds: float = 0.0, attempts: int = 0) -> TaskResult:
        """Build the result for a task whose function returned without raising."""
        return cls(
            TaskStatus.SUCCESS,
            result,
            None,
            elapsed_seconds=elapsed_seconds,
            attempts=attempts,
        )

    @classmethod
    def errored(
        cls,
        exception: Exception,
        *,
        error_data: ErrorData | None = None,
        elapsed_seconds: float = 0.0,
        attempts: int = 0,
    ) -> TaskResult:
        """Build the result for a task whose function raised after exhausting retries."""
        return cls(
            TaskStatus.ERRORED,
            None,
            exception,
            error_data=error_data,
            elapsed_seconds=elapsed_seconds,
            attempts=attempts,
        )


class TaskDependency:
    """
    Represents a dependency relationship between tasks.

    Defines how a task depends on another task, including how the result
    of the dependency should be passed to the dependent task (as additional
    positional arguments, keyword arguments, or both).

    Attributes
    ----------
    task_name : str
        The name of the task this dependency refers to.
    use_result_as_additional_args : bool
        If True, the result of the dependency task will be passed as an
        additional positional argument as the last argument. Defaults to False.
    use_result_as_additional_kwargs : bool
        If True, the result of the dependency task will be passed as a
        keyword argument. Defaults to False.
    additional_kwarg_name : str
        The name of the keyword argument to use if ``use_result_as_additional_kwargs``
        is True. Must be a non-empty string when
        ``use_result_as_additional_kwargs`` is True. Defaults to ``""``.

    Raises
    ------
    TypeError
        If any parameter type is invalid or if use_result_as_additional_kwargs
        is True but additional_kwarg_name is not a string.
    """

    def __init__(
        self,
        task_name: str,
        use_result_as_additional_args: bool = False,
        use_result_as_additional_kwargs: bool = False,
        additional_kwarg_name: str = "",
    ):
        self.task_name = task_name
        self.use_result_as_additional_args = use_result_as_additional_args
        self.use_result_as_additional_kwargs = use_result_as_additional_kwargs
        self.additional_kwarg_name = additional_kwarg_name

        if not isinstance(self.task_name, str):
            raise TypeError(f"task_name must be of type str. Got {type(self.task_name)}")
        if not isinstance(self.use_result_as_additional_args, bool):
            raise TypeError(
                f"use_result_as_additional_args must be of type bool. "
                f"Got {type(self.use_result_as_additional_args)}"
            )
        if not isinstance(self.use_result_as_additional_kwargs, bool):
            raise TypeError(
                f"use_result_as_additional_kwargs must be of type bool. "
                f"Got {type(self.use_result_as_additional_kwargs)}"
            )

        if self.use_result_as_additional_kwargs and self.additional_kwarg_name == "":
            raise TypeError(
                "If use_result_as_additional_kwargs is True, additional_kwarg_name"
                " must be a non-empty string."
            )

    def __hash__(self) -> int:
        """
        Return hash of the dependency based on task name.

        Returns
        -------
        int
            Hash value based on the task_name attribute.
        """
        return hash(self.task_name)
