"""Mutating a Process after construction: add_task, remove_task, add_task_dependency.

Each mutation re-validates and re-sorts the graph and is atomic: an invalid
mutation leaves the process unchanged and runnable.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest

from processes import Process, Task, TaskDependency, TaskStatus
from processes.exceptions import (
    CircularDependencyError,
    DependencyNotFoundError,
    TaskNotFoundError,
)

from .base_test import BaseTest


class TestProcessMutation(BaseTest):
    def _t(self, name: str, func: Callable[..., Any] | None = None) -> Task:
        return Task(name, func or (lambda: name), self._log(f"{name}.log"))

    # --- add_task ---------------------------------------------------------

    def test_add_task_runs(self) -> None:
        with Process([self._t("a")]) as p:
            p.add_task(self._t("b"))
            report = p.run(parallel=False)
        assert report.entries["b"].status == TaskStatus.SUCCESS

    def test_add_task_rejects_duplicate_name(self) -> None:
        with Process([self._t("a")]) as p:
            with pytest.raises(ValueError):
                p.add_task(self._t("a"))
            report = p.run(parallel=False)  # unchanged, still runnable
        assert set(report.successes) == {"a"}

    def test_add_task_missing_dependency_is_atomic(self) -> None:
        bad = Task("b", lambda: 1, self._log("b.log"), dependencies=[TaskDependency("ghost")])
        with Process([self._t("a")]) as p:
            with pytest.raises(DependencyNotFoundError):
                p.add_task(bad)
            report = p.run(parallel=False)
        assert "b" not in report.entries
        assert report.entries["a"].status == TaskStatus.SUCCESS
        self._close_handlers(bad)

    # --- remove_task ------------------------------------------------------

    def test_remove_leaf_task(self) -> None:
        with Process([self._t("a"), self._t("b")]) as p:
            p.remove_task("b")
            report = p.run(parallel=False)
        assert "b" not in report.entries
        assert "a" in report.entries

    def test_remove_task_with_dependents_rejected(self) -> None:
        a = self._t("a")
        b = Task(
            "b",
            lambda x: x,
            self._log("b.log"),
            dependencies=[TaskDependency("a", use_result_as_additional_args=True)],
        )
        with Process([a, b]) as p:
            with pytest.raises(ValueError):
                p.remove_task("a")
            report = p.run(parallel=False)
        assert report.entries["b"].status == TaskStatus.SUCCESS

    def test_remove_missing_task_raises(self) -> None:
        with Process([self._t("a")]) as p:
            with pytest.raises(TaskNotFoundError):
                p.remove_task("ghost")

    def test_remove_closes_logger_handlers(self) -> None:
        a, b = self._t("a"), self._t("b")
        with Process([a, b]) as p:
            assert b.logger.handlers  # FileHandler from log_path
            p.remove_task("b")
            assert not b.logger.handlers  # closed and detached

    # --- add_task_dependency ---------------------------------------------

    def test_add_dependency_flows_result(self) -> None:
        producer = Task("producer", lambda: 7, self._log("producer.log"))
        consumer = Task("consumer", lambda x=0: x * 2, self._log("consumer.log"))
        with Process([producer, consumer]) as p:
            p.add_task_dependency(
                "consumer",
                TaskDependency(
                    "producer",
                    use_result_as_additional_kwargs=True,
                    additional_kwarg_name="x",
                ),
            )
            report = p.run(parallel=False)
        assert report.entries["consumer"].result == 14

    def test_add_duplicate_dependency_rejected(self) -> None:
        producer = Task("producer", lambda: 1, self._log("producer.log"))
        consumer = Task(
            "consumer",
            lambda x=0: x,
            self._log("consumer.log"),
            dependencies=[
                TaskDependency(
                    "producer", use_result_as_additional_kwargs=True, additional_kwarg_name="x"
                )
            ],
        )
        with Process([producer, consumer]) as p:
            with pytest.raises(ValueError):
                p.add_task_dependency("consumer", TaskDependency("producer"))
            assert len(consumer.dependencies) == 1  # not doubled

    def test_add_dependency_cycle_is_atomic(self) -> None:
        a = Task("a", lambda x=0: x, self._log("a.log"))
        b = Task(
            "b",
            lambda x=0: x,
            self._log("b.log"),
            dependencies=[
                TaskDependency("a", use_result_as_additional_kwargs=True, additional_kwarg_name="x")
            ],
        )
        with Process([a, b]) as p:
            with pytest.raises(CircularDependencyError):
                p.add_task_dependency("a", TaskDependency("b"))  # a<->b cycle
            report = p.run(parallel=False)  # rolled back, still runnable
        assert report.entries["b"].status == TaskStatus.SUCCESS
        assert len(a.dependencies) == 0
