# Processes Examples & Usage Guide

Welcome to the **Processes** library examples! This directory shows you how to build workflows where multiple operations run together, with some depending on others.

## 📚 What is Processes?

**Processes** is a Python library that helps you run multiple tasks in sequence or in parallel, automatically handling when one task needs data from another. It handles errors gracefully and **sends email alerts when tasks fail** — no extra code needed.

### Three Main Ideas

- **Task**: A piece of work you want to do (run a function, fetch data, save results, etc.)
- **TaskDependency**: A task that depends on another task's result
- **Process**: The coordinator that runs all your tasks, handles data passing, and monitors for errors