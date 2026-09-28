import sqlite3

conn = sqlite3.connect('decretometro.db')
c = conn.cursor()

tables = ['cobro_fin_original_usos', 'cobro_desvios', 'cobro_reserva_usos', 'cobro_desvios_recuperos', 'cobro_reserva_usos_recuperos']

for t in tables:
    c.execute(f"SELECT count(*), count(nro_op), count(CASE WHEN nro_op IS NOT NULL AND nro_op != '' AND nro_op != 'Sin asignar' THEN 1 END) FROM {t}")
    tot, has_col, valid_op = c.fetchone()
    print(f"Tabla {t}: Total registros={tot}, OPs informadas={valid_op}")

print("\n--- Muestra de registros con 'Sin asignar' o sin OP ---")
c.execute("""
    SELECT 'cobro_fin_original_usos' as origen, id, cobro_id, monto, fecha, nro_op, notas 
    FROM cobro_fin_original_usos 
    WHERE nro_op IS NULL OR nro_op = '' OR nro_op = 'Sin asignar'
    LIMIT 10
""")
for r in c.fetchall():
    print(r)

c.execute("""
    SELECT 'cobro_desvios' as origen, id, cobro_id, monto, fecha, nro_op, motivo 
    FROM cobro_desvios 
    WHERE nro_op IS NULL OR nro_op = '' OR nro_op = 'Sin asignar'
    LIMIT 10
""")
for r in c.fetchall():
    print(r)
