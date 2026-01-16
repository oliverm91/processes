import os
import pytest

from processes import Process, Task

from .log_cleaner import clean_tasks_logs


def test_unique_name():
    def task_1() -> int:
        return 1
    def task_2() -> int:
        return 2
    def task_3(t2_res: int) -> int:
        return 3 + t2_res
    
    curdir = os.path.dirname(__file__)
    tasks: list[Task] = []
    try:
        t1 = Task("task_1", os.path.join(curdir, "logfile_12.log"), task_1)
        tasks.append(t1)
        t2 = Task("task_2", os.path.join(curdir, "logfile_12.log"), task_2)
        tasks.append(t2)
        t3 = Task("task_2", os.path.join(curdir, "logfile_3.log"), task_3, args=(1,))
        tasks.append(t3)
    except Exception as e:
        clean_tasks_logs()
        pytest.fail(f"Unexpected exception: {e}")

    with pytest.raises(ValueError, match="Duplicate task name: task_2"):
        with Process(tasks) as p:
            pass
        
    tasks[-1].name = "task_3"
    try:
        with Process(tasks) as p:
            pass
    except Exception as e:
        pytest.fail(f"Unexpected exception: {e}")
        clean_tasks_logs()

    clean_tasks_logs()
