import streamlit as st
import pandas as pd
import datetime
import os, sys
import io
import base64

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import database as db
import importlib
importlib.reload(db)
import utils
importlib.reload(utils)

# Importar componentes de pestañas de Distribución
from components.tab_estado import render_tab1
from components.tab_distribuir import render_tab2
from components.tab_historial import render_tab3
from components.tab_composicion import render_tab4

def display_pdf(file_path):
    with open(file_path, "rb") as f:
        base64_pdf = base64.b64encode(f.read()).decode('utf-8')
    pdf_display = f'<iframe src="data:application/pdf;base64,{base64_pdf}" width="100%" height="600" type="application/pdf"></iframe>'
    st.markdown(pdf_display, unsafe_allow_html=True)

st.set_page_config(page_title="Cobros y Distribución | Decretómetro", page_icon="💰", layout="wide")
utils.inject_style()
st.title("Gestión y Distribución de Cobros 💰")

tab1, tab2, tab3, tab4, tab5, tab6, tab7 = st.tabs([
    "📋 Historial de Ingresos", 
    "💸 Registrar Ingreso", 
    "🗓️ Estimación de Cobros",
    "📝 Distribuir un Cobro",
    "📊 Estado de Cobranzas",
    "🔄 Historial de Desvíos",
    "🔍 Composición e Historial de Cuotas"
])

