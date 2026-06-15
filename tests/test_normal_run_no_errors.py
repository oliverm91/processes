import time

import pytest

from processes import Process, Task, TaskDependency

from .base_test import BaseTest


def task_1() -> int:
    time.sleep(1)
    return 1


def task_2() -> int:
    time.sleep(0.5)
    return 2


def task_3(input: int) -> int:
    time.sleep(0.25)
    return input


def task_4(t2_res: int) -> int:
    time.sleep(1.25)
    return 3 + t2_res


def task_5(t1_res: int) -> int:
    time.sleep(0.75)
    return 4 + t1_res


def task_6(t2_res: int, t5_res: int) -> int:
    time.sleep(0.25)
    return t2_res + t5_res


@pytest.fixture
def fast_sleep(monkeypatch: pytest.MonkeyPatch) -> None:
    """Replace ``time.sleep`` with a no-op for tests that don't measure wall time."""
    monkeypatch.setattr(time, "sleep", lambda *_args, **_kwargs: None)


class TestNormalRun(BaseTest):
    def test_run_single_task_sequential(self, fast_sleep: None) -> None:
        t1 = Task("task_1", task_1, self._log("logfile_1.log"))
        with Process([t1]) as process:
            process.run(parallel=False)
        assert True

    def test_run_single_task_parallel(self, fast_sleep: None) -> None:
        t1 = Task("task_1", task_1, self._log("logfile_1.log"))
        with Process([t1]) as process:
            process.run(parallel=True)
        assert True

    def test_run_independent_tasks_sequential(self, fast_sleep: None) -> None:
        t1 = Task("task_1", task_1, self._log("logfile_1.log"))
        t2 = Task("task_2", task_2, self._log("logfile_1.log"))
        with Process([t1, t2]) as process:
            process.run(parallel=False)
        assert True

    def test_run_independent_tasks_parallel(self, fast_sleep: None) -> None:
        t1 = Task("task_1", task_1, self._log("logfile_1.log"))
        t2 = Task("task_2", task_2, self._log("logfile_1.log"))
        with Process([t1, t2]) as process:
            process.run(parallel=True)
        assert True

    def _build_dependent_task_graph(self) -> list[Task]:
        """Six-task graph: t1, t2 independent → t4(t2), t5(t1) → t6(t2,t5); t3 standalone."""
        log = self._log("logfile_1.log")
        return [
            Task("task_1", task_1, log),
            Task("task_2", task_2, log),
            Task("task_3", task_3, log, args=(1,)),
            Task(
                "task_4",
                task_4,
                log,
                dependencies=[TaskDependency("task_2", use_result_as_additional_args=True)],
            ),
            Task(
                "task_5",
                task_5,
                log,
                dependencies=[TaskDependency("task_1", use_result_as_additional_args=True)],
            ),
            Task(
                "task_6",
                task_6,
                log,
                dependencies=[
                    TaskDependency("task_2", use_result_as_additional_args=True),
                    TaskDependency("task_5", use_result_as_additional_args=True),
                ],
            ),
        ]

    def test_run_dependent_tasks_sequential(self) -> None:
        with Process(self._build_dependent_task_graph()) as process:
            t_start = time.time()
            report = process.run(parallel=False)
            t_end = time.time()

        assert len(report.successes) == 6, f"Expected 6 passed tasks. Got {len(report.successes)}"
        assert len(report.errored) + len(report.skipped) == 0, (
            f"Expected 0 failed tasks. Got {len(report.errored) + len(report.skipped)}"
        )
        elapsed = t_end - t_start
        assert 4.0 <= elapsed < 4.8, f"Sequential run took {elapsed} seconds. Expected ~4 seconds."

    def test_run_dependent_tasks_parallel(self) -> None:
        import os

        n_workers = os.cpu_count()
        with Process(self._build_dependent_task_graph()) as process:
            t_start = time.time()
            report = process.run(parallel=True, max_workers=n_workers)
            t_end = time.time()

        assert len(report.successes) == 6, f"Expected 6 passed tasks. Got {len(report.successes)}"
        assert len(report.errored) + len(report.skipped) == 0, (
            f"Expected 0 failed tasks. Got {len(report.errored) + len(report.skipped)}"
        )
        if n_workers and n_workers > 2:
            assert int(round(t_end - t_start, 0)) == 2, (
                f"Parallel run took {t_end - t_start} seconds. Expected 2 seconds."
            )
