# Example 3: Reports & Notifications

**When to use:** You want to inspect what a run did, and send a single
notification for the whole run instead of per-task alerts.

After `Process.run()` returns a `ProcessExecutionReport`, you can triage it and
deliver it through one or more channels with `report.notify(...)`.

Covers:
- Naming a `Process` so the name appears in the email subject and webhook payload
- Partial failure: a failing task cascade-skips its dependents while unrelated
  tasks keep running
- Inspecting the report (`successes` / `errored` / `skipped`) for triage
- Serializing the whole run with `report.to_json()`
- Delivering through `EmailChannel` and `WebhookChannel` in one `notify()` call
- The `only_errors` and `tasks` filters, and the `ReportContent` verbosity presets

## Run it

```bash
python example3.py
```

By default the example runs fully offline and only *describes* the notifications.
To actually attempt delivery (e.g. against a local maildev on `127.0.0.1:1025`):

```bash
SEND_NOTIFICATIONS=1 python example3.py
```

`notify()` never raises — an unreachable channel only emits a warning, so the
run is unaffected if a destination is down.
