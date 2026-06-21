from __future__ import annotations

import ssl
from dataclasses import dataclass

_VALID_PALETTES = frozenset({"neutral", "catppuccin", "neobones", "slate"})
_VALID_LANGUAGES = frozenset({"en", "es", "pt", "fr", "de", "it"})

_DEFAULT_PALETTE = "neutral"
_DEFAULT_LANGUAGE = "en"


@dataclass
class SMTPConfig:
    """SMTP transport configuration for HTML email error alerts.

    Attributes
    ----------
    mailhost : tuple[str, int]
        ``(host, port)`` of the SMTP server.
    fromaddr : str
        Sender email address.
    toaddrs : list[str]
        Recipient email addresses.
    credentials : tuple[str, str] | None
        ``(username, password)`` for SMTP authentication. Defaults to ``None``.
    secure : tuple[()] | tuple[str] | tuple[str, str] | tuple[str, str, ssl.SSLContext] | None
        Security configuration. Use ``()`` for STARTTLS, ``(keyfile,)`` or
        ``(keyfile, certfile)`` for explicit TLS context creation, or
        ``(keyfile, certfile, ssl_context)`` to supply a pre-built
        ``ssl.SSLContext``. ``None`` means no encryption. Defaults to ``None``.
    timeout : int
        Connection timeout in seconds. Defaults to ``5``.
    """

    mailhost: tuple[str, int]
    fromaddr: str
    toaddrs: list[str]
    credentials: tuple[str, str] | None = None
    secure: tuple[()] | tuple[str] | tuple[str, str] | tuple[str, str, ssl.SSLContext] | None = None
    timeout: int = 5


@dataclass(frozen=True, slots=True)
class HTMLEmailStyle:
    """HTML presentation settings for the report email.

    Both fields default to a neutral, English email — pass only what you want
    to override.

    Attributes
    ----------
    palette : str
        Color scheme: ``"neutral"``, ``"catppuccin"``, ``"neobones"``,
        or ``"slate"``. Defaults to ``"neutral"``.
    language : str
        ISO 639-1 code for the email body text: ``"en"``, ``"es"``, ``"pt"``,
        ``"fr"``, ``"de"``, or ``"it"``. Defaults to ``"en"``.

    Raises
    ------
    ValueError
        If ``palette`` or ``language`` is not one of the supported values.
    """

    palette: str = _DEFAULT_PALETTE
    language: str = _DEFAULT_LANGUAGE

    def __post_init__(self) -> None:
        if self.palette not in _VALID_PALETTES:
            raise ValueError(
                f"palette must be one of {sorted(_VALID_PALETTES)}, got {self.palette!r}"
            )
        if self.language not in _VALID_LANGUAGES:
            raise ValueError(
                f"language must be one of {sorted(_VALID_LANGUAGES)}, got {self.language!r}"
            )
