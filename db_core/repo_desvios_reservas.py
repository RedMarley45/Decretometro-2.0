"""
db_core/repo_desvios_reservas.py - Desvíos, Fondos de Reserva, Recuperos Ordinarios y Trazabilidad de Deudas
"""
from db_core.connection import db_session, TOLERANCE, DESTINO_FIN_ORIGINAL, DESTINO_RESERVA, DESTINO_OTRA_OBRA
from db_core.repo_auditoria import register_or_update_op, _validar_op_o_nota_db
from db_core.repo_cobros import _calcular_saldos_cobro_tx
from db_core.repo_obras import get_obra
from db_core.repo_decretos import get_decretos_by_obra
from db_core.repo_catalogos import get_ultima_cotizacion

_DESVIOS_SELECT_INICIAL = """
    SELECT 
        cd.id as desvio_id,
        cd.fecha,
        cd.monto,
        COALESCE((SELECT SUM(monto) FROM cobro_desvios_recuperos WHERE desvio_id = cd.id), 0) as total_recuperado,
        (cd.monto - COALESCE((SELECT SUM(monto) FROM cobro_desvios_recuperos WHERE desvio_id = cd.id), 0)) as saldo,
        cd.destino as destino_texto,
        cd.decreto_destino_id,
        d_dest.nro_decreto as dest_nro, d_dest.anio as dest_anio,
        d_dest.destino_fondos as dest_nombre, d_dest.expediente_imuh as dest_imuh,
        COALESCE(d_orig.id, conv.id) as orig_decreto_id,
        COALESCE(d_orig.nro_decreto, conv.nro_convenio) as orig_nro,
        COALESCE(d_orig.anio, strftime('%Y', conv.fecha_firma)) as orig_anio,
        COALESCE(d_orig.destino_fondos, conv.nombre_convenio) as orig_nombre,
        COALESCE(d_orig.expediente_imuh, conv.nro_expediente) as orig_imuh,
        COALESCE(cu.mes, strftime('%m', csol.fecha_solicitud)) as orig_cuota_mes,
        COALESCE(cu.anio, strftime('%Y', csol.fecha_solicitud)) as orig_cuota_anio,
        'inicial' as tipo_origen,
        cd.nro_op as nro_op,
        cd.motivo as motivo
    FROM cobro_desvios cd
    JOIN cobros c ON cd.cobro_id = c.id
    LEFT JOIN cuotas cu ON c.cuota_id = cu.id
    LEFT JOIN decretos d_orig ON cu.decreto_id = d_orig.id
    LEFT JOIN convenio_solicitudes csol ON c.convenio_solicitud_id = csol.id
    LEFT JOIN convenios conv ON csol.convenio_id = conv.id
    LEFT JOIN decretos d_dest ON cd.decreto_destino_id = d_dest.id
"""

_DESVIOS_SELECT_RESERVA = """
    SELECT 
        ru.id as desvio_id,
        ru.fecha,
        ru.monto,
        COALESCE((SELECT SUM(monto) FROM cobro_reserva_usos_recuperos WHERE reserva_uso_id = ru.id), 0) as total_recuperado,
        (ru.monto - COALESCE((SELECT SUM(monto) FROM cobro_reserva_usos_recuperos WHERE reserva_uso_id = ru.id), 0)) as saldo,
        ru.destino_detalle as destino_texto,
        ru.decreto_destino_id,
        d_dest.nro_decreto as dest_nro, d_dest.anio as dest_anio,
        d_dest.destino_fondos as dest_nombre, d_dest.expediente_imuh as dest_imuh,
        COALESCE(d_orig.id, conv.id) as orig_decreto_id,
        COALESCE(d_orig.nro_decreto, conv.nro_convenio) as orig_nro,
        COALESCE(d_orig.anio, strftime('%Y', conv.fecha_firma)) as orig_anio,
        COALESCE(d_orig.destino_fondos, conv.nombre_convenio) as orig_nombre,
        COALESCE(d_orig.expediente_imuh, conv.nro_expediente) as orig_imuh,
        COALESCE(cu.mes, strftime('%m', csol.fecha_solicitud)) as orig_cuota_mes,
        COALESCE(cu.anio, strftime('%Y', csol.fecha_solicitud)) as orig_cuota_anio,
        'reserva' as tipo_origen,
        ru.nro_op as nro_op,
        ru.notas as motivo
    FROM cobro_reserva_usos ru
    JOIN cobros c ON ru.cobro_id = c.id
    LEFT JOIN cuotas cu ON c.cuota_id = cu.id
    LEFT JOIN decretos d_orig ON cu.decreto_id = d_orig.id
    LEFT JOIN convenio_solicitudes csol ON c.convenio_solicitud_id = csol.id
    LEFT JOIN convenios conv ON csol.convenio_id = conv.id
    LEFT JOIN decretos d_dest ON ru.decreto_destino_id = d_dest.id
    WHERE ru.destino_tipo != 'fin_original'
"""

