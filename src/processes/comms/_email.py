from __future__ import annotations

import html
import json
import os
import smtplib
from email.mime.text import MIMEText
from email.utils import formatdate
from typing import TYPE_CHECKING, cast

from ..task_types import TaskStatus
from .email_config import HTMLEmailStyle, SMTPConfig

if TYPE_CHECKING:
    from ..execution_report import ProcessExecutionReport, TaskReportEntry
    from .base import ReportContent

_THEMES_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "themes")
_STYLES_DIR = os.path.join(_THEMES_DIR, "styles")
_PALETTES_DIR = os.path.join(_THEMES_DIR, "palettes")
_LANGUAGES_DIR = os.path.join(_THEMES_DIR, "languages")

_PALETTE_MARKER = "{{__palette_css__}}"


def _load_language_strings(language: str) -> dict[str, str]:
    """Load translatable strings for the given ISO 639-1 language code.

    Parameters
    ----------
    language : str
        ISO 639-1 language code, e.g. ``"en"``.

    Returns
    -------
    dict[str, str]
        Mapping of translation keys to localized strings.
    """
    path = os.path.join(_LANGUAGES_DIR, f"{language}.json")
    with open(path, encoding="utf-8") as fh:
        return cast(dict[str, str], json.load(fh))


class _SMTPTransport:
    """Sends one HTML email per call over a fresh SMTP connection.

    The single place that owns the SMTP conversation (connect, optional
    STARTTLS + login, ``sendmail``, ``quit``); ``send_report_email`` delegates
    here.
    """

    def __init__(self, config: SMTPConfig) -> None:
        self._config = config

    def send(self, subject: str, html_body: str) -> None:
        """Connect, send a single HTML message, and disconnect.

        Parameters
        ----------
        subject : str
            The email subject line.
        html_body : str
            The fully rendered HTML body.
        """
        config = self._config
        if isinstance(config.mailhost, tuple):
            host, port = config.mailhost[0], config.mailhost[1]
        else:
            host, port = config.mailhost, smtplib.SMTP_PORT

        smtp = smtplib.SMTP(host, port)
        mime_msg = MIMEText(html_body, "html")
        mime_msg["From"] = config.fromaddr
        mime_msg["To"] = ",".join(config.toaddrs)
        mime_msg["Subject"] = subject
        mime_msg["Date"] = formatdate()
        if config.credentials is not None:
            username, password = config.credentials
            if config.secure is not None:
                smtp.starttls(*config.secure)
            smtp.login(username, password)
        smtp.sendmail(config.fromaddr, config.toaddrs, mime_msg.as_string())
        smtp.quit()


def _build_task_section_html(
    entry: TaskReportEntry,
    lang: dict[str, str],
    content: ReportContent,
) -> str:
    """Build a ``<details>`` HTML block for one task entry.

    Errored tasks are rendered ``open`` with full error detail; success/skipped
    tasks are collapsed and show only the function name. ``<details>`` degrades
    gracefully in clients that don't support it (content shows expanded).
    """
    status_val = entry.status.value
    badge_classes = {
        "SUCCESS": "badge-success",
        "ERRORED": "badge-errored",
        "SKIPPED": "badge-skipped",
    }
    badge_class = badge_classes.get(status_val, "badge-skipped")
    status_label = {
        "SUCCESS": lang.get("lang_status_success", "Success"),
        "ERRORED": lang.get("lang_status_errored", "Error"),
        "SKIPPED": lang.get("lang_status_skipped", "Skipped"),
    }.get(status_val, status_val)
    open_attr = " open" if entry.status == TaskStatus.ERRORED else ""

    fn_label = html.escape(lang.get("lang_function_label", "Function"))
    parts = [
        f'<div class="row">'
        f'<div class="row-label">{fn_label}</div>'
        f'<div class="row-value"><code>{html.escape(entry.function)}</code></div>'
        f"</div>"
    ]

    if entry.status == TaskStatus.ERRORED and entry.error is not None:
        exc_label = html.escape(lang.get("lang_exception_label", "Exception"))
        parts.append(
            f'<div class="row">'
            f'<div class="row-label">{exc_label}</div>'
            f'<div class="row-value"><code>{html.escape(entry.error.exception)}</code></div>'
            f"</div>"
        )
        if entry.error.downstream_impact:
            ds_label = html.escape(lang.get("lang_downstream_title", "Downstream"))
            items_html = "".join(
                f"<li>{html.escape(n)}</li>" for n in entry.error.downstream_impact
            )
            parts.append(
                f'<div class="row">'
                f'<div class="row-label">{ds_label}</div>'
                f'<div class="row-value"><ul class="impact-list">{items_html}</ul></div>'
                f"</div>"
            )
        if content.show_traceback and entry.error.traceback_str:
            tb_title = html.escape(lang.get("lang_traceback_title", "Traceback"))
            parts.append(f'<div class="subsection-title">{tb_title}</div>')
            parts.append(f'<pre class="traceback">{html.escape(entry.error.traceback_str)}</pre>')

        if content.show_traced_vars and entry.error.traced_vars:
            tv_title = html.escape(lang.get("lang_traced_vars_title", "Traced Variables"))
            blurb = html.escape(
                lang.get("lang_traced_vars_blurb", "Local variables at {location}:").replace(
                    "{location}", entry.error.traced_vars_location
                )
            )
            traced_html = "\n".join(
                html.escape(f"{k} = {v}") for k, v in entry.error.traced_vars.items()
            )
            parts.append(f'<div class="subsection-title">{tv_title}</div>')
            parts.append(f'<div class="traced-vars-blurb">{blurb}</div>')
            parts.append(f'<pre class="traceback">{traced_html}</pre>')

    detail_inner = "\n".join(parts)
    task_detail = f'<div class="task-detail">\n{detail_inner}\n</div>'

    return (
        f"<details{open_attr}>\n"
        f"  <summary>"
        f'<span class="task-name-text">{html.escape(entry.name)}</span>'
        f'<span class="badge {badge_class}">{html.escape(status_label)}</span>'
        f"</summary>\n"
        f"  {task_detail}\n"
        f"</details>"
    )


