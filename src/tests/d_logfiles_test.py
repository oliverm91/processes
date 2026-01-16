import os

from processes import Process, Task

from .log_cleaner import clean_tasks_logs


def test_single_task_worked_log_entry():
    """
    Test the log entry for a single task that worked.
    """
    clean_tasks_logs()
    def task_1() -> int:
        return 1
    
    curdir = os.path.dirname(__file__)
    tasks = []
    log_file_path = os.path.join(curdir, "logfile_1.log")
    t1 = Task("task_1", log_file_path, task_1)
    tasks.append(t1)
    
    process = Process(tasks)
    process.run()

    with open(log_file_path, "r") as f:
        lines = f.readlines()
        assert len(lines) == 2
        assert "Starting task_1." in lines[0]
        assert "Finished task_1." in lines[1]

    for handler in t1.logger.handlers[:]:
        handler.close()
        t1.logger.removeHandler(handler)
    os.remove(log_file_path)


def test_two_task_worked_log_entry_same_logfile():
    """
    Test the log entry for two tasks that worked using the same log file.
    """
    clean_tasks_logs()
    def task_1() -> int:
        return 1
    
    curdir = os.path.dirname(__file__)
    tasks = []
    log_file_path = os.path.join(curdir, "logfile_1.log")
    t1 = Task("task_1", log_file_path, task_1)
    tasks.append(t1)
    t2 = Task("task_2", log_file_path, task_1)
    tasks.append(t2)
    
    process = Process(tasks)
    process.run()

    with open(log_file_path, "r") as f:
        lines = f.readlines()
        assert len(lines) == 4
        assert "Starting task_1." in lines[0]
        assert "Finished task_1." in lines[1]
        assert "Starting task_2." in lines[2]
        assert "Finished task_2." in lines[3]

    for task in tasks:
        for handler in task.logger.handlers[:]:
            handler.close()
            t1.logger.removeHandler(handler)
    os.remove(log_file_path)


def test_two_task_worked_log_entry_different_logfile():
    """
    Test the log entry for two tasks that worked using two different log files.
    """
    clean_tasks_logs()
    def task_1() -> int:
        return 1
    
    def task_2() -> int:
        return 2
    
    curdir = os.path.dirname(__file__)
    tasks = []
    log_file_path1 = os.path.join(curdir, "logfile_1.log")
    log_file_path2 = os.path.join(curdir, "logfile_2.log")
    t1 = Task("task_1", log_file_path1, task_1)
    tasks.append(t1)
    t2 = Task("task_2", log_file_path2, task_2)
    tasks.append(t2)
    
    process = Process(tasks)
    process.run()

    with open(log_file_path1, "r") as f:
        lines = f.readlines()
        assert len(lines) == 2
        assert "Starting task_1." in lines[0]
        assert "Finished task_1." in lines[1]

    with open(log_file_path2, "r") as f:
        lines = f.readlines()
        assert len(lines) == 2
        assert "Starting task_2." in lines[0]
        assert "Finished task_2." in lines[1]

    for task in tasks:
        for handler in task.logger.handlers[:]:
            handler.close()
            t1.logger.removeHandler(handler)
    os.remove(log_file_path1)
    os.remove(log_file_path2)


def test_exception_log_entry():
    """
    Test the log entry for a task that raised an exception.
    """
    clean_tasks_logs()
    def task_1() -> int:
        return 1 / 0
    
    curdir = os.path.dirname(__file__)
    tasks = []
    log_file_path = os.path.join(curdir, "logfile_1.log")
    t1 = Task("task_1", log_file_path, task_1)
    tasks.append(t1)
    
    process = Process(tasks)
    process.run()

    with open(log_file_path, "r") as f:
        lines = f.readlines()
        assert len(lines) >= 2 * len(tasks) + 4 # 4 lines minimum extra lines for the traceback
        assert "Starting task_1." in lines[0]
        assert "division by zero" in lines[1]
        assert "division by zero" in lines[-1]

    for handler in t1.logger.handlers[:]:
        handler.close()
        t1.logger.removeHandler(handler)
    os.remove(log_file_path)