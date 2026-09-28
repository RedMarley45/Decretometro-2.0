import sqlite3
import re
import os
import sys

# Append parent dir to path to import database
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
import utils

DB_PATH = "decretometro.db"

def migrate():
    print("Starting migration to populate gastos_funcionamiento...")
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    # 1. Ensure table exists (in case app hasn't run to trigger migrator yet)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS gastos_funcionamiento (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre          TEXT NOT NULL,
            expediente_imuh TEXT NOT NULL UNIQUE,
            activo          INTEGER NOT NULL DEFAULT 1 CHECK(activo IN (0, 1))
        )
    ''')
    conn.commit()

    # 2. Extract unique FUN entries from cobro_desvios
    cursor.execute('''
        SELECT DISTINCT gasto_nombre, gasto_expediente_imuh 
        FROM cobro_desvios 
        WHERE gasto_nombre IS NOT NULL AND TRIM(gasto_nombre) != ""
          AND gasto_expediente_imuh IS NOT NULL AND TRIM(gasto_expediente_imuh) != ""
    ''')
    desv_entries = cursor.fetchall()
    
    # 3. Extract unique FUN entries from cobro_reserva_usos
    cursor.execute('''
        SELECT DISTINCT gasto_nombre, gasto_expediente_imuh 
        FROM cobro_reserva_usos 
        WHERE gasto_nombre IS NOT NULL AND TRIM(gasto_nombre) != ""
          AND gasto_expediente_imuh IS NOT NULL AND TRIM(gasto_expediente_imuh) != ""
    ''')
    res_entries = cursor.fetchall()
    
    # Combine and normalize
    unique_entries = {}
    for entry in list(desv_entries) + list(res_entries):
        name = entry['gasto_nombre'].strip()
        exp = utils.normalizar_expediente_imuh(entry['gasto_expediente_imuh'].strip())
        if exp not in unique_entries:
            unique_entries[exp] = name
            
    # 4. Insert into gastos_funcionamiento
    count = 0
    for exp, name in unique_entries.items():
        try:
            cursor.execute('''
                INSERT INTO gastos_funcionamiento (nombre, expediente_imuh, activo)
                VALUES (?, ?, 1)
            ''', (name, exp))
            count += 1
            print(f"Inserted Gasto FUN: {name} (Exp: {exp})")
        except sqlite3.IntegrityError:
            print(f"Gasto FUN already exists: {name} (Exp: {exp})")
            
    conn.commit()
    conn.close()
    print(f"Migration completed. Successfully populated {count} entries.")

if __name__ == "__main__":
    migrate()
