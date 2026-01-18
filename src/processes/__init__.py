from importlib.metadata import PackageNotFoundError as _pnfe
from importlib.metadata import version as _v

from .html_logging import HTMLSMTPHandler as HTMLSMTPHandler
from .process import (
    CircularDependencyError as CircularDependencyError,
)
from .process import (
    DependencyNotFoundError as DependencyNotFoundError,
)
from .process import (
    Process as Process,
)
from .process import (
    TaskNotFoundError as TaskNotFoundError,
)
from .task import Task as Task
from .task import TaskDependency as TaskDependency
from .task import TaskResult as TaskResult

try:
    __version__ = _v("processes")
except _pnfe:
    __version__ = "0.0.0-unknown"
