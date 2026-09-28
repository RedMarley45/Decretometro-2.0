import streamlit as st
import os, sys
import datetime
import pandas as pd

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import database as db
import utils

st.set_page_config(page_title="Pagos Fondos Propios | Decretómetro", page_icon="💰", layout="wide")
utils.inject_style()

st.title("Adelantos con Fondos Propios 💰")
st.markdown("Registre los pagos que se realizan a las obras utilizando fondos propios de la gestión, antes de que salgan los decretos.")
st.markdown("---")

tab1, tab2 = st.tabs(["🗂️ Registro de Pagos", "➕ Cargar Nuevo Pago"])

# --- TAB 1: REGISTRO DE PAGOS ---
with tab1:
    st.subheader("Pagos con Fondos Propios Registrados")
    pagos = db.get_pagos_fondos_propios()
    
    if not pagos:
        st.info("No se han registrado pagos con fondos propios.")
    else:
        obras_dict = {o['id']: o for o in db.get_obras()}
        
        data = []
        for p in pagos:
            o_info = obras_dict.get(p['obra_id'], {})
            obra_nombre = f"{o_info.get('expediente_imuh', '')} - {o_info.get('nombre', 'Desconocida')}"
            m_cod = o_info.get('moneda_codigo', 'ARS')
            cant_amort = p.get('cantidad_moneda_amortizada')
            cotiz = p.get('cotizacion_pago')
            
            amort_txt = f"{cant_amort:,.2f} {m_cod}" if (cant_amort and m_cod != 'ARS') else "-"
            cotiz_txt = f"${cotiz:,.2f}" if (cotiz and m_cod != 'ARS') else "-"
            
            data.append({
                "ID": p['id'],
                "Obra": obra_nombre,
                "Fecha": utils.format_date_ar(p['fecha']),
                "Total Pagado ($)": utils.format_currency_ar(p['monto']),
                "Amortizado": amort_txt,
                "Cotización OP": cotiz_txt,
                "Nro OP": p['nro_op'] or "-",
                "Observaciones": p['observaciones'] or "-",
                "Sobrepago": p.get('motivo_sobrepago') or "-"
            })
            
        df = pd.DataFrame(data)
        st.dataframe(df, use_container_width=True, hide_index=True)
        
        st.divider()
        st.subheader("Eliminar Pago")
        id_a_eliminar = st.selectbox("Seleccione el ID del pago que desea eliminar", options=[p['id'] for p in pagos], format_func=lambda x: f"Pago #{x}")
        
        if id_a_eliminar:
            p_sel = next(p for p in pagos if p['id'] == id_a_eliminar)
            o_sel = obras_dict.get(p_sel['obra_id'], {})
            st.warning(f"Está por eliminar el pago de {utils.format_currency_ar(p_sel['monto'])} a la obra '{o_sel.get('nombre', '')}'.")
            chk_del = st.checkbox("Confirmo que deseo eliminar este registro.")
            if st.button("🗑️ Eliminar Pago", disabled=not chk_del):
                try:
                    db.delete_pago_fondos_propios(id_a_eliminar)
                    st.success("Pago eliminado exitosamente.")
                    st.rerun()
                except ValueError as e:
                    st.error(str(e))

