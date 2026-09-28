import sqlite3

conn = sqlite3.connect('decretometro.db')
sql = conn.execute("SELECT sql FROM sqlite_master WHERE name='cobros'").fetchone()[0]
print("--- COBROS SCHEMA ---")
print(sql)

print("\n--- PROBANDO CHECK DE EXCLUSION MUTUA ---")
try:
    conn.execute("INSERT INTO cobros (origen_tipo, cuota_id, convenio_solicitud_id, monto, fecha) VALUES ('decreto', 1, 1, 100, '2026-01-01')")
    print("FALLO: Debio bloquearse")
except sqlite3.IntegrityError as e:
    print("EXITO: Bloqueado a nivel motor SQL por CHECK:", e)

try:
    conn.execute("INSERT INTO cobros (origen_tipo, cuota_id, convenio_solicitud_id, monto, fecha) VALUES ('convenio', NULL, NULL, 100, '2026-01-01')")
    print("FALLO: Debio bloquearse")
except sqlite3.IntegrityError as e:
    print("EXITO: Bloqueado a nivel motor SQL por CHECK:", e)
