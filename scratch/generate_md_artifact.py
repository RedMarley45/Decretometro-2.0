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
        if imp_pagado > 0.001 and (not op_val or str(op_val).strip() in ["-", "Sin asignar", "Sin OP", ""]):
            unassigned_records.append({
                "Decreto": dec_str,
                "Expediente IMUH": dec.get("expediente_imuh") or "-",
                "Cuota": f"Cuota {r['Nro. Cuota']}",
                "Fecha Pago": r.get("Fecha de pago") or "-",
                "Proveedor": r.get("Proveedor") or "-",
                "Obra Destino": r.get("Obra destino") or "-",
                "Importe Pagado": utils.format_currency_ar(imp_pagado),
                "Observaciones": r.get("Observaciones/aclaraciones") or "-"
            })

df_unassigned = pd.DataFrame(unassigned_records)

# Crear el contenido Markdown
md_content = f"""# Listado de Pagos y Desvíos Sin Orden de Pago (OP Bejerman)

> [!NOTE]
> Este reporte consolida **{len(df_unassigned)}** registros de pagos y desvíos efectivamente ejecutados que actualmente no tienen asignada una Orden de Pago (OP Bejerman).

| # | Decreto | Exp. IMUH | Cuota | Fecha Pago | Proveedor | Obra Destino | Importe Pagado | Observaciones |
|---|---|---|---|---|---|---|---|---|
"""

for i, row in df_unassigned.iterrows():
    obs = str(row['Observaciones']).replace('\n', ' ')
    md_content += f"| {i+1} | {row['Decreto']} | {row['Expediente IMUH']} | {row['Cuota']} | {row['Fecha Pago']} | {row['Proveedor']} | {row['Obra Destino']} | {row['Importe Pagado']} | {obs} |\n"

artifact_path = r"C:\Users\bornemanns\.gemini\antigravity-ide\brain\86c1534e-f9ff-4b92-a836-2e24c399307e\listado_registros_sin_op.md"
with open(artifact_path, "w", encoding="utf-8") as f:
    f.write(md_content)

print(f"Artifact successfully written with {len(df_unassigned)} rows.")
