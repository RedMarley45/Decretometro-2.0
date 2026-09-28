import streamlit as st
import os, sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import utils
import importlib
importlib.reload(utils)
import database as db

st.set_page_config(page_title="Gastos de Funcionamiento | Decretometro", page_icon="\U0001f4bc", layout="wide")
utils.inject_style()

st.title("\U0001f4bc Gastos de Funcionamiento")
st.caption("Catalogo de gastos de funcionamiento. Administra el catalogo, sus proveedores asociados y su estado de habilitacion.")
st.markdown("---")


def _can_delete(gasto):
    """Verifica si un gasto puede eliminarse (sin historial asociado)."""
    import sqlite3 as _sq
    _db_path = db.DB_PATH
    _conn = _sq.connect(_db_path)
    _conn.row_factory = _sq.Row
    _cur = _conn.cursor()
    exp = gasto["expediente_imuh"]
    _cur.execute("SELECT COUNT(*) as cnt FROM cobro_desvios WHERE gasto_expediente_imuh = ?", (exp,))
    cnt_d = _cur.fetchone()["cnt"]
    _cur.execute("SELECT COUNT(*) as cnt FROM cobro_reserva_usos WHERE gasto_expediente_imuh = ?", (exp,))
    cnt_r = _cur.fetchone()["cnt"]
    _conn.close()
    return cnt_d == 0 and cnt_r == 0


# ─── Carga de datos ───────────────────────────────────────────────────────────
gastos_all = db.get_gastos_funcionamiento(only_active=False)
provs_fun_all = db.get_proveedores_funcionamiento(only_active=False)
provs_fun_act = db.get_proveedores_funcionamiento(only_active=True)

# ─── Boton nuevo gasto ────────────────────────────────────────────────────────
_, col_btn = st.columns([6, 2])
with col_btn:
    if st.button("\u2795 Nuevo Gasto FUN", type="primary", use_container_width=True):
        st.session_state["show_new_gasto_form"] = not st.session_state.get("show_new_gasto_form", False)

if st.session_state.get("show_new_gasto_form", False):
    with st.expander("\U0001f4dd Registrar Nuevo Gasto de Funcionamiento", expanded=True):
        with st.form("form_new_gasto_fun"):
            new_exp = st.text_input(
                "Nro. Expediente IMUH *",
                placeholder="Ej: 80001234-I-2026",
                help="Formato: 7 u 8 digitos - Letra mayuscula - 4 digitos"
            )
            new_nombre = st.text_input(
                "Nombre del expediente *",
                max_chars=50,
                placeholder="Hasta 50 caracteres"
            )
            opc_prov_new = {0: "\u2014 Sin proveedor asignado \u2014"}
            for p in sorted(provs_fun_act, key=lambda x: x["razon_social"]):
                opc_prov_new[p["id"]] = f"{p['razon_social']} (CUIT: {p['cuit']})"
            new_prov_id = st.selectbox(
                "Proveedor *",
                options=list(opc_prov_new.keys()),
                format_func=lambda x: opc_prov_new[x]
            )
            col_save, col_cancel = st.columns(2)
            submitted = col_save.form_submit_button("\U0001f4be Guardar Gasto", type="primary")
            cancelled = col_cancel.form_submit_button("Cancelar")

        if submitted:
            err = None
            if not new_exp.strip():
                err = "El Nro. de Expediente IMUH es obligatorio."
            elif not utils.validar_expediente_imuh(new_exp.strip()):
                err = "El Nro. de Expediente IMUH no tiene un formato valido. Usa: 80001234-I-2026"
            elif not new_nombre.strip():
                err = "El nombre del expediente es obligatorio."
            if err:
                st.error(err)
            else:
                try:
                    target_prov = new_prov_id if new_prov_id != 0 else None
                    db.add_gasto_funcionamiento(new_nombre.strip(), new_exp.strip(), target_prov)
                    st.success("\u2705 Gasto de Funcionamiento registrado correctamente.")
                    st.session_state["show_new_gasto_form"] = False
                    st.rerun()
                except ValueError as e:
                    st.error(str(e))
        if cancelled:
            st.session_state["show_new_gasto_form"] = False
            st.rerun()

