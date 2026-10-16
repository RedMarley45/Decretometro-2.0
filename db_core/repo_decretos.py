"""
db_core/repo_decretos.py - Decretos, Cuotas, Solicitudes de Financiamiento y Préstamos Legacy
"""
import datetime
import calendar
from db_core.connection import db_session, TOLERANCE

def add_decreto(nro_decreto, anio, nro_expediente, destino_fondos, pdf_path=None, expediente_imuh=None, moneda_id=1):
    if nro_decreto <= 0:
        raise ValueError("El número de decreto debe ser mayor a 0.")
    if anio <= 0:
        raise ValueError("El año debe ser mayor a 0.")
    if not nro_expediente or not nro_expediente.strip():
        raise ValueError("El número de expediente no puede estar vacío.")
    if not destino_fondos or not destino_fondos.strip():
        raise ValueError("El destino de fondos no puede estar vacío.")
    with db_session() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO decretos (nro_decreto, anio, nro_expediente, destino_fondos, pdf_path, estado, expediente_imuh, moneda_id)
            VALUES (?, ?, ?, ?, ?, 'Vigente', ?, ?)
        ''', (nro_decreto, anio, nro_expediente, destino_fondos, pdf_path, expediente_imuh, moneda_id or 1))
        decreto_id = cursor.lastrowid
        return decreto_id


def get_decretos():
    with db_session() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT d.*, m.simbolo as moneda_simbolo, m.codigo as moneda_codigo, m.nombre as moneda_nombre
            FROM decretos d
            LEFT JOIN monedas_indices m ON d.moneda_id = m.id
            ORDER BY d.anio DESC, d.nro_decreto DESC
        ''')
        rows = cursor.fetchall()
        return [dict(ix) for ix in rows]


