import concurrent.futures
from types import TracebackType
from typing import Literal, Self

from .task import Task, TaskResult


class DependencyNotFoundError(Exception):
    """Raised when a task depends on a non-existent task."""

    pass


class TaskNotFoundError(Exception):
    """Raised when attempting to retrieve a task that does not exist in the process."""

    pass


class CircularDependencyError(Exception):
    """Raised when circular dependencies are detected among tasks."""

    pass


class ProcessResult:
    """
    Container for the results of a process execution.

    Holds the outcomes of all tasks executed in a process, separating successful
    and failed tasks with their respective results.

    Attributes
    ----------
    passed_tasks_results : dict[str, TaskResult]
        Mapping of task names to TaskResult objects for all tasks that executed successfully.
    failed_tasks : set[str]
        Set of task names for all tasks that failed during execution.
    """

    def __init__(self, passed_tasks_results: dict[str, TaskResult], failed_tasks: set[str]):
        self.passed_tasks_results = passed_tasks_results
        self.failed_tasks = failed_tasks


class Process:
    """
    Manages and executes a collection of interdependent tasks.

    A Process orchestrates the execution of multiple tasks, handling dependency
    resolution, task ordering. Task execution can be performed in parallel or sequentially. It
    provides logging management and error propagation for dependent tasks. If a task fails,
    all tasks depending on it are marked as failed without execution, but non-dependent tasks
    continue to run.

    Attributes
    ----------
    tasks : list[Task]
        List of tasks to be executed, automatically sorted by dependencies.
    runner : ProcessRunner
        The runner responsible for executing the tasks.

    Raises
    ------
    TypeError
        If tasks is not a list or contains non-Task elements.
    ValueError
        If duplicate task names are found.
    DependencyNotFoundError
        If a task depends on a non-existent task.
    CircularDependencyError
        If circular dependencies are detected among tasks.
    """

    def __init__(self, tasks: list[Task]):
        self.tasks = tasks

        try:
            self._check_input_types()
            self._check_duplicate_names()
            self._check_dependencies_exist()
            self._topological_sort()
        except Exception as e:
            self.close_loggers()
            raise e
        self.runner = ProcessRunner(self)

    def __enter__(self) -> Self:
        """Called when entering the 'with' block."""
        return self

    def __exit__(
            self,
            exc_type: type[BaseException] | None,
            exc_value: BaseException | None,
            traceback: TracebackType | None,
        ) -> Literal[False]:
        """Called when exiting the 'with' block, even if an error occurred."""
        self.close_loggers()
        return False

    def _check_input_types(self) -> None:
        """Validate that tasks is a list containing only Task objects.

        Raises
        ------
        TypeError
            If tasks is not a list or contains non-Task elements.
        """
        if not isinstance(self.tasks, list):
            raise TypeError(f"tasks must be list. Got {type(self.tasks)}")
        for task in self.tasks:
            if not isinstance(task, Task):
                raise TypeError(f"task must be Task. Got {type(task)}")

    def _check_duplicate_names(self) -> None:
        """Verify that all task names are unique.

        Raises
        ------
        ValueError
            If duplicate task names are found.
        """
        names = set()
        for task in self.tasks:
            if task.name in names:
                raise ValueError(f"Duplicate task name: {task.name}")
            names.add(task.name)

    def _check_dependencies_exist(self) -> None:
        """Verify that all task dependencies refer to existing tasks.

        Raises
        ------
        DependencyNotFoundError
            If a task depends on a non-existent task.
        """
        names = {t.name for t in self.tasks}
        for task in self.tasks:
            for dep in task.get_dependencies_names():
                if dep not in names:
                    raise DependencyNotFoundError(
                        f"Task {task.name} depends on missing task: {dep}"
                    )

    def _topological_sort(self) -> None:
        """Sort tasks based on dependencies using Kahn's Algorithm in O(V+E) time.

        Reorders the task list so that dependencies are always executed before
        tasks that depend on them.

        Raises
        ------
        CircularDependencyError
            If circular dependencies are detected among tasks.
        """
        in_degree = {t.name: 0 for t in self.tasks}
        graph: dict[str, list[str]]= {t.name: [] for t in self.tasks}
        task_map = {t.name: t for t in self.tasks}

        for task in self.tasks:
            for dep in task.dependencies:
                graph[dep.task_name].append(task.name)
                in_degree[task.name] += 1

        queue = [name for name, deg in in_degree.items() if deg == 0]
        sorted_tasks = []

        while queue:
            u = queue.pop(0)
            sorted_tasks.append(task_map[u])
            for v in graph[u]:
                in_degree[v] -= 1
                if in_degree[v] == 0:
                    queue.append(v)

        if len(sorted_tasks) != len(self.tasks):
            raise CircularDependencyError("Circular dependency detected.")
        self.tasks = sorted_tasks

    def get_task(self, task_name: str) -> Task:
        """Retrieve a task by name.

        Parameters
        ----------
        task_name : str
            The name of the task to retrieve.

        Returns
        -------
        Task
            The task with the specified name.

        Raises
        ------
        TaskNotFoundError
            If no task with the given name exists.
        """
        for task in self.tasks:
            if task.name == task_name:
                return task
        raise TaskNotFoundError(f"Task not found: {task_name}")

    def run(self, parallel: bool | None = None, max_workers: int = 4) -> ProcessResult:
        """Execute all tasks in the process.

        Runs tasks sequentially or in parallel while respecting dependencies.
        Dependencies are always resolved before dependent tasks are executed.

        Parameters
        ----------
        parallel : bool, optional
            Whether to run tasks in parallel while respecting dependencies.
            If None, automatically set to True for processes with 10 or more tasks,
            False otherwise. Defaults to None.
        max_workers : int, optional
            Maximum number of worker threads for parallel execution. Defaults to 4.
            Only used when parallel=True. If set to 1, falls back to sequential execution.

        Returns
        -------
        ProcessResult
            Contains passed_tasks_results (dict mapping task names to TaskResult)
            and failed_tasks (set of task names that failed).
        """
        if parallel is None:
            parallel = len(self.tasks) >= 10

        max_workers = max(1, max_workers)
        if parallel:
            if max_workers == 1:
                parallel = False  # Fallback to sequential if only one worker
        process_result = self.runner.run(parallel, max_workers)
        return process_result

    def get_dependant_tasks(self, task_name: str) -> list[Task]:
        """Retrieve all tasks that directly or indirectly depend on a given task.

        Parameters
        ----------
        task_name : str
            The name of the task to find dependants for.

        Returns
        -------
        list[Task]
            List of all tasks that depend on the specified task, including
            transitive dependencies (tasks that depend on tasks that depend
            on the specified task).
        """
        found = []

        def find(name: str) -> None:
            for t in self.tasks:
                if name in t.get_dependencies_names() and t not in found:
                    found.append(t)
                    find(t.name)

        find(task_name)
        return found

    def close_loggers(self) -> None:
        """Close and clean up all logger handlers for all tasks.

        Should be called when the process is done to ensure proper resource cleanup.
        """
        for task in self.tasks:
            for handler in task.logger.handlers:
                handler.close()
                task.logger.removeHandler(handler)


