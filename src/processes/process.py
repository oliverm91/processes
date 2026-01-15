from dataclasses import dataclass

from .task import Task, TaskResult


class DependencyNotFoundError(Exception):
    pass


class TaskNotFoundError(Exception):
    pass


class CircularDependencyError(Exception):
    pass


@dataclass(slots=True)
class ProcessResult:
    passed_tasks_results: dict[str, TaskResult]
    failed_tasks: set[str]


@dataclass(slots=True)
class Process:
    tasks: list[Task]

    def __post_init__(self):
        self._check_input_types()
        self._check_dependencies()
        self._sort_tasks()        

    def _check_input_types(self):
        if not isinstance(self.tasks, list):
            raise TypeError(f"tasks must be list. Got {type(self.tasks)}")
        
        for task in self.tasks:
            if not isinstance(task, Task):
                raise TypeError(f"task must be of type Task. Got {type(task)}")   
                
    def _check_dependencies(self):
        tasks_names = []
        # Check duplicate tasks
        for task in self.tasks:
            if task.name in tasks_names:
                raise ValueError(f"Duplicate task name: {task.name}")
            tasks_names.append(task.name)

        # Check non present dependencies
        for task_name in tasks_names:
            task = self.get_task(task_name)
            task_dependencies_names = task.get_dependencies_names()
            for dependency in task_dependencies_names:
                if dependency not in tasks_names:
                    raise DependencyNotFoundError(f"Dependency not found: {dependency}. Task: {task.name}. Dependencies: {task_dependencies_names}")
            
        def check_circular_dependencies():
            stack = []

            def dfs(task: Task):
                if task.name in stack:
                    stack.append(task.name)
                    circular_dependency_repr = " -> ".join(stack)
                    raise CircularDependencyError(f"Found circular dependency: {circular_dependency_repr}")
                
                stack.append(task.name)

                task_names_dependencies = task.get_dependencies_names()
                for dependency_name in task_names_dependencies:
                    dependency_task = self.get_task(dependency_name)
                    if dependency_task.dependencies:
                        dfs(dependency_task)
                    
                stack.remove(task.name)

            for task in self.tasks:
                dfs(task)

        check_circular_dependencies()

    def _sort_tasks(self):
        sorted_tasks = []
        tasks_to_sort = [t.name for t in self.tasks]
        while tasks_to_sort:
            for task_name in tasks_to_sort[:]:
                task = self.get_task(task_name)
                if all(dependency.task_name in sorted_tasks for dependency in task.dependencies):
                    sorted_tasks.append(task_name)
                    tasks_to_sort.remove(task_name)

        self.tasks = [self.get_task(task_name) for task_name in sorted_tasks]

    def get_task(self, task_name: str) -> Task:
        for task in self.tasks:
            if task.name == task_name:
                return task
        raise TaskNotFoundError(f"Task not found: {task_name}")
    
    def get_dependant_tasks(self, task_name: str) -> list[Task]:
        dependant_tasks = []

        def dfs(current_task_name) -> list[str]:
            for task in self.tasks:
                if task in dependant_tasks:
                    continue
                if current_task_name in task.get_dependencies_names():
                    dependant_tasks.append(task)
                    dfs(task.name)

        dfs(task_name)
        return dependant_tasks
    
    def run(self) -> ProcessResult:
        """
        Executes the tasks in the correct order, respecting their dependencies.

        Each task is run only after its dependencies have successfully completed. If a task fails, 
        all tasks depending on it will not be executed. The results of successful tasks are stored 
        and passed as arguments to subsequent tasks if specified.

        Returns:
            ProcessResult: An object containing the results of the tasks that passed and a set of task names that failed.

        Raises:
            TaskNotFoundError: If a task required by a dependency is not found in the list of tasks.
            DependencyNotFoundError: If a dependency for a task is not found in the list of tasks.
            CircularDependencyError: If a circular dependency is detected among the tasks.
        """
        failed_tasks: set[str] = set()
        passed_results: dict[str, TaskResult] = {}
        for task in self.tasks:
            skip_task = False
            for dependency in task.dependencies:
                if dependency.task_name in failed_tasks:
                    failed_tasks.add(task.name)
                    skip_task = True
                    break
            if skip_task:
                continue
            extra_args = tuple(passed_results[d.task_name].result for d in task.dependencies if d.use_result_as_additional_args)
            extra_kwargs = {d.additional_kwarg_name: passed_results[d.task_name].result for d in task.dependencies if d.use_result_as_additional_kwargs}
            task_result: TaskResult = task.run(executing_process=self, aditional_args=extra_args, aditional_kwargs=extra_kwargs)
            if not task_result.worked:
                failed_tasks.add(task.name)
            else:
                passed_results[task.name] = task_result

        return ProcessResult(passed_results, failed_tasks)

    def close_loggers(self):
        for task in self.tasks:
            for handler in task.logger.handlers[:]:
                handler.close()
            task.logger.removeHandler(handler)
