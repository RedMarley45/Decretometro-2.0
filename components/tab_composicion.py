import streamlit as st
import datetime
import database as db
import pandas as pd
import utils
from utils import _validar_op_y_notas
from database import DESTINO_RESERVA

def render_tab4():
    st.subheader("🔍 Composición e Historial de Cuotas")
    st.info("Consulte la distribución, pagos y desvíos asociados a una cuota, y realice modificaciones o correcciones de Órdenes de Pago y montos.")
    
    decretos_list_sel = db.get_decretos()
    if not decretos_list_sel:
        st.warning("No hay decretos registrados.")
    else:
        opc_dec = {d['id']: f"Dto. {d['nro_decreto']}/{d['anio']} - {d['destino_fondos']}" for d in decretos_list_sel}
        sel_dec_id = st.selectbox("Seleccione el Decreto", options=list(opc_dec.keys()), format_func=lambda x: opc_dec[x], key="composition_dec_sel")
        
        if sel_dec_id:
            cuotas_list_sel = db.get_cuotas_by_decreto(sel_dec_id)
            if not cuotas_list_sel:
                st.info("Este decreto no tiene cuotas configuradas.")
            else:
                opc_cuota = {c['id']: f"Cuota {c['mes']:02d}/{c['anio']} - Monto: {utils.format_currency_ar(c['monto'])}" for c in cuotas_list_sel}
                sel_cuota_id = st.selectbox("Seleccione la Cuota", options=list(opc_cuota.keys()), format_func=lambda x: opc_cuota[x], key="composition_cuota_sel")
                
                if sel_cuota_id:
                    # Obtener cobros de esta cuota
                    conn_c = db.get_connection()
                    cursor_c = conn_c.cursor()
                    cursor_c.execute('SELECT * FROM cobros WHERE cuota_id = ?', (sel_cuota_id,))
                    cobros_cuota = [dict(r) for r in cursor_c.fetchall()]
                    conn_c.close()
                    
                    if not cobros_cuota:
                        st.warning("Esta cuota no registra ingresos (cobros) percibidos aún.")
                    else:
                        # Compilar todos los movimientos de usos
                        movimientos = []
                        total_fo_asignado = 0.0
                        total_res_asignado = 0.0
                        total_fo_pagado = 0.0
                        total_res_usado = 0.0
                        total_desviado = 0.0
                        total_recuperado = 0.0
                        total_ingresado = sum(c['monto'] for c in cobros_cuota)
                        
                        for cb in cobros_cuota:
                            # Ingreso
                            movimientos.append({
                                "id_rel": cb['id'],
                                "tipo_rel": "cobro",
                                "fecha": cb['fecha'],
                                "tipo_str": "💰 Ingreso (Cobro)",
                                "monto": cb['monto'],
                                "nro_op": "N/A",
                                "destino": "Sin distribuir",
                                "notas": f"Ingreso bancario de la cuota. Comprobante: {'Sí' if cb['comprobante_path'] else 'No'}",
                                "raw_data": cb
                            })
                            
                            dist = db.get_distribucion_by_cobro(cb['id'])
                            if dist:
                                total_fo_asignado += dist['monto_fin_orig']
                                total_res_asignado += dist['monto_reserva']
                            
                            # Usos Fin Original
                            usos_fo = db.get_fin_original_usos_by_cobro(cb['id'])
                            for u in usos_fo:
                                total_fo_pagado += u['monto']
                                movimientos.append({
                                    "id_rel": u['id'],
                                    "tipo_rel": "fin_original_uso",
                                    "fecha": u['fecha'],
                                    "tipo_str": "🏗️ Pago Fin Original",
                                    "monto": u['monto'],
                                    "nro_op": u['nro_op'] or "",
                                    "destino": "Obra Original (Fin Original)",
                                    "notas": u['notas'] or "",
                                    "raw_data": u
                                })
                                
                            recuperos_cb = db.get_recuperos_by_cobro(cb['id'])
                            for u in recuperos_cb:
                                total_fo_pagado += u['monto']
                                movimientos.append({
                                    "id_rel": u['id'],
                                    "tipo_rel": "recupero_fondos_propios",
                                    "fecha": u['fecha'],
                                    "tipo_str": "🔙 Recupero Adelanto F.P.",
                                    "monto": u['monto'],
                                    "nro_op": u['nro_op'] or "",
                                    "destino": "Fondos Propios (Devolución)",
                                    "notas": u['notas'] or "",
                                    "raw_data": u
                                })
                                
                            # Desvíos
                            desvios = db.get_desvios_by_cobro(cb['id'])
                            for d in desvios:
                                total_desviado += d['monto']
                                movimientos.append({
                                    "id_rel": d['id'],
                                    "tipo_rel": "desvio",
                                    "fecha": d['fecha'],
                                    "tipo_str": "💸 Desvío a otra obra",
                                    "monto": d['monto'],
                                    "nro_op": d['nro_op'] or "",
                                    "destino": d['destino'],
                                    "notas": d['motivo'] or "",
                                    "raw_data": d
                                })
                                
                                # Recuperos de desvíos
                                rec_d = db.get_recuperos_by_desvio(d['id'])
                                for rd in rec_d:
                                    total_recuperado += rd['monto']
                                    dest_str = "Fin Original" if rd['destino_tipo'] == 'fin_original' else f"Obra: {rd.get('dest_nombre') or rd.get('destino_detalle', '')}"
                                    movimientos.append({
                                        "id_rel": rd['id'],
                                        "tipo_rel": "desvio_recupero",
                                        "fecha": rd['fecha'],
                                        "tipo_str": "🔄 Recupero de Desvío",
                                        "monto": rd['monto'],
                                        "nro_op": rd['nro_op'] or "",
                                        "destino": dest_str,
                                        "notas": f"Devolución del desvío a {d['destino']}",
                                        "raw_data": rd
                                    })
                                    
                            # Usos de reserva
                            usos_r = db.get_reserva_usos_by_cobro(cb['id'])
                            for ur in usos_r:
                                total_res_usado += ur['monto']
                                dest_str = "Fin Original" if ur['destino_tipo'] == 'fin_original' else f"Obra: {ur['destino_detalle']}"
                                movimientos.append({
                                    "id_rel": ur['id'],
                                    "tipo_rel": "reserva_uso",
                                    "fecha": ur['fecha'],
                                    "tipo_str": "🔒 Uso de Reserva",
                                    "monto": ur['monto'],
                                    "nro_op": ur['nro_op'] or "",
                                    "destino": dest_str,
                                    "notas": ur['notas'] or "",
                                    "raw_data": ur
                                })
                                
                                # Recuperos de uso de reserva
                                rec_ur = db.get_recuperos_by_reserva_uso(ur['id'])
                                for rur in rec_ur:
                                    total_recuperado += rur['monto']
                                    dest_rur = "Fin Original" if rur['destino_tipo'] == 'fin_original' else ("Reserva" if rur['destino_tipo'] == 'reserva' else f"Obra: {rur.get('dest_nombre') or rur.get('destino_detalle','')}")
                                    movimientos.append({
                                        "id_rel": rur['id'],
                                        "tipo_rel": "reserva_uso_recupero",
                                        "fecha": rur['fecha'],
                                        "tipo_str": "🔄 Recupero de Reserva",
                                        "monto": rur['monto'],
                                        "nro_op": rur['nro_op'] or "",
                                        "destino": dest_rur,
                                        "notas": f"Devolución del uso de reserva a {dest_str}",
                                        "raw_data": rur
                                    })
                                    
                        # Ordenar por fecha cronológicamente
                        movimientos.sort(key=lambda x: x['fecha'])
                        
                        # --- Mostrar Resumen del Estado de la Cuota ---
                        st.markdown("### 📊 Estado de Distribución y Pagos de la Cuota")
                        
                        # --- CALCULO DE COMPOSICIÓN DEL ESTADO ACTUAL ---
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
                                    "Aclaraciones": u['notas'] or ""
                                })
                                
                            recuperos_cb2 = db.get_recuperos_by_cobro(cb_id)
                            for u in recuperos_cb2:
                                sum_usos_fo += u['monto']
                                estado_actual_filas.append({
                                    "Fecha": utils.format_date_ar(u['fecha']),
                                    "Movimiento": "Recupero de Fondos Propios",
                                    "Monto": u['monto'],
                                    "Orden de Pago (OP)": u['nro_op'] or "Sin asignar",
                                    "Destino": "Fondos Propios (Devolución)",
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
                                        "Aclaraciones": u['notas'] or ""
                                    })
                                    
                            # F. Desvíos Iniciales (Activos y Recuperos Redireccionados)
                            desvios = db.get_desvios_by_cobro(cb_id)
                            for d in desvios:
                                recs = db.get_recuperos_by_desvio(d['id'])
                                sum_recs = sum(r['monto'] for r in recs)
                                d_net = d['monto'] - sum_recs
                                if d_net > 0.01:
                                    estado_actual_filas.append({
                                        "Fecha": utils.format_date_ar(d['fecha']),
                                        "Movimiento": "Desvío a otra obra",
                                        "Monto": d_net,
                                        "Orden de Pago (OP)": d['nro_op'] or "Sin asignar",
                                        "Destino": d['destino'],
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
                                
                        # Calcular totales para las tarjetas de métricas basadas en la composición
                        tot_obra_orig = sum(f["Monto"] for f in estado_actual_filas if f["Movimiento"].startswith("Fin original"))
                        tot_reserva = sum(f["Monto"] for f in estado_actual_filas if f["Movimiento"] == "En reserva")
                        tot_desvios = sum(f["Monto"] for f in estado_actual_filas if "desvío" in f["Movimiento"].lower() or "desvio" in f["Movimiento"].lower())
                        tot_sin_dist = sum(f["Monto"] for f in estado_actual_filas if f["Movimiento"] == "Sin distribuir")
                        
                        col_m1, col_m2, col_m3, col_m4, col_m5 = st.columns(5)
                        col_m1.metric("Total Percibido (Cobros)", utils.format_currency_ar(total_ingresado))
                        col_m2.metric("Obra Original", utils.format_currency_ar(tot_obra_orig))
                        col_m3.metric("Reserva (Saldo)", utils.format_currency_ar(tot_reserva))
                        col_m4.metric("Desvíos Netos Pendientes", utils.format_currency_ar(tot_desvios))
                        col_m5.metric("Sin Distribuir", utils.format_currency_ar(tot_sin_dist))
                        
                        # Renderizar Tabla de Estado Actual
                        st.markdown("### 🔍 Composición del Estado Actual de Fondos")
                        if estado_actual_filas:
                            df_actual = pd.DataFrame(estado_actual_filas)
                            sum_total_actual = df_actual['Monto'].sum()
                            
                            # Formatear la columna Monto para visualización
                            df_actual_mostrar = df_actual.copy()
                            df_actual_mostrar['Monto'] = df_actual_mostrar['Monto'].apply(lambda x: utils.format_currency_ar(x))
                            
                            st.dataframe(
                                df_actual_mostrar, 
                                use_container_width=True, 
                                hide_index=True,
                                column_config={
                                    "Destino": st.column_config.TextColumn(width="large"),
                                    "Movimiento": st.column_config.TextColumn(width="medium"),
                                    "Aclaraciones": st.column_config.TextColumn(width="large")
                                }
                            )
                            
                            # Mostrar el total abajo para verificar balance
                            col_b1, col_b2 = st.columns([4, 1])
                            col_b2.markdown(f"**Total Sumatoria:** {utils.format_currency_ar(sum_total_actual)}")
                            
                            # --- GENERACION DE REPORTES EXCEL Y PDF ---
                            st.write("")
                            st.markdown("#### 📥 Descargar Reporte de Composición")
                            
                            try:
                                # Reutilizar la lógica centralizada de utils_reports
                                from utils_reports import obtener_datos_composicion, generar_excel_composicion, generar_pdf_composicion
                                
                                _, _, _, cuota_seq_num, fechas_str, aclaraciones_str, cuota_sel_dict = obtener_datos_composicion(sel_dec_id, sel_cuota_id)
                                dec = db.get_decreto(sel_dec_id)
                                
                                df_export = pd.DataFrame()
                                df_export["Fecha"] = df_actual["Fecha"]
                                df_export["Destino"] = df_actual["Destino"]
                                df_export["OP"] = df_actual["Orden de Pago (OP)"]
                                df_export["Aclaraciones"] = df_actual["Aclaraciones"]
                                df_export["Monto"] = df_actual["Monto"]
                                
                                excel_data = generar_excel_composicion(dec, cuota_sel_dict, cuota_seq_num, fechas_str, aclaraciones_str, df_export)
                                pdf_data = generar_pdf_composicion(dec, cuota_sel_dict, cuota_seq_num, fechas_str, aclaraciones_str, sum_total_actual, df_export)
                                
                                col_dl1, col_dl2 = st.columns(2)
                                
                                col_dl1.download_button(
                                    label="📊 Exportar Composición a Excel",
                                    data=excel_data,
                                    file_name=f"Composicion_{dec['nro_decreto']}_{dec['anio']}_Cuota_{cuota_seq_num}.xlsx",
                                    mime="application/vnd.ms-excel",
                                    use_container_width=True
                                )
                                
                                col_dl2.download_button(
                                    label="📄 Exportar Composición a PDF",
                                    data=pdf_data,
                                    file_name=f"Composicion_{dec['nro_decreto']}_{dec['anio']}_Cuota_{cuota_seq_num}.pdf",
                                    mime="application/pdf",
                                    use_container_width=True
                                )
                            except Exception as e:
                                st.error(f"Error generando descargas: {e}")
                            
                            # Alerta en caso de diferencia (tolerancia centavos)
                            if abs(sum_total_actual - total_ingresado) > 0.05:
                                st.warning(f"⚠️ Atención: Hay una discrepancia de {utils.format_currency_ar(abs(sum_total_actual - total_ingresado))} entre la sumatoria de composición y el total percibido.")
                        else:
                            st.info("No hay datos de distribución disponibles.")
                        st.write("")
                        
                        # --- Mostrar Tabla de Historial ---
                        st.markdown("### 🗓️ Historial Completo de Movimientos")
                        
                        df_movs = pd.DataFrame([{
                            "Fecha": utils.format_date_ar(m['fecha']),
                            "Movimiento": m['tipo_str'],
                            "Monto": utils.format_currency_ar(m['monto']),
                            "Orden de Pago (OP)": m['nro_op'],
                            "Destino / Origen": m['destino'],
                            "Notas": m['notas']
                        } for m in movimientos])
                        
                        st.dataframe(df_movs, use_container_width=True, hide_index=True)
                        
                        # --- Formulario de Edición de Movimientos ---
                        st.markdown("---")
                        st.markdown("### 📝 Modificar un Movimiento / Completar OP")
                        
                        # Filtrar solo movimientos que se pueden editar (excluir cobros directos)
                        editables = [m for m in movimientos if m['tipo_rel'] != 'cobro']
                        
                        if not editables:
                            st.info("No hay pagos, desvíos o recuperos registrados que se puedan modificar.")
                        else:
                            opc_edit = {f"{m['tipo_rel']}_{m['id_rel']}": f"{m['tipo_str']} - {utils.format_date_ar(m['fecha'])} - {utils.format_currency_ar(m['monto'])} (OP: {m['nro_op'] or 'Sin asignar'})" for m in editables}
                            sel_edit_key = st.selectbox("Seleccione el movimiento a editar:", options=list(opc_edit.keys()), format_func=lambda x: opc_edit[x], key="sel_movimiento_edit")
                            
                            if sel_edit_key:
                                m_sel = next(m for m in editables if f"{m['tipo_rel']}_{m['id_rel']}" == sel_edit_key)
                                
                                with st.form("form_edicion_uso_general"):
                                    st.write(f"✏️ **Editando: {m_sel['tipo_str']}**")
                                    
                                    col_ed1, col_ed2 = st.columns(2)
                                    new_monto = col_ed1.number_input("Monto ($)", min_value=0.01, value=float(m_sel['monto']), step=1000.0)
                                    new_fecha = col_ed2.date_input("Fecha", datetime.datetime.strptime(m_sel['fecha'], '%Y-%m-%d').date(), format="DD-MM-YYYY")
                                    
                                    # Para 'reserva_uso_recupero' con destino 'reserva', no aplica OP
                                    es_volver_reserva_edit = (m_sel['tipo_rel'] == 'reserva_uso_recupero' and m_sel['raw_data'].get('destino_tipo') == DESTINO_RESERVA)
                                    
                                    if not es_volver_reserva_edit:
                                        new_op = st.text_input("Número de Orden de Pago (OP)", value=m_sel['nro_op'] or "")
                                    else:
                                        new_op = ""
                                        st.info("ℹ️ Este movimiento ('Volver a Reserva') no requiere OP. Solo se exige observación.")
                                    
                                    # Notas
                                    old_notas = ""
                                    if m_sel['tipo_rel'] in ['fin_original_uso', 'reserva_uso']:
                                        old_notas = m_sel['raw_data'].get('notas') or ""
                                    elif m_sel['tipo_rel'] == 'desvio':
                                        old_notas = m_sel['raw_data'].get('motivo') or ""
                                    elif m_sel['tipo_rel'] in ['desvio_recupero', 'reserva_uso_recupero']:
                                        old_notas = m_sel['raw_data'].get('notas') or ""
                                    new_notas = st.text_area("Notas / Observaciones / Motivo (Obligatorio si no hay OP, 10-30 chars)", value=old_notas)
                                    
                                    st.caption(f"**Destino actual:** {m_sel['destino']}")
                                    
                                    confirmar_edit_sin_op = False
                                    if not es_volver_reserva_edit and not new_op.strip():
                                        st.warning("⚠️ Si no ingresa el Número de Orden de Pago, deberá completar las observaciones y confirmar.")
                                        confirmar_edit_sin_op = st.checkbox("Confirmo guardar este movimiento sin número de OP", key="chk_confirmar_edit_sin_op")
                                    else:
                                        confirmar_edit_sin_op = True
                                    
                                    if st.form_submit_button("Guardar Cambios", type="primary"):
                                        err_edit = _validar_op_y_notas(
                                            new_op if not es_volver_reserva_edit else None,
                                            new_notas,
                                            requiere_confirmacion=(not es_volver_reserva_edit),
                                            confirmado=confirmar_edit_sin_op
                                        )
                                        if err_edit:
                                            st.error(err_edit)
                                        else:
                                            try:
                                                tipo = m_sel['tipo_rel']
                                                pk_id = m_sel['id_rel']
                                                raw = m_sel['raw_data']
                                                
                                                op_val = new_op.strip() if new_op.strip() else None
                                                notas_val = new_notas.strip() or None
                                                
                                                if tipo == 'fin_original_uso':
                                                    db.update_fin_original_uso(pk_id, new_monto, new_fecha.strftime('%Y-%m-%d'), op_val, new_notas)
                                                
                                                elif tipo == 'desvio':
                                                    db.update_desvio(
                                                        pk_id, 
                                                        new_monto, 
                                                        raw['destino'], 
                                                        new_notas, 
                                                        new_fecha.strftime('%Y-%m-%d'), 
                                                        raw.get('decreto_destino_id'), 
                                                        op_val
                                                    )
                                                    
                                                elif tipo == 'reserva_uso':
                                                    db.update_reserva_uso(
                                                        pk_id, 
                                                        new_monto, 
                                                        raw['destino_tipo'], 
                                                        raw['destino_detalle'], 
                                                        new_fecha.strftime('%Y-%m-%d'), 
                                                        new_notas, 
                                                        raw.get('decreto_destino_id'), 
                                                        op_val
                                                    )
                                                    
                                                elif tipo == 'desvio_recupero':
                                                    db.update_desvio_recupero(
                                                        pk_id, 
                                                        new_monto, 
                                                        new_fecha.strftime('%Y-%m-%d'), 
                                                        raw['destino_tipo'], 
                                                        raw.get('destino_detalle'), 
                                                        raw.get('decreto_destino_id'), 
                                                        op_val,
                                                        notas=notas_val
                                                    )
                                                    
                                                elif tipo == 'reserva_uso_recupero':
                                                    db.update_reserva_uso_recupero(
                                                        pk_id, 
                                                        new_monto, 
                                                        new_fecha.strftime('%Y-%m-%d'), 
                                                        raw['destino_tipo'], 
                                                        raw.get('destino_detalle'), 
                                                        raw.get('decreto_destino_id'), 
                                                        op_val,
                                                        notas=notas_val
                                                    )
                                                    
                                                st.session_state['success_msg_dist'] = "Movimiento modificado con éxito."
                                                st.rerun()
                                            except ValueError as e:
                                                st.error(f"Error de validación: {e}")
                                            except Exception as e:
                                                st.error(f"Error inesperado: {e}")

