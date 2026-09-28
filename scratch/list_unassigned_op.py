import sys, os
sys.path.append(os.path.abspath('.'))
import database as db
import utils
import utils_reports

# Obtener todos los decretos
decretos = db.get_decretos()
unassigned_records = []

for dec in decretos:
    sel_dec_id = dec['id']
    dec_str = f"Dto. {dec['nro_decreto']}/{dec['anio']}"
    dec_obj, cuotas_list, filas_reporte = utils_reports.obtener_afectacion_decreto(sel_dec_id)
    
    for r in filas_reporte:
        op_val = r.get("Nro. OP Bejerman")
        imp_pagado = float(r.get("Importe pagado", 0.0))
        if imp_pagado > 0.001 and (not op_val or op_val.strip() in ["-", "Sin asignar", "Sin OP", ""]):
            # Guardar en la lista
            unassigned_records.append({
                "Decreto": dec_str,
                "Expediente IMUH": dec.get("expediente_imuh") or "-",
                "Cuota": f"Cuota {r['Nro. Cuota']}",
                "Fecha Cobro": r.get("Fecha de cobro") or "-",
                "Fecha Pago": r.get("Fecha de pago") or "-",
                "Proveedor": r.get("Proveedor") or "-",
                "Obra Destino": r.get("Obra destino") or "-",
                "Importe Pagado ($)": imp_pagado,
                "Observaciones": r.get("Observaciones/aclaraciones") or "-"
            })

import pandas as pd
df_unassigned = pd.DataFrame(unassigned_records)

# Guardar a CSV / Excel para facil acceso
df_unassigned.to_csv('scratch/registros_sin_op.csv', index=False, sep=';', encoding='utf-8-sig')

print(f"Total registros sin OP asignada: {len(df_unassigned)}")
print(df_unassigned.to_string())
