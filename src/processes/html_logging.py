import html
import json
import logging
import logging.handlers
import os
import smtplib
import ssl
import traceback
from email.mime.text import MIMEText
from email.utils import formatdate
from typing import cast

_THEMES_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "themes")
_STYLES_DIR = os.path.join(_THEMES_DIR, "styles")
_PALETTES_DIR = os.path.join(_THEMES_DIR, "palettes")
_LANGUAGES_DIR = os.path.join(_THEMES_DIR, "languages")

_VALID_STYLES = frozenset({"classic", "modern", "compact"})
_VALID_PALETTES = frozenset({"neutral", "catppuccin", "neobones", "slate"})
_VALID_LANGUAGES = frozenset({"en", "es", "pt", "fr", "de", "it"})

_DEFAULT_STYLE = "modern"
_DEFAULT_PALETTE = "neutral"
_DEFAULT_LANGUAGE = "en"

_PALETTE_MARKER = "{{__palette_css__}}"


def _load_language_strings(language: str) -> dict[str, str]:
    """Load translatable strings for the given ISO 639-1 language code.

    Parameters
    ----------
    language : str
        One of the supported language codes (``"en"``, ``"es"``, ``"pt"``,
        ``"fr"``, ``"de"``, ``"it"``).

    Returns
    -------
    dict[str, str]
        Mapping from placeholder name (e.g. ``"lang_function_label"``) to
        the translated string.
    """
    path = os.path.join(_LANGUAGES_DIR, f"{language}.json")
    with open(path, encoding="utf-8") as fh:
        return cast(dict[str, str], json.load(fh))


class HTMLSMTPHandler(logging.handlers.SMTPHandler):
    """
    A logging handler that sends log records via SMTP as HTML formatted emails.

    Extends the standard SMTPHandler to support HTML-formatted email messages,
    enabling richer formatting and styling in error notifications.

    Attributes
    ----------
    mailhost : tuple[str, int]
        A tuple of (host, port) for the SMTP server.
    fromaddr : str
        The email address to send messages from.
    toaddrs : list[str]
        List of email addresses to send messages to.
    credentials : tuple[str, str] | None
        A tuple of (username, password) for SMTP authentication. Defaults to None.
    secure : tuple | tuple[str, str] | tuple[str, str, ssl.SSLContext] | None
        Security configuration for SMTP connection. Can be an empty tuple for no security,
        a tuple of (certfile, keyfile), or (certfile, keyfile, SSLContext).
        Defaults to None.
    timeout : int
        Connection timeout in seconds. Defaults to 5.
    """

    def __init__(
        self,
        mailhost: tuple[str, int],
        fromaddr: str,
        toaddrs: list[str],
        credentials: tuple[str, str] | None = None,
        secure: tuple[()]
        | tuple[str]
        | tuple[str, str]
        | tuple[str, str, ssl.SSLContext]
        | None = None,
        timeout: int = 5,
        *,
        email_style: str = _DEFAULT_STYLE,
        color_palette: str = _DEFAULT_PALETTE,
        email_language: str = _DEFAULT_LANGUAGE,
    ):
        if email_style not in _VALID_STYLES:
            raise ValueError(
                f"email_style must be one of {sorted(_VALID_STYLES)}, "
                f"got {email_style!r}"
            )
        if color_palette not in _VALID_PALETTES:
            raise ValueError(
                f"color_palette must be one of {sorted(_VALID_PALETTES)}, "
                f"got {color_palette!r}"
            )
        if email_language not in _VALID_LANGUAGES:
            raise ValueError(
                f"email_language must be one of {sorted(_VALID_LANGUAGES)}, "
                f"got {email_language!r}"
            )

        self._crd = credentials
        self._sec = secure
        self._to = timeout
        self.email_style = email_style
        self.color_palette = color_palette
        self.email_language = email_language

        super().__init__(
            mailhost,
            fromaddr,
            toaddrs,
            "",
            credentials=credentials,
            secure=secure,  # type: ignore[arg-type]
            timeout=timeout,
        )

    def copy(self) -> "HTMLSMTPHandler":
        """Create a shallow copy of this handler.

        Returns
        -------
        HTMLSMTPHandler
            A new HTMLSMTPHandler instance with the same configuration.
        """
        if self.mailport:
            mailhost = (self.mailhost, self.mailport)
        else:
            mailhost = self.mailhost
        return HTMLSMTPHandler(
            mailhost,
            self.fromaddr,
            self.toaddrs,
            credentials=self._crd,
            secure=self._sec,
            timeout=self._to,
            email_style=self.email_style,
            color_palette=self.color_palette,
            email_language=self.email_language,
        )

    def __copy__(self) -> "HTMLSMTPHandler":
        """Support for copy.copy() method.

        Returns
        -------
        HTMLSMTPHandler
            A shallow copy of this handler.
        """
        return self.copy()

    def emit(self, record: logging.LogRecord) -> None:
        """Send a log record via email as HTML formatted message.

        Formats the log record using the handler's formatter and sends it
        as an HTML-formatted email. Errors during sending are handled gracefully.

        Parameters
        ----------
        record : logging.LogRecord
            The log record to send.
        """
        try:
            port = self.mailport
            if not port:
                port = smtplib.SMTP_PORT
            # ``SMTPHandler`` stores ``self.mailhost`` as a ``(host, port)``
            # tuple; ``smtplib.SMTP`` requires a host string.  Unpack it
            # explicitly — passing the tuple raises
            # ``TypeError: getaddrinfo() argument 1 must be string or None``.
            host = (
                self.mailhost[0]
                if isinstance(self.mailhost, tuple)
                else self.mailhost
            )
            smtp = smtplib.SMTP(host, port)
            msg = self.format(record)

            # Create MIMEText object with HTML content
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


