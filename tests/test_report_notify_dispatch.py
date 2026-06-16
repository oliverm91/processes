"""Architecture of report notification: notify/notify_errors dispatch to channels.

Message rendering is deferred, so the built-in channels' ``send_report`` raise
``NotImplementedError``; these tests cover only the dispatch wiring and config.
"""

from __future__ import annotations

from typing import Any

import pytest

from processes import (
    EmailChannel,
    ProcessExecutionReport,
    ReportChannel,
    ReportContent,
    SMTPConfig,
    WebhookChannel,
    WebhookConfig,
)


class _SpyChannel(ReportChannel):
    def __init__(self) -> None:
        self.calls: list[tuple[Any, bool]] = []

    def send_report(self, report: ProcessExecutionReport, *, errors_only: bool) -> None:
        self.calls.append((report, errors_only))


def _smtp() -> SMTPConfig:
    return SMTPConfig(mailhost=("host", 25), fromaddr="a@b.com", toaddrs=["c@d.com"])


def test_notify_dispatches_to_each_channel_in_order() -> None:
    report = ProcessExecutionReport()
    a, b = _SpyChannel(), _SpyChannel()
    report.notify(a, b)
    assert a.calls == [(report, False)]
    assert b.calls == [(report, False)]


def test_notify_errors_sets_errors_only() -> None:
    report = ProcessExecutionReport()
    spy = _SpyChannel()
    report.notify_errors(spy)
    assert spy.calls == [(report, True)]


def test_notify_with_no_channels_is_noop() -> None:
    ProcessExecutionReport().notify()
    ProcessExecutionReport().notify_errors()


def test_builtin_channels_send_report_not_implemented_yet() -> None:
    report = ProcessExecutionReport()
    with pytest.raises(NotImplementedError):
        EmailChannel(_smtp()).send_report(report, errors_only=False)
    with pytest.raises(NotImplementedError):
        WebhookChannel(WebhookConfig(url="http://x")).send_report(report, errors_only=True)


def test_report_content_defaults_and_per_channel_override() -> None:
    assert ReportContent() == ReportContent(show_traceback=True, show_traced_vars=True)

    custom = ReportContent(show_traceback=False)
    assert WebhookChannel(WebhookConfig(url="http://x"), content=custom).content is custom
    assert EmailChannel(_smtp()).content == ReportContent()  # default when omitted
