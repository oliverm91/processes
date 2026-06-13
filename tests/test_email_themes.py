"""Tests for the themed HTML email alert system.

Covers:

*   The 9 ``(email_style, color_palette)`` combinations render a fully
    substituted HTML body that pulls the palette's CSS variables into the
    style at the ``{{__palette_css__}}`` marker and carries the style's
    distinctive markup.
*   Every (style, palette, language) combination renders a body in the
    target language — a language-specific marker from each translation
    file must appear in the output.
*   Constructor validation on both ``HTMLSMTPHandler`` and
    ``ExceptionHTMLFormatter`` — unknown style/palette/language names
    must raise ``ValueError`` at construction time, not at first emit.
*   The handler → formatter wiring inside ``Task._setup_logger``: setting
    ``email_style``, ``color_palette`` and ``email_language`` on a handler
    attached to a ``Task`` must propagate through the runtime formatter
    so the rendered email body and subject carry the chosen options.
"""

from __future__ import annotations

import logging
import os
from email import message_from_string
from unittest.mock import patch

from processes import HTMLSMTPHandler, Process, Task
from processes.html_logging import ExceptionHTMLFormatter

from .log_cleaner import clean_tasks_logs

_CURDIR = os.path.dirname(__file__)


def _decode_mime_body(msg: str) -> str:
    """Decode the base64 HTML body from a sendmail payload."""
    parsed = message_from_string(msg)
    payload = parsed.get_payload(decode=True) or b""
    return payload.decode("utf-8", errors="replace")

# Style-specific markers that must appear in the rendered body to prove
# the chosen style layout is actually in use (not just the default).
_STYLE_MARKERS = {
    "classic": ["<h1>Pipeline Failure:", "class=\"impact\"", "class=\"traceback\""],
    "modern": ["class=\"card\"", "class=\"header\"", "class=\"alert\""],
    "compact": ["[failure]", "[Function]", "[Downstream Impact]", "[Traceback]"],
}

# A distinguishing substring from each palette's :root variable block.
_PALETTE_MARKERS = {
    "neutral": "--accent: #2563eb",
    "catppuccin": "--accent: #8839ef",
    "neobones": "--bg-page: #f3efec",
    "slate": "--bg-page: #1e293b",
}

_STYLES = ("classic", "modern", "compact")
_PALETTES = ("neutral", "catppuccin", "neobones", "slate")
_LANGUAGES = ("en", "es", "pt", "fr", "de", "it")

# A translation-unique substring for each language that must appear in
# the rendered body when that language is selected.
_LANGUAGE_MARKERS = {
    "en": ["Pipeline Failure:", "Function", "Downstream Impact"],
    "es": ["Fallo en el pipeline:", "Función", "Impacto en tareas dependientes"],
    "pt": ["Falha no pipeline:", "Função", "Impacto nas tarefas dependentes"],
    "fr": ["Échec du pipeline :", "Fonction", "Impact sur les tâches dépendantes"],
    "de": ["Pipeline-Fehlschlag:", "Funktion", "Auswirkung auf nachgelagerte Aufgaben"],
    "it": ["Fallimento del pipeline:", "Funzione", "Impatto sulle attività dipendenti"],
}

# The default subject prefix for each language (must end with a separator).
_SUBJECT_MARKERS = {
    "en": "Error in task ",
    "es": "Error en la tarea ",
    "pt": "Erro na tarefa ",
    "fr": "Erreur dans la tâche ",
    "de": "Fehler in Aufgabe ",
    "it": "Errore nell'attività ",
}

# All 7 content placeholders that every template must declare and that
# ``format()`` must substitute — no ``{{xxx}}`` may remain in the output.
_CONTENT_KEYS = (
    "task_name",
    "function",
    "args",
    "kwargs",
    "exception",
    "traceback",
    "downstream_items",
)

# All language placeholders that every template uses.
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
# 1. The 12 (style, palette, language) render combinations                       #
# --------------------------------------------------------------------------- #


