import streamlit as st
import os, sys
import datetime
import pandas as pd

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import database as db
import importlib
importlib.reload(db)
import utils
importlib.reload(utils)

st.set_page_config(page_title="Convenios | Decretómetro 2.0", page_icon="📜", layout="wide")
utils.inject_style()

st.title("Gestión de Convenios Multiobra 📜")
st.markdown("Administre los convenios de financiamiento y ejecución (Provincia, Nación u otros entes), pactados en **UVIs, USD o Pesos**, vinculados a múltiples obras y controlados en su moneda contractual.")

if "conv_success_msg" in st.session_state and st.session_state.conv_success_msg:
    st.success(st.session_state.conv_success_msg)
    st.session_state.conv_success_msg = ""

tab_gestion, tab_nuevo, tab_comparativa = st.tabs([
    "📋 Ficha y Control del Convenio",
    "➕ Cargar Nuevo Convenio",
    "📊 Comparativa Global de Convenios"
])

monedas_activas = db.get_monedas_indices(solo_activas=True)
monedas_dict = {m['id']: m for m in monedas_activas}

# =============================================================================
# TAB 1: FICHA Y CONTROL DEL CONVENIO
# =============================================================================
with tab_gestion:
    convenios = db.get_convenios()
    
    if not convenios:
        st.info("No hay convenios registrados en el sistema. Utilice la pestaña '➕ Cargar Nuevo Convenio' para registrar el primero.")
    else:
        opciones_conv = {c['id']: f"{c['nro_convenio']} — {c['ente_financiador']} ({c['nombre_convenio']}) [{c['estado']}]" for c in convenios}
        sel_conv_id = st.selectbox("Seleccione el Convenio para auditar o gestionar:", options=list(opciones_conv.keys()), format_func=lambda x: opciones_conv[x])
        
        if sel_conv_id:
            resumen = db.get_resumen_control_convenio(sel_conv_id)
            c_sel = resumen['convenio']
            m_cod = resumen['moneda_codigo']
            m_sim = resumen['moneda_simbolo']
            
            # Encabezado con datos generales
            col_h1, col_h2 = st.columns([3, 1.2])
            with col_h1:
                st.subheader(f"Convenio {c_sel['nro_convenio']} — {c_sel['nombre_convenio']}")
                st.write(f"🏛️ **Ente Financiador:** {c_sel['ente_financiador']} | 📁 **Expediente:** {c_sel['nro_expediente']} | 📅 **Fecha Firma:** {utils.format_date_ar(c_sel['fecha_firma'])}")
                if c_sel['notas']:
                    st.caption(f"📝 *Observaciones:* {c_sel['notas']}")
            with col_h2:
                estado_color = "green" if c_sel['estado'] == 'Vigente' else ("blue" if c_sel['estado'] == 'Terminado' else "red")
                st.markdown(f"**Estado:** :{estado_color}[{c_sel['estado']}]")
                if c_sel['pdf_path'] and os.path.exists(c_sel['pdf_path']):
                    with open(c_sel['pdf_path'], "rb") as f:
                        st.download_button("📄 Descargar Convenio PDF", f, file_name=os.path.basename(c_sel['pdf_path']), key=f"btn_pdf_conv_{sel_conv_id}")

            st.markdown("---")
            st.markdown(f"### 🎯 Panel de Control Contractual (en {m_cod} — {m_sim})")
            st.caption("Auditoría integral del convenio: Cupo total pactado, asignación por contratos individuales, saldo disponible para futuras licitaciones y avance de cobranza.")

            # TARJETA DESTACADA: DESCOMPOSICIÓN DEL CUPO CONTRACTUAL
            st.markdown("##### 🏛️ Composición y Disponibilidad del Cupo Global")
            col_c1, col_c2, col_c3 = st.columns(3)
            
            pactado_fmt = utils.format_moneda_custom(resumen['pactado_moneda_total'], simbolo=m_sim, codigo=m_cod)
            contratado_fmt = utils.format_moneda_custom(resumen['cupo_contratado_moneda'], simbolo=m_sim, codigo=m_cod)
            disponible_fmt = utils.format_moneda_custom(resumen['cupo_disponible_moneda'], simbolo=m_sim, codigo=m_cod)
            
            fecha_firma_str = utils.format_date_ar(c_sel['fecha_firma'])
            col_c1.metric(
                "1. Cupo Total Pactado",
                pactado_fmt,
                help=f"Monto total pactado en el convenio: {utils.format_currency_ar(resumen['pactado_ars_total'])} a cotización base de firma ({fecha_firma_str})."
            )
            col_c2.metric(
                "2. Cupo Contratado (Obras Activas)",
                contratado_fmt,
                delta=f"{resumen['porcentaje_contratado']:.1f}% del total",
                delta_color="normal",
                help=f"Monto comprometido en obras adjudicadas con contrato: {utils.format_currency_ar(resumen['cupo_contratado_ars'])}."
            )
            pct_libre = max(0.0, 100.0 - resumen['porcentaje_contratado'])
            col_c3.metric(
                "3. Cupo Disponible (Por Contratar)",
                disponible_fmt,
                delta=f"{pct_libre:.1f}% libre",
                delta_color="off",
                help=f"Saldo del convenio libre para licitaciones o etapas pendientes: {utils.format_currency_ar(resumen['cupo_disponible_ars'])}."
            )
            
            pct_cont = min(100.0, max(0.0, resumen['porcentaje_contratado']))
            st.progress(pct_cont / 100.0, text=f"Compromiso Contractual: {pct_cont:.1f}% asignado a obras contratadas | {pct_libre:.1f}% disponible para futuras licitaciones")

            st.markdown("##### 📈 Ejecución Financiera y Certificaciones (sobre obras contratadas)")
            col_k1, col_k2, col_k3, col_k4 = st.columns(4)
            solicitado_fmt = utils.format_moneda_custom(resumen['solicitado_moneda_total'], simbolo=m_sim, codigo=m_cod)
            cobrado_fmt = utils.format_moneda_custom(resumen['cobrado_moneda_total'], simbolo=m_sim, codigo=m_cod)
            transito_fmt = utils.format_moneda_custom(resumen['saldo_en_transito_moneda'], simbolo=m_sim, codigo=m_cod)
            dif_ajuste = resumen.get('diferencia_ajuste_ars_total', 0.0)

            col_k1.metric("Certificados Emitidos", solicitado_fmt, help="Total solicitado acumulado en UVIs/moneda presentado al ente financiador.")
            col_k2.metric("Cobrado en Banco", cobrado_fmt, help=f"Total acreditado en cuenta bancaria: {utils.format_currency_ar(resumen['cobrado_ars_total'])}")
            col_k3.metric("Saldo en Tránsito", transito_fmt, help="Fondos ya certificados y solicitados que el ente aún adeuda transferir.")
            col_k4.metric("Ajuste Cotización ($)", utils.format_currency_ar(dif_ajuste), delta=f"{utils.format_currency_ar(dif_ajuste)}", help="Diferencia acumulada en pesos por variación de cotización entre certificación y cobro bancario.")

            # Barra de progreso de cobranza sobre lo contratado
            pct_cob = (resumen['cobrado_moneda_total'] / resumen['cupo_contratado_moneda'] * 100.0) if resumen['cupo_contratado_moneda'] > 0 else 0.0
            st.progress(min(1.0, max(0.0, pct_cob / 100.0)), text=f"Avance de Cobranza sobre Obras Contratadas: {pct_cob:.1f}% acreditado en banco")

            st.markdown("---")
            
            # SECCIÓN 1: OBRAS VINCULADAS
            st.subheader("🏗️ Obras Comprendidas en el Convenio y Ocupación de Cupo")
            st.caption("Detalle de las obras adjudicadas, su contratista y el cupo individual que absorben respecto al convenio.")
            obras_detalle = resumen['obras_detalle']
            
            if not obras_detalle:
                st.warning("Este convenio aún no tiene obras asignadas. Por favor asigne al menos una obra a continuación.")
            else:
                tabla_obras = []
                for o in obras_detalle:
                    tabla_obras.append({
                        "Obra": o['obra_nombre'],
                        "Exp. IMUH": o['expediente_imuh'],
                        "Contratista": o.get('proveedor_razon_social') or '---',
                        f"Cupo Asignado ({m_sim})": utils.format_moneda_custom(o['monto_pactado_moneda'], simbolo=m_sim, codigo=m_cod),
                        f"Cupo ($ Base)": utils.format_currency_ar(o['monto_pactado_ars']),
                        f"Certificado ({m_sim})": utils.format_moneda_custom(o['solicitado_moneda'], simbolo=m_sim, codigo=m_cod),
                        f"Acreditado ({m_sim})": utils.format_moneda_custom(o['cobrado_moneda'], simbolo=m_sim, codigo=m_cod),
                        f"Saldo por Certificar ({m_sim})": utils.format_moneda_custom(o['saldo_remanente_moneda'], simbolo=m_sim, codigo=m_cod),
                        "Percibido ($ ARS)": utils.format_currency_ar(o['cobrado_ars']),
                        "Ajuste Cotiz. ($)": utils.format_currency_ar(o.get('diferencia_ajuste_ars', 0.0)),
                        "Avance (%)": f"{o['porcentaje_avance_financiero']:.1f}%"
                    })
                st.dataframe(pd.DataFrame(tabla_obras), use_container_width=True, hide_index=True)

            # Expander para agregar obras al convenio
            with st.expander("➕ Asociar otra Obra a este Convenio"):
                todas_obras = db.get_obras()
                obras_ya_asociadas = {o['obra_id'] for o in obras_detalle}
                obras_disponibles = [o for o in todas_obras if o['id'] not in obras_ya_asociadas and o['activa'] == 1]
                
                if not obras_disponibles:
                    st.info("Todas las obras activas ya forman parte de este convenio.")
                else:
                    opciones_o_add = {o['id']: f"{o['expediente_imuh']} — {o['nombre']}" for o in obras_disponibles}
                    dict_o_disp = {o['id']: o for o in obras_disponibles}
                    
                    st.caption(f"Saldo disponible en el convenio para nuevas obras: **{utils.format_moneda_custom(resumen['cupo_disponible_moneda'], simbolo=m_sim, codigo=m_cod)}** ({utils.format_currency_ar(resumen['cupo_disponible_ars'])})")
                    
                    col_sel_o, col_info_o = st.columns([2, 1])
                    sel_o_id = col_sel_o.selectbox(
                        "Seleccione la Obra a vincular *",
                        options=list(opciones_o_add.keys()),
                        format_func=lambda x: opciones_o_add[x],
                        key=f"sel_o_add_box_{sel_conv_id}"
                    )
                    
                    o_info = dict_o_disp[sel_o_id]
                    # Sugerir monto de contrato si existe
                    monto_sug = 0.01
                    if o_info.get('monto_contrato_moneda') and float(o_info['monto_contrato_moneda']) > 0 and o_info.get('moneda_id') == c_sel['moneda_id']:
                        monto_sug = float(o_info['monto_contrato_moneda'])
                    elif o_info.get('monto_contrato') and float(o_info['monto_contrato']) > 0:
                        cotiz_c = float(c_sel['cotizacion_base'] or 1.0)
                        if m_cod == 'ARS':
                            monto_sug = float(o_info['monto_contrato'])
                        else:
                            monto_sug = round(float(o_info['monto_contrato']) / max(0.0001, cotiz_c), 2)
                    
                    with col_info_o:
                        st.markdown(f"**Contratista:** {o_info.get('proveedor_razon_social') or 'Sin contrato'}")
                        if monto_sug > 0.01:
                            st.caption(f"Contrato original: {utils.format_moneda_custom(monto_sug, simbolo=m_sim, codigo=m_cod)}")

                    with st.form(f"form_add_obra_conv_{sel_conv_id}"):
                        col_o1, col_o2 = st.columns(2)
                        monto_o_moneda = col_o1.number_input(
                            f"Cupo a asignar en {m_cod} *",
                            min_value=0.01,
                            value=float(monto_sug),
                            step=100.0,
                            help="Predeterminado según el contrato individual de la obra. Editable si este convenio solo financia un porcentaje."
                        )
                        
                        cotiz_conv = float(c_sel['cotizacion_base'] or 1.0)
                        calc_ars = monto_o_moneda * cotiz_conv
                        monto_o_ars = col_o2.number_input(
                            "Equivalente en Pesos ($)",
                            min_value=0.01,
                            value=calc_ars,
                            step=1000.0,
                            help="Calculado según la cotización base del convenio. Editable por redondeos."
                        )
                        
                        if st.form_submit_button("Vincular Obra al Convenio", type="primary"):
                            try:
                                db.add_obra_to_convenio(sel_conv_id, sel_o_id, monto_o_moneda, monto_o_ars)
                                st.session_state.conv_success_msg = "Obra vinculada al convenio con éxito."
                                st.rerun()
                            except ValueError as e:
                                st.error(str(e))

            st.markdown("---")

            # SECCIÓN 2: SOLICITUDES DE DESEMBOLSO / CERTIFICADOS DE AVANCE
            st.subheader(f"📑 Solicitudes de Desembolso / Certificados de Avance por Obra")
            st.caption("A medida que cada obra avanza, registre aquí los certificados o pedidos de fondos enviados a Provincia/Nación para luego cobrar contra ellos.")

            solicitudes = db.get_solicitudes_by_convenio(sel_conv_id)
            
            if not solicitudes:
                st.info("Aún no se han emitido solicitudes de desembolso para este convenio.")
            else:
                tabla_sols = []
                for s in solicitudes:
                    estado_str = "⏳ Pendiente" if s['estado'] == 'Pendiente' else ("⚠️ Parcial" if s['estado'] == 'Parcial' else "✅ Cobrado")
                    tabla_sols.append({
                        "ID": s['id'],
                        "Certificado": s['nro_certificado'],
                        "Obra": s['obra_nombre'],
                        "Periodo": s['periodo'] or "---",
                        f"Cantidad ({m_sim})": utils.format_moneda_custom(s['cantidad_moneda'], simbolo=m_sim, codigo=m_cod),
                        f"Acreditado ({m_sim})": utils.format_moneda_custom(s['cantidad_moneda_cobrada'], simbolo=m_sim, codigo=m_cod),
                        "Cotización": f"$ {s['cotizacion_solicitud']:,.2f}",
                        "Monto Solicitado ($ ARS)": utils.format_currency_ar(s['monto_solicitado_ars']),
                        "Fecha Solicitud": utils.format_date_ar(s['fecha_solicitud']),
                        "Expediente Pago": s['expediente_pago'] or "---",
                        "Estado": estado_str,
                        "PDF": "📄 Sí" if s['pdf_path'] else "No"
                    })
                st.dataframe(pd.DataFrame(tabla_sols), use_container_width=True, hide_index=True)

            # Formulario de Alta de Solicitud por Obra
            with st.expander("➕ Emitir Nueva Solicitud de Desembolso (Certificado de Avance)"):
                if not obras_detalle:
                    st.error("Debe asociar al menos una obra al convenio antes de cargar solicitudes de avance.")
                else:
                    opciones_obras_sol = {o['obra_id']: f"{o['expediente_imuh']} — {o['obra_nombre']} (Cupo libre: {utils.format_moneda_custom(o['saldo_remanente_moneda'], simbolo=m_sim, codigo=m_cod)})" for o in obras_detalle}
                    
                    with st.form(f"form_new_solicitud_{sel_conv_id}"):
                        col_s1, col_s2, col_s3 = st.columns(3)
                        s_obra_id = col_s1.selectbox("Obra correspondiente *", options=list(opciones_obras_sol.keys()), format_func=lambda x: opciones_obras_sol[x])
                        s_nro_cert = col_s2.text_input("N° Certificado / Solicitud *", placeholder="Ej: Certificado N° 1")
                        s_periodo = col_s3.text_input("Periodo correspondiente", placeholder="Ej: Agosto 2026")
                        
                        col_s4, col_s5, col_s6 = st.columns(3)
                        s_cant_moneda = col_s4.number_input(f"Cantidad en {m_cod} a solicitar *", min_value=0.01, step=100.0)
                        
                        # Cotización sugerida: cotización base del convenio
                        cotiz_sug = float(c_sel['cotizacion_base'] or 1.0)
                        s_cotiz = col_s5.number_input(f"Cotización de la UVI/Moneda *", min_value=0.01, value=cotiz_sug, step=1.0, help="Valor de la UVI o moneda para la fecha de emisión del certificado.")
                        
                        calc_s_ars = s_cant_moneda * s_cotiz
                        s_monto_ars = col_s6.number_input("Monto en Pesos solicitado ($ ARS) *", min_value=0.01, value=calc_s_ars, step=1000.0, help="Calculado automáticamente pero editable con tolerancia por redondeo.")
                        
                        col_s7, col_s8 = st.columns(2)
                        s_fecha = col_s7.date_input("Fecha de Solicitud *", value=datetime.date.today(), format="DD-MM-YYYY")
                        s_exp_pago = col_s8.text_input("Expediente de Pago / Nota", placeholder="Ej: EXP-PROV-9876/2026")
                        
                        s_pdf = st.file_uploader("Adjuntar Certificado / Nota (PDF)", type=["pdf"], key=f"pdf_sol_{sel_conv_id}")
                        s_notas = st.text_area("Observaciones adicionales:")
                        
                        if st.form_submit_button("Registrar Solicitud de Desembolso", type="primary"):
                            try:
                                pdf_path = utils.save_uploaded_file(s_pdf) if s_pdf else None
                                db.add_solicitud_convenio(
                                    convenio_id=sel_conv_id,
                                    obra_id=s_obra_id,
                                    nro_certificado=s_nro_cert,
                                    periodo=s_periodo,
                                    cantidad_moneda=s_cant_moneda,
                                    cotizacion_solicitud=s_cotiz,
                                    monto_solicitado_ars=s_monto_ars,
                                    fecha_solicitud=s_fecha.strftime('%Y-%m-%d'),
                                    expediente_pago=s_exp_pago,
                                    pdf_path=pdf_path,
                                    notas=s_notas
                                )
                                st.session_state.conv_success_msg = f"Solicitud '{s_nro_cert}' registrada exitosamente."
                                st.rerun()
                            except ValueError as e:
                                st.error(str(e))

            # SECCIÓN 3: COBROS BANCARIOS ASENTADOS Y TRAZABILIDAD DE COTIZACIONES
            st.markdown("---")
            st.subheader("🏦 Cobros Bancarios Acreditados y Trazabilidad de Cotizaciones")
            st.caption("Detalle de las transferencias recibidas en la cuenta bancaria en pesos, cotizaciones aplicadas y resultado financiero por indexación.")
            
            cobros_conv = db.get_cobros_by_convenio(sel_conv_id)
            if not cobros_conv:
                st.info("Aún no se han asentado cobros bancarios para este convenio. Puede asentarlos desde el módulo '6. Cobros' asociando las solicitudes pendientes.")
            else:
                tabla_cobs = []
                for cb in cobros_conv:
                    dif_val = float(cb.get('diferencia_ajuste_ars') or 0.0)
                    dif_str = f"+{utils.format_currency_ar(dif_val)}" if dif_val >= 0 else f"-{utils.format_currency_ar(abs(dif_val))}"
                    tabla_cobs.append({
                        "Fecha Cobro": utils.format_date_ar(cb['fecha']),
                        "Certificado": cb.get('nro_certificado') or "---",
                        "Obra Afectada": cb.get('obra_nombre') or "Sin asignar",
                        f"Amortizado ({m_sim})": utils.format_moneda_custom(cb.get('cantidad_moneda_origen') or 0.0, simbolo=m_sim, codigo=m_cod),
                        "Cotiz. Solicitud": f"$ {float(cb.get('cotizacion_solicitud') or 0.0):,.2f}",
                        "Cotiz. al Cobro": f"$ {float(cb.get('cotizacion_cobro') or 0.0):,.2f}",
                        "Acreditado en Banco ($ ARS)": utils.format_currency_ar(cb['monto']),
                        "Ajuste Cotización ($)": dif_str,
                        "Comprobante": "📄 Sí" if cb.get('comprobante_path') else "No"
                    })
                st.dataframe(pd.DataFrame(tabla_cobs), use_container_width=True, hide_index=True)

            # Acciones del Convenio (Eliminar o Cambiar Estado)
            st.markdown("---")
            with st.expander("⚙️ Acciones Administrativas del Convenio"):
                col_a1, col_a2 = st.columns(2)
                with col_a1:
                    st.write("**Cambiar Estado:**")
                    nuevo_est = st.selectbox("Estado actual", ["Vigente", "Terminado", "Anulado"], index=["Vigente", "Terminado", "Anulado"].index(c_sel['estado']), key=f"sel_est_{sel_conv_id}")
                    if st.button("Actualizar Estado"):
                        db.update_estado_convenio(sel_conv_id, nuevo_est)
                        st.session_state.conv_success_msg = "Estado actualizado."
                        st.rerun()
                with col_a2:
                    st.write("**Eliminar Convenio:**")
                    st.caption("Solo permitido si no posee cobros bancarios asentados.")
                    chk_del = st.checkbox("Confirmo que deseo eliminar este convenio", key=f"chk_del_conv_{sel_conv_id}")
                    if st.button("🗑️ Eliminar Convenio", disabled=not chk_del):
                        try:
                            db.delete_convenio(sel_conv_id)
                            st.session_state.conv_success_msg = "Convenio eliminado con éxito."
                            st.rerun()
                        except ValueError as e:
                            st.error(str(e))


