"""
db_core/repo_cobros.py - Ingresos Bancarios, Distribución Primaria y Balance Canónico de Cobros
"""
import datetime
from db_core.connection import db_session, TOLERANCE
from db_core.repo_auditoria import register_or_update_op, _validar_op_o_nota_db
from db_core.repo_decretos import check_estado_decreto_by_cuota
from db_core.repo_convenios import check_estado_convenio_by_solicitud

def _calcular_saldos_cobro_tx(cursor, cobro_id, exclude_desvio_id=None, exclude_rec_fp_id=None):
    """Calcula de forma canónica y atómica la ecuación patrimonial de un cobro.
    Verifica montos de Fin Original, Reserva, Desvíos, Recuperos de Fondos Propios y
    los recuperos de desvíos y reservas devueltos a 'sin_distribucion' (tot_recuperos_sd).
    """
    cursor.execute('SELECT monto, fecha FROM cobros WHERE id = ?', (cobro_id,))
    c_row = cursor.fetchone()
    if not c_row:
        raise ValueError("Cobro no encontrado.")
        
    cursor.execute('SELECT monto_fin_orig, monto_reserva FROM cobro_distribuciones WHERE cobro_id = ?', (cobro_id,))
    dist = cursor.fetchone()
    fin_orig = float(dist['monto_fin_orig']) if dist else 0.0
    reserva = float(dist['monto_reserva']) if dist else 0.0

    if exclude_desvio_id:
        cursor.execute('SELECT COALESCE(SUM(monto), 0) as tot FROM cobro_desvios WHERE cobro_id = ? AND id != ?', (cobro_id, exclude_desvio_id))
    else:
        cursor.execute('SELECT COALESCE(SUM(monto), 0) as tot FROM cobro_desvios WHERE cobro_id = ?', (cobro_id,))
    tot_desvios = float(cursor.fetchone()['tot'])

    if exclude_rec_fp_id:
        cursor.execute('SELECT COALESCE(SUM(monto), 0) as tot FROM recuperos_fondos_propios WHERE cobro_id = ? AND id != ?', (cobro_id, exclude_rec_fp_id))
    else:
        cursor.execute('SELECT COALESCE(SUM(monto), 0) as tot FROM recuperos_fondos_propios WHERE cobro_id = ?', (cobro_id,))
    tot_rec_fp = float(cursor.fetchone()['tot'])

    cursor.execute('''
        SELECT COALESCE(SUM(cdr.monto), 0) as tot 
        FROM cobro_desvios_recuperos cdr
        JOIN cobro_desvios cd ON cdr.desvio_id = cd.id
        WHERE cd.cobro_id = ? AND cdr.destino_tipo = 'sin_distribucion'
    ''', (cobro_id,))
    rec_desv_sd = float(cursor.fetchone()['tot'])

    cursor.execute('''
        SELECT COALESCE(SUM(crur.monto), 0) as tot 
        FROM cobro_reserva_usos_recuperos crur
        JOIN cobro_reserva_usos cru ON crur.reserva_uso_id = cru.id
        WHERE cru.cobro_id = ? AND crur.destino_tipo = 'sin_distribucion'
    ''', (cobro_id,))
    rec_res_sd = float(cursor.fetchone()['tot'])

    tot_recuperos_sd = rec_desv_sd + rec_res_sd
    total_comprometido = fin_orig + reserva + tot_desvios + tot_rec_fp - tot_recuperos_sd
    saldo_sin_distribuir = float(c_row['monto']) - total_comprometido

    return {
        'monto_cobro': float(c_row['monto']),
        'fecha_cobro': c_row['fecha'],
        'fin_orig': fin_orig,
        'reserva': reserva,
        'tot_desvios': tot_desvios,
        'tot_rec_fp': tot_rec_fp,
        'tot_recuperos_sd': tot_recuperos_sd,
        'total_comprometido': total_comprometido,
        'saldo_sin_distribuir': saldo_sin_distribuir
    }