def add_desvio(cobro_id, destino, monto, motivo, fecha, decreto_destino_id=None, nro_op=None, obra_id=None, gasto_nombre=None, gasto_expediente_imuh=None, cantidad_moneda_amortizada=None, cotizacion_pago=None):
    _validar_op_o_nota_db(nro_op, motivo, contexto="desvío")
    if monto <= 0:
        raise ValueError("El monto a desviar debe ser mayor a 0.")
        
    if obra_id:
        obra = get_obra(obra_id)
        if obra:
            destino = obra['nombre']
            decretos_asoc = get_decretos_by_obra(obra_id)
            decretos_vigentes = [d for d in decretos_asoc if d['estado'] != 'Anulado']
            if decretos_vigentes:
                decreto_destino_id = decretos_vigentes[0]['id']
            elif decretos_asoc:
                decreto_destino_id = decretos_asoc[0]['id']
            else:
                decreto_destino_id = None
                
    with db_session() as conn:
        cursor = conn.cursor()
        saldos = _calcular_saldos_cobro_tx(cursor, cobro_id)
        
        if fecha < saldos['fecha_cobro']:
            raise ValueError(f"La fecha del desvío ({fecha}) no puede ser anterior a la fecha del cobro ({saldos['fecha_cobro']}).")
        
        if monto > (saldos['saldo_sin_distribuir'] + TOLERANCE):
            raise ValueError("El monto del desvío supera el saldo libre disponible sin distribuir.")

        if obra_id:
            cursor.execute("SELECT moneda_id, cotizacion_base_contrato FROM obras WHERE id = ?", (obra_id,))
            obra_row = cursor.fetchone()
            if obra_row and obra_row['moneda_id'] != 1:
                if cotizacion_pago is None or float(cotizacion_pago) <= 1.0:
                    ult_cot = get_ultima_cotizacion(obra_row['moneda_id'])
                    cotizacion_pago = ult_cot if (ult_cot and ult_cot > 1.0) else float(obra_row['cotizacion_base_contrato'] or 1.0)
                if cotizacion_pago <= 1.0:
                    raise ValueError("Debe especificar una cotización de pago mayor a 1.0 para imputar desvíos a una obra bimonetaria.")
                if cantidad_moneda_amortizada is None or float(cantidad_moneda_amortizada) <= 0:
                    cantidad_moneda_amortizada = round(monto / cotizacion_pago, 6)

        cursor.execute('''
            INSERT INTO cobro_desvios (cobro_id, destino, monto, motivo, fecha, decreto_destino_id, nro_op, obra_id, gasto_nombre, gasto_expediente_imuh, cantidad_moneda_amortizada, cotizacion_pago)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (cobro_id, destino, monto, motivo, fecha, decreto_destino_id, nro_op, obra_id, gasto_nombre, gasto_expediente_imuh, cantidad_moneda_amortizada, cotizacion_pago))
        new_id = cursor.lastrowid

        if nro_op:
            g_id = None
            if gasto_expediente_imuh:
                r = cursor.execute("SELECT id FROM gastos_funcionamiento WHERE expediente_imuh = ?", (gasto_expediente_imuh,)).fetchone()
                if r:
                    g_id = r['id']
            register_or_update_op(nro_op, obra_id=obra_id, gasto_id=g_id, conn=conn)

    return new_id


def update_desvio(desvio_id, monto, destino=None, motivo=None, fecha=None, decreto_destino_id=None, nro_op=None, obra_id=None, cantidad_moneda_amortizada=None, cotizacion_pago=None):
    _validar_op_o_nota_db(nro_op, motivo, contexto="desvío")
    if monto <= 0:
        raise ValueError("El monto del desvío debe ser mayor a 0.")
    with db_session() as conn:
        cursor = conn.cursor()
    
        cursor.execute('SELECT * FROM cobro_desvios WHERE id = ?', (desvio_id,))
        row_desv = cursor.fetchone()
        if not row_desv:
            raise ValueError("Desvío no encontrado.")
        cobro_id = row_desv['cobro_id']
    
        cursor.execute('SELECT COALESCE(SUM(monto), 0) as tot_rec FROM cobro_desvios_recuperos WHERE desvio_id = ?', (desvio_id,))
        tot_rec = cursor.fetchone()['tot_rec']
        if monto < (tot_rec - TOLERANCE):
            raise ValueError(f"No se puede reducir el monto del desvío por debajo del total ya recuperado ({tot_rec:.2f}).")
        
        saldos = _calcular_saldos_cobro_tx(cursor, cobro_id, exclude_desvio_id=desvio_id)
        if monto > (saldos['saldo_sin_distribuir'] + TOLERANCE):
            raise ValueError(f"El monto del desvío editado ({monto:.2f}) supera el saldo disponible sin distribuir del cobro ({saldos['saldo_sin_distribuir']:.2f}).")
        
        final_destino = destino if destino is not None else row_desv['destino']
        final_motivo = motivo if motivo is not None else row_desv['motivo']
        final_fecha = fecha if fecha is not None else row_desv['fecha']
        final_dec = decreto_destino_id if decreto_destino_id is not None else row_desv['decreto_destino_id']
        final_op = nro_op if nro_op is not None else row_desv['nro_op']
        final_obra = obra_id if obra_id is not None else row_desv['obra_id']
        desv_dict = dict(row_desv)
        final_cant_amort = cantidad_moneda_amortizada if cantidad_moneda_amortizada is not None else desv_dict.get('cantidad_moneda_amortizada')
        final_cotiz = cotizacion_pago if cotizacion_pago is not None else desv_dict.get('cotizacion_pago')

        if final_obra:
            cursor.execute("SELECT moneda_id, cotizacion_base_contrato FROM obras WHERE id = ?", (final_obra,))
            o_row = cursor.fetchone()
            if o_row and o_row['moneda_id'] != 1:
                if final_cotiz is None or float(final_cotiz) <= 1.0:
                    ult_cot = get_ultima_cotizacion(o_row['moneda_id'])
                    final_cotiz = ult_cot if (ult_cot and ult_cot > 1.0) else float(o_row['cotizacion_base_contrato'] or 1.0)
                if final_cant_amort is None or float(final_cant_amort) <= 0:
                    final_cant_amort = round(monto / final_cotiz, 6) if (final_cotiz and final_cotiz > 0) else 0.0

        cursor.execute('''
            UPDATE cobro_desvios
            SET monto = ?, destino = ?, motivo = ?, fecha = ?, decreto_destino_id = ?, nro_op = ?, obra_id = ?,
                cantidad_moneda_amortizada = ?, cotizacion_pago = ?
            WHERE id = ?
        ''', (monto, final_destino, final_motivo, final_fecha, final_dec, final_op, final_obra, final_cant_amort, final_cotiz, desvio_id))

        if final_op and str(final_op).strip():
            register_or_update_op(str(final_op).strip(), obra_id=final_obra, conn=conn)


def delete_desvio(desvio_id):
    with db_session() as conn:
        cursor = conn.cursor()
        
        cursor.execute('SELECT COUNT(*) as cnt FROM cobro_desvios_recuperos WHERE desvio_id = ?', (desvio_id,))
        if cursor.fetchone()['cnt'] > 0:
            raise ValueError("No se puede borrar un desvío que ya tiene recuperos registrados.")
            
        cursor.execute('DELETE FROM cobro_desvios WHERE id = ?', (desvio_id,))


def get_desvios_by_cobro(cobro_id):
    with db_session() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT cd.*, 
                   COALESCE((SELECT SUM(monto) FROM cobro_desvios_recuperos WHERE desvio_id = cd.id), 0) as total_recuperado
            FROM cobro_desvios cd
            WHERE cd.cobro_id = ?
            ORDER BY cd.fecha ASC
        ''', (cobro_id,))
        rows = cursor.fetchall()
        return [dict(ix) for ix in rows]


