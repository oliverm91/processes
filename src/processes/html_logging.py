import logging
import logging.handlers
import smtplib
import ssl
import traceback
from email.mime.text import MIMEText
from email.utils import formatdate


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
        return HTMLSMTPHandler(
            self.mailhost,  # type: ignore[arg-type]
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
            smtp = smtplib.SMTP(self.mailhost, port)
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

    Formats exception tracebacks with syntax-highlighted HTML styling and
    supports custom post-traceback content. Provides visually appealing
    exception reports suitable for email delivery.
    """

    def format(self, record: logging.LogRecord) -> str:
        """Format a log record as HTML, with special handling for exceptions.

        Extracts exception information and traceback, formats them with HTML
        styling, and includes any additional post-traceback content from the
        log record's `post_traceback_html_body` attribute.

        Parameters
        ----------
        record : logging.LogRecord
            The log record to format.

        Returns
        -------
        str
            HTML-formatted string containing exception details, traceback,
            and styling.
        """
        # Format the exception details and traceback
        if record.exc_info:
            exception_object = record.exc_info[1]
            exception = str(exception_object)
            tb_str = traceback.format_exc()
        else:
            exception = record.getMessage()
            tb_str = "No traceback available"

        post_traceback_html_body = getattr(record, "post_traceback_html_body", "")

        # HTML content
        tb_str = tb_str.replace("\n", "<br>")
        body = f"""
        <html>
        <head>
            <style>
                body {{
                    font-family: Arial, sans-serif;
                    margin: 20px;
                    color: #333;
                }}
                h2 {{
                    color: #d9534f;
                }}
                .exception {{
                    font-weight: bold;
                    color: #d9534f;
                }}
                .traceback {{
                    background-color: #f9f2f4;
                    border: 1px solid #d9534f;
                    padding: 10px;
                    font-family: 'Courier New', Courier, monospace;
                    white-space: pre-wrap;
                    color: #333;
                    border-radius: 4px;
                }}
            </style>
        </head>
        <body>
            <h2>Exception Details</h2>
            <p class="exception">Exception: {exception}</p>
            <p><strong>Traceback:</strong></p>
            <div class="traceback">{tb_str}</div>
            <br>
            {post_traceback_html_body}
        </body>
        </html>
        """
        return body
