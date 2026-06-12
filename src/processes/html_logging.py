import html
import logging
import logging.handlers
import os
import smtplib
import ssl
import traceback
from email.mime.text import MIMEText
from email.utils import formatdate

_DEFAULT_TEMPLATE_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "error_template.html"
)

_FALLBACK_TEMPLATE = """<!DOCTYPE html>
<html><body>
<h1>Pipeline Failure: {{task_name}}</h1>
<p><b>Function:</b> {{function}}</p>
<p><b>Args:</b> {{args}}</p>
<p><b>Kwargs:</b> {{kwargs}}</p>
<p><b>Exception:</b> {{exception}}</p>
<h2>Downstream Impact</h2>
<ul>{{downstream_items}}</ul>
<pre>{{traceback}}</pre>
</body></html>"""

_ENV_VAR_NAME = "PROCESSES_ERROR_TEMPLATE"


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
    ):
        self._crd = credentials
        self._sec = secure
        self._to = timeout

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

    Renders a Jinja-like ``error_template.html`` (resolved from the explicit
    ``template_path`` argument, the ``PROCESSES_ERROR_TEMPLATE`` environment
    variable, the bundled default, or an inline fallback) using the pure
    metadata dict supplied via ``extra={"task_context": ...}`` on the
    originating log call. This keeps the log payload framework-agnostic
    (no raw HTML fragments in ``extra``) while still producing a richly
    formatted HTML email body.
    """

    def __init__(self, template_path: str | None = None) -> None:
        super().__init__()
        self._explicit_template_path = template_path
        self._cached_template: str | None = None

    def _resolve_template(self) -> str:
        """Locate the template source: explicit, env var, default, fallback."""
        candidates: list[str] = []
        if self._explicit_template_path:
            candidates.append(self._explicit_template_path)
        env_path = os.environ.get(_ENV_VAR_NAME)
        if env_path:
            candidates.append(env_path)
        candidates.append(_DEFAULT_TEMPLATE_PATH)

        for path in candidates:
            try:
                with open(path, encoding="utf-8") as fh:
                    return fh.read()
            except (OSError, TypeError):
                continue
        return _FALLBACK_TEMPLATE

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

        substitutions = {
            "task_name": html.escape(str(task_context.get("task_name", "?")), quote=True),
            "function": html.escape(str(task_context.get("function", "?")), quote=True),
            "args": html.escape(repr(task_context.get("args", ())), quote=True),
            "kwargs": html.escape(repr(task_context.get("kwargs", {})), quote=True),
            "exception": html.escape(exception, quote=True),
            "traceback": html.escape(tb_str, quote=True),
            "downstream_items": downstream_items,
        }
        return self._render(self._get_template(), substitutions)
