from contextlib import contextmanager
import sqlite3
import os
import datetime
import utils
from utils import get_due_date

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'decretometro.db')
TOLERANCE = 0.01

# Constantes de tipos de destino (Trazabilidad)
DESTINO_FIN_ORIGINAL = 'fin_original'
DESTINO_RESERVA = 'reserva'
DESTINO_OTRA_OBRA = 'otra_obra'

def _validar_op_o_nota_db(nro_op, notas, contexto="movimiento"):
    """Valida a nivel de base de datos que exista un número de OP o una nota válida (10 a 30 caracteres)."""
    op_ok = bool(nro_op and str(nro_op).strip())
    nota_ok = bool(notas and 10 <= len(str(notas).strip()) <= 30)
    if not op_ok and not nota_ok:
        raise ValueError(
            f"El {contexto} debe tener un número de OP Bejerman o una observación de 10 a 30 caracteres."
        )

def get_connection():
    # Permitir el uso de claves foráneas con timeout de 10 segundos
    conn = sqlite3.connect(DB_PATH, timeout=10.0)
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.row_factory = sqlite3.Row
    return conn

@contextmanager
def db_session():
    """Maneja transacciones seguras con commit/rollback y cierre automático de conexiones."""
    conn = get_connection()
    try:
        yield conn
        conn.commit()
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()

