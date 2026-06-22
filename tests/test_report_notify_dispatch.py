"""Report notification dispatch: notify wiring, filtering and show_warnings behaviour."""

from __future__ import annotations

import warnings
from typing import Any

from processes import (
    EmailChannel,
    ProcessExecutionReport,
    ReportChannel,
    ReportContent,
    SMTPConfig,
    TaskReportEntry,
    TaskStatus,
    WebhookChannel,
    WebhookConfig,
)


def _report_with(*names: str) -> ProcessExecutionReport:
    """A report carrying one SUCCESS entry per given task name."""
    return ProcessExecutionReport(
        {
            name: TaskReportEntry(
                name=name,
                function="f",
                args=(),
                kwargs={},
                status=TaskStatus.SUCCESS,
                elapsed_seconds=0.0,
                attempts=1,
            )
            for name in names
        }
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


# def test_notify_only_errors_sets_errors_only() -> None:
#     report = ProcessExecutionReport()
#     spy = _SpyChannel()
#     report.notify(spy, only_errors=True)
#     assert spy.calls == [(report, True)]


def test_notify_with_no_channels_is_noop() -> None:
    ProcessExecutionReport().notify()
    ProcessExecutionReport().notify(only_errors=True)


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


# def test_notify_only_errors_continues_and_warns() -> None:
#     report = ProcessExecutionReport()
#     spy = _SpyChannel()
#     with warnings.catch_warnings(record=True) as caught:
#         warnings.simplefilter("always")
#         report.notify(_BrokenChannel(), spy, only_errors=True)
#     assert len(caught) == 1
#     assert spy.calls == [(report, True)]


def test_notify_tasks_filters_by_name() -> None:
    report = _report_with("alpha", "beta", "gamma")
    spy = _SpyChannel()
    report.notify(spy, tasks=["alpha", "gamma"])
    (sent_report, errors_only) = spy.calls[0]
    assert set(sent_report.entries) == {"alpha", "gamma"}
    assert errors_only is False


def test_notify_tasks_is_case_insensitive() -> None:
    report = _report_with("Fetch_Orders", "Decode_Payload")
    spy = _SpyChannel()
    report.notify(spy, tasks=["fetch_orders"])
    assert set(spy.calls[0][0].entries) == {"Fetch_Orders"}


def test_notify_tasks_empty_list_sends_empty_report() -> None:
    report = _report_with("alpha", "beta")
    spy = _SpyChannel()
    report.notify(spy, tasks=[])
    assert set(spy.calls[0][0].entries) == set()


def test_notify_tasks_none_includes_every_task() -> None:
    report = _report_with("alpha", "beta")
    spy = _SpyChannel()
    report.notify(spy)
    assert spy.calls[0][0] is report


# def test_notify_tasks_combines_with_only_errors() -> None:
#     report = _report_with("alpha", "beta")
#     spy = _SpyChannel()
#     report.notify(spy, only_errors=True, tasks=["alpha"])
#     (sent_report, errors_only) = spy.calls[0]
#     assert set(sent_report.entries) == {"alpha"}
#     assert errors_only is True



def test_report_content_defaults_and_per_channel_override() -> None:
    assert ReportContent() == ReportContent(show_traceback=True, show_traced_vars=True)

    custom = ReportContent(show_traceback=False)
    assert WebhookChannel(WebhookConfig(url="http://x"), content=custom).content is custom
    assert EmailChannel(_smtp()).content == ReportContent()  # default when omitted
