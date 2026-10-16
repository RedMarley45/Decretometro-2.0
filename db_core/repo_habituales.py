"""
db_core/repo_habituales.py - Gestión de Aportes Habituales (Funcionamiento, Sueldos y SAC)
"""
import datetime
from db_core.connection import db_session

def set_monto_funcionamiento_anio(anio, monto_mensual):
    if anio > datetime.date.today().year:
        raise ValueError("No se pueden generar aportes para un año futuro.")
    if monto_mensual <= 0:
        raise ValueError("El monto mensual pautado debe ser mayor a 0.")
    with db_session() as conn:
        cursor = conn.cursor()
        cursor.execute('DELETE FROM aportes_funcionamiento WHERE anio = ? AND fecha_cobro IS NULL', (anio,))
        for mes in range(1, 13):
            cursor.execute('''
                INSERT INTO aportes_funcionamiento (anio, mes, monto_pautado)
                VALUES (?, ?, ?)
            ''', (anio, mes, monto_mensual))

def get_aportes_funcionamiento(anio=None):
    with db_session() as conn:
        cursor = conn.cursor()
        if anio:
            cursor.execute('SELECT * FROM aportes_funcionamiento WHERE anio = ? ORDER BY mes ASC', (anio,))
        else:
            cursor.execute('SELECT * FROM aportes_funcionamiento ORDER BY anio DESC, mes ASC')
        rows = cursor.fetchall()
        return [dict(ix) for ix in rows]


def registrar_cobro_funcionamiento(aporte_id, monto, fecha):
    if monto <= 0:
        raise ValueError("El monto cobrado debe ser mayor a 0.")
    fecha_dt = datetime.datetime.strptime(fecha, '%Y-%m-%d').date()
    if fecha_dt > datetime.date.today():
        raise ValueError("La fecha de cobro no puede ser futura.")
    with db_session() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT monto_pautado FROM aportes_funcionamiento WHERE id = ?', (aporte_id,))
        row = cursor.fetchone()
        if not row:
            raise ValueError("Aporte de funcionamiento no encontrado.")
        if monto > (row['monto_pautado'] + 0.01):
            raise ValueError(f"El monto cobrado ({monto:.2f}) supera el monto pautado mensual ({row['monto_pautado']:.2f}).")
            
        cursor.execute('''
            UPDATE aportes_funcionamiento 
            SET monto_cobrado = ?, fecha_cobro = ?
            WHERE id = ?
        ''', (monto, fecha, aporte_id))

def reset_cobro_funcionamiento(aporte_id):
    with db_session() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            UPDATE aportes_funcionamiento 
            SET monto_cobrado = 0, fecha_cobro = NULL
            WHERE id = ?
        ''', (aporte_id,))

def delete_anio_funcionamiento(anio):
    with db_session() as conn:
        cursor = conn.cursor()
        cursor.execute('DELETE FROM aportes_funcionamiento WHERE anio = ?', (anio,))

    # --- Aportes Sueldo ---


def add_aporte_sueldo(anio, mes, monto_pedido, fecha_pedido):
    if anio > datetime.date.today().year:
        raise ValueError("El año no puede ser futuro.")
    if not (1 <= mes <= 12):
        raise ValueError("El mes debe estar entre 1 y 12.")
    if monto_pedido <= 0:
        raise ValueError("El monto pedido debe ser mayor a 0.")
    try:
        datetime.datetime.strptime(fecha_pedido, '%Y-%m-%d')
    except ValueError:
        raise ValueError("La fecha del pedido debe ser válida y tener el formato YYYY-MM-DD.")
    with db_session() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO aportes_sueldo (anio, mes, monto_pedido, fecha_pedido)
            VALUES (?, ?, ?, ?)
        ''', (anio, mes, monto_pedido, fecha_pedido))

def get_aportes_sueldo(anio=None):
    with db_session() as conn:
        cursor = conn.cursor()
        if anio:
            cursor.execute('SELECT * FROM aportes_sueldo WHERE anio = ? ORDER BY mes ASC', (anio,))
        else:
            cursor.execute('SELECT * FROM aportes_sueldo ORDER BY anio DESC, mes ASC')
        rows = cursor.fetchall()
        return [dict(ix) for ix in rows]


def registrar_cobro_sueldo(aporte_id, monto, fecha):
    if monto <= 0:
        raise ValueError("El monto cobrado debe ser mayor a 0.")
    fecha_dt = datetime.datetime.strptime(fecha, '%Y-%m-%d').date()
    if fecha_dt > datetime.date.today():
        raise ValueError("La fecha de cobro no puede ser futura.")
    with db_session() as conn:
        cursor = conn.cursor()
        # Obtener pedido original
        cursor.execute('SELECT monto_pedido, monto_cobrado FROM aportes_sueldo WHERE id = ?', (aporte_id,))
        row = cursor.fetchone()
        if not row: 
            return
    
        nuevo_total = (row['monto_cobrado'] or 0) + monto
        total_pedido = row['monto_pedido']
        
        # Validar no sobrepagar
        if nuevo_total > (total_pedido + 0.01):
            raise ValueError(f"El monto acumulado cobrado ({nuevo_total:.2f}) superaría el pedido original ({total_pedido:.2f}).")
    
        # Determinar nuevo estado
        if nuevo_total >= (total_pedido - 0.01):
            estado = 'Cobrado'
        else:
            estado = 'Parcial'

        cursor.execute('''
            UPDATE aportes_sueldo 
            SET monto_cobrado = ?, fecha_cobro = ?, estado = ?
            WHERE id = ?
        ''', (nuevo_total, fecha, estado, aporte_id))