def init_db():
    with db_session() as conn:
        cursor = conn.cursor()
    
        # Crear tabla de versiones si no existe
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS schema_version (
                id INTEGER PRIMARY KEY,
                version INTEGER NOT NULL
            )
        ''')
        
        # Obtener versión actual
        cursor.execute('SELECT version FROM schema_version WHERE id = 1')
        row = cursor.fetchone()
        version_actual = row['version'] if row else 0

        # --- Tablas Base (Esquema Inicial v0) ---
        
        # Tabla Decretos (sin expediente_imuh)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS decretos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nro_decreto INTEGER NOT NULL,
                anio INTEGER NOT NULL,
                nro_expediente TEXT NOT NULL,
                destino_fondos TEXT NOT NULL,
                estado TEXT NOT NULL DEFAULT 'Vigente',
                pdf_path TEXT
            )
        ''')
    
        # Tabla Cuotas
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS cuotas (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                decreto_id INTEGER NOT NULL,
                mes INTEGER NOT NULL,
                anio INTEGER NOT NULL,
                monto REAL NOT NULL,
                FOREIGN KEY (decreto_id) REFERENCES decretos(id) ON DELETE CASCADE
            )
        ''')
    
        # Tabla Cobros
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS cobros (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                cuota_id INTEGER NOT NULL,
                monto REAL NOT NULL,
                fecha DATE NOT NULL,
                comprobante_path TEXT,
                FOREIGN KEY (cuota_id) REFERENCES cuotas(id) ON DELETE CASCADE
            )
        ''')

        # Tabla Aportes Funcionamiento
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS aportes_funcionamiento (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                anio INTEGER NOT NULL,
                mes INTEGER NOT NULL,
                monto_pautado REAL NOT NULL,
                monto_cobrado REAL DEFAULT 0,
                fecha_cobro DATE
            )
        ''')

        # Tabla Aportes Sueldo (sin estado ni fecha_renuncia)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS aportes_sueldo (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                anio INTEGER NOT NULL,
                mes INTEGER NOT NULL,
                monto_pedido REAL NOT NULL,
                fecha_pedido DATE NOT NULL,
                monto_cobrado REAL DEFAULT 0,
                fecha_cobro DATE
            )
        ''')

        # Tabla Aportes SAC (sin estado ni fecha_renuncia)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS aportes_sac (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                anio INTEGER NOT NULL,
                cuota_nro INTEGER NOT NULL,
                monto_pedido REAL NOT NULL,
                fecha_pedido DATE NOT NULL,
                monto_cobrado REAL DEFAULT 0,
                fecha_cobro DATE
            )
        ''')
    
        # Tabla Prestamos Internos (Desvíos de fondos)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS prestamos_internos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                decreto_origen_id INTEGER NOT NULL,
                destino TEXT NOT NULL,
                monto REAL NOT NULL,
                fecha DATE NOT NULL,
                motivo TEXT,
                devolucion_estado TEXT NOT NULL DEFAULT 'Pendiente',
                fecha_devolucion DATE,
                FOREIGN KEY (decreto_origen_id) REFERENCES decretos(id) ON DELETE CASCADE
            )
        ''')
    
        # Tabla Recuperos (Devoluciones parciales o totales de préstamos)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS recuperos_internos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                prestamo_id INTEGER NOT NULL,
                monto REAL NOT NULL,
                fecha DATE NOT NULL,
                FOREIGN KEY (prestamo_id) REFERENCES prestamos_internos(id) ON DELETE CASCADE
            )
        ''')
    
        # --- TABLAS DE DISTRIBUCION (Trazabilidad) ---

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS cobro_distribuciones (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                cobro_id        INTEGER NOT NULL UNIQUE,
                monto_fin_orig  REAL NOT NULL DEFAULT 0,
                monto_reserva   REAL NOT NULL DEFAULT 0,
                notas           TEXT,
                FOREIGN KEY (cobro_id) REFERENCES cobros(id) ON DELETE CASCADE
            )
        ''')

        # sin decreto_destino_id
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS cobro_reserva_usos (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                cobro_id        INTEGER NOT NULL,
                monto           REAL NOT NULL,
                destino_tipo    TEXT NOT NULL,
                destino_detalle TEXT,
                fecha           DATE NOT NULL,
                notas           TEXT,
                nro_op          TEXT,
                FOREIGN KEY (cobro_id) REFERENCES cobros(id) ON DELETE CASCADE
            )
        ''')

        # sin decreto_destino_id
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS cobro_desvios (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                cobro_id    INTEGER NOT NULL,
                destino     TEXT NOT NULL,
                monto       REAL NOT NULL,
                motivo      TEXT,
                fecha       DATE NOT NULL,
                nro_op      TEXT,
                FOREIGN KEY (cobro_id) REFERENCES cobros(id) ON DELETE CASCADE
            )
        ''')

        # sin decreto_destino_id, sin notas
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS cobro_desvios_recuperos (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                desvio_id       INTEGER NOT NULL,
                monto           REAL NOT NULL,
                fecha           DATE NOT NULL,
                destino_tipo    TEXT NOT NULL,
                destino_detalle TEXT,
                nro_op          TEXT,
                grupo_compensacion_id TEXT,
                FOREIGN KEY (desvio_id) REFERENCES cobro_desvios(id) ON DELETE CASCADE
            )
        ''')

        # sin notas
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS cobro_reserva_usos_recuperos (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                reserva_uso_id  INTEGER NOT NULL,
                monto           REAL NOT NULL,
                fecha           DATE NOT NULL,
                destino_tipo    TEXT NOT NULL,
                destino_detalle TEXT,
                decreto_destino_id INTEGER REFERENCES decretos(id),
                nro_op          TEXT,
                grupo_compensacion_id TEXT,
                FOREIGN KEY (reserva_uso_id) REFERENCES cobro_reserva_usos(id) ON DELETE CASCADE
            )
        ''')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS cobro_fin_original_usos (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                cobro_id        INTEGER NOT NULL,
                monto           REAL NOT NULL,
                fecha           DATE NOT NULL,
                nro_op          TEXT,
                notas           TEXT,
                obra_id         INTEGER REFERENCES obras(id),
                gasto_nombre    TEXT,
                gasto_expediente_imuh TEXT,
                FOREIGN KEY (cobro_id) REFERENCES cobros(id) ON DELETE CASCADE
            )
        ''')
    
        # Tabla Solicitudes de Financiamiento
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS solicitudes_financiamiento (
                id                  INTEGER PRIMARY KEY AUTOINCREMENT,
                nro_expediente      TEXT NOT NULL UNIQUE,
                expediente_imuh     TEXT,
                destino_fondos      TEXT NOT NULL,
                monto_solicitado    REAL NOT NULL,
                fecha_solicitud     DATE NOT NULL,
                estado              TEXT NOT NULL DEFAULT 'Pendiente',
                decreto_id          INTEGER REFERENCES decretos(id) ON DELETE SET NULL,
                pdf_path            TEXT,
                notas               TEXT
            )
        ''')
        
        # --- Diccionario de Migraciones Ordenadas ---
        MIGRACIONES = [
            (1, "ALTER TABLE cobro_desvios ADD COLUMN decreto_destino_id INTEGER REFERENCES decretos(id)"),
            (2, "ALTER TABLE cobro_reserva_usos ADD COLUMN decreto_destino_id INTEGER REFERENCES decretos(id)"),
            (3, "ALTER TABLE cobro_desvios_recuperos ADD COLUMN decreto_destino_id INTEGER REFERENCES decretos(id)"),
            (4, "ALTER TABLE cobro_desvios_recuperos ADD COLUMN notas TEXT"),
            (5, "ALTER TABLE cobro_reserva_usos_recuperos ADD COLUMN notas TEXT"),
            (6, "ALTER TABLE decretos ADD COLUMN expediente_imuh TEXT"),
            (7, "ALTER TABLE aportes_sueldo ADD COLUMN estado TEXT DEFAULT 'Pendiente'"),
            (8, "ALTER TABLE aportes_sac ADD COLUMN estado TEXT DEFAULT 'Pendiente'"),
            (9, "ALTER TABLE aportes_sueldo ADD COLUMN fecha_renuncia DATE"),
            (10, "ALTER TABLE aportes_sac ADD COLUMN fecha_renuncia DATE"),
            (11, "UPDATE cobro_desvios_recuperos SET notas = 'Histórico - Sin OP' WHERE (nro_op IS NULL OR TRIM(nro_op) = '') AND (notas IS NULL OR TRIM(notas) = '')"),
            (12, "UPDATE cobro_reserva_usos_recuperos SET notas = 'Histórico - Sin OP' WHERE (nro_op IS NULL OR TRIM(nro_op) = '') AND (notas IS NULL OR TRIM(notas) = '')"),
            (13, "UPDATE aportes_sueldo SET estado = 'Cobrado' WHERE fecha_cobro IS NOT NULL AND estado = 'Pendiente'"),
            (14, "UPDATE aportes_sac SET estado = 'Cobrado' WHERE fecha_cobro IS NOT NULL AND estado = 'Pendiente'"),
            (15, "CREATE TABLE IF NOT EXISTS obras (id INTEGER PRIMARY KEY AUTOINCREMENT, nombre TEXT NOT NULL, expediente_imuh TEXT NOT NULL UNIQUE, activa INTEGER NOT NULL DEFAULT 1 CHECK(activa IN (0, 1)))"),
            (16, "CREATE TABLE IF NOT EXISTS decretos_obras (decreto_id INTEGER NOT NULL REFERENCES decretos(id) ON DELETE CASCADE, obra_id INTEGER NOT NULL REFERENCES obras(id) ON DELETE RESTRICT, PRIMARY KEY (decreto_id, obra_id))"),
            (17, "ALTER TABLE cobro_desvios ADD COLUMN obra_id INTEGER REFERENCES obras(id)"),
            (18, "ALTER TABLE cobro_desvios ADD COLUMN gasto_nombre TEXT"),
            (19, "ALTER TABLE cobro_desvios ADD COLUMN gasto_expediente_imuh TEXT"),
            (20, "ALTER TABLE cobro_reserva_usos ADD COLUMN obra_id INTEGER REFERENCES obras(id)"),
            (21, "ALTER TABLE cobro_reserva_usos ADD COLUMN gasto_nombre TEXT"),
            (22, "ALTER TABLE cobro_reserva_usos ADD COLUMN gasto_expediente_imuh TEXT"),
            (23, "ALTER TABLE solicitudes_financiamiento ADD COLUMN obra_id INTEGER REFERENCES obras(id)"),
            (24, "CREATE TABLE IF NOT EXISTS gastos_funcionamiento (id INTEGER PRIMARY KEY AUTOINCREMENT, nombre TEXT NOT NULL, expediente_imuh TEXT NOT NULL UNIQUE, activo INTEGER NOT NULL DEFAULT 1 CHECK(activo IN (0, 1)))"),
            (25, "CREATE TABLE IF NOT EXISTS proveedores_obras (id INTEGER PRIMARY KEY AUTOINCREMENT, razon_social TEXT NOT NULL UNIQUE, cuit TEXT NOT NULL UNIQUE, activo INTEGER NOT NULL DEFAULT 1 CHECK(activo IN (0, 1)))"),
            (26, "CREATE TABLE IF NOT EXISTS proveedores_funcionamiento (id INTEGER PRIMARY KEY AUTOINCREMENT, razon_social TEXT NOT NULL UNIQUE, cuit TEXT NOT NULL UNIQUE, activo INTEGER NOT NULL DEFAULT 1 CHECK(activo IN (0, 1)))"),
            (27, "ALTER TABLE obras ADD COLUMN proveedor_id INTEGER REFERENCES proveedores_obras(id)"),
            (28, "ALTER TABLE gastos_funcionamiento ADD COLUMN proveedor_id INTEGER REFERENCES proveedores_funcionamiento(id)"),
            (29, "ALTER TABLE cobro_fin_original_usos ADD COLUMN obra_id INTEGER REFERENCES obras(id)"),
            (30, "ALTER TABLE cobro_fin_original_usos ADD COLUMN gasto_nombre TEXT"),
            (31, "ALTER TABLE cobro_fin_original_usos ADD COLUMN gasto_expediente_imuh TEXT"),
            (32, "CREATE TABLE IF NOT EXISTS op_bejerman (nro_op TEXT PRIMARY KEY, obra_id INTEGER REFERENCES obras(id) ON DELETE RESTRICT, gasto_id INTEGER REFERENCES gastos_funcionamiento(id) ON DELETE RESTRICT)"),
            (33, "CREATE TABLE IF NOT EXISTS pagos_fondos_propios (id INTEGER PRIMARY KEY AUTOINCREMENT, obra_id INTEGER REFERENCES obras(id) ON DELETE RESTRICT, monto REAL NOT NULL, fecha DATE NOT NULL, nro_op TEXT, observaciones TEXT)"),
            (34, "CREATE TABLE IF NOT EXISTS recuperos_fondos_propios (id INTEGER PRIMARY KEY AUTOINCREMENT, cobro_id INTEGER REFERENCES cobros(id) ON DELETE CASCADE, obra_id INTEGER REFERENCES obras(id) ON DELETE RESTRICT, monto REAL NOT NULL, fecha DATE NOT NULL, nro_op TEXT, notas TEXT)"),
            (35, "ALTER TABLE cuotas ADD COLUMN fecha_estimada_cobro DATE"),
            (36, "CREATE TABLE IF NOT EXISTS monedas_indices (id INTEGER PRIMARY KEY AUTOINCREMENT, codigo TEXT NOT NULL UNIQUE, nombre TEXT NOT NULL, simbolo TEXT NOT NULL, tipo TEXT NOT NULL CHECK(tipo IN ('Moneda', 'Índice')), decimales INTEGER NOT NULL DEFAULT 2, activo INTEGER NOT NULL DEFAULT 1 CHECK(activo IN (0, 1)))"),
            (37, "INSERT OR IGNORE INTO monedas_indices (id, codigo, nombre, simbolo, tipo, decimales, activo) VALUES (1, 'ARS', 'Peso Argentino', '$', 'Moneda', 2, 1)"),
            (38, "INSERT OR IGNORE INTO monedas_indices (id, codigo, nombre, simbolo, tipo, decimales, activo) VALUES (2, 'USD', 'Dólar Estadounidense', 'U$S', 'Moneda', 2, 1)"),
            (39, "INSERT OR IGNORE INTO monedas_indices (id, codigo, nombre, simbolo, tipo, decimales, activo) VALUES (3, 'UVI', 'Unidad de Vivienda (Ley 27.271)', 'UVI', 'Índice', 2, 1)"),
            (40, "CREATE TABLE IF NOT EXISTS convenios (id INTEGER PRIMARY KEY AUTOINCREMENT, nro_convenio TEXT NOT NULL, ente_financiador TEXT NOT NULL, nombre_convenio TEXT NOT NULL, nro_expediente TEXT NOT NULL, fecha_firma DATE NOT NULL, moneda_id INTEGER NOT NULL DEFAULT 1 REFERENCES monedas_indices(id), monto_pactado_moneda REAL NOT NULL, cotizacion_base REAL NOT NULL DEFAULT 1.0, monto_equivalente_ars REAL NOT NULL, estado TEXT NOT NULL DEFAULT 'Vigente' CHECK(estado IN ('Vigente', 'Terminado', 'Anulado')), pdf_path TEXT, notas TEXT)"),
            (41, "CREATE TABLE IF NOT EXISTS convenio_obras (id INTEGER PRIMARY KEY AUTOINCREMENT, convenio_id INTEGER NOT NULL REFERENCES convenios(id) ON DELETE CASCADE, obra_id INTEGER NOT NULL REFERENCES obras(id) ON DELETE RESTRICT, monto_pactado_moneda REAL NOT NULL, monto_equivalente_ars REAL NOT NULL, porcentaje REAL DEFAULT 0.0, notas TEXT, UNIQUE(convenio_id, obra_id))"),
            (42, "CREATE TABLE IF NOT EXISTS convenio_solicitudes (id INTEGER PRIMARY KEY AUTOINCREMENT, convenio_id INTEGER NOT NULL REFERENCES convenios(id) ON DELETE CASCADE, obra_id INTEGER NOT NULL REFERENCES obras(id) ON DELETE RESTRICT, nro_certificado TEXT NOT NULL, periodo TEXT, cantidad_moneda REAL NOT NULL, cantidad_moneda_cobrada REAL NOT NULL DEFAULT 0.0, cotizacion_solicitud REAL NOT NULL DEFAULT 1.0, monto_solicitado_ars REAL NOT NULL, fecha_solicitud DATE NOT NULL, expediente_pago TEXT, estado TEXT NOT NULL DEFAULT 'Pendiente' CHECK(estado IN ('Pendiente', 'Parcial', 'Cobrado', 'Anulado')), pdf_path TEXT, notas TEXT)"),
            (43, "ALTER TABLE decretos ADD COLUMN moneda_id INTEGER DEFAULT 1"),
            (44, "-- Migración 44: Recreación segura de cobros con soporte para convenios --"),
            (45, "ALTER TABLE cobro_desvios_recuperos ADD COLUMN grupo_compensacion_id TEXT"),
            (46, "ALTER TABLE cobro_reserva_usos_recuperos ADD COLUMN grupo_compensacion_id TEXT"),
            (47, "-- Migración 47: Enforzamiento de CHECK de exclusión mutua para origen_tipo en tabla cobros --"),
            (48, "-- Migración 48: Soporte Bimonetario en Catálogo de Obras y Control de Pagos --")
        ]
        
        # Ejecutar migrador
        for version, sql in MIGRACIONES:
            if version > version_actual:
                try:
                    if version == 44:
                        conn.execute("PRAGMA foreign_keys = OFF;")
                        cursor.execute('''
                            CREATE TABLE IF NOT EXISTS cobros_v2 (
                                id INTEGER PRIMARY KEY AUTOINCREMENT,
                                cuota_id INTEGER REFERENCES cuotas(id) ON DELETE CASCADE,
                                convenio_solicitud_id INTEGER REFERENCES convenio_solicitudes(id) ON DELETE SET NULL,
                                origen_tipo TEXT NOT NULL DEFAULT 'decreto',
                                obra_id INTEGER REFERENCES obras(id),
                                moneda_origen_id INTEGER DEFAULT 1 REFERENCES monedas_indices(id),
                                cantidad_moneda_origen REAL,
                                cotizacion_cobro REAL DEFAULT 1.0,
                                diferencia_ajuste_ars REAL DEFAULT 0.0,
                                monto REAL NOT NULL,
                                fecha DATE NOT NULL,
                                comprobante_path TEXT
                            )
                        ''')
                        cursor.execute('''
                            INSERT INTO cobros_v2 (id, cuota_id, monto, fecha, comprobante_path, origen_tipo)
                            SELECT id, cuota_id, monto, fecha, comprobante_path, 'decreto' FROM cobros WHERE id NOT IN (SELECT id FROM cobros_v2)
                        ''')
                        cursor.execute('DROP TABLE cobros')
                        cursor.execute('ALTER TABLE cobros_v2 RENAME TO cobros')
                        conn.execute("PRAGMA foreign_keys = ON;")
                    elif version == 47:
                        conn.execute("PRAGMA foreign_keys = OFF;")
                        cursor.execute('''
                            CREATE TABLE IF NOT EXISTS cobros_v3 (
                                id INTEGER PRIMARY KEY AUTOINCREMENT,
                                cuota_id INTEGER REFERENCES cuotas(id) ON DELETE CASCADE,
                                convenio_solicitud_id INTEGER REFERENCES convenio_solicitudes(id) ON DELETE SET NULL,
                                origen_tipo TEXT NOT NULL DEFAULT 'decreto',
                                obra_id INTEGER REFERENCES obras(id),
                                moneda_origen_id INTEGER DEFAULT 1 REFERENCES monedas_indices(id),
                                cantidad_moneda_origen REAL,
                                cotizacion_cobro REAL DEFAULT 1.0,
                                diferencia_ajuste_ars REAL DEFAULT 0.0,
                                monto REAL NOT NULL,
                                fecha DATE NOT NULL,
                                comprobante_path TEXT,
                                CONSTRAINT check_origen_exclusivo CHECK (
                                    (origen_tipo = 'decreto' AND cuota_id IS NOT NULL AND convenio_solicitud_id IS NULL) OR
                                    (origen_tipo = 'convenio' AND convenio_solicitud_id IS NOT NULL AND cuota_id IS NULL)
                                )
                            )
                        ''')
                        cursor.execute('''
                            INSERT INTO cobros_v3 (
                                id, cuota_id, convenio_solicitud_id, origen_tipo, obra_id,
                                moneda_origen_id, cantidad_moneda_origen, cotizacion_cobro,
                                diferencia_ajuste_ars, monto, fecha, comprobante_path
                            )
                            SELECT id, cuota_id, convenio_solicitud_id, origen_tipo, obra_id,
                                   moneda_origen_id, cantidad_moneda_origen, cotizacion_cobro,
                                   diferencia_ajuste_ars, monto, fecha, comprobante_path
                            FROM cobros WHERE id NOT IN (SELECT id FROM cobros_v3)
                        ''')
                        cursor.execute('DROP TABLE cobros')
                        cursor.execute('ALTER TABLE cobros_v3 RENAME TO cobros')
                        conn.execute("PRAGMA foreign_keys = ON;")
                    elif version == 48:
                        # 1. Ampliación de la tabla 'obras'
                        for col_sql in [
                            "ALTER TABLE obras ADD COLUMN monto_contrato REAL DEFAULT 0.0",
                            "ALTER TABLE obras ADD COLUMN moneda_id INTEGER DEFAULT 1",
                            "ALTER TABLE obras ADD COLUMN monto_contrato_moneda REAL DEFAULT 0.0",
                            "ALTER TABLE obras ADD COLUMN cotizacion_base_contrato REAL DEFAULT 1.0",
                            "ALTER TABLE obras ADD COLUMN fecha_contrato DATE",
                            "ALTER TABLE obras ADD COLUMN notas_contrato TEXT"
                        ]:
                            try:
                                cursor.execute(col_sql)
                            except sqlite3.OperationalError:
                                pass

                        # 2. Tabla para Adicionales / Ampliaciones de Obra
                        cursor.execute('''
                            CREATE TABLE IF NOT EXISTS obra_adicionales (
                                id INTEGER PRIMARY KEY AUTOINCREMENT,
                                obra_id INTEGER NOT NULL REFERENCES obras(id) ON DELETE CASCADE,
                                nro_resolucion TEXT NOT NULL,
                                fecha DATE NOT NULL,
                                cantidad_moneda REAL NOT NULL,
                                cotizacion_base REAL NOT NULL DEFAULT 1.0,
                                monto_equivalente_ars REAL NOT NULL,
                                motivo TEXT
                            )
                        ''')

                        # 3. Ampliación de tablas de pagos a contratistas
                        for pcol_sql in [
                            "ALTER TABLE cobro_fin_original_usos ADD COLUMN cantidad_moneda_amortizada REAL",
                            "ALTER TABLE cobro_fin_original_usos ADD COLUMN cotizacion_pago REAL DEFAULT 1.0",
                            "ALTER TABLE cobro_fin_original_usos ADD COLUMN convenio_solicitud_id INTEGER",
                            "ALTER TABLE cobro_fin_original_usos ADD COLUMN motivo_sobrepago TEXT",
                            "ALTER TABLE pagos_fondos_propios ADD COLUMN cantidad_moneda_amortizada REAL",
                            "ALTER TABLE pagos_fondos_propios ADD COLUMN cotizacion_pago REAL DEFAULT 1.0",
                            "ALTER TABLE pagos_fondos_propios ADD COLUMN convenio_solicitud_id INTEGER",
                            "ALTER TABLE pagos_fondos_propios ADD COLUMN motivo_sobrepago TEXT"
                        ]:
                            try:
                                cursor.execute(pcol_sql)
                            except sqlite3.OperationalError:
                                pass

                        # 4. Sincronización inmutable de registros históricos:
                        cursor.execute('''
                            UPDATE obras 
                            SET moneda_id = 1,
                                monto_contrato_moneda = COALESCE(monto_contrato, 0.0),
                                cotizacion_base_contrato = 1.0
                            WHERE moneda_id IS NULL OR moneda_id = 1
                        ''')
                    else:
                        cursor.execute(sql)
                except sqlite3.OperationalError as e:
                    # Ignorar si la columna ya existe
                    err_msg = str(e).lower()
                    if "duplicate column name" in err_msg or "already exists" in err_msg:
                        pass
                    else:
                        raise e
                cursor.execute('INSERT OR REPLACE INTO schema_version (id, version) VALUES (1, ?)', (version,))
                conn.commit()

    # --- Decretos CRUD ---

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
        conn.commit()
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
        conn.commit()


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
    
        cursor.execute('SELECT pdf_path FROM decretos WHERE id = ?', (decreto_id,))
        d_row = cursor.fetchone()
        if d_row and d_row['pdf_path'] and os.path.exists(d_row['pdf_path']):
            try:
                os.remove(d_row['pdf_path'])
            except OSError:
                pass
        
        cursor.execute('''
            SELECT c.comprobante_path FROM cobros c
            JOIN cuotas cu ON c.cuota_id = cu.id
            WHERE cu.decreto_id = ?
        ''', (decreto_id,))
        comprobantes = cursor.fetchall()
        for row in comprobantes:
            if row['comprobante_path'] and os.path.exists(row['comprobante_path']):
                try:
                    os.remove(row['comprobante_path'])
                except OSError:
                    pass

        cursor.execute("UPDATE solicitudes_financiamiento SET estado = 'Pendiente', decreto_id = NULL WHERE decreto_id = ?", (decreto_id,))
        cursor.execute('DELETE FROM decretos WHERE id = ?', (decreto_id,))
        conn.commit()


