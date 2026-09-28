import os
import io
import tempfile
import uuid
import datetime
import pandas as pd
import database as db
import utils
import re
from pdf_generator import (
    generar_reporte_composicion_pdf, 
    generar_reporte_pdf, 
    generar_reporte_solicitudes_pdf, 
    generar_reporte_desvios_pdf, 
    generar_reporte_gastos_funcionamiento_financiados_obra_pdf
)

def clean_destino_name(dest):
    if not dest:
        return ""
    # Remover prefijo "ID: \d+ | "
    dest_clean = re.sub(r'^ID:\s*\d+\s*\|\s*', '', dest)
    # Remover "Dto. XX/YY - " o "Exp. XX - " o "XX - "
    dest_clean = re.sub(r'^(?:Dto\.\s*\d+/\d+|Exp\.\s*(?:IMUH\s*)?\d+-[A-Za-z0-9\-]+|\d+-[A-Za-z0-9\-]+)\s*-\s*', '', dest_clean, flags=re.IGNORECASE)
    return dest_clean


def obtener_datos_composicion(sel_dec_id, sel_cuota_id):
    """Calcula la composición de fondos para una cuota específica."""
    decretos_list = db.get_decretos()
    cuotas_list = db.get_cuotas_by_decreto(sel_dec_id)
    cuota_sel_dict = next(c for c in cuotas_list if c['id'] == sel_cuota_id)
    
    cuota_ids = [c['id'] for c in cuotas_list]
    cuota_seq_num = cuota_ids.index(sel_cuota_id) + 1
    
    cobros_cuota = db.get_cobros_by_cuota(sel_cuota_id) or []
    
    estado_actual_filas = []
    
    for cb in cobros_cuota:
        cb_id = cb['id']
        dist = db.get_distribucion_by_cobro(cb_id)
        monto_fo = dist['monto_fin_orig'] if dist else 0.0
        monto_res = dist['monto_reserva'] if dist else 0.0
        
        tot_rec_sin_distribucion = 0.0
        
        # A. Fin Original (Pagos realizados)
        usos_fo = db.get_fin_original_usos_by_cobro(cb_id)
        sum_usos_fo = 0.0
        for u in usos_fo:
            sum_usos_fo += u['monto']
            estado_actual_filas.append({
                "Fecha": utils.format_date_ar(u['fecha']),
                "Movimiento": "Fin original",
                "Monto": u['monto'],
                "Orden de Pago (OP)": u['nro_op'] or "Sin asignar",
                "Destino": "Obra original",
                "obra_id": u.get("obra_id"),
                "Aclaraciones": u['notas'] or ""
            })
            
        # B. Fin Original (Pendiente)
        fo_pendiente = monto_fo - sum_usos_fo
        if fo_pendiente > 0.01:
            estado_actual_filas.append({
                "Fecha": "-",
                "Movimiento": "Fin original (Pendiente)",
                "Monto": fo_pendiente,
                "Orden de Pago (OP)": "-",
                "Destino": "Obra original (Fondo en cuenta)",
                "Aclaraciones": ""
            })
            
        # C. En Reserva (Saldo Disponible)
        usos_r = db.get_reserva_usos_by_cobro(cb_id)
        tot_usos_r = sum(u['monto'] for u in usos_r)
        
        # Recuperos a reserva
        tot_rec_a_res = 0.0
        for u in usos_r:
            recs = db.get_recuperos_by_reserva_uso(u['id'])
            for r in recs:
                if r['destino_tipo'] == 'reserva':
                    tot_rec_a_res += r['monto']
                    
        res_saldo_neto = monto_res - tot_usos_r + tot_rec_a_res
        if res_saldo_neto > 0.01:
            estado_actual_filas.append({
                "Fecha": "-",
                "Movimiento": "En reserva",
                "Monto": res_saldo_neto,
                "Orden de Pago (OP)": "-",
                "Destino": "Reserva disponible",
                "Aclaraciones": ""
            })
            
        # D. Préstamos / Desvíos desde Reserva (Activos)
        for u in usos_r:
            if u['destino_tipo'] != 'fin_original':
                recs = db.get_recuperos_by_reserva_uso(u['id'])
                sum_recs = sum(r['monto'] for r in recs)
                u_net = u['monto'] - sum_recs
                if u_net > 0.01:
                    estado_actual_filas.append({
                        "Fecha": utils.format_date_ar(u['fecha']),
                        "Movimiento": "Desvío a otra obra (desde Reserva)",
                        "Monto": u_net,
                        "Orden de Pago (OP)": u['nro_op'] or "Sin asignar",
                        "Destino": u['destino_detalle'] or "Obra sin decreto",
                        "obra_id": u.get("obra_id"),
                        "gasto_nombre": u.get("gasto_nombre"),
                        "gasto_expediente_imuh": u.get("gasto_expediente_imuh"),
                        "Aclaraciones": u['notas'] or ""
                    })
                
                # E. Recuperos de Reserva (Redireccionados)
                for r in recs:
                    if r['destino_tipo'] != 'reserva':
                        if r['destino_tipo'] == 'sin_distribucion':
                            tot_rec_sin_distribucion += r['monto']
                        elif r['destino_tipo'] == 'compensacion':
                            detalles = db.obtener_detalles_compensacion_grupo(r['grupo_compensacion_id'])
                            fecha_pago = utils.format_date_ar(r['fecha'])
                            op_orig_str = "Sin OP"
                            dec_cruzado_str = "otro decreto"
                            fecha_orig_str = ""
                            
                            if detalles:
                                desv_rec = detalles['desvios'][0] if detalles['desvios'] else None
                                if desv_rec:
                                    dec_cruzado_str = f"Dto. {desv_rec['nro_decreto']}/{desv_rec['dec_anio']}"
                                
                                if u.get('nro_op'):
                                    op_orig_str = f"OP {u['nro_op']}"
                                elif u.get('fecha'):
                                    op_orig_str = f"pago del {utils.format_date_ar(u['fecha'])}"
                                
                                if u.get('fecha'):
                                    fecha_orig_str = f" del {utils.format_date_ar(u['fecha'])}"
                                    
                                all_ops = []
                                for x in detalles['desvios'] + detalles['reservas']:
                                    if x.get('rec_op'):
                                        all_ops.append(x['rec_op'])
                                
                                ops_list = []
                                for op in all_ops:
                                    if op and op.strip() and op.strip() != 'Sin OP':
                                        ops_list.extend([o.strip() for o in str(op).replace(',', '-').split('-')])
                                ops_uniq = sorted(list(set(ops_list)))
                                ops_str = ", ".join(ops_uniq) if ops_uniq else "Sin OP"
                                
                                acl = f"Originalmente desviado a {dec_cruzado_str} ({op_orig_str}{fecha_orig_str}), recuperado mediante compensación el {utils.format_date_ar(r['fecha'])} afectando a OP {ops_str} (Compensación)"
                            else:
                                acl = "Compensación de deudas cruzadas (Compensación)"
                                
                            estado_actual_filas.append({
                                "Fecha": fecha_pago,
                                "Movimiento": "Fin original (Recupero de Reserva)",
                                "Monto": r['monto'],
                                "Orden de Pago (OP)": r['nro_op'] or "Sin asignar",
                                "Destino": "Obra original",
                                "Aclaraciones": acl
                            })
                        else:
                            dest_r = "Obra original" if r['destino_tipo'] == 'fin_original' else (r.get('dest_nombre') or r.get('destino_detalle') or "Otra obra")
                            mov_r = "Fin original (Recupero de Reserva)" if r['destino_tipo'] == 'fin_original' else "Desvío a otra obra (Recupero de Reserva)"
                            estado_actual_filas.append({
                                "Fecha": utils.format_date_ar(r['fecha']),
                                "Movimiento": mov_r,
                                "Monto": r['monto'],
                                "Orden de Pago (OP)": r['nro_op'] or "Sin asignar",
                                "Destino": dest_r,
                                "Aclaraciones": ""
                            })
            else:
                # Reserve use to Fin Original
                estado_actual_filas.append({
                    "Fecha": utils.format_date_ar(u['fecha']),
                    "Movimiento": "Fin original (desde Reserva)",
                    "Monto": u['monto'],
                    "Orden de Pago (OP)": u['nro_op'] or "Sin asignar",
                    "Destino": "Obra original",
                    "obra_id": u.get("obra_id"),
                    "gasto_nombre": u.get("gasto_nombre"),
                    "gasto_expediente_imuh": u.get("gasto_expediente_imuh"),
                    "Aclaraciones": u['notas'] or ""
                })
                
        # F. Desvíos Iniciales (Activos y Recuperos Redireccionados)
        desvios = db.get_desvios_by_cobro(cb_id)
        for d in desvios:
            recs = db.get_recuperos_by_desvio(d['id'])
            sum_recs = sum(r['monto'] for r in recs)
            d_net = d['monto'] - sum_recs
            if d_net > 0.01:
                selected_op = d['nro_op'] or "Sin asignar"
                estado_actual_filas.append({
                    "Fecha": utils.format_date_ar(d['fecha']),
                    "Movimiento": "Desvío a otra obra",
                    "Monto": d_net,
                    "Orden de Pago (OP)": selected_op,
                    "Destino": d['destino'],
                    "obra_id": d.get("obra_id"),
                    "gasto_nombre": d.get("gasto_nombre"),
                    "gasto_expediente_imuh": d.get("gasto_expediente_imuh"),
                    "Aclaraciones": d['motivo'] or ""
                })
                
            # Recuperos redireccionados
            for r in recs:
                if r['destino_tipo'] == 'sin_distribucion':
                    tot_rec_sin_distribucion += r['monto']
                elif r['destino_tipo'] == 'compensacion':
                    detalles = db.obtener_detalles_compensacion_grupo(r['grupo_compensacion_id'])
                    fecha_pago = utils.format_date_ar(r['fecha'])
                    op_orig_str = "Sin OP"
                    dec_cruzado_str = "otro decreto"
                    fecha_orig_str = ""
                    
                    if detalles:
                        res_rec = detalles['reservas'][0] if detalles['reservas'] else None
                        if res_rec:
                            dec_cruzado_str = f"Dto. {res_rec['nro_decreto']}/{res_rec['dec_anio']}"
                            if res_rec.get('uso_fecha'):
                                fecha_pago = utils.format_date_ar(res_rec['uso_fecha'])
                                fecha_orig_str = f" del {utils.format_date_ar(res_rec['uso_fecha'])}"
                            if res_rec.get('uso_op'):
                                op_orig_str = f"OP {res_rec['uso_op']}"
                            elif res_rec.get('uso_fecha'):
                                op_orig_str = f"pago del {utils.format_date_ar(res_rec['uso_fecha'])}"
                                
                        all_ops = []
                        for x in detalles['desvios'] + detalles['reservas']:
                            if x.get('rec_op'):
                                all_ops.append(x['rec_op'])
                        
                        ops_list = []
                        for op in all_ops:
                            if op and op.strip() and op.strip() != 'Sin OP':
                                ops_list.extend([o.strip() for o in str(op).replace(',', '-').split('-')])
                        ops_uniq = sorted(list(set(ops_list)))
                        ops_str = ", ".join(ops_uniq) if ops_uniq else "Sin OP"
                        
                        acl = f"Fondos originados en {dec_cruzado_str} ({op_orig_str}{fecha_orig_str}), compensados el {utils.format_date_ar(r['fecha'])} afectando a OP {ops_str} (Compensación)"
                    else:
                        acl = "Compensación de deudas cruzadas (Compensación)"
                        
                    estado_actual_filas.append({
                        "Fecha": fecha_pago,
                        "Movimiento": "Fin original (Recupero)",
                        "Monto": r['monto'],
                        "Orden de Pago (OP)": r['nro_op'] or "Sin asignar",
                        "Destino": "Obra original",
                        "Aclaraciones": acl
                    })
                else:
                    dest_r = "Obra original" if r['destino_tipo'] == 'fin_original' else (r.get('dest_nombre') or r.get('destino_detalle') or "Otra obra")
                    mov_r = "Fin original (Recupero)" if r['destino_tipo'] == 'fin_original' else "Desvío a otra obra (Recupero)"
                    estado_actual_filas.append({
                        "Fecha": utils.format_date_ar(r['fecha']),
                        "Movimiento": mov_r,
                        "Monto": r['monto'],
                        "Orden de Pago (OP)": r['nro_op'] or "Sin asignar",
                        "Destino": dest_r,
                        "Aclaraciones": ""
                    })
                
        # G. Sin Distribuir
        tot_desvios_ini = sum(d['monto'] for d in desvios)
        saldo_libre = cb['monto'] - (monto_fo + monto_res + tot_desvios_ini) + tot_rec_sin_distribucion
        if saldo_libre > 0.01:
            estado_actual_filas.append({
                "Fecha": "-",
                "Movimiento": "Sin distribuir",
                "Monto": saldo_libre,
                "Orden de Pago (OP)": "-",
                "Destino": "Sin distribuir",
                "Aclaraciones": ""
            })
            
    sum_total_actual = sum(f['Monto'] for f in estado_actual_filas)
    
    fechas_list = sorted(list(set(utils.format_date_ar(c['fecha']) for c in cobros_cuota)))
    fechas_str = ", ".join(fechas_list) if fechas_list else "Sin cobros registrados"
    
    notas_list = []
    for cb in cobros_cuota:
        dist = db.get_distribucion_by_cobro(cb['id'])
        if dist and dist.get('notas') and dist['notas'].strip():
            notas_list.append(f"Cobro {utils.format_date_ar(cb['fecha'])}: {dist['notas'].strip()}")
    aclaraciones_str = "\n".join(notas_list) if notas_list else ""
    
    # Post-procesamiento para unificar Expediente IMUH
    obras_list = db.get_obras() or []
    obra_imuh_map = {o['id']: o['expediente_imuh'] for o in obras_list if o.get('id')}
    dec = db.get_decreto(sel_dec_id)
    dec_imuh = dec.get('expediente_imuh') if dec else None
    
    for row in estado_actual_filas:
        exp_val = None
        if row.get("gasto_expediente_imuh"):
            exp_val = row["gasto_expediente_imuh"]
        elif row.get("obra_id"):
            exp_val = obra_imuh_map.get(row["obra_id"])
            
        if not exp_val:
            dest_lower = str(row.get("Destino", "")).lower()
            if "obra original" in dest_lower or "reserva" in dest_lower:
                exp_val = dec_imuh
            else:
                extracted = utils.extraer_imuh_de_texto(str(row.get("Destino", "")))
                if extracted:
                    exp_val = extracted
                    
        row["expediente_imuh"] = exp_val or "-"

    return estado_actual_filas, sum_total_actual, cobros_cuota, cuota_seq_num, fechas_str, aclaraciones_str, cuota_sel_dict

