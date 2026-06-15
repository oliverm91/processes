from importlib.metadata import PackageNotFoundError as _pnfe
from importlib.metadata import version as _v

from ._error_data import ErrorData as ErrorData
from .email_config import HTMLEmailStyle as HTMLEmailStyle
from .email_config import SMTPConfig as SMTPConfig
from .exceptions import (
    CircularDependencyError as CircularDependencyError,
)
from .exceptions import (
    DependencyNotFoundError as DependencyNotFoundError,
)
from .exceptions import (
    TaskNotFoundError as TaskNotFoundError,
)
from .notification_channels import EmailChannel as EmailChannel
from .notification_channels import NotificationChannel as NotificationChannel
from .notification_channels import WebhookChannel as WebhookChannel
from .process import Process as Process
from .task import Task as Task
from .task import TaskDependency as TaskDependency
from .task import TaskResult as TaskResult
from .webhook_config import WebhookConfig as WebhookConfig

try:
    __version__ = _v("processes")
except _pnfe:
    __version__ = "0.0.0-unknown"