def get_decreto(decreto_id):
    with db_session() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT d.*, m.simbolo as moneda_simbolo, m.codigo as moneda_codigo, m.nombre as moneda_nombre
            FROM decretos d
            LEFT JOIN monedas_indices m ON d.moneda_id = m.id
            WHERE d.id = ?
        ''', (decreto_id,))
        row = cursor.fetchone()
        return dict(row) if row else None


def check_expediente_exists(nro_expediente, exclude_id=None):
    with db_session() as conn:
        cursor = conn.cursor()
        if exclude_id:
            cursor.execute('SELECT id FROM decretos WHERE nro_expediente = ? AND id != ?', (nro_expediente, exclude_id))
        else:
            cursor.execute('SELECT id FROM decretos WHERE nro_expediente = ?', (nro_expediente,))
        row = cursor.fetchone()
        return row is not None


def update_decreto(decreto_id, nro_decreto, anio, nro_expediente, destino_fondos, pdf_path, expediente_imuh=None, moneda_id=None):
    if nro_decreto <= 0:
        raise ValueError("El número de decreto debe ser mayor a 0.")
    if anio <= 0:
        raise ValueError("El año debe ser mayor a 0.")
    if not nro_expediente or not nro_expediente.strip():
        raise ValueError("El número de expediente no puede estar vacío.")
    if not destino_fondos or not destino_fondos.strip():
        raise ValueError("El destino de fondos no puede estar vacío.")
    with db_session() as conn:
        cursor = conn.cursor()
        if moneda_id is not None:
            cursor.execute('''
                UPDATE decretos
                SET nro_decreto = ?, anio = ?, nro_expediente = ?, destino_fondos = ?, pdf_path = ?, expediente_imuh = ?, moneda_id = ?
                WHERE id = ?
            ''', (nro_decreto, anio, nro_expediente, destino_fondos, pdf_path, expediente_imuh, moneda_id, decreto_id))
        else:
            cursor.execute('''
                UPDATE decretos
                SET nro_decreto = ?, anio = ?, nro_expediente = ?, destino_fondos = ?, pdf_path = ?, expediente_imuh = ?
                WHERE id = ?
            ''', (nro_decreto, anio, nro_expediente, destino_fondos, pdf_path, expediente_imuh, decreto_id))


def delete_decreto(decreto_id):
    with db_session() as conn:
        cursor = conn.cursor()

        # Verificar dependencias antes de eliminar para evitar cascadas accidentales
        cursor.execute('''
            SELECT COUNT(*) as cnt FROM cuotas cu 
            JOIN cobros c ON c.cuota_id = cu.id 
            WHERE cu.decreto_id = ?
        ''', (decreto_id,))
        if cursor.fetchone()['cnt'] > 0:
            raise ValueError("No se puede eliminar un decreto que tiene cobros registrados. Por favor, anule el decreto o elimine los cobros asociados primero.")
            
        cursor.execute('SELECT COUNT(*) as cnt FROM prestamos_internos WHERE decreto_origen_id = ?', (decreto_id,))
        if cursor.fetchone()['cnt'] > 0:
            raise ValueError("No se puede eliminar un decreto que tiene préstamos registrados. Por favor, elimine los préstamos asociados primero.")
    
        cursor.execute("UPDATE solicitudes_financiamiento SET estado = 'Pendiente', decreto_id = NULL WHERE decreto_id = ?", (decreto_id,))
        cursor.execute('DELETE FROM decretos WHERE id = ?', (decreto_id,))


def update_estado_decreto(decreto_id, estado):
    with db_session() as conn:
        cursor = conn.cursor()
        cursor.execute('UPDATE decretos SET estado = ? WHERE id = ?', (estado, decreto_id))

    # --- Cuotas CRUD ---


def check_estado_decreto(conn, decreto_id):
    cursor = conn.cursor()
    cursor.execute('SELECT estado FROM decretos WHERE id = ?', (decreto_id,))
    dec = cursor.fetchone()
    if not dec or dec['estado'] == 'Anulado':
        return

    cursor.execute('SELECT SUM(monto) as total FROM cuotas WHERE decreto_id = ?', (decreto_id,))
    total_proyectado = cursor.fetchone()['total'] or 0
    
    cursor.execute('''
        SELECT SUM(c.monto) as total 
        FROM cobros c 
        JOIN cuotas cu ON c.cuota_id = cu.id 
        WHERE cu.decreto_id = ?
    ''', (decreto_id,))
    total_cobrado = cursor.fetchone()['total'] or 0

    if total_cobrado >= (total_proyectado - TOLERANCE) and total_proyectado > 0:
        nuevo_estado = 'Terminado'
    else:
        # Check for overdue
        today = datetime.date.today()
        cursor.execute('SELECT id, mes, anio, monto FROM cuotas WHERE decreto_id = ?', (decreto_id,))
        cuotas = cursor.fetchall()
        
        tiene_deuda_atrasada = False
        for q in cuotas:
            cursor.execute('SELECT SUM(monto) as cobrado FROM cobros WHERE cuota_id = ?', (q['id'],))
            cobrado = cursor.fetchone()['cobrado'] or 0
            if (q['monto'] - cobrado) > TOLERANCE:
                due_date = get_due_date(q['mes'], q['anio'])
                if today > due_date:
                    tiene_deuda_atrasada = True
                    break
        
        nuevo_estado = 'Con deuda' if tiene_deuda_atrasada else 'Vigente'

    cursor.execute('UPDATE decretos SET estado = ? WHERE id = ?', (nuevo_estado, decreto_id))


def check_estado_decreto_by_cuota(conn, cuota_id):
    cursor = conn.cursor()
    cursor.execute('SELECT decreto_id FROM cuotas WHERE id = ?', (cuota_id,))
    row = cursor.fetchone()
    if row:
        check_estado_decreto(conn, row['decreto_id'])


def add_cuota(decreto_id, mes, anio, monto):
    if monto <= 0:
        raise ValueError("El monto de la cuota debe ser mayor a 0.")
    if not (1 <= mes <= 12):
        raise ValueError("El mes debe estar entre 1 y 12.")
    with db_session() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO cuotas (decreto_id, mes, anio, monto)
            VALUES (?, ?, ?, ?)
        ''', (decreto_id, mes, anio, monto))
        cuota_id = cursor.lastrowid
        return cuota_id


def get_cuotas_by_decreto(decreto_id):
    with db_session() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM cuotas WHERE decreto_id = ? ORDER BY anio ASC, mes ASC', (decreto_id,))
        rows = cursor.fetchall()
        return [dict(ix) for ix in rows]


def get_cuota(cuota_id):
    with db_session() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM cuotas WHERE id = ?', (cuota_id,))
        row = cursor.fetchone()
        return dict(row) if row else None