# --- TAB 2: CARGAR NUEVO PAGO ---
with tab2:
    st.subheader("Cargar Adelanto de Fondos Propios")
    st.info("Estos pagos se sumarán a lo que la contratista ya cobró, y quedarán adeudados por la obra a la gestión (Topes de Recupero).")
    
    obras_activas = [o for o in db.get_obras() if o['activa'] == 1]
    
    if not obras_activas:
        st.error("No hay obras activas en el sistema para imputar un pago.")
    else:
        if st.session_state.get('pago_fp_registrado_ok'):
            st.success("✅ El pago ha sido registrado correctamente.")
            del st.session_state['pago_fp_registrado_ok']

        col1, col2 = st.columns(2)
        
        with col1:
            opciones_obra = {o['id']: f"{o['expediente_imuh']} - {o['nombre']} ({o.get('moneda_codigo', 'ARS')})" for o in obras_activas}
            obra_id = st.selectbox("Obra Destino *", options=list(opciones_obra.keys()), format_func=lambda x: opciones_obra[x])
            
            monto = st.number_input("Monto ($ ARS) *", min_value=0.01, step=1000.0)
            fecha = st.date_input("Fecha del Pago", value=datetime.date.today(), format="DD-MM-YYYY")
        
        with col2:
            nro_op = st.text_input("Número de Orden de Pago (Bejerman)")
            observaciones = st.text_area("Observaciones", help="Obligatorio si no hay Nro OP. Entre 10 y 30 caracteres.")
            
        # Parámetros bimonetarios si la obra no es en Pesos
        obra_sel = db.get_obra(obra_id) if obra_id else None
        resumen_obra = db.get_resumen_contrato_obra(obra_id) if obra_id else None
        es_bimon = resumen_obra['es_bimonetaria'] if resumen_obra else False
        
        cant_moneda_amort = monto
        cotiz_pago = 1.0
        
        if es_bimon and resumen_obra:
            cod_mon = resumen_obra['moneda_codigo']
            st.markdown("---")
            st.markdown(f"#### Imputación Contractual en Moneda de Origen ({cod_mon})")
            c_bim1, c_bim2 = st.columns(2)
            cotiz_pago = c_bim1.number_input(
                f"Cotización de la OP ($ ARS por {cod_mon}) *",
                min_value=0.0001,
                step=10.0,
                value=float(resumen_obra.get('cotizacion_base_contrato') or 1.0),
                help="Cotización vigente al momento del libramiento de la Orden de Pago para amortizar unidades contractuales."
            )
            cant_moneda_amort = round(monto / cotiz_pago, 6) if cotiz_pago > 0 else 0.0
            c_bim2.info(f"💡 **Amortización Contractual:** `{cant_moneda_amort:,.2f} {cod_mon}`")

        st.divider()
        
        # Real-time warnings
        confirmar_sin_op = False
        if not nro_op.strip():
            st.warning("⚠️ Si no ingresa un número de OP, deberá proveer observaciones detalladas y confirmar.")
            confirmar_sin_op = st.checkbox("Confirmo que deseo registrar este pago sin OP")
        else:
            confirmar_sin_op = True
            
        # Verificación estricta de sobrepago
        chk_sp = {'es_sobrepago': False, 'mensaje': ''}
        if obra_id:
            if es_bimon:
                chk_sp = db.check_sobrepago_obra(obra_id, nuevo_monto_pesos=monto, nueva_cantidad_moneda=cant_moneda_amort)
            else:
                chk_sp = db.check_sobrepago_obra(obra_id, nuevo_monto_pesos=monto)
                
        confirmar_sobrepago = True
        motivo_sobrepago = None
        if chk_sp.get('es_sobrepago'):
            st.error(f"⚠️ **Atención:** {chk_sp['mensaje']}")
            confirmar_sobrepago = st.checkbox("Confirmo que deseo sobrepagar el contrato de la obra", key="chk_sobrepago_fp")
            motivo_sobrepago = st.text_input("Motivo / Justificación obligatoria del Sobrepago *", key="motivo_sp_fp")
            
        if st.button("Registrar Adelanto", type="primary"):
            try:
                if not nro_op.strip() and not confirmar_sin_op:
                    raise ValueError("Debe tildar la confirmación si no provee un número de Orden de Pago.")
                if chk_sp.get('es_sobrepago') and not confirmar_sobrepago:
                    raise ValueError("Debe confirmar el sobrepago marcando la casilla correspondiente.")
                if chk_sp.get('es_sobrepago') and (not motivo_sobrepago or not motivo_sobrepago.strip()):
                    raise ValueError("Debe ingresar el motivo / justificación obligatoria del sobrepago.")
                    
                db.add_pago_fondos_propios(
                    obra_id=obra_id,
                    monto=monto,
                    fecha=fecha.strftime('%Y-%m-%d'),
                    nro_op=nro_op.strip() if nro_op.strip() else None,
                    observaciones=observaciones.strip() if observaciones.strip() else None,
                    cantidad_moneda_amortizada=cant_moneda_amort,
                    cotizacion_pago=cotiz_pago,
                    motivo_sobrepago=motivo_sobrepago.strip() if motivo_sobrepago else None
                )
                st.session_state['pago_fp_registrado_ok'] = True
                st.rerun()
            except ValueError as e:
                st.error(str(e))