def add_reserva_uso(cobro_id, monto, destino_tipo, destino_detalle, fecha, notas, decreto_destino_id=None, nro_op=None, obra_id=None, gasto_nombre=None, gasto_expediente_imuh=None, cantidad_moneda_amortizada=None, cotizacion_pago=None):
    _validar_op_o_nota_db(nro_op, notas, contexto="uso de reserva")
    if monto <= 0:
        raise ValueError("El monto a usar debe ser mayor a 0.")
        
    if obra_id:
        obra = get_obra(obra_id)
        if obra:
            destino_detalle = obra['nombre']
            decretos_asoc = get_decretos_by_obra(obra_id)
            decretos_vigentes = [d for d in decretos_asoc if d['estado'] != 'Anulado']
            if decretos_vigentes:
                decreto_destino_id = decretos_vigentes[0]['id']
            elif decretos_asoc:
                decreto_destino_id = decretos_asoc[0]['id']
            else:
                decreto_destino_id = None
                
    with db_session() as conn:
        cursor = conn.cursor()
        
        cursor.execute('SELECT fecha FROM cobros WHERE id = ?', (cobro_id,))
        c_row = cursor.fetchone()
        if not c_row:
            raise ValueError("Cobro no encontrado.")
        if fecha < c_row['fecha']:
            raise ValueError(f"La fecha de uso de reserva ({fecha}) no puede ser anterior a la fecha del cobro ({c_row['fecha']}).")
    
        cursor.execute('SELECT monto_reserva FROM cobro_distribuciones WHERE cobro_id = ?', (cobro_id,))
        row_dist = cursor.fetchone()
        reserva_original = row_dist['monto_reserva'] if row_dist else 0
    
        cursor.execute('SELECT COALESCE(SUM(monto), 0) as tot FROM cobro_reserva_usos WHERE cobro_id = ?', (cobro_id,))
        ru_total = cursor.fetchone()['tot']
        
        cursor.execute('''
            SELECT COALESCE(SUM(crur.monto), 0) as tot 
            FROM cobro_reserva_usos_recuperos crur
            JOIN cobro_reserva_usos cru ON crur.reserva_uso_id = cru.id
            WHERE cru.cobro_id = ? AND crur.destino_tipo = 'reserva'
        ''', (cobro_id,))
        recru_res_total = cursor.fetchone()['tot']
        
        cursor.execute('''
            SELECT COALESCE(SUM(cdr.monto), 0) as tot 
            FROM cobro_desvios_recuperos cdr
            JOIN cobro_desvios cd ON cdr.desvio_id = cd.id
            WHERE cd.cobro_id = ? AND cdr.destino_tipo = 'reserva'
        ''', (cobro_id,))
        rec_desv_res_total = cursor.fetchone()['tot']
        
        ya_usado_neto = ru_total - recru_res_total - rec_desv_res_total
    
        if (ya_usado_neto + monto) > (reserva_original + TOLERANCE):
            raise ValueError("El monto a usar supera el saldo disponible de reserva.")

        if obra_id:
            cursor.execute("SELECT moneda_id, cotizacion_base_contrato FROM obras WHERE id = ?", (obra_id,))
            obra_row = cursor.fetchone()
            if obra_row and obra_row['moneda_id'] != 1:
                if cotizacion_pago is None or float(cotizacion_pago) <= 1.0:
                    ult_cot = get_ultima_cotizacion(obra_row['moneda_id'])
                    cotizacion_pago = ult_cot if (ult_cot and ult_cot > 1.0) else float(obra_row['cotizacion_base_contrato'] or 1.0)
                if cotizacion_pago <= 1.0:
                    raise ValueError("Debe especificar una cotización de pago mayor a 1.0 para imputar usos de reserva a una obra bimonetaria.")
                if cantidad_moneda_amortizada is None or float(cantidad_moneda_amortizada) <= 0:
                    cantidad_moneda_amortizada = round(monto / cotizacion_pago, 6)

        cursor.execute('''
            INSERT INTO cobro_reserva_usos (cobro_id, monto, destino_tipo, destino_detalle, fecha, notas, decreto_destino_id, nro_op, obra_id, gasto_nombre, gasto_expediente_imuh, cantidad_moneda_amortizada, cotizacion_pago)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (cobro_id, monto, destino_tipo, destino_detalle, fecha, notas, decreto_destino_id, nro_op, obra_id, gasto_nombre, gasto_expediente_imuh, cantidad_moneda_amortizada, cotizacion_pago))
        new_id = cursor.lastrowid

        if nro_op:
            g_id = None
            if gasto_expediente_imuh:
                r = cursor.execute("SELECT id FROM gastos_funcionamiento WHERE expediente_imuh = ?", (gasto_expediente_imuh,)).fetchone()
                if r:
                    g_id = r['id']
            register_or_update_op(nro_op, obra_id=obra_id, gasto_id=g_id, conn=conn)

    return new_id


def update_reserva_uso(uso_id, monto, destino_tipo=None, destino_detalle=None, fecha=None, notas=None, decreto_destino_id=None, nro_op=None, obra_id=None, cantidad_moneda_amortizada=None, cotizacion_pago=None):
    _validar_op_o_nota_db(nro_op, notas, contexto="uso de reserva")
    if monto <= 0:
        raise ValueError("El monto debe ser mayor a 0.")
    with db_session() as conn:
        cursor = conn.cursor()
    
        cursor.execute('SELECT * FROM cobro_reserva_usos WHERE id = ?', (uso_id,))
        uso_row = cursor.fetchone()
        if not uso_row:
            raise ValueError("Uso de reserva no encontrado.")
        cobro_id = uso_row['cobro_id']
    
        cursor.execute('SELECT COALESCE(SUM(monto), 0) as tot_rec FROM cobro_reserva_usos_recuperos WHERE reserva_uso_id = ?', (uso_id,))
        tot_rec = cursor.fetchone()['tot_rec']
        if monto < (tot_rec - TOLERANCE):
            raise ValueError(f"No se puede reducir el monto del uso de reserva por debajo del total ya recuperado ({tot_rec:.2f}).")
        
        cursor.execute('SELECT monto_reserva FROM cobro_distribuciones WHERE cobro_id = ?', (cobro_id,))
        row_dist = cursor.fetchone()
        reserva_original = row_dist['monto_reserva'] if row_dist else 0.0
    
        cursor.execute('SELECT COALESCE(SUM(monto), 0) as tot_usado FROM cobro_reserva_usos WHERE cobro_id = ? AND id != ?', (cobro_id, uso_id))
        otros_usos = cursor.fetchone()['tot_usado']

        cursor.execute('''
            SELECT COALESCE(SUM(crur.monto), 0) as tot 
            FROM cobro_reserva_usos_recuperos crur
            JOIN cobro_reserva_usos cru ON crur.reserva_uso_id = cru.id
            WHERE cru.cobro_id = ? AND crur.destino_tipo = 'reserva'
        ''', (cobro_id,))
        recru_res_total = cursor.fetchone()['tot']
        
        cursor.execute('''
            SELECT COALESCE(SUM(cdr.monto), 0) as tot 
            FROM cobro_desvios_recuperos cdr
            JOIN cobro_desvios cd ON cdr.desvio_id = cd.id
            WHERE cd.cobro_id = ? AND cdr.destino_tipo = 'reserva'
        ''', (cobro_id,))
        rec_desv_res_total = cursor.fetchone()['tot']
        
        disponible_para_este_uso = reserva_original - otros_usos + recru_res_total + rec_desv_res_total
    
        if monto > (disponible_para_este_uso + TOLERANCE):
            raise ValueError(f"El monto a usar editado ({monto:.2f}) supera el saldo disponible de reserva ({disponible_para_este_uso:.2f}).")
        
        final_tipo = destino_tipo if destino_tipo is not None else uso_row['destino_tipo']
        final_det = destino_detalle if destino_detalle is not None else uso_row['destino_detalle']
        final_fecha = fecha if fecha is not None else uso_row['fecha']
        final_notas = notas if notas is not None else uso_row['notas']
        final_dec = decreto_destino_id if decreto_destino_id is not None else uso_row['decreto_destino_id']
        final_op = nro_op if nro_op is not None else uso_row['nro_op']
        final_obra = obra_id if obra_id is not None else uso_row['obra_id']
        uso_dict = dict(uso_row)
        final_cant_amort = cantidad_moneda_amortizada if cantidad_moneda_amortizada is not None else uso_dict.get('cantidad_moneda_amortizada')
        final_cotiz = cotizacion_pago if cotizacion_pago is not None else uso_dict.get('cotizacion_pago')

        if final_obra:
            cursor.execute("SELECT moneda_id, cotizacion_base_contrato FROM obras WHERE id = ?", (final_obra,))
            o_row = cursor.fetchone()
            if o_row and o_row['moneda_id'] != 1:
                if final_cotiz is None or float(final_cotiz) <= 1.0:
                    ult_cot = get_ultima_cotizacion(o_row['moneda_id'])
                    final_cotiz = ult_cot if (ult_cot and ult_cot > 1.0) else float(o_row['cotizacion_base_contrato'] or 1.0)
                if final_cant_amort is None or float(final_cant_amort) <= 0:
                    final_cant_amort = round(monto / final_cotiz, 6) if (final_cotiz and final_cotiz > 0) else 0.0

        cursor.execute('''
            UPDATE cobro_reserva_usos
            SET monto = ?, destino_tipo = ?, destino_detalle = ?, fecha = ?, notas = ?, decreto_destino_id = ?, nro_op = ?, obra_id = ?,
                cantidad_moneda_amortizada = ?, cotizacion_pago = ?
            WHERE id = ?
        ''', (monto, final_tipo, final_det, final_fecha, final_notas, final_dec, final_op, final_obra, final_cant_amort, final_cotiz, uso_id))

        if final_op and str(final_op).strip():
            register_or_update_op(str(final_op).strip(), obra_id=final_obra, conn=conn)


def delete_reserva_uso(uso_id):
    with db_session() as conn:
        cursor = conn.cursor()
        
        cursor.execute('SELECT COUNT(*) as cnt FROM cobro_reserva_usos_recuperos WHERE reserva_uso_id = ?', (uso_id,))
        if cursor.fetchone()['cnt'] > 0:
            raise ValueError("No se puede borrar un uso de reserva que ya tiene recuperos registrados.")
            
        cursor.execute('DELETE FROM cobro_reserva_usos WHERE id = ?', (uso_id,))


def get_reserva_usos_by_cobro(cobro_id):
    with db_session() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM cobro_reserva_usos WHERE cobro_id = ? ORDER BY fecha ASC', (cobro_id,))
        rows = cursor.fetchall()
        return [dict(ix) for ix in rows]


def get_saldo_reserva_cobro(cobro_id):
    """Calcula el saldo neto disponible de reserva para un cobro individual:
    Reserva inicial - Usos totales + Recuperos de préstamos a reserva + Recuperos de desvíos a reserva.
    """
    with db_session() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT 
                MAX(0.0, ROUND(
                    COALESCE(dist.monto_reserva, 0) -
                    COALESCE((SELECT SUM(monto) FROM cobro_reserva_usos WHERE cobro_id = c.id), 0) +
                    COALESCE((
                        SELECT SUM(crur.monto) FROM cobro_reserva_usos_recuperos crur
                        JOIN cobro_reserva_usos cru ON crur.reserva_uso_id = cru.id
                        WHERE cru.cobro_id = c.id AND crur.destino_tipo = 'reserva'
                    ), 0) +
                    COALESCE((
                        SELECT SUM(cdr.monto) FROM cobro_desvios_recuperos cdr
                        JOIN cobro_desvios cd ON cdr.desvio_id = cd.id
                        WHERE cd.cobro_id = c.id AND cdr.destino_tipo = 'reserva'
                    ), 0), 2)
                ) as saldo_disponible
            FROM cobros c
            LEFT JOIN cobro_distribuciones dist ON c.id = dist.cobro_id
            WHERE c.id = ?
        ''', (cobro_id,))
        row = cursor.fetchone()
        return row['saldo_disponible'] if row else 0.0


