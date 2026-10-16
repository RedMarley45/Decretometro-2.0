"""
db_core/repo_catalogos.py - Monedas, Cotizaciones Históricas, Proveedores y Gastos de Funcionamiento
"""
import sqlite3
import utils
from db_core.connection import db_session, TOLERANCE

def get_monedas_indices(solo_activas=False):
    with db_session() as conn:
        cursor = conn.cursor()
        query = 'SELECT * FROM monedas_indices'
        if solo_activas:
            query += ' WHERE activo = 1'
        query += ' ORDER BY id ASC'
        cursor.execute(query)
        rows = cursor.fetchall()
        return [dict(ix) for ix in rows]


def get_moneda_indice(moneda_id):
    with db_session() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM monedas_indices WHERE id = ?', (moneda_id,))
        row = cursor.fetchone()
        return dict(row) if row else None


def add_moneda_indice(codigo, nombre, simbolo, tipo='Moneda', decimales=2):
    if not codigo or not codigo.strip():
        raise ValueError("El código de la moneda/índice no puede estar vacío.")
    if not nombre or not nombre.strip():
        raise ValueError("El nombre no puede estar vacío.")
    if not simbolo or not simbolo.strip():
        raise ValueError("El símbolo no puede estar vacío.")
    if tipo not in ('Moneda', 'Índice'):
        raise ValueError("El tipo debe ser 'Moneda' o 'Índice'.")

    codigo_clean = codigo.strip().upper()
    nombre_clean = nombre.strip()
    simbolo_clean = simbolo.strip()

    with db_session() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT id FROM monedas_indices WHERE UPPER(codigo) = ?', (codigo_clean,))
        if cursor.fetchone():
            raise ValueError(f"Ya existe una moneda o índice con el código '{codigo_clean}'.")

        cursor.execute('''
            INSERT INTO monedas_indices (codigo, nombre, simbolo, tipo, decimales, activo)
            VALUES (?, ?, ?, ?, ?, 1)
        ''', (codigo_clean, nombre_clean, simbolo_clean, tipo, int(decimales)))

        return cursor.lastrowid


def update_moneda_indice(moneda_id, codigo, nombre, simbolo, tipo, decimales, activo):
    if not codigo or not codigo.strip():
        raise ValueError("El código de la moneda/índice no puede estar vacío.")
    if not nombre or not nombre.strip():
        raise ValueError("El nombre no puede estar vacío.")
    if not simbolo or not simbolo.strip():
        raise ValueError("El símbolo no puede estar vacío.")
    if tipo not in ('Moneda', 'Índice'):
        raise ValueError("El tipo debe ser 'Moneda' o 'Índice'.")

    codigo_clean = codigo.strip().upper()
    with db_session() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT id FROM monedas_indices WHERE UPPER(codigo) = ? AND id != ?', (codigo_clean, moneda_id))
        if cursor.fetchone():
            raise ValueError(f"Ya existe otra moneda con el código '{codigo_clean}'.")

        cursor.execute('''
            UPDATE monedas_indices
            SET codigo = ?, nombre = ?, simbolo = ?, tipo = ?, decimales = ?, activo = ?
            WHERE id = ?
        ''', (codigo_clean, nombre.strip(), simbolo.strip(), tipo, int(decimales), 1 if activo else 0, moneda_id))

def get_ultima_cotizacion(moneda_id):
    """Retorna la cotización más reciente registrada para la moneda especificada,
    o None si aún no se ha registrado ninguna cotización mayor a 1.0.
    """
    info = get_ultima_cotizacion_info(moneda_id)
    return info['cotizacion'] if info else None


