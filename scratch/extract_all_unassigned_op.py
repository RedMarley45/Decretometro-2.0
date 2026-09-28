import sys, os
sys.path.append(os.path.abspath('.'))
import database as db
import utils
import utils_reports
import pandas as pd

decretos = db.get_decretos()
unassigned_records = []

for dec in decretos:
    sel_dec_id = dec['id']
    dec_str = f"Dto. {dec['nro_decreto']}/{dec['anio']}"
    dec_obj, cuotas_list, filas_reporte = utils_reports.obtener_afectacion_decreto(sel_dec_id)
    
    for r in filas_reporte:
        op_val = r.get("Nro. OP Bejerman")
        imp_pagado = float(r.get("Importe pagado", 0.0))
        
        # Filtramos solo movimientos que representan un pago/movimiento ejecutado real (> 0)
        # y donde la OP está en blanco, "-", "Sin asignar" o "Sin OP"
        if imp_pagado > 0.001 and (not op_val or str(op_val).strip() in ["-", "Sin asignar", "Sin OP", ""]):
            unassigned_records.append({
                "Decreto": dec_str,
                "Año Decreto": dec['anio'],
                "Expediente IMUH": dec.get("expediente_imuh") or "-",
                "Cuota": f"Cuota {r['Nro. Cuota']}",
                "Fecha Cobro": r.get("Fecha de cobro") or "-",
                "Fecha Pago": r.get("Fecha de pago") or "-",
                "Proveedor": r.get("Proveedor") or "-",
                "Obra Destino": r.get("Obra destino") or "-",
                "Importe Pagado": imp_pagado,
                "Importe Formateado": utils.format_currency_ar(imp_pagado),
                "Observaciones": r.get("Observaciones/aclaraciones") or "-"
            })

df_unassigned = pd.DataFrame(unassigned_records)
print(f"Total registros sin OP encontrados: {len(df_unassigned)}")
for idx, row in df_unassigned.iterrows():
    print(f"#{idx+1} | {row['Decreto']} | {row['Fecha Pago']} | {row['Importe Formateado']} | {row['Proveedor']} | {row['Obra Destino']}")
