from datetime import date

from processes import Process, Task, TaskDependency, HTMLSMTPHandler

# 1. Setup Email Alerts (Optional)
smtp_handler = HTMLSMTPHandler(
    ('smtp_server', 587), 'sender@example.com', ['admin@example.com', 'user@example.com'], 
    use_tls=True, credentials=('user', 'pass')
)

# 2. If necessary, create wrappers for your Tasks.
def get_previous_working_day():
    return date(2025, 12, 30)
def indep_task():
    return "foo"
def search_and_sum_csv(t: date):
    return 10
def sum_data_from_csv_and_x(x, a=1, b=2):
    return x + a + b

# 3. Create the Task Graph (order is irrelevant, that is handled by Process)
tasks = [
    Task("t-1", "etl.log", get_previous_working_day),
    Task("intependent", "indep.log", indep_task, html_mail_handler=smtp_handler),  # This task will send email on failure
    Task("sum_csv", "etl.log", search_and_sum_csv,
            dependencies= [
                TaskDependency("t-1",
                use_result_as_additional_args=True)  # Adds result of t-1 task to search_and_sum_csv function as aditional args
            ]
        ),
    Task("sum_x_and_csv", "etl.log", sum_data_from_csv_and_x,
            args = (10,), kwargs = {"b": 100},
            dependencies=[
                TaskDependency("sum_csv",
            use_result_as_additional_kwargs=True,
            additional_kwarg_name="a")
        ]
    )
]

# 4. Run the Process
with Process(tasks) as process: # Context Manager ensures correct disposal of loggers
    process_result = process.run() # To enable parallelization use .run(parallel=True)