from dataclasses import dataclass, field
from email.mime.text import MIMEText
from email.utils import formatdate
import logging
from logging.handlers import SMTPHandler

import smtplib
import traceback
from typing import Any, Callable, Optional


class HTMLSMTPHandler(SMTPHandler):
    def __init__(self, mailhost: tuple[str, str], fromaddr: str, toaddrs: list[str], subject: str, credencials: tuple[str, str] = None, secure: tuple[()] | tuple [str] |tuple[str, str] = None, timeout: int = 5):
        super().__init__(mailhost, fromaddr, toaddrs, subject, credentials=credencials, secure=secure, timeout=timeout)
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


class ExceptionHtmlFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord):
        # Format the exception details and traceback
        if record.exc_info:
            exception = record.exc_info[1]
            tb_str = traceback.format_exc()
        else:
            exception = record.getMessage()
            tb_str = "No traceback available"

        post_traceback_html_body = getattr(record, 'post_traceback_html_body', "")

        # HTML content
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


@dataclass(slots=True)
class TaskResult:
    worked: bool
    result: Any
    exception: Optional[Exception]


@dataclass(slots=True)
class TaskDependency:
    task_name: str
    use_result_as_additional_args: bool = field(default=False, repr=False)
    use_result_as_additional_kwargs: bool = field(default=False, repr=False)
    additional_kwarg_name: Optional[str] = field(default=None, repr=False)

    def __post_init__(self):
        if not isinstance(self.task_name, str):
            raise TypeError(f"task_name must be of type str. Got {type(self.task_name)}")
        if not isinstance(self.use_result_as_additional_args, bool):
            raise TypeError(f"use_result_as_additional_args must be of type bool. Got {type(self.use_result_as_additional_args)}")
        if not isinstance(self.use_result_as_additional_kwargs, bool):
            raise TypeError(f"use_result_as_additional_kwargs must be of type bool. Got {type(self.use_result_as_additional_kwargs)}")

        if self.use_result_as_additional_kwargs and not isinstance(self.additional_kwarg_name, str):
            raise TypeError(f"If use_result_as_additional_kwargs is True, additional_kwarg_name must be set of type str. Got {type(self.additional_kwarg_name)}")
        
        
    def __hash__(self) -> int:
        return hash(self.task_name)


@dataclass(slots=True)
class Task:
    name: str
    log_file: str
    func: Callable
    args: tuple = field(default_factory=tuple)
    kwargs: dict = field(default_factory=dict)

    dependencies: list[TaskDependency] = field(default_factory=list)
    
    html_mail_handler: HTMLSMTPHandler = field(default=None, repr=False)
    logger: logging.Logger = field(init=False, repr=False)

    def __post_init__(self):
        self._check_input_types()

        depedencies_names = []
        for dependency in self.dependencies:
            if dependency.task_name in depedencies_names:
                raise ValueError(f"Duplicate dependency name: {dependency.task_name}")
            depedencies_names.append(dependency.task_name)
            if dependency.task_name == self.name:
                raise ValueError(f"Got dependency with same name as Task. Task: {self.name}. Dependency: {dependency.task_name}")

        logger = logging.getLogger(self.name)
        logger.setLevel(logging.DEBUG)
        if logger.hasHandlers():
            logger.handlers.clear()
        
        file_handler = logging.FileHandler(self.log_file)
        file_handler.setLevel(logging.INFO)
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
        
        if self.html_mail_handler is not None:
            self.html_mail_handler.setFormatter(ExceptionHtmlFormatter())
            self.html_mail_handler.setLevel(logging.ERROR)
            self.html_mail_handler.subject = f"Error in task {self.name}"        
            logger.addHandler(self.html_mail_handler)

        self.logger = logger

    def _check_input_types(self):
        if not callable(self.func):
            raise TypeError(f"func must be callable. Got {type(self.func)}")
        
        if not isinstance(self.args, tuple):
            raise TypeError(f"args must be tuple. Got {type(self.args)}")
        
        if not isinstance(self.kwargs, dict):
            raise TypeError(f"kwargs must be dict. Got {type(self.kwargs)}")
        
        if self.html_mail_handler is not None and not isinstance(self.html_mail_handler, HTMLSMTPHandler):
            raise TypeError(f"mail_cfg must be of type SMTPHandler (easy_smtp library). Got {type(self.html_mail_handler)}")
        
        if not isinstance(self.dependencies, list):
            raise TypeError(f"dependencies must be list. Got {type(self.dependencies)}")
        
        for dependency in self.dependencies:
            if not isinstance(dependency, TaskDependency):
                raise TypeError(f"dependency must be of type TaskDependency. Got {type(dependency)}")            

    def get_dependencies_names(self) -> set[str]:
        return {dependency.task_name for dependency in self.dependencies}
    
    def add_args(self, *args):
        self.args += args

    def add_kwargs(self, **kwargs):
        self.kwargs = {**self.kwargs, **kwargs}

    def run(self, aditional_args: Optional[tuple[Any]] = None, aditional_kwargs: Optional[dict[str, Any]] = None, post_traceback_html_body: Optional[str] = None) -> TaskResult:
        try:
            if aditional_args:
                self.add_args(*aditional_args)
            if aditional_kwargs:
                self.add_kwargs(**aditional_kwargs)
            self.logger.info(f"Starting {self.name}.")
            result = self.func(*self.args, **self.kwargs)
            self.logger.info(f"Finished {self.name}.")
            return TaskResult(True, result, None)
        except Exception as e:
            if post_traceback_html_body is None:
                post_traceback_html_body = ""
            post_traceback_html_body += f"<br><p>Function was: {self.func.__name__}. Args were: {self.args}. Kwargs were: {self.kwargs}.</p>"
            self.logger.exception(e, extra={"post_traceback_html_body": post_traceback_html_body})
            return TaskResult(False, None, e)
