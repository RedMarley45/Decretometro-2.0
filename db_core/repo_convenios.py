"""
db_core/repo_convenios.py - Convenios Multiobra, Certificación Contractual y KPIs Globales
"""
from db_core.connection import db_session, TOLERANCE

def add_convenio(nro_convenio, ente_financiador, nombre_convenio, nro_expediente,
                 fecha_firma, moneda_id, monto_pactado_moneda, cotizacion_base,
                 monto_equivalente_ars, pdf_path=None, notas=None):
    if not nro_convenio or not str(nro_convenio).strip():
        raise ValueError("El número de convenio es obligatorio.")
    if not ente_financiador or not str(ente_financiador).strip():
        raise ValueError("El ente financiador es obligatorio.")
    if not nombre_convenio or not str(nombre_convenio).strip():
        raise ValueError("El nombre descriptivo del convenio es obligatorio.")
    if not nro_expediente or not str(nro_expediente).strip():
        raise ValueError("El número de expediente es obligatorio.")
    if monto_pactado_moneda <= 0:
        raise ValueError("El monto pactado en moneda del convenio debe ser mayor a 0.")
    if cotizacion_base <= 0:
        raise ValueError("La cotización base debe ser mayor a 0.")
    if monto_equivalente_ars <= 0:
        raise ValueError("El monto equivalente en pesos debe ser mayor a 0.")

    with db_session() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO convenios (
                nro_convenio, ente_financiador, nombre_convenio, nro_expediente,
                fecha_firma, moneda_id, monto_pactado_moneda, cotizacion_base,
                monto_equivalente_ars, estado, pdf_path, notas
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'Vigente', ?, ?)
        ''', (
            str(nro_convenio).strip(), str(ente_financiador).strip(), str(nombre_convenio).strip(),
            str(nro_expediente).strip(), fecha_firma, moneda_id or 1,
            float(monto_pactado_moneda), float(cotizacion_base), float(monto_equivalente_ars),
            pdf_path, notas.strip() if notas else None
        ))

        return cursor.lastrowid


def update_convenio(convenio_id, nro_convenio, ente_financiador, nombre_convenio, nro_expediente,
                    fecha_firma, moneda_id, monto_pactado_moneda, cotizacion_base,
                    monto_equivalente_ars, pdf_path=None, notas=None):
    if not nro_convenio or not str(nro_convenio).strip():
        raise ValueError("El número de convenio es obligatorio.")
    if not ente_financiador or not str(ente_financiador).strip():
        raise ValueError("El ente financiador es obligatorio.")
    if not nombre_convenio or not str(nombre_convenio).strip():
        raise ValueError("El nombre descriptivo del convenio es obligatorio.")
    if not nro_expediente or not str(nro_expediente).strip():
        raise ValueError("El número de expediente es obligatorio.")
    if monto_pactado_moneda <= 0:
        raise ValueError("El monto pactado debe ser mayor a 0.")

    with db_session() as conn:
        cursor = conn.cursor()
        
        cursor.execute('SELECT COALESCE(SUM(monto_pactado_moneda), 0) as tot FROM convenio_obras WHERE convenio_id = ?', (convenio_id,))
        tot_obras = float(cursor.fetchone()['tot'] or 0.0)
        if float(monto_pactado_moneda) < (tot_obras - TOLERANCE):
            raise ValueError(f"No se puede reducir el monto del convenio por debajo de la suma ya asignada a sus obras ({tot_obras:,.2f}).")

        cursor.execute('SELECT COALESCE(SUM(cantidad_moneda), 0) as tot FROM convenio_solicitudes WHERE convenio_id = ? AND estado != "Anulado"', (convenio_id,))
        tot_sol = float(cursor.fetchone()['tot'] or 0.0)
        if float(monto_pactado_moneda) < (tot_sol - TOLERANCE):
            raise ValueError(f"No se puede reducir el monto del convenio por debajo de la suma total solicitada en certificados ({tot_sol:,.2f}).")

        cursor.execute('''
            UPDATE convenios
            SET nro_convenio = ?, ente_financiador = ?, nombre_convenio = ?, nro_expediente = ?,
                fecha_firma = ?, moneda_id = ?, monto_pactado_moneda = ?, cotizacion_base = ?,
                monto_equivalente_ars = ?, pdf_path = ?, notas = ?
            WHERE id = ?
        ''', (
            str(nro_convenio).strip(), str(ente_financiador).strip(), str(nombre_convenio).strip(),
            str(nro_expediente).strip(), fecha_firma, moneda_id or 1,
            float(monto_pactado_moneda), float(cotizacion_base), float(monto_equivalente_ars),
            pdf_path, notas.strip() if notas else None, convenio_id
        ))
        check_estado_convenio(conn, convenio_id)


def delete_convenio(convenio_id):
    with db_session() as conn:
        cursor = conn.cursor()
        # Verificar si tiene cobros asociados antes de borrar
        cursor.execute('''
            SELECT COUNT(*) as cnt FROM cobros c
            JOIN convenio_solicitudes cs ON c.convenio_solicitud_id = cs.id
            WHERE cs.convenio_id = ?
        ''', (convenio_id,))
        if cursor.fetchone()['cnt'] > 0:
            raise ValueError("No se puede eliminar un convenio con cobros registrados. Anule el convenio en su lugar.")

        cursor.execute('DELETE FROM convenios WHERE id = ?', (convenio_id,))


def get_convenios(estado=None):
    with db_session() as conn:
        cursor = conn.cursor()
        query = '''
            SELECT cv.*, m.codigo as moneda_codigo, m.simbolo as moneda_simbolo, m.nombre as moneda_nombre
            FROM convenios cv
            LEFT JOIN monedas_indices m ON cv.moneda_id = m.id
        '''
        params = []
        if estado and estado != 'Todos':
            query += ' WHERE cv.estado = ?'
            params.append(estado)
        query += ' ORDER BY cv.fecha_firma DESC, cv.id DESC'
        cursor.execute(query, params)
        rows = cursor.fetchall()
        return [dict(ix) for ix in rows]


def get_convenio(convenio_id):
    with db_session() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT cv.*, m.codigo as moneda_codigo, m.simbolo as moneda_simbolo, m.nombre as moneda_nombre
            FROM convenios cv
            LEFT JOIN monedas_indices m ON cv.moneda_id = m.id
            WHERE cv.id = ?
        ''', (convenio_id,))
        row = cursor.fetchone()
        return dict(row) if row else None