def obtener_afectacion_decreto(sel_dec_id):
    """Obtiene la afectación consolidada de todas las cuotas de un decreto para el reporte 'Afectación de decretos'."""
    dec = db.get_decreto(sel_dec_id)
    cuotas_list = db.get_cuotas_by_decreto(sel_dec_id)
    cuota_ids = [c['id'] for c in cuotas_list]
    
    # Obtener proveedor de la obra original asignada al decreto
    obras_asoc = db.get_obras_by_decreto(sel_dec_id)
    prov_orig_razon = None
    if obras_asoc and obras_asoc[0].get('proveedor_razon_social'):
        prov_orig_razon = obras_asoc[0]['proveedor_razon_social']
    
    filas_reporte = []
    
    for c in cuotas_list:
        seq_num = cuota_ids.index(c['id']) + 1
        estado_actual_filas, sum_total_actual, cobros_cuota, _, fechas_str, _, _ = obtener_datos_composicion(sel_dec_id, c['id'])
        
        importe_percibido = sum(cb['monto'] for cb in cobros_cuota)
        
        if not estado_actual_filas:
            filas_reporte.append({
                "Nro. Cuota": seq_num,
                "Fecha de cobro": "-",
                "Importe percibido": importe_percibido,
                "Proveedor": "-",
                "Obra destino": "-",
                "Fecha de pago": "-",
                "Importe pagado": 0.0,
                "Nro. OP Bejerman": "-",
                "Observaciones/aclaraciones": "Pendiente de cobro / Sin distribución"
            })
        else:
            for row in estado_actual_filas:
                dest = str(row["Destino"])
                prov_str = "-"
                
                obra_obj = None
                if row.get("obra_id"):
                    obra_obj = db.get_obra(row["obra_id"])
                    
                if obra_obj and obra_obj.get('proveedor_razon_social'):
                    prov_str = obra_obj['proveedor_razon_social']
                elif dest == "Obra original":
                    prov_str = prov_orig_razon if prov_orig_razon else "NO INFORMA PROVEEDOR"
                elif dest in ["Sin distribuir", "Reserva disponible"]:
                    prov_str = "-"
                elif "FUN:" in dest or row.get("gasto_expediente_imuh") or row.get("gasto_nombre"):
                    exp = row.get("gasto_expediente_imuh")
                    g_fun = db.get_gasto_funcionamiento_by_expediente(exp) if exp else None
                    if g_fun and g_fun.get('proveedor_razon_social'):
                        prov_str = g_fun['proveedor_razon_social']
                    else:
                        prov_str = "NO INFORMA PROVEEDOR"
                else:
                    exp_imuh = utils.extraer_imuh_de_texto(dest)
                    if exp_imuh:
                        obra_obj = db.get_obra_by_expediente(exp_imuh)
                    if obra_obj and obra_obj.get('proveedor_razon_social'):
                        prov_str = obra_obj['proveedor_razon_social']
                    else:
                        prov_str = "NO INFORMA PROVEEDOR"

                # Calcular Tipo de afectación y Obra destino
                mov_str = str(row.get("Movimiento", ""))
                if "Fin original" in mov_str:
                    tipo_afectacion = "Obra original"
                elif dest in ["Sin distribuir", "Reserva disponible"]:
                    tipo_afectacion = "-"
                else:
                    tipo_afectacion = "Desvío"

                # Formatear Obra destino: Nro. expediente imuh + nombre de la obra o gasto
                if row.get("expediente_imuh") and row.get("expediente_imuh") != "-":
                    imuh = row["expediente_imuh"]
                    nombre_gasto_obra = ""
                    if obra_obj:
                        nombre_gasto_obra = obra_obj.get("nombre", "")
                    elif "FUN:" in dest or row.get("gasto_nombre"):
                        nombre_gasto_obra = row.get("gasto_nombre") or dest.replace("FUN: ", "")
                    elif dest and "Obra original" not in dest and "Reserva" not in dest:
                        nombre_gasto_obra = dest.split(" - ")[-1] if " - " in dest else dest
                    else:
                        # Si es obra original global (aun sin asignar a un expediente específico pero que tiene un exp)
                        # Trata de buscar la obra por el IMUH si no la encontró por obra_id
                        o_obj = db.get_obra_by_expediente(imuh)
                        if o_obj:
                            nombre_gasto_obra = o_obj.get("nombre", "")

                    if nombre_gasto_obra:
                        dest = f"{imuh} - {nombre_gasto_obra}"
                    else:
                        dest = f"{imuh}"
                
                filas_reporte.append({
                    "Nro. Cuota": seq_num,
                    "Fecha de cobro": fechas_str,
                    "Importe percibido": importe_percibido,
                    "Proveedor": prov_str,
                    "Tipo de afectación": tipo_afectacion,
                    "Obra destino": dest,
                    "Fecha de pago": row["Fecha"],
                    "Importe pagado": row["Monto"],
                    "Nro. OP Bejerman": row["Orden de Pago (OP)"],
                    "Observaciones/aclaraciones": row["Aclaraciones"]
                })
                
    return dec, cuotas_list, filas_reporte

def parse_excel_date_val(val):
    if not val or str(val).strip() == "-":
        return "-"
    if isinstance(val, (datetime.date, datetime.datetime)):
        return val
    if isinstance(val, str):
        v = val.strip()
        for fmt in ('%Y-%m-%d', '%d-%m-%Y', '%d/%m/%Y'):
            try:
                return datetime.datetime.strptime(v, fmt).date()
            except ValueError:
                pass
    return val

def generar_excel_afectacion(dec, filas_reporte, pendiente_cobro):
    excel_buffer = io.BytesIO()
    with pd.ExcelWriter(excel_buffer, engine='xlsxwriter', date_format='dd/mm/yyyy') as writer:
        workbook = writer.book
        worksheet = workbook.add_worksheet('Afectación')
        writer.sheets['Afectación'] = worksheet
        
        bold = workbook.add_format({'bold': True})
        money = workbook.add_format({'num_format': '#,##0.00'})
        header_format = workbook.add_format({'bold': True, 'bg_color': '#f0f0f0', 'border': 1})
        cell_format = workbook.add_format({'border': 1})
        money_cell = workbook.add_format({'num_format': '#,##0.00', 'border': 1})
        date_cell_format = workbook.add_format({'num_format': 'dd/mm/yyyy', 'border': 1})
        merge_date_format = workbook.add_format({'align': 'center', 'valign': 'vcenter', 'num_format': 'dd/mm/yyyy', 'border': 1})
        
        total_decreto = sum(c['monto'] for c in db.get_cuotas_by_decreto(dec['id']))
        
        worksheet.write(0, 0, f"Decreto {dec['nro_decreto']}/{dec['anio']}", bold)
        worksheet.write(1, 0, 'Expediente IMUH:', bold)
        worksheet.write(1, 1, dec.get('expediente_imuh') or "Sin asignar")
        worksheet.write(2, 0, 'Obra:', bold)
        worksheet.write(2, 1, dec['destino_fondos'])
        
        worksheet.write(4, 0, 'Total decreto', bold)
        worksheet.write(4, 1, total_decreto, money)
        worksheet.write(5, 0, 'Pendiente de cobro', bold)
        worksheet.write(5, 1, pendiente_cobro, money)
        
        headers = ["Nro. Cuota", "Fecha de cobro", "Importe percibido", "Proveedor", "Tipo de afectación", "Obra destino", "Fecha de pago", "Importe pagado", "Nro. OP Bejerman", "Observaciones/aclaraciones"]
        row_idx = 7
        for col_num, header in enumerate(headers):
            worksheet.write(row_idx, col_num, header, header_format)
            
        data_start_row = row_idx + 1
        
        # Para hacer merge de celdas como en el mockup, necesitamos trackear la cuota
        merge_format = workbook.add_format({'align': 'center', 'valign': 'vcenter', 'border': 1})
        merge_money_format = workbook.add_format({'align': 'center', 'valign': 'vcenter', 'num_format': '#,##0.00', 'border': 1})
        
        current_row = data_start_row
        
        import itertools
        for key, group in itertools.groupby(filas_reporte, key=lambda x: x["Nro. Cuota"]):
            group_list = list(group)
            num_rows = len(group_list)
            
            first_row = group_list[0]
            f_cobro_val = parse_excel_date_val(first_row["Fecha de cobro"])
            
            # Merge logic for Nro. Cuota, Fecha de cobro, Importe percibido
            if num_rows > 1:
                worksheet.merge_range(current_row, 0, current_row + num_rows - 1, 0, first_row["Nro. Cuota"], merge_format)
                if isinstance(f_cobro_val, (datetime.date, datetime.datetime)):
                    worksheet.merge_range(current_row, 1, current_row + num_rows - 1, 1, f_cobro_val, merge_date_format)
                else:
                    worksheet.merge_range(current_row, 1, current_row + num_rows - 1, 1, str(f_cobro_val), merge_format)
                worksheet.merge_range(current_row, 2, current_row + num_rows - 1, 2, first_row["Importe percibido"], merge_money_format)
            else:
                worksheet.write(current_row, 0, first_row["Nro. Cuota"], merge_format)
                if isinstance(f_cobro_val, (datetime.date, datetime.datetime)):
                    worksheet.write_datetime(current_row, 1, f_cobro_val, merge_date_format)
                else:
                    worksheet.write(current_row, 1, str(f_cobro_val), merge_format)
                worksheet.write(current_row, 2, first_row["Importe percibido"], merge_money_format)
                
            for i, r in enumerate(group_list):
                worksheet.write(current_row + i, 3, r.get("Proveedor", "-"), cell_format)
                worksheet.write(current_row + i, 4, r.get("Tipo de afectación", "-"), cell_format)
                worksheet.write(current_row + i, 5, r["Obra destino"], cell_format)
                
                f_pago_val = parse_excel_date_val(r["Fecha de pago"])
                if isinstance(f_pago_val, (datetime.date, datetime.datetime)):
                    worksheet.write_datetime(current_row + i, 6, f_pago_val, date_cell_format)
                else:
                    worksheet.write(current_row + i, 6, str(f_pago_val), cell_format)
                    
                worksheet.write(current_row + i, 7, r["Importe pagado"], money_cell)
                worksheet.write(current_row + i, 8, r["Nro. OP Bejerman"], cell_format)
                worksheet.write(current_row + i, 9, r.get("Observaciones/aclaraciones", ""), cell_format)
                
            current_row += num_rows
            
        # Adjust column widths
        worksheet.set_column(0, 0, 10)
        worksheet.set_column(1, 1, 15)
        worksheet.set_column(2, 2, 20)
        worksheet.set_column(3, 3, 25)
        worksheet.set_column(4, 4, 30)
        worksheet.set_column(5, 5, 15)
        worksheet.set_column(6, 6, 20)
        worksheet.set_column(7, 7, 20)
        worksheet.set_column(8, 8, 40)
        
    return excel_buffer.getvalue()

