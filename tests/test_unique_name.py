import pytest

from processes import Process, Task, TaskDependency

from .base_test import BaseTest


class TestNameNormalization(BaseTest):
    def test_name_lowercased_on_construction(self) -> None:
        t = Task("Fetch_Data", lambda: 1, self._log("norm.log"))
        try:
            assert t.name == "fetch_data"
            assert TaskDependency("Fetch_Data").task_name == "fetch_data"
        finally:
            self._close_handlers(t)

    def test_duplicate_names_detected_case_insensitively(self) -> None:
        t1 = Task("Fetch", lambda: 1, self._log("ci1.log"))
        t2 = Task("fetch", lambda: 2, self._log("ci2.log"))
        with pytest.raises(ValueError, match="Duplicate task name: fetch"):
            with Process([t1, t2]) as _:
                pass

    def test_dependency_resolves_across_case(self) -> None:
        """A dependency referencing a differently-cased upstream still resolves
        and its result is injected — no DependencyNotFoundError."""
        producer = Task("Producer", lambda: 21, self._log("prod.log"))
        consumer = Task(
            "Consumer",
            lambda upstream: upstream * 2,
            self._log("cons.log"),
            dependencies=[TaskDependency("PRODUCER", use_result_as_additional_args=True)],
        )
        with Process([producer, consumer]) as process:
            report = process.run()
        assert report.entries["consumer"].result == 42


class TestUniqueName(BaseTest):
    def test_unique_name(self) -> None:
        def task_1() -> int:
            return 1

        def task_2() -> int:
            return 2

        def task_3(t2_res: int) -> int:
            return 3 + t2_res

        tasks: list[Task] = []
        try:
            t1 = Task("task_1", task_1, self._log("logfile_12.log"))
            tasks.append(t1)
            t2 = Task("task_2", task_2, self._log("logfile_12.log"))
            tasks.append(t2)
            t3 = Task("task_2", task_3, self._log("logfile_3.log"), args=(1,))
            tasks.append(t3)
        except Exception as e:
            self._close_handlers(*tasks)
            pytest.fail(f"Unexpected exception: {e}")

        with pytest.raises(ValueError, match="Duplicate task name: task_2"):
            with Process(tasks) as _:
                pass

        tasks[-1].name = "task_3"
        try:
            with Process(tasks) as _:
                pass
        except Exception as e:
            pytest.fail(f"Unexpected exception: {e}")
