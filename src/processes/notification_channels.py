from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import TYPE_CHECKING

from ._email_internals import _build_task_email_handler
from ._logfile_formatting import _TaskLogfileFormatter
from ._webhook_internals import _build_task_webhook_handler
from .email_config import HTMLEmailStyle, SMTPConfig
from .webhook_config import WebhookConfig

if TYPE_CHECKING:
    from .execution_report import ProcessExecutionReport


@dataclass(frozen=True)
class ReportContent:
    """What detail a report notification includes.

    Channel-agnostic content selection, shared by every ``ReportChannel``.
    Construct once and pass the same instance to several channels for uniform
    content, or give each channel its own for per-destination verbosity.

    Attributes
    ----------
    show_traceback : bool
        Include each failure's full traceback. Defaults to ``True``.
    show_traced_vars : bool
        Include each failure's traced local variables. Defaults to ``True``.
    """

    show_traceback: bool = True
    show_traced_vars: bool = True


class ReportChannel(ABC):
    """Base class for channels that deliver a finished ``ProcessExecutionReport``.

    Unlike ``NotificationChannel`` (which builds a streaming ``logging.Handler``
    for a single ``Task``), a report channel sends a complete report **once**,
    after the run. ``ProcessExecutionReport.notify`` / ``notify_errors`` iterate
    the channels they are given and call ``send_report`` on each.
    """

    @abstractmethod
    def send_report(self, report: ProcessExecutionReport, *, errors_only: bool) -> None:
        """Deliver ``report`` to this channel's destination.

        Parameters
        ----------
        report : ProcessExecutionReport
            The finished report to deliver.
        errors_only : bool
            If True, only the ``ERRORED`` entries are sent; otherwise the whole
            report is sent.
        """


class NotificationChannel(ABC):
    """Base class for task notification channels.

    A notification channel knows how to build a configured
    ``logging.Handler`` that delivers a task's log records (and, on
    failure, its structured failure context) to some destination. ``Task``
    attaches one handler per configured channel to its logger.

    Concrete channels wrap a specific delivery mechanism (e.g. a logfile or
    an email alert). New channels can be added by subclassing
    ``NotificationChannel`` and implementing ``build_handler``.
    """

    @abstractmethod
    def build_handler(self, task_name: str) -> logging.Handler:
        """Build a configured handler for the given task.

        Parameters
        ----------
        task_name : str
            Name of the task the handler will be attached to.

        Returns
        -------
        logging.Handler
            A handler ready to be added to the task's logger.
        """

    @property
    def frame_filter(self) -> str | None:
        """Substring selecting the traceback frame to trace local variables of.

        See ``HTMLEmailStyle.traced_vars_frame_filter``. Channels that don't
        influence frame selection return ``None`` (the default).

        Returns
        -------
        str | None
            ``None`` unless overridden by a subclass.
        """
        return None


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
        """Send the report as an HTML email. Not implemented yet.

        Rendering (a report-shaped HTML body honoring ``style`` and ``content``)
        and the one-shot SMTP send are deferred.

        Raises
        ------
        NotImplementedError
            Always, until report email rendering is implemented.
        """
        raise NotImplementedError("EmailChannel.send_report is not implemented yet.")


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
        """POST the report as JSON. Not implemented yet.

        Payload shaping (honoring ``content`` and ``errors_only``) and the
        one-shot signed POST are deferred.

        Raises
        ------
        NotImplementedError
            Always, until report webhook delivery is implemented.
        """
        raise NotImplementedError("WebhookChannel.send_report is not implemented yet.")