def update_estado_decreto(decreto_id, estado):
    with db_session() as conn:
        cursor = conn.cursor()
        cursor.execute('UPDATE decretos SET estado = ? WHERE id = ?', (estado, decreto_id))
        conn.commit()

    # --- Cuotas CRUD ---

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
        conn.commit()
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
        conn.commit()

    # --- Cobros CRUD ---

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
            conn.commit()
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
            conn.commit()
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
        conn.commit()
        if cobro_row and cobro_row['cuota_id']:
            check_estado_decreto_by_cuota(conn, cobro_row['cuota_id'])

    # --- Aportes Funcionamiento ---

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
        conn.commit()


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
        conn.commit()


def reset_cobro_funcionamiento(aporte_id):
    with db_session() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            UPDATE aportes_funcionamiento 
            SET monto_cobrado = 0, fecha_cobro = NULL
            WHERE id = ?
        ''', (aporte_id,))
        conn.commit()


def delete_anio_funcionamiento(anio):
    with db_session() as conn:
        cursor = conn.cursor()
        cursor.execute('DELETE FROM aportes_funcionamiento WHERE anio = ?', (anio,))
        conn.commit()

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
        conn.commit()


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
        conn.commit()


def delete_aporte_sueldo(aporte_id):
    with db_session() as conn:
        cursor = conn.cursor()
        cursor.execute('DELETE FROM aportes_sueldo WHERE id = ?', (aporte_id,))
        conn.commit()


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
        conn.commit()

    # --- Aportes SAC ---

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
        conn.commit()


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
        conn.commit()


def delete_aporte_sac(aporte_id):
    with db_session() as conn:
        cursor = conn.cursor()
        cursor.execute('DELETE FROM aportes_sac WHERE id = ?', (aporte_id,))
        conn.commit()


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
        conn.commit()

    # --- Lógica de Negocio ---

def check_estado_decreto_by_cuota(conn, cuota_id):
    cursor = conn.cursor()
    cursor.execute('SELECT decreto_id FROM cuotas WHERE id = ?', (cuota_id,))
    row = cursor.fetchone()
    if row:
        check_estado_decreto(conn, row['decreto_id'])

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
    conn.commit()


def check_estado_convenio_by_solicitud(conn, solicitud_id):
    cursor = conn.cursor()
    cursor.execute('SELECT convenio_id FROM convenio_solicitudes WHERE id = ?', (solicitud_id,))
    row = cursor.fetchone()
    if row:
        check_estado_convenio(conn, row['convenio_id'])


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
        conn.commit()


# --- Prestamos Internos (Desvíos/Préstamos) ---
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
        conn.commit()
        return prestamo_id


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


def get_recuperos_by_prestamo(prestamo_id):
    with db_session() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM recuperos_internos WHERE prestamo_id = ? ORDER BY fecha ASC', (prestamo_id,))
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
        
        conn.commit()
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
        conn.commit()


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
        conn.commit()


def delete_prestamo(prestamo_id):
    with db_session() as conn:
        cursor = conn.cursor()
        cursor.execute('DELETE FROM prestamos_internos WHERE id = ?', (prestamo_id,))
        conn.commit()

    # --- Distribución de Cobranzas (NUEVO) ---


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
    
        cursor.execute('SELECT monto FROM cobros WHERE id = ?', (cobro_id,))
        c_row = cursor.fetchone()
        if not c_row:
            raise ValueError("Cobro no encontrado.")
    
        cursor.execute('SELECT COALESCE(SUM(monto), 0) as tot_desvios FROM cobro_desvios WHERE cobro_id = ?', (cobro_id,))
        tot_desvios = cursor.fetchone()['tot_desvios']

        cursor.execute('''
            SELECT COALESCE(SUM(cdr.monto), 0) as tot 
            FROM cobro_desvios_recuperos cdr
            JOIN cobro_desvios cd ON cdr.desvio_id = cd.id
            WHERE cd.cobro_id = ? AND cdr.destino_tipo = 'sin_distribucion'
        ''', (cobro_id,))
        rec_desv_sd = cursor.fetchone()['tot']

        cursor.execute('''
            SELECT COALESCE(SUM(crur.monto), 0) as tot 
            FROM cobro_reserva_usos_recuperos crur
            JOIN cobro_reserva_usos cru ON crur.reserva_uso_id = cru.id
            WHERE cru.cobro_id = ? AND crur.destino_tipo = 'sin_distribucion'
        ''', (cobro_id,))
        rec_res_sd = cursor.fetchone()['tot']

        tot_recuperos_sd = rec_desv_sd + rec_res_sd
    
        if (monto_fin_orig + monto_reserva + tot_desvios - tot_recuperos_sd) > (c_row['monto'] + TOLERANCE):
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
        conn.commit()


def get_cobros_con_resumen_distribucion():
    with db_session() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT c.id, c.monto, c.fecha, c.cuota_id, c.origen_tipo, c.convenio_solicitud_id,
                   cu.mes, cu.anio,
                   COALESCE(d.nro_decreto, cv.nro_convenio) as nro_decreto,
                   COALESCE(d.anio, strftime('%Y', cv.fecha_firma)) as decreto_anio,
                   d.id as decreto_id, cv.id as convenio_id,
                   COALESCE(d.destino_fondos, cv.nombre_convenio || ' — ' || o.nombre) as destino_fondos,
                   COALESCE(d.expediente_imuh, o.expediente_imuh) as expediente_imuh,
                   m.simbolo as moneda_simbolo, m.codigo as moneda_codigo,
                   c.cantidad_moneda_origen, c.cotizacion_cobro, cs.cotizacion_solicitud,
                   COALESCE(dist.monto_fin_orig, 0) as monto_fin_orig,
                   COALESCE(dist.monto_reserva, 0) as monto_reserva,
                   COALESCE((SELECT SUM(monto) FROM cobro_desvios WHERE cobro_id = c.id), 0) as total_desvios,
                   (
                       COALESCE(dist.monto_fin_orig, 0) + 
                       COALESCE(dist.monto_reserva, 0) + 
                       COALESCE((SELECT SUM(monto) FROM cobro_desvios WHERE cobro_id = c.id), 0) -
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
                   ) as total_distribuido
            FROM cobros c
            LEFT JOIN cuotas cu ON c.cuota_id = cu.id
            LEFT JOIN decretos d ON cu.decreto_id = d.id
            LEFT JOIN convenio_solicitudes cs ON c.convenio_solicitud_id = cs.id
            LEFT JOIN convenios cv ON cs.convenio_id = cv.id
            LEFT JOIN obras o ON (c.obra_id = o.id OR cs.obra_id = o.id)
            LEFT JOIN monedas_indices m ON c.moneda_origen_id = m.id
            LEFT JOIN cobro_distribuciones dist ON c.id = dist.cobro_id
            ORDER BY c.fecha DESC, c.id DESC
        ''')
        rows = cursor.fetchall()
        return [dict(ix) for ix in rows]


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


