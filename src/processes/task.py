from __future__ import annotations

import concurrent.futures
import time
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .process import Process

import logging

from ._tb_utils import _build_traced_vars, _build_traced_vars_location, _format_traceback
from .comms.base import NotificationChannel
from .comms.channels import _FileChannel
from .error_data import ErrorData
from .exceptions import CircularDependencyError
from .task_types import TaskDependency, TaskResult, TaskStatus

__all__ = ["Task", "TaskDependency", "TaskResult", "TaskStatus"]


class Task:
    """
    A Task represents a unit of work to be executed within a Process.

    A Task encapsulates a callable function with its arguments, dependencies on other tasks,
    and logging configuration. Tasks can be executed by the Process class, sequentially
    or in parallel, with automatic dependency resolution and result passing between dependent tasks.

    Attributes
    ----------
    name : str
        Unique name for the task (cannot contain spaces).
    log_path : str | None
        File path where task logs will be written. ``None`` if no file
        logging is configured.
    func : Callable
        The function to execute when the task runs.
    args : tuple
        Positional arguments to pass to the function. Defaults to empty tuple.
    kwargs : dict
        Keyword arguments to pass to the function. Defaults to empty dict.
    dependencies : list[TaskDependency]
        List of tasks this task depends on. Defaults to empty list.
    channels : list[NotificationChannel]
        Additional notification channels attached to this task's logger, on
        top of the implicit file channel built from ``log_path``. Defaults to
        empty list.
    timeout : float | None
        Seconds allowed per attempt before a ``TimeoutError`` is raised.
        ``None`` means no limit. Defaults to ``None``.
    retries : int
        Additional attempts after the first failure. ``0`` or ``None`` means
        no retries. Defaults to ``0``.
    retry_on : tuple[type[Exception], ...] | None
        Exception types that trigger a retry. When ``retries >= 1`` and
        ``retry_on`` is ``None``, defaults at call time to
        ``(ConnectionError, TimeoutError)``. Defaults to ``None``.
    logger : logging.Logger
        Logger instance for this task, automatically configured.

    Parameters
    ----------
    name : str
        Unique task name; must not contain spaces.
    func : Callable[..., Any]
        The callable executed when the task runs.
    log_path : str | None
        File path the task's log records are written to (one ``FileHandler``
        at ``INFO`` level, format
        ``"%(asctime)s - %(name)s - %(levelname)s - %(message)s"``). ``None``
        means no file logging is configured. If this leaves the task with no
        notification channels at all, a ``NullHandler`` is attached instead.
        Defaults to ``None``.
    args : tuple[Any, ...]
        Positional arguments forwarded to ``func``. Defaults to ``()``.
    kwargs : dict[str, Any] | None
        Keyword arguments forwarded to ``func``. ``None`` is treated as
        an empty dict.
    dependencies : list[TaskDependency] | None
        Tasks this task depends on. ``None`` is treated as an empty list.
    channels : list[NotificationChannel] | None
        Additional notification channels whose handlers are attached to this
        task's logger, alongside the implicit file channel built from
        ``log_path``. Use ``EmailChannel`` for HTML email alerts on
        ``logging.ERROR`` and above, or subclass ``NotificationChannel`` for
        other destinations. ``None`` is treated as an empty list. Defaults to
        ``None``.
    timeout : float | None
        Seconds allowed per attempt before ``TimeoutError`` is raised for that
        attempt. ``None`` means no limit. When a timeout fires, the underlying
        thread is detached rather than killed (Python threading limitation).
        Defaults to ``None``.
    retries : int | None
        Number of additional attempts after the first failure. ``0`` or ``None``
        means a single attempt with no retry. Defaults to ``0``.
    retry_on : tuple[type[Exception], ...] | None
        Exception types that trigger a retry. Evaluated only when
        ``retries >= 1``. When ``None``, defaults at call time to
        ``(ConnectionError, TimeoutError)``. Defaults to ``None``.

    Raises
    ------
    TypeError
        If any parameter is not of the expected type, ``timeout`` is not a
        positive number, ``retries`` is negative, ``retry_on`` is not a
        tuple of ``Exception`` subclasses, or ``channels`` is not a list of
        ``NotificationChannel`` instances.
    ValueError
        If ``name`` contains a space, if the same dependency name is
        listed more than once, or if the task lists itself as a
        dependency.
    """

    kwargs: dict[str, Any]
    dependencies: list[TaskDependency]

    def __init__(
        self,
        name: str,
        func: Callable[..., Any],
        log_path: str | None = None,
        args: tuple[Any, ...] = (),
        kwargs: dict[str, Any] | None = None,
        dependencies: list[TaskDependency] | None = None,
        channels: list[NotificationChannel] | None = None,
        timeout: float | None = None,
        retries: int | None = 0,
        retry_on: tuple[type[Exception], ...] | None = None,
    ):
        self.name = name
        self.log_path = log_path
        self.func = func
        self.args = args
        self.timeout = timeout
        self.retries = retries if retries is not None else 0
        self.retry_on = retry_on

        if kwargs is None:
            self.kwargs = {}
        else:
            self.kwargs = kwargs
        if dependencies is None:
            self.dependencies = []
        else:
            self.dependencies = dependencies
        if channels is None:
            self.channels = []
        else:
            self.channels = channels

        self._check_input_types()
        if " " in self.name:
            raise ValueError(f"Task name cannot contain spaces. Got {self.name}")

        depedencies_names = []
        for dependency in self.dependencies:
            if dependency.task_name in depedencies_names:
                raise ValueError(f"Duplicate dependency name: {dependency.task_name}")
            depedencies_names.append(dependency.task_name)
            if dependency.task_name == self.name:
                raise CircularDependencyError(f"Task '{self.name}' lists itself as a dependency.")

        logger = logging.getLogger(f"processes.{self.name}.{id(self)}")
        logger.setLevel(logging.DEBUG)

        file_channels: list[NotificationChannel] = (
            [_FileChannel(self.log_path)] if self.log_path is not None else []
        )
        all_channels: list[NotificationChannel] = [*file_channels, *self.channels]

        if all_channels:
            for channel in all_channels:
                logger.addHandler(channel.build_handler(self.name))
        else:
            logger.addHandler(logging.NullHandler())

        self._frame_filter: str | None = next(
            (c.frame_filter for c in all_channels if c.frame_filter is not None), None
        )
        self.logger = logger

    def _check_input_types(self) -> None:
        """
        Validates all input parameter types.

        Raises
        ------
        TypeError
            If any parameter is not of the expected type.
        """
        if not callable(self.func):
            raise TypeError(f"func must be callable. Got {type(self.func)}")

        if not isinstance(self.args, tuple):
            raise TypeError(f"args must be tuple. Got {type(self.args)}")

        if not isinstance(self.kwargs, dict):
            raise TypeError(f"kwargs must be dict. Got {type(self.kwargs)}")

        if not isinstance(self.dependencies, list):
            raise TypeError(f"dependencies must be list. Got {type(self.dependencies)}")

        for dependency in self.dependencies:
            if not isinstance(dependency, TaskDependency):
                raise TypeError(
                    f"dependency must be of type TaskDependency. Got {type(dependency)}"
                )

        if not isinstance(self.channels, list):
            raise TypeError(f"channels must be list. Got {type(self.channels)}")

        for channel in self.channels:
            if not isinstance(channel, NotificationChannel):
                raise TypeError(f"channel must be of type NotificationChannel. Got {type(channel)}")

        if self.timeout is not None and (
            not isinstance(self.timeout, (int, float)) or self.timeout <= 0
        ):
            raise TypeError(f"timeout must be a positive number or None, got {self.timeout!r}")
        if not isinstance(self.retries, int) or self.retries < 0:
            raise TypeError(f"retries must be a non-negative int, got {self.retries!r}")
        if self.retry_on is not None and (
            not isinstance(self.retry_on, tuple)
            or not all(isinstance(e, type) and issubclass(e, Exception) for e in self.retry_on)
        ):
            raise TypeError("retry_on must be None or a tuple of Exception subclasses")

    def get_dependencies_names(self) -> set[str]:
        """
        Get the names of all tasks this task depends on.

        Returns
        -------
        set[str]
            Set of dependency task names.
        """
        return {dependency.task_name for dependency in self.dependencies}

    def close_handlers(self) -> None:
        """Close and detach every handler on this task's logger.

        The task owns the lifecycle of the logger it builds in ``__init__``;
        this is the single teardown path used by ``Process.close_loggers`` and
        ``Process.remove_task``. Safe to call more than once.
        """
        for handler in list(self.logger.handlers):
            handler.close()
            self.logger.removeHandler(handler)

    def _call_with_timeout(self, args: list[Any], kwargs: dict[Any, Any]) -> Any:
        """Call ``self.func(*args, **kwargs)``, raising ``TimeoutError`` if
        ``self.timeout`` seconds elapse before the function returns.

        When a timeout fires the underlying thread is detached rather than
        killed — this is a Python threading limitation.
        """
        if self.timeout is None:
            return self.func(*args, **kwargs)
        executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
        fut = executor.submit(self.func, *args, **kwargs)
        try:
            return fut.result(timeout=self.timeout)
        except concurrent.futures.TimeoutError as err:
            raise TimeoutError(f"Task '{self.name}' timed out after {self.timeout}s") from err
        finally:
            executor.shutdown(wait=False)

    def _resolve_args(self, executing_process: Process | None) -> tuple[list[Any], dict[str, Any]]:
        """Inject upstream dependency results into args/kwargs."""
        final_args = list(self.args)
        final_kwargs = self.kwargs.copy()
        if executing_process is not None:
            for dep in self.dependencies:
                dep_result = executing_process.runner.results[dep.task_name].result
                if dep.use_result_as_additional_args:
                    final_args.append(dep_result)
                if dep.use_result_as_additional_kwargs:
                    final_kwargs[dep.additional_kwarg_name] = dep_result
        return final_args, final_kwargs

    def _build_failure_context(
        self, exc: Exception, executing_process: Process | None
    ) -> dict[str, Any]:
        """Build the structured failure payload passed to every log handler."""
        downstream_names: list[str] = (
            [d.name for d in executing_process.get_dependant_tasks(self.name)]
            if executing_process is not None
            else []
        )
        exc_tb = exc.__traceback__
        return {
            "task_name": self.name,
            "function": self.func.__name__,
            "args": self.args,
            "kwargs": self.kwargs,
            "downstream_impact": downstream_names,
            "exception": str(exc),
            "traceback_str": _format_traceback(exc),
            "traced_vars": _build_traced_vars(exc_tb, self._frame_filter),
            "traced_vars_location": _build_traced_vars_location(exc_tb, self._frame_filter),
        }

    def _errored_result(
        self,
        exc: Exception,
        executing_process: Process | None,
        elapsed_seconds: float,
        attempts: int,
    ) -> TaskResult:
        """Log ``exc`` through this task's handlers and wrap it in a TaskResult."""
        task_context = self._build_failure_context(exc, executing_process)
        self.logger.error(str(exc), exc_info=exc, extra={"task_context": task_context})
        return TaskResult.errored(
            exc,
            error_data=ErrorData(**task_context),
            elapsed_seconds=elapsed_seconds,
            attempts=attempts,
        )

    def run(self, executing_process: Process | None = None) -> TaskResult:
        """Execute the task, retrying on transient failures up to ``retries`` times.

        Never propagates: a failure while resolving dependency arguments (before
        any attempt runs) is captured and returned as an ``ERRORED`` result with
        ``attempts=0``, just like a failure inside the task's function.

        Parameters
        ----------
        executing_process : Process, optional
            Parent process; used to inject dependency results and to build
            the downstream impact list on failure.

        Returns
        -------
        TaskResult
            ``worked=True`` with the return value on success; ``worked=False``
            with the last exception on failure.
        """
        max_attempts = self.retries + 1
        effective_retry_on = (
            self.retry_on if self.retry_on is not None else (ConnectionError, TimeoutError)
        )

        self.logger.info(f"Starting {self.name}.")
        start = time.monotonic()

        try:
            final_args, final_kwargs = self._resolve_args(executing_process)
        except Exception as e:
            return self._errored_result(e, executing_process, time.monotonic() - start, attempts=0)

        last_exc: Exception | None = None
        for attempt in range(1, max_attempts + 1):
            try:
                result = self._call_with_timeout(final_args, final_kwargs)
                self.logger.info(f"Finished {self.name}.")
                return TaskResult.success(
                    result, elapsed_seconds=time.monotonic() - start, attempts=attempt
                )
            except Exception as e:
                last_exc = e
                retryable = self.retries >= 1 and attempt < max_attempts
                if retryable and isinstance(e, effective_retry_on):
                    self.logger.warning(
                        f"Attempt {attempt}/{max_attempts} failed: {e}. Retrying..."
                    )
                    continue
                break

        assert last_exc is not None
        return self._errored_result(
            last_exc, executing_process, time.monotonic() - start, attempts=attempt
        )
