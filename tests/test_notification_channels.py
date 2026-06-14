"""Tests for the NotificationChannel abstraction.

Covers:

*   ``NotificationChannel`` cannot be instantiated directly.
*   ``FileChannel.build_handler`` returns a ``FileHandler`` at the right
    level, formatted with ``_TaskLogfileFormatter``, writing to the given path.
*   ``EmailChannel.build_handler`` returns an ``ERROR``-level handler with the
    localized subject, mirroring the behaviour of ``_build_task_email_handler``.
"""

from __future__ import annotations

import logging

import pytest

from processes import EmailChannel, FileChannel, HTMLEmailStyle, NotificationChannel, SMTPConfig
from processes._email_internals import _HTMLEmailFormatter
from processes._logfile_formatting import _TaskLogfileFormatter

from .base_test import BaseTest


class TestNotificationChannelABC:
    def test_cannot_instantiate_abstract_base(self) -> None:
        with pytest.raises(TypeError):
            NotificationChannel()  # type: ignore[abstract]


class TestFileChannel(BaseTest):
    def test_build_handler_returns_configured_file_handler(self) -> None:
        log_path = self._log("file_channel.log")
        channel = FileChannel(log_path)
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
        channel = FileChannel(log_path, level=logging.WARNING)
        handler = channel.build_handler("some_task")

        try:
            assert handler.level == logging.WARNING
        finally:
            handler.close()

    def test_handler_writes_log_records_to_path(self) -> None:
        log_path = self._log("file_channel_write.log")
        channel = FileChannel(log_path)
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