def get_reserva_usos_prestamos_activos():
    """Retorna usos de reserva destinados a otras obras (préstamos a recuperar) con su saldo pendiente.
    No incluye los usos aplicados al fin original del cobro."""
    with db_session() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT
                ru.id,
                ru.cobro_id,
                ru.monto,
                (ru.monto - COALESCE((SELECT SUM(monto) FROM cobro_reserva_usos_recuperos WHERE reserva_uso_id = ru.id), 0)) as saldo,
                ru.fecha,
                ru.destino_tipo,
                ru.destino_detalle,
                ru.decreto_destino_id,
                ru.notas,
                ru.gasto_nombre,
                ru.gasto_expediente_imuh,
                COALESCE(d_orig.nro_decreto, cv_orig.nro_convenio) as orig_nro,
                COALESCE(d_orig.anio, strftime('%Y', cv_orig.fecha_firma)) as orig_anio,
                COALESCE(d_orig.destino_fondos, cv_orig.nombre_convenio || ' — ' || o_orig.nombre) as orig_nombre, 
                COALESCE(d_orig.expediente_imuh, o_orig.expediente_imuh) as orig_imuh,
                d_dest.nro_decreto as dest_nro,
                d_dest.anio      as dest_anio,
                d_dest.destino_fondos as dest_nombre, d_dest.expediente_imuh as dest_imuh,
                o_dest.expediente_imuh as dest_obra_imuh
            FROM cobro_reserva_usos ru
            JOIN cobros c    ON ru.cobro_id = c.id
            LEFT JOIN cuotas cu   ON c.cuota_id  = cu.id
            LEFT JOIN decretos d_orig ON cu.decreto_id = d_orig.id
            LEFT JOIN convenio_solicitudes cs ON c.convenio_solicitud_id = cs.id
            LEFT JOIN convenios cv_orig ON cs.convenio_id = cv_orig.id
            LEFT JOIN obras o_orig ON (c.obra_id = o_orig.id OR cs.obra_id = o_orig.id)
            LEFT JOIN decretos d_dest ON ru.decreto_destino_id = d_dest.id
            LEFT JOIN obras o_dest ON ru.obra_id = o_dest.id
            WHERE ru.destino_tipo != 'fin_original'
            ORDER BY ru.fecha DESC
        ''')
        rows = cursor.fetchall()
    
        activos = []
        for r in rows:
            if r['saldo'] > TOLERANCE:
                activos.append(dict(r))
        return activos


def add_desvio_recupero(desvio_id, monto, fecha, destino_tipo, destino_detalle=None, decreto_destino_id=None, nro_op=None, notas=None):
    _validar_op_o_nota_db(nro_op, notas, contexto="recupero de desvío")
    if monto <= 0:
        raise ValueError("El monto recuperado debe ser mayor a 0.")
        
    with db_session() as conn:
        cursor = conn.cursor()
    
        cursor.execute('SELECT monto, fecha FROM cobro_desvios WHERE id = ?', (desvio_id,))
        d_row = cursor.fetchone()
        if not d_row:
            raise ValueError("Desvío no encontrado.")
            
        if fecha < d_row['fecha']:
            raise ValueError(f"La fecha de recuperación ({fecha}) no puede ser anterior a la fecha del desvío ({d_row['fecha']}).")
        
        cursor.execute('SELECT COALESCE(SUM(monto), 0) as tot_recuperado FROM cobro_desvios_recuperos WHERE desvio_id = ?', (desvio_id,))
        tot_recuperado = cursor.fetchone()['tot_recuperado']
    
        if (tot_recuperado + monto) > (d_row['monto'] + TOLERANCE):
            raise ValueError("El monto a recuperar supera el saldo adeudado del desvío.")

        cursor.execute('''
            INSERT INTO cobro_desvios_recuperos (desvio_id, monto, fecha, destino_tipo, destino_detalle, decreto_destino_id, nro_op, notas)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (desvio_id, monto, fecha, destino_tipo, destino_detalle, decreto_destino_id, nro_op, notas))


def add_reserva_uso_recupero(reserva_uso_id, monto, fecha, destino_tipo, destino_detalle=None, decreto_destino_id=None, nro_op=None, notas=None):
    _validar_op_o_nota_db(nro_op, notas, contexto="recupero de reserva")
    if monto <= 0:
        raise ValueError("El monto recuperado debe ser mayor a 0.")
        
    with db_session() as conn:
        cursor = conn.cursor()
        
        cursor.execute('SELECT monto, fecha FROM cobro_reserva_usos WHERE id = ?', (reserva_uso_id,))
        ru_row = cursor.fetchone()
        if not ru_row:
            raise ValueError("Uso de reserva no encontrado.")
        if fecha < ru_row['fecha']:
            raise ValueError(f"La fecha de recuperación ({fecha}) no puede ser anterior a la fecha de uso de reserva ({ru_row['fecha']}).")
        
        cursor.execute('SELECT COALESCE(SUM(monto), 0) as tot_recuperado FROM cobro_reserva_usos_recuperos WHERE reserva_uso_id = ?', (reserva_uso_id,))
        tot_recuperado = cursor.fetchone()['tot_recuperado']
    
        if (tot_recuperado + monto) > (ru_row['monto'] + TOLERANCE):
            raise ValueError("El monto a recuperar supera el saldo adeudado del desvío de reserva.")

        cursor.execute('''
            INSERT INTO cobro_reserva_usos_recuperos (reserva_uso_id, monto, fecha, destino_tipo, destino_detalle, decreto_destino_id, nro_op, notas)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (reserva_uso_id, monto, fecha, destino_tipo, destino_detalle, decreto_destino_id, nro_op, notas))


def get_recuperos_by_desvio(desvio_id):
    with db_session() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT r.*,
                   d.nro_decreto as dest_nro, d.anio as dest_anio, d.destino_fondos as dest_nombre
            FROM cobro_desvios_recuperos r
            LEFT JOIN decretos d ON r.decreto_destino_id = d.id
            WHERE r.desvio_id = ? 
            ORDER BY r.fecha ASC
        ''', (desvio_id,))
        rows = cursor.fetchall()
        return [dict(ix) for ix in rows]


