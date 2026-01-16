from __future__ import annotations
from typing import Any, Callable, TYPE_CHECKING
if TYPE_CHECKING:
    from .process import Process

import logging
from .html_logging import HTMLSMTPHandler, ExceptionHTMLFormatter


class TaskResult:
    def __init__(self, worked: bool, result: Any, exception: Exception | None):
        self.worked = worked
        self.result = result
        self.exception = exception


class TaskDependency:
    def __init__(
            self,
            task_name: str,
            use_result_as_additional_args: bool = False,
            use_result_as_additional_kwargs: bool = False,
            additional_kwarg_name: str | None = None
        ):
        self.task_name = task_name
        self.use_result_as_additional_args = use_result_as_additional_args
        self.use_result_as_additional_kwargs = use_result_as_additional_kwargs
        self.additional_kwarg_name = additional_kwarg_name

        if not isinstance(self.task_name, str):
            raise TypeError(f"task_name must be of type str. Got {type(self.task_name)}")
        if not isinstance(self.use_result_as_additional_args, bool):
            raise TypeError(f"use_result_as_additional_args must be of type bool. Got {type(self.use_result_as_additional_args)}")
        if not isinstance(self.use_result_as_additional_kwargs, bool):
            raise TypeError(f"use_result_as_additional_kwargs must be of type bool. Got {type(self.use_result_as_additional_kwargs)}")

        if self.use_result_as_additional_kwargs and not isinstance(self.additional_kwarg_name, str):
            raise TypeError(f"If use_result_as_additional_kwargs is True, additional_kwarg_name must be set of type str. Got {type(self.additional_kwarg_name)}")
        
        
    def __hash__(self) -> int:
        return hash(self.task_name)


class Task:
    def __init__(
            self,
            name: str,
            log_path: str,
            func: Callable,
            args: tuple = (),
            kwargs: dict = {},
            dependencies: list[TaskDependency] = [],
            html_mail_handler: HTMLSMTPHandler = None
    ):
        self.name = name
        self.log_path = log_path
        self.func = func
        self.args = args
        self.kwargs = kwargs
        self.dependencies = dependencies
        self.html_mail_handler = html_mail_handler

        self._check_input_types()
        if ' ' in self.name:
            raise ValueError(f"Task name cannot contain spaces. Got {self.name}")

        depedencies_names = []
        for dependency in self.dependencies:
            if dependency.task_name in depedencies_names:
                raise ValueError(f"Duplicate dependency name: {dependency.task_name}")
            depedencies_names.append(dependency.task_name)
            if dependency.task_name == self.name:
                raise ValueError(f"Got dependency with same name as Task. Task: {self.name}. Dependency: {dependency.task_name}")

        logger = logging.getLogger(self.name)
        logger.setLevel(logging.DEBUG)
        if logger.hasHandlers():
            logger.handlers.clear()
        
        file_handler = logging.FileHandler(self.log_path)
        file_handler.setLevel(logging.INFO)
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
        
        if self.html_mail_handler is not None:
            _html_mail_handler = self.html_mail_handler.copy()
            _html_mail_handler.setFormatter(ExceptionHTMLFormatter())
            _html_mail_handler.setLevel(logging.ERROR)
            _html_mail_handler.subject = f"Error in task {self.name}"        
            logger.addHandler(_html_mail_handler)

        self.logger = logger

    def _check_input_types(self):
        if not callable(self.func):
            raise TypeError(f"func must be callable. Got {type(self.func)}")
        
        if not isinstance(self.args, tuple):
            raise TypeError(f"args must be tuple. Got {type(self.args)}")
        
        if not isinstance(self.kwargs, dict):
            raise TypeError(f"kwargs must be dict. Got {type(self.kwargs)}")
        
        if self.html_mail_handler is not None and not isinstance(self.html_mail_handler, HTMLSMTPHandler):
            raise TypeError(f"mail_cfg must be of type HTMLSMTPHandler. Got {type(self.html_mail_handler)}")
        
        if not isinstance(self.dependencies, list):
            raise TypeError(f"dependencies must be list. Got {type(self.dependencies)}")
        
        for dependency in self.dependencies:
            if not isinstance(dependency, TaskDependency):
                raise TypeError(f"dependency must be of type TaskDependency. Got {type(dependency)}")            

    def get_dependencies_names(self) -> set[str]:
        return {dependency.task_name for dependency in self.dependencies}
    
    def run(self, executing_process: Process | None = None) -> TaskResult:        
        aditional_args = () # Additional args coming from dependencies
        aditional_kwargs = {} # Additional kwargs coming from dependencies
        if executing_process is not None:
            for dep in self.dependencies:
                if dep.use_result_as_additional_args:
                    aditional_args += executing_process.runner.passed_results[dep.task_name].result,
                if dep.use_result_as_additional_kwargs:
                    aditional_kwargs[dep.additional_kwarg_name] = executing_process.runner.passed_results[dep.task_name].result

        self.args += aditional_args
        self.kwargs = {**self.kwargs, **(aditional_kwargs or {})}
        try:
            self.logger.info(f"Starting {self.name}.")
            result = self.func(*self.args, **self.kwargs)
            self.logger.info(f"Finished {self.name}.")
            return TaskResult(True, result, None)
        except Exception as e:
            report = ""
            if executing_process is not None:
                dependencies_names = [d.name for d in executing_process.get_dependant_tasks(self.name)]
                if dependencies_names:
                    report = "<h3>Downstream Impact</h3><p>The following tasks will be skipped:</p><ul>"
                    report += "".join(f"<li>{dependency_name}</li>" for dependency_name in dependencies_names)
                    report += "</ul>"
            report += f"<p><b>Context:</b><br>Function: {self.func.__name__}<br>Args: {self.args}<br>Kwargs: {self.kwargs}</p>"
            self.logger.exception(e, extra={"post_traceback_html_body": report})
            return TaskResult(False, None, e)