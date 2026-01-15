import os

from processes import Process, Task, TaskDependency


def test_args():
    """
    Test the args parameter of a Task.
    """
    def div10(a: int) -> int:
        return 10 / a
    
    curdir = os.path.dirname(__file__)
    t1 = Task("task_1", os.path.join(curdir, "logfile_12.log"), div10, args=(2,))
    task_result = t1.run()

    assert task_result.worked
    assert task_result.result == 5
    assert task_result.exception is None

    t2 = Task("task_2", os.path.join(curdir, "logfile_12.log"), div10, args=(0,))
    task_result = t2.run()

    assert not task_result.worked
    assert task_result.result is None
    assert isinstance(task_result.exception, ZeroDivisionError)
    
    for task in [t1, t2]:
        for handler in task.logger.handlers[:]:
            handler.close()
            task.logger.removeHandler(handler)
    os.remove(os.path.join(curdir, "logfile_12.log"))


def test_args_kwargs():
    """
    Test the args and kwargs parameters of a Task.
    """
    def div(a: int, b: int=2) -> int:
        return a / b
    
    curdir = os.path.dirname(__file__)
    t1 = Task("task_1", os.path.join(curdir, "logfile_123.log"), div, args=(10,))
    task_result = t1.run()

    assert task_result.worked
    assert task_result.result == 5
    assert task_result.exception is None

    t2 = Task("task_2", os.path.join(curdir, "logfile_123.log"), div, args=(10,), kwargs={"b":5})
    task_result = t2.run()

    assert task_result.worked
    assert task_result.result == 2
    assert task_result.exception is None

    t3 = Task("task_3", os.path.join(curdir, "logfile_123.log"), div, args=(10,), kwargs={"b":0})
    task_result = t3.run()

    assert not task_result.worked
    assert task_result.result is None
    assert isinstance(task_result.exception, ZeroDivisionError)
    
    for task in [t1, t2, t3]:
        for handler in task.logger.handlers[:]:
            handler.close()
            task.logger.removeHandler(handler)
    os.remove(os.path.join(curdir, "logfile_123.log"))


def test_add_extra_args():
    """
    Test passing extra arguments to a Task that come as result from dependencies.
    """
    def t1():
        return 2
    
    def div(a: int, b: int) -> int:
        return a / b
    
    curdir = os.path.dirname(__file__)
    tasks = []
    t1 = Task("task_1", os.path.join(curdir, "logfile_12.log"), t1)
    tasks.append(t1)
    t2 = Task("task_2", os.path.join(curdir, "logfile_12.log"), div, args=(10, ), dependencies=[TaskDependency("task_1", use_result_as_additional_args=True)])
    tasks.append(t2)
    process = Process(tasks)
    process_result = process.run()

    assert len(process_result.failed_tasks) == 0
    assert len(process_result.passed_tasks_results) == 2
    assert process_result.passed_tasks_results["task_1"].result == 2
    assert process_result.passed_tasks_results["task_2"].result == 5
    
    for task in [t1, t2]:
        for handler in task.logger.handlers[:]:
            handler.close()
            task.logger.removeHandler(handler)
    os.remove(os.path.join(curdir, "logfile_12.log"))


def test_add_extra_args_kwargs():
    """
    Test passing extra arguments and keyword arguments to a Task that come as result from dependencies.
    """
    def random_routine_to_do_first():
        pass

    def get_b():
        return 10
    
    def get_c():
        return 5
    
    def div(a: int, b: int, c: int=5) -> int:
        return (a + b) / c
    
    curdir = os.path.dirname(__file__)
    tasks = []
    t0 = Task("task_0", os.path.join(curdir, "logfile_0.log"),
                random_routine_to_do_first)
    tasks.append(t0)
    t1 = Task("task_1", os.path.join(curdir, "logfile_12.log"),
                get_b)
    tasks.append(t1)
    t2 = Task("task_2", os.path.join(curdir, "logfile_12.log"),
                get_c, dependencies=[TaskDependency("task_1")])
    tasks.append(t2)
    t3 = Task("task_3", os.path.join(curdir, "logfile_3.log"),
                div, args=(10, ), dependencies=[TaskDependency("task_1", use_result_as_additional_args=True),
                                                TaskDependency("task_2", use_result_as_additional_kwargs=True, additional_kwarg_name="c")])
    tasks.append(t3)
    process = Process(tasks)
    process_result = process.run()

    assert len(process_result.failed_tasks) == 0
    assert len(process_result.passed_tasks_results) == 4
    assert process_result.passed_tasks_results["task_1"].result == 10
    assert process_result.passed_tasks_results["task_2"].result == 5
    assert process_result.passed_tasks_results["task_3"].result == 4

    for task in [t0, t1, t2, t3]:
        for handler in task.logger.handlers[:]:
            handler.close()
            task.logger.removeHandler(handler)
    os.remove(os.path.join(curdir, "logfile_0.log"))
    os.remove(os.path.join(curdir, "logfile_12.log"))
    os.remove(os.path.join(curdir, "logfile_3.log"))