def get_recuperos_by_reserva_uso(reserva_uso_id):
    with db_session() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT r.*,
                   d.nro_decreto as dest_nro, d.anio as dest_anio, d.destino_fondos as dest_nombre
            FROM cobro_reserva_usos_recuperos r
            LEFT JOIN decretos d ON r.decreto_destino_id = d.id
            WHERE r.reserva_uso_id = ? 
            ORDER BY r.fecha ASC
        ''', (reserva_uso_id,))
        rows = cursor.fetchall()
        return [dict(ix) for ix in rows]


def get_recuperos_by_prestamo(prestamo_id):
    with db_session() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM recuperos_internos WHERE prestamo_id = ? ORDER BY fecha ASC', (prestamo_id,))
        rows = cursor.fetchall()
        return [dict(ix) for ix in rows]


def add_recupero_fondos_propios(cobro_id, obra_id, monto, fecha, nro_op, notas):
    _validar_op_o_nota_db(nro_op, notas, "recupero de fondos propios")
    if monto <= 0:
        raise ValueError("El monto a recuperar debe ser mayor a 0.")
    
    with db_session() as conn:
        cursor = conn.cursor()
        saldos = _calcular_saldos_cobro_tx(cursor, cobro_id)
        
        if fecha < saldos['fecha_cobro']:
            raise ValueError(f"La fecha del recupero ({fecha}) no puede ser anterior a la fecha del cobro ({saldos['fecha_cobro']}).")

        if monto > (saldos['saldo_sin_distribuir'] + TOLERANCE):
            raise ValueError(f"El monto a recuperar excede el saldo libre disponible sin distribuir del cobro (${saldos['saldo_sin_distribuir']:,.2f}).")

        # Validar que no supere el tope dentro de la misma transacción
        pagos_fp = sum(row['monto'] for row in conn.execute("SELECT monto FROM pagos_fondos_propios WHERE obra_id = ?", (obra_id,)).fetchall())
        recuperos = sum(row['monto'] for row in conn.execute("SELECT monto FROM recuperos_fondos_propios WHERE obra_id = ?", (obra_id,)).fetchall())
        tope = max(0.0, pagos_fp - recuperos)
        
        if monto > tope + TOLERANCE:
            raise ValueError(f"El monto a recuperar excede el total adeudado a Fondos Propios para esta obra (${tope:,.2f}).")
            
        cursor.execute('''
            INSERT INTO recuperos_fondos_propios (cobro_id, obra_id, monto, fecha, nro_op, notas)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (cobro_id, obra_id, monto, fecha, nro_op, notas))


def delete_recupero_fondos_propios(recupero_id):
    with db_session() as conn:
        conn.execute("DELETE FROM recuperos_fondos_propios WHERE id = ?", (recupero_id,))


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


def get_deuda_desvios_by_decreto(decreto_id):
    with db_session() as conn:
        cursor = conn.cursor()
    
        # 1. Deuda de desvíos iniciales recibidos
        cursor.execute('''
            SELECT 
                COALESCE(SUM(cd.monto), 0) - COALESCE((
                    SELECT SUM(cdr.monto) 
                    FROM cobro_desvios_recuperos cdr 
                    JOIN cobro_desvios cd_inner ON cdr.desvio_id = cd_inner.id 
                    WHERE cd_inner.decreto_destino_id = ?
                ), 0) as deuda
            FROM cobro_desvios cd
            WHERE cd.decreto_destino_id = ?
        ''', (decreto_id, decreto_id))
        r_desv = cursor.fetchone()
        deuda_desv = r_desv['deuda'] if r_desv and r_desv['deuda'] is not None else 0.0
    
        # 2. Deuda de desvíos de reserva recibidos
        cursor.execute('''
            SELECT 
                COALESCE(SUM(ru.monto), 0) - COALESCE((
                    SELECT SUM(rur.monto) 
                    FROM cobro_reserva_usos_recuperos rur 
                    JOIN cobro_reserva_usos ru_inner ON rur.reserva_uso_id = ru_inner.id 
                    WHERE ru_inner.decreto_destino_id = ?
                ), 0) as deuda
            FROM cobro_reserva_usos ru
            WHERE ru.decreto_destino_id = ? AND ru.destino_tipo != 'fin_original'
        ''', (decreto_id, decreto_id))
        r_res = cursor.fetchone()
        deuda_res = r_res['deuda'] if r_res and r_res['deuda'] is not None else 0.0
    
        return round(deuda_desv + deuda_res, 2)


def get_deudas_obras_propias():
    return get_deudas_consolidadas()


def get_deudas_consolidadas():
    with db_session() as conn:
        cursor = conn.cursor()
        
        # 1. Obtener deudas de OBRAS
        cursor.execute('''
            SELECT 
                o.id as obra_id,
                o.nombre,
                o.expediente_imuh,
                o.activa,
                -- Suma de desvíos directos
                COALESCE((SELECT SUM(monto) FROM cobro_desvios WHERE obra_id = o.id), 0) as desvios,
                -- Suma de recuperos de desvíos directos
                COALESCE((SELECT SUM(r.monto) FROM cobro_desvios_recuperos r JOIN cobro_desvios d ON r.desvio_id = d.id WHERE d.obra_id = o.id), 0) as desvios_rec,
                -- Suma de usos de reserva
                COALESCE((SELECT SUM(monto) FROM cobro_reserva_usos WHERE obra_id = o.id), 0) as reserva,
                -- Suma de recuperos de reserva
                COALESCE((SELECT SUM(r.monto) FROM cobro_reserva_usos_recuperos r JOIN cobro_reserva_usos u ON r.reserva_uso_id = u.id WHERE u.obra_id = o.id), 0) as reserva_rec
            FROM obras o
        ''')
        rows_obras = cursor.fetchall()
        
        # 2. Obtener deudas de GASTOS DE FUNCIONAMIENTO (FUN)
        cursor.execute('''
            SELECT 
                gasto_nombre as nombre,
                gasto_expediente_imuh as expediente_imuh,
                SUM(monto) as desvios,
                COALESCE((SELECT SUM(r.monto) FROM cobro_desvios_recuperos r JOIN cobro_desvios d ON r.desvio_id = d.id WHERE d.gasto_expediente_imuh = cd.gasto_expediente_imuh AND d.gasto_nombre = cd.gasto_nombre), 0) as desvios_rec
            FROM cobro_desvios cd
            WHERE cd.gasto_nombre IS NOT NULL AND cd.gasto_nombre != ''
            GROUP BY gasto_expediente_imuh, gasto_nombre
        ''')
        rows_fun_desv = cursor.fetchall()

        cursor.execute('''
            SELECT 
                gasto_nombre as nombre,
                gasto_expediente_imuh as expediente_imuh,
                SUM(monto) as reserva,
                COALESCE((SELECT SUM(r.monto) FROM cobro_reserva_usos_recuperos r JOIN cobro_reserva_usos u ON r.reserva_uso_id = u.id WHERE u.gasto_expediente_imuh = cru.gasto_expediente_imuh AND u.gasto_nombre = cru.gasto_nombre), 0) as reserva_rec
            FROM cobro_reserva_usos cru
            WHERE cru.gasto_nombre IS NOT NULL AND cru.gasto_nombre != ''
            GROUP BY gasto_expediente_imuh, gasto_nombre
        ''')
        rows_fun_res = cursor.fetchall()

        deudas = []
        
        # Procesar Obras
        for o in rows_obras:
            saldo = round((o['desvios'] - o['desvios_rec']) + (o['reserva'] - o['reserva_rec']), 2)
            if saldo <= TOLERANCE:
                continue
            if o['activa'] == 0:
                continue # Pérdida/olvidado, no se lista
                
            # Determinar tipo y decreto asociado
            cursor.execute('''
                SELECT d.id, d.nro_decreto, d.anio, d.estado
                FROM decretos d
                JOIN decretos_obras do ON do.decreto_id = d.id
                WHERE do.obra_id = ?
            ''', (o['obra_id'],))
            decretos_asoc = cursor.fetchall()
            
            tipo = "Obra con Fondos Propios"
            dec_str = "Fondos Propios"
            
            if decretos_asoc:
                vigentes = [d for d in decretos_asoc if d['estado'] != 'Anulado']
                if vigentes:
                    tipo = "Obra con Decreto"
                    dec_str = ", ".join(f"Dto. {d['nro_decreto']}/{d['anio']}" for d in vigentes)
                else:
                    tipo = "Obra con Decreto (ANULADO)"
                    dec_str = ", ".join(f"Dto. {d['nro_decreto']}/{d['anio']} (ANULADO)" for d in decretos_asoc)
            
            deudas.append({
                'destino': o['nombre'],
                'tipo': tipo,
                'expediente_imuh': o['expediente_imuh'],
                'decreto_asociado': dec_str,
                'saldo': saldo
            })
            
        # Procesar FUN
        fun_dict = {}
        for r in rows_fun_desv:
            k = (r['nombre'], r['expediente_imuh'])
            fun_dict[k] = fun_dict.get(k, 0.0) + (r['desvios'] - r['desvios_rec'])
            
        for r in rows_fun_res:
            k = (r['nombre'], r['expediente_imuh'])
            fun_dict[k] = fun_dict.get(k, 0.0) + (r['reserva'] - r['reserva_rec'])
            
        for (nombre, exp_imuh), saldo in fun_dict.items():
            saldo = round(saldo, 2)
            if saldo > TOLERANCE:
                deudas.append({
                    'destino': nombre,
                    'tipo': "Gasto de Funcionamiento",
                    'expediente_imuh': exp_imuh,
                    'decreto_asociado': "Gasto Corriente",
                    'saldo': saldo
                })
                
        deudas.sort(key=lambda x: x['destino'])
        return deudas


