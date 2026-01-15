import os

from processes import Process, Task, TaskDependency, DependencyNotFoundError, CircularDependencyError

import pytest

def clean_tasks_logs(tasks: list[Task]):
    curdir = os.path.dirname(__file__)
    for task in tasks:
            task_logger = task.logger
            for handler in task_logger.handlers[:]:
                handler.close()
                task_logger.removeHandler(handler)
    for file in os.listdir(curdir):
        if file.endswith(".log"):
            os.remove(os.path.join(curdir, file))


def test_present_dependencies():
    """
    Test the presence of dependencies.
    """
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
        t2 = Task("task_2", os.path.join(curdir, "logfile_12.log"), task_2, dependencies=[TaskDependency("task_1")])
        tasks.append(t2)
        t3 = Task("task_3", os.path.join(curdir, "logfile_3.log"), task_3, args=(1,), dependencies=[TaskDependency("task_1"), TaskDependency("task_4")])
        tasks.append(t3)
    except Exception as e:
        clean_tasks_logs(tasks)
        pytest.fail(f"Unexpected exception: {e}")

    with pytest.raises(DependencyNotFoundError, match=f"Dependency not found: task_4. Task: task_3. Dependencies: {t3.get_dependencies_names()}"):
        process = Process(tasks)

    tasks[-1].dependencies[-1].task_name = "task_2"
    try:
        process = Process(tasks)
    except Exception as e:
        clean_tasks_logs(tasks)
        pytest.fail(f"Unexpected exception: {e}")

    clean_tasks_logs(tasks)


def test_duplicate_dependency():
    """
    Test duplicate dependencies in a Task.
    """
    def task_3(t2_res: int) -> int:
        return 3 + t2_res
    
    curdir = os.path.dirname(__file__)
    did_not_fail = False
    with pytest.raises(ValueError, match="Duplicate dependency name: task_1"):
        t3 = Task("task_3", os.path.join(curdir, "logfile_3.log"), task_3, args=(1,), dependencies=[TaskDependency("task_1"), TaskDependency("task_1")])
        did_not_fail = True

    if did_not_fail:
        clean_tasks_logs([t3])


def test_self_dependency():
    """
    Test a Task depending on itself.
    """
    def task_3(t2_res: int) -> int:
        return 3 + t2_res
    
    curdir = os.path.dirname(__file__)
    did_not_fail = False
    with pytest.raises(ValueError, match=f"Got dependency with same name as Task. Task: task_3. Dependency: task_3"):
        t3 = Task("task_3", os.path.join(curdir, "logfile_3.log"), task_3, args=(1,), dependencies=[TaskDependency("task_1"), TaskDependency("task_3")])
        did_not_fail = True
    
    if did_not_fail:
        clean_tasks_logs([t3])


def test_circular_dependency_one_level():
    """
    Test a circular dependency in a Task at the first level (a->b->a).
    """
    def task_1() -> int:
        return 1
    def task_2() -> int:
        return 2
    curdir = os.path.dirname(__file__)

    try:
        tasks = []
        t1 = Task("task_1", os.path.join(curdir, "logfile_12.log"), task_1, dependencies=[TaskDependency("task_2")])
        tasks.append(t1)
        t2 = Task("task_2", os.path.join(curdir, "logfile_12.log"), task_2, dependencies=[TaskDependency("task_1")])
        tasks.append(t2)
    except Exception as e:
        clean_tasks_logs(tasks)
        pytest.fail(f"Unexpected exception: {e}")

    with pytest.raises(CircularDependencyError, match="Found circular dependency: task_1 -> task_2 -> task_1"):
        process = Process(tasks)

    clean_tasks_logs(tasks)


def test_circular_dependency_two_levels():
    """
    Test a circular dependency in a Task at the second level (a->b->c->a).
    """
    def task_1() -> int:
        return 1
    def task_2() -> int:
        return 2
    
    def task_3(t2_res: int) -> int:
        return 3 + t2_res

    curdir = os.path.dirname(__file__)

    try:
        tasks = []
        t1 = Task("task_1", os.path.join(curdir, "logfile_12.log"), task_1, dependencies=[TaskDependency("task_2")])
        tasks.append(t1)
        t2 = Task("task_2", os.path.join(curdir, "logfile_12.log"), task_2, dependencies=[TaskDependency("task_3")])
        tasks.append(t2)
        t3 = Task("task_3", os.path.join(curdir, "logfile_3.log"), task_3, args=(1,), dependencies=[TaskDependency("task_1")])
        tasks.append(t3)
    except Exception as e:
        clean_tasks_logs(tasks)
        pytest.fail(f"Unexpected exception: {e}")

    with pytest.raises(CircularDependencyError, match="Found circular dependency: task_1 -> task_2 -> task_3 -> task_1"):
        process = Process(tasks)

    clean_tasks_logs(tasks)


def test_circular_dependency_three_levels2():
    """
    Test a circular dependency in a Task at the third level (a->b->c->a).
    """
    def task_1() -> int:
        return 1
    def task_2() -> int:
        return 2
    
    def task_3(t2_res: int) -> int:
        return 3 + t2_res
    
    def task_4(t3_res: int) -> int:
        return 4 + t3_res

    curdir = os.path.dirname(__file__)

    try:
        tasks = []
        t1 = Task("task_1", os.path.join(curdir, "logfile_12.log"), task_1, dependencies=[TaskDependency("task_3")])
        tasks.append(t1)
        t2 = Task("task_2", os.path.join(curdir, "logfile_12.log"), task_2, dependencies=[TaskDependency("task_1")])
        tasks.append(t2)
        t3 = Task("task_3", os.path.join(curdir, "logfile_3.log"), task_3, args=(1,), dependencies=[TaskDependency("task_4")])
        tasks.append(t3)
        t4 = Task("task_4", os.path.join(curdir, "logfile_4.log"), task_4, args=(1,), dependencies=[TaskDependency("task_1")])
        tasks.append(t4)
    except Exception as e:
        clean_tasks_logs(tasks)
        pytest.fail(f"Unexpected exception: {e}")

    with pytest.raises(CircularDependencyError, match="Found circular dependency: task_1 -> task_3 -> task_4 -> task_1"):
        process = Process(tasks)

    clean_tasks_logs(tasks)