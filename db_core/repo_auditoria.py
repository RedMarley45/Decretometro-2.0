"""
db_core/repo_auditoria.py - Auditoría Forense, Trazabilidad de OPs Bejerman y Validaciones de Asientos
"""
from db_core.connection import db_session, get_connection


def _validar_op_o_nota_db(nro_op, notas, contexto="movimiento"):
    """Validación a nivel de base de datos para asegurar integridad documental."""
    op_limpia = str(nro_op).strip() if nro_op else ""
    if not op_limpia:
        notas_limpias = str(notas).strip() if notas else ""
        if len(notas_limpias) < 10 or len(notas_limpias) > 30:
            raise ValueError(f"Para registrar un {contexto} sin N° de OP, debe ingresar una Nota/Motivo explicativo de entre 10 y 30 caracteres (actual: {len(notas_limpias)}).")


def get_op_info(nro_op):
    with db_session() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM op_bejerman WHERE nro_op = ?', (str(nro_op).strip(),))
        row = cursor.fetchone()
        return dict(row) if row else None


def get_op_usage_count(nro_op):
    nro_op_str = str(nro_op).strip()
    if not nro_op_str:
        return 0
    with db_session() as conn:
        cursor = conn.cursor()
        count = 0
        cursor.execute("SELECT COUNT(*) FROM cobro_fin_original_usos WHERE nro_op = ?", (nro_op_str,))
        count += cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM cobro_desvios WHERE nro_op = ?", (nro_op_str,))
        count += cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM cobro_desvios_recuperos WHERE nro_op = ?", (nro_op_str,))
        count += cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM cobro_reserva_usos_recuperos WHERE nro_op = ?", (nro_op_str,))
        count += cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM cobro_reserva_usos WHERE nro_op = ?", (nro_op_str,))
        count += cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM pagos_fondos_propios WHERE nro_op = ?", (nro_op_str,))
        count += cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM recuperos_fondos_propios WHERE nro_op = ?", (nro_op_str,))
        count += cursor.fetchone()[0]
        return count


def get_op_usage_details(nro_op):
    nro_op_str = str(nro_op).strip()
    if not nro_op_str:
        return []
    usages = []
    with db_session() as conn:
        cursor = conn.cursor()
        
        cursor.execute("SELECT monto, fecha FROM cobro_fin_original_usos WHERE nro_op = ?", (nro_op_str,))
        for row in cursor.fetchall():
            usages.append({'origen': 'Fin Original', 'monto': row['monto'], 'fecha': row['fecha']})
            
        cursor.execute("SELECT monto, fecha FROM cobro_desvios WHERE nro_op = ?", (nro_op_str,))
        for row in cursor.fetchall():
            usages.append({'origen': 'Desvío', 'monto': row['monto'], 'fecha': row['fecha']})
            
        cursor.execute("SELECT monto, fecha FROM cobro_desvios_recuperos WHERE nro_op = ?", (nro_op_str,))
        for row in cursor.fetchall():
            usages.append({'origen': 'Recupero de Desvío', 'monto': row['monto'], 'fecha': row['fecha']})
            
        cursor.execute("SELECT monto, fecha FROM cobro_reserva_usos_recuperos WHERE nro_op = ?", (nro_op_str,))
        for row in cursor.fetchall():
            usages.append({'origen': 'Recupero de Reserva', 'monto': row['monto'], 'fecha': row['fecha']})

        cursor.execute("SELECT monto, fecha FROM cobro_reserva_usos WHERE nro_op = ?", (nro_op_str,))
        for row in cursor.fetchall():
            usages.append({'origen': 'Pago desde Reserva', 'monto': row['monto'], 'fecha': row['fecha']})

        cursor.execute("SELECT monto, fecha FROM pagos_fondos_propios WHERE nro_op = ?", (nro_op_str,))
        for row in cursor.fetchall():
            usages.append({'origen': 'Pago Fondos Propios', 'monto': row['monto'], 'fecha': row['fecha']})

        cursor.execute("SELECT monto, fecha FROM recuperos_fondos_propios WHERE nro_op = ?", (nro_op_str,))
        for row in cursor.fetchall():
            usages.append({'origen': 'Recupero Fondos Propios', 'monto': row['monto'], 'fecha': row['fecha']})
            
    return usages


def register_or_update_op(nro_op, obra_id=None, gasto_id=None, conn=None):
    nro_op_str = str(nro_op).strip()
    if not nro_op_str:
        return
    if conn is None:
        with db_session() as c:
            register_or_update_op(nro_op_str, obra_id=obra_id, gasto_id=gasto_id, conn=c)
        return

    cursor = conn.cursor()
    cursor.execute("SELECT * FROM op_bejerman WHERE nro_op = ?", (nro_op_str,))
    row = cursor.fetchone()
    if row:
        cursor.execute('''
            UPDATE op_bejerman 
            SET obra_id = COALESCE(?, obra_id), gasto_id = COALESCE(?, gasto_id) 
            WHERE nro_op = ?
        ''', (obra_id, gasto_id, nro_op_str))
    else:
        cursor.execute('''
            INSERT INTO op_bejerman (nro_op, obra_id, gasto_id)
            VALUES (?, ?, ?)
        ''', (nro_op_str, obra_id, gasto_id))


def get_audit_log(tabla=None, registro_id=None, limit=100):
    """
    Retorna los registros de auditoría forense almacenados en audit_log.
    Permite filtrar opcionalmente por nombre de tabla y registro_id.
    """
    with db_session() as conn:
        cursor = conn.cursor()
        query = "SELECT * FROM audit_log WHERE 1=1"
        params = []
        if tabla:
            query += " AND tabla = ?"
            params.append(tabla)
        if registro_id is not None:
            query += " AND registro_id = ?"
            params.append(str(registro_id))
        query += " ORDER BY fecha_hora DESC, id DESC LIMIT ?"
        params.append(int(limit))
        cursor.execute(query, tuple(params))
        return [dict(r) for r in cursor.fetchall()]


def get_historial_cambios_registro(tabla, registro_id):
    """
    Retorna el historial cronológico de modificaciones y bajas para un registro específico.
    """
    return get_audit_log(tabla=tabla, registro_id=registro_id, limit=500)