def generar_pdf_afectacion(dec, filas_reporte, pendiente_cobro, incluir_resumen=False):
    from fpdf import FPDF
    temp_path = os.path.join(tempfile.gettempdir(), f"Afectacion_{dec['nro_decreto']}_{dec['anio']}_{uuid.uuid4().hex[:8]}.pdf")
    
    class PDF(FPDF):
        def header(self):
            self.set_font('helvetica', 'B', 15)
            self.cell(0, 10, 'Reporte de Afectación de Decretos', ln=True, align='C')
            self.ln(5)
            
        def footer(self):
            self.set_y(-15)
            self.set_font('helvetica', 'I', 8)
            self.cell(0, 10, f'Página {self.page_no()}', 0, 0, 'C')

    pdf = PDF('L', 'mm', 'A4') # Landscape for more space
    pdf.add_page()
    
    total_decreto = sum(c['monto'] for c in db.get_cuotas_by_decreto(dec['id']))
    
    pdf.set_font("helvetica", "B", 12)
    pdf.cell(50, 8, f"Decreto {dec['nro_decreto']}/{dec['anio']}", ln=True)
    pdf.set_font("helvetica", "", 10)
    pdf.cell(40, 8, "Expediente IMUH:", 0, 0)
    pdf.multi_cell(0, 8, dec.get('expediente_imuh') or "Sin asignar")
    pdf.cell(40, 8, "Obra:", 0, 0)
    pdf.multi_cell(0, 8, dec['destino_fondos'], align='L')
    
    pdf.cell(40, 8, "Total decreto:", 0, 0)
    pdf.cell(0, 8, utils.format_currency_ar(total_decreto), ln=True)
    pdf.cell(40, 8, "Pendiente de cobro:", 0, 0)
    pdf.cell(0, 8, utils.format_currency_ar(pendiente_cobro), ln=True)
    
    if incluir_resumen:
        resumen_txt = generar_resumen_narrativo_decreto(dec, filas_reporte, total_decreto, pendiente_cobro)
        
        pdf.ln(3)
        pdf.set_font("helvetica", "B", 10)
        pdf.cell(0, 8, "Resumen y Afectacion del Decreto:", ln=True)
        pdf.set_font("helvetica", "", 8.5)
        
        lines = resumen_txt.split('\n')
        start_printing = False
        for line in lines:
            line_str = line.strip()
            if "Historial de Flujo de Fondos:" in line_str:
                start_printing = True
                pdf.ln(2)
                pdf.set_font("helvetica", "B", 9)
                pdf.cell(0, 6, "Historial de Flujo de Fondos:", ln=True)
                pdf.set_font("helvetica", "", 8.5)
                continue
            if "Estado Actual de Saldos Consolidados:" in line_str:
                start_printing = True
                pdf.ln(3)
                pdf.set_font("helvetica", "B", 9)
                pdf.cell(0, 6, "Estado Actual de Saldos Consolidados:", ln=True)
                pdf.set_font("helvetica", "", 8.5)
                continue
            
            if start_printing:
                if not line_str:
                    continue
                clean_line = line_str.replace('**', '').replace('*', '').strip()
                indent = 0
                if line.startswith('    *') or line.startswith('\t*') or line.startswith('  *'):
                    indent = 8
                
                pdf.set_x(10 + indent)
                pdf.multi_cell(0, 5, clean_line)
                
    pdf.ln(5)
    
    # Table Header
    pdf.set_font("helvetica", "B", 8)
    col_widths = [10, 16, 21, 28, 20, 48, 16, 21, 16, 69]
    headers = ["Cuota", "F. Cobro", "Imp. Percibido", "Proveedor", "Tipo afect.", "Obra destino", "F. Pago", "Imp. Pagado", "Nro. OP", "Observaciones"]
    
    for i, h in enumerate(headers):
        pdf.cell(col_widths[i], 10, h, border=1, align='C')
    pdf.ln()
    
    pdf.set_font("helvetica", "", 8)
    
    import itertools
    for key, group in itertools.groupby(filas_reporte, key=lambda x: x["Nro. Cuota"]):
        group_list = list(group)
        
        for i, r in enumerate(group_list):
            prov = str(r.get("Proveedor", "-"))
            tipo_afect = str(r.get("Tipo de afectación", "-"))
            dest = str(r["Obra destino"])
            obs = str(r["Observaciones/aclaraciones"])
            
            lines_prov = pdf.get_string_width(prov) / (col_widths[3] - 2)
            lines_tipo = pdf.get_string_width(tipo_afect) / (col_widths[4] - 2)
            lines_dest = pdf.get_string_width(dest) / (col_widths[5] - 2)
            lines_obs = pdf.get_string_width(obs) / (col_widths[9] - 2)
            max_lines = max(1, int(lines_prov) + 1, int(lines_tipo) + 1, int(lines_dest) + 1, int(lines_obs) + 1)
            line_height = 5
            row_height = max_lines * line_height

            start_x = pdf.get_x()
            start_y = pdf.get_y()
            
            # Check page break BEFORE drawing the cells for this row
            if start_y + row_height > 185:
                pdf.add_page()
                # Redraw header
                pdf.set_font("helvetica", "B", 8)
                for j, h in enumerate(headers):
                    pdf.cell(col_widths[j], 10, h, border=1, align='C')
                pdf.ln()
                pdf.set_font("helvetica", "", 8)
                start_x = pdf.get_x()
                start_y = pdf.get_y()
                
            # Print first 3 cols only if it's the first row of the group, else blank
            if i == 0:
                cuota_val = str(r["Nro. Cuota"])
                fecha_cobro = str(r["Fecha de cobro"])
                imp_perc = utils.format_currency_ar(r["Importe percibido"])
            else:
                cuota_val = ""
                fecha_cobro = ""
                imp_perc = ""
                
            # Draw cells
            pdf.cell(col_widths[0], row_height, cuota_val, border=1, align='C')
            
            # Fecha cobro multiline if needed
            x = pdf.get_x()
            y = pdf.get_y()
            pdf.rect(x, y, col_widths[1], row_height)
            pdf.set_xy(x, y + (row_height - line_height)/2 if cuota_val else y)
            pdf.multi_cell(col_widths[1], line_height, fecha_cobro, border=0, align='C')
            pdf.set_xy(x + col_widths[1], y)
            
            pdf.cell(col_widths[2], row_height, imp_perc, border=1, align='R')
            
            # Proveedor multiline
            x = pdf.get_x()
            y = pdf.get_y()
            pdf.rect(x, y, col_widths[3], row_height)
            pdf.multi_cell(col_widths[3], line_height, prov, border=0, align='L')
            pdf.set_xy(x + col_widths[3], y)
            
            # Tipo de afectacion multiline
            x = pdf.get_x()
            y = pdf.get_y()
            pdf.rect(x, y, col_widths[4], row_height)
            pdf.multi_cell(col_widths[4], line_height, tipo_afect, border=0, align='C')
            pdf.set_xy(x + col_widths[4], y)
            
            # Destino multiline
            x = pdf.get_x()
            y = pdf.get_y()
            pdf.rect(x, y, col_widths[5], row_height)
            pdf.multi_cell(col_widths[5], line_height, dest, border=0, align='L')
            pdf.set_xy(x + col_widths[5], y)
            
            pdf.cell(col_widths[6], row_height, str(r["Fecha de pago"]), border=1, align='C')
            pdf.cell(col_widths[7], row_height, utils.format_currency_ar(r["Importe pagado"]), border=1, align='R')
            pdf.cell(col_widths[8], row_height, str(r["Nro. OP Bejerman"]), border=1, align='C')
            
            # Observaciones multiline
            x = pdf.get_x()
            y = pdf.get_y()
            pdf.rect(x, y, col_widths[9], row_height)
            pdf.multi_cell(col_widths[9], line_height, obs, border=0, align='L')
            pdf.set_xy(start_x, y + row_height)
            
    pdf.output(temp_path)
    with open(temp_path, 'rb') as f:
        pdf_data = f.read()
    try:
        os.remove(temp_path)
    except OSError:
        pass
    return pdf_data



def generar_excel_composicion(dec, cuota_sel_dict, cuota_seq_num, fechas_str, aclaraciones_str, df_export):
    excel_buffer = io.BytesIO()
    with pd.ExcelWriter(excel_buffer, engine='xlsxwriter') as writer:
        workbook = writer.book
        worksheet = workbook.add_worksheet('Composición')
        writer.sheets['Composición'] = worksheet
        
        bold = workbook.add_format({'bold': True})
        money = workbook.add_format({'num_format': '#,##0.00'})
        
        worksheet.write(0, 0, 'REPORTE DE COMPOSICIÓN DE FONDOS', bold)
        worksheet.write(2, 0, 'Decreto:', bold)
        worksheet.write(2, 1, f"Dto. {dec['nro_decreto']}/{dec['anio']}")
        worksheet.write(3, 0, 'Expediente IMUH:', bold)
        worksheet.write(3, 1, dec.get('expediente_imuh') or "Sin asignar")
        worksheet.write(4, 0, 'Nombre de la Obra:', bold)
        worksheet.write(4, 1, dec['destino_fondos'])
        
        worksheet.write(2, 3, 'Cuota N°:', bold)
        worksheet.write(2, 4, f"Cuota {cuota_seq_num}")
        worksheet.write(3, 3, 'Importe de Cuota:', bold)
        worksheet.write(3, 4, cuota_sel_dict['monto'], money)
        worksheet.write(4, 3, 'Fechas de Cobro:', bold)
        worksheet.write(4, 4, fechas_str)
        
        row_idx = 6
        if aclaraciones_str:
            worksheet.write(row_idx, 0, 'Aclaraciones generales:', bold)
            worksheet.write(row_idx, 1, aclaraciones_str)
            row_idx += 2
            
        headers = ["Fecha", "Destino", "OP", "Aclaraciones", "Monto"]
        for col_num, header in enumerate(headers):
            worksheet.write(row_idx, col_num, header, bold)
            
        data_start_row = row_idx + 1
        for i, r in df_export.iterrows():
            curr_row = data_start_row + i
            worksheet.write(curr_row, 0, r["Fecha"])
            worksheet.write(curr_row, 1, r["Destino"])
            worksheet.write(curr_row, 2, r["OP"])
            worksheet.write(curr_row, 3, r["Aclaraciones"])
            worksheet.write(curr_row, 4, r["Monto"], money)
            
        total_row_idx = data_start_row + len(df_export)
        worksheet.write(total_row_idx, 0, "TOTAL", bold)
        worksheet.write(total_row_idx, 1, "")
        worksheet.write(total_row_idx, 2, "")
        worksheet.write(total_row_idx, 3, "")
        worksheet.write_formula(total_row_idx, 4, f"=SUM(E{data_start_row+1}:E{total_row_idx})", bold)
        
    return excel_buffer.getvalue()

def generar_pdf_composicion(dec, cuota_sel_dict, cuota_seq_num, fechas_str, aclaraciones_str, sum_total_actual, df_export):
    temp_path_comp = os.path.join(tempfile.gettempdir(), f"Reporte_Composicion_{dec['nro_decreto']}_{dec['anio']}_Cuota_{cuota_seq_num}_{uuid.uuid4().hex[:8]}.pdf")
    
    decreto_info = {
        "identificacion": f"Dto. {dec['nro_decreto']}/{dec['anio']}",
        "expediente_imuh": dec.get('expediente_imuh') or "Sin asignar",
        "destino": dec['destino_fondos']
    }
    
    cuota_info = {
        "numero": f"Cuota {cuota_seq_num} ({cuota_sel_dict['mes']:02d}/{cuota_sel_dict['anio']})",
        "importe": cuota_sel_dict['monto'],
        "fechas_cobro": fechas_str
    }
    
    df_comp_pdf = pd.DataFrame()
    df_comp_pdf["Fecha"] = df_export["Fecha"]
    df_comp_pdf["Destino"] = df_export["Destino"]
    df_comp_pdf["OP"] = df_export["OP"]
    df_comp_pdf["Aclaraciones"] = df_export["Aclaraciones"]
    df_comp_pdf["Monto"] = df_export["Monto"].apply(lambda x: utils.format_currency_ar(x, include_symbol=False))
    
    df_comp_pdf.loc[len(df_comp_pdf)] = ["TOTAL", "", "", "", utils.format_currency_ar(sum_total_actual, include_symbol=False)]
    
    generar_reporte_composicion_pdf(temp_path_comp, decreto_info, cuota_info, df_comp_pdf, aclaraciones=aclaraciones_str)
    
    with open(temp_path_comp, "rb") as f:
        pdf_data = f.read()
        
    try:
        os.remove(temp_path_comp)
    except OSError:
        pass
        
    return pdf_data

def obtener_obras_con_desvios(tipo_reporte):
    """Obtiene el listado de obras con desvíos y saldos activos."""
    desvios = db.get_historial_desvios()
    obras = {}
    
    for d in desvios:
        saldo = d['saldo']
        if saldo <= 0.01:
            continue
            
        if tipo_reporte == "deudoras":
            # Deudora = destino (quien recibió y debe devolver)
            dec_id = d['decreto_destino_id']
            nombre = d['dest_nombre'] or d['destino_texto'] or "Sin nombre"
            imuh = d['dest_imuh']
            if not imuh or imuh == "Sin asignar":
                imuh = utils.extraer_imuh_de_texto(nombre) or "Sin asignar"
            nro = d['dest_nro']
            anio = d['dest_anio']
            dec_ident = f"Dto. {nro}/{anio}" if nro and anio else "Histórico / Legacy"
            
            key = (dec_id, nombre)
            if key not in obras:
                obras[key] = {
                    "id": dec_id,
                    "destino_fondos": nombre,
                    "expediente_imuh": imuh,
                    "decreto_identificacion": dec_ident,
                    "total_saldo_pendiente": 0.0
                }
            obras[key]["total_saldo_pendiente"] += saldo
            
        elif tipo_reporte == "acreedoras":
            # Acreedora = origen (quien prestó y tiene derecho a cobro)
            dec_id = d['orig_decreto_id']
            nombre = d['orig_nombre'] or "Sin nombre"
            imuh = d['orig_imuh']
            if not imuh or imuh == "Sin asignar":
                imuh = utils.extraer_imuh_de_texto(nombre) or "Sin asignar"
            nro = d['orig_nro']
            anio = d['orig_anio']
            dec_ident = f"Dto. {nro}/{anio}" if nro and anio else "Histórico / Legacy"
            
            key = (dec_id, nombre)
            if key not in obras:
                obras[key] = {
                    "id": dec_id,
                    "destino_fondos": nombre,
                    "expediente_imuh": imuh,
                    "decreto_identificacion": dec_ident,
                    "total_saldo_pendiente": 0.0
                }
            obras[key]["total_saldo_pendiente"] += saldo
            
    return list(obras.values())