def add_desvio(cobro_id, destino, monto, motivo, fecha, decreto_destino_id=None, nro_op=None, obra_id=None, gasto_nombre=None, gasto_expediente_imuh=None):
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
    
        cursor.execute('SELECT monto, fecha FROM cobros WHERE id = ?', (cobro_id,))
        c_row = cursor.fetchone()
        if not c_row:
            raise ValueError("Cobro no encontrado.")
            
        if fecha < c_row['fecha']:
            raise ValueError(f"La fecha del desvío ({fecha}) no puede ser anterior a la fecha del cobro ({c_row['fecha']}).")
        
        cursor.execute('SELECT * FROM cobro_distribuciones WHERE cobro_id = ?', (cobro_id,))
        dist = cursor.fetchone()
        fin_orig = dist['monto_fin_orig'] if dist else 0
        reserva = dist['monto_reserva'] if dist else 0
    
        cursor.execute('SELECT COALESCE(SUM(monto), 0) as tot_desvios FROM cobro_desvios WHERE cobro_id = ?', (cobro_id,))
        tot_desvios = cursor.fetchone()['tot_desvios']
    
        if (fin_orig + reserva + tot_desvios + monto) > (c_row['monto'] + TOLERANCE):
            raise ValueError("El monto del desvío supera el saldo libre disponible sin distribuir.")

        cursor.execute('''
            INSERT INTO cobro_desvios (cobro_id, destino, monto, motivo, fecha, decreto_destino_id, nro_op, obra_id, gasto_nombre, gasto_expediente_imuh)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (cobro_id, destino, monto, motivo, fecha, decreto_destino_id, nro_op, obra_id, gasto_nombre, gasto_expediente_imuh))
        new_id = cursor.lastrowid
        conn.commit()

    if nro_op:
        g_id = None
        if gasto_expediente_imuh:
            with db_session() as c:
                r = c.execute("SELECT id FROM gastos_funcionamiento WHERE expediente_imuh = ?", (gasto_expediente_imuh,)).fetchone()
                if r: g_id = r['id']
        register_or_update_op(nro_op, obra_id=obra_id, gasto_id=g_id)
        
    return new_id


def delete_desvio(desvio_id):
    with db_session() as conn:
        cursor = conn.cursor()
        
        cursor.execute('SELECT COUNT(*) as cnt FROM cobro_desvios_recuperos WHERE desvio_id = ?', (desvio_id,))
        if cursor.fetchone()['cnt'] > 0:
            raise ValueError("No se puede borrar un desvío que ya tiene recuperos registrados.")
            
        cursor.execute('DELETE FROM cobro_desvios WHERE id = ?', (desvio_id,))
        conn.commit()


def update_desvio(desvio_id, nuevo_monto, nuevo_motivo, nueva_fecha, nuevo_nro_op):
    _validar_op_o_nota_db(nuevo_nro_op, nuevo_motivo, contexto="edición de desvío")
    if nuevo_monto <= 0:
        raise ValueError("El monto a desviar debe ser mayor a 0.")
        
    with db_session() as conn:
        cursor = conn.cursor()
        
        # Verificar suma recuperada
        cursor.execute('SELECT COALESCE(SUM(monto), 0) as tot_rec FROM cobro_desvios_recuperos WHERE desvio_id = ?', (desvio_id,))
        ya_recuperado = cursor.fetchone()['tot_rec']
        
        if nuevo_monto < ya_recuperado:
            raise ValueError(f"No puedes reducir el monto del desvío a {nuevo_monto:.2f} porque ya se recuperaron {ya_recuperado:.2f}.")
            
        cursor.execute('''
            UPDATE cobro_desvios 
            SET monto = ?, motivo = ?, fecha = ?, nro_op = ?
            WHERE id = ?
        ''', (nuevo_monto, nuevo_motivo, nueva_fecha, nuevo_nro_op, desvio_id))
        conn.commit()


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
        conn.commit()


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


def delete_desvio_recupero(recupero_id):
    with db_session() as conn:
        cursor = conn.cursor()
        cursor.execute('DELETE FROM cobro_desvios_recuperos WHERE id = ?', (recupero_id,))
        conn.commit()


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
        conn.commit()


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


def delete_reserva_uso_recupero(recupero_id):
    with db_session() as conn:
        cursor = conn.cursor()
        cursor.execute('DELETE FROM cobro_reserva_usos_recuperos WHERE id = ?', (recupero_id,))
        conn.commit()


def get_reserva_usos_by_cobro(cobro_id):
    with db_session() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM cobro_reserva_usos WHERE cobro_id = ? ORDER BY fecha ASC', (cobro_id,))
        rows = cursor.fetchall()
        return [dict(ix) for ix in rows]


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


def add_reserva_uso(cobro_id, monto, destino_tipo, destino_detalle, fecha, notas, decreto_destino_id=None, nro_op=None, obra_id=None, gasto_nombre=None, gasto_expediente_imuh=None):
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
        ''', (cobro_id, user_auth_id if 'user_auth_id' in locals() else None) if False else (cobro_id,)) # Simple tuple structure
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

        cursor.execute('''
            INSERT INTO cobro_reserva_usos (cobro_id, monto, destino_tipo, destino_detalle, fecha, notas, decreto_destino_id, nro_op, obra_id, gasto_nombre, gasto_expediente_imuh)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (cobro_id, monto, destino_tipo, destino_detalle, fecha, notas, decreto_destino_id, nro_op, obra_id, gasto_nombre, gasto_expediente_imuh))
        new_id = cursor.lastrowid
        conn.commit()
        
    if nro_op:
        g_id = None
        if gasto_expediente_imuh:
            with db_session() as c:
                r = c.execute("SELECT id FROM gastos_funcionamiento WHERE expediente_imuh = ?", (gasto_expediente_imuh,)).fetchone()
                if r: g_id = r['id']
        register_or_update_op(nro_op, obra_id=obra_id, gasto_id=g_id)
        
    return new_id


def delete_reserva_uso(uso_id):
    with db_session() as conn:
        cursor = conn.cursor()
        
        cursor.execute('SELECT COUNT(*) as cnt FROM cobro_reserva_usos_recuperos WHERE reserva_uso_id = ?', (uso_id,))
        if cursor.fetchone()['cnt'] > 0:
            raise ValueError("No se puede borrar un uso de reserva que ya tiene recuperos registrados.")
            
        cursor.execute('DELETE FROM cobro_reserva_usos WHERE id = ?', (uso_id,))
        conn.commit()


def update_reserva_uso(uso_id, nuevo_monto, nuevas_notas, nueva_fecha, nuevo_nro_op):
    _validar_op_o_nota_db(nuevo_nro_op, nuevas_notas, contexto="edición de préstamo de reserva")
    if nuevo_monto <= 0:
        raise ValueError("El monto del préstamo debe ser mayor a 0.")
        
    with db_session() as conn:
        cursor = conn.cursor()
        
        # Verificar suma recuperada
        cursor.execute('SELECT COALESCE(SUM(monto), 0) as tot_rec FROM cobro_reserva_usos_recuperos WHERE reserva_uso_id = ?', (uso_id,))
        ya_recuperado = cursor.fetchone()['tot_rec']
        
        if nuevo_monto < ya_recuperado:
            raise ValueError(f"No puedes reducir el préstamo de reserva a {nuevo_monto:.2f} porque ya se recuperaron {ya_recuperado:.2f}.")
            
        cursor.execute('''
            UPDATE cobro_reserva_usos 
            SET monto = ?, notas = ?, fecha = ?, nro_op = ?
            WHERE id = ?
        ''', (nuevo_monto, nuevas_notas, nueva_fecha, nuevo_nro_op, uso_id))
        conn.commit()


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


# Fix 10: Variantes optimizadas que filtran a nivel SQL para obras específicas

_DESVIOS_SELECT_INICIAL = '''
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
'''

_DESVIOS_SELECT_RESERVA = '''
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
'''


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


def renunciar_aporte_sueldo(aporte_id, fecha):
    with db_session() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            UPDATE aportes_sueldo 
            SET estado = 'Renunciado', fecha_renuncia = ?
            WHERE id = ?
        ''', (fecha, aporte_id))
        conn.commit()