def test_every_style_palette_renders_complete_substitution() -> None:
    """Every (style, palette) pair must render with all 7 placeholders filled."""
    for style in _STYLES:
        for palette in _PALETTES:
            formatter = ExceptionHTMLFormatter(
                email_style=style, color_palette=palette
            )
            output = formatter.format(_make_record(f"task_{style}_{palette}"))

            # (a) All 7 content placeholders are substituted — no {{xxx}} remains.
            for key in _CONTENT_KEYS:
                placeholder = "{{" + key + "}}"
                assert placeholder not in output, (
                    f"[{style}/{palette}] placeholder {placeholder!r} "
                    f"was not substituted"
                )

            # (b) The palette marker has been replaced with the palette's CSS
            # (so the palette's distinguishing --accent/--bg-page value appears).
            assert "{{__palette_css__}}" not in output, (
                f"[{style}/{palette}] palette marker was not injected"
            )
            assert _PALETTE_MARKERS[palette] in output, (
                f"[{style}/{palette}] palette marker "
                f"{_PALETTE_MARKERS[palette]!r} not found in rendered body"
            )

            # (c) At least one style-specific marker is present.
            for marker in _STYLE_MARKERS[style]:
                assert marker in output, (
                    f"[{style}/{palette}] style marker {marker!r} not found"
                )


def test_every_language_renders_translated_body() -> None:
    """For each supported language, the body must carry that language's text
    across all (style, palette) combinations."""
    for language in _LANGUAGES:
        for style in _STYLES:
            for palette in _PALETTES:
                formatter = ExceptionHTMLFormatter(
                    email_style=style,
                    color_palette=palette,
                    email_language=language,
                )
                output = formatter.format(
                    _make_record(f"task_{language}_{style}_{palette}")
                )

                # No language placeholder may remain unsubstituted.
                for key in _LANG_CONTENT_KEYS:
                    placeholder = "{{" + key + "}}"
                    assert placeholder not in output, (
                        f"[{language}/{style}/{palette}] placeholder "
                        f"{placeholder!r} was not substituted"
                    )

                # At least one language-distinctive marker must be in the body.
                markers = _LANGUAGE_MARKERS[language]
                assert any(marker in output for marker in markers), (
                    f"[{language}/{style}/{palette}] no language marker "
                    f"from {markers!r} found in rendered body"
                )


# --------------------------------------------------------------------------- #
# 2. Constructor validation                                                    #
# --------------------------------------------------------------------------- #


def test_formatter_rejects_unknown_email_style() -> None:
    import pytest

    with pytest.raises(ValueError, match="email_style must be one of"):
        ExceptionHTMLFormatter(email_style="neon")


def test_formatter_rejects_unknown_color_palette() -> None:
    import pytest

    with pytest.raises(ValueError, match="color_palette must be one of"):
        ExceptionHTMLFormatter(color_palette="rainbow")


def test_formatter_rejects_unknown_email_language() -> None:
    import pytest

    with pytest.raises(ValueError, match="email_language must be one of"):
        ExceptionHTMLFormatter(email_language="klingon")


def test_formatter_default_language_is_english() -> None:
    formatter = ExceptionHTMLFormatter()
    output = formatter.format(_make_record())
    assert "Pipeline Failure:" in output
    assert "Function" in output


def test_handler_rejects_unknown_email_style() -> None:
    import pytest

    with pytest.raises(ValueError, match="email_style must be one of"):
        HTMLSMTPHandler(
            mailhost=("smtp.test", 25),
            fromaddr="a@b.test",
            toaddrs=["c@d.test"],
            email_style="neon",
        )


def test_handler_rejects_unknown_color_palette() -> None:
    import pytest

    with pytest.raises(ValueError, match="color_palette must be one of"):
        HTMLSMTPHandler(
            mailhost=("smtp.test", 25),
            fromaddr="a@b.test",
            toaddrs=["c@d.test"],
            color_palette="rainbow",
        )


def test_handler_rejects_unknown_email_language() -> None:
    import pytest

    with pytest.raises(ValueError, match="email_language must be one of"):
        HTMLSMTPHandler(
            mailhost=("smtp.test", 25),
            fromaddr="a@b.test",
            toaddrs=["c@d.test"],
            email_language="klingon",
        )


def test_handler_copy_propagates_theme_kwargs() -> None:
    """``copy()`` must preserve email_style, color_palette and email_language."""
    original = HTMLSMTPHandler(
        mailhost=("smtp.test", 25),
        fromaddr="a@b.test",
        toaddrs=["c@d.test"],
        email_style="modern",
        color_palette="slate",
        email_language="fr",
    )
    clone = original.copy()
    assert clone.email_style == "modern"
    assert clone.color_palette == "slate"
    assert clone.email_language == "fr"


