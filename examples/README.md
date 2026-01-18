# Processes Examples & Usage Guide

Welcome to the **Processes** library examples! This directory shows you how to build workflows where multiple operations run together, with some depending on others.

## 📚 What is Processes?

**Processes** is a Python library that helps you run multiple tasks in sequence or in parallel, automatically handling when one task needs data from another. It handles errors gracefully and **sends email alerts when tasks fail** — no extra code needed.

### Three Main Ideas

- **Task**: A piece of work you want to do (run a function, fetch data, save results, etc.)
- **TaskDependency**: A task that depends on another task's result
- **Process**: The coordinator that runs all your tasks, handles data passing, and monitors for errors

---

## 🗂️ The 3 Examples

### 1. [Simple Independent Tasks](./01_simple_independent_tasks/)
**When to use:** Run multiple operations at the same time

Covers:
- Running tasks in parallel
- Comparing speed: sequential vs parallel
- Getting results back

---

### 2. [Task Dependencies & Data Flow](./02_task_dependencies_result_passing/)
**When to use:** One task needs data from another or to be executed after others


Covers:
- Passing results from one task to the next
- Automatically running tasks in the right order
- Running multiple tasks in parallel while respecting dependencies

---

## 💡 Common Scenarios

**Parallel Processing**: Fetch from API, fetch from database, fetch from file → all at once  
**Data Pipeline**: Fetch → Clean → Validate → Save (with email alert if any step fails)  
**Reports**: Generate 3 reports in parallel → Combine → Email results  
**Monitoring**: Check 5 services in parallel → **Email alert if any fail** automatically  

---

## 🚀 Quick Start

```bash
cd examples/01_simple_independent_tasks
python example.py

cd ../02_task_dependencies_result_passing
python example.py

cd ../03_advanced_workflow_error_handling
python example.py
```

---

## 📧 Email Alerts

When a task fails, automatically send an email:

```python
from processes import HTMLSMTPHandler, Task

handler = HTMLSMTPHandler(
    mailhost=('smtp.gmail.com', 587),
    fromaddr='bot@company.com',
    toaddrs=['alerts@company.com'],
    credentials=('email', 'password'),
    secure=(,),
    timeout=10
)

# This task sends an email if it fails
task = Task("critical_job", "log.log", my_function, html_mail_handler=handler)
```

---

## ⚙️ Key Features

**Parallel Execution**
```python
result = process.run(parallel=True, max_workers=4)  # Run up to 4 tasks at once
```

**Logging** - Each task logs to its own file (or share files)
```python
Task("task1", "logs/app.log", func1)
Task("task2", "logs/app.log", func2)
```

**Error Handling** - If a task fails, dependent tasks are skipped automatically
```python
result = process.run()
print(f"Failed: {result.failed_tasks}")
print(f"Passed: {list(result.passed_tasks_results.keys())}")
```

---

## 📖 Where to Go

1. **New to this?** → Start with [Example 1](./01_simple_independent_tasks/)
2. **Want data flow?** → Go to [Example 2](./02_task_dependencies_result_passing/)

Happy coding! 🎯

