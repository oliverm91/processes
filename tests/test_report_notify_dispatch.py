"""Report notification dispatch: notify/notify_errors wiring and show_warnings behaviour."""

from __future__ import annotations

import warnings
from typing import Any

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


class _BrokenChannel(ReportChannel):
    def send_report(self, report: ProcessExecutionReport, *, errors_only: bool) -> None:
        raise RuntimeError("boom")


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


def test_notify_continues_after_channel_failure() -> None:
    report = ProcessExecutionReport()
    broken = _BrokenChannel()
    spy = _SpyChannel()
    report.notify(broken, spy, show_warnings=False)
    assert spy.calls == [(report, False)]


def test_notify_warns_on_channel_failure() -> None:
    report = ProcessExecutionReport()
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        report.notify(_BrokenChannel())
    assert len(caught) == 1
    assert "boom" in str(caught[0].message)


def test_notify_silent_when_show_warnings_false() -> None:
    report = ProcessExecutionReport()
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        report.notify(_BrokenChannel(), show_warnings=False)
    assert caught == []


def test_notify_errors_continues_and_warns() -> None:
    report = ProcessExecutionReport()
    spy = _SpyChannel()
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        report.notify_errors(_BrokenChannel(), spy)
    assert len(caught) == 1
    assert spy.calls == [(report, True)]


def test_report_content_defaults_and_per_channel_override() -> None:
    assert ReportContent() == ReportContent(show_traceback=True, show_traced_vars=True)

    custom = ReportContent(show_traceback=False)
    assert WebhookChannel(WebhookConfig(url="http://x"), content=custom).content is custom
    assert EmailChannel(_smtp()).content == ReportContent()  # default when omitted
