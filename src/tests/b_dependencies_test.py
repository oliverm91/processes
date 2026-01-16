import os
import pytest

from processes import Process, Task, TaskDependency, DependencyNotFoundError, CircularDependencyError

from .log_cleaner import clean_tasks_logs


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

    with pytest.raises(DependencyNotFoundError, match=f"Task task_3 depends on missing task: task_4"):
        with Process(tasks) as p:
            pass

    tasks[-1].dependencies[-1].task_name = "task_2"
    try:
        with Process(tasks) as p:
            pass
    except Exception as e:
        clean_tasks_logs()
        pytest.fail(f"Unexpected exception: {e}")

    clean_tasks_logs()


def test_duplicate_dependency():
    """
    Test duplicate dependencies in a Task.
    """
    def task_3(t2_res: int) -> int:
        return 3 + t2_res
    
    curdir = os.path.dirname(__file__)
    with pytest.raises(ValueError, match="Duplicate dependency name: task_1"):
        Task("task_3", os.path.join(curdir, "logfile_3.log"), task_3, args=(1,), dependencies=[TaskDependency("task_1"), TaskDependency("task_1")])
    
    clean_tasks_logs()


def test_self_dependency():
    """
    Test a Task depending on itself.
    """
    def task_3(t2_res: int) -> int:
        return 3 + t2_res
    
    curdir = os.path.dirname(__file__)
    with pytest.raises(ValueError, match=f"Got dependency with same name as Task. Task: task_3. Dependency: task_3"):
        Task("task_3", os.path.join(curdir, "logfile_3.log"), task_3, args=(1,), dependencies=[TaskDependency("task_1"), TaskDependency("task_3")])


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
        tasks: list[Task] = []
        t1 = Task("task_1", os.path.join(curdir, "logfile_12.log"), task_1, dependencies=[TaskDependency("task_2")])
        tasks.append(t1)
        t2 = Task("task_2", os.path.join(curdir, "logfile_12.log"), task_2, dependencies=[TaskDependency("task_1")])
        tasks.append(t2)
    except Exception as e:
        for t in tasks:
            for handler in t.logger.handlers:
                handler.close()
                t.logger.removeHandler(handler)
        clean_tasks_logs()
        pytest.fail(f"Unexpected exception: {e}")

    with pytest.raises(CircularDependencyError, match="Circular dependency detected."):
        with Process(tasks) as p:
            pass
    clean_tasks_logs()


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
        tasks: list[Task] = []
        t1 = Task("task_1", os.path.join(curdir, "logfile_12.log"), task_1, dependencies=[TaskDependency("task_2")])
        tasks.append(t1)
        t2 = Task("task_2", os.path.join(curdir, "logfile_12.log"), task_2, dependencies=[TaskDependency("task_3")])
        tasks.append(t2)
        t3 = Task("task_3", os.path.join(curdir, "logfile_3.log"), task_3, args=(1,), dependencies=[TaskDependency("task_1")])
        tasks.append(t3)
    except Exception as e:
        clean_tasks_logs()
        pytest.fail(f"Unexpected exception: {e}")

    with pytest.raises(CircularDependencyError, match="Circular dependency detected."):
        with Process(tasks) as p:
            pass

    clean_tasks_logs()


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
        tasks: list[Task] = []
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

    with pytest.raises(CircularDependencyError, match="Circular dependency detected."):
        with Process(tasks) as p:
            pass

    clean_tasks_logs()