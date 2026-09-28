import sqlite3

conn = sqlite3.connect('decretometro.db')
c = conn.cursor()

c.execute("UPDATE cobro_desvios_recuperos SET nro_op = '3370' WHERE desvio_id = 1")
c.execute("UPDATE cobro_desvios_recuperos SET nro_op = '3371' WHERE id IN (SELECT r.id FROM cobro_desvios_recuperos r JOIN cobro_desvios cd ON r.desvio_id = cd.id WHERE ABS(cd.monto - 40000000.0) < 1)")

conn.commit()
print("Updated recuperos OP successfully.")
conn.close()
