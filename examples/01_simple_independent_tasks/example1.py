"""
Example 1: Simple Independent Tasks

This example demonstrates how to create and execute multiple independent tasks.
Each task runs independently without relying on results from other tasks.

Demonstrates:
- Creating Task objects
- Running tasks sequentially
- Running tasks in parallel
- Accessing results
- Comparing execution times
"""

import os
import time

from processes import Process, Task


# Step 1: Define task functions
def fetch_user_count() -> int:
    """Simulate fetching user count from database."""
    time.sleep(2)
    return 1000


def fetch_product_count() -> int:
    """Simulate fetching product count from database."""
    time.sleep(2)
    return 5000


def fetch_order_count() -> int:
    """Simulate fetching order count from database."""
    time.sleep(2)
    return 15000


def calculate_metrics(users: int, products: int, orders: int) -> dict:
    """Simulate calculating metrics from counts."""
    time.sleep(1)
    return {
        "avg_orders_per_user": orders / users if users > 0 else 0,
        "avg_products_per_order": products / orders if orders > 0 else 0,
        "total_records": users + products + orders,
    }


def main():
    """Main execution function."""

    # Create logs directory
    log_dir = "logs"
    os.makedirs(log_dir, exist_ok=True)

    # Step 2: Create Task objects
    t1 = Task("fetch_users", f"{log_dir}/fetch_users.log", fetch_user_count)
    t2 = Task("fetch_products", f"{log_dir}/fetch_products.log", fetch_product_count)
    t3 = Task("fetch_orders", f"{log_dir}/fetch_orders.log", fetch_order_count)
    t4 = Task("calculate_metrics", f"{log_dir}/calculate_metrics.log", calculate_metrics)

    # Step 3A: Sequential execution
    with Process([t1, t2, t3, t4]) as process:
        start = time.time()
        _ = process.run(parallel=False)
        duration_seq = time.time() - start

    # Step 3B: Parallel execution
    with Process([t1, t2, t3, t4]) as process:
        start = time.time()
        _ = process.run(parallel=True, max_workers=4)
        duration_par = time.time() - start

    # Step 4: Display results
    print("Sequential execution:", f"{duration_seq:.2f}s")
    print("Parallel execution:", f"{duration_par:.2f}s")
    print(f"Speedup: {duration_seq / duration_par:.2f}x")
    print()
    if os.path.exists(log_dir):
        log_files = os.listdir(log_dir)
        print(f"Log files created: {log_files}")


if __name__ == "__main__":
    main()
