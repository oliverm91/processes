"""Integration tests for WebhookChannel.send_report and EmailChannel.send_report."""

from __future__ import annotations

import email as _email_module
import json
from unittest.mock import MagicMock, patch

from processes import (
    EmailChannel,
    HTMLEmailStyle,
    ProcessExecutionReport,
    ReportContent,
    SMTPConfig,
    TaskReportEntry,
    TaskStatus,
    WebhookChannel,
    WebhookConfig,
)
from processes.comms._email import _build_report_html
from processes.error_data import ErrorData

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _entry(
    name: str,
    status: TaskStatus,
    *,
    error: ErrorData | None = None,
    elapsed: float = 0.1,
    attempts: int = 1,
) -> TaskReportEntry:
    return TaskReportEntry(
        name=name,
        function=f"fn_{name}",
        args=(),
        kwargs={},
        status=status,
        elapsed_seconds=elapsed,
        attempts=attempts,
        result="ok" if status == TaskStatus.SUCCESS else None,
        error=error,
    )


def _error(
    exception: str = "ValueError: bad",
    traceback_str: str = "Traceback ...\n  File x.py line 1\nValueError: bad",
    traced_vars: dict[str, str] | None = None,
    downstream: list[str] | None = None,
) -> ErrorData:
    return ErrorData(
        task_name="t",
        function="fn_t",
        exception=exception,
        traceback_str=traceback_str,
        traced_vars=traced_vars or {"x": "1"},
        traced_vars_location="x.py:1",
        downstream_impact=downstream or [],
    )


def _report(*entries: TaskReportEntry) -> ProcessExecutionReport:
    return ProcessExecutionReport({e.name: e for e in entries})


def _smtp() -> SMTPConfig:
    return SMTPConfig(mailhost=("localhost", 25), fromaddr="a@b.com", toaddrs=["c@d.com"])


def _decode_mime_body(mime_string: str) -> str:
    """Parse a MIME message string and return the decoded text body."""
    msg = _email_module.message_from_string(mime_string)
    payload = msg.get_payload(decode=True)
    if isinstance(payload, bytes):
        return payload.decode("utf-8", errors="replace")
    return str(payload or "")


# ---------------------------------------------------------------------------
# Webhook tests
# ---------------------------------------------------------------------------

