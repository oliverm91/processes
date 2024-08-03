from dataclasses import dataclass

from .Task import Task, TaskResult


class DependencyNotFoundError(Exception):
    pass


class TaskNotFoundError(Exception):
    pass


class CircularDependencyError(Exception):
    pass


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
            stack = set()

            def dfs(task: Task):
                if task.name in stack:
                    raise CircularDependencyError(f"Found circular dependency involving task {task.name}")

                stack.add(task.name)

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
        # Sort tasks by dependencies:
        # Non dependent tasks go first
        # Then all tasks that depend on tasks already sorted

        sorted_tasks = []
        tasks_to_sort = self.tasks.copy()

        while tasks_to_sort:
            for task in tasks_to_sort[:]:
                if all(dependency.task_name in sorted_tasks for dependency in task.dependencies):
                    sorted_tasks.append(task)
                    tasks_to_sort.remove(task)

        self.tasks = sorted_tasks

    def get_task(self, task_name: str) -> Task:
        for task in self.tasks:
            if task.name == task_name:
                return task
        raise TaskNotFoundError(f"Task not found: {task_name}")
    
    def get_dependant_tasks(self, task_name: str) -> list[Task]:
        dependant_tasks = []

        def dfs(current_task_name):
            for task in self.tasks:
                if current_task_name in task.get_dependencies_names():
                    dependant_tasks.append(task)
                    dfs(task.name)

        dfs(task_name)
        return dependant_tasks
    
    def run(self):
        failed_tasks: set[str] = set()
        passed_results: dict[str, TaskResult] = {}
        for task in self.tasks:
            for dependency in task.dependencies:
                if dependency.task_name in failed_tasks:
                    failed_tasks.add(task.name)
                    continue
            dependant_tasks = self.get_dependant_tasks(task.name)
            if dependant_tasks:
                post_traceback_html_body = "<p>This failure led that the following dependant tasks will not run:</p><ul>"
                for dependant_task in dependant_tasks:
                    post_traceback_html_body += f"<li>{dependant_task.name}</li>"
                post_traceback_html_body += "</ul>"
            extra_args = set()
            extra_kwargs = {}
            for dependency in task.dependencies:
                if dependency.use_result_as_additional_args:
                    extra_args.add(passed_results[dependency.task_name].result)
                if dependency.use_result_as_additional_kwargs:
                    extra_kwargs[dependency.additional_kwarg_name] = passed_results[dependency.task_name].result
            task.add_args(*extra_args)
            task.add_kwargs(**extra_kwargs)
            task_result: TaskResult = task.run(post_traceback_html_body=post_traceback_html_body)
            if not task_result.worked:
                failed_tasks.add(task.name)
                print(f"Task {task.name} failed. Exception: {task_result.exception}")
            else:
                passed_results[task.name] = task_result
                print(f"Task {task.name} succeeded with result: {task_result.result}")

        if not failed_tasks:
            print("Process finished successfully.")
        else:
            print(f"Process finished with {len(failed_tasks)} failed tasks: {failed_tasks}")