def add_cobro(cuota_id=None, monto=0.0, fecha=None, comprobante_path=None,
              convenio_solicitud_id=None, origen_tipo='decreto',
              moneda_origen_id=1, cantidad_moneda_origen=None,
              cotizacion_cobro=1.0, diferencia_ajuste_ars=0.0, obra_id=None):
    if monto <= 0:
        raise ValueError("El monto cobrado debe ser mayor a 0.")
    fecha_dt = datetime.datetime.strptime(fecha, '%Y-%m-%d').date()
    if fecha_dt > datetime.date.today():
        raise ValueError("La fecha de cobro no puede ser futura.")

    # Blindaje de integridad y exclusión mutua de origen
    if origen_tipo == 'decreto':
        if not cuota_id or convenio_solicitud_id is not None:
            raise ValueError("Un cobro de decreto debe tener cuota_id y no puede tener convenio_solicitud_id.")
    elif origen_tipo == 'convenio':
        if not convenio_solicitud_id or cuota_id is not None:
            raise ValueError("Un cobro de convenio debe tener convenio_solicitud_id y no puede tener cuota_id.")
    else:
        raise ValueError(f"Tipo de origen '{origen_tipo}' no válido (debe ser 'decreto' o 'convenio').")
        
    with db_session() as conn:
        cursor = conn.cursor()

        if origen_tipo == 'convenio':
            cursor.execute('SELECT * FROM convenio_solicitudes WHERE id = ?', (convenio_solicitud_id,))
            sol = cursor.fetchone()
            if not sol:
                raise ValueError("Solicitud de convenio no encontrada.")
            
            obra_dest_id = obra_id or sol['obra_id']
            # Cantidad en moneda/UVI a amortizar
            if cantidad_moneda_origen is None or float(cantidad_moneda_origen) <= 0:
                raise ValueError("La cantidad en moneda/UVI a amortizar es obligatoria y debe ser mayor a 0.")
            cant_amortizar = float(cantidad_moneda_origen)
            saldo_moneda_sol = float(sol['cantidad_moneda'] - (sol['cantidad_moneda_cobrada'] or 0.0))
            
            # Guardia de sobrepago en convenio
            if cant_amortizar > (saldo_moneda_sol + 0.01):
                raise ValueError(f"La cantidad a amortizar ({cant_amortizar:,.2f}) supera el saldo pendiente de la solicitud/certificado ({saldo_moneda_sol:,.2f}).")
            
            nueva_cant_cobrada = (sol['cantidad_moneda_cobrada'] or 0.0) + cant_amortizar
            nuevo_estado = 'Cobrado' if nueva_cant_cobrada >= (sol['cantidad_moneda'] - 0.01) else 'Parcial'
            
            cursor.execute('''
                UPDATE convenio_solicitudes 
                SET cantidad_moneda_cobrada = ?, estado = ?
                WHERE id = ?
            ''', (nueva_cant_cobrada, nuevo_estado, convenio_solicitud_id))

            # Calcular automáticamente la diferencia por indexación/cotización si no se especificó
            if (diferencia_ajuste_ars is None or diferencia_ajuste_ars == 0.0) and sol['cotizacion_solicitud']:
                monto_esperado_sol_ars = cant_amortizar * float(sol['cotizacion_solicitud'])
                diferencia_ajuste_ars = float(monto) - monto_esperado_sol_ars

            cursor.execute('''
                INSERT INTO cobros (
                    cuota_id, convenio_solicitud_id, origen_tipo, obra_id,
                    moneda_origen_id, cantidad_moneda_origen, cotizacion_cobro,
                    diferencia_ajuste_ars, monto, fecha, comprobante_path
                )
                VALUES (NULL, ?, 'convenio', ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (convenio_solicitud_id, obra_dest_id, moneda_origen_id or 1, cant_amortizar,
                  cotizacion_cobro or 1.0, diferencia_ajuste_ars or 0.0, monto, fecha, comprobante_path))
            cobro_id = cursor.lastrowid

            check_estado_convenio_by_solicitud(conn, convenio_solicitud_id)
            return cobro_id
        else:
            # Flujo Decreto tradicional
            cursor.execute('SELECT monto, mes, anio FROM cuotas WHERE id = ?', (cuota_id,))
            q_row = cursor.fetchone()
            if not q_row:
                raise ValueError("Cuota no encontrada.")
                
            # Validar período de la cuota
            cuota_start = f"{q_row['anio']}-{q_row['mes']:02d}-01"
            if fecha < cuota_start:
                raise ValueError(f"La fecha de cobro ({fecha}) no puede ser anterior al inicio del período de la cuota ({q_row['mes']:02d}/{q_row['anio']}).")
        
            cursor.execute('SELECT SUM(monto) as cobrado FROM cobros WHERE cuota_id = ?', (cuota_id,))
            c_row = cursor.fetchone()
            cobrado_previo = c_row['cobrado'] if c_row and c_row['cobrado'] else 0
            saldo = q_row['monto'] - cobrado_previo
        
            if monto > (saldo + 0.01):
                raise ValueError(f"El monto a cobrar ({monto}) supera el saldo pendiente de la cuota ({saldo:.2f}).")

            cursor.execute('''
                INSERT INTO cobros (
                    cuota_id, convenio_solicitud_id, origen_tipo, obra_id,
                    moneda_origen_id, cantidad_moneda_origen, cotizacion_cobro,
                    diferencia_ajuste_ars, monto, fecha, comprobante_path
                )
                VALUES (?, NULL, 'decreto', ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (cuota_id, obra_id, moneda_origen_id or 1, cantidad_moneda_origen, cotizacion_cobro or 1.0,
                  diferencia_ajuste_ars or 0.0, monto, fecha, comprobante_path))
            cobro_id = cursor.lastrowid

            check_estado_decreto_by_cuota(conn, cuota_id)
            return cobro_id


def get_all_cobros():
    with db_session() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            WITH ranked_cuotas AS (
                SELECT id, decreto_id, mes, anio,
                       ROW_NUMBER() OVER (PARTITION BY decreto_id ORDER BY anio ASC, mes ASC) as seq_nro,
                       COUNT(*) OVER (PARTITION BY decreto_id) as total_cuotas
                FROM cuotas
            )
            SELECT c.id, c.monto, c.fecha, c.comprobante_path, c.cuota_id,
                   c.convenio_solicitud_id, c.origen_tipo, c.obra_id as cobro_obra_id,
                   c.moneda_origen_id, c.cantidad_moneda_origen, c.cotizacion_cobro, c.diferencia_ajuste_ars,
                   rc.mes, rc.anio, 
                   rc.seq_nro, rc.total_cuotas,
                   d.nro_decreto, d.anio as decreto_anio, d.id as decreto_id,
                   COALESCE(d.destino_fondos, cv.nombre_convenio || ' — ' || o.nombre) as obra,
                   cv.nro_convenio, cv.nombre_convenio, cs.nro_certificado,
                   m.simbolo as moneda_simbolo, m.codigo as moneda_codigo
            FROM cobros c
            LEFT JOIN ranked_cuotas rc ON c.cuota_id = rc.id
            LEFT JOIN decretos d ON rc.decreto_id = d.id
            LEFT JOIN convenio_solicitudes cs ON c.convenio_solicitud_id = cs.id
            LEFT JOIN convenios cv ON cs.convenio_id = cv.id
            LEFT JOIN obras o ON (c.obra_id = o.id OR cs.obra_id = o.id)
            LEFT JOIN monedas_indices m ON c.moneda_origen_id = m.id
            ORDER BY c.fecha DESC, c.id DESC
        ''')
        rows = cursor.fetchall()
        return [dict(ix) for ix in rows]


def get_cobros_by_cuota(cuota_id):
    with db_session() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM cobros WHERE cuota_id = ? ORDER BY fecha ASC', (cuota_id,))
        rows = cursor.fetchall()
        return [dict(ix) for ix in rows]


def get_cobro(cobro_id):
    with db_session() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT c.*, 
                   d.id as decreto_id, 
                   COALESCE(d.nro_decreto, cv.nro_convenio) as nro_decreto, 
                   COALESCE(d.anio, strftime('%Y', cv.fecha_firma)) as decreto_anio,
                   cv.id as convenio_id, cv.nro_convenio, cv.nombre_convenio,
                   COALESCE(d.destino_fondos, cv.nombre_convenio || ' — ' || o.nombre) as obra_nombre
            FROM cobros c
            LEFT JOIN cuotas cu ON c.cuota_id = cu.id
            LEFT JOIN decretos d ON cu.decreto_id = d.id
            LEFT JOIN convenio_solicitudes cs ON c.convenio_solicitud_id = cs.id
            LEFT JOIN convenios cv ON cs.convenio_id = cv.id
            LEFT JOIN obras o ON (c.obra_id = o.id OR cs.obra_id = o.id)
            WHERE c.id = ?
        ''', (cobro_id,))
        row = cursor.fetchone()
        return dict(row) if row else None


