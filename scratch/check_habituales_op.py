import sqlite3
import pandas as pd

conn = sqlite3.connect('decretometro.db')
c = conn.cursor()

print("--- Aportes Funcionamiento ---")
c.execute("SELECT id, anio, mes, monto_pautado, fecha_cobro FROM aportes_funcionamiento WHERE fecha_cobro IS NOT NULL")
for r in c.fetchall():
    print(r)

print("\n--- Aportes Sueldo ---")
c.execute("SELECT id, anio, mes, monto_pedido, monto_cobrado, estado, fecha_cobro FROM aportes_sueldo")
for r in c.fetchall():
    print(r)

print("\n--- Aportes SAC ---")
c.execute("SELECT id, anio, cuota_nro, monto_pedido, monto_cobrado, estado, fecha_cobro FROM aportes_sac")
for r in c.fetchall():
    print(r)
