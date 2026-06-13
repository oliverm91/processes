import html
import json
import logging
import os
import sys
import traceback
from typing import Any, cast

from .html_logging import (
    _DEFAULT_LANGUAGE,
    _DEFAULT_PALETTE,
    _DEFAULT_STYLE,
    _VALID_LANGUAGES,
    _VALID_PALETTES,
    _VALID_STYLES,
)

_THEMES_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "themes")
_STYLES_DIR = os.path.join(_THEMES_DIR, "styles")
_PALETTES_DIR = os.path.join(_THEMES_DIR, "palettes")
_LANGUAGES_DIR = os.path.join(_THEMES_DIR, "languages")

_PALETTE_MARKER = "{{__palette_css__}}"


def _is_library_path(filename: str) -> bool:
    """Heuristic: True if ``filename`` lives inside a library or stdlib.

    Used by ``ExceptionHTMLFormatter._resolve_target_tb`` to skip
    third-party and standard-library frames when auto-resolving the
    traceback frame whose locals should be inspected.  Three checks:

    *   substring ``"site-packages"`` — third-party packages
    *   substring ``".venv"`` — POSIX-style virtualenv root
    *   any path under ``sys.base_prefix`` — the Python install
        itself, which on Windows is ``<prefix>\\Lib\\...`` and on
        POSIX is ``<prefix>/lib/python3.X/...``
    """
    if "site-packages" in filename:
        return True
    if ".venv" in filename:
        return True
    base_prefix = getattr(sys, "base_prefix", "")
    if base_prefix:
        try:
            if os.path.commonpath(
                [os.path.abspath(filename), os.path.abspath(base_prefix)]
            ) == os.path.abspath(base_prefix):
                return True
        except ValueError:
            # Different drives on Windows — can't be under base_prefix.
            return False
    return False


def _load_language_strings(language: str) -> dict[str, str]:
    """Load translatable strings for the given ISO 639-1 language code.

    Parameters
    ----------
    language : str
        One of the supported language codes (``"en"``, ``"es"``, ``"pt"``,
        ``"fr"``, ``"de"``, ``"it"``).

    Returns
    -------
    dict[str, str]
        Mapping from placeholder name (e.g. ``"lang_function_label"``) to
        the translated string.
    """
    path = os.path.join(_LANGUAGES_DIR, f"{language}.json")
    with open(path, encoding="utf-8") as fh:
        return cast(dict[str, str], json.load(fh))