def renunciar_aporte_sac(aporte_id, fecha):
    with db_session() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            UPDATE aportes_sac 
            SET estado = 'Renunciado', fecha_renuncia = ?
            WHERE id = ?
        ''', (fecha, aporte_id))
        conn.commit()

    # --- Solicitudes de Financiamiento CRUD ---

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
        conn.commit()
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
        conn.commit()


def delete_solicitud(solicitud_id):
    with db_session() as conn:
        cursor = conn.cursor()
        cursor.execute('DELETE FROM solicitudes_financiamiento WHERE id = ?', (solicitud_id,))
        conn.commit()


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
        conn.commit()

    # --- NUEVOS CRUDs PARA FIN ORIGINAL USOS Y MODIFICACIONES ---


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
                            cotiz = 1.0
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
        conn.commit()
        
    if nro_op:
        g_id = None
        if gasto_expediente_imuh:
            with db_session() as c:
                r = c.execute("SELECT id FROM gastos_funcionamiento WHERE expediente_imuh = ?", (gasto_expediente_imuh,)).fetchone()
                if r: g_id = r['id']
        register_or_update_op(nro_op, obra_id=target_obra_id, gasto_id=g_id)
        
    return new_id


def delete_fin_original_uso(uso_id):
    with db_session() as conn:
        cursor = conn.cursor()
        cursor.execute('DELETE FROM cobro_fin_original_usos WHERE id = ?', (uso_id,))
        conn.commit()


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
                    if cotiz is None or cotiz <= 0:
                        cotiz = 1.0
                    if cant_mon is None:
                        cant_mon = round(monto / cotiz, 6) if cotiz > 0 else 0.0

        cursor.execute('''
            UPDATE cobro_fin_original_usos
            SET monto = ?, fecha = ?, nro_op = ?, notas = ?, obra_id = ?, gasto_nombre = ?, gasto_expediente_imuh = ?,
                cantidad_moneda_amortizada = ?, cotizacion_pago = ?, convenio_solicitud_id = ?, motivo_sobrepago = ?
            WHERE id = ?
        ''', (monto, fecha, nro_op, notas, target_obra_id, gasto_nombre, gasto_expediente_imuh,
              cant_mon, cotiz, c_sol_id, motivo_sp, uso_id))
        conn.commit()


def update_desvio(desvio_id, monto, destino, motivo, fecha, decreto_destino_id, nro_op):
    _validar_op_o_nota_db(nro_op, motivo, contexto="desvío")
    if monto <= 0:
        raise ValueError("El monto del desvío debe ser mayor a 0.")
    with db_session() as conn:
        cursor = conn.cursor()
    
        cursor.execute('SELECT cobro_id FROM cobro_desvios WHERE id = ?', (desvio_id,))
        row_desv = cursor.fetchone()
        if not row_desv:
            raise ValueError("Desvío no encontrado.")
        cobro_id = row_desv['cobro_id']
    
        cursor.execute('SELECT COALESCE(SUM(monto), 0) as tot_rec FROM cobro_desvios_recuperos WHERE desvio_id = ?', (desvio_id,))
        tot_rec = cursor.fetchone()['tot_rec']
        if monto < (tot_rec - TOLERANCE):
            raise ValueError(f"No se puede reducir el monto del desvío por debajo del total ya recuperado ({tot_rec:.2f}).")
        
        cursor.execute('SELECT monto FROM cobros WHERE id = ?', (cobro_id,))
        c_row = cursor.fetchone()
    
        cursor.execute('SELECT * FROM cobro_distribuciones WHERE cobro_id = ?', (cobro_id,))
        dist = cursor.fetchone()
        fin_orig = dist['monto_fin_orig'] if dist else 0
        reserva = dist['monto_reserva'] if dist else 0
    
        cursor.execute('SELECT COALESCE(SUM(monto), 0) as tot FROM cobro_desvios WHERE cobro_id = ? AND id != ?', (cobro_id, desvio_id))
        otros_desvios = cursor.fetchone()['tot']
    
        if (fin_orig + reserva + otros_desvios + monto) > (c_row['monto'] + TOLERANCE):
            raise ValueError(f"La suma con este desvío editado ({fin_orig + reserva + otros_desvios + monto:.2f}) supera el monto total del cobro ({c_row['monto']:.2f}).")
        
        cursor.execute('''
            UPDATE cobro_desvios
            SET monto = ?, destino = ?, motivo = ?, fecha = ?, decreto_destino_id = ?, nro_op = ?
            WHERE id = ?
        ''', (monto, destino, motivo, fecha, decreto_destino_id, nro_op, desvio_id))
        conn.commit()


def update_reserva_uso(uso_id, monto, destino_tipo, destino_detalle, fecha, notas, decreto_destino_id, nro_op):
    _validar_op_o_nota_db(nro_op, notas, contexto="uso de reserva")
    if monto <= 0:
        raise ValueError("El monto debe ser mayor a 0.")
    with db_session() as conn:
        cursor = conn.cursor()
    
        cursor.execute('SELECT cobro_id FROM cobro_reserva_usos WHERE id = ?', (uso_id,))
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
        reserva_original = row_dist['monto_reserva'] if row_dist else 0
    
        cursor.execute('SELECT COALESCE(SUM(monto), 0) as tot_usado FROM cobro_reserva_usos WHERE cobro_id = ? AND id != ?', (cobro_id, uso_id))
        otros_usos = cursor.fetchone()['tot_usado']
    
        if (otros_usos + monto) > (reserva_original + TOLERANCE):
            raise ValueError(f"El monto a usar editado ({monto:.2f}) supera el saldo disponible de reserva ({reserva_original - otros_usos:.2f}).")
        
        cursor.execute('''
            UPDATE cobro_reserva_usos
            SET monto = ?, destino_tipo = ?, destino_detalle = ?, fecha = ?, notas = ?, decreto_destino_id = ?, nro_op = ?
            WHERE id = ?
        ''', (monto, destino_tipo, destino_detalle, fecha, notas, decreto_destino_id, nro_op, uso_id))
        conn.commit()


def update_desvio_recupero(rec_id, monto, fecha, destino_tipo, destino_detalle, decreto_destino_id, nro_op, notas=None):
    _validar_op_o_nota_db(nro_op, notas, contexto="recupero de desvío")
    if monto <= 0:
        raise ValueError("El monto recuperado debe ser mayor a 0.")
    with db_session() as conn:
        cursor = conn.cursor()
    
        cursor.execute('SELECT desvio_id FROM cobro_desvios_recuperos WHERE id = ?', (rec_id,))
        rec_row = cursor.fetchone()
        if not rec_row:
            raise ValueError("Recupero no encontrado.")
        desvio_id = rec_row['desvio_id']
    
        cursor.execute('SELECT monto FROM cobro_desvios WHERE id = ?', (desvio_id,))
        d_row = cursor.fetchone()
    
        cursor.execute('SELECT COALESCE(SUM(monto), 0) as tot_recuperado FROM cobro_desvios_recuperos WHERE desvio_id = ? AND id != ?', (desvio_id, rec_id))
        otros_recuperos = cursor.fetchone()['tot_recuperado']
    
        if (otros_recuperos + monto) > (d_row['monto'] + TOLERANCE):
            raise ValueError(f"El monto a recuperar editado ({monto:.2f}) supera el saldo adeudado del desvío ({d_row['monto'] - otros_recuperos:.2f}).")
        
        cursor.execute('''
            UPDATE cobro_desvios_recuperos
            SET monto = ?, fecha = ?, destino_tipo = ?, destino_detalle = ?, decreto_destino_id = ?, nro_op = ?, notas = ?
            WHERE id = ?
        ''', (monto, fecha, destino_tipo, destino_detalle, decreto_destino_id, nro_op, notas, rec_id))
        conn.commit()


def update_reserva_uso_recupero(rec_id, monto, fecha, destino_tipo, destino_detalle, decreto_destino_id, nro_op, notas=None):
    _validar_op_o_nota_db(nro_op, notas, contexto="recupero de reserva")
    if monto <= 0:
        raise ValueError("El monto recuperado debe ser mayor a 0.")
    with db_session() as conn:
        cursor = conn.cursor()
    
        cursor.execute('SELECT reserva_uso_id FROM cobro_reserva_usos_recuperos WHERE id = ?', (rec_id,))
        rec_row = cursor.fetchone()
        if not rec_row:
            raise ValueError("Recupero de reserva no encontrado.")
        reserva_uso_id = rec_row['reserva_uso_id']
    
        cursor.execute('SELECT monto FROM cobro_reserva_usos WHERE id = ?', (reserva_uso_id,))
        ru_row = cursor.fetchone()
    
        cursor.execute('SELECT COALESCE(SUM(monto), 0) as tot_recuperado FROM cobro_reserva_usos_recuperos WHERE reserva_uso_id = ? AND id != ?', (reserva_uso_id, rec_id))
        otros_recuperos = cursor.fetchone()['tot_recuperado']
    
        if (otros_recuperos + monto) > (ru_row['monto'] + TOLERANCE):
            raise ValueError(f"El monto a recuperar editado ({monto:.2f}) supera el saldo adeudado del desvío de reserva ({ru_row['monto'] - otros_recuperos:.2f}).")
        
        cursor.execute('''
            UPDATE cobro_reserva_usos_recuperos
            SET monto = ?, fecha = ?, destino_tipo = ?, destino_detalle = ?, decreto_destino_id = ?, nro_op = ?, notas = ?
            WHERE id = ?
        ''', (monto, fecha, destino_tipo, destino_detalle, decreto_destino_id, nro_op, notas, rec_id))
        conn.commit()



# --- NUEVOS CRUDs PARA PROVEEDORES, OBRAS Y GASTOS DE FUNCIONAMIENTO (v2.1) ---

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
        conn.commit()
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
        conn.commit()


def update_proveedor_obra_estado(prov_id, activo):
    with db_session() as conn:
        cursor = conn.cursor()
        cursor.execute('UPDATE proveedores_obras SET activo = ? WHERE id = ?', (activo, prov_id))
        conn.commit()


def delete_proveedor_obra(prov_id):
    with db_session() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT COUNT(*) as cnt FROM obras WHERE proveedor_id = ?', (prov_id,))
        if cursor.fetchone()['cnt'] > 0:
            raise ValueError("No se puede eliminar el proveedor porque está vinculado a una o más obras.")
        cursor.execute('DELETE FROM proveedores_obras WHERE id = ?', (prov_id,))
        conn.commit()


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
        conn.commit()
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
        conn.commit()


def update_proveedor_funcionamiento_estado(prov_id, activo):
    with db_session() as conn:
        cursor = conn.cursor()
        cursor.execute('UPDATE proveedores_funcionamiento SET activo = ? WHERE id = ?', (activo, prov_id))
        conn.commit()


def delete_proveedor_funcionamiento(prov_id):
    with db_session() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT COUNT(*) as cnt FROM gastos_funcionamiento WHERE proveedor_id = ?', (prov_id,))
        if cursor.fetchone()['cnt'] > 0:
            raise ValueError("No se puede eliminar el proveedor porque está vinculado a uno o más gastos de funcionamiento.")
        cursor.execute('DELETE FROM proveedores_funcionamiento WHERE id = ?', (prov_id,))
        conn.commit()


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


def add_obra(nombre, expediente_imuh, proveedor_id=None, moneda_id=1, monto_contrato_moneda=0.0, cotizacion_base_contrato=1.0, fecha_contrato=None, notas_contrato=None):
    if not nombre or not nombre.strip():
        raise ValueError("El nombre de la obra no puede estar vacío.")
    if not expediente_imuh or not expediente_imuh.strip():
        raise ValueError("El expediente IMUH no puede estar vacío.")
    import utils
    if not utils.validar_expediente_imuh(expediente_imuh):
        raise ValueError("El Expediente IMUH tiene un formato inválido (debe ser 8XXXXXX-I-AAAA o similar).")
        
    exp_normalizado = utils.normalizar_expediente_imuh(expediente_imuh)
    
    if get_obra_by_expediente(exp_normalizado):
        raise ValueError(f"Ya existe una obra registrada con el expediente {exp_normalizado}.")
    
    # Sincronización inmutable del camino de escritura
    m_id = int(moneda_id or 1)
    monto_mon = float(monto_contrato_moneda or 0.0)
    cotiz_base = float(cotizacion_base_contrato or 1.0)
    if m_id == 1:
        cotiz_base = 1.0
        monto_pesos = monto_mon
    else:
        monto_pesos = monto_mon * cotiz_base

    with db_session() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO obras (
                nombre, expediente_imuh, activa, proveedor_id,
                moneda_id, monto_contrato_moneda, cotizacion_base_contrato,
                monto_contrato, fecha_contrato, notas_contrato
            )
            VALUES (?, ?, 1, ?, ?, ?, ?, ?, ?, ?)
        ''', (nombre.strip(), exp_normalizado, proveedor_id,
              m_id, monto_mon, cotiz_base,
              monto_pesos, fecha_contrato, notas_contrato.strip() if notas_contrato else None))
        obra_id = cursor.lastrowid
        conn.commit()
        return obra_id


def get_obras(only_active=False):
    with db_session() as conn:
        cursor = conn.cursor()
        query = '''
            SELECT o.*, p.razon_social as proveedor_razon_social, p.cuit as proveedor_cuit,
                   COALESCE(m.codigo, 'ARS') as moneda_codigo,
                   COALESCE(m.simbolo, '$') as moneda_simbolo,
                   COALESCE(m.nombre, 'Peso Argentino') as moneda_nombre
            FROM obras o
            LEFT JOIN proveedores_obras p ON o.proveedor_id = p.id
            LEFT JOIN monedas_indices m ON o.moneda_id = m.id
        '''
        if only_active:
            query += ' WHERE o.activa = 1'
        query += ' ORDER BY o.nombre ASC'
        cursor.execute(query)
        rows = cursor.fetchall()
        return [dict(ix) for ix in rows]


def get_obra(obra_id):
    with db_session() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT o.*, p.razon_social as proveedor_razon_social, p.cuit as proveedor_cuit,
                   COALESCE(m.codigo, 'ARS') as moneda_codigo,
                   COALESCE(m.simbolo, '$') as moneda_simbolo,
                   COALESCE(m.nombre, 'Peso Argentino') as moneda_nombre
            FROM obras o
            LEFT JOIN proveedores_obras p ON o.proveedor_id = p.id
            LEFT JOIN monedas_indices m ON o.moneda_id = m.id
            WHERE o.id = ?
        ''', (obra_id,))
        row = cursor.fetchone()
        return dict(row) if row else None


def get_obra_by_expediente(expediente_imuh):
    with db_session() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT o.*, p.razon_social as proveedor_razon_social, p.cuit as proveedor_cuit,
                   COALESCE(m.codigo, 'ARS') as moneda_codigo,
                   COALESCE(m.simbolo, '$') as moneda_simbolo,
                   COALESCE(m.nombre, 'Peso Argentino') as moneda_nombre
            FROM obras o
            LEFT JOIN proveedores_obras p ON o.proveedor_id = p.id
            LEFT JOIN monedas_indices m ON o.moneda_id = m.id
            WHERE o.expediente_imuh = ?
        ''', (expediente_imuh,))
        row = cursor.fetchone()
        return dict(row) if row else None


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
            conn.commit()
            return gasto_id
        except sqlite3.IntegrityError:
            cursor.execute('SELECT * FROM gastos_funcionamiento WHERE expediente_imuh = ?', (expediente_imuh,))
            row = cursor.fetchone()
            if row:
                cursor.execute('UPDATE gastos_funcionamiento SET nombre = ?, activo = 1, proveedor_id = COALESCE(?, proveedor_id) WHERE id = ?', (nombre, proveedor_id, row['id']))
                conn.commit()
                return row['id']
            raise ValueError(f"Ya existe un Gasto FUN con el expediente {expediente_imuh}.")


def update_gasto_funcionamiento_proveedor(gasto_id, proveedor_id):
    with db_session() as conn:
        cursor = conn.cursor()
        cursor.execute('UPDATE gastos_funcionamiento SET proveedor_id = ? WHERE id = ?', (proveedor_id, gasto_id))
        conn.commit()


def update_gasto_funcionamiento_estado(gasto_id, activo):
    if activo not in [0, 1]:
        raise ValueError("El estado activo debe ser 0 o 1.")
    with db_session() as conn:
        cursor = conn.cursor()
        cursor.execute('UPDATE gastos_funcionamiento SET activo = ? WHERE id = ?', (activo, gasto_id))
        conn.commit()


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
        conn.commit()


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
        conn.commit()