def obtener_desvios_detalle(tipo_reporte, selected_obra):
    """Retorna la lista detallada de desvíos para la obra seleccionada.
    Usa funciones SQL-filtradas para mayor eficiencia (Fix 10).
    """
    if tipo_reporte == "deudoras":
        desvios = db.get_desvios_por_deudora(
            decreto_id=selected_obra['id'],
            nombre_texto=selected_obra['destino_fondos'] if selected_obra['id'] is None else None
        )
    else:
        desvios = db.get_desvios_por_acreedora(selected_obra['id'])

    detalle = []
    for d in desvios:
        if tipo_reporte == "deudoras":
            contraparte_label = "Acreedor"
            contraparte = d['orig_nombre'] or "Sin nombre"
            contraparte_imuh = d['orig_imuh']
            if not contraparte_imuh or contraparte_imuh == "Sin asignar":
                contraparte_imuh = utils.extraer_imuh_de_texto(contraparte) or "Sin asignar"
            nro = d['orig_nro']
            anio = d['orig_anio']
            contraparte_dec = f"Dto. {nro}/{anio}" if nro and anio else "N/A"
        else:
            contraparte_label = "Deudor"
            contraparte = d['dest_nombre'] or d['destino_texto'] or "Sin nombre"
            contraparte_imuh = d['dest_imuh']
            if not contraparte_imuh or contraparte_imuh == "Sin asignar":
                contraparte_imuh = utils.extraer_imuh_de_texto(contraparte) or "Sin asignar"
            nro = d['dest_nro']
            anio = d['dest_anio']
            contraparte_dec = f"Dto. {nro}/{anio}" if nro and anio else "Histórico / Legacy"

        try:
            if isinstance(d['fecha'], str):
                raw_dt = datetime.datetime.strptime(d['fecha'], '%Y-%m-%d').date()
            else:
                raw_dt = d['fecha']
        except Exception:
            raw_dt = d['fecha']

        detalle.append({
            "Fecha": utils.format_date_ar(d['fecha']),
            "raw_date": raw_dt,
            contraparte_label: contraparte,
            "Exp. IMUH": contraparte_imuh,
            "Decreto": contraparte_dec,
            "Monto Original": d['monto'],
            "Monto Reintegrado": d['total_recuperado'],
            "Saldo Pendiente": d['saldo'],
            "N° de OP": d['nro_op'] or "Sin asignar",
            "Tipo": "Reserva" if d['tipo_origen'] == 'reserva' else "Inicial",
            "Motivo/Notas": d['motivo'] or ""
        })

    return detalle

def generar_excel_desvios(tipo_reporte, selected_obra, df_desvios):
    """Genera un archivo Excel en memoria para exportar el detalle de desvíos."""
    excel_buffer = io.BytesIO()
    with pd.ExcelWriter(excel_buffer, engine='xlsxwriter') as writer:
        workbook = writer.book
        sheet_name = 'Obras Deudoras' if tipo_reporte == 'deudoras' else 'Obras Acreedoras'
        worksheet = workbook.add_worksheet(sheet_name)
        writer.sheets[sheet_name] = worksheet
        
        bold = workbook.add_format({'bold': True})
        money = workbook.add_format({'num_format': '#,##0.00'})
        
        titulo = 'REPORTE DE OBRAS DEUDORAS (DESVÍOS RECIBIDOS)' if tipo_reporte == 'deudoras' else 'REPORTE DE OBRAS ACREEDORAS (DESVÍOS OTORGADOS)'
        worksheet.write(0, 0, titulo, bold)
        
        worksheet.write(2, 0, 'Obra Seleccionada:', bold)
        worksheet.write(2, 1, selected_obra.get('destino_fondos', 'N/A'))
        
        worksheet.write(3, 0, 'Expediente IMUH:', bold)
        worksheet.write(3, 1, selected_obra.get('expediente_imuh', 'Sin asignar'))
        
        worksheet.write(4, 0, 'Asociado a Decreto:', bold)
        worksheet.write(4, 1, selected_obra.get('decreto_identificacion', 'N/A'))
        
        worksheet.write(5, 0, 'Total Saldo Pendiente:', bold)
        worksheet.write(5, 1, selected_obra.get('total_saldo_pendiente', 0.0), money)
        
        headers = list(df_desvios.columns)
        row_idx = 7
        for col_num, header in enumerate(headers):
            worksheet.write(row_idx, col_num, header, bold)
            
        data_start_row = row_idx + 1
        for i, r in df_desvios.iterrows():
            curr_row = data_start_row + i
            worksheet.write(curr_row, 0, r["Fecha"])
            worksheet.write(curr_row, 1, r[headers[1]])
            worksheet.write(curr_row, 2, r["Exp. IMUH"])
            worksheet.write(curr_row, 3, r["Decreto"])
            worksheet.write(curr_row, 4, r["Monto Original"], money)
            worksheet.write(curr_row, 5, r["Monto Reintegrado"], money)
            worksheet.write(curr_row, 6, r["Saldo Pendiente"], money)
            worksheet.write(curr_row, 7, r["N° de OP"])
            worksheet.write(curr_row, 8, r["Tipo"])
            worksheet.write(curr_row, 9, r["Motivo/Notas"])
            
        total_row_idx = data_start_row + len(df_desvios)
        worksheet.write(total_row_idx, 0, "TOTAL PENDIENTE", bold)
        worksheet.write(total_row_idx, 1, "")
        worksheet.write(total_row_idx, 2, "")
        worksheet.write(total_row_idx, 3, "")
        worksheet.write(total_row_idx, 4, "")
        worksheet.write(total_row_idx, 5, "")
        worksheet.write_formula(total_row_idx, 6, f"=SUM(G{data_start_row+1}:G{total_row_idx})", bold)
        
    return excel_buffer.getvalue()

def generar_pdf_desvios(tipo_reporte, selected_obra, df_desvios):
    """Genera un reporte en PDF para exportar el detalle de desvíos."""
    temp_path = os.path.join(tempfile.gettempdir(), f"Reporte_Desvios_{tipo_reporte}_{datetime.date.today().strftime('%Y%m%d')}_{uuid.uuid4().hex[:8]}.pdf")
    
    titulo = "Obras Deudoras - Detalle de Desvíos" if tipo_reporte == 'deudoras' else "Obras Acreedoras - Detalle de Desvíos"
    
    df_pdf = pd.DataFrame()
    df_pdf["Fecha"] = df_desvios["Fecha"]
    headers = list(df_desvios.columns)
    contraparte_header = headers[1]
    df_pdf[contraparte_header] = df_desvios[contraparte_header]
    df_pdf["Exp. IMUH"] = df_desvios["Exp. IMUH"]
    df_pdf["Decreto"] = df_desvios["Decreto"]
    df_pdf["Monto Orig."] = df_desvios["Monto Original"].apply(lambda x: utils.format_currency_ar(x, include_symbol=False))
    df_pdf["Reintegrado"] = df_desvios["Monto Reintegrado"].apply(lambda x: utils.format_currency_ar(x, include_symbol=False))
    df_pdf["Saldo Pend."] = df_desvios["Saldo Pendiente"].apply(lambda x: utils.format_currency_ar(x, include_symbol=False))
    df_pdf["N° OP"] = df_desvios["N° de OP"]
    
    total_saldo = df_desvios["Saldo Pendiente"].sum()
    df_pdf.loc[len(df_pdf)] = ["TOTAL", "", "", "", "", "", utils.format_currency_ar(total_saldo, include_symbol=False), ""]
    
    col_widths = [18, 42, 22, 22, 22, 22, 22, 20]
    
    generar_reporte_desvios_pdf(temp_path, titulo, selected_obra, df_pdf, col_widths)
    
    with open(temp_path, "rb") as f:
        pdf_data = f.read()
        
    try:
        os.remove(temp_path)
    except OSError:
        pass
        
    return pdf_data


# ─────────────────────────────────────────────────────────────────────────────
# Reporte Unificado: Estado de Deudas por Obra
# ─────────────────────────────────────────────────────────────────────────────

