import sqlite3
import sys

db_path = r"C:\Users\bornemanns\.gemini\antigravity-ide\scratch\decretometro\Montos de obra\obras_backup_15-09-2026_10-56.db"

try:
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    print("--- SCHEMA ---")
    cursor.execute("SELECT sql FROM sqlite_master WHERE type='table';")
    for row in cursor.fetchall():
        print(row[0])
        
    print("\n--- DATA (obras) ---")
    cursor.execute("SELECT * FROM obras LIMIT 5;")
    column_names = [description[0] for description in cursor.description]
    print(column_names)
    for row in cursor.fetchall():
        print(row)
        
    conn.close()
except Exception as e:
    print(f"Error: {e}")
