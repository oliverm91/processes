"""
Example 3: Reports & Notifications

This example demonstrates the report-centric model: after a Process runs, you get
a ProcessExecutionReport that lets you triage what happened and deliver a single
notification for the whole run.

Demonstrates:
- Naming a Process so the name appears in the email subject and webhook payload
- Partial failure: a failing task cascade-skips its dependents while unrelated
  tasks keep running
- Inspecting the report (successes / errored / skipped) for triage
- Serializing the whole run with report.to_json()
- Delivering the report through EmailChannel and WebhookChannel in one notify()
- The only_errors and tasks filters, and the ReportContent verbosity presets

Notifications are only attempted when SEND_NOTIFICATIONS=1 is set in the
environment (so the example runs fully offline by default). Even when attempted,
notify() never raises: a channel that fails only emits a warning.
"""

import os

from processes import (
    EmailChannel,
    HTMLEmailStyle,
    Process,
    ProcessExecutionReport,
    ReportContent,
    SMTPConfig,
    Task,
    TaskDependency,
    TaskStatus,
    WebhookChannel,
    WebhookConfig,
)


# Step 1: Define task functions ------------------------------------------------
def fetch_inventory() -> dict:
    """Independent root task — succeeds and feeds enrich_pricing."""
    return {"skus": ["A-1", "B-2", "C-3"], "warehouse": "us-east-1"}


def enrich_pricing(inventory: dict) -> dict:
    """Dependent task — runs because its upstream succeeded."""
    priced = {sku: round(10.0 + i, 2) for i, sku in enumerate(inventory["skus"])}
    return {"warehouse": inventory["warehouse"], "prices": priced}


def charge_payments(priced: dict) -> dict:
    """Fails from a frame rich in local variables (good traced-vars demo).

    With retries >= 1 and retry_on set, a transient error is retried before the
    task is finally declared failed.
    """
    gateway = "https://payments.internal/charge"
    attempt_budget = 3
    pending = list(priced["prices"])
    raise ConnectionError(
        f"gateway {gateway!r} refused the connection (budget={attempt_budget}, pending={pending})"
    )


def ship_orders(charge_result: dict) -> str:
    """Depends on charge_payments — must be cascade-skipped, never runs."""
    return f"shipped {len(charge_result)} orders"


def archive_logs() -> str:
    """Independent task — keeps running even though charge_payments failed."""
    return "logs archived to cold storage"


def build_tasks(log_dir: str) -> list[Task]:
    """A 5-task DAG: 3 successes, 1 failure, 1 cascade-skipped dependent."""
    return [
        Task("fetch_inventory", fetch_inventory, f"{log_dir}/fetch.log"),
        Task(
            "enrich_pricing",
            enrich_pricing,
            f"{log_dir}/enrich.log",
            dependencies=[TaskDependency("fetch_inventory", use_result_as_additional_args=True)],
        ),
        # Failing task: retried twice on ConnectionError before it is given up on.
        Task(
            "charge_payments",
            charge_payments,
            f"{log_dir}/charge.log",
            dependencies=[TaskDependency("enrich_pricing", use_result_as_additional_args=True)],
            retries=2,
            retry_on=(ConnectionError,),
        ),
        # Dependent on the failing task -> cascade-skipped.
        Task(
            "ship_orders",
            ship_orders,
            f"{log_dir}/ship.log",
            dependencies=[TaskDependency("charge_payments", use_result_as_additional_args=True)],
        ),
        # Unrelated independent task -> keeps running.
        Task("archive_logs", archive_logs, f"{log_dir}/archive.log"),
    ]


# Step 2: Inspect the report ---------------------------------------------------
def triage(report: ProcessExecutionReport) -> None:
    """Print a per-status breakdown — distinguish root failures from skips."""
    print("\noutcome:")
    for name, entry in report.entries.items():
        print(f"  {entry.status.value:8s}  {name}  ({entry.attempts} attempt(s))")

    print(f"\n  successes : {sorted(report.successes)}")
    print(f"  errored   : {sorted(report.errored)}   <- root failures")
    print(f"  skipped   : {sorted(report.skipped)}   <- cascade impact")

    # The whole run, losslessly, as a JSON string (e.g. to archive or ship).
    print(f"\n  to_json() head: {report.to_json()[:80]} ...")


# Step 3: Deliver the report ---------------------------------------------------
def deliver(report: ProcessExecutionReport) -> None:
    """Send the report through email + webhook in a single notify() call.

    Only attempted when SEND_NOTIFICATIONS=1; otherwise we just describe it.
    """
    email = EmailChannel(
        SMTPConfig(
            mailhost=("127.0.0.1", 1025),
            fromaddr="pipeline@example.test",
            toaddrs=["oncall@example.test"],
        ),
        # palette + language for the HTML body.
        HTMLEmailStyle(palette="slate", language="en"),
        # Verbosity preset: full traceback + traced local variables.
        ReportContent(show_traceback=True, show_traced_vars=True),
    )
    webhook = WebhookChannel(
        WebhookConfig(
            url="https://hooks.example.test/incoming",
            secret="s3cr3t",  # signs the body with HMAC-SHA256
            nest_under="report",
        )
    )

    if os.environ.get("SEND_NOTIFICATIONS") != "1":
        print("\n[notify] SEND_NOTIFICATIONS!=1 - skipping actual delivery.")
        print("         would send only_errors=True to email + webhook.")
        print("         the email subject embeds the process name + run date,")
        print("         and the webhook payload includes process_name.")
        return

    # Both channels get the report; only_errors restricts payload to failures.
    # notify() never raises — an unreachable channel only emits a warning.
    report.notify(email, webhook, only_errors=True)

    # You can also scope a delivery to specific tasks (case-insensitive):
    report.notify(email, tasks=["charge_payments"])


def main() -> None:
    log_dir = "logs"
    os.makedirs(log_dir, exist_ok=True)

    tasks = build_tasks(log_dir)
    # Naming the process: the name flows into the report, the email subject, and
    # the webhook payload.
    with Process(tasks, name="orders-pipeline") as process:
        report = process.run(parallel=False)

    assert report.process_name == "orders-pipeline"
    assert set(report.errored) == {"charge_payments"}
    assert set(report.skipped) == {"ship_orders"}
    assert report.entries["charge_payments"].status is TaskStatus.ERRORED

    triage(report)
    deliver(report)


if __name__ == "__main__":
    main()
