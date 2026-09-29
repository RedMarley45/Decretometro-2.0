import streamlit as st
import datetime
import database as db
import utils
from utils import _validar_op_y_notas
from database import DESTINO_RESERVA


def keep_expander_open(c_sel_id):
    st.session_state[f"expander_desv_active_{c_sel_id}"] = True

def render_tab2():
    st.subheader("Distribuir un Cobro Recibido")
    if 'success_msg_dist2' in st.session_state:
        st.success(st.session_state['success_msg_dist2'])
        del st.session_state['success_msg_dist2']
        
    st.info("Asigna cómo se dividieron inicialmente los fondos que ingresaron en el cobro. La suma de todas las partes no puede superar el total cobrado.")
    
    incluir_sin_saldo = st.checkbox("Incluir cobros sin saldo a distribuir", value=False, key="chk_incluir_sin_saldo")
    
    cobros_all = db.get_cobros_con_resumen_distribucion()
    if incluir_sin_saldo:
        cobros_base = cobros_all or []
    else:
        cobros_base = [c for c in (cobros_all or []) if (c['monto'] - c['total_distribuido']) > 0.01]

    if not cobros_base:
        if incluir_sin_saldo:
            st.info("No hay cobros registrados en el sistema.")
        else:
            st.info("No hay cobros con saldo pendiente de distribuir en el sistema. Puede marcar 'Incluir cobros sin saldo a distribuir' para consultar o modificar cobros anteriores.")
    else:
        def format_cobro_dist(c):
            if c.get('origen_tipo') == 'convenio':
                origen_lbl = f"Convenio {c.get('nro_convenio') or c.get('nro_decreto')}"
                cert_txt = ""
                if c.get('nro_certificado'):
                    cert_txt = f" - {c['nro_certificado']}"
                    if c.get('cantidad_moneda_solicitada') and c.get('moneda_codigo') and c.get('moneda_codigo') != 'ARS':
                        cert_txt += f" ({c['cantidad_moneda_solicitada']:,.2f} {c['moneda_codigo']})"
                obra_lbl = c.get('obra_nombre') or c.get('destino_fondos')
                return f"Cobro del {utils.format_date_ar(c['fecha'])} - {utils.format_currency_ar(c['monto'])} - {origen_lbl}{cert_txt} - Obra: {obra_lbl} (Saldo libre: {utils.format_currency_ar(max(0, c['monto'] - c['total_distribuido']))})"
            else:
                origen_lbl = f"Dto. {c['nro_decreto']}/{c['decreto_anio']}"
                return f"Cobro del {utils.format_date_ar(c['fecha'])} - {utils.format_currency_ar(c['monto'])} - {origen_lbl} - Obra: {c['destino_fondos']} (Saldo libre: {utils.format_currency_ar(max(0, c['monto'] - c['total_distribuido']))})"
        
        opciones_c = {c['id']: format_cobro_dist(c) for c in cobros_base}
        options = [None] + list(opciones_c.keys())
        c_sel_id = st.selectbox("1. Seleccione el Cobro a distribuir", options=options, format_func=lambda x: opciones_c[x] if x is not None else "--- Seleccione un cobro para comenzar ---")
        
        if c_sel_id is not None:
            c_sel = next(c for c in cobros_base if c['id'] == c_sel_id)
            dist_bd = db.get_distribucion_by_cobro(c_sel_id)
            desvios = db.get_desvios_by_cobro(c_sel_id)
            tot_desvios = sum(d['monto'] for d in desvios)
            
            val_fin = float(dist_bd['monto_fin_orig']) if dist_bd else 0.0
            val_res = float(dist_bd['monto_reserva']) if dist_bd else 0.0
            val_not = dist_bd['notas'] if dist_bd and dist_bd['notas'] else ""
            
            # Mostrar resumen de distribución actual
            st.markdown("#### Resumen Financiero de este Cobro")
            
            col_met1, col_met2, col_met3, col_met4 = st.columns(4)
            col_met1.metric("Total Cobrado", utils.format_currency_ar(c_sel['monto']))
            col_met2.metric("Fin Original", utils.format_currency_ar(val_fin))
            col_met3.metric("En Reserva", utils.format_currency_ar(val_res))
            col_met4.metric("Desviado", utils.format_currency_ar(tot_desvios))
            
            saldo_pendiente_dist = max(0.0, round(c_sel['monto'] - c_sel['total_distribuido'], 2))
            
            if saldo_pendiente_dist > 0.01:
                st.warning(f"⚠️ **Saldo Pendiente de Distribuir:** {utils.format_currency_ar(saldo_pendiente_dist)}")
            else:
                st.success("🎉 **Cobro totalmente distribuido ($0,00 pendiente).**")
            
            st.markdown("---")
            
            usos_fo = db.get_fin_original_usos_by_cobro(c_sel_id)
            recuperos = db.get_recuperos_by_cobro(c_sel_id)
            
            # Recompute val_fin dynamically from the individual uses and recuperos
            val_fin = sum(u['monto'] for u in usos_fo) + sum(r['monto'] for r in recuperos)
            if dist_bd and abs(val_fin - float(dist_bd['monto_fin_orig'])) > 0.01:
                # auto-heal distribution if mismatch
                db.upsert_distribucion(c_sel_id, val_fin, val_res, val_not)

            with st.form("form_distribucion_reserva"):
                st.write("**A. Guardar en Reserva**")
                st.caption(f"Tienes **{utils.format_currency_ar(saldo_pendiente_dist)}** pendientes de distribuir en este cobro.")
                
                monto_res = st.number_input("Guardado en Reserva ($)", min_value=0.0, value=val_res, step=1000.0, key=f"monto_res_{c_sel_id}")
                notas_dist = st.text_area("Aclaraciones generales de la distribución (opcional)", value=val_not, key=f"notas_dist_{c_sel_id}")
                
                st.caption("Si la suma de Fin Original, Reserva y Desvíos es menor al Total del Cobro, deberás marcar esta casilla para autorizar que quede saldo pendiente sin asignar:")
                confirmar_saldo = st.checkbox("Confirmo dejar saldo pendiente sin distribuir")
                
                if st.form_submit_button("Guardar Reserva", type="primary"):
                    suma_total = c_sel['total_distribuido'] - val_res + monto_res
                    
                    if suma_total > (c_sel['monto'] + 0.01):
                        st.error(f"Error: La nueva suma ({utils.format_currency_ar(suma_total)}) superaría el cobro total ({utils.format_currency_ar(c_sel['monto'])}). Ajuste los montos.")
                    elif suma_total < (c_sel['monto'] - 0.01) and not confirmar_saldo:
                        st.error(f"⚠️ Atención: Quedan {utils.format_currency_ar(c_sel['monto'] - suma_total)} sin distribuir. Si es correcto, marca la casilla de confirmación antes de guardar.")
                    else:
                        db.upsert_distribucion(c_sel_id, val_fin, monto_res, notas_dist)
                        st.success("Distribución de reserva guardada.")
                        st.rerun()
            st.divider()
            
            # --- FORMULARIOS DE REGISTRO (EXPANDERS) ---
            
            # 1. Calcular saldos disponibles para formularios
            saldo_disp_para_fo = max(0.0, c_sel['monto'] - c_sel['total_distribuido'])
            saldo_disp_para_desviar = max(0.0, c_sel['monto'] - c_sel['total_distribuido'])
            
            # Formulario de agregar a pago original (desplegable)
            if f"expander_fo_active_{c_sel_id}" not in st.session_state:
                st.session_state[f"expander_fo_active_{c_sel_id}"] = False
            
            def keep_fo_open():
                st.session_state[f"expander_fo_active_{c_sel_id}"] = True
                
            if saldo_disp_para_fo > 0.01:
                is_exp_fo = st.session_state[f"expander_fo_active_{c_sel_id}"]
                with st.expander("➕ Agregar Pago a Obra Original", expanded=is_exp_fo):
                    c_fo1, c_fo2 = st.columns(2)
                    monto_nuevo_fo = c_fo1.number_input("Monto a pagar ($)", min_value=0.0, max_value=float(saldo_disp_para_fo), value=float(saldo_disp_para_fo), step=1000.0, key=f"new_monto_fo_{c_sel_id}", on_change=keep_fo_open)
                    fecha_nuevo_fo = c_fo2.date_input("Fecha de Pago", value=datetime.date.today(), format="DD-MM-YYYY", key=f"new_fecha_fo_{c_sel_id}", on_change=keep_fo_open)
                    
                    op_nuevo_fo = st.text_input("Número de Orden de Pago", key=f"new_op_fo_{c_sel_id}", on_change=keep_fo_open)
                    notas_nuevo_fo = st.text_area("Observaciones (Obligatorio si no hay OP, 10-30 chars)", max_chars=30, key=f"new_notas_fo_{c_sel_id}", on_change=keep_fo_open)
                    
                    # Obra destino
                    cobro_obra_id = c_sel.get('obra_id')
                    if not cobro_obra_id and c_sel.get('convenio_solicitud_id'):
                        sol_tmp = db.get_solicitud_convenio(c_sel['convenio_solicitud_id'])
                        if sol_tmp:
                            cobro_obra_id = sol_tmp.get('obra_id')
                    
                    obras_del_decreto = db.get_obras_by_decreto(c_sel['decreto_id']) if c_sel.get('decreto_id') else []
                    
                    if cobro_obra_id:
                        target_obra_id = cobro_obra_id
                        obra_obj = db.get_obra(target_obra_id)
                        if obra_obj:
                            st.write(f"**Obra destino:** {obra_obj['expediente_imuh']} - {obra_obj['nombre']}")
                    elif len(obras_del_decreto) >= 1:
                        opciones_obra = {o['id']: f"{o['expediente_imuh']} - {o['nombre']}" for o in obras_del_decreto}
                        default_index = 1 if len(obras_del_decreto) == 1 else 0
                        is_disabled = (len(obras_del_decreto) == 1)
                        obra_id_selected = st.selectbox(
                            "Seleccione la Obra destino del pago", 
                            options=[None] + list(opciones_obra.keys()) if not is_disabled else list(opciones_obra.keys()), 
                            format_func=lambda x: opciones_obra[x] if x is not None else "--- Seleccione una obra ---", 
                            index=0 if is_disabled else default_index,
                            disabled=is_disabled,
                            key=f"sel_obra_fo_{c_sel_id}",
                            on_change=keep_fo_open
                        )
                        target_obra_id = obra_id_selected if obra_id_selected else (obras_del_decreto[0]['id'] if is_disabled else None)
                    else:
                        target_obra_id = None

                    # Verificaciones Bimonetarias y Sobrepago
                    cant_mon_pago = monto_nuevo_fo
                    cotiz_pago = 1.0
                    chk_sp = {'es_sobrepago': False, 'mensaje': ''}
                    resumen_ob = None
                    is_conv = bool(c_sel.get('origen_tipo') == 'convenio' or c_sel.get('convenio_solicitud_id') is not None)
                    
                    if target_obra_id:
                        resumen_ob = db.get_resumen_contrato_obra(target_obra_id)
                        if resumen_ob and resumen_ob['es_bimonetaria']:
                            cod_m = resumen_ob['moneda_codigo']
                            if is_conv:
                                cotiz_display = float(c_sel.get('cotizacion_cobro') or c_sel.get('cotizacion_solicitud') or 1.0)
                                cant_mon_pago = round(monto_nuevo_fo / cotiz_display, 6) if cotiz_display > 0 else 0.0
                                st.info(f"ℹ️ **Imputación automática:** Amortiza **{cant_mon_pago:,.2f} {cod_m}** a cotización **${cotiz_display:,.2f}** heredada del Certificado de Convenio.")
                            else:
                                c_cot1, c_cot2 = st.columns(2)
                                cotiz_pago = c_cot1.number_input(
                                    f"Cotización OP ($ ARS por {cod_m}) *",
                                    min_value=0.0001,
                                    step=10.0,
                                    value=float(resumen_ob.get('cotizacion_base_contrato') or 1.0),
                                    key=f"cotiz_fo_input_{c_sel_id}",
                                    on_change=keep_fo_open
                                )
                                cant_mon_pago = round(monto_nuevo_fo / cotiz_pago, 6) if cotiz_pago > 0 else 0.0
                                c_cot2.write(f"**Amortiza contractualmente:**\n\n`{cant_mon_pago:,.2f} {cod_m}`")
                                
                            chk_sp = db.check_sobrepago_obra(target_obra_id, nuevo_monto_pesos=monto_nuevo_fo, nueva_cantidad_moneda=cant_mon_pago)
                        else:
                            chk_sp = db.check_sobrepago_obra(target_obra_id, nuevo_monto_pesos=monto_nuevo_fo)

                    confirmar_sin_op_fo = False
                    if not op_nuevo_fo.strip():
                        st.warning("⚠️ Si no ingresa el Número de Orden de Pago, deberá completar las observaciones del pago y confirmar.")
                        confirmar_sin_op_fo = st.checkbox("Confirmo que deseo registrar el pago sin OP", key=f"new_chk_op_fo_{c_sel_id}", on_change=keep_fo_open)
                    else:
                        confirmar_sin_op_fo = True
                        
                    confirmar_sobrepago_fo = True
                    motivo_sp_fo = None
                    if chk_sp.get('es_sobrepago'):
                        st.error(f"⚠️ **Atención:** {chk_sp['mensaje']}")
                        confirmar_sobrepago_fo = st.checkbox("Confirmo que deseo sobrepagar el contrato de la obra", key=f"confirmar_sobrepago_fo_{c_sel_id}", on_change=keep_fo_open)
                        motivo_sp_fo = st.text_input("Motivo / Justificación obligatoria del Sobrepago *", key=f"motivo_sp_fo_{c_sel_id}", on_change=keep_fo_open)
                        
                    if st.button("Guardar Pago", key=f"btn_save_fo_{c_sel_id}"):
                        err_op = _validar_op_y_notas(op_nuevo_fo, notas_nuevo_fo, confirmado=confirmar_sin_op_fo)
                        if not target_obra_id:
                            st.error("Debe existir o seleccionarse una obra a la que se imputará este pago.")
                        elif err_op:
                            st.error(err_op)
                        elif monto_nuevo_fo <= 0:
                            st.error("El monto debe ser mayor a 0.")
                        elif chk_sp.get('es_sobrepago') and not confirmar_sobrepago_fo:
                            st.error("Debe confirmar el sobrepago para continuar.")
                        elif chk_sp.get('es_sobrepago') and (not motivo_sp_fo or not motivo_sp_fo.strip()):
                            st.error("Debe ingresar el motivo / justificación obligatoria del sobrepago.")
                        else:
                            nuevo_fo = val_fin + monto_nuevo_fo
                            db.upsert_distribucion(c_sel_id, nuevo_fo, val_res, val_not)
                            is_conv_bim = bool(resumen_ob and resumen_ob.get('es_bimonetaria') and is_conv)
                            db.add_fin_original_uso(
                                cobro_id=c_sel_id,
                                monto=monto_nuevo_fo,
                                fecha=fecha_nuevo_fo.strftime('%Y-%m-%d'),
                                nro_op=op_nuevo_fo.strip() if op_nuevo_fo.strip() else None,
                                notas=notas_nuevo_fo,
                                obra_id=target_obra_id,
                                cantidad_moneda_amortizada=None if is_conv_bim else cant_mon_pago,
                                cotizacion_pago=None if is_conv_bim else cotiz_pago,
                                motivo_sobrepago=motivo_sp_fo.strip() if motivo_sp_fo else None
                            )
                            st.session_state['success_msg_dist2'] = "Pago a Obra Original registrado."
                            st.rerun()
            else:
                st.info("No hay saldo libre para registrar pagos a la obra original.")
                
            # Formulario de Recuperar Adelanto de Fondos Propios (desplegable)
            if f"expander_recupero_active_{c_sel_id}" not in st.session_state:
                st.session_state[f"expander_recupero_active_{c_sel_id}"] = False
            
            def keep_recupero_open():
                st.session_state[f"expander_recupero_active_{c_sel_id}"] = True
                
            if saldo_disp_para_fo > 0.01:
                is_exp_recupero = st.session_state[f"expander_recupero_active_{c_sel_id}"]
                with st.expander("➕ Recuperar Adelanto de Fondos Propios", expanded=is_exp_recupero):
                    cobro_obra_rec_id = c_sel.get('obra_id')
                    obras_del_decreto_rec = db.get_obras_by_decreto(c_sel['decreto_id']) if c_sel.get('decreto_id') else []
                    obra_id_selected_rec = None
                    if cobro_obra_rec_id:
                        obra_id_selected_rec = cobro_obra_rec_id
                        obra_rec_obj = db.get_obra(cobro_obra_rec_id)
                        if obra_rec_obj:
                            st.write(f"**Obra destino del recupero:** {obra_rec_obj['expediente_imuh']} - {obra_rec_obj['nombre']}")
                    elif len(obras_del_decreto_rec) >= 1:
                        opciones_obra_rec = {o['id']: f"{o['expediente_imuh']} - {o['nombre']}" for o in obras_del_decreto_rec}
                        default_index_rec = 1 if len(obras_del_decreto_rec) == 1 else 0
                        is_disabled_rec = (len(obras_del_decreto_rec) == 1)
                        obra_id_selected_rec = st.selectbox(
                            "Seleccione la Obra para la cual se recupera el fondo", 
                            options=[None] + list(opciones_obra_rec.keys()) if not is_disabled_rec else list(opciones_obra_rec.keys()), 
                            format_func=lambda x: opciones_obra_rec[x] if x is not None else "--- Seleccione una obra ---", 
                            index=0 if is_disabled_rec else default_index_rec,
                            disabled=is_disabled_rec,
                            key=f"sel_obra_rec_{c_sel_id}",
                            on_change=keep_recupero_open
                        )
                        
                    tope = 0.0
                    if obra_id_selected_rec:
                        tope = db.get_tope_recupero(obra_id_selected_rec)
                        st.info(f"💡 Tope de recupero para esta obra: **${tope:,.2f}**")
                        
                    max_recupero = min(float(saldo_disp_para_fo), float(tope)) if obra_id_selected_rec else float(saldo_disp_para_fo)
                    
                    c_rec1, c_rec2 = st.columns(2)
                    monto_nuevo_rec = c_rec1.number_input("Monto a recuperar ($)", min_value=0.0, max_value=max_recupero, value=max_recupero, step=1000.0, key=f"new_monto_rec_{c_sel_id}", on_change=keep_recupero_open)
                    fecha_nuevo_rec = c_rec2.date_input("Fecha de Recupero", value=datetime.date.today(), format="DD-MM-YYYY", key=f"new_fecha_rec_{c_sel_id}", on_change=keep_recupero_open)
                    
                    op_nuevo_rec = st.text_input("Número de Orden de Pago (Opcional)", key=f"new_op_rec_{c_sel_id}", on_change=keep_recupero_open)
                    notas_nuevo_rec = st.text_area("Observaciones (Obligatorio si no hay OP)", max_chars=30, key=f"new_notas_rec_{c_sel_id}", on_change=keep_recupero_open)
                        
                    confirmar_sin_op_rec = False
                    if not op_nuevo_rec.strip():
                        st.warning("⚠️ Si no ingresa el Número de Orden de Pago, deberá completar las observaciones y confirmar.")
                        confirmar_sin_op_rec = st.checkbox("Confirmo que deseo registrar el recupero sin OP", key=f"new_chk_op_rec_{c_sel_id}", on_change=keep_recupero_open)
                    else:
                        confirmar_sin_op_rec = True
                        
                    if st.button("Registrar Recupero", key=f"btn_save_rec_{c_sel_id}"):
                        err_op = _validar_op_y_notas(op_nuevo_rec, notas_nuevo_rec, confirmado=confirmar_sin_op_rec)
                        if len(obras_del_decreto_rec) >= 1 and obra_id_selected_rec is None:
                            st.error("Debe seleccionar la obra de la que se recuperan los fondos.")
                        elif err_op:
                            st.error(err_op)
                        elif monto_nuevo_rec <= 0:
                            st.error("El monto debe ser mayor a 0.")
                        else:
                            try:
                                db.add_recupero_fondos_propios(
                                    cobro_id=c_sel_id,
                                    obra_id=obra_id_selected_rec if obra_id_selected_rec else obras_del_decreto_rec[0]['id'],
                                    monto=monto_nuevo_rec,
                                    fecha=fecha_nuevo_rec.strftime('%Y-%m-%d'),
                                    nro_op=op_nuevo_rec.strip() if op_nuevo_rec.strip() else None,
                                    notas=notas_nuevo_rec
                                )
                                nuevo_fo_rec = val_fin + monto_nuevo_rec
                                db.upsert_distribucion(c_sel_id, nuevo_fo_rec, val_res, val_not)
                                st.session_state['success_msg_dist2'] = "Recupero registrado con éxito."
                                st.rerun()
                            except ValueError as e:
                                st.error(str(e))
                
            # Formulario de agregar desvío nuevo (desplegable)
            if f"expander_desv_active_{c_sel_id}" not in st.session_state:
                st.session_state[f"expander_desv_active_{c_sel_id}"] = False
                
            if (st.session_state.get(f"nd_op_{c_sel_id}", "") != "" or 
                st.session_state.get(f"nd_motivo_{c_sel_id}", "") != "" or
                st.session_state.get(f"chk_confirmar_desv_sin_op_{c_sel_id}", False) or
                st.session_state.get(f"tipo_desvio_{c_sel_id}", "Hacia Obra (Catálogo)") != "Hacia Obra (Catálogo)"):
                st.session_state[f"expander_desv_active_{c_sel_id}"] = True
                
            if saldo_disp_para_desviar > 0.01:
                is_exp = st.session_state[f"expander_desv_active_{c_sel_id}"]
                with st.expander("➕ Agregar Nuevo Desvío", expanded=is_exp):
                    st.write("**Atención:** Se recomienda no usar `st.form` aquí para permitir la selección dinámica.")
                    nd_op = st.text_input("Número de Orden de Pago (Desvío)", key=f"nd_op_{c_sel_id}", on_change=keep_expander_open, args=(c_sel_id,))
                    nd_op = ''.join(filter(str.isdigit, nd_op))
                    
                    op_locked_obra = None
                    op_locked_gasto = None
                    op_locked_fecha = None
                    
                    if nd_op:
                        usos_op = db.get_op_usage_details(nd_op)
                        if usos_op:
                            st.info("ℹ️ **Esta OP ya está vinculada a los siguientes pagos:**")
                            for u in usos_op:
                                st.info(f"- {u['origen']} por {utils.format_currency_ar(u['monto'])}")
                            op_locked_fecha = datetime.datetime.strptime(usos_op[0]['fecha'], '%Y-%m-%d').date()
                            st.session_state[f"nd_fecha_{c_sel_id}"] = op_locked_fecha
                            op_info = db.get_op_info(nd_op)
                            if op_info:
                                if op_info['obra_id']: 
                                    op_locked_obra = op_info['obra_id']
                                    st.session_state[f"tipo_desvio_{c_sel_id}"] = "Hacia Obra (Catálogo)"
                                    st.session_state[f"nd_obra_id_{c_sel_id}"] = op_locked_obra
                                if op_info['gasto_id']: 
                                    op_locked_gasto = op_info['gasto_id']
                                    st.session_state[f"tipo_desvio_{c_sel_id}"] = "Hacia Gasto de Funcionamiento (FUN)"
                                    st.session_state[f"nd_gasto_id_sel_{c_sel_id}"] = op_locked_gasto
                                st.warning("⚠️ **OP ya utilizada:** El destino ha sido bloqueado. Si hay un error, elimine los pagos previos.")

                    tipo_opciones_d = ["Hacia Obra (Catálogo)", "Hacia Gasto de Funcionamiento (FUN)"]
                    index_tipo_d = 0
                    if op_locked_obra: index_tipo_d = 0
                    elif op_locked_gasto: index_tipo_d = 1
                    
                    tipo_desvio = st.radio("Destino del Desvío:", tipo_opciones_d, disabled=(op_locked_obra is not None or op_locked_gasto is not None), key=f"tipo_desvio_{c_sel_id}", on_change=keep_expander_open, args=(c_sel_id,))
                    
                    nd_obra_id = None
                    gasto_nombre = ""
                    gasto_expediente_imuh = ""
                    nd_destino = ""
                    
                    if tipo_desvio == "Hacia Obra (Catálogo)":
                        obras_disponibles = db.get_obras(only_active=True)
                        if not obras_disponibles:
                            st.warning("No hay obras activas en el catálogo.")
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
                            nd_obra_id = st.selectbox("Seleccione la Obra Destino", options=list(opc_obras.keys()), disabled=(op_locked_obra is not None), format_func=lambda x: opc_obras[x], key=f"nd_obra_id_{c_sel_id}", on_change=keep_expander_open, args=(c_sel_id,))
                            if nd_obra_id:
                                selected_o = next(o for o in obras_disponibles if o['id'] == nd_obra_id)
                    else:
                        gastos_disponibles = db.get_gastos_funcionamiento(only_active=True)
                        opc_gastos = {g['id']: f"{g['nombre']} (Exp: {g['expediente_imuh']})" for g in gastos_disponibles}
                        
                        gasto_id_sel = st.selectbox("Seleccione el Gasto de Funcionamiento (FUN)", options=list(opc_gastos.keys()), disabled=(op_locked_gasto is not None), format_func=lambda x: opc_gastos[x], key=f"nd_gasto_id_sel_{c_sel_id}", on_change=keep_expander_open, args=(c_sel_id,))
                        
                        if gasto_id_sel:
                            g_selected = next(g for g in gastos_disponibles if g['id'] == gasto_id_sel)
                            gasto_nombre = g_selected['nombre']
                            gasto_expediente_imuh = g_selected['expediente_imuh']
                            nd_destino = gasto_nombre
                            nd_gasto_prov_id = g_selected.get('proveedor_id')
                            p_txt = g_selected.get('proveedor_razon_social') or "Sin proveedor asignado"
                            st.text_input(
                                "Proveedor de Funcionamiento",
                                value=p_txt,
                                disabled=True
                            )
                            st.info(f"💡 **Gasto seleccionado:** {gasto_nombre} (Exp: {gasto_expediente_imuh}) | Proveedor: {p_txt}")
                        else:
                            gasto_nombre = ""
                            gasto_expediente_imuh = ""
                            nd_destino = ""
                            nd_gasto_prov_id = None
                            st.info("ℹ️ No hay gastos de funcionamiento activos en el catálogo. Registrá uno desde el menú 💼 Gastos de Funcionamiento.")
                        
                    nd_monto = st.number_input("Monto a Desviar ($)*", min_value=0.01, max_value=float(saldo_disp_para_desviar), value=float(saldo_disp_para_desviar), step=1000.0, key=f"nd_monto_{c_sel_id}", on_change=keep_expander_open, args=(c_sel_id,))
                    nd_fecha = st.date_input("Fecha del Desvío", key=f"nd_fecha_{c_sel_id}", format="DD-MM-YYYY", disabled=(op_locked_fecha is not None), on_change=keep_expander_open, args=(c_sel_id,))
                    nd_motivo = st.text_area("Motivo de la urgencia / Detalles", max_chars=30, key=f"nd_motivo_{c_sel_id}", on_change=keep_expander_open, args=(c_sel_id,))
                    
                    confirmar_desv_sin_op = False
                    if not nd_op.strip():
                        st.warning("⚠️ Si no informa número de orden de pago, deberá informar los detalles del desvío.")
                        confirmar_desv_sin_op = st.checkbox("Confirmo que deseo registrar el desvío sin número de OP", key=f"chk_confirmar_desv_sin_op_{c_sel_id}", on_change=keep_expander_open, args=(c_sel_id,))
                    else:
                        confirmar_desv_sin_op = True

                    if st.button("Confirmar Desvío", type="primary", key=f"btn_confirmar_desvio_{c_sel_id}"):
                        err_op = _validar_op_y_notas(nd_op, nd_motivo, confirmado=confirmar_desv_sin_op)
                        if tipo_desvio == "Hacia Obra (Catálogo)" and not nd_obra_id:
                            st.error("Debe seleccionar una obra del catálogo.")
                        elif tipo_desvio == "Hacia Gasto de Funcionamiento (FUN)" and not gasto_nombre.strip():
                            st.error("El nombre del gasto de funcionamiento es obligatorio.")
                        elif tipo_desvio == "Hacia Gasto de Funcionamiento (FUN)" and not gasto_expediente_imuh.strip():
                            st.error("El número de expediente IMUH es obligatorio.")
                        elif tipo_desvio == "Hacia Gasto de Funcionamiento (FUN)" and not utils.validar_expediente_imuh(gasto_expediente_imuh):
                            st.error("El número de expediente IMUH no tiene un formato válido (Ej: 8000000-I-2026).")
                        elif tipo_desvio == "Hacia Gasto de Funcionamiento (FUN)" and nd_gasto_prov_id == 0:
                            st.error("Debe seleccionar un Proveedor de Funcionamiento. Ya no se permite 'NO INFORMA PROVEEDOR'.")
                        elif err_op:
                            st.error(err_op)
                        else:
                            try:
                                if tipo_desvio == "Hacia Gasto de Funcionamiento (FUN)":
                                    gasto_exp_norm = utils.normalizar_expediente_imuh(gasto_expediente_imuh)
                                    db.add_desvio(c_sel_id, nd_destino, nd_monto, nd_motivo, nd_fecha.strftime('%Y-%m-%d'), nro_op=nd_op if nd_op.strip() else None, gasto_nombre=gasto_nombre, gasto_expediente_imuh=gasto_exp_norm)
                                else:
                                    db.add_desvio(c_sel_id, nd_destino, nd_monto, nd_motivo, nd_fecha.strftime('%Y-%m-%d'), obra_id=nd_obra_id, nro_op=nd_op if nd_op.strip() else None)
                                
                                # Limpiar campos de session_state para reiniciar el formulario
                                for k in [
                                    f"tipo_desvio_{c_sel_id}",
                                    f"nd_obra_id_{c_sel_id}",
                                    f"nd_gasto_id_sel_{c_sel_id}",
                                    f"nd_gasto_nombre_{c_sel_id}",
                                    f"nd_gasto_exp_{c_sel_id}",
                                    f"nd_monto_{c_sel_id}",
                                    f"nd_fecha_{c_sel_id}",
                                    f"nd_op_{c_sel_id}",
                                    f"nd_motivo_{c_sel_id}",
                                    f"chk_confirmar_desv_sin_op_{c_sel_id}"
                                ]:
                                    if k in st.session_state:
                                        del st.session_state[k]
                                        
                                # Colapsar el expander
                                st.session_state[f"expander_desv_active_{c_sel_id}"] = False
                                
                                st.session_state['success_msg_dist2'] = "Desvío agregado exitosamente."
                                st.rerun()
                            except ValueError as e:
                                st.error(str(e))
            else:
                st.info(f"No hay saldo libre ({utils.format_currency_ar(saldo_disp_para_desviar)}) para nuevos desvíos en este cobro.")
                
            st.divider()
            
            # --- LISTADOS DE MOVIMIENTOS REGISTRADOS ---
            
            # Listado B: Pagos a Obra Original
            st.write("**B. Pagos a Obra Original**")
            st.write(f"Total pagado a la obra: **{utils.format_currency_ar(val_fin)}**")
            
            if usos_fo:
                for u in usos_fo:
                    str_op = f" - OP: {u['nro_op']}" if u['nro_op'] else ""
                    str_notas = f" ({u['notas']})" if u['notas'] else ""
                    str_bimon = f" [Amortiza: {u['cantidad_moneda_amortizada']:,.2f} @ ${u['cotizacion_pago']:,.2f}]" if (u.get('cantidad_moneda_amortizada') and float(u.get('cotizacion_pago') or 1.0) > 1.0) else ""
                    str_sp = f" ⚠️ [Sobrepago: {u['motivo_sobrepago']}]" if u.get('motivo_sobrepago') else ""
                    col_u1.info(f"Pago el {utils.format_date_ar(u['fecha'])}: **{utils.format_currency_ar(u['monto'])}**{str_op}{str_bimon}{str_notas}{str_sp}")
                    if col_u2.button("Borrar", key=f"del_fo_{u['id']}"):
                        db.delete_fin_original_uso(u['id'])
                        nuevo_fo = val_fin - u['monto']
                        db.upsert_distribucion(c_sel_id, nuevo_fo, val_res, val_not)
                        st.session_state['success_msg_dist2'] = "Pago a Obra Original eliminado correctamente."
                        st.rerun()
            else:
                st.caption("No existen pagos a la obra original para este cobro.")
                
            st.write("") # Espaciado
            
            # Listado C: Desvíos a otras obras
            st.write("**C. Desvíos a otras obras**")
            st.write(f"Total Desviado inicialmente: **{utils.format_currency_ar(tot_desvios)}**")
            
            if desvios:
                for d in desvios:
                    col_d1, col_d2 = st.columns([4, 1])
                    saldo_d = d['monto'] - d['total_recuperado']
                    stado_d_str = f"| Debe: {utils.format_currency_ar(saldo_d)}" if saldo_d > 0 else "| Recuperado 100%"
                    col_d1.info(f"Desvío a **{d['destino']}** el {utils.format_date_ar(d['fecha'])}: **{utils.format_currency_ar(d['monto'])}** {stado_d_str}")
                    if col_d2.button("Borrar", key=f"del_desv_{d['id']}"):
                        if d['total_recuperado'] > 0:
                            st.error("No se puede borrar un desvío que ya tiene devoluciones registradas.")
                        else:
                            db.delete_desvio(d['id'])
                            st.session_state['success_msg_dist2'] = "Desvío eliminado correctamente."
                            st.rerun()
            else:
                st.caption("No existen desvíos registrados para este cobro.")

# --- TAB 3: HISTORIAL DE DESVÍOS ---