class TestWebhookSendReport:

    @patch("urllib.request.urlopen")
    def test_posts_json_with_all_entries(self, mock_urlopen: MagicMock) -> None:
        mock_urlopen.return_value.__enter__ = lambda s: s
        mock_urlopen.return_value.__exit__ = MagicMock(return_value=False)

        report = _report(
            _entry("a", TaskStatus.SUCCESS),
            _entry("b", TaskStatus.ERRORED, error=_error()),
        )
        WebhookChannel(WebhookConfig(url="http://hook")).send_report(report, errors_only=False)

        assert mock_urlopen.called
        request = mock_urlopen.call_args[0][0]
        payload = json.loads(request.data.decode())
        assert set(payload["entries"].keys()) == {"a", "b"}
        assert payload["entries"]["a"]["status"] == TaskStatus.SUCCESS.value
        assert payload["entries"]["b"]["status"] == TaskStatus.ERRORED.value

    @patch("urllib.request.urlopen")
    def test_errors_only_filters_to_errored(self, mock_urlopen: MagicMock) -> None:
        mock_urlopen.return_value.__enter__ = lambda s: s
        mock_urlopen.return_value.__exit__ = MagicMock(return_value=False)

        report = _report(
            _entry("a", TaskStatus.SUCCESS),
            _entry("b", TaskStatus.ERRORED, error=_error()),
            _entry("c", TaskStatus.SKIPPED),
        )
        WebhookChannel(WebhookConfig(url="http://hook")).send_report(report, errors_only=True)

        request = mock_urlopen.call_args[0][0]
        payload = json.loads(request.data.decode())
        assert list(payload["entries"].keys()) == ["b"]

    @patch("urllib.request.urlopen")
    def test_content_show_traceback_false_omits_traceback(self, mock_urlopen: MagicMock) -> None:
        mock_urlopen.return_value.__enter__ = lambda s: s
        mock_urlopen.return_value.__exit__ = MagicMock(return_value=False)

        report = _report(_entry("b", TaskStatus.ERRORED, error=_error()))
        WebhookChannel(
            WebhookConfig(url="http://hook"),
            content=ReportContent(show_traceback=False, show_traced_vars=True),
        ).send_report(report, errors_only=False)

        request = mock_urlopen.call_args[0][0]
        payload = json.loads(request.data.decode())
        error_dict = payload["entries"]["b"]["error"]
        assert "traceback" not in error_dict
        assert "traced_vars" in error_dict

    @patch("urllib.request.urlopen")
    def test_content_show_traced_vars_false_omits_vars(self, mock_urlopen: MagicMock) -> None:
        mock_urlopen.return_value.__enter__ = lambda s: s
        mock_urlopen.return_value.__exit__ = MagicMock(return_value=False)

        report = _report(_entry("b", TaskStatus.ERRORED, error=_error()))
        WebhookChannel(
            WebhookConfig(url="http://hook"),
            content=ReportContent(show_traceback=True, show_traced_vars=False),
        ).send_report(report, errors_only=False)

        request = mock_urlopen.call_args[0][0]
        payload = json.loads(request.data.decode())
        error_dict = payload["entries"]["b"]["error"]
        assert "traceback" in error_dict
        assert "traced_vars" not in error_dict

    @patch("urllib.request.urlopen")
    def test_nest_under_wraps_entries(self, mock_urlopen: MagicMock) -> None:
        mock_urlopen.return_value.__enter__ = lambda s: s
        mock_urlopen.return_value.__exit__ = MagicMock(return_value=False)

        report = _report(_entry("a", TaskStatus.SUCCESS))
        WebhookChannel(WebhookConfig(url="http://hook", nest_under="data")).send_report(
            report, errors_only=False
        )

        request = mock_urlopen.call_args[0][0]
        payload = json.loads(request.data.decode())
        assert "data" in payload
        assert "entries" in payload["data"]

    @patch("urllib.request.urlopen")
    def test_extra_payload_merged_top_level(self, mock_urlopen: MagicMock) -> None:
        mock_urlopen.return_value.__enter__ = lambda s: s
        mock_urlopen.return_value.__exit__ = MagicMock(return_value=False)

        report = _report(_entry("a", TaskStatus.SUCCESS))
        WebhookChannel(
            WebhookConfig(url="http://hook", extra_payload={"chat_id": "123"})
        ).send_report(report, errors_only=False)

        request = mock_urlopen.call_args[0][0]
        payload = json.loads(request.data.decode())
        assert payload["chat_id"] == "123"
        assert "entries" in payload

    @patch("urllib.request.urlopen")
    def test_hmac_signature_header_set(self, mock_urlopen: MagicMock) -> None:
        mock_urlopen.return_value.__enter__ = lambda s: s
        mock_urlopen.return_value.__exit__ = MagicMock(return_value=False)

        report = _report(_entry("a", TaskStatus.SUCCESS))
        WebhookChannel(WebhookConfig(url="http://hook", secret="s3cr3t")).send_report(
            report, errors_only=False
        )

        request = mock_urlopen.call_args[0][0]
        # urllib.request.Request lowercases header names
        header_names_lower = {k.lower() for k in request.headers}
        assert "x-signature-sha256" in header_names_lower


# ---------------------------------------------------------------------------
# Report HTML renderer tests (pure, no I/O mocks needed)
# ---------------------------------------------------------------------------

