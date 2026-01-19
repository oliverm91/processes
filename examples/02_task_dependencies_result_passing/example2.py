"""
Example 2: Task Dependencies & Result Passing

This example demonstrates how to create tasks with dependencies and automatically
pass results from one task to another.

Demonstrates:
- Creating TaskDependency objects
- Passing results as positional arguments
- Passing results as keyword arguments
- Multiple dependencies on a single task
- Dependency ordering (topological sort)
- Parallel execution with dependencies
"""

import json
import os
from datetime import datetime

from processes import Process, Task, TaskDependency


# Step 1: Define task functions
def fetch_user_data() -> dict:
    """Fetch raw user data from source."""
    users = [
        {"id": 1, "name": "Alice", "age": 30, "salary": 50000},
        {"id": 2, "name": "Bob", "age": 25, "salary": 45000},
        {"id": 3, "name": "Charlie", "age": 35, "salary": 60000},
    ]
    return {"users": users, "timestamp": datetime.now().isoformat()}


def validate_data(raw_data: dict) -> dict:
    """Validate the fetched data."""
    users = raw_data.get("users", [])
    valid_users = [u for u in users if all(k in u for k in ["id", "name", "age", "salary"])]
    return {
        "valid_count": len(valid_users),
        "invalid_count": len(users) - len(valid_users),
        "users": valid_users,
    }


def calculate_statistics(raw_data: dict) -> dict:
    """Calculate statistics from raw data."""
    users = raw_data.get("users", [])
    if not users:
        return {"avg_age": 0, "avg_salary": 0, "total_records": 0}

    ages = [u.get("age", 0) for u in users]
    salaries = [u.get("salary", 0) for u in users]

    return {
        "avg_age": sum(ages) / len(ages),
        "avg_salary": sum(salaries) / len(salaries),
        "total_records": len(users),
        "age_range": (min(ages), max(ages)) if ages else (0, 0),
        "salary_range": (min(salaries), max(salaries)) if salaries else (0, 0),
    }


def prepare_for_storage(validated: dict, stats: dict) -> dict:
    """Prepare data for storage combining validation and statistics."""
    return {
        "validation": validated,
        "statistics": stats,
        "prepared_at": datetime.now().isoformat(),
    }


def save_to_database(prepared_data: dict, output_file: str = "output.json") -> str:
    """Save prepared data to storage."""
    with open(output_file, "w") as f:
        json.dump(prepared_data, f, indent=2, default=str)
    return f"Data saved to {output_file}"


def generate_report(save_result: str, stats: dict | None = None) -> str:
    """Generate final report."""
    if stats is None:
        stats = {
            "avg_age": 0,
            "avg_salary": 0,
            "total_records": 0,
            "age_range": (0, 0),
            "salary_range": (0, 0),
        }
    report = f"""
    ========== DATA PROCESSING REPORT ==========
    {save_result}

    Statistics Summary:
    - Total Records: {stats["total_records"]}
    - Average Age: {stats["avg_age"]:.1f}
    - Average Salary: ${stats["avg_salary"]:.2f}
    - Age Range: {stats["age_range"][0]} - {stats["age_range"][1]}
    - Salary Range: ${stats["salary_range"][0]} - ${stats["salary_range"][1]}
    ============================================
    """
    return report


def main():
    """Main execution function."""

    # Create logs directory
    log_dir = "logs"
    os.makedirs(log_dir, exist_ok=True)

    # Task 1: Fetch data (no dependencies)
    t_fetch = Task("fetch_data", f"{log_dir}/fetch.log", fetch_user_data)

    # Task 2: Validate (depends on fetch)
    t_validate = Task(
        "validate",
        f"{log_dir}/validate.log",
        validate_data,
        dependencies=[
            TaskDependency(
                "fetch_data",
                use_result_as_additional_args=True,  # Pass fetch result as arg
            )
        ],
    )

    # Task 3: Calculate stats (depends on fetch)
    t_stats = Task(
        "calculate_stats",
        f"{log_dir}/stats.log",
        calculate_statistics,
        dependencies=[
            TaskDependency(
                "fetch_data",
                use_result_as_additional_args=True,  # Pass fetch result as arg
            )
        ],
    )

    # Task 4: Prepare (depends on both validate and stats)
    t_prepare = Task(
        "prepare_storage",
        f"{log_dir}/prepare.log",
        prepare_for_storage,
        dependencies=[
            TaskDependency(
                "validate",
                use_result_as_additional_args=True,  # validate result → 1st arg
            ),
            TaskDependency(
                "calculate_stats",
                use_result_as_additional_args=True,  # stats result → 2nd arg
            ),
        ],
    )

    # Task 5: Save (depends on prepare)
    output_file = os.path.join(log_dir, "data_output.json")
    t_save = Task(
        "save_data",
        f"{log_dir}/save.log",
        save_to_database,
        args=(),
        kwargs={"output_file": output_file},
        dependencies=[TaskDependency("prepare_storage", use_result_as_additional_args=True)],
    )

    # Task 6: Report (depends on save and stats)
    t_report = Task(
        "generate_report",
        f"{log_dir}/report.log",
        generate_report,
        dependencies=[
            TaskDependency(
                "save_data",
                use_result_as_additional_args=True,
            ),
            TaskDependency(
                "calculate_stats",
                use_result_as_additional_kwargs=True,
                additional_kwarg_name="stats",  # stats result → kwarg
            ),
        ],
    )

    with Process([t_fetch, t_validate, t_stats, t_prepare, t_save, t_report]) as process:
        _ = process.run(parallel=False)

    with Process([t_fetch, t_validate, t_stats, t_prepare, t_save, t_report]) as process:
        _ = process.run(parallel=True, max_workers=4)


if __name__ == "__main__":
    main()
