# Error context refactor — thoughts

## Current state

When a task fails, `Task.run()` builds a plain dict and passes it as a logging `extra`:

```python
task_context = {
    "task_name": self.name,
    "function": self.func.__name__,
    "args": self.args,
    "kwargs": self.kwargs,
    "downstream_impact": downstream_names,
}
self.logger.error(str(last_exc), exc_info=last_exc, extra={"task_context": task_context})
```

The `FileHandler` receives this record and ignores `task_context` entirely — it only formats
the message string and the standard traceback.

The `_HTMLEmailFormatter` picks up `task_context` from the record, *and also* walks
`record.exc_info` independently to extract the traceback, traced local variables, and
frame location. This means the formatter does dual work: it reads structured metadata from
one place and raw CPython internals from another.

**Result: two handlers, two information levels, logic split across two layers.**

---

## The core tension

There are two separable concerns:

1. **What happened** — task name, function, args, kwargs, downstream impact, exception,
   retry count, attempt number. This is *task-level* knowledge, available in `Task.run()`.

2. **How to present it** — plain text, structured JSON, HTML with palette and language,
   traced variables. This is *handler-level* knowledge; each handler renders differently.

Currently, concern 1 is partially in `Task.run()` (the `task_context` dict) and partially
re-derived in `_HTMLEmailFormatter` (traceback parsing, frame walking). Concern 2 is entirely
in the formatter, which is correct. The problem is only in concern 1 being incomplete at the
source.

---

## Proposed: `TaskFailureContext` dataclass

Replace the raw dict with a typed dataclass defined in `exceptions.py` or a new `_context.py`:

```python
@dataclass
class TaskFailureContext:
    task_name: str
    function_name: str
    args: tuple
    kwargs: dict
    downstream_impact: list[str]
    exception: BaseException
    attempts: int              # total attempts made (1 + retries fired)
```

`Task.run()` constructs one instance and passes it:

```python
ctx = TaskFailureContext(
    task_name=self.name,
    function_name=self.func.__name__,
    args=self.args,
    kwargs=self.kwargs,
    downstream_impact=downstream_names,
    exception=last_exc,
    attempts=attempt,
)
self.logger.error(str(last_exc), exc_info=last_exc, extra={"task_context": ctx})
```

Benefits:
- Type-safe: handlers get a real object, not a `dict[str, Any]`
- `attempts` is new but already available in `Task.run()` — currently lost
- The contract between `Task` and its handlers is explicit and checkable by mypy

---

## Traced variables — the asymmetry problem

Currently traced local variables are extracted only inside `_HTMLEmailFormatter`, so they
appear in emails but never in file logs. This is the core asymmetry.

### The fix: extract at the source, render in the formatter

`_HTMLEmailFormatter.format()` already reads everything from `record.task_context`.
The solution is simply to **do the extraction in `Task.run()` and include the results in
`task_context`** — the formatter then becomes a pure template renderer with no extraction
logic at all.

`TaskFailureContext` carries:

```python
@dataclass
class TaskFailureContext:
    # already present
    task_name: str
    function_name: str
    args: tuple
    kwargs: dict
    downstream_impact: list[str]
    attempts: int
    # moved from _HTMLEmailFormatter
    exception: BaseException
    traceback_str: str
    traced_vars: str           # pre-rendered "key = repr(value)" lines, HTML-escaped
    traced_vars_location: str  # "filename:lineno" of the selected frame
```

`Task.run()` calls extraction helpers (moved to module-level functions in
`_email_internals.py`, which `task.py` already imports from):

```python
ctx = TaskFailureContext(
    ...,
    traceback_str=_format_traceback(last_exc),
    traced_vars=_extract_traced_vars(last_exc.__traceback__, self._frame_filter),
    traced_vars_location=_extract_location(last_exc.__traceback__, self._frame_filter),
)
self.logger.error(str(last_exc), exc_info=last_exc, extra={"task_context": ctx})
```

`_HTMLEmailFormatter.format()` reads `record.task_context.*` and fills the template —
no `exc_info` parsing, no frame walking, no extraction of any kind.

### Frame filter

`traced_vars_frame_filter` from `HTMLEmailStyle` is per-task. Store it as a private attr
on `Task` during `__init__` (`self._frame_filter: str | None`) so `Task.run()` can pass it
to the extraction helpers. Only one field needed, not the full style object.

### Result

- Extraction happens once, at failure time, in `Task.run()`
- Every handler (file, email, future Slack/PagerDuty) gets the same complete context
- `_HTMLEmailFormatter` is a pure renderer: template + palette + language strings only
- No duplication, no re-extraction, no `exc_info` parsing in the formatter

---

## What the file handler could do

With a typed context object on the record, a custom `FileHandler` subclass (or a smarter
`Formatter`) could optionally emit structured metadata alongside the traceback:

```
2026-06-13 10:00:00 - ERROR - fetch failed
  task: fetch | fn: fetch_orders | downstream: [enrich, report] | attempts: 2
  Traceback ...
```

Currently none of this appears in file logs. Whether to add it is a separate decision, but
the structured object makes it possible without changing `Task.run()`.

---

## What this does NOT change

- Public API — `Task`, `Process`, `ProcessResult` signatures are untouched
- Email output — HTML looks identical; formatter just reads `.attr` instead of `["key"]`
- File log output — unchanged unless someone adds a richer formatter
- `extra={"task_context": ...}` key — kept for backwards compat with any external handler
  that inspects log records

---

## Effort estimate

Small. The dataclass is ~10 lines. `Task.run()` changes one dict literal to a constructor
call. `_HTMLEmailFormatter` changes `record.task_context["x"]` → `record.task_context.x`
throughout. Tests that assert `record.task_context` keys would assert attributes instead.
