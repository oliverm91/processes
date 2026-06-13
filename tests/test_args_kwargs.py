from processes import Process, Task, TaskDependency

from .base_test import BaseTest


class TestArgsKwargs(BaseTest):
    def test_args(self) -> None:
        """Test the args parameter of a Task."""

        def div10(a: int) -> int:
            return 10 / a

        t1 = Task("task_1", self._log("logfile_12.log"), div10, args=(2,))
        t2 = Task("task_2", self._log("logfile_12.log"), div10, args=(0,))
        try:
            tr1 = t1.run()
            tr2 = t2.run()
        finally:
            self._close_handlers(t1, t2)

        assert tr1.worked
        assert tr1.result == 5
        assert tr1.exception is None

        assert not tr2.worked
        assert tr2.result is None
        assert isinstance(tr2.exception, ZeroDivisionError)

    def test_args_kwargs(self) -> None:
        """Test the args and kwargs parameters of a Task."""

        def div(a: int, b: int = 2) -> int:
            return a / b

        t1 = Task("task_1", self._log("logfile_123.log"), div, args=(10,))
        t2 = Task("task_2", self._log("logfile_123.log"), div, args=(10,), kwargs={"b": 5})
        t3 = Task("task_3", self._log("logfile_123.log"), div, args=(10,), kwargs={"b": 0})
        try:
            tr1 = t1.run()
            tr2 = t2.run()
            tr3 = t3.run()
        finally:
            self._close_handlers(t1, t2, t3)

        assert tr1.worked
        assert tr1.result == 5
        assert tr1.exception is None

        assert tr2.worked
        assert tr2.result == 2
        assert tr2.exception is None

        assert not tr3.worked
        assert tr3.result is None
        assert isinstance(tr3.exception, ZeroDivisionError)

    def test_add_extra_args(self) -> None:
        """Test passing extra arguments to a Task that come as result from dependencies."""

        def t1_func():
            return 2

        def div(a: int, b: int) -> int:
            return a / b

        t1 = Task("task_1", self._log("logfile_12.log"), t1_func)
        t2 = Task(
            "task_2",
            self._log("logfile_12.log"),
            div,
            args=(10,),
            dependencies=[TaskDependency("task_1", use_result_as_additional_args=True)],
        )
        with Process([t1, t2]) as process:
            process_result = process.run()

        assert len(process_result.failed_tasks) == 0
        assert len(process_result.passed_tasks_results) == 2
        assert process_result.passed_tasks_results["task_1"].result == 2
        assert process_result.passed_tasks_results["task_2"].result == 5

    def test_add_extra_args_kwargs(self) -> None:
        """Test passing extra arguments and keyword arguments to a Task
        that come as result from dependencies."""

        def random_routine_to_do_first():
            pass

        def get_b():
            return 10

        def get_c():
            return 5

        def div(a: int, b: int, c: int = 5) -> int:
            return (a + b) / c

        t0 = Task("task_0", self._log("logfile_0.log"), random_routine_to_do_first)
        t1 = Task("task_1", self._log("logfile_12.log"), get_b)
        t2 = Task(
            "task_2",
            self._log("logfile_12.log"),
            get_c,
            dependencies=[TaskDependency("task_1")],
        )
        t3 = Task(
            "task_3",
            self._log("logfile_3.log"),
            div,
            args=(10,),
            dependencies=[
                TaskDependency("task_1", use_result_as_additional_args=True),
                TaskDependency(
                    "task_2", use_result_as_additional_kwargs=True, additional_kwarg_name="c"
                ),
            ],
        )
        with Process([t0, t1, t2, t3]) as process:
            process_result = process.run()

        assert len(process_result.failed_tasks) == 0
        assert len(process_result.passed_tasks_results) == 4
        assert process_result.passed_tasks_results["task_1"].result == 10
        assert process_result.passed_tasks_results["task_2"].result == 5
        assert process_result.passed_tasks_results["task_3"].result == 4
