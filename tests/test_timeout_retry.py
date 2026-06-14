"""Tests for per-task timeout and retry logic."""

from __future__ import annotations

import time

import pytest

from processes import Process, Task, TaskDependency

from .base_test import BaseTest


class TestTimeout(BaseTest):
    def test_timeout_fires(self) -> None:
        """A task that exceeds its timeout returns TaskResult(False, TimeoutError)."""

        def slow() -> str:
            time.sleep(0.3)
            return "done"

        task = Task("t_slow", slow, self._log("slow.log"), timeout=0.05)
        try:
            result = task.run()
        finally:
            self._close_handlers(task)

        assert not result.worked
        assert isinstance(result.exception, TimeoutError)
        assert "timed out" in str(result.exception)

    def test_timeout_not_triggered(self) -> None:
        """A task that finishes before the timeout succeeds normally."""

        def fast() -> int:
            return 42

        task = Task("t_fast", fast, self._log("fast.log"), timeout=5.0)
        try:
            result = task.run()
        finally:
            self._close_handlers(task)

        assert result.worked
        assert result.result == 42
        assert result.exception is None

    def test_timeout_in_sequential_process(self) -> None:
        """Timeout propagates through Process.run(parallel=False)."""

        def slow() -> str:
            time.sleep(0.3)
            return "done"

        task = Task("t_seq", slow, self._log("seq.log"), timeout=0.05)
        with Process([task]) as process:
            pr = process.run(parallel=False)

        assert "t_seq" in pr.failed_tasks
        assert "t_seq" in pr.errored_tasks
        assert isinstance(
            pr.passed_tasks_results.get("t_seq", None) or pr.failed_tasks, set
        )  # task did not pass

    def test_timeout_in_parallel_process(self) -> None:
        """Timeout propagates through Process.run(parallel=True)."""

        def slow() -> str:
            time.sleep(0.3)
            return "done"

        task = Task("t_par", slow, self._log("par.log"), timeout=0.05)
        with Process([task]) as process:
            pr = process.run(parallel=True)

        assert "t_par" in pr.failed_tasks
        assert "t_par" in pr.errored_tasks

    def test_timeout_cascades_to_dependants(self) -> None:
        """A timed-out task causes its dependants to be cascade-skipped."""

        def slow() -> str:
            time.sleep(0.3)
            return "ok"

        def child(x: str) -> str:
            return x.upper()

        t_root = Task("root", slow, self._log("root.log"), timeout=0.05)
        t_child = Task(
            "child",
            child,
            self._log("child.log"),
            dependencies=[TaskDependency("root", use_result_as_additional_args=True)],
        )
        with Process([t_root, t_child]) as process:
            pr = process.run(parallel=False)

        assert "root" in pr.errored_tasks
        assert "child" in pr.skipped_tasks
        assert "child" not in pr.passed_tasks_results

    # --- validation ---

    def test_timeout_zero_raises(self) -> None:
        with pytest.raises(TypeError, match="timeout must be a positive number"):
            Task("t", lambda: None, self._log("t.log"), timeout=0)

    def test_timeout_negative_raises(self) -> None:
        with pytest.raises(TypeError, match="timeout must be a positive number"):
            Task("t", lambda: None, self._log("t.log"), timeout=-1.0)

    def test_timeout_wrong_type_raises(self) -> None:
        with pytest.raises(TypeError, match="timeout must be a positive number"):
            Task("t", lambda: None, self._log("t.log"), timeout="30")  # type: ignore[arg-type]


