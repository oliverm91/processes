import logging
import json
import logging.handlers
import os

from processes import Process, Task, HTMLSMTPHandler



def send_mail_test():
    def div_zero_mail(a: int, b: int=0) -> int:
        return 1 / 0
    
    curdir = os.path.dirname(__file__)
    tasks = []
    log_file_path = os.path.join(curdir, "logfile_1.log")

    smtp_config_file = ""
    while smtp_config_file == "":
        smtp_config_file = input("Enter path to smtp config json file path (relative to current directory) (Press ENTER to skip test): ")
        if len(smtp_config_file) == 0:
            print("Skipping send mail test.")
            return
        if len(smtp_config_file) < 5:
            smtp_config_file += ".json"
        else:
            if not smtp_config_file.endswith(".json"):
                smtp_config_file += ".json"
        smtp_config_file = os.path.join(curdir, smtp_config_file)
        if not os.path.exists(smtp_config_file):
            print(f"File {smtp_config_file} not found. Please try again.")
            smtp_config_file = ""        

    with open(smtp_config_file, "r") as f:
        smtp_config = f.read()
        smtp_config_dict = json.loads(smtp_config)

    smtp_server = smtp_config_dict["smtp_server"]
    smtp_port = smtp_config_dict["smtp_port"]
    use_tls = smtp_config_dict["use_tls"]
    credentials = smtp_config_dict["credentials"]
    smtp_username = credentials["username"]
    smtp_password = credentials["password"]
    sender = smtp_config_dict["sender"]
    recipients = smtp_config_dict["recipients"]

    if use_tls:
        smtp_handler = HTMLSMTPHandler((smtp_server, smtp_port), sender, recipients, credentials=(smtp_username, smtp_password), secure=())
    else:
        smtp_handler = HTMLSMTPHandler((smtp_server, smtp_port), sender, recipients, credentials=(smtp_username, smtp_password))

    t1 = Task("task_1", log_file_path, div_zero_mail, func_args=(10,), html_mail_handler=smtp_handler)
    tasks.append(t1)

    process = Process(tasks)
    process.run()


    for handler in t1.logger.handlers[:]:
        handler.close()
        t1.logger.removeHandler(handler)
    os.remove(log_file_path)

    print(f"Please, check that an email was sent to {recipients}.")