import streamlit as st
import os, sys
import datetime

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import database as db
import importlib
importlib.reload(db)
import utils
importlib.reload(utils)

st.set_page_config(page_title="Obras | Decretómetro", page_icon="🏗️", layout="wide")
utils.inject_style()
st.title("Catálogo de Obras 🏗️")
st.markdown("---")

tab1, tab2 = st.tabs(["🗂️ Catálogo de Obras", "➕ Nueva Obra"])

# --- TAB 1: CATÁLOGO Y EDICIÓN ---
with tab1:
    obras = db.get_obras()
    if not obras:
        st.info("No hay obras registradas en el sistema.")
    else:
        st.subheader("Buscar / Seleccionar Obra")
        opciones = [f"ID: {o['id']} | {o['expediente_imuh']} - {o['nombre']}" for o in obras]
        seleccion = st.selectbox("Seleccione una obra para ver detalles o editar:", opciones)
        
        if seleccion:
            obra_id = int(seleccion.split(" | ")[0].replace("ID: ", ""))
            obra = db.get_obra(obra_id)
            resumen = db.get_resumen_contrato_obra(obra_id)
            es_bimon = resumen['es_bimonetaria'] if resumen else False
            m_codigo = resumen['moneda_codigo'] if resumen else 'ARS'
            m_simbolo = resumen['moneda_simbolo'] if resumen else '$'

            # --- TARJETAS MÉTRICAS DE RESUMEN CONTRACTUAL ---
            st.markdown("#### Posición Contractual y Financiera")
            c_m1, c_m2, c_m3, c_m4 = st.columns(4)
            if es_bimon:
                c_m1.metric(
                    label=f"Contrato Total ({m_codigo})",
                    value=f"{resumen['total_contratado_moneda']:,.2f} {m_simbolo}",
                    help=f"Base: {resumen['monto_contrato_base_moneda']:,.2f} | Adicionales: {resumen['cantidad_adicionales_moneda']:,.2f}"
                )
                c_m2.metric(
                    label="% Avance Contractual",
                    value=f"{resumen['porcentaje_avance_moneda']:.1f}%",
                    help=f"Amortizado: {resumen['total_moneda_amortizada']:,.2f} {m_codigo}"
                )
                c_m3.metric(
                    label=f"Saldo Remanente ({m_codigo})",
                    value=f"{resumen['saldo_moneda_remanente']:,.2f} {m_simbolo}",
                    help="Pendiente de amortizar / certificar"
                )
                c_m4.metric(
                    label="Desembolsos Totales (Banco)",
                    value=utils.format_currency_ar(resumen['total_pagado_efectivo_ars']),
                    delta=f"Indexación: {utils.format_currency_ar(resumen['resultado_indexacion_ars'])}",
                    delta_color="normal",
                    help="El badge muestra el Resultado por Indexación acumulado (Total Pagado - Costo Base Histórico FIFO)."
                )
            else:
                c_m1.metric(
                    label="Monto Contrato ($)",
                    value=utils.format_currency_ar(resumen['total_costo_base_contratado_ars'])
                )
                c_m2.metric(
                    label="% Avance Financiero",
                    value=f"{resumen['porcentaje_avance_moneda']:.1f}%"
                )
                c_m3.metric(
                    label="Saldo Disponible ($)",
                    value=utils.format_currency_ar(resumen['saldo_moneda_remanente'])
                )
                c_m4.metric(
                    label="Total Pagado ($)",
                    value=utils.format_currency_ar(resumen['total_pagado_efectivo_ars'])
                )

            st.markdown("---")
            
            # Obtener decretos asociados
            decretos = db.get_decretos_by_obra(obra_id)
            decretos_vigentes = [d for d in decretos if d['estado'] != 'Anulado']
            decretos_anulados = [d for d in decretos if d['estado'] == 'Anulado']
            
            col_info, col_edit = st.columns(2)
            
            with col_info:
                st.subheader("Detalles de la Obra")
                st.write(f"**Nombre de la Obra:** {obra['nombre']}")
                st.write(f"**Expediente IMUH:** `{obra['expediente_imuh']}`")
                
                if obra.get('proveedor_razon_social'):
                    st.write(f"**Proveedor:** {obra['proveedor_razon_social']} (CUIT: {obra['proveedor_cuit']})")
                else:
                    st.write("**Proveedor:** NO INFORMA PROVEEDOR")
                
                st.write(f"**Moneda Contractual:** {obra.get('moneda_nombre', 'Peso Argentino')} (`{obra.get('moneda_codigo', 'ARS')}`)")
                
                if es_bimon:
                    st.write(f"**Contrato Base ({m_codigo}):** {obra.get('monto_contrato_moneda', 0):,.2f} {m_simbolo}")
                    st.write(f"**Cotización Base Licitación:** ${obra.get('cotizacion_base_contrato', 1):,.2f} ARS")
                    st.write(f"**Costo Base Inicial:** {utils.format_currency_ar(obra.get('monto_contrato', 0))}")
                    if obra.get('fecha_contrato'):
                        st.write(f"**Fecha Contrato:** {obra['fecha_contrato']}")
                    if obra.get('notas_contrato'):
                        st.write(f"**Notas / Cláusula:** {obra['notas_contrato']}")
                else:
                    monto_contrato_val = obra.get('monto_contrato') or 0.0
                    st.write(f"**Monto de Contrato:** {utils.format_currency_ar(monto_contrato_val)}")
                
                estado_txt = "🟢 Habilitada" if obra['activa'] == 1 else "🔴 Inhabilitada"
                st.write(f"**Estado:** {estado_txt}")
                
                if decretos_vigentes:
                    dec_list = ", ".join(f"Dto. {d['nro_decreto']}/{d['anio']}" for d in decretos_vigentes)
                    st.success(f"📜 **Asociada a Decretos Vigentes:** {dec_list}")
                elif decretos_anulados:
                    dec_list = ", ".join(f"Dto. {d['nro_decreto']}/{d['anio']} (ANULADO)" for d in decretos_anulados)
                    st.warning(f"⚠️ **Asociada únicamente a Decretos Anulados:** {dec_list}")
                else:
                    st.info("📂 **Financiación:** Fondos Propios / Convenios (sin decreto ordinario)")
                
                # Botón de inhabilitar/habilitar
                st.divider()
                st.write("**Cambiar Estado de Disponibilidad:**")
                if obra['activa'] == 1:
                    if st.button("🚫 Inhabilitar Obra", use_container_width=True, type="primary"):
                        db.update_obra(obra_id, obra['nombre'], obra['expediente_imuh'], 0, obra.get('proveedor_id'))
                        st.success("Obra inhabilitada. Ya no aparecerá en formularios para nuevos desvíos o decretos.")
                        st.rerun()
                else:
                    if st.button("🟢 Habilitar Obra", use_container_width=True, type="primary"):
                        db.update_obra(obra_id, obra['nombre'], obra['expediente_imuh'], 1, obra.get('proveedor_id'))
                        st.success("Obra habilitada con éxito.")
                        st.rerun()

                # Eliminar obra por completo
                st.divider()
                st.write("**Eliminación:**")
                confirm_del = st.checkbox("Confirmar eliminación permanente de esta obra", key=f"del_chk_{obra_id}")
                if st.button("🗑️ Eliminar Obra", use_container_width=True, type="secondary", disabled=not confirm_del):
                    try:
                        db.delete_obra(obra_id)
                        st.success("Obra eliminada con éxito.")
                        st.rerun()
                    except ValueError as e:
                        st.error(str(e))
            
            with col_edit:
                st.subheader("✏️ Editar Obra")
                provs_obras = db.get_proveedores_obras(only_active=False)
                opc_provs_edit = {0: "NO INFORMA PROVEEDOR"}
                for p in provs_obras:
                    if p['activo'] == 1 or p['id'] == obra.get('proveedor_id'):
                        opc_provs_edit[p['id']] = f"{p['razon_social']} (CUIT: {p['cuit']})"
                
                curr_prov_id = obra.get('proveedor_id') or 0
                if curr_prov_id not in opc_provs_edit:
                    curr_prov_id = 0

                monedas_list = db.get_monedas_indices(solo_activas=True)
                monedas_dict = {m['id']: f"{m['nombre']} ({m['codigo']})" for m in monedas_list}
                curr_mon_id = obra.get('moneda_id') or 1
                if curr_mon_id not in monedas_dict:
                    curr_mon_id = 1

                # Formulario de edición
                e_nombre = st.text_input("Nombre de la Obra *", value=obra['nombre'], key="edit_nombre_obra")
                e_exp = st.text_input("Expediente IMUH *", value=obra['expediente_imuh'], help="Formato estricto: 8XXXXXX-I-AAAA.", key="edit_exp_obra")
                e_prov_id = st.selectbox(
                    "Proveedor",
                    options=list(opc_provs_edit.keys()),
                    format_func=lambda x: opc_provs_edit[x],
                    index=list(opc_provs_edit.keys()).index(curr_prov_id),
                    key="edit_prov_obra"
                )
                
                tiene_pagos_obra = bool(resumen and (resumen.get('total_pagado_efectivo_ars', 0.0) > 0 or resumen.get('total_moneda_amortizada', 0.0) > 0))
                
                e_moneda_id = st.selectbox(
                    "Moneda Contractual",
                    options=list(monedas_dict.keys()),
                    format_func=lambda x: monedas_dict[x],
                    index=list(monedas_dict.keys()).index(curr_mon_id),
                    disabled=tiene_pagos_obra,
                    help="Bloqueado porque la obra ya registra pagos u órdenes de pago emitidas." if tiene_pagos_obra else None,
                    key="edit_moneda_obra"
                )
                if tiene_pagos_obra:
                    st.caption("🔒 *La moneda contractual no puede modificarse porque la obra ya registra pagos u órdenes de pago.*")

                cambia_cotiz = False
                confirmar_rectif_cotiz = True
                motivo_rectif = None

                if e_moneda_id == 1:
                    # Obra en Pesos
                    e_monto_contrato = st.number_input(
                        "Monto de Contrato ($ ARS)",
                        min_value=0.0,
                        step=1000.0,
                        value=float(obra.get('monto_contrato', 0.0)),
                        key="edit_monto_ars_obra"
                    )
                    e_monto_moneda = e_monto_contrato
                    e_cotiz_base = 1.0
                    e_fecha_contrato = None
                    e_notas_contrato = None
                else:
                    # Obra Bimonetaria
                    sel_mon_obj = next((m for m in monedas_list if m['id'] == e_moneda_id), None)
                    cod_mon = sel_mon_obj['codigo'] if sel_mon_obj else 'UVI'
                    
                    e_c1, e_c2 = st.columns(2)
                    e_monto_moneda = e_c1.number_input(
                        f"Monto Contrato Base ({cod_mon}) *",
                        min_value=0.0,
                        step=100.0,
                        value=float(obra.get('monto_contrato_moneda') or obra.get('monto_contrato') or 0.0),
                        key="edit_monto_mon_obra"
                    )
                    old_cotiz_base = float(obra.get('cotizacion_base_contrato') or 1.0)
                    e_cotiz_base = e_c2.number_input(
                        f"Cotización Base Licitación ($ ARS)",
                        min_value=0.0001,
                        step=10.0,
                        value=old_cotiz_base,
                        key="edit_cotiz_base_obra"
                    )
                    equiv_ars_preview = e_monto_moneda * e_cotiz_base
                    st.info(f"💡 **Equivalente Contractual Base:** {utils.format_currency_ar(equiv_ars_preview)}")
                    
                    cambia_cotiz = (abs(e_cotiz_base - old_cotiz_base) > 0.0001)
                    if tiene_pagos_obra and cambia_cotiz:
                        st.warning("⚠️ **Atención:** Modificar la cotización base inicial recalculará retroactivamente el Costo Base y el Resultado por Indexación de todos los pagos registrados.")
                        confirmar_rectif_cotiz = st.checkbox("Confirmo la rectificación de la cotización base inicial", key=f"chk_rectif_{obra_id}")
                        motivo_rectif = st.text_input("Motivo / Justificación obligatoria de la rectificación *", key=f"motivo_rectif_{obra_id}")

                    # Fecha y notas
                    f_val = datetime.date.today()
                    if obra.get('fecha_contrato'):
                        try:
                            f_val = datetime.datetime.strptime(str(obra['fecha_contrato']), "%Y-%m-%d").date()
                        except Exception:
                            pass
                    e_fecha_contrato = st.date_input("Fecha de Firma del Contrato", value=f_val, key="edit_fecha_contrato")
                    e_notas_contrato = st.text_area("Notas / Cláusula de Ajuste", value=obra.get('notas_contrato') or '', key="edit_notas_contrato")
                    e_monto_contrato = equiv_ars_preview

                st.warning("⚠️ **Atención:** Si cambias el nombre o el expediente IMUH, el sistema actualizará en cascada todos los registros lógicos y solicitudes históricas asociadas.")
                confirm_cascade = st.checkbox("Entiendo y confirmo los cambios sobre esta obra", key=f"chk_cascade_{obra_id}")
                
                if st.button("Guardar Cambios", key="btn_save_obra_edit", type="primary"):
                    if not confirm_cascade:
                        st.error("Debe marcar la casilla de confirmación para poder aplicar los cambios.")
                    elif tiene_pagos_obra and cambia_cotiz and not confirmar_rectif_cotiz:
                        st.error("Debe confirmar la rectificación de la cotización base para continuar.")
                    elif tiene_pagos_obra and cambia_cotiz and (not motivo_rectif or not motivo_rectif.strip()):
                        st.error("Debe ingresar el motivo / justificación obligatoria de la rectificación.")
                    else:
                        try:
                            sel_p_id = e_prov_id if e_prov_id != 0 else None
                            db.update_obra(
                                obra_id=obra_id,
                                nombre=e_nombre,
                                expediente_imuh=e_exp,
                                activa=obra['activa'],
                                proveedor_id=sel_p_id,
                                moneda_id=e_moneda_id,
                                monto_contrato_moneda=e_monto_moneda,
                                cotizacion_base_contrato=e_cotiz_base,
                                fecha_contrato=e_fecha_contrato.strftime('%Y-%m-%d') if e_fecha_contrato else None,
                                notas_contrato=e_notas_contrato,
                                motivo_rectificacion=motivo_rectif.strip() if motivo_rectif else None
                            )
                            db.update_monto_contrato_obra(
                                obra_id=obra_id,
                                nuevo_monto=e_monto_contrato,
                                nuevo_monto_moneda=e_monto_moneda,
                                nueva_cotizacion_base=e_cotiz_base,
                                motivo_rectificacion=motivo_rectif.strip() if motivo_rectif else None
                            )
                            st.success("Obra actualizada correctamente.")
                            st.rerun()
                        except ValueError as e:
                            st.error(str(e))

            # --- SECCIONES BIMONETARIAS PARA OBRAS EN UVIs / EXTRANJERAS ---
            if es_bimon:
                st.markdown("---")
                st.subheader(f"➕ Adicionales de Obra ({m_codigo})")
                st.caption("Registre ampliaciones contractuales autorizadas por Resolución Municipal con su respectiva cotización base a la fecha de emisión.")
                
                adicionales = db.get_obra_adicionales(obra_id)
                
                with st.expander("➕ Registrar Nuevo Adicional de Obra"):
                    col_ad1, col_ad2, col_ad3 = st.columns(3)
                    ad_resolucion = col_ad1.text_input("N° de Resolución *", placeholder="Ej: Resol. 12/2026", key="ad_res_input")
                    ad_fecha = col_ad2.date_input("Fecha de Resolución *", value=datetime.date.today(), format="DD-MM-YYYY", key="ad_fecha_input")
                    ad_cantidad = col_ad3.number_input(f"Cantidad ({m_codigo}) *", min_value=0.01, step=100.0, key="ad_cant_input")
                    
                    col_ad4, col_ad5 = st.columns(2)
                    ad_cotiz = col_ad4.number_input("Cotización Base al dictado ($ ARS) *", min_value=0.0001, step=10.0, value=float(obra.get('cotizacion_base_contrato') or 1.0), key="ad_cotiz_input")
                    ad_motivo = col_ad5.text_input("Motivo / Fundamentación", placeholder="Ej: Ampliación de plazo y redeterminación", key="ad_motivo_input")
                    
                    monto_adic_preview = ad_cantidad * ad_cotiz
                    st.info(f"💡 **Monto Equivalente del Adicional:** {utils.format_currency_ar(monto_adic_preview)}")
                    
                    if st.button("Guardar Adicional de Obra", type="primary", key="btn_save_adicional"):
                        try:
                            db.add_obra_adicional(
                                obra_id=obra_id,
                                nro_resolucion=ad_resolucion,
                                fecha=ad_fecha.strftime('%Y-%m-%d'),
                                cantidad_moneda=ad_cantidad,
                                cotizacion_base=ad_cotiz,
                                motivo=ad_motivo
                            )
                            st.success(f"Adicional '{ad_resolucion}' registrado exitosamente.")
                            st.rerun()
                        except ValueError as ex:
                            st.error(str(ex))
                
                if adicionales:
                    st.markdown("##### Listado de Adicionales Registrados")
                    for ad in adicionales:
                        col_r1, col_r2, col_r3, col_r4, col_r5, col_r6 = st.columns([2, 1.5, 2, 2, 3, 1])
                        col_r1.write(f"**{ad['nro_resolucion']}**")
                        col_r2.write(f"`{ad['fecha']}`")
                        col_r3.write(f"{ad['cantidad_moneda']:,.2f} {m_codigo}")
                        col_r4.write(f"@ ${ad['cotizacion_base']:,.2f}")
                        col_r5.write(f"{utils.format_currency_ar(ad['monto_equivalente_ars'])} ({ad.get('motivo') or 'Sin motivo'})")
                        if col_r6.button("🗑️", key=f"btn_del_ad_{ad['id']}", help="Eliminar este adicional"):
                            db.delete_obra_adicional(ad['id'])
                            st.success("Adicional eliminado.")
                            st.rerun()
                else:
                    st.info("No hay adicionales registrados para esta obra.")

                # --- SECCIÓN DE TRAMOS CONTRACTUALES FIFO ---
                st.markdown("---")
                st.subheader(f"📑 Tramos Contractuales y Posición FIFO ({m_codigo})")
                st.caption("Consolidación cronológica de tramos y amortización bajo regla estricta FIFO.")
                if resumen and resumen.get('tramos'):
                    tramos_data = []
                    for t in resumen['tramos']:
                        tramos_data.append({
                            "Tramo": t['tipo'],
                            "Resolución": t['nro_resolucion'],
                            "Fecha": t['fecha'],
                            f"Total ({m_codigo})": f"{t['cantidad_moneda']:,.2f}",
                            "Cotiz. Base": f"${t['cotizacion_base']:,.2f}",
                            "Costo Base ($ ARS)": utils.format_currency_ar(t['monto_ars']),
                            f"Amortizado ({m_codigo})": f"{t['moneda_amortizada']:,.2f}",
                            "Costo Base Amortizado ($)": utils.format_currency_ar(t['costo_base_amortizado_ars']),
                            f"Saldo Remanente ({m_codigo})": f"{t['saldo_moneda']:,.2f}"
                        })
                    st.dataframe(tramos_data, use_container_width=True)

            # --- SECCIÓN DE TRAZABILIDAD DE PAGOS E INDEXACIÓN ---
            st.markdown("---")
            st.subheader("🔍 Trazabilidad de Pagos e Indexación por Orden de Pago")
            st.caption("Detalle comprobante por comprobante de los desembolsos imputados al contrato de la obra.")
            pagos_detalle = db.get_pagos_detalle_por_obra(obra_id)
            if pagos_detalle:
                tabla_pagos = []
                for p in pagos_detalle:
                    tabla_pagos.append({
                        "Fecha": p.get('fecha'),
                        "N° OP": p.get('nro_op') or 'Sin OP',
                        "Fuente": p.get('fuente_descripcion') or p.get('tipo_fuente'),
                        "Total Pagado ($ ARS)": utils.format_currency_ar(p.get('monto_ars') or 0.0),
                        f"Amortizado ({m_codigo})": f"{p.get('cantidad_moneda_amortizada', 0.0):,.2f}",
                        "Cotización OP": f"${p.get('cotizacion_pago', 1.0):,.2f}",
                        "Costo Base FIFO ($)": utils.format_currency_ar(p.get('costo_base_ars') or 0.0),
                        "Resultado por Indexación ($)": utils.format_currency_ar(p.get('resultado_indexacion_ars') or 0.0),
                        "Motivo Sobrepago / Notas": p.get('motivo_sobrepago') or p.get('notas') or '-'
                    })
                st.dataframe(tabla_pagos, use_container_width=True)
            else:
                st.info("No se registran órdenes de pago imputadas a esta obra.")

