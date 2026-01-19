# Example 1: Simple Independent Tasks

**Difficulty:** ⭐ Beginner  
**Time to understand:** 5 minutes

## Overview

This example demonstrates how to create and execute multiple independent (no dependencies) tasks. Use this when you have a set of unrelated operations that can potentially run in parallel.

## What You'll Learn

✅ Creating basic Task objects  
✅ Adding tasks to a Process  
✅ Running tasks sequentially vs in parallel  
✅ Accessing task results  
✅ Understanding execution timing  

## Scenario

Imagine you need to:
1. Fetch user count from a database
2. Fetch product count from a database  
3. Fetch order count from a database

All three operations are independent and can run in parallel.

## Code Walkthrough

### Step 1: Define Your Task Functions

Each task needs a callable (function) that performs the work:

```python
def fetch_user_count() -> int:
    """Simulate fetching user count."""
    time.sleep(2)  # Simulate I/O operation
    return 1000

def fetch_product_count() -> int:
    """Simulate fetching product count."""
    time.sleep(2)  # Simulate I/O operation
    return 5000

def fetch_order_count() -> int:
    """Simulate fetching order count."""
    time.sleep(2)  # Simulate I/O operation
    return 15000
```

### Step 2: Create Task Objects

Each task needs:
- **name**: Unique identifier (no spaces allowed)
- **log_path**: Where to write logs
- **func**: The callable to execute
- **dependencies** (optional): TaskDependency objects for dependent tasks

```python
t1 = Task("fetch_users", "logs/fetch_users.log", fetch_user_count)
t2 = Task("fetch_products", "logs/fetch_products.log", fetch_product_count)
t3 = Task("fetch_orders", "logs/fetch_orders.log", fetch_order_count)
t4 = Task(
    "calculate_metrics",
    "logs/calculate_metrics.log",
    calculate_metrics,
    dependencies=[
        TaskDependency("fetch_users", use_result_as_additional_args=True),
        TaskDependency("fetch_products", use_result_as_additional_args=True),
        TaskDependency("fetch_orders", use_result_as_additional_args=True),
    ]
)
```

### Step 3: Create Process and Execute

Use a context manager for automatic cleanup:

```python
with Process([t1, t2, t3, t4]) as process:
    # Sequential execution: ~6 seconds total (2+2+2+1)
    start = time.time()
    _ = process.run(parallel=False)
    duration_seq = time.time() - start
    
with Process([t1, t2, t3, t4]) as process:
    # Parallel execution: ~2 seconds total (all run concurrently)
    start = time.time()
    _ = process.run(parallel=True, max_workers=4)
    duration_par = time.time() - start
```


## Key Concepts

### Process Context Manager

```python
with Process([tasks]) as process:
    result = process.run()
# Automatically closes all loggers after execution
```

This ensures proper resource cleanup even if exceptions occur.

### Parallel vs Sequential

| Aspect | Sequential | Parallel |
|--------|-----------|----------|
| Execution Time | Sum of all task times | Max of task times |
| Worker Threads | 1 | Configurable (default 4) |
| Best For | Simple, dependent tasks | I/O-bound, independent tasks |
| Resource Usage | Low | Medium-High |

### Execution Timing

For three 2-second tasks:
- **Sequential**: ~6 seconds
- **Parallel (3 workers)**: ~2 seconds
- **Parallel (1 worker)**: ~6 seconds (falls back to sequential)

## Common Modifications

### Modify Task Arguments

```python
def fetch_count(table_name: str) -> int:
    # Fetch from specific table
    return database.count(table_name)

task = Task(
    "fetch_users",
    "logs/fetch.log",
    fetch_count,
    args=("users",)  # Pass arguments
)
```

### Modify Task Keyword Arguments

```python
def fetch_with_filter(table: str, status: str = "active") -> int:
    return database.count_where(table, status=status)

task = Task(
    "fetch_active",
    "logs/fetch.log",
    fetch_with_filter,
    args=("users",),
    kwargs={"status": "active"}
)
```

### Different Log Paths

```python
# Separate logs per task
t1 = Task("task1", "logs/task1.log", func1)
t2 = Task("task2", "logs/task2.log", func2)

# Shared log file
t1 = Task("task1", "logs/all.log", func1)
t2 = Task("task2", "logs/all.log", func2)
```