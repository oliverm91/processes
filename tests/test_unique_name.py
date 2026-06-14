import pytest

from processes import Process, Task

from .base_test import BaseTest


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
