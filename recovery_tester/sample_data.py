from __future__ import annotations

import random
import sqlite3
from pathlib import Path

from .exceptions import OperationalError


def create_sample_database(db_path: Path, order_count: int = 1000, seed: int = 42) -> Path:
    if order_count <= 0:
        raise OperationalError("order_count must be greater than zero")
    if db_path.exists():
        raise OperationalError(f"Destination database already exists: {db_path}")

    db_path.parent.mkdir(parents=True, exist_ok=True)
    rng = random.Random(seed)

    conn = sqlite3.connect(db_path)
    try:
        conn.execute("PRAGMA foreign_keys = ON")
        conn.executescript(
            """
            CREATE TABLE customers (
                customer_id INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                email TEXT NOT NULL UNIQUE,
                region TEXT NOT NULL
            );

            CREATE TABLE orders (
                order_id INTEGER PRIMARY KEY,
                customer_id INTEGER NOT NULL,
                order_date TEXT NOT NULL,
                amount REAL NOT NULL,
                status TEXT NOT NULL,
                FOREIGN KEY(customer_id) REFERENCES customers(customer_id)
            );
            """
        )

        regions = ["north", "south", "east", "west"]
        statuses = ["created", "paid", "shipped", "cancelled"]

        customers = []
        for customer_id in range(1, 101):
            customers.append(
                (
                    customer_id,
                    f"Customer {customer_id}",
                    f"customer{customer_id}@example.com",
                    regions[(customer_id - 1) % len(regions)],
                )
            )
        conn.executemany(
            "INSERT INTO customers(customer_id, name, email, region) VALUES (?, ?, ?, ?)",
            customers,
        )

        orders = []
        for order_id in range(1, order_count + 1):
            customer_id = rng.randint(1, 100)
            day = (order_id % 28) + 1
            month = ((order_id // 28) % 12) + 1
            amount = round(rng.uniform(10.0, 1000.0), 2)
            status = statuses[rng.randint(0, len(statuses) - 1)]
            orders.append((order_id, customer_id, f"2026-{month:02d}-{day:02d}", amount, status))

        conn.executemany(
            "INSERT INTO orders(order_id, customer_id, order_date, amount, status) VALUES (?, ?, ?, ?, ?)",
            orders,
        )
        conn.commit()
    finally:
        conn.close()

    return db_path
