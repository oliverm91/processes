"""Tests for the themed HTML email alert system.

Covers:

*   The 9 ``(style, palette)`` combinations render a fully substituted HTML
    body that pulls the palette's CSS variables into the style at the
    ``{{__palette_css__}}`` marker and carries the style's distinctive markup.
*   Every (style, palette, language) combination renders a body in the target
    language — a language-specific marker from each translation file must appear
    in the output.
*   Constructor validation on ``HTMLEmailStyle`` — unknown style/palette/language
    names must raise ``ValueError`` at construction time.
*   The wiring inside ``Task.__init__``: setting ``email_style`` on a Task must
    propagate through the runtime formatter so the rendered email body and subject
    carry the chosen options.
"""

from __future__ import annotations

import logging
import logging.handlers
from email import message_from_string
from unittest.mock import patch

import pytest

from processes import HTMLEmailStyle, Process, SMTPConfig, Task
from processes._email_internals import _HTMLEmailFormatter
from processes._tb_utils import (
    _build_traced_vars_html,
    _build_traced_vars_location,
    _format_traceback,
)

from .base_test import BaseTest


def _decode_mime_body(msg: str) -> str:
    """Decode the base64 HTML body from a sendmail payload."""
    parsed = message_from_string(msg)
    payload = parsed.get_payload(decode=True) or b""
    return payload.decode("utf-8", errors="replace")


_STYLE_MARKERS = {
    "classic": ["<h1>Pipeline Failure:", 'class="impact"', 'class="traceback"'],
    "modern": ['class="card"', 'class="header"', 'class="alert"'],
    "compact": ["[failure]", "[Function]", "[Downstream Impact]", "[Traceback]"],
}

_PALETTE_MARKERS = {
    "neutral": "--accent: #2563eb",
    "catppuccin": "--accent: #8839ef",
    "neobones": "--bg-page: #f3efec",
    "slate": "--bg-page: #1e293b",
}

_STYLES = ("classic", "modern", "compact")
_PALETTES = ("neutral", "catppuccin", "neobones", "slate")
_LANGUAGES = ("en", "es", "pt", "fr", "de", "it")

_LANGUAGE_MARKERS = {
    "en": ["Pipeline Failure:", "Function", "Downstream Impact"],
    "es": ["Fallo en el pipeline:", "Función", "Impacto en tareas dependientes"],
    "pt": ["Falha no pipeline:", "Função", "Impacto nas tarefas dependentes"],
    "fr": ["Échec du pipeline :", "Fonction", "Impact sur les tâches dépendantes"],
    "de": ["Pipeline-Fehlschlag:", "Funktion", "Auswirkung auf nachgelagerte Aufgaben"],
    "it": ["Fallimento del pipeline:", "Funzione", "Impatto sulle attività dipendenti"],
}

_SUBJECT_MARKERS = {
    "en": "Error in task ",
    "es": "Error en la tarea ",
    "pt": "Erro na tarefa ",
    "fr": "Erreur dans la tâche ",
    "de": "Fehler in Aufgabe ",
    "it": "Errore nell'attività ",
}

_CONTENT_KEYS = (
    "task_name",
    "function",
    "args",
    "kwargs",
    "exception",
    "traceback_before",
    "traceback_highlight",
    "traceback_after",
    "traced_vars",
    "downstream_items",
)

_LANG_CONTENT_KEYS = (
    "lang_title_prefix",
    "lang_failure_header",
    "lang_function_label",
    "lang_args_label",
    "lang_kwargs_label",
    "lang_exception_label",
    "lang_downstream_title",
    "lang_downstream_blurb",
    "lang_traceback_title",
    "lang_traced_vars_title",
    "lang_traced_vars_blurb",
)


