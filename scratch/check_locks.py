import sqlite3
import os

data_dir = "./data"
dbs = [
    "viki_working_memory.db",
    "orythix_narrative.db",
    "orythix_identity.db",
    "viki_knowledge.db",
    "history.db",
    "lessons_vector.sqlite",
    "traces.db"
]

for db_name in dbs:
    db_path = os.path.join(data_dir, db_name)
    if os.path.exists(db_path):
        print(f"Checking {db_name}...")
        try:
            conn = sqlite3.connect(db_path, timeout=5)
            conn.execute("BEGIN EXCLUSIVE")
            conn.rollback()
            conn.close()
            print(f"  {db_name} is UNLOCKED")
        except sqlite3.OperationalError as e:
            print(f"  {db_name} is LOCKED: {e}")
    else:
        print(f"{db_name} does not exist yet.")