def update_estado_convenio(convenio_id, estado):
    if estado not in ('Vigente', 'Terminado', 'Anulado'):
        raise ValueError("Estado de convenio no válido.")
    with db_session() as conn:
        cursor = conn.cursor()
        cursor.execute('UPDATE convenios SET estado = ? WHERE id = ?', (estado, convenio_id))


def check_estado_convenio(conn, convenio_id):
    cursor = conn.cursor()
    cursor.execute('SELECT estado, monto_pactado_moneda FROM convenios WHERE id = ?', (convenio_id,))
    conv = cursor.fetchone()
    if not conv or conv['estado'] == 'Anulado':
        return

    monto_pactado = conv['monto_pactado_moneda'] or 0.0
    cursor.execute('''
        SELECT COALESCE(SUM(cantidad_moneda_cobrada), 0) as total_cobrado
        FROM convenio_solicitudes
        WHERE convenio_id = ? AND estado != 'Anulado'
    ''', (convenio_id,))
    total_cobrado = cursor.fetchone()['total_cobrado'] or 0.0

    if total_cobrado >= (monto_pactado - 0.01) and monto_pactado > 0:
        nuevo_estado = 'Terminado'
    else:
        nuevo_estado = 'Vigente'

    if nuevo_estado != conv['estado']:
        cursor.execute("UPDATE convenios SET estado = ? WHERE id = ?", (nuevo_estado, convenio_id))


