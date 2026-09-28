import streamlit as st
import os
import sys
import pandas as pd
import datetime

# Configurar path para importar módulos locales
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import database as db
import importlib
importlib.reload(db)
import utils
importlib.reload(utils)
import utils_reports
importlib.reload(utils_reports)

from utils_reports import (
    REPORTE_REGISTRY, 
    obtener_datos_composicion, 
    generar_excel_composicion, 
    generar_pdf_composicion,
    obtener_estado_deudas_por_obra,
    generar_excel_estado_deudas,
    generar_pdf_estado_deudas,
    obtener_vista_estado_financiero,
    obtener_vista_pedidos_financiamiento,
    obtener_gastos_funcionamiento_financiados_obra,
    generar_excel_gastos_funcionamiento_financiados_obra,
    generar_pdf_gastos_funcionamiento_financiados_obra
)

st.set_page_config(page_title="Reportes | Decretómetro", page_icon="📥", layout="wide")

utils.inject_style()

st.title("📥 Centro de Reportes Consolidados")
st.markdown("---")

# Requisito C: Obtener opciones del registro dinámicamente
options = list(REPORTE_REGISTRY.keys())
format_func = lambda x: REPORTE_REGISTRY[x]["nombre"]

selected_key = st.selectbox(
    "Seleccione el reporte que desea generar:",
    options=options,
    format_func=format_func,
    key="central_report_selector"
)

report_meta = REPORTE_REGISTRY[selected_key]

# Requisito B: Explicación de la finalidad y qué información muestra
st.info(f"💡 **Finalidad del reporte:** {report_meta['descripcion']}")

st.write("")

if not report_meta["tiene_filtros"]:
    # Reportes sin filtros (Estado Financiero, Pedidos)
    if selected_key == "estado_financiero":
        st.subheader("📊 Vista Previa: Estado Financiero General")
        deudas, tot_d, reservas, tot_r = obtener_vista_estado_financiero()
        
        # Mostrar métricas
        m1, m2 = st.columns(2)
        m1.metric("Total Préstamos / Desvíos Pendientes", utils.format_currency_ar(tot_d), delta="Activos", delta_color="inverse")
        m2.metric("Total Reservas Disponibles", utils.format_currency_ar(tot_r), delta="Disponible")
        
        # Mostrar tabla 1
        st.markdown("#### 1. Préstamos Vigentes (Desvíos a Recuperar)")
        if deudas:
            df_deudas = pd.DataFrame(deudas)
            df_deudas_display = df_deudas.copy()
            df_deudas_display["Saldo Pendiente"] = df_deudas_display["Saldo Pendiente"].apply(utils.format_currency_ar)
            st.dataframe(df_deudas_display, use_container_width=True, hide_index=True)
            st.caption("Leyenda - T (Tipo): D = Desvío Decreto | R = Préstamo desde Reserva | L = Préstamo Legado")
        else:
            st.info("No hay desvíos ni préstamos pendientes de devolución.")
            
        # Mostrar tabla 2
        st.markdown("#### 2. Dinero en Reserva Disponible")
        if reservas:
            df_reservas = pd.DataFrame(reservas)
            df_reservas_display = df_reservas.copy()
            df_reservas_display["Saldo Reserva"] = df_reservas_display["Saldo Reserva"].apply(utils.format_currency_ar)
            st.dataframe(df_reservas_display, use_container_width=True, hide_index=True)
        else:
            st.info("No hay fondos disponibles en reserva.")
            
    elif selected_key == "pedidos_financiamiento":
        st.subheader("📋 Vista Previa: Pedidos de Financiamiento")
        filas, tot_sol, tot_apr, tot_pen = obtener_vista_pedidos_financiamiento()
        
        # Mostrar métricas
        m1, m2, m3 = st.columns(3)
        m1.metric("Total Solicitado", utils.format_currency_ar(tot_sol))
        m2.metric("Total Aprobado (Decretado)", utils.format_currency_ar(tot_apr), delta=f"{((tot_apr/tot_sol)*100 if tot_sol > 0 else 0):.1f}% Aprobado")
        m3.metric("Total Pendiente", utils.format_currency_ar(tot_pen), delta="Pendiente de aprobación", delta_color="inverse")
        
        # Mostrar tabla
        st.markdown("#### Detalle de Solicitudes de Financiamiento")
        if filas:
            df_filas = pd.DataFrame(filas)
            df_filas_display = df_filas.copy()
            df_filas_display["Monto"] = df_filas_display["Monto"].apply(utils.format_currency_ar)
            st.dataframe(df_filas_display, use_container_width=True, hide_index=True)
        else:
            st.info("No hay solicitudes de financiamiento registradas.")

    # Botón para descargar el PDF
    st.markdown("---")
    st.write("📥 **Descargar Reporte Completo en Formato PDF:**")
    try:
        filepath, filename, mime = report_meta["generar_func"]()
        with open(filepath, "rb") as f:
            pdf_bytes = f.read()
        try:
            os.remove(filepath)
        except OSError:
            pass
            
        st.download_button(
            label="📄 Descargar Reporte PDF (.pdf)",
            data=pdf_bytes,
            file_name=filename,
            mime=mime,
            use_container_width=True,
            key=f"dl_pdf_nofilter_{selected_key}"
        )
    except Exception as e:
        st.error(f"Error preparando la descarga del reporte: {e}")
