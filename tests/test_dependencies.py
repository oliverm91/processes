import pytest

from processes import (
    CircularDependencyError,
    DependencyNotFoundError,
    Process,
    Task,
    TaskDependency,
)

from .base_test import BaseTest


class TestDependencies(BaseTest):
    def test_present_dependencies(self) -> None:
        """Test the presence of dependencies."""

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
            t2 = Task(
                "task_2",
                task_2,
                self._log("logfile_12.log"),
                dependencies=[TaskDependency("task_1")],
            )
            tasks.append(t2)
            t3 = Task(
                "task_3",
                task_3,
                self._log("logfile_3.log"),
                args=(1,),
                dependencies=[TaskDependency("task_1"), TaskDependency("task_4")],
            )
            tasks.append(t3)
        except Exception as e:
            self._close_handlers(*tasks)
            pytest.fail(f"Unexpected exception: {e}")

        with pytest.raises(DependencyNotFoundError) as exc_info:
            with Process(tasks) as _:
                pass
        assert exc_info.value.task_name == "task_3"
        assert exc_info.value.missing_dep == "task_4"

        tasks[-1].dependencies[-1].task_name = "task_2"
        try:
            with Process(tasks) as _:
                pass
        except Exception as e:
            pytest.fail(f"Unexpected exception: {e}")

    def test_duplicate_dependency(self) -> None:
        """Test duplicate dependencies in a Task."""

        def task_3(t2_res: int) -> int:
            return 3 + t2_res

        with pytest.raises(ValueError, match="Duplicate dependency name: task_1"):
            Task(
                "task_3",
                task_3,
                self._log("logfile_3.log"),
                args=(1,),
                dependencies=[TaskDependency("task_1"), TaskDependency("task_1")],
            )

    def test_self_dependency(self) -> None:
        """Test a Task depending on itself."""

        def task_3(t2_res: int) -> int:
            return 3 + t2_res

        with pytest.raises(
            CircularDependencyError,
            match="Task 'task_3' lists itself as a dependency.",
        ):
            Task(
                "task_3",
                task_3,
                self._log("logfile_3.log"),
                args=(1,),
                dependencies=[TaskDependency("task_1"), TaskDependency("task_3")],
            )

    def test_circular_dependency_one_level(self) -> None:
        """Test a circular dependency in a Task at the first level (a->b->a)."""

        def task_1() -> int:
            return 1

        def task_2() -> int:
            return 2

        tasks: list[Task] = []
        try:
            t1 = Task(
                "task_1",
                task_1,
                self._log("logfile_12.log"),
                dependencies=[TaskDependency("task_2")],
            )
            tasks.append(t1)
            t2 = Task(
                "task_2",
                task_2,
                self._log("logfile_12.log"),
                dependencies=[TaskDependency("task_1")],
            )
            tasks.append(t2)
        except Exception as e:
            self._close_handlers(*tasks)
            pytest.fail(f"Unexpected exception: {e}")

        with pytest.raises(CircularDependencyError, match="Circular dependency detected."):
            with Process(tasks) as _:
                pass

        self._close_handlers(*tasks)

    def test_circular_dependency_two_levels(self) -> None:
        """Test a circular dependency in a Task at the second level (a->b->c->a)."""

        def task_1() -> int:
            return 1

        def task_2() -> int:
            return 2

        def task_3(t2_res: int) -> int:
            return 3 + t2_res

        tasks: list[Task] = []
        try:
            t1 = Task(
                "task_1",
                task_1,
                self._log("logfile_12.log"),
                dependencies=[TaskDependency("task_2")],
            )
            tasks.append(t1)
            t2 = Task(
                "task_2",
                task_2,
                self._log("logfile_12.log"),
                dependencies=[TaskDependency("task_3")],
            )
            tasks.append(t2)
            t3 = Task(
                "task_3",
                task_3,
                self._log("logfile_3.log"),
                args=(1,),
                dependencies=[TaskDependency("task_1")],
            )
            tasks.append(t3)
        except Exception as e:
            self._close_handlers(*tasks)
            pytest.fail(f"Unexpected exception: {e}")

        with pytest.raises(CircularDependencyError, match="Circular dependency detected."):
            with Process(tasks) as _:
                pass

        self._close_handlers(*tasks)

    def test_circular_dependency_three_levels2(self) -> None:
        """Test a circular dependency in a Task at the third level (a->b->c->a)."""

        def task_1() -> int:
            return 1

        def task_2() -> int:
            return 2

        def task_3(t2_res: int) -> int:
            return 3 + t2_res

        def task_4(t3_res: int) -> int:
            return 4 + t3_res

        tasks: list[Task] = []
        try:
            t1 = Task(
                "task_1",
                task_1,
                self._log("logfile_12.log"),
                dependencies=[TaskDependency("task_3")],
            )
            tasks.append(t1)
            t2 = Task(
                "task_2",
                task_2,
                self._log("logfile_12.log"),
                dependencies=[TaskDependency("task_1")],
            )
            tasks.append(t2)
            t3 = Task(
                "task_3",
                task_3,
                self._log("logfile_3.log"),
                args=(1,),
                dependencies=[TaskDependency("task_4")],
            )
            tasks.append(t3)
            t4 = Task(
                "task_4",
                task_4,
                self._log("logfile_4.log"),
                args=(1,),
                dependencies=[TaskDependency("task_1")],
            )
            tasks.append(t4)
        except Exception as e:
            self._close_handlers(*tasks)
            pytest.fail(f"Unexpected exception: {e}")

        with pytest.raises(CircularDependencyError, match="Circular dependency detected."):
            with Process(tasks) as _:
                pass

        self._close_handlers(*tasks)
