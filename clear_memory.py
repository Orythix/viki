"""
Clear poisoned memory entries from VIKI's SQLite databases.
These entries contain the old refusal responses that keep overriding the system prompt.
"""
import sqlite3
import os

POISON_KEYWORDS = ["I am VIKI, your personal sovereign", "not a former romantic", "I am not a former", "Orythix. Could you clarify"]

data_dir = r"d:\My Projects\VIKI\data"
dbs = []
for root, _, files in os.walk(data_dir):
    for f in files:
        if f.endswith(".db"):
            dbs.append(os.path.join(root, f))

print(f"Found {len(dbs)} databases: {dbs}\n")

total_deleted = 0
for db_path in dbs:
    try:
        conn = sqlite3.connect(db_path)
        cur = conn.cursor()
        cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [t[0] for t in cur.fetchall()]
        
        for table in tables:
            # Get columns to find text columns
            cur.execute(f"PRAGMA table_info({table})")
            cols = cur.fetchall()
            text_cols = [c[1] for c in cols if c[2].upper() in ("TEXT", "VARCHAR", "CLOB", "")]
            
            if not text_cols:
                continue
            
            for keyword in POISON_KEYWORDS:
                for col in text_cols:
                    try:
                        cur.execute(f"SELECT COUNT(*) FROM {table} WHERE {col} LIKE ?", (f"%{keyword}%",))
                        count = cur.fetchone()[0]
                        if count > 0:
                            print(f"  [{db_path}] table={table} col={col}: deleting {count} poisoned rows matching '{keyword[:40]}'")
                            cur.execute(f"DELETE FROM {table} WHERE {col} LIKE ?", (f"%{keyword}%",))
                            total_deleted += count
                    except Exception as e:
                        pass  # column may not be queryable
        
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"  Error with {db_path}: {e}")

print(f"\nDone. Total poisoned rows deleted: {total_deleted}")
print("Restart VIKI for the clean memory to take effect.")