def _make_record(task_name: str = "demo_task") -> logging.LogRecord:
    """Build a LogRecord carrying the canonical task_context payload."""
    record = logging.LogRecord(
        name=task_name,
        level=logging.ERROR,
        pathname=__file__,
        lineno=1,
        msg="planned failure in %s",
        args=(task_name,),
        exc_info=None,
    )
    record.task_context = {
        "task_name": task_name,
        "function": "func_demo",
        "args": ("a", 1),
        "kwargs": {"flag": True},
        "downstream_impact": ["child_a", "child_b"],
    }
    return record


# --------------------------------------------------------------------------- #
# 1. Formatter rendering tests (no Tasks or log files)                         #
# --------------------------------------------------------------------------- #


class TestEmailRendering(BaseTest):
    def test_every_style_palette_renders_complete_substitution(self) -> None:
        """Every (style, palette) pair must render with all placeholders filled."""
        for style in _STYLES:
            for palette in _PALETTES:
                formatter = _HTMLEmailFormatter(HTMLEmailStyle(style=style, palette=palette))
                output = formatter.format(_make_record(f"task_{style}_{palette}"))

                for key in _CONTENT_KEYS:
                    placeholder = "{{" + key + "}}"
                    assert placeholder not in output, (
                        f"[{style}/{palette}] placeholder {placeholder!r} was not substituted"
                    )

                assert "{{__palette_css__}}" not in output, (
                    f"[{style}/{palette}] palette marker was not injected"
                )
                assert _PALETTE_MARKERS[palette] in output, (
                    f"[{style}/{palette}] palette marker "
                    f"{_PALETTE_MARKERS[palette]!r} not found in rendered body"
                )
                for marker in _STYLE_MARKERS[style]:
                    assert marker in output, (
                        f"[{style}/{palette}] style marker {marker!r} not found"
                    )

    def test_every_language_renders_translated_body(self) -> None:
        """For each supported language, the body must carry that language's text
        across all (style, palette) combinations."""
        for language in _LANGUAGES:
            for style in _STYLES:
                for palette in _PALETTES:
                    formatter = _HTMLEmailFormatter(
                        HTMLEmailStyle(style=style, palette=palette, language=language)
                    )
                    output = formatter.format(_make_record(f"task_{language}_{style}_{palette}"))

                    for key in _LANG_CONTENT_KEYS:
                        placeholder = "{{" + key + "}}"
                        assert placeholder not in output, (
                            f"[{language}/{style}/{palette}] placeholder "
                            f"{placeholder!r} was not substituted"
                        )

                    markers = _LANGUAGE_MARKERS[language]
                    assert any(marker in output for marker in markers), (
                        f"[{language}/{style}/{palette}] no language marker "
                        f"from {markers!r} found in rendered body"
                    )

    def test_style_rejects_unknown_style(self) -> None:
        with pytest.raises(ValueError, match="style must be one of"):
            HTMLEmailStyle(style="neon")

    def test_style_rejects_unknown_palette(self) -> None:
        with pytest.raises(ValueError, match="palette must be one of"):
            HTMLEmailStyle(palette="rainbow")

    def test_style_rejects_unknown_language(self) -> None:
        with pytest.raises(ValueError, match="language must be one of"):
            HTMLEmailStyle(language="klingon")

    def test_style_defaults_to_english(self) -> None:
        formatter = _HTMLEmailFormatter(HTMLEmailStyle())
        output = formatter.format(_make_record())
        assert "Pipeline Failure:" in output
        assert "Function" in output

    def test_traced_vars_frame_filter_selects_user_frame(self) -> None:
        """traced_vars_frame_filter set to a substring of this test's path must
        pick this test module's frame over deeper frames in the call stack."""

        def _deep() -> None:
            user_local = "user_frame_value"  # noqa: F841
            raise RuntimeError("deep failure")

        try:
            _deep()
        except Exception as exc:
            record = _make_record("filter_user")
            frame_filter = "test_email_themes"
            record.task_context.update(
                {
                    "exception": str(exc),
                    "traceback_str": _format_traceback(exc),
                    "traced_vars": _build_traced_vars_html(exc.__traceback__, frame_filter),
                    "traced_vars_location": _build_traced_vars_location(
                        exc.__traceback__, frame_filter
                    ),
                }
            )

        formatter = _HTMLEmailFormatter(HTMLEmailStyle())
        body = formatter.format(record)

        assert "user_local" in body, (
            "frame_filter='test_email_themes' should pick the _deep frame "
            "whose locals include 'user_local'"
        )
        assert "user_frame_value" in body

    def test_traced_vars_frame_filter_selects_stdlib_frame(self) -> None:
        """traced_vars_frame_filter='json' must pick a frame inside the json stdlib
        module rather than the user hook frame that actually raised.

        The exception propagates through json.loads → json.decoder.raw_decode →
        (C scanner) → object_hook.  Filtering for 'json' selects the innermost
        json Python frame (raw_decode), whose ``s`` local holds the full input
        string — a reliable sentinel we can assert on.
        """
        import json

        sentinel_input = '{"unique_sentinel_9a3f": 1}'

        def _bad_hook(d: dict) -> None:
            hook_local = "this_is_from_our_hook"  # noqa: F841
            raise RuntimeError("hook raised")

        try:
            json.loads(sentinel_input, object_hook=_bad_hook)
        except Exception as exc:
            record = _make_record("filter_json")
            frame_filter = "json"
            record.task_context.update(
                {
                    "exception": str(exc),
                    "traceback_str": _format_traceback(exc),
                    "traced_vars": _build_traced_vars_html(exc.__traceback__, frame_filter),
                    "traced_vars_location": _build_traced_vars_location(
                        exc.__traceback__, frame_filter
                    ),
                }
            )

        formatter = _HTMLEmailFormatter(HTMLEmailStyle())
        body = formatter.format(record)

        assert "unique_sentinel_9a3f" in body, (
            "traced_vars_frame_filter='json' should select the innermost json frame "
            "(raw_decode) whose 's' local holds the original input string"
        )
        assert "this_is_from_our_hook" not in body, (
            "The hook frame (in test_email_themes.py) must not be selected when "
            "filtering for 'json'"
        )

    def test_traced_vars_section_renders_under_traceback(self) -> None:
        """Rendered body must include the *Traced Variables* section with local
        variables from the resolved target frame."""

        def _inner() -> None:
            marker = "traced_vars_marker_42"
            raise RuntimeError(f"planned traced-vars failure; marker={marker}")

        try:
            _inner()
        except Exception as exc:
            record = _make_record("traced_task")
            record.task_context.update(
                {
                    "exception": str(exc),
                    "traceback_str": _format_traceback(exc),
                    "traced_vars": _build_traced_vars_html(exc.__traceback__, None),
                    "traced_vars_location": _build_traced_vars_location(exc.__traceback__, None),
                }
            )

        formatter = _HTMLEmailFormatter(
            HTMLEmailStyle(style="modern", palette="neutral", language="en")
        )
        body = formatter.format(record)

        assert "Traced Variables" in body, (
            "Rendered body is missing the 'Traced Variables' section title"
        )
        assert "marker" in body, (
            "Rendered body is missing the local var name from the resolved frame"
        )
        assert "traced_vars_marker_42" in body, (
            "Rendered body is missing the local var value from the resolved frame"
        )
        assert "The following local variables had these values at" in body, (
            "Rendered body is missing the 'lang_traced_vars_blurb' blurb"
        )
        assert "test_email_themes.py:" in body, (
            "Rendered body is missing the test file:line reference in the traced-vars blurb"
        )
        assert "# at " not in body, (
            "Rendered body still carries the in-pre '# at …' console-style header"
        )

        tb_pos = body.find("RuntimeError: planned traced-vars failure")
        tv_pos = body.find("Traced Variables")
        assert 0 <= tb_pos < tv_pos, (
            "The 'Traced Variables' section must appear AFTER the traceback "
            f"(tb_pos={tb_pos}, tv_pos={tv_pos})"
        )

        strong_open = body.find("<strong>")
        strong_close = body.find("</strong>")
        assert strong_open != -1 and strong_close != -1, (
            "Rendered body is missing the <strong>…</strong> wrapper around the matching frame"
        )
        assert strong_open < strong_close, "<strong> must come before </strong>"
        strong_block = body[strong_open : strong_close + len("</strong>")]
        assert "test_email_themes.py" in strong_block, (
            "Bolded traceback line should reference the matching frame's filename, "
            f"got: {strong_block!r}"
        )
        assert " in _inner" in strong_block, (
            f"Bolded traceback line should reference function name '_inner', got: {strong_block!r}"
        )
        n_strong = body.count("<strong>")
        assert n_strong == 1, (
            f"Exactly one traceback frame line should be bolded, got {n_strong} <strong> tags"
        )