def check_estado_convenio_by_solicitud(conn, solicitud_id):
    cursor = conn.cursor()
    cursor.execute('SELECT convenio_id FROM convenio_solicitudes WHERE id = ?', (solicitud_id,))
    row = cursor.fetchone()
    if row:
        check_estado_convenio(conn, row['convenio_id'])


def get_convenios_by_obra(obra_id):
    with db_session() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT cv.*, co.monto_pactado_moneda as monto_obra_moneda, co.monto_equivalente_ars as monto_obra_ars,
                   m.simbolo as moneda_simbolo, m.codigo as moneda_codigo
            FROM convenios cv
            JOIN convenio_obras co ON cv.id = co.convenio_id
            LEFT JOIN monedas_indices m ON cv.moneda_id = m.id
            WHERE co.obra_id = ?
            ORDER BY cv.fecha_firma DESC
        ''', (obra_id,))
        rows = cursor.fetchall()
        return [dict(ix) for ix in rows]


def add_obra_to_convenio(convenio_id, obra_id, monto_pactado_moneda, monto_equivalente_ars, porcentaje=0.0, notas=None):
    if monto_pactado_moneda <= 0:
        raise ValueError("El monto asignado a la obra debe ser mayor a 0.")
    with db_session() as conn:
        cursor = conn.cursor()
        # Validar que la asignación no supere el total pactado del convenio
        cursor.execute('SELECT monto_pactado_moneda FROM convenios WHERE id = ?', (convenio_id,))
        conv_row = cursor.fetchone()
        if not conv_row:
            raise ValueError("El convenio especificado no existe.")
        total_conv = conv_row['monto_pactado_moneda']

        cursor.execute('''
            SELECT COALESCE(SUM(monto_pactado_moneda), 0) as asignado 
            FROM convenio_obras 
            WHERE convenio_id = ? AND obra_id != ?
        ''', (convenio_id, obra_id))
        asignado = cursor.fetchone()['asignado']

        if (asignado + float(monto_pactado_moneda)) > (total_conv + 0.01):
            raise ValueError(
                f"El cupo asignado a las obras ({asignado + float(monto_pactado_moneda):,.2f}) "
                f"supera el monto total pactado del convenio ({total_conv:,.2f})."
            )

        cursor.execute('''
            INSERT OR REPLACE INTO convenio_obras (
                convenio_id, obra_id, monto_pactado_moneda, monto_equivalente_ars, porcentaje, notas
            )
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (convenio_id, obra_id, float(monto_pactado_moneda), float(monto_equivalente_ars), float(porcentaje), notas))

        return cursor.lastrowid


def remove_obra_from_convenio(convenio_id, obra_id):
    with db_session() as conn:
        cursor = conn.cursor()
        # Validar si tiene solicitudes
        cursor.execute('''
            SELECT COUNT(*) as cnt FROM convenio_solicitudes
            WHERE convenio_id = ? AND obra_id = ?
        ''', (convenio_id, obra_id))
        if cursor.fetchone()['cnt'] > 0:
            raise ValueError("No se puede quitar una obra que ya posee solicitudes o certificados de avance cargados en este convenio.")
        cursor.execute('DELETE FROM convenio_obras WHERE convenio_id = ? AND obra_id = ?', (convenio_id, obra_id))

