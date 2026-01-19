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
                        ┌─→ [2] validate ────────┐
                        │                        │
[1] fetch_data ─────────┤                        ├─→ [4] prepare ─→ [5] save ─→ [6] report
                        │                        │                              ↑
                        └─→ [3] calculate_stats ─┴──────────────────────────────┘

Task Dependencies:
  1. fetch_data           - No dependencies
  2. validate             - Depends on: fetch_data (passes result as arg)
  3. calculate_stats      - Depends on: fetch_data (passes result as arg), validate (no result pass)
  4. prepare_storage      - Depends on: validate (passes result as arg), calculate_stats (passes result as arg)
  5. save_data            - Depends on: prepare_storage (passes result as arg)
  6. generate_report      - Depends on: save_data (passes result as arg), calculate_stats (passes result as kwarg)
```

Key observations:
- **fetch_data** starts first with no dependencies
- **validate** and **calculate_stats** can run in parallel (both depend only on fetch_data)
- **prepare_storage** waits for both validate and calculate_stats to complete
- **save_data** depends on prepare_storage
- **generate_report** depends on both save_data AND calculate_stats results, passing them in different ways

## Code Walkthrough

### Understanding TaskDependency
See how Task objects receive a list with their dependencies. Each `TaskDependency` object points to another task and specifies how to pass its result.

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
            use_result_as_additional_args=True,  # Pass fetch result as positional arg
        )
    ],
)

# Task 3: Calculate stats (depends on fetch, but also checks validate completion)
t_stats = Task(
    "calculate_stats",
    f"{log_dir}/stats.log",
    calculate_statistics,
    dependencies=[
        TaskDependency(
            "fetch_data",
            use_result_as_additional_args=True,  # Pass fetch result as positional arg
        )
    ],
)

# Task 4: Prepare (depends on both validate and stats, passing both results)
t_prepare = Task(
    "prepare_storage",
    f"{log_dir}/prepare.log",
    prepare_for_storage,
    dependencies=[
        TaskDependency(
            "validate",
            use_result_as_additional_args=True,  # validate result → 1st arg
        ),
        TaskDependency(
            "calculate_stats",
            use_result_as_additional_args=True,  # stats result → 2nd arg
        ),
    ],
)
```


### Using Keyword Arguments

Task results can also be passed as keyword arguments:

```python
def generate_report(save_result: str, stats: dict | None = None) -> str:
    """Generate final report with optional statistics."""
    if stats is None:
        stats = {"avg_age": 0, "avg_salary": 0, "total_records": 0, "age_range": (0, 0), "salary_range": (0, 0)}
    # Use both save_result and stats to generate report
    ...

t_report = Task(
    "generate_report",
    "logs/report.log",
    generate_report,
    dependencies=[
        TaskDependency(
            "save_data",
            use_result_as_additional_args=True,  # save_data result → positional arg
        ),
        TaskDependency(
            "calculate_stats",
            use_result_as_additional_kwargs=True,
            additional_kwarg_name="stats"  # calculate_stats result → 'stats' kwarg
        ),
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
