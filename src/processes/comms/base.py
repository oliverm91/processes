"""Communication ports: the abstract channel interfaces the domain depends on.

These abstractions are deliberately a leaf within ``comms`` — they import no
concrete channel, transport, or renderer — so ``task.py`` (streaming) and
``execution_report.py`` (one-shot) can depend on the *interface* without pulling
in the email/webhook implementations.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..execution_report import ProcessExecutionReport


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
    after the run. ``ProcessExecutionReport.notify`` iterates the channels it is
    given and calls ``send_report`` on each.
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
