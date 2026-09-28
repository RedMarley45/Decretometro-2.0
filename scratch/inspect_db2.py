import sqlite3

db_path = r"C:\Users\bornemanns\.gemini\antigravity-ide\scratch\decretometro\decretometro.db"

try:
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    print("--- SCHEMA of obras ---")
    cursor.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='obras';")
    row = cursor.fetchone()
    if row:
        print(row[0])
    else:
        print("Table 'obras' not found.")
        
    conn.close()
except Exception as e:
    print(f"Error: {e}")
