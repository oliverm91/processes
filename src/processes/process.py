import concurrent.futures
from collections import deque
from types import TracebackType
from typing import Literal, Self

from ._error_data import ErrorData
from .exceptions import CircularDependencyError, DependencyNotFoundError, TaskNotFoundError
from .execution_report import ProcessExecutionReport
from .task import Task, TaskResult, TaskStatus

__all__ = ["CircularDependencyError", "DependencyNotFoundError", "TaskNotFoundError"]


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

    Parameters
    ----------
    tasks : list[Task]
        The tasks to orchestrate. Order does not matter — the constructor
        topologically sorts the list in place. The list is mutated during
        construction; pass a copy if the original ordering matters.

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
        except Exception:
            self.close_loggers()
            raise
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
                    raise DependencyNotFoundError(task.name, dep)

    def _topological_sort(self) -> None:
        """Sort tasks based on dependencies using Kahn's algorithm in O(V+E) time.

        Reorders the task list so that dependencies are always executed before
        tasks that depend on them.  Also builds ``_task_map`` (name → Task) and
        ``_dependants_map`` (name → [direct dependant names]) for O(1) / O(V+E)
        downstream lookups.

        Raises
        ------
        CircularDependencyError
            If circular dependencies are detected among tasks.
        """
        in_degree = {t.name: 0 for t in self.tasks}
        graph: dict[str, list[str]] = {t.name: [] for t in self.tasks}
        task_map = {t.name: t for t in self.tasks}

        for task in self.tasks:
            for dep in task.dependencies:
                graph[dep.task_name].append(task.name)
                in_degree[task.name] += 1

        queue: deque[str] = deque(name for name, deg in in_degree.items() if deg == 0)
        sorted_tasks = []

        while queue:
            u = queue.popleft()
            sorted_tasks.append(task_map[u])
            for v in graph[u]:
                in_degree[v] -= 1
                if in_degree[v] == 0:
                    queue.append(v)

        if len(sorted_tasks) != len(self.tasks):
            raise CircularDependencyError("Circular dependency detected.")

        self._task_map: dict[str, Task] = task_map
        self._dependants_map: dict[str, list[str]] = graph
        self.tasks = sorted_tasks

    def get_task(self, task_name: str) -> Task:
        """Retrieve a task by name in O(1).

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
        try:
            return self._task_map[task_name]
        except KeyError as err:
            raise TaskNotFoundError(task_name) from err

    def run(self, parallel: bool | None = None, max_workers: int = 4) -> ProcessExecutionReport:
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
            Only used when parallel=True. If set to 1, falls back to sequential
            execution. Values below 1 are clamped to 1.

        Returns
        -------
        ProcessExecutionReport
            Per-task breakdown of the run, in topological order.
        """
        if parallel is None:
            parallel = len(self.tasks) >= 10

        max_workers = max(1, max_workers)
        if parallel:
            if max_workers == 1:
                parallel = False  # Fallback to sequential if only one worker
        return self.runner.run(parallel, max_workers)

    def get_dependant_tasks(self, task_name: str) -> list[Task]:
        """Retrieve all tasks that directly or indirectly depend on a given task.

        Uses a pre-built adjacency map for O(V+E) traversal.

        Parameters
        ----------
        task_name : str
            The name of the task to find dependants for.

        Returns
        -------
        list[Task]
            List of all tasks that depend on the specified task, including
            transitive dependants.
        """
        found: list[Task] = []
        seen: set[str] = set()
        queue: deque[str] = deque(self._dependants_map.get(task_name, []))
        while queue:
            name = queue.popleft()
            if name in seen:
                continue
            seen.add(name)
            found.append(self._task_map[name])
            queue.extend(self._dependants_map.get(name, []))
        return found

    def close_loggers(self) -> None:
        """Close and clean up all logger handlers for all tasks.

        Should be called when the process is done to ensure proper resource cleanup.
        """
        for task in self.tasks:
            for handler in list(task.logger.handlers):
                handler.close()
                task.logger.removeHandler(handler)


