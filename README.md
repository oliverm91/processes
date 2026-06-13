<div align="center">
  <img src="https://raw.githubusercontent.com/oliverm91/processes/refs/heads/main/assets/banner.svg" width="100%" alt="Processes - Smart Task Orchestration">
</div>

# 🚀 Processes: Robust Routines Management

[![Python Version](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/)
![Fast & Lightweight](https://img.shields.io/badge/Library-Pure%20Python-green.svg)


[![Documentation](https://img.shields.io/badge/docs-GitHub%20Pages-blue.svg)](https://oliverm91.github.io/processes/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)


[![Python Tests Status](https://github.com/oliverm91/processes/actions/workflows/tests.yml/badge.svg?branch=main)](https://github.com/oliverm91/processes/actions/workflows/tests.yml)
[![Ruff Lint Status](https://github.com/oliverm91/processes/actions/workflows/lint.yml/badge.svg?branch=main)](https://github.com/oliverm91/processes/actions/workflows/lint.yml)
[![mypy-check](https://github.com/oliverm91/processes/actions/workflows/mypy.yml/badge.svg)](https://github.com/oliverm91/processes/actions/workflows/mypy.yml)

[![PyPI version](https://img.shields.io/pypi/v/processes.svg)](https://pypi.org/project/processes/)




**Processes** is a lightweight, high-performance Python library designed to execute complex task graphs. It manages **dependencies**, handles **parallel execution**, and ensures system resilience without any external libraries.

File logging and **email notification** is supported.

---

## 📑 Table of Contents
* [✨ Features](#-features)
* [⚙️ Core Concepts](#️-core-concepts)
* [🛠️ Use Cases](#️-use-cases)
* [💻 Quick Start](#-quick-start)
* [🛡️ Fault Tolerance & Logs](#️-fault-tolerance--logs)
* [📦 Installation](#-installation)

---

## ✨ Features

* **🐍 Pure Python:** Zero external dependencies. Built entirely on the **Python Standard Library**.
* **⚡ Parallel Execution:** Built-in support for parallelization to maximize throughput.
* **🔗 Dependency Resolution:** Automatically sorts and executes tasks based on their requirements, regardless of input order.
* **📝 Shared Logging:** Multiple tasks can write to the same logfile or maintain separate ones seamlessly.
* **📧 Email Notifications:** Integrated SMTP support (including HTML) to alert you the moment an exception occurs.

---

## ⚙️ Core Concepts

The library operates on two main primitives:

1.  **Task**: The atomic unit of work. It encapsulates a function, its parameters, its specific logfile, and its relationship with other tasks.
2.  **Process**: The orchestrator. It builds the execution graph, validates dependencies, and manages the lifecycle of the entire workflow.


---

## 🛠️ Use Cases
- **ETL Pipelines:** Fetch data from an API, transform it, and load it into a database as separate, dependent tasks.

- **System Maintenance:** Run parallel cleanup scripts, check server health, and receive email alerts if a specific check fails.

- **Automated Reporting:** Generate multiple data parts in parallel, aggregate them into a final report, and distribute via SMTP.


---

## 💻 Quick Start

Four short examples — read top to bottom.

### 1. One task

```python
from processes import Process, Task

def hello():
    return 42

tasks = [Task("greet", "run.log", hello)]

with Process(tasks) as process:
    result = process.run()

print(result.passed_tasks_results["greet"].result)   # 42
```

### 2. `args` and `kwargs`

`args` and `kwargs` are forwarded to your function — like `func(*args, **kwargs)`.

```python
from processes import Process, Task

def fetch(source, *, limit=100, dry_run=False):
    return ["row1", "row2"]

tasks = [
    Task(
        "fetch_orders", "run.log", fetch,
        args=("orders_api",),
        kwargs={"limit": 500, "dry_run": True},
    ),
]

with Process(tasks) as process:
    process.run()
```

### 3. Dependencies + result injection

`TaskDependency` orders tasks. To also pipe the upstream result into the downstream function, pick one:

* `use_result_as_additional_args=True` — appended as the next **positional** argument.
* `use_result_as_additional_kwargs=True` + `additional_kwarg_name="..."` — passed as a **keyword** argument.

```python
from processes import Process, Task, TaskDependency

def load_users():
    return [{"id": 1}, {"id": 2}, {"id": 3}]

def enrich(api_key, users):                # `users` injected positionally
    return [{**u, "name": f"user-{u['id']}"} for u in users]

def summarize(*, enriched, label="report"):  # `enriched` injected as kwarg
    return f"{label}: {len(enriched)} users"

tasks = [
    Task("load", "run.log", load_users),

    Task(
        "enrich", "run.log", enrich,
        args=("MY_API_KEY",),
        dependencies=[
            TaskDependency("load", use_result_as_additional_args=True),
        ],
    ),

    Task(
        "summary", "run.log", summarize,
        kwargs={"label": "daily"},
        dependencies=[
            TaskDependency(
                "enrich",
                use_result_as_additional_kwargs=True,
                additional_kwarg_name="enriched",
            ),
        ],
    ),
]

with Process(tasks) as process:
    result = process.run(parallel=True)

print(result.passed_tasks_results["summary"].result)
# "daily: 3 users"
```

> Task order doesn't matter — `Process` sorts them. A failure only skips its own dependents; the rest keeps running.

### 4. Email alerts on failure

Attach an `HTMLSMTPHandler` to any task. If it raises, an HTML email is sent.

```python
from processes import HTMLSMTPHandler, Process, Task

smtp = HTMLSMTPHandler(
    mailhost=("smtp.example.com", 587),
    fromaddr="alerts@example.com",
    toaddrs=["oncall@example.com"],
    credentials=("user", "pass"),
    secure=(),                             # () = STARTTLS; omit for no encryption
)

tasks = [
    Task("risky_step", "run.log", lambda: 1 / 0, html_mail_handler=smtp),
]

with Process(tasks) as process:
    process.run()
```

---

## 🛡️ Fault Tolerance & Logs
### Resilience by Design
If a `Task` raises an exception, the `Process` **does not stop**. It intelligently skips any tasks that depend on the failed one but continues to execute all other independent branches of your workflow.

### Advanced Logging
All tasks record their execution flow to their assigned logfiles. You can share a single logfile across the whole process or isolate specific tasks for easier debugging.


---

## 📦 Installation

Registered in PyPI: https://pypi.org/project/processes/
```bash
pip install processes
```

Also, since it's a pure Python library, you can install it directly from the repository:

```bash
pip install git+https://github.com/oliverm91/processes.git
```