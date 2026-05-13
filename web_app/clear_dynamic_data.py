"""
Clear all dynamic/operational data from the database.

IMPORTANT: Stop the Streamlit app and prediction loop before running this.

Usage (from the web_app folder):
    python clear_dynamic_data.py
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from backend.mysql_database_manager import db_manager

DYNAMIC_TABLES = ["alerts", "leak_predictions", "sensor_readings"]


def row_count(table: str) -> int:
    df = db_manager._query_to_df(f"SELECT COUNT(*) AS n FROM {table}")
    return int(df["n"].iloc[0])


def main():
    print("\n=== THIWASCO — Clear Dynamic Data ===\n")

    # Show current counts
    print("Current row counts:")
    totals_before = {}
    for table in DYNAMIC_TABLES:
        n = row_count(table)
        totals_before[table] = n
        print(f"  {table:<22} {n:>8,} rows")

    total = sum(totals_before.values())
    if total == 0:
        print("\nAll tables are already empty. Nothing to do.")
        return

    print(f"\n  Total rows to delete: {total:,}")
    confirm = input("\nProceed? (yes / no): ").strip().lower()
    if confirm != "yes":
        print("Aborted.")
        return

    # Truncate each table (DDL — bypasses row-level locks)
    print()
    for table in DYNAMIC_TABLES:
        try:
            db_manager._execute(f"SET FOREIGN_KEY_CHECKS = 0")
            db_manager._execute(f"TRUNCATE TABLE {table}")
            db_manager._execute(f"SET FOREIGN_KEY_CHECKS = 1")
            remaining = row_count(table)
            print(f"  {table:<22} cleared  ({remaining} rows remaining)")
        except Exception as e:
            print(f"  {table:<22} FAILED — {e}")

    print("\nDone. Restart the app and prediction loop when ready.\n")


if __name__ == "__main__":
    main()