with tab2:
    st.subheader("Registrar Nuevo Cobro (Ingreso Bancario)")
    if "succ_cobro" in st.session_state:
        st.success(st.session_state["succ_cobro"])
        del st.session_state["succ_cobro"]

    tipo_origen = st.radio("Seleccione el Origen del Financiamiento a Cobrar:", ["🏛️ Decreto Municipal", "📜 Convenio Provincia/Nación"], horizontal=True)

    if tipo_origen == "🏛️ Decreto Municipal":
        decretos = db.get_decretos()
        activos = [d for d in decretos if d['estado'] != 'Anulado' and d['estado'] != 'Terminado']
        
        if not activos:
            st.info("No hay decretos activos con deuda pendiente.")
        else:
            opciones_dec = {d['id']: f"Dto. {d['nro_decreto']}/{d['anio']} - {d['destino_fondos']}" for d in activos}
            sel_dec_id = st.selectbox("1. Seleccione el Decreto", options=list(opciones_dec.keys()), format_func=lambda x: opciones_dec[x])
            
            if sel_dec_id:
                deuda_por_desvios = db.get_deuda_desvios_by_decreto(sel_dec_id)
                if deuda_por_desvios > 0.01:
                    st.warning(f"⚠️ **Atención:** Esta obra adeuda **{utils.format_currency_ar(deuda_por_desvios)}** por desvíos recibidos anteriormente desde otros decretos.")
                    
                cuotas = db.get_cuotas_by_decreto(sel_dec_id)
                cobros_existentes = db.get_all_cobros()
                
                cuotas_pendientes = []
                for c in cuotas:
                    cobrado = sum(cb['monto'] for cb in cobros_existentes if cb.get('cuota_id') == c['id'])
                    saldo = c['monto'] - cobrado
                    if saldo > 0.01:
                        c['saldo'] = saldo
                        cuotas_pendientes.append(c)
                
                if not cuotas_pendientes:
                    st.success("Este decreto ya no tiene cuotas pendientes.")
                else:
                    opciones_cuota = {c['id']: f"Cuota {c['mes']:02d}/{c['anio']} - Saldo: {utils.format_currency_ar(c['saldo'])}" for c in cuotas_pendientes}
                    sel_cuota_id = st.selectbox("2. Seleccione la Cuota", options=list(opciones_cuota.keys()), format_func=lambda x: opciones_cuota[x])
                    
                    if sel_cuota_id:
                        c_sel = next(c for c in cuotas_pendientes if c['id'] == sel_cuota_id)
                        
                        if "cobro_form_id" not in st.session_state:
                            st.session_state["cobro_form_id"] = 0
                            
                        with st.form(key=f"form_cobro_{st.session_state['cobro_form_id']}"):
                            monto = st.number_input("Monto a Cobrar ($)", min_value=0.01, max_value=float(c_sel['saldo']), value=float(c_sel['saldo']), step=1000.0)
                            fecha = st.date_input("Fecha del Ingreso Bancario", value=datetime.date.today(), format="DD-MM-YYYY")
                            comp_file = st.file_uploader("Adjuntar Comprobante (PDF opcional)", type=['pdf'])
                            
                            btn = st.form_submit_button("Registrar Cobro de Decreto", type="primary")
                            if btn:
                                if fecha > datetime.date.today():
                                    st.error("Error: No se pueden registrar cobros con fecha futura.")
                                else:
                                    try:
                                        path = utils.save_uploaded_file(comp_file) if comp_file else None
                                        db.add_cobro(cuota_id=sel_cuota_id, monto=float(monto), fecha=fecha.strftime('%Y-%m-%d'), comprobante_path=path, origen_tipo='decreto')
                                        st.session_state["succ_cobro"] = f"Cobro de {utils.format_currency_ar(float(monto))} registrado exitosamente."
                                        st.session_state["cobro_form_id"] += 1
                                        st.rerun()
                                    except Exception as e:
                                        st.error(f"Error: {e}")

    else:
        # Origen: Convenio Provincia/Nación
        sols_pendientes = db.get_solicitudes_convenio_pendientes()
        if not sols_pendientes:
            st.info("No hay solicitudes de desembolso ni certificados de avance pendientes de cobro en convenios vigentes. Puede emitir certificados desde la página de 'Convenios'.")
        else:
            opciones_sol = {
                s['id']: f"{s['nro_convenio']} ({s['ente_financiador']}) | Obra: {s['obra_nombre']} | {s['nro_certificado']} | Pendiente: {utils.format_moneda_custom(s['cantidad_moneda'] - s['cantidad_moneda_cobrada'], simbolo=s['moneda_simbolo'], codigo=s['moneda_codigo'])} (~{utils.format_currency_ar(s['monto_solicitado_ars'])})"
                for s in sols_pendientes
            }
            sel_sol_id = st.selectbox("1. Seleccione la Solicitud / Certificado a Cobrar", options=list(opciones_sol.keys()), format_func=lambda x: opciones_sol[x])
            
            if sel_sol_id:
                s_sel = next(s for s in sols_pendientes if s['id'] == sel_sol_id)
                saldo_moneda_pend = float(s_sel['cantidad_moneda'] - s_sel['cantidad_moneda_cobrada'])
                
                st.info(f"🏛️ **Convenio:** {s_sel['nro_convenio']} ({s_sel['nombre_convenio']}) — **Obra:** {s_sel['obra_nombre']} (Exp. IMUH {s_sel['expediente_imuh']})\n\n"
                        f"📊 **Solicitado:** {utils.format_moneda_custom(s_sel['cantidad_moneda'], simbolo=s_sel['moneda_simbolo'], codigo=s_sel['moneda_codigo'])} | **Pendiente de Acreditar:** {utils.format_moneda_custom(saldo_moneda_pend, simbolo=s_sel['moneda_simbolo'], codigo=s_sel['moneda_codigo'])} | **Cotización de Emisión:** $ {s_sel['cotizacion_solicitud']:,.2f}")
                
                cotiz_sol = float(s_sel.get('cotizacion_solicitud') or 1.0)
                key_cant = f"cobro_conv_cant_{sel_sol_id}"
                key_monto = f"cobro_conv_monto_{sel_sol_id}"
                
                # Inicialización reactiva de estado al seleccionar o cambiar solicitud
                if st.session_state.get("last_sel_sol_cobro") != sel_sol_id:
                    st.session_state["last_sel_sol_cobro"] = sel_sol_id
                    st.session_state[key_cant] = float(saldo_moneda_pend)
                    st.session_state[key_monto] = round(saldo_moneda_pend * cotiz_sol, 2)
                elif key_cant not in st.session_state:
                    st.session_state[key_cant] = float(saldo_moneda_pend)
                    st.session_state[key_monto] = round(saldo_moneda_pend * cotiz_sol, 2)

                def on_cobro_cant_change(s_id, c_sol):
                    cant_val = float(st.session_state.get(f"cobro_conv_cant_{s_id}") or 0.0)
                    st.session_state[f"cobro_conv_monto_{s_id}"] = round(cant_val * c_sol, 2)
                
                with st.container(border=True):
                    col_cb1, col_cb2 = st.columns(2)
                    cant_cancelar = col_cb1.number_input(
                        f"Cantidad en {s_sel['moneda_codigo']} a cancelar/amortizar *",
                        min_value=0.01,
                        max_value=float(saldo_moneda_pend),
                        step=10.0,
                        key=key_cant,
                        on_change=on_cobro_cant_change,
                        args=(sel_sol_id, cotiz_sol),
                        help=f"Cantidad de {s_sel['moneda_codigo']} que quedan amortizadas y saldadas con este desembolso bancario. Tope máximo: {saldo_moneda_pend:,.2f}."
                    )
                    
                    monto_ars_efectivo = col_cb2.number_input(
                        "Monto efectivamente acreditado en banco ($ ARS) *",
                        min_value=0.01,
                        step=1000.0,
                        key=key_monto,
                        help="Calculado automáticamente en tiempo real (Cantidad × Cotización de Solicitud). Puede editarlo manualmente si hay una pequeña diferencia por redondeo o ajuste bancario."
                    )
                    
                    col_cb3, col_cb4 = st.columns(2)
                    fecha_cobro_conv = col_cb3.date_input("Fecha del Ingreso Bancario *", value=datetime.date.today(), format="DD-MM-YYYY", key=f"cobro_conv_fecha_{sel_sol_id}")
                    comp_file_conv = col_cb4.file_uploader("Adjuntar Comprobante Bancario (PDF opcional)", type=['pdf'], key=f"comp_conv_{sel_sol_id}")
                    
                    # Cálculo de diferencia
                    monto_teorico = round(cant_cancelar * cotiz_sol, 2)
                    dif_cotiz = round(monto_ars_efectivo - monto_teorico, 2)
                    cotiz_efectiva = (monto_ars_efectivo / cant_cancelar) if cant_cancelar > 0 else cotiz_sol
                    
                    if abs(dif_cotiz) > 0.01:
                        signo = "+" if dif_cotiz > 0 else ""
                        st.caption(f"ℹ️ **Cálculo Teórico:** {utils.format_currency_ar(monto_teorico)} | **Diferencia de liquidación / redondeo:** {signo}{utils.format_currency_ar(dif_cotiz)} (Cotización efectiva resultante: ${cotiz_efectiva:,.2f} / {s_sel['moneda_codigo']})")
                    else:
                        st.caption(f"✓ Coincide exactamente con el cálculo teórico a ${cotiz_sol:,.2f} / {s_sel['moneda_codigo']}.")

                    btn_conv = st.button("Registrar Cobro de Convenio", type="primary", key=f"btn_save_cobro_conv_{sel_sol_id}")
                    if btn_conv:
                        if cant_cancelar > (saldo_moneda_pend + 0.0001):
                            st.error(f"Error: La cantidad a cancelar ({cant_cancelar:,.2f}) no puede ser superior a la pendiente de la solicitud ({saldo_moneda_pend:,.2f} {s_sel['moneda_codigo']}).")
                        elif fecha_cobro_conv > datetime.date.today():
                            st.error("Error: No se pueden registrar cobros con fecha futura.")
                        elif monto_ars_efectivo <= 0:
                            st.error("Error: El monto efectivamente acreditado debe ser mayor a 0.")
                        else:
                            try:
                                path_comp = utils.save_uploaded_file(comp_file_conv) if comp_file_conv else None
                                db.add_cobro(
                                    convenio_solicitud_id=sel_sol_id,
                                    monto=float(monto_ars_efectivo),
                                    fecha=fecha_cobro_conv.strftime('%Y-%m-%d'),
                                    comprobante_path=path_comp,
                                    origen_tipo='convenio',
                                    moneda_origen_id=s_sel.get('moneda_id') or 1,
                                    cantidad_moneda_origen=float(cant_cancelar),
                                    cotizacion_cobro=float(cotiz_efectiva),
                                    diferencia_ajuste_ars=float(dif_cotiz),
                                    obra_id=s_sel['obra_id']
                                )
                                # Limpiar estado
                                if key_cant in st.session_state: del st.session_state[key_cant]
                                if key_monto in st.session_state: del st.session_state[key_monto]
                                st.session_state["succ_cobro"] = f"Cobro de {utils.format_currency_ar(float(monto_ars_efectivo))} ({cant_cancelar:,.2f} {s_sel['moneda_codigo']}) registrado exitosamente."
                                st.rerun()
                            except Exception as e:
                                st.error(f"Error: {e}")

