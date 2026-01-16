from .task import Task, TaskResult


class DependencyNotFoundError(Exception):
    pass


class TaskNotFoundError(Exception):
    pass


class CircularDependencyError(Exception):
    pass


class ProcessResult:
    def __init__(self, passed_tasks_results: dict[str, TaskResult], failed_tasks: set[str]):
        self.passed_tasks_results = passed_tasks_results
        self.failed_tasks = failed_tasks


class Process:
    def __init__(self, tasks: list[Task]):
        self.tasks = tasks

        self._check_input_types()
        self._check_duplicate_names()
        self._check_dependencies_exist()
        self._topological_sort()
        self.runner = ProcessRunner(self)

    def _check_input_types(self):
        if not isinstance(self.tasks, list):
            raise TypeError(f"tasks must be list. Got {type(self.tasks)}")
        for task in self.tasks:
            if not isinstance(task, Task):
                raise TypeError(f"task must be Task. Got {type(task)}")
    
    def _check_duplicate_names(self):
        names = set()
        for task in self.tasks:
            if task.name in names:
                raise ValueError(f"Duplicate task name: {task.name}")
            names.add(task.name)

    def _check_dependencies_exist(self):
        names = {t.name for t in self.tasks}
        for task in self.tasks:
            for dep in task.get_dependencies_names():
                if dep not in names:
                    raise DependencyNotFoundError(f"Task {task.name} depends on missing task: {dep}")

    def _topological_sort(self):
        """Kahn's Algorithm: Sorts tasks based on dependencies in O(V+E) time."""
        in_degree = {t.name: 0 for t in self.tasks}
        graph = {t.name: [] for t in self.tasks}
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
        for task in self.tasks:
            if task.name == task_name:
                return task
        raise TaskNotFoundError(f"Task not found: {task_name}")

    def run(self, parallel: bool = None, max_workers: int = 4) -> ProcessResult:
        """
        Runs the tasks in the process.
        
        ------
        Parameters
        ------
        - parallel: Whether to run tasks in parallel (dependancies are taken into consideration). If None, automatically set to True 
                   for processes with 10 or more tasks, False otherwise.
        - max_workers: Maximum number of worker threads for parallel execution. Default is 4.
                      Only used when parallel=True.

        ------
        Returns
        ------
        - ProcessResult: Contains passed_tasks_results (dict mapping task names to TaskResult)
                        and failed_tasks (set of task names that failed).
        
        """
        if parallel is None:
            parallel = len(self.tasks) >= 10
        
        process_result = self.runner.run(parallel, max_workers)
        return process_result

    def get_dependant_tasks(self, task_name: str) -> list[Task]:
        """Returns all tasks that depend on this task recursively."""
        found = []
        def find(name):
            for t in self.tasks:
                if name in t.get_dependencies_names() and t not in found:
                    found.append(t)
                    find(t.name)
        find(task_name)
        return found

    def close_loggers(self):
        for task in self.tasks:
            for handler in task.logger.handlers[:]:
                handler.close()
            task.logger.removeHandler(handler)


import concurrent.futures
class ProcessRunner:
    def __init__(self, process_ref: Process):
        self.process = process_ref
        self.passed_results: dict[str, TaskResult] = {}
        self.failed_tasks: set[str] = set()
        self.submitted_tasks: set[str] = set()

    def run(self, parallel: bool, max_workers: int) -> ProcessResult:
        if parallel:
            self._run_parallel(max_workers)
        else:
            self._run_sequential()
        return ProcessResult(self.passed_results, self.failed_tasks)

    def _is_unrunnable(self, task: Task) -> bool:
        if any(d.task_name in self.failed_tasks for d in task.dependencies):
            self.failed_tasks.add(task.name) # Propagate failure
            return True
        return False

    def _all_deps_met(self, task: Task) -> bool:
        return all(d.task_name in self.passed_results for d in task.dependencies)

    def _run_sequential(self):
        for task in self.process.tasks:
            if self._is_unrunnable(task): continue
            if self._all_deps_met(task):
                res = task.run(self.process)
                if res.worked: self.passed_results[task.name] = res
                else: self.failed_tasks.add(task.name)

    def _run_parallel(self, max_workers: int):
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            fut_to_name = {}
            while len(self.passed_results) + len(self.failed_tasks) < len(self.process.tasks):
                # Look for candidates to execute now
                candidates = [t for t in self.process.tasks 
                            if t.name not in self.submitted_tasks 
                            and t.name not in self.failed_tasks
                            and not self._is_unrunnable(t)
                            and self._all_deps_met(t)]

                # Send tasks for execution and register as Task as submitted
                for task in candidates:
                    fut = executor.submit(task.run, self.process)
                    fut_to_name[fut] = task.name
                    self.submitted_tasks.add(task.name)

                # If there are tasks pending, wait. As soon one is completed, save as passed or failed and remove from futures.
                if fut_to_name:
                    done, _ = concurrent.futures.wait(fut_to_name.keys(), return_when='FIRST_COMPLETED')
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
                    raise RuntimeError("Parallel execution stalled: no candidates found and no tasks running")