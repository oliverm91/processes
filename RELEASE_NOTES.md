# v3.0.1 — Email API Overhaul, Task Retries & Timeouts

## ⚠️ Breaking Changes

- **Removed `HTMLSMTPHandler` and `html_mail_handler`**. Email alerting is now configured with two plain dataclasses passed to `Task`:
  - `SMTPConfig` — SMTP transport settings (host, credentials, sender/recipients, TLS).
  - `HTMLEmailStyle` — presentation settings (style, color palette, language, traced-vars frame filter).

  ```python
  Task(..., smtp_config=SMTPConfig(...), email_style=HTMLEmailStyle(style="modern", palette="catppuccin"))
  ```

## ✨ New Features

- **Per-task timeouts**: `Task(..., timeout=30)` raises `TimeoutError` if an attempt exceeds the limit.
- **Automatic retries**: `Task(..., retries=3, retry_on=(ConnectionError, TimeoutError))` retries failed attempts on the specified exception types (defaults to `ConnectionError`/`TimeoutError`).
- **Structured exceptions**: `DependencyNotFoundError`, `TaskNotFoundError`, and `CircularDependencyError` now carry structured attributes (`task_name`, `missing_dep`) instead of plain messages.
- **Traced variables in error emails**: failure emails include a "Traced Variables" section showing local variables at the relevant stack frame, with a configurable `traced_vars_frame_filter` to target a specific module.

## 🔧 Refactoring

- Centralized failure-context extraction: `Task._resolve_args` and `Task._build_failure_context` cleanly separate dependency-result injection from failure reporting.
- Split traceback/frame-walking utilities (`_tb_utils.py`) from email-rendering internals (`_email_internals.py`) — each module now has a single responsibility.
- Each `Task` now gets a unique per-instance logger, preventing handler leakage between tasks with the same name.
- Minor cleanups in `Process`: bare `raise` for re-raised exceptions, extracted `_is_done()` helper for the parallel runner loop.

## 🐛 Bug Fixes

- Fixed a logging bug where `logger.exception(...)` was called outside an `except` block, resulting in empty exception details (`None`) in failure emails. Errors now log with full `exc_info` and a structured `task_context` payload.
- Fixed `Task.run()` not reporting the actual exception when retries were exhausted.

## 🧪 Testing & CI

- Migrated the test suite to a shared `BaseTest` base class with consistent per-test log directories and cleanup.
- Added dedicated tests for timeout and retry behavior.
- Bumped GitHub Actions (`actions/checkout` → v6, `astral-sh/setup-uv` → v6) to silence deprecation warnings.