from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from ._email import _build_task_email_handler, send_report_email
from ._logfile import _TaskLogfileFormatter
from ._webhook import _build_task_webhook_handler, send_report_webhook
from .base import NotificationChannel, ReportChannel, ReportContent
from .email_config import HTMLEmailStyle, SMTPConfig
from .webhook_config import WebhookConfig

if TYPE_CHECKING:
    from ..execution_report import ProcessExecutionReport

__all__ = [
    "EmailChannel",
    "NotificationChannel",
    "ReportChannel",
    "ReportContent",
    "WebhookChannel",
]


class _FileChannel(NotificationChannel):
    """Notification channel that writes task log records to a plain-text file.

    Attributes
    ----------
    log_path : str
        File path the handler writes to.
    level : int
        Minimum log level handled. Defaults to ``logging.INFO``.

    Parameters
    ----------
    log_path : str
        File path the handler writes to.
    level : int
        Minimum log level handled. Defaults to ``logging.INFO``.
    """

    def __init__(self, log_path: str, level: int = logging.INFO):
        self.log_path = log_path
        self.level = level

    def build_handler(self, task_name: str) -> logging.Handler:
        """Build a ``FileHandler`` writing to ``log_path``.

        Parameters
        ----------
        task_name : str
            Name of the task the handler will be attached to. Unused by
            this channel, accepted for interface consistency.

        Returns
        -------
        logging.Handler
            A ``FileHandler`` at ``level``, formatted with
            ``_TaskLogfileFormatter``.
        """
        handler = logging.FileHandler(self.log_path)
        handler.setLevel(self.level)
        handler.setFormatter(_TaskLogfileFormatter())
        return handler


class EmailChannel(NotificationChannel, ReportChannel):
    """Channel that sends HTML email: a per-task failure alert and/or a report.

    As a ``NotificationChannel`` it builds a streaming handler for a ``Task``
    (one email per failure). As a ``ReportChannel`` it sends a finished
    ``ProcessExecutionReport`` once via :meth:`send_report`. The same instance
    can serve both roles.

    Attributes
    ----------
    smtp_config : SMTPConfig
        SMTP transport configuration for the alert.
    style : HTMLEmailStyle
        HTML presentation settings used to render the alert.
    content : ReportContent
        Content selection used by :meth:`send_report` (ignored by the per-task
        handler).

    Parameters
    ----------
    smtp_config : SMTPConfig
        SMTP transport configuration for the alert.
    style : HTMLEmailStyle | None
        HTML presentation settings used to render the alert. Defaults to
        ``HTMLEmailStyle()`` (modern, neutral, English) when ``None``.
    content : ReportContent | None
        Content selection for report delivery. Defaults to ``ReportContent()``
        (everything) when ``None``.
    """

    def __init__(
        self,
        smtp_config: SMTPConfig,
        style: HTMLEmailStyle | None = None,
        content: ReportContent | None = None,
    ):
        self.smtp_config = smtp_config
        self.style = style or HTMLEmailStyle()
        self.content = content or ReportContent()

    def build_handler(self, task_name: str) -> logging.Handler:
        """Build an HTML email handler bound to ``task_name``.

        Parameters
        ----------
        task_name : str
            Name of the task the handler will be attached to, used in the
            email subject.

        Returns
        -------
        logging.Handler
            A handler at ``logging.ERROR`` level that sends a styled HTML
            email for each error log record.
        """
        return _build_task_email_handler(self.smtp_config, self.style, task_name)

    @property
    def frame_filter(self) -> str | None:
        """Frame filter sourced from ``style.traced_vars_frame_filter``.

        Returns
        -------
        str | None
            The configured ``traced_vars_frame_filter``, or ``None``.
        """
        return self.style.traced_vars_frame_filter

    def send_report(self, report: ProcessExecutionReport, *, errors_only: bool) -> None:
        """Send the report as a styled HTML email via SMTP.

        Renders a multi-task HTML body using ``style`` (palette + language)
        and ``content`` (traceback / traced-vars flags), then sends it as a
        one-shot SMTP message.

        Parameters
        ----------
        report : ProcessExecutionReport
            The finished report to deliver.
        errors_only : bool
            When ``True`` only ERRORED entries are included in the email.
        """
        send_report_email(
            report, self.smtp_config, self.style, self.content, errors_only=errors_only
        )


class WebhookChannel(NotificationChannel, ReportChannel):
    """Channel that POSTs JSON: a per-task failure alert and/or a report.

    As a ``NotificationChannel`` it builds a streaming handler for a ``Task``
    (one POST per failure). As a ``ReportChannel`` it POSTs a finished
    ``ProcessExecutionReport`` once via :meth:`send_report`. The payload is
    generic JSON, so it can be consumed directly or transformed by downstream
    relays (Slack/Discord/Teams adapters, custom alerting servers); it is not
    coupled to any specific service.

    Attributes
    ----------
    webhook_config : WebhookConfig
        Webhook transport configuration for the alert.
    content : ReportContent
        Content selection used by :meth:`send_report` (ignored by the per-task
        handler).

    Parameters
    ----------
    webhook_config : WebhookConfig
        Webhook transport configuration for the alert.
    content : ReportContent | None
        Content selection for report delivery. Defaults to ``ReportContent()``
        (everything) when ``None``.
    """

    def __init__(self, webhook_config: WebhookConfig, content: ReportContent | None = None):
        self.webhook_config = webhook_config
        self.content = content or ReportContent()

    def build_handler(self, task_name: str) -> logging.Handler:
        """Build a JSON webhook handler.

        Parameters
        ----------
        task_name : str
            Name of the task the handler will be attached to. Unused by
            this channel, accepted for interface consistency.

        Returns
        -------
        logging.Handler
            A handler at ``logging.ERROR`` level that POSTs a JSON payload
            describing the failure for each error log record.
        """
        return _build_task_webhook_handler(self.webhook_config)

    def send_report(self, report: ProcessExecutionReport, *, errors_only: bool) -> None:
        """POST the report as a signed JSON payload.

        Builds the payload from the report entries (all or errored-only),
        applies ``content`` flags to control traceback / traced-vars inclusion,
        and performs a one-shot POST via ``webhook_config`` (honoring
        ``nest_under``, ``extra_payload``, HMAC signing, and custom headers).

        Parameters
        ----------
        report : ProcessExecutionReport
            The finished report to deliver.
        errors_only : bool
            When ``True`` only ERRORED entries are included in the payload.
        """
        send_report_webhook(report, self.webhook_config, self.content, errors_only=errors_only)
