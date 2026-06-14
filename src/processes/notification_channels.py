from __future__ import annotations

import logging
from abc import ABC, abstractmethod

from ._email_internals import _build_task_email_handler
from ._logfile_formatting import _TaskLogfileFormatter
from .email_config import HTMLEmailStyle, SMTPConfig


class NotificationChannel(ABC):
    """Base class for task notification channels.

    A notification channel knows how to build a configured
    ``logging.Handler`` that delivers a task's log records (and, on
    failure, its structured failure context) to some destination. ``Task``
    attaches one handler per configured channel to its logger.

    Concrete channels (e.g. ``FileChannel``, ``EmailChannel``) wrap a
    specific delivery mechanism. New channels can be added by subclassing
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


class FileChannel(NotificationChannel):
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


class EmailChannel(NotificationChannel):
    """Notification channel that sends an HTML email alert on task failure.

    Attributes
    ----------
    smtp_config : SMTPConfig
        SMTP transport configuration for the alert.
    style : HTMLEmailStyle
        HTML presentation settings used to render the alert.

    Parameters
    ----------
    smtp_config : SMTPConfig
        SMTP transport configuration for the alert.
    style : HTMLEmailStyle | None
        HTML presentation settings used to render the alert. Defaults to
        ``HTMLEmailStyle()`` (modern, neutral, English) when ``None``.
    """

    def __init__(self, smtp_config: SMTPConfig, style: HTMLEmailStyle | None = None):
        self.smtp_config = smtp_config
        self.style = style or HTMLEmailStyle()

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