st.divider()

# ─── Filtros ──────────────────────────────────────────────────────────────────
st.markdown("#### \U0001f50d Filtros")
col_f1, col_f2, col_f3 = st.columns(3)
filtro_exp = col_f1.text_input("Buscar por Nro. Expediente", placeholder="Ej: 8000231")
filtro_nombre = col_f2.text_input("Buscar por nombre del expediente", placeholder="Ej: Contratacion")
prov_opc_f = {"": "\u2014 Todos los proveedores \u2014"}
for p in sorted(provs_fun_all, key=lambda x: x["razon_social"]):
    prov_opc_f[str(p["id"])] = p["razon_social"]
filtro_prov_key = col_f3.selectbox("Filtrar por proveedor", options=list(prov_opc_f.keys()), format_func=lambda x: prov_opc_f[x])

gastos_filtrados = gastos_all
if filtro_exp.strip():
    gastos_filtrados = [g for g in gastos_filtrados if filtro_exp.strip().lower() in (g["expediente_imuh"] or "").lower()]
if filtro_nombre.strip():
    gastos_filtrados = [g for g in gastos_filtrados if filtro_nombre.strip().lower() in (g["nombre"] or "").lower()]
if filtro_prov_key:
    gastos_filtrados = [g for g in gastos_filtrados if str(g.get("proveedor_id", "")) == filtro_prov_key]

# ─── Paginacion ───────────────────────────────────────────────────────────────
PAGE_SIZE = 10
total = len(gastos_filtrados)
total_pages = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)

filtro_key = (filtro_exp, filtro_nombre, filtro_prov_key)
if st.session_state.get("_last_filtros_gasto") != filtro_key:
    st.session_state["gasto_page"] = 1
    st.session_state["_last_filtros_gasto"] = filtro_key
if "gasto_page" not in st.session_state:
    st.session_state["gasto_page"] = 1

page = st.session_state["gasto_page"]
inicio = (page - 1) * PAGE_SIZE
gastos_pagina = gastos_filtrados[inicio: inicio + PAGE_SIZE]

# Controles de paginacion
col_pag1, col_pag2, col_pag3 = st.columns([1, 3, 1])
with col_pag1:
    if st.button("\u25c0 Anterior", disabled=(page <= 1), use_container_width=True):
        st.session_state["gasto_page"] -= 1
        st.rerun()
col_pag2.markdown(f"<div style='text-align:center; padding-top:8px;'><b>{total}</b> resultado(s) \u2014 Pagina <b>{page}</b> de <b>{total_pages}</b></div>", unsafe_allow_html=True)
with col_pag3:
    if st.button("Siguiente \u25b6", disabled=(page >= total_pages), use_container_width=True):
        st.session_state["gasto_page"] += 1
        st.rerun()

st.markdown("---")

# ─── Encabezados tabla ────────────────────────────────────────────────────────
hdr = st.columns([2, 3, 3, 2])
hdr[0].markdown("**Nro. Expediente IMUH**")
hdr[1].markdown("**Nombre del expediente**")
hdr[2].markdown("**Proveedor asociado**")
hdr[3].markdown("**Acciones**")
st.markdown("---")

