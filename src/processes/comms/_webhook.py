from __future__ import annotations

import hashlib
import hmac
import json
import urllib.request
from typing import TYPE_CHECKING, Any

from ..task_types import TaskStatus
from .webhook_config import WebhookConfig

if TYPE_CHECKING:
    from ..execution_report import ProcessExecutionReport, TaskReportEntry
    from .base import ReportContent

_SIGNATURE_HEADER = "X-Signature-SHA256"


class _WebhookTransport:
    """Signs and POSTs a JSON string to the configured webhook URL.

    The single place that owns the HTTP conversation (HMAC-SHA256 signing,
    headers, POST); ``send_report_webhook`` delegates here.
    """

    def __init__(self, config: WebhookConfig) -> None:
        self._config = config

    def post(self, payload: str) -> None:
        """Sign (if a secret is set) and POST ``payload`` as the request body.

        Parameters
        ----------
        payload : str
            JSON string to POST as the request body.
        """
        config = self._config
        body = payload.encode("utf-8")
        headers = {"Content-Type": "application/json", **config.headers}
        if config.secret is not None:
            digest = hmac.new(config.secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
            headers[_SIGNATURE_HEADER] = digest
        request = urllib.request.Request(config.url, data=body, headers=headers, method="POST")
        with urllib.request.urlopen(request, timeout=config.timeout):
            pass


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
    _WebhookTransport(config).post(json.dumps(payload))
