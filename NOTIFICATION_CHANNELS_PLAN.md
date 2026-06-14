# Plan: Notification Channel abstraction

Branch: `feature/notification-channels`

## Goal

Introduce an internal `NotificationChannel` abstraction that the two existing
delivery mechanisms — the per-task **log file** and the **HTML email** alert —
are expressed through. This refactor enables adding new notification handlers
later (Telegram, Slack, Discord, …) by simply implementing a new
`NotificationChannel` subclass, without touching `Task` internals.

**In scope (this branch):**
- Define the `NotificationChannel` abstract base class.
- Wrap the two *existing* handlers as channels: `_FileChannel` (internal) and
  `EmailChannel` (public).
- Wire `Task` to build its logger handlers through these channels.
- Expose a `channels` parameter on `Task` so extra channels can be plugged in
  (the extensibility point).
- Tests, type checking (mypy strict) and lint (ruff) green.

**Out of scope (explicitly NOT in this branch):**
- No new concrete channels (no Telegram/Slack/Discord). Only the abstraction +
  the two current handlers.
- No final merge / PR — the maintainer will open the PR.

## Design

### Abstraction

```python
class NotificationChannel(ABC):
    @abstractmethod
    def build_handler(self, task_name: str) -> logging.Handler: ...
```

A channel knows how to build a fully configured `logging.Handler`. `Task`
iterates over its channels and attaches each handler to its logger. This keeps
the existing `record.task_context` failure-context flow intact — channels reuse
the same formatters (`_TaskLogfileFormatter`, `_HTMLEmailFormatter`).

### Concrete channels (wrapping current handlers)

- `_FileChannel(log_path, level=logging.INFO)` (internal) → builds the
  `FileHandler` with `_TaskLogfileFormatter` (current logfile behaviour).
- `EmailChannel(smtp_config, style=None)` (public) → delegates to the existing
  `_build_task_email_handler(smtp_config, style, task_name)` (current email
  behaviour: `ERROR` level, localized subject).

### `Task` wiring (breaking change)

`smtp_config` and `email_style` are removed from `Task.__init__` entirely.
`log_path` remains the only logging-related required argument and is
converted internally into a `_FileChannel`. Everything else — including email
alerts — is configured via `channels: list[NotificationChannel]`, positioned
right after `dependencies` and before `timeout`:

```python
def __init__(
    self, name, log_path, func, args=(), kwargs=None,
    dependencies=None, channels: list[NotificationChannel] | None = None,
    timeout=None, retries=0, retry_on=None,
):
    ...
    all_channels: list[NotificationChannel] = [_FileChannel(self.log_path), *self.channels]
    for channel in all_channels:
        logger.addHandler(channel.build_handler(self.name))
    self._frame_filter = next(
        (c.frame_filter for c in all_channels if c.frame_filter is not None), None
    )
```

- `_frame_filter` (traced-vars frame filter) is sourced from the first channel
  that defines a non-`None` `frame_filter` property (e.g. `EmailChannel`,
  via `style.traced_vars_frame_filter`); it governs how failure context is
  *built*, independent of delivery.
- To get email alerts, pass `channels=[EmailChannel(smtp_config, style)]`.

### Public API exports

Export `NotificationChannel` and `EmailChannel` from `processes/__init__.py`.
`_FileChannel` stays internal.

## Files

- `src/processes/notification_channels.py` — new module (ABC + two channels).
- `src/processes/task.py` — build handlers via channels; `channels` param
  replaces `smtp_config`/`email_style`.
- `src/processes/__init__.py` — export the new public names.
- `tests/test_notification_channels.py` — new test module.

## Testing

- `NotificationChannel` cannot be instantiated directly (is abstract).
- `_FileChannel.build_handler` returns a `FileHandler` at the right level with
  `_TaskLogfileFormatter`, writing to the given path.
- `EmailChannel.build_handler` returns an `ERROR`-level handler with the
  localized subject (mock SMTP, mirroring `test_email_themes.py`).
- Integration: a `Task` with a custom extra channel attaches its handler;
  the implicit file channel and any `EmailChannel` in `channels` keep working.
- Full existing suite (updated to the new `channels` API) stays green.

## Commit sequence (conventional commits, no Claude attribution)

Commit only after the relevant tests + ruff + mypy pass.

1. `docs: add notification channel abstraction plan` — this file.
2. `feat: add NotificationChannel abstraction with file and email channels`
   — new module + unit tests + exports.
3. `refactor: build task handlers through notification channels`
   — wire `Task` to channels, add `channels` param, integration tests,
   docstring updates.

No final merge; push the branch so it appears on GitHub for the maintainer's PR.
