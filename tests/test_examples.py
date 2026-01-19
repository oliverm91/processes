import sys

sys.path.insert(0, "examples/01_basic_tasks_and_dependencies")
sys.path.insert(0, "examples/02_task_dependencies_result_passing")

from example1 import main as example_1
from example2 import main as example_2


def test_example_1():
    example_1()
    assert True


def test_example_2():
    example_2()
    assert True
