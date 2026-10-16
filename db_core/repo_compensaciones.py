"""
db_core/repo_compensaciones.py - Compensación Bilateral de Deudas Cruzadas con Simetría Atómica y Tope Bilateral
"""
from db_core.connection import db_session, TOLERANCE
from db_core.repo_auditoria import _validar_op_o_nota_db


def obtener_detalles_compensacion_grupo(grupo_id):
    """Retorna los registros asociados a un grupo de compensación."""
    with db_session() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM cobro_desvios_recuperos WHERE grupo_compensacion_id = ?", (grupo_id,))
        desv = [dict(r) for r in cursor.fetchall()]
        cursor.execute("SELECT * FROM cobro_reserva_usos_recuperos WHERE grupo_compensacion_id = ?", (grupo_id,))
        res = [dict(r) for r in cursor.fetchall()]
        return {"desvios_recuperos": desv, "reserva_usos_recuperos": res}


def delete_desvio_recupero(recupero_id=None, rec_id=None):
    if recupero_id is None and rec_id is not None:
        recupero_id = rec_id
    if recupero_id is None:
        raise ValueError("ID de recupero no especificado.")
    with db_session() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT grupo_compensacion_id FROM cobro_desvios_recuperos WHERE id = ?", (recupero_id,))
        row = cursor.fetchone()
        if row and row["grupo_compensacion_id"]:
            gid = row["grupo_compensacion_id"]
            cursor.execute("DELETE FROM cobro_desvios_recuperos WHERE grupo_compensacion_id = ?", (gid,))
            cursor.execute("DELETE FROM cobro_reserva_usos_recuperos WHERE grupo_compensacion_id = ?", (gid,))
        else:
            cursor.execute("DELETE FROM cobro_desvios_recuperos WHERE id = ?", (recupero_id,))


def delete_reserva_uso_recupero(recupero_id=None, rec_id=None):
    if recupero_id is None and rec_id is not None:
        recupero_id = rec_id
    if recupero_id is None:
        raise ValueError("ID de recupero no especificado.")
    with db_session() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT grupo_compensacion_id FROM cobro_reserva_usos_recuperos WHERE id = ?", (recupero_id,))
        row = cursor.fetchone()
        if row and row["grupo_compensacion_id"]:
            gid = row["grupo_compensacion_id"]
            cursor.execute("DELETE FROM cobro_desvios_recuperos WHERE grupo_compensacion_id = ?", (gid,))
            cursor.execute("DELETE FROM cobro_reserva_usos_recuperos WHERE grupo_compensacion_id = ?", (gid,))
        else:
            cursor.execute("DELETE FROM cobro_reserva_usos_recuperos WHERE id = ?", (recupero_id,))


