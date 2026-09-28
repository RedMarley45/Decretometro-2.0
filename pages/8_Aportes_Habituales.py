import streamlit as st
import pandas as pd
import datetime
import os
import sys
import io
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import database as db
import utils
from database import (
    get_aportes_funcionamiento, set_monto_funcionamiento_anio, registrar_cobro_funcionamiento, delete_anio_funcionamiento,
    get_aportes_sueldo, add_aporte_sueldo, registrar_cobro_sueldo, delete_aporte_sueldo, update_aporte_sueldo,
    get_aportes_sac, add_aporte_sac, registrar_cobro_sac, delete_aporte_sac, update_aporte_sac
)
from utils import format_currency_ar, format_date_ar

st.set_page_config(page_title="Aportes Habituales | Decretómetro", page_icon="🏦", layout="wide")
utils.inject_style()
st.title("Gestión de Aportes Habituales")

tab1, tab2 = st.tabs(["🏢 Funcionamiento", "👥 Sueldos y SAC"])

# --- TAB 1: FUNCIONAMIENTO ---
with tab1:
    st.subheader("Aportes de Funcionamiento")
    if "succ_fun" in st.session_state:
        st.success(st.session_state["succ_fun"])
        del st.session_state["succ_fun"]
    st.info("Se establece un monto fijo mensual para todo el año.")
    
    with st.expander("➕ Configurar / Actualizar Año"):
        with st.form("form_fun"):
            f_anio = st.number_input("Año", value=datetime.date.today().year, step=1)
            f_monto = st.number_input("Monto Mensual Pautado ($)", min_value=0.01, step=1000.0)
            f_submit = st.form_submit_button("Guardar Configuración Anual")
            if f_submit:
                set_monto_funcionamiento_anio(f_anio, f_monto)
                st.success(f"Configuración para {f_anio} guardada. Se generaron 12 cuotas de {format_currency_ar(f_monto)}.")
                st.rerun()

    anios_disponibles = sorted(list(set(f['anio'] for f in get_aportes_funcionamiento())), reverse=True)
    if not anios_disponibles:
        st.info("No hay aportes de funcionamiento configurados.")
    else:
        sel_anio = st.selectbox("Seleccione Año para visualizar/cobrar:", anios_disponibles)
        aportes = get_aportes_funcionamiento(sel_anio)
        
        tabla_fun = []
        for a in aportes:
            tabla_fun.append({
                "ID": a['id'],
                "Mes": f"{a['mes']:02d}/{a['anio']}",
                "Monto Pautado": a['monto_pautado'],
                "Fecha Cobro": format_date_ar(a['fecha_cobro']) if a['fecha_cobro'] else "Pendiente",
                "Estado": "✅ Cobrado" if a['fecha_cobro'] else "⏳ Pendiente"
            })
        
        df_fun_export = pd.DataFrame(tabla_fun)
        df_fun = df_fun_export.copy()
        if not df_fun.empty:
            df_fun['Monto Pautado'] = df_fun['Monto Pautado'].apply(lambda x: format_currency_ar(x))

        st.dataframe(
            df_fun,
            use_container_width=True,
            hide_index=True,
            column_config={
                "Monto Pautado": "Monto Pautado",
                "ID": st.column_config.NumberColumn(format="%d"),
            }
        )
        
        # Acciones de cobro
        st.markdown("---")
        col_c1, col_c2 = st.columns(2)
        with col_c1:
            st.write("**Registrar Cobro de Mes**")
            meses_pendientes = {a['id']: f"Mes {a['mes']:02d}" for a in aportes if not a['fecha_cobro']}
            if meses_pendientes:
                sel_aporte_id = st.selectbox("Seleccione mes a cobrar:", options=list(meses_pendientes.keys()), format_func=lambda x: meses_pendientes[x])
                c_fecha = st.date_input("Fecha de Cobro", value=datetime.date.today(), format="DD-MM-YYYY")
                if st.button("Confirmar Cobro", key="btn_confirmar_fun"):
                    if c_fecha > datetime.date.today():
                        st.error("Error: La fecha de cobro no puede ser futura.")
                    else:
                        # El monto cobrado es el pautado (cobro total según requerimiento)
                        aporte_sel = next(a for a in aportes if a['id'] == sel_aporte_id)
                        registrar_cobro_funcionamiento(sel_aporte_id, aporte_sel['monto_pautado'], c_fecha.strftime('%Y-%m-%d'))
                        st.session_state["succ_fun"] = f"Cobro registrado para {meses_pendientes[sel_aporte_id]}."
                        st.rerun()
            else:
                st.success("Todos los meses de este año están cobrados.")
        
        with col_c2:
            st.write("**Opciones de Año**")
            meses_cobrados = {a['id']: f"Mes {a['mes']:02d}" for a in aportes if a['fecha_cobro']}
            if meses_cobrados:
                with st.expander("🗑️ Eliminar Cobranza Individual"):
                    sel_del_fun = st.selectbox("Seleccione mes a resetear:", options=list(meses_cobrados.keys()), format_func=lambda x: meses_cobrados[x])
                    if st.button("Eliminar Cobro Seleccionado", use_container_width=True):
                        from database import reset_cobro_funcionamiento
                        reset_cobro_funcionamiento(sel_del_fun)
                        st.success("Cobro eliminado (vuelto a pendiente).")
                        st.rerun()

            if st.button(f"🗑️ Eliminar Año {sel_anio} completo"):
                delete_anio_funcionamiento(sel_anio)
                st.success(f"Año {sel_anio} eliminado.")
                st.rerun()

        # Exportación
        buffer = io.BytesIO()
        with pd.ExcelWriter(buffer, engine='xlsxwriter') as writer:
            df_fun_export.to_excel(writer, index=False, sheet_name=f'Funcionamiento {sel_anio}')
            workbook = writer.book
            worksheet = writer.sheets[f'Funcionamiento {sel_anio}']
            num_format = workbook.add_format({'num_format': '#,##0.00'})
            if 'Monto Pautado' in df_fun_export.columns:
                col_idx = df_fun_export.columns.get_loc("Monto Pautado")
                worksheet.set_column(col_idx, col_idx, 18, num_format)
        st.download_button(
            label="📥 Exportar este año a Excel",
            data=buffer.getvalue(),
            file_name=f"funcionamiento_{sel_anio}.xlsx",
            mime="application/vnd.ms-excel"
        )

