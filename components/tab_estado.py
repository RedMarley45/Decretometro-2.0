import streamlit as st
import datetime
import math
import database as db
import pandas as pd
import utils
from utils import _validar_op_y_notas

def render_tab1():
    st.subheader("Estado de Cobranzas")
    # Mostrar notificaciones persistentes de Tab 1
    if 'success_msg_dist' in st.session_state:
        st.success(st.session_state['success_msg_dist'])
        del st.session_state['success_msg_dist']
        
    cobros = db.get_cobros_con_resumen_distribucion()
    # Precargar datos globales para evitar N+1 queries
    decretos_global = db.get_decretos()
    
    if not cobros:
        st.info("No hay cobros registrados en el sistema.")
    else:
        # Filtros
        col_f1, col_f2 = st.columns(2)
        estado_filtro = col_f1.selectbox("Filtrar por Estado", ["Todos", "Con desvíos pendientes", "Totalmente distribuido", "Sin distribuir aún", "Con saldo en reserva"])
        busqueda = col_f2.text_input("Buscar por decreto o Exp. IMUH")
        df_c = pd.DataFrame(cobros)
        
        # Filtros manuales
        if busqueda:
            busqueda = busqueda.strip()
            if busqueda.isdigit() and len(busqueda) <= 4:
                # Si es un número corto (posible nro de decreto), buscamos coincidencia exacta de decreto
                mask_dec = df_c['nro_decreto'].astype(str) == busqueda
                df_c = df_c[mask_dec]
            else:
                # Búsqueda parcial inteligente, incluyendo formato nro_decreto/decreto_anio
                dec_completo = df_c['nro_decreto'].astype(str) + '/' + df_c['decreto_anio'].astype(str)
                mask_dec = dec_completo.str.contains(busqueda, case=False, na=False)
                mask_exp = df_c['expediente_imuh'].astype(str).str.contains(busqueda, case=False, na=False)
                df_c = df_c[mask_dec | mask_exp]
            
        if not df_c.empty:
            # Agrupar cobros por cuota_id
            grouped_cobros = {}
            for _, row in df_c.iterrows():
                q_id = row['cuota_id']
                if q_id not in grouped_cobros:
                    grouped_cobros[q_id] = []
                grouped_cobros[q_id].append(row.to_dict())
            
            # Ordenar grupos por la fecha del cobro más reciente
            groups_list = []
            for q_id, group_cobros in grouped_cobros.items():
                latest_date = max(c['fecha'] for c in group_cobros)
                groups_list.append((q_id, group_cobros, latest_date))
            
            groups_list.sort(key=lambda x: (x[2], x[1][0]['nro_decreto']), reverse=True)
            
            filtered_groups = []
            for q_id, group_cobros, _ in groups_list:
                # 1. Calcular métricas agregadas y listas unificadas
                monto_total_cobrado = sum(c['monto'] for c in group_cobros)
                monto_total_fin_orig = sum(c['monto_fin_orig'] for c in group_cobros)
                monto_total_reserva = sum(c['monto_reserva'] for c in group_cobros)
                monto_total_desvios = sum(c['total_desvios'] for c in group_cobros)
                
                ru_fo_total = 0.0
                ru_other_total = 0.0
                recru_fo_total = 0.0
                recru_res_total = 0.0
                recru_sd_total = 0.0
                rec_fo_total_total = 0.0
                rec_sd_total_total = 0.0
                rec_desv_res_total_total = 0.0
                
                unified_desvios = []
                desvios_all = []
                usos_r_all = []
                
                for c_item in group_cobros:
                    c_id = c_item['id']
                    
                    # Calcular usos de reserva por tipo
                    usos_r_inline = db.get_reserva_usos_by_cobro(c_id)
                    usos_r_all.extend(usos_r_inline)
                    ru_fo_total += sum(u['monto'] for u in usos_r_inline if u['destino_tipo'] == 'fin_original')
                    ru_other_total += sum(u['monto'] for u in usos_r_inline if u['destino_tipo'] != 'fin_original')

                    # Calcular recuperos de desvíos de reserva
                    for u in usos_r_inline:
                        if u['destino_tipo'] != 'fin_original':
                            rec_usos_item = db.get_recuperos_by_reserva_uso(u['id'])
                            for ri in rec_usos_item:
                                if ri['destino_tipo'] == 'fin_original':
                                    recru_fo_total += ri['monto']
                                elif ri['destino_tipo'] == 'reserva':
                                    recru_res_total += ri['monto']
                                elif ri['destino_tipo'] == 'sin_distribucion':
                                    recru_sd_total += ri['monto']
                                    
                            # Active desvios from reserve
                            tot_rec_uso = sum(r['monto'] for r in rec_usos_item)
                            saldo_uso = u['monto'] - tot_rec_uso
                            if saldo_uso > 0.01:
                                unified_desvios.append({
                                    'fecha': u['fecha'],
                                    'monto': saldo_uso,
                                    'destino': u['destino_detalle'] or 'Otra obra',
                                    'nro_op': u.get('nro_op')
                                })

                    # Calcular recuperos a fin original
                    desvios = db.get_desvios_by_cobro(c_id)
                    desvios_all.extend(desvios)
                    for d in desvios:
                        recuperos_del_desvio = db.get_recuperos_by_desvio(d['id'])
                        for rec_item in recuperos_del_desvio:
                            if rec_item['destino_tipo'] == 'fin_original':
                                rec_fo_total_total += rec_item['monto']
                            elif rec_item['destino_tipo'] == 'sin_distribucion':
                                rec_sd_total_total += rec_item['monto']
                            elif rec_item['destino_tipo'] == 'reserva':
                                rec_desv_res_total_total += rec_item['monto']
                                
                        # Active desvios from initial
                        saldo_desv = d['monto'] - d['total_recuperado']
                        if saldo_desv > 0.01:
                            unified_desvios.append({
                                'fecha': d['fecha'],
                                'monto': saldo_desv,
                                'destino': d['destino'],
                                'nro_op': d.get('nro_op')
                            })

                # Aplicar fórmulas matemáticas lineales consistentes
                item_sin_dist = max(0.0, round(monto_total_cobrado - monto_total_fin_orig - monto_total_reserva - monto_total_desvios + rec_sd_total_total + recru_sd_total, 2))
                item_fin_orig = round(monto_total_fin_orig + ru_fo_total + rec_fo_total_total + recru_fo_total, 2)
                item_desvios = round(monto_total_desvios + ru_other_total - rec_fo_total_total - recru_fo_total - recru_res_total - rec_sd_total_total - recru_sd_total - rec_desv_res_total_total, 2)
                item_en_reserva = max(0.0, round(monto_total_reserva - ru_fo_total - ru_other_total + recru_res_total + rec_desv_res_total_total, 2))

                # 2. Filtrar por estado de la tarjeta unificada
                if item_sin_dist > 0.01:
                    estado_calculado = "Sin distribuir aún"
                elif len(unified_desvios) > 0:
                    estado_calculado = "Con desvíos pendientes"
                else:
                    estado_calculado = "Totalmente distribuido"
                    
                if estado_filtro == "Con saldo en reserva":
                    if item_en_reserva <= 0.01:
                        continue
                elif estado_filtro != "Todos" and estado_calculado != estado_filtro:
                    continue
                
                filtered_groups.append({
                    'q_id': q_id,
                    'group_cobros': group_cobros,
                    'monto_total_cobrado': monto_total_cobrado,
                    'item_sin_dist': item_sin_dist,
                    'item_fin_orig': item_fin_orig,
                    'item_desvios': item_desvios,
                    'item_en_reserva': item_en_reserva,
                    'unified_desvios': unified_desvios,
                    'desvios_all': desvios_all,
                    'usos_r_all': usos_r_all
                })
            
            total_items = len(filtered_groups)
            if total_items == 0:
                st.warning("No se encontraron cobros con esos filtros.")
            else:
                cards_per_page = 10
                total_pages = max(1, math.ceil(total_items / cards_per_page))
                
                if 'page_estado' not in st.session_state:
                    st.session_state['page_estado'] = 1
                    
                current_page = max(1, min(st.session_state['page_estado'], total_pages))
                st.session_state['page_estado'] = current_page
                
                def render_pagination_controls(key_suffix):
                    c_pag1, c_pag2, c_pag3 = st.columns([1, 2, 1])
                    with c_pag1:
                        if st.button("⬅️ Anterior", disabled=(current_page <= 1), key=f"prev_pag_{key_suffix}"):
                            st.session_state['page_estado'] = current_page - 1
                            st.rerun()
                    with c_pag2:
                        st.markdown(f"<div style='text-align: center; padding-top: 5px;'><b>Página {current_page} de {total_pages}</b> ({total_items} cobranzas en total)</div>", unsafe_allow_html=True)
                    with c_pag3:
                        if st.button("Siguiente ➡️", disabled=(current_page >= total_pages), key=f"next_pag_{key_suffix}"):
                            st.session_state['page_estado'] = current_page + 1
                            st.rerun()

                render_pagination_controls("top")
                st.write("")

                start_idx = (current_page - 1) * cards_per_page
                end_idx = start_idx + cards_per_page
                page_items = filtered_groups[start_idx:end_idx]

                for item in page_items:
                    q_id = item['q_id']
                    group_cobros = item['group_cobros']
                    monto_total_cobrado = item['monto_total_cobrado']
                    item_sin_dist = item['item_sin_dist']
                    item_fin_orig = item['item_fin_orig']
                    item_desvios = item['item_desvios']
                    item_en_reserva = item['item_en_reserva']
                    unified_desvios = item['unified_desvios']
                    desvios_all = item['desvios_all']
                    usos_r_all = item['usos_r_all']
                    
                    first_row = group_cobros[0]
                    with st.container(border=True):
                        col1, col2, col3 = st.columns([1.8, 2, 2.2])
                    
                        with col1:
                            dec_cuotas = db.get_cuotas_by_decreto(first_row['decreto_id'])
                            cuota_seq = 0
                            for idx, c_c in enumerate(dec_cuotas):
                                if c_c['id'] == q_id:
                                    cuota_seq = idx + 1
                                    break
                            total_cuotas = len(dec_cuotas)
                        
                            st.markdown(f"**Cobro de:** Dto. {first_row['nro_decreto']}/{first_row['decreto_anio']}")
                            st.caption(f"Cuota {first_row['mes']:02d}/{first_row['anio']} (Cuota {cuota_seq} de {total_cuotas}) - Destino: {first_row['destino_fondos']}")
                            exp_imuh_d = first_row['expediente_imuh'] if pd.notna(first_row['expediente_imuh']) and first_row['expediente_imuh'] else "Sin asignar"
                            st.caption(f"Expediente IMUH: {exp_imuh_d}")
                            st.subheader(f"Total cobrado: {utils.format_currency_ar(monto_total_cobrado)}")
                        
                            st.write("**Fecha de cobro:**")
                            for c_item in sorted(group_cobros, key=lambda x: x['fecha']):
                                st.write(f"{utils.format_date_ar(c_item['fecha'])} &nbsp;&nbsp; **{utils.format_currency_ar(c_item['monto'])}**", unsafe_allow_html=True)
                            
                        with col2:
                            st.write("**Distribución Actual:**")
                        
                            if item_sin_dist > 0.01:
                                st.warning(f"🟡 Sin distribución: {utils.format_currency_ar(item_sin_dist)}")
                            else:
                                st.write(f"⚪ Sin distribución: {utils.format_currency_ar(item_sin_dist)}")
                            
                            st.write(f"✅ Fin original: {utils.format_currency_ar(item_fin_orig)}")
                            st.write(f"🚨 Desvíos: {utils.format_currency_ar(item_desvios)}")
                            st.write(f"🔒 En reserva: {utils.format_currency_ar(item_en_reserva)}")
                        
                            # Item 5 Condicional: Pendiente de cobro
                            cuota = db.get_cuota(q_id)
                            if cuota:
                                cuota_monto = cuota['monto']
                                cobrado_total_cuota = db.get_total_cobrado_por_cuota(q_id)
                            
                                saldo_pendiente_cuota = max(0.0, round(cuota_monto - cobrado_total_cuota, 2))
                                if saldo_pendiente_cuota > 0.01:
                                    st.warning(f"🕒 Pendiente de cobro: {utils.format_currency_ar(saldo_pendiente_cuota)}")
                                
                        with col3:
                            # Ordenar cronológicamente (más antiguo primero)
                            unified_desvios.sort(key=lambda x: x['fecha'])
                        
                            st.write("**Desvíos Activos:**")
                            if unified_desvios:
                                for ud in unified_desvios:
                                    op_str = f" | OP Bejerman: {ud['nro_op']}" if ud.get('nro_op') else ""
                                    st.error(f"🔴 {utils.format_date_ar(ud['fecha'])}: **{utils.format_currency_ar(ud['monto'])}** desviados a {ud['destino']}{op_str}")
                            else:
                                st.success("Sin desvíos activos registrados. ✅")
                            
                        # Expandir detalles
                        with st.expander("Ver / Registrar Movimientos de Recuperos y Reservas"):
                            tiene_movimientos = bool(desvios_all or usos_r_all or any(c.get('monto_fin_orig', 0) > 0 or c.get('monto_reserva', 0) > 0 for c in group_cobros))
                            if not tiene_movimientos:
                                st.info("ℹ️ Esta cobranza no posee desvíos, reservas ni pagos a Fin Original registrados para gestionar.")

                            # Mostrar desvios para recuperar
                            desvios_pendientes = []
                            for d in desvios_all:
                                st.write(f"💸 **Recuperos de {d['destino']} (Desviado: {utils.format_currency_ar(d['monto'])})**")
                                recuperos_del_desvio = db.get_recuperos_by_desvio(d['id'])
                                if recuperos_del_desvio:
                                    for rec in recuperos_del_desvio:
                                        col_r1, col_r2 = st.columns([4, 1])
                                        if rec['destino_tipo'] == "fin_original":
                                            dest_str = "Fin original"
                                        elif rec['destino_tipo'] == "reserva":
                                            dest_str = "Reserva"
                                        elif rec['destino_tipo'] == "sin_distribucion":
                                            dest_str = "Sin distribución"
                                        else:
                                            dest_str = f"Otra obra: {rec.get('dest_nombre') or rec.get('destino_detalle', '')}"
                                    
                                        col_r1.caption(f"- {utils.format_date_ar(rec['fecha'])}: {utils.format_currency_ar(rec['monto'])} a {dest_str}")
                                        if col_r2.button("Borrar", key=f"del_rec_{rec['id']}"):
                                            db.delete_desvio_recupero(rec['id'])
                                            st.session_state['success_msg_dist'] = "Recupero eliminado correctamente."
                                            st.rerun()
                                    st.write("---")
                                
                                saldo_d = d['monto'] - d['total_recuperado']
                                if saldo_d > 0.01:
                                    d['saldo_pendiente'] = saldo_d
                                    desvios_pendientes.append(d)

                            if desvios_pendientes:
                                st.write("---")
                                st.write("**Registrar Nuevo Recupero de Desvío**")
                            
                                opciones_desv = {
                                    d['id']: f"{d['destino']} ({utils.format_date_ar(d['fecha'])}) - Saldo Libre: {utils.format_currency_ar(d['saldo_pendiente'])}"
                                    for d in desvios_pendientes
                                }
                            
                                sel_desv_id = st.selectbox("Seleccione el Desvío a recuperar:", options=list(opciones_desv.keys()), format_func=lambda x: opciones_desv[x], key=f"sel_desv_recuperar_{q_id}")
                            
                                if sel_desv_id:
                                    d_sel = next(d for d in desvios_pendientes if d['id'] == sel_desv_id)
                                    saldo_sel = d_sel['saldo_pendiente']
                                
                                    with st.container():
                                        m_rec = st.number_input("Monto", min_value=0.01, max_value=float(saldo_sel), value=float(saldo_sel), step=1000.0, key=f"m_rec_{q_id}")
                                        f_rec = st.date_input("Fecha", datetime.date.today(), format="DD-MM-YYYY", key=f"f_rec_{q_id}")
                                        op_rec = st.text_input("Número de Orden de Pago (Recupero)", key=f"op_rec_{q_id}")
                                        notas_rec = st.text_input("Notas u observaciones (Obligatorio si no hay OP, 10-30 chars)", key=f"notas_rec_{q_id}")
                                        st.caption("Destino del recupero:")
                                        tipo_rec_r = st.radio("¿Hacia dónde va?", ["Fin original", "Reserva", "Obra (Catálogo)", "Sin distribución"], key=f"tipo_rec_r_{q_id}")
                                    
                                        rec_obra_id = None
                                        if tipo_rec_r == "Obra (Catálogo)":
                                            obras_disponibles = db.get_obras(only_active=True)
                                            opc_obras = {}
                                            if obras_disponibles:
                                                for o in obras_disponibles:
                                                    label = f"{o['nombre']} (Exp: {o['expediente_imuh']})"
                                                    decretos_asoc = db.get_decretos_by_obra(o['id'])
                                                    if decretos_asoc:
                                                        parts = []
                                                        for dd in decretos_asoc:
                                                            if dd.get('estado') == 'Anulado':
                                                                parts.append(f"Decreto {dd['nro_decreto']}/{dd['anio']} - ANULADO")
                                                            else:
                                                                parts.append(f"Decreto {dd['nro_decreto']}/{dd['anio']}")
                                                        label += f" ({', '.join(parts)})"
                                                    opc_obras[o['id']] = label
                                            rec_obra_id = st.selectbox("Seleccione la obra de destino:", options=list(opc_obras.keys()), format_func=lambda x: opc_obras[x], key=f"sec_obra_rec_{q_id}")
                                    
                                        confirmar_rec_sin_op = False
                                        if not op_rec.strip():
                                            st.warning("⚠️ Si no ingresa el Número de Orden de Pago, deberá completar las observaciones y confirmar.")
                                            confirmar_rec_sin_op = st.checkbox("Confirmo que deseo registrar el recupero sin número de OP", key=f"chk_confirmar_rec_sin_op_{q_id}")
                                        else:
                                            confirmar_rec_sin_op = True
    
                                        if st.button("Confirmar Recupero", type="primary", key=f"btn_confirmar_rec_{q_id}"):
                                            det_rec = ""
                                            rec_decreto_id = None
                                            if tipo_rec_r == "Obra (Catálogo)" and rec_obra_id:
                                                obra_obj = db.get_obra(rec_obra_id)
                                                if obra_obj:
                                                    det_rec = obra_obj['nombre']
                                                    decretos_asoc = db.get_decretos_by_obra(rec_obra_id)
                                                    decretos_vigentes = [dd for dd in decretos_asoc if dd['estado'] != 'Anulado']
                                                    if decretos_vigentes:
                                                        rec_decreto_id = decretos_vigentes[0]['id']
                                                    elif decretos_asoc:
                                                        rec_decreto_id = decretos_asoc[0]['id']
                                                
                                            err_op = _validar_op_y_notas(op_rec, notas_rec, requiere_confirmacion=True, confirmado=confirmar_rec_sin_op)
                                            if tipo_rec_r == "Obra (Catálogo)" and not det_rec.strip():
                                                st.error("Especifica la obra de destino.")
                                            elif err_op:
                                                st.error(err_op)
                                            else:
                                                try:
                                                    if tipo_rec_r == "Fin original":
                                                        t_enum = "fin_original"
                                                    elif tipo_rec_r == "Reserva":
                                                        t_enum = "reserva"
                                                    elif tipo_rec_r == "Sin distribución":
                                                        t_enum = "sin_distribucion"
                                                    else:
                                                        t_enum = "nueva_obra"
                                                    db.add_desvio_recupero(sel_desv_id, m_rec, f_rec.strftime('%Y-%m-%d'), t_enum, det_rec, rec_decreto_id, nro_op=op_rec if op_rec.strip() else None, notas=notas_rec.strip() or None)
                                                    st.session_state['success_msg_dist'] = "Recupero registrado con éxito."
                                                
                                                    # Clean up state so we don't have lingering data
                                                    for k in [f"sel_desv_recuperar_{q_id}", f"m_rec_{q_id}", f"f_rec_{q_id}", f"op_rec_{q_id}", f"notas_rec_{q_id}", f"tipo_rec_r_{q_id}", f"sec_obra_rec_{q_id}", f"chk_confirmar_rec_sin_op_{q_id}"]:
                                                        if k in st.session_state:
                                                            del st.session_state[k]
                                                        
                                                    st.rerun()
                                                except ValueError as e:
                                                    st.error(str(e))
                                                
                            # Mostrar recuperos para desvíos desde reserva
                            usos_r_pendientes = []
                            for u in usos_r_all:
                                if u['destino_tipo'] != 'fin_original':
                                    u_destino = u['destino_detalle'] or 'Otra obra'
                                    st.write(f"🔒 **Recuperos de Reserva a {u_destino} (Prestado: {utils.format_currency_ar(u['monto'])})**")
                                    rec_usos = db.get_recuperos_by_reserva_uso(u['id'])
                                    if rec_usos:
                                        for rec in rec_usos:
                                            col_r1, col_r2 = st.columns([4, 1])
                                            if rec['destino_tipo'] == "fin_original":
                                                dest_str = "Fin original"
                                            elif rec['destino_tipo'] == "reserva":
                                                dest_str = "Volver a Reserva"
                                            elif rec['destino_tipo'] == "sin_distribucion":
                                                dest_str = "Sin distribución"
                                            else:
                                                dest_str = f"Otra obra: {rec.get('dest_nombre') or rec.get('destino_detalle', '')}"
                                        
                                            col_r1.caption(f"- {utils.format_date_ar(rec['fecha'])}: {utils.format_currency_ar(rec['monto'])} a {dest_str}. Notas: {rec.get('notas') or 'Sin observaciones'}")
                                            if col_r2.button("Borrar", key=f"del_rec_res_{rec['id']}"):
                                                db.delete_reserva_uso_recupero(rec['id'])
                                                st.session_state['success_msg_dist'] = "Recupero de reserva eliminado correctamente."
                                                st.rerun()
                                        st.write("---")
                                
                                    tot_rec_u = sum(r['monto'] for r in rec_usos)
                                    saldo_u = u['monto'] - tot_rec_u
                                    if saldo_u > 0.01:
                                        u['saldo_pendiente'] = saldo_u
                                        usos_r_pendientes.append(u)

                            if usos_r_pendientes:
                                st.write("---")
                                st.write("**Registrar Nuevo Recupero de Reserva**")
                            
                                opciones_uso_r = {
                                    u['id']: f"{u['destino_detalle'] or 'Otra obra'} ({utils.format_date_ar(u['fecha'])}) - Saldo Libre: {utils.format_currency_ar(u['saldo_pendiente'])}"
                                    for u in usos_r_pendientes
                                }
                            
                                sel_uso_r_id = st.selectbox("Seleccione el Préstamo de Reserva a recuperar:", options=list(opciones_uso_r.keys()), format_func=lambda x: opciones_uso_r[x], key=f"sel_uso_r_recuperar_{q_id}")
                            
                                if sel_uso_r_id:
                                    u_sel = next(u for u in usos_r_pendientes if u['id'] == sel_uso_r_id)
                                    saldo_u = u_sel['saldo_pendiente']
                                
                                    with st.container():
                                        m_rec_res = st.number_input("Monto", min_value=0.01, max_value=float(saldo_u), value=float(saldo_u), step=1000.0, key=f"m_rec_res_{q_id}")
                                        f_rec_res = st.date_input("Fecha", datetime.date.today(), format="DD-MM-YYYY", key=f"f_rec_res_{q_id}")
                                    
                                        st.caption("Destino del recupero:")
                                        tipo_rec_r_res = st.radio("¿Hacia dónde va?", ["Fin original", "Volver a Reserva", "Obra (Catálogo)", "Sin distribución"], key=f"tipo_rec_r_res_{q_id}")
                                    
                                        es_volver_reserva = (tipo_rec_r_res == "Volver a Reserva")
                                    
                                        if not es_volver_reserva:
                                            op_rec_res = st.text_input("Número de Orden de Pago (Recupero Reserva)", key=f"op_rec_res_{q_id}")
                                        else:
                                            op_rec_res = ""
                                            st.info("ℹ️ Para 'Volver a Reserva' no se requiere OP. Solo se exige una observación.")
                                    
                                        notas_rec_res = st.text_input("Notas u observaciones (Obligatorio, 10-30 chars)", key=f"notas_rec_res_{q_id}")
                                    
                                        rec_obra_id_res = None
                                        if tipo_rec_r_res == "Obra (Catálogo)":
                                            obras_disponibles = db.get_obras(only_active=True)
                                            opc_obras = {}
                                            if obras_disponibles:
                                                for o in obras_disponibles:
                                                    label = f"{o['nombre']} (Exp: {o['expediente_imuh']})"
                                                    decretos_asoc = db.get_decretos_by_obra(o['id'])
                                                    if decretos_asoc:
                                                        parts = []
                                                        for dd in decretos_asoc:
                                                            if dd.get('estado') == 'Anulado':
                                                                parts.append(f"Decreto {dd['nro_decreto']}/{dd['anio']} - ANULADO")
                                                            else:
                                                                parts.append(f"Decreto {dd['nro_decreto']}/{dd['anio']}")
                                                        label += f" ({', '.join(parts)})"
                                                    opc_obras[o['id']] = label
                                            rec_obra_id_res = st.selectbox("Seleccione la obra de destino:", options=list(opc_obras.keys()), format_func=lambda x: opc_obras[x], key=f"sec_obra_rec_res_{q_id}")
                                    
                                        confirmar_rec_res_sin_op = False
                                        if not es_volver_reserva and not op_rec_res.strip():
                                            st.warning("⚠️ Si no ingresa el Número de Orden de Pago, deberá completar las observaciones y confirmar.")
                                            confirmar_rec_res_sin_op = st.checkbox("Confirmo que deseo registrar el recupero sin número de OP", key=f"chk_confirmar_rec_res_sin_op_{q_id}")
                                        else:
                                            confirmar_rec_res_sin_op = True
    
                                        if st.button("Confirmar Recupero de Reserva", type="primary", key=f"btn_confirmar_rec_res_{q_id}"):
                                            det_rec = ""
                                            rec_decreto_id = None
                                            if tipo_rec_r_res == "Obra (Catálogo)" and rec_obra_id_res:
                                                obra_obj = db.get_obra(rec_obra_id_res)
                                                if obra_obj:
                                                    det_rec = obra_obj['nombre']
                                                    decretos_asoc = db.get_decretos_by_obra(rec_obra_id_res)
                                                    decretos_vigentes = [dd for dd in decretos_asoc if dd['estado'] != 'Anulado']
                                                    if decretos_vigentes:
                                                        rec_decreto_id = decretos_vigentes[0]['id']
                                                    elif decretos_asoc:
                                                        rec_decreto_id = decretos_asoc[0]['id']
                                                    
                                            err_op = _validar_op_y_notas(
                                                op_rec_res if not es_volver_reserva else None,
                                                notas_rec_res,
                                                requiere_confirmacion=(not es_volver_reserva),
                                                confirmado=confirmar_rec_res_sin_op
                                            )
                                            if tipo_rec_r_res == "Obra (Catálogo)" and not det_rec.strip():
                                                st.error("Especifica la obra de destino.")
                                            elif err_op:
                                                st.error(err_op)
                                            else:
                                                try:
                                                    if tipo_rec_r_res == "Fin original":
                                                        t_enum = "fin_original"
                                                    elif tipo_rec_r_res == "Volver a Reserva":
                                                        t_enum = "reserva"
                                                    elif tipo_rec_r_res == "Sin distribución":
                                                        t_enum = "sin_distribucion"
                                                    else:
                                                        t_enum = "nueva_obra"
                                                    db.add_reserva_uso_recupero(sel_uso_r_id, m_rec_res, f_rec_res.strftime('%Y-%m-%d'), t_enum, det_rec, rec_decreto_id, nro_op=op_rec_res if op_rec_res.strip() else None, notas=notas_rec_res.strip() or None)
                                                    st.session_state['success_msg_dist'] = "Recupero de reserva registrado con éxito."
                                                
                                                    for k in [f"sel_uso_r_recuperar_{q_id}", f"m_rec_res_{q_id}", f"f_rec_res_{q_id}", f"tipo_rec_r_res_{q_id}", f"op_rec_res_{q_id}", f"notas_rec_res_{q_id}", f"sec_obra_rec_res_{q_id}", f"chk_confirmar_rec_res_sin_op_{q_id}"]:
                                                        if k in st.session_state:
                                                            del st.session_state[k]
                                                        
                                                    st.rerun()
                                                except ValueError as e:
                                                    st.error(str(e))

                            # Mostrar usos de Fin Original si hay asignado
                            for c_item in group_cobros:
                                cobro_id = c_item['id']
                                fo_asignado = c_item['monto_fin_orig']
                                usos_fo = db.get_fin_original_usos_by_cobro(cobro_id)
                                total_fo_pagado = sum(u['monto'] for u in usos_fo)
                                saldo_fo_pendiente = max(0.0, round(fo_asignado - total_fo_pagado, 2))
                            
                                if fo_asignado > 0:
                                    st.write("---")
                                    st.write(f"🏗️ **Pagos de Fin Original del Cobro {utils.format_date_ar(c_item['fecha'])} (Saldo pendiente de pago: {utils.format_currency_ar(saldo_fo_pendiente)}):**")
                                    if saldo_fo_pendiente > 0.01:
                                        with st.container():
                                            op_fo_pay = st.text_input("Número de Orden de Pago", key=f"op_fo_pay_inp_{cobro_id}")
                                            op_fo_pay = ''.join(filter(str.isdigit, op_fo_pay)) # force digits
                                            
                                            op_locked_fecha_fo = None
                                            if op_fo_pay:
                                                usos_op = db.get_op_usage_details(op_fo_pay)
                                                if usos_op:
                                                    st.info("ℹ️ **Esta OP ya está vinculada a los siguientes pagos:**")
                                                    for u in usos_op:
                                                        st.info(f"- {u['origen']} por {utils.format_currency_ar(u['monto'])}")
                                                    op_locked_fecha_fo = datetime.datetime.strptime(usos_op[0]['fecha'], '%Y-%m-%d').date()
                                                    st.session_state[f"f_fo_pay_{cobro_id}"] = op_locked_fecha_fo
                                            cc1, cc2 = st.columns(2)
                                            m_fo_pay = cc1.number_input("Monto a pagar", min_value=0.01, max_value=float(saldo_fo_pendiente), value=float(saldo_fo_pendiente), step=1000.0)
                                            f_fo_pay = cc2.date_input("Fecha de pago", key=f"f_fo_pay_{cobro_id}", format="DD-MM-YYYY", disabled=(op_locked_fecha_fo is not None))
                                            notas_fo_pay = st.text_input("Notas u observaciones (Obligatorio si no hay OP, 10-30 chars)")
                                        
                                            confirmar_fo_pay_sin_op = False
                                            if not op_fo_pay.strip():
                                                st.warning("⚠️ Si no ingresa el Número de Orden de Pago, deberá completar las observaciones y confirmar.")
                                                confirmar_fo_pay_sin_op = st.checkbox("Confirmo que deseo registrar el pago sin número de OP", key=f"chk_confirmar_fo_pay_sin_op_{cobro_id}")
                                            else:
                                                confirmar_fo_pay_sin_op = True
                                            
                                            if st.button("Registrar Pago de Fin Original", type="primary", key=f"btn_fo_{cobro_id}"):
                                                err_op = _validar_op_y_notas(op_fo_pay, notas_fo_pay, confirmado=confirmar_fo_pay_sin_op)
                                                if err_op:
                                                    st.error(err_op)
                                                else:
                                                    try:
                                                        db.add_fin_original_uso(cobro_id, m_fo_pay, f_fo_pay.strftime('%Y-%m-%d'), op_fo_pay if op_fo_pay.strip() else None, notas_fo_pay.strip() or None)
                                                        st.session_state['success_msg_dist'] = "Pago a Fin Original registrado."
                                                        for k in [f"op_fo_pay_inp_{cobro_id}", f"chk_confirmar_fo_pay_sin_op_{cobro_id}"]:
                                                            if k in st.session_state:
                                                                del st.session_state[k]
                                                        st.rerun()
                                                    except ValueError as e:
                                                        st.error(str(e))
                                    if usos_fo:
                                        st.write(f"**Historial de pagos a Fin Original del Cobro {utils.format_date_ar(c_item['fecha'])}:**")
                                        for u in usos_fo:
                                            op_str = f"OP: {u['nro_op']}" if u['nro_op'] else "OP: Sin asignar"
                                            notes_str = f". Notas: {u['notas']}" if u['notas'] else ""
                                            col_u1, col_u2 = st.columns([4, 1])
                                            col_u1.caption(f"- {utils.format_date_ar(u['fecha'])}: {utils.format_currency_ar(u['monto'])} ({op_str}){notes_str}")
                                            if col_u2.button("Borrar", key=f"del_uso_fo_{u['id']}"):
                                                db.delete_fin_original_uso(u['id'])
                                                st.session_state['success_msg_dist'] = "Pago a Fin Original eliminado correctamente."
                                                st.rerun()

                            # Mostrar usos de reserva si hay reserva
                            for c_item in group_cobros:
                                cobro_id = c_item['id']
                                reserva_actual = c_item['monto_reserva']
                                usos_r = db.get_reserva_usos_by_cobro(cobro_id)
                                total_usado = sum(u['monto'] for u in usos_r)
                                saldo_reserva = reserva_actual - total_usado
                            
                                if reserva_actual > 0:
                                    st.write("---")
                                    st.write(f"🔒 **Usar Reservas del Cobro {utils.format_date_ar(c_item['fecha'])} (Saldo disponible: {utils.format_currency_ar(saldo_reserva)}):**")
                                    if saldo_reserva > 0.01:
                                        with st.container():
                                            op_uso = st.text_input("Número de Orden de Pago (Uso Reserva)", key=f"op_uso_{cobro_id}")
                                            op_uso = ''.join(filter(str.isdigit, op_uso))
                                            
                                            op_locked_obra = None
                                            op_locked_gasto = None
                                            op_locked_fecha_uso = None
                                            
                                            if op_uso:
                                                usos_op = db.get_op_usage_details(op_uso)
                                                if usos_op:
                                                    st.info("ℹ️ **Esta OP ya está vinculada a los siguientes pagos:**")
                                                    for u in usos_op:
                                                        st.info(f"- {u['origen']} por {utils.format_currency_ar(u['monto'])}")
                                                    op_locked_fecha_uso = datetime.datetime.strptime(usos_op[0]['fecha'], '%Y-%m-%d').date()
                                                    st.session_state[f"f_uso_{cobro_id}"] = op_locked_fecha_uso
                                                    op_info = db.get_op_info(op_uso)
                                                    if op_info:
                                                        if op_info['obra_id']: 
                                                            op_locked_obra = op_info['obra_id']
                                                            st.session_state[f"tipo_uso_{cobro_id}"] = "obra_catalogo"
                                                            st.session_state[f"uso_obra_id_{cobro_id}"] = op_locked_obra
                                                        if op_info['gasto_id']: 
                                                            op_locked_gasto = op_info['gasto_id']
                                                            st.session_state[f"tipo_uso_{cobro_id}"] = "gasto_fun"
                                                            st.session_state[f"uso_gasto_id_sel_{cobro_id}"] = op_locked_gasto
                                                        st.warning("⚠️ **OP ya utilizada:** El destino (Obra/Gasto) ha sido bloqueado para coincidir con el original. Si hay un error, debe eliminar los pagos previos de esta OP.")

                                            cc1, cc2, cc3 = st.columns(3)
                                            m_uso = cc1.number_input("Monto a usar", min_value=0.01, max_value=float(saldo_reserva), value=float(saldo_reserva), step=1000.0)
                                            f_uso = cc2.date_input("Fecha de uso", key=f"f_uso_{cobro_id}", format="DD-MM-YYYY", disabled=(op_locked_fecha_uso is not None))
                                            tipo_opciones = ["fin_original", "obra_catalogo", "gasto_fun"]
                                            index_tipo = 0
                                            if op_locked_obra: index_tipo = 1
                                            elif op_locked_gasto: index_tipo = 2
                                            tipo_uso = cc3.selectbox("¿Hacia dónde va?", tipo_opciones, disabled=(op_locked_obra is not None or op_locked_gasto is not None), format_func=lambda x: "Fin original" if x == "fin_original" else ("Obra (Catálogo)" if x == "obra_catalogo" else "Gasto de Funcionamiento (FUN)"), key=f"tipo_uso_{cobro_id}")
                                        
                                            nd_obra_id = None
                                            gasto_nombre = ""
                                            gasto_expediente_imuh = ""
                                        
                                            if tipo_uso == "obra_catalogo":
                                                obras_disponibles = db.get_obras(only_active=True)
                                                if not obras_disponibles:
                                                    st.warning("No hay obras activas en el catálogo.")
                                                    opc_obras = {}
                                                else:
                                                    opc_obras = {}
                                                    for o in obras_disponibles:
                                                        label = f"{o['nombre']} (Exp: {o['expediente_imuh']})"
                                                        decretos_asoc = db.get_decretos_by_obra(o['id'])
                                                        if decretos_asoc:
                                                            parts = []
                                                            for d in decretos_asoc:
                                                                if d.get('estado') == 'Anulado':
                                                                    parts.append(f"Decreto {d['nro_decreto']}/{d['anio']} - ANULADO")
                                                                else:
                                                                    parts.append(f"Decreto {d['nro_decreto']}/{d['anio']}")
                                                            label += f" ({', '.join(parts)})"
                                                        opc_obras[o['id']] = label
                                                idx_o = list(opc_obras.keys()).index(op_locked_obra) if op_locked_obra in opc_obras else 0
                                                nd_obra_id = st.selectbox("Seleccione la Obra Destino", options=list(opc_obras.keys()), disabled=(op_locked_obra is not None), format_func=lambda x: opc_obras[x], key=f"uso_obra_id_{cobro_id}")
                                            elif tipo_uso == "gasto_fun":
                                                gastos_disponibles = db.get_gastos_funcionamiento(only_active=True)
                                                opc_gastos = {g['id']: f"{g['nombre']} (Exp: {g['expediente_imuh']})" for g in gastos_disponibles}
                                            
                                                idx_g = list(opc_gastos.keys()).index(op_locked_gasto) if op_locked_gasto in opc_gastos else 0
                                                gasto_id_sel = st.selectbox("Seleccione el Gasto de Funcionamiento (FUN)", options=list(opc_gastos.keys()), disabled=(op_locked_gasto is not None), format_func=lambda x: opc_gastos[x], key=f"uso_gasto_id_sel_{cobro_id}")
                                            
                                                if gasto_id_sel:
                                                    g_selected = next(g for g in gastos_disponibles if g['id'] == gasto_id_sel)
                                                    gasto_nombre = g_selected['nombre']
                                                    gasto_expediente_imuh = g_selected['expediente_imuh']
                                                    uso_gasto_prov_id = g_selected.get('proveedor_id')
                                                    p_txt = g_selected.get('proveedor_razon_social') or "Sin proveedor asignado"
                                                    st.text_input(
                                                        "Proveedor de Funcionamiento",
                                                        value=p_txt,
                                                        disabled=True,
                                                        key=f"uso_gasto_prov_txt_{cobro_id}"
                                                    )
                                                    st.info(f"💡 **Gasto seleccionado:** {gasto_nombre} (Exp: {gasto_expediente_imuh}) | Proveedor: {p_txt}")
                                                else:
                                                    gasto_nombre = ""
                                                    gasto_expediente_imuh = ""
                                                    uso_gasto_prov_id = None
                                                    st.info("ℹ️ No hay gastos de funcionamiento activos en el catálogo. Registrá uno desde el menú 💼 Gastos de Funcionamiento.")
                                            
                                            notas_uso = st.text_input("Notas u observaciones (Obligatorio si no hay OP, 10-30 chars)", key=f"notes_uso_{cobro_id}")
                                        
                                            confirmar_uso_sin_op = False
                                            if not op_uso.strip():
                                                st.warning("⚠️ Si no ingresa el Número de Orden de Pago, deberá completar las observaciones y confirmar.")
                                                confirmar_uso_sin_op = st.checkbox("Confirmo que deseo registrar el uso de reserva sin número de OP", key=f"chk_confirmar_uso_sin_op_{cobro_id}")
                                            else:
                                                confirmar_uso_sin_op = True

                                            if st.button("Registrar Uso de Reserva", type="primary", key=f"btn_uso_r_{cobro_id}"):
                                                err_op = _validar_op_y_notas(op_uso, notas_uso, confirmado=confirmar_uso_sin_op)
                                                if tipo_uso == "obra_catalogo" and not nd_obra_id:
                                                    st.error("Debe seleccionar una obra del catálogo.")
                                                elif tipo_uso == "gasto_fun" and not gasto_nombre.strip():
                                                    st.error("El nombre del gasto de funcionamiento es obligatorio.")
                                                elif tipo_uso == "gasto_fun" and not gasto_expediente_imuh.strip():
                                                    st.error("El número de expediente IMUH es obligatorio.")
                                                elif tipo_uso == "gasto_fun" and not utils.validar_expediente_imuh(gasto_expediente_imuh):
                                                    st.error("El número de expediente IMUH no tiene un formato válido (Ej: 8000000-I-2026).")
                                                elif tipo_uso == "gasto_fun" and uso_gasto_prov_id == 0:
                                                    st.error("Debe seleccionar un Proveedor de Funcionamiento. Ya no se permite 'NO INFORMA PROVEEDOR'.")
                                                elif err_op:
                                                    st.error(err_op)
                                                else:
                                                    try:
                                                        if tipo_uso == "fin_original":
                                                            db.add_reserva_uso(cobro_id, m_uso, "fin_original", "", f_uso.strftime('%Y-%m-%d'), notas_uso.strip() or None, nro_op=op_uso if op_uso.strip() else None)
                                                        elif tipo_uso == "obra_catalogo":
                                                            db.add_reserva_uso(cobro_id, m_uso, "otra_obra", "", f_uso.strftime('%Y-%m-%d'), notas_uso.strip() or None, nro_op=op_uso if op_uso.strip() else None, obra_id=nd_obra_id)
                                                        else: # gasto_fun
                                                            gasto_exp_norm = utils.normalizar_expediente_imuh(gasto_expediente_imuh)
                                                            db.add_reserva_uso(cobro_id, m_uso, "otra_obra", gasto_nombre, f_uso.strftime('%Y-%m-%d'), notas_uso.strip() or None, nro_op=op_uso if op_uso.strip() else None, gasto_nombre=gasto_nombre, gasto_expediente_imuh=gasto_exp_norm)
                                                        st.session_state['success_msg_dist'] = "Uso de reserva registrado."
                                                        for k in [f"op_uso_{cobro_id}", f"notes_uso_{cobro_id}", f"chk_confirmar_uso_sin_op_{cobro_id}", f"uso_obra_id_{cobro_id}", f"uso_gasto_id_sel_{cobro_id}", f"uso_gasto_prov_txt_{cobro_id}"]:
                                                            if k in st.session_state:
                                                                del st.session_state[k]
                                                        st.rerun()
                                                    except ValueError as e:
                                                        st.error(str(e))
                                    if usos_r:
                                        st.write(f"**Historial de uso de reservas del Cobro {utils.format_date_ar(c_item['fecha'])}:**")
                                        for u in usos_r:
                                            destino_str = "Fin original" if u['destino_tipo'] == "fin_original" else "Otra obra"
                                            detalle_str = f" ({u.get('destino_detalle', '')})" if u.get('destino_detalle') else ""
                                            op_str = f" | OP: {u['nro_op']}" if u['nro_op'] else " | OP: Sin asignar"
                                            st.caption(f"- {utils.format_date_ar(u['fecha'])}: {utils.format_currency_ar(u['monto'])} a {destino_str}{detalle_str}{op_str}. Notas: {u.get('notas','')}")
            
                        with st.expander("🗺️ Ver Mapa de Trazabilidad de Fondos (Camino del Dinero)"):
                            from trazabilidad_graph import mostrar_mapa_trazabilidad
                            if len(group_cobros) > 1:
                                cobro_opciones = {c['id']: f"Cobro del {utils.format_date_ar(c['fecha'])} - {utils.format_currency_ar(c['monto'])}" for c in group_cobros}
                                sel_c_id = st.selectbox("Seleccione el cobro a visualizar:", options=list(cobro_opciones.keys()), format_func=lambda x: cobro_opciones[x], key=f"sel_graph_c_{q_id}")
                                mostrar_mapa_trazabilidad(sel_c_id)
                            else:
                                mostrar_mapa_trazabilidad(group_cobros[0]['id'])
            
                if total_pages > 1:
                    st.write("")
                    render_pagination_controls("bottom")
        else:
            st.warning("No se encontraron cobros con esos filtros.")
            
        # Tabla de Deudas Obras Propias
        st.write("---")
        st.subheader("Deudas Acumuladas: Obras / Gastos de Funcionamiento")
        deudas_propias = db.get_deudas_obras_propias()
        if deudas_propias:
            st.info("Listado de deudas pendientes de devolución para obras sin decreto vigente y gastos de funcionamiento.")
            df_dp = pd.DataFrame(deudas_propias)
            df_dp = df_dp[['destino', 'tipo', 'expediente_imuh', 'decreto_asociado', 'saldo']]
            st.dataframe(df_dp.style.format({'saldo': '${:,.2f}'}), use_container_width=True)
        else:
            st.success("No hay deudas pendientes reportadas para obras o gastos de funcionamiento.")

# --- TAB 2: REGISTRAR ---
