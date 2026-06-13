import os
import shutil
import sys

sys.path.insert(0, "examples/01_basic_tasks_and_dependencies")
sys.path.insert(0, "examples/02_task_dependencies_result_passing")

from example1 import main as example_1
from example2 import main as example_2

# The examples hardcode ``log_dir = "logs"`` relative to CWD and
# example2 also writes ``data_output.json``.  Clean them up after each
# test so they don't litter the repo root.
_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
_EXAMPLE_LOGS = os.path.join(_REPO_ROOT, "logs")
_EXAMPLE_OUTPUT = os.path.join(_REPO_ROOT, "data_output.json")


def _clean_example_artifacts() -> None:
    if os.path.isdir(_EXAMPLE_LOGS):
        shutil.rmtree(_EXAMPLE_LOGS, ignore_errors=True)
    if os.path.isfile(_EXAMPLE_OUTPUT):
        os.remove(_EXAMPLE_OUTPUT)


def test_example_1():
    _clean_example_artifacts()
    try:
        example_1()
        assert True
    finally:
        _clean_example_artifacts()


def test_example_2():
    _clean_example_artifacts()
    try:
        example_2()
        assert True
    finally:
        _clean_example_artifacts()