class ProcessRunner:
    """
    Executes tasks in a Process, handling both sequential and parallel execution.

    Manages task execution state and coordinates dependencies during execution.

    Attributes
    ----------
    process : Process
        Reference to the parent Process being executed.
    results : dict[str, TaskResult]
        One entry per task, keyed by task name. Every task starts out
        ``PENDING`` and transitions to ``SUCCESS``, ``ERRORED``, or
        ``SKIPPED`` once it is resolved.
    submitted_tasks : set[str]
        Names of tasks that have been submitted for execution.
    """

    def __init__(self, process_ref: Process):
        self.process = process_ref
        self.results: dict[str, TaskResult] = {
            task.name: TaskResult.pending() for task in process_ref.tasks
        }
        self.submitted_tasks: set[str] = set()

    def _is_done(self) -> bool:
        """Check whether every task has been resolved.

        Returns
        -------
        bool
            True if no task is still ``PENDING``, False otherwise.
        """
        return all(res.status != TaskStatus.PENDING for res in self.results.values())

    def run(self, parallel: bool, max_workers: int) -> ProcessExecutionReport:
        """Execute all tasks in the process using the specified execution mode.

        Parameters
        ----------
        parallel : bool
            If True, execute tasks in parallel; otherwise execute sequentially.
        max_workers : int
            Maximum number of worker threads for parallel execution.

        Returns
        -------
        ProcessExecutionReport
            Per-task breakdown of the run, in topological order.
        """
        if parallel:
            self._run_parallel(max_workers)
        else:
            self._run_sequential()
        return ProcessExecutionReport.from_results(self.process, self.results)

    def _has_failed_dep(self, task: Task) -> bool:
        """Return whether any dependency errored or was skipped.

        Pure query with no side effects: it does not record the task as
        ``SKIPPED``. Callers decide when to mark the cascade-skip.

        Parameters
        ----------
        task : Task
            The task to check.

        Returns
        -------
        bool
            True if any of the task's dependencies errored or were skipped,
            False otherwise.
        """
        return any(
            self.results[d.task_name].status in (TaskStatus.ERRORED, TaskStatus.SKIPPED)
            for d in task.dependencies
        )

    def _all_deps_met(self, task: Task) -> bool:
        """Check if all dependencies of a task have been successfully executed.

        Parameters
        ----------
        task : Task
            The task to check.

        Returns
        -------
        bool
            True if all dependencies succeeded, False otherwise.
        """
        return all(self.results[d.task_name].worked for d in task.dependencies)

    def _run_sequential(self) -> None:
        """Execute all tasks sequentially in dependency order."""
        for task in self.process.tasks:
            if self._has_failed_dep(task):
                self.results[task.name] = TaskResult.skipped()
                continue
            if self._all_deps_met(task):
                self.results[task.name] = task.run(self.process)

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
            while not self._is_done():
                # Record cascade-skips first (a dependency errored or was
                # skipped), then look for candidates whose deps all succeeded.
                for t in self.process.tasks:
                    if (
                        t.name not in self.submitted_tasks
                        and self.results[t.name].status == TaskStatus.PENDING
                        and self._has_failed_dep(t)
                    ):
                        self.results[t.name] = TaskResult.skipped()

                candidates = [
                    t
                    for t in self.process.tasks
                    if t.name not in self.submitted_tasks
                    and self.results[t.name].status == TaskStatus.PENDING
                    and self._all_deps_met(t)
                ]

                # Send tasks for execution and register as Task as submitted
                for task in candidates:
                    fut = executor.submit(task.run, self.process)
                    fut_to_name[fut] = task.name
                    self.submitted_tasks.add(task.name)

                # If there are tasks pending, wait. As soon one is completed,
                # save its result and remove from futures.
                if fut_to_name:
                    done, _ = concurrent.futures.wait(
                        fut_to_name.keys(), return_when="FIRST_COMPLETED"
                    )
                    for fut in done:
                        name = fut_to_name.pop(fut)
                        try:
                            self.results[name] = fut.result()
                        except Exception as e:
                            self.results[name] = TaskResult.errored(
                                e, error_data=ErrorData(task_name=name, exception=str(e))
                            )
                else:
                    # No running tasks and no new candidates. The
                    # ``_is_unrunnable`` side effect above may have
                    # marked the remaining tasks as skipped, completing
                    # the DAG. Re-check the loop condition before
                    # declaring a stall.
                    if not self._is_done():
                        raise RuntimeError(
                            "Parallel execution stalled: no candidates found and no tasks running"
                        )
