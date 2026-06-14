"""Tests for the NotificationChannel abstraction.

Covers:

*   ``NotificationChannel`` cannot be instantiated directly.
*   ``_FileChannel.build_handler`` returns a ``FileHandler`` at the right
    level, formatted with ``_TaskLogfileFormatter``, writing to the given path.
*   ``EmailChannel.build_handler`` returns an ``ERROR``-level handler with the
    localized subject, mirroring the behaviour of ``_build_task_email_handler``.
"""

from __future__ import annotations

import json
import logging

import pytest

from processes import (
    EmailChannel,
    HTMLEmailStyle,
    NotificationChannel,
    Process,
    SMTPConfig,
    Task,
    WebhookChannel,
    WebhookConfig,
)
from processes._email_internals import _HTMLEmailFormatter
from processes._logfile_formatting import _TaskLogfileFormatter
from processes._webhook_internals import _WebhookFormatter
from processes.notification_channels import _FileChannel

from .base_test import BaseTest


class TestNotificationChannelABC:
    def test_cannot_instantiate_abstract_base(self) -> None:
        with pytest.raises(TypeError):
            NotificationChannel()  # type: ignore[abstract]


class TestFileChannel(BaseTest):
    def test_build_handler_returns_configured_file_handler(self) -> None:
        log_path = self._log("file_channel.log")
        channel = _FileChannel(log_path)
        handler = channel.build_handler("some_task")

        try:
            assert isinstance(handler, logging.FileHandler)
            assert handler.level == logging.INFO
            assert isinstance(handler.formatter, _TaskLogfileFormatter)
            assert handler.baseFilename == log_path
        finally:
            handler.close()

    def test_build_handler_respects_custom_level(self) -> None:
        log_path = self._log("file_channel_level.log")
        channel = _FileChannel(log_path, level=logging.WARNING)
        handler = channel.build_handler("some_task")

        try:
            assert handler.level == logging.WARNING
        finally:
            handler.close()

    def test_handler_writes_log_records_to_path(self) -> None:
        log_path = self._log("file_channel_write.log")
        channel = _FileChannel(log_path)
        handler = channel.build_handler("write_task")

        logger = logging.getLogger("test.notification_channels.file_write")
        logger.setLevel(logging.DEBUG)
        logger.addHandler(handler)
        try:
            logger.info("hello from file channel")
        finally:
            handler.close()
            logger.removeHandler(handler)

        with open(log_path) as f:
            content = f.read()
        assert "hello from file channel" in content


class TestEmailChannel(BaseTest):
    def _smtp_config(self) -> SMTPConfig:
        return SMTPConfig(
            mailhost=("smtp.example.test", 25),
            fromaddr="alerts@example.test",
            toaddrs=["oncall@example.test"],
        )

    def test_build_handler_defaults_to_error_level_and_default_style(self) -> None:
        channel = EmailChannel(self._smtp_config())
        handler = channel.build_handler("email_task")

        assert handler.level == logging.ERROR
        assert isinstance(handler.formatter, _HTMLEmailFormatter)
        assert handler.subject == "Error in task email_task"

    def test_build_handler_uses_provided_style_for_subject_language(self) -> None:
        channel = EmailChannel(self._smtp_config(), HTMLEmailStyle(language="es"))
        handler = channel.build_handler("email_task")

        assert handler.subject == "Error en la tarea email_task"

    def test_default_style_is_modern_neutral_english(self) -> None:
        channel = EmailChannel(self._smtp_config())
        assert channel.style == HTMLEmailStyle()

    def test_frame_filter_sourced_from_style(self) -> None:
        channel = EmailChannel(self._smtp_config(), HTMLEmailStyle(traced_vars_frame_filter="json"))
        assert channel.frame_filter == "json"

    def test_frame_filter_defaults_to_none(self) -> None:
        channel = EmailChannel(self._smtp_config())
        assert channel.frame_filter is None


