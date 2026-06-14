## v4.0.0 (2026-06-14)

### BREAKING CHANGE

- Task no longer accepts smtp_config or email_style.
Pass channels=[EmailChannel(smtp_config, style)] instead.

### Feat

- add NotificationChannel abstraction with file and email channels

### Refactor

- configure email alerts via channels instead of Task smtp_config
- keep file and email channel implementations internal
- build task handlers through notification channels

## v3.1.1 (2026-06-13)

### Refactor

- rename _log_formatting to _logfile_formatting and _TaskLogFormatter to _TaskLogfileFormatter

## v3.1.0 (2026-06-13)

### Feat

- **logging**: include failure context in task logfiles

### Refactor

- extract typed _ErrorData from task_context via shared base formatter
- inline single-use _task_context_lines helper
- move task logfile formatting out of _email_internals

## v3.0.1 (2026-06-13)

### Refactor

- **process**: use bare raise and extract _is_done helper

## v3.0.0 (2026-06-13)

### BREAKING CHANGE

- html_mail_handler parameter removed from Task; use
smtp_config and email_style instead. HTMLSMTPHandler removed from public API.

### Feat

- **html_logging**: expose last_path_traced_vars on HTMLSMTPHandler

### Refactor

- **email**: replace HTMLSMTPHandler with SMTPConfig/HTMLEmailStyle

## v2.0.1 (2026-06-12)

### Fix

- **publish.yml**: remove unneeded step ruff format check in quality-gate

## v2.0.0 (2026-06-12)

### BREAKING CHANGE

- log records no longer carry
``post_traceback_html_body``. Consumers introspecting that attribute
must read ``record.task_context`` instead.

### Feat

- **email_alerting**: Traced Variables section with file:line reference in email body
- **email_alerting**: language alternatives for HTML email body
- **email_alerting**: template-driven HTML body from pure metadata

### Fix

- **process**: parallel runner no longer raises on unrunnable tail

## v1.0.5 (2026-01-19)

### Fix

- **docs**: added urls to pyproject file

## v1.0.4 (2026-01-19)

### Fix

- **docs**: added pypi badge and pip install instruction to readme

## v1.0.3 (2026-01-19)

### Fix

- **docs**: changes in readme and index of docs to show banner

## v1.0.2 (2026-01-19)

### Fix

- **ci**: added a workflow for publishing to pypi

## v1.0.1 (2026-01-19)

### Fix

- **lint**: fix ruff formatting

## v1.0.0 (2026-01-19)

### BREAKING CHANGE

- Task.run method had one of its kwargs removed

### Fix

- **Task-can-no-longer-pass-logger-to-its-function.-Changed-some-examples,-documentations-and-better-type-hints**: Task.run method no longer can pass logger to its function as kwarg

## v0.1.0 (2026-01-18)
