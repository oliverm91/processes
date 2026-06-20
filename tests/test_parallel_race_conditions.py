"""
Parallel-execution race-condition stress tests.

Two scenarios designed to maximise contention on ``ProcessRunner``'s
shared state (``results``, ``submitted_tasks``):

1. ``test_diamond_fan_in_race`` — wide fan-in diamond. Many sibling
   tasks gate on a ``threading.Barrier`` and release simultaneously,
   then a single dependent collects results from all of them via
   positional injection. Verifies no results are dropped, no task is
   double-submitted, and the dependent runs exactly once with the
   complete result set.

2. ``test_high_fanout_cascading_failures_race`` — many independent
   failing branches racing many independent passing branches. All
   roots release from a single barrier so failures and successes
   interleave on the runner's bookkeeping dicts. Verifies the failed
   / passed sets stay perfectly disjoint, cascading-skip propagates
   only along the failing branches, and every task's ``func`` invocation
   count is exact.

Each scenario runs multiple iterations because race conditions are
non-deterministic — a single passing iteration proves nothing.
"""

from __future__ import annotations

import os
import threading
from collections import defaultdict

from processes import Process, Task, TaskDependency

from .base_test import BaseTest


def _make_task(name: str, func, log_dir: str, deps=None) -> Task:
    return Task(
        name=name,
        log_path=os.path.join(log_dir, f"{name}.log"),
        func=func,
        dependencies=deps or [],
    )


def _run_diamond_iteration(sibling_count: int, run_idx: int, log_dir: str) -> None:
    """One diamond fan-in iteration, isolated so closures bind to params."""
    call_counts: dict[str, int] = defaultdict(int)
    counts_lock = threading.Lock()
    barrier = threading.Barrier(sibling_count)

    def root_func():
        with counts_lock:
            call_counts["root"] += 1
        return "root_payload"

    def make_sibling(idx: int):
        def _sibling(_root_payload):
            barrier.wait(timeout=10)
            with counts_lock:
                call_counts[f"S{idx}"] += 1
            return f"sibling_{idx}_payload"

        _sibling.__name__ = f"sibling_{idx}"
        return _sibling

    def collector(*sibling_results):
        with counts_lock:
            call_counts["collector"] += 1
        call_counts["__collector_arg_count"] = len(sibling_results)
        return sorted(sibling_results)

    dep = TaskDependency
    tasks = [_make_task("root", root_func, log_dir)]
    for i in range(sibling_count):
        tasks.append(
            _make_task(
                f"S{i}",
                make_sibling(i),
                log_dir,
                deps=[dep("root", use_result_as_additional_args=True)],
            )
        )
    collector_deps = [
        dep(f"S{i}", use_result_as_additional_args=True) for i in range(sibling_count)
    ]
    tasks.append(_make_task("collector", collector, log_dir, deps=collector_deps))

    with Process(tasks) as process:
        result = process.run(parallel=True, max_workers=sibling_count + 2)

    tag = f"[iter {run_idx}]"

    assert call_counts["root"] == 1, f"{tag} root called {call_counts['root']}x"
    assert call_counts["collector"] == 1, f"{tag} collector called {call_counts['collector']}x"
    for i in range(sibling_count):
        assert call_counts[f"S{i}"] == 1, f"{tag} sibling S{i} called {call_counts[f'S{i}']}x"

    assert call_counts["__collector_arg_count"] == sibling_count, (
        f"{tag} collector received {call_counts['__collector_arg_count']} "
        f"args, expected {sibling_count}"
    )
    failed = set(result.errored) | set(result.skipped)
    assert not failed, f"{tag} unexpected failures: {failed}"
    assert len(result.successes) == sibling_count + 2, f"{tag} passed count mismatch"

    stored = result.successes["collector"].result
    assert stored == sorted(f"sibling_{i}_payload" for i in range(sibling_count)), (
        f"{tag} collector result missing sibling payloads: {stored}"
    )


