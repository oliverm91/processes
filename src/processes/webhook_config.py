from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class WebhookConfig:
    """Transport configuration for generic webhook error alerts.

    Attributes
    ----------
    url : str
        Destination URL the JSON payload is POSTed to.
    headers : dict[str, str]
        Additional HTTP headers sent with the request. ``Content-Type``
        defaults to ``"application/json"`` if not overridden here.
        Defaults to ``{}``.
    timeout : int
        Request timeout in seconds. Defaults to ``5``.
    secret : str | None
        Shared secret used to HMAC-SHA256 sign the JSON request body. When
        set, the hex digest is sent in the ``X-Signature-SHA256`` header.
        ``None`` disables signing. Defaults to ``None``.
    extra_payload : dict[str, Any]
        Additional top-level keys merged into the JSON payload, taking
        precedence over the generic fields if names collide. Useful for
        service-specific routing fields (e.g. a Telegram ``chat_id``).
        Defaults to ``{}``.
    nest_under : str | None
        If set, the generic failure fields (``task_name``, ``function``,
        ``exception``, etc.) are nested under this key instead of being
        top-level, e.g. ``{"data": {...}, "chat_id": ...}`` for
        ``nest_under="data"``. ``extra_payload`` keys always stay top-level
        and still take precedence on collision. ``None`` or ``""`` means no
        nesting (the default, flat payload). Defaults to ``None``.
    """

    url: str
    headers: dict[str, str] = field(default_factory=dict)
    timeout: int = 5
    secret: str | None = None
    extra_payload: dict[str, Any] = field(default_factory=dict)
    nest_under: str | None = None