# --- TAB 2: SUELDOS Y SAC ---
with tab2:
    st.subheader("Gestión de Aportes para Sueldos y SAC")
    if "succ_sueldo_sac" in st.session_state:
        st.success(st.session_state["succ_sueldo_sac"])
        del st.session_state["succ_sueldo_sac"]
    
    # Inicializar dataframes para evitar NameError en exportación si no hay datos
    df_s = pd.DataFrame()
    df_sac = pd.DataFrame()
    
    col_l, col_r = st.columns(2)
    
    with col_l:
        st.write("### 👥 Sueldos")
        with st.expander("➕ Cargar Pedido de Sueldos"):
            with st.form("form_sueldo"):
                col1, col2 = st.columns(2)
                s_mes = col1.selectbox("Mes", range(1, 13), index=datetime.date.today().month - 1, key="s_mes_in")
                s_anio = col2.number_input("Año", value=datetime.date.today().year, step=1, key="s_anio_in")
                s_monto = st.number_input("Monto Pedido ($)", min_value=0.01, step=1000.0, key="s_monto_in")
                s_fecha_p = st.date_input("Fecha del Pedido", value=datetime.date.today(), format="DD-MM-YYYY", key="s_fecha_p_in")
                s_submit = st.form_submit_button("Guardar Pedido")
                if s_submit:
                    if s_fecha_p > datetime.date.today():
                        st.error("Error: La fecha del pedido no puede ser futura.")
                    else:
                        add_aporte_sueldo(s_anio, s_mes, s_monto, s_fecha_p.strftime('%Y-%m-%d'))
                        st.session_state["succ_sueldo_sac"] = f"Pedido de fondos para Sueldos del periodo {s_mes:02d}/{s_anio} registrado con éxito."
                        for k in ["s_mes_in", "s_anio_in", "s_monto_in", "s_fecha_p_in"]:
                            if k in st.session_state:
                                del st.session_state[k]
                        st.rerun()

        sueldos = get_aportes_sueldo()
        if not sueldos:
            st.info("No hay pedidos de sueldos registrados.")
        else:
            tabla_s = []
            for s in sueldos:
                saldo = s['monto_pedido'] - (s['monto_cobrado'] or 0)
                # Lógica de icono según estado
                icon = "⌛" # Pendiente
                if s['estado'] == 'Cobrado': icon = "✅"
                elif s['estado'] == 'Parcial': icon = "🟡"
                elif s['estado'] == 'Renunciado': icon = "🛑"
                
                tabla_s.append({
                    "ID": s['id'],
                    "Periodo": f"{s['mes']:02d}/{s['anio']}",
                    "Monto Solicitado": s['monto_pedido'],
                    "Monto Ingresado": s['monto_cobrado'] or 0,
                    "Saldo Pendiente": saldo if s['estado'] != 'Renunciado' else 0,
                    "Fecha": format_date_ar(s['fecha_cobro'] or s['fecha_renuncia']) if (s['fecha_cobro'] or s['fecha_renuncia']) else "---",
                    "Estado": icon
                })
            df_s_export = pd.DataFrame(tabla_s)
            df_s = df_s_export.copy()
            if not df_s.empty:
                df_s['Monto Solicitado'] = df_s['Monto Solicitado'].apply(lambda x: format_currency_ar(x))
                df_s['Monto Ingresado'] = df_s['Monto Ingresado'].apply(lambda x: format_currency_ar(x))
                df_s['Saldo Pendiente'] = df_s['Saldo Pendiente'].apply(lambda x: format_currency_ar(x))

            st.dataframe(df_s, use_container_width=True, hide_index=True)
            
            with st.expander("⚙️ Acciones Sueldos"):
                st.write("**Registrar Cobro**")
                pendientes_s = {s['id']: f"{s['mes']:02d}/{s['anio']} (Ped: {format_currency_ar(s['monto_pedido'])})" 
                                for s in sueldos if s['estado'] in ['Pendiente', 'Parcial']}
                if pendientes_s:
                    sel_s_id = st.selectbox("Seleccione pedido:", options=list(pendientes_s.keys()), format_func=lambda x: pendientes_s[x])
                    s_sel = next(s for s in sueldos if s['id'] == sel_s_id)
                    saldo_actual = s_sel['monto_pedido'] - (s_sel['monto_cobrado'] or 0)
                    
                    c1, c2 = st.columns(2)
                    monto_a_cobrar = c1.number_input("Monto a Ingresar ($)", min_value=0.01, max_value=float(saldo_actual), value=float(saldo_actual))
                    sc_fecha = c2.date_input("Fecha Cobro", value=datetime.date.today(), key="sc_fecha_in", format="DD-MM-YYYY")
                    
                    c_btn1, c_btn2 = st.columns(2)
                    if c_btn1.button("Confirmar Cobro", key="btn_confirmar_sueldo", use_container_width=True):
                        if sc_fecha > datetime.date.today():
                            st.error("Error: La fecha de cobro no puede ser futura.")
                        else:
                            registrar_cobro_sueldo(sel_s_id, monto_a_cobrar, sc_fecha.strftime('%Y-%m-%d'))
                            st.session_state["succ_sueldo_sac"] = f"Ingreso de {format_currency_ar(monto_a_cobrar)} para sueldo {pendientes_s[sel_s_id]} registrado."
                            st.rerun()
                    
                    if s_sel['estado'] == 'Parcial':
                        if c_btn2.button("🚫 Renunciar a la diferencia", key="btn_renunciar_sueldo", use_container_width=True, help="Cierra el pedido marcando la diferencia como incobrable."):
                            from database import renunciar_aporte_sueldo
                            renunciar_aporte_sueldo(sel_s_id, datetime.date.today().strftime('%Y-%m-%d'))
                            st.warning(f"Se ha renunciado a la diferencia del periodo {s_sel['mes']:02d}/{s_sel['anio']}.")
                            st.rerun()
                
                st.write("---")
                st.write("**Eliminar Pedido**")
                del_s_id = st.number_input("ID a eliminar", min_value=0, step=1, key="del_s_id")
                if del_s_id > 0:
                    confirm_del_s = st.checkbox(
                        f"⚠️ Confirmo que deseo eliminar el pedido con ID {del_s_id}",
                        key="confirm_del_s"
                    )
                    if st.button("🗑️ Eliminar Sueldo", key="btn_del_sueldo", disabled=not confirm_del_s):
                        delete_aporte_sueldo(del_s_id)
                        st.success("Eliminado correctamente.")
                        st.rerun()
                else:
                    st.caption("Ingrese un ID válido (mayor a 0) para habilitar la eliminación.")

    with col_r:
        st.write("### 💰 SAC (Aguinaldo)")
        with st.expander("➕ Cargar Pedido de SAC"):
            with st.form("form_sac"):
                col1, col2 = st.columns(2)
                sac_cuota = col1.selectbox("Cuota", [1, 2], format_func=lambda x: f"Cuota {x}", key="sac_cuota_in")
                sac_anio = col2.number_input("Año", value=datetime.date.today().year, step=1, key="sac_anio_in")
                sac_monto = st.number_input("Monto Pedido ($)", min_value=0.01, step=1000.0, key="sac_monto_in")
                sac_fecha_p = st.date_input("Fecha del Pedido", value=datetime.date.today(), key="sac_fecha_p_in", format="DD-MM-YYYY")
                sac_submit = st.form_submit_button("Guardar Pedido SAC")
                if sac_submit:
                    if sac_fecha_p > datetime.date.today():
                        st.error("Error: La fecha del pedido no puede ser futura.")
                    else:
                        add_aporte_sac(sac_anio, sac_cuota, sac_monto, sac_fecha_p.strftime('%Y-%m-%d'))
                        st.session_state["succ_sueldo_sac"] = f"Pedido SAC Cuota {sac_cuota} del año {sac_anio} registrado con éxito."
                        for k in ["sac_cuota_in", "sac_anio_in", "sac_monto_in", "sac_fecha_p_in"]:
                            if k in st.session_state:
                                del st.session_state[k]
                        st.rerun()

        sacs = get_aportes_sac()
        if not sacs:
            st.info("No hay pedidos de SAC registrados.")
        else:
            tabla_sac = []
            for s in sacs:
                saldo = s['monto_pedido'] - (s['monto_cobrado'] or 0)
                icon = "⌛"
                if s['estado'] == 'Cobrado': icon = "✅"
                elif s['estado'] == 'Parcial': icon = "🟡"
                elif s['estado'] == 'Renunciado': icon = "🛑"
                
                tabla_sac.append({
                    "ID": s['id'],
                    "Cuota": f"{s['cuota_nro']}° - {s['anio']}",
                    "Monto Solicitado": s['monto_pedido'],
                    "Monto Ingresado": s['monto_cobrado'] or 0,
                    "Saldo Pendiente": saldo if s['estado'] != 'Renunciado' else 0,
                    "Fecha": format_date_ar(s['fecha_cobro'] or s['fecha_renuncia']) if (s['fecha_cobro'] or s['fecha_renuncia']) else "---",
                    "Estado": icon
                })
            df_sac_export = pd.DataFrame(tabla_sac)
            df_sac = df_sac_export.copy()
            if not df_sac.empty:
                df_sac['Monto Solicitado'] = df_sac['Monto Solicitado'].apply(lambda x: format_currency_ar(x))
                df_sac['Monto Ingresado'] = df_sac['Monto Ingresado'].apply(lambda x: format_currency_ar(x))
                df_sac['Saldo Pendiente'] = df_sac['Saldo Pendiente'].apply(lambda x: format_currency_ar(x))

            st.dataframe(df_sac, use_container_width=True, hide_index=True)
            
            with st.expander("⚙️ Acciones SAC"):
                st.write("**Registrar Cobro**")
                pendientes_sac = {s['id']: f"{s['cuota_nro']}° - {s['anio']} (Ped: {format_currency_ar(s['monto_pedido'])})" 
                                  for s in sacs if s['estado'] in ['Pendiente', 'Parcial']}
                if pendientes_sac:
                    sel_sac_id = st.selectbox("Seleccione pedido SAC:", options=list(pendientes_sac.keys()), format_func=lambda x: pendientes_sac[x])
                    sac_sel = next(s for s in sacs if s['id'] == sel_sac_id)
                    saldo_actual_sac = sac_sel['monto_pedido'] - (sac_sel['monto_cobrado'] or 0)
                    
                    c1, c2 = st.columns(2)
                    monto_a_cobrar_sac = c1.number_input("Monto SAC a Ingresar ($)", min_value=0.01, max_value=float(saldo_actual_sac), value=float(saldo_actual_sac))
                    sac_c_fecha = c2.date_input("Fecha Cobro SAC", value=datetime.date.today(), key="sac_c_fecha_in", format="DD-MM-YYYY")
                    
                    c_btn1, c_btn2 = st.columns(2)
                    if c_btn1.button("Confirmar Cobro SAC", key="btn_confirmar_sac", use_container_width=True):
                        if sac_c_fecha > datetime.date.today():
                            st.error("Error: La fecha de cobro no puede ser futura.")
                        else:
                            registrar_cobro_sac(sel_sac_id, monto_a_cobrar_sac, sac_c_fecha.strftime('%Y-%m-%d'))
                            st.session_state["succ_sueldo_sac"] = f"Ingreso de {format_currency_ar(monto_a_cobrar_sac)} para SAC {pendientes_sac[sel_sac_id]} registrado."
                            st.rerun()

                    if sac_sel['estado'] == 'Parcial':
                        if c_btn2.button("🚫 Renunciar a la diferencia", key="btn_renunciar_sac", use_container_width=True, help="Cierra el pedido de SAC marcando la diferencia como incobrable."):
                            from database import renunciar_aporte_sac
                            renunciar_aporte_sac(sel_sac_id, datetime.date.today().strftime('%Y-%m-%d'))
                            st.warning(f"Se ha renunciado a la diferencia del SAC {sac_sel['cuota_nro']}° - {sac_sel['anio']}.")
                            st.rerun()
                
                st.write("---")
                st.write("**Eliminar Pedido**")
                del_sac_id = st.number_input("ID a eliminar", min_value=0, step=1, key="del_sac_id")
                if del_sac_id > 0:
                    confirm_del_sac = st.checkbox(
                        f"⚠️ Confirmo que deseo eliminar el pedido SAC con ID {del_sac_id}",
                        key="confirm_del_sac"
                    )
                    if st.button("🗑️ Eliminar SAC", key="btn_del_sac", disabled=not confirm_del_sac):
                        delete_aporte_sac(del_sac_id)
                        st.success("Eliminado correctamente.")
                        st.rerun()
                else:
                    st.caption("Ingrese un ID válido (mayor a 0) para habilitar la eliminación.")

    st.markdown("---")
    st.write("### 📥 Exportación")
    col_ex1, col_ex2 = st.columns(2)
    
    # Exportación Sueldos
    if 'df_s_export' in locals() and not df_s_export.empty:
        buffer_s = io.BytesIO()
        with pd.ExcelWriter(buffer_s, engine='xlsxwriter') as writer:
            df_s_export.to_excel(writer, index=False, sheet_name='Sueldos')
            workbook = writer.book
            worksheet = writer.sheets['Sueldos']
            num_format = workbook.add_format({'num_format': '#,##0.00'})
            for m_col in ["Monto Solicitado", "Monto Ingresado", "Saldo Pendiente"]:
                if m_col in df_s_export.columns:
                    c_idx = df_s_export.columns.get_loc(m_col)
                    worksheet.set_column(c_idx, c_idx, 18, num_format)
        col_ex1.download_button(label="📥 Exportar Sueldos", data=buffer_s.getvalue(), file_name="sueldos.xlsx")

    # Exportación SAC
    if 'df_sac_export' in locals() and not df_sac_export.empty:
        buffer_sac = io.BytesIO()
        with pd.ExcelWriter(buffer_sac, engine='xlsxwriter') as writer:
            df_sac_export.to_excel(writer, index=False, sheet_name='SAC')
            workbook = writer.book
            worksheet = writer.sheets['SAC']
            num_format = workbook.add_format({'num_format': '#,##0.00'})
            for m_col in ["Monto Solicitado", "Monto Ingresado", "Saldo Pendiente"]:
                if m_col in df_sac_export.columns:
                    c_idx = df_sac_export.columns.get_loc(m_col)
                    worksheet.set_column(c_idx, c_idx, 18, num_format)
        col_ex2.download_button(label="📥 Exportar SAC", data=buffer_sac.getvalue(), file_name="sac.xlsx")
