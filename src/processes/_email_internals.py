from __future__ import annotations

import html
import json
import logging
import logging.handlers
import os
import smtplib
from email.mime.text import MIMEText
from email.utils import formatdate
from typing import cast

from .email_config import HTMLEmailStyle, SMTPConfig

_THEMES_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "themes")
_STYLES_DIR = os.path.join(_THEMES_DIR, "styles")
_PALETTES_DIR = os.path.join(_THEMES_DIR, "palettes")
_LANGUAGES_DIR = os.path.join(_THEMES_DIR, "languages")

_PALETTE_MARKER = "{{__palette_css__}}"


def _load_language_strings(language: str) -> dict[str, str]:
    """Load translatable strings for the given ISO 639-1 language code."""
    path = os.path.join(_LANGUAGES_DIR, f"{language}.json")
    with open(path, encoding="utf-8") as fh:
        return cast(dict[str, str], json.load(fh))


class _HTMLEmailFormatter(logging.Formatter):
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

        Returns ``(before, highlight, after)`` where ``highlight`` is the
        ``File "<filename>", line <lineno>, in <func>`` line for that frame.
        Returns ``("", "", tb_str)`` if no match is found.
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
        """Render a log record as a complete HTML email body."""
        ctx = getattr(record, "task_context", None) or {}

        exception = ctx.get("exception", record.getMessage())
        tb_str = ctx.get("traceback_str", "")
        traced_vars = ctx.get("traced_vars", "")
        traced_vars_location = ctx.get("traced_vars_location", "")

        tb_before, tb_highlight, tb_after = self._split_traceback_at_target(
            tb_str, traced_vars_location
        )

        downstream = ctx.get("downstream_impact", []) or []
        downstream_items = "".join(
            f"<li>{html.escape(str(name), quote=True)}</li>" for name in downstream
        )

        substitutions = dict(_load_language_strings(self._email_language))
        substitutions["lang_traced_vars_blurb"] = substitutions.get(
            "lang_traced_vars_blurb", ""
        ).replace("{location}", traced_vars_location)
        substitutions.update(
            {
                "task_name": html.escape(str(ctx.get("task_name", "?")), quote=True),
                "function": html.escape(str(ctx.get("function", "?")), quote=True),
                "args": html.escape(repr(ctx.get("args", ())), quote=True),
                "kwargs": html.escape(repr(ctx.get("kwargs", {})), quote=True),
                "exception": html.escape(exception, quote=True),
                "traceback_before": html.escape(tb_before, quote=True),
                "traceback_highlight": html.escape(tb_highlight, quote=True),
                "traceback_after": html.escape(tb_after, quote=True),
                "traced_vars": traced_vars,
                "downstream_items": downstream_items,
            }
        )
        return self._render(self._get_template(), substitutions)


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

    def emit(self, record: logging.LogRecord) -> None:
        try:
            port = self.mailport
            if not port:
                port = smtplib.SMTP_PORT
            host = self.mailhost[0] if isinstance(self.mailhost, tuple) else self.mailhost
            smtp = smtplib.SMTP(host, port)
            msg = self.format(record)

            mime_msg = MIMEText(msg, "html")
            mime_msg["From"] = self.fromaddr
            mime_msg["To"] = ",".join(self.toaddrs)
            mime_msg["Subject"] = self.getSubject(record)
            mime_msg["Date"] = formatdate()

            if self.username:
                if self.secure is not None:
                    smtp.starttls(*self.secure)
                smtp.login(self.username, self.password)
            smtp.sendmail(self.fromaddr, self.toaddrs, mime_msg.as_string())
            smtp.quit()
        except Exception:
            self.handleError(record)


def _build_task_email_handler(
    smtp_config: SMTPConfig,
    style: HTMLEmailStyle,
    task_name: str,
) -> _HTMLEmailHandler:
    """Create a fully configured email handler bound to one task."""
    handler = _HTMLEmailHandler(smtp_config)
    handler.setFormatter(_HTMLEmailFormatter(style))
    handler.setLevel(logging.ERROR)
    lang_strings = _load_language_strings(style.language)
    handler.subject = f"{lang_strings['lang_email_subject']}{task_name}"
    return handler
