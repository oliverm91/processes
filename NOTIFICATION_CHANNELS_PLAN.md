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
- Wrap the two *existing* handlers as channels: `FileChannel` and `EmailChannel`.
- Wire `Task` to build its logger handlers through these channels.
- Expose an optional `channels` parameter on `Task` so extra channels can be
  plugged in (the extensibility point).
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

- `FileChannel(log_path, level=logging.INFO)` → builds the `FileHandler` with
  `_TaskLogfileFormatter` (current logfile behaviour).
- `EmailChannel(smtp_config, style=None)` → delegates to the existing
  `_build_task_email_handler(smtp_config, style, task_name)` (current email
  behaviour: `ERROR` level, localized subject).

### `Task` wiring (backward compatible)

`Task.__init__` keeps its current signature and behaviour, plus one additive
optional parameter:

```python
def __init__(self, ..., channels: list[NotificationChannel] | None = None):
    ...
    self._channels: list[NotificationChannel] = [FileChannel(self.log_path)]
    if smtp_config is not None:
        self._channels.append(EmailChannel(smtp_config, email_style or HTMLEmailStyle()))
    if channels is not None:
        self._channels.extend(channels)
    for channel in self._channels:
        logger.addHandler(channel.build_handler(self.name))
```

- `log_path` / `smtp_config` / `email_style` keep working exactly as before —
  they are translated into the file and email channels internally.
- `_frame_filter` (traced-vars frame filter) stays sourced from `email_style`;
  it governs how failure context is *built*, independent of delivery.
- New `channels` param is additive and defaults to `None` → zero behaviour
  change for existing callers.

### Public API exports

Export `NotificationChannel`, `FileChannel`, `EmailChannel` from
`processes/__init__.py`.

## Files

- `src/processes/notification_channels.py` — new module (ABC + two channels).
- `src/processes/task.py` — build handlers via channels; add `channels` param.
- `src/processes/__init__.py` — export the new public names.
- `tests/test_notification_channels.py` — new test module.

## Testing

- `NotificationChannel` cannot be instantiated directly (is abstract).
- `FileChannel.build_handler` returns a `FileHandler` at the right level with
  `_TaskLogfileFormatter`, writing to the given path.
- `EmailChannel.build_handler` returns an `ERROR`-level handler with the
  localized subject (mock SMTP, mirroring `test_email_themes.py`).
- Integration: a `Task` with a custom extra channel attaches its handler;
  existing file + email behaviour unchanged.
- Full existing suite must stay green (backward-compat guarantee).

## Commit sequence (conventional commits, no Claude attribution)

Commit only after the relevant tests + ruff + mypy pass.

1. `docs: add notification channel abstraction plan` — this file.
2. `feat: add NotificationChannel abstraction with file and email channels`
   — new module + unit tests + exports.
3. `refactor: build task handlers through notification channels`
   — wire `Task` to channels, add `channels` param, integration tests,
   docstring updates.

No final merge; push the branch so it appears on GitHub for the maintainer's PR.
