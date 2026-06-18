from __future__ import annotations

import html
import json
import logging
import logging.handlers
import os
import smtplib
from email.mime.text import MIMEText
from email.utils import formatdate
from typing import TYPE_CHECKING, cast

from ..task_types import TaskStatus
from ._error_context import _ErrorContextFormatter
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


class _HTMLEmailFormatter(_ErrorContextFormatter):
    """Pure renderer: reads all error context from ``record.task_context`` and
    fills the HTML template.  No exception-info parsing or frame walking here.
    """

    def __init__(self, style: HTMLEmailStyle) -> None:
        super().__init__()
        self._email_style = style.style
        self._color_palette = style.palette
        self._email_language = style.language
        self._cached_template: str | None = None

    def _resolve_template(self) -> str:
        style_path = os.path.join(_STYLES_DIR, f"{self._email_style}.html")
        palette_path = os.path.join(_PALETTES_DIR, f"{self._color_palette}.css")
        with open(style_path, encoding="utf-8") as fh:
            style = fh.read()
        with open(palette_path, encoding="utf-8") as fh:
            palette = fh.read()
        return style.replace(_PALETTE_MARKER, palette)

    def _get_template(self) -> str:
        if self._cached_template is None:
            self._cached_template = self._resolve_template()
        return self._cached_template

    def _split_traceback_at_target(self, tb_str: str, location: str) -> tuple[str, str, str]:
        """Split *tb_str* around the frame line matching *location*.

        Parameters
        ----------
        tb_str : str
            Full formatted traceback to split.
        location : str
            ``"filename:lineno"`` of the frame to highlight, as produced by
            ``_build_traced_vars_location``.

        Returns
        -------
        tuple[str, str, str]
            ``(before, highlight, after)`` where ``highlight`` is the
            ``File "<filename>", line <lineno>, in <func>`` line for that
            frame. Returns ``("", "", tb_str)`` if no match is found.
        """
        if not tb_str or not location:
            return ("", "", tb_str)
        try:
            filename, lineno_str = location.rsplit(":", 1)
            lineno = int(lineno_str)
        except ValueError:
            return ("", "", tb_str)

        needle = f'  File "{filename}", line {lineno}, in'
        lines = tb_str.splitlines(keepends=True)
        for i, line in enumerate(lines):
            if needle in line:
                return ("".join(lines[:i]), line, "".join(lines[i + 1 :]))
        return ("", "", tb_str)

    def _render(self, template: str, substitutions: dict[str, str]) -> str:
        rendered = template
        for key, value in substitutions.items():
            rendered = rendered.replace("{{" + key + "}}", value)
        return rendered

    def format(self, record: logging.LogRecord) -> str:
        """Render a log record as a complete HTML email body.

        Parameters
        ----------
        record : logging.LogRecord
            The record being formatted.

        Returns
        -------
        str
            The fully rendered HTML email body.
        """
        error = self._error_data(record)

        tb_before, tb_highlight, tb_after = self._split_traceback_at_target(
            error.traceback_str, error.traced_vars_location
        )

        downstream_items = "".join(
            f"<li>{html.escape(str(name), quote=True)}</li>" for name in error.downstream_impact
        )

        traced_vars_html = "\n".join(
            html.escape(f"{name} = {value}", quote=True)
            for name, value in error.traced_vars.items()
        )

        substitutions = dict(_load_language_strings(self._email_language))
        substitutions["lang_traced_vars_blurb"] = substitutions.get(
            "lang_traced_vars_blurb", ""
        ).replace("{location}", error.traced_vars_location)
        substitutions.update(
            {
                "task_name": html.escape(error.task_name, quote=True),
                "function": html.escape(error.function, quote=True),
                "args": html.escape(repr(error.args), quote=True),
                "kwargs": html.escape(repr(error.kwargs), quote=True),
                "exception": html.escape(error.exception, quote=True),
                "traceback_before": html.escape(tb_before, quote=True),
                "traceback_highlight": html.escape(tb_highlight, quote=True),
                "traceback_after": html.escape(tb_after, quote=True),
                "traced_vars": traced_vars_html,
                "downstream_items": downstream_items,
            }
        )
        return self._render(self._get_template(), substitutions)


class _SMTPTransport:
    """Sends one HTML email per call over a fresh SMTP connection.

    The single place that owns the SMTP conversation (connect, optional
    STARTTLS + login, ``sendmail``, ``quit``). Both the streaming task handler
    (``_HTMLEmailHandler``) and the one-shot report sender (``send_report_email``)
    delegate here, so the transport logic exists exactly once.
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


class _HTMLEmailHandler(logging.handlers.SMTPHandler):
    """Internal SMTP handler that sends log records as HTML emails."""

    def __init__(self, config: SMTPConfig) -> None:
        super().__init__(
            config.mailhost,
            config.fromaddr,
            config.toaddrs,
            "",  # subject set by _build_task_email_handler
            credentials=config.credentials,
            secure=config.secure,  # type: ignore[arg-type]
            timeout=config.timeout,
        )
        self._transport = _SMTPTransport(config)

    def emit(self, record: logging.LogRecord) -> None:
        try:
            self._transport.send(self.getSubject(record), self.format(record))
        except Exception:
            self.handleError(record)


def _build_task_email_handler(
    smtp_config: SMTPConfig,
    style: HTMLEmailStyle,
    task_name: str,
) -> _HTMLEmailHandler:
    """Create a fully configured email handler bound to one task.

    Parameters
    ----------
    smtp_config : SMTPConfig
        SMTP transport configuration for the handler.
    style : HTMLEmailStyle
        HTML presentation settings used by the handler's formatter.
    task_name : str
        Name of the task the handler is bound to, used in the email subject.

    Returns
    -------
    _HTMLEmailHandler
        A handler at ``logging.ERROR`` level, with its formatter and
        localized subject configured.
    """
    handler = _HTMLEmailHandler(smtp_config)
    handler.setFormatter(_HTMLEmailFormatter(style))
    handler.setLevel(logging.ERROR)
    lang_strings = _load_language_strings(style.language)
    handler.subject = f"{lang_strings['lang_email_subject']}{task_name}"
    return handler


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
        f'  <summary>'
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
    ``style.style`` (layout variant) is not used for reports — a single
    multi-task layout is defined in ``report.html`` regardless of the
    classic/modern/compact setting.

    Parameters
    ----------
    report : ProcessExecutionReport
        The finished report to render.
    style : HTMLEmailStyle
        Palette and language are respected; layout variant is not.
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
        "lang_report_summary_title": html.escape(
            lang.get("lang_report_summary_title", "Summary")
        ),
        "lang_report_success_label": html.escape(
            lang.get("lang_report_success_label", "Successes")
        ),
        "lang_report_error_label": html.escape(lang.get("lang_report_error_label", "Errors")),
        "lang_report_skipped_label": html.escape(
            lang.get("lang_report_skipped_label", "Skipped")
        ),
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
    subject_key = (
        "lang_report_email_subject_errors" if errors_only else "lang_report_email_subject"
    )
    subject = lang.get(subject_key, "Process Execution Report")
    html_body = _build_report_html(report, style, content, errors_only=errors_only)
    _SMTPTransport(smtp_config).send(subject, html_body)
