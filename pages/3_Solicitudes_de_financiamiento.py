import streamlit as st
import pandas as pd
import datetime
import os, sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import database as db
import importlib
importlib.reload(db)
import utils
importlib.reload(utils)
import pdf_generator
importlib.reload(pdf_generator)
import time
import tempfile
import uuid
from pdf_generator import generar_reporte_solicitudes_pdf
from utils import format_currency_ar, format_date_ar

st.set_page_config(page_title="Pedidos de Financiamiento | Decretómetro", page_icon="📋", layout="wide")
utils.inject_style()

st.title("Gestión de Pedidos de Financiamiento 📋")

if "success_msg_dec" in st.session_state:
    st.toast(f"✅ {st.session_state['success_msg_dec']}")
    del st.session_state["success_msg_dec"]

tab1, tab2, tab3, tab4 = st.tabs(["📊 Reporte y Métricas", "➕ Nuevo Pedido", "🏛️ Aprobar y Convertir", "✏️ Gestión y Edición"])

solicitudes = db.get_solicitudes()

# --- TAB 1: REPORTE Y METRICAS ---
with tab1:
    st.subheader("Informe de Estado de Pedidos")
    
    # Calcular KPIs Simplificados
    cant_pendientes = sum(1 for s in solicitudes if s['estado'] == 'Pendiente')
    tot_pendiente = sum(s['monto_solicitado'] for s in solicitudes if s['estado'] == 'Pendiente')
    
    # Renderizar KPIs Premium
    kpi_col1, kpi_col2 = st.columns(2)
    with kpi_col1:
        st.markdown(f"""
        <div class="metric-card pending">
            <span style="color: #6c757d; font-size: 0.9rem; font-weight: bold;">CANTIDAD DE PEDIDOS PENDIENTES</span><br>
            <span style="font-size: 1.8rem; font-weight: bold; color: #d39e00;">{cant_pendientes}</span><br>
            <span style="color: #6c757d; font-size: 0.8rem;">En espera de resolución</span>
        </div>
        """, unsafe_allow_html=True)
    with kpi_col2:
        st.markdown(f"""
        <div class="metric-card">
            <span style="color: #6c757d; font-size: 0.9rem; font-weight: bold;">MONTO PENDIENTE</span><br>
            <span style="font-size: 1.8rem; font-weight: bold; color: #343a40;">{format_currency_ar(tot_pendiente)}</span><br>
            <span style="color: #6c757d; font-size: 0.8rem;">Pendiente de aprobar/financiar</span>
        </div>
        """, unsafe_allow_html=True)
        
    st.write("")
    
    # Filtros y Tabla
    st.markdown("### 🔍 Buscador y Filtros")
    f_col1, f_col2, f_col3 = st.columns([2, 1, 1])
    search_query = f_col1.text_input("Buscar por Obra / Expediente:", placeholder="Ej: Pavimentación, OE-...")
    status_filter = f_col2.selectbox("Filtrar por Estado:", ["Todos", "Pendiente", "Aprobado", "Rechazado", "Desestimado"])
    
    # Filtrar datos
    filtered_sols = solicitudes.copy()
    if search_query:
        q = search_query.lower()
        filtered_sols = [s for s in filtered_sols if q in s['nro_expediente'].lower() or q in s['destino_fondos'].lower() or (s['notas'] and q in s['notas'].lower())]
        
    if status_filter != "Todos":
        filtered_sols = [s for s in filtered_sols if s['estado'] == status_filter]
        
    # Tabla interactiva
    if not filtered_sols:
        st.info("No se encontraron pedidos de financiamiento que coincidan con los filtros aplicados.")
    else:
        rows = []
        for s in filtered_sols:
            estado_label = "⏳ Pendiente" if s['estado'] == 'Pendiente' else ("✅ Aprobado" if s['estado'] == 'Aprobado' else ("❌ Rechazado" if s['estado'] == 'Rechazado' else "🚫 Desestimado"))
            dec_vinculado = f"Dto. {s['nro_decreto']}/{s['decreto_anio']}" if (s['estado'] == 'Aprobado' and s.get('nro_decreto')) else "-"
            rows.append({
                "ID": s['id'],
                "Expediente": s['nro_expediente'],
                "IMUH pre-vinculados": s['expediente_imuh'] if s['expediente_imuh'] else "-",
                "Destino / Obra": s['destino_fondos'],
                "Monto Solicitado": s['monto_solicitado'],
                "Fecha Solicitud": format_date_ar(s['fecha_solicitud']),
                "Estado": estado_label,
                "Decreto Vinculado": dec_vinculado,
                "Tiene PDF": "📄 Sí" if s['pdf_path'] else "No",
                "Notas / Observaciones": s['notas'] if s['notas'] else ""
            })
            
        df_show = pd.DataFrame(rows)
        # Formatear moneda para visualización
        df_show_fmt = df_show.copy()
        df_show_fmt['Monto Solicitado'] = df_show_fmt['Monto Solicitado'].apply(lambda x: format_currency_ar(x))
        
        st.dataframe(
            df_show_fmt,
            use_container_width=True,
            hide_index=True,
            column_config={
                "ID": st.column_config.NumberColumn(format="%d"),
                "Destino / Obra": st.column_config.TextColumn(width="large"),
                "Notas / Observaciones": st.column_config.TextColumn(width="large"),
            }
        )
        
        # Botón para descargar reporte PDF
        st.write("")
        st.write("**Reporte de Estado de Pedidos**")
        
        temp_path = os.path.join(tempfile.gettempdir(), f"Reporte_Pedidos_Financiamiento_{datetime.date.today().strftime('%Y%m%d')}_{uuid.uuid4().hex[:8]}.pdf")
        generar_reporte_solicitudes_pdf(temp_path)
        with open(temp_path, "rb") as f:
            pdf_bytes = f.read()
            
        st.download_button(
            label="📥 Descargar Reporte PDF Completo",
            data=pdf_bytes,
            file_name=f"Reporte_Pedidos_Financiamiento_{datetime.date.today().strftime('%Y%m%d')}.pdf",
            mime="application/pdf"
        )

