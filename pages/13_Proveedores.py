import streamlit as st
import os, sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import database as db
import importlib
importlib.reload(db)
import utils
importlib.reload(utils)

st.set_page_config(page_title="Proveedores | Decretómetro", page_icon="🤝", layout="wide")
utils.inject_style()

# Header con Título y Botón Agregar Proveedor
if "prov_success_msg" in st.session_state and st.session_state.prov_success_msg:
    st.success(st.session_state.prov_success_msg)
    st.session_state.prov_success_msg = ""

col_title, col_add = st.columns([3, 1.2])

with col_title:
    st.title("Gestión de Proveedores 🤝")

with col_add:
    st.write("")
    if "show_add_prov_form" not in st.session_state:
        st.session_state.show_add_prov_form = False
        
    btn_label = "❌ Cancelar" if st.session_state.show_add_prov_form else "➕ Agregar Proveedor"
    btn_type = "secondary" if st.session_state.show_add_prov_form else "primary"
    if st.button(btn_label, use_container_width=True, type=btn_type):
        st.session_state.show_add_prov_form = not st.session_state.show_add_prov_form
        st.rerun()

st.markdown("---")

# Formulario de Alta de Proveedor (Si está activo)
if st.session_state.show_add_prov_form:
    st.subheader("➕ Registrar Nuevo Proveedor")
    with st.form("new_proveedor_form"):
        col_f1, col_f2, col_f3 = st.columns(3)
        n_razon = col_f1.text_input("Razón Social *", placeholder="Ej: Constructora San Martín S.A.")
        n_cuit = col_f2.text_input("CUIT *", placeholder="20-12345678-9", help="Formato AFIP: XX-XXXXXXXX-X (dos dígitos, guión, 8 dígitos, guión, 1 dígito).")
        n_tipo = col_f3.selectbox("Tipo de Proveedor *", ["Obra", "Funcionamiento"])
        
        if st.form_submit_button("Guardar Proveedor", type="primary"):
            try:
                if n_tipo == "Obra":
                    prov_id = db.add_proveedor_obra(n_razon, n_cuit)
                else:
                    prov_id = db.add_proveedor_funcionamiento(n_razon, n_cuit)
                st.session_state.prov_success_msg = f"Proveedor registrado con éxito en el catálogo de {n_tipo}."
                st.session_state.show_add_prov_form = False
                st.rerun()
            except ValueError as e:
                st.error(str(e))

# Controles de Filtros y Búsqueda
col_s1, col_s2 = st.columns([3, 1])
busqueda = col_s1.text_input("🔍 Buscar por Razón Social o CUIT:", placeholder="Ej: 20-12345678-9 o Constructora...")
filtro_tipo = col_s2.selectbox("Filtrar por Tipo:", ["Todos", "Obra", "Funcionamiento"])

# Obtener catálogo unificado de proveedores
todos_provs = db.get_todos_proveedores(only_active=False)

# Aplicar filtros
if filtro_tipo != "Todos":
    todos_provs = [p for p in todos_provs if p['tipo'] == filtro_tipo]

if busqueda.strip():
    term = busqueda.strip().lower()
    todos_provs = [
        p for p in todos_provs
        if term in p['razon_social'].lower() or term in p['cuit'].lower()
    ]

# Tabla / Listado de Proveedores
if not todos_provs:
    st.info("No se encontraron proveedores registrados con los criterios seleccionados.")
else:
    st.subheader(f"Catálogo de Proveedores ({len(todos_provs)} registros)")
    
    # Encabezados de tabla
    h_c1, h_c2, h_c3, h_c4, h_c5 = st.columns([3, 2, 1.8, 1.5, 3.5])
    h_c1.markdown("**Razón Social**")
    h_c2.markdown("**CUIT**")
    h_c3.markdown("**Tipo**")
    h_c4.markdown("**Estado**")
    h_c5.markdown("**Acciones**")
    st.divider()
    
    for p in todos_provs:
        c1, c2, c3, c4, c5 = st.columns([3, 2, 1.8, 1.5, 3.5])
        
        c1.write(f"**{p['razon_social']}**")
        c2.code(p['cuit'])
        
        tipo_badge = "🏗️ Obra" if p['tipo'] == "Obra" else "💼 Funcionamiento"
        c3.write(tipo_badge)
        
        estado_txt = "🟢 Habilitado" if p['activo'] == 1 else "🔴 Inhabilitado"
        c4.write(estado_txt)
        
        # Botones de Acción
        btn_col1, btn_col2, btn_col3 = c5.columns(3)
        
        # Key única por proveedor
        key_id = f"{p['tipo']}_{p['id']}"
        
        # 1. Editar
        if btn_col1.button("✏️ Editar", key=f"edit_btn_{key_id}", use_container_width=True):
            st.session_state[f"editing_{key_id}"] = not st.session_state.get(f"editing_{key_id}", False)
            st.rerun()
            
        # 2. Toggle Habilitar/Deshabilitar
        toggle_label = "🚫 Inhabilitar" if p['activo'] == 1 else "🟢 Habilitar"
        toggle_type = "secondary" if p['activo'] == 1 else "primary"
        if btn_col2.button(toggle_label, key=f"toggle_btn_{key_id}", type=toggle_type, use_container_width=True):
            nuevo_st = 0 if p['activo'] == 1 else 1
            if p['tipo'] == "Obra":
                db.update_proveedor_obra_estado(p['id'], nuevo_st)
            else:
                db.update_proveedor_funcionamiento_estado(p['id'], nuevo_st)
            st.rerun()
            
        # 3. Eliminar (Deshabilitado si está vinculado)
        del_disabled = p['is_linked']
        help_del = "No se puede eliminar un proveedor vinculado a obras o gastos registrados." if del_disabled else None
        if btn_col3.button("🗑️ Eliminar", key=f"del_btn_{key_id}", disabled=del_disabled, help=help_del, use_container_width=True):
            try:
                if p['tipo'] == "Obra":
                    db.delete_proveedor_obra(p['id'])
                else:
                    db.delete_proveedor_funcionamiento(p['id'])
                st.session_state.prov_success_msg = "Proveedor eliminado con éxito."
                st.rerun()
            except ValueError as e:
                st.error(str(e))

        # Sub-formulario de Edición si está activo
        if st.session_state.get(f"editing_{key_id}", False):
            with st.expander(f"✏️ Editando: {p['razon_social']} ({p['tipo']})", expanded=True):
                with st.form(f"form_edit_{key_id}"):
                    fe_razon = st.text_input("Razón Social *", value=p['razon_social'])
                    fe_cuit = st.text_input("CUIT *", value=p['cuit'])
                    
                    c_b1, c_b2 = st.columns(2)
                    if c_b1.form_submit_button("Guardar Cambios", type="primary"):
                        try:
                            if p['tipo'] == "Obra":
                                db.update_proveedor_obra(p['id'], fe_razon, fe_cuit, p['activo'])
                            else:
                                db.update_proveedor_funcionamiento(p['id'], fe_razon, fe_cuit, p['activo'])
                            st.session_state[f"editing_{key_id}"] = False
                            st.session_state.prov_success_msg = "Proveedor actualizado correctamente."
                            st.rerun()
                        except ValueError as e:
                            st.error(str(e))
                            
                    if c_b2.form_submit_button("Cancelar"):
                        st.session_state[f"editing_{key_id}"] = False
                        st.rerun()
        st.divider()