with tab1:
    st.subheader("Historial de Ingresos Percibidos")
    if "succ_del_cobro" in st.session_state:
        st.success(st.session_state["succ_del_cobro"])
        del st.session_state["succ_del_cobro"]
    
    cobros = db.get_all_cobros()
    if not cobros:
        st.info("Aún no hay cobros registrados en el sistema.")
    else:
        # Filtros
        col_f1, col_f2, col_f3 = st.columns(3)
        with col_f1:
            f_desde = st.date_input("Desde", value=datetime.date(datetime.date.today().year, 1, 1), format="DD-MM-YYYY")
            f_hasta = st.date_input("Hasta", value=datetime.date.today(), format="DD-MM-YYYY")
        with col_f2:
            instrumentos_list = sorted(list(set(
                f"Convenio {c['nro_convenio']}" if c.get('origen_tipo') == 'convenio' and c.get('nro_convenio')
                else f"Dto. {c['nro_decreto']}/{c['decreto_anio']}"
                for c in cobros
            )))
            f_instrumento = st.multiselect("Filtrar por Decreto / Convenio", options=instrumentos_list)
        with col_f3:
            min_m = min(c['monto'] for c in cobros) if cobros else 0
            max_m = max(c['monto'] for c in cobros) if cobros else 0
            f_monto = st.slider("Filtrar por Importe ($)", float(min_m), float(max_m), (float(min_m), float(max_m)))

        tabla = []
        for c in cobros:
            fecha_dt = datetime.datetime.strptime(c['fecha'], '%Y-%m-%d').date()
            es_conv = (c.get('origen_tipo') == 'convenio')
            inst_str = f"Convenio {c.get('nro_convenio', '')}" if es_conv else f"Dto. {c.get('nro_decreto', '')}/{c.get('decreto_anio', '')}"
            periodo_str = c.get('nro_certificado', '---') if es_conv else (f"{c['mes']:02d}/{c['anio']}" if c.get('mes') else "---")
            cuota_str = "Certificado" if es_conv else f"{c.get('seq_nro', 1)}/{c.get('total_cuotas', 1)}"
            
            # Aplicar filtros
            if not (f_desde <= fecha_dt <= f_hasta): continue
            if f_instrumento and inst_str not in f_instrumento: continue
            if not (f_monto[0] <= c['monto'] <= f_monto[1]): continue

            moneda_origen_str = f"{c.get('cantidad_moneda_origen', 0):,.2f} {c.get('moneda_codigo', 'ARS')}" if c.get('cantidad_moneda_origen') else "---"

            tabla.append({
                "ID": c['id'],
                "Fecha": fecha_dt,
                "Origen": "Convenio" if es_conv else "Decreto",
                "Instrumento": inst_str,
                "Obra": c.get('obra', ''),
                "Concepto / Cuota": cuota_str,
                "Periodo / Ref": periodo_str,
                "Moneda Origen": moneda_origen_str,
                "Monto ($ ARS)": c['monto'],
                "Comprobante": "📄 Sí" if c['comprobante_path'] else "No"
            })
        df_export = pd.DataFrame(tabla)
        df_c = df_export.copy()
        if not df_c.empty:
            df_c['Fecha'] = df_c['Fecha'].apply(lambda d: utils.format_date_ar(d))
            df_c['Monto ($ ARS)'] = df_c['Monto ($ ARS)'].apply(lambda x: utils.format_currency_ar(x))

        st.dataframe(
            df_c, 
            use_container_width=True, 
            hide_index=True,
            column_config={
                "ID": st.column_config.NumberColumn("ID", format="%d"),
            }
        )
        
        # Botones de exportación
        col_ex_1, col_ex_2 = st.columns(2)
        with col_ex_1:
            try:
                # Descargar a Excel
                buffer = io.BytesIO()
                with pd.ExcelWriter(buffer, engine='xlsxwriter', date_format='dd/mm/yyyy') as writer:
                    df_export.to_excel(writer, index=False, sheet_name='Cobros')
                    workbook = writer.book
                    worksheet = writer.sheets['Cobros']
                    num_format = workbook.add_format({'num_format': '$ #,##0.00'})
                    date_format = workbook.add_format({'num_format': 'dd/mm/yyyy'})
                    
                    # Ajuste automático del ancho de columnas y asignación de formatos
                    for idx, col in enumerate(df_export.columns):
                        # Calcular largo máximo entre encabezado y contenido
                        max_len = len(str(col))
                        if not df_export.empty:
                            col_series_len = df_export[col].astype(str).map(len).max()
                            if pd.notna(col_series_len):
                                max_len = max(max_len, int(col_series_len))
                        
                        col_width = max(max_len + 3, 10)
                        
                        # Limitar ancho máximo para descripciones largas (ej. Obras)
                        if col == "Obra":
                            col_width = min(col_width, 60)
                        else:
                            col_width = min(col_width, 40)
                            
                        if col == 'Fecha':
                            worksheet.set_column(idx, idx, col_width, date_format)
                        elif col == 'Monto ($ ARS)':
                            # Se asegura un ancho mínimo cómodo para montos contables
                            worksheet.set_column(idx, idx, max(col_width, 18), num_format)
                        else:
                            worksheet.set_column(idx, idx, col_width)
                st.download_button(
                    label="📊 Exportar Historial a Excel",
                    data=buffer.getvalue(),
                    file_name="historial_cobros_decretometro.xlsx",
                    mime="application/vnd.ms-excel",
                    use_container_width=True
                )
            except Exception as e:
                st.error(f"No se pudo generar Excel. Error: {e}")
        
        with col_ex_2:
            st.info("💡 PDF: Se puede exportar desde Excel o utilizando la impresión del navegador.")
        
        st.markdown("---")
        with st.expander("Modificar / Eliminar un Cobro"):
            del_id = st.number_input("Introducir ID del Cobro", min_value=0, step=1)
            c_target = db.get_cobro(del_id) if del_id > 0 else None
            if c_target:
                st.write(f"Cobro seleccionado: **{utils.format_currency_ar(c_target['monto'])}** del {utils.format_date_ar(c_target['fecha'])}")
                
                if c_target['comprobante_path'] and os.path.exists(c_target['comprobante_path']):
                    st.info("Visualizando comprobante adjunto:")
                    display_pdf(c_target['comprobante_path'])
                    with open(c_target['comprobante_path'], "rb") as f:
                        st.download_button("📥 Descargar Comprobante", f, file_name=os.path.basename(c_target['comprobante_path']), key="btn_desc_comp")
                
                if st.button("🗑️ Eliminar Cobro (Restituye saldo a la cuota)", use_container_width=True):
                    try:
                        db.delete_cobro(del_id)
                        if c_target['comprobante_path']:
                            utils.delete_file(c_target['comprobante_path'])
                        st.session_state["succ_del_cobro"] = f"Cobro ID {del_id} eliminado exitosamente."
                        st.rerun()
                    except Exception as e:
                        st.error(f"Error al eliminar: {e}")

