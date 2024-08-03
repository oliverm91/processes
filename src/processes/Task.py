from dataclasses import dataclass, field
import logging
from typing import Any, Callable, Optional

from easy_smtp import SMTPHandler

from .task_logger.TaskLogger import TaskLogger


@dataclass(slots=True)
class TaskResult:
    worked: bool
    result: Any
    exception: Optional[Exception]


@dataclass(slots=True)
class TaskDependency:
    task_name: str
    use_result_as_additional_args: bool
    use_result_as_additional_kwargs: bool
    additional_kwarg_name: Optional[str] = field(default=None)

    def __post_init__(self):
        if self.use_result_as_additional_kwargs and self.additional_kwarg_name is None:
            raise ValueError("additional_kwarg_name must be set if use_result_as_additional_kwargs is True")
        
    def __hash__(self) -> int:
        return hash(self.task_name)


@dataclass(slots=True)
class Task:
    name: str
    log_file: str
    func: Callable
    args: tuple = field(default_factory=tuple)
    kwargs: dict = field(default_factory=dict)

    dependencies: list[TaskDependency] = field(default_factory=set)
    
    mail_handler: Optional[SMTPHandler] = field(default=None)
    logger: TaskLogger = field(init=False)

    def __post_init__(self):
        self._check_input_types()

        logger = logging.getLogger(self.name)
        logger.setLevel(logging.DEBUG)
        file_handler = logging.FileHandler(self.log_file)
        file_handler.setLevel(logging.DEBUG)
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

        self.logger = TaskLogger(self.name, logger, mail_handler=self.mail_handler)

        depedencies_names = []
        for dependency in self.dependencies:
            if dependency.task_name in depedencies_names:
                raise ValueError(f"Duplicate dependency name: {dependency.task_name}")
            depedencies_names.append(dependency.task_name)

    def _check_input_types(self):
        if not callable(self.func):
            raise TypeError(f"func must be callable. Got {type(self.func)}")
        
        if not isinstance(self.args, tuple):
            raise TypeError(f"args must be tuple. Got {type(self.args)}")
        
        if not isinstance(self.kwargs, dict):
            raise TypeError(f"kwargs must be dict. Got {type(self.kwargs)}")
        
        if self.mail_handler is not None and not isinstance(self.mail_handler, SMTPHandler):
            raise TypeError(f"mail_cfg must be of type SMTPHandler (easy_smtp library). Got {type(self.mail_handler)}")
        
        if not isinstance(self.dependencies, list):
            raise TypeError(f"dependencies must be list. Got {type(self.dependencies)}")
        
        for dependency in self.dependencies:
            if not isinstance(dependency, str):
                raise TypeError(f"dependency must be str. Got {type(dependency)}")
            if dependency == self.name:
                raise ValueError(f"Got dependency with same name as Task. {dependency} == {self.name}")

    def get_dependencies_names(self) -> set[str]:
        return {dependency.task_name for dependency in self.dependencies}
    
    def add_args(self, *args):
        self.args += args

    def add_kwargs(self, **kwargs):
        self.kwargs = {**self.kwargs, **kwargs}

    def run(self, aditional_args: Optional[tuple[Any]] = None, aditional_kwargs: Optional[dict[str, Any]] = None, post_traceback_html_body: Optional[str] = None) -> TaskResult:
        try:
            if aditional_args:
                self.args += aditional_args
            if aditional_kwargs:
                self.kwargs = {**self.kwargs, **aditional_kwargs}
            self.logger.log_message(f"Starting {self.name}.")
            result = self.func(*self.args, **self.kwargs)
            self.logger.log_message(f"Finished {self.name}.")
            return TaskResult(True, result, None)
        except Exception as e:
            if post_traceback_html_body is None:
                post_traceback_html_body = ""
            post_traceback_html_body += f"<br><p>Function was: {self.func.__name__}. Args were: {self.args}. Kwargs were: {self.kwargs}.</p>"
            self.logger.log_error(e)
            return TaskResult(False, None, e)
