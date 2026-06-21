from importlib.metadata import PackageNotFoundError as _pnfe
from importlib.metadata import version as _v

from .comms import EmailChannel as EmailChannel
from .comms import HTMLEmailStyle as HTMLEmailStyle
from .comms import ReportChannel as ReportChannel
from .comms import ReportContent as ReportContent
from .comms import SMTPConfig as SMTPConfig
from .comms import WebhookChannel as WebhookChannel
from .comms import WebhookConfig as WebhookConfig
from .error_data import ErrorData as ErrorData
from .exceptions import (
    CircularDependencyError as CircularDependencyError,
)
from .exceptions import (
    DependencyNotFoundError as DependencyNotFoundError,
)
from .exceptions import (
    TaskNotFoundError as TaskNotFoundError,
)
from .execution_report import ProcessExecutionReport as ProcessExecutionReport
from .execution_report import TaskReportEntry as TaskReportEntry
from .process import Process as Process
from .task import Task as Task
from .task_types import TaskDependency as TaskDependency
from .task_types import TaskResult as TaskResult
from .task_types import TaskStatus as TaskStatus

try:
    __version__ = _v("processes")
except _pnfe:
    __version__ = "0.0.0-unknown"
