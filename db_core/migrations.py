"""
db_core/migrations.py - Motor de Versiones del Esquema, Migraciones v1 a v49 y Triggers Forenses
"""
import sqlite3
from db_core.connection import get_connection, db_session
def _instalar_triggers_auditoria(cursor):
    """Instala de forma idempotente triggers forenses en las tablas operativas del sistema.
    Registra en audit_log el estado anterior (OLD) y posterior (NEW) serializado en JSON.
    """
    tablas_auditadas = [
        'decretos', 'cuotas', 'cobros', 'cobro_distribuciones', 'cobro_desvios',
        'cobro_reserva_usos', 'cobro_fin_original_usos', 'cobro_desvios_recuperos',
        'cobro_reserva_usos_recuperos', 'solicitudes_financiamiento', 'obras',
        'convenios', 'convenio_obras', 'convenio_solicitudes',
        'pagos_fondos_propios', 'recuperos_fondos_propios', 'obra_adicionales'
    ]
    for tabla in tablas_auditadas:
        cursor.execute(f"PRAGMA table_info({tabla});")
        columnas = cursor.fetchall()
        if not columnas:
            continue
        col_names = [col['name'] for col in columnas]
        if 'id' not in col_names:
            continue
        
        args_old = ", ".join([f"'{c}', OLD.{c}" for c in col_names])
        args_new = ", ".join([f"'{c}', NEW.{c}" for c in col_names])
        
        # Trigger DELETE
        cursor.execute(f'''
            CREATE TRIGGER IF NOT EXISTS trg_audit_{tabla}_del
            BEFORE DELETE ON {tabla}
            BEGIN
                INSERT INTO audit_log (tabla, registro_id, accion, valores_anteriores, valores_nuevos)
                VALUES ('{tabla}', OLD.id, 'DELETE', json_object({args_old}), NULL);
            END;
        ''')
        
        # Trigger UPDATE
        cursor.execute(f'''
            CREATE TRIGGER IF NOT EXISTS trg_audit_{tabla}_upd
            AFTER UPDATE ON {tabla}
            BEGIN
                INSERT INTO audit_log (tabla, registro_id, accion, valores_anteriores, valores_nuevos)
                VALUES ('{tabla}', NEW.id, 'UPDATE', json_object({args_old}), json_object({args_new}));
            END;
        ''')

    # --- Decretos CRUD ---


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
            (48, "-- Migración 48: Soporte Bimonetario en Catálogo de Obras y Control de Pagos --"),
            (49, "-- Migración 49: Soporte bimonetario en desvíos/usos de reserva y bitácora de auditoría forense --")
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
                    elif version == 49:
                        # 1. Soporte bimonetario en cobro_desvios y cobro_reserva_usos
                        for col_sql in [
                            "ALTER TABLE cobro_desvios ADD COLUMN cantidad_moneda_amortizada REAL",
                            "ALTER TABLE cobro_desvios ADD COLUMN cotizacion_pago REAL DEFAULT 1.0",
                            "ALTER TABLE cobro_reserva_usos ADD COLUMN cantidad_moneda_amortizada REAL",
                            "ALTER TABLE cobro_reserva_usos ADD COLUMN cotizacion_pago REAL DEFAULT 1.0"
                        ]:
                            try:
                                cursor.execute(col_sql)
                            except sqlite3.OperationalError:
                                pass

                        # 2. Tabla audit_log para bitácora forense
                        cursor.execute('''
                            CREATE TABLE IF NOT EXISTS audit_log (
                                id INTEGER PRIMARY KEY AUTOINCREMENT,
                                tabla TEXT NOT NULL,
                                registro_id INTEGER,
                                accion TEXT NOT NULL,
                                valores_anteriores TEXT,
                                valores_nuevos TEXT,
                                usuario TEXT DEFAULT 'sistema',
                                fecha_hora TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                            )
                        ''')
                        cursor.execute('CREATE INDEX IF NOT EXISTS idx_audit_log_tabla_reg ON audit_log(tabla, registro_id)')
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

        # Asegurar tabla audit_log y sus triggers forenses instalados
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS audit_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tabla TEXT NOT NULL,
                registro_id INTEGER,
                accion TEXT NOT NULL,
                valores_anteriores TEXT,
                valores_nuevos TEXT,
                usuario TEXT DEFAULT 'sistema',
                fecha_hora TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_audit_log_tabla_reg ON audit_log(tabla, registro_id)')
        _instalar_triggers_auditoria(cursor)