class ExceptionHTMLFormatter(logging.Formatter):
    """
    A logging formatter that converts exception records to HTML format.

    Renders a Jinja-like template by composing a bundled style layout from
    ``themes/styles/`` with a color palette from ``themes/palettes/``, using
    the pure metadata dict supplied via ``extra={"task_context": ...}`` on
    the originating log call.  This keeps the log payload framework-agnostic
    (no raw HTML fragments in ``extra``) while still producing a richly
    formatted HTML email body.

    Parameters
    ----------
    email_style : str
        Name of the bundled style layout (``"classic"``, ``"modern"`` or
        ``"compact"``).
    color_palette : str
        Name of the bundled color palette (``"neutral"``, ``"catppuccin"``,
        ``"neobones"`` or ``"slate"``) injected into the style at the
        ``{{__palette_css__}}`` marker.
    email_language : str
        ISO 639-1 language code for the email body and subject
        (``"en"``, ``"es"``, ``"pt"``, ``"fr"``, ``"de"``, ``"it"``).
    last_path_traced_vars : str | None
        Substring used to pick the traceback frame whose local variables
        are printed at format time.  When ``None`` (the default) the
        formatter walks ``exc_tb.tb_next`` and resolves it to the *last*
        frame in the chain whose filename does not contain
        ``site-packages`` or ``.venv`` — i.e. the outermost user / project
        frame in the call stack.  When set, the formatter walks the chain
        and picks the *last* frame whose filename contains the substring
        (useful for pointing at a specific project directory or library).
        The locals are printed to stdout for debugging; they are not yet
        included in the rendered email body.
    """

    def __init__(
        self,
        *,
        email_style: str = _DEFAULT_STYLE,
        color_palette: str = _DEFAULT_PALETTE,
        email_language: str = _DEFAULT_LANGUAGE,
        last_path_traced_vars: str | None = None,
    ) -> None:
        super().__init__()
        if email_style not in _VALID_STYLES:
            raise ValueError(
                f"email_style must be one of {sorted(_VALID_STYLES)}, got {email_style!r}"
            )
        if color_palette not in _VALID_PALETTES:
            raise ValueError(
                f"color_palette must be one of {sorted(_VALID_PALETTES)}, got {color_palette!r}"
            )
        if email_language not in _VALID_LANGUAGES:
            raise ValueError(
                f"email_language must be one of {sorted(_VALID_LANGUAGES)}, got {email_language!r}"
            )
        self._email_style = email_style
        self._color_palette = color_palette
        self._email_language = email_language
        self._last_path_traced_vars = last_path_traced_vars
        self._cached_template: str | None = None

    def _resolve_template(self) -> str:
        """Compose the bundled style + palette into a single template string."""
        style_path = os.path.join(_STYLES_DIR, f"{self._email_style}.html")
        palette_path = os.path.join(_PALETTES_DIR, f"{self._color_palette}.css")
        with open(style_path, encoding="utf-8") as fh:
            style = fh.read()
        with open(palette_path, encoding="utf-8") as fh:
            palette = fh.read()
        return style.replace(_PALETTE_MARKER, palette)

    def _get_template(self) -> str:
        if self._cached_template is None:
            self._cached_template = self._resolve_template()
        return self._cached_template

    def _format_exception_block(self, record: logging.LogRecord) -> tuple[str, str, str, str]:
        """Return (exception_str, tb_str, traced_vars_html, traced_vars_location)."""
        if record.exc_info:
            exc_type, exc_value, exc_tb = record.exc_info
            exception = "" if exc_value is None else str(exc_value)
            tb_str = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
            self._print_traced_locals(exc_tb)
            traced_vars = self._build_traced_vars_html(exc_tb)
            location = self._build_traced_vars_location(exc_tb)
        else:
            exception = record.getMessage()
            tb_str = ""
            traced_vars = ""
            location = ""
        return exception, tb_str, traced_vars, location

    def _build_traced_vars_html(self, exc_tb: Any) -> str:
        """Build the HTML body of the *Traced Variables* section.

        Lines are ``name = value`` pairs (one per local variable),
        HTML-escaped and ready to drop into a ``<pre>`` block.

        The location header that points to the resolved frame is
        rendered separately by the templates — see
        ``_build_traced_vars_location`` and ``lang_traced_vars_blurb``.

        Returns ``""`` if no target frame can be resolved.
        """
        target = self._resolve_target_tb(exc_tb)
        if target is None:
            return ""

        frame = target.tb_frame
        lines: list[str] = []
        for name, value in frame.f_locals.items():
            try:
                rendered = repr(value)
            except Exception as exc:
                rendered = f"<unreprable: {type(exc).__name__}: {exc}>"
            lines.append(f"{name} = {rendered}")
        return "\n".join(html.escape(line, quote=True) for line in lines)

    def _build_traced_vars_location(self, exc_tb: Any) -> str:
        """Build a ``<filename>:<lineno>`` reference for the resolved frame.

        Used by the templates to render the *Traced Variables* blurb,
        so the reader can jump to the source location of the listed
        locals.

        Returns ``""`` if no target frame can be resolved.
        """
        target = self._resolve_target_tb(exc_tb)
        if target is None:
            return ""
        frame = target.tb_frame
        return f"{frame.f_code.co_filename}:{frame.f_lineno}"

    def _split_traceback_at_target(self, tb_str: str, location: str) -> tuple[str, str, str]:
        """Split ``tb_str`` around the frame line matching ``location``.

        Returns a 3-tuple ``(before, highlight, after)`` where ``highlight``
        is the matching ``  File "<filename>", line <lineno>, in <func>``
        line (with its trailing newline), and ``before`` / ``after`` are
        the lines on either side of it.

        The output is pure text — the formatter never emits HTML tags.
        Templates decide how to style the highlight segment (e.g. wrap
        it in ``<strong>``).

        Returns ``("", "", tb_str)`` if ``tb_str`` or ``location`` is
        empty/malformed, or if the matching line is not present in the
        traceback text.
        """
        if not tb_str or not location:
            return ("", "", tb_str)
        try:
            filename, lineno_str = location.rsplit(":", 1)
            lineno = int(lineno_str)
        except ValueError:
            return ("", "", tb_str)

        needle = f'  File "{filename}", line {lineno}, in'
        lines = tb_str.splitlines(keepends=True)
        for i, line in enumerate(lines):
            if needle in line:
                return ("".join(lines[:i]), line, "".join(lines[i + 1 :]))
        return ("", "", tb_str)

    @staticmethod
    def _iter_tb(exc_tb: Any) -> Any:
        """Yield every traceback frame from innermost to outermost.

        Mirrors the standard ``traceback.walk_tb`` contract: starting at
        the frame that raised (or that the exception is attached to) and
        following ``tb_next`` until the chain ends.
        """
        tb = exc_tb
        while tb is not None:
            yield tb
            tb = tb.tb_next

    def _resolve_target_tb(self, exc_tb: Any) -> Any:
        """Pick the traceback frame whose ``f_locals`` should be inspected.

        Walks the ``tb_next`` chain and returns the *last* matching frame
        (i.e. the outermost match when iterating innermost→outermost).

        *   If ``self._last_path_traced_vars`` is ``None`` the match
            predicate is "filename does not contain ``site-packages`` or
            ``.venv``" — the outermost user / project frame.
        *   Otherwise the match predicate is "filename contains the
            configured substring" — useful for pointing at a specific
            project directory or library.

        Falls back to the outermost frame in the chain if nothing
        matches, so the caller always gets a frame to inspect.
        """
        frames = list(self._iter_tb(exc_tb))
        if not frames:
            return None

        needle = self._last_path_traced_vars
        if needle is None:
            matches = [tb for tb in frames if not _is_library_path(tb.tb_frame.f_code.co_filename)]
        else:
            matches = [tb for tb in frames if needle in tb.tb_frame.f_code.co_filename]

        return matches[-1] if matches else frames[-1]

    def _print_traced_locals(self, exc_tb: Any) -> None:
        """Print ``f_locals`` of the resolved traceback frame to stdout.

        The locals are intentionally *not* added to the rendered email
        body in this revision — this is the diagnostic half of the
        feature, so the user can see them locally while the formatter
        is being iterated on.
        """
        target = self._resolve_target_tb(exc_tb)
        if target is None:
            return

        frame = target.tb_frame
        filename = frame.f_code.co_filename
        lineno = frame.f_lineno
        funcname = frame.f_code.co_name
        print(f"[{type(self).__name__}] local vars at {filename}:{lineno} in {funcname}:")
        for name, value in frame.f_locals.items():
            try:
                rendered = repr(value)
            except Exception as exc:
                rendered = f"<unreprable: {type(exc).__name__}: {exc}>"
            print(f"  {name} = {rendered}")

    def _render(self, template: str, substitutions: dict[str, str]) -> str:
        rendered = template
        for key, value in substitutions.items():
            rendered = rendered.replace("{{" + key + "}}", value)
        return rendered

    def format(self, record: logging.LogRecord) -> str:
        exception, tb_str, traced_vars, traced_vars_location = self._format_exception_block(record)
        # Split the traceback into (before, highlight, after) segments
        # around the frame line that matches the traced-vars location.
        # Output is pure text — the templates own the visual styling
        # of the highlight segment (e.g. wrapping it in <strong>).
        tb_before, tb_highlight, tb_after = self._split_traceback_at_target(
            tb_str, traced_vars_location
        )
        task_context = getattr(record, "task_context", None) or {}

        downstream = task_context.get("downstream_impact", []) or []
        downstream_items = "".join(
            f"<li>{html.escape(str(name), quote=True)}</li>" for name in downstream
        )

        substitutions = dict(_load_language_strings(self._email_language))
        # The lang_traced_vars_blurb string carries a {location} placeholder
        # that points at the resolved frame (e.g. "…had these values at
        # file:42:").  Substitute the actual location into the translated
        # blurb before the template is rendered.
        substitutions["lang_traced_vars_blurb"] = substitutions.get(
            "lang_traced_vars_blurb", ""
        ).replace("{location}", traced_vars_location)
        substitutions.update(
            {
                "task_name": html.escape(str(task_context.get("task_name", "?")), quote=True),
                "function": html.escape(str(task_context.get("function", "?")), quote=True),
                "args": html.escape(repr(task_context.get("args", ())), quote=True),
                "kwargs": html.escape(repr(task_context.get("kwargs", {})), quote=True),
                "exception": html.escape(exception, quote=True),
                "traceback_before": html.escape(tb_before, quote=True),
                "traceback_highlight": html.escape(tb_highlight, quote=True),
                "traceback_after": html.escape(tb_after, quote=True),
                "traced_vars": traced_vars,
                "downstream_items": downstream_items,
            }
        )
        return self._render(self._get_template(), substitutions)