def update_obra(obra_id, nombre, expediente_imuh, activa, proveedor_id=None,
                moneda_id=None, monto_contrato_moneda=None, cotizacion_base_contrato=None,
                fecha_contrato=None, notas_contrato=None, motivo_rectificacion=None):
    if not nombre or not nombre.strip():
        raise ValueError("El nombre de la obra no puede estar vacío.")
    if not expediente_imuh or not expediente_imuh.strip():
        raise ValueError("El expediente IMUH no puede estar vacío.")
    import utils
    if not utils.validar_expediente_imuh(expediente_imuh):
        raise ValueError("El Expediente IMUH tiene un formato inválido.")
        
    exp_normalizado = utils.normalizar_expediente_imuh(expediente_imuh)

    with db_session() as conn:
        cursor = conn.cursor()
        # Verificar duplicados del expediente excluyendo la obra actual
        cursor.execute('SELECT id FROM obras WHERE expediente_imuh = ? AND id != ?', (exp_normalizado, obra_id))
        if cursor.fetchone():
            raise ValueError(f"Ya existe otra obra registrada con el expediente IMUH '{exp_normalizado}'.")
            
        cursor.execute('SELECT moneda_id, monto_contrato_moneda, cotizacion_base_contrato, monto_contrato, fecha_contrato, notas_contrato FROM obras WHERE id = ?', (obra_id,))
        cur_row = cursor.fetchone()
        
        old_m_id = int(cur_row['moneda_id'] or 1)
        m_id = int(moneda_id if moneda_id is not None else old_m_id)
        monto_mon = float(monto_contrato_moneda if monto_contrato_moneda is not None else (cur_row['monto_contrato_moneda'] or cur_row['monto_contrato'] or 0.0))
        old_cotiz = float(cur_row['cotizacion_base_contrato'] or 1.0)
        cotiz_base = float(cotizacion_base_contrato if cotizacion_base_contrato is not None else old_cotiz)
        f_contrato = fecha_contrato if fecha_contrato is not None else cur_row['fecha_contrato']
        n_contrato = notas_contrato if notas_contrato is not None else cur_row['notas_contrato']

        pagos_existentes = get_pagos_detalle_por_obra(obra_id)
        tiene_pagos = (len(pagos_existentes) > 0 or get_total_pagado_obra(obra_id) > 0)

        # Guarda 1: Bloqueo terminante de cambio de moneda si ya hay pagos
        if m_id != old_m_id and tiene_pagos:
            raise ValueError("No se puede modificar la moneda de contratación de una obra que ya registra pagos u órdenes de pago emitidas.")

        # Guarda 2: Rectificación de cotización base inicial si ya hay pagos
        if m_id != 1 and abs(cotiz_base - old_cotiz) > 0.0001 and tiene_pagos:
            if not motivo_rectificacion or not str(motivo_rectificacion).strip():
                raise ValueError("Debe ingresar un motivo / justificación obligatoria para rectificar la cotización base de una obra con pagos registrados.")
            import datetime
            fecha_hoy = datetime.date.today().strftime('%Y-%m-%d')
            constancia = f"\n[Rectificación Cotiz. Base: ${old_cotiz:,.2f} -> ${cotiz_base:,.2f} | Motivo: {str(motivo_rectificacion).strip()} | Fecha: {fecha_hoy}]"
            n_contrato = (n_contrato or "") + constancia

        if m_id == 1:
            cotiz_base = 1.0
            monto_pesos = monto_mon
            total_pagado = get_total_pagado_obra(obra_id)
            if monto_pesos > 0 and monto_pesos < (total_pagado - TOLERANCE):
                raise ValueError(f"No se puede reducir el monto de contrato por debajo del total ya pagado a la contratista (${total_pagado:,.2f})")
        else:
            monto_pesos = monto_mon * cotiz_base
            resumen = get_resumen_contrato_obra(obra_id)
            if resumen:
                total_amortizado = float(resumen.get('total_moneda_amortizada') or 0.0)
                cant_adic = float(resumen.get('cantidad_adicionales_moneda') or 0.0)
                nuevo_tope_moneda = monto_mon + cant_adic
                cod_mon = resumen.get('moneda_codigo') or 'UVI'
                if monto_mon > 0 and nuevo_tope_moneda < (total_amortizado - 0.0001):
                    raise ValueError(f"No se puede reducir el contrato en {cod_mon} ({nuevo_tope_moneda:,.2f}) por debajo del total ya amortizado ({total_amortizado:,.2f} {cod_mon}).")

        cursor.execute('''
            UPDATE obras
            SET nombre = ?, expediente_imuh = ?, activa = ?, proveedor_id = ?,
                moneda_id = ?, monto_contrato_moneda = ?, cotizacion_base_contrato = ?,
                monto_contrato = ?, fecha_contrato = ?, notas_contrato = ?
            WHERE id = ?
        ''', (nombre.strip(), exp_normalizado, activa, proveedor_id,
              m_id, monto_mon, cotiz_base,
              monto_pesos, f_contrato, n_contrato, obra_id))
        
        # Sincronizar campo expediente_imuh en solicitudes_financiamiento por consistencia
        cursor.execute('''
            UPDATE solicitudes_financiamiento
            SET expediente_imuh = ?
            WHERE obra_id = ?
        ''', (exp_normalizado, obra_id))
        
        conn.commit()


def delete_obra(obra_id):
    with db_session() as conn:
        cursor = conn.cursor()
        
        # Verificar si tiene movimientos asociados
        cursor.execute('SELECT COUNT(*) as cnt FROM cobro_desvios WHERE obra_id = ?', (obra_id,))
        if cursor.fetchone()['cnt'] > 0:
            raise ValueError("No se puede eliminar la obra porque tiene desvíos directos asociados. Pruebe inhabilitándola.")
            
        cursor.execute('SELECT COUNT(*) as cnt FROM cobro_reserva_usos WHERE obra_id = ?', (obra_id,))
        if cursor.fetchone()['cnt'] > 0:
            raise ValueError("No se puede eliminar la obra porque tiene desvíos desde reserva asociados. Pruebe inhabilitándola.")
            
        cursor.execute('SELECT COUNT(*) as cnt FROM solicitudes_financiamiento WHERE obra_id = ?', (obra_id,))
        if cursor.fetchone()['cnt'] > 0:
            raise ValueError("No se puede eliminar la obra porque tiene solicitudes de financiamiento asociadas. Pruebe inhabilitándola.")

        cursor.execute('SELECT COUNT(*) as cnt FROM decretos_obras WHERE obra_id = ?', (obra_id,))
        if cursor.fetchone()['cnt'] > 0:
            raise ValueError("No se puede eliminar la obra porque está asociada a decretos. Pruebe inhabilitándola.")

        cursor.execute('DELETE FROM obras WHERE id = ?', (obra_id,))
        conn.commit()


# --- ADICIONALES DE OBRA Y ANÁLISIS BIMONETARIO FIFO ---

def add_obra_adicional(obra_id, nro_resolucion, fecha, cantidad_moneda, cotizacion_base=1.0, motivo=None):
    if not obra_id:
        raise ValueError("Debe especificar la obra.")
    if not nro_resolucion or not str(nro_resolucion).strip():
        raise ValueError("El N° de Resolución del adicional no puede estar vacío.")
    if not fecha:
        raise ValueError("La fecha del adicional es obligatoria.")
    try:
        cant_mon = float(cantidad_moneda)
    except (ValueError, TypeError):
        raise ValueError("La cantidad en moneda debe ser un número válido.")
    if cant_mon <= 0:
        raise ValueError("La cantidad en moneda debe ser mayor a 0.")
        
    try:
        cotiz = float(cotizacion_base)
    except (ValueError, TypeError):
        cotiz = 1.0
    if cotiz <= 0:
        cotiz = 1.0
        
    monto_ars = round(cant_mon * cotiz, 2)
    
    with db_session() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT id, moneda_id FROM obras WHERE id = ?', (obra_id,))
        o_row = cursor.fetchone()
        if not o_row:
            raise ValueError("Obra no encontrada.")
            
        cursor.execute('''
            INSERT INTO obra_adicionales (obra_id, nro_resolucion, fecha, cantidad_moneda, cotizacion_base, monto_equivalente_ars, motivo)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (obra_id, str(nro_resolucion).strip(), str(fecha), cant_mon, cotiz, monto_ars, motivo.strip() if motivo else None))
        new_id = cursor.lastrowid
        conn.commit()
        return new_id


def get_obra_adicionales(obra_id):
    with db_session() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT * FROM obra_adicionales
            WHERE obra_id = ?
            ORDER BY fecha ASC, id ASC
        ''', (obra_id,))
        return [dict(r) for r in cursor.fetchall()]


def delete_obra_adicional(adicional_id):
    with db_session() as conn:
        cursor = conn.cursor()
        cursor.execute('DELETE FROM obra_adicionales WHERE id = ?', (adicional_id,))
        conn.commit()