class TestRetry(BaseTest):
    def test_retry_succeeds_on_second_attempt(self) -> None:
        """A task that fails once then succeeds is marked as passed."""
        calls: list[int] = []

        def flaky() -> str:
            calls.append(1)
            if len(calls) < 2:
                raise ConnectionError("transient")
            return "ok"

        task = Task("flaky", flaky, self._log("flaky.log"), retries=1)
        try:
            result = task.run()
        finally:
            self._close_handlers(task)

        assert result.worked
        assert result.result == "ok"
        assert len(calls) == 2

    def test_retry_exhausted_returns_failed(self) -> None:
        """A task that fails all attempts returns TaskResult(False, ...)."""
        calls: list[int] = []

        def always_fails() -> None:
            calls.append(1)
            raise ConnectionError("permanent")

        task = Task("perm", always_fails, self._log("perm.log"), retries=2)
        try:
            result = task.run()
        finally:
            self._close_handlers(task)

        assert not result.worked
        assert isinstance(result.exception, ConnectionError)
        assert len(calls) == 3  # 1 original + 2 retries

    def test_retry_zero_means_no_retry(self) -> None:
        """retries=0 (default) never retries, even for a retryable exception."""
        calls: list[int] = []

        def fail_once() -> None:
            calls.append(1)
            raise ConnectionError("boom")

        task = Task("no_retry", fail_once, self._log("nr.log"), retries=0)
        try:
            result = task.run()
        finally:
            self._close_handlers(task)

        assert not result.worked
        assert len(calls) == 1

    def test_retry_none_treated_as_zero(self) -> None:
        """retries=None is normalised to 0 — no retry."""
        calls: list[int] = []

        def fail_once() -> None:
            calls.append(1)
            raise ConnectionError("boom")

        task = Task("none_retry", fail_once, self._log("nr2.log"), retries=None)
        try:
            result = task.run()
        finally:
            self._close_handlers(task)

        assert not result.worked
        assert len(calls) == 1

    def test_retry_non_retryable_exception_skips_retry(self) -> None:
        """A ValueError is not in the default retry_on — no retry fires."""
        calls: list[int] = []

        def logic_error() -> None:
            calls.append(1)
            raise ValueError("bad input")

        task = Task("le", logic_error, self._log("le.log"), retries=3)
        try:
            result = task.run()
        finally:
            self._close_handlers(task)

        assert not result.worked
        assert isinstance(result.exception, ValueError)
        assert len(calls) == 1  # retried 0 times despite retries=3

    def test_retry_custom_retry_on(self) -> None:
        """Only exceptions matching retry_on trigger a retry."""
        calls: list[int] = []

        def flaky() -> str:
            calls.append(1)
            if len(calls) < 3:
                raise RuntimeError("transient runtime")
            return "ok"

        task = Task(
            "custom",
            flaky,
            self._log("custom.log"),
            retries=3,
            retry_on=(RuntimeError,),
        )
        try:
            result = task.run()
        finally:
            self._close_handlers(task)

        assert result.worked
        assert len(calls) == 3

    def test_retry_default_catches_connection_error(self) -> None:
        """With retries=1, retry_on=None: ConnectionError is retried by default."""
        calls: list[int] = []

        def flaky() -> str:
            calls.append(1)
            if len(calls) == 1:
                raise ConnectionError("refused")
            return "connected"

        task = Task("conn", flaky, self._log("conn.log"), retries=1, retry_on=None)
        try:
            result = task.run()
        finally:
            self._close_handlers(task)

        assert result.worked
        assert len(calls) == 2

    def test_retry_in_process_run(self) -> None:
        """Retry logic works end-to-end inside Process.run()."""
        calls: list[int] = []

        def flaky() -> str:
            calls.append(1)
            if len(calls) < 2:
                raise ConnectionError("transient")
            return "ok"

        task = Task("proc_retry", flaky, self._log("pr.log"), retries=1)
        with Process([task]) as process:
            pr = process.run(parallel=False)

        assert "proc_retry" in pr.passed_tasks_results
        assert pr.passed_tasks_results["proc_retry"].result == "ok"
        assert len(calls) == 2

    # --- validation ---

    def test_retries_negative_raises(self) -> None:
        with pytest.raises(TypeError, match="retries must be a non-negative int"):
            Task("t", lambda: None, self._log("t.log"), retries=-1)

    def test_retry_on_string_raises(self) -> None:
        with pytest.raises(TypeError, match="retry_on must be None or a tuple"):
            Task("t", lambda: None, self._log("t.log"), retries=1, retry_on="ConnectionError")  # type: ignore[arg-type]

    def test_retry_on_non_exception_raises(self) -> None:
        with pytest.raises(TypeError, match="retry_on must be None or a tuple"):
            Task(
                "t", lambda: None, self._log("t.log"), retries=1, retry_on=(int,)
            )  # int is not an Exception subclass


class TestTimeoutWithRetry(BaseTest):
    def test_timeout_retried_with_default_retry_on(self) -> None:
        """TimeoutError is in the default retry_on — a timed-out task is retried."""
        calls: list[int] = []

        def eventually_fast() -> str:
            calls.append(1)
            if len(calls) == 1:
                time.sleep(0.3)  # First call: too slow
            return "fast"

        task = Task(
            "t_retry_timeout",
            eventually_fast,
            self._log("trt.log"),
            timeout=0.05,
            retries=1,
        )
        try:
            result = task.run()
        finally:
            self._close_handlers(task)

        assert result.worked
        assert result.result == "fast"
        assert len(calls) == 2

    def test_timeout_retry_exhausted(self) -> None:
        """All attempts time out → task fails with TimeoutError."""
        calls: list[int] = []

        def always_slow() -> str:
            calls.append(1)
            time.sleep(0.3)
            return "done"

        task = Task(
            "t_all_timeout",
            always_slow,
            self._log("tat.log"),
            timeout=0.05,
            retries=2,
        )
        try:
            result = task.run()
        finally:
            self._close_handlers(task)

        assert not result.worked
        assert isinstance(result.exception, TimeoutError)
        assert len(calls) == 3  # 1 original + 2 retries
