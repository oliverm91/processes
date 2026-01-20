# Processes Examples & Usage Guide

Welcome to the **Processes** library examples! This directory shows you how to build workflows where multiple operations run together, with some depending on others.

## 📚 What is Processes?

**Processes** is a Python library that helps you run multiple tasks in sequence or in parallel, automatically handling when one task needs data from another. It handles errors gracefully and **sends email alerts when tasks fail** — no extra code needed.

### Three Main Ideas

- **Task**: A piece of work you want to do (run a function, fetch data, save results, etc.)
- **TaskDependency**: A task that depends on another task's result
- **Process**: The coordinator that runs all your tasks, handles data passing, and monitors for errors

---

## 🗂️ The 2 Examples

### 1. [Basic Tasks & Dependencies](./01_basic_tasks_and_dependencies/)
**When to use:** Run multiple operations at the same time, including tasks with simple dependencies

Covers:
- Creating basic tasks
- Running tasks in parallel
- Comparing speed: sequential vs parallel
- Simple task dependencies
- Passing results from one task to the next

---

### 2. [Task Dependencies & Data Flow](./02_task_dependencies_result_passing/)
**When to use:** One task needs data from another or to be executed after others


Covers:
- Passing results from one task to the next
- Automatically running tasks in the right order
- Running multiple tasks in parallel while respecting dependencies

---