def _run_cascading_iteration(
    failing_branches: int,
    passing_branches: int,
    chain_depth: int,
    run_idx: int,
    log_dir: str,
) -> None:
    """One cascading-failure iteration, isolated so closures bind to params."""
    call_counts: dict[str, int] = defaultdict(int)
    counts_lock = threading.Lock()
    barrier = threading.Barrier(failing_branches + passing_branches)

    def make_root(name: str, fail: bool):
        def _root():
            barrier.wait(timeout=10)
            with counts_lock:
                call_counts[name] += 1
            if fail:
                raise RuntimeError(f"planned failure in {name}")
            return f"{name}_payload"

        _root.__name__ = f"root_{name}"
        return _root

    def make_child(name: str):
        def _child(*_args, **_kwargs):
            with counts_lock:
                call_counts[name] += 1
            return f"{name}_payload"

        _child.__name__ = f"child_{name}"
        return _child

    dep = TaskDependency
    tasks: list[Task] = []

    failing_chains: list[list[str]] = []
    for b in range(failing_branches):
        chain_names = [f"f{b}_{d}" for d in range(chain_depth + 1)]
        failing_chains.append(chain_names)
        tasks.append(_make_task(chain_names[0], make_root(chain_names[0], fail=True), log_dir))
        for d in range(1, chain_depth + 1):
            tasks.append(
                _make_task(
                    chain_names[d],
                    make_child(chain_names[d]),
                    log_dir,
                    deps=[dep(chain_names[d - 1])],
                )
            )

    passing_chains: list[list[str]] = []
    for b in range(passing_branches):
        chain_names = [f"p{b}_{d}" for d in range(chain_depth + 1)]
        passing_chains.append(chain_names)
        tasks.append(_make_task(chain_names[0], make_root(chain_names[0], fail=False), log_dir))
        for d in range(1, chain_depth + 1):
            tasks.append(
                _make_task(
                    chain_names[d],
                    make_child(chain_names[d]),
                    log_dir,
                    deps=[dep(chain_names[d - 1])],
                )
            )

    with Process(tasks) as process:
        result = process.run(
            parallel=True,
            max_workers=failing_branches + passing_branches + 4,
        )

    tag = f"[iter {run_idx}]"

    for chain in failing_chains:
        root_name = chain[0]
        assert call_counts[root_name] == 1, (
            f"{tag} failing root {root_name} called {call_counts[root_name]}x"
        )
        for descendant in chain[1:]:
            assert call_counts[descendant] == 0, (
                f"{tag} cascade-skipped {descendant} was invoked "
                f"{call_counts[descendant]}x — race leaked execution"
            )

    for chain in passing_chains:
        for name in chain:
            assert call_counts[name] == 1, f"{tag} passing task {name} called {call_counts[name]}x"

    expected_failed = {n for chain in failing_chains for n in chain}
    expected_passed = {n for chain in passing_chains for n in chain}

    failed = set(result.errored) | set(result.skipped)
    passed = set(result.successes)

    assert failed == expected_failed, (
        f"{tag} failed set mismatch: "
        f"missing={expected_failed - failed}, "
        f"extra={failed - expected_failed}"
    )
    assert passed == expected_passed, (
        f"{tag} passed set mismatch: "
        f"missing={expected_passed - passed}, "
        f"extra={passed - expected_passed}"
    )
    assert not (failed & passed), f"{tag} a task appears in both passed and failed sets"
    assert len(failed) + len(passed) == len(tasks), (
        f"{tag} task accounting drifted: "
        f"{len(failed)} failed + {len(passed)} passed != {len(tasks)} total"
    )


class TestParallelRaceConditions(BaseTest):
    def test_diamond_fan_in_race(self) -> None:
        """Wide diamond fan-in: N siblings → 1 dependent, all gated by barrier."""
        for run_idx in range(5):
            _run_diamond_iteration(sibling_count=16, run_idx=run_idx, log_dir=self._CURDIR)

    def test_high_fanout_cascading_failures_race(self) -> None:
        """Many failing + passing branches released simultaneously from a barrier."""
        for run_idx in range(5):
            _run_cascading_iteration(
                failing_branches=8,
                passing_branches=8,
                chain_depth=3,
                run_idx=run_idx,
                log_dir=self._CURDIR,
            )
