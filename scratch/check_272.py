import sqlite3

conn = sqlite3.connect('decretometro.db')
c = conn.cursor()

c.execute("SELECT id FROM decretos WHERE nro_decreto = 272 AND anio = 2026")
dec_id = c.fetchone()[0]
print("Decreto 272/2026 ID:", dec_id)

c.execute("SELECT id FROM cuotas WHERE decreto_id = ?", (dec_id,))
cuota_ids = [r[0] for r in c.fetchall()]
print("Cuotas IDs:", cuota_ids)

for t in ['cobro_fin_original_usos', 'cobro_desvios', 'cobro_reserva_usos', 'cobro_desvios_recuperos', 'cobro_reserva_usos_recuperos']:
    placeholders = ','.join('?' * len(cuota_ids))
    if t in ['cobro_desvios_recuperos', 'cobro_reserva_usos_recuperos']:
        continue
    c.execute(f"SELECT '{t}', x.id, x.monto, x.nro_op FROM {t} x JOIN cobros cb ON x.cobro_id = cb.id WHERE cb.cuota_id IN ({placeholders})", cuota_ids)
    res = c.fetchall()
    if res:
        print(t, res)
