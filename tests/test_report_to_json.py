"""``ProcessExecutionReport.to_json`` must serialize every field losslessly.

Exotic values (enums, the nested ErrorData, arbitrary objects in result) must be
rendered faithfully instead of dropped or raising.
"""

from __future__ import annotations

import json

from processes import Process, Task, TaskDependency, TaskStatus

from .base_test import BaseTest

_ENTRY_FIELDS = {
    "name",
    "function",
    "args",
    "kwargs",
    "status",
    "elapsed_seconds",
    "attempts",
    "result",
    "error",
}


class _Custom:
    def __repr__(self) -> str:
        return "<Custom obj>"


def _ok() -> dict[str, object]:
    return {"k": 1, "nested": [1, 2]}


def _returns_obj() -> _Custom:
    return _Custom()


def _boom() -> None:
    raise ValueError("nope")


class TestReportToJson(BaseTest):
    def test_to_json_is_complete_and_lossless(self) -> None:
        ok = Task("ok", _ok, self._log("ok.log"))
        obj = Task("obj", _returns_obj, self._log("obj.log"))
        boom = Task("boom", _boom, self._log("boom.log"))
        down = Task(
            "down",
            lambda x=None: x,
            self._log("down.log"),
            dependencies=[
                TaskDependency(
                    "boom", use_result_as_additional_kwargs=True, additional_kwarg_name="x"
                )
            ],
        )
        with Process([ok, obj, boom, down]) as p:
            report = p.run(parallel=False)

        data = json.loads(report.to_json())
        entries = data["entries"]

        # No task and no field is dropped.
        assert set(entries) == {"ok", "obj", "boom", "down"}
        for entry in entries.values():
            assert set(entry) == _ENTRY_FIELDS

        # Enum serialized as its string value.
        assert entries["ok"]["status"] == TaskStatus.SUCCESS.value == "success"
        assert entries["boom"]["status"] == "errored"
        assert entries["down"]["status"] == "skipped"

        # JSON-native result preserved exactly; exotic result kept via repr.
        assert entries["ok"]["result"] == {"k": 1, "nested": [1, 2]}
        assert entries["obj"]["result"] == "<Custom obj>"

        # Nested ErrorData fully captured for the failure.
        err = entries["boom"]["error"]
        assert err is not None
        assert "nope" in err["exception"]
        assert err["traceback_str"]
        assert "down" in err["downstream_impact"]

        # Non-errored tasks carry a null error; skipped task has no result.
        assert entries["ok"]["error"] is None
        assert entries["down"]["result"] is None

    def test_to_json_indent_produces_valid_json(self) -> None:
        ok = Task("ok", _ok, self._log("ok.log"))
        with Process([ok]) as p:
            report = p.run(parallel=False)

        pretty = report.to_json(indent=2)
        assert "\n" in pretty
        json.loads(pretty)  # parses without error
