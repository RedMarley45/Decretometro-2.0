"""
Script de Migración Histórica: backup_decretometro_20260929_083646.db -> decretometro.db
Este script migra los datos transaccionales históricos preservando el catálogo de obras y proveedores,
remapeando referencias de Obra ID 54 -> 56, e inicializando los nuevos campos bimonetarios en ARS.
"""

import sqlite3
import os
import sys

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SOURCE_DB = os.path.join(BASE_DIR, 'Migración', 'backup_decretometro_20260929_083646.db')
TARGET_DB = os.path.join(BASE_DIR, 'decretometro.db')

TABLES_TO_MIGRATE = [
    "decretos",
    "decretos_obras",
    "cuotas",
    "solicitudes_financiamiento",
    "cobros",
    "cobro_distribuciones",
    "cobro_fin_original_usos",
    "cobro_reserva_usos",
    "cobro_desvios",
    "cobro_reserva_usos_recuperos",
    "cobro_desvios_recuperos",
    "pagos_fondos_propios",
    "prestamos_internos",
    "aportes_funcionamiento",
    "aportes_sueldo",
    "aportes_sac",
    "op_bejerman"
]

DEFAULTS_FOR_NEW_COLS = {
    "moneda_id": 1,
    "origen_tipo": "decreto",
    "moneda_origen_id": 1,
    "cotizacion_cobro": 1.0,
    "cotizacion_pago": 1.0,
    "diferencia_ajuste_ars": 0.0,
    "cantidad_moneda_origen": None,
    "cantidad_moneda_amortizada": None,
    "convenio_solicitud_id": None,
    "motivo_sobrepago": None,
    "obra_id": None
}

def run_migration():
    print("=" * 60)
    print("INICIANDO MIGRACIÓN HISTÓRICA A DECRETOMETRO.DB")
    print(f"Origen:  {SOURCE_DB}")
    print(f"Destino: {TARGET_DB}")
    print("=" * 60)

    if not os.path.exists(SOURCE_DB):
        raise FileNotFoundError(f"No se encontró la base origen en {SOURCE_DB}")
    if not os.path.exists(TARGET_DB):
        raise FileNotFoundError(f"No se encontró la base destino en {TARGET_DB}")

    conn_src = sqlite3.connect(SOURCE_DB)
    conn_src.row_factory = sqlite3.Row
    cur_src = conn_src.cursor()

    conn_tgt = sqlite3.connect(TARGET_DB)
    cur_tgt = conn_tgt.cursor()

    cur_tgt.execute("PRAGMA foreign_keys = OFF;")
    cur_tgt.execute("BEGIN TRANSACTION;")

    try:
        total_filas = 0
        for tbl in TABLES_TO_MIGRATE:
            cur_tgt.execute(f'PRAGMA table_info("{tbl}")')
            tgt_cols_info = {r[1]: r for r in cur_tgt.fetchall()}
            tgt_cols = set(tgt_cols_info.keys())

            cur_src.execute(f'PRAGMA table_info("{tbl}")')
            src_cols = [r[1] for r in cur_src.fetchall()]

            cur_src.execute(f'SELECT * FROM "{tbl}"')
            rows = cur_src.fetchall()

            insert_cols = [col for col in src_cols if col in tgt_cols]
            added_cols = [col for col in DEFAULTS_FOR_NEW_COLS if col in tgt_cols and col not in src_cols]

            all_insert_cols = insert_cols + added_cols
            placeholders = ", ".join(["?"] * len(all_insert_cols))
            cols_clause = ", ".join([f'"{c}"' for c in all_insert_cols])
            insert_sql = f'INSERT INTO "{tbl}" ({cols_clause}) VALUES ({placeholders})'

            for r in rows:
                row_dict = dict(r)
                # Remapeo de obra 54 a 56
                if 'obra_id' in row_dict and row_dict['obra_id'] == 54:
                    row_dict['obra_id'] = 56

                vals = [row_dict[c] for c in insert_cols]
                for c in added_cols:
                    vals.append(DEFAULTS_FOR_NEW_COLS[c])

                cur_tgt.execute(insert_sql, vals)

            total_filas += len(rows)
            print(f" -> Tabla '{tbl}': {len(rows)} filas migradas exitosamente.")

        # Actualizar secuencias automáticas
        for tbl in TABLES_TO_MIGRATE:
            cur_tgt.execute(f'PRAGMA table_info("{tbl}")')
            cols = [r[1] for r in cur_tgt.fetchall()]
            if 'id' in cols:
                cur_tgt.execute(f'SELECT MAX(id) FROM "{tbl}"')
                max_id = cur_tgt.fetchone()[0]
                if max_id:
                    cur_tgt.execute("INSERT OR REPLACE INTO sqlite_sequence (name, seq) VALUES (?, ?)", (tbl, max_id))
        print(" -> Sincronizada tabla sqlite_sequence con los MAX(id) respectivos.")

        cur_tgt.execute("COMMIT;")
        print("=" * 60)
        print(f"MIGRACIÓN COMPLETADA CON ÉXITO: {total_filas} registros importados.")
        print("=" * 60)

    except Exception as e:
        cur_tgt.execute("ROLLBACK;")
        print(f"ERROR DURANTE LA MIGRACIÓN: {e}")
        raise e
    finally:
        cur_tgt.execute("PRAGMA foreign_keys = ON;")
        conn_src.close()
        conn_tgt.close()

if __name__ == '__main__':
    run_migration()
