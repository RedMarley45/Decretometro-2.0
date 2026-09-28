import sys, os
sys.path.append(os.path.abspath('.'))
import database as db
import utils
import utils_reports
import pandas as pd
import sqlite3

df_csv = pd.read_csv('OP sin asignar.csv', encoding='latin1', sep=';')
df_with_op = df_csv[df_csv['OP'].notnull() & (df_csv['OP'].astype(str).str.strip() != '')].copy()

decretos = db.get_decretos()
unassigned_records = []

for dec in decretos:
    sel_dec_id = dec['id']
    dec_str = f"Dto. {dec['nro_decreto']}/{dec['anio']}"
    cuotas_list = db.get_cuotas_by_decreto(sel_dec_id)
    cuota_ids = [c['id'] for c in cuotas_list]
    
    for c in cuotas_list:
        seq_num = cuota_ids.index(c['id']) + 1
        estado_actual_filas, sum_total_actual, cobros_cuota, _, fechas_str, _, _ = utils_reports.obtener_datos_composicion(sel_dec_id, c['id'])
        
        for row in estado_actual_filas:
            imp_pagado = float(row.get("Monto", 0.0))
            op_val = row.get("Orden de Pago (OP)")
            
            if imp_pagado > 0.001 and (not op_val or str(op_val).strip() in ["-", "Sin asignar", "Sin OP", ""]):
                unassigned_records.append({
                    "dec_id": sel_dec_id,
                    "cuota_id": c['id'],
                    "Decreto": dec_str,
                    "Cuota": f"Cuota {seq_num}",
                    "Fecha Pago": row.get("Fecha") or "-",
                    "Obra Destino": row.get("Destino") or "-",
                    "Importe Pagado": imp_pagado,
                    "row_data": row
                })

conn = sqlite3.connect('decretometro.db')
cursor = conn.cursor()

updated_count = 0
not_found_count = 0

