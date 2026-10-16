"""
db_core/connection.py - Gestión de Conexiones SQLite, Modo WAL y Transaccionalidad Reentrante
"""
import os
import sys
import sqlite3
import threading
from contextlib import contextmanager

# Constantes del sistema
DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'decretometro.db')
TOLERANCE = 0.01

DESTINO_FIN_ORIGINAL = 'fin_original'
DESTINO_RESERVA = 'reserva'
DESTINO_OTRA_OBRA = 'otra_obra'

# Sesión local por hilo para soportar transaccionalidad anidada (reentrancia segura)
_local_session = threading.local()


def get_db_path():
    """
    Resuelve dinámicamente la ruta a la base de datos respetando overrides
    o monkeypatches realizados sobre el módulo fachada 'database'.
    Cumple con la Regla 1 de ingeniería para aislamiento en tests automatizados.
    """
    db_mod = sys.modules.get('database')
    if db_mod is not None and hasattr(db_mod, 'DB_PATH'):
        return db_mod.DB_PATH
    return DB_PATH


def get_connection():
    """
    Crea y configura una conexión de base de datos SQLite con optimizaciones de concurrencia.
    Utiliza isolation_level=None (modo autocommit nativo) para delegar el control
    transaccional explícito a 'BEGIN IMMEDIATE;' gestionado por db_session().
    """
    current_path = get_db_path()
    conn = sqlite3.connect(current_path, isolation_level=None)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute('PRAGMA foreign_keys = ON;')
    cursor.execute('PRAGMA busy_timeout = 20000;')  # 20 segundos de tolerancia ante locks
    cursor.execute('PRAGMA journal_mode = WAL;')     # Write-Ahead Logging para lecturas no bloqueantes
    cursor.execute('PRAGMA synchronous = NORMAL;')   # Rendimiento seguro en modo WAL
    return conn


@contextmanager
def db_session():
    """
    Context manager de sesión transaccional reentrante.
    - Si ya existe una transacción activa en el hilo actual, reutiliza la conexión.
    - Si es la llamada de nivel exterior, inicia una transacción exclusiva con 'BEGIN IMMEDIATE;',
      confirma con 'COMMIT;' al finalizar o realiza 'ROLLBACK;' ante excepciones,
      garantizando el cierre de la conexión al concluir.
    """
    if getattr(_local_session, 'conn', None) is not None:
        # Llamada reentrante/anidada en el mismo hilo: reutilizar conexión activa
        _local_session.depth += 1
        try:
            yield _local_session.conn
        finally:
            _local_session.depth -= 1
    else:
        # Nivel exterior: abrir conexión y tomar bloqueo exclusivo inmediato de escritura
        conn = get_connection()
        _local_session.conn = conn
        _local_session.depth = 1
        try:
            conn.execute("BEGIN IMMEDIATE;")
        except Exception:
            pass
        try:
            yield conn
            if conn.in_transaction:
                conn.execute("COMMIT;")
        except Exception:
            try:
                if conn.in_transaction:
                    conn.execute("ROLLBACK;")
            except Exception:
                pass
            raise
        finally:
            _local_session.conn = None
            _local_session.depth = 0
            conn.close()