class ProcessRunner:
    """
    Executes tasks in a Process, handling both sequential and parallel execution.

    Manages task execution state, tracks passed and failed tasks, and coordinates
    dependencies during execution.

    Attributes
    ----------
    process : Process
        Reference to the parent Process being executed.
    passed_results : dict[str, TaskResult]
        Results from successfully executed tasks.
    failed_tasks : set[str]
        Names of tasks that failed during execution.
    submitted_tasks : set[str]
        Names of tasks that have been submitted for execution.
    """

    def __init__(self, process_ref: Process):
        self.process = process_ref
        self.passed_results: dict[str, TaskResult] = {}
        self.failed_tasks: set[str] = set()
        self.submitted_tasks: set[str] = set()

    def run(self, parallel: bool, max_workers: int) -> ProcessResult:
        """Execute all tasks in the process using the specified execution mode.

        Parameters
        ----------
        parallel : bool
            If True, execute tasks in parallel; otherwise execute sequentially.
        max_workers : int
            Maximum number of worker threads for parallel execution.

        Returns
        -------
        ProcessResult
            The combined results of all task executions.
        """
        if parallel:
            self._run_parallel(max_workers)
        else:
            self._run_sequential()
        return ProcessResult(self.passed_results, self.failed_tasks)

    def _is_unrunnable(self, task: Task) -> bool:
        """Check if a task cannot be run due to failed dependencies.

        Parameters
        ----------
        task : Task
            The task to check.

        Returns
        -------
        bool
            True if any of the task's dependencies have failed, False otherwise.
            If True, the task is also marked as failed.
        """
        if any(d.task_name in self.failed_tasks for d in task.dependencies):
            self.failed_tasks.add(task.name)  # Propagate failure
            return True
        return False

    def _all_deps_met(self, task: Task) -> bool:
        """Check if all dependencies of a task have been successfully executed.

        Parameters
        ----------
        task : Task
            The task to check.

        Returns
        -------
        bool
            True if all dependencies have passed, False otherwise.
        """
        return all(d.task_name in self.passed_results for d in task.dependencies)

    def _run_sequential(self) -> None:
        """Execute all tasks sequentially in dependency order."""
        for task in self.process.tasks:
            if self._is_unrunnable(task):
                continue
            if self._all_deps_met(task):
                res = task.run(self.process)
                if res.worked:
                    self.passed_results[task.name] = res
                else:
                    self.failed_tasks.add(task.name)

    def _run_parallel(self, max_workers: int) -> None:
        """Execute tasks in parallel using a thread pool while respecting dependencies.

        Parameters
        ----------
        max_workers : int
            Maximum number of worker threads to use.

        Raises
        ------
        RuntimeError
            If execution stalls with no candidates ready and no tasks running.
        """
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            fut_to_name = {}
            while len(self.passed_results) + len(self.failed_tasks) < len(self.process.tasks):
                # Look for candidates to execute now
                candidates = [
                    t
                    for t in self.process.tasks
                    if t.name not in self.submitted_tasks
                    and t.name not in self.failed_tasks
                    and not self._is_unrunnable(t)
                    and self._all_deps_met(t)
                ]

                # Send tasks for execution and register as Task as submitted
                for task in candidates:
                    fut = executor.submit(task.run, self.process)
                    fut_to_name[fut] = task.name
                    self.submitted_tasks.add(task.name)

                # If there are tasks pending, wait. As soon one is completed,
                # save as passed or failed and remove from futures.
                if fut_to_name:
                    done, _ = concurrent.futures.wait(
                        fut_to_name.keys(), return_when="FIRST_COMPLETED"
                    )
                    for fut in done:
                        name = fut_to_name.pop(fut)
                        try:
                            res = fut.result()
                            if res.worked:
                                self.passed_results[name] = res
                            else:
                                self.failed_tasks.add(name)
                        except Exception:
                            self.failed_tasks.add(name)
                else:
                    # No candidates and no running tasks - likely a deadlock or logic error
                    raise RuntimeError(
                        "Parallel execution stalled: no candidates found and no tasks running"
                    )
