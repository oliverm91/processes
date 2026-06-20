"""Report HTML rendering (palette + language), HTMLEmailStyle validation, and
traced-variables capture driven by ``Task.traced_vars_frame_filter``.

The per-task streaming email was removed; what survives is the report renderer
(``_build_report_html``, honoring palette + language only) and the capture-time
frame filter, which now lives on ``Task`` and feeds both the report and the
logfile.
"""

from __future__ import annotations

import json

import pytest

from processes import (
    HTMLEmailStyle,
    ProcessExecutionReport,
    ReportContent,
    Task,
    TaskReportEntry,
    TaskStatus,
)
from processes.comms._email import _build_report_html

# Apostrophe-free per-language marker (the summary-section title), so the
# html-escaped output still contains it verbatim.
_LANGUAGE_MARKERS = {
    "en": "Summary",
    "es": "Resumen",
    "pt": "Resumo",
    "fr": "Résumé",
    "de": "Zusammenfassung",
    "it": "Riepilogo",
}

_PALETTE_MARKERS = {
    "neutral": "--accent: #2563eb",
    "catppuccin": "--accent: #8839ef",
    "neobones": "--bg-page: #f3efec",
    "slate": "--bg-page: #1e293b",
}


def _one_task_report() -> ProcessExecutionReport:
    return ProcessExecutionReport(
        {
            "t": TaskReportEntry(
                name="t",
                function="f",
                args=(),
                kwargs={},
                status=TaskStatus.SUCCESS,
                elapsed_seconds=0.0,
                attempts=1,
            )
        }
    )


# ---------------------------------------------------------------------------
# HTMLEmailStyle validation
# ---------------------------------------------------------------------------


class TestHTMLEmailStyle:
    def test_defaults_to_neutral_english(self) -> None:
        style = HTMLEmailStyle()
        assert style.palette == "neutral"
        assert style.language == "en"

    def test_rejects_unknown_palette(self) -> None:
        with pytest.raises(ValueError, match="palette must be one of"):
            HTMLEmailStyle(palette="rainbow")

    def test_rejects_unknown_language(self) -> None:
        with pytest.raises(ValueError, match="language must be one of"):
            HTMLEmailStyle(language="klingon")


# ---------------------------------------------------------------------------
# Report HTML rendering
# ---------------------------------------------------------------------------


class TestReportRendering:
    def test_renders_every_language(self) -> None:
        report = _one_task_report()
        for language, marker in _LANGUAGE_MARKERS.items():
            html = _build_report_html(
                report, HTMLEmailStyle(language=language), ReportContent(), errors_only=False
            )
            assert marker in html, f"[{language}] marker {marker!r} not found in report body"

    def test_injects_every_palette(self) -> None:
        report = _one_task_report()
        for palette, marker in _PALETTE_MARKERS.items():
            html = _build_report_html(
                report, HTMLEmailStyle(palette=palette), ReportContent(), errors_only=False
            )
            assert "{{__palette_css__}}" not in html, f"[{palette}] palette marker not injected"
            assert marker in html, f"[{palette}] CSS marker {marker!r} not found"


# ---------------------------------------------------------------------------
# Traced-variables capture via Task.traced_vars_frame_filter
# ---------------------------------------------------------------------------


class TestTracedVarsCapture:
    def test_default_filter_captures_outermost_user_frame(self) -> None:
        def boom() -> None:
            marker_local = "frame_marker_value"
            raise RuntimeError(f"kaboom ({marker_local})")

        result = Task("boom", boom).run()

        assert result.status == TaskStatus.ERRORED
        assert result.error_data is not None
        assert "marker_local" in result.error_data.traced_vars
        assert result.error_data.traced_vars["marker_local"] == "'frame_marker_value'"

    def test_default_filter_skips_stdlib_frame(self) -> None:
        def decode() -> None:
            payload = '{"bad"'
            json.loads(payload)

        result = Task("decode", decode).run()

        assert result.status == TaskStatus.ERRORED
        assert result.error_data is not None
        # default selects the user frame, not json's internals
        assert "json" not in result.error_data.traced_vars_location
        assert "payload" in result.error_data.traced_vars

    def test_custom_filter_targets_named_frame(self) -> None:
        def decode() -> None:
            json.loads('{"bad"')

        result = Task("decode", decode, traced_vars_frame_filter="json").run()

        assert result.status == TaskStatus.ERRORED
        assert result.error_data is not None
        # the custom filter pins capture to the stdlib json frame
        assert "json" in result.error_data.traced_vars_location

    def test_frame_filter_must_be_str_or_none(self) -> None:
        with pytest.raises(TypeError, match="traced_vars_frame_filter must be a str or None"):
            Task("bad", lambda: None, traced_vars_frame_filter=123)  # type: ignore[arg-type]
