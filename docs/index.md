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
* [📧 Customizing the HTML email](#-customizing-the-html-email)
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
Define your tasks and their dependencies. **Processes** will handle the execution order and data injection between tasks.

```python
from datetime import date

from processes import Process, Task, TaskDependency, HTMLSMTPHandler

# 1. Setup Email Alerts (Optional)
smtp_handler = HTMLSMTPHandler(
    ('smtp_server', 587), 'sender@example.com', ['admin@example.com', 'user@example.com'],
    credentials=('user', 'pass'),
    secure=(),                       # () = STARTTLS; omit for no encryption
    email_style='modern',            # classic | modern | compact
    color_palette='neutral',         # neutral | catppuccin | neobones | slate
    email_language='en',             # en | es | pt | fr | de | it
)

# 2. If necessary, create wrappers for your Tasks.
def get_previous_working_day():
    return date(2025, 12, 30)
def indep_task():
    return "foo"
def search_and_sum_csv(t: date):
    return 10
def sum_data_from_csv_and_x(x, a=1, b=2):
    return x + a + b

# 3. Create the Task Graph (order is irrelevant, that is handled by Process)
tasks = [
    Task("t-1", "etl.log", get_previous_working_day),
    Task("intependent", "indep.log", indep_task, html_mail_handler=smtp_handler),  # This task will send email on failure
    Task("sum_csv", "etl.log", search_and_sum_csv,
            dependencies= [
                TaskDependency("t-1",
                use_result_as_additional_args=True)  # Adds result of t-1 task to search_and_sum_csv function as aditional args
            ]
        ),
    Task("sum_x_and_csv", "etl.log", sum_data_from_csv_and_x,
            args = (10,), kwargs = {"b": 100},
            dependencies=[
                TaskDependency("sum_csv",
            use_result_as_additional_kwargs=True,
            additional_kwarg_name="a")
        ]
    )
]

# 4. Run the Process
with Process(tasks) as process: # Context Manager ensures correct disposal of loggers
    process_result = process.run() # To enable parallelization use .run(parallel=True)

```

---

## 📧 Customizing the HTML email

When a task with an `HTMLSMTPHandler` raises, the alert is a **styled HTML
email** built from a bundled template. The body includes the exception,
the traceback (with the user-frame highlighted), the task context, the
list of downstream tasks that were skipped because of the failure, and
the local variables at the failing frame (see [Traced Variables](#traced-variables) below).

Four keyword-only arguments on `HTMLSMTPHandler` control the look, the language, and which frame's locals appear in the email body:

| Argument | Values | Default |
|---|---|---|
| `email_style` | `classic`, `modern`, `compact` | `modern` |
| `color_palette` | `neutral`, `catppuccin`, `neobones`, `slate` | `neutral` |
| `email_language` | `en`, `es`, `pt`, `fr`, `de`, `it` | `en` |
| `last_path_traced_vars` | any path substring, or `None` | `None` (outermost user frame) |

```python
from processes import HTMLSMTPHandler

smtp = HTMLSMTPHandler(
    mailhost=("smtp.example.com", 587),
    fromaddr="alerts@example.com",
    toaddrs=["oncall@example.com"],
    credentials=("user", "pass"),
    secure=(),                          # () = STARTTLS; omit for no encryption
    email_style="compact",              # classic | modern | compact
    color_palette="catppuccin",         # neutral | catppuccin | neobones | slate
    email_language="es",                # en | es | pt | fr | de | it
)
```

All assets ship inside the wheel — the styles are Jinja-style HTML
templates at `src/processes/themes/styles/` and the palettes are CSS
fragments at `src/processes/themes/palettes/`. No template engine or
extra install is required; the formatter composes them at send time.

### Traced Variables

On failure, the email body includes the local variables of the
**outermost user frame in the traceback** — i.e. the last frame in
the chain that is not inside `site-packages` or your virtualenv.
A `file:line` reference next to the section tells you exactly where
in the source the listed values were captured, which is usually the
fastest way to figure out *why* a complex task broke deep inside a
wrapper.

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