def delete_cobro(cobro_id):
    with db_session() as conn:
        cursor = conn.cursor()

        # Verificar dependencias antes de eliminar
        cursor.execute('SELECT COUNT(*) as cnt FROM cobro_fin_original_usos WHERE cobro_id = ?', (cobro_id,))
        if cursor.fetchone()['cnt'] > 0:
            raise ValueError("No se puede eliminar un cobro con pagos a Fin Original registrados. Elimine los pagos primero.")
            
        cursor.execute('SELECT COUNT(*) as cnt FROM cobro_desvios WHERE cobro_id = ?', (cobro_id,))
        if cursor.fetchone()['cnt'] > 0:
            raise ValueError("No se puede eliminar un cobro que tiene desvíos de fondos registrados. Elimine los desvíos primero.")
            
        cursor.execute('SELECT COUNT(*) as cnt FROM cobro_reserva_usos WHERE cobro_id = ?', (cobro_id,))
        if cursor.fetchone()['cnt'] > 0:
            raise ValueError("No se puede eliminar un cobro que tiene usos de reserva registrados. Elimine los usos primero.")

        cursor.execute('SELECT COUNT(*) as cnt FROM recuperos_fondos_propios WHERE cobro_id = ?', (cobro_id,))
        if cursor.fetchone()['cnt'] > 0:
            raise ValueError("No se puede eliminar un cobro con recuperos de fondos propios registrados. Elimine los recuperos primero.")

        cursor.execute('SELECT cuota_id, convenio_solicitud_id, cantidad_moneda_origen FROM cobros WHERE id = ?', (cobro_id,))
        cobro_row = cursor.fetchone()
        cursor.execute('DELETE FROM cobros WHERE id = ?', (cobro_id,))
        if cobro_row and cobro_row['convenio_solicitud_id']:
            sol_id = cobro_row['convenio_solicitud_id']
            cant_amort = float(cobro_row['cantidad_moneda_origen'] or 0.0)
            cursor.execute('SELECT cantidad_moneda, cantidad_moneda_cobrada FROM convenio_solicitudes WHERE id = ?', (sol_id,))
            sol = cursor.fetchone()
            if sol:
                nueva_cobrada = max(0.0, float(sol['cantidad_moneda_cobrada'] or 0.0) - cant_amort)
                nuevo_estado = 'Pendiente' if nueva_cobrada <= 0.01 else 'Parcial'
                cursor.execute('UPDATE convenio_solicitudes SET cantidad_moneda_cobrada = ?, estado = ? WHERE id = ?', (nueva_cobrada, nuevo_estado, sol_id))
                check_estado_convenio_by_solicitud(conn, sol_id)
        if cobro_row and cobro_row['cuota_id']:
            check_estado_decreto_by_cuota(conn, cobro_row['cuota_id'])

    # --- Aportes Funcionamiento ---