def get_resumen_contrato_obra(obra_id):
    """
    Consolida la posición contractual y financiera de una obra.
    Para obras bimonetarias (UVIs, USD, etc.), aplica costeo cronológico FIFO sobre los tramos
    (Contrato Base + Adicionales por Resolución) y determina el Costo Base Histórico
    y el Resultado por Indexación acumulado.
    """
    obra = get_obra(obra_id)
    if not obra:
        return None
        
    moneda_id = obra.get('moneda_id') or 1
    es_bimonetaria = (moneda_id != 1)
    
    # 1. Definición de Tramos Contractuales (FIFO)
    # Tramo 0: Contrato Base
    monto_base_moneda = float(obra.get('monto_contrato_moneda') or 0.0)
    cotiz_base_contrato = float(obra.get('cotizacion_base_contrato') or 1.0)
    if not es_bimonetaria:
        monto_base_moneda = float(obra.get('monto_contrato') or 0.0)
        cotiz_base_contrato = 1.0
    costo_base_contrato_ars = monto_base_moneda * cotiz_base_contrato
    
    tramos = [{
        'tipo': 'Contrato Base',
        'nro_resolucion': 'Original',
        'fecha': obra.get('fecha_contrato') or 'Inicial',
        'cantidad_moneda': monto_base_moneda,
        'cotizacion_base': cotiz_base_contrato,
        'monto_ars': costo_base_contrato_ars,
        'moneda_amortizada': 0.0,
        'costo_base_amortizado_ars': 0.0,
        'saldo_moneda': monto_base_moneda
    }]
    
    # Tramos 1..N: Adicionales ordenados cronológicamente
    adicionales = get_obra_adicionales(obra_id)
    cant_adicionales_moneda = 0.0
    costo_adicionales_ars = 0.0
    for adic in adicionales:
        cant_adic = float(adic.get('cantidad_moneda') or 0.0)
        cotiz_adic = float(adic.get('cotizacion_base') or 1.0)
        monto_adic_ars = float(adic.get('monto_equivalente_ars') or (cant_adic * cotiz_adic))
        cant_adicionales_moneda += cant_adic
        costo_adicionales_ars += monto_adic_ars
        tramos.append({
            'tipo': 'Adicional',
            'nro_resolucion': adic.get('nro_resolucion') or '',
            'fecha': str(adic.get('fecha') or ''),
            'cantidad_moneda': cant_adic,
            'cotizacion_base': cotiz_adic,
            'monto_ars': monto_adic_ars,
            'moneda_amortizada': 0.0,
            'costo_base_amortizado_ars': 0.0,
            'saldo_moneda': cant_adic
        })
        
    total_contratado_moneda = monto_base_moneda + cant_adicionales_moneda
    total_costo_base_contratado_ars = costo_base_contrato_ars + costo_adicionales_ars
    
    # 2. Pagos efectivos imputados a la obra
    with db_session() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT id, fecha, monto, cantidad_moneda_amortizada, cotizacion_pago, 'Fin Original' as fuente
            FROM cobro_fin_original_usos
            WHERE obra_id = ?
            ORDER BY fecha ASC, id ASC
        ''', (obra_id,))
        pagos_fo = [dict(r) for r in cursor.fetchall()]
        
        cursor.execute('''
            SELECT id, fecha, monto, cantidad_moneda_amortizada, cotizacion_pago, 'Fondos Propios' as fuente
            FROM pagos_fondos_propios
            WHERE obra_id = ?
            ORDER BY fecha ASC, id ASC
        ''', (obra_id,))
        pagos_fp = [dict(r) for r in cursor.fetchall()]
        
        cursor.execute('''
            SELECT id, fecha, monto, NULL as cantidad_moneda_amortizada, 1.0 as cotizacion_pago, 'Desvío Fin Original' as fuente
            FROM cobro_desvios
            WHERE obra_id = ?
            ORDER BY fecha ASC, id ASC
        ''', (obra_id,))
        pagos_desv = [dict(r) for r in cursor.fetchall()]
        
        cursor.execute('''
            SELECT id, fecha, monto, NULL as cantidad_moneda_amortizada, 1.0 as cotizacion_pago, 'Uso Reserva' as fuente
            FROM cobro_reserva_usos
            WHERE obra_id = ?
            ORDER BY fecha ASC, id ASC
        ''', (obra_id,))
        pagos_res = [dict(r) for r in cursor.fetchall()]
        
    todos_pagos = pagos_fo + pagos_fp + pagos_desv + pagos_res
    todos_pagos.sort(key=lambda x: (str(x.get('fecha') or ''), x.get('id') or 0))
    
    total_pagado_efectivo_ars = sum(float(p.get('monto') or 0.0) for p in todos_pagos)
    
    # Cálculo de moneda amortizada
    total_moneda_amortizada = 0.0
    for p in todos_pagos:
        monto_ars = float(p.get('monto') or 0.0)
        if not es_bimonetaria:
            cant = monto_ars
        else:
            cant_raw = p.get('cantidad_moneda_amortizada')
            if cant_raw is not None and float(cant_raw) > 0:
                cant = float(cant_raw)
            else:
                cotiz_p = float(p.get('cotizacion_pago') or 1.0)
                cant = (monto_ars / cotiz_p) if cotiz_p > 0 else 0.0
        total_moneda_amortizada += cant
        
    # 3. Aplicación del algoritmo FIFO sobre los tramos
    rem_amortizar = total_moneda_amortizada
    costo_base_amortizado_ars = 0.0
    last_cotiz = cotiz_base_contrato
    
    for tramo in tramos:
        last_cotiz = tramo['cotizacion_base']
        if rem_amortizar <= 0:
            break
        capacidad = tramo['cantidad_moneda']
        tomar = min(rem_amortizar, capacidad)
        tramo['moneda_amortizada'] = tomar
        tramo_costo = tomar * tramo['cotizacion_base']
        tramo['costo_base_amortizado_ars'] = tramo_costo
        tramo['saldo_moneda'] = max(0.0, capacidad - tomar)
        costo_base_amortizado_ars += tramo_costo
        rem_amortizar -= tomar
        
    if rem_amortizar > 0:
        costo_base_amortizado_ars += (rem_amortizar * last_cotiz)
        
    resultado_indexacion_ars = total_pagado_efectivo_ars - costo_base_amortizado_ars
    saldo_moneda_remanente = max(0.0, total_contratado_moneda - total_moneda_amortizada)
    porcentaje_avance = (total_moneda_amortizada / total_contratado_moneda * 100.0) if total_contratado_moneda > 0 else 0.0
    
    return {
        'obra_id': obra_id,
        'nombre': obra.get('nombre'),
        'expediente_imuh': obra.get('expediente_imuh'),
        'moneda_id': moneda_id,
        'moneda_codigo': obra.get('moneda_codigo') or 'ARS',
        'moneda_simbolo': obra.get('moneda_simbolo') or '$',
        'moneda_nombre': obra.get('moneda_nombre') or 'Peso Argentino',
        'es_bimonetaria': es_bimonetaria,
        'monto_contrato_base_moneda': monto_base_moneda,
        'cotizacion_base_contrato': cotiz_base_contrato,
        'costo_base_contrato_ars': costo_base_contrato_ars,
        'cantidad_adicionales_moneda': cant_adicionales_moneda,
        'costo_adicionales_ars': costo_adicionales_ars,
        'total_contratado_moneda': total_contratado_moneda,
        'total_costo_base_contratado_ars': total_costo_base_contratado_ars,
        'total_moneda_amortizada': total_moneda_amortizada,
        'saldo_moneda_remanente': saldo_moneda_remanente,
        'porcentaje_avance_moneda': min(100.0, porcentaje_avance),
        'total_pagado_efectivo_ars': total_pagado_efectivo_ars,
        'costo_base_amortizado_ars': costo_base_amortizado_ars,
        'resultado_indexacion_ars': resultado_indexacion_ars,
        'tramos': tramos
    }


def get_pagos_detalle_por_obra(obra_id):
    """
    Retorna el detalle cronológico de órdenes de pago imputadas a la obra
    con su desglose bimonetario y la imputación FIFO al Costo Base y Resultado por Indexación.
    """
    obra = get_obra(obra_id)
    if not obra:
        return []
        
    moneda_id = obra.get('moneda_id') or 1
    es_bimonetaria = (moneda_id != 1)
    
    resumen = get_resumen_contrato_obra(obra_id)
    tramos_base = []
    if resumen and resumen.get('tramos'):
        for t in resumen['tramos']:
            tramos_base.append({
                'tipo': t['tipo'],
                'cantidad_moneda': t['cantidad_moneda'],
                'cotizacion_base': t['cotizacion_base'],
                'disponible': t['cantidad_moneda']
            })
    last_cotiz_base = resumen.get('cotizacion_base_contrato') or 1.0 if resumen else 1.0
    
    with db_session() as conn:
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT fu.id, fu.fecha, fu.nro_op, fu.monto as monto_ars,
                   fu.cantidad_moneda_amortizada, fu.cotizacion_pago,
                   fu.convenio_solicitud_id, fu.motivo_sobrepago, fu.notas,
                   c.origen_tipo, cs.nro_certificado, conv.nombre_convenio,
                   'Fin Original' as tipo_fuente
            FROM cobro_fin_original_usos fu
            LEFT JOIN cobros c ON fu.cobro_id = c.id
            LEFT JOIN convenio_solicitudes cs ON (fu.convenio_solicitud_id = cs.id OR c.convenio_solicitud_id = cs.id)
            LEFT JOIN convenios conv ON cs.convenio_id = conv.id
            WHERE fu.obra_id = ?
        ''', (obra_id,))
        pagos_fo = [dict(r) for r in cursor.fetchall()]
        
        cursor.execute('''
            SELECT pfp.id, pfp.fecha, pfp.nro_op, pfp.monto as monto_ars,
                   pfp.cantidad_moneda_amortizada, pfp.cotizacion_pago,
                   pfp.convenio_solicitud_id, pfp.motivo_sobrepago, pfp.observaciones as notas,
                   'fondos_propios' as origen_tipo, cs.nro_certificado, conv.nombre_convenio,
                   'Fondos Propios' as tipo_fuente
            FROM pagos_fondos_propios pfp
            LEFT JOIN convenio_solicitudes cs ON pfp.convenio_solicitud_id = cs.id
            LEFT JOIN convenios conv ON cs.convenio_id = conv.id
            WHERE pfp.obra_id = ?
        ''', (obra_id,))
        pagos_fp = [dict(r) for r in cursor.fetchall()]
        
    todos = pagos_fo + pagos_fp
    todos.sort(key=lambda x: (str(x.get('fecha') or ''), x.get('id') or 0))
    
    for p in todos:
        monto_ars = float(p.get('monto_ars') or 0.0)
        if not es_bimonetaria:
            cant_mon = monto_ars
            cotiz = 1.0
        else:
            cant_raw = p.get('cantidad_moneda_amortizada')
            cotiz_raw = p.get('cotizacion_pago')
            cotiz = float(cotiz_raw) if (cotiz_raw and float(cotiz_raw) > 0) else 1.0
            if cant_raw is not None and float(cant_raw) > 0:
                cant_mon = float(cant_raw)
            else:
                cant_mon = round(monto_ars / cotiz, 6) if cotiz > 0 else 0.0
                
        p['cantidad_moneda_amortizada'] = cant_mon
        p['cotizacion_pago'] = cotiz
        
        rem = cant_mon
        costo_base_pago_ars = 0.0
        for tr in tramos_base:
            last_cotiz_base = tr['cotizacion_base']
            if rem <= 0:
                break
            if tr['disponible'] > 0:
                take = min(rem, tr['disponible'])
                costo_base_pago_ars += (take * tr['cotizacion_base'])
                tr['disponible'] -= take
                rem -= take
        if rem > 0:
            costo_base_pago_ars += (rem * last_cotiz_base)
            
        p['costo_base_ars'] = costo_base_pago_ars
        p['resultado_indexacion_ars'] = monto_ars - costo_base_pago_ars
        
        if p.get('nombre_convenio') or p.get('nro_certificado'):
            cert_txt = f" (Cert. {p['nro_certificado']})" if p.get('nro_certificado') else ""
            conv_txt = f" - {p['nombre_convenio']}" if p.get('nombre_convenio') else ""
            p['fuente_descripcion'] = f"Convenio{conv_txt}{cert_txt}"
        else:
            p['fuente_descripcion'] = p.get('tipo_fuente')
            
    return todos


def check_sobrepago_obra(obra_id, nuevo_monto_pesos=0.0, nueva_cantidad_moneda=0.0):
    """
    Verifica si un pago propuesto excede el tope de contrato.
    Retorna un diccionario de control con indicador booleano y mensaje explicativo.
    """
    obra = get_obra(obra_id)
    if not obra:
        return {'es_sobrepago': False, 'mensaje': ''}
        
    resumen = get_resumen_contrato_obra(obra_id)
    if not resumen:
        return {'es_sobrepago': False, 'mensaje': ''}
        
    es_bimonetaria = resumen['es_bimonetaria']
    simbolo = resumen['moneda_simbolo']
    codigo = resumen['moneda_codigo']
    
    if es_bimonetaria:
        tope = resumen['total_contratado_moneda']
        acumulado_previo = resumen['total_moneda_amortizada']
        nuevo_total = acumulado_previo + float(nueva_cantidad_moneda or 0.0)
        es_sobrepago = (tope > 0 and nuevo_total > (tope + 0.001))
        exceso = max(0.0, nuevo_total - tope)
        unidad = codigo
        msg = f"El total amortizado alcanzará {nuevo_total:,.2f} {codigo}, superando el contrato total ({tope:,.2f} {codigo}) por {exceso:,.2f} {codigo}."
    else:
        tope = resumen['total_costo_base_contratado_ars']
        acumulado_previo = resumen['total_pagado_efectivo_ars']
        nuevo_total = acumulado_previo + float(nuevo_monto_pesos or 0.0)
        es_sobrepago = (tope > 0 and nuevo_total > (tope + TOLERANCE))
        exceso = max(0.0, nuevo_total - tope)
        unidad = 'ARS'
        msg = f"El total pagado alcanzará ${nuevo_total:,.2f} ARS, superando el monto de contrato (${tope:,.2f} ARS) por ${exceso:,.2f} ARS."
        
    return {
        'es_sobrepago': es_sobrepago,
        'es_bimonetaria': es_bimonetaria,
        'tope': tope,
        'acumulado_previo': acumulado_previo,
        'nuevo_total': nuevo_total,
        'exceso': exceso,
        'unidad': unidad,
        'mensaje': msg if es_sobrepago else ''
    }


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


def add_decreto_obras(decreto_id, obra_ids):
    with db_session() as conn:
        cursor = conn.cursor()
        cursor.execute('DELETE FROM decretos_obras WHERE decreto_id = ?', (decreto_id,))
        for o_id in obra_ids:
            cursor.execute('INSERT INTO decretos_obras (decreto_id, obra_id) VALUES (?, ?)', (decreto_id, o_id))
        conn.commit()


