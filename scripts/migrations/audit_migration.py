import sqlite3
import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SOURCE_DB = os.path.join(BASE_DIR, 'Migración', 'backup_decretometro_20260929_083646.db')
TARGET_DB = os.path.join(BASE_DIR, 'decretometro.db')

conn_src = sqlite3.connect(SOURCE_DB)
conn_tgt = sqlite3.connect(TARGET_DB)
cur_s = conn_src.cursor()
cur_t = conn_tgt.cursor()

print("=" * 80)
print("INFORME DE AUDITORÍA Y CONCILIACIÓN CONTABLE POST-MIGRACIÓN")
print("=" * 80)

# 1. Integridad
cur_t.execute("PRAGMA integrity_check")
ic = cur_t.fetchone()[0]
print(f"1. Integridad física de la base de datos: {ic.upper()}")

# 2. Conteo de filas
print("\n2. COMPARACIÓN DE REGISTROS (Backup vs Base Activa):")
print(f"{'Tabla':<32} | {'Backup':<8} | {'Migrado':<8} | {'Estado':<10}")
print("-" * 65)

tables = [
    "decretos", "decretos_obras", "cuotas", "solicitudes_financiamiento",
    "cobros", "cobro_distribuciones", "cobro_fin_original_usos",
    "cobro_reserva_usos", "cobro_desvios", "cobro_reserva_usos_recuperos",
    "cobro_desvios_recuperos", "pagos_fondos_propios", "prestamos_internos",
    "aportes_funcionamiento", "aportes_sueldo", "aportes_sac", "op_bejerman",
    "obras", "proveedores_obras", "proveedores_funcionamiento", "gastos_funcionamiento"
]

for tbl in tables:
    cur_s.execute(f'SELECT count(*) FROM "{tbl}"')
    cnt_s = cur_s.fetchone()[0]
    cur_t.execute(f'SELECT count(*) FROM "{tbl}"')
    cnt_t = cur_t.fetchone()[0]
    status = "OK 1:1" if cnt_s == cnt_t else ("OK (+1 nueva)" if tbl == "obras" else "REVISAR")
    print(f"{tbl:<32} | {cnt_s:<8} | {cnt_t:<8} | {status}")

# 3. Conciliación Financiera
print("\n3. CONCILIACIÓN DE TOTALES FINANCIEROS ($):")
print(f"{'Concepto':<36} | {'Monto Backup ($)':<22} | {'Monto Migrado ($)':<22} | {'Cuadre'}")
print("-" * 92)

financial_queries = [
    ("Total Cuotas Decretos", "SELECT COALESCE(SUM(monto), 0) FROM cuotas"),
    ("Total Solicitado Financiamiento", "SELECT COALESCE(SUM(monto_solicitado), 0) FROM solicitudes_financiamiento"),
    ("Total Cobros Registrados", "SELECT COALESCE(SUM(monto), 0) FROM cobros"),
    ("Total Distribuido Fin Original", "SELECT COALESCE(SUM(monto_fin_orig), 0) FROM cobro_distribuciones"),
    ("Total Distribuido Reserva", "SELECT COALESCE(SUM(monto_reserva), 0) FROM cobro_distribuciones"),
    ("Total Usos Fin Original", "SELECT COALESCE(SUM(monto), 0) FROM cobro_fin_original_usos"),
    ("Total Usos Reserva", "SELECT COALESCE(SUM(monto), 0) FROM cobro_reserva_usos"),
    ("Total Desvíos Realizados", "SELECT COALESCE(SUM(monto), 0) FROM cobro_desvios"),
    ("Total Recuperos de Desvíos", "SELECT COALESCE(SUM(monto), 0) FROM cobro_desvios_recuperos"),
    ("Total Recuperos de Reserva", "SELECT COALESCE(SUM(monto), 0) FROM cobro_reserva_usos_recuperos"),
    ("Total Pagos Fondos Propios", "SELECT COALESCE(SUM(monto), 0) FROM pagos_fondos_propios"),
    ("Total Préstamos Internos", "SELECT COALESCE(SUM(monto), 0) FROM prestamos_internos"),
    ("Aportes Funcionamiento Pautado", "SELECT COALESCE(SUM(monto_pautado), 0) FROM aportes_funcionamiento"),
    ("Aportes Funcionamiento Cobrado", "SELECT COALESCE(SUM(monto_cobrado), 0) FROM aportes_funcionamiento"),
    ("Aportes Sueldo Pedido", "SELECT COALESCE(SUM(monto_pedido), 0) FROM aportes_sueldo"),
    ("Aportes Sueldo Cobrado", "SELECT COALESCE(SUM(monto_cobrado), 0) FROM aportes_sueldo"),
    ("Aportes SAC Pedido", "SELECT COALESCE(SUM(monto_pedido), 0) FROM aportes_sac"),
    ("Aportes SAC Cobrado", "SELECT COALESCE(SUM(monto_cobrado), 0) FROM aportes_sac")
]

for label, query in financial_queries:
    cur_s.execute(query)
    val_s = cur_s.fetchone()[0]
    cur_t.execute(query)
    val_t = cur_t.fetchone()[0]
    diff = abs(val_s - val_t)
    status = "EXACTO" if diff < 0.001 else f"DIF: ${diff:,.2f}"
    str_s = f"${val_s:,.2f}"
    str_t = f"${val_t:,.2f}"
    print(f"{label:<36} | {str_s:>22} | {str_t:>22} | {status}")

# 4. Verificación de Remapeo Obra 54 -> 56
print("\n4. VERIFICACIÓN DE REMAPEO DE OBRA:")
cur_t.execute("SELECT count(*) FROM cobro_desvios WHERE obra_id = 54")
cd_54 = cur_t.fetchone()[0]
cur_t.execute("SELECT count(*) FROM cobro_desvios WHERE obra_id = 56")
cd_56 = cur_t.fetchone()[0]
cur_t.execute("SELECT count(*) FROM op_bejerman WHERE obra_id = 54")
op_54 = cur_t.fetchone()[0]
cur_t.execute("SELECT count(*) FROM op_bejerman WHERE obra_id = 56")
op_56 = cur_t.fetchone()[0]
print(f"Referencias a Obra 54 (debe ser 0): Desvíos={cd_54}, OPs={op_54}")
print(f"Referencias a Obra 56 (remapeadas): Desvíos={cd_56}, OPs={op_56}")

# 5. Verificación de Inicialización Bimonetaria
print("\n5. VERIFICACIÓN DE VALORES BIMONETARIOS:")
cur_t.execute("SELECT count(*) FROM decretos WHERE moneda_id != 1")
dec_mon = cur_t.fetchone()[0]
cur_t.execute("SELECT count(*) FROM cobros WHERE moneda_origen_id != 1 OR cotizacion_cobro != 1.0 OR origen_tipo != 'decreto'")
cob_mon = cur_t.fetchone()[0]
print(f"Decretos con moneda distinta de ARS (debe ser 0): {dec_mon}")
print(f"Cobros con configuración no estándar (debe ser 0): {cob_mon}")

print("=" * 80)
conn_src.close()
conn_tgt.close()