for idx, row_csv in df_with_op.iterrows():
    row_num = int(row_csv['#'])
    op_text = str(row_csv['OP']).strip()
    
    parts = [p.strip() for p in op_text.split('/') if p.strip()]
    op_clean = " / ".join(parts) if len(parts) > 1 else op_text
    
    if 1 <= row_num <= len(unassigned_records):
        db_rec = unassigned_records[row_num - 1]
        r = db_rec["row_data"]
        monto = r["Monto"]
        mov_tipo = r.get("Movimiento", "")
        dest_str = str(r.get("Destino", ""))
        
        # Buscar en fo, desv o res según mov_tipo
        matched = False
        
        # 1. Probar en la tabla principal correspondiente
        if "Fin original" in mov_tipo and "Reserva" not in mov_tipo and "Recupero" not in mov_tipo:
            cursor.execute("""
                SELECT fo.id FROM cobro_fin_original_usos fo
                JOIN cobros cb ON fo.cobro_id = cb.id
                WHERE cb.cuota_id = ? AND ABS(fo.monto - ?) < 0.01 AND (fo.nro_op IS NULL OR fo.nro_op = '' OR fo.nro_op = 'Sin asignar')
            """, (db_rec["cuota_id"], monto))
            rows = cursor.fetchall()
            if rows:
                fo_id = rows[0][0]
                cursor.execute("UPDATE cobro_fin_original_usos SET nro_op = ? WHERE id = ?", (op_clean, fo_id))
                updated_count += 1
                matched = True
                print(f"[OK] Fila #{row_num} -> cobro_fin_original_usos ID {fo_id} = OP '{op_clean}'")

        if not matched and ("Desvío" in mov_tipo or "Desvio" in mov_tipo) and "Reserva" not in mov_tipo:
            cursor.execute("""
                SELECT cd.id FROM cobro_desvios cd
                JOIN cobros cb ON cd.cobro_id = cb.id
                WHERE cb.cuota_id = ? AND ABS(cd.monto - ?) < 0.01 AND (cd.nro_op IS NULL OR cd.nro_op = '' OR cd.nro_op = 'Sin asignar')
            """, (db_rec["cuota_id"], monto))
            rows = cursor.fetchall()
            if rows:
                desv_id = rows[0][0]
                cursor.execute("UPDATE cobro_desvios SET nro_op = ? WHERE id = ?", (op_clean, desv_id))
                updated_count += 1
                matched = True
                print(f"[OK] Fila #{row_num} -> cobro_desvios ID {desv_id} = OP '{op_clean}'")

        if not matched and "Reserva" in mov_tipo:
            cursor.execute("""
                SELECT ru.id FROM cobro_reserva_usos ru
                JOIN cobros cb ON ru.cobro_id = cb.id
                WHERE cb.cuota_id = ? AND ABS(ru.monto - ?) < 0.01 AND (ru.nro_op IS NULL OR ru.nro_op = '' OR ru.nro_op = 'Sin asignar')
            """, (db_rec["cuota_id"], monto))
            rows = cursor.fetchall()
            if rows:
                ru_id = rows[0][0]
                cursor.execute("UPDATE cobro_reserva_usos SET nro_op = ? WHERE id = ?", (op_clean, ru_id))
                updated_count += 1
                matched = True
                print(f"[OK] Fila #{row_num} -> cobro_reserva_usos ID {ru_id} = OP '{op_clean}'")

        # Fallback a buscar en cualquiera de las 3 tablas si no se encontró arriba
        if not matched:
            # Probar fo
            cursor.execute("SELECT fo.id FROM cobro_fin_original_usos fo JOIN cobros cb ON fo.cobro_id = cb.id WHERE cb.cuota_id = ? AND ABS(fo.monto - ?) < 0.01 AND (fo.nro_op IS NULL OR fo.nro_op = '' OR fo.nro_op = 'Sin asignar')", (db_rec["cuota_id"], monto))
            r_fo = cursor.fetchall()
            if r_fo:
                cursor.execute("UPDATE cobro_fin_original_usos SET nro_op = ? WHERE id = ?", (op_clean, r_fo[0][0]))
                updated_count += 1
                matched = True
                print(f"[OK Fallback] Fila #{row_num} -> cobro_fin_original_usos ID {r_fo[0][0]} = OP '{op_clean}'")

        if not matched:
            # Probar desv
            cursor.execute("SELECT cd.id FROM cobro_desvios cd JOIN cobros cb ON cd.cobro_id = cb.id WHERE cb.cuota_id = ? AND ABS(cd.monto - ?) < 0.01 AND (cd.nro_op IS NULL OR cd.nro_op = '' OR cd.nro_op = 'Sin asignar')", (db_rec["cuota_id"], monto))
            r_desv = cursor.fetchall()
            if r_desv:
                cursor.execute("UPDATE cobro_desvios SET nro_op = ? WHERE id = ?", (op_clean, r_desv[0][0]))
                updated_count += 1
                matched = True
                print(f"[OK Fallback] Fila #{row_num} -> cobro_desvios ID {r_desv[0][0]} = OP '{op_clean}'")

        if not matched:
            # Probar ru
            cursor.execute("SELECT ru.id FROM cobro_reserva_usos ru JOIN cobros cb ON ru.cobro_id = cb.id WHERE cb.cuota_id = ? AND ABS(ru.monto - ?) < 0.01 AND (ru.nro_op IS NULL OR ru.nro_op = '' OR ru.nro_op = 'Sin asignar')", (db_rec["cuota_id"], monto))
            r_ru = cursor.fetchall()
            if r_ru:
                cursor.execute("UPDATE cobro_reserva_usos SET nro_op = ? WHERE id = ?", (op_clean, r_ru[0][0]))
                updated_count += 1
                matched = True
                print(f"[OK Fallback] Fila #{row_num} -> cobro_reserva_usos ID {r_ru[0][0]} = OP '{op_clean}'")

        if not matched:
            print(f"[MISSING] Fila #{row_num} {db_rec['Decreto']} Cuota {db_rec['cuota_id']} ${monto}")
            not_found_count += 1

conn.commit()
conn.close()

print(f"\n==========================================")
print(f"RESULTADO: {updated_count} de {len(df_with_op)} OPs actualizadas exitosamente.")
print(f"No encontrados: {not_found_count}")
print(f"==========================================")
