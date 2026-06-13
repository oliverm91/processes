from importlib.metadata import PackageNotFoundError as _pnfe
from importlib.metadata import version as _v

from .email_config import HTMLEmailStyle as HTMLEmailStyle, SMTPConfig as SMTPConfig
from .exceptions import (
    CircularDependencyError as CircularDependencyError,
    DependencyNotFoundError as DependencyNotFoundError,
    TaskNotFoundError as TaskNotFoundError,
)
from .process import Process as Process
from .task import Task as Task, TaskDependency as TaskDependency, TaskResult as TaskResult

try:
    __version__ = _v("processes")
except _pnfe:
    __version__ = "0.0.0-unknown"