# --- TAB 2: NUEVO PEDIDO ---
with tab2:
    st.subheader("Registrar Nuevo Pedido de Financiamiento")
    
    if "succ_sol" in st.session_state:
        st.success(st.session_state["succ_sol"])
        del st.session_state["succ_sol"]
        
    if "err_sol" in st.session_state:
        st.error(st.session_state["err_sol"])
        del st.session_state["err_sol"]
        
    if "form_id" not in st.session_state:
        st.session_state["form_id"] = 0
        
    obras_activas = db.get_obras(only_active=True)
    if not obras_activas:
        st.warning("⚠️ No hay obras habilitadas en el catálogo. Por favor, registre y habilite al menos una obra en la página de Obras antes de crear solicitudes.")
    else:
        obras_opciones = {o['id']: f"{o['expediente_imuh']} - {o['nombre']}" for o in obras_activas}
        
        if "new_obras_ids" not in st.session_state:
            st.session_state["new_obras_ids"] = []
            
        fid = st.session_state['form_id']
        
        col_s1, col_s2 = st.columns(2)
        nro_expediente = col_s1.text_input("Nro. Expediente Municipal *", placeholder="Ej: OE-2849-I-2026", key=f"new_nro_expediente_{fid}")
        
        with col_s2:
            st.write("Seleccione las Obras del Catálogo *")
            col_sel, col_btn = st.columns([3, 1.2])
            # Filtrar las que ya están seleccionadas
            disponibles = {k: v for k, v in obras_opciones.items() if k not in st.session_state["new_obras_ids"]}
            if disponibles:
                sel_obra = col_sel.selectbox("Buscar obra", options=list(disponibles.keys()), format_func=lambda x: disponibles[x], label_visibility="collapsed", key=f"sel_obra_picker_{fid}")
                if col_btn.button("Agregar obra", use_container_width=True, key=f"btn_add_obra_{fid}"):
                    st.session_state["new_obras_ids"].append(sel_obra)
                    st.rerun()
            else:
                col_sel.info("Todas las obras ya fueron agregadas.")
                
        # Listado de obras seleccionadas
        if st.session_state["new_obras_ids"]:
            st.write("#### Obras Seleccionadas:")
            for o_id in list(st.session_state["new_obras_ids"]):
                obra_obj = db.get_obra(o_id)
                if obra_obj:
                    col_info, col_del = st.columns([4, 1])
                    col_info.info(f"🏗️ {obra_obj['expediente_imuh']} - {obra_obj['nombre']}")
                    
                    confirm_key = f"confirm_del_new_{o_id}_{fid}"
                    if st.session_state.get("confirm_delete_obra") == confirm_key:
                        col_info.warning(f"⚠️ ¿Confirmas que deseas quitar la obra '{obra_obj['nombre']}'?")
                        col_si, col_no = col_info.columns(2)
                        if col_si.button("Sí, quitar", key=f"yes_{confirm_key}"):
                            st.session_state["new_obras_ids"].remove(o_id)
                            del st.session_state["confirm_delete_obra"]
                            st.rerun()
                        if col_no.button("Cancelar", key=f"no_{confirm_key}"):
                            del st.session_state["confirm_delete_obra"]
                            st.rerun()
                    else:
                        if col_del.button("Borrar", key=f"del_{confirm_key}"):
                            st.session_state["confirm_delete_obra"] = confirm_key
                            st.rerun()
        else:
            st.warning("⚠️ No se ha agregado ninguna obra a este pedido aún.")
            
        st.write("---")
        
        col_m1, col_m2 = st.columns(2)
        monto_solicitado = col_m1.number_input("Monto Solicitado * ($)", min_value=0.01, step=1000.0, key=f"new_monto_solicitado_{fid}")
        fecha_solicitud = col_m2.date_input("Fecha de Solicitud *", value=datetime.date.today(), format="DD-MM-YYYY", key=f"new_fecha_solicitud_{fid}")
        
        pdf_file = st.file_uploader("Adjuntar Presupuesto / Nota (Opcional PDF)", type=["pdf"], key=f"new_pdf_file_{fid}")
        notas = st.text_area("Notas / Observaciones adicionales:", key=f"new_notas_{fid}")
        
        submit_sol = st.button("Registrar Pedido", type="primary", key=f"btn_reg_sol_{fid}")
        
        if submit_sol:
            nro_exp_clean = nro_expediente.strip()
            
            # Validar expediente duplicado en solicitudes
            exp_dup = any(s['nro_expediente'].strip().lower() == nro_exp_clean.lower() for s in solicitudes)
            
            if not nro_exp_clean or not st.session_state["new_obras_ids"]:
                st.error("Por favor completa los campos obligatorios (*) y seleccione al menos una obra.")
            elif exp_dup:
                st.session_state["err_sol"] = f"El expediente '{nro_exp_clean}' ya está registrado en otra solicitud."
                st.session_state["form_id"] += 1
                st.session_state["new_obras_ids"] = []
                st.rerun()
            elif fecha_solicitud > datetime.date.today():
                st.error("La fecha de solicitud no puede ser futura.")
            else:
                try:
                    pdf_path = utils.save_uploaded_file(pdf_file) if pdf_file else None
                    
                    # Concatenar obras
                    selected_obras = [db.get_obra(oid) for oid in st.session_state["new_obras_ids"]]
                    destino_fondos_val = " // ".join(o['nombre'] for o in selected_obras)
                    expediente_imuh_val = ", ".join(o['expediente_imuh'] for o in selected_obras)
                    first_obra_id = st.session_state["new_obras_ids"][0]
                    
                    db.add_solicitud(
                        nro_expediente=nro_exp_clean,
                        expediente_imuh=expediente_imuh_val,
                        destino_fondos=destino_fondos_val,
                        monto_solicitado=monto_solicitado,
                        fecha_solicitud=fecha_solicitud.strftime('%Y-%m-%d'),
                        pdf_path=pdf_path,
                        notas=notas.strip() if notas else None,
                        obra_id=first_obra_id
                    )
                    st.session_state["succ_sol"] = f"Pedido Exp {nro_exp_clean} registrado con éxito."
                    st.session_state["form_id"] += 1
                    st.session_state["new_obras_ids"] = []
                    st.rerun()
                except Exception as e:
                    st.error(f"Error al registrar solicitud: {e}")

