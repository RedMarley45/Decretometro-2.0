import streamlit as st
import os, sys
import pandas as pd

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import database as db
import importlib
importlib.reload(db)
import utils
importlib.reload(utils)

st.set_page_config(page_title="Monedas e Índices | Decretómetro 2.0", page_icon="💱", layout="wide")
utils.inject_style()

# Header con Título y Botón de Acción
if "moneda_success_msg" in st.session_state and st.session_state.moneda_success_msg:
    st.success(st.session_state.moneda_success_msg)
    st.session_state.moneda_success_msg = ""

col_title, col_add = st.columns([3, 1.2])

with col_title:
    st.title("Catálogo de Monedas e Índices 💱")
    st.markdown("Gestione las unidades de medida monetarias e índices de actualización (como las **UVIs - Ley 27.271** o **USD**) que se utilizarán para la suscripción de convenios y decretos.")

with col_add:
    st.write("")
    if "show_add_moneda_form" not in st.session_state:
        st.session_state.show_add_moneda_form = False
        
    btn_label = "❌ Cancelar" if st.session_state.show_add_moneda_form else "➕ Nueva Moneda / Índice"
    btn_type = "secondary" if st.session_state.show_add_moneda_form else "primary"
    if st.button(btn_label, use_container_width=True, type=btn_type):
        st.session_state.show_add_moneda_form = not st.session_state.show_add_moneda_form
        st.rerun()

st.markdown("---")

# Formulario de Alta
if st.session_state.show_add_moneda_form:
    st.subheader("➕ Registrar Nueva Moneda o Índice")
    with st.form("new_moneda_form"):
        col1, col2, col3 = st.columns(3)
        codigo = col1.text_input("Código *", placeholder="Ej: CAC, EUR, etc.", help="Identificador único corto en mayúsculas.").upper()
        nombre = col2.text_input("Nombre Completo *", placeholder="Ej: Índice Cámara Argentina de la Construcción")
        simbolo = col3.text_input("Símbolo o Abreviatura *", placeholder="Ej: CAC, €, etc.")
        
        col4, col5 = st.columns(2)
        tipo = col4.selectbox("Tipo *", ["Moneda", "Índice"], help="Elija 'Índice' para unidades que representan valor de construcción o vivienda (como UVI/UVA/CAC), o 'Moneda' para divisas extranjeras.")
        decimales = col5.number_input("Decimales permitidos", min_value=0, max_value=6, value=2, step=1)
        
        btn_guardar = st.form_submit_button("Guardar en Catálogo", type="primary")
        if btn_guardar:
            try:
                db.add_moneda_indice(codigo, nombre, simbolo, tipo, decimales)
                st.session_state.moneda_success_msg = f"Unidad '{codigo}' ({nombre}) registrada con éxito."
                st.session_state.show_add_moneda_form = False
                st.rerun()
            except ValueError as e:
                st.error(str(e))

# Listado y Métricas
monedas = db.get_monedas_indices(solo_activas=False)

col_m1, col_m2, col_m3, col_m4 = st.columns(4)
col_m1.metric("Total Registrados", len(monedas))
col_m2.metric("Activos", sum(1 for m in monedas if m['activo'] == 1))
col_m3.metric("Monedas Tradicionales", sum(1 for m in monedas if m['tipo'] == 'Moneda'))
col_m4.metric("Índices de Actualización", sum(1 for m in monedas if m['tipo'] == 'Índice'))

st.markdown("### Listado de Unidades Habilitadas")

if not monedas:
    st.info("No hay monedas registradas.")
else:
    data = []
    for m in monedas:
        estado_label = "🟢 Activo" if m['activo'] == 1 else "🔴 Inactivo"
        data.append({
            "ID": m['id'],
            "Código": m['codigo'],
            "Nombre": m['nombre'],
            "Símbolo": m['simbolo'],
            "Tipo": m['tipo'],
            "Decimales": m['decimales'],
            "Estado": estado_label
        })
        
    df = pd.DataFrame(data)
    st.dataframe(df, use_container_width=True, hide_index=True)
    
    st.markdown("---")
    st.subheader("✏️ Modificar Estado / Datos")
    
    opciones_editar = {m['id']: f"{m['codigo']} - {m['nombre']} ({m['simbolo']})" for m in monedas}
    sel_id = st.selectbox("Seleccione la moneda/índice para editar:", options=list(opciones_editar.keys()), format_func=lambda x: opciones_editar[x])
    
    if sel_id:
        m_sel = next(m for m in monedas if m['id'] == sel_id)
        es_ars = (m_sel['codigo'] == 'ARS')
        
        with st.form(f"form_edit_moneda_{sel_id}"):
            col_e1, col_e2, col_e3 = st.columns(3)
            e_codigo = col_e1.text_input("Código", value=m_sel['codigo'], disabled=es_ars)
            e_nombre = col_e2.text_input("Nombre", value=m_sel['nombre'])
            e_simbolo = col_e3.text_input("Símbolo", value=m_sel['simbolo'])
            
            col_e4, col_e5, col_e6 = st.columns(3)
            tipo_idx = 0 if m_sel['tipo'] == 'Moneda' else 1
            e_tipo = col_e4.selectbox("Tipo", ["Moneda", "Índice"], index=tipo_idx, disabled=es_ars)
            e_dec = col_e5.number_input("Decimales", min_value=0, max_value=6, value=int(m_sel['decimales']), step=1)
            e_activo = col_e6.checkbox("Activo para nuevas operaciones", value=bool(m_sel['activo']), disabled=es_ars)
            
            if es_ars:
                st.caption("ℹ️ El Peso Argentino (ARS) es la moneda de curso legal base del sistema y no puede desactivarse.")
                
            if st.form_submit_button("Guardar Cambios", type="primary"):
                try:
                    db.update_moneda_indice(
                        moneda_id=sel_id,
                        codigo=e_codigo,
                        nombre=e_nombre,
                        simbolo=e_simbolo,
                        tipo=e_tipo,
                        decimales=e_dec,
                        activo=e_activo
                    )
                    st.session_state.moneda_success_msg = f"Moneda '{e_codigo}' actualizada exitosamente."
                    st.rerun()
                except ValueError as e:
                    st.error(str(e))
