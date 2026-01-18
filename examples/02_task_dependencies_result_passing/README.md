# Example 2: Task Dependencies & Result Passing

**Difficulty:** ⭐⭐ Intermediate  
**Time to understand:** 10 minutes

## Overview

This example demonstrates how to create task dependencies and automatically pass results from one task to another. This is where the real power of the library shines!

## What You'll Learn

✅ Creating tasks with dependencies  
✅ Passing task results as positional arguments  
✅ Passing task results as keyword arguments  
✅ Understanding topological sort (dependency ordering)  
✅ Complex task graphs with multiple dependency paths  

## Scenario

Imagine you're building a data pipeline with 6 tasks:

```
                        ┌─→ [2] validate ─────┐
                        │                      │
[1] fetch_data ─────────┤                      ├─→ [4] prepare ─→ [5] save ─→ [6] report
                        │                      │                              ↑
                        └─→ [3] calculate ─────┴──────────────────────────────┘

Task Dependencies:
  1. fetch_data        - No dependencies
  2. validate          - Depends on: fetch_data (runs in parallel with 3.)
  3. calculate_stats   - Depends on: fetch_data (runs in parallel with 2.)
  4. prepare_storage   - Depends on: validate, calculate_stats
  5. save_data         - Depends on: prepare_storage
  6. generate_report   - Depends on: save_data, calculate_stats
```

Key observations:
- **fetch_data** starts first with no dependencies
- **validate** and **calculate_stats** can run in parallel (both depend only on fetch_data)
- **prepare_storage** waits for both validate and calculate_stats to complete
- **save_data** depends on prepare_storage
- **generate_report** depends on both save_data AND calculate_stats results

## Code Walkthrough

### Understanding TaskDependency
See how the second `Task` object receives a list with its dependencies. In this case it is only one `TaskDependency` object pointing to `fetch_data`.
It also uses the result obtained from it and add it as additional args to `validate` function.
```python
# Task 1: Fetch data (no dependencies)
t_fetch = Task("fetch_data", f"{log_dir}/fetch.log", fetch_user_data)

# Task 2: Validate (depends on fetch)
t_validate = Task(
    "validate",
    f"{log_dir}/validate.log",
    validate_data,
    dependencies=[
        TaskDependency(
            "fetch_data",
            use_result_as_additional_args=True,  # Pass fetch result as arg
        )
    ],
)
```


### Using Keyword Arguments

```python
def generate_report(result: str, include_details: bool = False) -> str:
    """Generate final report with optional details."""
    if include_details:
        return f"Full Report: {result}"
    return f"Summary: {result}"

t5 = Task(
    "report",
    "logs/report.log",
    generate_report,
    args=(),
    kwargs={"include_details": True},
    dependencies=[
        TaskDependency(
            "save",
            use_result_as_additional_kwargs=True,
            additional_kwarg_name="result"  # save result → 'result' kwarg
        )
    ]
)
```

## Dependency Ordering (Topological Sort)

The Process automatically reorders tasks using Kahn's algorithm:

```python
# Order of creation (doesn't matter)
tasks = [t4, t1, t3, t2]

# Automatic reordering by Process
with Process(tasks) as process:
    # Internal order becomes: t1 → (t2, t3 in parallel) → t4
    process.run(parallel=True)
```

## Key Concepts

### Positional Arguments (`use_result_as_additional_args=True`)

Results are appended to the task function's positional arguments:

```python
def func(a, b, c):  # Original signature
    pass

# With dependency passing a result
t = Task(
    "task",
    "log.log",
    func,
    args=(1, 2),  # Original args
    dependencies=[TaskDependency("source", use_result_as_additional_args=True)]
)

# Effective call: func(1, 2, <source_result>)
```

### Keyword Arguments (`use_result_as_additional_kwargs=True`)

Results are passed with a specified keyword argument name:

```python
def func(a, b=None):
    pass

t = Task(
    "task",
    "log.log",
    func,
    args=(1,),
    kwargs={"b": "default"},
    dependencies=[TaskDependency("source", use_result_as_additional_kwargs=True, additional_kwarg_name="b")]
)

# Effective call: func(1, b=<source_result>)
# Note: keyword arg from dependency overrides kwargs
```

### Handling Multiple Dependencies

When a task depends on multiple tasks, results are added in dependency order:

```python
dependencies=[
    TaskDependency("task_a", use_result_as_additional_args=True),  # 1st arg
    TaskDependency("task_b", use_result_as_additional_args=True),  # 2nd arg
    TaskDependency("task_c", use_result_as_additional_args=True)   # 3rd arg
]

# Effective call: func(res_a, res_b, res_c, ...)
```