def get_ultima_cotizacion_info(moneda_id):
    """Retorna información detallada de la cotización más reciente registrada para la moneda especificada:
    {'cotizacion': float, 'fecha': str, 'origen': str} o None si no hay registros.
    """
    if moneda_id == 1:
        return {'cotizacion': 1.0, 'fecha': str(datetime.date.today()), 'origen': 'Moneda Base (ARS)'}
    with db_session() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT cotizacion, fecha, origen FROM (
                SELECT fu.cotizacion_pago as cotizacion, fu.fecha, 'Pago Fin Original' as origen
                FROM cobro_fin_original_usos fu
                JOIN obras o ON fu.obra_id = o.id
                WHERE o.moneda_id = ? AND fu.cotizacion_pago IS NOT NULL AND fu.cotizacion_pago > 1.0
                UNION ALL
                SELECT pfp.cotizacion_pago as cotizacion, pfp.fecha, 'Pago Fondos Propios' as origen
                FROM pagos_fondos_propios pfp
                JOIN obras o ON pfp.obra_id = o.id
                WHERE o.moneda_id = ? AND pfp.cotizacion_pago IS NOT NULL AND pfp.cotizacion_pago > 1.0
                UNION ALL
                SELECT c.cotizacion_cobro as cotizacion, c.fecha, 'Cobro Convenio/Decreto' as origen
                FROM cobros c
                WHERE c.moneda_origen_id = ? AND c.cotizacion_cobro IS NOT NULL AND c.cotizacion_cobro > 1.0
                UNION ALL
                SELECT cs.cotizacion_solicitud as cotizacion, cs.fecha_solicitud as fecha, 'Solicitud Certificado' as origen
                FROM convenio_solicitudes cs
                JOIN convenios cv ON cs.convenio_id = cv.id
                WHERE cv.moneda_id = ? AND cs.cotizacion_solicitud IS NOT NULL AND cs.cotizacion_solicitud > 1.0
            ) ORDER BY fecha DESC, cotizacion DESC LIMIT 1
        ''', (moneda_id, moneda_id, moneda_id, moneda_id))
        r = cursor.fetchone()
        if r:
            return {'cotizacion': float(r['cotizacion']), 'fecha': str(r['fecha']), 'origen': str(r['origen'])}
        return None


def add_proveedor_obra(razon_social, cuit):
    if not razon_social or not str(razon_social).strip():
        raise ValueError("La Razón Social no puede estar vacía.")
    import utils
    if not utils.validar_cuit(cuit):
        raise ValueError("El CUIT no tiene un formato AFIP válido (Ej: 20-12345678-9).")
    
    razon_social = razon_social.strip()
    cuit = cuit.strip()
    
    with db_session() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT id FROM proveedores_obras WHERE LOWER(razon_social) = LOWER(?)', (razon_social,))
        if cursor.fetchone():
            raise ValueError(f"Ya existe un proveedor de obra con la razón social '{razon_social}'.")
        cursor.execute('SELECT id FROM proveedores_obras WHERE cuit = ?', (cuit,))
        if cursor.fetchone():
            raise ValueError(f"Ya existe un proveedor de obra con el CUIT '{cuit}'.")
            
        cursor.execute('''
            INSERT INTO proveedores_obras (razon_social, cuit, activo)
            VALUES (?, ?, 1)
        ''', (razon_social, cuit))
        prov_id = cursor.lastrowid

        return prov_id


def get_proveedores_obras(only_active=False):
    with db_session() as conn:
        cursor = conn.cursor()
        query = 'SELECT * FROM proveedores_obras'
        if only_active:
            query += ' WHERE activo = 1'
        query += ' ORDER BY razon_social ASC'
        cursor.execute(query)
        return [dict(r) for r in cursor.fetchall()]


def get_proveedor_obra(prov_id):
    if not prov_id:
        return None
    with db_session() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM proveedores_obras WHERE id = ?', (prov_id,))
        row = cursor.fetchone()
        return dict(row) if row else None


def update_proveedor_obra(prov_id, razon_social, cuit, activo=1):
    if not razon_social or not str(razon_social).strip():
        raise ValueError("La Razón Social no puede estar vacía.")
    import utils
    if not utils.validar_cuit(cuit):
        raise ValueError("El CUIT no tiene un formato AFIP válido (Ej: 20-12345678-9).")
        
    razon_social = razon_social.strip()
    cuit = cuit.strip()
    
    with db_session() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT id FROM proveedores_obras WHERE LOWER(razon_social) = LOWER(?) AND id != ?', (razon_social, prov_id))
        if cursor.fetchone():
            raise ValueError(f"Ya existe otro proveedor de obra registrado con la razón social '{razon_social}'.")
        cursor.execute('SELECT id FROM proveedores_obras WHERE cuit = ? AND id != ?', (cuit, prov_id))
        if cursor.fetchone():
            raise ValueError(f"Ya existe otro proveedor de obra registrado con el CUIT '{cuit}'.")
            
        cursor.execute('''
            UPDATE proveedores_obras
            SET razon_social = ?, cuit = ?, activo = ?
            WHERE id = ?
        ''', (razon_social, cuit, activo, prov_id))

def update_proveedor_obra_estado(prov_id, activo):
    with db_session() as conn:
        cursor = conn.cursor()
        cursor.execute('UPDATE proveedores_obras SET activo = ? WHERE id = ?', (activo, prov_id))

def delete_proveedor_obra(prov_id):
    with db_session() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT COUNT(*) as cnt FROM obras WHERE proveedor_id = ?', (prov_id,))
        if cursor.fetchone()['cnt'] > 0:
            raise ValueError("No se puede eliminar el proveedor porque está vinculado a una o más obras.")
        cursor.execute('DELETE FROM proveedores_obras WHERE id = ?', (prov_id,))

def add_proveedor_funcionamiento(razon_social, cuit):
    if not razon_social or not str(razon_social).strip():
        raise ValueError("La Razón Social no puede estar vacía.")
    import utils
    if not utils.validar_cuit(cuit):
        raise ValueError("El CUIT no tiene un formato AFIP válido (Ej: 20-12345678-9).")
        
    razon_social = razon_social.strip()
    cuit = cuit.strip()
    
    with db_session() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT id FROM proveedores_funcionamiento WHERE LOWER(razon_social) = LOWER(?)', (razon_social,))
        if cursor.fetchone():
            raise ValueError(f"Ya existe un proveedor de funcionamiento con la razón social '{razon_social}'.")
        cursor.execute('SELECT id FROM proveedores_funcionamiento WHERE cuit = ?', (cuit,))
        if cursor.fetchone():
            raise ValueError(f"Ya existe un proveedor de funcionamiento con el CUIT '{cuit}'.")
            
        cursor.execute('''
            INSERT INTO proveedores_funcionamiento (razon_social, cuit, activo)
            VALUES (?, ?, 1)
        ''', (razon_social, cuit))
        prov_id = cursor.lastrowid

        return prov_id


def get_proveedores_funcionamiento(only_active=False):
    with db_session() as conn:
        cursor = conn.cursor()
        query = 'SELECT * FROM proveedores_funcionamiento'
        if only_active:
            query += ' WHERE activo = 1'
        query += ' ORDER BY razon_social ASC'
        cursor.execute(query)
        return [dict(r) for r in cursor.fetchall()]


def get_proveedor_funcionamiento(prov_id):
    if not prov_id:
        return None
    with db_session() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM proveedores_funcionamiento WHERE id = ?', (prov_id,))
        row = cursor.fetchone()
        return dict(row) if row else None


def update_proveedor_funcionamiento(prov_id, razon_social, cuit, activo=1):
    if not razon_social or not str(razon_social).strip():
        raise ValueError("La Razón Social no puede estar vacía.")
    import utils
    if not utils.validar_cuit(cuit):
        raise ValueError("El CUIT no tiene un formato AFIP válido (Ej: 20-12345678-9).")
        
    razon_social = razon_social.strip()
    cuit = cuit.strip()
    
    with db_session() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT id FROM proveedores_funcionamiento WHERE LOWER(razon_social) = LOWER(?) AND id != ?', (razon_social, prov_id))
        if cursor.fetchone():
            raise ValueError(f"Ya existe otro proveedor de funcionamiento registrado con la razón social '{razon_social}'.")
        cursor.execute('SELECT id FROM proveedores_funcionamiento WHERE cuit = ? AND id != ?', (cuit, prov_id))
        if cursor.fetchone():
            raise ValueError(f"Ya existe otro proveedor de funcionamiento registrado con el CUIT '{cuit}'.")
            
        cursor.execute('''
            UPDATE proveedores_funcionamiento
            SET razon_social = ?, cuit = ?, activo = ?
            WHERE id = ?
        ''', (razon_social, cuit, activo, prov_id))

def update_proveedor_funcionamiento_estado(prov_id, activo):
    with db_session() as conn:
        cursor = conn.cursor()
        cursor.execute('UPDATE proveedores_funcionamiento SET activo = ? WHERE id = ?', (activo, prov_id))

def delete_proveedor_funcionamiento(prov_id):
    with db_session() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT COUNT(*) as cnt FROM gastos_funcionamiento WHERE proveedor_id = ?', (prov_id,))
        if cursor.fetchone()['cnt'] > 0:
            raise ValueError("No se puede eliminar el proveedor porque está vinculado a uno o más gastos de funcionamiento.")
        cursor.execute('DELETE FROM proveedores_funcionamiento WHERE id = ?', (prov_id,))

def get_todos_proveedores(only_active=False):
    """Retorna listado unificado de proveedores (Obra y Funcionamiento) ordenados alfabéticamente por Razón Social."""
    with db_session() as conn:
        cursor = conn.cursor()
        provs = []
        
        # 1. Obras
        q_obras = 'SELECT id, razon_social, cuit, activo FROM proveedores_obras'
        if only_active:
            q_obras += ' WHERE activo = 1'
        cursor.execute(q_obras)
        for r in cursor.fetchall():
            pid = r['id']
            cursor.execute('SELECT COUNT(*) as cnt FROM obras WHERE proveedor_id = ?', (pid,))
            is_linked = cursor.fetchone()['cnt'] > 0
            provs.append({
                'id': pid,
                'razon_social': r['razon_social'],
                'cuit': r['cuit'],
                'tipo': 'Obra',
                'activo': r['activo'],
                'is_linked': is_linked
            })
            
        # 2. Funcionamiento
        q_fun = 'SELECT id, razon_social, cuit, activo FROM proveedores_funcionamiento'
        if only_active:
            q_fun += ' WHERE activo = 1'
        cursor.execute(q_fun)
        for r in cursor.fetchall():
            pid = r['id']
            cursor.execute('SELECT COUNT(*) as cnt FROM gastos_funcionamiento WHERE proveedor_id = ?', (pid,))
            is_linked = cursor.fetchone()['cnt'] > 0
            provs.append({
                'id': pid,
                'razon_social': r['razon_social'],
                'cuit': r['cuit'],
                'tipo': 'Funcionamiento',
                'activo': r['activo'],
                'is_linked': is_linked
            })
            
        provs.sort(key=lambda x: x['razon_social'].lower())
        return provs


def add_gasto_funcionamiento(nombre, expediente_imuh, proveedor_id=None):
    nombre = nombre.strip()
    expediente_imuh = utils.normalizar_expediente_imuh(expediente_imuh.strip())
    if not nombre:
        raise ValueError("El nombre del Gasto FUN no puede estar vacío.")
    if not utils.validar_expediente_imuh(expediente_imuh):
        raise ValueError("El expediente municipal/IMUH no tiene un formato válido (Ej: 8000000-I-2026).")
        
    with db_session() as conn:
        cursor = conn.cursor()
        try:
            cursor.execute('''
                INSERT INTO gastos_funcionamiento (nombre, expediente_imuh, activo, proveedor_id)
                VALUES (?, ?, 1, ?)
            ''', (nombre, expediente_imuh, proveedor_id))
            gasto_id = cursor.lastrowid
            return gasto_id
        except sqlite3.IntegrityError:
            cursor.execute('SELECT * FROM gastos_funcionamiento WHERE expediente_imuh = ?', (expediente_imuh,))
            row = cursor.fetchone()
            if row:
                cursor.execute('UPDATE gastos_funcionamiento SET nombre = ?, activo = 1, proveedor_id = COALESCE(?, proveedor_id) WHERE id = ?', (nombre, proveedor_id, row['id']))
                return row['id']
            raise ValueError(f"Ya existe un Gasto FUN con el expediente {expediente_imuh}.")


def get_gastos_funcionamiento(only_active=False):
    with db_session() as conn:
        cursor = conn.cursor()
        query = '''
            SELECT g.*, p.razon_social as proveedor_razon_social, p.cuit as proveedor_cuit
            FROM gastos_funcionamiento g
            LEFT JOIN proveedores_funcionamiento p ON g.proveedor_id = p.id
        '''
        if only_active:
            query += ' WHERE g.activo = 1'
        query += ' ORDER BY g.nombre ASC'
        cursor.execute(query)
        rows = cursor.fetchall()
        return [dict(ix) for ix in rows]


def get_gasto_funcionamiento(gasto_id):
    with db_session() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT g.*, p.razon_social as proveedor_razon_social, p.cuit as proveedor_cuit
            FROM gastos_funcionamiento g
            LEFT JOIN proveedores_funcionamiento p ON g.proveedor_id = p.id
            WHERE g.id = ?
        ''', (gasto_id,))
        row = cursor.fetchone()
        return dict(row) if row else None