def delete_aporte_sueldo(aporte_id):
    with db_session() as conn:
        cursor = conn.cursor()
        cursor.execute('DELETE FROM aportes_sueldo WHERE id = ?', (aporte_id,))

def update_aporte_sueldo(aporte_id, anio, mes, monto_pedido, fecha_pedido):
    if anio > datetime.date.today().year:
        raise ValueError("El año no puede ser futuro.")
    if not (1 <= mes <= 12):
        raise ValueError("El mes debe estar entre 1 y 12.")
    if monto_pedido <= 0:
        raise ValueError("El monto pedido debe ser mayor a 0.")
    try:
        datetime.datetime.strptime(fecha_pedido, '%Y-%m-%d')
    except ValueError:
        raise ValueError("La fecha del pedido debe ser válida y tener el formato YYYY-MM-DD.")
    with db_session() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            UPDATE aportes_sueldo
            SET anio = ?, mes = ?, monto_pedido = ?, fecha_pedido = ?
            WHERE id = ?
        ''', (anio, mes, monto_pedido, fecha_pedido, aporte_id))

    # --- Aportes SAC ---


def renunciar_aporte_sueldo(aporte_id, fecha):
    with db_session() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            UPDATE aportes_sueldo 
            SET estado = 'Renunciado', fecha_renuncia = ?
            WHERE id = ?
        ''', (fecha, aporte_id))

def add_aporte_sac(anio, cuota_nro, monto_pedido, fecha_pedido):
    if anio > datetime.date.today().year:
        raise ValueError("El año no puede ser futuro.")
    if cuota_nro not in (1, 2):
        raise ValueError("La cuota de SAC solo puede ser 1 o 2.")
    if monto_pedido <= 0:
        raise ValueError("El monto pedido debe ser mayor a 0.")
    try:
        datetime.datetime.strptime(fecha_pedido, '%Y-%m-%d')
    except ValueError:
        raise ValueError("La fecha del pedido debe ser válida y tener el formato YYYY-MM-DD.")
    with db_session() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO aportes_sac (anio, cuota_nro, monto_pedido, fecha_pedido)
            VALUES (?, ?, ?, ?)
        ''', (anio, cuota_nro, monto_pedido, fecha_pedido))

def get_aportes_sac(anio=None):
    with db_session() as conn:
        cursor = conn.cursor()
        if anio:
            cursor.execute('SELECT * FROM aportes_sac WHERE anio = ? ORDER BY cuota_nro ASC', (anio,))
        else:
            cursor.execute('SELECT * FROM aportes_sac ORDER BY anio DESC, cuota_nro ASC')
        rows = cursor.fetchall()
        return [dict(ix) for ix in rows]


def registrar_cobro_sac(aporte_id, monto, fecha):
    if monto <= 0:
        raise ValueError("El monto cobrado debe ser mayor a 0.")
    fecha_dt = datetime.datetime.strptime(fecha, '%Y-%m-%d').date()
    if fecha_dt > datetime.date.today():
        raise ValueError("La fecha de cobro no puede ser futura.")
    with db_session() as conn:
        cursor = conn.cursor()
        # Obtener pedido original
        cursor.execute('SELECT monto_pedido, monto_cobrado FROM aportes_sac WHERE id = ?', (aporte_id,))
        row = cursor.fetchone()
        if not row: 
            return
    
        nuevo_total = (row['monto_cobrado'] or 0) + monto
        total_pedido = row['monto_pedido']
        
        # Validar no sobrepagar
        if nuevo_total > (total_pedido + 0.01):
            raise ValueError(f"El monto acumulado cobrado ({nuevo_total:.2f}) superaría el pedido original ({total_pedido:.2f}).")
    
        # Determinar nuevo estado
        if nuevo_total >= (total_pedido - 0.01):
            estado = 'Cobrado'
        else:
            estado = 'Parcial'

        cursor.execute('''
            UPDATE aportes_sac 
            SET monto_cobrado = ?, fecha_cobro = ?, estado = ?
            WHERE id = ?
        ''', (nuevo_total, fecha, estado, aporte_id))

def delete_aporte_sac(aporte_id):
    with db_session() as conn:
        cursor = conn.cursor()
        cursor.execute('DELETE FROM aportes_sac WHERE id = ?', (aporte_id,))

def update_aporte_sac(aporte_id, anio, cuota_nro, monto_pedido, fecha_pedido):
    if anio > datetime.date.today().year:
        raise ValueError("El año no puede ser futuro.")
    if cuota_nro not in (1, 2):
        raise ValueError("La cuota de SAC solo puede ser 1 o 2.")
    if monto_pedido <= 0:
        raise ValueError("El monto pedido debe ser mayor a 0.")
    try:
        datetime.datetime.strptime(fecha_pedido, '%Y-%m-%d')
    except ValueError:
        raise ValueError("La fecha del pedido debe ser válida y tener el formato YYYY-MM-DD.")
    with db_session() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            UPDATE aportes_sac
            SET anio = ?, cuota_nro = ?, monto_pedido = ?, fecha_pedido = ?
            WHERE id = ?
        ''', (anio, cuota_nro, monto_pedido, fecha_pedido, aporte_id))

    # --- Lógica de Negocio ---


def renunciar_aporte_sac(aporte_id, fecha):
    with db_session() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            UPDATE aportes_sac 
            SET estado = 'Renunciado', fecha_renuncia = ?
            WHERE id = ?
        ''', (fecha, aporte_id))

    # --- Solicitudes de Financiamiento CRUD ---