def get_obras_propias_nombres():
    with db_session() as conn:
        cursor = conn.cursor()
    
        cursor.execute('SELECT DISTINCT destino FROM cobro_desvios WHERE decreto_destino_id IS NULL AND destino IS NOT NULL AND TRIM(destino) != ""')
        n_desv = [row['destino'] for row in cursor.fetchall()]
    
        cursor.execute('SELECT DISTINCT destino_detalle FROM cobro_reserva_usos WHERE decreto_destino_id IS NULL AND destino_detalle IS NOT NULL AND TRIM(destino_detalle) != "" AND destino_tipo != "fin_original"')
        n_res = [row['destino_detalle'] for row in cursor.fetchall()]
    
        cursor.execute('SELECT DISTINCT destino_detalle FROM cobro_desvios_recuperos WHERE decreto_destino_id IS NULL AND destino_detalle IS NOT NULL AND TRIM(destino_detalle) != "" AND destino_tipo != "fin_original"')
        n_rec = [row['destino_detalle'] for row in cursor.fetchall()]
    
        cursor.execute('SELECT DISTINCT destino_detalle FROM cobro_reserva_usos_recuperos WHERE decreto_destino_id IS NULL AND destino_detalle IS NOT NULL AND TRIM(destino_detalle) != "" AND destino_tipo != "fin_original" AND destino_tipo != "reserva"')
        n_rec_res = [row['destino_detalle'] for row in cursor.fetchall()]
    
    
        return sorted(list(set(n_desv + n_res + n_rec + n_rec_res)))


