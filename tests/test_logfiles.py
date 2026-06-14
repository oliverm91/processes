from processes import Process, Task

from .base_test import BaseTest


class TestLogFiles(BaseTest):
    def test_single_task_worked_log_entry(self) -> None:
        """Test the log entry for a single task that worked."""

        def task_1() -> int:
            return 1

        log_path = self._log("logfile_1.log")
        with Process([Task("task_1", task_1, log_path)]) as process:
            process.run()

        with open(log_path) as f:
            lines = f.readlines()
        assert len(lines) == 2
        assert "Starting task_1." in lines[0]
        assert "Finished task_1." in lines[1]

    def test_two_task_worked_log_entry_same_logfile(self) -> None:
        """Test the log entry for two tasks that worked using the same log file."""

        def task_1() -> int:
            return 1

        log_path = self._log("logfile_1.log")
        tasks = [Task("task_1", task_1, log_path), Task("task_2", task_1, log_path)]
        with Process(tasks) as process:
            process.run()

        with open(log_path) as f:
            lines = f.readlines()
        assert len(lines) == 4
        assert "Starting task_1." in lines[0]
        assert "Finished task_1." in lines[1]
        assert "Starting task_2." in lines[2]
        assert "Finished task_2." in lines[3]

    def test_two_task_worked_log_entry_different_logfile(self) -> None:
        """Test the log entry for two tasks that worked using two different log files."""

        def task_1() -> int:
            return 1

        def task_2() -> int:
            return 2

        log_path1 = self._log("logfile_1.log")
        log_path2 = self._log("logfile_2.log")
        tasks = [Task("task_1", task_1, log_path1), Task("task_2", task_2, log_path2)]
        with Process(tasks) as process:
            process.run()

        with open(log_path1) as f:
            lines1 = f.readlines()
        assert len(lines1) == 2
        assert "Starting task_1." in lines1[0]
        assert "Finished task_1." in lines1[1]

        with open(log_path2) as f:
            lines2 = f.readlines()
        assert len(lines2) == 2
        assert "Starting task_2." in lines2[0]
        assert "Finished task_2." in lines2[1]

    def test_exception_log_entry(self) -> None:
        """Test the log entry for a task that raised an exception."""

        def task_1() -> int:
            return 1 / 0

        log_path = self._log("logfile_1.log")
        with Process([Task("task_1", task_1, log_path)]) as process:
            process.run()

        with open(log_path) as f:
            lines = f.readlines()
        assert len(lines) >= 2 + 4  # 4 lines minimum extra lines for the traceback
        assert "Starting task_1." in lines[0]
        assert "division by zero" in lines[1]
        assert "division by zero" in lines[-1]
