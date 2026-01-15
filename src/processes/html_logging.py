from email.mime.text import MIMEText
from email.utils import formatdate
import logging
import logging.handlers
import smtplib
import traceback
import ssl


class HTMLSMTPHandler(logging.handlers.SMTPHandler):
    def __init__(self, mailhost: tuple[str, str], fromaddr: str, toaddrs: list[str],
                 credentials: tuple[str, str] | None = None,
                 secure: tuple | tuple[str, str] | tuple[str, str, ssl.SSLContext] | None = None,
                 timeout: int = 5):
        self._crd = credentials
        self._sec = secure
        self._to = timeout

        super().__init__(mailhost, fromaddr, toaddrs, '', credentials=credentials, secure=secure, timeout=timeout)

    def copy(self):
        return HTMLSMTPHandler(self.mailhost, self.fromaddr, self.toaddrs, credentials=self._crd, secure=self._sec, timeout=self._to)
    
    def __copy__(self):
        return self.copy()

    def emit(self, record):
        try:
            port = self.mailport
            if not port:
                port = smtplib.SMTP_PORT
            smtp = smtplib.SMTP(self.mailhost, port)
            msg = self.format(record)

            # Create MIMEText object with HTML content
            mime_msg = MIMEText(msg, 'html')
            mime_msg['From'] = self.fromaddr
            mime_msg['To'] = ','.join(self.toaddrs)
            mime_msg['Subject'] = self.getSubject(record)
            mime_msg['Date'] = formatdate()

            if self.username:
                if self.secure is not None:
                    smtp.starttls(*self.secure)
                smtp.login(self.username, self.password)
            smtp.sendmail(self.fromaddr, self.toaddrs, mime_msg.as_string())
            smtp.quit()
        except Exception:
            self.handleError(record)


class ExceptionHTMLFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        # Format the exception details and traceback
        if record.exc_info:
            exception = record.exc_info[1]
            tb_str = traceback.format_exc()
        else:
            exception = record.getMessage()
            tb_str = "No traceback available"

        post_traceback_html_body = getattr(record, 'post_traceback_html_body', "")

        # HTML content
        tb_str = tb_str.replace('\n', '<br>')
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