def get_distribucion_by_cobro(cobro_id):
    with db_session() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM cobro_distribuciones WHERE cobro_id = ?', (cobro_id,))
        row = cursor.fetchone()
        return dict(row) if row else None


def upsert_distribucion(cobro_id, monto_fin_orig, monto_reserva, notas=""):
    if monto_fin_orig < 0 or monto_reserva < 0:
        raise ValueError("Los montos no pueden ser negativos.")
        
    with db_session() as conn:
        cursor = conn.cursor()
        saldos = _calcular_saldos_cobro_tx(cursor, cobro_id)
        
        total_otros = saldos['tot_desvios'] + saldos['tot_rec_fp'] - saldos['tot_recuperos_sd']
        if (monto_fin_orig + monto_reserva + total_otros) > (saldos['monto_cobro'] + TOLERANCE):
            raise ValueError("La suma ingresada supera el monto total del cobro.")

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
        
        if monto_reserva < (ya_usado_neto - TOLERANCE):
            raise ValueError(f"No se puede reducir la reserva a {monto_reserva} porque ya se han utilizado {ya_usado_neto} de la misma.")

        cursor.execute('SELECT id FROM cobro_distribuciones WHERE cobro_id = ?', (cobro_id,))
        row = cursor.fetchone()
        if row:
            cursor.execute('''
                UPDATE cobro_distribuciones
                SET monto_fin_orig = ?, monto_reserva = ?, notas = ?
                WHERE id = ?
            ''', (monto_fin_orig, monto_reserva, notas, row['id']))
        else:
            cursor.execute('''
                INSERT INTO cobro_distribuciones (cobro_id, monto_fin_orig, monto_reserva, notas)
                VALUES (?, ?, ?, ?)
            ''', (cobro_id, monto_fin_orig, monto_reserva, notas))