def get_obras_by_convenio(convenio_id):
    with db_session() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT co.*, o.nombre as obra_nombre, o.expediente_imuh, o.activa as obra_activa,
                   p.razon_social as proveedor_razon_social,
                   o.monto_contrato, o.monto_contrato_moneda, o.cotizacion_base_contrato, o.moneda_id as obra_moneda_id
            FROM convenio_obras co
            JOIN obras o ON co.obra_id = o.id
            LEFT JOIN proveedores_obras p ON o.proveedor_id = p.id
            WHERE co.convenio_id = ?
            ORDER BY o.nombre ASC
        ''', (convenio_id,))
        rows = cursor.fetchall()
        return [dict(ix) for ix in rows]


def add_solicitud_convenio(convenio_id, obra_id, nro_certificado, periodo,
                           cantidad_moneda, cotizacion_solicitud, monto_solicitado_ars,
                           fecha_solicitud, expediente_pago=None, pdf_path=None, notas=None):
    if not nro_certificado or not str(nro_certificado).strip():
        raise ValueError("El número de certificado / solicitud es obligatorio.")
    if cantidad_moneda <= 0:
        raise ValueError("La cantidad en moneda/UVI solicitada debe ser mayor a 0.")
    if cotizacion_solicitud <= 0:
        raise ValueError("La cotización del certificado/solicitud debe ser mayor a 0.")
    if monto_solicitado_ars <= 0:
        raise ValueError("El importe en pesos solicitado debe ser mayor a 0.")

    with db_session() as conn:
        cursor = conn.cursor()
        
        # Validar que la cantidad solicitada no supere el remanente disponible del convenio
        cursor.execute('SELECT monto_pactado_moneda FROM convenios WHERE id = ?', (convenio_id,))
        conv = cursor.fetchone()
        if not conv:
            raise ValueError("El convenio especificado no existe.")
        total_pactado = conv['monto_pactado_moneda']
        
        cursor.execute('''
            SELECT COALESCE(SUM(cantidad_moneda), 0) as total_solicitado
            FROM convenio_solicitudes
            WHERE convenio_id = ? AND estado != 'Anulado'
        ''', (convenio_id,))
        total_sol = cursor.fetchone()['total_solicitado']
        remanente = total_pactado - total_sol

        if float(cantidad_moneda) > (remanente + 0.01):
            raise ValueError(
                f"La cantidad solicitada ({float(cantidad_moneda):,.2f}) supera el remanente disponible "
                f"del convenio ({remanente:,.2f} / {total_pactado:,.2f})."
            )

        # Auditoría de Cupo Nominal por Obra (Tribunal de Cuentas)
        cursor.execute('''
            SELECT monto_pactado_moneda FROM convenio_obras
            WHERE convenio_id = ? AND obra_id = ?
        ''', (convenio_id, obra_id))
        co_row = cursor.fetchone()
        cupo_obra = co_row['monto_pactado_moneda'] if co_row else None

        cursor.execute('''
            SELECT COALESCE(SUM(cantidad_moneda), 0) as sol_obra
            FROM convenio_solicitudes
            WHERE convenio_id = ? AND obra_id = ? AND estado != 'Anulado'
        ''', (convenio_id, obra_id))
        sol_obra_previo = cursor.fetchone()['sol_obra']

        notas_final = str(notas).strip() if notas else ""
        if cupo_obra is not None and (sol_obra_previo + float(cantidad_moneda)) > (cupo_obra + 0.01):
            exceso = (sol_obra_previo + float(cantidad_moneda)) - cupo_obra
            aviso_reasig = f"[Reasignación de cupo interno: supera cupo nominal de obra en {exceso:,.2f} dentro del remanente global del convenio]"
            if aviso_reasig not in notas_final:
                notas_final = f"{notas_final} | {aviso_reasig}".strip(" |")

        cursor.execute('''
            INSERT INTO convenio_solicitudes (
                convenio_id, obra_id, nro_certificado, periodo,
                cantidad_moneda, cantidad_moneda_cobrada, cotizacion_solicitud,
                monto_solicitado_ars, fecha_solicitud, expediente_pago,
                estado, pdf_path, notas
            )
            VALUES (?, ?, ?, ?, ?, 0.0, ?, ?, ?, ?, 'Pendiente', ?, ?)
        ''', (
            convenio_id, obra_id, str(nro_certificado).strip(), periodo,
            float(cantidad_moneda), float(cotizacion_solicitud), float(monto_solicitado_ars),
            fecha_solicitud, expediente_pago, pdf_path, notas_final if notas_final else None
        ))
        sol_id = cursor.lastrowid
        check_estado_convenio(conn, convenio_id)
        return sol_id


def update_solicitud_convenio(solicitud_id, nro_certificado, periodo,
                              cantidad_moneda, cotizacion_solicitud, monto_solicitado_ars,
                              fecha_solicitud, expediente_pago=None, pdf_path=None, notas=None):
    with db_session() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM convenio_solicitudes WHERE id = ?', (solicitud_id,))
        sol = cursor.fetchone()
        if not sol:
            raise ValueError("La solicitud de convenio no existe.")

        convenio_id = sol['convenio_id']
        cantidad_cobrada = float(sol['cantidad_moneda_cobrada'] or 0.0)
        cantidad_moneda = float(cantidad_moneda)

        if cantidad_moneda <= 0:
            raise ValueError("La cantidad solicitada en moneda contractual debe ser mayor a cero.")

        # Validación de piso: no puede ser menor a lo ya percibido
        if cantidad_moneda < (cantidad_cobrada - 0.01):
            raise ValueError(
                f"No se puede reducir la solicitud ({cantidad_moneda:,.2f}) por debajo de lo ya percibido "
                f"en cuenta bancaria ({cantidad_cobrada:,.2f})."
            )

        # Validación de techo global del convenio
        cursor.execute('SELECT monto_pactado_moneda FROM convenios WHERE id = ?', (convenio_id,))
        conv = cursor.fetchone()
        total_pactado = float(conv['monto_pactado_moneda'] or 0.0) if conv else 0.0

        cursor.execute('''
            SELECT COALESCE(SUM(cantidad_moneda), 0) as total_otras
            FROM convenio_solicitudes
            WHERE convenio_id = ? AND id != ? AND estado != 'Anulado'
        ''', (convenio_id, solicitud_id))
        total_otras = float(cursor.fetchone()['total_otras'] or 0.0)

        if (total_otras + cantidad_moneda) > (total_pactado + 0.01):
            remanente = max(0.0, total_pactado - total_otras)
            raise ValueError(
                f"La cantidad modificada ({cantidad_moneda:,.2f}) excede el cupo disponible del convenio "
                f"({remanente:,.2f} / {total_pactado:,.2f})."
            )

        # Recalcular estado de la solicitud
        if cantidad_cobrada >= (cantidad_moneda - 0.0001):
            nuevo_estado = 'Cobrado'
        elif cantidad_cobrada > 0.0001:
            nuevo_estado = 'Parcial'
        else:
            nuevo_estado = 'Pendiente'

        cursor.execute('''
            UPDATE convenio_solicitudes
            SET nro_certificado = ?, periodo = ?, cantidad_moneda = ?,
                cotizacion_solicitud = ?, monto_solicitado_ars = ?, fecha_solicitud = ?,
                expediente_pago = ?, pdf_path = ?, notas = ?, estado = ?
            WHERE id = ?
        ''', (
            str(nro_certificado).strip(), periodo, cantidad_moneda,
            float(cotizacion_solicitud), float(monto_solicitado_ars), fecha_solicitud,
            expediente_pago, pdf_path, notas.strip() if notas else None, nuevo_estado, solicitud_id
        ))
        check_estado_convenio(conn, convenio_id)


def delete_solicitud_convenio(solicitud_id):
    with db_session() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT convenio_id FROM convenio_solicitudes WHERE id = ?', (solicitud_id,))
        sol = cursor.fetchone()
        if not sol:
            return
        convenio_id = sol['convenio_id']

        cursor.execute('SELECT COUNT(*) as cnt FROM cobros WHERE convenio_solicitud_id = ?', (solicitud_id,))
        if cursor.fetchone()['cnt'] > 0:
            raise ValueError("No se puede eliminar una solicitud que tiene cobros bancarios asentados.")
        cursor.execute('DELETE FROM convenio_solicitudes WHERE id = ?', (solicitud_id,))
        check_estado_convenio(conn, convenio_id)


def get_solicitudes_by_convenio(convenio_id, obra_id=None):
    with db_session() as conn:
        cursor = conn.cursor()
        query = '''
            SELECT cs.*, o.nombre as obra_nombre, o.expediente_imuh,
                   m.simbolo as moneda_simbolo, m.codigo as moneda_codigo
            FROM convenio_solicitudes cs
            JOIN obras o ON cs.obra_id = o.id
            JOIN convenios cv ON cs.convenio_id = cv.id
            LEFT JOIN monedas_indices m ON cv.moneda_id = m.id
            WHERE cs.convenio_id = ?
        '''
        params = [convenio_id]
        if obra_id:
            query += ' AND cs.obra_id = ?'
            params.append(obra_id)
        query += ' ORDER BY cs.fecha_solicitud DESC, cs.id DESC'
        cursor.execute(query, params)
        rows = cursor.fetchall()
        return [dict(ix) for ix in rows]


def get_solicitudes_convenio_pendientes():
    with db_session() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT cs.*, cv.nro_convenio, cv.nro_convenio as convenio_numero, cv.nombre_convenio, cv.ente_financiador,
                   cv.moneda_id,
                   o.nombre as obra_nombre, o.expediente_imuh, o.expediente_imuh as obra_expediente_imuh,
                   m.simbolo as moneda_simbolo, m.codigo as moneda_codigo
            FROM convenio_solicitudes cs
            JOIN convenios cv ON cs.convenio_id = cv.id
            JOIN obras o ON cs.obra_id = o.id
            LEFT JOIN monedas_indices m ON cv.moneda_id = m.id
            WHERE cs.estado IN ('Pendiente', 'Parcial') AND cv.estado = 'Vigente'
            ORDER BY cs.fecha_solicitud ASC
        ''')
        rows = cursor.fetchall()
        result = []
        for ix in rows:
            d = dict(ix)
            cant_moneda = float(d.get('cantidad_moneda') or 0.0)
            cant_cobrada = float(d.get('cantidad_moneda_cobrada') or 0.0)
            cant_pendiente = max(0.0, cant_moneda - cant_cobrada)
            cotiz = float(d.get('cotizacion_solicitud') or 1.0)
            d['monto_ars_estimado'] = cant_pendiente * cotiz if cant_pendiente > 0 else float(d.get('monto_solicitado_ars') or 0.0)
            result.append(d)
        return result


