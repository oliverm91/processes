import os
def clean_tasks_logs():
    curdir = os.path.dirname(__file__)
    for file in os.listdir(curdir):
        if file.endswith(".log"):
            os.remove(os.path.join(curdir, file))