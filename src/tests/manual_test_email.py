import tomllib
import os

from processes import Process, Task, TaskDependency, HTMLSMTPHandler

from log_cleaner import clean_tasks_logs

# To run this test. Install the library then run `python manual_test_email.py` or `uv run python ...` (adjust path accordingly)
# To install the library use `pip install -e .` or `uv pip insstall -e .` standing on root directory (/processes/)

def send_mail_test():
    def div_zero_mail(a: int, b: int=0) -> int:
        return 1 / 0
    
    def indep_task() -> int:
        return 1
    
    def dep_task_level_1() -> int:
        return 1
    
    def dep_task_level_2() -> int:
        return 1
    
    
    curdir = os.path.dirname(__file__)
    tasks = []
    log_file_path = os.path.join(curdir, "logfile_1.log")

    smtp_config_file = ""
    while smtp_config_file == "":
        smtp_config_file = input("Enter path to smtp config toml file path (relative to current directory) (Press ENTER to skip test): ")
        if len(smtp_config_file) == 0:
            print("Skipping send mail test.")
            return
        if len(smtp_config_file) < 5:
            smtp_config_file += ".toml"
        else:
            if not smtp_config_file.endswith(".toml"):
                smtp_config_file += ".toml"
        smtp_config_file = os.path.join(curdir, smtp_config_file)
        if not os.path.exists(smtp_config_file):
            print(f"File {smtp_config_file} not found. Please try again.")
            smtp_config_file = ""        

    with open(smtp_config_file, "rb") as f:
        smtp_config_dict = tomllib.load(f)

    smtp_server: str = smtp_config_dict["smtp_server"]
    smtp_port: int = smtp_config_dict["smtp_port"]
    use_tls: bool = smtp_config_dict["use_tls"]
    credentials: dict[str, str] = smtp_config_dict["credentials"]
    smtp_username: str = credentials["username"]
    smtp_password: str = credentials["password"]
    sender: str = smtp_config_dict["sender"]
    recipients: list[str] = smtp_config_dict["recipients"]
    
    secure = () if use_tls else None
    smtp_handler = HTMLSMTPHandler((smtp_server, smtp_port), sender, recipients, credentials=(smtp_username, smtp_password), secure=secure)
    t1 = Task("task_1", log_file_path, div_zero_mail, args=(10,), html_mail_handler=smtp_handler)    
    tasks.append(t1)

    t2 = Task("indep_task", log_file_path, indep_task)
    tasks.append(t2)

    t3 = Task("dep_task_level_1", log_file_path, dep_task_level_1, dependencies=[TaskDependency("task_1")])
    tasks.append(t3)

    t4 = Task("dep_task_level_2", log_file_path, dep_task_level_2, dependencies=[TaskDependency("dep_task_level_1")])
    tasks.append(t4)


    process = Process(tasks)
    process.run()

    for handler in t1.logger.handlers[:]:
        handler.close()
        t1.logger.removeHandler(handler)
    os.remove(log_file_path)

    print(f"Please, check that an email was sent to {recipients}.")

    clean_tasks_logs()


if __name__ == "__main__":
    send_mail_test()