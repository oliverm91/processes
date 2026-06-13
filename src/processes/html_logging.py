import logging
import logging.handlers
import smtplib
import ssl
from email.mime.text import MIMEText
from email.utils import formatdate

_VALID_STYLES = frozenset({"classic", "modern", "compact"})
_VALID_PALETTES = frozenset({"neutral", "catppuccin", "neobones", "slate"})
_VALID_LANGUAGES = frozenset({"en", "es", "pt", "fr", "de", "it"})

_DEFAULT_STYLE = "modern"
_DEFAULT_PALETTE = "neutral"
_DEFAULT_LANGUAGE = "en"


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
                f"email_style must be one of {sorted(_VALID_STYLES)}, got {email_style!r}"
            )
        if color_palette not in _VALID_PALETTES:
            raise ValueError(
                f"color_palette must be one of {sorted(_VALID_PALETTES)}, got {color_palette!r}"
            )
        if email_language not in _VALID_LANGUAGES:
            raise ValueError(
                f"email_language must be one of {sorted(_VALID_LANGUAGES)}, got {email_language!r}"
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
            mailhost = self.mailhost  # type: ignore[assignment]
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
            host = self.mailhost[0] if isinstance(self.mailhost, tuple) else self.mailhost
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
