import streamlit as st
import pandas as pd
import datetime
import os, sys
import base64

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import database as db
import importlib
importlib.reload(db)
import utils
importlib.reload(utils)

def display_pdf(file_path):
    with open(file_path, "rb") as f:
        base64_pdf = base64.b64encode(f.read()).decode('utf-8')
    # Usamos <embed> en lugar de <iframe> para mayor compatibilidad con buffers base64 en navegadores modernos
    pdf_display = f'<embed src="data:application/pdf;base64,{base64_pdf}" width="100%" height="800" type="application/pdf">'
    st.markdown(pdf_display, unsafe_allow_html=True)

st.set_page_config(page_title="Decretos | Decretómetro", page_icon="📜", layout="wide")
utils.inject_style()
st.title("Decretos 📜")

if "success_msg_dec" in st.session_state:
    st.toast(f"✅ {st.session_state['success_msg_dec']}")
    del st.session_state["success_msg_dec"]

tab1, tab2 = st.tabs(["🗂️ Directorio y Detalles", "➕ Nuevo Decreto"])

# --- TAB 1: LISTADO Y DETALLES ---
with tab1:
    decretos = db.get_decretos()
    if not decretos:
        st.info("No hay decretos cargados en el sistema.")
    else:
        st.subheader("Buscar / Seleccionar Decreto")
        opciones = []
        obras_all = db.get_obras()
        mapa_imuh_nombres = {o['expediente_imuh'].strip(): o['nombre'] for o in obras_all if o.get('expediente_imuh')}
        
        for d in decretos:
            if d.get('expediente_imuh'):
                parts = [p.strip() for p in d['expediente_imuh'].split(',') if p.strip()]
                imuh_con_nombres = []
                for p in parts:
                    nombre = mapa_imuh_nombres.get(p)
                    if nombre:
                        imuh_con_nombres.append(f"{p} ({nombre})")
                    else:
                        imuh_con_nombres.append(p)
                exp_imuh_str = f" | IMUH: {', '.join(imuh_con_nombres)}"
            else:
                exp_imuh_str = " | IMUH: Sin asignar"
            
            opciones.append(f"ID: {d['id']} | Dto. {d['nro_decreto']}/{d['anio']} - {d['destino_fondos']}{exp_imuh_str}")
        seleccion = st.selectbox("Seleccione un decreto para ver su detalle (puede tipear el Exp IMUH):", opciones)
        
        if seleccion:
            dec_id = int(seleccion.split(" | ")[0].replace("ID: ", ""))
            dec = db.get_decreto(dec_id)
            cuotas = db.get_cuotas_by_decreto(dec_id)
            cobros = [c for c in db.get_all_cobros() if c['decreto_id'] == dec_id]
            
            st.markdown("---")
            col_info, col_actions = st.columns([3, 1])
            
            with col_info:
                st.subheader(f"Decreto {dec['nro_decreto']}/{dec['anio']}")
                
                # Mostrar origen si proviene de una Solicitud de Financiamiento
                sol_asoc = db.get_solicitud_por_decreto(dec_id)
                if sol_asoc:
                    st.info(f"📑 **Decreto originado desde la Solicitud de Financiamiento Exp: {sol_asoc['nro_expediente']} (Aprobada)**")
                    
                st.write(f"**Expediente:** {dec['nro_expediente']}")
                if dec.get('expediente_imuh'):
                    parts = [p.strip() for p in dec['expediente_imuh'].split(',') if p.strip()]
                    imuh_con_nombres = []
                    obras_all = db.get_obras()
                    mapa_imuh_nombres = {o['expediente_imuh'].strip(): o['nombre'] for o in obras_all if o.get('expediente_imuh')}
                    for p in parts:
                        nombre = mapa_imuh_nombres.get(p)
                        if nombre:
                            imuh_con_nombres.append(f"{p} ({nombre})")
                        else:
                            imuh_con_nombres.append(p)
                    exp_imuh_disp = ', '.join(imuh_con_nombres)
                else:
                    exp_imuh_disp = "Expediente IMUH sin asignar"
                    
                st.write(f"**Expediente IMUH:** {exp_imuh_disp}")
                
                with st.expander("✏️ Editar solo Expediente IMUH"):
                    with st.form("form_quick_imuh"):
                        new_imuh = st.text_input("Nuevo Expediente IMUH", value=dec.get('expediente_imuh', ''), help="Formato: 8XXXXXX-Y-AAAA.")
                        st.caption("💡 Puedes ingresar varios separados por coma, punto y coma, o barra. Ej: `8000063-I-2026, 8000064-I-2026`")
                        if st.form_submit_button("Guardar IMUH"):
                            if not utils.validar_expediente_imuh(new_imuh):
                                st.error("El Expediente IMUH tiene un formato inválido. Asegúrese que cada uno respete 8XXXXXX-Y-AAAA.")
                            else:
                                exp_imuh_val = utils.normalizar_expediente_imuh(new_imuh)
                                db.update_decreto(dec_id, dec['nro_decreto'], dec['anio'], dec['nro_expediente'], dec['destino_fondos'], dec['pdf_path'], exp_imuh_val)
                                st.success("Expediente IMUH actualizado.")
                                st.rerun()

                st.write(f"**Destino:** {dec['destino_fondos']}")
                simbolo_mon = dec.get('moneda_simbolo') or '$'
                codigo_mon = dec.get('moneda_codigo') or 'ARS'
                nombre_mon = dec.get('moneda_nombre') or 'Pesos Argentinos'
                st.write(f"**Moneda:** {codigo_mon} ({nombre_mon}) - Símbolo: `{simbolo_mon}`")
                
                estado_color = "red" if dec['estado'] == 'Con deuda' else ("green" if dec['estado'] == 'Terminado' else ("blue" if dec['estado'] == 'Vigente' else "gray"))
                st.markdown(f"**Estado General:** :{estado_color}[{dec['estado']}]")
                
                if dec['pdf_path'] and os.path.exists(dec['pdf_path']):
                    st.write("📄 **PDF Adjunto disponible:**")
                    with open(dec['pdf_path'], "rb") as f:
                        st.download_button("📥 Descargar PDF para Ver", f, file_name=os.path.basename(dec['pdf_path']), key="btn_desc_dec")
                else:
                    st.write("No hay PDF adjunto.")
            
            with col_actions:
                st.write("**Acciones:**")
                # Botón de anular
                if dec['estado'] != 'Anulado':
                    confirma_anular = st.checkbox("Confirmar anulación", key=f"chk_anular_{dec_id}")
                    if st.button("🚫 Anular Decreto", use_container_width=True, disabled=not confirma_anular):
                        db.update_estado_decreto(dec_id, 'Anulado')
                        st.success("Decreto anulado.")
                        st.rerun()
                
                # Botón de eliminar archivo
                if dec['pdf_path']:
                    if st.button("🗑️ Eliminar Archivo PDF", use_container_width=True):
                        utils.delete_file(dec['pdf_path'])
                        db.update_decreto(dec_id, dec['nro_decreto'], dec['anio'], dec['nro_expediente'], dec['destino_fondos'], None)
                        st.success("Archivo eliminado.")
                        st.rerun()
                
                # Eliminación completa (Cascada)
                st.divider()
                st.info("Eliminar decreto borrará también cuotas y cobros.")
                # We need a confirmation but streamlit buttons are tricky, let's use a checkbox + button
                confirma = st.checkbox("Estoy seguro de eliminar")
                if st.button("💀 Eliminar Decreto Completo", use_container_width=True, disabled=not confirma):
                    try:
                        db.delete_decreto(dec_id)
                        utils.delete_file(dec['pdf_path'])
                        st.session_state["success_msg_dec"] = "Decreto eliminado correctamente."
                        st.rerun()
                    except ValueError as e:
                        st.error(str(e))
            
            # Movimientos Internos de Fondos
            prestamos = db.get_prestamos(dec_id)
            if prestamos:
                pendientes = [p for p in prestamos if p['devolucion_estado'] == 'Pendiente']
                if pendientes:
                    total_prestado = sum(p['monto'] for p in pendientes)
                    st.warning(f"⚠️ **Atención:** Este decreto tiene **{utils.format_currency_ar(total_prestado)}** prestados temporalmente a otras obras/urgencias. (Ve a la pestaña '💸 Préstamos Internos' para más detalles).")

            st.markdown("### Estado de Cuotas")
            # Presentar cuotas y su estado de cobro (desglosado por pagos parciales)
            tabla_cuotas = []
            total_proyectado = 0
            total_cobrado = 0
            
            for cuota in cuotas:
                monto_q = cuota['monto']
                total_proyectado += monto_q
                
                # Cobros de esta cuota
                cobro_list = [c for c in cobros if c['cuota_id'] == cuota['id']]
                due_date = utils.get_due_date(cuota['mes'], cuota['anio'])
                today_date = datetime.date.today()
                
                is_anulado = (dec.get('estado') == 'Anulado')
                
                if not cobro_list:
                    # Sin cobros
                    if is_anulado:
                        estado_cuota = "🚫 Decreto anulado"
                    else:
                        atrasado = today_date > due_date
                        estado_cuota = "🔴 Atrasado" if atrasado else "🟢 Al día"
                        
                    tabla_cuotas.append({
                        "ID Cuota": cuota['id'],
                        "Periodo": f"{cuota['mes']:02d}/{cuota['anio']}",
                        "Vencimiento": utils.format_date_ar(due_date),
                        "Proyectado": monto_q,
                        "Cobrado": 0.0,
                        "Fecha Cobro": "-",
                        "Saldo": monto_q,
                        "Estado": estado_cuota
                    })
                else:
                    saldo_acumulado = monto_q
                    for c_idx, c_item in enumerate(sorted(cobro_list, key=lambda x: x['fecha'])):
                        monto_c = c_item['monto']
                        total_cobrado += monto_c
                        saldo_acumulado -= monto_c
                        
                        atrasado = utils.is_late(cuota['mes'], cuota['anio'], c_item['fecha'])
                        
                        if saldo_acumulado <= 0.01:
                            estado_str = "✅ Cobrado"
                            if atrasado:
                                estado_str += " (Tarde)"
                        else:
                            if is_anulado:
                                estado_str = "🚫 Decreto anulado (Parcial)"
                            else:
                                estado_str = "🟢 Parcial"
                                if atrasado:
                                    estado_str += " 🔴 Atrasado"
                        
                        tabla_cuotas.append({
                            "ID Cuota": cuota['id'],
                            "Periodo": f"{cuota['mes']:02d}/{cuota['anio']}",
                            "Vencimiento": utils.format_date_ar(due_date),
                            "Proyectado": monto_q,
                            "Cobrado": monto_c,
                            "Fecha Cobro": utils.format_date_ar(c_item['fecha']),
                            "Saldo": max(0, saldo_acumulado),
                            "Estado": estado_str
                        })
                
            df_tc = pd.DataFrame(tabla_cuotas)
            
            # Aplicar formato de moneda para visualización
            df_tc['Proyectado'] = df_tc['Proyectado'].apply(lambda x: utils.format_currency_ar(x))
            df_tc['Cobrado'] = df_tc['Cobrado'].apply(lambda x: utils.format_currency_ar(x))
            df_tc['Saldo'] = df_tc['Saldo'].apply(lambda x: utils.format_currency_ar(x))
            
            st.dataframe(
                df_tc, 
                use_container_width=True, 
                hide_index=True,
                column_config={
                    "ID Cuota": st.column_config.NumberColumn(format="%d"),
                    "Proyectado": "Proyectado",
                    "Cobrado": "Cobrado",
                    "Saldo": "Saldo",
                }
            )
            
            st.write(f"**Total Proyectado:** {utils.format_currency_ar(total_proyectado)} | **Total Cobrado:** {utils.format_currency_ar(total_cobrado)} | **Saldo Total:** {utils.format_currency_ar(total_proyectado - total_cobrado)}")
            
            st.markdown("---")
            st.markdown("### Editar Decreto (Datos Generales)")
            with st.expander("Modificar datos de este decreto"):
                obras_totales = db.get_obras()
                obras_asociadas = db.get_obras_by_decreto(dec_id)
                obras_asociadas_ids = [o['id'] for o in obras_asociadas]
                
                obras_opc_edit = {o['id']: f"{o['expediente_imuh']} - {o['nombre']}" for o in obras_totales}
                
                if f"edit_decreto_obras_ids_{dec_id}" not in st.session_state:
                    st.session_state[f"edit_decreto_obras_ids_{dec_id}"] = obras_asociadas_ids
                
                e_nro = st.number_input("Nro", value=dec['nro_decreto'], min_value=1, step=1, key=f"edit_dec_nro_{dec_id}")
                e_anio = st.number_input("Año", value=dec['anio'], step=1, key=f"edit_dec_anio_{dec_id}")
                e_exp = st.text_input("Expediente Municipal", value=dec['nro_expediente'], key=f"edit_dec_exp_{dec_id}")
                
                monedas_cat = db.get_monedas_indices(solo_activas=True)
                monedas_dict_ed = {m['id']: f"{m['codigo']} - {m['nombre']} ({m['simbolo']})" for m in monedas_cat}
                curr_mon_id = dec.get('moneda_id') or 1
                keys_list = list(monedas_dict_ed.keys())
                idx_mon = keys_list.index(curr_mon_id) if curr_mon_id in keys_list else 0
                e_moneda_id = st.selectbox("Moneda del Decreto", options=keys_list, format_func=lambda x: monedas_dict_ed[x], index=idx_mon, key=f"edit_dec_mon_{dec_id}")
                
                # Selector de obras interactivo en edición de decreto
                st.write("Obras del Catálogo Asociadas *")
                col_sel_ed, col_btn_ed = st.columns([3, 1.2])
                disponibles_ed = {k: v for k, v in obras_opc_edit.items() if k not in st.session_state[f"edit_decreto_obras_ids_{dec_id}"]}
                
                if disponibles_ed:
                    sel_obra_ed = col_sel_ed.selectbox("Buscar obra", options=list(disponibles_ed.keys()), format_func=lambda x: disponibles_ed[x], label_visibility="collapsed", key=f"sel_dec_edit_{dec_id}")
                    if col_btn_ed.button("Agregar obra", use_container_width=True, key=f"btn_add_dec_edit_{dec_id}"):
                        st.session_state[f"edit_decreto_obras_ids_{dec_id}"].append(sel_obra_ed)
                        st.rerun()
                else:
                    col_sel_ed.info("Todas las obras ya fueron agregadas.")
                
                # Listado interactivo
                e_obras_sel = st.session_state[f"edit_decreto_obras_ids_{dec_id}"]
                if e_obras_sel:
                    for o_id in list(e_obras_sel):
                        obra_obj = db.get_obra(o_id)
                        if obra_obj:
                            col_info_ed, col_del_ed = st.columns([4, 1])
                            col_info_ed.info(f"🏗️ {obra_obj['expediente_imuh']} - {obra_obj['nombre']}")
                            
                            confirm_key = f"confirm_del_dec_edit_{o_id}_{dec_id}"
                            if st.session_state.get("confirm_delete_obra") == confirm_key:
                                col_info_ed.warning(f"⚠️ ¿Confirmas que deseas desvincular la obra '{obra_obj['nombre']}' del decreto?")
                                col_si, col_no = col_info_ed.columns(2)
                                if col_si.button("Sí, desvincular", key=f"yes_{confirm_key}"):
                                    st.session_state[f"edit_decreto_obras_ids_{dec_id}"].remove(o_id)
                                    del st.session_state["confirm_delete_obra"]
                                    st.rerun()
                                if col_no.button("Cancelar", key=f"no_{confirm_key}"):
                                    del st.session_state["confirm_delete_obra"]
                                    st.rerun()
                            else:
                                if col_del_ed.button("Borrar", key=f"del_{confirm_key}"):
                                    st.session_state["confirm_delete_obra"] = confirm_key
                                    st.rerun()
                else:
                    st.warning("⚠️ Debe asociar al menos una obra al decreto.")
                
                # Advertencias de cruce de decretos
                obras_con_otros_decretos = []
                for o_id in e_obras_sel:
                    otros_decretos = [d for d in db.get_decretos_by_obra(o_id) if d['id'] != dec_id]
                    if otros_decretos:
                        obra_obj = db.get_obra(o_id)
                        dec_strs = ", ".join(f"{d['nro_decreto']}/{d['anio']}" for d in otros_decretos)
                        obras_con_otros_decretos.append(f"- **{obra_obj['nombre']}**: ya está en Decreto(s) {dec_strs}")
                        
                confirmar_cruce_edit = False
                if obras_con_otros_decretos:
                    st.warning("⚠️ **Advertencia de Obras duplicadas en Decretos:**\n" + "\n".join(obras_con_otros_decretos))
                    confirmar_cruce_edit = st.checkbox("Confirmo que deseo asociar estas obras a pesar de estar en otros decretos", key=f"chk_cruce_edit_{dec_id}")
                
                # Validación manual de expediente duplicado
                exp_existe = db.check_expediente_exists(e_exp, exclude_id=dec_id)
                confirmar_duplicado_edit = False
                if exp_existe:
                    st.warning(f"⚠️ El expediente municipal '{e_exp}' ya está vinculado a otro decreto.")
                    confirmar_duplicado_edit = st.checkbox("Confirmar uso de expediente duplicado", key=f"chk_exp_dup_edit_{dec_id}")
                    
                e_sub = st.button("Actualizar", type="primary", key=f"btn_save_dec_edit_{dec_id}")
                if e_sub:
                    if exp_existe and not confirmar_duplicado_edit:
                        st.error("Debe confirmar el uso del expediente duplicado.")
                    elif obras_con_otros_decretos and not confirmar_cruce_edit:
                        st.error("Debe confirmar la asociación de obras duplicadas en otros decretos.")
                    elif not e_obras_sel:
                        st.error("Debe seleccionar al menos una obra para el decreto.")
                    else:
                        # Auto-generar campos heredados destino_fondos y expediente_imuh
                        selected_obras_objs = [db.get_obra(oid) for oid in e_obras_sel]
                        e_dest = " + ".join(o['nombre'] for o in selected_obras_objs)
                        e_exp_imuh = ", ".join(o['expediente_imuh'] for o in selected_obras_objs)
                        
                        db.update_decreto(dec_id, e_nro, e_anio, e_exp, e_dest, dec['pdf_path'], e_exp_imuh, e_moneda_id)
                        db.add_decreto_obras(dec_id, e_obras_sel)
                        
                        # Limpiar session state del selector para este decreto
                        if f"edit_decreto_obras_ids_{dec_id}" in st.session_state:
                            del st.session_state[f"edit_decreto_obras_ids_{dec_id}"]
                            
                        st.success("Decreto actualizado correctamente.")
                        st.rerun()