def obtener_estado_deudas_por_obra(obra):
    """Dado un dict de obra (id, nombre, expediente_imuh, tipo),
    retorna (rows_acreedora, rows_deudora) donde:
      - rows_acreedora: desvíos que la obra OTORGÓ (es acreedora — le deben)
      - rows_deudora:   desvíos que la obra RECIBIÓ (es deudora — debe devolver)
    Ambos son listas de dicts con columnas estándar.
    Incluye obras del catálogo Y legacy (sin ID).
    """
    obra_id = obra.get('id')         # None si legacy
    obra_nombre = obra.get('nombre', '')
    
    rows_acreedora = []
    rows_deudora = []
    
    with db.db_session() as conn:
        cursor = conn.cursor()
        
        # 1. Acreedora (la obra prestó dinero): solo si es obra del catálogo.
        #    Un desvío o reserva se considera otorgado por esta obra si el decreto o convenio de origen 
        #    pertenece a esta obra (a través de decretos_obras o convenio_obras).
        if obra_id is not None:
            # Desvíos iniciales otorgados
            cursor.execute('''
                SELECT 
                    cd.id as desvio_id,
                    cd.fecha,
                    cd.monto,
                    COALESCE((SELECT SUM(monto) FROM cobro_desvios_recuperos WHERE desvio_id = cd.id), 0) as total_recuperado,
                    (cd.monto - COALESCE((SELECT SUM(monto) FROM cobro_desvios_recuperos WHERE desvio_id = cd.id), 0)) as saldo,
                    COALESCE(o_dest.nombre, d_dest.destino_fondos, cd.destino, 'Sin nombre') as contraparte_nombre,
                    COALESCE(o_dest.expediente_imuh, d_dest.expediente_imuh, 'Sin asignar') as contraparte_imuh,
                    CASE 
                        WHEN d_dest.id IS NOT NULL THEN 'Dto. ' || d_dest.nro_decreto || '/' || d_dest.anio 
                        ELSE 'Histórico / Legacy' 
                    END as contraparte_dec,
                    cd.nro_op,
                    'Inicial' as tipo,
                    cd.motivo
                FROM cobro_desvios cd
                JOIN cobros c ON cd.cobro_id = c.id
                LEFT JOIN cuotas cu ON c.cuota_id = cu.id
                LEFT JOIN decretos d_orig ON cu.decreto_id = d_orig.id
                LEFT JOIN convenio_solicitudes csol ON c.convenio_solicitud_id = csol.id
                LEFT JOIN convenios conv ON csol.convenio_id = conv.id
                LEFT JOIN decretos d_dest ON cd.decreto_destino_id = d_dest.id
                LEFT JOIN obras o_dest ON cd.obra_id = o_dest.id
                WHERE (
                    d_orig.id IN (SELECT decreto_id FROM decretos_obras WHERE obra_id = ?)
                    OR conv.id IN (SELECT convenio_id FROM convenio_obras WHERE obra_id = ?)
                )
            ''', (obra_id, obra_id))
            for r in cursor.fetchall():
                d = dict(r)
                if d['saldo'] > 0.01:
                    rows_acreedora.append(d)
                    
            # Usos de reserva otorgados
            cursor.execute('''
                SELECT 
                    ru.id as desvio_id,
                    ru.fecha,
                    ru.monto,
                    COALESCE((SELECT SUM(monto) FROM cobro_reserva_usos_recuperos WHERE reserva_uso_id = ru.id), 0) as total_recuperado,
                    (ru.monto - COALESCE((SELECT SUM(monto) FROM cobro_reserva_usos_recuperos WHERE reserva_uso_id = ru.id), 0)) as saldo,
                    COALESCE(o_dest.nombre, d_dest.destino_fondos, ru.destino_detalle, 'Sin nombre') as contraparte_nombre,
                    COALESCE(o_dest.expediente_imuh, d_dest.expediente_imuh, 'Sin asignar') as contraparte_imuh,
                    CASE 
                        WHEN d_dest.id IS NOT NULL THEN 'Dto. ' || d_dest.nro_decreto || '/' || d_dest.anio 
                        ELSE 'Histórico / Legacy' 
                    END as contraparte_dec,
                    ru.nro_op,
                    'Reserva' as tipo,
                    ru.notas as motivo
                FROM cobro_reserva_usos ru
                JOIN cobros c ON ru.cobro_id = c.id
                LEFT JOIN cuotas cu ON c.cuota_id = cu.id
                LEFT JOIN decretos d_orig ON cu.decreto_id = d_orig.id
                LEFT JOIN convenio_solicitudes csol ON c.convenio_solicitud_id = csol.id
                LEFT JOIN convenios conv ON csol.convenio_id = conv.id
                LEFT JOIN decretos d_dest ON ru.decreto_destino_id = d_dest.id
                LEFT JOIN obras o_dest ON ru.obra_id = o_dest.id
                WHERE ru.destino_tipo != 'fin_original'
                  AND (
                      d_orig.id IN (SELECT decreto_id FROM decretos_obras WHERE obra_id = ?)
                      OR conv.id IN (SELECT convenio_id FROM convenio_obras WHERE obra_id = ?)
                  )
            ''', (obra_id, obra_id))
            for r in cursor.fetchall():
                d = dict(r)
                if d['saldo'] > 0.01:
                    rows_acreedora.append(d)

        # 2. Deudora (la obra recibió dinero y debe devolver):
        #    Si es del catálogo: filtrar por cd.obra_id = ? o decreto_destino_id asociado.
        #    Si es legacy: filtrar por cd.destino = ? o ru.destino_detalle = ?.
        if obra_id is not None:
            # Desvíos iniciales recibidos
            cursor.execute('''
                SELECT 
                    cd.id as desvio_id,
                    cd.fecha,
                    cd.monto,
                    COALESCE((SELECT SUM(monto) FROM cobro_desvios_recuperos WHERE desvio_id = cd.id), 0) as total_recuperado,
                    (cd.monto - COALESCE((SELECT SUM(monto) FROM cobro_desvios_recuperos WHERE desvio_id = cd.id), 0)) as saldo,
                    COALESCE(d_orig.destino_fondos, conv.nombre_convenio) as contraparte_nombre,
                    COALESCE(d_orig.expediente_imuh, conv.nro_expediente, 'Sin asignar') as contraparte_imuh,
                    CASE 
                        WHEN d_orig.id IS NOT NULL THEN 'Dto. ' || d_orig.nro_decreto || '/' || d_orig.anio 
                        WHEN conv.id IS NOT NULL THEN 'Conv. ' || conv.nro_convenio
                        ELSE 'Histórico / Legacy' 
                    END as contraparte_dec,
                    cd.nro_op,
                    'Inicial' as tipo,
                    cd.motivo
                FROM cobro_desvios cd
                JOIN cobros c ON cd.cobro_id = c.id
                LEFT JOIN cuotas cu ON c.cuota_id = cu.id
                LEFT JOIN decretos d_orig ON cu.decreto_id = d_orig.id
                LEFT JOIN convenio_solicitudes csol ON c.convenio_solicitud_id = csol.id
                LEFT JOIN convenios conv ON csol.convenio_id = conv.id
                WHERE (cd.obra_id = ? OR cd.decreto_destino_id IN (SELECT decreto_id FROM decretos_obras WHERE obra_id = ?))
            ''', (obra_id, obra_id))
            for r in cursor.fetchall():
                d = dict(r)
                if d['saldo'] > 0.01:
                    rows_deudora.append(d)

            # Usos de reserva recibidos
            cursor.execute('''
                SELECT 
                    ru.id as desvio_id,
                    ru.fecha,
                    ru.monto,
                    COALESCE((SELECT SUM(monto) FROM cobro_reserva_usos_recuperos WHERE reserva_uso_id = ru.id), 0) as total_recuperado,
                    (ru.monto - COALESCE((SELECT SUM(monto) FROM cobro_reserva_usos_recuperos WHERE reserva_uso_id = ru.id), 0)) as saldo,
                    COALESCE(d_orig.destino_fondos, conv.nombre_convenio) as contraparte_nombre,
                    COALESCE(d_orig.expediente_imuh, conv.nro_expediente, 'Sin asignar') as contraparte_imuh,
                    CASE 
                        WHEN d_orig.id IS NOT NULL THEN 'Dto. ' || d_orig.nro_decreto || '/' || d_orig.anio 
                        WHEN conv.id IS NOT NULL THEN 'Conv. ' || conv.nro_convenio
                        ELSE 'Histórico / Legacy' 
                    END as contraparte_dec,
                    ru.nro_op,
                    'Reserva' as tipo,
                    ru.notas as motivo
                FROM cobro_reserva_usos ru
                JOIN cobros c ON ru.cobro_id = c.id
                LEFT JOIN cuotas cu ON c.cuota_id = cu.id
                LEFT JOIN decretos d_orig ON cu.decreto_id = d_orig.id
                LEFT JOIN convenio_solicitudes csol ON c.convenio_solicitud_id = csol.id
                LEFT JOIN convenios conv ON csol.convenio_id = conv.id
                WHERE ru.destino_tipo != 'fin_original'
                  AND (ru.obra_id = ? OR ru.decreto_destino_id IN (SELECT decreto_id FROM decretos_obras WHERE obra_id = ?))
            ''', (obra_id, obra_id))
            for r in cursor.fetchall():
                d = dict(r)
                if d['saldo'] > 0.01:
                    rows_deudora.append(d)
        else:
            # Legacy: por nombre
            cursor.execute('''
                SELECT 
                    cd.id as desvio_id,
                    cd.fecha,
                    cd.monto,
                    COALESCE((SELECT SUM(monto) FROM cobro_desvios_recuperos WHERE desvio_id = cd.id), 0) as total_recuperado,
                    (cd.monto - COALESCE((SELECT SUM(monto) FROM cobro_desvios_recuperos WHERE desvio_id = cd.id), 0)) as saldo,
                    COALESCE(d_orig.destino_fondos, conv.nombre_convenio) as contraparte_nombre,
                    COALESCE(d_orig.expediente_imuh, conv.nro_expediente, 'Sin asignar') as contraparte_imuh,
                    CASE 
                        WHEN d_orig.id IS NOT NULL THEN 'Dto. ' || d_orig.nro_decreto || '/' || d_orig.anio 
                        WHEN conv.id IS NOT NULL THEN 'Conv. ' || conv.nro_convenio
                        ELSE 'Histórico / Legacy' 
                    END as contraparte_dec,
                    cd.nro_op,
                    'Inicial' as tipo,
                    cd.motivo
                FROM cobro_desvios cd
                JOIN cobros c ON cd.cobro_id = c.id
                LEFT JOIN cuotas cu ON c.cuota_id = cu.id
                LEFT JOIN decretos d_orig ON cu.decreto_id = d_orig.id
                LEFT JOIN convenio_solicitudes csol ON c.convenio_solicitud_id = csol.id
                LEFT JOIN convenios conv ON csol.convenio_id = conv.id
                WHERE cd.obra_id IS NULL AND cd.decreto_destino_id IS NULL AND cd.destino = ?
            ''', (obra_nombre,))
            for r in cursor.fetchall():
                d = dict(r)
                if d['saldo'] > 0.01:
                    rows_deudora.append(d)

            cursor.execute('''
                SELECT 
                    ru.id as desvio_id,
                    ru.fecha,
                    ru.monto,
                    COALESCE((SELECT SUM(monto) FROM cobro_reserva_usos_recuperos WHERE reserva_uso_id = ru.id), 0) as total_recuperado,
                    (ru.monto - COALESCE((SELECT SUM(monto) FROM cobro_reserva_usos_recuperos WHERE reserva_uso_id = ru.id), 0)) as saldo,
                    COALESCE(d_orig.destino_fondos, conv.nombre_convenio) as contraparte_nombre,
                    COALESCE(d_orig.expediente_imuh, conv.nro_expediente, 'Sin asignar') as contraparte_imuh,
                    CASE 
                        WHEN d_orig.id IS NOT NULL THEN 'Dto. ' || d_orig.nro_decreto || '/' || d_orig.anio 
                        WHEN conv.id IS NOT NULL THEN 'Conv. ' || conv.nro_convenio
                        ELSE 'Histórico / Legacy' 
                    END as contraparte_dec,
                    ru.nro_op,
                    'Reserva' as tipo,
                    ru.notas as motivo
                FROM cobro_reserva_usos ru
                JOIN cobros c ON ru.cobro_id = c.id
                LEFT JOIN cuotas cu ON c.cuota_id = cu.id
                LEFT JOIN decretos d_orig ON cu.decreto_id = d_orig.id
                LEFT JOIN convenio_solicitudes csol ON c.convenio_solicitud_id = csol.id
                LEFT JOIN convenios conv ON csol.convenio_id = conv.id
                WHERE ru.destino_tipo != 'fin_original'
                  AND ru.obra_id IS NULL AND ru.decreto_destino_id IS NULL AND ru.destino_detalle = ?
            ''', (obra_nombre,))
            for r in cursor.fetchall():
                d = dict(r)
                if d['saldo'] > 0.01:
                    rows_deudora.append(d)

    # 3. Formatear ambas listas con el esquema esperado por la UI y Excel
    def _format_rows(desvios_list):
        formatted = []
        with db.db_session() as conn:
            cursor = conn.cursor()
            for d in desvios_list:
                try:
                    raw_dt = datetime.datetime.strptime(str(d['fecha']), '%Y-%m-%d').date() if isinstance(d['fecha'], str) else d['fecha']
                except Exception:
                    raw_dt = d['fecha']
                
                # Calcular Estado
                if d['tipo'] == 'Inicial':
                    cursor.execute("SELECT SUM(monto) FROM cobro_desvios_recuperos WHERE desvio_id = ? AND destino_tipo = 'compensacion'", (d['desvio_id'],))
                else:
                    cursor.execute("SELECT SUM(monto) FROM cobro_reserva_usos_recuperos WHERE reserva_uso_id = ? AND destino_tipo = 'compensacion'", (d['desvio_id'],))
                res = cursor.fetchone()
                total_comp = res[0] if res and res[0] else 0.0
                
                estado = "Vigente"
                saldo = float(d['saldo'])
                monto = float(d['monto'])
                if saldo <= 0.01:
                    if total_comp >= monto - 0.01:
                        estado = "Compensado"
                    elif total_comp > 0:
                        estado = "Reint. / Comp."
                    else:
                        estado = "Reintegrado"
                elif total_comp > 0:
                    estado = "Parcialmente compensado"
                elif float(d['total_recuperado']) > 0:
                    estado = "Parcialmente reintegrado"

                formatted.append({
                    'Fecha':            utils.format_date_ar(d['fecha']),
                    'raw_date':         raw_dt,
                    'Contraparte':      d['contraparte_nombre'],
                    'Exp. IMUH':        d['contraparte_imuh'],
                    'Decreto':          d['contraparte_dec'],
                    'Monto Original':   d['monto'],
                    'Reintegrado':      d['total_recuperado'],
                    'Saldo Pendiente':  d['saldo'],
                    'Estado':           estado,
                    'N° de OP':         d['nro_op'] or 'Sin asignar',
                    'Tipo':             d['tipo'],
                    'Motivo/Notas':     d['motivo'] or '',
                    'desvio_id':        d['desvio_id'],
                })
        # Ordenar por fecha decreciente
        formatted.sort(key=lambda x: x['raw_date'] if x['raw_date'] else datetime.date.min, reverse=True)
        return formatted

    return _format_rows(rows_acreedora), _format_rows(rows_deudora)


def generar_excel_estado_deudas(obra, rows_acreedora, rows_deudora):
    """Genera un Excel con dos hojas: 'Acreedora' y 'Deudora' para la obra seleccionada."""
    excel_buffer = io.BytesIO()
    with pd.ExcelWriter(excel_buffer, engine='xlsxwriter') as writer:
        workbook  = writer.book
        bold      = workbook.add_format({'bold': True})
        money_fmt = workbook.add_format({'num_format': '#,##0.00'})

        def _write_sheet(sheet_name, titulo, rows):
            ws = workbook.add_worksheet(sheet_name)
            writer.sheets[sheet_name] = ws
            ws.write(0, 0, titulo, bold)
            ws.write(2, 0, 'Obra:', bold)
            ws.write(2, 1, obra.get('nombre', 'N/A'))
            ws.write(3, 0, 'Expediente IMUH:', bold)
            ws.write(3, 1, obra.get('expediente_imuh') or 'Sin asignar')

            headers = ['Fecha', 'Contraparte', 'Exp. IMUH', 'Decreto',
                       'Monto Original', 'Reintegrado', 'Saldo Pendiente', 'N° de OP', 'Tipo', 'Motivo/Notas']
            for col, h in enumerate(headers):
                ws.write(5, col, h, bold)
            for row_i, r in enumerate(rows):
                ws.write(6 + row_i, 0, r['Fecha'])
                ws.write(6 + row_i, 1, r['Contraparte'])
                ws.write(6 + row_i, 2, r['Exp. IMUH'])
                ws.write(6 + row_i, 3, r['Decreto'])
                ws.write(6 + row_i, 4, r['Monto Original'], money_fmt)
                ws.write(6 + row_i, 5, r['Reintegrado'],    money_fmt)
                ws.write(6 + row_i, 6, r['Saldo Pendiente'], money_fmt)
                ws.write(6 + row_i, 7, r['N° de OP'])
                ws.write(6 + row_i, 8, r['Tipo'])
                ws.write(6 + row_i, 9, r['Motivo/Notas'])
            tot_row = 6 + len(rows)
            ws.write(tot_row, 0, 'TOTAL', bold)
            total_val = sum(r['Saldo Pendiente'] for r in rows)
            ws.write(tot_row, 6, total_val, money_fmt)

        _write_sheet('Acreedora (Le deben)', 'DEUDAS A FAVOR DE LA OBRA (ACREEDOR)', rows_acreedora)
        _write_sheet('Deudora (Debe devolver)', 'DEUDAS DE LA OBRA (DEUDOR)', rows_deudora)

    return excel_buffer.getvalue()