# --- TAB 3: APROBAR Y CONVERTIR ---
with tab3:
    st.subheader("Aprobar Pedido y Vincular Decreto")
    
    solicitudes_pendientes = [s for s in solicitudes if s['estado'] == 'Pendiente']
    
    if not solicitudes_pendientes:
        st.info("No hay pedidos pendientes de gestión en el sistema.")
    else:
        # Armar opciones
        opciones_sol = {}
        for s in solicitudes_pendientes:
            opciones_sol[s['id']] = f"Exp: {s['nro_expediente']} | {s['destino_fondos'][:40]}"
            
        sel_sol_id = st.selectbox("Seleccione Pedido a Aprobar:", options=list(opciones_sol.keys()), format_func=lambda x: opciones_sol[x], key="selectbox_approve_sol")
        
        sol_sel = db.get_solicitud(sel_sol_id)
        
        if sol_sel:
            st.markdown("---")
            col_det1, col_det2 = st.columns(2)
            
            with col_det1:
                st.markdown("#### 📄 Detalles del Pedido Original")
                st.write(f"**Nro. Expediente:** {sol_sel['nro_expediente']}")
                
                exp_imuh_raw = sol_sel['expediente_imuh'] if sol_sel['expediente_imuh'] else ''
                obras_all = db.get_obras()
                mapa_imuh_nombres = {o['expediente_imuh'].strip(): o['nombre'] for o in obras_all if o.get('expediente_imuh')}
                mapa_imuh_to_obra = {o['expediente_imuh'].strip(): o for o in obras_all if o.get('expediente_imuh')}
                
                imuh_parts = [p.strip() for p in exp_imuh_raw.split(',') if p.strip()]
                
                if len(imuh_parts) > 1:
                    st.markdown(f"**Expedientes IMUH pre-vinculados ({len(imuh_parts)}):**")
                    for part in imuh_parts:
                        nombre = mapa_imuh_nombres.get(part)
                        display_text = f"{part} ({nombre})" if nombre else part
                        st.markdown(f"- {display_text}")
                else:
                    part = imuh_parts[0] if imuh_parts else "Sin asignar"
                    nombre = mapa_imuh_nombres.get(part)
                    display_text = f"{part} ({nombre})" if nombre else part
                    st.write(f"**Expediente IMUH pre-vinculado:** {display_text}")
                    
                st.write(f"**Destino / Obra:** {sol_sel['destino_fondos']}")
                st.write(f"**Monto Solicitado:** {format_currency_ar(sol_sel['monto_solicitado'])}")
                st.write(f"**Fecha Solicitud:** {format_date_ar(sol_sel['fecha_solicitud'])}")
                st.write(f"**Notas:** {sol_sel['notas'] if sol_sel['notas'] else 'Sin observaciones.'}")
                
                if sol_sel['pdf_path'] and os.path.exists(sol_sel['pdf_path']):
                    st.write("📄 **Documentación adjunta disponible:**")
                    with open(sol_sel['pdf_path'], "rb") as f:
                        st.download_button(
                            label="📥 Descargar PDF del Pedido",
                            data=f.read(),
                            file_name=os.path.basename(sol_sel['pdf_path']),
                            key=f"btn_dl_pdf_conv_{sol_sel['id']}"
                        )
                else:
                    st.write("No hay PDF adjunto en esta solicitud.")
                    
            with col_det2:
                st.markdown("#### 🏛️ Aprobar y Vincular Decreto")
                st.info("Al aprobar la solicitud, se insertará un Decreto y se planificarán sus cuotas. Puedes desestimar obras de la solicitud deseleccionándolas abajo.")
                
                # Cargar listado de obras del catálogo
                obras_opciones = {o['id']: f"{o['expediente_imuh']} - {o['nombre']}" for o in obras_all if o.get('expediente_imuh')}
                
                default_obras_ids = []
                for part in imuh_parts:
                    if part in mapa_imuh_to_obra:
                        default_obras_ids.append(mapa_imuh_to_obra[part]['id'])
                if not default_obras_ids:
                    pass
                if f"sel_obras_conv_list_{sol_sel['id']}" not in st.session_state:
                    st.session_state[f"sel_obras_conv_list_{sol_sel['id']}"] = default_obras_ids
                
                # Selector de obras individual para conversión
                st.write("Obras Aprobadas para Financiamiento *")
                col_sel_c, col_btn_c = st.columns([3, 1.2])
                disponibles_c = {k: v for k, v in obras_opciones.items() if k not in st.session_state[f"sel_obras_conv_list_{sol_sel['id']}"]}
                if disponibles_c:
                    sel_obra_c = col_sel_c.selectbox("Buscar obra", options=list(disponibles_c.keys()), format_func=lambda x: disponibles_c[x], label_visibility="collapsed", key=f"sel_c_{sol_sel['id']}")
                    if col_btn_c.button("Agregar obra", use_container_width=True, key=f"btn_add_c_{sol_sel['id']}"):
                        st.session_state[f"sel_obras_conv_list_{sol_sel['id']}"].append(sel_obra_c)
                        st.rerun()
                else:
                    col_sel_c.info("Todas las obras ya fueron agregadas.")
                
                # Listado interactivo
                current_conv_list = st.session_state[f"sel_obras_conv_list_{sol_sel['id']}"]
                if current_conv_list:
                    for o_id in list(current_conv_list):
                        obra_obj = db.get_obra(o_id)
                        if obra_obj:
                            col_info_c, col_del_c = st.columns([4, 1])
                            col_info_c.info(f"🏗️ {obra_obj['expediente_imuh']} - {obra_obj['nombre']}")
                            
                            confirm_key = f"confirm_del_conv_{o_id}_{sol_sel['id']}"
                            if st.session_state.get("confirm_delete_obra") == confirm_key:
                                col_info_c.warning(f"⚠️ ¿Confirmas que deseas quitar la obra '{obra_obj['nombre']}' de la aprobación?")
                                col_si, col_no = col_info_c.columns(2)
                                if col_si.button("Sí, quitar", key=f"yes_{confirm_key}"):
                                    st.session_state[f"sel_obras_conv_list_{sol_sel['id']}"].remove(o_id)
                                    del st.session_state["confirm_delete_obra"]
                                    st.rerun()
                                if col_no.button("Cancelar", key=f"no_{confirm_key}"):
                                    del st.session_state["confirm_delete_obra"]
                                    st.rerun()
                            else:
                                if col_del_c.button("Borrar", key=f"del_{confirm_key}"):
                                    st.session_state["confirm_delete_obra"] = confirm_key
                                    st.rerun()
                else:
                    st.warning("⚠️ No hay ninguna obra agregada para ser aprobada.")
                
                # Botón de anular/rechazar pedido en vez de aprobar
                col_actions_rej = st.columns(2)
                with col_actions_rej[0]:
                    if st.button("❌ Rechazar Pedido", use_container_width=True, key=f"btn_rej_{sol_sel['id']}"):
                        db.update_estado_solicitud(sol_sel['id'], 'Rechazado')
                        st.error("Pedido de financiamiento marcado como Rechazado.")
                        st.rerun()
                with col_actions_rej[1]:
                    if st.button("🚫 Desestimar Pedido", use_container_width=True, key=f"btn_desest_{sol_sel['id']}"):
                        db.update_estado_solicitud(sol_sel['id'], 'Desestimado')
                        st.warning("Pedido de financiamiento marcado como Desestimado.")
                        st.rerun()
                
                st.divider()
                
                with st.container():
                    col_conv1, col_conv2, col_conv3 = st.columns(3)
                    nro_decreto = col_conv1.number_input("Nro. Decreto *", min_value=1, step=1, value=1, key=f"conv_nro_{sol_sel['id']}")
                    anio_decreto = col_conv2.number_input("Año Decreto *", min_value=2000, max_value=2100, value=datetime.date.today().year, step=1, key=f"conv_anio_{sol_sel['id']}")
                    monto_decreto = col_conv3.number_input("Monto del Decreto * ($)", min_value=0.01, step=1000.0, value=float(sol_sel['monto_solicitado']), key=f"conv_monto_{sol_sel['id']}")
                    
                    pdf_decreto = st.file_uploader("Adjuntar PDF del Decreto (Opcional)", type=["pdf"], key=f"pdf_decreto_conv_{sol_sel['id']}")
                    
                    st.write("**Planificación de Cuotas**")
                    MONTHS = ["1 - Enero", "2 - Febrero", "3 - Marzo", "4 - Abril", "5 - Mayo", "6 - Junio", 
                              "7 - Julio", "8 - Agosto", "9 - Septiembre", "10 - Octubre", "11 - Noviembre", "12 - Diciembre"]
                    
                    # Generar propuesta de cuota inicial por defecto con el monto completo del decreto
                    mes_sug = MONTHS[datetime.date.today().month - 1]
                    if 'cuotas_conv' not in st.session_state or st.session_state.get('sol_id_conv') != sol_sel['id']:
                        st.session_state.cuotas_conv = pd.DataFrame([{"Mes": mes_sug, "Año": datetime.date.today().year, "Monto ($)": monto_decreto}])
                        st.session_state.sol_id_conv = sol_sel['id']
                        
                    edited_cuotas = st.data_editor(
                        st.session_state.cuotas_conv,
                        num_rows="dynamic",
                        use_container_width=True,
                        key=f"editor_cuotas_conv_key_{sol_sel['id']}",
                        column_config={
                            "Mes": st.column_config.SelectboxColumn("Mes", options=MONTHS, required=True),
                            "Año": st.column_config.NumberColumn("Año", min_value=2000, max_value=2100, step=1, required=True),
                            "Monto ($)": st.column_config.NumberColumn("Monto ($)", min_value=0.01, step=0.01, required=True)
                        }
                    )
                    
                    # Auto progreso de cuotas
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
                            
                            current_sum = pd.to_numeric(df.loc[:idx-1, "Monto ($)"], errors='coerce').sum()
                            remain = monto_decreto - current_sum
                            df.at[idx, 'Monto ($)'] = max(0.01, remain)
                            
                        st.session_state.cuotas_conv = df
                        st.rerun()
                        
                    total_planificado = pd.to_numeric(edited_cuotas["Monto ($)"], errors='coerce').sum() if not edited_cuotas.empty else 0.0
                    diferencia = monto_decreto - total_planificado
                    
                    st.markdown(f"""
                    - **Monto del Decreto:** {format_currency_ar(monto_decreto)}
                    - **Subtotal Cuotas:** {format_currency_ar(total_planificado)}
                    - **Diferencia:** {format_currency_ar(diferencia)}
                    """)
                    
                    if abs(diferencia) > 0.01:
                        st.warning("⚠️ La diferencia debe ser $0.00 para poder aprobar el decreto.")
                        
                    # Check for deselected works in approval
                    sel_obras_conv = st.session_state[f"sel_obras_conv_list_{sol_sel['id']}"]
                    obras_desestimadas_ids = [oid for oid in default_obras_ids if oid not in sel_obras_conv]
                    confirmar_quitar_conv = False
                    if obras_desestimadas_ids:
                        obras_desestimadas_objs = [db.get_obra(oid) for oid in obras_desestimadas_ids]
                        nombres_desestimadas = ", ".join(f"{o['expediente_imuh']} - {o['nombre']}" for o in obras_desestimadas_objs if o)
                        st.warning(f"⚠️ **Atención:** Estás quitando (desestimando) las siguientes obras del financiamiento de este pedido: {nombres_desestimadas}")
                        confirmar_quitar_conv = st.checkbox("Confirmo que deseo desestimar estas obras de este financiamiento", value=False, key=f"chk_confirm_remove_obras_conv_{sol_sel['id']}")
                        
                    confirmar_conv = st.button("Aprobar y Crear Decreto", type="primary", key=f"btn_confirm_conv_{sol_sel['id']}")
                    
                    if confirmar_conv:
                        dec_existe = any(d['nro_decreto'] == nro_decreto and d['anio'] == anio_decreto for d in db.get_decretos())
                        
                        if obras_desestimadas_ids and not confirmar_quitar_conv:
                            st.error("Debe confirmar que desea quitar (desestimar) las obras deseleccionadas marcando la casilla de arriba.")
                        elif not sel_obras_conv:
                            st.error("Debes seleccionar al menos una obra aprobada para el decreto.")
                        elif dec_existe:
                            st.error(f"Ya existe el Decreto N° {nro_decreto}/{anio_decreto} en el sistema.")
                        elif edited_cuotas.empty or edited_cuotas["Monto ($)"].isna().any():
                            st.error("Debes planificar al menos una cuota válida.")
                        elif abs(total_planificado - monto_decreto) > 0.01:
                            st.error("La suma de las cuotas debe ser igual al monto del decreto.")
                        else:
                            try:
                                # 2. Guardar PDF del decreto
                                pdf_to_save = None
                                if pdf_decreto:
                                    pdf_to_save = utils.save_uploaded_file(pdf_decreto)
                                elif sol_sel['pdf_path']:
                                    pdf_to_save = sol_sel['pdf_path'] # Heredar
                                    
                                # 3. Insertar decreto con los detalles de las obras aprobadas únicamente
                                selected_obras_conv_objs = [db.get_obra(oid) for oid in sel_obras_conv]
                                destino_fondos_decreto = " + ".join(o['nombre'] for o in selected_obras_conv_objs)
                                expediente_imuh_decreto = ", ".join(o['expediente_imuh'] for o in selected_obras_conv_objs)
                                
                                d_id = db.add_decreto(
                                    nro_decreto=int(nro_decreto),
                                    anio=int(anio_decreto),
                                    nro_expediente=sol_sel['nro_expediente'],
                                    destino_fondos=destino_fondos_decreto,
                                    pdf_path=pdf_to_save,
                                    expediente_imuh=expediente_imuh_decreto
                                )
                                
                                # 4. Vincular obras al decreto
                                db.add_decreto_obras(d_id, sel_obras_conv)
                                    
                                # 5. Insertar cuotas
                                for _, row in edited_cuotas.iterrows():
                                    mes_int = int(str(row['Mes']).split(" - ")[0])
                                    db.add_cuota(d_id, mes_int, int(row['Año']), float(row['Monto ($)']))
                                    
                                # 6. Actualizar solicitud a Aprobado vinculándola al decreto sin alterar sus obras originales
                                db.update_estado_solicitud(sol_sel['id'], 'Aprobado', d_id)
                                
                                st.session_state["success_msg_dec"] = f"Decreto N° {nro_decreto}/{anio_decreto} creado con éxito desde la solicitud."
                                
                                # Limpiar estados de sesión
                                if "cuotas_conv" in st.session_state:
                                    del st.session_state["cuotas_conv"]
                                if "sol_id_conv" in st.session_state:
                                    del st.session_state["sol_id_conv"]
                                if f"sel_obras_conv_list_{sol_sel['id']}" in st.session_state:
                                    del st.session_state[f"sel_obras_conv_list_{sol_sel['id']}"]
                                    
                                st.rerun()
                            except Exception as e:
                                st.error(f"Error al aprobar y crear decreto: {e}")

