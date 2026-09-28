import sqlite3

conn = sqlite3.connect('decretometro.db')
c = conn.cursor()

# Actualizar Dto 441/2026 $40.000.000 (OP 3371)
c.execute("""
    UPDATE cobro_reserva_usos 
    SET nro_op = '3371' 
    WHERE id IN (
        SELECT ru.id FROM cobro_reserva_usos ru
        JOIN cobros cb ON ru.cobro_id = cb.id
        JOIN cuotas q ON cb.cuota_id = q.id
        JOIN decretos d ON q.decreto_id = d.id
        WHERE d.nro_decreto = 441 AND ABS(ru.monto - 40000000.0) < 1.0
    )
""")

# Actualizar Dto 272/2026 $344.560.246,39 (OP 3370)
c.execute("""
    UPDATE cobro_desvios 
    SET nro_op = '3370' 
    WHERE id IN (
        SELECT cd.id FROM cobro_desvios cd
        JOIN cobros cb ON cd.cobro_id = cb.id
        JOIN cuotas q ON cb.cuota_id = q.id
        JOIN decretos d ON q.decreto_id = d.id
        WHERE d.nro_decreto = 272 AND ABS(cd.monto - 344560246.39) < 1.0
    )
""")

conn.commit()
print("Updated remaining OP 3371 and 3370.")
conn.close()
