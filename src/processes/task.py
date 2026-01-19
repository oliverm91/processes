from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .process import Process

import logging

from .html_logging import ExceptionHTMLFormatter, HTMLSMTPHandler


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
    additional_kwarg_name : str | None
        The name of the keyword argument to use if use_result_as_additional_kwargs
        is True. Required when use_result_as_additional_kwargs is True.
        Defaults to None.

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
    and logging configuration. Tasks can be executed, by the Process class, sequentially
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
    html_mail_handler : HTMLSMTPHandler, optional
        Handler for sending error logs via email in HTML format. Defaults to None.
    logger : logging.Logger
        Logger instance for this task, automatically configured.
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
        html_mail_handler: HTMLSMTPHandler | None = None,
    ):
        self.name = name
        self.log_path = log_path
        self.func = func
        self.args = args
        self.html_mail_handler = html_mail_handler

        if kwargs is None:
            self.kwargs = {}
        else:
            self.kwargs = kwargs
        if dependencies is None:
            self.dependencies = []
        else:
            self.dependencies = dependencies

        self._check_input_types()
        if " " in self.name:
            raise ValueError(f"Task name cannot contain spaces. Got {self.name}")

        depedencies_names = []
        for dependency in self.dependencies:
            if dependency.task_name in depedencies_names:
                raise ValueError(f"Duplicate dependency name: {dependency.task_name}")
            depedencies_names.append(dependency.task_name)
            if dependency.task_name == self.name:
                raise ValueError(
                    f"Got dependency with same name as Task. "
                    f"Task: {self.name}. Dependency: {dependency.task_name}"
                )

        logger = logging.getLogger(self.name)
        logger.setLevel(logging.DEBUG)
        if logger.hasHandlers():
            logger.handlers.clear()

        file_handler = logging.FileHandler(self.log_path)
        file_handler.setLevel(logging.INFO)
        formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

        if self.html_mail_handler is not None:
            _html_mail_handler = self.html_mail_handler.copy()
            _html_mail_handler.setFormatter(ExceptionHTMLFormatter())
            _html_mail_handler.setLevel(logging.ERROR)
            _html_mail_handler.subject = f"Error in task {self.name}"
            logger.addHandler(_html_mail_handler)

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

        if self.html_mail_handler is not None and not isinstance(
            self.html_mail_handler, HTMLSMTPHandler
        ):
            raise TypeError(
                f"mail_cfg must be of type HTMLSMTPHandler. Got {type(self.html_mail_handler)}"
            )

        if not isinstance(self.dependencies, list):
            raise TypeError(f"dependencies must be list. Got {type(self.dependencies)}")

        for dependency in self.dependencies:
            if not isinstance(dependency, TaskDependency):
                raise TypeError(
                    f"dependency must be of type TaskDependency. Got {type(dependency)}"
                )

    def get_dependencies_names(self) -> set[str]:
        """
        Get the names of all tasks this task depends on.

        Returns
        -------
        set[str]
            Set of dependency task names.
        """
        return {dependency.task_name for dependency in self.dependencies}

    def run(
        self, executing_process: Process | None = None
    ) -> TaskResult:
        """
        Execute the task's function with its arguments and dependencies.

        This method runs the task's function, automatically injecting results from
        dependent tasks as specified in the dependency configuration. Logs the task
        execution and captures any exceptions.

        Parameters
        ----------
        executing_process : Process, optional
            The parent Process executing this task. Used to retrieve results from
            dependent tasks. Defaults to None.

        Returns
        -------
        TaskResult
            Object containing:
            - worked (bool): True if execution succeeded, False otherwise.
            - result: The return value of the function if successful, None if failed.
            - exception (Exception | None): The exception raised if execution failed,
            None if successful.
        """
        final_args = list(self.args)  # Start with original positional args
        final_kwargs = self.kwargs.copy()  # Start with original keyword args

        if executing_process is not None:
            for dep in self.dependencies:
                dep_result = executing_process.runner.passed_results[dep.task_name].result
                if dep.use_result_as_additional_args:
                    final_args.append(dep_result)
                if dep.use_result_as_additional_kwargs:
                    final_kwargs[dep.additional_kwarg_name] = dep_result

        try:
            self.logger.info(f"Starting {self.name}.")
            result = self.func(*final_args, **final_kwargs)
            self.logger.info(f"Finished {self.name}.")
            return TaskResult(True, result, None)
        except Exception as e:
            report = ""
            if executing_process is not None:
                dependencies_names = [
                    d.name for d in executing_process.get_dependant_tasks(self.name)
                ]
                if dependencies_names:
                    report = (
                        "<h3>Downstream Impact</h3><p>The following tasks will be skipped:</p><ul>"
                    )
                    report += "".join(
                        f"<li>{dependency_name}</li>" for dependency_name in dependencies_names
                    )
                    report += "</ul>"
            report += f"<p><b>Context:</b><br>Function: {self.func.__name__}"
            report += f"<br>Args: {self.args}<br>Kwargs: {self.kwargs}</p>"
            self.logger.exception(e, extra={"post_traceback_html_body": report})
            return TaskResult(False, None, e)
