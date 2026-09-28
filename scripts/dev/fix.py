import os

EXTRA_LOGIC = """

# --- PAGOS A FONDOS PROPIOS Y RECUPEROS ---

def update_monto_contrato_obra(obra_id, nuevo_monto):
    total_pagado = get_total_pagado_obra(obra_id)
    if nuevo_monto > 0 and nuevo_monto < (total_pagado - TOLERANCE):
        raise ValueError(f"No se puede reducir el monto de contrato por debajo del total ya pagado a la contratista (${total_pagado:,.2f})")
    
    with db_session() as conn:
        conn.execute("UPDATE obras SET monto_contrato = ? WHERE id = ?", (nuevo_monto, obra_id))

def get_pagos_fondos_propios(obra_id=None):
    with db_session() as conn:
        query = "SELECT * FROM pagos_fondos_propios"
        params = []
        if obra_id:
            query += " WHERE obra_id = ?"
            params.append(obra_id)
        query += " ORDER BY fecha DESC"
        return [dict(row) for row in conn.execute(query, params).fetchall()]

def add_pago_fondos_propios(obra_id, monto, fecha, nro_op, observaciones):
    _validar_op_o_nota_db(nro_op, observaciones, "pago con fondos propios")
    with db_session() as conn:
        conn.execute('''
            INSERT INTO pagos_fondos_propios (obra_id, monto, fecha, nro_op, observaciones)
            VALUES (?, ?, ?, ?, ?)
        ''', (obra_id, monto, fecha, nro_op, observaciones))

def delete_pago_fondos_propios(pago_id):
    with db_session() as conn:
        pago = conn.execute("SELECT * FROM pagos_fondos_propios WHERE id = ?", (pago_id,)).fetchone()
        if not pago: return
        obra_id = pago['obra_id']
        monto_pago = pago['monto']
        
        # Validar si ya se recuperó algo de esta obra
        total_pagado_fp = sum(p['monto'] for p in conn.execute("SELECT monto FROM pagos_fondos_propios WHERE obra_id = ?", (obra_id,)).fetchall())
        total_recuperado = sum(r['monto'] for r in conn.execute("SELECT monto FROM recuperos_fondos_propios WHERE obra_id = ?", (obra_id,)).fetchall())
        
        if (total_pagado_fp - monto_pago) < (total_recuperado - TOLERANCE):
            raise ValueError(f"No se puede eliminar. Al hacerlo, el total de adelantos sería menor a los fondos que ya recuperó la gestión (${total_recuperado:,.2f}). Elimine los recuperos primero.")
            
        conn.execute("DELETE FROM pagos_fondos_propios WHERE id = ?", (pago_id,))

def get_recuperos_fondos_propios(obra_id=None):
    with db_session() as conn:
        query = "SELECT * FROM recuperos_fondos_propios"
        params = []
        if obra_id:
            query += " WHERE obra_id = ?"
            params.append(obra_id)
        query += " ORDER BY fecha DESC"
        return [dict(row) for row in conn.execute(query, params).fetchall()]

def get_recuperos_by_cobro(cobro_id):
    with db_session() as conn:
        return [dict(row) for row in conn.execute("SELECT * FROM recuperos_fondos_propios WHERE cobro_id = ? ORDER BY fecha DESC", (cobro_id,)).fetchall()]

def add_recupero_fondos_propios(cobro_id, obra_id, monto, fecha, nro_op, notas):
    _validar_op_o_nota_db(nro_op, notas, "recupero de fondos propios")
    
    # Validar que no supere el tope
    tope = get_tope_recupero(obra_id)
    if monto > tope + TOLERANCE:
        raise ValueError(f"El monto a recuperar excede el total adeudado a Fondos Propios para esta obra (${tope:,.2f}).")
        
    with db_session() as conn:
        conn.execute('''
            INSERT INTO recuperos_fondos_propios (cobro_id, obra_id, monto, fecha, nro_op, notas)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (cobro_id, obra_id, monto, fecha, nro_op, notas))

def delete_recupero_fondos_propios(recupero_id):
    with db_session() as conn:
        conn.execute("DELETE FROM recuperos_fondos_propios WHERE id = ?", (recupero_id,))

def get_total_pagado_obra(obra_id):
    with db_session() as conn:
        pagos_fp = sum(row['monto'] for row in conn.execute("SELECT monto FROM pagos_fondos_propios WHERE obra_id = ?", (obra_id,)).fetchall())
        fin_orig = sum(row['monto'] for row in conn.execute("SELECT monto FROM cobro_fin_original_usos WHERE obra_id = ?", (obra_id,)).fetchall())
        desvios = sum(row['monto'] for row in conn.execute("SELECT monto FROM cobro_desvios WHERE obra_id = ?", (obra_id,)).fetchall())
        reservas = sum(row['monto'] for row in conn.execute("SELECT monto FROM cobro_reserva_usos WHERE obra_id = ?", (obra_id,)).fetchall())
        return pagos_fp + fin_orig + desvios + reservas

def get_tope_recupero(obra_id):
    with db_session() as conn:
        pagos_fp = sum(row['monto'] for row in conn.execute("SELECT monto FROM pagos_fondos_propios WHERE obra_id = ?", (obra_id,)).fetchall())
        recuperos = sum(row['monto'] for row in conn.execute("SELECT monto FROM recuperos_fondos_propios WHERE obra_id = ?", (obra_id,)).fetchall())
        return max(0.0, pagos_fp - recuperos)
"""

with open('database.py', 'a', encoding='utf-8') as f:
    f.write(EXTRA_LOGIC)