def update_desvio_recupero(rec_id=None, monto=0, fecha=None, destino_tipo=None, destino_detalle=None, decreto_destino_id=None, nro_op=None, notas=None, recupero_id=None):
    """
    Edita un recupero de desvío.
    Si pertenece a un grupo de compensación bilateral, valida el tope adeudado en TODAS las contrapartes
    y propaga simétricamente el cambio a todos los registros hermanos del grupo.
    """
    if rec_id is None and recupero_id is not None:
        rec_id = recupero_id
    if rec_id is None:
        raise ValueError("ID de recupero no especificado.")
    _validar_op_o_nota_db(nro_op, notas, contexto="recupero de desvío")
    if monto <= 0:
        raise ValueError("El monto recuperado debe ser mayor a 0.")
    with db_session() as conn:
        cursor = conn.cursor()
    
        cursor.execute("SELECT * FROM cobro_desvios_recuperos WHERE id = ?", (rec_id,))
        rec_row = cursor.fetchone()
        if not rec_row:
            raise ValueError("Recupero no encontrado.")
        desvio_id = rec_row["desvio_id"]
        grupo_id = rec_row["grupo_compensacion_id"]

        if destino_tipo is None:
            destino_tipo = rec_row["destino_tipo"]
        if destino_detalle is None:
            destino_detalle = rec_row["destino_detalle"]
        if decreto_destino_id is None:
            decreto_destino_id = rec_row["decreto_destino_id"]
    
        cursor.execute("SELECT monto FROM cobro_desvios WHERE id = ?", (desvio_id,))
        d_row = cursor.fetchone()
    
        cursor.execute("SELECT COALESCE(SUM(monto), 0) as tot_recuperado FROM cobro_desvios_recuperos WHERE desvio_id = ? AND id != ?", (desvio_id, rec_id))
        otros_recuperos = cursor.fetchone()["tot_recuperado"]
    
        if (otros_recuperos + monto) > (d_row["monto"] + TOLERANCE):
            raise ValueError(f"El monto a recuperar editado ({monto:.2f}) supera el saldo adeudado del desvío ({d_row['monto'] - otros_recuperos:.2f}).")
        
        if grupo_id:
            # Validación de Tope Bilateral en todas las contrapartes del grupo
            cursor.execute("SELECT * FROM cobro_desvios_recuperos WHERE grupo_compensacion_id = ? AND id != ?", (grupo_id, rec_id))
            hermanos_desv = cursor.fetchall()
            for hd in hermanos_desv:
                cursor.execute("SELECT monto FROM cobro_desvios WHERE id = ?", (hd["desvio_id"],))
                hd_row = cursor.fetchone()
                cursor.execute("SELECT COALESCE(SUM(monto), 0) as tot FROM cobro_desvios_recuperos WHERE desvio_id = ? AND id != ?", (hd["desvio_id"], hd["id"]))
                hd_otros = cursor.fetchone()["tot"]
                if (hd_otros + monto) > (hd_row["monto"] + TOLERANCE):
                    raise ValueError(f"El monto editado supera el saldo adeudado del desvío compensado hermano ({hd_row['monto'] - hd_otros:.2f}).")

            cursor.execute("SELECT * FROM cobro_reserva_usos_recuperos WHERE grupo_compensacion_id = ?", (grupo_id,))
            hermanos_res = cursor.fetchall()
            for hr in hermanos_res:
                cursor.execute("SELECT monto FROM cobro_reserva_usos WHERE id = ?", (hr["reserva_uso_id"],))
                hr_row = cursor.fetchone()
                cursor.execute("SELECT COALESCE(SUM(monto), 0) as tot FROM cobro_reserva_usos_recuperos WHERE reserva_uso_id = ? AND id != ?", (hr["reserva_uso_id"], hr["id"]))
                hr_otros = cursor.fetchone()["tot"]
                if (hr_otros + monto) > (hr_row["monto"] + TOLERANCE):
                    raise ValueError(f"El monto editado supera el saldo adeudado del uso de reserva compensado ({hr_row['monto'] - hr_otros:.2f}).")

            # Si todos los topes bilaterales son válidos, propagar simétricamente
            for hd in hermanos_desv:
                cursor.execute("""
                    UPDATE cobro_desvios_recuperos
                    SET monto = ?, fecha = ?, nro_op = ?, notas = ?
                    WHERE id = ?
                """, (monto, fecha, nro_op, notas, hd["id"]))

            for hr in hermanos_res:
                cursor.execute("""
                    UPDATE cobro_reserva_usos_recuperos
                    SET monto = ?, fecha = ?, nro_op = ?, notas = ?
                    WHERE id = ?
                """, (monto, fecha, nro_op, notas, hr["id"]))

            cursor.execute("""
                UPDATE cobro_desvios_recuperos
                SET monto = ?, fecha = ?, destino_tipo = ?, destino_detalle = ?, decreto_destino_id = ?, nro_op = ?, notas = ?
                WHERE id = ?
            """, (monto, fecha, destino_tipo, destino_detalle, decreto_destino_id, nro_op, notas, rec_id))
        else:
            cursor.execute("""
                UPDATE cobro_desvios_recuperos
                SET monto = ?, fecha = ?, destino_tipo = ?, destino_detalle = ?, decreto_destino_id = ?, nro_op = ?, notas = ?
                WHERE id = ?
            """, (monto, fecha, destino_tipo, destino_detalle, decreto_destino_id, nro_op, notas, rec_id))


