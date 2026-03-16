#!/usr/bin/env python3
"""
Echo Budget Tracker — offline, local only, never synced to Notion.
Simple income/expense tracker with categories.
"""
import json, sqlite3, sys
from pathlib import Path
from datetime import datetime

DB = Path.home() / ".echo_budget.db"  # hidden file, not in Echo directory

def init():
    con = sqlite3.connect(DB)
    con.execute("""
        CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT,
            type TEXT,  -- income or expense
            category TEXT,
            description TEXT,
            amount REAL
        )
    """)
    con.commit()
    return con

def add(type_, category, description, amount):
    con = init()
    con.execute(
        "INSERT INTO transactions (date, type, category, description, amount) VALUES (?,?,?,?,?)",
        (datetime.now().strftime("%Y-%m-%d"), type_, category, description, float(amount))
    )
    con.commit()
    print(f"Added: {type_} ${amount} — {category}: {description}")

def summary():
    con = init()
    income = con.execute("SELECT SUM(amount) FROM transactions WHERE type='income'").fetchone()[0] or 0
    expenses = con.execute("SELECT SUM(amount) FROM transactions WHERE type='expense'").fetchone()[0] or 0
    print(f"\n{'='*40}")
    print(f"  BUDGET SUMMARY")
    print(f"{'='*40}")
    print(f"  Income:   ${income:.2f}")
    print(f"  Expenses: ${expenses:.2f}")
    print(f"  Balance:  ${income - expenses:.2f}")
    print(f"{'='*40}\n")

    print("  BY CATEGORY:")
    rows = con.execute("""
        SELECT type, category, SUM(amount) as total
        FROM transactions
        GROUP BY type, category
        ORDER BY type, total DESC
    """).fetchall()
    for row in rows:
        print(f"  [{row[0]}] {row[1]}: ${row[2]:.2f}")
    print()

def recent(n=10):
    con = init()
    rows = con.execute(
        "SELECT date, type, category, description, amount FROM transactions ORDER BY id DESC LIMIT ?", (n,)
    ).fetchall()
    print(f"\n  RECENT TRANSACTIONS:")
    for r in rows:
        sign = "+" if r[1] == "income" else "-"
        print(f"  {r[0]} {sign}${r[4]:.2f} [{r[2]}] {r[3]}")
    print()

def monthly():
    con = init()
    rows = con.execute("""
        SELECT strftime('%Y-%m', date) as month,
               SUM(CASE WHEN type='income' THEN amount ELSE 0 END) as income,
               SUM(CASE WHEN type='expense' THEN amount ELSE 0 END) as expenses
        FROM transactions
        GROUP BY month
        ORDER BY month DESC
    """).fetchall()
    print(f"\n  MONTHLY BREAKDOWN:")
    for r in rows:
        balance = r[1] - r[2]
        print(f"  {r[0]} — In: ${r[1]:.2f} Out: ${r[2]:.2f} Net: ${balance:.2f}")
    print()

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("""
Echo Budget Tracker (local only — never synced)

Commands:
  python3 tools/budget.py income  [category] [description] [amount]
  python3 tools/budget.py expense [category] [description] [amount]
  python3 tools/budget.py summary
  python3 tools/budget.py recent
  python3 tools/budget.py monthly

Examples:
  python3 tools/budget.py income  golem "compute task" 5.50
  python3 tools/budget.py expense bills "AT&T internet" 30.00
  python3 tools/budget.py expense propane "2x 20lb bottles" 40.00
  python3 tools/budget.py summary
        """)
    elif sys.argv[1] == "income":
        add("income", sys.argv[2], sys.argv[3], sys.argv[4])
    elif sys.argv[1] == "expense":
        add("expense", sys.argv[2], sys.argv[3], sys.argv[4])
    elif sys.argv[1] == "summary":
        summary()
    elif sys.argv[1] == "recent":
        recent()
    elif sys.argv[1] == "monthly":
        monthly()