def get_desvios_activos_completos():
    with db_session() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT 
                cd.id as desvio_id,
                (cd.monto - COALESCE((SELECT SUM(monto) FROM cobro_desvios_recuperos WHERE desvio_id = cd.id), 0)) as saldo,
                cd.destino as destino_texto,
                cd.decreto_destino_id,
                cd.gasto_nombre,
                cd.gasto_expediente_imuh,
                d_dest.nro_decreto as dest_nro, d_dest.anio as dest_anio, d_dest.destino_fondos as dest_nombre, d_dest.expediente_imuh as dest_imuh,
                COALESCE(d_orig.nro_decreto, conv.nro_convenio) as orig_nro,
                COALESCE(d_orig.anio, strftime('%Y', conv.fecha_firma)) as orig_anio,
                COALESCE(d_orig.destino_fondos, conv.nombre_convenio) as orig_nombre,
                COALESCE(d_orig.expediente_imuh, conv.nro_expediente) as orig_imuh,
                o_dest.expediente_imuh as dest_obra_imuh
            FROM cobro_desvios cd
            JOIN cobros c ON cd.cobro_id = c.id
            LEFT JOIN cuotas cu ON c.cuota_id = cu.id
            LEFT JOIN decretos d_orig ON cu.decreto_id = d_orig.id
            LEFT JOIN convenio_solicitudes csol ON c.convenio_solicitud_id = csol.id
            LEFT JOIN convenios conv ON csol.convenio_id = conv.id
            LEFT JOIN decretos d_dest ON cd.decreto_destino_id = d_dest.id
            LEFT JOIN obras o_dest ON cd.obra_id = o_dest.id
        ''')
        rows = cursor.fetchall()
    
        activos = []
        for r in rows:
            if r['saldo'] > TOLERANCE:
                activos.append(dict(r))
        return activos


def get_historial_desvios():
    with db_session() as conn:
        cursor = conn.cursor()
    
        # 1. Desvíos iniciales
        cursor.execute('''
            SELECT 
                cd.id as desvio_id,
                cd.fecha,
                cd.monto,
                COALESCE((SELECT SUM(monto) FROM cobro_desvios_recuperos WHERE desvio_id = cd.id), 0) as total_recuperado,
                (cd.monto - COALESCE((SELECT SUM(monto) FROM cobro_desvios_recuperos WHERE desvio_id = cd.id), 0)) as saldo,
                cd.destino as destino_texto,
                cd.decreto_destino_id,
                d_dest.nro_decreto as dest_nro, d_dest.anio as dest_anio, d_dest.destino_fondos as dest_nombre, d_dest.expediente_imuh as dest_imuh,
                COALESCE(d_orig.id, conv.id) as orig_decreto_id,
                COALESCE(d_orig.nro_decreto, conv.nro_convenio) as orig_nro,
                COALESCE(d_orig.anio, strftime('%Y', conv.fecha_firma)) as orig_anio,
                COALESCE(d_orig.destino_fondos, conv.nombre_convenio) as orig_nombre,
                COALESCE(d_orig.expediente_imuh, conv.nro_expediente) as orig_imuh,
                COALESCE(cu.mes, strftime('%m', csol.fecha_solicitud)) as orig_cuota_mes,
                COALESCE(cu.anio, strftime('%Y', csol.fecha_solicitud)) as orig_cuota_anio,
                'inicial' as tipo_origen,
                cd.nro_op as nro_op,
                cd.motivo as motivo
            FROM cobro_desvios cd
            JOIN cobros c ON cd.cobro_id = c.id
            LEFT JOIN cuotas cu ON c.cuota_id = cu.id
            LEFT JOIN decretos d_orig ON cu.decreto_id = d_orig.id
            LEFT JOIN convenio_solicitudes csol ON c.convenio_solicitud_id = csol.id
            LEFT JOIN convenios conv ON csol.convenio_id = conv.id
            LEFT JOIN decretos d_dest ON cd.decreto_destino_id = d_dest.id
        ''')
        rows_desv = [dict(r) for r in cursor.fetchall()]
    
        # 2. Desvíos de reserva
        cursor.execute('''
            SELECT 
                ru.id as desvio_id,
                ru.fecha,
                ru.monto,
                COALESCE((SELECT SUM(monto) FROM cobro_reserva_usos_recuperos WHERE reserva_uso_id = ru.id), 0) as total_recuperado,
                (ru.monto - COALESCE((SELECT SUM(monto) FROM cobro_reserva_usos_recuperos WHERE reserva_uso_id = ru.id), 0)) as saldo,
                ru.destino_detalle as destino_texto,
                ru.decreto_destino_id,
                d_dest.nro_decreto as dest_nro, d_dest.anio as dest_anio, d_dest.destino_fondos as dest_nombre, d_dest.expediente_imuh as dest_imuh,
                COALESCE(d_orig.id, conv.id) as orig_decreto_id,
                COALESCE(d_orig.nro_decreto, conv.nro_convenio) as orig_nro,
                COALESCE(d_orig.anio, strftime('%Y', conv.fecha_firma)) as orig_anio,
                COALESCE(d_orig.destino_fondos, conv.nombre_convenio) as orig_nombre,
                COALESCE(d_orig.expediente_imuh, conv.nro_expediente) as orig_imuh,
                COALESCE(cu.mes, strftime('%m', csol.fecha_solicitud)) as orig_cuota_mes,
                COALESCE(cu.anio, strftime('%Y', csol.fecha_solicitud)) as orig_cuota_anio,
                'reserva' as tipo_origen,
                ru.nro_op as nro_op,
                ru.notas as motivo
            FROM cobro_reserva_usos ru
            JOIN cobros c ON ru.cobro_id = c.id
            LEFT JOIN cuotas cu ON c.cuota_id = cu.id
            LEFT JOIN decretos d_orig ON cu.decreto_id = d_orig.id
            LEFT JOIN convenio_solicitudes csol ON c.convenio_solicitud_id = csol.id
            LEFT JOIN convenios conv ON csol.convenio_id = conv.id
            LEFT JOIN decretos d_dest ON ru.decreto_destino_id = d_dest.id
            WHERE ru.destino_tipo != 'fin_original'
        ''')
        rows_res = [dict(r) for r in cursor.fetchall()]
    
        # Combinar y ordenar
        todos = rows_desv + rows_res
        todos.sort(key=lambda x: x['fecha'], reverse=True)
        return todos


def get_desvios_por_deudora(decreto_id=None, nombre_texto=None):
    """Retorna desvíos activos para una obra DEUDORA (quien recibió fondos).
    Filtra a nivel SQL por decreto_destino_id o por nombre de destino para legados.
    Solo retorna registros con saldo > 0 (Fix 10).
    """
    with db_session() as conn:
        cursor = conn.cursor()

        if decreto_id is not None:
            # Filtro por decreto registrado
            sql_ini = _DESVIOS_SELECT_INICIAL + " WHERE cd.decreto_destino_id = ?"
            cursor.execute(sql_ini, (decreto_id,))
            rows_d = [dict(r) for r in cursor.fetchall()]

            sql_res = _DESVIOS_SELECT_RESERVA + " AND ru.decreto_destino_id = ?"
            cursor.execute(sql_res, (decreto_id,))
            rows_r = [dict(r) for r in cursor.fetchall()]
        else:
            # Filtro por nombre de destino (obras sin decreto registrado)
            sql_ini = _DESVIOS_SELECT_INICIAL + " WHERE cd.decreto_destino_id IS NULL AND cd.destino = ?"
            cursor.execute(sql_ini, (nombre_texto,))
            rows_d = [dict(r) for r in cursor.fetchall()]

            sql_res = _DESVIOS_SELECT_RESERVA + " AND ru.decreto_destino_id IS NULL AND ru.destino_detalle = ?"
            cursor.execute(sql_res, (nombre_texto,))
            rows_r = [dict(r) for r in cursor.fetchall()]

        todos = rows_d + rows_r
        todos.sort(key=lambda x: x['fecha'], reverse=True)
        return [r for r in todos if r['saldo'] > TOLERANCE]


def get_desvios_por_acreedora(decreto_id):
    """Retorna desvíos activos para una obra ACREEDORA (quien prestó fondos).
    Filtra a nivel SQL por d_orig.id (decreto de origen del cobro).
    Solo retorna registros con saldo > 0 (Fix 10).
    """
    with db_session() as conn:
        cursor = conn.cursor()

        sql_ini = _DESVIOS_SELECT_INICIAL + " WHERE d_orig.id = ?"
        cursor.execute(sql_ini, (decreto_id,))
        rows_d = [dict(r) for r in cursor.fetchall()]

        sql_res = _DESVIOS_SELECT_RESERVA + " AND d_orig.id = ?"
        cursor.execute(sql_res, (decreto_id,))
        rows_r = [dict(r) for r in cursor.fetchall()]

        todos = rows_d + rows_r
        todos.sort(key=lambda x: x['fecha'], reverse=True)
        return [r for r in todos if r['saldo'] > TOLERANCE]


def get_todas_obras_para_trazabilidad():
    """Retorna todas las entidades conocidas como destino de desvíos.
    Incluye:
      - Obras del catálogo formal (tabla obras).
      - Destinos legacy: entradas de cobro_desvios y cobro_reserva_usos sin
        decreto_destino_id ni obra_id (texto libre), con saldo > 0.
    Retorna lista de dicts con keys: id, nombre, expediente_imuh, tipo
      tipo: 'catalogo' | 'legacy'
    """
    with db_session() as conn:
        cursor = conn.cursor()

        # 1. Obras del catálogo
        cursor.execute('SELECT id, nombre, expediente_imuh FROM obras ORDER BY nombre ASC')
        obras_cat = [{'id': r['id'], 'nombre': r['nombre'],
                      'expediente_imuh': r['expediente_imuh'], 'tipo': 'catalogo'}
                     for r in cursor.fetchall()]

        # 2. Destinos legacy en cobro_desvios (sin obra_id ni decreto_destino_id, saldo > 0)
        cursor.execute(f'''
            SELECT DISTINCT cd.destino as nombre
            FROM cobro_desvios cd
            WHERE cd.obra_id IS NULL
              AND cd.decreto_destino_id IS NULL
              AND (cd.monto - COALESCE(
                      (SELECT SUM(monto) FROM cobro_desvios_recuperos WHERE desvio_id = cd.id), 0
                  )) > {TOLERANCE}
        ''')
        legacy_nombres_desv = {r['nombre'] for r in cursor.fetchall() if r['nombre']}

        # 3. Destinos legacy en cobro_reserva_usos
        cursor.execute(f'''
            SELECT DISTINCT ru.destino_detalle as nombre
            FROM cobro_reserva_usos ru
            WHERE ru.obra_id IS NULL
              AND ru.decreto_destino_id IS NULL
              AND ru.destino_tipo != 'fin_original'
              AND (ru.monto - COALESCE(
                      (SELECT SUM(monto) FROM cobro_reserva_usos_recuperos WHERE reserva_uso_id = ru.id), 0
                  )) > {TOLERANCE}
        ''')
        legacy_nombres_res = {r['nombre'] for r in cursor.fetchall() if r['nombre']}

        legacy_todos = legacy_nombres_desv | legacy_nombres_res
        obras_legacy = [{'id': None, 'nombre': n, 'expediente_imuh': None, 'tipo': 'legacy'}
                        for n in sorted(legacy_todos)]

        return obras_cat + obras_legacy


def get_trazabilidad_fuentes_por_obra(obra_id=None, obra_nombre_legacy=None):
    """Retorna todos los cobros que financiaron directa o indirectamente a una obra.
    Para obras del catálogo, usar obra_id (int).
    Para obras legacy (sin ID), usar obra_nombre_legacy (str).
    Retorna lista de dicts con:
      decreto_id, nro_decreto, decreto_anio, destino_fondos, decreto_expediente_imuh,
      cobro_id, cobro_fecha, cobro_monto, tipo_financiamiento, monto_financiado, saldo_pendiente, nro_op
    tipo_financiamiento: 'Fin Original' | 'Desvío' | 'Uso de Reserva'
    """
    with db_session() as conn:
        cursor = conn.cursor()
        filas = []

        if obra_id is not None:
            # --- Desvíos directos (cobro_desvios) ---
            cursor.execute(f'''
                SELECT
                    COALESCE(d_orig.id, conv.id) as decreto_id,
                    COALESCE(d_orig.nro_decreto, conv.nro_convenio) as nro_decreto,
                    COALESCE(d_orig.anio, strftime('%Y', conv.fecha_firma)) as decreto_anio,
                    COALESCE(d_orig.destino_fondos, conv.nombre_convenio) as destino_fondos,
                    COALESCE(d_orig.expediente_imuh, conv.nro_expediente) as decreto_expediente_imuh,
                    c.id as cobro_id, c.fecha as cobro_fecha, c.monto as cobro_monto,
                    'Desvío' as tipo_financiamiento,
                    cd.monto as monto_financiado,
                    (cd.monto - COALESCE(
                        (SELECT SUM(monto) FROM cobro_desvios_recuperos WHERE desvio_id = cd.id), 0
                    )) as saldo_pendiente,
                    cd.nro_op
                FROM cobro_desvios cd
                JOIN cobros c ON cd.cobro_id = c.id
                LEFT JOIN cuotas cu ON c.cuota_id = cu.id
                LEFT JOIN decretos d_orig ON cu.decreto_id = d_orig.id
                LEFT JOIN convenio_solicitudes csol ON c.convenio_solicitud_id = csol.id
                LEFT JOIN convenios conv ON csol.convenio_id = conv.id
                WHERE cd.obra_id = ?
                  AND cd.monto > {TOLERANCE}
            ''', (obra_id,))
            filas += [dict(r) for r in cursor.fetchall()]

            # --- Usos de reserva (cobro_reserva_usos) ---
            cursor.execute(f'''
                SELECT
                    COALESCE(d_orig.id, conv.id) as decreto_id,
                    COALESCE(d_orig.nro_decreto, conv.nro_convenio) as nro_decreto,
                    COALESCE(d_orig.anio, strftime('%Y', conv.fecha_firma)) as decreto_anio,
                    COALESCE(d_orig.destino_fondos, conv.nombre_convenio) as destino_fondos,
                    COALESCE(d_orig.expediente_imuh, conv.nro_expediente) as decreto_expediente_imuh,
                    c.id as cobro_id, c.fecha as cobro_fecha, c.monto as cobro_monto,
                    'Uso de Reserva' as tipo_financiamiento,
                    ru.monto as monto_financiado,
                    (ru.monto - COALESCE(
                        (SELECT SUM(monto) FROM cobro_reserva_usos_recuperos WHERE reserva_uso_id = ru.id), 0
                    )) as saldo_pendiente,
                    ru.nro_op
                FROM cobro_reserva_usos ru
                JOIN cobros c ON ru.cobro_id = c.id
                LEFT JOIN cuotas cu ON c.cuota_id = cu.id
                LEFT JOIN decretos d_orig ON cu.decreto_id = d_orig.id
                LEFT JOIN convenio_solicitudes csol ON c.convenio_solicitud_id = csol.id
                LEFT JOIN convenios conv ON csol.convenio_id = conv.id
                WHERE ru.obra_id = ?
                  AND ru.destino_tipo != 'fin_original'
                  AND ru.monto > {TOLERANCE}
            ''', (obra_id,))
            filas += [dict(r) for r in cursor.fetchall()]

            # --- Fin original (decretos asociados a la obra) ---
            cursor.execute(f'''
                SELECT
                    d.id as decreto_id, d.nro_decreto, d.anio as decreto_anio,
                    d.destino_fondos, d.expediente_imuh as decreto_expediente_imuh,
                    c.id as cobro_id, c.fecha as cobro_fecha, c.monto as cobro_monto,
                    'Fin Original' as tipo_financiamiento,
                    COALESCE(cd_dist.monto_fin_orig, c.monto) as monto_financiado,
                    COALESCE(cd_dist.monto_fin_orig, c.monto) -
                        COALESCE((SELECT SUM(monto) FROM cobro_fin_original_usos WHERE cobro_id = c.id), 0)
                    as saldo_pendiente,
                    NULL as nro_op
                FROM decretos_obras do_j
                JOIN decretos d ON do_j.decreto_id = d.id
                JOIN cuotas cu ON cu.decreto_id = d.id
                JOIN cobros c ON c.cuota_id = cu.id
                LEFT JOIN cobro_distribuciones cd_dist ON cd_dist.cobro_id = c.id
                WHERE do_j.obra_id = ?
            ''', (obra_id,))
            filas += [dict(r) for r in cursor.fetchall()]

            # --- Fin original (convenios asociados a la obra) ---
            cursor.execute(f'''
                SELECT
                    conv.id as decreto_id, conv.nro_convenio as nro_decreto, strftime('%Y', conv.fecha_firma) as decreto_anio,
                    conv.nombre_convenio as destino_fondos, conv.nro_expediente as decreto_expediente_imuh,
                    c.id as cobro_id, c.fecha as cobro_fecha, c.monto as cobro_monto,
                    'Fin Original' as tipo_financiamiento,
                    COALESCE(cd_dist.monto_fin_orig, c.monto) as monto_financiado,
                    COALESCE(cd_dist.monto_fin_orig, c.monto) -
                        COALESCE((SELECT SUM(monto) FROM cobro_fin_original_usos WHERE cobro_id = c.id), 0)
                    as saldo_pendiente,
                    NULL as nro_op
                FROM convenio_obras co
                JOIN convenios conv ON co.convenio_id = conv.id
                JOIN cobros c ON c.convenio_solicitud_id IN (SELECT id FROM convenio_solicitudes WHERE convenio_id = conv.id)
                              AND (c.obra_id = co.obra_id OR c.obra_id IS NULL)
                LEFT JOIN cobro_distribuciones cd_dist ON cd_dist.cobro_id = c.id
                WHERE co.obra_id = ?
            ''', (obra_id,))
            filas += [dict(r) for r in cursor.fetchall()]

        else:
            # --- Obra legacy: filtrar por nombre de texto ---
            nombre = obra_nombre_legacy or ''
            cursor.execute(f'''
                SELECT
                    COALESCE(d_orig.id, conv.id) as decreto_id,
                    COALESCE(d_orig.nro_decreto, conv.nro_convenio) as nro_decreto,
                    COALESCE(d_orig.anio, strftime('%Y', conv.fecha_firma)) as decreto_anio,
                    COALESCE(d_orig.destino_fondos, conv.nombre_convenio) as destino_fondos,
                    COALESCE(d_orig.expediente_imuh, conv.nro_expediente) as decreto_expediente_imuh,
                    c.id as cobro_id, c.fecha as cobro_fecha, c.monto as cobro_monto,
                    'Desvío' as tipo_financiamiento,
                    cd.monto as monto_financiado,
                    (cd.monto - COALESCE(
                        (SELECT SUM(monto) FROM cobro_desvios_recuperos WHERE desvio_id = cd.id), 0
                    )) as saldo_pendiente,
                    cd.nro_op
                FROM cobro_desvios cd
                JOIN cobros c ON cd.cobro_id = c.id
                LEFT JOIN cuotas cu ON c.cuota_id = cu.id
                LEFT JOIN decretos d_orig ON cu.decreto_id = d_orig.id
                LEFT JOIN convenio_solicitudes csol ON c.convenio_solicitud_id = csol.id
                LEFT JOIN convenios conv ON csol.convenio_id = conv.id
                WHERE cd.obra_id IS NULL AND cd.decreto_destino_id IS NULL AND cd.destino = ?
                  AND cd.monto > {TOLERANCE}
            ''', (nombre,))
            filas += [dict(r) for r in cursor.fetchall()]

            cursor.execute(f'''
                SELECT
                    COALESCE(d_orig.id, conv.id) as decreto_id,
                    COALESCE(d_orig.nro_decreto, conv.nro_convenio) as nro_decreto,
                    COALESCE(d_orig.anio, strftime('%Y', conv.fecha_firma)) as decreto_anio,
                    COALESCE(d_orig.destino_fondos, conv.nombre_convenio) as destino_fondos,
                    COALESCE(d_orig.expediente_imuh, conv.nro_expediente) as decreto_expediente_imuh,
                    c.id as cobro_id, c.fecha as cobro_fecha, c.monto as cobro_monto,
                    'Uso de Reserva' as tipo_financiamiento,
                    ru.monto as monto_financiado,
                    (ru.monto - COALESCE(
                        (SELECT SUM(monto) FROM cobro_reserva_usos_recuperos WHERE reserva_uso_id = ru.id), 0
                    )) as saldo_pendiente,
                    ru.nro_op
                FROM cobro_reserva_usos ru
                JOIN cobros c ON ru.cobro_id = c.id
                LEFT JOIN cuotas cu ON c.cuota_id = cu.id
                LEFT JOIN decretos d_orig ON cu.decreto_id = d_orig.id
                LEFT JOIN convenio_solicitudes csol ON c.convenio_solicitud_id = csol.id
                LEFT JOIN convenios conv ON csol.convenio_id = conv.id
                WHERE ru.obra_id IS NULL AND ru.decreto_destino_id IS NULL
                  AND ru.destino_tipo != 'fin_original' AND ru.destino_detalle = ?
                  AND ru.monto > {TOLERANCE}
            ''', (nombre,))
            filas += [dict(r) for r in cursor.fetchall()]

        filas.sort(key=lambda x: x['cobro_fecha'])
        return filas



# Alias de compatibilidad
get_recuperos_fondos_propios_by_cobro = get_recuperos_by_cobro
