from __future__ import annotations

import hashlib
import hmac
import json
import logging
import urllib.request
from typing import Any

from ._error_data import _ErrorContextFormatter, _ErrorData
from .webhook_config import WebhookConfig

_SIGNATURE_HEADER = "X-Signature-SHA256"


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

    def _build_payload(self, error: _ErrorData) -> dict[str, Any]:
        """Build the JSON-serializable payload dict from ``_ErrorData``.

        Subclasses targeting a specific webhook service can override this
        to reshape the payload, while reusing ``format`` and the rest of
        the channel/handler machinery.

        Parameters
        ----------
        error : _ErrorData
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
            body = self.format(record).encode("utf-8")
            headers = {"Content-Type": "application/json", **self._config.headers}
            if self._config.secret is not None:
                digest = hmac.new(
                    self._config.secret.encode("utf-8"), body, hashlib.sha256
                ).hexdigest()
                headers[_SIGNATURE_HEADER] = digest

            request = urllib.request.Request(
                self._config.url, data=body, headers=headers, method="POST"
            )
            with urllib.request.urlopen(request, timeout=self._config.timeout):
                pass
        except Exception:
            self.handleError(record)


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
