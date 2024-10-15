import os

from processes import Process, Task

import pytest

def clean_tasks_logs(tasks: list[Task]):
    curdir = os.path.dirname(__file__)
    print(curdir)
    for task in tasks:
            task_logger = task.logger
            for handler in task_logger.handlers[:]:
                handler.close()
                task_logger.removeHandler(handler)
    for file in os.listdir(curdir):
        print(os.path.join(curdir, file))
        if file.endswith(".log"):
            os.remove(os.path.join(curdir, file))

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
        clean_tasks_logs(tasks)
        pytest.fail(f"Unexpected exception: {e}")

    with pytest.raises(ValueError, match="Duplicate task name: task_2"):
        process = Process(tasks)

    tasks[-1].name = "task_3"
    try:
        process = Process(tasks)
    except Exception as e:
        pytest.fail(f"Unexpected exception: {e}")
        clean_tasks_logs(tasks)

    clean_tasks_logs(tasks)
