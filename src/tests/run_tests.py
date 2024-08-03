from processes import Process, Task, TaskResult

import json
import os
from typing import Any

from easy_smtp import SMTPHandler, SMTPCredentials


curdir = os.path.dirname(__file__)
filename = input("Enter SMTP Config filename without extension (file must be in same directory as this file) (press Enter to continue without SMTP):")
if filename == "":
    handler = None
else:
    with open(os.path.join(curdir, f"{filename}.json"), "r") as f:
        config_dict: dict[str, Any] = json.load(f)
        credentials_dict = config_dict.get("credentials", None)
        recipients = config_dict["recipients"]
        sender = config_dict["sender"]
        smtp_port = config_dict["smtp_port"]
        smtp_server = config_dict["smtp_server"]
        use_tls = config_dict["use_tls"]

    if credentials_dict is not None:
        credentials = SMTPCredentials(credentials_dict["username"], credentials_dict["password"])
    else:
        credentials = None
    handler = SMTPHandler(sender, recipients, smtp_server, smtp_port, use_tls=use_tls, credentials=credentials)


def task_1() -> int:
    return 1

def task_2() -> int:
    return 2

def task_3(t2_res: int) -> int:
    return 3 + t2_res

def task_4(t3_res: int) -> int:
    return (4 + t3_res) / 0

def task_5(t4_res: int) -> int:
    return 5 + t4_res


# Create list of tasks with duplicate names, no dependencies
tasks = [
    Task("task_1", "logfile_12.log", task_1),
    Task("task_2", "logfile_12.log", task_2),
    Task("task_2", "logfile_3.log", task_3),
]
process = Process(tasks)

