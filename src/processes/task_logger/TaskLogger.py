from dataclasses import dataclass, field
import logging
from typing import Optional

from easy_smtp import SMTPHandler


class NotInExceptBlockError(Exception):
    """Exception raised when log_error is called outside of an except block."""
    def __init__(self, message="log_error should only be called within an except block."):
        super().__init__(message)


@dataclass(slots=True)
class TaskLogger:
    task_name: str
    logger: logging.Logger

    mail_handler: Optional[SMTPHandler] = field(default=None)

    def __post_init__(self):
        if not isinstance(self.logger, logging.Logger):
            raise TypeError(f"logger must be of type logging.Logger. Got {type(self.logger)}")
            
        if self.mail_handler is not None:
            if not isinstance(self.mail_handler, SMTPHandler):
                raise TypeError(f"mail_config must be of type SMTPHandler (easy_smtp library). Got {type(self.mail_handler)}")
            
    def log_message(self, message: str):
        self.logger.info(message)

    def log_error(self, exception: Exception, post_traceback_html_body: Optional[str] = None):
        self.logger.exception(exception)
        if self.mail_handler is not None:
            self.mail_handler.send_exception_email(exception, f"Error in task {self.task_name}", post_traceback_html_body=post_traceback_html_body)