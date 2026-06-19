"""Shared pytest fixtures.

``smtp_server`` runs a real in-process SMTP server (aiosmtpd) that captures every
delivered message in memory, so email tests exercise the full send path —
``smtplib`` conversation, MIME serialization, recipients — and assert on what is
actually *received*, instead of mocking ``smtplib.SMTP``.
"""

from __future__ import annotations

import socket
from collections.abc import Iterator
from email import message_from_bytes
from email.message import Message

import pytest
from aiosmtpd.controller import Controller


class _CapturingHandler:
    """aiosmtpd handler that records every received message in memory."""

    def __init__(self) -> None:
        self.messages: list[Message] = []

    async def handle_DATA(self, server: object, session: object, envelope: object) -> str:
        content = envelope.content  # type: ignore[attr-defined]
        self.messages.append(message_from_bytes(content))
        return "250 Message accepted for delivery"


class SMTPCapture:
    """A running capture server: connection details plus the received messages."""

    def __init__(self, host: str, port: int, handler: _CapturingHandler) -> None:
        self.host = host
        self.port = port
        self._handler = handler

    @property
    def messages(self) -> list[Message]:
        """Every message received so far, in arrival order."""
        return self._handler.messages

    def last(self) -> Message:
        """The most recently received message (asserts at least one arrived)."""
        assert self._handler.messages, "no email was received by the capture server"
        return self._handler.messages[-1]

    def last_html(self) -> str:
        """The decoded text body of the most recently received message."""
        payload = self.last().get_payload(decode=True)
        if isinstance(payload, bytes):
            return payload.decode("utf-8", errors="replace")
        return str(payload or "")


def _free_port() -> int:
    """Reserve and return an ephemeral localhost port."""
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


@pytest.fixture
def smtp_server() -> Iterator[SMTPCapture]:
    """Start a fresh in-process SMTP capture server for one test."""
    handler = _CapturingHandler()
    host, port = "127.0.0.1", _free_port()
    controller = Controller(handler, hostname=host, port=port)
    controller.start()
    try:
        yield SMTPCapture(host, port, handler)
    finally:
        controller.stop()