# =============================================================================
# TAB 2: CARGAR NUEVO CONVENIO
# =============================================================================
with tab_nuevo:
    st.subheader("➕ Registrar Nuevo Convenio de Financiamiento")
    st.markdown("Cargue los datos del convenio firmado con Provincia, Nación u otros organismos. Podrá seleccionar la moneda o índice (ej: **UVI**), ingresar la cotización base contractual y asignar las obras que abarcará.")

    col_c1, col_c2, col_c3 = st.columns(3)
    nro_conv = col_c1.text_input(
        "N° de Convenio / Resolución / Norma *",
        placeholder="Ej: RESOL-2026-322-ADUS o CONV-2026-0045",
        help="Número formal del convenio. Si no posee número correlativo propio, consigne la Resolución o Decreto aprobatorio, el N° GDE o 'S/N' (Sin Número)."
    )
    ente_fin = col_c2.text_input(
        "Ente Financiador *",
        placeholder="Ej: ADUS - IPVU (Provincia del Neuquén)",
        help="Organismo que aporta o financia los fondos (ej: Nación, Provincia, ADUS-IPVU)."
    )
    nom_conv = col_c3.text_input(
        "Nombre Descriptivo *",
        placeholder="Ej: 569 Lotes con Servicios - Cuenca Intermedia",
        help="Denominación del programa o conjunto de obras que financia."
    )

    col_c4, col_c5, col_c6 = st.columns(3)
    exp_conv = col_c4.text_input(
        "N° de Expediente (Ente o IMUH) *",
        placeholder="Ej: EX-2026-002545778-NEU-ALGR#ADUS o 8000478-I-2026",
        help="Expediente electrónico de origen (GDE de Provincia/Nación) o carátula municipal interna del IMUH."
    )
    fec_conv = col_c5.date_input("Fecha de Firma *", value=datetime.date.today(), format="DD-MM-YYYY")
    
    # Selector de Moneda
    moneda_sel_id = col_c6.selectbox(
        "Moneda o Índice del Convenio *",
        options=list(monedas_dict.keys()),
        format_func=lambda x: f"{monedas_dict[x]['codigo']} — {monedas_dict[x]['nombre']} ({monedas_dict[x]['simbolo']})"
    )

    m_info = monedas_dict[moneda_sel_id]
    m_cod = m_info['codigo']
    m_sim = m_info['simbolo']

    col_c7, col_c8, col_c9 = st.columns(3)
    monto_moneda = col_c7.number_input(f"Monto Total Pactado ({m_cod}) *", min_value=0.01, step=1000.0)
    cotiz_base = col_c8.number_input(
        f"Cotización Base Contractual *",
        min_value=0.01,
        value=1.0 if m_cod == 'ARS' else 1000.0,
        step=1.0,
        help="Valor unitario en pesos fijado en el convenio a la fecha base (ej: valor UVI a marzo 2026). Surge de dividir el equivalente en pesos sobre el monto en moneda/UVI."
    )
    
    calc_ars_base = monto_moneda * cotiz_base
    monto_ars = col_c9.number_input(
        "Equivalente en Pesos ($ ARS) *",
        min_value=0.01,
        value=calc_ars_base,
        step=10000.0,
        help="Calculado automáticamente (Monto Moneda × Cotización). Editable para ajustar redondeos exactos de centavos."
    )

    pdf_conv = st.file_uploader("Adjuntar PDF del Convenio (Opcional)", type=["pdf"], key="pdf_conv_nuevo")
    notas_conv = st.text_area("Notas / Observaciones del Convenio:", placeholder="Detalles de afectación, normas complementarias, plazos de obra, etc.")

    st.markdown("---")
    st.write("🏗️ **Asignación Inicial de Obras del Catálogo (Opcional)**")
    st.caption("Seleccione las obras comprendidas en este convenio. Cada obra ocupará automáticamente el cupo de su contrato individual, dejando el resto como saldo disponible para obras pendientes de contratar.")
    
    obras_catalogo = db.get_obras()
    obras_activas = [o for o in obras_catalogo if o['activa'] == 1]
    dict_obras_cat = {o['id']: o for o in obras_activas}
    opc_obras_multi = {o['id']: f"{o['expediente_imuh']} — {o['nombre']}" for o in obras_activas}
    
    obras_seleccionadas = st.multiselect(
        "Obras vinculadas a este convenio:",
        options=list(opc_obras_multi.keys()),
        format_func=lambda x: opc_obras_multi[x]
    )

    cupos_asignados = {}
    total_asignado_obras_moneda = 0.0

    if obras_seleccionadas:
        st.markdown("##### 📐 Asignación de Cupos Individuales por Obra")
        st.caption("Verifique o modifique el cupo asignado a cada obra. Si la obra ya está contratada, el sistema sugiere automáticamente su monto contractual.")
        
        for oid in obras_seleccionadas:
            o_data = dict_obras_cat[oid]
            # Detectar contrato individual
            monto_def = 0.01
            if o_data.get('monto_contrato_moneda') and float(o_data['monto_contrato_moneda']) > 0 and o_data.get('moneda_id') == moneda_sel_id:
                monto_def = float(o_data['monto_contrato_moneda'])
            elif o_data.get('monto_contrato') and float(o_data['monto_contrato']) > 0:
                if m_cod == 'ARS':
                    monto_def = float(o_data['monto_contrato'])
                else:
                    monto_def = round(float(o_data['monto_contrato']) / max(0.0001, cotiz_base), 2)
            
            col_ob_desc, col_ob_input, col_ob_ars = st.columns([2.5, 1.2, 1.3])
            prov_txt = f"Contratista: **{o_data.get('proveedor_razon_social') or 'Sin contrato'}**"
            col_ob_desc.markdown(f"**{o_data['expediente_imuh']}** — {o_data['nombre']}<br><small>{prov_txt}</small>", unsafe_allow_html=True)
            
            c_val = col_ob_input.number_input(
                f"Cupo en {m_cod}",
                min_value=0.01,
                value=float(monto_def),
                step=100.0,
                key=f"cupo_input_nuevo_{oid}"
            )
            cupos_asignados[oid] = c_val
            total_asignado_obras_moneda += c_val
            
            equiv_ob_ars = c_val * cotiz_base
            col_ob_ars.markdown(f"<br>≈ **{utils.format_currency_ar(equiv_ob_ars)}**", unsafe_allow_html=True)

        saldo_libre_moneda = max(0.0, monto_moneda - total_asignado_obras_moneda)
        saldo_libre_ars = saldo_libre_moneda * cotiz_base

        st.markdown("---")
        col_res1, col_res2, col_res3 = st.columns(3)
        col_res1.metric("Cupo Total Convenio", utils.format_moneda_custom(monto_moneda, simbolo=m_sim, codigo=m_cod))
        col_res2.metric("Asignado a Obras", utils.format_moneda_custom(total_asignado_obras_moneda, simbolo=m_sim, codigo=m_cod), delta=f"{(total_asignado_obras_moneda / max(0.001, monto_moneda) * 100):.1f}% del total")
        col_res3.metric("Saldo Libre para Obras Pendientes", utils.format_moneda_custom(saldo_libre_moneda, simbolo=m_sim, codigo=m_cod), delta=f"{utils.format_currency_ar(saldo_libre_ars)}")

        exceso = total_asignado_obras_moneda - monto_moneda
        if exceso > 0.01:
            st.error(f"⚠️ El total asignado a las obras ({utils.format_moneda_custom(total_asignado_obras_moneda, simbolo=m_sim, codigo=m_cod)}) supera el monto total pactado del convenio ({utils.format_moneda_custom(monto_moneda, simbolo=m_sim, codigo=m_cod)}) por {utils.format_moneda_custom(exceso, simbolo=m_sim, codigo=m_cod)}. Ajuste los cupos para poder guardar.")

    btn_disabled = (total_asignado_obras_moneda > (monto_moneda + 0.01)) and bool(obras_seleccionadas)

    if st.button("💾 Guardar Convenio", type="primary", disabled=btn_disabled, key="btn_guardar_nuevo_conv"):
        # Validaciones
        errores = []
        if not nro_conv or not str(nro_conv).strip():
            errores.append("El número de convenio / resolución es obligatorio.")
        if not ente_fin or not str(ente_fin).strip():
            errores.append("El ente financiador es obligatorio.")
        if not nom_conv or not str(nom_conv).strip():
            errores.append("El nombre descriptivo del convenio es obligatorio.")
        if not exp_conv or not str(exp_conv).strip():
            errores.append("El número de expediente es obligatorio.")
        if monto_moneda <= 0:
            errores.append("El monto pactado debe ser mayor a 0.")
        if cotiz_base <= 0:
            errores.append("La cotización base debe ser mayor a 0.")
        if monto_ars <= 0:
            errores.append("El monto equivalente en pesos debe ser mayor a 0.")

        if errores:
            for err in errores:
                st.error(f"❌ {err}")
        else:
            try:
                pdf_path = utils.save_uploaded_file(pdf_conv) if pdf_conv else None
                nuevo_conv_id = db.add_convenio(
                    nro_convenio=nro_conv,
                    ente_financiador=ente_fin,
                    nombre_convenio=nom_conv,
                    nro_expediente=exp_conv,
                    fecha_firma=fec_conv.strftime('%Y-%m-%d'),
                    moneda_id=moneda_sel_id,
                    monto_pactado_moneda=monto_moneda,
                    cotizacion_base=cotiz_base,
                    monto_equivalente_ars=monto_ars,
                    pdf_path=pdf_path,
                    notas=notas_conv
                )

                # Asignar cada obra con su cupo individual
                if obras_seleccionadas:
                    for oid in obras_seleccionadas:
                        cupo_o_m = cupos_asignados.get(oid, 0.01)
                        cupo_o_ars = cupo_o_m * cotiz_base
                        pct_o = (cupo_o_m / monto_moneda * 100.0) if monto_moneda > 0 else 0.0
                        db.add_obra_to_convenio(nuevo_conv_id, oid, cupo_o_m, cupo_o_ars, porcentaje=pct_o)

                st.session_state.conv_success_msg = f"Convenio '{nro_conv}' registrado exitosamente con {len(obras_seleccionadas)} obras asociadas."
                st.rerun()
            except ValueError as e:
                st.error(str(e))