def get_solicitud_convenio(solicitud_id):
    with db_session() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT cs.*, cv.nro_convenio, cv.nombre_convenio, cv.ente_financiador, cv.moneda_id as convenio_moneda_id,
                   o.nombre as obra_nombre, o.expediente_imuh,
                   m.simbolo as moneda_simbolo, m.codigo as moneda_codigo
            FROM convenio_solicitudes cs
            JOIN convenios cv ON cs.convenio_id = cv.id
            JOIN obras o ON cs.obra_id = o.id
            LEFT JOIN monedas_indices m ON cv.moneda_id = m.id
            WHERE cs.id = ?
        ''', (solicitud_id,))
        row = cursor.fetchone()
        return dict(row) if row else None


def get_resumen_control_convenio(convenio_id):
    """
    Retorna el estado de cuenta y control del convenio en su moneda o índice contractual (UVIs/USD),
    desglosado en Total Convenio, Cupo Contratado (en obras activas), Cupo Disponible (pendientes de licitar),
    Solicitado, Cobrado/Acreditado, Saldo en Tránsito y Saldo Remanente.
    """
    convenio = get_convenio(convenio_id)
    if not convenio:
        return None

    obras_convenio = get_obras_by_convenio(convenio_id)
    solicitudes = get_solicitudes_by_convenio(convenio_id)

    with db_session() as conn:
        cursor = conn.cursor()
        # Obtener todos los cobros asociados a este convenio
        cursor.execute('''
            SELECT c.*, cs.obra_id, cs.nro_certificado
            FROM cobros c
            JOIN convenio_solicitudes cs ON c.convenio_solicitud_id = cs.id
            WHERE cs.convenio_id = ?
        ''', (convenio_id,))
        cobros = [dict(ix) for ix in cursor.fetchall()]

    # Totales globales del Convenio en su Moneda
    pactado_moneda_total = float(convenio['monto_pactado_moneda'] or 0.0)
    pactado_ars_total = float(convenio['monto_equivalente_ars'] or 0.0)

    # Cupo Contratado / Asignado a Obras vs Cupo Disponible para Futuras Obras
    cupo_contratado_moneda = sum(float(ob['monto_pactado_moneda'] or 0.0) for ob in obras_convenio)
    cupo_contratado_ars = sum(float(ob['monto_equivalente_ars'] or 0.0) for ob in obras_convenio)
    cupo_disponible_moneda = max(0.0, pactado_moneda_total - cupo_contratado_moneda)
    cupo_disponible_ars = max(0.0, pactado_ars_total - cupo_contratado_ars)
    porcentaje_contratado = (cupo_contratado_moneda / pactado_moneda_total * 100) if pactado_moneda_total > 0 else 0.0

    solicitado_moneda_total = sum(float(s['cantidad_moneda'] or 0.0) for s in solicitudes if s['estado'] != 'Anulado')
    cobrado_moneda_total = sum(float(c.get('cantidad_moneda_origen') or 0.0) for c in cobros)
    cobrado_ars_total = sum(float(c['monto'] or 0.0) for c in cobros)
    diferencia_ajuste_ars_total = sum(float(c.get('diferencia_ajuste_ars') or 0.0) for c in cobros)

    saldo_en_transito_moneda = max(0.0, solicitado_moneda_total - cobrado_moneda_total)
    saldo_remanente_moneda = max(0.0, pactado_moneda_total - solicitado_moneda_total)
    saldo_por_certificar_contratado = max(0.0, cupo_contratado_moneda - solicitado_moneda_total)

    # Detalle por obra
    obras_resumen = []
    for ob in obras_convenio:
        o_id = ob['obra_id']
        o_pactado_moneda = float(ob['monto_pactado_moneda'] or 0.0)
        o_sols = [s for s in solicitudes if s['obra_id'] == o_id and s['estado'] != 'Anulado']
        o_solicitado_moneda = sum(float(s['cantidad_moneda'] or 0.0) for s in o_sols)
        o_cobs = [c for c in cobros if c['obra_id'] == o_id]
        o_cobrado_moneda = sum(float(c.get('cantidad_moneda_origen') or 0.0) for c in o_cobs)
        o_cobrado_ars = sum(float(c['monto'] or 0.0) for c in o_cobs)
        o_dif_ars = sum(float(c.get('diferencia_ajuste_ars') or 0.0) for c in o_cobs)

        o_transito_moneda = max(0.0, o_solicitado_moneda - o_cobrado_moneda)
        o_remanente_moneda = max(0.0, o_pactado_moneda - o_solicitado_moneda)

        obras_resumen.append({
            'obra_id': o_id,
            'obra_nombre': ob['obra_nombre'],
            'expediente_imuh': ob['expediente_imuh'],
            'proveedor_razon_social': ob.get('proveedor_razon_social') or '---',
            'monto_pactado_moneda': o_pactado_moneda,
            'monto_pactado_ars': float(ob['monto_equivalente_ars'] or 0.0),
            'solicitado_moneda': o_solicitado_moneda,
            'cobrado_moneda': o_cobrado_moneda,
            'saldo_en_transito_moneda': o_transito_moneda,
            'saldo_remanente_moneda': o_remanente_moneda,
            'cobrado_ars': o_cobrado_ars,
            'diferencia_ajuste_ars': o_dif_ars,
            'porcentaje_avance_financiero': (o_cobrado_moneda / o_pactado_moneda * 100) if o_pactado_moneda > 0 else 0.0
        })

    return {
        'convenio': convenio,
        'moneda_codigo': convenio.get('moneda_codigo', 'ARS'),
        'moneda_simbolo': convenio.get('moneda_simbolo', '$'),
        'pactado_moneda_total': pactado_moneda_total,
        'pactado_ars_total': pactado_ars_total,
        'cupo_contratado_moneda': cupo_contratado_moneda,
        'cupo_contratado_ars': cupo_contratado_ars,
        'cupo_disponible_moneda': cupo_disponible_moneda,
        'cupo_disponible_ars': cupo_disponible_ars,
        'porcentaje_contratado': porcentaje_contratado,
        'saldo_por_certificar_contratado': saldo_por_certificar_contratado,
        'solicitado_moneda_total': solicitado_moneda_total,
        'cobrado_moneda_total': cobrado_moneda_total,
        'saldo_en_transito_moneda': saldo_en_transito_moneda,
        'saldo_remanente_moneda': saldo_remanente_moneda,
        'cobrado_ars_total': cobrado_ars_total,
        'diferencia_ajuste_ars_total': diferencia_ajuste_ars_total,
        'porcentaje_cobranza': (cobrado_moneda_total / pactado_moneda_total * 100) if pactado_moneda_total > 0 else 0.0,
        'obras_detalle': obras_resumen
    }


def get_cobros_by_convenio(convenio_id):
    """Retorna los cobros bancarios asentados para un convenio multiobra específico."""
    with db_session() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT c.*, cs.nro_certificado, cs.cotizacion_solicitud, cs.periodo,
                   cs.cantidad_moneda as solicitud_moneda_total,
                   o.nombre as obra_nombre, o.expediente_imuh as obra_imuh
            FROM cobros c
            JOIN convenio_solicitudes cs ON c.convenio_solicitud_id = cs.id
            LEFT JOIN obras o ON (c.obra_id = o.id OR cs.obra_id = o.id)
            WHERE cs.convenio_id = ?
            ORDER BY c.fecha DESC, c.id DESC
        ''', (convenio_id,))
        return [dict(r) for r in cursor.fetchall()]