class TestWebhookChannel(BaseTest):
    def _webhook_config(self, **overrides: object) -> WebhookConfig:
        defaults: dict[str, object] = {"url": "https://example.test/hook"}
        defaults.update(overrides)
        return WebhookConfig(**defaults)  # type: ignore[arg-type]

    def test_build_handler_defaults_to_error_level(self) -> None:
        channel = WebhookChannel(self._webhook_config())
        handler = channel.build_handler("webhook_task")

        assert handler.level == logging.ERROR
        assert isinstance(handler.formatter, _WebhookFormatter)

    def test_config_round_trips_onto_channel(self) -> None:
        config = self._webhook_config(
            headers={"Authorization": "Bearer x"}, timeout=10, secret="shh"
        )
        channel = WebhookChannel(config)

        assert channel.webhook_config is config
        assert channel.webhook_config.url == "https://example.test/hook"
        assert channel.webhook_config.headers == {"Authorization": "Bearer x"}
        assert channel.webhook_config.timeout == 10
        assert channel.webhook_config.secret == "shh"

    def test_frame_filter_defaults_to_none(self) -> None:
        channel = WebhookChannel(self._webhook_config())
        assert channel.frame_filter is None

    def _failure_record(self) -> logging.LogRecord:
        record = logging.LogRecord(
            name="processes.task_1",
            level=logging.ERROR,
            pathname=__file__,
            lineno=1,
            msg="boom",
            args=None,
            exc_info=None,
        )
        record.task_context = {
            "task_name": "task_1",
            "function": "do_thing",
            "args": (),
            "kwargs": {},
            "downstream_impact": [],
            "exception": "boom",
            "traceback_str": "",
            "traced_vars": {},
            "traced_vars_location": "",
        }
        return record

    def test_format_without_nest_under_is_flat(self) -> None:
        formatter = _WebhookFormatter(extra_payload={"chat_id": "123"})
        payload = json.loads(formatter.format(self._failure_record()))

        assert payload["task_name"] == "task_1"
        assert payload["chat_id"] == "123"

    def test_format_with_nest_under_nests_generic_fields(self) -> None:
        formatter = _WebhookFormatter(extra_payload={"chat_id": "123"}, nest_under="data")
        payload = json.loads(formatter.format(self._failure_record()))

        assert payload["data"]["task_name"] == "task_1"
        assert payload["data"]["function"] == "do_thing"
        assert payload["chat_id"] == "123"
        assert "task_name" not in payload

    def test_extra_payload_still_wins_on_collision_with_nest_under(self) -> None:
        formatter = _WebhookFormatter(extra_payload={"data": "overridden"}, nest_under="data")
        payload = json.loads(formatter.format(self._failure_record()))

        assert payload["data"] == "overridden"

    def test_webhook_config_nest_under_reaches_formatter(self) -> None:
        config = self._webhook_config(nest_under="data")
        channel = WebhookChannel(config)
        handler = channel.build_handler("webhook_task")

        assert isinstance(handler.formatter, _WebhookFormatter)
        payload = json.loads(handler.formatter.format(self._failure_record()))
        assert payload["data"]["task_name"] == "task_1"


class _RecordingChannel(NotificationChannel):
    """Test-only channel that captures every record it receives."""

    def __init__(self) -> None:
        self.records: list[logging.LogRecord] = []

    def build_handler(self, task_name: str) -> logging.Handler:
        records = self.records

        class _Handler(logging.Handler):
            def emit(self, record: logging.LogRecord) -> None:
                records.append(record)

        handler = _Handler()
        handler.setLevel(logging.INFO)
        return handler


class TestTaskChannelsWiring(BaseTest):
    def test_extra_channel_receives_log_records(self) -> None:
        def task_1() -> int:
            return 1

        channel = _RecordingChannel()
        task = Task("task_1", task_1, self._log("channels_extra.log"), channels=[channel])

        with Process([task]) as process:
            process.run()

        messages = [r.getMessage() for r in channel.records]
        assert "Starting task_1." in messages
        assert "Finished task_1." in messages

    def test_default_channels_remain_when_extra_channel_given(self) -> None:
        def task_1() -> int:
            return 1

        log_path = self._log("channels_default_plus_extra.log")
        channel = _RecordingChannel()
        task = Task("task_1", task_1, log_path, channels=[channel])

        with Process([task]) as process:
            process.run()

        with open(log_path) as f:
            lines = f.readlines()
        assert "Starting task_1." in lines[0]
        assert "Finished task_1." in lines[1]
        assert len(channel.records) == 2

    def test_channels_must_be_list(self) -> None:
        def task_1() -> int:
            return 1

        with pytest.raises(TypeError, match="channels must be list"):
            Task(
                "task_1",
                task_1,
                self._log("channels_bad_type.log"),
                channels="not-a-list",  # type: ignore[arg-type]
            )

    def test_channels_entries_must_be_notification_channel(self) -> None:
        def task_1() -> int:
            return 1

        with pytest.raises(TypeError, match="channel must be of type NotificationChannel"):
            Task(
                "task_1",
                task_1,
                self._log("channels_bad_entry.log"),
                channels=["not-a-channel"],  # type: ignore[list-item]
            )