with tab3:
    st.subheader("Estimación de Semanas de Cobro")
    st.info("Utiliza esta sección para informar cuándo estimas que se percibirá cada cuota pendiente de las obras.")
    
    # Obtener todas las cuotas pendientes de obras
    decretos = db.get_decretos()
    activos = [d for d in decretos if d['estado'] not in ['Anulado', 'Terminado']]
    all_cobros = db.get_all_cobros()
    
    pendientes_data = []
    today = datetime.date.today()
    for d in activos:
        cuotas = db.get_cuotas_by_decreto(d['id'])
        for q in cuotas:
            cobrado = sum(c['monto'] for c in all_cobros if c['cuota_id'] == q['id'])
            saldo = q['monto'] - cobrado
            if saldo > 0.01:
                # Filtrar: Atrazadas o Mes Vigente
                # (q['anio'] < today.year) o (q['anio'] == today.year y q['mes'] <= today.month)
                if q['anio'] < today.year or (q['anio'] == today.year and q['mes'] <= today.month):
                    pendientes_data.append({
                        "id": q['id'],
                        "decreto": f"{d['nro_decreto']}/{d['anio']}",
                        "obra": d['destino_fondos'],
                        "periodo": f"{q['mes']:02d}/{q['anio']}",
                        "saldo": saldo,
                        "estimacion": q['fecha_estimada_cobro']
                    })
    
    if not pendientes_data:
        st.success("No hay cuotas de obras con saldo pendiente.")
    else:
        # Agrupar por decreto para mejor visualización
        df_p = pd.DataFrame(pendientes_data)
        
        with st.form("form_estimaciones"):
            st.write("Complete las fechas estimadas y presione 'Guardar Cambios'.")
            
            # Usaremos un diccionario para capturar los inputs del formulario
            nuevas_estimaciones = {}
            
            # Mostrar por grupos de obra
            for obra, group in df_p.groupby("obra"):
                st.markdown(f"#### 🏗️ {obra}")
                for _, row in group.iterrows():
                    c1, c2, c3 = st.columns([1, 1, 2])
                    c1.write(f"**{row['periodo']}**")
                    c2.write(f"{utils.format_currency_ar(row['saldo'])}")
                    
                    # Valor inicial para el date_input
                    val_init = datetime.date.today()
                    if row['estimacion']:
                        try:
                            val_init = datetime.datetime.strptime(row['estimacion'], '%Y-%m-%d').date()
                        except: pass
                    
                    # Usar un checkbox para habilitar la edición de la fecha (u opcionalidad)
                    # O simplemente un date_input y detectar cambios si fuera dinámico, 
                    # pero en un form necesitamos keys estables.
                    key_date = f"est_{row['id']}"
                    nuevas_estimaciones[row['id']] = c3.date_input(
                        f"Est. para {row['periodo']}", 
                        value=val_init, 
                        key=key_date,
                        label_visibility="collapsed",
                        format="DD-MM-YYYY"
                    )
                st.divider()
            
            if st.form_submit_button("💾 Guardar Todas las Estimaciones", type="primary", use_container_width=True):
                try:
                    for cid, f_est in nuevas_estimaciones.items():
                        db.update_cuota_estimacion(cid, f_est.strftime('%Y-%m-%d'))
                    st.success("✅ Estimaciones actualizadas correctamente.")
                    st.rerun()
                except Exception as e:
                    st.error(f"Error al guardar: {e}")

with tab4:
    render_tab2()

with tab5:
    render_tab1()

with tab6:
    render_tab3()

with tab7:
    render_tab4()

