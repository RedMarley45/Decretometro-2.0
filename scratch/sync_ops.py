import sqlite3
from database import register_or_update_op, get_connection

with get_connection() as conn:
    cursor = conn.cursor()
    
    # from cobro_desvios
    rows = cursor.execute("SELECT nro_op, obra_id, gasto_expediente_imuh FROM cobro_desvios WHERE nro_op IS NOT NULL").fetchall()
    for r in rows:
        nro_op = r['nro_op']
        obra_id = r['obra_id']
        g_exp = r['gasto_expediente_imuh']
        gasto_id = None
        if g_exp:
            gr = cursor.execute("SELECT id FROM gastos_funcionamiento WHERE expediente_imuh = ?", (g_exp,)).fetchone()
            if gr: gasto_id = gr['id']
        register_or_update_op(nro_op, obra_id=obra_id, gasto_id=gasto_id)

    # from cobro_reserva_usos
    rows = cursor.execute("SELECT nro_op, obra_id, gasto_expediente_imuh FROM cobro_reserva_usos WHERE nro_op IS NOT NULL").fetchall()
    for r in rows:
        nro_op = r['nro_op']
        obra_id = r['obra_id']
        g_exp = r['gasto_expediente_imuh']
        gasto_id = None
        if g_exp:
            gr = cursor.execute("SELECT id FROM gastos_funcionamiento WHERE expediente_imuh = ?", (g_exp,)).fetchone()
            if gr: gasto_id = gr['id']
        register_or_update_op(nro_op, obra_id=obra_id, gasto_id=gasto_id)
        
    # from cobro_fin_original_usos
    rows = cursor.execute("SELECT nro_op, obra_id, gasto_expediente_imuh FROM cobro_fin_original_usos WHERE nro_op IS NOT NULL").fetchall()
    for r in rows:
        nro_op = r['nro_op']
        obra_id = r['obra_id']
        g_exp = r['gasto_expediente_imuh']
        gasto_id = None
        if g_exp:
            gr = cursor.execute("SELECT id FROM gastos_funcionamiento WHERE expediente_imuh = ?", (g_exp,)).fetchone()
            if gr: gasto_id = gr['id']
        register_or_update_op(nro_op, obra_id=obra_id, gasto_id=gasto_id)

print("Sincronizacion completada.")
