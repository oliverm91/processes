"""Manual end-to-end inspection of ``WebhookChannel`` alerts.

This is the webhook counterpart to ``manual_pipeline_inspect.py`` (which
exercises ``EmailChannel`` against maildev). It is **not** picked up by
pytest — see ``tests/conftest.py`` and the ``python_files = "test_*.py"``
setting in ``pytest.ini``. Run it by hand:

    python tests/manual_tests/manual_webhook_inspect.py

What this exercises
--------------------
A small DAG with one failing task and one cascading-skipped downstream task.
Both ``A_load_config`` (success) and ``B_apply_config`` (failure) are wired
with a ``WebhookChannel`` pointing at a throwaway local HTTP server started
by this script. ``C_notify_done`` depends on ``B_apply_config`` and is
cascade-skipped.

The local server prints every received request: method, headers (including
the ``X-Signature-SHA256`` header), and the JSON body. It also independently
recomputes the HMAC signature from ``WEBHOOK_SECRET`` and reports whether it
matches, so a single run verifies both the payload shape and the optional
HMAC body-signing end to end.

Inspect
-------
*   The console output for the recomputed-vs-received signature check.
*   The printed JSON payload for ``B_apply_config`` — confirm it carries
    ``task_name``, ``function``, ``args``, ``kwargs``, ``exception``,
    ``traceback``, ``downstream_impact`` (containing ``C_notify_done``),
    ``traced_vars`` and ``traced_vars_location``.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any

# Make the in-tree package importable when the script is run directly.
_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from processes import Process, Task, TaskDependency, WebhookChannel, WebhookConfig  # noqa: E402

WEBHOOK_SECRET = "manual-test-shared-secret"


class _WebhookRequestHandler(BaseHTTPRequestHandler):
    def do_POST(self) -> None:  # noqa: N802 (stdlib-mandated name)
        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length)
        signature = self.headers.get("X-Signature-SHA256")

        print(f"  [server] {self.command} {self.path}")
        print(f"  [server] Content-Type: {self.headers.get('Content-Type')}")
        print(f"  [server] X-Signature-SHA256: {signature}")

        expected = hmac.new(WEBHOOK_SECRET.encode("utf-8"), body, hashlib.sha256).hexdigest()
        match = "OK" if signature == expected else "MISMATCH"
        print(f"  [server] signature check: {match} (expected={expected})")

        payload = json.loads(body)
        print("  [server] payload:")
        print(json.dumps(payload, indent=2))

        self.send_response(200)
        self.end_headers()

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
        pass  # silence default request logging; we print our own summary above


def _start_server() -> tuple[HTTPServer, int]:
    server = HTTPServer(("127.0.0.1", 0), _WebhookRequestHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, server.server_address[1]


# --------------------------------------------------------------------------- #
# Task functions                                                              #
# --------------------------------------------------------------------------- #


def load_config(env: str) -> dict[str, Any]:
    """Load configuration for the given environment.  Always succeeds."""
    print(f"  [load_config] env={env!r}")
    return {"env": env, "feature_flags": {"new_pricing": True}}


def apply_config(
    target: str,
    config: dict[str, Any] | None = None,
    restart: bool = True,
) -> str:
    """Apply the loaded configuration.  **Fails** — target service rejects it."""
    print(f"  [apply_config] target={target!r} restart={restart} config={config!r}")
    raise RuntimeError(f"target service {target!r} rejected configuration")


def notify_done(*_args: Any, **_kwargs: Any) -> str:
    """Notify that the rollout finished.  Cascading-skip target."""
    print("  [notify_done] this should never run — FAILED upstream")
    return "done-notified"


# --------------------------------------------------------------------------- #
# Entry point                                                                 #
# --------------------------------------------------------------------------- #


def main() -> int:
    here = os.path.dirname(os.path.abspath(__file__))
    logs_dir = os.path.join(here, "logs")
    os.makedirs(logs_dir, exist_ok=True)

    server, port = _start_server()
    print(f"webhook server: http://127.0.0.1:{port}/hook")

    webhook = WebhookChannel(
        WebhookConfig(url=f"http://127.0.0.1:{port}/hook", secret=WEBHOOK_SECRET)
    )

    dep = TaskDependency
    tasks = [
        Task(
            name="A_load_config",
            log_path=os.path.join(logs_dir, "A_load_config.log"),
            func=load_config,
            args=("staging",),
            channels=[webhook],
        ),
        Task(
            name="B_apply_config",
            log_path=os.path.join(logs_dir, "B_apply_config.log"),
            func=apply_config,
            args=("pricing-service",),
            kwargs={"restart": True},
            dependencies=[
                dep(
                    "A_load_config",
                    use_result_as_additional_kwargs=True,
                    additional_kwarg_name="config",
                )
            ],
            channels=[webhook],
        ),
        Task(
            name="C_notify_done",
            log_path=os.path.join(logs_dir, "C_notify_done.log"),
            func=notify_done,
            dependencies=[dep("B_apply_config")],
            channels=[webhook],
        ),
    ]

    print(f"tasks: {len(tasks)}")
    print("-" * 72)

    try:
        with Process(tasks) as process:
            result = process.run(parallel=False)
    finally:
        server.shutdown()

    print("-" * 72)
    print("passed:")
    for name in sorted(result.passed_tasks_results):
        print(f"  + {name}")
    print("failed (includes cascading-skipped):")
    for name in sorted(result.failed_tasks):
        print(f"  - {name}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
