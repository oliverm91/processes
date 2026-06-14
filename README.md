<div align="center">
  <img src="https://raw.githubusercontent.com/oliverm91/processes/refs/heads/main/assets/banner.svg" width="100%" alt="Processes - Smart Task Orchestration">
</div>

# Processes: Smart Task Orchestration

[![Python Version](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/)
![Fast & Lightweight](https://img.shields.io/badge/Library-Pure%20Python-green.svg)
[![Documentation](https://img.shields.io/badge/docs-GitHub%20Pages-blue.svg)](https://oliverm91.github.io/processes/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![PyPI version](https://img.shields.io/pypi/v/processes.svg)](https://pypi.org/project/processes/)

[![Python Tests Status](https://github.com/oliverm91/processes/actions/workflows/tests.yml/badge.svg?branch=main)](https://github.com/oliverm91/processes/actions/workflows/tests.yml)
[![Ruff Lint Status](https://github.com/oliverm91/processes/actions/workflows/lint.yml/badge.svg?branch=main)](https://github.com/oliverm91/processes/actions/workflows/lint.yml)
[![mypy-check](https://github.com/oliverm91/processes/actions/workflows/mypy.yml/badge.svg)](https://github.com/oliverm91/processes/actions/workflows/mypy.yml)

---

**Run a list of Python callables that depend on each other — in parallel when possible, with per-task log files and optional HTML email notification on failure. Zero dependencies. Pure Python 3.10+.**

---

## ✨ Why Processes?

- 🔗 **Declare what depends on what** — write your tasks in any order; the runtime sorts them so every dependency runs first.
- ⚡ **Run in parallel when you can** — independent tasks run together on a thread pool; the runtime switches on automatically for jobs with 10+ tasks.
- 🛡️ **One failure doesn't stop the rest** — a failed task skips only the jobs that depend on it, and **every other part of the workflow keeps running**.
- 📝 **One log file per task** — share a single log across the whole run, or keep them separate for easier debugging.
- 📧 **Email alerts when something breaks** — pass an `SMTPConfig` to a task and get a styled HTML email (with traceback, task context, and the list of jobs that were skipped) the instant it raises.
- 🧰 **Modern, strictly-typed Python 3.10+** — `from __future__ import annotations`, full `mypy --strict` clean, `dict[str, TaskResult]`, `set[str]`, `|` unions.

---

## ⚙️ How it works

A `Process` holds a list of `Task`s. At construction it validates names, types, dependency references, and detects cycles — raising before anything runs. 

When you call `process.run()`, tasks are topologically sorted and scheduled: dependencies first, independent tasks in parallel.

A `TaskDependency` can forward an upstream result directly into a downstream function, as a positional or keyword argument. The result is a `ProcessResult` with `passed_tasks_results` and `failed_tasks` for inspection.

---

## 🚀 Quick start

A 15-line "hello pipeline" — one upstream task feeding a downstream one, run in parallel.

```python
from processes import Process, Task, TaskDependency


def load_users() -> list[dict]:
    return [{"id": 1}, {"id": 2}, {"id": 3}]


def enrich(users: list[dict]) -> list[dict]:
    return [{**u, "name": f"user-{u['id']}"} for u in users]


tasks = [
    Task("load", "run.log", load_users),
    Task(
        "enrich",
        "run.log",
        enrich,
        dependencies=[TaskDependency("load", use_result_as_additional_args=True)],
    ),
]

with Process(tasks) as p:
    result = p.run(parallel=True)

print(result.passed_tasks_results["enrich"].result)
# [{'id': 1, 'name': 'user-1'}, {'id': 2, 'name': 'user-2'}, {'id': 3, 'name': 'user-3'}]
```

---

## 🧪 End-to-end example

A realistic mini-pipeline: fetch two sources **in parallel**, transform them, aggregate, and notify — with per-task log files, result piping, and one task deliberately failing to show fault isolation.

<details>
<summary>Show the full end-to-end example</summary>

```python
import logging
from pathlib import Path

from processes import EmailChannel, HTMLEmailStyle, Process, SMTPConfig, Task, TaskDependency

LOG_DIR = Path("logs")
LOG_DIR.mkdir(exist_ok=True)


# --- 1. Two independent "fetch" tasks that run in parallel -----------------
def fetch_orders() -> list[dict]:
    logging.info("querying orders API")
    return [{"order_id": 1, "amount": 42.0}, {"order_id": 2, "amount": 17.5}]


def fetch_inventory() -> list[dict]:
    logging.info("querying inventory API")
    return [{"sku": "A-1", "qty": 12}, {"sku": "B-2", "qty": 3}]


# --- 2. Two transforms that consume the upstream results -------------------
def total_revenue(orders: list[dict]) -> float:
    total = sum(o["amount"] for o in orders)
    logging.info("revenue computed: %s", total)
    return total


def stock_value(inventory: list[dict], *, price_per_unit: float = 10.0) -> float:
    value = sum(i["qty"] for i in inventory) * price_per_unit
    logging.info("stock value: %s", value)
    return value


# --- 3. An aggregator that joins the two branches --------------------------
def build_report(*, revenue: float, stock: float) -> str:
    return f"daily-report | revenue={revenue:.2f} stock={stock:.2f}"


# --- 4. A flaky notifier that ALWAYS fails — to show fault isolation -------
def notify_slack(report: str) -> None:
    raise RuntimeError("slack webhook returned 503")


# --- 5. A sibling task that does NOT depend on notify and still runs -------
def archive_report(report: str) -> str:
    out = LOG_DIR / "report.txt"
    out.write_text(report)
    return str(out)


# --- 6. Optional: SMTP config so failures page on-call --------------------
smtp = SMTPConfig(
    mailhost=("smtp.example.com", 587),
    fromaddr="alerts@example.com",
    toaddrs=["oncall@example.com"],
    credentials=("user", "pass"),
    secure=(),
)

tasks = [
    Task("fetch_orders",   LOG_DIR / "fetch_orders.log",   fetch_orders),
    Task("fetch_inventory", LOG_DIR / "fetch_inventory.log", fetch_inventory),

    Task(
        "compute_revenue",
        LOG_DIR / "compute_revenue.log",
        total_revenue,
        dependencies=[TaskDependency("fetch_orders", use_result_as_additional_args=True)],
    ),
    Task(
        "compute_stock",
        LOG_DIR / "compute_stock.log",
        stock_value,
        kwargs={"price_per_unit": 7.25},
        dependencies=[
            TaskDependency(
                "fetch_inventory",
                use_result_as_additional_kwargs=True,
                additional_kwarg_name="inventory",
            )
        ],
    ),

    Task(
        "build_report",
        LOG_DIR / "build_report.log",
        build_report,
        dependencies=[
            TaskDependency("compute_revenue", use_result_as_additional_kwargs=True,
                           additional_kwarg_name="revenue"),
            TaskDependency("compute_stock",    use_result_as_additional_kwargs=True,
                           additional_kwarg_name="stock"),
        ],
    ),

    # notify_slack fails on purpose. archive_report is a *sibling*
    # of notify_slack (both depend on build_report), so it has no
    # dependency on the failed task and runs normally — the rest of
    # the workflow is not blackholed by one broken step.
    Task(
        "notify_slack",
        LOG_DIR / "notify_slack.log",
        notify_slack,
        dependencies=[TaskDependency("build_report", use_result_as_additional_args=True)],
        channels=[EmailChannel(smtp)],
    ),
    Task(
        "archive_report",
        LOG_DIR / "archive_report.log",
        archive_report,
        dependencies=[TaskDependency("build_report", use_result_as_additional_args=True)],
    ),
]

with Process(tasks) as process:
    result = process.run(parallel=True)

print("passed:", sorted(result.passed_tasks_results))
# archive_report, build_report, compute_revenue, compute_stock, fetch_inventory, fetch_orders
print("failed:", sorted(result.failed_tasks))
# notify_slack
print("report:", result.passed_tasks_results["build_report"].result)
# daily-report | revenue=59.50 stock=262.50
```

The failing `notify_slack` task does **not** abort the run. `archive_report` is a sibling of the failed task (both depend on the successful `build_report`), so it runs unaffected — the rest of the workflow is not blackholed by one broken step. The HTML email handler also fires on the `notify_slack` task, paging on-call with the full traceback and the list of downstream tasks that were skipped because of it.

</details>

---

## 📚 API Reference

<details>
<summary>Show API reference</summary>

### `Task`

```python
Task(
    name: str,
    log_path: str | os.PathLike,
    func: Callable[..., Any],
    args: tuple = (),
    kwargs: dict | None = None,
    dependencies: list[TaskDependency] | None = None,
    channels: list[NotificationChannel] | None = None,
    timeout: float | None = None,
    retries: int | None = 0,
    retry_on: tuple[type[Exception], ...] | None = None,
)
```

- `name` — unique within the `Process`; no spaces.
- `log_path` — the file this task logs to (INFO level, format `%(asctime)s - %(name)s - %(levelname)s - %(message)s`); wired internally into a file `NotificationChannel`.
- `func` — the callable; receives `func(*args, **kwargs)` after result-injection.
- `channels` — additional `NotificationChannel`s attached to the task's logger. Use `EmailChannel(smtp_config, style=None)` to fire an HTML email on `logging.ERROR`; body includes `task_name`, `function`, `args`, `kwargs`, and `downstream_impact`. `style` defaults to `HTMLEmailStyle()` (modern, neutral, English).
- `timeout` — seconds allowed per attempt; `None` means no limit. When the timeout fires the underlying thread is detached (Python threading limitation).
- `retries` — additional attempts after the first failure; `0` or `None` means a single attempt. Defaults to `0`.
- `retry_on` — tuple of exception types that trigger a retry. When `retries >= 1` and `retry_on` is `None`, defaults to `(ConnectionError, TimeoutError)` at call time.

### `TaskDependency`

```python
TaskDependency(
    task_name: str,
    use_result_as_additional_args: bool = False,
    use_result_as_additional_kwargs: bool = False,
    additional_kwarg_name: str = "",
)
```

- `use_result_as_additional_args=True` — upstream result appended as the next **positional** arg.
- `use_result_as_additional_kwargs=True` with a non-empty `additional_kwarg_name` — upstream result injected as a **keyword** arg.
- Both flags can be combined (positional first, then kwarg).

### `Process`

```python
Process(tasks: list[Task])  # validates types, names, deps, cycles

process.run(parallel: bool | None = None, max_workers: int = 4) -> ProcessResult
```

- Raises `DependencyNotFoundError`, `CircularDependencyError`, `TypeError`, `ValueError` on construction if the workflow is malformed.
- `parallel=None` auto-parallelises when `len(tasks) >= 10`; `max_workers=1` is always sequential.
- Use as a context manager — it cleans up `FileHandler`s on exit.

### `ProcessResult`

```python
result.passed_tasks_results  # dict[str, TaskResult] — name → TaskResult for every task that succeeded
result.failed_tasks          # set[str] — all tasks that did not produce a result (errored + skipped)
result.errored_tasks         # set[str] — tasks whose function actually raised
result.skipped_tasks         # set[str] — tasks skipped because an upstream dependency failed

TaskResult(worked: bool, result: Any, exception: Exception | None)
```

### `SMTPConfig`

```python
SMTPConfig(
    mailhost,                      # (host, port)
    fromaddr,
    toaddrs,                       # list[str]
    credentials=None,              # (username, password) | None
    secure=None,                   # () = STARTTLS; omit for no encryption
    timeout=5,
)
```

### `HTMLEmailStyle`

```python
HTMLEmailStyle(
    style="modern",                # classic | modern | compact
    palette="neutral",             # neutral | catppuccin | neobones | slate
    language="en",                 # en | es | pt | fr | de | it
    traced_vars_frame_filter=None, # substring to pick the traced frame | None
)
```

### `NotificationChannel`

```python
NotificationChannel  # ABC: subclass and implement build_handler(task_name) -> logging.Handler
```

Every `Task` always attaches an internal file channel built from `log_path`. Extra channels passed via `channels` are attached on top of it.

### `EmailChannel`

```python
EmailChannel(
    smtp_config: SMTPConfig,
    style: HTMLEmailStyle | None = None,  # defaults to HTMLEmailStyle()
)
```

Fires a styled HTML email on `logging.ERROR` and above.

All fields are optional — omit `HTMLEmailStyle` entirely to use the defaults.

#### Traced Variables

On failure, the email body includes the local variables of the **outermost
user frame in the traceback** — i.e. the last frame that is not inside
`site-packages` or your virtualenv. A `file:line` reference next to the
section shows exactly where those values were captured.

`traced_vars_frame_filter` lets you point this at a different frame: set it
to a path substring (e.g. one of your own package or module names) to
capture locals from the outermost frame whose filename contains that
substring instead. This is useful for deep-debugging code that runs through
several layers of internal libraries or wrappers, where the default
outermost-user-frame would land too high up the call stack.

</details>

<details>
<summary>Show fault-tolerance rules in detail</summary>

When a task raises:

1. The exception is caught and stored in `TaskResult.exception`; the task name goes into `failed_tasks` and `errored_tasks`.
2. **Every task that depends on it (directly or indirectly) is skipped** — added to `failed_tasks` and `skipped_tasks` without running.
3. **Every other independent part of the workflow keeps running.** With `parallel=True` they keep running concurrently on the worker pool.
4. After `run()` returns, `ProcessResult.errored_tasks` and `ProcessResult.skipped_tasks` let you distinguish root failures from cascade skips for triage or alerting.

When a task has `retries >= 1`, a failure matching `retry_on` triggers another attempt before the task is declared failed and its dependants are skipped. This gives transient errors (network blips, connection resets) a chance to resolve without aborting downstream work.

This makes the library a good fit for fan-out / fan-in pipelines, "best-effort" notifications, and any workflow where one broken step should not blackhole the rest.

</details>

<details>
<summary>Show comparison with other libraries</summary>

| | **Processes** | Airflow | Celery | Luigi |
|---|---|---|---|---|
| External dependencies | **None** | many | broker (Redis/RabbitMQ) | few |
| Setup cost | `pip install` | cluster | broker + workers | task + config |
| Parallelism | built-in | via executors | via workers | via workers |
| Per-task file logs | **yes (built-in)** | via handlers | via signals | partial |
| HTML email on failure | **yes (built-in)** | via callbacks | via signals | manual |
| DAG validation at construction | **yes** | yes (DAG file) | n/a | partial |
| Strict typing (`mypy --strict`) | **yes** | partial | partial | no |

`Processes` is **not** a distributed scheduler — there are no workers on remote machines, no SLA monitoring, no web UI. If you need any of those, you need Airflow or a similar orchestrator. If you want a small, fast, dependency-aware pipeline that *just runs* in a single process, this is it.

</details>

<details>
<summary>Show advanced configuration</summary>

- **Shared log file** — pass the same `log_path` to every `Task` for a single combined run.log; pass distinct paths for per-task isolation.
- **Auto-parallel** — `Process.run()` with no argument runs sequentially for small workflows and switches to parallel for `len(tasks) >= 10`. Pass `parallel=True` or `parallel=False` to force the mode.
- **Result inspection** — iterate `result.passed_tasks_results.items()` to log or post-process every successful task; iterate `result.failed_tasks` for triage.
- **Re-raising** — wrap `process.run()` in `try/except` if you need a non-zero exit code on any failure; the library itself does not raise on partial failure.

</details>

---

## 📦 Installation

From PyPI:

```bash
pip install processes
```

Or straight from the repository (pure Python, no build step):

```bash
pip install git+https://github.com/oliverm91/processes.git
```

Requires **Python 3.10+**.

---

## 📄 License & contributing

Released under the **MIT License** — see [docs](https://oliverm91.github.io/processes/) for full API details.

Contributions welcome — see [CONTRIBUTING.md](CONTRIBUTING.md) for the workflow, style, and commit-message conventions used by this project.
