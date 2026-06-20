"""Communication layer: channels, transports and renderers.

Public surface re-exported here (and, in turn, from ``processes``):
the channel ports (``NotificationChannel``, ``ReportChannel``), the shared
``ReportContent`` selector, the concrete ``EmailChannel`` / ``WebhookChannel``,
and their transport configs.
"""

from .base import NotificationChannel as NotificationChannel
from .base import ReportChannel as ReportChannel
from .base import ReportContent as ReportContent
from .channels import EmailChannel as EmailChannel
from .channels import WebhookChannel as WebhookChannel
from .email_config import HTMLEmailStyle as HTMLEmailStyle
from .email_config import SMTPConfig as SMTPConfig
from .webhook_config import WebhookConfig as WebhookConfig
