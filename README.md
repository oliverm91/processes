# Library for process automation

In processes, a `Process` can execute a series of `Task`s sequentially. The `process` takes into account dependencies of `Task`s.

All `Task`s write logs to a logfile. Logfiles can be shared across Tasks. Optionally, it can inform of raised exceptions via email with SMTP.

If a `Task` raises an exception, the `Process` does not stop and it will execute all other `Task`s that do not have a dependency on failed `Task`.

Order of `Task`s is not relevant. `Process` will sort according to `Task`s dependencies.

##### Example (`SMTPHandler`, and `SMTPCredentials` classes come from [easy_smtp](https://github.com/oliverm91/easy_smtp/) library):

``` python

def random_routine_to_do_first():
    pass

def get_b():
    return 10

def get_c():
    return 5

def div(a: int, b: int, c: int=5) -> int:
    return (a + b) / c

# Optional, defined in easy_smtp lib
smtp_handler = SMTPHandler('sender@example.com', ['receiver@example.com'],'smtp_server', 587, use_tls=True, credentials=SMTPCredentials('username', 'password'))

curdir = os.path.dirname(__file__)
tasks = []
# Task(name (unique in a process), logfile, function, Optional args, Optional kwargs, Optional mail_handler)
t1 = Task("task_1", os.path.join(curdir, "logfile_12.log"),
            get_b, mail_handler=smtp_handler)
tasks.append(t1)
t2 = Task("task_2", os.path.join(curdir, "logfile_12.log"),
            get_c, dependencies=[TaskDependency("task_1")]) # Need task_1 to complete first
tasks.append(t2)
t3 = Task("task_3", os.path.join(curdir, "logfile_3.log"),
            div, args=(10, ), dependencies=[TaskDependency("task_1", use_result_as_additional_args=True),
                                            TaskDependency("task_2", use_result_as_additional_kwargs=True, additional_kwarg_name="c")])
# Task 3 needs task_1 and task_2 to execute first.
# Additionally, task_3 will add result of task_1 as an extra args for its function (10, ) -> (10, result_task1)
# Also, task_3 will add result of task_2 as a kwarg it keyword "c".
# Finally, task_3 calls div(10, result_1, c=result_2) or div(10, 10, c=5).
tasks.append(t3)

# Order of tasks is not relevant. Process sort according to dependencies.
process = Process(tasks)
process_result = process.run()
```