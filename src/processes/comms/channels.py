from __future__ import annotations

from typing import TYPE_CHECKING

from ._email import send_report_email
from ._webhook import send_report_webhook
from .base import ReportChannel, ReportContent
from .email_config import HTMLEmailStyle, SMTPConfig
from .webhook_config import WebhookConfig

if TYPE_CHECKING:
    from ..execution_report import ProcessExecutionReport

__all__ = ["EmailChannel", "ReportChannel", "ReportContent", "WebhookChannel"]


class EmailChannel(ReportChannel):
    """Report channel that sends a finished report as a styled HTML email.

    Attributes
    ----------
    smtp_config : SMTPConfig
        SMTP transport configuration.
    style : HTMLEmailStyle
        HTML presentation settings (palette + language) for the report body.
    content : ReportContent
        Content selection used by :meth:`send_report`.

    Parameters
    ----------
    smtp_config : SMTPConfig
        SMTP transport configuration.
    style : HTMLEmailStyle | None
        HTML presentation settings. Defaults to ``HTMLEmailStyle()``
        (neutral palette, English) when ``None``.
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


class WebhookChannel(ReportChannel):
    """Report channel that POSTs a finished report as generic JSON.

    The payload is generic JSON, so it can be consumed directly or transformed
    by downstream relays (Slack/Discord/Teams adapters, custom alerting
    servers); it is not coupled to any specific service.

    Attributes
    ----------
    webhook_config : WebhookConfig
        Webhook transport configuration.
    content : ReportContent
        Content selection used by :meth:`send_report`.

    Parameters
    ----------
    webhook_config : WebhookConfig
        Webhook transport configuration.
    content : ReportContent | None
        Content selection for report delivery. Defaults to ``ReportContent()``
        (everything) when ``None``.
    """

    def __init__(self, webhook_config: WebhookConfig, content: ReportContent | None = None):
        self.webhook_config = webhook_config
        self.content = content or ReportContent()

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
