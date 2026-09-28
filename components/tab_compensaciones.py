import streamlit as st
import importlib
import utils
import backend_compensaciones as backend
importlib.reload(backend)

def render():
    st.subheader("⚖️ Compensación Automática de Saldos Cruzados")
    st.markdown("Analiza la base de datos completa para encontrar pares de obras que se deban dinero mutuamente.")
    
    with st.spinner("Buscando saldos cruzados..."):
        pares = backend.calcular_saldos_cruzados_globales()
        
    if not pares:
        st.success("¡Excelente! No se encontraron saldos cruzados pendientes de compensación.")
    else:
        st.info(f"Se encontraron {len(pares)} pares de obras con saldos cruzados.")
        for p in pares:
            with st.expander(f"🔄 {p['O1_name']} ↔ {p['O2_name']}"):
                col1, col2 = st.columns(2)
                col1.metric(f"Le debe a {p['O2_name']}", utils.format_currency_ar(p['deuda_O1_to_O2']))
                col2.metric(f"Le debe a {p['O1_name']}", utils.format_currency_ar(p['deuda_O2_to_O1']))
                
                max_comp = p['monto_maximo']
                
                c_monto, c_btn = st.columns([3, 1])
                with c_monto:
                    monto_input = st.number_input("Monto a compensar:", min_value=0.01, max_value=max_comp, value=max_comp, step=1000.0, key=f"monto_{p['O1']}_{p['O2']}")
                with c_btn:
                    st.write("")
                    st.write("")
                    if st.button("Ejecutar Compensación", key=f"btn_{p['O1']}_{p['O2']}", type="primary", use_container_width=True):
                        with st.spinner("Compensando..."):
                            success, msg = backend.ejecutar_compensacion(p['O1'], p['O2'], monto_input)
                            if success:
                                st.success(msg)
                                st.rerun()
                            else:
                                st.error(msg)

    st.markdown("---")
    st.subheader("📜 Historial de Compensaciones")
    historial = backend.get_historial_compensaciones()
    if not historial:
        st.info("No hay compensaciones registradas.")
    else:
        # Dropdown selection of particular compensation
        opciones_c = {"": "--- Seleccione una compensación para ver su ficha visual ---"}
        for h in historial:
            opciones_c[h['grupo_compensacion_id']] = f"{h['obras_str']} ({utils.format_date_ar(h['fecha'])} - {utils.format_currency_ar(h['monto_compensado'])})"
        
        sel_comp_id = st.selectbox(
            "Seleccione una compensación para ver su ficha de trazabilidad:",
            options=list(opciones_c.keys()),
            format_func=lambda x: opciones_c[x],
            key="selectbox_ficha_compensacion"
        )
        
        if sel_comp_id:
            import database as db
            detalles = db.obtener_detalles_compensacion_grupo(sel_comp_id)
            if detalles:
                desv_item = detalles['desvios'][0] if detalles['desvios'] else None
                res_item = detalles['reservas'][0] if detalles['reservas'] else None
                
                if desv_item and res_item:
                    st.markdown("### 🔗 Ficha de Trazabilidad de Compensación Cruzada")
                    
                    col_card1, col_arrow, col_card2 = st.columns([5, 1, 5])
                    
                    with col_card1:
                        st.info(f"**Decreto Origen A:** Dto. {desv_item['nro_decreto']}/{desv_item['dec_anio']}\n\n"
                                f"**Obra:** {desv_item['desvio_destino']}\n\n"
                                f"**Tipo:** Préstamo (Desvío Inicial)\n\n"
                                f"**Fecha de Pago Original:** {utils.format_date_ar(desv_item['desvio_fecha'])}\n\n"
                                f"**Monto de Pago Original:** {utils.format_currency_ar(desv_item['desvio_monto'])}\n\n"
                                f"**OP Original:** {desv_item.get('desvio_op') or 'Sin OP'}\n\n"
                                f"**Monto Compensado:** {utils.format_currency_ar(desv_item['monto'])}")
                        if st.button(f"🔎 Ver Afectación Dto. {desv_item['nro_decreto']}/{desv_item['dec_anio']}", key="btn_nav_desv"):
                            st.session_state['sel_dec_afectacion'] = desv_item['dec_id']
                            st.session_state['central_report_selector'] = 'afectacion_decretos'
                            st.switch_page("pages/10_Reportes.py")
                            
                    with col_arrow:
                        st.markdown("<h2 style='text-align: center; margin-top: 80px;'>🔄</h2>", unsafe_allow_html=True)
                        
                    with col_card2:
                        st.info(f"**Decreto Origen B:** Dto. {res_item['nro_decreto']}/{res_item['dec_anio']}\n\n"
                                f"**Obra:** {res_item['uso_destino']}\n\n"
                                f"**Tipo:** Préstamo (Uso de Reserva)\n\n"
                                f"**Fecha de Pago Original:** {utils.format_date_ar(res_item['uso_fecha'])}\n\n"
                                f"**Monto de Pago Original:** {utils.format_currency_ar(res_item['uso_monto'])}\n\n"
                                f"**OP Original:** {res_item.get('uso_op') or 'Sin OP'}\n\n"
                                f"**Monto Compensado:** {utils.format_currency_ar(res_item['monto'])}")
                        if st.button(f"🔎 Ver Afectación Dto. {res_item['nro_decreto']}/{res_item['dec_anio']}", key="btn_nav_res"):
                            st.session_state['sel_dec_afectacion'] = res_item['dec_id']
                            st.session_state['central_report_selector'] = 'afectacion_decretos'
                            st.switch_page("pages/10_Reportes.py")
                            
                    st.markdown("---")
        
        for h in historial:
            with st.container():
                st.markdown(f"**🔄 {h['obras_str']}**")
                c1, c2, c3, c4 = st.columns([2, 2, 4, 1])
                c1.write(f"**Fecha:** {utils.format_date_ar(h['fecha'])}")
                c2.write(f"**Monto:** {utils.format_currency_ar(h['monto_compensado'])}")
                c3.caption(f"OPs: {h['ops_str']} | Registros compensados: {h['cant_movimientos']}<br>ID: {h['grupo_compensacion_id']}", unsafe_allow_html=True)
                with c4:
                    undo_key = f"confirm_undo_{h['grupo_compensacion_id']}"
                    if not st.session_state.get(undo_key, False):
                        if st.button("🗑️ Deshacer", key=f"undo_{h['grupo_compensacion_id']}", help="Eliminar registros de compensación", use_container_width=True):
                            st.session_state[undo_key] = True
                            st.rerun()
                    else:
                        st.warning("¿Confirmar?")
                        col_y, col_n = st.columns(2)
                        with col_y:
                            if st.button("Sí", key=f"yes_{h['grupo_compensacion_id']}", type="primary", use_container_width=True):
                                backend.deshacer_compensacion(h['grupo_compensacion_id'])
                                st.session_state[undo_key] = False
                                st.rerun()
                        with col_n:
                            if st.button("No", key=f"no_{h['grupo_compensacion_id']}", use_container_width=True):
                                st.session_state[undo_key] = False
                                st.rerun()
                st.markdown("---")
