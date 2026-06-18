from __future__ import annotations

import hashlib
import hmac
import json
import logging
import urllib.request
from typing import TYPE_CHECKING, Any

from ._error_data import ErrorData, _ErrorContextFormatter
from .task_types import TaskStatus
from .webhook_config import WebhookConfig

if TYPE_CHECKING:
    from .execution_report import ProcessExecutionReport, TaskReportEntry
    from .notification_channels import ReportContent

_SIGNATURE_HEADER = "X-Signature-SHA256"


def _post_json(config: WebhookConfig, payload: str) -> None:
    """Sign and POST a JSON string to ``config.url``.

    Parameters
    ----------
    config : WebhookConfig
        Transport configuration (URL, headers, timeout, optional HMAC secret).
    payload : str
        JSON string to POST as the request body.
    """
    body = payload.encode("utf-8")
    headers = {"Content-Type": "application/json", **config.headers}
    if config.secret is not None:
        digest = hmac.new(
            config.secret.encode("utf-8"), body, hashlib.sha256
        ).hexdigest()
        headers[_SIGNATURE_HEADER] = digest
    request = urllib.request.Request(config.url, data=body, headers=headers, method="POST")
    with urllib.request.urlopen(request, timeout=config.timeout):
        pass


class _WebhookFormatter(_ErrorContextFormatter):
    """Pure renderer: builds a generic JSON payload from ``record.task_context``."""

    def __init__(
        self, extra_payload: dict[str, Any] | None = None, nest_under: str | None = None
    ) -> None:
        super().__init__()
        self._extra_payload = extra_payload or {}
        self._nest_under = nest_under or None

    def format(self, record: logging.LogRecord) -> str:
        """Render a log record as a JSON payload string.

        Parameters
        ----------
        record : logging.LogRecord
            The record being formatted.

        Returns
        -------
        str
            A JSON-encoded object describing the task failure, merged with
            any configured ``extra_payload`` keys (which take precedence on
            collision). If ``nest_under`` is set, the failure fields are
            nested under that key instead of being top-level.
        """
        error = self._error_data(record)
        generic_payload = self._build_payload(error)
        if self._nest_under is not None:
            generic_payload = {self._nest_under: generic_payload}
        payload = {**generic_payload, **self._extra_payload}
        return json.dumps(payload)

    def _build_payload(self, error: ErrorData) -> dict[str, Any]:
        """Build the JSON-serializable payload dict from ``ErrorData``.

        Subclasses targeting a specific webhook service can override this
        to reshape the payload, while reusing ``format`` and the rest of
        the channel/handler machinery.

        Parameters
        ----------
        error : ErrorData
            Typed failure context for the record being formatted.

        Returns
        -------
        dict[str, Any]
            JSON-serializable payload.
        """
        return {
            "task_name": error.task_name,
            "function": error.function,
            "args": repr(error.args),
            "kwargs": repr(error.kwargs),
            "exception": error.exception,
            "traceback": error.traceback_str,
            "downstream_impact": list(error.downstream_impact),
            "traced_vars": error.traced_vars,
            "traced_vars_location": error.traced_vars_location,
        }


class _WebhookHandler(logging.Handler):
    """Internal handler that POSTs formatted log records as JSON."""

    def __init__(self, config: WebhookConfig) -> None:
        super().__init__()
        self._config = config

    def emit(self, record: logging.LogRecord) -> None:
        try:
            _post_json(self._config, self.format(record))
        except Exception:
            self.handleError(record)


def _build_report_webhook_payload(
    entries: dict[str, TaskReportEntry],
    content: ReportContent,
    config: WebhookConfig,
) -> dict[str, Any]:
    """Build the JSON-serializable payload dict for a report POST.

    Parameters
    ----------
    entries : dict[str, TaskReportEntry]
        Filtered task entries (all or errored-only, caller decides).
    content : ReportContent
        Content selection flags (``show_traceback``, ``show_traced_vars``).
    config : WebhookConfig
        Transport config used for ``nest_under`` and ``extra_payload``.

    Returns
    -------
    dict[str, Any]
        Ready-to-serialize payload with ``nest_under`` and ``extra_payload``
        already applied.
    """
    tasks_payload: dict[str, Any] = {}
    for name, entry in entries.items():
        task_dict: dict[str, Any] = {
            "status": entry.status.value,
            "function": entry.function,
            "elapsed_seconds": entry.elapsed_seconds,
            "attempts": entry.attempts,
        }
        if entry.status == TaskStatus.SUCCESS:
            task_dict["result"] = repr(entry.result)
        if entry.error is not None:
            error_dict: dict[str, Any] = {
                "exception": entry.error.exception,
                "downstream_impact": list(entry.error.downstream_impact),
            }
            if content.show_traceback:
                error_dict["traceback"] = entry.error.traceback_str
            if content.show_traced_vars and entry.error.traced_vars:
                error_dict["traced_vars"] = entry.error.traced_vars
                error_dict["traced_vars_location"] = entry.error.traced_vars_location
            task_dict["error"] = error_dict
        tasks_payload[name] = task_dict

    generic: dict[str, Any] = {"entries": tasks_payload}
    if config.nest_under:
        generic = {config.nest_under: generic}
    return {**generic, **config.extra_payload}


def send_report_webhook(
    report: ProcessExecutionReport,
    config: WebhookConfig,
    content: ReportContent,
    *,
    errors_only: bool,
) -> None:
    """POST a finished ``ProcessExecutionReport`` to ``config.url`` as JSON.

    Parameters
    ----------
    report : ProcessExecutionReport
        The finished report to deliver.
    config : WebhookConfig
        Transport configuration (URL, headers, timeout, HMAC secret,
        ``extra_payload``, ``nest_under``).
    content : ReportContent
        Content selection: ``show_traceback`` / ``show_traced_vars``.
    errors_only : bool
        When ``True`` only ``ERRORED`` entries are included in the payload.
    """
    entries = report.errored if errors_only else report.entries
    payload = _build_report_webhook_payload(entries, content, config)
    _post_json(config, json.dumps(payload))


def _build_task_webhook_handler(config: WebhookConfig) -> _WebhookHandler:
    """Create a fully configured webhook handler.

    Parameters
    ----------
    config : WebhookConfig
        Webhook transport configuration for the handler.

    Returns
    -------
    _WebhookHandler
        A handler at ``logging.ERROR`` level with a ``_WebhookFormatter``.
    """
    handler = _WebhookHandler(config)
    handler.setFormatter(
        _WebhookFormatter(extra_payload=config.extra_payload, nest_under=config.nest_under)
    )
    handler.setLevel(logging.ERROR)
    return handler