# --- TAB 4: GESTION Y EDICION ---
with tab4:
    st.subheader("Gestión, Edición y Eliminación de Solicitudes")
    
    if "succ_sol_edit" in st.session_state:
        st.success(st.session_state["succ_sol_edit"])
        del st.session_state["succ_sol_edit"]
        
    st.write("Selecciona cualquier solicitud de la base de datos para editar sus montos, obras pre-vinculadas o eliminarla.")
    
    # Obtener todas las solicitudes del sistema (sin filtrar por Pendiente)
    todas_solicitudes = db.get_solicitudes()
    
    if not todas_solicitudes:
        st.info("No hay solicitudes registradas en el sistema.")
    else:
        opciones_sol_edit = {}
        for s in todas_solicitudes:
            estado_tag = "⏳" if s['estado'] == 'Pendiente' else ("✅" if s['estado'] == 'Aprobado' else ("❌" if s['estado'] == 'Rechazado' else "🚫"))
            opciones_sol_edit[s['id']] = f"{estado_tag} Exp: {s['nro_expediente']} | {s['destino_fondos'][:40]} | ({format_currency_ar(s['monto_solicitado'])})"
            
        sel_sol_edit_id = st.selectbox("Seleccione Pedido a Gestionar/Editar:", options=list(opciones_sol_edit.keys()), format_func=lambda x: opciones_sol_edit[x], key="selectbox_edit_sol")
        
        sol_sel = db.get_solicitud(sel_sol_edit_id)
        
        if sol_sel:
            st.markdown("---")
            col_ed_left, col_ed_right = st.columns(2)
            
            with col_ed_left:
                st.markdown("#### 📄 Detalles Actuales del Pedido")
                st.write(f"**Nro. Expediente:** {sol_sel['nro_expediente']}")
                
                exp_imuh_raw = sol_sel['expediente_imuh'] if sol_sel['expediente_imuh'] else ''
                obras_all = db.get_obras()
                mapa_imuh_nombres = {o['expediente_imuh'].strip(): o['nombre'] for o in obras_all if o.get('expediente_imuh')}
                imuh_parts = [p.strip() for p in exp_imuh_raw.split(',') if p.strip()]
                
                if sol_sel['decreto_id']:
                    dec_asoc = db.get_decreto(sol_sel['decreto_id'])
                    dec_obras = db.get_obras_by_decreto(sol_sel['decreto_id']) if dec_asoc else []
                    dec_imuhs = {o['expediente_imuh'].strip() for o in dec_obras}
                else:
                    dec_asoc = None
                    dec_imuhs = set()
                
                st.write("**Obras pre-vinculadas:**")
                for part in imuh_parts:
                    nombre = mapa_imuh_nombres.get(part)
                    display_text = f"{part} - {nombre}" if nombre else part
                    if dec_asoc:
                        if part in dec_imuhs:
                            st.markdown(f"- ✅ **{display_text}**")
                        else:
                            st.markdown(f"- ❌ {display_text} *(no incluida en el decreto N° {dec_asoc['nro_decreto']}/{dec_asoc['anio']})*")
                    else:
                        st.markdown(f"- ⏳ {display_text}")
                
                st.write(f"**Monto Solicitado:** {format_currency_ar(sol_sel['monto_solicitado'])}")
                st.write(f"**Fecha Solicitud:** {format_date_ar(sol_sel['fecha_solicitud'])}")
                
                estado_color = "blue" if sol_sel['estado'] == 'Pendiente' else ("green" if sol_sel['estado'] == 'Aprobado' else "red")
                st.markdown(f"**Estado:** :{estado_color}[{sol_sel['estado']}]")
                st.write(f"**Notas:** {sol_sel['notas'] if sol_sel['notas'] else 'Sin observaciones.'}")
                
                if sol_sel['decreto_id']:
                    dec_asoc = db.get_decreto(sol_sel['decreto_id'])
                    if dec_asoc:
                        st.success(f"🔗 **Vinculado al Decreto:** N° {dec_asoc['nro_decreto']}/{dec_asoc['anio']}")
                
                if sol_sel['pdf_path'] and os.path.exists(sol_sel['pdf_path']):
                    st.write("📄 **PDF Adjunto:**")
                    with open(sol_sel['pdf_path'], "rb") as f:
                        st.download_button(
                            label="📥 Descargar PDF actual",
                            data=f.read(),
                            file_name=os.path.basename(sol_sel['pdf_path']),
                            key=f"btn_dl_pdf_edit_{sol_sel['id']}"
                        )
                else:
                    st.write("No hay PDF adjunto en esta solicitud.")
                    
                # Permitir restaurar estado
                if sol_sel['estado'] != 'Pendiente':
                    if sol_sel['estado'] == 'Aprobado' and sol_sel['decreto_id']:
                        dec_asoc = db.get_decreto(sol_sel['decreto_id'])
                        dec_nro_str = f" N° {dec_asoc['nro_decreto']}/{dec_asoc['anio']}" if dec_asoc else ""
                        cobros_asoc = [c for c in db.get_all_cobros() if c['decreto_id'] == sol_sel['decreto_id']]
                        
                        if cobros_asoc:
                            st.error(f"⚠️ No se puede revertir a Pendiente: el Decreto{dec_nro_str} vinculado ya registra cobros percibidos en el sistema.")
                        else:
                            st.warning(f"⚠️ Al volver a Pendiente, se ELIMINARÁ permanentemente el Decreto{dec_nro_str} vinculado y todas sus cuotas asociadas.")
                            chk_revert = st.checkbox("Confirmo que deseo revertir el estado y eliminar el decreto vinculado", value=False, key=f"chk_revert_{sol_sel['id']}")
                            if st.button("🔄 Volver a estado Pendiente", use_container_width=True, disabled=not chk_revert, key=f"btn_restore_pending_{sol_sel['id']}"):
                                db.delete_decreto(sol_sel['decreto_id'])
                                db.update_estado_solicitud(sol_sel['id'], 'Pendiente')
                                st.success("Estado restablecido a Pendiente y decreto vinculado eliminado.")
                                st.rerun()
                    else:
                        # Para Rechazado/Desestimado no hay decreto
                        if st.button("🔄 Volver a estado Pendiente", use_container_width=True, key=f"btn_restore_pending_{sol_sel['id']}"):
                            db.update_estado_solicitud(sol_sel['id'], 'Pendiente')
                            st.success("Estado restablecido a Pendiente.")
                            st.rerun()
                else:
                    col_edit_actions = st.columns(2)
                    with col_edit_actions[0]:
                        if st.button("❌ Rechazar Pedido", use_container_width=True, key=f"btn_edit_rej_{sol_sel['id']}"):
                            db.update_estado_solicitud(sol_sel['id'], 'Rechazado')
                            st.error("Pedido de financiamiento marcado como Rechazado.")
                            st.rerun()
                    with col_edit_actions[1]:
                        if st.button("🚫 Desestimar Pedido", use_container_width=True, key=f"btn_edit_desest_{sol_sel['id']}"):
                            db.update_estado_solicitud(sol_sel['id'], 'Desestimado')
                            st.warning("Pedido de financiamiento marcado como Desestimado.")
                            st.rerun()

            with col_ed_right:
                st.markdown("#### ✏️ Editar Datos del Pedido")
                
                try:
                    fecha_val = datetime.datetime.strptime(sol_sel['fecha_solicitud'], '%Y-%m-%d').date()
                except:
                    fecha_val = datetime.date.today()
                    
                obras_totales = db.get_obras()
                obras_opciones_edit = {o['id']: f"{o['expediente_imuh']} - {o['nombre']}" for o in obras_totales if o.get('expediente_imuh')}
                mapa_imuh_to_obra_edit = {o['expediente_imuh'].strip(): o for o in obras_totales if o.get('expediente_imuh')}
                
                imuh_parts_edit = [p.strip() for p in (sol_sel['expediente_imuh'] or '').split(',') if p.strip()]
                default_obras_edit_ids = []
                for part in imuh_parts_edit:
                    if part in mapa_imuh_to_obra_edit:
                        default_obras_edit_ids.append(mapa_imuh_to_obra_edit[part]['id'])
                if not default_obras_edit_ids and sol_sel.get('obra_id'):
                    default_obras_edit_ids = [sol_sel['obra_id']]
                        
                is_approved = (sol_sel['estado'] == 'Aprobado')
                if is_approved:
                    dec_asoc = db.get_decreto(sol_sel['decreto_id']) if sol_sel['decreto_id'] else None
                    dec_nro_str = f" N° {dec_asoc['nro_decreto']}/{dec_asoc['anio']}" if dec_asoc else ""
                    st.warning(f"⚠️ Este pedido ya ha sido aprobado y convertido en el Decreto{dec_nro_str}, por lo que no se permite su edición o eliminación. Si necesitas modificarlo, primero debes restablecer su estado a Pendiente mediante el botón de la izquierda.")
                
                if f"edit_obras_ids_list_{sol_sel['id']}" not in st.session_state:
                    st.session_state[f"edit_obras_ids_list_{sol_sel['id']}"] = default_obras_edit_ids
                
                edit_nro_exp = st.text_input("Nro. Expediente Municipal *", value=sol_sel['nro_expediente'], disabled=is_approved, key=f"edit_nro_exp_input_{sol_sel['id']}")
                
                # Selector de obras interactivo en edición
                st.write("Obras del Catálogo Asociadas *")
                col_sel_e, col_btn_e = st.columns([3, 1.2])
                disponibles_e = {k: v for k, v in obras_opciones_edit.items() if k not in st.session_state[f"edit_obras_ids_list_{sol_sel['id']}"]}
                
                if disponibles_e and not is_approved:
                    sel_obra_e = col_sel_e.selectbox("Buscar obra", options=list(disponibles_e.keys()), format_func=lambda x: disponibles_e[x], label_visibility="collapsed", key=f"sel_e_{sol_sel['id']}")
                    if col_btn_e.button("Agregar obra", use_container_width=True, key=f"btn_add_e_{sol_sel['id']}"):
                        st.session_state[f"edit_obras_ids_list_{sol_sel['id']}"].append(sel_obra_e)
                        st.rerun()
                elif is_approved:
                    col_sel_e.info("No se pueden modificar las obras porque el pedido ya está aprobado.")
                else:
                    col_sel_e.info("Todas las obras ya fueron agregadas.")
                
                # Listado de obras seleccionadas
                edit_obras_ids = st.session_state[f"edit_obras_ids_list_{sol_sel['id']}"]
                if edit_obras_ids:
                    for o_id in list(edit_obras_ids):
                        obra_obj = db.get_obra(o_id)
                        if obra_obj:
                            col_info_e, col_del_e = st.columns([4, 1])
                            col_info_e.info(f"🏗️ {obra_obj['expediente_imuh']} - {obra_obj['nombre']}")
                            
                            confirm_key = f"confirm_del_edit_{o_id}_{sol_sel['id']}"
                            if st.session_state.get("confirm_delete_obra") == confirm_key and not is_approved:
                                col_info_e.warning(f"⚠️ ¿Confirmas que deseas desvincular la obra '{obra_obj['nombre']}'?")
                                col_si, col_no = col_info_e.columns(2)
                                if col_si.button("Sí, quitar", key=f"yes_{confirm_key}"):
                                    st.session_state[f"edit_obras_ids_list_{sol_sel['id']}"].remove(o_id)
                                    del st.session_state["confirm_delete_obra"]
                                    st.rerun()
                                if col_no.button("Cancelar", key=f"no_{confirm_key}"):
                                    del st.session_state["confirm_delete_obra"]
                                    st.rerun()
                            else:
                                if col_del_e.button("Borrar", key=f"del_{confirm_key}", disabled=is_approved):
                                    st.session_state["confirm_delete_obra"] = confirm_key
                                    st.rerun()
                else:
                    st.warning("⚠️ Debe asociar al menos una obra a la solicitud.")
                
                col_edm1, col_edm2 = st.columns(2)
                edit_monto = col_edm1.number_input("Monto Solicitado * ($)", min_value=0.01, step=1000.0, value=float(sol_sel['monto_solicitado']), key=f"edit_monto_{sol_sel['id']}", disabled=is_approved)
                edit_fecha = col_edm2.date_input("Fecha de Solicitud *", value=fecha_val, format="DD-MM-YYYY", key=f"edit_fecha_{sol_sel['id']}", disabled=is_approved)
                
                edit_pdf_file = st.file_uploader("Actualizar Presupuesto / Nota PDF (Opcional)", type=["pdf"], key=f"edit_pdf_file_premium_{sol_sel['id']}", disabled=is_approved)
                
                tiene_pdf = bool(sol_sel['pdf_path'] and os.path.exists(sol_sel['pdf_path']))
                eliminar_pdf = False
                if tiene_pdf:
                    eliminar_pdf = st.checkbox("Eliminar el archivo PDF adjunto actual", value=False, key=f"del_pdf_chk_{sol_sel['id']}", disabled=is_approved)
                    
                edit_notas = st.text_area("Notas / Observaciones adicionales:", value=sol_sel['notas'] or "", key=f"edit_notas_{sol_sel['id']}", disabled=is_approved)
                
                btn_guardar = st.button("Guardar Cambios", type="primary", disabled=is_approved, key=f"btn_save_edit_{sol_sel['id']}")
                
                if btn_guardar:
                    nro_exp_clean = edit_nro_exp.strip()
                    
                    exp_dup = any(s['nro_expediente'].strip().lower() == nro_exp_clean.lower() and s['id'] != sol_sel['id'] for s in todas_solicitudes)
                    
                    if not nro_exp_clean or not edit_obras_ids:
                        st.error("Por favor completa los campos obligatorios (*) y seleccione al menos una obra.")
                    elif exp_dup:
                        st.error(f"El expediente '{nro_exp_clean}' ya está registrado en otra solicitud.")
                    elif edit_fecha > datetime.date.today():
                        st.error("La fecha de solicitud no puede ser futura.")
                    else:
                        try:
                            pdf_path_final = sol_sel['pdf_path']
                            
                            if eliminar_pdf:
                                if sol_sel['pdf_path']:
                                    utils.delete_file(sol_sel['pdf_path'])
                                pdf_path_final = None
                                
                            if edit_pdf_file:
                                if sol_sel['pdf_path'] and not eliminar_pdf:
                                    utils.delete_file(sol_sel['pdf_path'])
                                pdf_path_final = utils.save_uploaded_file(edit_pdf_file)
                                
                            # Concatenar obras
                            selected_obras_edit = [db.get_obra(oid) for oid in edit_obras_ids]
                            destino_fondos_val = " // ".join(o['nombre'] for o in selected_obras_edit)
                            expediente_imuh_val = ", ".join(o['expediente_imuh'] for o in selected_obras_edit)
                            first_obra_id = edit_obras_ids[0]
                            
                            # Actualizar BD
                            db.update_solicitud(
                                solicitud_id=sol_sel['id'],
                                nro_expediente=nro_exp_clean,
                                expediente_imuh=expediente_imuh_val,
                                destino_fondos=destino_fondos_val,
                                monto_solicitado=edit_monto,
                                fecha_solicitud=edit_fecha.strftime('%Y-%m-%d'),
                                pdf_path=pdf_path_final,
                                notas=edit_notas.strip() if edit_notas else None,
                                obra_id=first_obra_id
                            )
                            
                            # Propagar cambios al decreto vinculado si ya existe
                            if sol_sel['decreto_id']:
                                db.add_decreto_obras(sol_sel['decreto_id'], edit_obras_ids)
                                db.update_decreto_details_for_solicitud(
                                    sol_sel['decreto_id'],
                                        nro_exp_clean,
                                        destino_fondos_val,
                                        pdf_path_final,
                                        expediente_imuh_val
                                    )
                                    
                            st.session_state["succ_sol_edit"] = "¡Pedido actualizado con éxito!"
                            st.rerun()
                        except Exception as e:
                            st.error(f"Error al actualizar la solicitud: {e}")
                
                # Sección de eliminación irreversible
                st.divider()
                st.write("🗑️ **Zona de Peligro: Eliminar Solicitud**")
                chk_eliminar = st.checkbox("Confirmar eliminación permanente de este pedido", value=False, key=f"chk_del_sol_premium_{sol_sel['id']}", disabled=is_approved)
                if st.button("💀 Eliminar Solicitud Permanente", type="primary", use_container_width=True, disabled=not chk_eliminar or is_approved, key=f"btn_del_sol_premium_{sol_sel['id']}"):
                    if sol_sel['pdf_path']:
                        utils.delete_file(sol_sel['pdf_path'])
                    db.delete_solicitud(sol_sel['id'])
                    st.success("Solicitud eliminada de forma permanente del sistema.")
                    st.rerun()
