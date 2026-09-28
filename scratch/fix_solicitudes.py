import sqlite3

db_path = 'decretometro.db'
conn = sqlite3.connect(db_path)
conn.row_factory = sqlite3.Row
cursor = conn.cursor()
cursor.execute("UPDATE solicitudes_financiamiento SET estado = 'Pendiente', decreto_id = NULL WHERE estado = 'Aprobado' AND (decreto_id IS NULL OR decreto_id NOT IN (SELECT id FROM decretos))")
print(f"Filas actualizadas: {cursor.rowcount}")
conn.commit()
conn.close()