# --- TAB 2: NUEVO DECRETO ---
with tab2:
    if "success_msg" in st.session_state:
        st.success(st.session_state["success_msg"])
        del st.session_state["success_msg"]
        
    st.subheader("Cargar Nuevo Decreto")
    
    # Vincular con Solicitud de Financiamiento pendiente
    solicitudes_pendientes = [s for s in db.get_solicitudes() if s['estado'] == 'Pendiente']
    opciones_sol = ["(Cargar decreto sin pedido de financiamiento asociado)"] + [
        f"ID Solicitud: {s['id']} | Exp: {s['nro_expediente']} | {s['destino_fondos']} ({utils.format_currency_ar(s['monto_solicitado'])})"
        for s in solicitudes_pendientes
    ]
    
    sol_seleccionada_str = st.selectbox(
        "¿Este decreto corresponde a un pedido de financiamiento pendiente?", 
        options=opciones_sol,
        key="sel_solicitud_asoc"
    )
    
    sol_id_asoc = None
    default_exp = ""
    default_monto = 0.01
    
    if sol_seleccionada_str != "(Cargar decreto sin pedido de financiamiento asociado)":
        sol_id_asoc = int(sol_seleccionada_str.split(" | ")[0].replace("ID Solicitud: ", ""))
        sol_asoc = next(s for s in solicitudes_pendientes if s['id'] == sol_id_asoc)
        default_exp = sol_asoc['nro_expediente']
        default_monto = float(sol_asoc['monto_solicitado'])
        
    col1, col2, col3 = st.columns([1, 1, 1])
    nro_decreto = col1.number_input("Nro. Decreto *", min_value=1, step=1, key="in_nro_dec")
    anio_decreto = col2.number_input("Año *", min_value=2000, max_value=2100, value=datetime.date.today().year, step=1, key="in_anio_dec")
    monedas_cat_new = db.get_monedas_indices(solo_activas=True)
    monedas_dict_new = {m['id']: f"{m['codigo']} - {m['nombre']} ({m['simbolo']})" for m in monedas_cat_new}
    sel_moneda_id_new = col3.selectbox("Moneda / Índice *", options=list(monedas_dict_new.keys()), format_func=lambda x: monedas_dict_new[x], index=0, key="in_moneda_new_dec")
    
    if sol_id_asoc is not None:
        nro_expediente = default_exp
        st.info(f"📁 **Nro. Expediente Municipal (Asociado del Pedido):** `{nro_expediente}`")
    else:
        nro_expediente = st.text_input("Nro. Expediente Municipal * (Ej: OE-5732-M-2025)", value=default_exp, key="in_exp")
    
    selected_obras_new = []
    
    if sol_id_asoc is not None:
        sol_asoc_obj = db.get_solicitud(sol_id_asoc)
        if sol_asoc_obj and sol_asoc_obj['expediente_imuh']:
            imuh_parts = [p.strip() for p in sol_asoc_obj['expediente_imuh'].split(',') if p.strip()]
            resolved_obras_objs = []
            resolved_obras_ids = []
            for part in imuh_parts:
                o_obj = db.get_obra_by_expediente(part)
                if o_obj:
                    resolved_obras_objs.append(o_obj)
                    resolved_obras_ids.append(o_obj['id'])
            if resolved_obras_objs:
                st.info("🏗️ **Obras asociadas automáticamente (del Pedido):**")
                for o_obj in resolved_obras_objs:
                    st.markdown(f"- {o_obj['expediente_imuh']} - {o_obj['nombre']}")
                selected_obras_new = resolved_obras_ids
    else:
        # Filtrar obras vinculadas a solicitudes activas (Pendientes)
        sols_totales = db.get_solicitudes()
        imuhs_pendientes = set()
        for s in sols_totales:
            if s['estado'] == 'Pendiente' and s.get('expediente_imuh'):
                parts = [p.strip() for p in s['expediente_imuh'].split(',') if p.strip()]
                imuhs_pendientes.update(parts)
                
        obras_totales = db.get_obras()
        obras_disponibles = [o for o in obras_totales if o.get('expediente_imuh') and o['expediente_imuh'].strip() not in imuhs_pendientes]
        obras_opc_new = {o['id']: f"{o['expediente_imuh']} - {o['nombre']}" for o in obras_disponibles}

        if "new_decreto_obras_ids" not in st.session_state:
            st.session_state["new_decreto_obras_ids"] = []
            
        st.write("Seleccione Obras del Catálogo Asociadas *")
        col_sel_nd, col_btn_nd = st.columns([3, 1.2])
        disponibles_nd = {k: v for k, v in obras_opc_new.items() if k not in st.session_state["new_decreto_obras_ids"]}
        
        if disponibles_nd:
            sel_obra_nd = col_sel_nd.selectbox("Buscar obra", options=list(disponibles_nd.keys()), format_func=lambda x: disponibles_nd[x], label_visibility="collapsed", key="sel_obra_new_dec")
            if col_btn_nd.button("Agregar obra", use_container_width=True, key="btn_add_obra_new_dec"):
                st.session_state["new_decreto_obras_ids"].append(sel_obra_nd)
                st.rerun()
        else:
            col_sel_nd.info("Todas las obras ya fueron agregadas.")
            
        # Listado interactivo
        if st.session_state["new_decreto_obras_ids"]:
            for o_id in list(st.session_state["new_decreto_obras_ids"]):
                obra_obj = db.get_obra(o_id)
                if obra_obj:
                    col_info_nd, col_del_nd = st.columns([4, 1])
                    col_info_nd.info(f"🏗️ {obra_obj['expediente_imuh']} - {obra_obj['nombre']}")
                    
                    confirm_key = f"confirm_del_new_dec_{o_id}"
                    if st.session_state.get("confirm_delete_obra") == confirm_key:
                        col_info_nd.warning(f"⚠️ ¿Confirmas que deseas quitar la obra '{obra_obj['nombre']}'?")
                        col_si, col_no = col_info_nd.columns(2)
                        if col_si.button("Sí, quitar", key=f"yes_{confirm_key}"):
                            st.session_state["new_decreto_obras_ids"].remove(o_id)
                            del st.session_state["confirm_delete_obra"]
                            st.rerun()
                        if col_no.button("Cancelar", key=f"no_{confirm_key}"):
                            del st.session_state["confirm_delete_obra"]
                            st.rerun()
                    else:
                        if col_del_nd.button("Borrar", key=f"del_{confirm_key}"):
                            st.session_state["confirm_delete_obra"] = confirm_key
                            st.rerun()
        else:
            st.warning("⚠️ No se ha seleccionado ninguna obra para el decreto.")
            
        selected_obras_new = st.session_state["new_decreto_obras_ids"]
        
    obras_con_otros_decretos_new = []
    for o_id in selected_obras_new:
        otros_decretos = db.get_decretos_by_obra(o_id)
        if otros_decretos:
            obra_obj = db.get_obra(o_id)
            dec_strs = ", ".join(f"{d['nro_decreto']}/{d['anio']}" for d in otros_decretos)
            obras_con_otros_decretos_new.append(f"- **{obra_obj['nombre']}**: ya está en Decreto(s) {dec_strs}")
            
    confirmar_cruce_nuevo = False
    if obras_con_otros_decretos_new:
        st.warning("⚠️ **Advertencia de Obras duplicadas en Decretos:**\n" + "\n".join(obras_con_otros_decretos_new))
        confirmar_cruce_nuevo = st.checkbox("Confirmo que deseo asociar estas obras a pesar de estar en otros decretos", key="chk_cruce_new")
    
    monto_total = st.number_input("Monto Total del Decreto * ($)", min_value=0.01, value=default_monto, step=1000.0, key="in_monto")
    
    pdf_file = st.file_uploader("Adjuntar PDF del Decreto (Opcional)", type=["pdf"], key="in_pdf")
    
    st.markdown("### Cuotas")
    st.info("Ingresa las cuotas a continuación. Puedes usar la tabla para añadir cuotas manualmente o usar el botón para auto-agregar el mes consecutivo:")
    
    MONTHS = ["1 - Enero", "2 - Febrero", "3 - Marzo", "4 - Abril", "5 - Mayo", "6 - Junio", 
              "7 - Julio", "8 - Agosto", "9 - Septiembre", "10 - Octubre", "11 - Noviembre", "12 - Diciembre"]
              
    if 'cuotas_base' not in st.session_state:
        mes_actual = MONTHS[datetime.date.today().month - 1]
        st.session_state.cuotas_base = pd.DataFrame([{"Mes": mes_actual, "Año": datetime.date.today().year, "Monto ($)": 0.01}])

    edited_cuotas = st.data_editor(
        st.session_state.cuotas_base, 
        num_rows="dynamic", 
        use_container_width=True,
        key="editor_cuotas_key",
        column_config={
            "Mes": st.column_config.SelectboxColumn("Mes", options=MONTHS, required=True),
            "Año": st.column_config.NumberColumn("Año", min_value=2000, max_value=2100, step=1, required=True),
            "Monto ($)": st.column_config.NumberColumn("Monto ($)", min_value=0.01, step=0.01, required=True)
        }
    )
    
    # Interceptar cuando el usuario añade una fila vía TAB o la UI nativa
    mask_empty = edited_cuotas['Mes'].isna()
    if mask_empty.any():
        df = edited_cuotas.copy()
        for idx in df[mask_empty].index:
            if idx > 0:
                prev_row = df.loc[idx - 1]
                try: curr_mes_idx = MONTHS.index(prev_row["Mes"])
                except: curr_mes_idx = 0
                curr_anio = int(prev_row["Año"]) if not pd.isna(prev_row["Año"]) else datetime.date.today().year
                next_mes_idx = (curr_mes_idx + 1) % 12
                next_anio = curr_anio + 1 if next_mes_idx == 0 else curr_anio
            else:
                next_mes_idx = datetime.date.today().month - 1
                next_anio = datetime.date.today().year

            df.at[idx, 'Mes'] = MONTHS[next_mes_idx]
            df.at[idx, 'Año'] = next_anio
            
            # Auto completado de saldo
            current_sum = pd.to_numeric(df.loc[:idx-1, "Monto ($)"], errors='coerce').sum()
            remain = monto_total - current_sum
            df.at[idx, 'Monto ($)'] = max(0.01, remain)
            
        st.session_state.cuotas_base = df
        if "editor_cuotas_key" in st.session_state:
            del st.session_state["editor_cuotas_key"]
        st.rerun()

    if st.button("➕ Auto-agregar Mes Consecutivo"):
        df = edited_cuotas.copy()
        if not df.empty:
            last_row = df.iloc[-1]
            try:
                curr_mes_idx = MONTHS.index(last_row["Mes"])
            except:
                curr_mes_idx = 0
            curr_anio = int(last_row["Año"])
            
            next_mes_idx = (curr_mes_idx + 1) % 12
            next_anio = curr_anio + 1 if next_mes_idx == 0 else curr_anio
            
            # Auto completado de saldo
            current_sum = pd.to_numeric(df["Monto ($)"], errors='coerce').sum()
            remain = monto_total - current_sum
            
            new_row = {"Mes": MONTHS[next_mes_idx], "Año": next_anio, "Monto ($)": max(0.01, remain)}
            df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
            st.session_state.cuotas_base = df
            if "editor_cuotas_key" in st.session_state:
                del st.session_state["editor_cuotas_key"]
            st.rerun()

    # Calcular total al vuelo
    total_edited = pd.to_numeric(edited_cuotas["Monto ($)"], errors='coerce').sum() if not edited_cuotas.empty else 0.0
    
    col_sum1, col_sum2 = st.columns(2)
    with col_sum1:
        st.write(f"Monto Total del Decreto: **{utils.format_currency_ar(monto_total)}**")
    with col_sum2:
        st.write(f"Suma de Cuotas Cargadas: **{utils.format_currency_ar(total_edited)}**")
    
    if abs(total_edited - monto_total) > 0.01 and total_edited > 0:
        st.warning("⚠️ La sumatoria de las cuotas no coincide con el monto total.")
        
    if sol_id_asoc is not None:
        sol_asoc = next(s for s in solicitudes_pendientes if s['id'] == sol_id_asoc)
        if abs(monto_total - float(sol_asoc['monto_solicitado'])) > 0.01:
            st.info(f"💡 **Nota:** La solicitud de financiamiento asociada requiere **{utils.format_currency_ar(sol_asoc['monto_solicitado'])}**, pero el monto del decreto es **{utils.format_currency_ar(monto_total)}**.")
    
    # Validación preventiva de duplicados para mostrar checkbox
    exp_existe_nuevo = False
    confirmar_duplicado_nuevo = False
    if nro_expediente:
        if db.check_expediente_exists(nro_expediente):
            exp_existe_nuevo = True
            st.warning(f"⚠️ El expediente '{nro_expediente}' ya fue ingresado previamente en otro decreto.")
            confirmar_duplicado_nuevo = st.checkbox("Confirmar ingreso de expediente duplicado", key="in_exp_dup_new")

    submit = st.button("Guardar Decreto", type="primary", use_container_width=True)
    if submit:
        # Validations
        if not nro_decreto or not anio_decreto or not nro_expediente:
            st.error("Por favor completa los campos obligatorios (*).")
        elif not selected_obras_new:
            st.error("Debe asociar al menos una obra al decreto.")
        elif obras_con_otros_decretos_new and not confirmar_cruce_nuevo:
            st.error("Debe confirmar la asociación de obras duplicadas en otros decretos.")
        elif edited_cuotas.empty or edited_cuotas["Monto ($)"].isna().any():
            st.error("Debes ingresar al menos una cuota válida y completa.")
        elif edited_cuotas["Mes"].isna().any() or edited_cuotas["Año"].isna().any():
            st.error("Mes y Año son obligatorios en las cuotas.")
        elif any(pd.to_numeric(edited_cuotas["Monto ($)"], errors='coerce') <= 0):
            st.error("El monto de cada cuota debe ser mayor a 0.")
        elif abs(total_edited - float(monto_total)) > 0.01:
            st.error(f"La sumatoria de las cuotas ({utils.format_currency_ar(total_edited)}) debe ser exactamente igual al Monto Total cargado ({utils.format_currency_ar(monto_total)}).")
        elif exp_existe_nuevo and not confirmar_duplicado_nuevo:
            st.error(f"El número de expediente '{nro_expediente}' ya existe. Debe confirmar su ingreso duplicado marcando el checkbox de arriba.")
        else:
            try:
                pdf_path = utils.save_uploaded_file(pdf_file) if pdf_file else None
                # Auto-generar campos heredados destino y expediente_imuh
                selected_obras_objs = [db.get_obra(oid) for oid in selected_obras_new]
                destino = " + ".join(o['nombre'] for o in selected_obras_objs)
                exp_imuh_val = ", ".join(o['expediente_imuh'] for o in selected_obras_objs)
                
                d_id = db.add_decreto(int(nro_decreto), int(anio_decreto), nro_expediente, destino, pdf_path, exp_imuh_val, sel_moneda_id_new)
                db.add_decreto_obras(d_id, selected_obras_new)
                
                for _, row in edited_cuotas.iterrows():
                    mes_int = int(str(row['Mes']).split(" - ")[0])
                    db.add_cuota(d_id, mes_int, int(row['Año']), float(row['Monto ($)']))
                
                st.session_state["success_msg_dec"] = f"Decreto N° {nro_decreto}/{anio_decreto} creado con éxito."
                
                # Si hay solicitud asociada, vincular y aprobar
                if sol_id_asoc is not None:
                    db.update_estado_solicitud(sol_id_asoc, 'Aprobado', d_id)
                
                # Clear state
                for key in ["in_nro_dec", "in_anio_dec", "in_exp", "in_monto", "in_pdf", "cuotas_base", "editor_cuotas_key", "sel_solicitud_asoc", "in_obras_new", "new_decreto_obras_ids", "in_moneda_new_dec"]:
                    if key in st.session_state:
                        del st.session_state[key]
                st.rerun()
            except Exception as e:
                st.error(f"Error al guardar: {e}")