def generar_pdf_estado_deudas(obra, rows_acreedora, rows_deudora):
    """Genera un PDF con dos secciones para la obra seleccionada."""
    import re
    safe_name = re.sub(r'[^\w\-_]', '_', obra.get('nombre', 'obra'))
    temp_path = os.path.join(
        tempfile.gettempdir(),
        f"Estado_Deudas_{safe_name}_{datetime.date.today().strftime('%Y%m%d')}.pdf"
    )

    def _build_section_df(rows, contraparte_header):
        if not rows:
            return pd.DataFrame()
        df = pd.DataFrame(rows)
        out = pd.DataFrame()
        out['Fecha']         = df['Fecha']
        out[contraparte_header] = df['Contraparte']
        out['Exp. IMUH']     = df['Exp. IMUH']
        out['Decreto']       = df['Decreto']
        out['Monto Orig.']   = df['Monto Original'].apply(lambda x: utils.format_currency_ar(x, include_symbol=False))
        out['Reintegrado']   = df['Reintegrado'].apply(lambda x: utils.format_currency_ar(x, include_symbol=False))
        out['Saldo Pend.']   = df['Saldo Pendiente'].apply(lambda x: utils.format_currency_ar(x, include_symbol=False))
        out['N° OP']         = df['N° de OP']
        total = df['Saldo Pendiente'].sum()
        out.loc[len(out)] = ['TOTAL', '', '', '', '', '', utils.format_currency_ar(total, include_symbol=False), '']
        return out

    df_acr = _build_section_df(rows_acreedora, 'Deudor (debe a esta obra)')
    df_deu = _build_section_df(rows_deudora,   'Acreedor (le prestó a esta obra)')

    col_widths = [18, 48, 22, 22, 22, 22, 22, 20]
    obra_info  = {
        'destino_fondos':      obra.get('nombre', 'N/A'),
        'expediente_imuh':     obra.get('expediente_imuh') or 'Sin asignar',
        'decreto_identificacion': obra.get('decreto_identificacion', 'N/A'),
    }

    # Reusar la función generar_reporte_desvios_pdf dos veces (acreedora primero)
    from pdf_generator import FPDF
    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.alias_nb_pages()
    pdf.set_font('Arial', 'B', 14)
    pdf.add_page()
    pdf.cell(0, 10, 'Estado de Deudas por Obra', 0, 1, 'C')
    pdf.set_font('Arial', '', 11)
    pdf.cell(0, 7, f"Obra: {obra.get('nombre','')}", 0, 1)
    pdf.cell(0, 7, f"IMUH: {obra.get('expediente_imuh') or 'Sin asignar'}", 0, 1)
    pdf.ln(4)

    def _write_section(title, df_sec):
        pdf.set_font('Arial', 'B', 12)
        pdf.set_fill_color(220, 235, 255)
        pdf.cell(0, 8, title, 0, 1, 'L', fill=True)
        pdf.ln(2)
        if df_sec.empty:
            pdf.set_font('Arial', 'I', 10)
            pdf.cell(0, 7, 'Sin registros.', 0, 1)
        else:
            pdf.set_font('Arial', 'B', 9)
            col_w = [18, 46, 22, 20, 20, 20, 22, 20]
            for i, col in enumerate(df_sec.columns):
                pdf.cell(col_w[i] if i < len(col_w) else 20, 7, str(col)[:20], 1, 0, 'C')
            pdf.ln()
            pdf.set_font('Arial', '', 8)
            for _, row in df_sec.iterrows():
                for i, val in enumerate(row):
                    w = col_w[i] if i < len(col_w) else 20
                    pdf.cell(w, 6, str(val)[:28], 1, 0, 'L')
                pdf.ln()
        pdf.ln(6)

    _write_section('1. Le deben a esta obra (Acreedora)', df_acr)
    _write_section('2. Esta obra debe devolver (Deudora)', df_deu)

    pdf.output(temp_path)
    with open(temp_path, 'rb') as f:
        pdf_data = f.read()
    try:
        os.remove(temp_path)
    except OSError:
        pass
    return pdf_data

def obtener_vista_estado_financiero():

    """Obtiene datos formateados para mostrar la vista previa del Estado Financiero en pantalla."""
    # 1. Préstamos Vigentes (Desvíos a Recuperar)
    deudas = []
    tot_d = 0
    desvios_activos = db.get_desvios_activos_completos()
    for d in (desvios_activos or []):
        origen_str = f"Dto. {d['orig_nro']}/{d['orig_anio']} - {d['orig_nombre']}"
        if d['decreto_destino_id']:
            destino_str = f"Dto. {d['dest_nro']}/{d['dest_anio']} - {utils.limpiar_prefijo_expediente(d['dest_nombre'])}"
        elif d.get('gasto_nombre'):
            destino_str = f"FUN: {d['gasto_nombre']} (Exp: {d['gasto_expediente_imuh']})"
        else:
            destino_str = utils.limpiar_prefijo_expediente(d['destino_texto'])
            
        tipo_str = "D (Desvío Decreto)"
        if d.get('gasto_nombre'):
            tipo_str = "FUN (Gasto Func.)"
            
        deudas.append({
            "Origen": origen_str,
            "Destino": destino_str,
            "Tipo": tipo_str,
            "Saldo Pendiente": d['saldo'],
            "Observaciones": ""
        })
        tot_d += d['saldo']

    prestamos_legacy = db.get_prestamos()
    for p in (prestamos_legacy or []):
        s_p = p['monto'] - p.get('total_devuelto', 0)
        if s_p > 0.01:
            deudas.append({
                "Origen": f"Dto. {p['nro_decreto']}/{p['decreto_anio']}",
                "Destino": utils.limpiar_prefijo_expediente(p['destino']),
                "Tipo": "L (Legacy)",
                "Saldo Pendiente": s_p,
                "Observaciones": p.get('motivo', '') or ""
            })
            tot_d += s_p

    reserva_prestamos = db.get_reserva_usos_prestamos_activos()
    for rp in (reserva_prestamos or []):
        origen_str = f"Dto. {rp['orig_nro']}/{rp['orig_anio']} - {rp['orig_nombre']}"
        if rp['decreto_destino_id']:
            destino_str = f"Dto. {rp['dest_nro']}/{rp['dest_anio']} - {utils.limpiar_prefijo_expediente(rp['dest_nombre'])}"
        elif rp.get('gasto_nombre'):
            destino_str = f"FUN: {rp['gasto_nombre']} (Exp: {rp['gasto_expediente_imuh']})"
        else:
            destino_str = utils.limpiar_prefijo_expediente(rp['destino_detalle']) or "Obra sin decreto"
            
        tipo_str = "R (Reserva)"
        if rp.get('gasto_nombre'):
            tipo_str = "FUN (Uso Reserva)"
            
        deudas.append({
            "Origen": origen_str,
            "Destino": destino_str,
            "Tipo": tipo_str,
            "Saldo Pendiente": rp['saldo'],
            "Observaciones": rp.get('notas', '') or ""
        })
        tot_d += rp['saldo']

    # 2. Dinero en Reserva Disponible
    reservas = []
    tot_r = 0
    cobros_dist = db.get_cobros_con_resumen_distribucion()
    for c in (cobros_dist or []):
        if c['monto_reserva'] > 0:
            usos = db.get_reserva_usos_by_cobro(c['id'])
            tot_usado = sum(u['monto'] for u in usos) if usos else 0
            saldo_r = c['monto_reserva'] - tot_usado
            if saldo_r > 0.01:
                reservas.append({
                    "Decreto / Obra": f"Dto. {c['nro_decreto']}/{c['decreto_anio']} - {c['destino_fondos']}",
                    "Fecha Cobro": utils.format_date_ar(c['fecha']),
                    "Saldo Reserva": saldo_r
                })
                tot_r += saldo_r

    return deudas, tot_d, reservas, tot_r

def obtener_vista_pedidos_financiamiento():
    """Obtiene datos formateados para mostrar la vista previa de Pedidos de Financiamiento en pantalla."""
    solicitudes = db.get_solicitudes()
    filas = []
    tot_solicitado = 0
    tot_aprobado = 0
    tot_pendiente = 0
    
    for s in (solicitudes or []):
        monto = s['monto_solicitado']
        tot_solicitado += monto
        if s['estado'] == 'Aprobado':
            tot_aprobado += monto
        elif s['estado'] == 'Pendiente':
            tot_pendiente += monto
            
        fecha_str = s['fecha_solicitud']
        if isinstance(fecha_str, str):
            try:
                dt = datetime.datetime.strptime(fecha_str, '%Y-%m-%d').date()
                fecha_str = dt.strftime("%d-%m-%Y")
            except:
                pass
                
        estado_val = s['estado']
        if s['estado'] == 'Aprobado' and s.get('nro_decreto'):
            estado_val = f"Dto. {s['nro_decreto']}/{s['decreto_anio']}"
            
        filas.append({
            "Expediente": s['nro_expediente'],
            "Destino / Obra": s['destino_fondos'],
            "Fecha": fecha_str,
            "Estado": estado_val,
            "Monto": monto
        })
        
    return filas, tot_solicitado, tot_aprobado, tot_pendiente

# Registro Centralizado de Reportes (Requisito B, C y D)
REPORTE_REGISTRY = {
    "estado_financiero": {
        "nombre": "📊 Reporte de Estado Financiero General",
        "descripcion": "Muestra un informe consolidado del estado de todos los decretos cargados, sus cuotas asignadas, los importes cobrados a la fecha, los desvíos realizados y los saldos pendientes.",
        "tipo": "PDF",
        "tiene_filtros": False,
        "generar_func": lambda: (generar_reporte_pdf(os.path.join(tempfile.gettempdir(), f"Reporte_General_{datetime.date.today().strftime('%Y%m%d')}_{uuid.uuid4().hex[:8]}.pdf")), f"Reporte_General_{datetime.date.today().strftime('%Y%m%d')}.pdf", "application/pdf")
    },
    "pedidos_financiamiento": {
        "nombre": "📋 Reporte de Estado de Pedidos de Financiamiento",
        "descripcion": "Detalla todas las solicitudes de financiamiento registradas, incluyendo su estado actual (Pendiente, Aprobado), montos solicitados, fechas de registro y vinculaciones con decretos.",
        "tipo": "PDF",
        "tiene_filtros": False,
        "generar_func": lambda: (generar_reporte_solicitudes_pdf(os.path.join(tempfile.gettempdir(), f"Reporte_Pedidos_Financiamiento_{datetime.date.today().strftime('%Y%m%d')}_{uuid.uuid4().hex[:8]}.pdf")), f"Reporte_Pedidos_Financiamiento_{datetime.date.today().strftime('%Y%m%d')}.pdf", "application/pdf")
    },
    "composicion_fondos": {
        "nombre": "🔍 Reporte de Composición de Fondos de Cuota",
        "descripcion": "Presenta el desglose del destino y los movimientos de una cuota de decreto específica: montos en obra original, fondos en reserva, desvíos realizados hacia otras obras y saldos aún sin distribuir.",
        "tipo": "Ambos",
        "tiene_filtros": True
    },
    "estado_deudas_obra": {
        "nombre": "⚖️ Estado de Deudas por Obra",
        "descripcion": "Muestra, para la obra seleccionada, los desvíos que recibió de otras obras (deudas que debe devolver) y los desvíos que otorgó a otras obras (saldos que le deben). Incluye obras del catálogo y destinos históricos legacy.",
        "tipo": "Ambos",
        "tiene_filtros": True
    },
    "afectacion_decretos": {
        "nombre": "📑 Afectación de Decretos",
        "descripcion": "Consolida los cobros y la afectación (distribución) para cada una de las cuotas de un decreto seleccionado.",
        "tipo": "Ambos",
        "tiene_filtros": True
    },
    "gastos_financiados_aportes_obra": {
        "nombre": "💼 Gastos de funcionamiento financiados con aportes de obra",
        "descripcion": "Detalla todos los gastos de funcionamiento que han sido financiados con fondos destinados originalmente a obras y que aún no han sido devueltos a las obras acreedoras.",
        "tipo": "Ambos",
        "tiene_filtros": True
    }
}