class ExceptionHTMLFormatter(logging.Formatter):
    """
    A logging formatter that converts exception records to HTML format.

    Renders a Jinja-like template by composing a bundled style layout from
    ``themes/styles/`` with a color palette from ``themes/palettes/``, using
    the pure metadata dict supplied via ``extra={"task_context": ...}`` on
    the originating log call.  This keeps the log payload framework-agnostic
    (no raw HTML fragments in ``extra``) while still producing a richly
    formatted HTML email body.

    Parameters
    ----------
    email_style : str
        Name of the bundled style layout (``"classic"``, ``"modern"`` or
        ``"compact"``).
    color_palette : str
        Name of the bundled color palette (``"neutral"``, ``"catppuccin"``,
        ``"neobones"`` or ``"slate"``) injected into the style at the
        ``{{__palette_css__}}`` marker.
    email_language : str
        ISO 639-1 language code for the email body and subject
        (``"en"``, ``"es"``, ``"pt"``, ``"fr"``, ``"de"``, ``"it"``).
    """

    def __init__(
        self,
        *,
        email_style: str = _DEFAULT_STYLE,
        color_palette: str = _DEFAULT_PALETTE,
        email_language: str = _DEFAULT_LANGUAGE,
    ) -> None:
        super().__init__()
        if email_style not in _VALID_STYLES:
            raise ValueError(
                f"email_style must be one of {sorted(_VALID_STYLES)}, "
                f"got {email_style!r}"
            )
        if color_palette not in _VALID_PALETTES:
            raise ValueError(
                f"color_palette must be one of {sorted(_VALID_PALETTES)}, "
                f"got {color_palette!r}"
            )
        if email_language not in _VALID_LANGUAGES:
            raise ValueError(
                f"email_language must be one of {sorted(_VALID_LANGUAGES)}, "
                f"got {email_language!r}"
            )
        self._email_style = email_style
        self._color_palette = color_palette
        self._email_language = email_language
        self._cached_template: str | None = None

    def _resolve_template(self) -> str:
        """Compose the bundled style + palette into a single template string."""
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

    def _format_exception_block(self, record: logging.LogRecord) -> tuple[str, str]:
        if record.exc_info:
            exc_type, exc_value, exc_tb = record.exc_info
            exception = "" if exc_value is None else str(exc_value)
            tb_str = "".join(
                traceback.format_exception(exc_type, exc_value, exc_tb)
            )
        else:
            exception = record.getMessage()
            tb_str = ""
        return exception, tb_str

    def _render(self, template: str, substitutions: dict[str, str]) -> str:
        rendered = template
        for key, value in substitutions.items():
            rendered = rendered.replace("{{" + key + "}}", value)
        return rendered

    def format(self, record: logging.LogRecord) -> str:
        exception, tb_str = self._format_exception_block(record)
        task_context = getattr(record, "task_context", None) or {}

        downstream = task_context.get("downstream_impact", []) or []
        downstream_items = "".join(
            f"<li>{html.escape(str(name), quote=True)}</li>" for name in downstream
        )

        substitutions = dict(_load_language_strings(self._email_language))
        substitutions.update(
            {
                "task_name": html.escape(str(task_context.get("task_name", "?")), quote=True),
                "function": html.escape(str(task_context.get("function", "?")), quote=True),
                "args": html.escape(repr(task_context.get("args", ())), quote=True),
                "kwargs": html.escape(repr(task_context.get("kwargs", {})), quote=True),
                "exception": html.escape(exception, quote=True),
                "traceback": html.escape(tb_str, quote=True),
                "downstream_items": downstream_items,
            }
        )
        return self._render(self._get_template(), substitutions)