# --------------------------------------------------------------------------- #
# 3. Handler → formatter wiring (end-to-end through Task._setup_logger)        #
# --------------------------------------------------------------------------- #


def test_handler_to_formatter_wiring_under_task() -> None:
    """A handler with non-default themes attached to a Task must produce an
    email body that carries the chosen style, palette and language, and
    a subject carrying the language prefix."""
    clean_tasks_logs()
    log_path = os.path.join(_CURDIR, "wired_task.log")

    handler = HTMLSMTPHandler(
        mailhost=("smtp.enterprise.test", 25),
        fromaddr="alerts@enterprise.test",
        toaddrs=["oncall@enterprise.test"],
        email_style="modern",
        color_palette="catppuccin",
        email_language="es",
    )

    def boom() -> None:
        raise RuntimeError("planned end-to-end failure")

    try:
        task = Task(name="wired", log_path=log_path, func=boom, html_mail_handler=handler)

        with patch("processes.html_logging.smtplib.SMTP") as mock_smtp_class:
            with Process([task]) as process:
                process.run(parallel=False)

        smtp_instance = mock_smtp_class.return_value
        assert smtp_instance.sendmail.call_count == 1, (
            "Failing task should trigger exactly one sendmail call"
        )
        _fromaddr, _toaddrs, msg = smtp_instance.sendmail.call_args.args
        body = _decode_mime_body(msg)

        # Style marker: modern template uses class="card" for the main wrapper.
        assert 'class="card"' in body, (
            "Rendered email body is missing the 'modern' style marker "
            "class=\"card\" — handler kwargs were not propagated to the "
            "formatter inside Task._setup_logger"
        )

        # Palette marker: catppuccin palette sets --accent: #8839ef.
        assert "--accent: #8839ef" in body, (
            "Rendered email body is missing the 'catppuccin' palette marker "
            "--accent: #8839ef — handler kwargs were not propagated to the "
            "formatter inside Task._setup_logger"
        )

        # Language marker: Spanish subject prefix and a Spanish body label.
        assert "Fallo en el pipeline: wired" in body, (
            "Rendered email body is missing the Spanish 'lang_failure_header' "
            "— handler email_language was not propagated to the formatter"
        )
        assert "Función" in body, (
            "Rendered email body is missing the Spanish 'lang_function_label' "
            "— handler email_language was not propagated to the formatter"
        )

        # Sanity: the failure metadata still surfaces.
        assert "planned end-to-end failure" in body
    finally:
        clean_tasks_logs()
        if os.path.isfile(log_path):
            os.remove(log_path)



def test_handler_subject_carries_language_prefix() -> None:
    """The subject set on the handler in Task._setup_logger must be the
    language-specific prefix followed by the task name."""
    clean_tasks_logs()
    log_path = os.path.join(_CURDIR, "subject_task.log")

    handler = HTMLSMTPHandler(
        mailhost=("smtp.enterprise.test", 25),
        fromaddr="alerts@enterprise.test",
        toaddrs=["oncall@enterprise.test"],
        email_language="de",
    )

    def boom() -> None:
        raise RuntimeError("kaboom")

    try:
        task = Task(name="subject_de", log_path=log_path, func=boom, html_mail_handler=handler)

        with patch("processes.html_logging.smtplib.SMTP") as mock_smtp_class:
            with Process([task]) as process:
                process.run(parallel=False)

        smtp_instance = mock_smtp_class.return_value
        assert smtp_instance.sendmail.call_count == 1
        _fromaddr, _toaddrs, msg = smtp_instance.sendmail.call_args.args

        # The MIME-encoded subject must contain the German prefix + task name.
        assert "Subject:" in msg
        # Decode the subject header line; the value is RFC 2047 if non-ASCII
        # but our German prefix is plain ASCII, so a substring match is enough.
        assert _SUBJECT_MARKERS["de"] + "subject_de" in msg, (
            f"Expected subject containing {_SUBJECT_MARKERS['de']!r} + task name, "
            f"got message:\n{msg}"
        )
    finally:
        clean_tasks_logs()
        if os.path.isfile(log_path):
            os.remove(log_path)
