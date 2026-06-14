from __future__ import annotations

from dataclasses import dataclass, field


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
    """

    url: str
    headers: dict[str, str] = field(default_factory=dict)
    timeout: int = 5
    secret: str | None = None