# =============================================================================
# TAB 3: COMPARATIVA GLOBAL DE CONVENIOS
# =============================================================================
with tab_comparativa:
    st.subheader("📊 Resumen Comparativo de Convenios")
    st.caption("Visión consolidada de todos los convenios vigentes, avance financiero y saldos contractuales.")

    todos_convs = db.get_convenios()
    if not todos_convs:
        st.info("No hay convenios cargados.")
    else:
        filas_comp = []
        for cv in todos_convs:
            res = db.get_resumen_control_convenio(cv['id'])
            m_s = res['moneda_simbolo']
            m_c = res['moneda_codigo']
            filas_comp.append({
                "N° Convenio / Norma": cv['nro_convenio'],
                "Ente": cv['ente_financiador'],
                "Nombre": cv['nombre_convenio'],
                "Moneda": m_c,
                "Cupo Total": utils.format_moneda_custom(res['pactado_moneda_total'], simbolo=m_s, codigo=m_c),
                "Cupo Contratado": utils.format_moneda_custom(res['cupo_contratado_moneda'], simbolo=m_s, codigo=m_c),
                "Saldo Libre (Licitaciones)": utils.format_moneda_custom(res['cupo_disponible_moneda'], simbolo=m_s, codigo=m_c),
                "Certificado": utils.format_moneda_custom(res['solicitado_moneda_total'], simbolo=m_s, codigo=m_c),
                "Cobrado en Banco": utils.format_moneda_custom(res['cobrado_moneda_total'], simbolo=m_s, codigo=m_c),
                "En Tránsito": utils.format_moneda_custom(res['saldo_en_transito_moneda'], simbolo=m_s, codigo=m_c),
                "Percibido ($ ARS)": utils.format_currency_ar(res['cobrado_ars_total']),
                "Avance (%)": f"{res['porcentaje_cobranza']:.1f}%",
                "Estado": cv['estado']
            })
        st.dataframe(pd.DataFrame(filas_comp), use_container_width=True, hide_index=True)