def generar_resumen_narrativo_decreto(dec, filas_reporte, total_decreto, pendiente_cobro):
    total_percibido = sum(r['Importe percibido'] for r in filas_reporte if r['Importe pagado'] == 0.0 or r == next(iter([f for f in filas_reporte if f['Nro. Cuota'] == r['Nro. Cuota']]), None))
    
    obra_original = 0.0
    reserva = 0.0
    desvios_netos = 0.0
    desvios_ini = 0.0
    recuperado = 0.0
    compensado = 0.0
    sin_distribuir = 0.0
    
    for r in filas_reporte:
        destino = r["Obra destino"]
        monto = r["Importe pagado"]
        obs = str(r["Observaciones/aclaraciones"]).lower()
        
        if destino == "Obra original":
            if "compensado" in obs or "compensación" in obs:
                compensado += monto
            else:
                obra_original += monto
        elif destino == "Sin distribuir":
            sin_distribuir += monto
        elif destino == "Reserva":
            reserva += monto
        elif "desvío" in str(r.get("Movimiento", "")).lower() or "desvio" in str(r.get("Movimiento", "")).lower():
            desvios_netos += monto
            
    with db.db_session() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT SUM(cd.monto) FROM cobro_desvios cd
            JOIN cobros c ON cd.cobro_id = c.id
            JOIN cuotas q ON c.cuota_id = q.id
            WHERE q.decreto_id = ?
        ''', (dec['id'],))
        row = cursor.fetchone()
        desvios_ini = row[0] if row and row[0] else 0.0
        
        cursor.execute('''
            SELECT SUM(r.monto) FROM cobro_desvios_recuperos r
            JOIN cobro_desvios cd ON r.desvio_id = cd.id
            JOIN cobros c ON cd.cobro_id = c.id
            JOIN cuotas q ON c.cuota_id = q.id
            WHERE q.decreto_id = ?
        ''', (dec['id'],))
        row = cursor.fetchone()
        recuperado_desv = row[0] if row and row[0] else 0.0

        cursor.execute('''
            SELECT SUM(r.monto) FROM cobro_reserva_usos_recuperos r
            JOIN cobro_reserva_usos ru ON r.reserva_uso_id = ru.id
            JOIN cobros c ON ru.cobro_id = c.id
            JOIN cuotas q ON c.cuota_id = q.id
            WHERE q.decreto_id = ?
        ''', (dec['id'],))
        row = cursor.fetchone()
        recuperado_res = row[0] if row and row[0] else 0.0

        recuperado = recuperado_desv + recuperado_res
        
        cursor.execute('''
            SELECT SUM(r.monto) FROM cobro_desvios_recuperos r
            JOIN cobro_desvios cd ON r.desvio_id = cd.id
            JOIN cobros c ON cd.cobro_id = c.id
            JOIN cuotas q ON c.cuota_id = q.id
            WHERE q.decreto_id = ? AND r.destino_tipo = 'compensacion'
        ''', (dec['id'],))
        row = cursor.fetchone()
        compensado_desv = row[0] if row and row[0] else 0.0

        cursor.execute('''
            SELECT SUM(r.monto) FROM cobro_reserva_usos_recuperos r
            JOIN cobro_reserva_usos ru ON r.reserva_uso_id = ru.id
            JOIN cobros c ON ru.cobro_id = c.id
            JOIN cuotas q ON c.cuota_id = q.id
            WHERE q.decreto_id = ? AND r.destino_tipo = 'compensacion'
        ''', (dec['id'],))
        row = cursor.fetchone()
        compensado_res = row[0] if row and row[0] else 0.0

        compensado = compensado_desv + compensado_res
    
    desvios_netos = desvios_ini - recuperado
    
    total_decreto_fmt = utils.format_currency_ar(total_decreto)
    percibido_fmt = utils.format_currency_ar(total_percibido)
    pendiente_fmt = utils.format_currency_ar(max(0.0, pendiente_cobro))
    obra_original_fmt = utils.format_currency_ar(obra_original + compensado)
    reserva_fmt = utils.format_currency_ar(reserva)
    desvios_netos_fmt = utils.format_currency_ar(desvios_netos)
    compensado_fmt = utils.format_currency_ar(compensado)
    sin_distribuir_fmt = utils.format_currency_ar(sin_distribuir)

    # Construcción de la historia cronológica por cuota
    narrativa_list = []
    
    def obtener_contraparte_compensacion(cursor, grupo_id, current_dec_id):
        cursor.execute('''
            SELECT r.monto, r.fecha as rec_fecha,
                   d.monto as desvio_monto, d.fecha as desvio_fecha, d.destino as desvio_destino,
                   COALESCE(dec.nro_decreto, conv.nro_convenio) as nro_decreto,
                   COALESCE(dec.anio, strftime('%Y', conv.fecha_firma)) as dec_anio,
                   COALESCE(dec.id, conv.id) as dec_id
            FROM cobro_desvios_recuperos r
            JOIN cobro_desvios d ON r.desvio_id = d.id
            JOIN cobros c ON d.cobro_id = c.id
            LEFT JOIN cuotas q ON c.cuota_id = q.id
            LEFT JOIN decretos dec ON q.decreto_id = dec.id
            LEFT JOIN convenio_solicitudes csol ON c.convenio_solicitud_id = csol.id
            LEFT JOIN convenios conv ON (c.convenio_id = conv.id OR csol.convenio_id = conv.id)
            WHERE r.grupo_compensacion_id = ?
        ''', (grupo_id,))
        desvios = [dict(row) for row in cursor.fetchall()]
        
        cursor.execute('''
            SELECT r.monto, r.fecha as rec_fecha,
                   u.monto as uso_monto, u.fecha as uso_fecha, u.destino_detalle as uso_destino,
                   COALESCE(dec.nro_decreto, conv.nro_convenio) as nro_decreto,
                   COALESCE(dec.anio, strftime('%Y', conv.fecha_firma)) as dec_anio,
                   COALESCE(dec.id, conv.id) as dec_id
            FROM cobro_reserva_usos_recuperos r
            JOIN cobro_reserva_usos u ON r.reserva_uso_id = u.id
            JOIN cobros c ON u.cobro_id = c.id
            LEFT JOIN cuotas q ON c.cuota_id = q.id
            LEFT JOIN decretos dec ON q.decreto_id = dec.id
            LEFT JOIN convenio_solicitudes csol ON c.convenio_solicitud_id = csol.id
            LEFT JOIN convenios conv ON (c.convenio_id = conv.id OR csol.convenio_id = conv.id)
            WHERE r.grupo_compensacion_id = ?
        ''', (grupo_id,))
        reserves = [dict(row) for row in cursor.fetchall()]
        
        for d in desvios:
            if d['dec_id'] != current_dec_id:
                return {
                    'tipo': 'desvio',
                    'monto_original': d['desvio_monto'],
                    'fecha_original': d['desvio_fecha'],
                    'nro_decreto': d['nro_decreto'],
                    'anio': d['dec_anio']
                }
        for r in reserves:
            if r['dec_id'] != current_dec_id:
                return {
                    'tipo': 'reserva',
                    'monto_original': r['uso_monto'],
                    'fecha_original': r['uso_fecha'],
                    'nro_decreto': r['nro_decreto'],
                    'anio': r['dec_anio']
                }
        return None

    with db.db_session() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM cuotas WHERE decreto_id = ? ORDER BY anio ASC, mes ASC', (dec['id'],))
        cuotas = [dict(row) for row in cursor.fetchall()]
        
        for idx, q in enumerate(cuotas):
            seq_num = idx + 1
            cursor.execute('SELECT * FROM cobros WHERE cuota_id = ? ORDER BY fecha ASC', (q['id'],))
            cobros = [dict(row) for row in cursor.fetchall()]
            
            cuota_header = f'*   **Cuota {seq_num} (Presupuesto: {total_decreto_fmt if len(cuotas) == 1 else utils.format_currency_ar(q["monto"])})**:'
            
            if not cobros:
                narrativa_list.append(f'{cuota_header}\n    *   Sin cobros registrados a la fecha.')
                continue
                
            events = []
            for cb_idx, cb in enumerate(cobros):
                is_last_cobro = (cb_idx == len(cobros) - 1)
                is_partial = len(cobros) > 1 and not is_last_cobro
                
                events.append({
                    'fecha': cb['fecha'],
                    'tipo': 'cobro',
                    'monto': cb['monto'],
                    'is_partial': is_partial,
                    'is_last': is_last_cobro and len(cobros) > 1
                })
                
                # Fin original usos
                cursor.execute('SELECT * FROM cobro_fin_original_usos WHERE cobro_id = ?', (cb['id'],))
                for u in cursor.fetchall():
                    events.append({
                        'fecha': u['fecha'],
                        'tipo': 'pago_original',
                        'monto': u['monto']
                    })
                    
                # Desvios
                cursor.execute('''
                    SELECT cd.*, o.nombre as obra_nombre, o.expediente_imuh as obra_exp_imuh
                    FROM cobro_desvios cd
                    LEFT JOIN obras o ON cd.obra_id = o.id
                    WHERE cd.cobro_id = ?
                ''', (cb['id'],))
                desvios = [dict(row) for row in cursor.fetchall()]
                for d in desvios:
                    if d.get('obra_nombre'):
                        dest_desc = f"{d['obra_nombre']} (Exp. IMUH {d['obra_exp_imuh']})"
                    else:
                        dest_desc = d['destino']
                    events.append({
                        'fecha': d['fecha'],
                        'tipo': 'transferencia_desvio',
                        'monto': d['monto'],
                        'destino': dest_desc,
                        'desvio_id': d['id']
                    })
                    
                    # Recuperos de desvio
                    cursor.execute('SELECT * FROM cobro_desvios_recuperos WHERE desvio_id = ?', (d['id'],))
                    for r in cursor.fetchall():
                        events.append({
                            'fecha': r['fecha'],
                            'tipo': 'recupero_desvio',
                            'monto': r['monto'],
                            'destino_tipo': r['destino_tipo'],
                            'destino_detalle': r['destino_detalle'],
                            'grupo_id': r['grupo_compensacion_id'],
                            'orig_fecha': d['fecha'],
                            'orig_monto': d['monto'],
                            'orig_destino': dest_desc
                        })
                        
                # Reserva usos
                cursor.execute('''
                    SELECT ru.*, o.nombre as obra_nombre, o.expediente_imuh as obra_exp_imuh
                    FROM cobro_reserva_usos ru
                    LEFT JOIN obras o ON ru.obra_id = o.id
                    WHERE ru.cobro_id = ?
                ''', (cb['id'],))
                reserva_usos = [dict(row) for row in cursor.fetchall()]
                for ru in reserva_usos:
                    if ru.get('obra_nombre'):
                        dest_desc = f"{ru['obra_nombre']} (Exp. IMUH {ru['obra_exp_imuh']})"
                    else:
                        dest_desc = ru['destino_detalle'] or 'Otra obra'
                    events.append({
                        'fecha': ru['fecha'],
                        'tipo': 'reserva_uso',
                        'monto': ru['monto'],
                        'destino_tipo': ru['destino_tipo'],
                        'destino_detalle': dest_desc,
                        'uso_id': ru['id']
                    })
                    
                    # Recuperos de reserva
                    cursor.execute('SELECT * FROM cobro_reserva_usos_recuperos WHERE reserva_uso_id = ?', (ru['id'],))
                    for r in cursor.fetchall():
                        events.append({
                            'fecha': r['fecha'],
                            'tipo': 'recupero_reserva_uso',
                            'monto': r['monto'],
                            'destino_tipo': r['destino_tipo'],
                            'destino_detalle': r['destino_detalle'],
                            'grupo_id': r['grupo_compensacion_id'],
                            'orig_fecha': ru['fecha'],
                            'orig_monto': ru['monto'],
                            'orig_destino': dest_desc
                        })

            # Sort events
            def get_event_sort_key(ev):
                type_priority = {
                    'cobro': 0,
                    'pago_original': 1,
                    'transferencia_desvio': 2,
                    'reserva_uso': 2,
                    'recupero_desvio': 3,
                    'recupero_reserva_uso': 3
                }
                return (ev['fecha'], type_priority.get(ev['tipo'], 9))
                
            events.sort(key=get_event_sort_key)
            
            # Process/group events by date
            grouped_by_date = {}
            for ev in events:
                d_str = ev['fecha']
                if d_str not in grouped_by_date:
                    grouped_by_date[d_str] = []
                grouped_by_date[d_str].append(ev)
                
            sorted_dates = sorted(list(grouped_by_date.keys()))
            
            cuota_lines = [cuota_header]
            for d_str in sorted_dates:
                day_events = grouped_by_date[d_str]
                date_fmt = utils.format_date_ar(d_str)
                
                # 1. Cobros of the day
                cobros_day = [e for e in day_events if e['tipo'] == 'cobro']
                for cb in cobros_day:
                    if cb['is_partial']:
                        cuota_lines.append(f'    *   **{date_fmt} (Cobro parcial):** Se percibieron **{utils.format_currency_ar(cb["monto"])}**.')
                    elif cb['is_last']:
                        cuota_lines.append(f'    *   **{date_fmt} (Saldo de cuota):** Se percibieron **{utils.format_currency_ar(cb["monto"])}** (completando los cobros de esta cuota).')
                    else:
                        cuota_lines.append(f'    *   **{date_fmt} (Cobro):** Se percibieron **{utils.format_currency_ar(cb["monto"])}**.')
                        
                # 2. Pagos a obra original (direct + reserve use to fin_original)
                pagos_orig_monto = 0.0
                for e in day_events:
                    if e['tipo'] == 'pago_original':
                        pagos_orig_monto += e['monto']
                    elif e['tipo'] == 'reserva_uso' and e['destino_tipo'] == 'fin_original':
                        pagos_orig_monto += e['monto']
                        
                if pagos_orig_monto > 0.01:
                    cuota_lines.append(f'    *   **{date_fmt} (Pago):** Se efectuó un pago a la obra original por **{utils.format_currency_ar(pagos_orig_monto)}**.')
                    
                # 3. Transferencias temporarias
                transf_monto = 0.0
                transf_destinos = []
                for e in day_events:
                    if e['tipo'] == 'transferencia_desvio':
                        transf_monto += e['monto']
                        transf_destinos.append(e['destino'])
                    elif e['tipo'] == 'reserva_uso' and e['destino_tipo'] != 'fin_original':
                        transf_monto += e['monto']
                        transf_destinos.append(e['destino_detalle'] or 'Otra obra')
                        
                if transf_monto > 0.01:
                    dest_uniq = []
                    for dest in transf_destinos:
                        clean_dest = clean_destino_name(dest)
                        if clean_dest not in dest_uniq:
                            dest_uniq.append(clean_dest)
                    dest_str = ', '.join(dest_uniq)
                    cuota_lines.append(f'    *   **{date_fmt} (Transferencia):** Se realizaron transferencias temporarias a otras obras por un total de **{utils.format_currency_ar(transf_monto)}** (distribuidos en: *{dest_str}*).')
                    
                # 4. Recuperos
                rec_events = [e for e in day_events if e['tipo'] in ('recupero_desvio', 'recupero_reserva_uso')]
                for r in rec_events:
                    orig_dest_clean = clean_destino_name(r['orig_destino'])
                    if r['destino_tipo'] == 'compensacion' and r['grupo_id']:
                        contra = obtener_contraparte_compensacion(cursor, r['grupo_id'], dec['id'])
                        if contra:
                            contra_dec = f"Decreto {contra['nro_decreto']}/{contra['anio']}"
                            contra_orig_fecha = utils.format_date_ar(contra['fecha_original'])
                            contra_orig_monto = utils.format_currency_ar(contra['monto_original'])
                            cuota_lines.append(
                                f'    *   **{date_fmt} (Compensación):** Se aplicaron **{utils.format_currency_ar(r["monto"])}** a la obra original, '
                                f'compensados mediante saldos cruzados con el *{contra_dec}* (fondos originalmente recibidos el **{contra_orig_fecha}**). '
                                f'La compensación formal se concretó el **{utils.format_date_ar(r["fecha"])}** tras registrarse una transferencia temporaria de fondos '
                                f'a favor del *{contra_dec}* realizada el **{utils.format_date_ar(r["orig_fecha"])}** (por un monto original de **{utils.format_currency_ar(r["orig_monto"])}**).'
                            )
                        else:
                            cuota_lines.append(
                                f'    *   **{date_fmt} (Compensación):** Se reintegraron **{utils.format_currency_ar(r["monto"])}** de la transferencia realizada el '
                                f'**{utils.format_date_ar(r["orig_fecha"])}** (originalmente de **{utils.format_currency_ar(r["orig_monto"])}**) a la obra *{orig_dest_clean}*, '
                                f'mediante compensación de saldos.'
                            )
                    else:
                        dest_txt = 'a la reserva' if r['destino_tipo'] == 'reserva' else ('a la obra original' if r['destino_tipo'] == 'fin_original' else 'a caja líquida sin distribuir')
                        cuota_lines.append(
                            f'    *   **{date_fmt} (Recupero):** Se recuperaron **{utils.format_currency_ar(r["monto"])}** de la transferencia realizada el '
                            f'**{utils.format_date_ar(r["orig_fecha"])}** (originalmente de **{utils.format_currency_ar(r["orig_monto"])}**) al destino *{orig_dest_clean}*, devueltos {dest_txt}.'
                        )
                        
            narrativa_list.append('\n'.join(cuota_lines))

    narrativa_text = '\n\n'.join(narrativa_list)

    resumen = (
        f"El **Decreto {dec['nro_decreto']}/{dec['anio']}** (Destinado a *{dec['destino_fondos']}*) "
        f"tiene un presupuesto pautado de **{total_decreto_fmt}**, "
        f"habiéndose cobrado a la fecha **{percibido_fmt}** (quedando **{pendiente_fmt}** pendiente de cobro).\n\n"
        f"**Historial de Flujo de Fondos:**\n\n"
        f"{narrativa_text}\n\n"
        f"**Estado Actual de Saldos Consolidados:**\n"
        f"- **Obra Original (Invertido/Pagado):** **{obra_original_fmt}**"
    )
    if compensado > 0.01:
        resumen += f" (de los cuales **{compensado_fmt}** provienen de compensación de saldos con otros decretos)"
    resumen += (
        f"\n- **Reserva (Saldo neto disponible):** **{reserva_fmt}**\n"
        f"- **Transferencias temporarias activas (Pendientes de recuperar):** **{desvios_netos_fmt}**\n"
        f"- **Caja líquida (Sin distribuir):** **{sin_distribuir_fmt}**"
    )
    
    return resumen


def obtener_gastos_funcionamiento_financiados_obra():
    """Retorna un DataFrame con todos los gastos de funcionamiento financiados con aportes de obra que aún tienen saldo pendiente."""
    with db.db_session() as conn:
        cursor = conn.cursor()
        
        # 1. Desvíos iniciales
        cursor.execute('''
            SELECT 
                cd.fecha AS fecha_desvio,
                cd.gasto_expediente_imuh AS gasto_expediente_imuh,
                cd.gasto_nombre AS gasto_nombre,
                p.razon_social AS proveedor_nombre,
                COALESCE('Dto. ' || d_orig.nro_decreto || '/' || d_orig.anio, 'Conv. ' || conv.nro_convenio) AS decreto_financiador,
                COALESCE(d_orig.expediente_imuh, conv.nro_expediente) AS orig_obra_imuh,
                COALESCE(d_orig.destino_fondos, conv.nombre_convenio) AS orig_obra_nombre,
                cd.nro_op AS nro_op_bejerman,
                cd.monto AS importe_desviado,
                COALESCE((SELECT SUM(monto) FROM cobro_desvios_recuperos WHERE desvio_id = cd.id), 0) AS total_recuperado
            FROM cobro_desvios cd
            JOIN cobros c ON cd.cobro_id = c.id
            LEFT JOIN cuotas cu ON c.cuota_id = cu.id
            LEFT JOIN decretos d_orig ON cu.decreto_id = d_orig.id
            LEFT JOIN convenio_solicitudes csol ON c.convenio_solicitud_id = csol.id
            LEFT JOIN convenios conv ON csol.convenio_id = conv.id
            LEFT JOIN gastos_funcionamiento gf ON cd.gasto_expediente_imuh = gf.expediente_imuh
            LEFT JOIN proveedores_funcionamiento p ON gf.proveedor_id = p.id
            WHERE cd.gasto_expediente_imuh IS NOT NULL
        ''')
        rows1 = [dict(r) for r in cursor.fetchall()]
        
        # 2. Desvíos desde reserva
        cursor.execute('''
            SELECT 
                ru.fecha AS fecha_desvio,
                ru.gasto_expediente_imuh AS gasto_expediente_imuh,
                ru.gasto_nombre AS gasto_nombre,
                p.razon_social AS proveedor_nombre,
                COALESCE('Dto. ' || d_orig.nro_decreto || '/' || d_orig.anio, 'Conv. ' || conv.nro_convenio) AS decreto_financiador,
                COALESCE(d_orig.expediente_imuh, conv.nro_expediente) AS orig_obra_imuh,
                COALESCE(d_orig.destino_fondos, conv.nombre_convenio) AS orig_obra_nombre,
                ru.nro_op AS nro_op_bejerman,
                ru.monto AS importe_desviado,
                COALESCE((SELECT SUM(monto) FROM cobro_reserva_usos_recuperos WHERE reserva_uso_id = ru.id), 0) AS total_recuperado
            FROM cobro_reserva_usos ru
            JOIN cobros c ON ru.cobro_id = c.id
            LEFT JOIN cuotas cu ON c.cuota_id = cu.id
            LEFT JOIN decretos d_orig ON cu.decreto_id = d_orig.id
            LEFT JOIN convenio_solicitudes csol ON c.convenio_solicitud_id = csol.id
            LEFT JOIN convenios conv ON csol.convenio_id = conv.id
            LEFT JOIN gastos_funcionamiento gf ON ru.gasto_expediente_imuh = gf.expediente_imuh
            LEFT JOIN proveedores_funcionamiento p ON gf.proveedor_id = p.id
            WHERE ru.gasto_expediente_imuh IS NOT NULL
        ''')
        rows2 = [dict(r) for r in cursor.fetchall()]
        
    all_rows = rows1 + rows2
    
    # Calcular importe adeudado y filtrar
    filtrados = []
    for r in all_rows:
        importe_adeudado = r['importe_desviado'] - r['total_recuperado']
        if importe_adeudado > 0.01:
            filtrados.append({
                "Fecha del desvío": r['fecha_desvio'],
                "Expediente IMUH del gasto": r['gasto_expediente_imuh'] or 'Sin asignar',
                "Nombre del expediente del gasto": r['gasto_nombre'] or 'Sin asignar',
                "Proveedor": r['proveedor_nombre'] or 'Sin asignar',
                "Decreto financiador": r['decreto_financiador'] or 'Sin asignar',
                "Expediente IMUH de la obra financiadora": r['orig_obra_imuh'] or 'Sin asignar',
                "Nombre de la obra acreedora": r['orig_obra_nombre'] or 'Sin asignar',
                "OP Bejerman": r['nro_op_bejerman'] or 'Sin OP',
                "Importe adeudado": importe_adeudado
            })
            
    # Ordenar por fecha del desvío desc
    filtrados.sort(key=lambda x: x['Fecha del desvío'], reverse=True)
    return pd.DataFrame(filtrados)

def generar_excel_gastos_funcionamiento_financiados_obra(df):
    """Genera un reporte Excel en bytes para gastos de funcionamiento adeudados."""
    excel_buffer = io.BytesIO()
    with pd.ExcelWriter(excel_buffer, engine='xlsxwriter') as writer:
        workbook  = writer.book
        bold      = workbook.add_format({'bold': True})
        money_fmt = workbook.add_format({'num_format': '#,##0.00'})
        
        ws = workbook.add_worksheet('Gastos Financiados')
        writer.sheets['Gastos Financiados'] = ws
        
        ws.write(0, 0, 'REPORTES: GASTOS DE FUNCIONAMIENTO FINANCIADOS CON APORTES DE OBRA', bold)
        ws.write(2, 0, 'Fecha de generación:', bold)
        ws.write(2, 1, datetime.date.today().strftime('%d/%m/%Y'))
        
        headers = [
            "Fecha del desvío",
            "Expediente IMUH del gasto",
            "Nombre del expediente del gasto",
            "Proveedor",
            "Decreto financiador",
            "Expediente IMUH de la obra financiadora",
            "Nombre de la obra acreedora",
            "OP Bejerman",
            "Importe adeudado"
        ]
        
        for col_idx, h in enumerate(headers):
            ws.write(4, col_idx, h, bold)
            
        total_val = 0.0
        for row_idx, (_, row) in enumerate(df.iterrows()):
            ws.write(5 + row_idx, 0, row["Fecha del desvío"])
            ws.write(5 + row_idx, 1, row["Expediente IMUH del gasto"])
            ws.write(5 + row_idx, 2, row["Nombre del expediente del gasto"])
            ws.write(5 + row_idx, 3, row["Proveedor"])
            ws.write(5 + row_idx, 4, row["Decreto financiador"])
            ws.write(5 + row_idx, 5, row["Expediente IMUH de la obra financiadora"])
            ws.write(5 + row_idx, 6, row["Nombre de la obra acreedora"])
            ws.write(5 + row_idx, 7, row["OP Bejerman"])
            
            val = float(row["Importe adeudado"])
            ws.write(5 + row_idx, 8, val, money_fmt)
            total_val += val
            
        tot_row = 5 + len(df)
        ws.write(tot_row, 0, 'TOTAL', bold)
        ws.write(tot_row, 8, total_val, money_fmt)
        
    return excel_buffer.getvalue()

def generar_pdf_gastos_funcionamiento_financiados_obra(df):
    """Wrapper para generar el reporte PDF en bytes."""
    temp_path = os.path.join(tempfile.gettempdir(), f"temp_gf_financiados_{datetime.date.today().strftime('%Y%m%d')}_{uuid.uuid4().hex[:8]}.pdf")
    
    # Formatear montos para el PDF
    df_pdf = df.copy()
    df_pdf["Importe adeudado"] = df_pdf["Importe adeudado"].apply(utils.format_currency_ar)
    
    # Formatear fechas para el PDF
    df_pdf["Fecha del desvío"] = df_pdf["Fecha del desvío"].apply(utils.format_date_ar)
    
    generar_reporte_gastos_funcionamiento_financiados_obra_pdf(temp_path, df_pdf)
    
    with open(temp_path, 'rb') as f:
        pdf_bytes = f.read()
        
    try:
        os.remove(temp_path)
    except OSError:
        pass
        
    return pdf_bytes
