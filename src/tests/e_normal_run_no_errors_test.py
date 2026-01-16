from processes import Process, Task, TaskDependency
import time

import os

from .log_cleaner import clean_tasks_logs

def task_1() -> int:
    time.sleep(4)
    return 1

def task_2() -> int:
    time.sleep(2)
    return 2

def task_3(input: int) -> int:
    time.sleep(1)
    return input

def task_4(t2_res: int) -> int:
    time.sleep(5)
    return 3 + t2_res

def task_5(t1_res: int) -> int:
    time.sleep(3)
    return 4 + t1_res

def task_6(t2_res: int, t5_res: int) -> int:
    time.sleep(1)
    return t2_res + t5_res


curdir = os.path.dirname(__file__)
log_file_path = os.path.join(curdir, "logfile_1.log")
def test_run_single_task_sequential():
    clean_tasks_logs()
    t1 = Task("task_1", log_file_path, task_1)
    process = Process([t1])
    process.run(parallel=False)

    assert True

def test_run_single_task_parallel():
    clean_tasks_logs()
    t1 = Task("task_1", log_file_path, task_1)
    process = Process([t1])
    process.run(parallel=True)

    assert True

def test_run_independent_tasks_sequential():
    clean_tasks_logs()
    t1 = Task("task_1", log_file_path, task_1)
    t2 = Task("task_2", log_file_path, task_2)

    process = Process([t1, t2])
    process.run(parallel=False)

    assert True

def test_run_independent_tasks_parallel():
    clean_tasks_logs()
    t1 = Task("task_1", log_file_path, task_1)
    t2 = Task("task_2", log_file_path, task_2)

    process = Process([t1, t2])
    process.run(parallel=True)

    assert True

def test_run_dependent_tasks_sequential():
    clean_tasks_logs()
    t1 = Task("task_1", log_file_path, task_1)
    t2 = Task("task_2", log_file_path, task_2)
    t3 = Task("task_3", log_file_path, task_3, args=(1,))
    t4 = Task("task_4", log_file_path, task_4, dependencies=[TaskDependency("task_2", use_result_as_additional_args=True)])
    t5 = Task("task_5", log_file_path, task_5, dependencies=[TaskDependency("task_1", use_result_as_additional_args=True)])
    t6 = Task("task_6", log_file_path, task_6, dependencies=[
            TaskDependency("task_2", use_result_as_additional_args=True),
            TaskDependency("task_5", use_result_as_additional_args=True)
        ])

    process = Process([t1, t2, t3, t4, t5, t6])
    t0 = time.time()
    process_result = process.run(parallel=False)
    t1 = time.time()
    
    assert len(process_result.passed_tasks_results) == 6, f"Expected 6 passed tasks. Got {len(process_result.passed_tasks_results)}"
    assert len(process_result.failed_tasks) == 0, f"Expected 0 failed tasks. Got {len(process_result.failed_tasks)}"
    assert int(round(t1 - t0, 0)) == 16, f"Sequential run took {t1 - t0} seconds. Expected 16 seconds."

def test_run_dependent_tasks_parallel():
    clean_tasks_logs()
    t1 = Task("task_1", log_file_path, task_1)
    t2 = Task("task_2", log_file_path, task_2)
    t3 = Task("task_3", log_file_path, task_3, args=(1,))
    t4 = Task("task_4", log_file_path, task_4, dependencies=[TaskDependency("task_2", use_result_as_additional_args=True)])
    t5 = Task("task_5", log_file_path, task_5, dependencies=[
            TaskDependency("task_1", use_result_as_additional_args=True)
        ])
    t6 = Task("task_6", log_file_path, task_6, dependencies=[
            TaskDependency("task_2", use_result_as_additional_args=True),
            TaskDependency("task_5", use_result_as_additional_args=True)
        ])

    process = Process([t1, t2, t3, t4, t5, t6])
    t0 = time.time()
    n_workers = os.cpu_count()
    process_result = process.run(parallel=True, max_workers=n_workers)
    t1 = time.time()
    
    assert len(process_result.passed_tasks_results) == 6, f"Expected 6 passed tasks. Got {len(process_result.passed_tasks_results)}"
    assert len(process_result.failed_tasks) == 0, f"Expected 0 failed tasks. Got {len(process_result.failed_tasks)}"
    if n_workers > 2:
        assert int(round(t1 - t0, 0)) == 8, f"Parallel run took {t1 - t0} seconds. Expected 8 seconds."

    clean_tasks_logs()