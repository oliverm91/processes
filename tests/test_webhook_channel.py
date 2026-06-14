"""Tests for the generic ``WebhookChannel`` handler/formatter internals.

Covers:

*   ``_WebhookFormatter.format`` renders the canonical ``task_context``
    payload as JSON with the expected keys.
*   ``_WebhookHandler.emit`` POSTs the JSON body to the configured URL with
    the right method, headers, and timeout.
*   Optional HMAC-SHA256 body signing via ``WebhookConfig.secret``.
*   Errors during emission are routed through ``handleError`` instead of
    propagating.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
from unittest.mock import MagicMock, patch

from processes import WebhookChannel, WebhookConfig
from processes._webhook_internals import _build_task_webhook_handler, _WebhookFormatter

from .base_test import BaseTest


def _make_record(task_name: str = "demo_task") -> logging.LogRecord:
    """Build a LogRecord carrying the canonical task_context payload."""
    record = logging.LogRecord(
        name=task_name,
        level=logging.ERROR,
        pathname=__file__,
        lineno=1,
        msg="planned failure in %s",
        args=(task_name,),
        exc_info=None,
    )
    record.task_context = {
        "task_name": task_name,
        "function": "func_demo",
        "args": ("a", 1),
        "kwargs": {"flag": True},
        "downstream_impact": ["child_a", "child_b"],
        "exception": "RuntimeError('boom')",
        "traceback_str": "Traceback (most recent call last):\n...\nRuntimeError: boom\n",
        "traced_vars": {"a": "'a'", "flag": "True"},
        "traced_vars_location": "demo.py:42",
    }
    return record


class TestWebhookFormatter(BaseTest):
    def test_format_renders_expected_payload_keys(self) -> None:
        formatter = _WebhookFormatter()
        payload = json.loads(formatter.format(_make_record()))

        assert payload == {
            "task_name": "demo_task",
            "function": "func_demo",
            "args": "('a', 1)",
            "kwargs": "{'flag': True}",
            "exception": "RuntimeError('boom')",
            "traceback": "Traceback (most recent call last):\n...\nRuntimeError: boom\n",
            "downstream_impact": ["child_a", "child_b"],
            "traced_vars": {"a": "'a'", "flag": "True"},
            "traced_vars_location": "demo.py:42",
        }


class TestWebhookHandlerEmit(BaseTest):
    def _config(self, **overrides: object) -> WebhookConfig:
        defaults: dict[str, object] = {"url": "https://example.test/hook"}
        defaults.update(overrides)
        return WebhookConfig(**defaults)  # type: ignore[arg-type]

    def test_emit_posts_json_payload(self) -> None:
        handler = _build_task_webhook_handler(self._config())

        with patch("processes._webhook_internals.urllib.request.urlopen") as mock_urlopen:
            mock_urlopen.return_value = MagicMock()
            handler.emit(_make_record())

        assert mock_urlopen.call_count == 1
        request = mock_urlopen.call_args.args[0]
        assert request.full_url == "https://example.test/hook"
        assert request.get_method() == "POST"
        assert json.loads(request.data)["task_name"] == "demo_task"
        assert mock_urlopen.call_args.kwargs["timeout"] == 5

    def test_default_content_type_header(self) -> None:
        handler = _build_task_webhook_handler(self._config())

        with patch("processes._webhook_internals.urllib.request.urlopen") as mock_urlopen:
            mock_urlopen.return_value = MagicMock()
            handler.emit(_make_record())

        request = mock_urlopen.call_args.args[0]
        assert request.get_header("Content-type") == "application/json"

    def test_custom_headers_merge_with_default_content_type(self) -> None:
        config = self._config(headers={"Authorization": "Bearer token123"}, timeout=10)
        handler = _build_task_webhook_handler(config)

        with patch("processes._webhook_internals.urllib.request.urlopen") as mock_urlopen:
            mock_urlopen.return_value = MagicMock()
            handler.emit(_make_record())

        request = mock_urlopen.call_args.args[0]
        assert request.get_header("Content-type") == "application/json"
        assert request.get_header("Authorization") == "Bearer token123"
        assert mock_urlopen.call_args.kwargs["timeout"] == 10

    def test_hmac_signature_added_when_secret_set(self) -> None:
        config = self._config(secret="shh")
        handler = _build_task_webhook_handler(config)

        with patch("processes._webhook_internals.urllib.request.urlopen") as mock_urlopen:
            mock_urlopen.return_value = MagicMock()
            handler.emit(_make_record())

        request = mock_urlopen.call_args.args[0]
        expected = hmac.new(b"shh", request.data, hashlib.sha256).hexdigest()
        assert request.get_header("X-signature-sha256") == expected

    def test_no_signature_header_when_secret_none(self) -> None:
        handler = _build_task_webhook_handler(self._config())

        with patch("processes._webhook_internals.urllib.request.urlopen") as mock_urlopen:
            mock_urlopen.return_value = MagicMock()
            handler.emit(_make_record())

        request = mock_urlopen.call_args.args[0]
        assert request.get_header("X-signature-sha256") is None

    def test_emit_routes_request_errors_through_handle_error(self) -> None:
        handler = _build_task_webhook_handler(self._config())

        with patch("processes._webhook_internals.urllib.request.urlopen") as mock_urlopen:
            mock_urlopen.side_effect = OSError("connection refused")
            with patch.object(handler, "handleError") as mock_handle_error:
                handler.emit(_make_record())

        mock_handle_error.assert_called_once()


class TestWebhookChannelHandlerWiring(BaseTest):
    def test_channel_builds_handler_using_webhook_internals(self) -> None:
        channel = WebhookChannel(WebhookConfig(url="https://example.test/hook"))
        handler = channel.build_handler("webhook_task")

        with patch("processes._webhook_internals.urllib.request.urlopen") as mock_urlopen:
            mock_urlopen.return_value = MagicMock()
            handler.emit(_make_record("webhook_task"))

        assert mock_urlopen.call_count == 1