def get_cobros_con_resumen_distribucion():
    with db_session() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT c.id, c.monto, c.fecha, c.cuota_id, c.origen_tipo, c.convenio_solicitud_id,
                   cu.mes, cu.anio,
                   COALESCE(d.nro_decreto, cv.nro_convenio) as nro_decreto,
                   COALESCE(d.anio, strftime('%Y', cv.fecha_firma)) as decreto_anio,
                   d.id as decreto_id, cv.id as convenio_id,
                   cv.nro_convenio, cv.nombre_convenio, cv.ente_financiador,
                   cs.nro_certificado, cs.periodo, cs.cantidad_moneda as cantidad_moneda_solicitada,
                   COALESCE(cs.cotizacion_solicitud, 1.0) as cotizacion_solicitud,
                   COALESCE(c.obra_id, cs.obra_id) as obra_id,
                   o.nombre as obra_nombre,
                   COALESCE(d.destino_fondos, cv.nombre_convenio || ' — ' || o.nombre) as destino_fondos,
                   COALESCE(d.expediente_imuh, o.expediente_imuh) as expediente_imuh,
                   COALESCE(mc.simbolo, m.simbolo, '$') as moneda_simbolo,
                   COALESCE(mc.codigo, m.codigo, 'ARS') as moneda_codigo,
                   c.cantidad_moneda_origen, c.cotizacion_cobro,
                   COALESCE(dist.monto_fin_orig, 0) as monto_fin_orig,
                   COALESCE(dist.monto_reserva, 0) as monto_reserva,
                   COALESCE((SELECT SUM(monto) FROM cobro_desvios WHERE cobro_id = c.id), 0) as total_desvios,
                   COALESCE((SELECT SUM(monto) FROM recuperos_fondos_propios WHERE cobro_id = c.id), 0) as total_recuperos_fp,
                   (
                       COALESCE(dist.monto_fin_orig, 0) + 
                       COALESCE(dist.monto_reserva, 0) + 
                       COALESCE((SELECT SUM(monto) FROM cobro_desvios WHERE cobro_id = c.id), 0) +
                       COALESCE((SELECT SUM(monto) FROM recuperos_fondos_propios WHERE cobro_id = c.id), 0) -
                       COALESCE((
                           SELECT SUM(cdr.monto) FROM cobro_desvios_recuperos cdr
                           JOIN cobro_desvios cd ON cdr.desvio_id = cd.id
                           WHERE cd.cobro_id = c.id AND cdr.destino_tipo = 'sin_distribucion'
                       ), 0) -
                       COALESCE((
                           SELECT SUM(crur.monto) FROM cobro_reserva_usos_recuperos crur
                           JOIN cobro_reserva_usos cru ON crur.reserva_uso_id = cru.id
                           WHERE cru.cobro_id = c.id AND crur.destino_tipo = 'sin_distribucion'
                       ), 0)
                   ) as total_distribuido,
                   COALESCE((SELECT SUM(monto) FROM cobro_reserva_usos WHERE cobro_id = c.id), 0) as total_reserva_usada,
                   COALESCE((
                       SELECT SUM(crur.monto) FROM cobro_reserva_usos_recuperos crur
                       JOIN cobro_reserva_usos cru ON crur.reserva_uso_id = cru.id
                       WHERE cru.cobro_id = c.id AND crur.destino_tipo = 'reserva'
                   ), 0) as total_recuperos_reserva_a_reserva,
                   COALESCE((
                       SELECT SUM(cdr.monto) FROM cobro_desvios_recuperos cdr
                       JOIN cobro_desvios cd ON cdr.desvio_id = cd.id
                       WHERE cd.cobro_id = c.id AND cdr.destino_tipo = 'reserva'
                   ), 0) as total_recuperos_desvios_a_reserva,
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
                   ) as saldo_reserva_disponible
            FROM cobros c
            LEFT JOIN cuotas cu ON c.cuota_id = cu.id
            LEFT JOIN decretos d ON cu.decreto_id = d.id
            LEFT JOIN convenio_solicitudes cs ON c.convenio_solicitud_id = cs.id
            LEFT JOIN convenios cv ON cs.convenio_id = cv.id
            LEFT JOIN obras o ON (c.obra_id = o.id OR cs.obra_id = o.id)
            LEFT JOIN monedas_indices m ON c.moneda_origen_id = m.id
            LEFT JOIN monedas_indices mc ON cv.moneda_id = mc.id
            LEFT JOIN cobro_distribuciones dist ON c.id = dist.cobro_id
            ORDER BY c.fecha DESC, c.id DESC
        ''')
        rows = cursor.fetchall()
        return [dict(ix) for ix in rows]


def add_fin_original_uso(cobro_id, monto, fecha, nro_op=None, notas=None, obra_id=None, gasto_nombre=None, gasto_expediente_imuh=None,
                         cantidad_moneda_amortizada=None, cotizacion_pago=None, convenio_solicitud_id=None, motivo_sobrepago=None):
    _validar_op_o_nota_db(nro_op, notas, contexto="pago de Fin Original")
    if monto <= 0:
        raise ValueError("El monto a pagar debe ser mayor a 0.")
    
    with db_session() as conn:
        cursor = conn.cursor()
    
        cursor.execute('SELECT monto_fin_orig FROM cobro_distribuciones WHERE cobro_id = ?', (cobro_id,))
        row_dist = cursor.fetchone()
        fin_orig_presupuesto = row_dist['monto_fin_orig'] if row_dist else 0.0
    
        cursor.execute('SELECT COALESCE(SUM(monto), 0) as tot_pagado FROM cobro_fin_original_usos WHERE cobro_id = ?', (cobro_id,))
        ya_pagado = cursor.fetchone()['tot_pagado']
    
        if (ya_pagado + monto) > (fin_orig_presupuesto + TOLERANCE):
            raise ValueError(f"El monto a pagar ({monto:.2f}) supera el saldo disponible asignado a Fin Original ({fin_orig_presupuesto - ya_pagado:.2f}).")
        
        # Obtener información del cobro para auto-derivación de convenio si corresponde
        cursor.execute('''
            SELECT c.*, cs.id as cs_id, cs.obra_id as cs_obra_id, cs.cotizacion_solicitud, cs.cantidad_moneda, cs.nro_certificado
            FROM cobros c
            LEFT JOIN convenio_solicitudes cs ON c.convenio_solicitud_id = cs.id
            WHERE c.id = ?
        ''', (cobro_id,))
        c_row = cursor.fetchone()
        
        target_obra_id = obra_id
        if not target_obra_id and c_row:
            target_obra_id = c_row['obra_id'] or c_row['cs_obra_id']
            
        c_sol_id = convenio_solicitud_id
        if c_sol_id is None and c_row and c_row['convenio_solicitud_id']:
            c_sol_id = c_row['convenio_solicitud_id']
            
        cotiz = cotizacion_pago
        cant_mon = cantidad_moneda_amortizada
        
        if target_obra_id:
            cursor.execute('SELECT moneda_id FROM obras WHERE id = ?', (target_obra_id,))
            o_row = cursor.fetchone()
            if o_row:
                o_moneda_id = o_row['moneda_id'] or 1
                if o_moneda_id == 1:
                    cotiz = 1.0
                    cant_mon = float(monto)
                else:
                    if cotiz is None or cotiz <= 0:
                        cotiz_sol = c_row['cotizacion_solicitud'] if (c_row and 'cotizacion_solicitud' in c_row.keys()) else None
                        if not cotiz_sol and c_sol_id:
                            cursor.execute('SELECT cotizacion_solicitud FROM convenio_solicitudes WHERE id = ?', (c_sol_id,))
                            cs_f = cursor.fetchone()
                            if cs_f:
                                cotiz_sol = cs_f['cotizacion_solicitud']

                        if c_row and c_row['cotizacion_cobro'] and float(c_row['cotizacion_cobro']) > 1.0:
                            cotiz = float(c_row['cotizacion_cobro'])
                        elif cotiz_sol and float(cotiz_sol) > 1.0:
                            cotiz = float(cotiz_sol)
                        else:
                            raise ValueError(
                                "Para obras contratadas en UVIs u otra moneda extranjera es obligatorio especificar "
                                "una cotización de pago válida (mayor a 1.0) o asociar un cobro/solicitud con cotización."
                            )
                    if cant_mon is None:
                        cant_mon = round(monto / cotiz, 6) if cotiz > 0 else 0.0

        cursor.execute('''
            INSERT INTO cobro_fin_original_usos (
                cobro_id, monto, fecha, nro_op, notas, obra_id, gasto_nombre, gasto_expediente_imuh,
                cantidad_moneda_amortizada, cotizacion_pago, convenio_solicitud_id, motivo_sobrepago
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (cobro_id, monto, fecha, nro_op, notas, target_obra_id, gasto_nombre, gasto_expediente_imuh,
              cant_mon, cotiz, c_sol_id, motivo_sobrepago))
        new_id = cursor.lastrowid

        if nro_op:
            g_id = None
            if gasto_expediente_imuh:
                r = cursor.execute("SELECT id FROM gastos_funcionamiento WHERE expediente_imuh = ?", (gasto_expediente_imuh,)).fetchone()
                if r:
                    g_id = r['id']
            register_or_update_op(nro_op, obra_id=target_obra_id, gasto_id=g_id, conn=conn)

    return new_id


