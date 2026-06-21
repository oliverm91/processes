# Example 3: Reports & Notifications

## 👁️‍🗨️ Overview

Every `Process.run()` returns a **`ProcessExecutionReport`** — a per-task
breakdown of the run in topological order. Instead of sending an alert from
inside each task, you inspect the report and deliver **one** notification for the
whole run. This example shows triage and delivery together.

## 🔁 Scenario

An orders pipeline of 5 tasks. The payment step fails, which cascade-skips
shipping, while the unrelated archive step keeps running:

```
[1] fetch_inventory ─→ [2] enrich_pricing ─→ [3] charge_payments ─✗─→ [4] ship_orders (skipped)

[5] archive_logs   (independent, keeps running)
```

Result: **3 successes**, **1 errored** (`charge_payments`), **1 skipped**
(`ship_orders`).

## 💻 Code Walkthrough

### Naming the process

```python
from processes import Process, Task, TaskDependency

with Process(tasks, name="orders-pipeline") as process:
    report = process.run(parallel=False)
```

The optional `name` is recorded on the report as `report.process_name` and is
used to label notifications (the email subject and the webhook payload).

### Triaging the report

```python
report.successes   # {name: TaskReportEntry} for status == SUCCESS
report.errored     # root failures
report.skipped     # tasks cascade-skipped because a dependency failed/skipped

for name, entry in report.entries.items():
    print(entry.status.value, name, entry.attempts, entry.elapsed_seconds)
```

`errored` vs `skipped` is the key distinction: `errored` are the tasks that
actually raised; `skipped` are the downstream tasks that never ran because of
them. You can serialize everything losslessly with `report.to_json()`.

### A failing task with retries

```python
Task(
    "charge_payments",
    charge_payments,
    "logs/charge.log",
    dependencies=[TaskDependency("enrich_pricing", use_result_as_additional_args=True)],
    retries=2,
    retry_on=(ConnectionError,),
)
```

With `retries=2` and `retry_on`, a transient `ConnectionError` is retried twice
before the task is finally declared failed (the report shows `attempts == 3`).

## 📧 Delivering the report

`report.notify(*channels, ...)` renders and sends the report through each
channel, in order. A channel that fails only emits a warning — `notify()` never
raises, so one broken destination never aborts the rest.

```python
from processes import (
    EmailChannel, HTMLEmailStyle, ReportContent, SMTPConfig,
    WebhookChannel, WebhookConfig,
)

email = EmailChannel(
    SMTPConfig(
        mailhost=("127.0.0.1", 1025),
        fromaddr="pipeline@example.test",
        toaddrs=["oncall@example.test"],
    ),
    HTMLEmailStyle(palette="slate", language="en"),
    ReportContent(show_traceback=True, show_traced_vars=True),
)
webhook = WebhookChannel(
    WebhookConfig(url="https://hooks.example.test/incoming", secret="s3cr3t", nest_under="report")
)

report.notify(email, webhook, only_errors=True)
```

### Filters

- **`only_errors=True`** — each channel restricts its payload to `ERRORED`
  entries (useful for on-call alerts).
- **`tasks=[...]`** — restrict the report to specific task names
  (case-insensitive). Combines with `only_errors`.

```python
report.notify(email, tasks=["charge_payments"])
```

### Content presets (`ReportContent`)

`ReportContent` controls how much detail each failure shows — independent of
`only_errors`:

| Preset | `show_traceback` | `show_traced_vars` | Shows |
|--------|:---:|:---:|---|
| full   | ✅ | ✅ | Traceback **and** captured local variables |
| trace  | ✅ | ❌ | Traceback only |
| min    | ❌ | ❌ | Task name, status and error message only |

`HTMLEmailStyle` independently controls the email **palette** (`neutral`,
`catppuccin`, `neobones`, `slate`) and **language** (`en`, `es`, `pt`, `fr`,
`de`, `it`).

## ▶️ Running the example

The runnable script lives in
[`examples/03_reports_and_notifications/`](https://github.com/oliverm91/processes/tree/main/examples/03_reports_and_notifications).
It runs fully offline by default (it only *describes* the notifications); set
`SEND_NOTIFICATIONS=1` to attempt actual delivery against a local SMTP/webhook.
