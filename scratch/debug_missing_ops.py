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
        
        # Probar buscar sin filtrar por nro_op nulo para ver si ya fue actualizado o si el monto difiere
        print(f"Row #{row_num} | {db_rec['Decreto']} | Cuota {db_rec['cuota_id']} | ${monto} | Mov: {mov_tipo} | Dest: {r.get('Destino')}")
        cursor.execute("""
            SELECT 'fo', fo.id, fo.monto, fo.nro_op FROM cobro_fin_original_usos fo JOIN cobros cb ON fo.cobro_id = cb.id WHERE cb.cuota_id = ?
            UNION ALL
            SELECT 'desv', cd.id, cd.monto, cd.nro_op FROM cobro_desvios cd JOIN cobros cb ON cd.cobro_id = cb.id WHERE cb.cuota_id = ?
            UNION ALL
            SELECT 'res', ru.id, ru.monto, ru.nro_op FROM cobro_reserva_usos ru JOIN cobros cb ON ru.cobro_id = cb.id WHERE cb.cuota_id = ?
        """, (db_rec["cuota_id"], db_rec["cuota_id"], db_rec["cuota_id"]))
        
        for row in cursor.fetchall():
            print("   DB candidate:", row)