def update_fin_original_uso(uso_id, monto, fecha, nro_op, notas, obra_id=None, gasto_nombre=None, gasto_expediente_imuh=None,
                            cantidad_moneda_amortizada=None, cotizacion_pago=None, convenio_solicitud_id=None, motivo_sobrepago=None):
    _validar_op_o_nota_db(nro_op, notas, contexto="pago de Fin Original")
    if monto <= 0:
        raise ValueError("El monto debe ser mayor a 0.")
    with db_session() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT cobro_id FROM cobro_fin_original_usos WHERE id = ?', (uso_id,))
        uso_row = cursor.fetchone()
        if not uso_row:
            raise ValueError("Pago de Fin Original no encontrado.")
        cobro_id = uso_row['cobro_id']
    
        cursor.execute('SELECT monto_fin_orig FROM cobro_distribuciones WHERE cobro_id = ?', (cobro_id,))
        dist_row = cursor.fetchone()
        presupuesto = dist_row['monto_fin_orig'] if dist_row else 0.0
    
        cursor.execute('SELECT COALESCE(SUM(monto), 0) as tot FROM cobro_fin_original_usos WHERE cobro_id = ? AND id != ?', (cobro_id, uso_id))
        otros_pagos = cursor.fetchone()['tot']
    
        if (otros_pagos + monto) > (presupuesto + TOLERANCE):
            raise ValueError(f"El monto editado ({monto:.2f}) supera el saldo disponible asignado a Fin Original ({presupuesto - otros_pagos:.2f}).")
            
        cursor.execute('SELECT * FROM cobro_fin_original_usos WHERE id = ?', (uso_id,))
        cur_u = cursor.fetchone()
        
        target_obra_id = obra_id if obra_id is not None else cur_u['obra_id']
        cotiz = cotizacion_pago if cotizacion_pago is not None else cur_u['cotizacion_pago']
        cant_mon = cantidad_moneda_amortizada if cantidad_moneda_amortizada is not None else cur_u['cantidad_moneda_amortizada']
        c_sol_id = convenio_solicitud_id if convenio_solicitud_id is not None else cur_u['convenio_solicitud_id']
        motivo_sp = motivo_sobrepago if motivo_sobrepago is not None else cur_u['motivo_sobrepago']
        
        if target_obra_id:
            cursor.execute('SELECT moneda_id FROM obras WHERE id = ?', (target_obra_id,))
            o_row = cursor.fetchone()
            if o_row:
                o_moneda_id = o_row['moneda_id'] or 1
                if o_moneda_id == 1:
                    cotiz = 1.0
                    cant_mon = float(monto)
                else:
                    if cotiz is None or float(cotiz) <= 0:
                        raise ValueError(
                            "Para obras contratadas en UVIs u otra moneda extranjera es obligatorio especificar una cotización de pago válida."
                        )
                    cotiz = float(cotiz)
                    if cant_mon is None:
                        cant_mon = round(monto / cotiz, 6)

        cursor.execute('''
            UPDATE cobro_fin_original_usos
            SET monto = ?, fecha = ?, nro_op = ?, notas = ?, obra_id = ?, gasto_nombre = ?, gasto_expediente_imuh = ?,
                cantidad_moneda_amortizada = ?, cotizacion_pago = ?, convenio_solicitud_id = ?, motivo_sobrepago = ?
            WHERE id = ?
        ''', (monto, fecha, nro_op, notas, target_obra_id, gasto_nombre, gasto_expediente_imuh,
              cant_mon, cotiz, c_sol_id, motivo_sp, uso_id))

        if nro_op and str(nro_op).strip():
            register_or_update_op(str(nro_op).strip(), obra_id=target_obra_id, conn=conn)


def delete_fin_original_uso(uso_id):
    with db_session() as conn:
        cursor = conn.cursor()
        cursor.execute('DELETE FROM cobro_fin_original_usos WHERE id = ?', (uso_id,))


def get_fin_original_usos_by_cobro(cobro_id):
    with db_session() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT fu.*, 
                   o.expediente_imuh as o_expediente, 
                   o.nombre as o_nombre
            FROM cobro_fin_original_usos fu
            LEFT JOIN obras o ON fu.obra_id = o.id
            WHERE fu.cobro_id = ? 
            ORDER BY fu.fecha ASC
        ''', (cobro_id,))
        rows = cursor.fetchall()
        return [dict(ix) for ix in rows]