def get_total_cobrado_por_cuota(cuota_id):
    with db_session() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT SUM(monto) as cobrado FROM cobros WHERE cuota_id = ?', (cuota_id,))
        c_row = cursor.fetchone()
        return c_row['cobrado'] if c_row and c_row['cobrado'] else 0.0


def update_cuota_estimacion(cuota_id, fecha_estimada):
    with db_session() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            UPDATE cuotas SET fecha_estimada_cobro = ? WHERE id = ?
        ''', (fecha_estimada, cuota_id))

    # --- Cobros CRUD ---


def get_due_date(mes, anio):
    if not mes or not anio:
        return None
    _, last_day = calendar.monthrange(int(anio), int(mes))
    return datetime.date(int(anio), int(mes), last_day)


def get_decretos_by_obra(obra_id):
    with db_session() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT d.*
            FROM decretos d
            JOIN decretos_obras do ON do.decreto_id = d.id
            WHERE do.obra_id = ?
            ORDER BY d.anio DESC, d.nro_decreto DESC
        ''', (obra_id,))
        rows = cursor.fetchall()
        return [dict(ix) for ix in rows]


def get_obras_by_decreto(decreto_id):
    with db_session() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT o.*, p.razon_social as proveedor_razon_social
            FROM obras o
            JOIN decretos_obras do ON do.obra_id = o.id
            LEFT JOIN proveedores_obras p ON o.proveedor_id = p.id
            WHERE do.decreto_id = ?
            ORDER BY o.nombre ASC
        ''', (decreto_id,))
        rows = cursor.fetchall()
        return [dict(ix) for ix in rows]


def add_decreto_obras(decreto_id, obra_ids):
    with db_session() as conn:
        cursor = conn.cursor()
        cursor.execute('DELETE FROM decretos_obras WHERE decreto_id = ?', (decreto_id,))
        for o_id in obra_ids:
            cursor.execute('INSERT INTO decretos_obras (decreto_id, obra_id) VALUES (?, ?)', (decreto_id, o_id))

def update_decreto_details_for_solicitud(decreto_id, nro_expediente, destino_fondos, pdf_path, expediente_imuh):
    with db_session() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            UPDATE decretos
            SET nro_expediente = ?, destino_fondos = ?, pdf_path = ?, expediente_imuh = ?
            WHERE id = ?
        ''', (nro_expediente, destino_fondos, pdf_path, expediente_imuh, decreto_id))

def add_solicitud(nro_expediente, expediente_imuh, destino_fondos, monto_solicitado, fecha_solicitud, pdf_path=None, notas=None, obra_id=None):
    if not nro_expediente or not str(nro_expediente).strip():
        raise ValueError("El número de expediente no puede estar vacío.")
    # Si no se proveen destino_fondos/expediente_imuh o están vacíos, y hay obra_id, autocompletar con los datos de la obra
    if obra_id and (not destino_fondos or not str(destino_fondos).strip()):
        obra = get_obra(obra_id)
        if obra:
            destino_fondos = obra['nombre']
            expediente_imuh = obra['expediente_imuh']
            
    if not destino_fondos or not str(destino_fondos).strip():
        raise ValueError("El destino de fondos no puede estar vacío.")
    if monto_solicitado <= 0:
        raise ValueError("El monto solicitado debe ser mayor a 0.")
    with db_session() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO solicitudes_financiamiento (nro_expediente, expediente_imuh, destino_fondos, monto_solicitado, fecha_solicitud, pdf_path, notas, estado, obra_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, 'Pendiente', ?)
        ''', (nro_expediente, expediente_imuh, destino_fondos, monto_solicitado, fecha_solicitud, pdf_path, notas, obra_id))
        solicitud_id = cursor.lastrowid

        return solicitud_id


def update_solicitud(solicitud_id, nro_expediente, expediente_imuh, destino_fondos, monto_solicitado, fecha_solicitud, pdf_path=None, notas=None, obra_id=None):
    if not nro_expediente or not str(nro_expediente).strip():
        raise ValueError("El número de expediente no puede estar vacío.")
    # Si no se proveen destino_fondos/expediente_imuh o están vacíos, y hay obra_id, autocompletar con los datos de la obra
    if obra_id and (not destino_fondos or not str(destino_fondos).strip()):
        obra = get_obra(obra_id)
        if obra:
            destino_fondos = obra['nombre']
            expediente_imuh = obra['expediente_imuh']
            
    if not destino_fondos or not str(destino_fondos).strip():
        raise ValueError("El destino de fondos no puede estar vacío.")
    if monto_solicitado <= 0:
        raise ValueError("El monto solicitado debe ser mayor a 0.")
    with db_session() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            UPDATE solicitudes_financiamiento
            SET nro_expediente = ?, expediente_imuh = ?, destino_fondos = ?, monto_solicitado = ?, fecha_solicitud = ?, pdf_path = ?, notas = ?, obra_id = ?
            WHERE id = ?
        ''', (nro_expediente, expediente_imuh, destino_fondos, monto_solicitado, fecha_solicitud, pdf_path, notas, obra_id, solicitud_id))

