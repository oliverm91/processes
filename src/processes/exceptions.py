from __future__ import annotations


class DependencyNotFoundError(Exception):
    """Raised when a task depends on a non-existent task.

    Attributes
    ----------
    task_name : str
        Name of the task that declared the missing dependency.
    missing_dep : str
        Name of the dependency that could not be found.
    """

    def __init__(self, task_name: str, missing_dep: str) -> None:
        self.task_name = task_name
        self.missing_dep = missing_dep
        super().__init__(f"Task '{task_name}' depends on missing task: '{missing_dep}'")


class TaskNotFoundError(Exception):
    """Raised when attempting to retrieve a task that does not exist in the process.

    Attributes
    ----------
    task_name : str
        Name of the task that was requested but not found.
    """

    def __init__(self, task_name: str) -> None:
        self.task_name = task_name
        super().__init__(f"Task not found: '{task_name}'")


class CircularDependencyError(Exception):
    """Raised when circular dependencies are detected among tasks."""
