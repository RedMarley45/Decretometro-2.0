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
                "Año Decreto": dec['anio'],
                "Expediente IMUH": dec.get("expediente_imuh") or "-",
                "Cuota": f"Cuota {r['Nro. Cuota']}",
                "Fecha Cobro": r.get("Fecha de cobro") or "-",
                "Fecha Pago": r.get("Fecha de pago") or "-",
                "Proveedor": r.get("Proveedor") or "-",
                "Obra Destino": r.get("Obra destino") or "-",
                "Importe Pagado": utils.format_currency_ar(imp_pagado),
                "Observaciones": r.get("Observaciones/aclaraciones") or "-"
            })

df_unassigned = pd.DataFrame(unassigned_records)

# Crear el contenido Markdown
md_content = f"""# Listado Consolidado de Registros Sin Orden de Pago (OP Bejerman)

> [!IMPORTANT]
> Tras la actualización masiva realizada con el archivo CSV, de los **62 registros iniciales**, únicamente restan **3 pagos efectivamente realizados** pendientes de asignar su número de OP Bejerman (además de 2 fondos percibidos en cuotas que aún se encuentran sin distribuir/pagar).

## 📌 Pagos Ejecutados Pendientes de OP ({len(df_unassigned[df_unassigned['Obra Destino'] != 'Sin distribuir'])})

| # | Decreto | Exp. IMUH | Cuota | Fecha Pago | Proveedor | Obra Destino | Importe Pagado | Observaciones |
|---|---|---|---|---|---|---|---|---|
"""

idx_pago = 1
for i, row in df_unassigned.iterrows():
    if row['Obra Destino'] != 'Sin distribuir':
        obs = str(row['Observaciones']).replace('\n', ' ')
        md_content += f"| {idx_pago} | {row['Decreto']} | {row['Expediente IMUH']} | {row['Cuota']} | {row['Fecha Pago']} | {row['Proveedor']} | {row['Obra Destino']} | {row['Importe Pagado']} | {obs} |\n"
        idx_pago += 1

md_content += f"""

## ⏳ Fondos Percibidos Pendientes de Distribución / Pago ({len(df_unassigned[df_unassigned['Obra Destino'] == 'Sin distribuir'])})
*Estos montos corresponden a fondos ingresados en cuotas que aún no han sido asignados ni pagados a ningún destino, por lo que no poseen una OP Bejerman asociada.*

| # | Decreto | Exp. IMUH | Cuota | Fecha Cobro | Obra Destino | Importe Percibido | Estado |
|---|---|---|---|---|---|---|---|
"""

idx_pend = 1
for i, row in df_unassigned.iterrows():
    if row['Obra Destino'] == 'Sin distribuir':
        md_content += f"| {idx_pend} | {row['Decreto']} | {row['Expediente IMUH']} | {row['Cuota']} | {row['Fecha Cobro']} | {row['Obra Destino']} | {row['Importe Pagado']} | Fondo en cuenta / Sin aplicar |\n"
        idx_pend += 1

artifact_path = r"C:\Users\bornemanns\.gemini\antigravity-ide\brain\86c1534e-f9ff-4b92-a836-2e24c399307e\listado_registros_sin_op.md"
with open(artifact_path, "w", encoding="utf-8") as f:
    f.write(md_content)

print(f"Artifact successfully updated with {len(df_unassigned)} total unassigned rows.")
