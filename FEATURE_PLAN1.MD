USER: Could ProcessResult be ditched and replaced by ProcessExecutionReport? Show impacts. Don't code yet.

Claude: Could ProcessResult be replaced by ProcessExecutionReport?

Structurally, yes — ProcessExecutionReport.entries is a superset of what ProcessResult carries (it adds function/args/kwargs/status/elapsed_seconds/attempts for every task, success/errored/skipped alike, in topological order). The raw data ProcessRunner already collects (passed_results, failed_results, skipped_tasks, process.tasks) is exactly what from_result consumes — so ProcessRunner.run() could build a ProcessExecutionReport directly instead of a ProcessResult, without from_result needing a ProcessResult input at all (avoids the current process.py ↔ execution_report.py TYPE_CHECKING coupling — execution_report.py becomes self-sufficient).

What breaks / changes

1. Lost: raw Exception object access
TaskResult.exception is a live Exception instance (tests do isinstance(result.exception, TimeoutError)). TaskReportEntry.error is ErrorData | None, whose .exception field is a str(exception). Any caller that needs to isinstance()-check or re-raise the original exception loses that — ErrorData would need an added field, or TaskReportEntry would need to carry the raw TaskResult too.

2. API shape changes for every consumer
- result.passed_tasks_results["x"].result → report.successes["x"].result (or report.entries["x"].result)
- result.failed_tasks (a set[str]) → no direct equivalent; becomes set(report.errored) | set(report.skipped)
- result.errored_tasks / result.skipped_tasks → set(report.errored) / set(report.skipped)
- result.failed_tasks_results["x"] (a TaskResult) → report.entries["x"].error (an ErrorData, narrower — see #1)
- .worked / boolean checks → .status == TaskStatus.SUCCESS etc.

3. Test impact — large
Every test file that touches these attributes needs rewriting:
test_args_kwargs.py, test_complex_dag_failures.py, test_normal_run_no_errors.py, test_parallel_race_conditions.py, test_timeout_retry.py, plus 3 manual-test scripts. This is the bulk of the effort — dozens of assertion sites.

4. Docs impact
README's ProcessResult section (added in this session) and any usage examples would need replacing with ProcessExecutionReport equivalents; docs/reference.md would drop the ProcessResult mkdocstrings entry.

5. Breaking change vs. additive discipline
This session deliberately kept everything additive (FEATURE_PLAN's stance). Removing ProcessResult and changing Process.run()'s return type is a hard breaking change — would warrant a major version bump and a migration note, not a patch/minor release.

6. Minor ergonomics loss
Simple "did everything pass?" checks (if not result.failed_tasks) become if not report.errored and not report.skipped unless a convenience property (e.g. report.ok) is added.

Net assessment

Feasible and arguably a cleaner unified model long-term, but it's a breaking API change with wide blast radius across tests/docs, and needs at least one new field on ErrorData/TaskReportEntry to avoid losing the raw exception object. If you want this, I'd suggest either (a) a v6 major bump doing a clean replacement, or (b) keep ProcessResult as a thin deprecated wrapper for one release while Process.run() returns ProcessExecutionReport and ProcessResult.from_report(...) is offered for back-compat.

✻ Cooked for 49s

❯ /advisor off
  ⎿  Advisor disabled

❯ is ProcessExecutionReport being created anywhere yet?

  Searched for 1 pattern

Every test file that touches these attributes needs rewriting:
test_args_kwargs.py, test_complex_dag_failures.py, test_normal_run_no_errors.py, test_parallel_race_conditions.py, test_timeout_retry.py, plus 3 manual-test scripts. This is the bulk of the effort — dozens of assertion sites.

4. Docs impact
README's ProcessResult section (added in this session) and any usage examples would need replacing with ProcessExecutionReport equivalents; docs/reference.md would drop the ProcessResult mkdocstrings entry.

5. Breaking change vs. additive discipline
This session deliberately kept everything additive (FEATURE_PLAN's stance). Removing ProcessResult and changing Process.run()'s return type is a hard breaking change — would warrant a major version bump and a migration note, not a patch/minor release.

6. Minor ergonomics loss
Simple "did everything pass?" checks (if not result.failed_tasks) become if not report.errored and not report.skipped unless a convenience property (e.g. report.ok) is added.

Net assessment

Feasible and arguably a cleaner unified model long-term, but it's a breaking API change with wide blast radius across tests/docs, and needs at least one new field on ErrorData/TaskReportEntry to avoid losing the raw exception object. If you want this, I'd suggest either (a) a v6 major bump doing a clean replacement, or (b) keep ProcessResult as a thin deprecated wrapper for one release while Process.run() returns ProcessExecutionReport and ProcessResult.from_report(...) is offered for back-compat.

USER: failed_results and passed_results and failed_tasks are separated. Shouldn't they be in a single dict with k:v task.name:task_result_obj ?

Claude: Yes — and it'd fix a latent inconsistency: currently failed_tasks (a set) = errored_tasks ∪ skipped_tasks, but failed_results (a dict) only has entries for errored tasks, not skipped ones. So failed_tasks and failed_results.keys() silently diverge — anyone iterating failed_tasks and indexing into failed_results will KeyError on skipped tasks.

Proposal

Maintain one internal dict in ProcessRunner: self.results: dict[str, TaskResult], one entry per task regardless of outcome (success, errored, or skipped — synthesizing a TaskResult for skipped tasks the same way the parallel defensive branch already does for unexpected exceptions).

Discriminator problem: TaskResult.worked: bool alone can't tell errored apart from skipped (both worked=False). Two options:
- Implicit: attempts == 0 ⇒ skipped. Works, but relies on an unstated convention — fragile if someone constructs a TaskResult manually.
- Explicit (cleaner): give TaskResult a status: TaskStatus field (reuse the enum from execution_report.py). Then results[name].status is authoritative everywhere.

Impact

- Internals: _is_done, _all_deps_met, _is_unrunnable currently check membership across passed_results/failed_tasks/skipped_tasks/failed_results — all rewritten to query self.results by status. Net simplification.
- ProcessResult public API: can stay byte-for-byte unchanged. passed_tasks_results, failed_tasks, skipped_tasks, errored_tasks, failed_tasks_results all become derived views filtered from self.results at the end of run() — zero breaking change, fixes the divergence bug above as a side effect.
- Ties into the ProcessExecutionReport question: if TaskResult gains status: TaskStatus, then self.results is already shaped almost exactly like ProcessExecutionReport.entries (just missing name/function/args/kwargs, which come from Task). from_result/ProcessRunner.run() could build the report directly from this dict with minimal mapping — makes that future migration much cheaper.
- Effort: moderate, contained to process.py (ProcessRunner) + adding a field to TaskResult (additive, default-valued — safe). No test changes needed if ProcessResult's shape is preserved.

This seems like a good incremental step worth doing on its own regardless of the ProcessExecutionReport replacement decision.

USER: Tasks could have an extra attr TaskStatus already defined. Status could be expanded to PENDING, SUCCESS, ERRORED, SKIPPED. These changes should simplify or solve some of the problems stated by you. 



INSTRUCTION: IMPLEMENT BOTH THINGS. Removal of ProcessResult and use of single dict self.results.