# --------------------------------------------------------------------------- #
# 2. Task wiring tests (create Tasks + log files)                              #
# --------------------------------------------------------------------------- #


class TestTaskEmailWiring(BaseTest):
    def test_task_wiring_propagates_style_palette_language(self) -> None:
        """smtp_config + non-default email_style attached to a Task must produce an
        email body that carries the chosen style, palette and language, and a subject
        carrying the language prefix."""
        smtp_cfg = SMTPConfig(
            mailhost=("smtp.enterprise.test", 25),
            fromaddr="alerts@enterprise.test",
            toaddrs=["oncall@enterprise.test"],
        )
        style_cfg = HTMLEmailStyle(style="modern", palette="catppuccin", language="es")

        def boom() -> None:
            raise RuntimeError("planned end-to-end failure")

        task = Task(
            name="wired",
            log_path=self._log("wired_task.log"),
            func=boom,
            smtp_config=smtp_cfg,
            email_style=style_cfg,
        )

        with patch("processes._email_internals.smtplib.SMTP") as mock_smtp_class:
            with Process([task]) as process:
                process.run(parallel=False)

        smtp_instance = mock_smtp_class.return_value
        assert smtp_instance.sendmail.call_count == 1, (
            "Failing task should trigger exactly one sendmail call"
        )
        _fromaddr, _toaddrs, msg = smtp_instance.sendmail.call_args.args
        body = _decode_mime_body(msg)

        assert 'class="card"' in body, (
            "Rendered email body is missing the 'modern' style marker class=\"card\""
        )
        assert "--accent: #8839ef" in body, (
            "Rendered email body is missing the 'catppuccin' palette marker --accent: #8839ef"
        )
        assert "Fallo en el pipeline: wired" in body, (
            "Rendered email body is missing the Spanish 'lang_failure_header'"
        )
        assert "Función" in body, "Rendered email body is missing the Spanish 'lang_function_label'"
        assert "planned end-to-end failure" in body

    def test_task_subject_carries_language_prefix(self) -> None:
        """The subject set on the handler in Task.__init__ must be the
        language-specific prefix followed by the task name."""
        smtp_cfg = SMTPConfig(
            mailhost=("smtp.enterprise.test", 25),
            fromaddr="alerts@enterprise.test",
            toaddrs=["oncall@enterprise.test"],
        )
        style_cfg = HTMLEmailStyle(language="de")

        def boom() -> None:
            raise RuntimeError("kaboom")

        task = Task(
            name="subject_de",
            log_path=self._log("subject_task.log"),
            func=boom,
            smtp_config=smtp_cfg,
            email_style=style_cfg,
        )

        with patch("processes._email_internals.smtplib.SMTP") as mock_smtp_class:
            with Process([task]) as process:
                process.run(parallel=False)

        smtp_instance = mock_smtp_class.return_value
        assert smtp_instance.sendmail.call_count == 1
        _fromaddr, _toaddrs, msg = smtp_instance.sendmail.call_args.args

        assert "Subject:" in msg
        assert _SUBJECT_MARKERS["de"] + "subject_de" in msg, (
            f"Expected subject containing {_SUBJECT_MARKERS['de']!r} + task name, "
            f"got message:\n{msg}"
        )

    def test_task_without_email_style_uses_defaults(self) -> None:
        """When smtp_config is provided but email_style is None, the handler uses
        the HTMLEmailStyle defaults (modern/neutral/en)."""
        smtp_cfg = SMTPConfig(
            mailhost=("smtp.test", 25),
            fromaddr="a@b.test",
            toaddrs=["c@d.test"],
        )

        def boom() -> None:
            raise RuntimeError("boom")

        task = Task(
            name="default_style",
            log_path=self._log("default_style_task.log"),
            func=boom,
            smtp_config=smtp_cfg,
        )

        with patch("processes._email_internals.smtplib.SMTP") as mock_smtp_class:
            with Process([task]) as process:
                process.run(parallel=False)

        smtp_instance = mock_smtp_class.return_value
        assert smtp_instance.sendmail.call_count == 1
        _fromaddr, _toaddrs, msg = smtp_instance.sendmail.call_args.args
        body = _decode_mime_body(msg)

        assert 'class="card"' in body, "Default 'modern' style marker missing"
        assert "--accent: #2563eb" in body, "Default 'neutral' palette marker missing"
        assert "Pipeline Failure:" in body, "Default English language marker missing"

    def test_two_tasks_sharing_smtp_config_get_independent_subjects(self) -> None:
        """Two tasks sharing one SMTPConfig must each get a handler with their own
        subject line — per-task isolation must be preserved."""
        smtp_cfg = SMTPConfig(
            mailhost=("smtp.test", 25),
            fromaddr="a@b.test",
            toaddrs=["c@d.test"],
        )

        def boom() -> None:
            raise RuntimeError("boom")

        task_a = Task(
            name="iso_task_a", log_path=self._log("iso_task_a.log"), func=boom, smtp_config=smtp_cfg
        )
        task_b = Task(
            name="iso_task_b", log_path=self._log("iso_task_b.log"), func=boom, smtp_config=smtp_cfg
        )
        try:
            email_handlers_a = [
                h for h in task_a.logger.handlers if isinstance(h, logging.handlers.SMTPHandler)
            ]
            email_handlers_b = [
                h for h in task_b.logger.handlers if isinstance(h, logging.handlers.SMTPHandler)
            ]

            assert len(email_handlers_a) == 1, "Task A should have exactly one email handler"
            assert len(email_handlers_b) == 1, "Task B should have exactly one email handler"
            assert email_handlers_a[0] is not email_handlers_b[0], (
                "The two tasks must have distinct handler instances"
            )
            assert email_handlers_a[0].subject.endswith("iso_task_a"), (
                f"Task A handler subject should end with task name, "
                f"got {email_handlers_a[0].subject!r}"
            )
            assert email_handlers_b[0].subject.endswith("iso_task_b"), (
                f"Task B handler subject should end with task name, "
                f"got {email_handlers_b[0].subject!r}"
            )
        finally:
            self._close_handlers(task_a, task_b)

    def test_no_smtp_config_attaches_no_email_handler(self) -> None:
        """When smtp_config is None, no email handler must be attached even if
        email_style is provided."""
        task = Task(
            name="no_smtp",
            log_path=self._log("no_smtp_task.log"),
            func=lambda: None,
            smtp_config=None,
            email_style=HTMLEmailStyle(style="classic"),
        )
        try:
            email_handlers = [
                h for h in task.logger.handlers if isinstance(h, logging.handlers.SMTPHandler)
            ]
            assert len(email_handlers) == 0, (
                f"No email handler should be attached when smtp_config is None, "
                f"got {len(email_handlers)}"
            )
        finally:
            self._close_handlers(task)