# --- TAB 2: NUEVA OBRA ---
with tab2:
    st.subheader("Registrar Nueva Obra")
    st.info("Las obras se crean inicialmente como Fondos Propios (sin decreto). Podrán asociarse a decretos o convenios posteriormente desde sus respectivos módulos.")

    if st.session_state.get('obra_registrada_ok'):
        st.success(f"✅ Obra **\"{st.session_state['obra_registrada_nombre']}\"** registrada exitosamente.")
        del st.session_state['obra_registrada_ok']
        del st.session_state['obra_registrada_nombre']

    if 'new_obra_counter' not in st.session_state:
        st.session_state['new_obra_counter'] = 0
    form_key = f"new_obra_form_{st.session_state['new_obra_counter']}"

    provs_obras_act = db.get_proveedores_obras(only_active=True)
    opc_provs_new = {0: "NO INFORMA PROVEEDOR"}
    for p in provs_obras_act:
        opc_provs_new[p['id']] = f"{p['razon_social']} (CUIT: {p['cuit']})"

    monedas_act = db.get_monedas_indices(solo_activas=True)
    monedas_new_dict = {m['id']: f"{m['nombre']} ({m['codigo']})" for m in monedas_act}
        
    n_nombre = st.text_input("Nombre de la Obra *", key=f"n_nombre_{form_key}")
    n_exp = st.text_input(
        "Expediente IMUH * (Ej: 8000422-I-2024)",
        help="Formato: 7 dígitos, guión, letra mayúscula, guión, 4 dígitos. Ej: 8000422-I-2024. Es único por obra.",
        key=f"n_exp_{form_key}"
    )
    n_prov_id = st.selectbox(
        "Proveedor (Opcional)",
        options=list(opc_provs_new.keys()),
        format_func=lambda x: opc_provs_new[x],
        key=f"n_prov_{form_key}"
    )
    
    n_moneda_id = st.selectbox(
        "Moneda Contractual *",
        options=list(monedas_new_dict.keys()),
        format_func=lambda x: monedas_new_dict[x],
        index=0,
        key=f"n_moneda_{form_key}"
    )

    if n_moneda_id == 1:
        n_monto_contrato = st.number_input(
            "Monto de Contrato ($ ARS) (Opcional)",
            min_value=0.0,
            step=1000.0,
            value=0.0,
            key=f"n_monto_contrato_{form_key}"
        )
        n_monto_moneda = n_monto_contrato
        n_cotiz_base = 1.0
        n_fecha_contrato = None
        n_notas_contrato = None
    else:
        sel_mon = next((m for m in monedas_act if m['id'] == n_moneda_id), None)
        c_cod = sel_mon['codigo'] if sel_mon else 'UVI'
        col_nm1, col_nm2 = st.columns(2)
        n_monto_moneda = col_nm1.number_input(
            f"Monto Contrato Base ({c_cod}) *",
            min_value=0.0,
            step=100.0,
            value=0.0,
            key=f"n_monto_mon_{form_key}"
        )
        n_cotiz_base = col_nm2.number_input(
            f"Cotización Base de Licitación ($ ARS) *",
            min_value=0.0001,
            step=10.0,
            value=1.0,
            key=f"n_cotiz_base_{form_key}"
        )
        equiv_nuevo_ars = n_monto_moneda * n_cotiz_base
        st.info(f"💡 **Equivalente Contractual Inicial:** {utils.format_currency_ar(equiv_nuevo_ars)}")
        n_fecha_contrato = st.date_input("Fecha de Firma del Contrato", value=datetime.date.today(), key=f"n_fecha_c_{form_key}")
        n_notas_contrato = st.text_area("Notas / Cláusula de Ajuste (Opcional)", key=f"n_notas_c_{form_key}")
        n_monto_contrato = equiv_nuevo_ars
    
    if st.button("Registrar Obra", type="primary", key=f"btn_reg_obra_{form_key}"):
        if not n_nombre.strip():
            st.error("El nombre de la obra es obligatorio.")
        elif not n_exp.strip():
            st.error("El Expediente IMUH es obligatorio.")
        elif not utils.validar_expediente_imuh(n_exp.strip()):
            st.error("❌ El Expediente IMUH no tiene un formato válido. Debe ser: 7 dígitos, guión, letra mayúscula, guión, 4 dígitos (Ej: 8000422-I-2024).")
        else:
            try:
                sel_p_id = n_prov_id if n_prov_id != 0 else None
                obra_id = db.add_obra(
                    nombre=n_nombre.strip(),
                    expediente_imuh=n_exp.strip(),
                    proveedor_id=sel_p_id,
                    moneda_id=n_moneda_id,
                    monto_contrato_moneda=n_monto_moneda,
                    cotizacion_base_contrato=n_cotiz_base,
                    fecha_contrato=n_fecha_contrato.strftime('%Y-%m-%d') if n_fecha_contrato else None,
                    notas_contrato=n_notas_contrato
                )
                db.update_monto_contrato_obra(obra_id, n_monto_contrato, n_monto_moneda, n_cotiz_base)
                st.session_state['obra_registrada_ok'] = True
                st.session_state['obra_registrada_nombre'] = n_nombre.strip()
                st.session_state['new_obra_counter'] += 1
                st.rerun()
            except ValueError as e:
                st.error(str(e))