def update_decreto_details_for_solicitud(decreto_id, nro_expediente, destino_fondos, pdf_path, expediente_imuh):
    with db_session() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            UPDATE decretos
            SET nro_expediente = ?, destino_fondos = ?, pdf_path = ?, expediente_imuh = ?
            WHERE id = ?
        ''', (nro_expediente, destino_fondos, pdf_path, expediente_imuh, decreto_id))
        conn.commit()


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

def obtener_detalles_compensacion_grupo(grupo_id):
    if not grupo_id:
        return None
    with db_session() as conn:
        cursor = conn.cursor()
        
        # Consultar recuperos de desvíos
        cursor.execute('''
            SELECT r.id as rec_id, r.monto, r.fecha as rec_fecha, r.nro_op as rec_op, r.destino_tipo, r.destino_detalle,
                   d.id as desvio_id, d.monto as desvio_monto, d.fecha as desvio_fecha, d.nro_op as desvio_op, d.destino as desvio_destino,
                   COALESCE(dec.id, conv.id) as dec_id,
                   COALESCE(dec.nro_decreto, conv.nro_convenio) as nro_decreto,
                   COALESCE(dec.anio, strftime('%Y', conv.fecha_firma)) as dec_anio
            FROM cobro_desvios_recuperos r
            JOIN cobro_desvios d ON r.desvio_id = d.id
            JOIN cobros c ON d.cobro_id = c.id
            LEFT JOIN cuotas q ON c.cuota_id = q.id
            LEFT JOIN decretos dec ON q.decreto_id = dec.id
            LEFT JOIN convenio_solicitudes csol ON c.convenio_solicitud_id = csol.id
            LEFT JOIN convenios conv ON csol.convenio_id = conv.id
            WHERE r.grupo_compensacion_id = ?
        ''', (grupo_id,))
        desv_recs = [dict(row) for row in cursor.fetchall()]
        
        # Consultar recuperos de reserva
        cursor.execute('''
            SELECT r.id as rec_id, r.monto, r.fecha as rec_fecha, r.nro_op as rec_op, r.destino_tipo, r.destino_detalle,
                   u.id as uso_id, u.monto as uso_monto, u.fecha as uso_fecha, u.nro_op as uso_op, u.destino_detalle as uso_destino,
                   COALESCE(dec.id, conv.id) as dec_id,
                   COALESCE(dec.nro_decreto, conv.nro_convenio) as nro_decreto,
                   COALESCE(dec.anio, strftime('%Y', conv.fecha_firma)) as dec_anio
            FROM cobro_reserva_usos_recuperos r
            JOIN cobro_reserva_usos u ON r.reserva_uso_id = u.id
            JOIN cobros c ON u.cobro_id = c.id
            LEFT JOIN cuotas q ON c.cuota_id = q.id
            LEFT JOIN decretos dec ON q.decreto_id = dec.id
            LEFT JOIN convenio_solicitudes csol ON c.convenio_solicitud_id = csol.id
            LEFT JOIN convenios conv ON csol.convenio_id = conv.id
            WHERE r.grupo_compensacion_id = ?
        ''', (grupo_id,))
        res_recs = [dict(row) for row in cursor.fetchall()]
        
        return {
            'desvios': desv_recs,
            'reservas': res_recs
        }

def get_op_info(nro_op):
    with db_session() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT nro_op, obra_id, gasto_id FROM op_bejerman WHERE nro_op = ?", (str(nro_op).strip(),))
        row = cursor.fetchone()
        if row:
            return dict(row)
        return None

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

            
    return usages

def register_or_update_op(nro_op, obra_id=None, gasto_id=None):
    nro_op_str = str(nro_op).strip()
    if not nro_op_str:
        return
    with db_session() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM op_bejerman WHERE nro_op = ?", (nro_op_str,))
        row = cursor.fetchone()
        if row:
            cursor.execute('''
                UPDATE op_bejerman 
                SET obra_id = ?, gasto_id = ? 
                WHERE nro_op = ?
            ''', (obra_id, gasto_id, nro_op_str))
        else:
            cursor.execute('''
                INSERT INTO op_bejerman (nro_op, obra_id, gasto_id)
                VALUES (?, ?, ?)
            ''', (nro_op_str, obra_id, gasto_id))
        conn.commit()

if __name__ == '__main__':
    init_db()



# --- PAGOS A FONDOS PROPIOS Y RECUPEROS ---

def update_monto_contrato_obra(obra_id, nuevo_monto, nuevo_monto_moneda=None, nueva_cotizacion_base=None, motivo_rectificacion=None):
    obra = get_obra(obra_id)
    if not obra:
        raise ValueError("Obra no encontrada.")
    m_id = obra.get('moneda_id') or 1
    
    if m_id == 1:
        monto_moneda = float(nuevo_monto or 0.0)
        cotiz = 1.0
        monto_pesos = float(nuevo_monto or 0.0)
    else:
        monto_moneda = float(nuevo_monto_moneda if nuevo_monto_moneda is not None else (obra.get('monto_contrato_moneda') or 0.0))
        cotiz = float(nueva_cotizacion_base if nueva_cotizacion_base is not None else (obra.get('cotizacion_base_contrato') or 1.0))
        monto_pesos = float(nuevo_monto if nuevo_monto is not None else (monto_moneda * cotiz))

    old_cotiz = float(obra.get('cotizacion_base_contrato') or 1.0)
    pagos_existentes = get_pagos_detalle_por_obra(obra_id)
    tiene_pagos = (len(pagos_existentes) > 0 or get_total_pagado_obra(obra_id) > 0)
    
    # Preparación en memoria de la constancia de rectificación (no se escribe hasta que pasen las guardas)
    nueva_constancia = None
    if m_id != 1 and nueva_cotizacion_base is not None and abs(cotiz - old_cotiz) > 0.0001 and tiene_pagos:
        if not motivo_rectificacion or not str(motivo_rectificacion).strip():
            raise ValueError("Debe ingresar un motivo / justificación obligatoria para rectificar la cotización base de una obra con pagos registrados.")
        import datetime
        fecha_hoy = datetime.date.today().strftime('%Y-%m-%d')
        nueva_constancia = f"\n[Rectificación Cotiz. Base: ${old_cotiz:,.2f} -> ${cotiz:,.2f} | Motivo: {str(motivo_rectificacion).strip()} | Fecha: {fecha_hoy}]"

    # Guardas de reducción contra importes ya amortizados / pagados
    resumen = get_resumen_contrato_obra(obra_id)
    if m_id == 1:
        total_pagado = get_total_pagado_obra(obra_id)
        if monto_pesos > 0 and monto_pesos < (total_pagado - TOLERANCE):
            raise ValueError(f"No se puede reducir el monto de contrato por debajo del total ya pagado a la contratista (${total_pagado:,.2f})")
    else:
        if resumen:
            total_amortizado = float(resumen.get('total_moneda_amortizada') or 0.0)
            cant_adic = float(resumen.get('cantidad_adicionales_moneda') or 0.0)
            nuevo_tope_moneda = monto_moneda + cant_adic
            cod_mon = resumen.get('moneda_codigo') or 'UVI'
            if monto_moneda > 0 and nuevo_tope_moneda < (total_amortizado - 0.0001):
                raise ValueError(f"No se puede reducir el contrato en {cod_mon} ({nuevo_tope_moneda:,.2f}) por debajo del total ya amortizado ({total_amortizado:,.2f} {cod_mon}).")
    
    # Escritura atómica única en base de datos
    with db_session() as conn:
        if nueva_constancia:
            notas_actuales = obra.get('notas_contrato') or ""
            nuevas_notas = notas_actuales + nueva_constancia
            conn.execute("""
                UPDATE obras 
                SET monto_contrato = ?, monto_contrato_moneda = ?, cotizacion_base_contrato = ?, notas_contrato = ?
                WHERE id = ?
            """, (monto_pesos, monto_moneda, cotiz, nuevas_notas, obra_id))
        else:
            conn.execute("""
                UPDATE obras 
                SET monto_contrato = ?, monto_contrato_moneda = ?, cotizacion_base_contrato = ?
                WHERE id = ?
            """, (monto_pesos, monto_moneda, cotiz, obra_id))

def get_pagos_fondos_propios(obra_id=None):
    with db_session() as conn:
        query = "SELECT * FROM pagos_fondos_propios"
        params = []
        if obra_id:
            query += " WHERE obra_id = ?"
            params.append(obra_id)
        query += " ORDER BY fecha DESC"
        return [dict(row) for row in conn.execute(query, params).fetchall()]

def add_pago_fondos_propios(obra_id, monto, fecha, nro_op, observaciones,
                            cantidad_moneda_amortizada=None, cotizacion_pago=None,
                            convenio_solicitud_id=None, motivo_sobrepago=None):
    _validar_op_o_nota_db(nro_op, observaciones, "pago con fondos propios")
    if monto <= 0:
        raise ValueError("El monto a pagar debe ser mayor a 0.")
        
    with db_session() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT moneda_id FROM obras WHERE id = ?', (obra_id,))
        o_row = cursor.fetchone()
        o_moneda_id = o_row['moneda_id'] if o_row else 1
        
        cotiz = cotizacion_pago
        cant_mon = cantidad_moneda_amortizada
        if o_moneda_id == 1:
            cotiz = 1.0
            cant_mon = float(monto)
        else:
            if cotiz is None or cotiz <= 0:
                cotiz = 1.0
            if cant_mon is None:
                cant_mon = round(monto / cotiz, 6) if cotiz > 0 else 0.0

        cursor.execute('''
            INSERT INTO pagos_fondos_propios (
                obra_id, monto, fecha, nro_op, observaciones,
                cantidad_moneda_amortizada, cotizacion_pago, convenio_solicitud_id, motivo_sobrepago
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (obra_id, monto, fecha, nro_op, observaciones,
              cant_mon, cotiz, convenio_solicitud_id, motivo_sobrepago))
              
    if nro_op:
        register_or_update_op(nro_op, obra_id=obra_id)

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
    
    with db_session() as conn:
        # Validar que no supere el tope dentro de la misma transacción
        pagos_fp = sum(row['monto'] for row in conn.execute("SELECT monto FROM pagos_fondos_propios WHERE obra_id = ?", (obra_id,)).fetchall())
        recuperos = sum(row['monto'] for row in conn.execute("SELECT monto FROM recuperos_fondos_propios WHERE obra_id = ?", (obra_id,)).fetchall())
        tope = max(0.0, pagos_fp - recuperos)
        
        if monto > tope + TOLERANCE:
            raise ValueError(f"El monto a recuperar excede el total adeudado a Fondos Propios para esta obra (${tope:,.2f}).")
            
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


# =============================================================================
# --- MÓDULO: MONEDAS E ÍNDICES ---
# =============================================================================

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
        conn.commit()
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
        conn.commit()


# =============================================================================
# --- MÓDULO: CONVENIOS MULTIOBRA ---
# =============================================================================

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
        conn.commit()
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
        conn.commit()


def update_estado_convenio(convenio_id, estado):
    if estado not in ('Vigente', 'Terminado', 'Anulado'):
        raise ValueError("Estado de convenio no válido.")
    with db_session() as conn:
        cursor = conn.cursor()
        cursor.execute('UPDATE convenios SET estado = ? WHERE id = ?', (estado, convenio_id))
        conn.commit()


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
        conn.commit()


# =============================================================================
# --- MÓDULO: CONVENIO - OBRAS ASOCIADAS ---
# =============================================================================

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
        conn.commit()
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
        conn.commit()


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


# =============================================================================
# --- MÓDULO: CONVENIO - SOLICITUDES DE DESEMBOLSO / CERTIFICADOS DE AVANCE ---
# =============================================================================

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
            SELECT cs.*, cv.nro_convenio, cv.nombre_convenio, cv.ente_financiador,
                   o.nombre as obra_nombre, o.expediente_imuh,
                   m.simbolo as moneda_simbolo, m.codigo as moneda_codigo
            FROM convenio_solicitudes cs
            JOIN convenios cv ON cs.convenio_id = cv.id
            JOIN obras o ON cs.obra_id = o.id
            LEFT JOIN monedas_indices m ON cv.moneda_id = m.id
            WHERE cs.estado IN ('Pendiente', 'Parcial') AND cv.estado = 'Vigente'
            ORDER BY cs.fecha_solicitud ASC
        ''')
        rows = cursor.fetchall()
        return [dict(ix) for ix in rows]


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
        conn.commit()
        return cursor.lastrowid


def update_solicitud_convenio(solicitud_id, nro_certificado, periodo,
                              cantidad_moneda, cotizacion_solicitud, monto_solicitado_ars,
                              fecha_solicitud, expediente_pago=None, pdf_path=None, notas=None):
    with db_session() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            UPDATE convenio_solicitudes
            SET nro_certificado = ?, periodo = ?, cantidad_moneda = ?,
                cotizacion_solicitud = ?, monto_solicitado_ars = ?, fecha_solicitud = ?,
                expediente_pago = ?, pdf_path = ?, notas = ?
            WHERE id = ?
        ''', (
            str(nro_certificado).strip(), periodo, float(cantidad_moneda),
            float(cotizacion_solicitud), float(monto_solicitado_ars), fecha_solicitud,
            expediente_pago, pdf_path, notas.strip() if notas else None, solicitud_id
        ))
        conn.commit()


def delete_solicitud_convenio(solicitud_id):
    with db_session() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT COUNT(*) as cnt FROM cobros WHERE convenio_solicitud_id = ?', (solicitud_id,))
        if cursor.fetchone()['cnt'] > 0:
            raise ValueError("No se puede eliminar una solicitud que tiene cobros bancarios asentados.")
        cursor.execute('DELETE FROM convenio_solicitudes WHERE id = ?', (solicitud_id,))
        conn.commit()


# =============================================================================
# --- CONTROL Y AUDITORÍA DE CONVENIOS (MÉTRICAS EN UVI / MONEDA CONTRACTUAL) ---
# =============================================================================

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

        # Certificados en tránsito
        cursor.execute('''
            SELECT 
                COUNT(*) as cant_pendientes,
                COALESCE(SUM(monto_solicitado_ars), 0) as total_solicitado_ars,
                COALESCE(SUM(cantidad_moneda - cantidad_moneda_cobrada), 0) as total_transito_moneda
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
            'total_transito_ars': float(row_trans['total_solicitado_ars'] or 0.0) if row_trans else 0.0,
            'total_transito_moneda': float(row_trans['total_transito_moneda'] or 0.0) if row_trans else 0.0
        }