def get_kpis_convenios_global():
    """Retorna métricas agregadas de todos los convenios vigentes para el Dashboard."""
    with db_session() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) as cnt FROM convenios WHERE estado = 'Vigente'")
        total_vigentes = cursor.fetchone()['cnt']
        
        cursor.execute('''
            SELECT 
                COALESCE(SUM(c.monto), 0) as total_cobrado_ars,
                COALESCE(SUM(c.diferencia_ajuste_ars), 0) as total_diferencia_ars
            FROM cobros c
            WHERE c.origen_tipo = 'convenio'
        ''')
        row_cobros = cursor.fetchone()
        cobrado_ars = float(row_cobros['total_cobrado_ars'] or 0.0) if row_cobros else 0.0
        diferencia_ars = float(row_cobros['total_diferencia_ars'] or 0.0) if row_cobros else 0.0

        # Certificados en tránsito: valuación exacta del remanente en moneda por su cotización de solicitud
        cursor.execute('''
            SELECT 
                COUNT(*) as cant_pendientes,
                COALESCE(SUM((cs.cantidad_moneda - cs.cantidad_moneda_cobrada) * COALESCE(cs.cotizacion_solicitud, 1.0)), 0) as total_transito_ars,
                COALESCE(SUM(cs.cantidad_moneda - cs.cantidad_moneda_cobrada), 0) as total_transito_moneda
            FROM convenio_solicitudes cs
            JOIN convenios cv ON cs.convenio_id = cv.id
            WHERE cs.estado IN ('Pendiente', 'Parcial') AND cv.estado = 'Vigente'
        ''')
        row_trans = cursor.fetchone()
        
        return {
            'total_vigentes': total_vigentes,
            'total_cobrado_ars': cobrado_ars,
            'total_diferencia_ars': diferencia_ars,
            'cant_certificados_transito': row_trans['cant_pendientes'] if row_trans else 0,
            'total_transito_ars': float(row_trans['total_transito_ars'] or 0.0) if row_trans else 0.0,
            'total_transito_moneda': float(row_trans['total_transito_moneda'] or 0.0) if row_trans else 0.0
        }