for g in gastos_pagina:
    gasto_id = g["id"]
    activo = g["activo"] == 1
    prov_txt = g.get("proveedor_razon_social") or "\u2014"
    estado_badge = "" if activo else " \U0001f534 *(Inhabilitado)*"

    # ── Modo edicion ──────────────────────────────────────────────────────────
    if st.session_state.get(f"edit_gasto_{gasto_id}", False):
        st.markdown(f"**\u270f\ufe0f Editando:** {g['nombre']}")
        with st.form(f"form_edit_gasto_{gasto_id}"):
            edit_exp = st.text_input("Nro. Expediente IMUH *", value=g["expediente_imuh"], help="Formato: 7 u 8 digitos - Letra mayuscula - 4 digitos")
            edit_nombre = st.text_input("Nombre del expediente *", value=g["nombre"], max_chars=50)
            opc_prov_edit = {0: "\u2014 Sin proveedor asignado \u2014"}
            for p in sorted(provs_fun_all, key=lambda x: x["razon_social"]):
                if p["activo"] == 1 or p["id"] == g.get("proveedor_id"):
                    opc_prov_edit[p["id"]] = f"{p['razon_social']} (CUIT: {p['cuit']})"
            curr_pid = g.get("proveedor_id") or 0
            if curr_pid not in opc_prov_edit:
                curr_pid = 0
            edit_prov_id = st.selectbox("Proveedor *", options=list(opc_prov_edit.keys()), format_func=lambda x: opc_prov_edit[x], index=list(opc_prov_edit.keys()).index(curr_pid))
            col_s, col_c = st.columns(2)
            save_edit = col_s.form_submit_button("\U0001f4be Guardar cambios", type="primary")
            cancel_edit = col_c.form_submit_button("Cancelar")
        if save_edit:
            try:
                target_prov = edit_prov_id if edit_prov_id != 0 else None
                db.update_gasto_funcionamiento(gasto_id, edit_nombre, edit_exp, target_prov)
                st.session_state[f"edit_gasto_{gasto_id}"] = False
                st.success("\u2705 Gasto actualizado correctamente.")
                st.rerun()
            except ValueError as e:
                st.error(str(e))
        if cancel_edit:
            st.session_state[f"edit_gasto_{gasto_id}"] = False
            st.rerun()
        st.divider()
        continue

    # ── Vista normal ──────────────────────────────────────────────────────────
    col1, col2, col3, col4 = st.columns([2, 3, 3, 2])
    col1.write(f"`{g['expediente_imuh']}`{estado_badge}")
    col2.write(g["nombre"])
    col3.caption(f"\U0001f91d {prov_txt}")

    btn_cols = col4.columns(3)

    if btn_cols[0].button("\u270f\ufe0f", key=f"btn_edit_{gasto_id}", help="Editar"):
        st.session_state[f"edit_gasto_{gasto_id}"] = True
        st.rerun()

    lbl_toggle = "\U0001f6ab" if activo else "\U0001f7e2"
    tip_toggle = "Inhabilitar" if activo else "Habilitar"
    if btn_cols[1].button(lbl_toggle, key=f"btn_toggle_{gasto_id}", help=tip_toggle):
        db.update_gasto_funcionamiento_estado(gasto_id, 0 if activo else 1)
        st.rerun()

    can_del = _can_delete(g)
    if can_del:
        if btn_cols[2].button("\U0001f5d1\ufe0f", key=f"btn_del_{gasto_id}", help="Eliminar"):
            st.session_state[f"confirm_del_{gasto_id}"] = True

        if st.session_state.get(f"confirm_del_{gasto_id}", False):
            st.warning(f"\u26a0\ufe0f Confirmas eliminar el gasto **{g['nombre']}** (`{g['expediente_imuh']}`)? Esta accion es irreversible.")
            col_conf1, col_conf2 = st.columns(2)
            if col_conf1.button("\u2705 Si, eliminar", key=f"conf_del_yes_{gasto_id}", type="primary"):
                try:
                    db.delete_gasto_funcionamiento(gasto_id)
                    st.session_state.pop(f"confirm_del_{gasto_id}", None)
                    st.success("Gasto eliminado correctamente.")
                    st.rerun()
                except ValueError as e:
                    st.error(str(e))
            if col_conf2.button("Cancelar", key=f"conf_del_no_{gasto_id}"):
                st.session_state.pop(f"confirm_del_{gasto_id}", None)
                st.rerun()
    else:
        btn_cols[2].button("\U0001f5d1\ufe0f", key=f"btn_del_{gasto_id}", disabled=True, help="No puede eliminarse: tiene movimientos asociados")

    st.divider()