def delete_solicitud(solicitud_id):
    with db_session() as conn:
        cursor = conn.cursor()
        cursor.execute('DELETE FROM solicitudes_financiamiento WHERE id = ?', (solicitud_id,))

def get_solicitudes():
    with db_session() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT s.*, d.nro_decreto, d.anio as decreto_anio, o.nombre as obra_nombre, o.expediente_imuh as obra_expediente
            FROM solicitudes_financiamiento s
            LEFT JOIN decretos d ON s.decreto_id = d.id
            LEFT JOIN obras o ON s.obra_id = o.id
            ORDER BY s.fecha_solicitud DESC, s.id DESC
        ''')
        rows = cursor.fetchall()
        return [dict(ix) for ix in rows]


def get_solicitud(solicitud_id):
    with db_session() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT s.*, d.nro_decreto, d.anio as decreto_anio
            FROM solicitudes_financiamiento s
            LEFT JOIN decretos d ON s.decreto_id = d.id
            WHERE s.id = ?
        ''', (solicitud_id,))
        row = cursor.fetchone()
        return dict(row) if row else None


def get_solicitud_por_decreto(decreto_id):
    with db_session() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM solicitudes_financiamiento WHERE decreto_id = ?', (decreto_id,))
        row = cursor.fetchone()
        return dict(row) if row else None


def update_estado_solicitud(solicitud_id, estado, decreto_id=None):
    with db_session() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            UPDATE solicitudes_financiamiento
            SET estado = ?, decreto_id = ?
            WHERE id = ?
        ''', (estado, decreto_id, solicitud_id))

    # --- NUEVOS CRUDs PARA FIN ORIGINAL USOS Y MODIFICACIONES ---


def get_obras_sin_solicitud():
    with db_session() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT o.*
            FROM obras o
            WHERE o.activa = 1 AND o.id NOT IN (
                SELECT DISTINCT obra_id FROM solicitudes_financiamiento WHERE obra_id IS NOT NULL
            )
            ORDER BY o.nombre ASC
        ''')
        rows = cursor.fetchall()
        return [dict(ix) for ix in rows]