def get_gasto_funcionamiento_by_expediente(expediente_imuh):
    with db_session() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT g.*, p.razon_social as proveedor_razon_social, p.cuit as proveedor_cuit
            FROM gastos_funcionamiento g
            LEFT JOIN proveedores_funcionamiento p ON g.proveedor_id = p.id
            WHERE g.expediente_imuh = ?
        ''', (expediente_imuh,))
        row = cursor.fetchone()
        return dict(row) if row else None


def update_gasto_funcionamiento(gasto_id, nombre, expediente_imuh, proveedor_id=None):
    """Actualiza nombre, expediente y proveedor de un Gasto FUN.
    Si cambia el expediente, actualiza en cascada el historial de desvíos y usos de reserva."""
    import utils as _utils
    nombre = nombre.strip()[:50]
    if not nombre:
        raise ValueError("El nombre del Gasto FUN no puede estar vacío.")
    exp_norm = _utils.normalizar_expediente_imuh(expediente_imuh.strip()) if expediente_imuh else None
    if not exp_norm or not _utils.validar_expediente_imuh(exp_norm):
        raise ValueError("El Nro. de Expediente IMUH no tiene un formato válido (Ej: 80001234-I-2026).")

    with db_session() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT id FROM gastos_funcionamiento WHERE expediente_imuh = ? AND id != ?', (exp_norm, gasto_id))
        if cursor.fetchone():
            raise ValueError(f"Ya existe otro Gasto de Funcionamiento con el expediente IMUH '{exp_norm}'.")

        cursor.execute('SELECT expediente_imuh FROM gastos_funcionamiento WHERE id = ?', (gasto_id,))
        row = cursor.fetchone()
        exp_anterior = row['expediente_imuh'] if row else None

        cursor.execute('''
            UPDATE gastos_funcionamiento
            SET nombre = ?, expediente_imuh = ?, proveedor_id = ?
            WHERE id = ?
        ''', (nombre, exp_norm, proveedor_id, gasto_id))

        if exp_anterior and exp_anterior != exp_norm:
            cursor.execute('''
                UPDATE cobro_desvios SET gasto_expediente_imuh = ?, gasto_nombre = ?
                WHERE gasto_expediente_imuh = ?
            ''', (exp_norm, nombre, exp_anterior))
            cursor.execute('''
                UPDATE cobro_reserva_usos SET gasto_expediente_imuh = ?, gasto_nombre = ?
                WHERE gasto_expediente_imuh = ?
            ''', (exp_norm, nombre, exp_anterior))

def update_gasto_funcionamiento_estado(gasto_id, activo):
    if activo not in [0, 1]:
        raise ValueError("El estado activo debe ser 0 o 1.")
    with db_session() as conn:
        cursor = conn.cursor()
        cursor.execute('UPDATE gastos_funcionamiento SET activo = ? WHERE id = ?', (activo, gasto_id))


def update_gasto_funcionamiento_proveedor(gasto_id, proveedor_id):
    with db_session() as conn:
        cursor = conn.cursor()
        cursor.execute('UPDATE gastos_funcionamiento SET proveedor_id = ? WHERE id = ?', (proveedor_id, gasto_id))


def delete_gasto_funcionamiento(gasto_id):
    """Elimina un Gasto FUN, siempre que no tenga desvíos o usos de reserva asociados."""
    with db_session() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT expediente_imuh FROM gastos_funcionamiento WHERE id = ?', (gasto_id,))
        row = cursor.fetchone()
        if not row:
            raise ValueError("No se encontró el Gasto de Funcionamiento.")
        exp = row['expediente_imuh']

        cursor.execute('SELECT COUNT(*) as cnt FROM cobro_desvios WHERE gasto_expediente_imuh = ?', (exp,))
        if cursor.fetchone()['cnt'] > 0:
            raise ValueError("No se puede eliminar este Gasto porque tiene desvíos asociados. Puede inhabilitarlo en su lugar.")

        cursor.execute('SELECT COUNT(*) as cnt FROM cobro_reserva_usos WHERE gasto_expediente_imuh = ?', (exp,))
        if cursor.fetchone()['cnt'] > 0:
            raise ValueError("No se puede eliminar este Gasto porque tiene usos de reserva asociados. Puede inhabilitarlo en su lugar.")

        cursor.execute('DELETE FROM gastos_funcionamiento WHERE id = ?', (gasto_id,))
