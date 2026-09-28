import sqlite3
import pandas as pd

conn = sqlite3.connect('decretometro.db')
c = conn.cursor()

# Ver la lista de tablas
c.execute("SELECT name FROM sqlite_master WHERE type='table'")
tables = [r[0] for r in c.fetchall()]
print("Tablas en la BD:", tables)

for t in tables:
    c.execute(f"PRAGMA table_info('{t}')")
    cols = [r[1] for r in c.fetchall()]
    if 'nro_op' in cols or 'op' in cols:
        print(f"\n--- Tabla: {t} (Contiene OP) ---")
        c.execute(f"SELECT count(*) FROM {t}")
        tot = c.fetchone()[0]
        c.execute(f"SELECT count(*) FROM {t} WHERE nro_op IS NULL OR TRIM(nro_op) = '' OR nro_op = 'Sin asignar'")
        sin_op = c.fetchone()[0]
        print(f"Total filas: {tot} | Sin OP: {sin_op}")
