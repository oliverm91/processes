from __future__ import annotations

import concurrent.futures
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .process import Process

import logging

from ._email_internals import _build_task_email_handler
from ._logfile_formatting import _TaskLogfileFormatter
from ._tb_utils import _build_traced_vars_html, _build_traced_vars_location, _format_traceback
from .email_config import HTMLEmailStyle, SMTPConfig
from .exceptions import CircularDependencyError


class TaskResult:
    """
    Container for the result of a task execution.

    Holds the outcome of running a task, including whether it succeeded,
    its return value, and any exception that occurred.

    Attributes
    ----------
    worked : bool
        True if the task executed successfully, False if an exception occurred.
    result : Any
        The return value of the task's function if execution succeeded, None if failed.
    exception : Exception | None
        The exception object if execution failed, None if successful.
    """

    def __init__(self, worked: bool, result: Any, exception: Exception | None):
        self.worked = worked
        self.result = result
        self.exception = exception


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
    log_path : str
        File path where task logs will be written.
    func : Callable
        The function to execute when the task runs.
    args : tuple
        Positional arguments to pass to the function. Defaults to empty tuple.
    kwargs : dict
        Keyword arguments to pass to the function. Defaults to empty dict.
    dependencies : list[TaskDependency]
        List of tasks this task depends on. Defaults to empty list.
    smtp_config : SMTPConfig, optional
        SMTP transport configuration for HTML email error alerts.
    email_style : HTMLEmailStyle, optional
        HTML presentation settings used alongside ``smtp_config``.
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
    log_path : str
        File path the task's log records are written to (one ``FileHandler``
        at ``INFO`` level, format
        ``"%(asctime)s - %(name)s - %(levelname)s - %(message)s"``).
    func : Callable[..., Any]
        The callable executed when the task runs.
    args : tuple[Any, ...]
        Positional arguments forwarded to ``func``. Defaults to ``()``.
    kwargs : dict[str, Any] | None
        Keyword arguments forwarded to ``func``. ``None`` is treated as
        an empty dict.
    dependencies : list[TaskDependency] | None
        Tasks this task depends on. ``None`` is treated as an empty list.
    smtp_config : SMTPConfig | None
        SMTP transport configuration. When provided, a styled HTML email is sent
        on ``logging.ERROR`` and above. Defaults to ``None``.
    email_style : HTMLEmailStyle | None
        HTML presentation settings (style, palette, language, traced-vars filter).
        Used only when ``smtp_config`` is set. Defaults to ``HTMLEmailStyle()``
        (modern, neutral, English).
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
        positive number, ``retries`` is negative, or ``retry_on`` is not a
        tuple of ``Exception`` subclasses.
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
        log_path: str,
        func: Callable[..., Any],
        args: tuple[Any, ...] = (),
        kwargs: dict[str, Any] | None = None,
        dependencies: list[TaskDependency] | None = None,
        smtp_config: SMTPConfig | None = None,
        email_style: HTMLEmailStyle | None = None,
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

        self._check_input_types(smtp_config, email_style)
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

        file_handler = logging.FileHandler(self.log_path)
        file_handler.setLevel(logging.INFO)
        file_handler.setFormatter(_TaskLogfileFormatter())
        logger.addHandler(file_handler)

        if smtp_config is not None:
            style = email_style or HTMLEmailStyle()
            logger.addHandler(_build_task_email_handler(smtp_config, style, self.name))

        self._frame_filter: str | None = (
            email_style.traced_vars_frame_filter if email_style is not None else None
        )
        self.logger = logger

    def _check_input_types(
        self,
        smtp_config: SMTPConfig | None,
        email_style: HTMLEmailStyle | None,
    ) -> None:
        """
        Validates all input parameter types.

        Parameters
        ----------
        smtp_config : SMTPConfig | None
            SMTP transport configuration passed to the constructor, if any.
        email_style : HTMLEmailStyle | None
            HTML presentation settings passed to the constructor, if any.

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

        if smtp_config is not None and not isinstance(smtp_config, SMTPConfig):
            raise TypeError(f"smtp_config must be of type SMTPConfig. Got {type(smtp_config)}")
        if email_style is not None and not isinstance(email_style, HTMLEmailStyle):
            raise TypeError(f"email_style must be of type HTMLEmailStyle. Got {type(email_style)}")

        if not isinstance(self.dependencies, list):
            raise TypeError(f"dependencies must be list. Got {type(self.dependencies)}")

        for dependency in self.dependencies:
            if not isinstance(dependency, TaskDependency):
                raise TypeError(
                    f"dependency must be of type TaskDependency. Got {type(dependency)}"
                )

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
                dep_result = executing_process.runner.passed_results[dep.task_name].result
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
            "traced_vars": _build_traced_vars_html(exc_tb, self._frame_filter),
            "traced_vars_location": _build_traced_vars_location(exc_tb, self._frame_filter),
        }

    def run(self, executing_process: Process | None = None) -> TaskResult:
        """Execute the task, retrying on transient failures up to ``retries`` times.

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
        final_args, final_kwargs = self._resolve_args(executing_process)

        max_attempts = self.retries + 1
        effective_retry_on = (
            self.retry_on if self.retry_on is not None else (ConnectionError, TimeoutError)
        )

        self.logger.info(f"Starting {self.name}.")
        last_exc: Exception | None = None

        for attempt in range(1, max_attempts + 1):
            try:
                result = self._call_with_timeout(final_args, final_kwargs)
                self.logger.info(f"Finished {self.name}.")
                return TaskResult(True, result, None)
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
        task_context = self._build_failure_context(last_exc, executing_process)
        self.logger.error(str(last_exc), exc_info=last_exc, extra={"task_context": task_context})
        return TaskResult(False, None, last_exc)