else:
    # Reportes con filtros (Composición de Fondos)
    if selected_key == "composicion_fondos":
        decretos_list = db.get_decretos()
        if not decretos_list:
            st.warning("No hay decretos registrados para generar este reporte.")
        else:
            opc_dec = {d['id']: f"Dto. {d['nro_decreto']}/{d['anio']} - {d['destino_fondos']}" for d in decretos_list}
            sel_dec_id = st.selectbox("Seleccione el Decreto:", options=list(opc_dec.keys()), format_func=lambda x: opc_dec[x], key="rep_central_dec")
            
            if sel_dec_id:
                cuotas_list = db.get_cuotas_by_decreto(sel_dec_id)
                if not cuotas_list:
                    st.info("Este decreto no tiene cuotas configuradas.")
                else:
                    opc_cuota = {c['id']: f"Cuota {c['mes']:02d}/{c['anio']} - Monto: {utils.format_currency_ar(c['monto'])}" for c in cuotas_list}
                    sel_cuota_id = st.selectbox("Seleccione la Cuota:", options=list(opc_cuota.keys()), format_func=lambda x: opc_cuota[x], key="rep_central_cuota")
                    
                    if sel_cuota_id:
                        try:
                            # Obtener datos de la composición automáticamente
                            estado_actual_filas, sum_total_actual, cobros_cuota, cuota_seq_num, fechas_str, aclaraciones_str, cuota_sel_dict = obtener_datos_composicion(sel_dec_id, sel_cuota_id)
                            dec = db.get_decreto(sel_dec_id)
                            
                            st.markdown("### 🔍 Vista Previa: Composición de Fondos de Cuota")
                            
                            # Mostrar información general como métricas
                            m1, m2 = st.columns(2)
                            m1.metric("Importe de Cuota Pautado", utils.format_currency_ar(cuota_sel_dict['monto']))
                            m2.metric("Total Distribuido / Desviado", utils.format_currency_ar(sum_total_actual))
                            
                            st.write(f"📅 **Fechas de Cobro:** {fechas_str}")
                            if aclaraciones_str:
                                st.info(f"💡 **Aclaraciones de la Cuota:**\n{aclaraciones_str}")
                            
                            # Preparar DataFrames para exportación y visualización
                            df_actual = pd.DataFrame(estado_actual_filas)
                            if not df_actual.empty:
                                # Mostrar tabla interactiva
                                df_table = df_actual.copy()
                                df_table["Monto"] = df_table["Monto"].apply(utils.format_currency_ar)
                                
                                # Ocultar columnas redundantes/internas
                                drop_cols = ["obra_id", "gasto_nombre", "gasto_expediente_imuh"]
                                df_table = df_table.drop(columns=[c for c in drop_cols if c in df_table.columns], errors="ignore")
                                    
                                # Renombrar columnas
                                rename_map = {}
                                if "expediente_imuh" in df_table.columns:
                                    rename_map["expediente_imuh"] = "Expediente IMUH"
                                if rename_map:
                                    df_table = df_table.rename(columns=rename_map)
                                    
                                # Limpiar None / vacíos de las columnas para visualización
                                for col in df_table.columns:
                                    df_table[col] = df_table[col].apply(lambda x: "-" if x is None or str(x).lower().strip() in ("none", "nan", "") else x)
                                    
                                st.dataframe(df_table, use_container_width=True, hide_index=True)
                                
                                df_export = pd.DataFrame()
                                df_export["Fecha"] = df_actual["Fecha"]
                                df_export["Destino"] = df_actual["Destino"]
                                df_export["OP"] = df_actual["Orden de Pago (OP)"]
                                df_export["Aclaraciones"] = df_actual["Aclaraciones"]
                                df_export["Monto"] = df_actual["Monto"]
                                
                                # Generar ambos archivos
                                excel_bytes = generar_excel_composicion(dec, cuota_sel_dict, cuota_seq_num, fechas_str, aclaraciones_str, df_export)
                                pdf_bytes = generar_pdf_composicion(dec, cuota_sel_dict, cuota_seq_num, fechas_str, aclaraciones_str, sum_total_actual, df_export)
                                
                                st.markdown("---")
                                st.write("📥 **Descargar Reporte:**")
                                c1, c2 = st.columns(2)
                                c1.download_button(
                                    label="📊 Descargar Reporte Excel (.xlsx)",
                                    data=excel_bytes,
                                    file_name=f"Composicion_{dec['nro_decreto']}_{dec['anio']}_Cuota_{cuota_seq_num}.xlsx",
                                    mime="application/vnd.ms-excel",
                                    use_container_width=True
                                )
                                c2.download_button(
                                    label="📄 Descargar Reporte PDF (.pdf)",
                                    data=pdf_bytes,
                                    file_name=f"Composicion_{dec['nro_decreto']}_{dec['anio']}_Cuota_{cuota_seq_num}.pdf",
                                    mime="application/pdf",
                                    use_container_width=True
                                )
                            else:
                                st.info("No hay movimientos registrados para esta cuota.")
                        except Exception as e:
                            st.error(f"Error generando reporte de composición: {e}")
    elif selected_key in ["obras_deudoras", "obras_acreedoras"]:
        st.warning("Este reporte ha sido reemplazado por el nuevo \u2696\ufe0f Estado de Deudas por Obra.")

    elif selected_key == "afectacion_decretos":
        decretos_list = db.get_decretos()
        if not decretos_list:
            st.warning("No hay decretos registrados para generar este reporte.")
        else:
            st.markdown("### 🔍 Seleccionar Decreto")
            busqueda_dec = st.text_input(
                "Buscar por nro. decreto, año, expediente IMUH o nombre de obra:",
                placeholder="Ej: 1, 2026, 8000422-I-2024, Ampliación...",
                key="busq_afectacion_dec"
            )

            if busqueda_dec.strip():
                term_dec = busqueda_dec.strip().lower()
                decretos_filtrados = [
                    d for d in decretos_list
                    if term_dec in str(d['nro_decreto'])
                    or term_dec in str(d['anio'])
                    or (d['expediente_imuh'] and term_dec in d['expediente_imuh'].lower())
                    or (d['destino_fondos'] and term_dec in d['destino_fondos'].lower())
                ]
            else:
                decretos_filtrados = decretos_list

            if not decretos_filtrados:
                st.info("No se encontraron decretos que coincidan con la búsqueda.")
            else:
                def _label_dec(d):
                    imuh = d['expediente_imuh'] or 'Sin IMUH'
                    return f"Dto. {d['nro_decreto']}/{d['anio']} - [{imuh}] {d['destino_fondos'][:40]}"

                opc_dec_map = {d['id']: d for d in decretos_filtrados}
                sel_dec_id = st.selectbox(
                    "Decreto seleccionado:",
                    options=list(opc_dec_map.keys()),
                    format_func=lambda x: _label_dec(opc_dec_map[x]),
                    key="sel_dec_afectacion"
                )

                if sel_dec_id:
                    st.markdown("---")
                    from utils_reports import obtener_afectacion_decreto, generar_excel_afectacion, generar_pdf_afectacion
                    
                    try:
                        dec, cuotas_list, filas_reporte = obtener_afectacion_decreto(sel_dec_id)
                        
                        total_decreto = sum(c['monto'] for c in cuotas_list)
                        total_percibido = sum(r['Importe percibido'] for r in filas_reporte if r['Importe pagado'] == 0.0 or r == next(iter([f for f in filas_reporte if f['Nro. Cuota'] == r['Nro. Cuota']]), None))
                        # Better calculation for pendiente
                        cobros_tot = 0
                        for c in cuotas_list:
                            cobs = db.get_cobros_by_cuota(c['id'])
                            cobros_tot += sum(cb['monto'] for cb in cobs) if cobs else 0
                        pendiente_cobro = total_decreto - cobros_tot
                        
                        # Info cards
                        m1, m2 = st.columns(2)
                        m1.metric("Total decreto", utils.format_currency_ar(total_decreto))
                        m2.metric("Pendiente de cobro", utils.format_currency_ar(max(0, pendiente_cobro)))
                        
                        st.markdown("### 🔍 Vista Previa: Afectación de Decreto")
                        
                        if filas_reporte:
                            resumen_txt = utils_reports.generar_resumen_narrativo_decreto(dec, filas_reporte, total_decreto, max(0, pendiente_cobro))
                            st.info(f"📝 **Resumen del Decreto:**\n\n{resumen_txt}")
                            
                            df_reporte = pd.DataFrame(filas_reporte)
                            df_display = df_reporte.copy()
                            df_display["Importe percibido"] = df_display["Importe percibido"].apply(utils.format_currency_ar)
                            df_display["Importe pagado"] = df_display["Importe pagado"].apply(utils.format_currency_ar)
                            
                            st.dataframe(df_display, use_container_width=True, hide_index=True)
                            
                            st.markdown("---")
                            st.write("📥 **Descargar Reporte:**")
                            inc_resumen = st.checkbox("Incluir resumen narrativo en el reporte PDF", value=False, key="chk_inc_resumen_pdf")
                            excel_bytes = generar_excel_afectacion(dec, filas_reporte, max(0, pendiente_cobro))
                            pdf_bytes = generar_pdf_afectacion(dec, filas_reporte, max(0, pendiente_cobro), incluir_resumen=inc_resumen)
                            
                            c1, c2 = st.columns(2)
                            c1.download_button(
                                label="📊 Descargar Reporte Excel (.xlsx)",
                                data=excel_bytes,
                                file_name=f"Afectacion_{dec['nro_decreto']}_{dec['anio']}.xlsx",
                                mime="application/vnd.ms-excel",
                                use_container_width=True,
                                key=f"dl_excel_afectacion_{dec['id']}"
                            )
                            c2.download_button(
                                label="📄 Descargar Reporte PDF (.pdf)",
                                data=pdf_bytes,
                                file_name=f"Afectacion_{dec['nro_decreto']}_{dec['anio']}.pdf",
                                mime="application/pdf",
                                use_container_width=True,
                                key=f"dl_pdf_afectacion_{dec['id']}_{inc_resumen}"
                            )
                        else:
                            st.info("No se pudo generar el reporte para este decreto.")
                    except Exception as e:
                        st.error(f"Error generando reporte de afectación: {e}")

    elif selected_key == "estado_deudas_obra":
        # ─ Selector único por nombre o IMUH ───────────────────────────────────
        todas_obras = db.get_todas_obras_para_trazabilidad()

        if not todas_obras:
            st.warning("No hay obras registradas con movimientos de desvios.")
        else:
            st.markdown("### 🔍 Seleccionar Obra")
            busqueda = st.text_input(
                "Buscar por nombre de obra o expediente IMUH:",
                placeholder="Ej: Ampliación, 8000422-I-2024...",
                key="busq_estado_deudas"
            )

            if busqueda.strip():
                term = busqueda.strip().lower()
                obras_filtradas = [
                    o for o in todas_obras
                    if term in o['nombre'].lower()
                    or (o['expediente_imuh'] and term in o['expediente_imuh'].lower())
                ]
            else:
                obras_filtradas = todas_obras

            if not obras_filtradas:
                st.info("No se encontraron obras que coincidan con la búsqueda.")
            else:
                def _label_obra(o):
                    imuh = o['expediente_imuh'] or 'Sin IMUH'
                    tag  = ' 📦 legacy' if o['tipo'] == 'legacy' else ''
                    return f"[{imuh}] {o['nombre']}{tag}"

                opciones_map = {i: o for i, o in enumerate(obras_filtradas)}
                sel_idx = st.selectbox(
                    "Obra seleccionada:",
                    options=list(opciones_map.keys()),
                    format_func=lambda x: _label_obra(opciones_map[x]),
                    key="sel_obra_estado_deudas"
                )
                obra_sel = opciones_map[sel_idx]

                st.markdown("---")

                # Obtener datos
                rows_acr, rows_deu = obtener_estado_deudas_por_obra(obra_sel)

                # Métricas globales
                tot_acr = sum(r['Saldo Pendiente'] for r in rows_acr)
                tot_deu = sum(r['Saldo Pendiente'] for r in rows_deu)
                saldo_neto = tot_acr - tot_deu

                mc1, mc2, mc3 = st.columns(3)
                mc1.metric(
                    "Le deben a esta obra",
                    utils.format_currency_ar(tot_acr),
                    delta="Acreedor" if tot_acr > 0 else None
                )
                mc2.metric(
                    "Esta obra debe devolver",
                    utils.format_currency_ar(tot_deu),
                    delta="Deudor" if tot_deu > 0 else None,
                    delta_color="inverse"
                )
                mc3.metric(
                    "Saldo Neto",
                    utils.format_currency_ar(abs(saldo_neto)),
                    delta="A favor" if saldo_neto >= 0 else "En contra",
                    delta_color="normal" if saldo_neto >= 0 else "inverse"
                )

                st.markdown("---")

                # Sección 1: Acreedora (Le deben a esta obra)
                st.markdown("### 🟢 1. Obras que le deben a esta obra (Acreedora)")
                if not rows_acr:
                    st.info("Esta obra no tiene saldos pendientes de cobro por desvíos otorgados.")
                else:
                    df_acr = pd.DataFrame(rows_acr).drop(columns=['raw_date', 'desvio_id'], errors='ignore')
                    df_acr_disp = df_acr.copy()
                    for col in ['Monto Original', 'Reintegrado', 'Saldo Pendiente']:
                        df_acr_disp[col] = df_acr_disp[col].apply(utils.format_currency_ar)
                    df_acr_disp = df_acr_disp.rename(columns={'Contraparte': 'Obra Deudora'})
                    st.dataframe(df_acr_disp, use_container_width=True, hide_index=True)

                st.markdown("---")

                st.markdown("### 🔴 2. Obras a las que esta obra les debe (Deudora)")
                if not rows_deu:
                    st.info("Esta obra no registra deudas pendientes por desvíos recibidos.")
                else:
                    df_deu = pd.DataFrame(rows_deu).drop(columns=['raw_date', 'desvio_id'], errors='ignore')
                    df_deu_disp = df_deu.copy()
                    for col in ['Monto Original', 'Reintegrado', 'Saldo Pendiente']:
                        df_deu_disp[col] = df_deu_disp[col].apply(utils.format_currency_ar)
                    df_deu_disp = df_deu_disp.rename(columns={'Contraparte': 'Obra Acreedora'})
                    st.dataframe(df_deu_disp, use_container_width=True, hide_index=True)

                st.markdown("---")
                st.markdown("### 🔵 3. Resumen de Saldos Cruzados (Neto por Obra)")
                if not rows_acr and not rows_deu:
                    st.info("No hay saldos cruzados para mostrar.")
                else:
                    import re
                    def get_imuh_base(exp_str):
                        m = re.search(r'(8\d{6})', str(exp_str))
                        return m.group(1) if m else str(exp_str).strip().lower()

                    saldos_cruzados = {}
                    
                    def add_to_saldos(r, is_acr=True):
                        base = get_imuh_base(r.get('Exp. IMUH', 'Sin asignar'))
                        if base == 'sin asignar' or not base.startswith('8'):
                            k = (base, r['Contraparte'].strip().lower()[:15])
                        else:
                            k = base
                            
                        if k not in saldos_cruzados:
                            saldos_cruzados[k] = {
                                'nos_deben': 0.0, 
                                'le_debemos': 0.0, 
                                'nombre': r['Contraparte'], 
                                'exp_imuh': r.get('Exp. IMUH', 'Sin asignar')
                            }
                        else:
                            # Preferir el nombre más corto/limpio si ya existía
                            if len(r['Contraparte']) < len(saldos_cruzados[k]['nombre']):
                                saldos_cruzados[k]['nombre'] = r['Contraparte']
                                saldos_cruzados[k]['exp_imuh'] = r.get('Exp. IMUH', 'Sin asignar')
                                
                        if is_acr:
                            saldos_cruzados[k]['nos_deben'] += float(r.get('Saldo Pendiente', 0.0))
                        else:
                            saldos_cruzados[k]['le_debemos'] += float(r.get('Saldo Pendiente', 0.0))

                    for r in rows_acr:
                        add_to_saldos(r, is_acr=True)
                    for r in rows_deu:
                        add_to_saldos(r, is_acr=False)
                        
                    cruzados_list = []
                    for k, montos in saldos_cruzados.items():
                        nos = montos['nos_deben']
                        les = montos['le_debemos']
                        neto = nos - les
                        if nos > 0 and les > 0:
                            if neto > 0:
                                estado = "A favor 🟢"
                            elif neto < 0:
                                estado = "En contra 🔴"
                            else:
                                estado = "Saldado ⚪"
                                
                            cruzados_list.append({
                                "Obra Contraparte": montos['nombre'],
                                "Exp. IMUH": montos['exp_imuh'],
                                "Nos deben (Acreedora)": utils.format_currency_ar(nos),
                                "Le debemos (Deudora)": utils.format_currency_ar(les),
                                "Saldo Neto": utils.format_currency_ar(abs(neto)),
                                "Estado": estado
                            })
                    
                    if cruzados_list:
                        df_cruzados = pd.DataFrame(cruzados_list)
                        st.dataframe(df_cruzados, use_container_width=True, hide_index=True)
                    else:
                        st.info("No hay obras con las que se mantengan deudas cruzadas simultáneamente (como deudor y acreedor a la vez).")

                # Exportación
                if rows_acr or rows_deu:
                    st.markdown("---")
                    st.write("📥 **Descargar Reporte del Estado de Deudas:**")
                    try:
                        excel_bytes = generar_excel_estado_deudas(obra_sel, rows_acr, rows_deu)
                        pdf_bytes   = generar_pdf_estado_deudas(obra_sel, rows_acr, rows_deu)
                        obra_clean  = obra_sel['nombre'].replace(' ', '_')[:40]
                        c1, c2 = st.columns(2)
                        c1.download_button(
                            label="📊 Descargar Excel (.xlsx)",
                            data=excel_bytes,
                            file_name=f"Estado_Deudas_{obra_clean}.xlsx",
                            mime="application/vnd.ms-excel",
                            use_container_width=True,
                            key="dl_excel_estado_deudas"
                        )
                        c2.download_button(
                            label="📄 Descargar PDF (.pdf)",
                            data=pdf_bytes,
                            file_name=f"Estado_Deudas_{obra_clean}.pdf",
                            mime="application/pdf",
                            use_container_width=True,
                            key="dl_pdf_estado_deudas"
                        )
                    except Exception as e:
                        st.error(f"❌ Error al preparar archivos de descarga: {e}")

    elif selected_key == "gastos_financiados_aportes_obra":
        st.markdown("### 💼 Gastos de Funcionamiento Financiados con Aportes de Obra")
        df_gf = obtener_gastos_funcionamiento_financiados_obra()
        
        if df_gf.empty:
            st.info("No hay gastos de funcionamiento activos financiados con aportes de obra.")
        else:
            st.markdown("#### 🔍 Filtros de Búsqueda")
            col1, col2, col3 = st.columns(3)
            
            # Fechas
            try:
                min_d = datetime.datetime.strptime(df_gf["Fecha del desvío"].min(), "%Y-%m-%d").date()
                max_d = datetime.datetime.strptime(df_gf["Fecha del desvío"].max(), "%Y-%m-%d").date()
            except Exception:
                min_d = datetime.date.today() - datetime.timedelta(days=365)
                max_d = datetime.date.today()
                
            date_range = col1.date_input(
                "Fecha del desvío (Rango):",
                value=[min_d, max_d],
                key="gf_filtro_fecha"
            )
            
            # Gasto
            f_gasto_imuh = col2.text_input("Expediente IMUH del Gasto:", key="gf_filtro_gasto_imuh")
            f_gasto_nombre = col3.text_input("Nombre del Gasto:", key="gf_filtro_gasto_nombre")
            
            col4, col5 = st.columns(2)
            
            # Proveedores y Decretos
            unique_provs = sorted(df_gf["Proveedor"].unique().tolist())
            f_provs = col4.multiselect("Proveedor:", options=unique_provs, key="gf_filtro_proveedores")
            
            unique_decretos = sorted(df_gf["Decreto financiador"].unique().tolist())
            f_decretos = col5.multiselect("Decreto financiador:", options=unique_decretos, key="gf_filtro_decretos")
            
            col6, col7 = st.columns(2)
            f_obra_imuh = col6.text_input("Expediente IMUH de la Obra Financiadora (Acreedora):", key="gf_filtro_obra_imuh")
            f_obra_nombre = col7.text_input("Nombre de la Obra Acreedora:", key="gf_filtro_obra_nombre")
            
            # Aplicar filtros
            df_filtered = df_gf.copy()
            
            if isinstance(date_range, (list, tuple)) and len(date_range) == 2:
                s_d, e_d = date_range
                df_filtered = df_filtered[
                    (pd.to_datetime(df_filtered["Fecha del desvío"]).dt.date >= s_d) &
                    (pd.to_datetime(df_filtered["Fecha del desvío"]).dt.date <= e_d)
                ]
            elif isinstance(date_range, datetime.date):
                df_filtered = df_filtered[pd.to_datetime(df_filtered["Fecha del desvío"]).dt.date == date_range]
                
            if f_gasto_imuh.strip():
                df_filtered = df_filtered[df_filtered["Expediente IMUH del gasto"].str.contains(f_gasto_imuh.strip(), case=False, na=False)]
                
            if f_gasto_nombre.strip():
                df_filtered = df_filtered[df_filtered["Nombre del expediente del gasto"].str.contains(f_gasto_nombre.strip(), case=False, na=False)]
                
            if f_obra_imuh.strip():
                df_filtered = df_filtered[df_filtered["Expediente IMUH de la obra financiadora"].str.contains(f_obra_imuh.strip(), case=False, na=False)]
                
            if f_obra_nombre.strip():
                df_filtered = df_filtered[df_filtered["Nombre de la obra acreedora"].str.contains(f_obra_nombre.strip(), case=False, na=False)]
                
            if f_provs:
                df_filtered = df_filtered[df_filtered["Proveedor"].isin(f_provs)]
                
            if f_decretos:
                df_filtered = df_filtered[df_filtered["Decreto financiador"].isin(f_decretos)]
                
            st.markdown("---")
            
            # Mostrar métricas
            tot_adeudado = df_filtered["Importe adeudado"].sum()
            mc1, mc2 = st.columns(2)
            mc1.metric("Total Adeudado Pendiente", utils.format_currency_ar(tot_adeudado))
            mc2.metric("Cantidad de Gastos", len(df_filtered))
            
            if df_filtered.empty:
                st.info("No se encontraron registros que coincidan con los filtros seleccionados.")
            else:
                # Tabla para mostrar
                df_display = df_filtered.copy()
                df_display["Importe adeudado"] = df_display["Importe adeudado"].apply(utils.format_currency_ar)
                df_display["Fecha del desvío"] = df_display["Fecha del desvío"].apply(utils.format_date_ar)
                st.dataframe(df_display, use_container_width=True, hide_index=True)
                
                # Botones de descarga
                st.markdown("---")
                st.write("📥 **Descargar Reporte Filtrado:**")
                try:
                    excel_bytes = generar_excel_gastos_funcionamiento_financiados_obra(df_filtered)
                    pdf_bytes = generar_pdf_gastos_funcionamiento_financiados_obra(df_filtered)
                    
                    c1, c2 = st.columns(2)
                    c1.download_button(
                        label="📊 Descargar Reporte Excel (.xlsx)",
                        data=excel_bytes,
                        file_name=f"Gastos_Financiados_{datetime.date.today().strftime('%Y%m%d')}.xlsx",
                        mime="application/vnd.ms-excel",
                        use_container_width=True,
                        key="dl_excel_gf_financiados"
                    )
                    c2.download_button(
                        label="📄 Descargar Reporte PDF (.pdf)",
                        data=pdf_bytes,
                        file_name=f"Gastos_Financiados_{datetime.date.today().strftime('%Y%m%d')}.pdf",
                        mime="application/pdf",
                        use_container_width=True,
                        key="dl_pdf_gf_financiados"
                    )
                except Exception as e:
                    st.error(f"❌ Error al preparar los archivos de descarga: {e}")