def _build_report_html(
    report: ProcessExecutionReport,
    style: HTMLEmailStyle,
    content: ReportContent,
    *,
    errors_only: bool,
) -> str:
    """Render a ``ProcessExecutionReport`` as a full HTML email body.

    Uses ``themes/styles/report.html`` + the palette chosen in ``style``.
    Language strings from ``style.language`` are applied throughout.

    Parameters
    ----------
    report : ProcessExecutionReport
        The finished report to render.
    style : HTMLEmailStyle
        Palette and language for the rendered body.
    content : ReportContent
        Controls whether traceback and traced-variables sections appear.
    errors_only : bool
        When ``True`` only ERRORED entries appear in the output.
    """
    lang = _load_language_strings(style.language)
    palette_path = os.path.join(_PALETTES_DIR, f"{style.palette}.css")
    with open(palette_path, encoding="utf-8") as fh:
        palette_css = fh.read()
    report_template_path = os.path.join(_STYLES_DIR, "report.html")
    with open(report_template_path, encoding="utf-8") as fh:
        template = fh.read()

    template = template.replace(_PALETTE_MARKER, palette_css)

    entries = report.errored if errors_only else report.entries
    header = (
        lang.get("lang_report_header_errors_only", "Failed Tasks Report")
        if errors_only
        else lang.get("lang_report_header", "Process Execution Report")
    )
    task_sections = "\n".join(
        _build_task_section_html(entry, lang, content) for entry in entries.values()
    )

    substitutions = {
        "lang_report_header": html.escape(header),
        "lang_report_title_prefix": html.escape(
            lang.get("lang_report_title_prefix", "Process Report")
        ),
        "lang_report_summary_title": html.escape(lang.get("lang_report_summary_title", "Summary")),
        "lang_report_success_label": html.escape(
            lang.get("lang_report_success_label", "Successes")
        ),
        "lang_report_error_label": html.escape(lang.get("lang_report_error_label", "Errors")),
        "lang_report_skipped_label": html.escape(lang.get("lang_report_skipped_label", "Skipped")),
        "summary_successes": str(len(report.successes)),
        "summary_errors": str(len(report.errored)),
        "summary_skipped": str(len(report.skipped)),
        "task_sections": task_sections,
    }
    rendered = template
    for key, value in substitutions.items():
        rendered = rendered.replace("{{" + key + "}}", value)
    return rendered


def send_report_email(
    report: ProcessExecutionReport,
    smtp_config: SMTPConfig,
    style: HTMLEmailStyle,
    content: ReportContent,
    *,
    errors_only: bool,
) -> None:
    """Send a finished ``ProcessExecutionReport`` as an HTML email.

    Parameters
    ----------
    report : ProcessExecutionReport
        The finished report to deliver.
    smtp_config : SMTPConfig
        SMTP transport configuration.
    style : HTMLEmailStyle
        Palette and language for the HTML body.
    content : ReportContent
        Content selection (traceback, traced-vars).
    errors_only : bool
        When ``True`` only ERRORED entries are included and the subject
        uses ``lang_report_email_subject_errors``.
    """
    lang = _load_language_strings(style.language)
    subject_key = "lang_report_email_subject_errors" if errors_only else "lang_report_email_subject"
    subject = lang.get(subject_key, "Process Execution Report")
    html_body = _build_report_html(report, style, content, errors_only=errors_only)
    _SMTPTransport(smtp_config).send(subject, html_body)