class TestBuildReportHtml:
    def _style(self) -> HTMLEmailStyle:
        return HTMLEmailStyle()

    def test_contains_task_name(self) -> None:
        report = _report(_entry("my_unique_task", TaskStatus.ERRORED, error=_error()))
        html = _build_report_html(report, self._style(), ReportContent(), errors_only=False)
        assert "my_unique_task" in html

    def test_traceback_present_when_enabled(self) -> None:
        report = _report(
            _entry("b", TaskStatus.ERRORED, error=_error(traceback_str="UNIQUE_TRACE_TEXT"))
        )
        html = _build_report_html(
            report, self._style(), ReportContent(show_traceback=True), errors_only=False
        )
        assert "UNIQUE_TRACE_TEXT" in html

    def test_traceback_absent_when_disabled(self) -> None:
        report = _report(
            _entry("b", TaskStatus.ERRORED, error=_error(traceback_str="UNIQUE_TRACE_TEXT"))
        )
        html = _build_report_html(
            report, self._style(), ReportContent(show_traceback=False), errors_only=False
        )
        assert "UNIQUE_TRACE_TEXT" not in html

    def test_traced_vars_absent_when_disabled(self) -> None:
        report = _report(
            _entry("b", TaskStatus.ERRORED, error=_error(traced_vars={"UNIQUE_VAR": "42"}))
        )
        html = _build_report_html(
            report, self._style(), ReportContent(show_traced_vars=False), errors_only=False
        )
        assert "UNIQUE_VAR" not in html

    def test_errors_only_excludes_success(self) -> None:
        report = _report(
            _entry("ok", TaskStatus.SUCCESS),
            _entry("bad", TaskStatus.ERRORED, error=_error()),
        )
        html = _build_report_html(report, self._style(), ReportContent(), errors_only=True)
        assert "bad" in html
        assert "ok" not in html

    def test_summary_counts_appear(self) -> None:
        report = _report(
            _entry("a", TaskStatus.SUCCESS),
            _entry("b", TaskStatus.ERRORED, error=_error()),
            _entry("c", TaskStatus.SKIPPED),
        )
        html = _build_report_html(report, self._style(), ReportContent(), errors_only=False)
        assert ">1<" in html  # each count cell shows "1"

    def test_palette_css_injected(self) -> None:
        report = _report(_entry("a", TaskStatus.SUCCESS))
        html = _build_report_html(
            report, HTMLEmailStyle(palette="catppuccin"), ReportContent(), errors_only=False
        )
        # catppuccin palette has its own CSS variable names
        assert "--bg" in html or "catppuccin" in html.lower() or "var(--" in html


# ---------------------------------------------------------------------------
# Email send tests (verify SMTP transport)
# ---------------------------------------------------------------------------

class TestEmailSendReport:

    @patch("smtplib.SMTP")
    def test_sendmail_called(self, mock_smtp_cls: MagicMock) -> None:
        mock_smtp = MagicMock()
        mock_smtp_cls.return_value = mock_smtp

        report = _report(
            _entry("a", TaskStatus.SUCCESS),
            _entry("b", TaskStatus.ERRORED, error=_error()),
        )
        EmailChannel(_smtp()).send_report(report, errors_only=False)

        mock_smtp.sendmail.assert_called_once()
        mock_smtp.quit.assert_called_once()

    @patch("smtplib.SMTP")
    def test_mime_type_is_html(self, mock_smtp_cls: MagicMock) -> None:
        mock_smtp = MagicMock()
        mock_smtp_cls.return_value = mock_smtp

        EmailChannel(_smtp()).send_report(
            _report(_entry("a", TaskStatus.SUCCESS)), errors_only=False
        )

        _, _, msg_str = mock_smtp.sendmail.call_args[0]
        assert 'Content-Type: text/html' in msg_str

    @patch("smtplib.SMTP")
    def test_html_body_contains_task_name(self, mock_smtp_cls: MagicMock) -> None:
        mock_smtp = MagicMock()
        mock_smtp_cls.return_value = mock_smtp

        report = _report(_entry("my_task", TaskStatus.ERRORED, error=_error()))
        EmailChannel(_smtp()).send_report(report, errors_only=False)

        _, _, msg_str = mock_smtp.sendmail.call_args[0]
        body = _decode_mime_body(msg_str)
        assert "my_task" in body

    @patch("smtplib.SMTP")
    def test_errors_only_uses_errors_subject(self, mock_smtp_cls: MagicMock) -> None:
        mock_smtp = MagicMock()
        mock_smtp_cls.return_value = mock_smtp

        report = _report(_entry("b", TaskStatus.ERRORED, error=_error()))
        EmailChannel(_smtp()).send_report(report, errors_only=True)

        _, _, msg_str = mock_smtp.sendmail.call_args[0]
        assert "Failed" in msg_str or "failed" in msg_str.lower()
