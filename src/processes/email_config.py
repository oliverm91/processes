from __future__ import annotations

import ssl
from dataclasses import dataclass

_VALID_STYLES = frozenset({"classic", "modern", "compact"})
_VALID_PALETTES = frozenset({"neutral", "catppuccin", "neobones", "slate"})
_VALID_LANGUAGES = frozenset({"en", "es", "pt", "fr", "de", "it"})

_DEFAULT_STYLE = "modern"
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


@dataclass(frozen=True)
class HTMLEmailStyle:
    """HTML presentation settings for email error alerts.

    All fields default to a modern, neutral, English email — pass only
    what you want to override.

    Attributes
    ----------
    style : str
        Layout to use: ``"classic"``, ``"modern"``, or ``"compact"``.
        Defaults to ``"modern"``.
    palette : str
        Color scheme: ``"neutral"``, ``"catppuccin"``, ``"neobones"``,
        or ``"slate"``. Defaults to ``"neutral"``.
    language : str
        ISO 639-1 code for the email body text: ``"en"``, ``"es"``, ``"pt"``,
        ``"fr"``, ``"de"``, or ``"it"``. Defaults to ``"en"``.
    traced_vars_frame_filter : str | None
        Substring used to select the traceback frame whose local variables
        appear in the *Traced Variables* section. When ``None`` (default),
        the outermost user frame is used; when set, the outermost frame whose
        filename contains this substring is used instead.

    Raises
    ------
    ValueError
        If ``style``, ``palette``, or ``language`` is not one of the
        supported values.
    TypeError
        If ``traced_vars_frame_filter`` is neither ``str`` nor ``None``.
    """

    style: str = _DEFAULT_STYLE
    palette: str = _DEFAULT_PALETTE
    language: str = _DEFAULT_LANGUAGE
    traced_vars_frame_filter: str | None = None

    def __post_init__(self) -> None:
        if self.style not in _VALID_STYLES:
            raise ValueError(f"style must be one of {sorted(_VALID_STYLES)}, got {self.style!r}")
        if self.palette not in _VALID_PALETTES:
            raise ValueError(
                f"palette must be one of {sorted(_VALID_PALETTES)}, got {self.palette!r}"
            )
        if self.language not in _VALID_LANGUAGES:
            raise ValueError(
                f"language must be one of {sorted(_VALID_LANGUAGES)}, got {self.language!r}"
            )
        if self.traced_vars_frame_filter is not None and not isinstance(
            self.traced_vars_frame_filter, str
        ):
            raise TypeError(
                f"traced_vars_frame_filter must be a str or None. "
                f"Got {type(self.traced_vars_frame_filter)}"
            )