def update_reserva_uso_recupero(rec_id=None, monto=0, fecha=None, destino_tipo=None, destino_detalle=None, decreto_destino_id=None, nro_op=None, notas=None, recupero_id=None):
    """
    Edita un recupero de reserva.
    Si pertenece a un grupo de compensación bilateral, valida el tope adeudado en TODAS las contrapartes
    y propaga simétricamente el cambio a todos los registros hermanos del grupo.
    """
    if rec_id is None and recupero_id is not None:
        rec_id = recupero_id
    if rec_id is None:
        raise ValueError("ID de recupero de reserva no especificado.")
    _validar_op_o_nota_db(nro_op, notas, contexto="recupero de reserva")
    if monto <= 0:
        raise ValueError("El monto recuperado debe ser mayor a 0.")
    with db_session() as conn:
        cursor = conn.cursor()
    
        cursor.execute("SELECT * FROM cobro_reserva_usos_recuperos WHERE id = ?", (rec_id,))
        rec_row = cursor.fetchone()
        if not rec_row:
            raise ValueError("Recupero de reserva no encontrado.")
        reserva_uso_id = rec_row["reserva_uso_id"]
        grupo_id = rec_row["grupo_compensacion_id"]

        if destino_tipo is None:
            destino_tipo = rec_row["destino_tipo"]
        if destino_detalle is None:
            destino_detalle = rec_row["destino_detalle"]
        if decreto_destino_id is None:
            decreto_destino_id = rec_row["decreto_destino_id"]
    
        cursor.execute("SELECT monto FROM cobro_reserva_usos WHERE id = ?", (reserva_uso_id,))
        ru_row = cursor.fetchone()
    
        cursor.execute("SELECT COALESCE(SUM(monto), 0) as tot_recuperado FROM cobro_reserva_usos_recuperos WHERE reserva_uso_id = ? AND id != ?", (reserva_uso_id, rec_id))
        otros_recuperos = cursor.fetchone()["tot_recuperado"]
    
        if (otros_recuperos + monto) > (ru_row["monto"] + TOLERANCE):
            raise ValueError(f"El monto a recuperar editado ({monto:.2f}) supera el saldo adeudado del desvío de reserva ({ru_row['monto'] - otros_recuperos:.2f}).")
        
        if grupo_id:
            # Validación de Tope Bilateral en todas las contrapartes del grupo
            cursor.execute("SELECT * FROM cobro_desvios_recuperos WHERE grupo_compensacion_id = ?", (grupo_id,))
            hermanos_desv = cursor.fetchall()
            for hd in hermanos_desv:
                cursor.execute("SELECT monto FROM cobro_desvios WHERE id = ?", (hd["desvio_id"],))
                hd_row = cursor.fetchone()
                cursor.execute("SELECT COALESCE(SUM(monto), 0) as tot FROM cobro_desvios_recuperos WHERE desvio_id = ? AND id != ?", (hd["desvio_id"], hd["id"]))
                hd_otros = cursor.fetchone()["tot"]
                if (hd_otros + monto) > (hd_row["monto"] + TOLERANCE):
                    raise ValueError(f"El monto editado supera el saldo adeudado del desvío compensado ({hd_row['monto'] - hd_otros:.2f}).")

            cursor.execute("SELECT * FROM cobro_reserva_usos_recuperos WHERE grupo_compensacion_id = ? AND id != ?", (grupo_id, rec_id))
            hermanos_res = cursor.fetchall()
            for hr in hermanos_res:
                cursor.execute("SELECT monto FROM cobro_reserva_usos WHERE id = ?", (hr["reserva_uso_id"],))
                hr_row = cursor.fetchone()
                cursor.execute("SELECT COALESCE(SUM(monto), 0) as tot FROM cobro_reserva_usos_recuperos WHERE reserva_uso_id = ? AND id != ?", (hr["reserva_uso_id"], hr["id"]))
                hr_otros = cursor.fetchone()["tot"]
                if (hr_otros + monto) > (hr_row["monto"] + TOLERANCE):
                    raise ValueError(f"El monto editado supera el saldo adeudado del uso de reserva compensado hermano ({hr_row['monto'] - hr_otros:.2f}).")

            # Si todos los topes bilaterales son válidos, propagar simétricamente
            for hd in hermanos_desv:
                cursor.execute("""
                    UPDATE cobro_desvios_recuperos
                    SET monto = ?, fecha = ?, nro_op = ?, notas = ?
                    WHERE id = ?
                """, (monto, fecha, nro_op, notas, hd["id"]))

            for hr in hermanos_res:
                cursor.execute("""
                    UPDATE cobro_reserva_usos_recuperos
                    SET monto = ?, fecha = ?, nro_op = ?, notas = ?
                    WHERE id = ?
                """, (monto, fecha, nro_op, notas, hr["id"]))

            cursor.execute("""
                UPDATE cobro_reserva_usos_recuperos
                SET monto = ?, fecha = ?, destino_tipo = ?, destino_detalle = ?, decreto_destino_id = ?, nro_op = ?, notas = ?
                WHERE id = ?
            """, (monto, fecha, destino_tipo, destino_detalle, decreto_destino_id, nro_op, notas, rec_id))
        else:
            cursor.execute("""
                UPDATE cobro_reserva_usos_recuperos
                SET monto = ?, fecha = ?, destino_tipo = ?, destino_detalle = ?, decreto_destino_id = ?, nro_op = ?, notas = ?
                WHERE id = ?
            """, (monto, fecha, destino_tipo, destino_detalle, decreto_destino_id, nro_op, notas, rec_id))