def add_prestamo(decreto_origen_id, destino, monto, fecha, motivo=None):
    if monto <= 0:
        raise ValueError("El monto del préstamo debe ser mayor a 0.")
    fecha_dt = datetime.datetime.strptime(fecha, '%Y-%m-%d').date()
    if fecha_dt > datetime.date.today():
        raise ValueError("La fecha del préstamo no puede ser futura.")
        
    with db_session() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO prestamos_internos (decreto_origen_id, destino, monto, fecha, motivo, devolucion_estado)
            VALUES (?, ?, ?, ?, ?, 'Pendiente')
        ''', (decreto_origen_id, destino, monto, fecha, motivo))
        prestamo_id = cursor.lastrowid

        return prestamo_id


def delete_prestamo(prestamo_id):
    with db_session() as conn:
        cursor = conn.cursor()
        cursor.execute('DELETE FROM prestamos_internos WHERE id = ?', (prestamo_id,))

    # --- Distribución de Cobranzas (NUEVO) ---


def update_estado_prestamo(prestamo_id, estado, fecha_devolucion=None):
    with db_session() as conn:
        cursor = conn.cursor()
        if estado == 'Devuelto':
            if not fecha_devolucion:
                fecha_devolucion = datetime.date.today().strftime('%Y-%m-%d')
            cursor.execute('''
                UPDATE prestamos_internos 
                SET devolucion_estado = ?, fecha_devolucion = ?
                WHERE id = ?
            ''', (estado, fecha_devolucion, prestamo_id))
        else:
            cursor.execute('''
                UPDATE prestamos_internos 
                SET devolucion_estado = ?, fecha_devolucion = NULL
                WHERE id = ?
            ''', (estado, prestamo_id))

def get_prestamos(decreto_origen_id=None):
    with db_session() as conn:
        cursor = conn.cursor()
        if decreto_origen_id:
            cursor.execute('''
                SELECT p.*, d.nro_decreto, d.anio as decreto_anio, d.expediente_imuh,
                       COALESCE((SELECT SUM(monto) FROM recuperos_internos WHERE prestamo_id = p.id), 0) as total_devuelto
                FROM prestamos_internos p
                JOIN decretos d ON p.decreto_origen_id = d.id
                WHERE p.decreto_origen_id = ?
                ORDER BY p.fecha DESC
            ''', (decreto_origen_id,))
        else:
            cursor.execute('''
                SELECT p.*, d.nro_decreto, d.anio as decreto_anio, d.expediente_imuh,
                       COALESCE((SELECT SUM(monto) FROM recuperos_internos WHERE prestamo_id = p.id), 0) as total_devuelto
                FROM prestamos_internos p
                JOIN decretos d ON p.decreto_origen_id = d.id
                ORDER BY p.fecha DESC
            ''')
        rows = cursor.fetchall()
        return [dict(ix) for ix in rows]


def add_recupero(prestamo_id, monto, fecha):
    if monto <= 0:
        raise ValueError("El monto devuelto debe ser mayor a 0.")
    fecha_dt = datetime.datetime.strptime(fecha, '%Y-%m-%d').date()
    if fecha_dt > datetime.date.today():
        raise ValueError("La fecha de devolución no puede ser futura.")
        
    with db_session() as conn:
        cursor = conn.cursor()
    
        # Validar no devolver de más
        cursor.execute('SELECT monto, fecha FROM prestamos_internos WHERE id = ?', (prestamo_id,))
        p_row = cursor.fetchone()
        if not p_row:
            raise ValueError("Préstamo no encontrado.")
        monto_prestamo = p_row['monto']
        fecha_prestamo = p_row['fecha']
        
        if fecha < fecha_prestamo:
            raise ValueError(f"La fecha de devolución ({fecha}) no puede ser anterior a la fecha del préstamo ({fecha_prestamo}).")
    
        cursor.execute('SELECT SUM(monto) as cobrado FROM recuperos_internos WHERE prestamo_id = ?', (prestamo_id,))
        ya_devuelto = cursor.fetchone()['cobrado'] or 0
    
        if (monto + ya_devuelto) > (monto_prestamo + TOLERANCE):
             raise ValueError(f"El monto a devolver ({monto}) supera el saldo pendiente del préstamo ({monto_prestamo - ya_devuelto}).")
         
        cursor.execute('''
            INSERT INTO recuperos_internos (prestamo_id, monto, fecha)
            VALUES (?, ?, ?)
        ''', (prestamo_id, monto, fecha))
        recupero_id = cursor.lastrowid
    
        # Verificar si con esto se salda
        if (monto + ya_devuelto) >= (monto_prestamo - TOLERANCE):
            cursor.execute('''
                UPDATE prestamos_internos 
                SET devolucion_estado = 'Devuelto', fecha_devolucion = ?
                WHERE id = ?
            ''', (fecha, prestamo_id))
        else:
            cursor.execute('''
                UPDATE prestamos_internos 
                SET devolucion_estado = 'Pendiente', fecha_devolucion = NULL
                WHERE id = ?
            ''', (prestamo_id,))

        return recupero_id


def delete_recupero(recupero_id, prestamo_id):
    with db_session() as conn:
        cursor = conn.cursor()
        cursor.execute('DELETE FROM recuperos_internos WHERE id = ?', (recupero_id,))
        # Always set condition back to Pendiente if a recovery is deleted
        cursor.execute('''
            UPDATE prestamos_internos 
            SET devolucion_estado = 'Pendiente', fecha_devolucion = NULL
            WHERE id = ?
        ''', (prestamo_id,))
