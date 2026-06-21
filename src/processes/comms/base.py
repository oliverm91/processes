"""Communication port: the abstract report-channel interface the domain depends on.

``ReportChannel`` is deliberately a leaf within ``comms`` — it imports no concrete
channel, transport, or renderer — so ``execution_report.py`` can depend on the
*interface* without pulling in the email/webhook implementations.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..execution_report import ProcessExecutionReport


@dataclass(frozen=True, slots=True)
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

    A report channel sends a complete report **once**, after the run.
    ``ProcessExecutionReport.notify`` iterates the channels it is given and calls
    ``send_report`` on each.
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
