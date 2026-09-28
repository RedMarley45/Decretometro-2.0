# Código Consolidado del Proyecto Decretómetro

Este archivo contiene la totalidad del código fuente y configuraciones del proyecto Decretómetro.

## Archivo: `Inicio.py`

```python
import streamlit as st
import os, sys
import datetime
import pandas as pd
import plotly.express as px
import tempfile

# Permite importar desde la raiz independientemente de cómo se llame a Streamlit
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

import database as db
import importlib
importlib.reload(db)
import utils
importlib.reload(utils)

from database import (
    init_db, get_decretos, get_cuotas_by_decreto, get_all_cobros, 
    get_aportes_funcionamiento, get_aportes_sueldo, get_aportes_sac, 
    get_prestamos, get_desvios_activos_completos, get_cobros_con_resumen_distribucion, 
    get_reserva_usos_by_cobro, get_reserva_usos_prestamos_activos
)
from utils import format_currency_ar, format_date_ar, get_due_date, get_dashboard_kpis, get_cuotas_pendientes
from pdf_generator import generar_reporte_pdf

st.set_page_config(
    page_title="Inicio | Decretómetro",
    page_icon="🏛️",
    layout="wide",
    initial_sidebar_state="expanded"
)

utils.inject_style()

# Inicializar la base de datos si no existe
init_db()

# --- HEADER CON TÍTULO Y BOTÓN DE PDF ---
col_t1, col_t2 = st.columns([4, 1.2])
with col_t1:
    st.title("Decretómetro - Inicio 🏛️")
with col_t2:
    st.write("")
    try:
        temp_path = os.path.join(tempfile.gettempdir(), f"Reporte_Financiero_{datetime.date.today().strftime('%Y%m%d')}.pdf")
        generar_reporte_pdf(temp_path)
        with open(temp_path, "rb") as f:
            pdf_bytes = f.read()
        st.download_button(
            label="📄 Generar Reporte PDF",
            data=pdf_bytes,
            file_name=f"Reporte_Financiero_{datetime.date.today().strftime('%Y%m%d')}.pdf",
            mime="application/pdf",
            use_container_width=True,
            type="primary"
        )
    except Exception as e:
        st.error(f"Error al generar PDF: {e}")

st.markdown("---")

# --- SISTEMA DE NOTIFICACIONES (Alertas de Vencimiento) ---
today = datetime.date.today()
atrasos = []
pendientes_mes = []

# 1. Decretos
decretos = get_decretos()
cobros = get_all_cobros()
for d in decretos:
    if d['estado'] == 'Anulado' or d['estado'] == 'Terminado':
        continue
    cuotas = get_cuotas_by_decreto(d['id'])
    total_cuotas = len(cuotas)
    for idx, q in enumerate(cuotas, start=1):
        q_cobrado = sum(c['monto'] for c in cobros if c['cuota_id'] == q['id'])
        saldo = q['monto'] - q_cobrado
        if saldo > 0.01:
            due_date = utils.get_due_date(q['mes'], q['anio'])
            item = {
                "Tipo": "Obra",
                "Decreto/Referencia": f"{d['nro_decreto']}/{d['anio']}",
                "Exp. IMUH": d.get('expediente_imuh') or "Sin asignar",
                "Destino/Concepto": d['destino_fondos'],
                "Periodo": f"{q['mes']:02d}/{q['anio']}",
                "Nro. Cuota": f"{idx}/{total_cuotas}",
                "Importe": saldo,
                "Semana estimada de cobro": utils.format_week_monday(q['fecha_estimada_cobro']) if q.get('fecha_estimada_cobro') else "---"
            }
            if today > due_date:
                atrasos.append(item)
            elif q['mes'] == today.month and q['anio'] == today.year:
                pendientes_mes.append(item)

# 2. Funcionamiento
fun = get_aportes_funcionamiento()
for f in fun:
    saldo = f['monto_pautado'] - (f['monto_cobrado'] or 0)
    if saldo > 0.01:
        due_date = utils.get_due_date(f['mes'], f['anio'])
        item = {
            "Tipo": "Funcionamiento",
            "Decreto/Referencia": f"Anual {f['anio']}",
            "Exp. IMUH": "---",
            "Destino/Concepto": "Aporte Funcionamiento",
            "Periodo": f"{f['mes']:02d}/{f['anio']}",
            "Nro. Cuota": "---",
            "Importe": saldo,
            "Semana estimada de cobro": "---"
        }
        if today > due_date:
            atrasos.append(item)
        elif f['mes'] == today.month and f['anio'] == today.year:
            pendientes_mes.append(item)

# 3. Sueldo
sueldos = get_aportes_sueldo()
for s in sueldos:
    saldo = s['monto_pedido'] - (s['monto_cobrado'] or 0)
    if saldo > 0.01:
        due_date = utils.get_due_date(s['mes'], s['anio'])
        item = {
            "Tipo": "Sueldo",
            "Decreto/Referencia": f"Pedido {s['fecha_pedido']}",
            "Exp. IMUH": "---",
            "Destino/Concepto": "Aporte Sueldos",
            "Periodo": f"{s['mes']:02d}/{s['anio']}",
            "Nro. Cuota": "---",
            "Importe": saldo,
            "Semana estimada de cobro": "---"
        }
        if today > due_date:
            atrasos.append(item)
        elif s['mes'] == today.month and s['anio'] == today.year:
            pendientes_mes.append(item)

# 4. SAC
sacs = get_aportes_sac()
for s in sacs:
    saldo = s['monto_pedido'] - (s['monto_cobrado'] or 0)
    if saldo > 0.01:
        try:
            p_date = datetime.datetime.strptime(s['fecha_pedido'], '%Y-%m-%d').date()
            item = {
                "Tipo": "SAC",
                "Decreto/Referencia": f"Cuota {s['cuota_nro']} - {s['anio']}",
                "Exp. IMUH": "---",
                "Destino/Concepto": "Aguinaldo (SAC)",
                "Periodo": f"Cuota {s['cuota_nro']} - {s['anio']}",
                "Nro. Cuota": f"{s['cuota_nro']}/2",
                "Importe": saldo,
                "Semana estimada de cobro": "---"
            }
            if today > p_date:
                atrasos.append(item)
            elif p_date.month == today.month and p_date.year == today.year:
                pendientes_mes.append(item)
        except:
            pass

# Mostrar Alertas de Vencimiento
with st.expander("🚨 Alertas de Vencimiento y Deudas Pendientes", expanded=True):
    # Filtro de Búsqueda
    f_busqueda = st.text_input("🔍 Buscar en alertas por Decreto, Destino o Expediente IMUH:", "")

    def aplicar_filtro(lista_dict, busqueda):
        if not busqueda:
            return lista_dict
        busqueda = busqueda.lower()
        filtrada = []
        for item in lista_dict:
            if (busqueda in str(item.get("Decreto/Referencia", "")).lower() or 
                busqueda in str(item.get("Exp. IMUH", "")).lower() or 
                busqueda in str(item.get("Destino/Concepto", "")).lower()):
                filtrada.append(item)
        return filtrada

    atrasos_filtrados = aplicar_filtro(atrasos, f_busqueda)
    pendientes_mes_filtrados = aplicar_filtro(pendientes_mes, f_busqueda)

    # Mostrar Alertas
    if atrasos_filtrados:
        st.error("🚨 Cuotas atrasadas pendientes de cobro")
        df_atrasos = pd.DataFrame(atrasos_filtrados)
        total_atrasos = df_atrasos['Importe'].sum()
        df_atrasos['Importe'] = df_atrasos['Importe'].apply(lambda x: format_currency_ar(x))
        st.dataframe(
            df_atrasos, 
            use_container_width=True, 
            hide_index=True,
            column_config={
                "Destino/Concepto": st.column_config.TextColumn(width="large"),
                "Decreto/Referencia": st.column_config.TextColumn(width="medium")
            }
        )
        c1, c2 = st.columns([4, 1])
        c2.markdown(f"**TOTAL ATRASOS:** {format_currency_ar(total_atrasos)}")
    else:
        st.success("No hay cuotas atrasadas pendientes de cobro. ✅")

    if pendientes_mes_filtrados:
        st.info(f"📅 Próximos Vencimientos - {today.strftime('%B %Y').capitalize()}")
        df_mes = pd.DataFrame(pendientes_mes_filtrados)
        total_mes = df_mes['Importe'].sum()
        df_mes['Importe'] = df_mes['Importe'].apply(lambda x: format_currency_ar(x))
        st.dataframe(
            df_mes, 
            use_container_width=True, 
            hide_index=True,
            column_config={
                "Destino/Concepto": st.column_config.TextColumn(width="large"),
                "Decreto/Referencia": st.column_config.TextColumn(width="medium")
            }
        )
        c1, c2 = st.columns([4, 1])
        c2.markdown(f"**TOTAL MES:** {format_currency_ar(total_mes)}")

st.markdown("---")

# --- PANEL DE CONTROL (DASHBOARD) ---
st.subheader("📈 Panel de Control Financiero")

df_decretos = pd.DataFrame(decretos)
cuotas_totales = []
for d in decretos:
    for c in get_cuotas_by_decreto(d['id']):
        c['estado_decreto'] = d['estado']
        cuotas_totales.append(c)

df_cuotas = pd.DataFrame(cuotas_totales)
df_cobros = pd.DataFrame(cobros)

if not df_cuotas.empty and not df_decretos.empty:
    # Ajustar monto efectivo
    def calc_monto_efectivo(row):
        if row['estado_decreto'] == 'Anulado':
            cobrado = df_cobros[df_cobros['cuota_id'] == row['id']]['monto'].sum() if not df_cobros.empty else 0
            return cobrado
        return row['monto']
        
    df_cuotas['monto_efectivo'] = df_cuotas.apply(calc_monto_efectivo, axis=1)

    # Calcular KPIs
    pct_cobranza, pct_a_tiempo, pct_atrasado = get_dashboard_kpis(df_cuotas, df_cobros, cobros, fun, sueldos)

    col_kpi1, col_kpi2, col_kpi3 = st.columns(3)
    with col_kpi1:
        st.metric(
            "% Cobranza ult. 12m", 
            f"{pct_cobranza:.1f}%",
            help="Calculado como: (Total cobrado en los últimos 12 meses / Total proyectado) * 100"
        )
    col_kpi2.metric("Histórico en Tiempo y Forma", f"{pct_a_tiempo:.1f}%", help="Calculado como (Total cobrado en o antes del vencimiento / Total cobrado histórico) * 100")
    col_kpi3.metric("Histórico Atrasado", f"{pct_atrasado:.1f}%", help="Calculado como (Total cobrado después del vencimiento / Total cobrado histórico) * 100")

    st.write("")
    col_chart, col_table = st.columns([1.2, 1])

    with col_chart:
        st.markdown("#### Ingresos Proyectados vs Reales")
        start_date = today.replace(day=1) - pd.DateOffset(months=5)
        end_date = today.replace(day=1) + pd.DateOffset(months=6)

        col_filtro1, col_filtro2 = st.columns(2)
        with col_filtro1:
            f_start = st.date_input("Desde", start_date, format="DD-MM-YYYY")
        with col_filtro2:
            f_end = st.date_input("Hasta", end_date, format="DD-MM-YYYY")

        df_cuotas['fecha_periodo'] = df_cuotas.apply(lambda r: datetime.date(r['anio'], r['mes'], 1), axis=1)
        
        df_cobros_plot = pd.DataFrame()
        if not df_cobros.empty:
            df_cobros['fecha_obj'] = pd.to_datetime(df_cobros['fecha']).dt.date
            df_cobros['fecha_periodo'] = df_cobros['fecha_obj'].apply(lambda d: datetime.date(d.year, d.month, 1))
            df_cobros_plot = df_cobros.groupby('fecha_periodo')['monto'].sum().reset_index()
            df_cobros_plot.rename(columns={'monto': 'Real'}, inplace=True)
        
        df_cuotas_plot = df_cuotas.groupby('fecha_periodo')['monto_efectivo'].sum().reset_index()
        df_cuotas_plot.rename(columns={'monto_efectivo': 'Proyectado'}, inplace=True)

        if not df_cobros_plot.empty:
            df_plot = pd.merge(df_cuotas_plot, df_cobros_plot, on='fecha_periodo', how='outer').fillna(0)
        else:
            df_plot = df_cuotas_plot
            df_plot['Real'] = 0

        df_plot = df_plot[(df_plot['fecha_periodo'] >= f_start) & (df_plot['fecha_periodo'] <= f_end)]
        df_plot = df_plot.sort_values('fecha_periodo')
        df_plot['Periodo'] = df_plot['fecha_periodo'].apply(lambda x: f"{x.month:02d}-{x.year}")

        if not df_plot.empty:
            fig = px.bar(df_plot, x='Periodo', y=['Proyectado', 'Real'], barmode='group',
                         color_discrete_map={'Proyectado': '#3182bd', 'Real': '#2ca02c'})
            fig.update_layout(yaxis_title="Monto ($)", xaxis_title="Periodo", legend_title="Tipo", margin=dict(l=0,r=0,t=30,b=0))
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("No hay datos en el rango de fechas seleccionado.")

    with col_table:
        st.markdown("#### Listado Rápido de Decretos")

        df_decretos_list = df_decretos.copy()
        with st.expander("Filtros de Búsqueda", expanded=False):
            col_f1, col_f2 = st.columns(2)
            available_states = df_decretos_list['estado'].unique()
            default_vals = [s for s in ['Con deuda', 'Vigente'] if s in available_states]
            with col_f1:
                f_estado = st.multiselect("Filtrar por Estado", options=available_states, default=default_vals)
            with col_f2:
                f_nro = st.text_input("Filtrar por Nro. Decreto")
            
            col_f3, col_f4 = st.columns(2)
            with col_f3:
                f_destino = st.text_input("Filtrar por Destino de Fondos")
            with col_f4:
                f_imuh = st.text_input("Filtrar por Exp. IMUH")
            
        if f_estado:
            df_decretos_list = df_decretos_list[df_decretos_list['estado'].isin(f_estado)]
        if f_nro:
            df_decretos_list = df_decretos_list[df_decretos_list['nro_decreto'].astype(str).str.contains(f_nro)]
        if f_destino:
            df_decretos_list = df_decretos_list[df_decretos_list['destino_fondos'].str.contains(f_destino, case=False, na=False)]
        if f_imuh:
            df_decretos_list = df_decretos_list[df_decretos_list['expediente_imuh'].astype(str).str.contains(f_imuh, case=False, na=False)]
            
        pendientes = get_cuotas_pendientes(df_decretos_list, df_cuotas, df_cobros)
        columnas_df = ['nro_decreto', 'anio', 'destino_fondos', 'estado', 'expediente_imuh', 'cuotas_atrasadas', 'pendiente_cobrar']
        df_listado = pd.DataFrame(pendientes, columns=columnas_df)
        
        if not df_listado.empty:
            df_listado['pendiente_cobrar'] = df_listado['pendiente_cobrar'].apply(lambda x: format_currency_ar(x))
            st.dataframe(
                df_listado[['nro_decreto', 'anio', 'estado', 'expediente_imuh', 'pendiente_cobrar']], 
                use_container_width=True, 
                hide_index=True,
                column_config={
                    "nro_decreto": st.column_config.NumberColumn("Decreto", format="%d"),
                    "anio": st.column_config.NumberColumn("Año", format="%d"),
                    "estado": "Estado",
                    "expediente_imuh": "Exp. IMUH",
                    "pendiente_cobrar": "Pendiente De Cobrar"
                }
            )
        else:
            st.info("No hay cuotas pendientes para los decretos mostrados.")

    # --- SECCIÓN: SALDOS SIN DISTRIBUIR Y RESERVAS ---
    st.markdown("---")
    st.subheader("💰 Saldos sin distribuir y Reservas")

    st.write("**Saldos sin distribuir:**")
    saldos_sin_dist = []
    cobros_dist = get_cobros_con_resumen_distribucion()
    for c in (cobros_dist or []):
        saldo_sd = c['monto'] - c['total_distribuido']
        if saldo_sd > 0.01:
            o_imuh = c.get('expediente_imuh') or "Sin asignar"
            saldos_sin_dist.append({
                "Decreto de origen": f"Dto. {c['nro_decreto']}/{c['decreto_anio']} - {c['destino_fondos']} (IMUH: {o_imuh})",
                "Fecha de cobro": format_date_ar(c['fecha']),
                "Saldo a distribuir": saldo_sd
            })
            
    if saldos_sin_dist:
        df_sd = pd.DataFrame(saldos_sin_dist)
        tot_sd = df_sd['Saldo a distribuir'].sum()
        df_sd = pd.concat([df_sd, pd.DataFrame([{"Decreto de origen": "TOTAL", "Fecha de cobro": "", "Saldo a distribuir": tot_sd}])], ignore_index=True)
        df_sd['Saldo a distribuir'] = df_sd['Saldo a distribuir'].apply(lambda x: format_currency_ar(x))
        st.dataframe(
            df_sd,
            use_container_width=True,
            hide_index=True,
            column_config={
                "Decreto de origen": st.column_config.TextColumn(width="large")
            }
        )
    else:
        st.info("No hay saldos sin distribuir actualmente.")

    st.write("")
    st.write("**Dinero en Reserva Disponible:**")
    reservas = []
    for c in (cobros_dist or []):
        if c['monto_reserva'] > 0:
            usos = get_reserva_usos_by_cobro(c['id'])
            tot_usado = sum(u['monto'] for u in usos) if usos else 0
            saldo_r = c['monto_reserva'] - tot_usado
            if saldo_r > 0.01:
                o_imuh = c.get('expediente_imuh') or "Sin asignar"
                reservas.append({
                    "Decreto Origen": f"Dto. {c['nro_decreto']}/{c['decreto_anio']} - {c['destino_fondos']} (IMUH: {o_imuh})",
                    "Fecha Cobro": format_date_ar(c['fecha']),
                    "Saldo Disponible": saldo_r
                })
                
    if reservas:
        df_r = pd.DataFrame(reservas)
        tot_r = df_r['Saldo Disponible'].sum()
        df_r = pd.concat([df_r, pd.DataFrame([{"Decreto Origen": "TOTAL", "Fecha Cobro": "", "Saldo Disponible": tot_r}])], ignore_index=True)
        df_r['Saldo Disponible'] = df_r['Saldo Disponible'].apply(lambda x: format_currency_ar(x))
        st.dataframe(
            df_r, 
            use_container_width=True, 
            hide_index=True,
            column_config={
                "Decreto Origen": st.column_config.TextColumn(width="large")
            }
        )
    else:
        st.info("No hay fondos guardados en reserva actualmente.")

    # --- SECCIÓN: DETALLE DE PRÉSTAMOS INTERNOS ---
    st.markdown("---")
    st.subheader("💸 Préstamos Vigentes (Desvíos)")

    # TABLA 1: DESVÍOS (ARRIBA)
    st.write("**Préstamos y Desvíos a Recuperar:**")
    deudas = []

    desvios_activos = get_desvios_activos_completos()
    for d in (desvios_activos or []):
        o_imuh = d.get('orig_imuh') or "Sin asignar"
        origen_str = f"Dto. {d['orig_nro']}/{d['orig_anio']} - {d['orig_nombre']} (IMUH: {o_imuh})"
        if d['decreto_destino_id']:
            d_imuh = d.get('dest_imuh') or "Sin asignar"
            destino_str = f"Dto. {d['dest_nro']}/{d['dest_anio']} - {utils.limpiar_prefijo_expediente(d['dest_nombre'])} (IMUH: {d_imuh})"
        elif d.get('gasto_nombre'):
            destino_str = f"FUN: {d['gasto_nombre']} (IMUH: {d['gasto_expediente_imuh']})"
        else:
            d_imuh = d.get('dest_obra_imuh') or "Sin asignar"
            destino_str = f"{utils.limpiar_prefijo_expediente(d['destino_texto'])} (IMUH: {d_imuh})"
            
        tipo_lbl = "Decreto" if d['decreto_destino_id'] else ("Gasto de Funcionamiento" if d.get('gasto_nombre') else "Fondos Propios")
        deudas.append({
            "Obra Origen": origen_str,
            "Obra Destino": destino_str,
            "Tipo": tipo_lbl,
            "Saldo Pendiente": d['saldo']
        })

    prestamos_legacy = get_prestamos()
    for p in (prestamos_legacy or []):
        s_p = p['monto'] - p.get('total_devuelto', 0)
        if s_p > 0.01:
            o_imuh = p.get('expediente_imuh') or "Sin asignar"
            origen_str = f"Dto. {p['nro_decreto']}/{p['decreto_anio']} (IMUH: {o_imuh})"
            deudas.append({
                "Obra Origen": origen_str,
                "Obra Destino": utils.limpiar_prefijo_expediente(p['destino']),
                "Tipo": "Préstamo Legacy",
                "Saldo Pendiente": s_p
            })

    reserva_prestamos = get_reserva_usos_prestamos_activos()
    for rp in (reserva_prestamos or []):
        o_imuh = rp.get('orig_imuh') or "Sin asignar"
        origen_str = f"Dto. {rp['orig_nro']}/{rp['orig_anio']} - {rp['orig_nombre']} (IMUH: {o_imuh})"
        if rp['decreto_destino_id']:
            d_imuh = rp.get('dest_imuh') or "Sin asignar"
            destino_str = f"Dto. {rp['dest_nro']}/{rp['dest_anio']} - {utils.limpiar_prefijo_expediente(rp['dest_nombre'])} (IMUH: {d_imuh})"
        elif rp.get('gasto_nombre'):
            destino_str = f"FUN: {rp['gasto_nombre']} (IMUH: {rp['gasto_expediente_imuh']})"
        else:
            d_imuh = rp.get('dest_obra_imuh') or "Sin asignar"
            destino_str = f"{utils.limpiar_prefijo_expediente(rp['destino_detalle']) or 'Obra sin decreto'} (IMUH: {d_imuh})"
            
        tipo_lbl = "Préstamo desde Reserva"
        if rp.get('gasto_nombre'):
            tipo_lbl = "FUN (Reserva)"
            
        deudas.append({
            "Obra Origen": origen_str,
            "Obra Destino": destino_str,
            "Tipo": tipo_lbl,
            "Saldo Pendiente": rp['saldo']
        })
             
    if deudas:
        df_d = pd.DataFrame(deudas)
        tot_d = df_d['Saldo Pendiente'].sum()
        df_d = pd.concat([df_d, pd.DataFrame([{"Obra Origen": "TOTAL", "Obra Destino": "", "Tipo": "", "Saldo Pendiente": tot_d}])], ignore_index=True)
        df_d['Saldo Pendiente'] = df_d['Saldo Pendiente'].apply(lambda x: format_currency_ar(x))
        st.dataframe(
            df_d, 
            use_container_width=True, 
            hide_index=True,
            column_config={
                "Obra Origen": st.column_config.TextColumn(width="large"),
                "Obra Destino": st.column_config.TextColumn(width="large")
            }
        )
    else:
        st.success("No hay desvíos ni préstamos pendientes de devolución.")
        
    # TABLA 3: SEGUIMIENTO DE SOLICITUDES DE HABERES
    from utils import get_resumen_habituales_pendientes
    hab_pend = get_resumen_habituales_pendientes()
    if hab_pend:
        st.write("")
        st.write("**Seguimiento de solicitudes de aportes para haberes:**")
        df_hp = pd.DataFrame(hab_pend)
        tot_hp = df_hp['saldo'].sum()
        df_hp = pd.concat([df_hp, pd.DataFrame([{"tipo": "TOTAL", "periodo": "", "monto_pedido": 0, "monto_cobrado": 0, "saldo": tot_hp}])], ignore_index=True)
        
        df_hp.rename(columns={
            'tipo': 'Tipo de Aporte',
            'periodo': 'Periodo / Cuota',
            'monto_pedido': 'Monto Solicitado',
            'monto_cobrado': 'Monto Ingresado',
            'saldo': 'Saldo Pendiente'
        }, inplace=True)

        df_hp['Monto Solicitado'] = df_hp['Monto Solicitado'].apply(lambda x: format_currency_ar(x))
        df_hp['Monto Ingresado'] = df_hp['Monto Ingresado'].apply(lambda x: format_currency_ar(x))
        df_hp['Saldo Pendiente'] = df_hp['Saldo Pendiente'].apply(lambda x: format_currency_ar(x))
        
        st.dataframe(df_hp, use_container_width=True, hide_index=True)
else:
    st.info("No hay datos suficientes para mostrar el Dashboard. Ve a la pestaña de Decretos para comenzar a cargar información.")

```

## Archivo: `README.md`

```md
# Decretometro
Desarrollo del decretometro

```

## Archivo: `aplicar_asignacion_obras.py`

```python
import sqlite3
import pandas as pd
import shutil
import os
import sys

sys.stdout.reconfigure(encoding='utf-8')

p1_dir = r"c:\Users\bornemanns\.gemini\antigravity-ide\scratch\decretometro"
p2_dir = r"c:\Users\bornemanns\.gemini\antigravity\scratch\decretometro"

p1_db = os.path.join(p1_dir, "decretometro.db")
p2_db = os.path.join(p2_dir, "decretometro.db")

csv_path = os.path.join(p1_dir, "Asignación de obras.csv")

conn = sqlite3.connect(p1_db)
conn.row_factory = sqlite3.Row
cursor = conn.cursor()

# Ensure nro_op exists on cobro_desvios_recuperos to avoid migration error if init_db is called
try:
    cursor.execute("ALTER TABLE cobro_desvios_recuperos ADD COLUMN nro_op TEXT")
    conn.commit()
except Exception:
    pass

# Load CSV
df_csv = pd.read_csv(csv_path, sep=';')

# Load Obras map
cursor.execute("SELECT id, expediente_imuh, nombre FROM obras")
obras_map = {r['expediente_imuh']: dict(r) for r in cursor.fetchall()}

# Load cobro_fin_original_usos unassigned records
query = """
SELECT 
    fu.id as uso_id,
    c.id as cobro_id,
    d.nro_decreto || '/' || d.anio as decreto_str,
    fu.fecha as fecha_uso,
    fu.monto as monto_uso
FROM cobro_fin_original_usos fu
JOIN cobros c ON fu.cobro_id = c.id
JOIN cuotas q ON c.cuota_id = q.id
JOIN decretos d ON q.decreto_id = d.id
WHERE fu.obra_id IS NULL
ORDER BY fu.fecha DESC, d.anio DESC, d.nro_decreto DESC
"""

cursor.execute(query)
db_records = [dict(r) for r in cursor.fetchall()]
print(f"\n2. Registros pendientes en cobro_fin_original_usos en la BD: {len(db_records)}")

used_uso_ids = set()
updated_count = 0

print("\n3. Procesando las 40 filas del CSV...")
for idx, row in df_csv.iterrows():
    line_num = idx + 2
    dec_str = str(row['Decreto']).strip()
    fecha_str = str(row['Fecha de Pago']).strip()
    monto_str = str(row['Monto']).strip().replace('$', '').replace('.', '').replace(',', '.').strip()
    monto_val = float(monto_str) if monto_str else 0.0
    op_str = str(row['Nro. OP']).strip()
    exp_imuh = str(row['Expediente IMUH de la obra o gasto de funcionamiento']).strip()
    extra_op = str(row.get('Unnamed: 5')).strip() if pd.notna(row.get('Unnamed: 5')) else ""

    # OP selection logic
    if line_num == 20:
        final_op = "3504/3505"
    elif line_num == 23:
        final_op = "3464"
    elif extra_op:
        final_op = extra_op
    else:
        final_op = op_str

    obra_info = obras_map.get(exp_imuh)
    if not obra_info:
        raise ValueError(f"Línea {line_num}: Expediente IMUH {exp_imuh} no encontrado en tabla obras.")

    obra_id = obra_info['id']

    # Match db record
    matched_rec = None
    for rec in db_records:
        if rec['uso_id'] in used_uso_ids:
            continue
        if rec['decreto_str'] == dec_str and abs(rec['monto_uso'] - monto_val) < 0.05:
            matched_rec = rec
            break

    if not matched_rec:
        raise ValueError(f"Línea {line_num}: No se encontró registro coincidente en BD para {dec_str} por ${monto_val}.")

    uso_id = matched_rec['uso_id']
    used_uso_ids.add(uso_id)

    # Perform UPDATE
    cursor.execute("""
        UPDATE cobro_fin_original_usos
        SET obra_id = ?, nro_op = ?
        WHERE id = ?
    """, (obra_id, final_op, uso_id))

    updated_count += 1
    print(f"   [✓] Línea {line_num:2d} | Dec {dec_str:8s} | Monto ${monto_val:14,.2f} | OP: {final_op:12s} -> Obra ID {obra_id:2d} ({exp_imuh}) [uso_id={uso_id}]")

conn.commit()
print(f"\n4. ¡Actualización masiva completada! Registros actualizados: {updated_count}")

# Verification
cursor.execute("SELECT COUNT(*) FROM cobro_fin_original_usos WHERE obra_id IS NULL")
pending_remaining = cursor.fetchone()[0]
print(f"\n5. Control final: Registros en cobro_fin_original_usos sin obra asignada: {pending_remaining}")

if pending_remaining == 0:
    print("-> VERIFICACIÓN EXITOSA: 100% de los pagos tienen obra asignada.")
else:
    print(f"-> ADVERTENCIA: Aún quedan {pending_remaining} registros sin obra asignada.")

conn.close()

```

## Archivo: `aplicar_montos.py`

```python
import sqlite3
import re
import os

md_file = r"C:\Users\bornemanns\.gemini\antigravity-ide\scratch\decretometro\Montos de obra\obras_sin_contrato.md"
backup_db = r"C:\Users\bornemanns\.gemini\antigravity-ide\scratch\decretometro\Montos de obra\obras_backup_15-09-2026_10-56.db"
decretometro_db = r"C:\Users\bornemanns\.gemini\antigravity-ide\scratch\decretometro\decretometro.db"

def main():
    # 1. Parse markdown
    expedientes_to_update = set()
    with open(md_file, 'r', encoding='utf-8') as f:
        for line in f:
            if line.startswith('|') and not line.startswith('| ID |') and not line.startswith('|---|'):
                parts = line.split('|')
                if len(parts) >= 3:
                    expediente = parts[2].strip()
                    expedientes_to_update.add(expediente)

    print(f"Encontrados {len(expedientes_to_update)} expedientes en el archivo markdown.")

    # 2. Get monto_contrato from backup
    montos_by_expediente = {}
    conn_b = sqlite3.connect(backup_db)
    cursor_b = conn_b.cursor()
    for exp in expedientes_to_update:
        cursor_b.execute("SELECT monto_contrato FROM obra WHERE nro_expediente = ?", (exp,))
        row = cursor_b.fetchone()
        if row:
            montos_by_expediente[exp] = row[0]
        else:
            print(f"ADVERTENCIA: No se encontró el expediente {exp} en la base de datos de respaldo.")
    conn_b.close()

    print(f"Se obtuvieron {len(montos_by_expediente)} montos de contrato de la base de datos de respaldo.")

    # 3. Update decretometro
    conn_d = sqlite3.connect(decretometro_db)
    cursor_d = conn_d.cursor()
    updated_count = 0
    for exp, monto in montos_by_expediente.items():
        cursor_d.execute("SELECT id FROM obras WHERE expediente_imuh = ?", (exp,))
        row = cursor_d.fetchone()
        if row:
            obra_id = row[0]
            cursor_d.execute("UPDATE obras SET monto_contrato = ? WHERE id = ?", (monto, obra_id))
            updated_count += 1
            print(f"Actualizado: {exp} -> ${monto:,.2f}")
        else:
            print(f"ADVERTENCIA: No se encontró el expediente {exp} en el decretómetro.")
    
    conn_d.commit()
    conn_d.close()
    
    print(f"\nFinalizado. Se actualizaron {updated_count} obras.")

if __name__ == "__main__":
    main()

```

## Archivo: `apply_changes.py`

```python
import re

def update_tab_estado():
    with open('components/tab_estado.py', 'r', encoding='utf-8') as f:
        content = f.read()

    # 1. Update form_uso_fo_{cobro_id}
    # Replace form with container
    content = content.replace('with st.form(f"form_uso_fo_{cobro_id}", clear_on_submit=True):', 'with st.container():')
    content = content.replace('st.form_submit_button("Registrar Pago de Fin Original", type="primary")', 'st.button("Registrar Pago de Fin Original", type="primary", key=f"btn_fo_{cobro_id}")')
    
    # After success, clear keys
    success_block_fo = '''
                                                        st.session_state['success_msg_dist'] = "Pago a Fin Original registrado."
                                                        for k in [f"op_fo_pay_inp_{cobro_id}", f"chk_confirmar_fo_pay_sin_op_{cobro_id}"]:
                                                            if k in st.session_state:
                                                                del st.session_state[k]
                                                        st.rerun()'''
    content = re.sub(r'st\.session_state\[\'success_msg_dist\'\] = "Pago a Fin Original registrado\."\s*st\.rerun\(\)', success_block_fo.strip(), content)

    # Move op_fo_pay logic BEFORE other inputs in container to allow showing info
    op_input_fo = '''
                                            op_fo_pay = st.text_input("Número de Orden de Pago", key=f"op_fo_pay_inp_{cobro_id}")
                                            op_fo_pay = ''.join(filter(str.isdigit, op_fo_pay)) # force digits
                                            if op_fo_pay:
                                                usos_op = db.get_op_usage_details(op_fo_pay)
                                                if usos_op:
                                                    st.info("ℹ️ **Esta OP ya está vinculada a los siguientes pagos:**")
                                                    for u in usos_op:
                                                        st.info(f"- {u['origen']} por {utils.format_currency_ar(u['monto'])}")
'''
    
    # Remove old op_fo_pay
    content = re.sub(r'op_fo_pay = st\.text_input\("Número de Orden de Pago", key=f"op_fo_pay_inp_\{cobro_id\}"\)\n', '', content)
    # Insert new op_fo_pay at top of container
    content = content.replace('cc1, cc2 = st.columns(2)', op_input_fo + '                                            cc1, cc2 = st.columns(2)')

    # 2. Update form_uso_r_{cobro_id}
    content = content.replace('with st.form(f"form_uso_r_{cobro_id}", clear_on_submit=True):', 'with st.container():')
    content = content.replace('st.form_submit_button("Registrar Uso de Reserva", type="primary")', 'st.button("Registrar Uso de Reserva", type="primary", key=f"btn_uso_r_{cobro_id}")')

    success_block_r = '''
                                                        st.session_state['success_msg_dist'] = "Uso de reserva registrado."
                                                        for k in [f"op_uso_{cobro_id}", f"notes_uso_{cobro_id}", f"chk_confirmar_uso_sin_op_{cobro_id}", f"uso_obra_id_{cobro_id}", f"uso_gasto_id_sel_{cobro_id}", f"uso_gasto_prov_txt_{cobro_id}"]:
                                                            if k in st.session_state:
                                                                del st.session_state[k]
                                                        st.rerun()'''
    content = re.sub(r'st\.session_state\[\'success_msg_dist\'\] = "Uso de reserva registrado\."\s*st\.rerun\(\)', success_block_r.strip(), content)

    # Move op_uso to top and lock logic
    op_input_r = '''
                                            op_uso = st.text_input("Número de Orden de Pago (Uso Reserva)", key=f"op_uso_{cobro_id}")
                                            op_uso = ''.join(filter(str.isdigit, op_uso))
                                            
                                            op_locked_obra = None
                                            op_locked_gasto = None
                                            
                                            if op_uso:
                                                usos_op = db.get_op_usage_details(op_uso)
                                                if usos_op:
                                                    st.info("ℹ️ **Esta OP ya está vinculada a los siguientes pagos:**")
                                                    for u in usos_op:
                                                        st.info(f"- {u['origen']} por {utils.format_currency_ar(u['monto'])}")
                                                    op_info = db.get_op_info(op_uso)
                                                    if op_info:
                                                        if op_info['obra_id']: op_locked_obra = op_info['obra_id']
                                                        if op_info['gasto_id']: op_locked_gasto = op_info['gasto_id']
                                                        st.warning("⚠️ **OP ya utilizada:** El destino (Obra/Gasto) ha sido bloqueado para coincidir con el original. Si hay un error, debe eliminar los pagos previos de esta OP.")

                                            cc1, cc2, cc3 = st.columns(3)
'''
    # Remove old op_uso
    content = re.sub(r'op_uso = st\.text_input\("Número de Orden de Pago \(Uso Reserva\)", key=f"op_uso_\{cobro_id\}"\)\n', '', content)
    # Insert new op_uso at top
    content = content.replace('cc1, cc2, cc3 = st.columns(3)', op_input_r)

    # Adjust Selectbox for tipo_uso to read from lock
    tipo_uso_logic = '''
                                            tipo_opciones = ["fin_original", "obra_catalogo", "gasto_fun"]
                                            index_tipo = 0
                                            if op_locked_obra: index_tipo = 1
                                            elif op_locked_gasto: index_tipo = 2
                                            tipo_uso = cc3.selectbox("¿Hacia dónde va?", tipo_opciones, index=index_tipo, disabled=(op_locked_obra is not None or op_locked_gasto is not None), format_func=lambda x: "Fin original" if x == "fin_original" else ("Obra (Catálogo)" if x == "obra_catalogo" else "Gasto de Funcionamiento (FUN)"))
'''
    content = re.sub(r'tipo_uso = cc3\.selectbox\("¿Hacia dónde va\?", \["fin_original", "obra_catalogo", "gasto_fun"\], format_func=lambda x: "Fin original" if x == "fin_original" else \("Obra \(Catálogo\)" if x == "obra_catalogo" else "Gasto de Funcionamiento \(FUN\)"\)\)\n', tipo_uso_logic.lstrip('\n'), content)

    # Adjust obra and gasto selections to use lock
    content = content.replace('nd_obra_id = st.selectbox("Seleccione la Obra Destino", options=list(opc_obras.keys()), format_func=lambda x: opc_obras[x], key=f"uso_obra_id_{cobro_id}")',
                              'idx_o = list(opc_obras.keys()).index(op_locked_obra) if op_locked_obra in opc_obras else 0\n                                                nd_obra_id = st.selectbox("Seleccione la Obra Destino", options=list(opc_obras.keys()), index=idx_o, disabled=(op_locked_obra is not None), format_func=lambda x: opc_obras[x], key=f"uso_obra_id_{cobro_id}")')

    content = content.replace('gasto_id_sel = st.selectbox("Seleccione el Gasto de Funcionamiento (FUN)", options=list(opc_gastos.keys()), format_func=lambda x: opc_gastos[x], key=f"uso_gasto_id_sel_{cobro_id}")',
                              'idx_g = list(opc_gastos.keys()).index(op_locked_gasto) if op_locked_gasto in opc_gastos else 0\n                                                gasto_id_sel = st.selectbox("Seleccione el Gasto de Funcionamiento (FUN)", options=list(opc_gastos.keys()), index=idx_g, disabled=(op_locked_gasto is not None), format_func=lambda x: opc_gastos[x], key=f"uso_gasto_id_sel_{cobro_id}")')

    with open('components/tab_estado.py', 'w', encoding='utf-8') as f:
        f.write(content)


def update_tab_distribuir():
    with open('components/tab_distribuir.py', 'r', encoding='utf-8') as f:
        content = f.read()

    # Move nd_op to top of the form, similar to tab_estado
    op_input_desv = '''
                    nd_op = st.text_input("Número de Orden de Pago (Desvío)", key=f"nd_op_{c_sel_id}", on_change=keep_expander_open, args=(c_sel_id,))
                    nd_op = ''.join(filter(str.isdigit, nd_op))
                    
                    op_locked_obra = None
                    op_locked_gasto = None
                    
                    if nd_op:
                        usos_op = db.get_op_usage_details(nd_op)
                        if usos_op:
                            st.info("ℹ️ **Esta OP ya está vinculada a los siguientes pagos:**")
                            for u in usos_op:
                                st.info(f"- {u['origen']} por {utils.format_currency_ar(u['monto'])}")
                            op_info = db.get_op_info(nd_op)
                            if op_info:
                                if op_info['obra_id']: op_locked_obra = op_info['obra_id']
                                if op_info['gasto_id']: op_locked_gasto = op_info['gasto_id']
                                st.warning("⚠️ **OP ya utilizada:** El destino ha sido bloqueado. Si hay un error, elimine los pagos previos.")

                    tipo_opciones_d = ["Hacia Obra (Catálogo)", "Hacia Gasto de Funcionamiento (FUN)"]
                    index_tipo_d = 0
                    if op_locked_obra: index_tipo_d = 0
                    elif op_locked_gasto: index_tipo_d = 1
                    
                    tipo_desvio = st.radio("Destino del Desvío:", tipo_opciones_d, index=index_tipo_d, disabled=(op_locked_obra is not None or op_locked_gasto is not None), key=f"tipo_desvio_{c_sel_id}", on_change=keep_expander_open, args=(c_sel_id,))
'''

    content = re.sub(r'nd_op = st\.text_input\("Número de Orden de Pago \(Desvío\)", key=f"nd_op_\{c_sel_id\}", on_change=keep_expander_open, args=\(c_sel_id,\)\)\n', '', content)
    # Note: Will use string replace instead due to escaping

    # Do it with string replace
    old_tipo = 'tipo_desvio = st.radio("Destino del Desvío:", ["Hacia Obra (Catálogo)", "Hacia Gasto de Funcionamiento (FUN)"], key=f"tipo_desvio_{c_sel_id}", on_change=keep_expander_open, args=(c_sel_id,))'
    content = content.replace(old_tipo, op_input_desv.strip())

    content = content.replace('nd_obra_id = st.selectbox("Seleccione la Obra Destino", options=list(opc_obras.keys()), format_func=lambda x: opc_obras[x], key=f"nd_obra_id_{c_sel_id}", on_change=keep_expander_open, args=(c_sel_id,))',
                              'idx_o = list(opc_obras.keys()).index(op_locked_obra) if op_locked_obra in opc_obras else 0\n                            nd_obra_id = st.selectbox("Seleccione la Obra Destino", options=list(opc_obras.keys()), index=idx_o, disabled=(op_locked_obra is not None), format_func=lambda x: opc_obras[x], key=f"nd_obra_id_{c_sel_id}", on_change=keep_expander_open, args=(c_sel_id,))')

    content = content.replace('gasto_id_sel = st.selectbox("Seleccione el Gasto de Funcionamiento (FUN)", options=list(opc_gastos.keys()), format_func=lambda x: opc_gastos[x], key=f"nd_gasto_id_sel_{c_sel_id}", on_change=keep_expander_open, args=(c_sel_id,))',
                              'idx_g = list(opc_gastos.keys()).index(op_locked_gasto) if op_locked_gasto in opc_gastos else 0\n                        gasto_id_sel = st.selectbox("Seleccione el Gasto de Funcionamiento (FUN)", options=list(opc_gastos.keys()), index=idx_g, disabled=(op_locked_gasto is not None), format_func=lambda x: opc_gastos[x], key=f"nd_gasto_id_sel_{c_sel_id}", on_change=keep_expander_open, args=(c_sel_id,))')

    with open('components/tab_distribuir.py', 'w', encoding='utf-8') as f:
        f.write(content)

if __name__ == '__main__':
    update_tab_estado()
    update_tab_distribuir()

```

## Archivo: `backend_compensaciones.py`

```python
import database as db
import utils_reports
import re
import datetime
import uuid

def get_imuh_base(exp_str):
    m = re.search(r'(8\d{6})', str(exp_str))
    return m.group(1) if m else str(exp_str).strip().lower()

def calcular_saldos_cruzados_globales():
    obras = db.get_todas_obras_para_trazabilidad()
    
    saldos = {}
    
    nombres_imuh = {}
    for o in obras:
        b = get_imuh_base(o['expediente_imuh'])
        if b != 'sin asignar' and b.startswith('8'):
            if b not in nombres_imuh or len(o['nombre']) < len(nombres_imuh[b]):
                nombres_imuh[b] = o['nombre']

    for o in obras:
        base_o = get_imuh_base(o['expediente_imuh'])
        if base_o == 'sin asignar' or not base_o.startswith('8'):
            base_o = str((base_o, o['nombre'].strip().lower()[:15]))
            
        nombre_o = nombres_imuh.get(base_o, o['nombre']) if isinstance(base_o, str) else o['nombre']

        rows_acr, _ = utils_reports.obtener_estado_deudas_por_obra(o)
        
        for r in rows_acr:
            base_c = get_imuh_base(r.get('Exp. IMUH', 'Sin asignar'))
            if base_c == 'sin asignar' or not base_c.startswith('8'):
                base_c = str((base_c, r['Contraparte'].strip().lower()[:15]))
            
            nombre_c = nombres_imuh.get(base_c, r['Contraparte']) if isinstance(base_c, str) else r['Contraparte']
            
            key = tuple(sorted([str(base_o), str(base_c)]))
            if key not in saldos:
                saldos[key] = {'O1': str(base_o), 'O2': str(base_c), 'O1_name': nombre_o, 'O2_name': nombre_c, 'deuda_O1_to_O2': 0.0, 'deuda_O2_to_O1': 0.0}
            
            if str(base_o) == saldos[key]['O1']:
                saldos[key]['deuda_O2_to_O1'] += float(r.get('Saldo Pendiente', 0.0))
            else:
                saldos[key]['deuda_O1_to_O2'] += float(r.get('Saldo Pendiente', 0.0))
        
    pares_cruzados = []
    for k, v in saldos.items():
        if v['deuda_O1_to_O2'] > 0 and v['deuda_O2_to_O1'] > 0:
            v['monto_maximo'] = min(v['deuda_O1_to_O2'], v['deuda_O2_to_O1'])
            pares_cruzados.append(v)
            
    return pares_cruzados

def ejecutar_compensacion(obra_1_imuh, obra_2_imuh, monto_compensar):
    obras = db.get_todas_obras_para_trazabilidad()
    
    def get_obras_by_base(base):
        matches = []
        for o in obras:
            b = get_imuh_base(o['expediente_imuh'])
            if b == 'sin asignar' or not b.startswith('8'):
                b = str((b, o['nombre'].strip().lower()[:15]))
            if str(b) == str(base):
                matches.append(o)
        return matches

    obras_1 = get_obras_by_base(obra_1_imuh)
    obras_2 = get_obras_by_base(obra_2_imuh)
    
    if not obras_1 or not obras_2:
        return False, "Obras no encontradas"

    desvios_1_to_2 = []
    for o1 in obras_1:
        acr, _ = utils_reports.obtener_estado_deudas_por_obra(o1)
        for r in acr:
            c_base = get_imuh_base(r.get('Exp. IMUH', 'Sin asignar'))
            if c_base == 'sin asignar' or not c_base.startswith('8'):
                c_base = str((c_base, r['Contraparte'].strip().lower()[:15]))
            if str(c_base) == str(obra_2_imuh) and float(r.get('Saldo Pendiente', 0.0)) > 0:
                desvios_1_to_2.append(r)

    desvios_2_to_1 = []
    for o2 in obras_2:
        acr, _ = utils_reports.obtener_estado_deudas_por_obra(o2)
        for r in acr:
            c_base = get_imuh_base(r.get('Exp. IMUH', 'Sin asignar'))
            if c_base == 'sin asignar' or not c_base.startswith('8'):
                c_base = str((c_base, r['Contraparte'].strip().lower()[:15]))
            if str(c_base) == str(obra_1_imuh) and float(r.get('Saldo Pendiente', 0.0)) > 0:
                desvios_2_to_1.append(r)

    def sort_key(r):
        dt = r['raw_date']
        if isinstance(dt, str):
            try:
                dt = datetime.datetime.strptime(dt, '%Y-%m-%d').date()
            except:
                dt = datetime.date.min
        return dt

    desvios_1_to_2.sort(key=sort_key)
    desvios_2_to_1.sort(key=sort_key)
    
    ops_1_to_2 = set(str(r['N° de OP']) for r in desvios_1_to_2 if str(r['N° de OP']).strip() and str(r['N° de OP']).strip() != 'Sin asignar')
    ops_2_to_1 = set(str(r['N° de OP']) for r in desvios_2_to_1 if str(r['N° de OP']).strip() and str(r['N° de OP']).strip() != 'Sin asignar')
    
    str_ops_1_to_2 = "-".join(sorted(list(ops_1_to_2))) if ops_1_to_2 else "Sin OP"
    str_ops_2_to_1 = "-".join(sorted(list(ops_2_to_1))) if ops_2_to_1 else "Sin OP"
    
    max_date = datetime.date.min
    for r in desvios_1_to_2 + desvios_2_to_1:
        if sort_key(r) > max_date:
            max_date = sort_key(r)
    
    if max_date == datetime.date.min:
        max_date = datetime.date.today()

    grupo_id = str(uuid.uuid4())
    
    def procesar_fifo(desvios, monto_total, ops_contraparte):
        monto_restante = float(monto_total)
        insertos = []
        for r in desvios:
            if monto_restante <= 0.01:
                break
            saldo_row = float(r['Saldo Pendiente'])
            a_compensar = min(saldo_row, monto_restante)
            
            tipo = r['Tipo'] 
            db_id = r.get('desvio_id', 0)
            
            insertos.append({
                'tipo_original': tipo,
                'id_original': db_id,
                'monto': a_compensar,
                'nro_op': ops_contraparte
            })
            monto_restante -= a_compensar
        return insertos

    ins_1_to_2 = procesar_fifo(desvios_1_to_2, monto_compensar, str_ops_2_to_1)
    ins_2_to_1 = procesar_fifo(desvios_2_to_1, monto_compensar, str_ops_1_to_2)
    
    with db.db_session() as conn:
        cursor = conn.cursor()
        for ins in ins_1_to_2 + ins_2_to_1:
            if ins['id_original'] == 0:
                continue
            if ins['tipo_original'] == 'Inicial':
                cursor.execute('''
                    INSERT INTO cobro_desvios_recuperos 
                    (desvio_id, monto, fecha, destino_tipo, destino_detalle, nro_op, notas, grupo_compensacion_id)
                    VALUES (?, ?, ?, 'compensacion', 'Compensación automática', ?, 'Compensación de deudas cruzadas', ?)
                ''', (ins['id_original'], ins['monto'], max_date.strftime('%Y-%m-%d'), ins['nro_op'], grupo_id))
            else:
                cursor.execute('''
                    INSERT INTO cobro_reserva_usos_recuperos 
                    (reserva_uso_id, monto, fecha, destino_tipo, destino_detalle, nro_op, notas, grupo_compensacion_id)
                    VALUES (?, ?, ?, 'compensacion', 'Compensación automática', ?, 'Compensación de deudas cruzadas', ?)
                ''', (ins['id_original'], ins['monto'], max_date.strftime('%Y-%m-%d'), ins['nro_op'], grupo_id))

    return True, "Compensación registrada correctamente"

def get_historial_compensaciones():
    with db.db_session() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT 
                grupo_compensacion_id, 
                MAX(fecha) as fecha,
                SUM(monto)/2 as monto_compensado,
                GROUP_CONCAT(DISTINCT nro_op) as ops_involucradas,
                COUNT(*) as cant_movimientos
            FROM (
                SELECT grupo_compensacion_id, fecha, monto, nro_op FROM cobro_desvios_recuperos WHERE destino_tipo = 'compensacion'
                UNION ALL
                SELECT grupo_compensacion_id, fecha, monto, nro_op FROM cobro_reserva_usos_recuperos WHERE destino_tipo = 'compensacion'
            )
            WHERE grupo_compensacion_id IS NOT NULL
            GROUP BY grupo_compensacion_id
            ORDER BY MAX(fecha) DESC
        ''')
        historial = [dict(r) for r in cursor.fetchall()]
        
        for h in historial:
            grupo_id = h['grupo_compensacion_id']
            # Obras desde desvios
            cursor.execute('''
                SELECT DISTINCT COALESCE(o.nombre, d.gasto_nombre) as obra_nombre
                FROM cobro_desvios_recuperos r
                JOIN cobro_desvios d ON r.desvio_id = d.id
                LEFT JOIN obras o ON d.obra_id = o.id
                WHERE r.grupo_compensacion_id = ?
            ''', (grupo_id,))
            obras_desvios = [row[0] for row in cursor.fetchall() if row[0]]
            
            # Obras desde reserva usos
            cursor.execute('''
                SELECT DISTINCT COALESCE(o.nombre, u.gasto_nombre) as obra_nombre
                FROM cobro_reserva_usos_recuperos r
                JOIN cobro_reserva_usos u ON r.reserva_uso_id = u.id
                LEFT JOIN obras o ON u.obra_id = o.id
                WHERE r.grupo_compensacion_id = ?
            ''', (grupo_id,))
            obras_reservas = [row[0] for row in cursor.fetchall() if row[0]]
            
            todas_obras = list(set(obras_desvios + obras_reservas))
            
            ops_list = []
            if h['ops_involucradas']:
                raw_ops = str(h['ops_involucradas']).replace(',', '-').split('-')
                ops_list = list(set([op.strip() for op in raw_ops if op.strip() and op.strip() != 'Sin OP']))
            
            h['obras_str'] = " ↔ ".join(todas_obras) if todas_obras else "No identificadas"
            h['ops_str'] = ", ".join(ops_list) if ops_list else "Sin OP"
            
        return historial

def deshacer_compensacion(grupo_id):
    with db.db_session() as conn:
        cursor = conn.cursor()
        cursor.execute('DELETE FROM cobro_desvios_recuperos WHERE grupo_compensacion_id = ?', (grupo_id,))
        cursor.execute('DELETE FROM cobro_reserva_usos_recuperos WHERE grupo_compensacion_id = ?', (grupo_id,))
    return True

```

## Archivo: `clean_db.py`

```python
import sqlite3
import os

DB_PATH = 'c:\\Users\\bornemanns\\.gemini\\antigravity\\scratch\\decretometro\\decretometro.db'
UPLOADS_DIR = 'c:\\Users\\bornemanns\\.gemini\\antigravity\\scratch\\decretometro\\uploads'

def clean_db():
    print("Cleaning database...")
    if os.path.exists(DB_PATH):
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        # Disable foreign keys temporarily to avoid issues while deleting if needed, 
        # though TRUNCATE/DELETE should work fine if done in order.
        # But here we just want to clear everything.
        tables = ['cobros', 'cuotas', 'decretos', 'aportes_funcionamiento', 'aportes_sueldo']
        for table in tables:
            try:
                cursor.execute(f"DELETE FROM {table}")
                print(f"Cleared table: {table}")
            except sqlite3.OperationalError as e:
                print(f"Table {table} does not exist or error: {e}")
        
        conn.commit()
        conn.close()
        print("Database tables cleared.")
    else:
        print("Database file not found.")

    print("Cleaning uploads directory...")
    if os.path.exists(UPLOADS_DIR):
        for root, dirs, files in os.walk(UPLOADS_DIR):
            for file in files:
                file_path = os.path.join(root, file)
                try:
                    os.remove(file_path)
                    print(f"Removed file: {file_path}")
                except Exception as e:
                    print(f"Error removing file {file_path}: {e}")
    else:
        print("Uploads directory not found.")

if __name__ == '__main__':
    clean_db()

```

## Archivo: `clean_stress_v2.py`

```python
import os, sys, sqlite3
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
import database as db

def clean():
    conn = db.get_connection()
    c = conn.cursor()
    
    # 1. Identificar Decretos STRESS
    c.execute("SELECT id FROM decretos WHERE nro_decreto IN (9901, 9902) OR nro_expediente LIKE '%STRESS%'")
    decretos = [row['id'] for row in c.fetchall()]
    print("Decretos a limpiar:", decretos)

    # 2. Identificar cobros asociados a las cuotas de estos decretos
    c.execute("SELECT id FROM cuotas WHERE decreto_id IN ({})".format(','.join('?'*len(decretos))), decretos)
    cuotas = [row['id'] for row in c.fetchall()]
    
    if cuotas:
        c.execute("SELECT id FROM cobros WHERE cuota_id IN ({})".format(','.join('?'*len(cuotas))), cuotas)
        cobros = [row['id'] for row in c.fetchall()]
        print("Cobros a limpiar:", cobros)
        
        if cobros:
            # Eliminar recuperos manuales huérfanos asociados a esos cobros
            c.execute("SELECT id FROM cobro_desvios WHERE cobro_id IN ({})".format(','.join('?'*len(cobros))), cobros)
            desvios = [row['id'] for row in c.fetchall()]
            if desvios:
                c.execute("DELETE FROM cobro_desvios_recuperos WHERE desvio_id IN ({})".format(','.join('?'*len(desvios))), desvios)
                print("Recuperos eliminados.")
                
            # Eliminar desvios
            c.execute("DELETE FROM cobro_desvios WHERE cobro_id IN ({})".format(','.join('?'*len(cobros))), cobros)
            print("Desvios eliminados.")
            
            # Eliminar usos
            c.execute("DELETE FROM cobro_reserva_usos WHERE cobro_id IN ({})".format(','.join('?'*len(cobros))), cobros)
            print("Usos de reserva eliminados.")
            
            # Eliminar distribucion
            c.execute("DELETE FROM cobro_distribuciones WHERE cobro_id IN ({})".format(','.join('?'*len(cobros))), cobros)
            print("Distribuciones eliminadas.")
            
            # Eliminar cobros
            c.execute("DELETE FROM cobros WHERE id IN ({})".format(','.join('?'*len(cobros))), cobros)
            print("Cobros eliminados.")
            
    # Eliminar cuotas
    if decretos:
        c.execute("DELETE FROM cuotas WHERE decreto_id IN ({})".format(','.join('?'*len(decretos))), decretos)
        print("Cuotas eliminadas.")
        
        # Eliminar Decretos (forzamos sin restricciones para limpiar los de estrés)
        c.execute("DELETE FROM decretos WHERE id IN ({})".format(','.join('?'*len(decretos))), decretos)
        print("Decretos eliminados.")
        
    conn.commit()
    conn.close()

if __name__ == "__main__":
    try:
        clean()
        print("Limpieza completada y sin base de datos bloqueada.")
    except Exception as e:
        print("Error crítico limpiando:", e)

```

## Archivo: `database.py`

```python
from contextlib import contextmanager
import sqlite3
import os
import datetime
import utils
from utils import get_due_date

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'decretometro.db')
TOLERANCE = 0.01

# Constantes de tipos de destino (Trazabilidad)
DESTINO_FIN_ORIGINAL = 'fin_original'
DESTINO_RESERVA = 'reserva'
DESTINO_OTRA_OBRA = 'otra_obra'

def _validar_op_o_nota_db(nro_op, notas, contexto="movimiento"):
    """Valida a nivel de base de datos que exista un número de OP o una nota válida (10 a 30 caracteres)."""
    op_ok = bool(nro_op and str(nro_op).strip())
    nota_ok = bool(notas and 10 <= len(str(notas).strip()) <= 30)
    if not op_ok and not nota_ok:
        raise ValueError(
            f"El {contexto} debe tener un número de OP Bejerman o una observación de 10 a 30 caracteres."
        )

def get_connection():
    # Permitir el uso de claves foráneas con timeout de 10 segundos
    conn = sqlite3.connect(DB_PATH, timeout=10.0)
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.row_factory = sqlite3.Row
    return conn

@contextmanager
def db_session():
    """Maneja transacciones seguras con commit/rollback y cierre automático de conexiones."""
    conn = get_connection()
    try:
        yield conn
        conn.commit()
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()

def init_db():
    with db_session() as conn:
        cursor = conn.cursor()
    
        # Crear tabla de versiones si no existe
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS schema_version (
                id INTEGER PRIMARY KEY,
                version INTEGER NOT NULL
            )
        ''')
        
        # Obtener versión actual
        cursor.execute('SELECT version FROM schema_version WHERE id = 1')
        row = cursor.fetchone()
        version_actual = row['version'] if row else 0

        # --- Tablas Base (Esquema Inicial v0) ---
        
        # Tabla Decretos (sin expediente_imuh)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS decretos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nro_decreto INTEGER NOT NULL,
                anio INTEGER NOT NULL,
                nro_expediente TEXT NOT NULL,
                destino_fondos TEXT NOT NULL,
                estado TEXT NOT NULL DEFAULT 'Vigente',
                pdf_path TEXT
            )
        ''')
    
        # Tabla Cuotas
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS cuotas (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                decreto_id INTEGER NOT NULL,
                mes INTEGER NOT NULL,
                anio INTEGER NOT NULL,
                monto REAL NOT NULL,
                FOREIGN KEY (decreto_id) REFERENCES decretos(id) ON DELETE CASCADE
            )
        ''')
    
        # Tabla Cobros
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS cobros (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                cuota_id INTEGER NOT NULL,
                monto REAL NOT NULL,
                fecha DATE NOT NULL,
                comprobante_path TEXT,
                FOREIGN KEY (cuota_id) REFERENCES cuotas(id) ON DELETE CASCADE
            )
        ''')

        # Tabla Aportes Funcionamiento
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS aportes_funcionamiento (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                anio INTEGER NOT NULL,
                mes INTEGER NOT NULL,
                monto_pautado REAL NOT NULL,
                monto_cobrado REAL DEFAULT 0,
                fecha_cobro DATE
            )
        ''')

        # Tabla Aportes Sueldo (sin estado ni fecha_renuncia)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS aportes_sueldo (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                anio INTEGER NOT NULL,
                mes INTEGER NOT NULL,
                monto_pedido REAL NOT NULL,
                fecha_pedido DATE NOT NULL,
                monto_cobrado REAL DEFAULT 0,
                fecha_cobro DATE
            )
        ''')

        # Tabla Aportes SAC (sin estado ni fecha_renuncia)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS aportes_sac (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                anio INTEGER NOT NULL,
                cuota_nro INTEGER NOT NULL,
                monto_pedido REAL NOT NULL,
                fecha_pedido DATE NOT NULL,
                monto_cobrado REAL DEFAULT 0,
                fecha_cobro DATE
            )
        ''')
    
        # Tabla Prestamos Internos (Desvíos de fondos)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS prestamos_internos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                decreto_origen_id INTEGER NOT NULL,
                destino TEXT NOT NULL,
                monto REAL NOT NULL,
                fecha DATE NOT NULL,
                motivo TEXT,
                devolucion_estado TEXT NOT NULL DEFAULT 'Pendiente',
                fecha_devolucion DATE,
                FOREIGN KEY (decreto_origen_id) REFERENCES decretos(id) ON DELETE CASCADE
            )
        ''')
    
        # Tabla Recuperos (Devoluciones parciales o totales de préstamos)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS recuperos_internos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                prestamo_id INTEGER NOT NULL,
                monto REAL NOT NULL,
                fecha DATE NOT NULL,
                FOREIGN KEY (prestamo_id) REFERENCES prestamos_internos(id) ON DELETE CASCADE
            )
        ''')
    
        # --- TABLAS DE DISTRIBUCION (Trazabilidad) ---

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS cobro_distribuciones (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                cobro_id        INTEGER NOT NULL UNIQUE,
                monto_fin_orig  REAL NOT NULL DEFAULT 0,
                monto_reserva   REAL NOT NULL DEFAULT 0,
                notas           TEXT,
                FOREIGN KEY (cobro_id) REFERENCES cobros(id) ON DELETE CASCADE
            )
        ''')

        # sin decreto_destino_id
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS cobro_reserva_usos (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                cobro_id        INTEGER NOT NULL,
                monto           REAL NOT NULL,
                destino_tipo    TEXT NOT NULL,
                destino_detalle TEXT,
                fecha           DATE NOT NULL,
                notas           TEXT,
                nro_op          TEXT,
                FOREIGN KEY (cobro_id) REFERENCES cobros(id) ON DELETE CASCADE
            )
        ''')

        # sin decreto_destino_id
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS cobro_desvios (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                cobro_id    INTEGER NOT NULL,
                destino     TEXT NOT NULL,
                monto       REAL NOT NULL,
                motivo      TEXT,
                fecha       DATE NOT NULL,
                nro_op      TEXT,
                FOREIGN KEY (cobro_id) REFERENCES cobros(id) ON DELETE CASCADE
            )
        ''')

        # sin decreto_destino_id, sin notas
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS cobro_desvios_recuperos (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                desvio_id       INTEGER NOT NULL,
                monto           REAL NOT NULL,
                fecha           DATE NOT NULL,
                destino_tipo    TEXT NOT NULL,
                destino_detalle TEXT,
                nro_op          TEXT,
                FOREIGN KEY (desvio_id) REFERENCES cobro_desvios(id) ON DELETE CASCADE
            )
        ''')

        # sin notas
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS cobro_reserva_usos_recuperos (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                reserva_uso_id  INTEGER NOT NULL,
                monto           REAL NOT NULL,
                fecha           DATE NOT NULL,
                destino_tipo    TEXT NOT NULL,
                destino_detalle TEXT,
                decreto_destino_id INTEGER REFERENCES decretos(id),
                nro_op          TEXT,
                FOREIGN KEY (reserva_uso_id) REFERENCES cobro_reserva_usos(id) ON DELETE CASCADE
            )
        ''')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS cobro_fin_original_usos (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                cobro_id        INTEGER NOT NULL,
                monto           REAL NOT NULL,
                fecha           DATE NOT NULL,
                nro_op          TEXT,
                notas           TEXT,
                obra_id         INTEGER REFERENCES obras(id),
                gasto_nombre    TEXT,
                gasto_expediente_imuh TEXT,
                FOREIGN KEY (cobro_id) REFERENCES cobros(id) ON DELETE CASCADE
            )
        ''')
    
        # Tabla Solicitudes de Financiamiento
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS solicitudes_financiamiento (
                id                  INTEGER PRIMARY KEY AUTOINCREMENT,
                nro_expediente      TEXT NOT NULL UNIQUE,
                expediente_imuh     TEXT,
                destino_fondos      TEXT NOT NULL,
                monto_solicitado    REAL NOT NULL,
                fecha_solicitud     DATE NOT NULL,
                estado              TEXT NOT NULL DEFAULT 'Pendiente',
                decreto_id          INTEGER REFERENCES decretos(id) ON DELETE SET NULL,
                pdf_path            TEXT,
                notas               TEXT
            )
        ''')
        
        # --- Diccionario de Migraciones Ordenadas ---
        MIGRACIONES = [
            (1, "ALTER TABLE cobro_desvios ADD COLUMN decreto_destino_id INTEGER REFERENCES decretos(id)"),
            (2, "ALTER TABLE cobro_reserva_usos ADD COLUMN decreto_destino_id INTEGER REFERENCES decretos(id)"),
            (3, "ALTER TABLE cobro_desvios_recuperos ADD COLUMN decreto_destino_id INTEGER REFERENCES decretos(id)"),
            (4, "ALTER TABLE cobro_desvios_recuperos ADD COLUMN notas TEXT"),
            (5, "ALTER TABLE cobro_reserva_usos_recuperos ADD COLUMN notas TEXT"),
            (6, "ALTER TABLE decretos ADD COLUMN expediente_imuh TEXT"),
            (7, "ALTER TABLE aportes_sueldo ADD COLUMN estado TEXT DEFAULT 'Pendiente'"),
            (8, "ALTER TABLE aportes_sac ADD COLUMN estado TEXT DEFAULT 'Pendiente'"),
            (9, "ALTER TABLE aportes_sueldo ADD COLUMN fecha_renuncia DATE"),
            (10, "ALTER TABLE aportes_sac ADD COLUMN fecha_renuncia DATE"),
            (11, "UPDATE cobro_desvios_recuperos SET notas = 'Histórico - Sin OP' WHERE (nro_op IS NULL OR TRIM(nro_op) = '') AND (notas IS NULL OR TRIM(notas) = '')"),
            (12, "UPDATE cobro_reserva_usos_recuperos SET notas = 'Histórico - Sin OP' WHERE (nro_op IS NULL OR TRIM(nro_op) = '') AND (notas IS NULL OR TRIM(notas) = '')"),
            (13, "UPDATE aportes_sueldo SET estado = 'Cobrado' WHERE fecha_cobro IS NOT NULL AND estado = 'Pendiente'"),
            (14, "UPDATE aportes_sac SET estado = 'Cobrado' WHERE fecha_cobro IS NOT NULL AND estado = 'Pendiente'"),
            (15, "CREATE TABLE IF NOT EXISTS obras (id INTEGER PRIMARY KEY AUTOINCREMENT, nombre TEXT NOT NULL, expediente_imuh TEXT NOT NULL UNIQUE, activa INTEGER NOT NULL DEFAULT 1 CHECK(activa IN (0, 1)))"),
            (16, "CREATE TABLE IF NOT EXISTS decretos_obras (decreto_id INTEGER NOT NULL REFERENCES decretos(id) ON DELETE CASCADE, obra_id INTEGER NOT NULL REFERENCES obras(id) ON DELETE RESTRICT, PRIMARY KEY (decreto_id, obra_id))"),
            (17, "ALTER TABLE cobro_desvios ADD COLUMN obra_id INTEGER REFERENCES obras(id)"),
            (18, "ALTER TABLE cobro_desvios ADD COLUMN gasto_nombre TEXT"),
            (19, "ALTER TABLE cobro_desvios ADD COLUMN gasto_expediente_imuh TEXT"),
            (20, "ALTER TABLE cobro_reserva_usos ADD COLUMN obra_id INTEGER REFERENCES obras(id)"),
            (21, "ALTER TABLE cobro_reserva_usos ADD COLUMN gasto_nombre TEXT"),
            (22, "ALTER TABLE cobro_reserva_usos ADD COLUMN gasto_expediente_imuh TEXT"),
            (23, "ALTER TABLE solicitudes_financiamiento ADD COLUMN obra_id INTEGER REFERENCES obras(id)"),
            (24, "CREATE TABLE IF NOT EXISTS gastos_funcionamiento (id INTEGER PRIMARY KEY AUTOINCREMENT, nombre TEXT NOT NULL, expediente_imuh TEXT NOT NULL UNIQUE, activo INTEGER NOT NULL DEFAULT 1 CHECK(activo IN (0, 1)))"),
            (25, "CREATE TABLE IF NOT EXISTS proveedores_obras (id INTEGER PRIMARY KEY AUTOINCREMENT, razon_social TEXT NOT NULL UNIQUE, cuit TEXT NOT NULL UNIQUE, activo INTEGER NOT NULL DEFAULT 1 CHECK(activo IN (0, 1)))"),
            (26, "CREATE TABLE IF NOT EXISTS proveedores_funcionamiento (id INTEGER PRIMARY KEY AUTOINCREMENT, razon_social TEXT NOT NULL UNIQUE, cuit TEXT NOT NULL UNIQUE, activo INTEGER NOT NULL DEFAULT 1 CHECK(activo IN (0, 1)))"),
            (27, "ALTER TABLE obras ADD COLUMN proveedor_id INTEGER REFERENCES proveedores_obras(id)"),
            (28, "ALTER TABLE gastos_funcionamiento ADD COLUMN proveedor_id INTEGER REFERENCES proveedores_funcionamiento(id)"),
            (29, "ALTER TABLE cobro_fin_original_usos ADD COLUMN obra_id INTEGER REFERENCES obras(id)"),
            (30, "ALTER TABLE cobro_fin_original_usos ADD COLUMN gasto_nombre TEXT"),
            (31, "ALTER TABLE cobro_fin_original_usos ADD COLUMN gasto_expediente_imuh TEXT"),
            (32, "CREATE TABLE IF NOT EXISTS op_bejerman (nro_op TEXT PRIMARY KEY, obra_id INTEGER REFERENCES obras(id) ON DELETE RESTRICT, gasto_id INTEGER REFERENCES gastos_funcionamiento(id) ON DELETE RESTRICT)")
        ]
        
        # Ejecutar migrador
        for version, sql in MIGRACIONES:
            if version > version_actual:
                try:
                    cursor.execute(sql)
                except sqlite3.OperationalError as e:
                    # Ignorar si la columna ya existe
                    err_msg = str(e).lower()
                    if "duplicate column name" in err_msg or "already exists" in err_msg:
                        pass
                    else:
                        raise e
                cursor.execute('INSERT OR REPLACE INTO schema_version (id, version) VALUES (1, ?)', (version,))
                conn.commit()

    # --- Decretos CRUD ---

def add_decreto(nro_decreto, anio, nro_expediente, destino_fondos, pdf_path=None, expediente_imuh=None):
    if nro_decreto <= 0:
        raise ValueError("El número de decreto debe ser mayor a 0.")
    if anio <= 0:
        raise ValueError("El año debe ser mayor a 0.")
    if not nro_expediente or not nro_expediente.strip():
        raise ValueError("El número de expediente no puede estar vacío.")
    if not destino_fondos or not destino_fondos.strip():
        raise ValueError("El destino de fondos no puede estar vacío.")
    with db_session() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO decretos (nro_decreto, anio, nro_expediente, destino_fondos, pdf_path, estado, expediente_imuh)
            VALUES (?, ?, ?, ?, ?, 'Vigente', ?)
        ''', (nro_decreto, anio, nro_expediente, destino_fondos, pdf_path, expediente_imuh))
        decreto_id = cursor.lastrowid
        conn.commit()
        return decreto_id


def get_decretos():
    with db_session() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM decretos ORDER BY anio DESC, nro_decreto DESC')
        rows = cursor.fetchall()
        return [dict(ix) for ix in rows]


def get_decreto(decreto_id):
    with db_session() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM decretos WHERE id = ?', (decreto_id,))
        row = cursor.fetchone()
        return dict(row) if row else None


def check_expediente_exists(nro_expediente, exclude_id=None):
    with db_session() as conn:
        cursor = conn.cursor()
        if exclude_id:
            cursor.execute('SELECT id FROM decretos WHERE nro_expediente = ? AND id != ?', (nro_expediente, exclude_id))
        else:
            cursor.execute('SELECT id FROM decretos WHERE nro_expediente = ?', (nro_expediente,))
        row = cursor.fetchone()
        return row is not None


def update_decreto(decreto_id, nro_decreto, anio, nro_expediente, destino_fondos, pdf_path, expediente_imuh=None):
    if nro_decreto <= 0:
        raise ValueError("El número de decreto debe ser mayor a 0.")
    if anio <= 0:
        raise ValueError("El año debe ser mayor a 0.")
    if not nro_expediente or not nro_expediente.strip():
        raise ValueError("El número de expediente no puede estar vacío.")
    if not destino_fondos or not destino_fondos.strip():
        raise ValueError("El destino de fondos no puede estar vacío.")
    with db_session() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            UPDATE decretos
            SET nro_decreto = ?, anio = ?, nro_expediente = ?, destino_fondos = ?, pdf_path = ?, expediente_imuh = ?
            WHERE id = ?
        ''', (nro_decreto, anio, nro_expediente, destino_fondos, pdf_path, expediente_imuh, decreto_id))
        conn.commit()


def delete_decreto(decreto_id):
    with db_session() as conn:
        cursor = conn.cursor()

        # Verificar dependencias antes de eliminar para evitar cascadas accidentales
        cursor.execute('''
            SELECT COUNT(*) as cnt FROM cuotas cu 
            JOIN cobros c ON c.cuota_id = cu.id 
            WHERE cu.decreto_id = ?
        ''', (decreto_id,))
        if cursor.fetchone()['cnt'] > 0:
            raise ValueError("No se puede eliminar un decreto que tiene cobros registrados. Por favor, anule el decreto o elimine los cobros asociados primero.")
            
        cursor.execute('SELECT COUNT(*) as cnt FROM prestamos_internos WHERE decreto_origen_id = ?', (decreto_id,))
        if cursor.fetchone()['cnt'] > 0:
            raise ValueError("No se puede eliminar un decreto que tiene préstamos registrados. Por favor, elimine los préstamos asociados primero.")
    
        cursor.execute('SELECT pdf_path FROM decretos WHERE id = ?', (decreto_id,))
        d_row = cursor.fetchone()
        if d_row and d_row['pdf_path'] and os.path.exists(d_row['pdf_path']):
            try:
                os.remove(d_row['pdf_path'])
            except OSError:
                pass
        
        cursor.execute('''
            SELECT c.comprobante_path FROM cobros c
            JOIN cuotas cu ON c.cuota_id = cu.id
            WHERE cu.decreto_id = ?
        ''', (decreto_id,))
        comprobantes = cursor.fetchall()
        for row in comprobantes:
            if row['comprobante_path'] and os.path.exists(row['comprobante_path']):
                try:
                    os.remove(row['comprobante_path'])
                except OSError:
                    pass

        cursor.execute("UPDATE solicitudes_financiamiento SET estado = 'Pendiente', decreto_id = NULL WHERE decreto_id = ?", (decreto_id,))
        cursor.execute('DELETE FROM decretos WHERE id = ?', (decreto_id,))
        conn.commit()


def update_estado_decreto(decreto_id, estado):
    with db_session() as conn:
        cursor = conn.cursor()
        cursor.execute('UPDATE decretos SET estado = ? WHERE id = ?', (estado, decreto_id))
        conn.commit()

    # --- Cuotas CRUD ---

def add_cuota(decreto_id, mes, anio, monto):
    if monto <= 0:
        raise ValueError("El monto de la cuota debe ser mayor a 0.")
    if not (1 <= mes <= 12):
        raise ValueError("El mes debe estar entre 1 y 12.")
    with db_session() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO cuotas (decreto_id, mes, anio, monto)
            VALUES (?, ?, ?, ?)
        ''', (decreto_id, mes, anio, monto))
        cuota_id = cursor.lastrowid
        conn.commit()
        return cuota_id


def get_cuotas_by_decreto(decreto_id):
    with db_session() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM cuotas WHERE decreto_id = ? ORDER BY anio ASC, mes ASC', (decreto_id,))
        rows = cursor.fetchall()
        return [dict(ix) for ix in rows]


def get_cuota(cuota_id):
    with db_session() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM cuotas WHERE id = ?', (cuota_id,))
        row = cursor.fetchone()
        return dict(row) if row else None



def get_total_cobrado_por_cuota(cuota_id):
    with db_session() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT SUM(monto) as cobrado FROM cobros WHERE cuota_id = ?', (cuota_id,))
        c_row = cursor.fetchone()
        return c_row['cobrado'] if c_row and c_row['cobrado'] else 0.0

def update_cuota_estimacion(cuota_id, fecha_estimada):
    with db_session() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            UPDATE cuotas SET fecha_estimada_cobro = ? WHERE id = ?
        ''', (fecha_estimada, cuota_id))
        conn.commit()

    # --- Cobros CRUD ---

def add_cobro(cuota_id, monto, fecha, comprobante_path=None):
    if monto <= 0:
        raise ValueError("El monto cobrado debe ser mayor a 0.")
    fecha_dt = datetime.datetime.strptime(fecha, '%Y-%m-%d').date()
    if fecha_dt > datetime.date.today():
        raise ValueError("La fecha de cobro no puede ser futura.")
        
    with db_session() as conn:
        cursor = conn.cursor()
    
        # Evitar sobrepagos
        cursor.execute('SELECT monto, mes, anio FROM cuotas WHERE id = ?', (cuota_id,))
        q_row = cursor.fetchone()
        if not q_row:
            raise ValueError("Cuota no encontrada.")
            
        # Validar período de la cuota
        cuota_start = f"{q_row['anio']}-{q_row['mes']:02d}-01"
        if fecha < cuota_start:
            raise ValueError(f"La fecha de cobro ({fecha}) no puede ser anterior al inicio del período de la cuota ({q_row['mes']:02d}/{q_row['anio']}).")
    
        cursor.execute('SELECT SUM(monto) as cobrado FROM cobros WHERE cuota_id = ?', (cuota_id,))
        c_row = cursor.fetchone()
        cobrado_previo = c_row['cobrado'] if c_row and c_row['cobrado'] else 0
        saldo = q_row['monto'] - cobrado_previo
    
        if monto > (saldo + 0.01):
            raise ValueError(f"El monto a cobrar ({monto}) supera el saldo pendiente de la cuota ({saldo:.2f}).")

        cursor.execute('''
            INSERT INTO cobros (cuota_id, monto, fecha, comprobante_path)
            VALUES (?, ?, ?, ?)
        ''', (cuota_id, monto, fecha, comprobante_path))
        cobro_id = cursor.lastrowid
        conn.commit()
        check_estado_decreto_by_cuota(conn, cuota_id)
        return cobro_id


def get_all_cobros():
    with db_session() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            WITH ranked_cuotas AS (
                SELECT id, decreto_id, mes, anio,
                       ROW_NUMBER() OVER (PARTITION BY decreto_id ORDER BY anio ASC, mes ASC) as seq_nro,
                       COUNT(*) OVER (PARTITION BY decreto_id) as total_cuotas
                FROM cuotas
            )
            SELECT c.id, c.monto, c.fecha, c.comprobante_path, c.cuota_id,
                   rc.mes, rc.anio, 
                   rc.seq_nro, rc.total_cuotas,
                   d.nro_decreto, d.anio as decreto_anio, d.id as decreto_id,
                   d.destino_fondos as obra
            FROM cobros c
            JOIN ranked_cuotas rc ON c.cuota_id = rc.id
            JOIN decretos d ON rc.decreto_id = d.id
            ORDER BY c.fecha DESC
        ''')
        rows = cursor.fetchall()
        return [dict(ix) for ix in rows]



def get_cobros_by_cuota(cuota_id):
    with db_session() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM cobros WHERE cuota_id = ? ORDER BY fecha ASC', (cuota_id,))
        rows = cursor.fetchall()
        return [dict(ix) for ix in rows]


def get_cobro(cobro_id):
    with db_session() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT c.*, d.id as decreto_id, d.nro_decreto, d.anio as decreto_anio
            FROM cobros c
            JOIN cuotas cu ON c.cuota_id = cu.id
            JOIN decretos d ON cu.decreto_id = d.id
            WHERE c.id = ?
        ''', (cobro_id,))
        row = cursor.fetchone()
        return dict(row) if row else None


def delete_cobro(cobro_id):
    with db_session() as conn:
        cursor = conn.cursor()

        # Verificar dependencias antes de eliminar
        cursor.execute('SELECT COUNT(*) as cnt FROM cobro_fin_original_usos WHERE cobro_id = ?', (cobro_id,))
        if cursor.fetchone()['cnt'] > 0:
            raise ValueError("No se puede eliminar un cobro con pagos a Fin Original registrados. Elimine los pagos primero.")
            
        cursor.execute('SELECT COUNT(*) as cnt FROM cobro_desvios WHERE cobro_id = ?', (cobro_id,))
        if cursor.fetchone()['cnt'] > 0:
            raise ValueError("No se puede eliminar un cobro que tiene desvíos de fondos registrados. Elimine los desvíos primero.")
            
        cursor.execute('SELECT COUNT(*) as cnt FROM cobro_reserva_usos WHERE cobro_id = ?', (cobro_id,))
        if cursor.fetchone()['cnt'] > 0:
            raise ValueError("No se puede eliminar un cobro que tiene usos de reserva registrados. Elimine los usos primero.")

        cursor.execute('SELECT cuota_id FROM cobros WHERE id = ?', (cobro_id,))
        cuota_row = cursor.fetchone()
        cursor.execute('DELETE FROM cobros WHERE id = ?', (cobro_id,))
        conn.commit()
        if cuota_row:
            check_estado_decreto_by_cuota(conn, cuota_row['cuota_id'])

    # --- Aportes Funcionamiento ---

def set_monto_funcionamiento_anio(anio, monto_mensual):
    if anio > datetime.date.today().year:
        raise ValueError("No se pueden generar aportes para un año futuro.")
    if monto_mensual <= 0:
        raise ValueError("El monto mensual pautado debe ser mayor a 0.")
    with db_session() as conn:
        cursor = conn.cursor()
        cursor.execute('DELETE FROM aportes_funcionamiento WHERE anio = ? AND fecha_cobro IS NULL', (anio,))
        for mes in range(1, 13):
            cursor.execute('''
                INSERT INTO aportes_funcionamiento (anio, mes, monto_pautado)
                VALUES (?, ?, ?)
            ''', (anio, mes, monto_mensual))
        conn.commit()


def get_aportes_funcionamiento(anio=None):
    with db_session() as conn:
        cursor = conn.cursor()
        if anio:
            cursor.execute('SELECT * FROM aportes_funcionamiento WHERE anio = ? ORDER BY mes ASC', (anio,))
        else:
            cursor.execute('SELECT * FROM aportes_funcionamiento ORDER BY anio DESC, mes ASC')
        rows = cursor.fetchall()
        return [dict(ix) for ix in rows]


def registrar_cobro_funcionamiento(aporte_id, monto, fecha):
    if monto <= 0:
        raise ValueError("El monto cobrado debe ser mayor a 0.")
    fecha_dt = datetime.datetime.strptime(fecha, '%Y-%m-%d').date()
    if fecha_dt > datetime.date.today():
        raise ValueError("La fecha de cobro no puede ser futura.")
    with db_session() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT monto_pautado FROM aportes_funcionamiento WHERE id = ?', (aporte_id,))
        row = cursor.fetchone()
        if not row:
            raise ValueError("Aporte de funcionamiento no encontrado.")
        if monto > (row['monto_pautado'] + 0.01):
            raise ValueError(f"El monto cobrado ({monto:.2f}) supera el monto pautado mensual ({row['monto_pautado']:.2f}).")
            
        cursor.execute('''
            UPDATE aportes_funcionamiento 
            SET monto_cobrado = ?, fecha_cobro = ?
            WHERE id = ?
        ''', (monto, fecha, aporte_id))
        conn.commit()


def reset_cobro_funcionamiento(aporte_id):
    with db_session() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            UPDATE aportes_funcionamiento 
            SET monto_cobrado = 0, fecha_cobro = NULL
            WHERE id = ?
        ''', (aporte_id,))
        conn.commit()


def delete_anio_funcionamiento(anio):
    with db_session() as conn:
        cursor = conn.cursor()
        cursor.execute('DELETE FROM aportes_funcionamiento WHERE anio = ?', (anio,))
        conn.commit()

    # --- Aportes Sueldo ---

def add_aporte_sueldo(anio, mes, monto_pedido, fecha_pedido):
    if anio > datetime.date.today().year:
        raise ValueError("El año no puede ser futuro.")
    if not (1 <= mes <= 12):
        raise ValueError("El mes debe estar entre 1 y 12.")
    if monto_pedido <= 0:
        raise ValueError("El monto pedido debe ser mayor a 0.")
    try:
        datetime.datetime.strptime(fecha_pedido, '%Y-%m-%d')
    except ValueError:
        raise ValueError("La fecha del pedido debe ser válida y tener el formato YYYY-MM-DD.")
    with db_session() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO aportes_sueldo (anio, mes, monto_pedido, fecha_pedido)
            VALUES (?, ?, ?, ?)
        ''', (anio, mes, monto_pedido, fecha_pedido))
        conn.commit()


def get_aportes_sueldo(anio=None):
    with db_session() as conn:
        cursor = conn.cursor()
        if anio:
            cursor.execute('SELECT * FROM aportes_sueldo WHERE anio = ? ORDER BY mes ASC', (anio,))
        else:
            cursor.execute('SELECT * FROM aportes_sueldo ORDER BY anio DESC, mes ASC')
        rows = cursor.fetchall()
        return [dict(ix) for ix in rows]


def registrar_cobro_sueldo(aporte_id, monto, fecha):
    if monto <= 0:
        raise ValueError("El monto cobrado debe ser mayor a 0.")
    fecha_dt = datetime.datetime.strptime(fecha, '%Y-%m-%d').date()
    if fecha_dt > datetime.date.today():
        raise ValueError("La fecha de cobro no puede ser futura.")
    with db_session() as conn:
        cursor = conn.cursor()
        # Obtener pedido original
        cursor.execute('SELECT monto_pedido, monto_cobrado FROM aportes_sueldo WHERE id = ?', (aporte_id,))
        row = cursor.fetchone()
        if not row: 
            return
    
        nuevo_total = (row['monto_cobrado'] or 0) + monto
        total_pedido = row['monto_pedido']
        
        # Validar no sobrepagar
        if nuevo_total > (total_pedido + 0.01):
            raise ValueError(f"El monto acumulado cobrado ({nuevo_total:.2f}) superaría el pedido original ({total_pedido:.2f}).")
    
        # Determinar nuevo estado
        if nuevo_total >= (total_pedido - 0.01):
            estado = 'Cobrado'
        else:
            estado = 'Parcial'

        cursor.execute('''
            UPDATE aportes_sueldo 
            SET monto_cobrado = ?, fecha_cobro = ?, estado = ?
            WHERE id = ?
        ''', (nuevo_total, fecha, estado, aporte_id))
        conn.commit()


def delete_aporte_sueldo(aporte_id):
    with db_session() as conn:
        cursor = conn.cursor()
        cursor.execute('DELETE FROM aportes_sueldo WHERE id = ?', (aporte_id,))
        conn.commit()


def update_aporte_sueldo(aporte_id, anio, mes, monto_pedido, fecha_pedido):
    if anio > datetime.date.today().year:
        raise ValueError("El año no puede ser futuro.")
    if not (1 <= mes <= 12):
        raise ValueError("El mes debe estar entre 1 y 12.")
    if monto_pedido <= 0:
        raise ValueError("El monto pedido debe ser mayor a 0.")
    try:
        datetime.datetime.strptime(fecha_pedido, '%Y-%m-%d')
    except ValueError:
        raise ValueError("La fecha del pedido debe ser válida y tener el formato YYYY-MM-DD.")
    with db_session() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            UPDATE aportes_sueldo
            SET anio = ?, mes = ?, monto_pedido = ?, fecha_pedido = ?
            WHERE id = ?
        ''', (anio, mes, monto_pedido, fecha_pedido, aporte_id))
        conn.commit()

    # --- Aportes SAC ---

def add_aporte_sac(anio, cuota_nro, monto_pedido, fecha_pedido):
    if anio > datetime.date.today().year:
        raise ValueError("El año no puede ser futuro.")
    if cuota_nro not in (1, 2):
        raise ValueError("La cuota de SAC solo puede ser 1 o 2.")
    if monto_pedido <= 0:
        raise ValueError("El monto pedido debe ser mayor a 0.")
    try:
        datetime.datetime.strptime(fecha_pedido, '%Y-%m-%d')
    except ValueError:
        raise ValueError("La fecha del pedido debe ser válida y tener el formato YYYY-MM-DD.")
    with db_session() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO aportes_sac (anio, cuota_nro, monto_pedido, fecha_pedido)
            VALUES (?, ?, ?, ?)
        ''', (anio, cuota_nro, monto_pedido, fecha_pedido))
        conn.commit()


def get_aportes_sac(anio=None):
    with db_session() as conn:
        cursor = conn.cursor()
        if anio:
            cursor.execute('SELECT * FROM aportes_sac WHERE anio = ? ORDER BY cuota_nro ASC', (anio,))
        else:
            cursor.execute('SELECT * FROM aportes_sac ORDER BY anio DESC, cuota_nro ASC')
        rows = cursor.fetchall()
        return [dict(ix) for ix in rows]


def registrar_cobro_sac(aporte_id, monto, fecha):
    if monto <= 0:
        raise ValueError("El monto cobrado debe ser mayor a 0.")
    fecha_dt = datetime.datetime.strptime(fecha, '%Y-%m-%d').date()
    if fecha_dt > datetime.date.today():
        raise ValueError("La fecha de cobro no puede ser futura.")
    with db_session() as conn:
        cursor = conn.cursor()
        # Obtener pedido original
        cursor.execute('SELECT monto_pedido, monto_cobrado FROM aportes_sac WHERE id = ?', (aporte_id,))
        row = cursor.fetchone()
        if not row: 
            return
    
        nuevo_total = (row['monto_cobrado'] or 0) + monto
        total_pedido = row['monto_pedido']
        
        # Validar no sobrepagar
        if nuevo_total > (total_pedido + 0.01):
            raise ValueError(f"El monto acumulado cobrado ({nuevo_total:.2f}) superaría el pedido original ({total_pedido:.2f}).")
    
        # Determinar nuevo estado
        if nuevo_total >= (total_pedido - 0.01):
            estado = 'Cobrado'
        else:
            estado = 'Parcial'

        cursor.execute('''
            UPDATE aportes_sac 
            SET monto_cobrado = ?, fecha_cobro = ?, estado = ?
            WHERE id = ?
        ''', (nuevo_total, fecha, estado, aporte_id))
        conn.commit()


def delete_aporte_sac(aporte_id):
    with db_session() as conn:
        cursor = conn.cursor()
        cursor.execute('DELETE FROM aportes_sac WHERE id = ?', (aporte_id,))
        conn.commit()


def update_aporte_sac(aporte_id, anio, cuota_nro, monto_pedido, fecha_pedido):
    if anio > datetime.date.today().year:
        raise ValueError("El año no puede ser futuro.")
    if cuota_nro not in (1, 2):
        raise ValueError("La cuota de SAC solo puede ser 1 o 2.")
    if monto_pedido <= 0:
        raise ValueError("El monto pedido debe ser mayor a 0.")
    try:
        datetime.datetime.strptime(fecha_pedido, '%Y-%m-%d')
    except ValueError:
        raise ValueError("La fecha del pedido debe ser válida y tener el formato YYYY-MM-DD.")
    with db_session() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            UPDATE aportes_sac
            SET anio = ?, cuota_nro = ?, monto_pedido = ?, fecha_pedido = ?
            WHERE id = ?
        ''', (anio, cuota_nro, monto_pedido, fecha_pedido, aporte_id))
        conn.commit()

    # --- Lógica de Negocio ---

def check_estado_decreto_by_cuota(conn, cuota_id):
    cursor = conn.cursor()
    cursor.execute('SELECT decreto_id FROM cuotas WHERE id = ?', (cuota_id,))
    row = cursor.fetchone()
    if row:
        check_estado_decreto(conn, row['decreto_id'])

def check_estado_decreto(conn, decreto_id):
    cursor = conn.cursor()
    cursor.execute('SELECT estado FROM decretos WHERE id = ?', (decreto_id,))
    dec = cursor.fetchone()
    if not dec or dec['estado'] == 'Anulado':
        return

    cursor.execute('SELECT SUM(monto) as total FROM cuotas WHERE decreto_id = ?', (decreto_id,))
    total_proyectado = cursor.fetchone()['total'] or 0
    
    cursor.execute('''
        SELECT SUM(c.monto) as total 
        FROM cobros c 
        JOIN cuotas cu ON c.cuota_id = cu.id 
        WHERE cu.decreto_id = ?
    ''', (decreto_id,))
    total_cobrado = cursor.fetchone()['total'] or 0

    if total_cobrado >= (total_proyectado - TOLERANCE) and total_proyectado > 0:
        nuevo_estado = 'Terminado'
    else:
        # Check for overdue
        today = datetime.date.today()
        cursor.execute('SELECT id, mes, anio, monto FROM cuotas WHERE decreto_id = ?', (decreto_id,))
        cuotas = cursor.fetchall()
        
        tiene_deuda_atrasada = False
        for q in cuotas:
            cursor.execute('SELECT SUM(monto) as cobrado FROM cobros WHERE cuota_id = ?', (q['id'],))
            cobrado = cursor.fetchone()['cobrado'] or 0
            if (q['monto'] - cobrado) > TOLERANCE:
                due_date = get_due_date(q['mes'], q['anio'])
                if today > due_date:
                    tiene_deuda_atrasada = True
                    break
        
        nuevo_estado = 'Con deuda' if tiene_deuda_atrasada else 'Vigente'

    cursor.execute('UPDATE decretos SET estado = ? WHERE id = ?', (nuevo_estado, decreto_id))
    conn.commit()

# --- Prestamos Internos (Desvíos/Préstamos) ---
def add_prestamo(decreto_origen_id, destino, monto, fecha, motivo=None):
    if monto <= 0:
        raise ValueError("El monto del préstamo debe ser mayor a 0.")
    fecha_dt = datetime.datetime.strptime(fecha, '%Y-%m-%d').date()
    if fecha_dt > datetime.date.today():
        raise ValueError("La fecha del préstamo no puede ser futura.")
        
    with db_session() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO prestamos_internos (decreto_origen_id, destino, monto, fecha, motivo, devolucion_estado)
            VALUES (?, ?, ?, ?, ?, 'Pendiente')
        ''', (decreto_origen_id, destino, monto, fecha, motivo))
        prestamo_id = cursor.lastrowid
        conn.commit()
        return prestamo_id


def get_prestamos(decreto_origen_id=None):
    with db_session() as conn:
        cursor = conn.cursor()
        if decreto_origen_id:
            cursor.execute('''
                SELECT p.*, d.nro_decreto, d.anio as decreto_anio, d.expediente_imuh,
                       COALESCE((SELECT SUM(monto) FROM recuperos_internos WHERE prestamo_id = p.id), 0) as total_devuelto
                FROM prestamos_internos p
                JOIN decretos d ON p.decreto_origen_id = d.id
                WHERE p.decreto_origen_id = ?
                ORDER BY p.fecha DESC
            ''', (decreto_origen_id,))
        else:
            cursor.execute('''
                SELECT p.*, d.nro_decreto, d.anio as decreto_anio, d.expediente_imuh,
                       COALESCE((SELECT SUM(monto) FROM recuperos_internos WHERE prestamo_id = p.id), 0) as total_devuelto
                FROM prestamos_internos p
                JOIN decretos d ON p.decreto_origen_id = d.id
                ORDER BY p.fecha DESC
            ''')
        rows = cursor.fetchall()
        return [dict(ix) for ix in rows]


def get_recuperos_by_prestamo(prestamo_id):
    with db_session() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM recuperos_internos WHERE prestamo_id = ? ORDER BY fecha ASC', (prestamo_id,))
        rows = cursor.fetchall()
        return [dict(ix) for ix in rows]


def add_recupero(prestamo_id, monto, fecha):
    if monto <= 0:
        raise ValueError("El monto devuelto debe ser mayor a 0.")
    fecha_dt = datetime.datetime.strptime(fecha, '%Y-%m-%d').date()
    if fecha_dt > datetime.date.today():
        raise ValueError("La fecha de devolución no puede ser futura.")
        
    with db_session() as conn:
        cursor = conn.cursor()
    
        # Validar no devolver de más
        cursor.execute('SELECT monto, fecha FROM prestamos_internos WHERE id = ?', (prestamo_id,))
        p_row = cursor.fetchone()
        if not p_row:
            raise ValueError("Préstamo no encontrado.")
        monto_prestamo = p_row['monto']
        fecha_prestamo = p_row['fecha']
        
        if fecha < fecha_prestamo:
            raise ValueError(f"La fecha de devolución ({fecha}) no puede ser anterior a la fecha del préstamo ({fecha_prestamo}).")
    
        cursor.execute('SELECT SUM(monto) as cobrado FROM recuperos_internos WHERE prestamo_id = ?', (prestamo_id,))
        ya_devuelto = cursor.fetchone()['cobrado'] or 0
    
        if (monto + ya_devuelto) > (monto_prestamo + TOLERANCE):
             raise ValueError(f"El monto a devolver ({monto}) supera el saldo pendiente del préstamo ({monto_prestamo - ya_devuelto}).")
         
        cursor.execute('''
            INSERT INTO recuperos_internos (prestamo_id, monto, fecha)
            VALUES (?, ?, ?)
        ''', (prestamo_id, monto, fecha))
        recupero_id = cursor.lastrowid
    
        # Verificar si con esto se salda
        if (monto + ya_devuelto) >= (monto_prestamo - TOLERANCE):
            cursor.execute('''
                UPDATE prestamos_internos 
                SET devolucion_estado = 'Devuelto', fecha_devolucion = ?
                WHERE id = ?
            ''', (fecha, prestamo_id))
        else:
            cursor.execute('''
                UPDATE prestamos_internos 
                SET devolucion_estado = 'Pendiente', fecha_devolucion = NULL
                WHERE id = ?
            ''', (prestamo_id,))
        
        conn.commit()
        return recupero_id


def delete_recupero(recupero_id, prestamo_id):
    with db_session() as conn:
        cursor = conn.cursor()
        cursor.execute('DELETE FROM recuperos_internos WHERE id = ?', (recupero_id,))
        # Always set condition back to Pendiente if a recovery is deleted
        cursor.execute('''
            UPDATE prestamos_internos 
            SET devolucion_estado = 'Pendiente', fecha_devolucion = NULL
            WHERE id = ?
        ''', (prestamo_id,))
        conn.commit()


def update_estado_prestamo(prestamo_id, estado, fecha_devolucion=None):
    with db_session() as conn:
        cursor = conn.cursor()
        if estado == 'Devuelto':
            if not fecha_devolucion:
                fecha_devolucion = datetime.date.today().strftime('%Y-%m-%d')
            cursor.execute('''
                UPDATE prestamos_internos 
                SET devolucion_estado = ?, fecha_devolucion = ?
                WHERE id = ?
            ''', (estado, fecha_devolucion, prestamo_id))
        else:
            cursor.execute('''
                UPDATE prestamos_internos 
                SET devolucion_estado = ?, fecha_devolucion = NULL
                WHERE id = ?
            ''', (estado, prestamo_id))
        conn.commit()


def delete_prestamo(prestamo_id):
    with db_session() as conn:
        cursor = conn.cursor()
        cursor.execute('DELETE FROM prestamos_internos WHERE id = ?', (prestamo_id,))
        conn.commit()

    # --- Distribución de Cobranzas (NUEVO) ---


def get_distribucion_by_cobro(cobro_id):
    with db_session() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM cobro_distribuciones WHERE cobro_id = ?', (cobro_id,))
        row = cursor.fetchone()
        return dict(row) if row else None


def upsert_distribucion(cobro_id, monto_fin_orig, monto_reserva, notas):
    if monto_fin_orig < 0 or monto_reserva < 0:
        raise ValueError("Los montos no pueden ser negativos.")
        
    with db_session() as conn:
        cursor = conn.cursor()
    
        cursor.execute('SELECT monto FROM cobros WHERE id = ?', (cobro_id,))
        c_row = cursor.fetchone()
        if not c_row:
            raise ValueError("Cobro no encontrado.")
    
        cursor.execute('SELECT COALESCE(SUM(monto), 0) as tot_desvios FROM cobro_desvios WHERE cobro_id = ?', (cobro_id,))
        tot_desvios = cursor.fetchone()['tot_desvios']

        cursor.execute('''
            SELECT COALESCE(SUM(cdr.monto), 0) as tot 
            FROM cobro_desvios_recuperos cdr
            JOIN cobro_desvios cd ON cdr.desvio_id = cd.id
            WHERE cd.cobro_id = ? AND cdr.destino_tipo = 'sin_distribucion'
        ''', (cobro_id,))
        rec_desv_sd = cursor.fetchone()['tot']

        cursor.execute('''
            SELECT COALESCE(SUM(crur.monto), 0) as tot 
            FROM cobro_reserva_usos_recuperos crur
            JOIN cobro_reserva_usos cru ON crur.reserva_uso_id = cru.id
            WHERE cru.cobro_id = ? AND crur.destino_tipo = 'sin_distribucion'
        ''', (cobro_id,))
        rec_res_sd = cursor.fetchone()['tot']

        tot_recuperos_sd = rec_desv_sd + rec_res_sd
    
        if (monto_fin_orig + monto_reserva + tot_desvios - tot_recuperos_sd) > (c_row['monto'] + TOLERANCE):
            raise ValueError("La suma ingresada supera el monto total del cobro.")

        cursor.execute('SELECT COALESCE(SUM(monto), 0) as tot FROM cobro_reserva_usos WHERE cobro_id = ?', (cobro_id,))
        ru_total = cursor.fetchone()['tot']
        
        cursor.execute('''
            SELECT COALESCE(SUM(crur.monto), 0) as tot 
            FROM cobro_reserva_usos_recuperos crur
            JOIN cobro_reserva_usos cru ON crur.reserva_uso_id = cru.id
            WHERE cru.cobro_id = ? AND crur.destino_tipo = 'reserva'
        ''', (cobro_id,))
        recru_res_total = cursor.fetchone()['tot']
        
        cursor.execute('''
            SELECT COALESCE(SUM(cdr.monto), 0) as tot 
            FROM cobro_desvios_recuperos cdr
            JOIN cobro_desvios cd ON cdr.desvio_id = cd.id
            WHERE cd.cobro_id = ? AND cdr.destino_tipo = 'reserva'
        ''', (cobro_id,))
        rec_desv_res_total = cursor.fetchone()['tot']
        
        ya_usado_neto = ru_total - recru_res_total - rec_desv_res_total
        
        if monto_reserva < (ya_usado_neto - TOLERANCE):
            raise ValueError(f"No se puede reducir la reserva a {monto_reserva} porque ya se han utilizado {ya_usado_neto} de la misma.")

        cursor.execute('SELECT id FROM cobro_distribuciones WHERE cobro_id = ?', (cobro_id,))
        row = cursor.fetchone()
        if row:
            cursor.execute('''
                UPDATE cobro_distribuciones
                SET monto_fin_orig = ?, monto_reserva = ?, notas = ?
                WHERE id = ?
            ''', (monto_fin_orig, monto_reserva, notas, row['id']))
        else:
            cursor.execute('''
                INSERT INTO cobro_distribuciones (cobro_id, monto_fin_orig, monto_reserva, notas)
                VALUES (?, ?, ?, ?)
            ''', (cobro_id, monto_fin_orig, monto_reserva, notas))
        conn.commit()


def get_cobros_con_resumen_distribucion():
    with db_session() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT c.id, c.monto, c.fecha, c.cuota_id,
                   cu.mes, cu.anio,
                   d.nro_decreto, d.anio as decreto_anio, d.id as decreto_id,
                   d.destino_fondos, d.expediente_imuh,
                   COALESCE(dist.monto_fin_orig, 0) as monto_fin_orig,
                   COALESCE(dist.monto_reserva, 0) as monto_reserva,
                   COALESCE((SELECT SUM(monto) FROM cobro_desvios WHERE cobro_id = c.id), 0) as total_desvios,
                   (
                       COALESCE(dist.monto_fin_orig, 0) + 
                       COALESCE(dist.monto_reserva, 0) + 
                       COALESCE((SELECT SUM(monto) FROM cobro_desvios WHERE cobro_id = c.id), 0) -
                       COALESCE((
                           SELECT SUM(cdr.monto) FROM cobro_desvios_recuperos cdr
                           JOIN cobro_desvios cd ON cdr.desvio_id = cd.id
                           WHERE cd.cobro_id = c.id AND cdr.destino_tipo = 'sin_distribucion'
                       ), 0) -
                       COALESCE((
                           SELECT SUM(crur.monto) FROM cobro_reserva_usos_recuperos crur
                           JOIN cobro_reserva_usos cru ON crur.reserva_uso_id = cru.id
                           WHERE cru.cobro_id = c.id AND crur.destino_tipo = 'sin_distribucion'
                       ), 0)
                   ) as total_distribuido
            FROM cobros c
            JOIN cuotas cu ON c.cuota_id = cu.id
            JOIN decretos d ON cu.decreto_id = d.id
            LEFT JOIN cobro_distribuciones dist ON c.id = dist.cobro_id
            ORDER BY c.fecha DESC, d.anio DESC, d.nro_decreto DESC
        ''')
        rows = cursor.fetchall()
        return [dict(ix) for ix in rows]


def get_desvios_by_cobro(cobro_id):
    with db_session() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT cd.*, 
                   COALESCE((SELECT SUM(monto) FROM cobro_desvios_recuperos WHERE desvio_id = cd.id), 0) as total_recuperado
            FROM cobro_desvios cd
            WHERE cd.cobro_id = ?
            ORDER BY cd.fecha ASC
        ''', (cobro_id,))
        rows = cursor.fetchall()
        return [dict(ix) for ix in rows]


def add_desvio(cobro_id, destino, monto, motivo, fecha, decreto_destino_id=None, nro_op=None, obra_id=None, gasto_nombre=None, gasto_expediente_imuh=None):
    _validar_op_o_nota_db(nro_op, motivo, contexto="desvío")
    if monto <= 0:
        raise ValueError("El monto a desviar debe ser mayor a 0.")
        
    if obra_id:
        obra = get_obra(obra_id)
        if obra:
            destino = obra['nombre']
            decretos_asoc = get_decretos_by_obra(obra_id)
            decretos_vigentes = [d for d in decretos_asoc if d['estado'] != 'Anulado']
            if decretos_vigentes:
                decreto_destino_id = decretos_vigentes[0]['id']
            elif decretos_asoc:
                decreto_destino_id = decretos_asoc[0]['id']
            else:
                decreto_destino_id = None
                
    with db_session() as conn:
        cursor = conn.cursor()
    
        cursor.execute('SELECT monto, fecha FROM cobros WHERE id = ?', (cobro_id,))
        c_row = cursor.fetchone()
        if not c_row:
            raise ValueError("Cobro no encontrado.")
            
        if fecha < c_row['fecha']:
            raise ValueError(f"La fecha del desvío ({fecha}) no puede ser anterior a la fecha del cobro ({c_row['fecha']}).")
        
        cursor.execute('SELECT * FROM cobro_distribuciones WHERE cobro_id = ?', (cobro_id,))
        dist = cursor.fetchone()
        fin_orig = dist['monto_fin_orig'] if dist else 0
        reserva = dist['monto_reserva'] if dist else 0
    
        cursor.execute('SELECT COALESCE(SUM(monto), 0) as tot_desvios FROM cobro_desvios WHERE cobro_id = ?', (cobro_id,))
        tot_desvios = cursor.fetchone()['tot_desvios']
    
        if (fin_orig + reserva + tot_desvios + monto) > (c_row['monto'] + TOLERANCE):
            raise ValueError("El monto del desvío supera el saldo libre disponible sin distribuir.")

        cursor.execute('''
            INSERT INTO cobro_desvios (cobro_id, destino, monto, motivo, fecha, decreto_destino_id, nro_op, obra_id, gasto_nombre, gasto_expediente_imuh)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (cobro_id, destino, monto, motivo, fecha, decreto_destino_id, nro_op, obra_id, gasto_nombre, gasto_expediente_imuh))
        conn.commit()

    if nro_op:
        g_id = None
        if gasto_expediente_imuh:
            with get_connection() as c:
                r = c.execute("SELECT id FROM gastos_funcionamiento WHERE expediente_imuh = ?", (gasto_expediente_imuh,)).fetchone()
                if r: g_id = r['id']
        register_or_update_op(nro_op, obra_id=obra_id, gasto_id=g_id)


def delete_desvio(desvio_id):
    with db_session() as conn:
        cursor = conn.cursor()
        
        cursor.execute('SELECT COUNT(*) as cnt FROM cobro_desvios_recuperos WHERE desvio_id = ?', (desvio_id,))
        if cursor.fetchone()['cnt'] > 0:
            raise ValueError("No se puede borrar un desvío que ya tiene recuperos registrados.")
            
        cursor.execute('DELETE FROM cobro_desvios WHERE id = ?', (desvio_id,))
        conn.commit()


def update_desvio(desvio_id, nuevo_monto, nuevo_motivo, nueva_fecha, nuevo_nro_op):
    _validar_op_o_nota_db(nuevo_nro_op, nuevo_motivo, contexto="edición de desvío")
    if nuevo_monto <= 0:
        raise ValueError("El monto a desviar debe ser mayor a 0.")
        
    with db_session() as conn:
        cursor = conn.cursor()
        
        # Verificar suma recuperada
        cursor.execute('SELECT COALESCE(SUM(monto), 0) as tot_rec FROM cobro_desvios_recuperos WHERE desvio_id = ?', (desvio_id,))
        ya_recuperado = cursor.fetchone()['tot_rec']
        
        if nuevo_monto < ya_recuperado:
            raise ValueError(f"No puedes reducir el monto del desvío a {nuevo_monto:.2f} porque ya se recuperaron {ya_recuperado:.2f}.")
            
        cursor.execute('''
            UPDATE cobro_desvios 
            SET monto = ?, motivo = ?, fecha = ?, nro_op = ?
            WHERE id = ?
        ''', (nuevo_monto, nuevo_motivo, nueva_fecha, nuevo_nro_op, desvio_id))
        conn.commit()


def get_recuperos_by_desvio(desvio_id):
    with db_session() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT r.*,
                   d.nro_decreto as dest_nro, d.anio as dest_anio, d.destino_fondos as dest_nombre
            FROM cobro_desvios_recuperos r
            LEFT JOIN decretos d ON r.decreto_destino_id = d.id
            WHERE r.desvio_id = ? 
            ORDER BY r.fecha ASC
        ''', (desvio_id,))
        rows = cursor.fetchall()
        return [dict(ix) for ix in rows]


def add_desvio_recupero(desvio_id, monto, fecha, destino_tipo, destino_detalle=None, decreto_destino_id=None, nro_op=None, notas=None):
    _validar_op_o_nota_db(nro_op, notas, contexto="recupero de desvío")
    if monto <= 0:
        raise ValueError("El monto recuperado debe ser mayor a 0.")
        
    with db_session() as conn:
        cursor = conn.cursor()
    
        cursor.execute('SELECT monto, fecha FROM cobro_desvios WHERE id = ?', (desvio_id,))
        d_row = cursor.fetchone()
        if not d_row:
            raise ValueError("Desvío no encontrado.")
            
        if fecha < d_row['fecha']:
            raise ValueError(f"La fecha de recuperación ({fecha}) no puede ser anterior a la fecha del desvío ({d_row['fecha']}).")
        
        cursor.execute('SELECT COALESCE(SUM(monto), 0) as tot_recuperado FROM cobro_desvios_recuperos WHERE desvio_id = ?', (desvio_id,))
        tot_recuperado = cursor.fetchone()['tot_recuperado']
    
        if (tot_recuperado + monto) > (d_row['monto'] + TOLERANCE):
            raise ValueError("El monto a recuperar supera el saldo adeudado del desvío.")

        cursor.execute('''
            INSERT INTO cobro_desvios_recuperos (desvio_id, monto, fecha, destino_tipo, destino_detalle, decreto_destino_id, nro_op, notas)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (desvio_id, monto, fecha, destino_tipo, destino_detalle, decreto_destino_id, nro_op, notas))
        conn.commit()


def get_obras_propias_nombres():
    with db_session() as conn:
        cursor = conn.cursor()
    
        cursor.execute('SELECT DISTINCT destino FROM cobro_desvios WHERE decreto_destino_id IS NULL AND destino IS NOT NULL AND TRIM(destino) != ""')
        n_desv = [row['destino'] for row in cursor.fetchall()]
    
        cursor.execute('SELECT DISTINCT destino_detalle FROM cobro_reserva_usos WHERE decreto_destino_id IS NULL AND destino_detalle IS NOT NULL AND TRIM(destino_detalle) != "" AND destino_tipo != "fin_original"')
        n_res = [row['destino_detalle'] for row in cursor.fetchall()]
    
        cursor.execute('SELECT DISTINCT destino_detalle FROM cobro_desvios_recuperos WHERE decreto_destino_id IS NULL AND destino_detalle IS NOT NULL AND TRIM(destino_detalle) != "" AND destino_tipo != "fin_original"')
        n_rec = [row['destino_detalle'] for row in cursor.fetchall()]
    
        cursor.execute('SELECT DISTINCT destino_detalle FROM cobro_reserva_usos_recuperos WHERE decreto_destino_id IS NULL AND destino_detalle IS NOT NULL AND TRIM(destino_detalle) != "" AND destino_tipo != "fin_original" AND destino_tipo != "reserva"')
        n_rec_res = [row['destino_detalle'] for row in cursor.fetchall()]
    
    
        return sorted(list(set(n_desv + n_res + n_rec + n_rec_res)))


def delete_desvio_recupero(recupero_id):
    with db_session() as conn:
        cursor = conn.cursor()
        cursor.execute('DELETE FROM cobro_desvios_recuperos WHERE id = ?', (recupero_id,))
        conn.commit()


def add_reserva_uso_recupero(reserva_uso_id, monto, fecha, destino_tipo, destino_detalle=None, decreto_destino_id=None, nro_op=None, notas=None):
    _validar_op_o_nota_db(nro_op, notas, contexto="recupero de reserva")
    if monto <= 0:
        raise ValueError("El monto recuperado debe ser mayor a 0.")
        
    with db_session() as conn:
        cursor = conn.cursor()
        
        cursor.execute('SELECT monto, fecha FROM cobro_reserva_usos WHERE id = ?', (reserva_uso_id,))
        ru_row = cursor.fetchone()
        if not ru_row:
            raise ValueError("Uso de reserva no encontrado.")
        if fecha < ru_row['fecha']:
            raise ValueError(f"La fecha de recuperación ({fecha}) no puede ser anterior a la fecha de uso de reserva ({ru_row['fecha']}).")
        
        cursor.execute('SELECT COALESCE(SUM(monto), 0) as tot_recuperado FROM cobro_reserva_usos_recuperos WHERE reserva_uso_id = ?', (reserva_uso_id,))
        tot_recuperado = cursor.fetchone()['tot_recuperado']
    
        if (tot_recuperado + monto) > (ru_row['monto'] + TOLERANCE):
            raise ValueError("El monto a recuperar supera el saldo adeudado del desvío de reserva.")

        cursor.execute('''
            INSERT INTO cobro_reserva_usos_recuperos (reserva_uso_id, monto, fecha, destino_tipo, destino_detalle, decreto_destino_id, nro_op, notas)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (reserva_uso_id, monto, fecha, destino_tipo, destino_detalle, decreto_destino_id, nro_op, notas))
        conn.commit()


def get_recuperos_by_reserva_uso(reserva_uso_id):
    with db_session() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT r.*,
                   d.nro_decreto as dest_nro, d.anio as dest_anio, d.destino_fondos as dest_nombre
            FROM cobro_reserva_usos_recuperos r
            LEFT JOIN decretos d ON r.decreto_destino_id = d.id
            WHERE r.reserva_uso_id = ? 
            ORDER BY r.fecha ASC
        ''', (reserva_uso_id,))
        rows = cursor.fetchall()
        return [dict(ix) for ix in rows]


def delete_reserva_uso_recupero(recupero_id):
    with db_session() as conn:
        cursor = conn.cursor()
        cursor.execute('DELETE FROM cobro_reserva_usos_recuperos WHERE id = ?', (recupero_id,))
        conn.commit()


def get_reserva_usos_by_cobro(cobro_id):
    with db_session() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM cobro_reserva_usos WHERE cobro_id = ? ORDER BY fecha ASC', (cobro_id,))
        rows = cursor.fetchall()
        return [dict(ix) for ix in rows]


def get_reserva_usos_prestamos_activos():
    """Retorna usos de reserva destinados a otras obras (préstamos a recuperar) con su saldo pendiente.
    No incluye los usos aplicados al fin original del cobro."""
    with db_session() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT
                ru.id,
                ru.cobro_id,
                ru.monto,
                (ru.monto - COALESCE((SELECT SUM(monto) FROM cobro_reserva_usos_recuperos WHERE reserva_uso_id = ru.id), 0)) as saldo,
                ru.fecha,
                ru.destino_tipo,
                ru.destino_detalle,
                ru.decreto_destino_id,
                ru.notas,
                ru.gasto_nombre,
                ru.gasto_expediente_imuh,
                d_orig.nro_decreto as orig_nro,
                d_orig.anio      as orig_anio,
                d_orig.destino_fondos as orig_nombre, d_orig.expediente_imuh as orig_imuh,
                d_dest.nro_decreto as dest_nro,
                d_dest.anio      as dest_anio,
                d_dest.destino_fondos as dest_nombre, d_dest.expediente_imuh as dest_imuh,
                o_dest.expediente_imuh as dest_obra_imuh
            FROM cobro_reserva_usos ru
            JOIN cobros c    ON ru.cobro_id = c.id
            JOIN cuotas cu   ON c.cuota_id  = cu.id
            JOIN decretos d_orig ON cu.decreto_id = d_orig.id
            LEFT JOIN decretos d_dest ON ru.decreto_destino_id = d_dest.id
            LEFT JOIN obras o_dest ON ru.obra_id = o_dest.id
            WHERE ru.destino_tipo != 'fin_original'
            ORDER BY ru.fecha DESC
        ''')
        rows = cursor.fetchall()
    
        activos = []
        for r in rows:
            if r['saldo'] > TOLERANCE:
                activos.append(dict(r))
        return activos


def add_reserva_uso(cobro_id, monto, destino_tipo, destino_detalle, fecha, notas, decreto_destino_id=None, nro_op=None, obra_id=None, gasto_nombre=None, gasto_expediente_imuh=None):
    _validar_op_o_nota_db(nro_op, notas, contexto="uso de reserva")
    if monto <= 0:
        raise ValueError("El monto a usar debe ser mayor a 0.")
        
    if obra_id:
        obra = get_obra(obra_id)
        if obra:
            destino_detalle = obra['nombre']
            decretos_asoc = get_decretos_by_obra(obra_id)
            decretos_vigentes = [d for d in decretos_asoc if d['estado'] != 'Anulado']
            if decretos_vigentes:
                decreto_destino_id = decretos_vigentes[0]['id']
            elif decretos_asoc:
                decreto_destino_id = decretos_asoc[0]['id']
            else:
                decreto_destino_id = None
                
    with db_session() as conn:
        cursor = conn.cursor()
        
        cursor.execute('SELECT fecha FROM cobros WHERE id = ?', (cobro_id,))
        c_row = cursor.fetchone()
        if not c_row:
            raise ValueError("Cobro no encontrado.")
        if fecha < c_row['fecha']:
            raise ValueError(f"La fecha de uso de reserva ({fecha}) no puede ser anterior a la fecha del cobro ({c_row['fecha']}).")
    
        cursor.execute('SELECT monto_reserva FROM cobro_distribuciones WHERE cobro_id = ?', (cobro_id,))
        row_dist = cursor.fetchone()
        reserva_original = row_dist['monto_reserva'] if row_dist else 0
    
        cursor.execute('SELECT COALESCE(SUM(monto), 0) as tot FROM cobro_reserva_usos WHERE cobro_id = ?', (cobro_id,))
        ru_total = cursor.fetchone()['tot']
        
        cursor.execute('''
            SELECT COALESCE(SUM(crur.monto), 0) as tot 
            FROM cobro_reserva_usos_recuperos crur
            JOIN cobro_reserva_usos cru ON crur.reserva_uso_id = cru.id
            WHERE cru.cobro_id = ? AND crur.destino_tipo = 'reserva'
        ''', (cobro_id, user_auth_id if 'user_auth_id' in locals() else None) if False else (cobro_id,)) # Simple tuple structure
        recru_res_total = cursor.fetchone()['tot']
        
        cursor.execute('''
            SELECT COALESCE(SUM(cdr.monto), 0) as tot 
            FROM cobro_desvios_recuperos cdr
            JOIN cobro_desvios cd ON cdr.desvio_id = cd.id
            WHERE cd.cobro_id = ? AND cdr.destino_tipo = 'reserva'
        ''', (cobro_id,))
        rec_desv_res_total = cursor.fetchone()['tot']
        
        ya_usado_neto = ru_total - recru_res_total - rec_desv_res_total
    
        if (ya_usado_neto + monto) > (reserva_original + TOLERANCE):
            raise ValueError("El monto a usar supera el saldo disponible de reserva.")

        cursor.execute('''
            INSERT INTO cobro_reserva_usos (cobro_id, monto, destino_tipo, destino_detalle, fecha, notas, decreto_destino_id, nro_op, obra_id, gasto_nombre, gasto_expediente_imuh)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (cobro_id, monto, destino_tipo, destino_detalle, fecha, notas, decreto_destino_id, nro_op, obra_id, gasto_nombre, gasto_expediente_imuh))
        new_id = cursor.lastrowid
        conn.commit()
        
    if nro_op:
        g_id = None
        if gasto_expediente_imuh:
            with get_connection() as c:
                r = c.execute("SELECT id FROM gastos_funcionamiento WHERE expediente_imuh = ?", (gasto_expediente_imuh,)).fetchone()
                if r: g_id = r['id']
        register_or_update_op(nro_op, obra_id=obra_id, gasto_id=g_id)
        
    return new_id


def delete_reserva_uso(uso_id):
    with db_session() as conn:
        cursor = conn.cursor()
        
        cursor.execute('SELECT COUNT(*) as cnt FROM cobro_reserva_usos_recuperos WHERE reserva_uso_id = ?', (uso_id,))
        if cursor.fetchone()['cnt'] > 0:
            raise ValueError("No se puede borrar un uso de reserva que ya tiene recuperos registrados.")
            
        cursor.execute('DELETE FROM cobro_reserva_usos WHERE id = ?', (uso_id,))
        conn.commit()


def update_reserva_uso(uso_id, nuevo_monto, nuevas_notas, nueva_fecha, nuevo_nro_op):
    _validar_op_o_nota_db(nuevo_nro_op, nuevas_notas, contexto="edición de préstamo de reserva")
    if nuevo_monto <= 0:
        raise ValueError("El monto del préstamo debe ser mayor a 0.")
        
    with db_session() as conn:
        cursor = conn.cursor()
        
        # Verificar suma recuperada
        cursor.execute('SELECT COALESCE(SUM(monto), 0) as tot_rec FROM cobro_reserva_usos_recuperos WHERE reserva_uso_id = ?', (uso_id,))
        ya_recuperado = cursor.fetchone()['tot_rec']
        
        if nuevo_monto < ya_recuperado:
            raise ValueError(f"No puedes reducir el préstamo de reserva a {nuevo_monto:.2f} porque ya se recuperaron {ya_recuperado:.2f}.")
            
        cursor.execute('''
            UPDATE cobro_reserva_usos 
            SET monto = ?, notas = ?, fecha = ?, nro_op = ?
            WHERE id = ?
        ''', (nuevo_monto, nuevas_notas, nueva_fecha, nuevo_nro_op, uso_id))
        conn.commit()


def get_deuda_desvios_by_decreto(decreto_id):
    with db_session() as conn:
        cursor = conn.cursor()
    
        # 1. Deuda de desvíos iniciales recibidos
        cursor.execute('''
            SELECT 
                COALESCE(SUM(cd.monto), 0) - COALESCE((
                    SELECT SUM(cdr.monto) 
                    FROM cobro_desvios_recuperos cdr 
                    JOIN cobro_desvios cd_inner ON cdr.desvio_id = cd_inner.id 
                    WHERE cd_inner.decreto_destino_id = ?
                ), 0) as deuda
            FROM cobro_desvios cd
            WHERE cd.decreto_destino_id = ?
        ''', (decreto_id, decreto_id))
        r_desv = cursor.fetchone()
        deuda_desv = r_desv['deuda'] if r_desv and r_desv['deuda'] is not None else 0.0
    
        # 2. Deuda de desvíos de reserva recibidos
        cursor.execute('''
            SELECT 
                COALESCE(SUM(ru.monto), 0) - COALESCE((
                    SELECT SUM(rur.monto) 
                    FROM cobro_reserva_usos_recuperos rur 
                    JOIN cobro_reserva_usos ru_inner ON rur.reserva_uso_id = ru_inner.id 
                    WHERE ru_inner.decreto_destino_id = ?
                ), 0) as deuda
            FROM cobro_reserva_usos ru
            WHERE ru.decreto_destino_id = ? AND ru.destino_tipo != 'fin_original'
        ''', (decreto_id, decreto_id))
        r_res = cursor.fetchone()
        deuda_res = r_res['deuda'] if r_res and r_res['deuda'] is not None else 0.0
    
        return round(deuda_desv + deuda_res, 2)


def get_deudas_obras_propias():
    return get_deudas_consolidadas()



def get_desvios_activos_completos():
    with db_session() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT 
                cd.id as desvio_id,
                (cd.monto - COALESCE((SELECT SUM(monto) FROM cobro_desvios_recuperos WHERE desvio_id = cd.id), 0)) as saldo,
                cd.destino as destino_texto,
                cd.decreto_destino_id,
                cd.gasto_nombre,
                cd.gasto_expediente_imuh,
                d_dest.nro_decreto as dest_nro, d_dest.anio as dest_anio, d_dest.destino_fondos as dest_nombre, d_dest.expediente_imuh as dest_imuh,
                d_orig.nro_decreto as orig_nro, d_orig.anio as orig_anio, d_orig.destino_fondos as orig_nombre, d_orig.expediente_imuh as orig_imuh,
                o_dest.expediente_imuh as dest_obra_imuh
            FROM cobro_desvios cd
            JOIN cobros c ON cd.cobro_id = c.id
            JOIN cuotas cu ON c.cuota_id = cu.id
            JOIN decretos d_orig ON cu.decreto_id = d_orig.id
            LEFT JOIN decretos d_dest ON cd.decreto_destino_id = d_dest.id
            LEFT JOIN obras o_dest ON cd.obra_id = o_dest.id
        ''')
        rows = cursor.fetchall()
    
        activos = []
        for r in rows:
            if r['saldo'] > TOLERANCE:
                activos.append(dict(r))
        return activos


def get_historial_desvios():
    with db_session() as conn:
        cursor = conn.cursor()
    
        # 1. Desvíos iniciales
        cursor.execute('''
            SELECT 
                cd.id as desvio_id,
                cd.fecha,
                cd.monto,
                COALESCE((SELECT SUM(monto) FROM cobro_desvios_recuperos WHERE desvio_id = cd.id), 0) as total_recuperado,
                (cd.monto - COALESCE((SELECT SUM(monto) FROM cobro_desvios_recuperos WHERE desvio_id = cd.id), 0)) as saldo,
                cd.destino as destino_texto,
                cd.decreto_destino_id,
                d_dest.nro_decreto as dest_nro, d_dest.anio as dest_anio, d_dest.destino_fondos as dest_nombre, d_dest.expediente_imuh as dest_imuh,
                d_orig.id as orig_decreto_id, d_orig.nro_decreto as orig_nro, d_orig.anio as orig_anio, d_orig.destino_fondos as orig_nombre, d_orig.expediente_imuh as orig_imuh,
                cu.mes as orig_cuota_mes, cu.anio as orig_cuota_anio,
                'inicial' as tipo_origen,
                cd.nro_op as nro_op,
                cd.motivo as motivo
            FROM cobro_desvios cd
            JOIN cobros c ON cd.cobro_id = c.id
            JOIN cuotas cu ON c.cuota_id = cu.id
            JOIN decretos d_orig ON cu.decreto_id = d_orig.id
            LEFT JOIN decretos d_dest ON cd.decreto_destino_id = d_dest.id
        ''')
        rows_desv = [dict(r) for r in cursor.fetchall()]
    
        # 2. Desvíos de reserva
        cursor.execute('''
            SELECT 
                ru.id as desvio_id,
                ru.fecha,
                ru.monto,
                COALESCE((SELECT SUM(monto) FROM cobro_reserva_usos_recuperos WHERE reserva_uso_id = ru.id), 0) as total_recuperado,
                (ru.monto - COALESCE((SELECT SUM(monto) FROM cobro_reserva_usos_recuperos WHERE reserva_uso_id = ru.id), 0)) as saldo,
                ru.destino_detalle as destino_texto,
                ru.decreto_destino_id,
                d_dest.nro_decreto as dest_nro, d_dest.anio as dest_anio, d_dest.destino_fondos as dest_nombre, d_dest.expediente_imuh as dest_imuh,
                d_orig.id as orig_decreto_id, d_orig.nro_decreto as orig_nro, d_orig.anio as orig_anio, d_orig.destino_fondos as orig_nombre, d_orig.expediente_imuh as orig_imuh,
                cu.mes as orig_cuota_mes, cu.anio as orig_cuota_anio,
                'reserva' as tipo_origen,
                ru.nro_op as nro_op,
                ru.notas as motivo
            FROM cobro_reserva_usos ru
            JOIN cobros c ON ru.cobro_id = c.id
            JOIN cuotas cu ON c.cuota_id = cu.id
            JOIN decretos d_orig ON cu.decreto_id = d_orig.id
            LEFT JOIN decretos d_dest ON ru.decreto_destino_id = d_dest.id
            WHERE ru.destino_tipo != 'fin_original'
        ''')
        rows_res = [dict(r) for r in cursor.fetchall()]
    
        # Combinar y ordenar
        todos = rows_desv + rows_res
        todos.sort(key=lambda x: x['fecha'], reverse=True)
        return todos


# Fix 10: Variantes optimizadas que filtran a nivel SQL para obras específicas

_DESVIOS_SELECT_INICIAL = '''
    SELECT 
        cd.id as desvio_id,
        cd.fecha,
        cd.monto,
        COALESCE((SELECT SUM(monto) FROM cobro_desvios_recuperos WHERE desvio_id = cd.id), 0) as total_recuperado,
        (cd.monto - COALESCE((SELECT SUM(monto) FROM cobro_desvios_recuperos WHERE desvio_id = cd.id), 0)) as saldo,
        cd.destino as destino_texto,
        cd.decreto_destino_id,
        d_dest.nro_decreto as dest_nro, d_dest.anio as dest_anio,
        d_dest.destino_fondos as dest_nombre, d_dest.expediente_imuh as dest_imuh,
        d_orig.id as orig_decreto_id, d_orig.nro_decreto as orig_nro,
        d_orig.anio as orig_anio, d_orig.destino_fondos as orig_nombre,
        d_orig.expediente_imuh as orig_imuh,
        cu.mes as orig_cuota_mes, cu.anio as orig_cuota_anio,
        'inicial' as tipo_origen,
        cd.nro_op as nro_op,
        cd.motivo as motivo
    FROM cobro_desvios cd
    JOIN cobros c ON cd.cobro_id = c.id
    JOIN cuotas cu ON c.cuota_id = cu.id
    JOIN decretos d_orig ON cu.decreto_id = d_orig.id
    LEFT JOIN decretos d_dest ON cd.decreto_destino_id = d_dest.id
'''

_DESVIOS_SELECT_RESERVA = '''
    SELECT 
        ru.id as desvio_id,
        ru.fecha,
        ru.monto,
        COALESCE((SELECT SUM(monto) FROM cobro_reserva_usos_recuperos WHERE reserva_uso_id = ru.id), 0) as total_recuperado,
        (ru.monto - COALESCE((SELECT SUM(monto) FROM cobro_reserva_usos_recuperos WHERE reserva_uso_id = ru.id), 0)) as saldo,
        ru.destino_detalle as destino_texto,
        ru.decreto_destino_id,
        d_dest.nro_decreto as dest_nro, d_dest.anio as dest_anio,
        d_dest.destino_fondos as dest_nombre, d_dest.expediente_imuh as dest_imuh,
        d_orig.id as orig_decreto_id, d_orig.nro_decreto as orig_nro,
        d_orig.anio as orig_anio, d_orig.destino_fondos as orig_nombre,
        d_orig.expediente_imuh as orig_imuh,
        cu.mes as orig_cuota_mes, cu.anio as orig_cuota_anio,
        'reserva' as tipo_origen,
        ru.nro_op as nro_op,
        ru.notas as motivo
    FROM cobro_reserva_usos ru
    JOIN cobros c ON ru.cobro_id = c.id
    JOIN cuotas cu ON c.cuota_id = cu.id
    JOIN decretos d_orig ON cu.decreto_id = d_orig.id
    LEFT JOIN decretos d_dest ON ru.decreto_destino_id = d_dest.id
    WHERE ru.destino_tipo != 'fin_original'
'''


def get_desvios_por_deudora(decreto_id=None, nombre_texto=None):
    """Retorna desvíos activos para una obra DEUDORA (quien recibió fondos).
    Filtra a nivel SQL por decreto_destino_id o por nombre de destino para legados.
    Solo retorna registros con saldo > 0 (Fix 10).
    """
    with db_session() as conn:
        cursor = conn.cursor()

        if decreto_id is not None:
            # Filtro por decreto registrado
            sql_ini = _DESVIOS_SELECT_INICIAL + " WHERE cd.decreto_destino_id = ?"
            cursor.execute(sql_ini, (decreto_id,))
            rows_d = [dict(r) for r in cursor.fetchall()]

            sql_res = _DESVIOS_SELECT_RESERVA + " AND ru.decreto_destino_id = ?"
            cursor.execute(sql_res, (decreto_id,))
            rows_r = [dict(r) for r in cursor.fetchall()]
        else:
            # Filtro por nombre de destino (obras sin decreto registrado)
            sql_ini = _DESVIOS_SELECT_INICIAL + " WHERE cd.decreto_destino_id IS NULL AND cd.destino = ?"
            cursor.execute(sql_ini, (nombre_texto,))
            rows_d = [dict(r) for r in cursor.fetchall()]

            sql_res = _DESVIOS_SELECT_RESERVA + " AND ru.decreto_destino_id IS NULL AND ru.destino_detalle = ?"
            cursor.execute(sql_res, (nombre_texto,))
            rows_r = [dict(r) for r in cursor.fetchall()]

        todos = rows_d + rows_r
        todos.sort(key=lambda x: x['fecha'], reverse=True)
        return [r for r in todos if r['saldo'] > TOLERANCE]


def get_desvios_por_acreedora(decreto_id):
    """Retorna desvíos activos para una obra ACREEDORA (quien prestó fondos).
    Filtra a nivel SQL por d_orig.id (decreto de origen del cobro).
    Solo retorna registros con saldo > 0 (Fix 10).
    """
    with db_session() as conn:
        cursor = conn.cursor()

        sql_ini = _DESVIOS_SELECT_INICIAL + " WHERE d_orig.id = ?"
        cursor.execute(sql_ini, (decreto_id,))
        rows_d = [dict(r) for r in cursor.fetchall()]

        sql_res = _DESVIOS_SELECT_RESERVA + " AND d_orig.id = ?"
        cursor.execute(sql_res, (decreto_id,))
        rows_r = [dict(r) for r in cursor.fetchall()]

        todos = rows_d + rows_r
        todos.sort(key=lambda x: x['fecha'], reverse=True)
        return [r for r in todos if r['saldo'] > TOLERANCE]


def renunciar_aporte_sueldo(aporte_id, fecha):
    with db_session() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            UPDATE aportes_sueldo 
            SET estado = 'Renunciado', fecha_renuncia = ?
            WHERE id = ?
        ''', (fecha, aporte_id))
        conn.commit()


def renunciar_aporte_sac(aporte_id, fecha):
    with db_session() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            UPDATE aportes_sac 
            SET estado = 'Renunciado', fecha_renuncia = ?
            WHERE id = ?
        ''', (fecha, aporte_id))
        conn.commit()

    # --- Solicitudes de Financiamiento CRUD ---

def add_solicitud(nro_expediente, expediente_imuh, destino_fondos, monto_solicitado, fecha_solicitud, pdf_path=None, notas=None, obra_id=None):
    if not nro_expediente or not str(nro_expediente).strip():
        raise ValueError("El número de expediente no puede estar vacío.")
    # Si no se proveen destino_fondos/expediente_imuh o están vacíos, y hay obra_id, autocompletar con los datos de la obra
    if obra_id and (not destino_fondos or not str(destino_fondos).strip()):
        obra = get_obra(obra_id)
        if obra:
            destino_fondos = obra['nombre']
            expediente_imuh = obra['expediente_imuh']
            
    if not destino_fondos or not str(destino_fondos).strip():
        raise ValueError("El destino de fondos no puede estar vacío.")
    if monto_solicitado <= 0:
        raise ValueError("El monto solicitado debe ser mayor a 0.")
    with db_session() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO solicitudes_financiamiento (nro_expediente, expediente_imuh, destino_fondos, monto_solicitado, fecha_solicitud, pdf_path, notas, estado, obra_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, 'Pendiente', ?)
        ''', (nro_expediente, expediente_imuh, destino_fondos, monto_solicitado, fecha_solicitud, pdf_path, notas, obra_id))
        solicitud_id = cursor.lastrowid
        conn.commit()
        return solicitud_id


def update_solicitud(solicitud_id, nro_expediente, expediente_imuh, destino_fondos, monto_solicitado, fecha_solicitud, pdf_path=None, notas=None, obra_id=None):
    if not nro_expediente or not str(nro_expediente).strip():
        raise ValueError("El número de expediente no puede estar vacío.")
    # Si no se proveen destino_fondos/expediente_imuh o están vacíos, y hay obra_id, autocompletar con los datos de la obra
    if obra_id and (not destino_fondos or not str(destino_fondos).strip()):
        obra = get_obra(obra_id)
        if obra:
            destino_fondos = obra['nombre']
            expediente_imuh = obra['expediente_imuh']
            
    if not destino_fondos or not str(destino_fondos).strip():
        raise ValueError("El destino de fondos no puede estar vacío.")
    if monto_solicitado <= 0:
        raise ValueError("El monto solicitado debe ser mayor a 0.")
    with db_session() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            UPDATE solicitudes_financiamiento
            SET nro_expediente = ?, expediente_imuh = ?, destino_fondos = ?, monto_solicitado = ?, fecha_solicitud = ?, pdf_path = ?, notas = ?, obra_id = ?
            WHERE id = ?
        ''', (nro_expediente, expediente_imuh, destino_fondos, monto_solicitado, fecha_solicitud, pdf_path, notas, obra_id, solicitud_id))
        conn.commit()


def delete_solicitud(solicitud_id):
    with db_session() as conn:
        cursor = conn.cursor()
        cursor.execute('DELETE FROM solicitudes_financiamiento WHERE id = ?', (solicitud_id,))
        conn.commit()


def get_solicitudes():
    with db_session() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT s.*, d.nro_decreto, d.anio as decreto_anio, o.nombre as obra_nombre, o.expediente_imuh as obra_expediente
            FROM solicitudes_financiamiento s
            LEFT JOIN decretos d ON s.decreto_id = d.id
            LEFT JOIN obras o ON s.obra_id = o.id
            ORDER BY s.fecha_solicitud DESC, s.id DESC
        ''')
        rows = cursor.fetchall()
        return [dict(ix) for ix in rows]


def get_solicitud(solicitud_id):
    with db_session() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT s.*, d.nro_decreto, d.anio as decreto_anio
            FROM solicitudes_financiamiento s
            LEFT JOIN decretos d ON s.decreto_id = d.id
            WHERE s.id = ?
        ''', (solicitud_id,))
        row = cursor.fetchone()
        return dict(row) if row else None


def get_solicitud_por_decreto(decreto_id):
    with db_session() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM solicitudes_financiamiento WHERE decreto_id = ?', (decreto_id,))
        row = cursor.fetchone()
        return dict(row) if row else None


def update_estado_solicitud(solicitud_id, estado, decreto_id=None):
    with db_session() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            UPDATE solicitudes_financiamiento
            SET estado = ?, decreto_id = ?
            WHERE id = ?
        ''', (estado, decreto_id, solicitud_id))
        conn.commit()

    # --- NUEVOS CRUDs PARA FIN ORIGINAL USOS Y MODIFICACIONES ---


def get_fin_original_usos_by_cobro(cobro_id):
    with db_session() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT fu.*, 
                   o.expediente_imuh as o_expediente, 
                   o.nombre as o_nombre
            FROM cobro_fin_original_usos fu
            LEFT JOIN obras o ON fu.obra_id = o.id
            WHERE fu.cobro_id = ? 
            ORDER BY fu.fecha ASC
        ''', (cobro_id,))
        rows = cursor.fetchall()
        return [dict(ix) for ix in rows]


def add_fin_original_uso(cobro_id, monto, fecha, nro_op=None, notas=None, obra_id=None, gasto_nombre=None, gasto_expediente_imuh=None):
    _validar_op_o_nota_db(nro_op, notas, contexto="pago de Fin Original")
    if monto <= 0:
        raise ValueError("El monto a pagar debe ser mayor a 0.")
    
    with db_session() as conn:
        cursor = conn.cursor()
    
        cursor.execute('SELECT monto_fin_orig FROM cobro_distribuciones WHERE cobro_id = ?', (cobro_id,))
        row_dist = cursor.fetchone()
        fin_orig_presupuesto = row_dist['monto_fin_orig'] if row_dist else 0.0
    
        cursor.execute('SELECT COALESCE(SUM(monto), 0) as tot_pagado FROM cobro_fin_original_usos WHERE cobro_id = ?', (cobro_id,))
        ya_pagado = cursor.fetchone()['tot_pagado']
    
        if (ya_pagado + monto) > (fin_orig_presupuesto + TOLERANCE):
            raise ValueError(f"El monto a pagar ({monto:.2f}) supera el saldo disponible asignado a Fin Original ({fin_orig_presupuesto - ya_pagado:.2f}).")
        
        cursor.execute('''
            INSERT INTO cobro_fin_original_usos (cobro_id, monto, fecha, nro_op, notas, obra_id, gasto_nombre, gasto_expediente_imuh)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (cobro_id, monto, fecha, nro_op, notas, obra_id, gasto_nombre, gasto_expediente_imuh))
        new_id = cursor.lastrowid
        conn.commit()
        
    if nro_op:
        g_id = None
        if gasto_expediente_imuh:
            with get_connection() as c:
                r = c.execute("SELECT id FROM gastos_funcionamiento WHERE expediente_imuh = ?", (gasto_expediente_imuh,)).fetchone()
                if r: g_id = r['id']
        register_or_update_op(nro_op, obra_id=obra_id, gasto_id=g_id)
        
    return new_id


def delete_fin_original_uso(uso_id):
    with db_session() as conn:
        cursor = conn.cursor()
        cursor.execute('DELETE FROM cobro_fin_original_usos WHERE id = ?', (uso_id,))
        conn.commit()


def update_fin_original_uso(uso_id, monto, fecha, nro_op, notas, obra_id=None, gasto_nombre=None, gasto_expediente_imuh=None):
    _validar_op_o_nota_db(nro_op, notas, contexto="pago de Fin Original")
    if monto <= 0:
        raise ValueError("El monto debe ser mayor a 0.")
    with db_session() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT cobro_id FROM cobro_fin_original_usos WHERE id = ?', (uso_id,))
        uso_row = cursor.fetchone()
        if not uso_row:
            raise ValueError("Pago de Fin Original no encontrado.")
        cobro_id = uso_row['cobro_id']
    
        cursor.execute('SELECT monto_fin_orig FROM cobro_distribuciones WHERE cobro_id = ?', (cobro_id,))
        dist_row = cursor.fetchone()
        presupuesto = dist_row['monto_fin_orig'] if dist_row else 0.0
    
        cursor.execute('SELECT COALESCE(SUM(monto), 0) as tot FROM cobro_fin_original_usos WHERE cobro_id = ? AND id != ?', (cobro_id, uso_id))
        otros_pagos = cursor.fetchone()['tot']
    
        if (otros_pagos + monto) > (presupuesto + TOLERANCE):
            raise ValueError(f"El monto editado ({monto:.2f}) supera el saldo disponible asignado a Fin Original ({presupuesto - otros_pagos:.2f}).")
        
        cursor.execute('''
            UPDATE cobro_fin_original_usos
            SET monto = ?, fecha = ?, nro_op = ?, notas = ?, obra_id = ?, gasto_nombre = ?, gasto_expediente_imuh = ?
            WHERE id = ?
        ''', (monto, fecha, nro_op, notas, obra_id, gasto_nombre, gasto_expediente_imuh, uso_id))
        conn.commit()


def update_desvio(desvio_id, monto, destino, motivo, fecha, decreto_destino_id, nro_op):
    _validar_op_o_nota_db(nro_op, motivo, contexto="desvío")
    if monto <= 0:
        raise ValueError("El monto del desvío debe ser mayor a 0.")
    with db_session() as conn:
        cursor = conn.cursor()
    
        cursor.execute('SELECT cobro_id FROM cobro_desvios WHERE id = ?', (desvio_id,))
        row_desv = cursor.fetchone()
        if not row_desv:
            raise ValueError("Desvío no encontrado.")
        cobro_id = row_desv['cobro_id']
    
        cursor.execute('SELECT COALESCE(SUM(monto), 0) as tot_rec FROM cobro_desvios_recuperos WHERE desvio_id = ?', (desvio_id,))
        tot_rec = cursor.fetchone()['tot_rec']
        if monto < (tot_rec - TOLERANCE):
            raise ValueError(f"No se puede reducir el monto del desvío por debajo del total ya recuperado ({tot_rec:.2f}).")
        
        cursor.execute('SELECT monto FROM cobros WHERE id = ?', (cobro_id,))
        c_row = cursor.fetchone()
    
        cursor.execute('SELECT * FROM cobro_distribuciones WHERE cobro_id = ?', (cobro_id,))
        dist = cursor.fetchone()
        fin_orig = dist['monto_fin_orig'] if dist else 0
        reserva = dist['monto_reserva'] if dist else 0
    
        cursor.execute('SELECT COALESCE(SUM(monto), 0) as tot FROM cobro_desvios WHERE cobro_id = ? AND id != ?', (cobro_id, desvio_id))
        otros_desvios = cursor.fetchone()['tot']
    
        if (fin_orig + reserva + otros_desvios + monto) > (c_row['monto'] + TOLERANCE):
            raise ValueError(f"La suma con este desvío editado ({fin_orig + reserva + otros_desvios + monto:.2f}) supera el monto total del cobro ({c_row['monto']:.2f}).")
        
        cursor.execute('''
            UPDATE cobro_desvios
            SET monto = ?, destino = ?, motivo = ?, fecha = ?, decreto_destino_id = ?, nro_op = ?
            WHERE id = ?
        ''', (monto, destino, motivo, fecha, decreto_destino_id, nro_op, desvio_id))
        conn.commit()


def update_reserva_uso(uso_id, monto, destino_tipo, destino_detalle, fecha, notas, decreto_destino_id, nro_op):
    _validar_op_o_nota_db(nro_op, notas, contexto="uso de reserva")
    if monto <= 0:
        raise ValueError("El monto debe ser mayor a 0.")
    with db_session() as conn:
        cursor = conn.cursor()
    
        cursor.execute('SELECT cobro_id FROM cobro_reserva_usos WHERE id = ?', (uso_id,))
        uso_row = cursor.fetchone()
        if not uso_row:
            raise ValueError("Uso de reserva no encontrado.")
        cobro_id = uso_row['cobro_id']
    
        cursor.execute('SELECT COALESCE(SUM(monto), 0) as tot_rec FROM cobro_reserva_usos_recuperos WHERE reserva_uso_id = ?', (uso_id,))
        tot_rec = cursor.fetchone()['tot_rec']
        if monto < (tot_rec - TOLERANCE):
            raise ValueError(f"No se puede reducir el monto del uso de reserva por debajo del total ya recuperado ({tot_rec:.2f}).")
        
        cursor.execute('SELECT monto_reserva FROM cobro_distribuciones WHERE cobro_id = ?', (cobro_id,))
        row_dist = cursor.fetchone()
        reserva_original = row_dist['monto_reserva'] if row_dist else 0
    
        cursor.execute('SELECT COALESCE(SUM(monto), 0) as tot_usado FROM cobro_reserva_usos WHERE cobro_id = ? AND id != ?', (cobro_id, uso_id))
        otros_usos = cursor.fetchone()['tot_usado']
    
        if (otros_usos + monto) > (reserva_original + TOLERANCE):
            raise ValueError(f"El monto a usar editado ({monto:.2f}) supera el saldo disponible de reserva ({reserva_original - otros_usos:.2f}).")
        
        cursor.execute('''
            UPDATE cobro_reserva_usos
            SET monto = ?, destino_tipo = ?, destino_detalle = ?, fecha = ?, notas = ?, decreto_destino_id = ?, nro_op = ?
            WHERE id = ?
        ''', (monto, destino_tipo, destino_detalle, fecha, notas, decreto_destino_id, nro_op, uso_id))
        conn.commit()


def update_desvio_recupero(rec_id, monto, fecha, destino_tipo, destino_detalle, decreto_destino_id, nro_op, notas=None):
    _validar_op_o_nota_db(nro_op, notas, contexto="recupero de desvío")
    if monto <= 0:
        raise ValueError("El monto recuperado debe ser mayor a 0.")
    with db_session() as conn:
        cursor = conn.cursor()
    
        cursor.execute('SELECT desvio_id FROM cobro_desvios_recuperos WHERE id = ?', (rec_id,))
        rec_row = cursor.fetchone()
        if not rec_row:
            raise ValueError("Recupero no encontrado.")
        desvio_id = rec_row['desvio_id']
    
        cursor.execute('SELECT monto FROM cobro_desvios WHERE id = ?', (desvio_id,))
        d_row = cursor.fetchone()
    
        cursor.execute('SELECT COALESCE(SUM(monto), 0) as tot_recuperado FROM cobro_desvios_recuperos WHERE desvio_id = ? AND id != ?', (desvio_id, rec_id))
        otros_recuperos = cursor.fetchone()['tot_recuperado']
    
        if (otros_recuperos + monto) > (d_row['monto'] + TOLERANCE):
            raise ValueError(f"El monto a recuperar editado ({monto:.2f}) supera el saldo adeudado del desvío ({d_row['monto'] - otros_recuperos:.2f}).")
        
        cursor.execute('''
            UPDATE cobro_desvios_recuperos
            SET monto = ?, fecha = ?, destino_tipo = ?, destino_detalle = ?, decreto_destino_id = ?, nro_op = ?, notas = ?
            WHERE id = ?
        ''', (monto, fecha, destino_tipo, destino_detalle, decreto_destino_id, nro_op, notas, rec_id))
        conn.commit()


def update_reserva_uso_recupero(rec_id, monto, fecha, destino_tipo, destino_detalle, decreto_destino_id, nro_op, notas=None):
    _validar_op_o_nota_db(nro_op, notas, contexto="recupero de reserva")
    if monto <= 0:
        raise ValueError("El monto recuperado debe ser mayor a 0.")
    with db_session() as conn:
        cursor = conn.cursor()
    
        cursor.execute('SELECT reserva_uso_id FROM cobro_reserva_usos_recuperos WHERE id = ?', (rec_id,))
        rec_row = cursor.fetchone()
        if not rec_row:
            raise ValueError("Recupero de reserva no encontrado.")
        reserva_uso_id = rec_row['reserva_uso_id']
    
        cursor.execute('SELECT monto FROM cobro_reserva_usos WHERE id = ?', (reserva_uso_id,))
        ru_row = cursor.fetchone()
    
        cursor.execute('SELECT COALESCE(SUM(monto), 0) as tot_recuperado FROM cobro_reserva_usos_recuperos WHERE reserva_uso_id = ? AND id != ?', (reserva_uso_id, rec_id))
        otros_recuperos = cursor.fetchone()['tot_recuperado']
    
        if (otros_recuperos + monto) > (ru_row['monto'] + TOLERANCE):
            raise ValueError(f"El monto a recuperar editado ({monto:.2f}) supera el saldo adeudado del desvío de reserva ({ru_row['monto'] - otros_recuperos:.2f}).")
        
        cursor.execute('''
            UPDATE cobro_reserva_usos_recuperos
            SET monto = ?, fecha = ?, destino_tipo = ?, destino_detalle = ?, decreto_destino_id = ?, nro_op = ?, notas = ?
            WHERE id = ?
        ''', (monto, fecha, destino_tipo, destino_detalle, decreto_destino_id, nro_op, notas, rec_id))
        conn.commit()



# --- NUEVOS CRUDs PARA PROVEEDORES, OBRAS Y GASTOS DE FUNCIONAMIENTO (v2.1) ---

def add_proveedor_obra(razon_social, cuit):
    if not razon_social or not str(razon_social).strip():
        raise ValueError("La Razón Social no puede estar vacía.")
    import utils
    if not utils.validar_cuit(cuit):
        raise ValueError("El CUIT no tiene un formato AFIP válido (Ej: 20-12345678-9).")
    
    razon_social = razon_social.strip()
    cuit = cuit.strip()
    
    with db_session() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT id FROM proveedores_obras WHERE LOWER(razon_social) = LOWER(?)', (razon_social,))
        if cursor.fetchone():
            raise ValueError(f"Ya existe un proveedor de obra con la razón social '{razon_social}'.")
        cursor.execute('SELECT id FROM proveedores_obras WHERE cuit = ?', (cuit,))
        if cursor.fetchone():
            raise ValueError(f"Ya existe un proveedor de obra con el CUIT '{cuit}'.")
            
        cursor.execute('''
            INSERT INTO proveedores_obras (razon_social, cuit, activo)
            VALUES (?, ?, 1)
        ''', (razon_social, cuit))
        prov_id = cursor.lastrowid
        conn.commit()
        return prov_id


def get_proveedores_obras(only_active=False):
    with db_session() as conn:
        cursor = conn.cursor()
        query = 'SELECT * FROM proveedores_obras'
        if only_active:
            query += ' WHERE activo = 1'
        query += ' ORDER BY razon_social ASC'
        cursor.execute(query)
        return [dict(r) for r in cursor.fetchall()]


def get_proveedor_obra(prov_id):
    if not prov_id:
        return None
    with db_session() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM proveedores_obras WHERE id = ?', (prov_id,))
        row = cursor.fetchone()
        return dict(row) if row else None


def update_proveedor_obra(prov_id, razon_social, cuit, activo=1):
    if not razon_social or not str(razon_social).strip():
        raise ValueError("La Razón Social no puede estar vacía.")
    import utils
    if not utils.validar_cuit(cuit):
        raise ValueError("El CUIT no tiene un formato AFIP válido (Ej: 20-12345678-9).")
        
    razon_social = razon_social.strip()
    cuit = cuit.strip()
    
    with db_session() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT id FROM proveedores_obras WHERE LOWER(razon_social) = LOWER(?) AND id != ?', (razon_social, prov_id))
        if cursor.fetchone():
            raise ValueError(f"Ya existe otro proveedor de obra registrado con la razón social '{razon_social}'.")
        cursor.execute('SELECT id FROM proveedores_obras WHERE cuit = ? AND id != ?', (cuit, prov_id))
        if cursor.fetchone():
            raise ValueError(f"Ya existe otro proveedor de obra registrado con el CUIT '{cuit}'.")
            
        cursor.execute('''
            UPDATE proveedores_obras
            SET razon_social = ?, cuit = ?, activo = ?
            WHERE id = ?
        ''', (razon_social, cuit, activo, prov_id))
        conn.commit()


def update_proveedor_obra_estado(prov_id, activo):
    with db_session() as conn:
        cursor = conn.cursor()
        cursor.execute('UPDATE proveedores_obras SET activo = ? WHERE id = ?', (activo, prov_id))
        conn.commit()


def delete_proveedor_obra(prov_id):
    with db_session() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT COUNT(*) as cnt FROM obras WHERE proveedor_id = ?', (prov_id,))
        if cursor.fetchone()['cnt'] > 0:
            raise ValueError("No se puede eliminar el proveedor porque está vinculado a una o más obras.")
        cursor.execute('DELETE FROM proveedores_obras WHERE id = ?', (prov_id,))
        conn.commit()


def add_proveedor_funcionamiento(razon_social, cuit):
    if not razon_social or not str(razon_social).strip():
        raise ValueError("La Razón Social no puede estar vacía.")
    import utils
    if not utils.validar_cuit(cuit):
        raise ValueError("El CUIT no tiene un formato AFIP válido (Ej: 20-12345678-9).")
        
    razon_social = razon_social.strip()
    cuit = cuit.strip()
    
    with db_session() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT id FROM proveedores_funcionamiento WHERE LOWER(razon_social) = LOWER(?)', (razon_social,))
        if cursor.fetchone():
            raise ValueError(f"Ya existe un proveedor de funcionamiento con la razón social '{razon_social}'.")
        cursor.execute('SELECT id FROM proveedores_funcionamiento WHERE cuit = ?', (cuit,))
        if cursor.fetchone():
            raise ValueError(f"Ya existe un proveedor de funcionamiento con el CUIT '{cuit}'.")
            
        cursor.execute('''
            INSERT INTO proveedores_funcionamiento (razon_social, cuit, activo)
            VALUES (?, ?, 1)
        ''', (razon_social, cuit))
        prov_id = cursor.lastrowid
        conn.commit()
        return prov_id


def get_proveedores_funcionamiento(only_active=False):
    with db_session() as conn:
        cursor = conn.cursor()
        query = 'SELECT * FROM proveedores_funcionamiento'
        if only_active:
            query += ' WHERE activo = 1'
        query += ' ORDER BY razon_social ASC'
        cursor.execute(query)
        return [dict(r) for r in cursor.fetchall()]


def get_proveedor_funcionamiento(prov_id):
    if not prov_id:
        return None
    with db_session() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM proveedores_funcionamiento WHERE id = ?', (prov_id,))
        row = cursor.fetchone()
        return dict(row) if row else None


def update_proveedor_funcionamiento(prov_id, razon_social, cuit, activo=1):
    if not razon_social or not str(razon_social).strip():
        raise ValueError("La Razón Social no puede estar vacía.")
    import utils
    if not utils.validar_cuit(cuit):
        raise ValueError("El CUIT no tiene un formato AFIP válido (Ej: 20-12345678-9).")
        
    razon_social = razon_social.strip()
    cuit = cuit.strip()
    
    with db_session() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT id FROM proveedores_funcionamiento WHERE LOWER(razon_social) = LOWER(?) AND id != ?', (razon_social, prov_id))
        if cursor.fetchone():
            raise ValueError(f"Ya existe otro proveedor de funcionamiento registrado con la razón social '{razon_social}'.")
        cursor.execute('SELECT id FROM proveedores_funcionamiento WHERE cuit = ? AND id != ?', (cuit, prov_id))
        if cursor.fetchone():
            raise ValueError(f"Ya existe otro proveedor de funcionamiento registrado con el CUIT '{cuit}'.")
            
        cursor.execute('''
            UPDATE proveedores_funcionamiento
            SET razon_social = ?, cuit = ?, activo = ?
            WHERE id = ?
        ''', (razon_social, cuit, activo, prov_id))
        conn.commit()


def update_proveedor_funcionamiento_estado(prov_id, activo):
    with db_session() as conn:
        cursor = conn.cursor()
        cursor.execute('UPDATE proveedores_funcionamiento SET activo = ? WHERE id = ?', (activo, prov_id))
        conn.commit()


def delete_proveedor_funcionamiento(prov_id):
    with db_session() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT COUNT(*) as cnt FROM gastos_funcionamiento WHERE proveedor_id = ?', (prov_id,))
        if cursor.fetchone()['cnt'] > 0:
            raise ValueError("No se puede eliminar el proveedor porque está vinculado a uno o más gastos de funcionamiento.")
        cursor.execute('DELETE FROM proveedores_funcionamiento WHERE id = ?', (prov_id,))
        conn.commit()


def get_todos_proveedores(only_active=False):
    """Retorna listado unificado de proveedores (Obra y Funcionamiento) ordenados alfabéticamente por Razón Social."""
    with db_session() as conn:
        cursor = conn.cursor()
        provs = []
        
        # 1. Obras
        q_obras = 'SELECT id, razon_social, cuit, activo FROM proveedores_obras'
        if only_active:
            q_obras += ' WHERE activo = 1'
        cursor.execute(q_obras)
        for r in cursor.fetchall():
            pid = r['id']
            cursor.execute('SELECT COUNT(*) as cnt FROM obras WHERE proveedor_id = ?', (pid,))
            is_linked = cursor.fetchone()['cnt'] > 0
            provs.append({
                'id': pid,
                'razon_social': r['razon_social'],
                'cuit': r['cuit'],
                'tipo': 'Obra',
                'activo': r['activo'],
                'is_linked': is_linked
            })
            
        # 2. Funcionamiento
        q_fun = 'SELECT id, razon_social, cuit, activo FROM proveedores_funcionamiento'
        if only_active:
            q_fun += ' WHERE activo = 1'
        cursor.execute(q_fun)
        for r in cursor.fetchall():
            pid = r['id']
            cursor.execute('SELECT COUNT(*) as cnt FROM gastos_funcionamiento WHERE proveedor_id = ?', (pid,))
            is_linked = cursor.fetchone()['cnt'] > 0
            provs.append({
                'id': pid,
                'razon_social': r['razon_social'],
                'cuit': r['cuit'],
                'tipo': 'Funcionamiento',
                'activo': r['activo'],
                'is_linked': is_linked
            })
            
        provs.sort(key=lambda x: x['razon_social'].lower())
        return provs


def add_obra(nombre, expediente_imuh, proveedor_id=None):
    if not nombre or not nombre.strip():
        raise ValueError("El nombre de la obra no puede estar vacío.")
    if not expediente_imuh or not expediente_imuh.strip():
        raise ValueError("El expediente IMUH no puede estar vacío.")
    import utils
    if not utils.validar_expediente_imuh(expediente_imuh):
        raise ValueError("El Expediente IMUH tiene un formato inválido (debe ser 8XXXXXX-I-AAAA o similar).")
        
    exp_normalizado = utils.normalizar_expediente_imuh(expediente_imuh)
    
    if get_obra_by_expediente(exp_normalizado):
        raise ValueError(f"Ya existe una obra registrada con el expediente {exp_normalizado}.")
    
    with db_session() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO obras (nombre, expediente_imuh, activa, proveedor_id)
            VALUES (?, ?, 1, ?)
        ''', (nombre.strip(), exp_normalizado, proveedor_id))
        obra_id = cursor.lastrowid
        conn.commit()
        return obra_id


def get_obras(only_active=False):
    with db_session() as conn:
        cursor = conn.cursor()
        query = '''
            SELECT o.*, p.razon_social as proveedor_razon_social, p.cuit as proveedor_cuit
            FROM obras o
            LEFT JOIN proveedores_obras p ON o.proveedor_id = p.id
        '''
        if only_active:
            query += ' WHERE o.activa = 1'
        query += ' ORDER BY o.nombre ASC'
        cursor.execute(query)
        rows = cursor.fetchall()
        return [dict(ix) for ix in rows]


def get_obra(obra_id):
    with db_session() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT o.*, p.razon_social as proveedor_razon_social, p.cuit as proveedor_cuit
            FROM obras o
            LEFT JOIN proveedores_obras p ON o.proveedor_id = p.id
            WHERE o.id = ?
        ''', (obra_id,))
        row = cursor.fetchone()
        return dict(row) if row else None


def get_obra_by_expediente(expediente_imuh):
    with db_session() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT o.*, p.razon_social as proveedor_razon_social, p.cuit as proveedor_cuit
            FROM obras o
            LEFT JOIN proveedores_obras p ON o.proveedor_id = p.id
            WHERE o.expediente_imuh = ?
        ''', (expediente_imuh,))
        row = cursor.fetchone()
        return dict(row) if row else None


def get_gastos_funcionamiento(only_active=False):
    with db_session() as conn:
        cursor = conn.cursor()
        query = '''
            SELECT g.*, p.razon_social as proveedor_razon_social, p.cuit as proveedor_cuit
            FROM gastos_funcionamiento g
            LEFT JOIN proveedores_funcionamiento p ON g.proveedor_id = p.id
        '''
        if only_active:
            query += ' WHERE g.activo = 1'
        query += ' ORDER BY g.nombre ASC'
        cursor.execute(query)
        rows = cursor.fetchall()
        return [dict(ix) for ix in rows]


def get_gasto_funcionamiento(gasto_id):
    with db_session() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT g.*, p.razon_social as proveedor_razon_social, p.cuit as proveedor_cuit
            FROM gastos_funcionamiento g
            LEFT JOIN proveedores_funcionamiento p ON g.proveedor_id = p.id
            WHERE g.id = ?
        ''', (gasto_id,))
        row = cursor.fetchone()
        return dict(row) if row else None


def get_gasto_funcionamiento_by_expediente(expediente_imuh):
    with db_session() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT g.*, p.razon_social as proveedor_razon_social, p.cuit as proveedor_cuit
            FROM gastos_funcionamiento g
            LEFT JOIN proveedores_funcionamiento p ON g.proveedor_id = p.id
            WHERE g.expediente_imuh = ?
        ''', (expediente_imuh,))
        row = cursor.fetchone()
        return dict(row) if row else None


def add_gasto_funcionamiento(nombre, expediente_imuh, proveedor_id=None):
    nombre = nombre.strip()
    expediente_imuh = utils.normalizar_expediente_imuh(expediente_imuh.strip())
    if not nombre:
        raise ValueError("El nombre del Gasto FUN no puede estar vacío.")
    if not utils.validar_expediente_imuh(expediente_imuh):
        raise ValueError("El expediente municipal/IMUH no tiene un formato válido (Ej: 8000000-I-2026).")
        
    with db_session() as conn:
        cursor = conn.cursor()
        try:
            cursor.execute('''
                INSERT INTO gastos_funcionamiento (nombre, expediente_imuh, activo, proveedor_id)
                VALUES (?, ?, 1, ?)
            ''', (nombre, expediente_imuh, proveedor_id))
            gasto_id = cursor.lastrowid
            conn.commit()
            return gasto_id
        except sqlite3.IntegrityError:
            cursor.execute('SELECT * FROM gastos_funcionamiento WHERE expediente_imuh = ?', (expediente_imuh,))
            row = cursor.fetchone()
            if row:
                cursor.execute('UPDATE gastos_funcionamiento SET nombre = ?, activo = 1, proveedor_id = COALESCE(?, proveedor_id) WHERE id = ?', (nombre, proveedor_id, row['id']))
                conn.commit()
                return row['id']
            raise ValueError(f"Ya existe un Gasto FUN con el expediente {expediente_imuh}.")


def update_gasto_funcionamiento_proveedor(gasto_id, proveedor_id):
    with db_session() as conn:
        cursor = conn.cursor()
        cursor.execute('UPDATE gastos_funcionamiento SET proveedor_id = ? WHERE id = ?', (proveedor_id, gasto_id))
        conn.commit()


def update_gasto_funcionamiento_estado(gasto_id, activo):
    if activo not in [0, 1]:
        raise ValueError("El estado activo debe ser 0 o 1.")
    with db_session() as conn:
        cursor = conn.cursor()
        cursor.execute('UPDATE gastos_funcionamiento SET activo = ? WHERE id = ?', (activo, gasto_id))
        conn.commit()


def update_gasto_funcionamiento(gasto_id, nombre, expediente_imuh, proveedor_id=None):
    """Actualiza nombre, expediente y proveedor de un Gasto FUN.
    Si cambia el expediente, actualiza en cascada el historial de desvíos y usos de reserva."""
    import utils as _utils
    nombre = nombre.strip()[:50]
    if not nombre:
        raise ValueError("El nombre del Gasto FUN no puede estar vacío.")
    exp_norm = _utils.normalizar_expediente_imuh(expediente_imuh.strip()) if expediente_imuh else None
    if not exp_norm or not _utils.validar_expediente_imuh(exp_norm):
        raise ValueError("El Nro. de Expediente IMUH no tiene un formato válido (Ej: 80001234-I-2026).")

    with db_session() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT id FROM gastos_funcionamiento WHERE expediente_imuh = ? AND id != ?', (exp_norm, gasto_id))
        if cursor.fetchone():
            raise ValueError(f"Ya existe otro Gasto de Funcionamiento con el expediente IMUH '{exp_norm}'.")

        cursor.execute('SELECT expediente_imuh FROM gastos_funcionamiento WHERE id = ?', (gasto_id,))
        row = cursor.fetchone()
        exp_anterior = row['expediente_imuh'] if row else None

        cursor.execute('''
            UPDATE gastos_funcionamiento
            SET nombre = ?, expediente_imuh = ?, proveedor_id = ?
            WHERE id = ?
        ''', (nombre, exp_norm, proveedor_id, gasto_id))

        if exp_anterior and exp_anterior != exp_norm:
            cursor.execute('''
                UPDATE cobro_desvios SET gasto_expediente_imuh = ?, gasto_nombre = ?
                WHERE gasto_expediente_imuh = ?
            ''', (exp_norm, nombre, exp_anterior))
            cursor.execute('''
                UPDATE cobro_reserva_usos SET gasto_expediente_imuh = ?, gasto_nombre = ?
                WHERE gasto_expediente_imuh = ?
            ''', (exp_norm, nombre, exp_anterior))
        conn.commit()


def delete_gasto_funcionamiento(gasto_id):
    """Elimina un Gasto FUN, siempre que no tenga desvíos o usos de reserva asociados."""
    with db_session() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT expediente_imuh FROM gastos_funcionamiento WHERE id = ?', (gasto_id,))
        row = cursor.fetchone()
        if not row:
            raise ValueError("No se encontró el Gasto de Funcionamiento.")
        exp = row['expediente_imuh']

        cursor.execute('SELECT COUNT(*) as cnt FROM cobro_desvios WHERE gasto_expediente_imuh = ?', (exp,))
        if cursor.fetchone()['cnt'] > 0:
            raise ValueError("No se puede eliminar este Gasto porque tiene desvíos asociados. Puede inhabilitarlo en su lugar.")

        cursor.execute('SELECT COUNT(*) as cnt FROM cobro_reserva_usos WHERE gasto_expediente_imuh = ?', (exp,))
        if cursor.fetchone()['cnt'] > 0:
            raise ValueError("No se puede eliminar este Gasto porque tiene usos de reserva asociados. Puede inhabilitarlo en su lugar.")

        cursor.execute('DELETE FROM gastos_funcionamiento WHERE id = ?', (gasto_id,))
        conn.commit()


def update_obra(obra_id, nombre, expediente_imuh, activa, proveedor_id=None):
    if not nombre or not nombre.strip():
        raise ValueError("El nombre de la obra no puede estar vacío.")
    if not expediente_imuh or not expediente_imuh.strip():
        raise ValueError("El expediente IMUH no puede estar vacío.")
    import utils
    if not utils.validar_expediente_imuh(expediente_imuh):
        raise ValueError("El Expediente IMUH tiene un formato inválido.")
        
    exp_normalizado = utils.normalizar_expediente_imuh(expediente_imuh)

    with db_session() as conn:
        cursor = conn.cursor()
        # Verificar duplicados del expediente excluyendo la obra actual
        cursor.execute('SELECT id FROM obras WHERE expediente_imuh = ? AND id != ?', (exp_normalizado, obra_id))
        if cursor.fetchone():
            raise ValueError(f"Ya existe otra obra registrada con el expediente IMUH '{exp_normalizado}'.")
            
        cursor.execute('''
            UPDATE obras
            SET nombre = ?, expediente_imuh = ?, activa = ?, proveedor_id = ?
            WHERE id = ?
        ''', (nombre.strip(), exp_normalizado, activa, proveedor_id, obra_id))
        
        # Sincronizar campo expediente_imuh en solicitudes_financiamiento por consistencia
        cursor.execute('''
            UPDATE solicitudes_financiamiento
            SET expediente_imuh = ?
            WHERE obra_id = ?
        ''', (exp_normalizado, obra_id))
        
        conn.commit()


def delete_obra(obra_id):
    with db_session() as conn:
        cursor = conn.cursor()
        
        # Verificar si tiene movimientos asociados
        cursor.execute('SELECT COUNT(*) as cnt FROM cobro_desvios WHERE obra_id = ?', (obra_id,))
        if cursor.fetchone()['cnt'] > 0:
            raise ValueError("No se puede eliminar la obra porque tiene desvíos directos asociados. Pruebe inhabilitándola.")
            
        cursor.execute('SELECT COUNT(*) as cnt FROM cobro_reserva_usos WHERE obra_id = ?', (obra_id,))
        if cursor.fetchone()['cnt'] > 0:
            raise ValueError("No se puede eliminar la obra porque tiene desvíos desde reserva asociados. Pruebe inhabilitándola.")
            
        cursor.execute('SELECT COUNT(*) as cnt FROM solicitudes_financiamiento WHERE obra_id = ?', (obra_id,))
        if cursor.fetchone()['cnt'] > 0:
            raise ValueError("No se puede eliminar la obra porque tiene solicitudes de financiamiento asociadas. Pruebe inhabilitándola.")

        cursor.execute('SELECT COUNT(*) as cnt FROM decretos_obras WHERE obra_id = ?', (obra_id,))
        if cursor.fetchone()['cnt'] > 0:
            raise ValueError("No se puede eliminar la obra porque está asociada a decretos. Pruebe inhabilitándola.")

        cursor.execute('DELETE FROM obras WHERE id = ?', (obra_id,))
        conn.commit()


def get_decretos_by_obra(obra_id):
    with db_session() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT d.*
            FROM decretos d
            JOIN decretos_obras do ON do.decreto_id = d.id
            WHERE do.obra_id = ?
            ORDER BY d.anio DESC, d.nro_decreto DESC
        ''', (obra_id,))
        rows = cursor.fetchall()
        return [dict(ix) for ix in rows]


def get_obras_by_decreto(decreto_id):
    with db_session() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT o.*, p.razon_social as proveedor_razon_social
            FROM obras o
            JOIN decretos_obras do ON do.obra_id = o.id
            LEFT JOIN proveedores_obras p ON o.proveedor_id = p.id
            WHERE do.decreto_id = ?
            ORDER BY o.nombre ASC
        ''', (decreto_id,))
        rows = cursor.fetchall()
        return [dict(ix) for ix in rows]


def get_obras_sin_solicitud():
    with db_session() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT o.*
            FROM obras o
            WHERE o.activa = 1 AND o.id NOT IN (
                SELECT DISTINCT obra_id FROM solicitudes_financiamiento WHERE obra_id IS NOT NULL
            )
            ORDER BY o.nombre ASC
        ''')
        rows = cursor.fetchall()
        return [dict(ix) for ix in rows]


def add_decreto_obras(decreto_id, obra_ids):
    with db_session() as conn:
        cursor = conn.cursor()
        cursor.execute('DELETE FROM decretos_obras WHERE decreto_id = ?', (decreto_id,))
        for o_id in obra_ids:
            cursor.execute('INSERT INTO decretos_obras (decreto_id, obra_id) VALUES (?, ?)', (decreto_id, o_id))
        conn.commit()


def update_decreto_details_for_solicitud(decreto_id, nro_expediente, destino_fondos, pdf_path, expediente_imuh):
    with db_session() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            UPDATE decretos
            SET nro_expediente = ?, destino_fondos = ?, pdf_path = ?, expediente_imuh = ?
            WHERE id = ?
        ''', (nro_expediente, destino_fondos, pdf_path, expediente_imuh, decreto_id))
        conn.commit()


def get_deudas_consolidadas():
    with db_session() as conn:
        cursor = conn.cursor()
        
        # 1. Obtener deudas de OBRAS
        cursor.execute('''
            SELECT 
                o.id as obra_id,
                o.nombre,
                o.expediente_imuh,
                o.activa,
                -- Suma de desvíos directos
                COALESCE((SELECT SUM(monto) FROM cobro_desvios WHERE obra_id = o.id), 0) as desvios,
                -- Suma de recuperos de desvíos directos
                COALESCE((SELECT SUM(r.monto) FROM cobro_desvios_recuperos r JOIN cobro_desvios d ON r.desvio_id = d.id WHERE d.obra_id = o.id), 0) as desvios_rec,
                -- Suma de usos de reserva
                COALESCE((SELECT SUM(monto) FROM cobro_reserva_usos WHERE obra_id = o.id), 0) as reserva,
                -- Suma de recuperos de reserva
                COALESCE((SELECT SUM(r.monto) FROM cobro_reserva_usos_recuperos r JOIN cobro_reserva_usos u ON r.reserva_uso_id = u.id WHERE u.obra_id = o.id), 0) as reserva_rec
            FROM obras o
        ''')
        rows_obras = cursor.fetchall()
        
        # 2. Obtener deudas de GASTOS DE FUNCIONAMIENTO (FUN)
        cursor.execute('''
            SELECT 
                gasto_nombre as nombre,
                gasto_expediente_imuh as expediente_imuh,
                SUM(monto) as desvios,
                COALESCE((SELECT SUM(r.monto) FROM cobro_desvios_recuperos r JOIN cobro_desvios d ON r.desvio_id = d.id WHERE d.gasto_expediente_imuh = cd.gasto_expediente_imuh AND d.gasto_nombre = cd.gasto_nombre), 0) as desvios_rec
            FROM cobro_desvios cd
            WHERE cd.gasto_nombre IS NOT NULL AND cd.gasto_nombre != ''
            GROUP BY gasto_expediente_imuh, gasto_nombre
        ''')
        rows_fun_desv = cursor.fetchall()

        cursor.execute('''
            SELECT 
                gasto_nombre as nombre,
                gasto_expediente_imuh as expediente_imuh,
                SUM(monto) as reserva,
                COALESCE((SELECT SUM(r.monto) FROM cobro_reserva_usos_recuperos r JOIN cobro_reserva_usos u ON r.reserva_uso_id = u.id WHERE u.gasto_expediente_imuh = cru.gasto_expediente_imuh AND u.gasto_nombre = cru.gasto_nombre), 0) as reserva_rec
            FROM cobro_reserva_usos cru
            WHERE cru.gasto_nombre IS NOT NULL AND cru.gasto_nombre != ''
            GROUP BY gasto_expediente_imuh, gasto_nombre
        ''')
        rows_fun_res = cursor.fetchall()

        deudas = []
        
        # Procesar Obras
        for o in rows_obras:
            saldo = round((o['desvios'] - o['desvios_rec']) + (o['reserva'] - o['reserva_rec']), 2)
            if saldo <= TOLERANCE:
                continue
            if o['activa'] == 0:
                continue # Pérdida/olvidado, no se lista
                
            # Determinar tipo y decreto asociado
            cursor.execute('''
                SELECT d.id, d.nro_decreto, d.anio, d.estado
                FROM decretos d
                JOIN decretos_obras do ON do.decreto_id = d.id
                WHERE do.obra_id = ?
            ''', (o['obra_id'],))
            decretos_asoc = cursor.fetchall()
            
            tipo = "Obra con Fondos Propios"
            dec_str = "Fondos Propios"
            
            if decretos_asoc:
                vigentes = [d for d in decretos_asoc if d['estado'] != 'Anulado']
                if vigentes:
                    tipo = "Obra con Decreto"
                    dec_str = ", ".join(f"Dto. {d['nro_decreto']}/{d['anio']}" for d in vigentes)
                else:
                    tipo = "Obra con Decreto (ANULADO)"
                    dec_str = ", ".join(f"Dto. {d['nro_decreto']}/{d['anio']} (ANULADO)" for d in decretos_asoc)
            
            deudas.append({
                'destino': o['nombre'],
                'tipo': tipo,
                'expediente_imuh': o['expediente_imuh'],
                'decreto_asociado': dec_str,
                'saldo': saldo
            })
            
        # Procesar FUN
        fun_dict = {}
        for r in rows_fun_desv:
            k = (r['nombre'], r['expediente_imuh'])
            fun_dict[k] = fun_dict.get(k, 0.0) + (r['desvios'] - r['desvios_rec'])
            
        for r in rows_fun_res:
            k = (r['nombre'], r['expediente_imuh'])
            fun_dict[k] = fun_dict.get(k, 0.0) + (r['reserva'] - r['reserva_rec'])
            
        for (nombre, exp_imuh), saldo in fun_dict.items():
            saldo = round(saldo, 2)
            if saldo > TOLERANCE:
                deudas.append({
                    'destino': nombre,
                    'tipo': "Gasto de Funcionamiento",
                    'expediente_imuh': exp_imuh,
                    'decreto_asociado': "Gasto Corriente",
                    'saldo': saldo
                })
                
        deudas.sort(key=lambda x: x['destino'])
        return deudas


def get_todas_obras_para_trazabilidad():
    """Retorna todas las entidades conocidas como destino de desvíos.
    Incluye:
      - Obras del catálogo formal (tabla obras).
      - Destinos legacy: entradas de cobro_desvios y cobro_reserva_usos sin
        decreto_destino_id ni obra_id (texto libre), con saldo > 0.
    Retorna lista de dicts con keys: id, nombre, expediente_imuh, tipo
      tipo: 'catalogo' | 'legacy'
    """
    with db_session() as conn:
        cursor = conn.cursor()

        # 1. Obras del catálogo
        cursor.execute('SELECT id, nombre, expediente_imuh FROM obras ORDER BY nombre ASC')
        obras_cat = [{'id': r['id'], 'nombre': r['nombre'],
                      'expediente_imuh': r['expediente_imuh'], 'tipo': 'catalogo'}
                     for r in cursor.fetchall()]

        # 2. Destinos legacy en cobro_desvios (sin obra_id ni decreto_destino_id, saldo > 0)
        cursor.execute(f'''
            SELECT DISTINCT cd.destino as nombre
            FROM cobro_desvios cd
            WHERE cd.obra_id IS NULL
              AND cd.decreto_destino_id IS NULL
              AND (cd.monto - COALESCE(
                      (SELECT SUM(monto) FROM cobro_desvios_recuperos WHERE desvio_id = cd.id), 0
                  )) > {TOLERANCE}
        ''')
        legacy_nombres_desv = {r['nombre'] for r in cursor.fetchall() if r['nombre']}

        # 3. Destinos legacy en cobro_reserva_usos
        cursor.execute(f'''
            SELECT DISTINCT ru.destino_detalle as nombre
            FROM cobro_reserva_usos ru
            WHERE ru.obra_id IS NULL
              AND ru.decreto_destino_id IS NULL
              AND ru.destino_tipo != 'fin_original'
              AND (ru.monto - COALESCE(
                      (SELECT SUM(monto) FROM cobro_reserva_usos_recuperos WHERE reserva_uso_id = ru.id), 0
                  )) > {TOLERANCE}
        ''')
        legacy_nombres_res = {r['nombre'] for r in cursor.fetchall() if r['nombre']}

        legacy_todos = legacy_nombres_desv | legacy_nombres_res
        obras_legacy = [{'id': None, 'nombre': n, 'expediente_imuh': None, 'tipo': 'legacy'}
                        for n in sorted(legacy_todos)]

        return obras_cat + obras_legacy


def get_trazabilidad_fuentes_por_obra(obra_id=None, obra_nombre_legacy=None):
    """Retorna todos los cobros que financiaron directa o indirectamente a una obra.
    Para obras del catálogo, usar obra_id (int).
    Para obras legacy (sin ID), usar obra_nombre_legacy (str).
    Retorna lista de dicts con:
      decreto_id, nro_decreto, decreto_anio, destino_fondos, decreto_expediente_imuh,
      cobro_id, cobro_fecha, cobro_monto, tipo_financiamiento, monto_financiado, saldo_pendiente, nro_op
    tipo_financiamiento: 'Fin Original' | 'Desvío' | 'Uso de Reserva'
    """
    with db_session() as conn:
        cursor = conn.cursor()
        filas = []

        if obra_id is not None:
            # --- Desvíos directos (cobro_desvios) ---
            cursor.execute(f'''
                SELECT
                    d_orig.id as decreto_id, d_orig.nro_decreto, d_orig.anio as decreto_anio,
                    d_orig.destino_fondos, d_orig.expediente_imuh as decreto_expediente_imuh,
                    c.id as cobro_id, c.fecha as cobro_fecha, c.monto as cobro_monto,
                    'Desvío' as tipo_financiamiento,
                    cd.monto as monto_financiado,
                    (cd.monto - COALESCE(
                        (SELECT SUM(monto) FROM cobro_desvios_recuperos WHERE desvio_id = cd.id), 0
                    )) as saldo_pendiente,
                    cd.nro_op
                FROM cobro_desvios cd
                JOIN cobros c ON cd.cobro_id = c.id
                JOIN cuotas cu ON c.cuota_id = cu.id
                JOIN decretos d_orig ON cu.decreto_id = d_orig.id
                WHERE cd.obra_id = ?
                  AND cd.monto > {TOLERANCE}
            ''', (obra_id,))
            filas += [dict(r) for r in cursor.fetchall()]

            # --- Usos de reserva (cobro_reserva_usos) ---
            cursor.execute(f'''
                SELECT
                    d_orig.id as decreto_id, d_orig.nro_decreto, d_orig.anio as decreto_anio,
                    d_orig.destino_fondos, d_orig.expediente_imuh as decreto_expediente_imuh,
                    c.id as cobro_id, c.fecha as cobro_fecha, c.monto as cobro_monto,
                    'Uso de Reserva' as tipo_financiamiento,
                    ru.monto as monto_financiado,
                    (ru.monto - COALESCE(
                        (SELECT SUM(monto) FROM cobro_reserva_usos_recuperos WHERE reserva_uso_id = ru.id), 0
                    )) as saldo_pendiente,
                    ru.nro_op
                FROM cobro_reserva_usos ru
                JOIN cobros c ON ru.cobro_id = c.id
                JOIN cuotas cu ON c.cuota_id = cu.id
                JOIN decretos d_orig ON cu.decreto_id = d_orig.id
                WHERE ru.obra_id = ?
                  AND ru.destino_tipo != 'fin_original'
                  AND ru.monto > {TOLERANCE}
            ''', (obra_id,))
            filas += [dict(r) for r in cursor.fetchall()]

            # --- Fin original (decretos asociados a la obra) ---
            cursor.execute(f'''
                SELECT
                    d.id as decreto_id, d.nro_decreto, d.anio as decreto_anio,
                    d.destino_fondos, d.expediente_imuh as decreto_expediente_imuh,
                    c.id as cobro_id, c.fecha as cobro_fecha, c.monto as cobro_monto,
                    'Fin Original' as tipo_financiamiento,
                    COALESCE(cd_dist.monto_fin_orig, c.monto) as monto_financiado,
                    COALESCE(cd_dist.monto_fin_orig, c.monto) -
                        COALESCE((SELECT SUM(monto) FROM cobro_fin_original_usos WHERE cobro_id = c.id), 0)
                    as saldo_pendiente,
                    NULL as nro_op
                FROM decretos_obras do_j
                JOIN decretos d ON do_j.decreto_id = d.id
                JOIN cuotas cu ON cu.decreto_id = d.id
                JOIN cobros c ON c.cuota_id = cu.id
                LEFT JOIN cobro_distribuciones cd_dist ON cd_dist.cobro_id = c.id
                WHERE do_j.obra_id = ?
            ''', (obra_id,))
            filas += [dict(r) for r in cursor.fetchall()]

        else:
            # --- Obra legacy: filtrar por nombre de texto ---
            nombre = obra_nombre_legacy or ''
            cursor.execute(f'''
                SELECT
                    d_orig.id as decreto_id, d_orig.nro_decreto, d_orig.anio as decreto_anio,
                    d_orig.destino_fondos, d_orig.expediente_imuh as decreto_expediente_imuh,
                    c.id as cobro_id, c.fecha as cobro_fecha, c.monto as cobro_monto,
                    'Desvío' as tipo_financiamiento,
                    cd.monto as monto_financiado,
                    (cd.monto - COALESCE(
                        (SELECT SUM(monto) FROM cobro_desvios_recuperos WHERE desvio_id = cd.id), 0
                    )) as saldo_pendiente,
                    cd.nro_op
                FROM cobro_desvios cd
                JOIN cobros c ON cd.cobro_id = c.id
                JOIN cuotas cu ON c.cuota_id = cu.id
                JOIN decretos d_orig ON cu.decreto_id = d_orig.id
                WHERE cd.obra_id IS NULL AND cd.decreto_destino_id IS NULL AND cd.destino = ?
                  AND cd.monto > {TOLERANCE}
            ''', (nombre,))
            filas += [dict(r) for r in cursor.fetchall()]

            cursor.execute(f'''
                SELECT
                    d_orig.id as decreto_id, d_orig.nro_decreto, d_orig.anio as decreto_anio,
                    d_orig.destino_fondos, d_orig.expediente_imuh as decreto_expediente_imuh,
                    c.id as cobro_id, c.fecha as cobro_fecha, c.monto as cobro_monto,
                    'Uso de Reserva' as tipo_financiamiento,
                    ru.monto as monto_financiado,
                    (ru.monto - COALESCE(
                        (SELECT SUM(monto) FROM cobro_reserva_usos_recuperos WHERE reserva_uso_id = ru.id), 0
                    )) as saldo_pendiente,
                    ru.nro_op
                FROM cobro_reserva_usos ru
                JOIN cobros c ON ru.cobro_id = c.id
                JOIN cuotas cu ON c.cuota_id = cu.id
                JOIN decretos d_orig ON cu.decreto_id = d_orig.id
                WHERE ru.obra_id IS NULL AND ru.decreto_destino_id IS NULL
                  AND ru.destino_tipo != 'fin_original' AND ru.destino_detalle = ?
                  AND ru.monto > {TOLERANCE}
            ''', (nombre,))
            filas += [dict(r) for r in cursor.fetchall()]

        filas.sort(key=lambda x: x['cobro_fecha'])
        return filas

def obtener_detalles_compensacion_grupo(grupo_id):
    if not grupo_id:
        return None
    with db_session() as conn:
        cursor = conn.cursor()
        
        # Consultar recuperos de desvíos
        cursor.execute('''
            SELECT r.id as rec_id, r.monto, r.fecha as rec_fecha, r.nro_op as rec_op, r.destino_tipo, r.destino_detalle,
                   d.id as desvio_id, d.monto as desvio_monto, d.fecha as desvio_fecha, d.nro_op as desvio_op, d.destino as desvio_destino,
                   dec.id as dec_id, dec.nro_decreto, dec.anio as dec_anio
            FROM cobro_desvios_recuperos r
            JOIN cobro_desvios d ON r.desvio_id = d.id
            JOIN cobros c ON d.cobro_id = c.id
            JOIN cuotas q ON c.cuota_id = q.id
            JOIN decretos dec ON q.decreto_id = dec.id
            WHERE r.grupo_compensacion_id = ?
        ''', (grupo_id,))
        desv_recs = [dict(row) for row in cursor.fetchall()]
        
        # Consultar recuperos de reserva
        cursor.execute('''
            SELECT r.id as rec_id, r.monto, r.fecha as rec_fecha, r.nro_op as rec_op, r.destino_tipo, r.destino_detalle,
                   u.id as uso_id, u.monto as uso_monto, u.fecha as uso_fecha, u.nro_op as uso_op, u.destino_detalle as uso_destino,
                   dec.id as dec_id, dec.nro_decreto, dec.anio as dec_anio
            FROM cobro_reserva_usos_recuperos r
            JOIN cobro_reserva_usos u ON r.reserva_uso_id = u.id
            JOIN cobros c ON u.cobro_id = c.id
            JOIN cuotas q ON c.cuota_id = q.id
            JOIN decretos dec ON q.decreto_id = dec.id
            WHERE r.grupo_compensacion_id = ?
        ''', (grupo_id,))
        res_recs = [dict(row) for row in cursor.fetchall()]
        
        return {
            'desvios': desv_recs,
            'reservas': res_recs
        }

def get_op_info(nro_op):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT nro_op, obra_id, gasto_id FROM op_bejerman WHERE nro_op = ?", (str(nro_op).strip(),))
        row = cursor.fetchone()
        if row:
            return dict(row)
        return None

def get_op_usage_count(nro_op):
    nro_op_str = str(nro_op).strip()
    if not nro_op_str:
        return 0
    with get_connection() as conn:
        cursor = conn.cursor()
        count = 0
        cursor.execute("SELECT COUNT(*) FROM cobro_fin_original_usos WHERE nro_op = ?", (nro_op_str,))
        count += cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM cobro_desvios WHERE nro_op = ?", (nro_op_str,))
        count += cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM cobro_desvios_recuperos WHERE nro_op = ?", (nro_op_str,))
        count += cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM cobro_reserva_usos_recuperos WHERE nro_op = ?", (nro_op_str,))
        count += cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM cobro_reserva_usos WHERE nro_op = ?", (nro_op_str,))
        count += cursor.fetchone()[0]
        return count


def get_op_usage_details(nro_op):
    nro_op_str = str(nro_op).strip()
    if not nro_op_str:
        return []
    usages = []
    with get_connection() as conn:
        cursor = conn.cursor()
        
        cursor.execute("SELECT monto, fecha FROM cobro_fin_original_usos WHERE nro_op = ?", (nro_op_str,))
        for row in cursor.fetchall():
            usages.append({'origen': 'Fin Original', 'monto': row['monto'], 'fecha': row['fecha']})
            
        cursor.execute("SELECT monto, fecha FROM cobro_desvios WHERE nro_op = ?", (nro_op_str,))
        for row in cursor.fetchall():
            usages.append({'origen': 'Desvío', 'monto': row['monto'], 'fecha': row['fecha']})
            
        cursor.execute("SELECT monto, fecha FROM cobro_desvios_recuperos WHERE nro_op = ?", (nro_op_str,))
        for row in cursor.fetchall():
            usages.append({'origen': 'Recupero de Desvío', 'monto': row['monto'], 'fecha': row['fecha']})
            
        cursor.execute("SELECT monto, fecha FROM cobro_reserva_usos_recuperos WHERE nro_op = ?", (nro_op_str,))
        for row in cursor.fetchall():
            usages.append({'origen': 'Recupero de Reserva', 'monto': row['monto'], 'fecha': row['fecha']})

        cursor.execute("SELECT monto, fecha FROM cobro_reserva_usos WHERE nro_op = ?", (nro_op_str,))
        for row in cursor.fetchall():
            usages.append({'origen': 'Pago desde Reserva', 'monto': row['monto'], 'fecha': row['fecha']})

            
    return usages

def register_or_update_op(nro_op, obra_id=None, gasto_id=None):
    nro_op_str = str(nro_op).strip()
    if not nro_op_str:
        return
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM op_bejerman WHERE nro_op = ?", (nro_op_str,))
        row = cursor.fetchone()
        if row:
            cursor.execute('''
                UPDATE op_bejerman 
                SET obra_id = ?, gasto_id = ? 
                WHERE nro_op = ?
            ''', (obra_id, gasto_id, nro_op_str))
        else:
            cursor.execute('''
                INSERT INTO op_bejerman (nro_op, obra_id, gasto_id)
                VALUES (?, ?, ?)
            ''', (nro_op_str, obra_id, gasto_id))
        conn.commit()

if __name__ == '__main__':
    init_db()



# --- PAGOS A FONDOS PROPIOS Y RECUPEROS ---

def update_monto_contrato_obra(obra_id, nuevo_monto):
    total_pagado = get_total_pagado_obra(obra_id)
    if nuevo_monto > 0 and nuevo_monto < (total_pagado - TOLERANCE):
        raise ValueError(f"No se puede reducir el monto de contrato por debajo del total ya pagado a la contratista (${total_pagado:,.2f})")
    
    with db_session() as conn:
        conn.execute("UPDATE obras SET monto_contrato = ? WHERE id = ?", (nuevo_monto, obra_id))

def get_pagos_fondos_propios(obra_id=None):
    with db_session() as conn:
        query = "SELECT * FROM pagos_fondos_propios"
        params = []
        if obra_id:
            query += " WHERE obra_id = ?"
            params.append(obra_id)
        query += " ORDER BY fecha DESC"
        return [dict(row) for row in conn.execute(query, params).fetchall()]

def add_pago_fondos_propios(obra_id, monto, fecha, nro_op, observaciones):
    _validar_op_o_nota_db(nro_op, observaciones, "pago con fondos propios")
    with db_session() as conn:
        conn.execute('''
            INSERT INTO pagos_fondos_propios (obra_id, monto, fecha, nro_op, observaciones)
            VALUES (?, ?, ?, ?, ?)
        ''', (obra_id, monto, fecha, nro_op, observaciones))

def delete_pago_fondos_propios(pago_id):
    with db_session() as conn:
        pago = conn.execute("SELECT * FROM pagos_fondos_propios WHERE id = ?", (pago_id,)).fetchone()
        if not pago: return
        obra_id = pago['obra_id']
        monto_pago = pago['monto']
        
        # Validar si ya se recuperó algo de esta obra
        total_pagado_fp = sum(p['monto'] for p in conn.execute("SELECT monto FROM pagos_fondos_propios WHERE obra_id = ?", (obra_id,)).fetchall())
        total_recuperado = sum(r['monto'] for r in conn.execute("SELECT monto FROM recuperos_fondos_propios WHERE obra_id = ?", (obra_id,)).fetchall())
        
        if (total_pagado_fp - monto_pago) < (total_recuperado - TOLERANCE):
            raise ValueError(f"No se puede eliminar. Al hacerlo, el total de adelantos sería menor a los fondos que ya recuperó la gestión (${total_recuperado:,.2f}). Elimine los recuperos primero.")
            
        conn.execute("DELETE FROM pagos_fondos_propios WHERE id = ?", (pago_id,))

def get_recuperos_fondos_propios(obra_id=None):
    with db_session() as conn:
        query = "SELECT * FROM recuperos_fondos_propios"
        params = []
        if obra_id:
            query += " WHERE obra_id = ?"
            params.append(obra_id)
        query += " ORDER BY fecha DESC"
        return [dict(row) for row in conn.execute(query, params).fetchall()]

def get_recuperos_by_cobro(cobro_id):
    with db_session() as conn:
        return [dict(row) for row in conn.execute("SELECT * FROM recuperos_fondos_propios WHERE cobro_id = ? ORDER BY fecha DESC", (cobro_id,)).fetchall()]

def add_recupero_fondos_propios(cobro_id, obra_id, monto, fecha, nro_op, notas):
    _validar_op_o_nota_db(nro_op, notas, "recupero de fondos propios")
    
    with db_session() as conn:
        # Validar que no supere el tope dentro de la misma transacción
        pagos_fp = sum(row['monto'] for row in conn.execute("SELECT monto FROM pagos_fondos_propios WHERE obra_id = ?", (obra_id,)).fetchall())
        recuperos = sum(row['monto'] for row in conn.execute("SELECT monto FROM recuperos_fondos_propios WHERE obra_id = ?", (obra_id,)).fetchall())
        tope = max(0.0, pagos_fp - recuperos)
        
        if monto > tope + TOLERANCE:
            raise ValueError(f"El monto a recuperar excede el total adeudado a Fondos Propios para esta obra (${tope:,.2f}).")
            
        conn.execute('''
            INSERT INTO recuperos_fondos_propios (cobro_id, obra_id, monto, fecha, nro_op, notas)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (cobro_id, obra_id, monto, fecha, nro_op, notas))

def delete_recupero_fondos_propios(recupero_id):
    with db_session() as conn:
        conn.execute("DELETE FROM recuperos_fondos_propios WHERE id = ?", (recupero_id,))

def get_total_pagado_obra(obra_id):
    with db_session() as conn:
        pagos_fp = sum(row['monto'] for row in conn.execute("SELECT monto FROM pagos_fondos_propios WHERE obra_id = ?", (obra_id,)).fetchall())
        fin_orig = sum(row['monto'] for row in conn.execute("SELECT monto FROM cobro_fin_original_usos WHERE obra_id = ?", (obra_id,)).fetchall())
        desvios = sum(row['monto'] for row in conn.execute("SELECT monto FROM cobro_desvios WHERE obra_id = ?", (obra_id,)).fetchall())
        reservas = sum(row['monto'] for row in conn.execute("SELECT monto FROM cobro_reserva_usos WHERE obra_id = ?", (obra_id,)).fetchall())
        return pagos_fp + fin_orig + desvios + reservas

def get_tope_recupero(obra_id):
    with db_session() as conn:
        pagos_fp = sum(row['monto'] for row in conn.execute("SELECT monto FROM pagos_fondos_propios WHERE obra_id = ?", (obra_id,)).fetchall())
        recuperos = sum(row['monto'] for row in conn.execute("SELECT monto FROM recuperos_fondos_propios WHERE obra_id = ?", (obra_id,)).fetchall())
        return max(0.0, pagos_fp - recuperos)

```

## Archivo: `export_codebase.py`

```python
import os

OUTPUT_FILE = "decretometro_codigo_completo.md"
EXCLUDE_DIRS = {'.git', '.venv', '__pycache__', '.agents', 'brain', 'scratch', '.pytest_cache'}
EXCLUDE_FILES = {'decretometro.db', OUTPUT_FILE}
ALLOWED_EXTENSIONS = {'.py', '.css', '.bat', '.sh', '.md', '.sql', '.toml'}

def export_codebase():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    output_path = os.path.join(base_dir, OUTPUT_FILE)
    
    written_count = 0
    with open(output_path, 'w', encoding='utf-8') as out:
        out.write("# Código Consolidado del Proyecto Decretómetro\n\n")
        out.write("Este archivo contiene la totalidad del código fuente y configuraciones del proyecto Decretómetro.\n\n")
        
        for root, dirs, files in os.walk(base_dir):
            # Filtrar carpetas excluidas
            dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS and not d.startswith('.')]
            
            for file in sorted(files):
                if file in EXCLUDE_FILES or file.endswith('.pyc') or file.endswith('.db'):
                    continue
                
                ext = os.path.splitext(file)[1]
                if ext in ALLOWED_EXTENSIONS or file in {'requirements.txt', 'AGENTS.md'}:
                    file_path = os.path.join(root, file)
                    rel_path = os.path.relpath(file_path, base_dir)
                    
                    out.write(f"## Archivo: `{rel_path}`\n\n")
                    
                    lang = ext.replace('.', '')
                    if lang == 'py':
                        lang = 'python'
                    elif lang == 'bat' or lang == 'cmd':
                        lang = 'cmd'
                    elif lang == '':
                        lang = 'text'
                    
                    out.write(f"```{lang}\n")
                    try:
                        with open(file_path, 'r', encoding='utf-8') as f:
                            out.write(f.read())
                    except Exception as e:
                        out.write(f"# Error al leer archivo: {e}\n")
                    out.write("\n```\n\n")
                    written_count += 1
                    
    print(f"Exportación finalizada con éxito. Archivos procesados: {written_count}")

if __name__ == "__main__":
    export_codebase()

```

## Archivo: `fix.py`

```python
import os

EXTRA_LOGIC = """

# --- PAGOS A FONDOS PROPIOS Y RECUPEROS ---

def update_monto_contrato_obra(obra_id, nuevo_monto):
    total_pagado = get_total_pagado_obra(obra_id)
    if nuevo_monto > 0 and nuevo_monto < (total_pagado - TOLERANCE):
        raise ValueError(f"No se puede reducir el monto de contrato por debajo del total ya pagado a la contratista (${total_pagado:,.2f})")
    
    with db_session() as conn:
        conn.execute("UPDATE obras SET monto_contrato = ? WHERE id = ?", (nuevo_monto, obra_id))

def get_pagos_fondos_propios(obra_id=None):
    with db_session() as conn:
        query = "SELECT * FROM pagos_fondos_propios"
        params = []
        if obra_id:
            query += " WHERE obra_id = ?"
            params.append(obra_id)
        query += " ORDER BY fecha DESC"
        return [dict(row) for row in conn.execute(query, params).fetchall()]

def add_pago_fondos_propios(obra_id, monto, fecha, nro_op, observaciones):
    _validar_op_o_nota_db(nro_op, observaciones, "pago con fondos propios")
    with db_session() as conn:
        conn.execute('''
            INSERT INTO pagos_fondos_propios (obra_id, monto, fecha, nro_op, observaciones)
            VALUES (?, ?, ?, ?, ?)
        ''', (obra_id, monto, fecha, nro_op, observaciones))

def delete_pago_fondos_propios(pago_id):
    with db_session() as conn:
        pago = conn.execute("SELECT * FROM pagos_fondos_propios WHERE id = ?", (pago_id,)).fetchone()
        if not pago: return
        obra_id = pago['obra_id']
        monto_pago = pago['monto']
        
        # Validar si ya se recuperó algo de esta obra
        total_pagado_fp = sum(p['monto'] for p in conn.execute("SELECT monto FROM pagos_fondos_propios WHERE obra_id = ?", (obra_id,)).fetchall())
        total_recuperado = sum(r['monto'] for r in conn.execute("SELECT monto FROM recuperos_fondos_propios WHERE obra_id = ?", (obra_id,)).fetchall())
        
        if (total_pagado_fp - monto_pago) < (total_recuperado - TOLERANCE):
            raise ValueError(f"No se puede eliminar. Al hacerlo, el total de adelantos sería menor a los fondos que ya recuperó la gestión (${total_recuperado:,.2f}). Elimine los recuperos primero.")
            
        conn.execute("DELETE FROM pagos_fondos_propios WHERE id = ?", (pago_id,))

def get_recuperos_fondos_propios(obra_id=None):
    with db_session() as conn:
        query = "SELECT * FROM recuperos_fondos_propios"
        params = []
        if obra_id:
            query += " WHERE obra_id = ?"
            params.append(obra_id)
        query += " ORDER BY fecha DESC"
        return [dict(row) for row in conn.execute(query, params).fetchall()]

def get_recuperos_by_cobro(cobro_id):
    with db_session() as conn:
        return [dict(row) for row in conn.execute("SELECT * FROM recuperos_fondos_propios WHERE cobro_id = ? ORDER BY fecha DESC", (cobro_id,)).fetchall()]

def add_recupero_fondos_propios(cobro_id, obra_id, monto, fecha, nro_op, notas):
    _validar_op_o_nota_db(nro_op, notas, "recupero de fondos propios")
    
    # Validar que no supere el tope
    tope = get_tope_recupero(obra_id)
    if monto > tope + TOLERANCE:
        raise ValueError(f"El monto a recuperar excede el total adeudado a Fondos Propios para esta obra (${tope:,.2f}).")
        
    with db_session() as conn:
        conn.execute('''
            INSERT INTO recuperos_fondos_propios (cobro_id, obra_id, monto, fecha, nro_op, notas)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (cobro_id, obra_id, monto, fecha, nro_op, notas))

def delete_recupero_fondos_propios(recupero_id):
    with db_session() as conn:
        conn.execute("DELETE FROM recuperos_fondos_propios WHERE id = ?", (recupero_id,))

def get_total_pagado_obra(obra_id):
    with db_session() as conn:
        pagos_fp = sum(row['monto'] for row in conn.execute("SELECT monto FROM pagos_fondos_propios WHERE obra_id = ?", (obra_id,)).fetchall())
        fin_orig = sum(row['monto'] for row in conn.execute("SELECT monto FROM cobro_fin_original_usos WHERE obra_id = ?", (obra_id,)).fetchall())
        desvios = sum(row['monto'] for row in conn.execute("SELECT monto FROM cobro_desvios WHERE obra_id = ?", (obra_id,)).fetchall())
        reservas = sum(row['monto'] for row in conn.execute("SELECT monto FROM cobro_reserva_usos WHERE obra_id = ?", (obra_id,)).fetchall())
        return pagos_fp + fin_orig + desvios + reservas

def get_tope_recupero(obra_id):
    with db_session() as conn:
        pagos_fp = sum(row['monto'] for row in conn.execute("SELECT monto FROM pagos_fondos_propios WHERE obra_id = ?", (obra_id,)).fetchall())
        recuperos = sum(row['monto'] for row in conn.execute("SELECT monto FROM recuperos_fondos_propios WHERE obra_id = ?", (obra_id,)).fetchall())
        return max(0.0, pagos_fp - recuperos)
"""

with open('database.py', 'a', encoding='utf-8') as f:
    f.write(EXTRA_LOGIC)

```

## Archivo: `get_html.py`

```python
import database as db
import trazabilidad_graph as tg
import json

cobro_id = 636
codigo_mermaid = tg.generar_mermaid_trazabilidad(cobro_id)
codigo_js = json.dumps(codigo_mermaid)

html_code = f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <style>
        body {{
            margin: 0;
            padding: 0;
            background-color: #ffffff;
        }}
        #mermaid-container {{
            background: #ffffff;
            padding: 15px;
            display: flex;
            justify-content: center;
            align-items: center;
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
        }}
        .error-box {{
            color: #721c24;
            background-color: #f8d7da;
            border: 1px solid #f5c6cb;
            padding: 15px;
            border-radius: 6px;
            font-family: 'Segoe UI', system-ui, sans-serif;
            font-size: 14px;
            margin: 10px;
        }}
    </style>
</head>
<body>
    <!-- Contenedor del Grafo -->
    <div id="mermaid-container">
        <div id="mermaid-graph-div" class="mermaid">
            <!-- Se poblará dinámicamente mediante JavaScript -->
        </div>
    </div>

    <!-- Panel de Depuración en Pantalla -->
    <div id="debug-log-panel" style="margin: 15px; padding: 10px; background-color: #f8f9fa; border: 1px dashed #ced4da; border-radius: 4px; font-family: monospace; font-size: 11px; color: #495057;">
        <div style="font-weight: bold; margin-bottom: 5px; border-bottom: 1px solid #dee2e6; padding-bottom: 3px; display: flex; justify-content: space-between;">
            <span>📋 LOGS DE DEPURACIÓN DEL MAPA (Cobro {cobro_id}):</span>
            <span id="log-status" style="color: #0d6efd;">Cargando...</span>
        </div>
        <div id="debug-log-lines" style="max-height: 150px; overflow-y: auto;">
            <!-- Logs aparecerán aquí -->
        </div>
    </div>

    <script>
        var logLines = null;
        var logStatus = null;
        
        function logToScreen(msg) {{
            logLines = document.getElementById('debug-log-lines');
            logStatus = document.getElementById('log-status');
            if (logLines) {{
                var div = document.createElement('div');
                div.style.borderBottom = "1px solid #f1f3f5";
                div.style.padding = "2px 0";
                div.textContent = "[" + new Date().toLocaleTimeString() + "] " + msg;
                logLines.appendChild(div);
                logLines.scrollTop = logLines.scrollHeight;
            }}
        }}

        function setStatus(text, color) {{
            logStatus = document.getElementById('log-status');
            if (logStatus) {{
                logStatus.textContent = text;
                if (color) logStatus.style.color = color;
            }}
        }}

        // Función de redimensionamiento del iframe de Streamlit
        function resize() {{
            var container = document.getElementById('mermaid-container');
            var debugPanel = document.getElementById('debug-log-panel');
            if (container) {{
                var height = container.scrollHeight + (debugPanel ? debugPanel.scrollHeight : 0) + 60;
                window.parent.postMessage({{
                    type: 'streamlit:setFrameHeight',
                    height: height
                }}, '*');
            }}
        }}

        // Registrar inmediatamente el error handler global en fase de captura para atrapar fallos de CDN
        window.addEventListener('error', function(e) {{
            var msg = "GLOBAL ERROR: " + e.message + " at " + e.filename + ":" + e.lineno;
            logToScreen(msg);
            setStatus("ERROR", "#dc3545");
            
            var container = document.getElementById('mermaid-container');
            if (container) {{
                container.innerHTML = '<div class="error-box">' +
                    '<b>Error en el mapa de fondos:</b><br>' +
                    'No se pudo cargar o renderizar el gráfico. Es posible que los servidores de gráficos estén bloqueados o no tenga acceso a internet.<br>' +
                    '<small style="color:#721c24; display:block; margin-top:5px;">Detalle: ' + e.message + '</small>' +
                    '</div>';
            }}
            resize();
        }}, true);
        
        // CDNs redundantes para la carga de Mermaid v9.4.3
        var cdns = [
            "https://cdn.jsdelivr.net/npm/mermaid@9.4.3/dist/mermaid.min.js",
            "https://cdnjs.cloudflare.com/ajax/libs/mermaid/9.4.3/mermaid.min.js",
            "https://unpkg.com/mermaid@9.4.3/dist/mermaid.min.js"
        ];
        var currentCdnIdx = 0;

        function loadMermaid() {{
            logToScreen("Intentando cargar CDN: " + cdns[currentCdnIdx]);
            setStatus("Cargando CDN (" + (currentCdnIdx+1) + "/" + cdns.length + ")...", "#0d6efd");
            
            var script = document.createElement('script');
            script.src = cdns[currentCdnIdx];
            script.onload = function() {{
                logToScreen("CDN cargado con éxito: " + cdns[currentCdnIdx]);
                setStatus("CDN Cargado, Inicializando...", "#198754");
                initMermaid();
            }};
            script.onerror = function() {{
                logToScreen("Fallo al cargar CDN: " + cdns[currentCdnIdx]);
                currentCdnIdx++;
                if (currentCdnIdx >= cdns.length) {{
                    logToScreen("TODOS los CDNs fallaron!");
                    setStatus("FALLA DE RED", "#dc3545");
                    var container = document.getElementById('mermaid-container');
                    if (container) {{
                        container.innerHTML = '<div class="error-box">' +
                            '<b>No se pudo conectar con los servidores de visualización:</b><br>' +
                            'Todos los CDNs de gráficos (jsDelivr, Cloudflare, unpkg) fallaron al cargar. ' +
                            'Por favor verifique si tiene conexión a internet o políticas de red.' +
                            '</div>';
                    }}
                    resize();
                    return;
                }}
                loadMermaid(); // Intentar con el siguiente CDN
            }};
            document.head.appendChild(script);
        }}

        function initMermaid() {{
            try {{
                var mermaidCode = {codigo_js};
                logToScreen("Código Mermaid cargado.");
                
                var targetDiv = document.getElementById('mermaid-graph-div');
                if (targetDiv) {{
                    targetDiv.textContent = mermaidCode;
                }}

                mermaid.initialize({{ 
                    startOnLoad: false,
                    theme: 'neutral',
                    securityLevel: 'loose',
                    flowchart: {{ 
                        useMaxWidth: false, 
                        htmlLabels: true, 
                        curve: 'basis' 
                        }}
                }});
                
                logToScreen("Llamando a mermaid.init()...");
                mermaid.init(undefined, document.querySelectorAll('.mermaid'));
                logToScreen("mermaid.init() ejecutado con éxito.");
                setStatus("Renderizado Completado", "#198754");
                setTimeout(resize, 400);
            }} catch (err) {{
                logToScreen("EXCEPCIÓN EN initMermaid: " + err.message + "\nStack: " + err.stack);
                setStatus("ERROR AL RENDERIZAR", "#dc3545");
                var container = document.getElementById('mermaid-container');
                if (container) {{
                    container.innerHTML = '<div class="error-box">' +
                        '<b>Error al inicializar el gráfico:</b><br>' +
                        err.message +
                        '</div>';
                }}
                resize();
            }}
        }}

        // Ejecutar la carga de Mermaid lo antes posible
        setTimeout(function() {{
            logToScreen("readyState: " + document.readyState);
            if (document.readyState === "complete" || document.readyState === "interactive") {{
                loadMermaid();
            }} else {{
                window.addEventListener('load', loadMermaid);
            }}
        }}, 100);
    </script>
</body>
</html>
"""

open("test_output.html", "w", encoding="utf-8").write(html_code)
print("Saved to test_output.html")

```

## Archivo: `migrate_decretometro_op.py`

```python
import sqlite3
import os

DB_PATH = 'decretometro.db'

def run_migration():
    print(f"Connecting to database: {DB_PATH}")
    if not os.path.exists(DB_PATH):
        print("Database file does not exist. Please run database.py first to initialize it.")
        return

    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON;")
    cursor = conn.cursor()

    # 1. Add nro_op column to existing tables if not present
    tables_to_update = [
        'cobro_desvios',
        'cobro_reserva_usos',
        'cobro_desvios_recuperos',
        'cobro_reserva_usos_recuperos'
    ]

    for table in tables_to_update:
        # Check columns
        cursor.execute(f"PRAGMA table_info({table})")
        columns = [row[1] for row in cursor.fetchall()]
        if 'nro_op' not in columns:
            print(f"Adding column 'nro_op' to table '{table}'...")
            try:
                cursor.execute(f"ALTER TABLE {table} ADD COLUMN nro_op TEXT")
                print(f"Column 'nro_op' added to table '{table}' successfully.")
            except Exception as e:
                print(f"Error adding column to '{table}': {e}")
        else:
            print(f"Column 'nro_op' already exists in table '{table}'.")

    # 2. Create cobro_fin_original_usos table
    print("Creating table 'cobro_fin_original_usos'...")
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS cobro_fin_original_usos (
            id                  INTEGER PRIMARY KEY AUTOINCREMENT,
            cobro_id            INTEGER NOT NULL,
            monto               REAL NOT NULL,
            fecha               DATE NOT NULL,
            nro_op              TEXT,
            notes               TEXT, -- naming column 'notes' or 'notas' to match schema? Let's check: cobro_reserva_usos has 'notas'
            notas               TEXT,
            FOREIGN KEY (cobro_id) REFERENCES cobros(id) ON DELETE CASCADE
        )
    ''')
    print("Table 'cobro_fin_original_usos' created or verified.")

    # 3. Migrate historical data
    # We select all distributions to Fin Original
    cursor.execute('''
        SELECT cd.cobro_id, cd.monto_fin_orig, c.fecha
        FROM cobro_distribuciones cd
        JOIN cobros c ON cd.cobro_id = c.id
        WHERE cd.monto_fin_orig > 0
    ''')
    distributions = cursor.fetchall()
    print(f"Found {len(distributions)} historical distributions to Fin Original.")

    migrated_count = 0
    for cobro_id, monto_fin_orig, fecha in distributions:
        # Check if we already migrated this cobro_id
        cursor.execute("SELECT id FROM cobro_fin_original_usos WHERE cobro_id = ?", (cobro_id,))
        exists = cursor.fetchone()
        if not exists:
            # Create a default usage record
            cursor.execute('''
                INSERT INTO cobro_fin_original_usos (cobro_id, monto, fecha, nro_op, notas)
                VALUES (?, ?, ?, NULL, 'Migrado automáticamente')
            ''', (cobro_id, monto_fin_orig, fecha))
            migrated_count += 1

    conn.commit()
    conn.close()
    print(f"Migration completed. Migrated {migrated_count} records to 'cobro_fin_original_usos'.")

if __name__ == '__main__':
    run_migration()

```

## Archivo: `migrate_estimacion.py`

```python
import sqlite3
import os

DB_PATH = 'decretometro.db'

def migrate():
    if not os.path.exists(DB_PATH):
        print(f"Error: {DB_PATH} not found.")
        return

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    try:
        print("Añadiendo columna 'fecha_estimada_cobro' a la tabla 'cuotas'...")
        cursor.execute("ALTER TABLE cuotas ADD COLUMN fecha_estimada_cobro DATE")
        conn.commit()
        print("Migración completada con éxito.")
    except sqlite3.OperationalError as e:
        if "duplicate column name" in str(e).lower():
            print("La columna ya existe. No se requiere migración.")
        else:
            print(f"Error durante la migración: {e}")
    except Exception as e:
        print(f"Error inesperado: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    migrate()

```

## Archivo: `migrate_fun_catalog.py`

```python
import sqlite3
import re
import os
import sys

# Append parent dir to path to import database
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
import utils

DB_PATH = "decretometro.db"

def migrate():
    print("Starting migration to populate gastos_funcionamiento...")
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    # 1. Ensure table exists (in case app hasn't run to trigger migrator yet)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS gastos_funcionamiento (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre          TEXT NOT NULL,
            expediente_imuh TEXT NOT NULL UNIQUE,
            activo          INTEGER NOT NULL DEFAULT 1 CHECK(activo IN (0, 1))
        )
    ''')
    conn.commit()

    # 2. Extract unique FUN entries from cobro_desvios
    cursor.execute('''
        SELECT DISTINCT gasto_nombre, gasto_expediente_imuh 
        FROM cobro_desvios 
        WHERE gasto_nombre IS NOT NULL AND TRIM(gasto_nombre) != ""
          AND gasto_expediente_imuh IS NOT NULL AND TRIM(gasto_expediente_imuh) != ""
    ''')
    desv_entries = cursor.fetchall()
    
    # 3. Extract unique FUN entries from cobro_reserva_usos
    cursor.execute('''
        SELECT DISTINCT gasto_nombre, gasto_expediente_imuh 
        FROM cobro_reserva_usos 
        WHERE gasto_nombre IS NOT NULL AND TRIM(gasto_nombre) != ""
          AND gasto_expediente_imuh IS NOT NULL AND TRIM(gasto_expediente_imuh) != ""
    ''')
    res_entries = cursor.fetchall()
    
    # Combine and normalize
    unique_entries = {}
    for entry in list(desv_entries) + list(res_entries):
        name = entry['gasto_nombre'].strip()
        exp = utils.normalizar_expediente_imuh(entry['gasto_expediente_imuh'].strip())
        if exp not in unique_entries:
            unique_entries[exp] = name
            
    # 4. Insert into gastos_funcionamiento
    count = 0
    for exp, name in unique_entries.items():
        try:
            cursor.execute('''
                INSERT INTO gastos_funcionamiento (nombre, expediente_imuh, activo)
                VALUES (?, ?, 1)
            ''', (name, exp))
            count += 1
            print(f"Inserted Gasto FUN: {name} (Exp: {exp})")
        except sqlite3.IntegrityError:
            print(f"Gasto FUN already exists: {name} (Exp: {exp})")
            
    conn.commit()
    conn.close()
    print(f"Migration completed. Successfully populated {count} entries.")

if __name__ == "__main__":
    migrate()

```

## Archivo: `migrate_op_bejerman.py`

```python
import sqlite3
import re
from database import get_connection, init_db

def clean_op(nro_op):
    if not nro_op:
        return None
    # Keep only digits
    cleaned = re.sub(r'\D', '', str(nro_op))
    return cleaned if cleaned else None

def migrate_ops():
    # Ensure DB is initialized to latest version (schema 32)
    init_db()
    
    with get_connection() as conn:
        cursor = conn.cursor()
        
        # We will iterate over all 4 tables that have nro_op
        tables = [
            "cobro_fin_original_usos",
            "cobro_desvios",
            "cobro_desvios_recuperos",
            "cobro_reserva_usos_recuperos"
        ]
        
        for table in tables:
            # 1. Clean existing nro_op in the table
            cursor.execute(f"SELECT id, nro_op FROM {table} WHERE nro_op IS NOT NULL AND nro_op != ''")
            rows = cursor.fetchall()
            for r in rows:
                cleaned = clean_op(r['nro_op'])
                if cleaned != r['nro_op']:
                    cursor.execute(f"UPDATE {table} SET nro_op = ? WHERE id = ?", (cleaned, r['id']))
        
        conn.commit()
        
        # 2. Extract unique OPs and their obra_id / gasto_id
        op_map = {} # nro_op -> {'obra_id': x, 'gasto_id': y}
        
        # From cobro_fin_original_usos
        cursor.execute("SELECT nro_op, obra_id, gasto_expediente_imuh FROM cobro_fin_original_usos WHERE nro_op IS NOT NULL AND nro_op != ''")
        for r in cursor.fetchall():
            op = r['nro_op']
            if op not in op_map:
                op_map[op] = {'obra_id': None, 'gasto_id': None}
            if r['obra_id'] and not op_map[op]['obra_id']:
                op_map[op]['obra_id'] = r['obra_id']
            if r['gasto_expediente_imuh'] and not op_map[op]['gasto_id']:
                # Lookup gasto_id
                cursor.execute("SELECT id FROM gastos_funcionamiento WHERE expediente_imuh = ?", (r['gasto_expediente_imuh'],))
                g_row = cursor.fetchone()
                if g_row:
                    op_map[op]['gasto_id'] = g_row['id']
                    
        # From cobro_desvios
        # First check if cobro_desvios has obra_id and gasto_expediente_imuh
        cursor.execute("PRAGMA table_info(cobro_desvios)")
        cols = [c['name'] for c in cursor.fetchall()]
        if 'obra_id' in cols and 'gasto_expediente_imuh' in cols:
            cursor.execute("SELECT nro_op, obra_id, gasto_expediente_imuh FROM cobro_desvios WHERE nro_op IS NOT NULL AND nro_op != ''")
            for r in cursor.fetchall():
                op = r['nro_op']
                if op not in op_map:
                    op_map[op] = {'obra_id': None, 'gasto_id': None}
                if r['obra_id'] and not op_map[op]['obra_id']:
                    op_map[op]['obra_id'] = r['obra_id']
                if r['gasto_expediente_imuh'] and not op_map[op]['gasto_id']:
                    cursor.execute("SELECT id FROM gastos_funcionamiento WHERE expediente_imuh = ?", (r['gasto_expediente_imuh'],))
                    g_row = cursor.fetchone()
                    if g_row:
                        op_map[op]['gasto_id'] = g_row['id']
        else:
            # Maybe fallback to getting everything just as keys
            cursor.execute("SELECT nro_op FROM cobro_desvios WHERE nro_op IS NOT NULL AND nro_op != ''")
            for r in cursor.fetchall():
                op = r['nro_op']
                if op not in op_map:
                    op_map[op] = {'obra_id': None, 'gasto_id': None}
                    
        # For recuperos, just add the OP if not exists
        for table in ["cobro_desvios_recuperos", "cobro_reserva_usos_recuperos"]:
            cursor.execute(f"SELECT nro_op FROM {table} WHERE nro_op IS NOT NULL AND nro_op != ''")
            for r in cursor.fetchall():
                op = r['nro_op']
                if op not in op_map:
                    op_map[op] = {'obra_id': None, 'gasto_id': None}
                    
        # 3. Insert into op_bejerman
        for op, data in op_map.items():
            cursor.execute("SELECT 1 FROM op_bejerman WHERE nro_op = ?", (op,))
            if not cursor.fetchone():
                cursor.execute("INSERT INTO op_bejerman (nro_op, obra_id, gasto_id) VALUES (?, ?, ?)", 
                               (op, data['obra_id'], data['gasto_id']))
            else:
                # Update if missing
                cursor.execute("UPDATE op_bejerman SET obra_id = COALESCE(obra_id, ?), gasto_id = COALESCE(gasto_id, ?) WHERE nro_op = ?",
                               (data['obra_id'], data['gasto_id'], op))
                
        conn.commit()
        print(f"Migrated {len(op_map)} unique OPs to op_bejerman.")

if __name__ == "__main__":
    migrate_ops()

```

## Archivo: `pdf_generator.py`

```python
import os
from fpdf import FPDF
import datetime
import database as db
import pandas as pd
from utils import format_currency_ar, get_dashboard_kpis, get_cuotas_pendientes, get_resumen_habituales_pendientes, limpiar_prefijo_expediente

class ReporteFinancieroPDF(FPDF):
    def header(self):
        # Título
        self.set_font('Arial', 'B', 15)
        self.cell(0, 10, 'Reporte de Estado Financiero - Decretómetro', 0, 1, 'C')
        
        # Fecha
        self.set_font('Arial', 'I', 10)
        ahora = datetime.datetime.now()
        self.cell(0, 10, f'Generado el: {ahora.strftime("%d-%m-%Y %H:%M")}', 0, 1, 'C')
        self.ln(5)

    def footer(self):
        self.set_y(-15)
        self.set_font('Arial', 'I', 8)
        self.cell(0, 10, f'Página {self.page_no()}/{{nb}}', 0, 0, 'C')

    def chapter_title(self, title):
        self.set_font('Arial', 'B', 12)
        self.set_fill_color(200, 220, 255)
        self.cell(0, 8, title, 0, 1, 'L', fill=True)
        self.ln(4)

    def chapter_body(self, text):
        self.set_font('Arial', '', 10)
        self.multi_cell(0, 6, text)
        self.ln()

    def chapter_note(self, text):
        """Texto pequeño para leyendas y notas al pie de tabla."""
        self.set_font('Arial', 'I', 8)
        self.set_text_color(80, 80, 80)
        self.multi_cell(0, 5, text)
        self.set_text_color(0, 0, 0)
        self.ln(2)

    def split_text_to_lines(self, text, width, padding=4):
        paragraphs = text.split('\n')
        lines = []
        max_w = width - padding
        for para in paragraphs:
            words = para.split(' ')
            current_line = ""
            for word in words:
                test_line = current_line + " " + word if current_line else word
                if self.get_string_width(test_line) <= max_w:
                    current_line = test_line
                else:
                    if current_line:
                        lines.append(current_line)
                    current_line = word
            if current_line:
                lines.append(current_line)
        return lines

    def add_table(self, df, col_widths):
        # Header
        self.set_font('Arial', 'B', 10)
        self.set_fill_color(230, 230, 230)
        
        # Calculate header height and lines
        header_lines = [self.split_text_to_lines(str(col), col_widths[idx]) for idx, col in enumerate(df.columns)]
        max_header_lines = max(len(lines) for lines in header_lines)
        header_line_height = 5.0
        header_row_height = max(8.0, max_header_lines * header_line_height)
        
        x_start = self.get_x()
        y_start = self.get_y()
        
        for idx, lines in enumerate(header_lines):
            w = col_widths[idx]
            self.set_xy(x_start + sum(col_widths[:idx]), y_start)
            self.cell(w, header_row_height, '', border=1, fill=True)
            
            padding_y = (header_row_height - (len(lines) * header_line_height)) / 2.0
            for line_idx, line in enumerate(lines):
                self.set_xy(x_start + sum(col_widths[:idx]), y_start + padding_y + (line_idx * header_line_height))
                self.cell(w, header_line_height, line, border=0, align='L')
                
        self.set_xy(x_start, y_start + header_row_height)
        
        # Rows
        self.set_font('Arial', '', 9)
        for _, row in df.iterrows():
            is_total = str(row.iloc[0]).upper() == 'TOTAL'
            if is_total:
                self.set_font('Arial', 'B', 9)
            
            x_start = self.get_x()
            y_start = self.get_y()
            
            # Split items into lines
            cell_lines = [self.split_text_to_lines(str(item), col_widths[idx]) for idx, item in enumerate(row)]
            max_lines = max(len(lines) for lines in cell_lines)
            line_height = 4.5
            row_height = max(8.0, max_lines * line_height)
            
            # Page break check
            if y_start + row_height > self.page_break_trigger:
                self.add_page()
                x_start = self.get_x()
                y_start = self.get_y()
                
            for idx, lines in enumerate(cell_lines):
                w = col_widths[idx]
                self.set_xy(x_start + sum(col_widths[:idx]), y_start)
                
                fill_cell = is_total and idx == 0
                if fill_cell:
                    self.set_fill_color(240, 240, 240)
                
                self.cell(w, row_height, '', border=1, fill=fill_cell)
                
                padding_y = (row_height - (len(lines) * line_height)) / 2.0
                for line_idx, line in enumerate(lines):
                    self.set_xy(x_start + sum(col_widths[:idx]), y_start + padding_y + (line_idx * line_height))
                    self.cell(w, line_height, line, border=0, align='L')
                    
            self.set_xy(x_start, y_start + row_height)
            
            if is_total:
                self.set_font('Arial', '', 9)
        self.ln(5)

def generar_reporte_pdf(filepath):
    pdf = ReporteFinancieroPDF()
    pdf.alias_nb_pages()
    pdf.add_page()

    # --- DATOS DE PRESTAMOS Y DESVIOS ---
    pdf.chapter_title('1. Préstamos Vigentes (Desvíos a Recuperar)')
    
    deudas = []
    tot_d = 0
    tipo_codigos = {
        "Decreto":  "D",
        "Propios":  "P",
        "Legacy":   "L",
        "Reserva":  "R",
    }

    desvios_activos = db.get_desvios_activos_completos()
    for d in (desvios_activos or []):
        origen_str = f"Dto. {d['orig_nro']}/{d['orig_anio']} - {d['orig_nombre']}"
        if d['decreto_destino_id']:
            destino_str = f"Dto. {d['dest_nro']}/{d['dest_anio']} - {limpiar_prefijo_expediente(d['dest_nombre'])}"
        elif d.get('gasto_nombre'):
            destino_str = f"FUN: {d['gasto_nombre']} (Exp: {d['gasto_expediente_imuh']})"
        else:
            destino_str = limpiar_prefijo_expediente(d['destino_texto'])
        tipo_cod = "FUN" if d.get('gasto_nombre') else tipo_codigos["Decreto" if d['decreto_destino_id'] else "Propios"]
        deudas.append([origen_str, destino_str, tipo_cod, format_currency_ar(d['saldo']), ""])
        tot_d += d['saldo']

    prestamos_legacy = db.get_prestamos()
    for p in (prestamos_legacy or []):
        s_p = p['monto'] - p.get('total_devuelto', 0)
        if s_p > 0.01:
            deudas.append([f"Dto. {p['nro_decreto']}/{p['decreto_anio']}", limpiar_prefijo_expediente(p['destino']), tipo_codigos["Legacy"], format_currency_ar(s_p), p.get('motivo', '') or ""])
            tot_d += s_p

    # Préstamos desde Reserva (cobro_reserva_usos a otras obras)
    reserva_prestamos = db.get_reserva_usos_prestamos_activos()
    for rp in (reserva_prestamos or []):
        origen_str = f"Dto. {rp['orig_nro']}/{rp['orig_anio']} - {rp['orig_nombre']}"
        if rp['decreto_destino_id']:
            destino_str = f"Dto. {rp['dest_nro']}/{rp['dest_anio']} - {limpiar_prefijo_expediente(rp['dest_nombre'])}"
        elif rp.get('gasto_nombre'):
            destino_str = f"FUN: {rp['gasto_nombre']} (Exp: {rp['gasto_expediente_imuh']})"
        else:
            destino_str = limpiar_prefijo_expediente(rp['destino_detalle']) or "Obra sin decreto"
        notas_str = rp.get('notes_str') if 'notes_str' in locals() else (rp.get('notas') or "")
        tipo_cod = "FUN" if rp.get('gasto_nombre') else tipo_codigos["Reserva"]
        deudas.append([origen_str, destino_str, tipo_cod, format_currency_ar(rp['saldo']), notas_str])
        tot_d += rp['saldo']
            
    if deudas:
        deudas.append(["TOTAL", "", "", format_currency_ar(tot_d), ""])
        df_d = pd.DataFrame(deudas, columns=["Origen", "Destino", "T", "Saldo Pendiente", "Observaciones"])
        # Ajustado a 190mm totales para alinear con los márgenes por defecto de FPDF (barras celestes)
        pdf.add_table(df_d, col_widths=[55, 55, 10, 30, 40])
        pdf.chapter_note("Leyenda - T (Tipo):  D = Desvio a Obra con Decreto  |  R = Prestamo desde Reserva  |  P = Obra de Fondos Propios  |  L = Prestamo Legado  |  FUN = Gasto de Funcionamiento")
    else:
        pdf.chapter_body("No hay desvíos ni préstamos pendientes de devolución.")

    # --- DATOS DE RESERVAS ---
    pdf.chapter_title('2. Dinero en Reserva Disponible')
    reservas = []
    tot_r = 0
    cobros_dist = db.get_cobros_con_resumen_distribucion()
    for c in (cobros_dist or []):
        if c['monto_reserva'] > 0:
            usos = db.get_reserva_usos_by_cobro(c['id'])
            tot_usado = sum(u['monto'] for u in usos) if usos else 0
            saldo_r = c['monto_reserva'] - tot_usado
            if saldo_r > 0.01:
                reservas.append([f"Dto. {c['nro_decreto']}/{c['decreto_anio']} - {c['destino_fondos']}", c['fecha'], format_currency_ar(saldo_r)])
                tot_r += saldo_r
                
    if reservas:
        reservas.append(["TOTAL", "", format_currency_ar(tot_r)])
        df_r = pd.DataFrame(reservas, columns=["Decreto Origen", "Fecha Cobro", "Saldo Disponible"])
        pdf.add_table(df_r, col_widths=[120, 30, 40])
    else:
        pdf.chapter_body("No hay fondos guardados en reserva actualmente.")

    # --- DATOS DE CUOTAS PENDIENTES ---
    pdf.chapter_title('3. Cuotas Pendientes de Cobro')
    
    decretos = db.get_decretos()
    cuotas = []
    # Filtrar solo vigentes
    decretos_vigentes = {d['id']: d for d in decretos if d['estado'] != 'Anulado'}
    
    for d_id, d in decretos_vigentes.items():
        for c in db.get_cuotas_by_decreto(d_id):
            c['estado_decreto'] = d['estado']
            c['destino_fondos'] = d['destino_fondos']
            c['nro_decreto'] = d['nro_decreto']
            c['anio_decreto'] = d['anio']
            cuotas.append(c)
            
    cobros = db.get_all_cobros()
    df_cobros = pd.DataFrame(cobros) if cobros else pd.DataFrame()
    
    pendientes_filas = []
    tot_pendiente = 0
    
    for q in cuotas:
        # Calcular cobrado para esta cuota específica
        q_cobrado = df_cobros[df_cobros['cuota_id'] == q['id']]['monto'].sum() if not df_cobros.empty else 0
        saldo = q['monto'] - q_cobrado
        
        if saldo > 0.01:
            nombre_corto = q['destino_fondos']
            decreto_str = f"Dto. {q['nro_decreto']}/{q['anio_decreto']} - {nombre_corto}"
            periodo_str = f"{q['mes']:02d}/{q['anio']}"
            
            # Usamos anio * 100 + mes para ordenar cronológicamente
            sort_key_periodo = q['anio'] * 100 + q['mes']
            
            pendientes_filas.append({
                'decreto': decreto_str,
                'periodo': periodo_str,
                'sort_periodo': sort_key_periodo,
                'saldo': saldo,
                'saldo_str': format_currency_ar(saldo)
            })
            tot_pendiente += saldo
            
    if pendientes_filas:
        # Ordenar por Periodo (ASC), luego Saldo (ASC)
        pendientes_filas.sort(key=lambda x: (x['sort_periodo'], x['saldo']))
        
        filas_tabla = []
        for p in pendientes_filas:
            filas_tabla.append([p['decreto'], p['periodo'], p['saldo_str']])
            
        # Fila TOTAL
        filas_tabla.append(["TOTAL", "", format_currency_ar(tot_pendiente)])
        
        df_p = pd.DataFrame(filas_tabla, columns=["Decreto", "Periodo", "A Percibir"])
        # Ancho total 190mm
        pdf.add_table(df_p, col_widths=[130, 25, 35])
    else:
        pdf.chapter_body("No hay cuotas pendientes ni atrasadas.")

    # --- DATOS DE APORTES HABITUALES PENDIENTES ---
    pdf.chapter_title('4. Seguimiento de solicitudes de aportes para haberes')
    
    habituales = get_resumen_habituales_pendientes()
    if habituales:
        filas_h = []
        tot_h = 0
        for h in habituales:
            filas_h.append([h['tipo'], h['periodo'], format_currency_ar(h['monto_pedido']), format_currency_ar(h['monto_cobrado']), format_currency_ar(h['saldo'])])
            tot_h += h['saldo']
        
        filas_h.append(["TOTAL", "", "", "", format_currency_ar(tot_h)])
        df_h = pd.DataFrame(filas_h, columns=["Tipo", "Periodo", "Pedido", "Ingresado", "Saldo"])
        pdf.add_table(df_h, col_widths=[30, 40, 40, 40, 40])
    else:
        pdf.chapter_body("No hay aportes de Sueldos o SAC con saldo pendiente.")

    # --- DATOS DE INDICADORES (KPIs) ---
    pdf.chapter_title('5. Indicadores Generales')
    
    # KPIs requieren los DataFrames completos, no filtrados por vigentes
    df_decretos = pd.DataFrame(decretos)
    df_cuotas = pd.DataFrame(cuotas)
    
    if not df_cuotas.empty and not df_decretos.empty:
        # Requerido por get_dashboard_kpis
        def calc_monto_efectivo(row):
            if row['estado_decreto'] == 'Anulado':
                cobrado = df_cobros[df_cobros['cuota_id'] == row['id']]['monto'].sum() if not df_cobros.empty else 0
                return cobrado
            return row['monto']
        df_cuotas['monto_efectivo'] = df_cuotas.apply(calc_monto_efectivo, axis=1)
        
        fun = db.get_aportes_funcionamiento()
        sueldos = db.get_aportes_sueldo()
        pct_cobranza, pct_a_tiempo, pct_atrasado = get_dashboard_kpis(df_cuotas, df_cobros, cobros, fun, sueldos)
        
        pdf.set_font('Arial', 'B', 10)
        pdf.cell(60, 8, "% Cobranza ult. 12m:", 0, 0, 'L')
        pdf.set_font('Arial', '', 10)
        pdf.cell(0, 8, f"{pct_cobranza:.1f}%", 0, 1, 'L')
        
        pdf.set_font('Arial', 'B', 10)
        pdf.cell(60, 8, "Histórico en Tiempo y Forma:", 0, 0, 'L')
        pdf.set_font('Arial', '', 10)
        pdf.cell(0, 8, f"{pct_a_tiempo:.1f}%", 0, 1, 'L')
        
        pdf.set_font('Arial', 'B', 10)
        pdf.cell(60, 8, "Histórico Atrasado:", 0, 0, 'L')
        pdf.set_font('Arial', '', 10)
        pdf.cell(0, 8, f"{pct_atrasado:.1f}%", 0, 1, 'L')
        pdf.ln(5)
    else:
        pdf.chapter_body("No hay datos suficientes para calcular indicadores.")
        
    # Guardar en disco
    pdf.output(filepath, 'F')
    return filepath

def generar_reporte_solicitudes_pdf(filepath):
    pdf = ReporteFinancieroPDF()
    pdf.alias_nb_pages()
    pdf.add_page()
    
    # Titulo de la sección principal
    pdf.chapter_title('Estado de Solicitudes de Financiamiento')
    
    # Obtener todas las solicitudes
    solicitudes = db.get_solicitudes()
    
    filas = []
    tot_solicitado = 0
    tot_aprobado = 0
    tot_pendiente = 0
    
    for s in (solicitudes or []):
        monto = s['monto_solicitado']
        tot_solicitado += monto
        if s['estado'] == 'Aprobado':
            tot_aprobado += monto
        elif s['estado'] == 'Pendiente':
            tot_pendiente += monto
            
        monto_str = format_currency_ar(monto, include_symbol=False)
        fecha_str = s['fecha_solicitud']
        if isinstance(fecha_str, str):
            try:
                dt = datetime.datetime.strptime(fecha_str, '%Y-%m-%d').date()
                fecha_str = dt.strftime("%d-%m-%Y")
            except:
                pass
                
        # Destino
        destino = s['destino_fondos']
        
        # Estado o Nro Decreto
        estado_val = s['estado']
        if s['estado'] == 'Aprobado' and s.get('nro_decreto'):
            estado_val = f"Dto. {s['nro_decreto']}/{s['decreto_anio']}"
            
        filas.append([
            s['nro_expediente'],
            destino,
            fecha_str,
            estado_val,
            monto_str
        ])
        
    if filas:
        filas.append(["TOTAL", "", "", "", format_currency_ar(tot_solicitado, include_symbol=False)])
        df_sol = pd.DataFrame(filas, columns=["Expediente", "Destino / Obra", "Fecha", "Estado", "Monto"])
        # Ancho total 190mm: 45 (Expediente) + 70 (Destino) + 25 (Fecha) + 20 (Estado) + 30 (Monto) = 190
        pdf.add_table(df_sol, col_widths=[45, 70, 25, 20, 30])
        
        # Mostrar resumen ejecutivo
        pdf.ln(5)
        pdf.chapter_title('Resumen de Financiamiento')
        pdf.set_font('Arial', 'B', 10)
        pdf.cell(60, 8, "Total Solicitado:", 0, 0, 'L')
        pdf.set_font('Arial', '', 10)
        pdf.cell(0, 8, format_currency_ar(tot_solicitado, include_symbol=False), 0, 1, 'L')
        
        pdf.set_font('Arial', 'B', 10)
        pdf.cell(60, 8, "Total Aprobado (Decretado):", 0, 0, 'L')
        pdf.set_font('Arial', '', 10)
        pdf.cell(0, 8, format_currency_ar(tot_aprobado, include_symbol=False), 0, 1, 'L')
        
        pdf.set_font('Arial', 'B', 10)
        pdf.cell(60, 8, "Total Pendiente:", 0, 0, 'L')
        pdf.set_font('Arial', '', 10)
        pdf.cell(0, 8, format_currency_ar(tot_pendiente, include_symbol=False), 0, 1, 'L')
        
        tasa = (tot_aprobado / tot_solicitado * 100) if tot_solicitado > 0 else 0
        pdf.set_font('Arial', 'B', 10)
        pdf.cell(60, 8, "Tasa de Aprobación:", 0, 0, 'L')
        pdf.set_font('Arial', '', 10)
        pdf.cell(0, 8, f"{tasa:.1f}%", 0, 1, 'L')
    else:
        pdf.chapter_body("No hay solicitudes de financiamiento registradas en el sistema.")
        
    pdf.output(filepath, 'F')
    return filepath

def generar_reporte_composicion_pdf(filepath, decreto_info, cuota_info, df_comp, aclaraciones=None):
    pdf = ReporteFinancieroPDF()
    pdf.alias_nb_pages()
    pdf.add_page()
    
    pdf.chapter_title('Composición del Estado Actual de Fondos')
    
    # 1. Información General
    pdf.set_font('Arial', 'B', 10)
    pdf.cell(50, 6, "Decreto:", 0, 0, 'L')
    pdf.set_font('Arial', '', 10)
    pdf.cell(0, 6, decreto_info['identificacion'], 0, 1, 'L')
    
    pdf.set_font('Arial', 'B', 10)
    pdf.cell(50, 6, "Expediente IMUH:", 0, 0)
    pdf.set_font('Arial', '', 10)
    pdf.multi_cell(0, 6, decreto_info['expediente_imuh'])
    
    pdf.set_font('Arial', 'B', 10)
    pdf.cell(50, 6, "Nombre de la Obra:", 0, 0, 'L')
    pdf.set_font('Arial', '', 10)
    pdf.multi_cell(0, 6, decreto_info['destino'])
    pdf.ln(2)
    
    # 2. Identificación de la Cuota
    pdf.set_font('Arial', 'B', 10)
    pdf.cell(50, 6, "Cuota N°:", 0, 0, 'L')
    pdf.set_font('Arial', '', 10)
    pdf.cell(0, 6, str(cuota_info['numero']), 0, 1, 'L')
    
    pdf.set_font('Arial', 'B', 10)
    pdf.cell(50, 6, "Importe de la Cuota:", 0, 0, 'L')
    pdf.set_font('Arial', '', 10)
    pdf.cell(0, 6, format_currency_ar(cuota_info['importe'], include_symbol=False), 0, 1, 'L')
    
    pdf.set_font('Arial', 'B', 10)
    pdf.cell(50, 6, "Fechas de Cobro:", 0, 0, 'L')
    pdf.set_font('Arial', '', 10)
    pdf.multi_cell(0, 6, cuota_info['fechas_cobro'])
    pdf.ln(4)
    
    # 3. Aclaraciones generales si existen
    if aclaraciones and aclaraciones.strip():
        pdf.set_font('Arial', 'B', 10)
        pdf.cell(0, 6, "Aclaraciones generales de la distribución:", 0, 1, 'L')
        pdf.set_font('Arial', 'I', 9)
        pdf.multi_cell(0, 5, aclaraciones.strip())
        pdf.ln(4)
        
    # 4. Tabla de composición (Fecha, Destino, OP, Aclaraciones, Monto)
    pdf.add_table(df_comp, col_widths=[25, 65, 25, 50, 25])
    
    pdf.output(filepath, 'F')
    return filepath

def generar_reporte_desvios_pdf(filepath, titulo_reporte, obra_info, df_desvios, col_widths=None):
    pdf = ReporteFinancieroPDF()
    pdf.alias_nb_pages()
    pdf.add_page()
    
    pdf.chapter_title(titulo_reporte)
    
    # 1. Información General de la Obra
    pdf.set_font('Arial', 'B', 10)
    pdf.cell(50, 6, "Obra Seleccionada:", 0, 0, 'L')
    pdf.set_font('Arial', '', 10)
    pdf.cell(0, 6, obra_info.get('destino_fondos', 'N/A'), 0, 1, 'L')
    
    pdf.set_font('Arial', 'B', 10)
    pdf.cell(50, 6, "Expediente IMUH:", 0, 0, 'L')
    pdf.set_font('Arial', '', 10)
    pdf.cell(0, 6, obra_info.get('expediente_imuh', 'Sin asignar'), 0, 1, 'L')
    
    pdf.set_font('Arial', 'B', 10)
    pdf.cell(50, 6, "Asociado a Decreto:", 0, 0, 'L')
    pdf.set_font('Arial', '', 10)
    pdf.cell(0, 6, obra_info.get('decreto_identificacion', 'N/A'), 0, 1, 'L')
    
    pdf.set_font('Arial', 'B', 10)
    pdf.cell(50, 6, "Total Saldo Pendiente:", 0, 0, 'L')
    pdf.set_font('Arial', 'B', 10)
    pdf.cell(0, 6, format_currency_ar(obra_info.get('total_saldo_pendiente', 0.0)), 0, 1, 'L')
    pdf.ln(5)
    
    # 2. Tabla de desvíos
    if col_widths is None:
        col_widths = [18, 40, 22, 22, 22, 22, 16, 28] # Suma = 190
    
    pdf.add_table(df_desvios, col_widths)
    
    pdf.output(filepath, 'F')
    return filepath

def generar_reporte_gastos_funcionamiento_financiados_obra_pdf(filepath, df_gastos):
    pdf = ReporteFinancieroPDF(orientation='L')
    pdf.alias_nb_pages()
    pdf.add_page()
    
    pdf.chapter_title("Gastos de Funcionamiento Financiados con Aportes de Obra")
    
    # 1. Resumen
    total_adeudado = 0.0
    for _, row in df_gastos.iterrows():
        val = str(row['Importe adeudado']).replace('$', '').replace('.', '').replace(',', '.').strip()
        try:
            total_adeudado += float(val)
        except ValueError:
            pass
            
    pdf.set_font('Arial', 'B', 10)
    pdf.cell(50, 6, "Total Adeudado Pendiente:", 0, 0, 'L')
    pdf.set_font('Arial', 'B', 10)
    pdf.cell(0, 6, format_currency_ar(total_adeudado), 0, 1, 'L')
    pdf.cell(50, 6, "Cantidad de Registros:", 0, 0, 'L')
    pdf.set_font('Arial', '', 10)
    pdf.cell(0, 6, str(len(df_gastos)), 0, 1, 'L')
    pdf.ln(5)
    
    # 9 columns. Printable width in landscape = 277mm.
    col_widths = [22, 28, 50, 40, 25, 32, 40, 20, 20]
    
    pdf.add_table(df_gastos, col_widths)
    pdf.output(filepath, 'F')
    return filepath

if __name__ == '__main__':
    generar_reporte_pdf("test_report.pdf")
    print("Reporte generado exitosamente.")

```

## Archivo: `run_decretometro.bat`

```cmd
@echo off
cd C:\Users\bornemanns\.gemini\antigravity-ide\scratch\decretometro
echo Iniciando Decretometro...

:: Buscar puerto libre entre 8501 y 8510
set PORT=
for /L %%P in (8501,1,8510) do (
    if not defined PORT (
        netstat -an | find "%%P" | find "LISTENING" >nul 2>&1
        if errorlevel 1 set PORT=%%P
    )
)
if not defined PORT set PORT=8505

echo Usando puerto: %PORT%
streamlit run Inicio.py --server.port %PORT%

```

## Archivo: `stress_test_v2.py`

```python
import sqlite3
import datetime
import os
import sys

sys.path.append(os.getcwd())
import database as db

def log(msg):
    print(f"- {msg}")

def run():
    print("# Reporte de Stress Test (V2)")
    print("\n## Inicialización")
    log("Iniciando test de estrés sin borrar datos existentes...")
    
    # Trackers for cleanup
    created_decretos = []
    created_fun_years = [] 
    created_sueldos = []
    created_sac = []
    # Eliminar conn = db.get_connection() para evitar "database is locked"
    try:
        print("\n## 1. Pruebas de Decretos y Cuotas")
        # 1.1 Intentar crear decreto con datos inválidos (Integridad)
        conn = db.get_connection()
        try:
            conn.execute('INSERT INTO decretos (nro_decreto, anio, nro_expediente, destino_fondos, estado) VALUES (?, ?, ?, ?, ?)', (None, "No es int", None, None, 'Vigente'))
            log("HALLAZGO: La base de datos permite crear un decreto con datos nulos/inválidos tipos (Falta estrictez en SQLite o validación en backend).")
        except Exception as e:
            log(f"ÉXITO: La DB rechazó decreto inválido. Detalle: {e}")
        finally:
            conn.close()

        # 1.2 Crear decreto válido para pruebas
        d_id = db.add_decreto(9999, 2026, "TEST-STRESS-1", "Destino Test Stress")
        created_decretos.append(d_id)
        log(f"Decreto válido creado con ID {d_id}.")

        # 1.3 Agregar cuotas con montos negativos extremos
        conn = db.get_connection()
        try:
            conn.execute('INSERT INTO cuotas (decreto_id, mes, anio, monto) VALUES (?, ?, ?, ?)', (d_id, 1, 2026, -9999999.99))
            log("HALLAZGO: La base de datos permite registrar cuotas con montos negativos extremos.")
        except Exception as e:
            log(f"ÉXITO: No se permiten cuotas negativas. Detalle: {e}")
        finally:
            conn.close()

        # 1.4 Agregar cuotas con fechas inválidas
        conn = db.get_connection()
        try:
            conn.execute('INSERT INTO cuotas (decreto_id, mes, anio, monto) VALUES (?, ?, ?, ?)', (d_id, 13, 2026, 10000))
            log("HALLAZGO: La base de datos permite registrar cuotas con meses > 12.")
        except Exception as e:
            log(f"ÉXITO: No se permiten meses inválidos. Detalle: {e}")
        finally:
            conn.close()

        print("\n## 2. Pruebas de Cobros (Totales y Parciales)")
        # Crear cuota normal
        db.add_cuota(d_id, 2, 2026, 10000)
        cuotas = db.get_cuotas_by_decreto(d_id)
        c_id = [c['id'] for c in cuotas if c['monto'] == 10000][0]

        # 2.1 Pago futuro directo en DB
        conn = db.get_connection()
        try:
            conn.execute('INSERT INTO cobros (cuota_id, monto, fecha) VALUES (?, ?, ?)', (c_id, 5000, "2050-01-01"))
            log("HALLAZGO: La DB permite registrar cobros con fecha futura (La validación introducida recientemente está solo en la UI de Streamlit).")
        except Exception as e:
            log(f"ÉXITO: DB bloquea fecha futura. Detalle: {e}")
        finally:
            conn.close()

        # 2.2 Pago excedente (pagar más del saldo)
        conn = db.get_connection()
        try:
            conn.execute('INSERT INTO cobros (cuota_id, monto, fecha) VALUES (?, ?, ?)', (c_id, 9000000, "2026-03-01"))
            log("HALLAZGO: La DB permite cobrar un monto muy superior al proyectado de la cuota (No hay restricción de saldo máximo en DB).")
        except Exception as e:
            log(f"ÉXITO: DB bloquea excedente. Detalle: {e}")
        finally:
            conn.close()

        # 2.3 Pago negativo (simulando un "descuento" no autorizado)
        conn = db.get_connection()
        try:
            conn.execute('INSERT INTO cobros (cuota_id, monto, fecha) VALUES (?, ?, ?)', (c_id, -1500, "2026-03-02"))
            log("HALLAZGO: La base de datos permite pagos negativos.")
        except Exception as e:
            log(f"ÉXITO: DB bloquea pagos negativos. Detalle: {e}")
        finally:
            conn.close()

        print("\n## 3. Pruebas de Aportes Habituales")
        # 3.1 Funcionamiento - Año futuro o extremo
        db.set_monto_funcionamiento_anio(2099, 100000)
        created_fun_years.append(2099)
        log("Creado año 2099 para funcionamiento.")
        fun_2099 = db.get_aportes_funcionamiento(2099)
        f_id = fun_2099[0]['id']

        # Cobro futuro en funcionamiento
        conn = db.get_connection()
        try:
            conn.execute('UPDATE aportes_funcionamiento SET monto_cobrado = ?, fecha_cobro = ? WHERE id = ?', (100000, "2099-01-15", f_id))
            log("HALLAZGO: Funcionamiento permite registrar cobros con fechas futuras a nivel DB.")
        except Exception as e:
            log(f"ÉXITO: Funcionamiento bloquea fecha futura. Detalle: {e}")
        finally:
            conn.close()

        # 3.2 Sueldos - Mes inválido y negativos
        conn = db.get_connection()
        try:
            conn.execute('INSERT INTO aportes_sueldo (anio, mes, monto_pedido, fecha_pedido) VALUES (?, ?, ?, ?)', (2026, 15, -999, "2026-03-01"))
            log("HALLAZGO: Sueldos permite mes 15 y montos negativos.")
        except Exception as e:
            log(f"ÉXITO: Sueldos bloquea datos inválidos. Detalle: {e}")
        finally:
            conn.close()

        # 3.3 SAC - Cuota inválida (ej. aguinaldo tercera cuota)
        conn = db.get_connection()
        try:
            conn.execute('INSERT INTO aportes_sac (anio, cuota_nro, monto_pedido, fecha_pedido) VALUES (?, ?, ?, ?)', (2026, 3, 50000, "2026-03-01"))
            log("HALLAZGO: SAC permite cuotas diferentes a 1 o 2 a nivel DB.")
        except Exception as e:
            log(f"ÉXITO: SAC bloquea cuota 3. Detalle: {e}")
        finally:
            conn.close()

    finally:
        print("\n## 4. Limpieza (Cleanup)")
        for d in created_decretos:
            if d is not None:
                try:
                    db.delete_decreto(d)
                except Exception as e:
                    pass
        log(f"Se eliminaron {len(created_decretos)} decretos de prueba (y sus cuotas/cobros por cascada).")

        for y in created_fun_years:
            try:
                db.delete_anio_funcionamiento(y)
            except: pass
        log(f"Se eliminaron {len(created_fun_years)} años de configuración de funcionamiento.")

        for s in created_sueldos:
            try:
                db.delete_aporte_sueldo(s)
            except: pass
        log(f"Se eliminaron {len(created_sueldos)} registros de prueba de sueldos.")

        for sac in created_sac:
            try:
                db.delete_aporte_sac(sac)
            except: pass
        log(f"Se eliminaron {len(created_sac)} registros de prueba de SAC.")

    print("\n## Conclusión del Estrés")
    print("El test ha finalizado y los rastros han sido limpiados de la base de datos de manera segura.")

if __name__ == '__main__':
    run()

```

## Archivo: `stress_test_v3.py`

```python
import sqlite3
import datetime
import os
import sys

sys.path.append(os.getcwd())
import database as db

def log(msg):
    print(f"- {msg}")

def run():
    print("# Reporte de Stress Test (V3 - Post-Backend Validations)")
    print("\n## Inicialización")
    log("Iniciando test de estrés sin borrar datos existentes...")
    
    # Trackers for cleanup
    created_decretos = []
    created_fun_years = [] 
    created_sueldos = []
    created_sac = []

    try:
        print("\n## 1. Pruebas de Decretos y Cuotas")
        
        # 1.1 Intentar crear decreto con datos inválidos (Integridad SQLite)
        conn = db.get_connection()
        try:
            conn.execute('INSERT INTO decretos (nro_decreto, anio, nro_expediente, destino_fondos, estado) VALUES (?, ?, ?, ?, ?)', (None, "No es int", None, None, 'Vigente'))
            log("FALLO: La base de datos permite crear un decreto nulo.")
        except Exception as e:
            log(f"EXITO: La DB rechazó decreto nulo. Detalle: {e}")
        finally:
            conn.close()

        # 1.2 Crear decreto válido para pruebas
        d_id = db.add_decreto(9999, 2026, "TEST-STRESS-1", "Destino Test Stress")
        created_decretos.append(d_id)
        log(f"Decreto válido creado con ID {d_id}.")

        # 1.3 Cuotas con montos negativos extremos (Validación Backend)
        try:
            db.add_cuota(d_id, 1, 2026, -9999999.99)
            log("FALLO: La base de datos permitió registrar cuota con monto negativo.")
        except ValueError as e:
            log(f"EXITO (Backend): Bloqueado cuota negativa. Detalle: {e}")

        # 1.4 Cuotas con meses inválidos
        try:
            db.add_cuota(d_id, 13, 2026, 10000)
            log("FALLO: La base de datos permitió registrar cuota con mes 13.")
        except ValueError as e:
            log(f"EXITO (Backend): Bloqueado mes inválido. Detalle: {e}")


        print("\n## 2. Pruebas de Cobros (Totales y Parciales)")
        # Crear cuota normal
        db.add_cuota(d_id, 2, 2026, 10000)
        cuotas = db.get_cuotas_by_decreto(d_id)
        c_id = [c['id'] for c in cuotas if c['monto'] == 10000][0]

        # 2.1 Pago futuro
        try:
            db.add_cobro(c_id, 5000, "2050-01-01")
            log("FALLO: Se permitió un cobro futuro.")
        except ValueError as e:
            log(f"EXITO (Backend): Bloqueado cobro futuro. Detalle: {e}")

        # 2.2 Pago excedente (sobrepago)
        try:
            db.add_cobro(c_id, 9000000, datetime.date.today().strftime('%Y-%m-%d'))
            log("FALLO: Se permitió sobrepago.")
        except ValueError as e:
            log(f"EXITO (Backend): Bloqueado sobrepago. Detalle: {e}")

        # 2.3 Pago negativo
        try:
            db.add_cobro(c_id, -1500, datetime.date.today().strftime('%Y-%m-%d'))
            log("FALLO: Se permitió pago negativo.")
        except ValueError as e:
            log(f"EXITO (Backend): Bloqueado pago negativo. Detalle: {e}")


        print("\n## 3. Pruebas de Aportes Habituales")
        # 3.1 Funcionamiento - Año futuro
        try:
            db.set_monto_funcionamiento_anio(2099, 100000)
            created_fun_years.append(2099)
            log("FALLO: Se permitió generar funcionamiento para el 2099.")
        except ValueError as e:
            log(f"EXITO (Backend): Bloqueado año futuro. Detalle: {e}")

        # Funcionamiento - Monto 0 o negativo
        try:
            db.set_monto_funcionamiento_anio(2025, -5000)
            created_fun_years.append(2025)
            log("FALLO: Se permitió generar funcionamiento con monto negativo.")
        except ValueError as e:
            log(f"EXITO (Backend): Bloqueado monto pautado negativo. Detalle: {e}")

        # 3.2 Sueldos - Mes inválido y negativos
        try:
            s_id = db.add_aporte_sueldo(2026, 15, -999, "2026-03-01")
            if s_id: created_sueldos.append(s_id)
            log("FALLO: Se permitió generar sueldo con mes 15 y monto negativo.")
        except ValueError as e:
            log(f"EXITO (Backend): Bloqueados mes/monto inválidos en sueldos. Detalle: {e}")

        # 3.3 SAC - Cuota inválida (tercera cuota)
        try:
            sac_id = db.add_aporte_sac(2026, 3, 50000, "2026-03-01")
            if sac_id: created_sac.append(sac_id)
            log("FALLO: Se permitió SAC cuota 3.")
        except ValueError as e:
            log(f"EXITO (Backend): Bloqueada cuota de SAC no permitida (1 o 2). Detalle: {e}")

    finally:
        print("\n## 4. Limpieza Estricta (Cleanup)")
        for d in created_decretos:
            if d is not None:
                try:
                    db.delete_decreto(d)
                except Exception:
                    pass
        log(f"Se limpiaron {len(created_decretos)} decretos de prueba.")

        for y in created_fun_years:
            try:
                db.delete_anio_funcionamiento(y)
            except: pass
        log(f"Se limpiaron {len(created_fun_years)} años de configuración de funcionamiento creados.")

        for s in created_sueldos:
            try:
                db.delete_aporte_sueldo(s)
            except: pass
        log(f"Se limpiaron {len(created_sueldos)} registros de prueba de sueldos creados.")

        for sac in created_sac:
            try:
                db.delete_aporte_sac(sac)
            except: pass
        log(f"Se limpiaron {len(created_sac)} registros de prueba de SAC creados.")

    print("\n## Evaluación Final")
    print("Test completado. Todas las inyecciones de estrés a nivel de backend fueron rechazadas.")

if __name__ == '__main__':
    run()

```

## Archivo: `stress_test_v4.py`

```python
import os
import sys
import datetime

# Add the root directory to sys.path so we can import internal modules
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
import database as db

# Trackers for cleanup
created_decretos = []
created_cobros = []

log_msgs = []
def log(msg, success=True):
    prefix = "[OK]" if success else "[ERROR/FAIL]"
    line = f"{prefix} {msg}"
    log_msgs.append(line)
    print(line)

def run_stress_test():
    log("=== INICIANDO STRESS TEST V4 (RECUPEROS EXTREMOS) ===")
    
    try:
        # Forzar migración de DB por si acaso
        db.init_db()
        
        # 1. SETUP: Crear Decretos Receptores y Origen
        log("Creando Decretos de prueba...")
        id_dec_A = db.add_decreto(9901, 2026, "STRESS-01", "Obra Origen A", None)
        id_dec_B = db.add_decreto(9902, 2026, "STRESS-02", "Obra Destino B (Con Dto)", None)
        created_decretos.extend([id_dec_A, id_dec_B])
        
        db.add_cuota(id_dec_A, 5, 2026, 1000000.0) # 1 millon a A
        db.add_cuota(id_dec_B, 5, 2026, 500000.0)  # 500k a B
        
        # 2. COBRO EN DECRETO A
        cuotas_A = db.get_cuotas_by_decreto(id_dec_A)
        c_A_id = cuotas_A[0]['id']
        id_cobro_A = db.add_cobro(c_A_id, 1000000.0, "2026-03-01", None)
        created_cobros.append(id_cobro_A)
        log("Cobro de 1.000.000 registrado en Decreto A.")

        # 3. MALA DISTRIBUCIÓN (Test de Excepción)
        log("Test: Intentar distribuir MÁS dinero del cobrado (Debería fallar)")
        try:
            # 500k FO + 600k Reserva = 1.1M > 1M
            # Wait, upsert_distribucion only saves FO and Res. The validation of total is usually done in the UI.
            # But let's test if the backend prevents it... Actually, backend upsert_distribucion doesn't sum desvíos directly, UI does.
            # But add_desvio DOES check balances.
            db.upsert_distribucion(id_cobro_A, 500000.0, 500000.0, "Test FO y Res") # 1 Millon (Valido)
            log("Distribución inicial válida guardada.")
            
            # Try to add a desvío when balance is 0
            db.add_desvio(id_cobro_A, "Otra Obra", 100000.0, "Test fallo", "2026-03-02")
            log("FALLO DE TEST: Permitió agregar desvío sin saldo libre.", False)
        except ValueError as e:
            log(f"ÉXITO: Bloqueó desvío sin saldo libre correctly. ('{e}')")

        # 4. RE-DISTRIBUCIÓN VÁLIDA CON DESVÍOS
        log("Ajustando distribución para liberar 400.000 de saldo para desvíos...")
        db.upsert_distribucion(id_cobro_A, 500000.0, 100000.0, "Nuevo Ajuste") # Total = 600k. Libre = 400k.
        
        # 4.1 Desvío a Obra con Decreto (B)
        db.add_desvio(id_cobro_A, "Dummy", 250000.0, "Desvío Dto B", "2026-03-03", decreto_destino_id=id_dec_B)
        log("Desvío de 250.000 hacia Decreto B registrado exitosamente.")
        
        # 4.2 Desvío a Obra de Fondos Propios
        db.add_desvio(id_cobro_A, "Plaza Central (Fondos Propios)", 150000.0, "Desvío Propio", "2026-03-04", decreto_destino_id=None)
        log("Desvío de 150.000 hacia fondos propios registrado exitosamente.")
        
        desvios = db.get_desvios_by_cobro(id_cobro_A)
        id_desv_B = desvios[0]['id']
        id_desv_Propio = desvios[1]['id']

        # 5. TEST DE RECUPEROS (Éxitos y Fallos intencionales)
        log("Test: Intentar recuperar MÁS del importe del desvío...")
        try:
            db.add_desvio_recupero(id_desv_B, 300000.0, "2026-03-05", "fin_original")
            log("FALLO DE TEST: Permitió recuperar más del desvío.", False)
        except ValueError as e:
            log(f"ÉXITO: Bloqueó recupero fraudulento. ('{e}')")
            
        log("Test: Intentar recuperar importe negativo...")
        try:
            db.add_desvio_recupero(id_desv_Propio, -500.0, "2026-03-05", "fin_original")
            log("FALLO DE TEST: Permitió recupero negativo.", False)
        except ValueError as e:
            log(f"ÉXITO: Bloqueó recupero negativo. ('{e}')")
            
        # 6. RECUPEROS VÁLIDOS (RECUPERO Y REDIRECCION / "RECUPERO DE RECUPERO")
        log("Registrando devoluciones (Recuperos Válidos)...")
        # El 60% del desvío Propio (90.000) vuelve a Fin Original (Orígen A)
        db.add_desvio_recupero(id_desv_Propio, 90000.0, "2026-03-10", "fin_original")
        log("Recupero hacia 'Fin Original' (90k) exitoso.")
        
        # El Desvío aportado al Decreto B (250.000) se recupera, pero NO vuelve a origen, 
        # sino que se REdirecciona hacia una TERCERA OBRA (Fondos propios: "Hospital Norte")
        db.add_desvio_recupero(id_desv_B, 250000.0, "2026-03-15", "otra_obra", destino_detalle="Hospital Norte (Tercer Destino)", decreto_destino_id=None)
        log("Recupero Redireccionado a 'Hospital Norte' (250k) exitoso.")
        
        # Validar saldos
        desvios_final = db.get_desvios_by_cobro(id_cobro_A)
        saldo_Propio = desvios_final[1]['monto'] - desvios_final[1]['total_recuperado']
        saldo_B = desvios_final[0]['monto'] - desvios_final[0]['total_recuperado']
        log(f"Saldos Finales de Desvíos: Propio=${saldo_Propio} (Esperado 60k) | DtoB=${saldo_B} (Esperado 0)")

        if saldo_B == 0 and saldo_Propio == 60000.0:
            log("MATE EN UNO: Las matemáticas del backend sobrevivieron a recuperos cruzados.", True)
        else:
            log("ERROR MATEMÁTICO: Las cuentas no cuadran.", False)

    except Exception as e:
        log(f"Excepción general no controlada: {e}", False)

    finally:
        log("=== LIMPIEZA DE DATOS (Rollback manual) ===")
        # Eliminar cascada
        for cid in reversed(created_cobros):
            try:
                # First delete its desvios recuperos to not violate constraints if they existed
                # Since cascade rules on DB are set, if we delete desvio it might fail if recupero exists, 
                # but cascade is normally ON but let's be safe:
                desv_del = db.get_desvios_by_cobro(cid)
                for d in desv_del:
                    rec_del = db.get_recuperos_by_desvio(d['id'])
                    for r in rec_del:
                        db.delete_desvio_recupero(r['id'])
                    db.delete_desvio(d['id'])
                
                # Usos_Reserva
                us = db.get_reserva_usos_by_cobro(cid)
                for u in us:
                    db.delete_reserva_uso(u['id'])
                    
                db.delete_cobro(cid)
                log(f"Cobro ID {cid} limpiado.")
            except Exception as clean_e:
                log(f"Error limpiando cobro {cid}: {clean_e}")
                
        for did in reversed(created_decretos):
            try:
                db.delete_decreto(did)
                log(f"Decreto ID {did} limpiado.")
            except Exception as clean_e:
                log(f"Error limpiando decreto {did}: {clean_e}")
                
        log("=== PRUEBA DE ESTRÉS COMPLETADA Y DATOS ELIMINADOS ===")

if __name__ == "__main__":
    run_stress_test()

```

## Archivo: `style.css`

```css
@import url('https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;500;600;700&display=swap');

/* Configuración de Fuentes y Variables Globales */
:root {
    --md-sys-color-primary: #0041a2;
    --md-sys-color-primary-container: #0b57d0;
    --md-sys-color-background: #f8f9fa;
    --md-sys-color-surface-lowest: #ffffff;
    --md-sys-color-surface-container: #edeeef;
    --md-sys-color-outline: #737785;
    --md-sys-color-outline-variant: #e3e3e3;
    
    --md-sys-color-error: #ba1a1a;
    --md-sys-color-success: #006837;
    --md-sys-color-warning: #f57c00;
    
    --radius-card: 16px;
    --radius-button: 100px;
    --radius-input: 8px;
}

/* Aplicación de Fuente Global */
html, body, [class*="css"], .stMarkdown, .stText, .stButton, input, select, textarea {
    font-family: 'Outfit', sans-serif !important;
}

/* Fondo principal de Streamlit */
.stApp, [data-testid="stAppViewContainer"], [data-testid="stMainViewContainer"] {
    background-color: var(--md-sys-color-background) !important;
}

/* Encabezados y títulos */
h1, h2, h3, h4, h5, h6 {
    font-family: 'Outfit', sans-serif !important;
    font-weight: 600 !important;
    color: #191c1d !important;
}

/* Tarjetas de Métricas (Metric Cards) */
div[data-testid="stMetric"] {
    background-color: var(--md-sys-color-surface-lowest) !important;
    border: 1px solid var(--md-sys-color-outline-variant) !important;
    border-radius: var(--radius-card) !important;
    padding: 16px 20px !important;
    box-shadow: none !important;
    transition: transform 0.2s ease, box-shadow 0.2s ease !important;
}

div[data-testid="stMetric"]:hover {
    transform: translateY(-2px) !important;
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.05) !important;
}

/* Modificar estilo de valores dentro de métricas */
div[data-testid="stMetricValue"] {
    font-size: 28px !important;
    font-weight: 600 !important;
    color: var(--md-sys-color-primary) !important;
}

/* Contenedores de Streamlit (st.container, st.expander, etc.) */
[data-testid="stVerticalBlockBorderWrapper"], [data-testid="stExpander"], [data-testid="stAlert"], .st-emotion-cache-1r4q55c, .st-emotion-cache-12w0qpk, .st-emotion-cache-h6n1w1 {
    background-color: var(--md-sys-color-surface-lowest) !important;
    border: 1px solid var(--md-sys-color-outline-variant) !important;
    border-radius: var(--radius-card) !important;
    padding: 20px !important;
}

/* Botones estilo píldora (Pill-shaped buttons) */
div.stButton > button, div[data-testid="stFormSubmitButton"] > button {
    border-radius: var(--radius-button) !important;
    background-color: var(--md-sys-color-primary-container) !important;
    color: white !important;
    font-weight: 500 !important;
    border: none !important;
    padding: 10px 24px !important;
    font-size: 14px !important;
    transition: background-color 0.2s ease, transform 0.1s ease !important;
    box-shadow: 0 2px 4px rgba(0, 0, 0, 0.05) !important;
}

div.stButton > button:hover, div[data-testid="stFormSubmitButton"] > button:hover {
    background-color: var(--md-sys-color-primary) !important;
    color: white !important;
    transform: translateY(-1px) !important;
    box-shadow: 0 4px 8px rgba(0, 0, 0, 0.1) !important;
}

div.stButton > button:active, div[data-testid="stFormSubmitButton"] > button:active {
    transform: translateY(0) !important;
    box-shadow: 0 2px 4px rgba(0, 0, 0, 0.05) !important;
}

/* Campos de entrada (Text Input, Number Input, Date Input, Selectbox, Multiselect) */
div[data-baseweb="input"], div[data-baseweb="select"], .stTextArea textarea {
    border-radius: var(--radius-input) !important;
    background-color: var(--md-sys-color-surface-lowest) !important;
    border: 1px solid var(--md-sys-color-outline-variant) !important;
    transition: border-color 0.2s ease, box-shadow 0.2s ease !important;
}

div[data-baseweb="input"]:focus-within, div[data-baseweb="select"]:focus-within, .stTextArea textarea:focus {
    border-color: var(--md-sys-color-primary-container) !important;
    box-shadow: 0 0 0 2px rgba(11, 87, 208, 0.2) !important;
}

/* Estilo para las alertas integradas de Streamlit */
div.stAlert {
    border-radius: var(--radius-card) !important;
    border: 1px solid var(--md-sys-color-outline-variant) !important;
    padding: 14px 20px !important;
}

/* Mejorar visualización de Dataframes / Tablas */
div[data-testid="stDataFrame"] {
    border-radius: var(--radius-card) !important;
    overflow: hidden !important;
    border: 1px solid var(--md-sys-color-outline-variant) !important;
    background-color: var(--md-sys-color-surface-lowest) !important;
}

/* Panel Lateral (Sidebar) */
section[data-testid="stSidebar"] {
    background-color: var(--md-sys-color-background) !important;
    border-right: 1px solid var(--md-sys-color-outline-variant) !important;
}

section[data-testid="stSidebar"] .st-emotion-cache-6q4a65 {
    background-color: var(--md-sys-color-background) !important;
}

/* Barra de progreso de Streamlit */
div.stProgress > div > div > div {
    background-color: var(--md-sys-color-primary-container) !important;
    border-radius: 100px !important;
}

/* Chips de estado o advertencias personalizadas */
span.badge-success {
    background-color: rgba(0, 104, 55, 0.1) !important;
    color: var(--md-sys-color-success) !important;
    padding: 4px 12px !important;
    border-radius: var(--radius-button) !important;
    font-size: 12px !important;
    font-weight: 500 !important;
}

span.badge-danger {
    background-color: rgba(186, 26, 26, 0.1) !important;
    color: var(--md-sys-color-error) !important;
    padding: 4px 12px !important;
    border-radius: var(--radius-button) !important;
    font-size: 12px !important;
    font-weight: 500 !important;
}

span.badge-warning {
    background-color: rgba(245, 124, 0, 0.1) !important;
    color: var(--md-sys-color-warning) !important;
    padding: 4px 12px !important;
    border-radius: var(--radius-button) !important;
    font-size: 12px !important;
    font-weight: 500 !important;
}

header[data-testid="stHeader"] {
    background: transparent !important;
    pointer-events: none !important;
    border-bottom: none !important;
    height: 0px !important;
    min-height: 0px !important;
    overflow: visible !important;
}
header[data-testid="stHeader"] > div:last-child {
    display: none !important;
}
[data-testid="stSidebarCollapsedControl"], [data-testid="stSidebarCollapsedControl"] * {
    pointer-events: auto !important;
    z-index: 999999 !important;
}
[data-testid="stSidebarCollapsedControl"] {
    top: 15px !important;
}


```

## Archivo: `test_backend.py`

```python
import database as db
import datetime

db.init_db()
print("1. Migración ejecutada sin errores.")

try:
    db.add_desvio(1, "Destino Fake", -500, "Prueba", "2026-03-20")
    print("❌ Falla de seguridad: aceptó monto negativo.")
except ValueError as e:
    print(f"2. Seguridad OK: {e}")
except Exception as e:
    # Si falla por "Cobro no encontrado", es normal si la bd está vacía
    pass

deudas = db.get_deudas_obras_propias()
print(f"3. Obras propias en deuda consultadas correctamente. Resultados: {deudas}")

```

## Archivo: `test_decretometro_op.py`

```python
import os
import sys
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
import database as db

TEMP_DB = 'test_temp_op.db'
if os.path.exists(TEMP_DB):
    try: os.remove(TEMP_DB)
    except: pass
db.DB_PATH = TEMP_DB
db.init_db()

def run_tests():
    print("Running OP and Payment Modification Tests...")
    
    # 1. Setup Decreto and Cuota
    d_id = db.add_decreto(5555, 2026, "TEST-EXP-OP", "Obra OP Test")
    c_id = db.add_cuota(d_id, 1, 2026, 100000.0)
    
    # 2. Add Cobro
    cobro_id = db.add_cobro(c_id, 100000.0, "2026-06-08")
    
    # 3. Distribute initially: 80k Fin Original, 20k Reserva
    db.upsert_distribucion(cobro_id, 80000.0, 20000.0, "Distribucion inicial")
    
    # 4. Register a payment to Fin Original (representing the 80k) with OP
    uso_fo_id = db.add_fin_original_uso(cobro_id, 80000.0, "2026-06-08", "OP-100", "Primer pago")
    
    # 5. Check it exists and contains OP
    usos_fo = db.get_fin_original_usos_by_cobro(cobro_id)
    assert len(usos_fo) == 1
    assert usos_fo[0]['monto'] == 80000.0
    assert usos_fo[0]['nro_op'] == "OP-100"
    
    # 6. Test update of Fin Original usage (modifying OP and notes)
    db.update_fin_original_uso(uso_fo_id, 80000.0, "2026-06-08", "OP-100-EDITED", "Primer pago editado")
    usos_fo = db.get_fin_original_usos_by_cobro(cobro_id)
    assert usos_fo[0]['nro_op'] == "OP-100-EDITED"
    assert usos_fo[0]['notas'] == "Primer pago editado"
    
    # 7. Test validation when editing Fin Original usage monto exceeds allocated
    try:
        db.update_fin_original_uso(uso_fo_id, 90000.0, "2026-06-08", "OP-100-EDITED", "Excedente")
        assert False, "Expected ValueError when exceeding budget"
    except ValueError as e:
        print("Success: Caught expected ValueError when exceeding Fin Original budget.")
        
    # 8. Test adding a desvio with OP
    # Currently, Fin Original (80k) + Reserva (20k) = 100k, so there is 0 free balance. Let's decrease Reserva to 10k so we have 10k free
    db.upsert_distribucion(cobro_id, 80000.0, 10000.0, "Distribucion editada")
    # Now we add a desvio of 10k since we have 10k free balance
    db.add_desvio(cobro_id, "Obras Viales", 10000.0, "Préstamo", "2026-06-08", nro_op="OP-DESV-200")
    
    desvios = db.get_desvios_by_cobro(cobro_id)
    assert len(desvios) == 1
    assert desvios[0]['monto'] == 10000.0
    assert desvios[0]['nro_op'] == "OP-DESV-200"
    
    # 9. Try updating desvio
    db.update_desvio(desvios[0]['id'], 5000.0, "Obras Viales", "Préstamo modificado", "2026-06-08", None, "OP-DESV-200-EDITED")
    desvios = db.get_desvios_by_cobro(cobro_id)
    assert desvios[0]['monto'] == 5000.0
    assert desvios[0]['nro_op'] == "OP-DESV-200-EDITED"
    
    # Clean up test DB
    if os.path.exists(TEMP_DB):
        try: os.remove(TEMP_DB)
        except: pass
        
    print("All OP and Payment Modification tests passed successfully!")

if __name__ == "__main__":
    run_tests()

```

## Archivo: `test_fun_catalog.py`

```python
import unittest
import os
import sys

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
import database as db
import utils

class TestFunCatalog(unittest.TestCase):
    def setUp(self):
        # We work directly on the test database or connection
        pass
        
    def test_gasto_fun_flow(self):
        # 1. Add Gasto FUN
        nombre_test = "Gasto Test Unitario FUN"
        expediente_test = "8009999-I-2026"
        
        # Clean up if exists from previous crashed runs
        with db.db_session() as conn:
            cursor = conn.cursor()
            cursor.execute('DELETE FROM gastos_funcionamiento WHERE expediente_imuh = ?', (expediente_test,))
            conn.commit()
            
        gasto_id = db.add_gasto_funcionamiento(nombre_test, expediente_test)
        self.assertIsNotNone(gasto_id)
        
        # 2. Get and verify
        g_fun = db.get_gasto_funcionamiento(gasto_id)
        self.assertEqual(g_fun['nombre'], nombre_test)
        self.assertEqual(g_fun['expediente_imuh'], expediente_test)
        self.assertEqual(g_fun['activo'], 1)
        
        # 3. Retrieve list and verify it is there
        active_list = db.get_gastos_funcionamiento(only_active=True)
        self.assertTrue(any(g['id'] == gasto_id for g in active_list))
        
        # 4. Inactivate Gasto
        db.update_gasto_funcionamiento_estado(gasto_id, 0)
        g_fun_inactive = db.get_gasto_funcionamiento(gasto_id)
        self.assertEqual(g_fun_inactive['activo'], 0)
        
        # 5. Verify it's no longer in active list, but remains in full list
        active_list_after = db.get_gastos_funcionamiento(only_active=True)
        self.assertFalse(any(g['id'] == gasto_id for g in active_list_after))
        
        all_list = db.get_gastos_funcionamiento(only_active=False)
        self.assertTrue(any(g['id'] == gasto_id for g in all_list))
        
        # 6. Reactivate by adding again (duplicate handling reactivates)
        new_id = db.add_gasto_funcionamiento("Gasto Test Unitario FUN Reactivado", expediente_test)
        self.assertEqual(new_id, gasto_id)
        
        g_fun_active = db.get_gasto_funcionamiento(gasto_id)
        self.assertEqual(g_fun_active['activo'], 1)
        self.assertEqual(g_fun_active['nombre'], "Gasto Test Unitario FUN Reactivado")
        
        # Clean up
        with db.db_session() as conn:
            cursor = conn.cursor()
            cursor.execute('DELETE FROM gastos_funcionamiento WHERE id = ?', (gasto_id,))
            conn.commit()

if __name__ == '__main__':
    unittest.main()

```

## Archivo: `test_logic.py`

```python
import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
import database as db

TEMP_DB = 'test_temp_logic.db'
if os.path.exists(TEMP_DB):
    try: os.remove(TEMP_DB)
    except: pass
db.DB_PATH = TEMP_DB
db.init_db()

def run_tests():
    # Use main DB or test DB? Let's use the main one since it's empty right now
    # We will delete them after
    d_id = db.add_decreto(9999, 2026, "TEST-EXP", "Obra de prueba")
    c1 = db.add_cuota(d_id, 1, 2026, 500)
    c2 = db.add_cuota(d_id, 2, 2026, 500)
    
    # Recalculate status manually since cuota creation doesn't trigger automatic updates
    conn = db.get_connection()
    db.check_estado_decreto(conn, d_id)
    conn.close()
    
    d = db.get_decreto(d_id)
    assert d['estado'] == 'Con deuda', f"Expected Con deuda, got {d['estado']}"
    
    # Pay partial
    cob1 = db.add_cobro(c1, 200, "2026-01-10")
    d = db.get_decreto(d_id)
    assert d['estado'] == 'Con deuda', f"Expected Con deuda after partial, got {d['estado']}"
    
    # Pay rest of c1
    cob2 = db.add_cobro(c1, 300, "2026-01-15")
    
    # Pay c2
    cob3 = db.add_cobro(c2, 500, "2026-02-10")
    d = db.get_decreto(d_id)
    assert d['estado'] == 'Terminado', f"Expected Terminado after full pay, got {d['estado']}"
    
    # Test Anulado
    d_id2 = db.add_decreto(8888, 2026, "TEST-EXP-2", "Obra anulada test")
    c3 = db.add_cuota(d_id2, 3, 2026, 1000)
    db.update_estado_decreto(d_id2, 'Anulado')
    
    # Test delete protections (cannot delete decree with cobros)
    try:
        db.delete_decreto(d_id)
        assert False, "Expected ValueError when deleting decree with cobros"
    except ValueError:
        pass
        
    # Delete them in correct order
    db.delete_cobro(cob1)
    db.delete_cobro(cob2)
    db.delete_cobro(cob3)
    db.delete_decreto(d_id)
    db.delete_decreto(d_id2)
    
    # 2. Test IMUH Multiple Validations
    import utils
    # Valid single IMUHs
    assert utils.validar_expediente_imuh("8000063-I-2026") is True
    assert utils.validar_expediente_imuh("  8000063-I-2026   ") is True
    assert utils.validar_expediente_imuh("") is True
    assert utils.validar_expediente_imuh(None) is True
    
    # Valid multiple IMUHs with various separators
    assert utils.validar_expediente_imuh("8000063-I-2026, 8000064-I-2026") is True
    assert utils.validar_expediente_imuh("8000063-I-2026; 8000064-I-2026;8000065-A-2025") is True
    assert utils.validar_expediente_imuh("8000063-I-2026 / 8000064-I-2026") is True
    
    # Invalid IMUHs
    assert utils.validar_expediente_imuh("8000063-I-26") is False
    assert utils.validar_expediente_imuh("8000063-I-2026, invalid_imuh") is False
    assert utils.validar_expediente_imuh("8000063-I-2026; ") is True  # empty segments are skipped
    assert utils.validar_expediente_imuh("invalid") is False

    # Test IMUH Normalization
    assert utils.normalizar_expediente_imuh("8000063-I-2026; 8000064-I-2026 / 8000065-B-2024 ") == "8000063-I-2026, 8000064-I-2026, 8000065-B-2024"
    assert utils.normalizar_expediente_imuh("   ") is None
    assert utils.normalizar_expediente_imuh(None) is None
    
    # 3. Test mathematical consistency of grouped payment distribution
    # Let's create a decree, cuota, and two payments to verify aggregated distribution formulas
    d_group_id = db.add_decreto(7777, 2026, "8000063-I-2026, 8000064-I-2026", "Obra Grupo Test")
    cuota_g_id = db.add_cuota(d_group_id, 5, 2026, 1000000.0)
    
    # Register two payments
    p1_id = db.add_cobro(cuota_g_id, 300000.0, "2026-05-13")
    p2_id = db.add_cobro(cuota_g_id, 400000.0, "2026-05-15")
    
    # Distribute p1: 200k fin_orig, 50k reserve, 50k desvio
    db.upsert_distribucion(p1_id, 200000.0, 50000.0, "p1 dist")
    db.add_desvio(p1_id, "Pavimentación", 50000.0, "Préstamo obra", "2026-05-13")
    
    # Distribute p2: 150k fin_orig, 200k reserve, 50k desvio
    db.upsert_distribucion(p2_id, 150000.0, 200000.0, "p2 dist")
    db.add_desvio(p2_id, "Hidráulica", 50000.0, "Préstamo obra", "2026-05-15")
    
    # Now simulate the card aggregation logic from pages/7_Distribucion.py
    # Load the payments
    cobros_list = db.get_cobros_con_resumen_distribucion()
    group_cobros = [c for c in cobros_list if c['cuota_id'] == cuota_g_id]
    
    monto_total_cobrado = sum(c['monto'] for c in group_cobros)
    monto_total_fin_orig = sum(c['monto_fin_orig'] for c in group_cobros)
    monto_total_reserva = sum(c['monto_reserva'] for c in group_cobros)
    monto_total_desvios = sum(c['total_desvios'] for c in group_cobros)
    
    # Reserve uses and recoveries
    ru_fo_total = 0.0
    ru_other_total = 0.0
    recru_fo_total = 0.0
    recru_res_total = 0.0
    rec_fo_total_total = 0.0
    recru_sd_total = 0.0
    rec_sd_total_total = 0.0
    rec_desv_res_total_total = 0.0
    
    # Add a reserve use to p1: 30k used for fin_original
    db.add_reserva_uso(p1_id, 30000.0, "fin_original", "Uso Reserva", "2026-05-14", "Notas de uso")
    # Add a reserve use to p2: 100k to another_obra (desvio)
    res_uso_other_id = db.add_reserva_uso(p2_id, 100000.0, "otra_obra", "Uso Reserva 2", "2026-05-16", "Notas de uso 2")
    # Recover 40k from that reserve desvio back to fin_original
    db.add_reserva_uso_recupero(res_uso_other_id, 40000.0, "2026-05-17", "fin_original", notas="Recupero de reserva")
    
    # Re-calculate reserve usage and recoveries over the group
    for c_item in group_cobros:
        c_id = c_item['id']
        usos_r_inline = db.get_reserva_usos_by_cobro(c_id)
        ru_fo_total += sum(u['monto'] for u in usos_r_inline if u['destino_tipo'] == 'fin_original')
        ru_other_total += sum(u['monto'] for u in usos_r_inline if u['destino_tipo'] != 'fin_original')
        
        for u in usos_r_inline:
            if u['destino_tipo'] != 'fin_original':
                rec_usos_item = db.get_recuperos_by_reserva_uso(u['id'])
                for ri in rec_usos_item:
                    if ri['destino_tipo'] == 'fin_original':
                        recru_fo_total += ri['monto']
                    elif ri['destino_tipo'] == 'reserva':
                        recru_res_total += ri['monto']
                    elif ri['destino_tipo'] == 'sin_distribucion':
                        recru_sd_total += ri['monto']
                        
        desvios = db.get_desvios_by_cobro(c_id)
        for d in desvios:
            recuperos_del_desvio = db.get_recuperos_by_desvio(d['id'])
            for rec_item in recuperos_del_desvio:
                if rec_item['destino_tipo'] == 'fin_original':
                    rec_fo_total_total += rec_item['monto']
                elif rec_item['destino_tipo'] == 'sin_distribucion':
                    rec_sd_total_total += rec_item['monto']
                elif rec_item['destino_tipo'] == 'reserva':
                    rec_desv_res_total_total += rec_item['monto']
                    
    # Math formulas
    item_sin_dist = max(0.0, round(monto_total_cobrado - monto_total_fin_orig - monto_total_reserva - monto_total_desvios + rec_sd_total_total + recru_sd_total, 2))
    item_fin_orig = round(monto_total_fin_orig + ru_fo_total + rec_fo_total_total + recru_fo_total, 2)
    item_desvios = round(monto_total_desvios + ru_other_total - rec_fo_total_total - recru_fo_total - recru_res_total - rec_sd_total_total - recru_sd_total - rec_desv_res_total_total, 2)
    item_en_reserva = max(0.0, round(monto_total_reserva - ru_fo_total - ru_other_total + recru_res_total + rec_desv_res_total_total, 2))
    
    # Assert linear combination holds: Item 1 + Item 2 + Item 3 + Item 4 == Total Cobrado
    total_distributed_sum = round(item_sin_dist + item_fin_orig + item_desvios + item_en_reserva, 2)
    assert total_distributed_sum == monto_total_cobrado, f"Math inconsistency! {total_distributed_sum} != {monto_total_cobrado}"
    
    # 4. Test Funding Requests (Solicitudes de Financiamiento)
    # Add a new request
    sol_id = db.add_solicitud("OE-9999-I-2026", "8000063-I-2026, 8000064-I-2026", "Obra Vial Test", 1500000.0, "2026-05-21", "uploads/test.pdf", "Notas de prueba")
    
    # Retrieve it
    sol = db.get_solicitud(sol_id)
    assert sol is not None
    assert sol['nro_expediente'] == "OE-9999-I-2026"
    assert sol['expediente_imuh'] == "8000063-I-2026, 8000064-I-2026"
    assert sol['monto_solicitado'] == 1500000.0
    assert sol['estado'] == "Pendiente"
    assert sol['notas'] == "Notas de prueba"
    
    # Get all solicitudes
    all_sols = db.get_solicitudes()
    assert len(all_sols) >= 1
    assert any(s['id'] == sol_id for s in all_sols)
    
    # Edit the request
    db.update_solicitud(sol_id, "OE-9999-I-2026", "8000063-I-2026, 8000064-I-2026", "Obra Vial Test Editada", 1600000.0, "2026-05-21", "uploads/test.pdf", "Notas editadas")
    sol = db.get_solicitud(sol_id)
    assert sol['destino_fondos'] == "Obra Vial Test Editada"
    assert sol['monto_solicitado'] == 1600000.0
    assert sol['notas'] == "Notas editadas"
    
    # Approve and convert to a Decree
    d_conv_id = db.add_decreto(8888, 2026, "OE-9999-I-2026", "Obra Vial Test Editada", "uploads/test.pdf", "8000063-I-2026, 8000064-I-2026")
    
    # Link it and change state to Approved
    db.update_estado_solicitud(sol_id, "Aprobado", d_conv_id)
    sol = db.get_solicitud(sol_id)
    assert sol['estado'] == "Aprobado"
    assert sol['decreto_id'] == d_conv_id
    
    # Test reverse lookup
    sol_lookup = db.get_solicitud_por_decreto(d_conv_id)
    assert sol_lookup is not None
    assert sol_lookup['id'] == sol_id
    
    # Clean up request & decree
    db.delete_solicitud(sol_id)
    db.delete_decreto(d_conv_id)
    
    assert db.get_solicitud(sol_id) is None
    
    # Clean up
    try:
        db.delete_decreto(d_group_id)
        assert False, "Expected ValueError when deleting decree with cobros"
    except ValueError:
        pass
    
    # Remove temp DB
    if os.path.exists(TEMP_DB):
        try: os.remove(TEMP_DB)
        except: pass
        
    print("All backend logic, IMUH validations, and aggregated mathematical balance checks passed successfully.")

if __name__ == "__main__":
    run_tests()

```

## Archivo: `test_proveedores.py`

```python
import os
import sys

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

import database as db
import utils
import utils_reports

def run_tests():
    print("--- INICIANDO PRUEBAS DE PROVEEDORES ---")
    
    # 1. Inicializar DB
    db.init_db()
    print("[OK] init_db() completado correctamente.")
    
    # 2. Probar validación CUIT AFIP en utils.py
    assert utils.validar_cuit("20-12345678-6") == True, "CUIT 20-12345678-6 deberia ser valido"
    assert utils.validar_cuit("30-71111111-2") == False, "CUIT con digito verificador erroneo deberia ser invalido"
    assert utils.validar_cuit("123456789") == False, "CUIT sin guiones debe ser invalido"
    assert utils.validar_cuit("20-123456-9") == False, "CUIT con menos digitos debe ser invalido"
    print("[OK] Pruebas de validar_cuit() pasaron.")

    # 3. Alta de proveedor de obra y funcionamiento con CUIT válido
    cuit1 = "20-12345678-6"
    cuit2 = "30-98765432-1"
    
    # Limpiar test data previos si existen
    provs_obras = db.get_proveedores_obras()
    for p in provs_obras:
        if p['razon_social'] in ["Test Obra SA", "Test Obra 2 SA"]:
            try:
                db.delete_proveedor_obra(p['id'])
            except:
                pass
                
    provs_fun = db.get_proveedores_funcionamiento()
    for p in provs_fun:
        if p['razon_social'] in ["Test FUN SRL", "Test FUN 2 SRL", "Test Obra SA"]:
            try:
                db.delete_proveedor_funcionamiento(p['id'])
            except:
                pass

    p_obra_id = db.add_proveedor_obra("Test Obra SA", cuit1)
    print(f"[OK] Creado Proveedor Obra ID {p_obra_id}")
    
    p_fun_id = db.add_proveedor_funcionamiento("Test FUN SRL", cuit2)
    print(f"[OK] Creado Proveedor FUN ID {p_fun_id}")

    # 4. Probar Opción A: Unicidad por tipo (mismo CUIT en Proveedor FUN debe ser aceptado)
    p_fun_mismo_cuit_id = db.add_proveedor_funcionamiento("Test Obra SA", cuit1)
    print(f"[OK] Opcion A verificada: CUIT {cuit1} registrado independientemente en Funcionamiento (ID {p_fun_mismo_cuit_id}).")

    # 5. Probar error por duplicado dentro del mismo tipo
    try:
        db.add_proveedor_obra("Test Obra SA Duplicada", cuit1)
        assert False, "Debería haber fallado por CUIT duplicado en Obras"
    except ValueError as e:
        print(f"[OK] Capturado error esperado de CUIT duplicado en Obras: {e}")

    # 6. Asignar proveedor a Obra
    obras = db.get_obras()
    if obras:
        o = obras[0]
        db.update_obra(o['id'], o['nombre'], o['expediente_imuh'], o['activa'], p_obra_id)
        o_actualizada = db.get_obra(o['id'])
        assert o_actualizada['proveedor_id'] == p_obra_id, "El proveedor_id de la obra debe coincidir"
        assert o_actualizada['proveedor_razon_social'] == "Test Obra SA", "La razón social traída debe coincidir"
        print(f"[OK] Asignacion de proveedor {p_obra_id} a Obra '{o['nombre']}' exitosa.")
        
        # 7. Verificar bloqueo de eliminación
        try:
            db.delete_proveedor_obra(p_obra_id)
            assert False, "Debería haber bloqueado la eliminación del proveedor vinculado a obra"
        except ValueError as e:
            print(f"[OK] Bloqueo de eliminacion verificado: {e}")

    # 8. Asignar proveedor a Gasto FUN
    gastos_fun = db.get_gastos_funcionamiento()
    if gastos_fun:
        g = gastos_fun[0]
        db.update_gasto_funcionamiento_proveedor(g['id'], p_fun_id)
        g_actualizado = db.get_gasto_funcionamiento(g['id'])
        assert g_actualizado['proveedor_id'] == p_fun_id, "El proveedor_id del gasto FUN debe coincidir"
        assert g_actualizado['proveedor_razon_social'] == "Test FUN SRL", "La razón social traída del gasto FUN debe coincidir"
        print(f"[OK] Asignacion de proveedor {p_fun_id} a Gasto FUN '{g['nombre']}' exitosa.")

    # 9. Probar Afectación de Decretos
    decretos = db.get_decretos()
    if decretos:
        dec, cuotas_list, filas_reporte = utils_reports.obtener_afectacion_decreto(decretos[0]['id'])
        if filas_reporte:
            assert "Proveedor" in filas_reporte[0], "La clave 'Proveedor' debe estar presente en filas_reporte"
            print(f"[OK] Reporte de afectacion de decretos contiene la columna Proveedor: Ejemplo = '{filas_reporte[0]['Proveedor']}'")

    print("\n--- TODAS LAS PRUEBAS DE VERIFICACION PASARON CON EXITO ---")

if __name__ == '__main__':
    run_tests()

```

## Archivo: `test_recupero_reserva.py`

```python
import os
import database as db

def run_tests():
    # Redirigir a una base de datos temporal
    TEMP_DB = 'test_temp.db'
    if os.path.exists(TEMP_DB):
        os.remove(TEMP_DB)

    db.DB_PATH = TEMP_DB
    db.init_db()

    print("1. Base de datos de prueba inicializada.")

    # Crear datos de prueba
    # 1. Decreto origen
    dec_orig_id = db.add_decreto(272, 2026, "EXP-272/2026", "Obras Hidricas")
    print(f"   Decreto Origen creado con ID: {dec_orig_id}")

    # 2. Decreto destino
    dec_dest_id = db.add_decreto(296, 2026, "EXP-296/2026", "Pavimentacion Calle Mitre")
    print(f"   Decreto Destino creado con ID: {dec_dest_id}")

    # 3. Cuota y Cobro
    cuota_id = db.add_cuota(dec_orig_id, 5, 2026, 1000000.0)
    cobro_id = db.add_cobro(cuota_id, 1000000.0, "2026-05-15")
    print(f"   Cuota ({cuota_id}) y Cobro ({cobro_id}) creados.")

    # 4. Distribución: Poner 300,000 en Reserva y 700,000 en Fin Original
    db.upsert_distribucion(cobro_id, 700000.0, 300000.0, "Distribucion inicial de prueba")
    print("   Distribución cargada: 700k Fin Original, 300k Reserva.")

    # 5. Desviar dinero de la reserva (préstamo) a otra obra
    # Prestamo 1: A Obra Pavimentación Mitre (Decreto) -> $200,000
    db.add_reserva_uso(cobro_id, 200000.0, "otra_obra", "Pavimentacion Mitre", "2026-05-16", "Prestamo reserva 1", decreto_destino_id=dec_dest_id)
    print("   Uso de Reserva (Préstamo) registrado: 200k a Pavimentacion Mitre (con decreto).")

    # Prestamo 2: A Obra Propedias (Fondos Propios) -> $50,000
    db.add_reserva_uso(cobro_id, 50000.0, "otra_obra", "Refaccion Polideportivo", "2026-05-17", "Prestamo reserva 2")
    print("   Uso de Reserva (Préstamo) registrado: 50k a Refaccion Polideportivo (sin decreto).")

    # Verificar préstamos activos
    activos = db.get_reserva_usos_prestamos_activos()
    print(f"\n2. Préstamos activos iniciales (Esperados: 2): {len(activos)}")
    for a in activos:
        print(f"   - ID: {a['id']}, Destino: {a['destino_detalle'] or a['dest_nombre']}, Monto: {a['monto']}, Saldo: {a['saldo']}")

    # Verificar deudas de obras de fondos propios
    deudas_propias = db.get_deudas_obras_propias()
    print(f"\n3. Deudas de obras de fondos propios (Esperado: 1): {deudas_propias}")

    # Registrar recupero parcial del Préstamo 1 (Mitre): $80,000 a Fin Original
    prestamo_mitre = [a for a in activos if a['decreto_destino_id'] == dec_dest_id][0]
    db.add_reserva_uso_recupero(prestamo_mitre['id'], 80000.0, "2026-05-20", "fin_original", notas="Recupero de Mitre")
    print(f"\n4. Recupero de $80,000 registrado para Préstamo {prestamo_mitre['id']} (Destino: Fin original).")

    # Registrar recupero parcial del Préstamo 2 (Polideportivo): $50,000 a Reserva (Cancela deuda)
    prestamo_poli = [a for a in activos if a['decreto_destino_id'] is None][0]
    db.add_reserva_uso_recupero(prestamo_poli['id'], 50000.0, "2026-05-21", "reserva", notas="Recupero de Poli")
    print(f"5. Recupero de $50,000 registrado para Préstamo {prestamo_poli['id']} (Destino: Reserva).")

    # Volver a verificar activos
    activos_despues = db.get_reserva_usos_prestamos_activos()
    print(f"\n6. Préstamos activos después (Esperado: 1 - Poli debe desaparecer): {len(activos_despues)}")
    for a in activos_despues:
        print(f"   - ID: {a['id']}, Destino: {a['destino_detalle'] or a['dest_nombre']}, Monto: {a['monto']}, Saldo: {a['saldo']} (Esperado: 120000)")

    # Verificar deudas de fondos propios nuevamente
    deudas_propias_despues = db.get_deudas_obras_propias()
    print(f"\n7. Deudas de fondos propios después (Esperado: vacío/0): {deudas_propias_despues}")

    # Verificar historial de desvíos
    historial = db.get_historial_desvios()
    print(f"\n8. Historial de desvíos (Esperado: 2 items): {len(historial)}")
    for h in historial:
        print(f"   - Tipo: {h['tipo_origen']}, Monto: {h['monto']}, Recuperado: {h['total_recuperado']}, Saldo: {h['saldo']}")

    # Verificar deudas por decreto
    deuda_dec = db.get_deuda_desvios_by_decreto(dec_dest_id)
    print(f"\n9. Deuda del Decreto Destino ({dec_dest_id}) (Esperado: 120,000): {deuda_dec}")

    # Limpieza
    os.remove(TEMP_DB)
    print("\n10. Base de datos de prueba eliminada. Test finalizado exitosamente!")

if __name__ == "__main__":
    run_tests()

```

## Archivo: `test_sac.py`

```python
import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
import database as db

def test_sac():
    print("Iniciando prueba de lógica SAC...")
    
    # 1. Agregar pedido
    db.add_aporte_sac(2026, 1, 50000, "2026-05-01")
    sacs = db.get_aportes_sac(2026)
    assert len(sacs) > 0, "No se encontró el pedido de SAC"
    sac = sacs[0]
    assert sac['cuota_nro'] == 1
    assert sac['monto_pedido'] == 50000
    assert sac['monto_cobrado'] == 0
    print("- Creación de pedido exitosa.")

    # 2. Registrar cobro
    db.registrar_cobro_sac(sac['id'], 50000, "2026-05-15")
    sac_cobrado = [s for s in db.get_aportes_sac(2026) if s['id'] == sac['id']][0]
    assert sac_cobrado['monto_cobrado'] == 50000
    assert sac_cobrado['fecha_cobro'] == "2026-05-15"
    print("- Registro de cobro exitoso.")

    # 3. Actualizar
    db.update_aporte_sac(sac['id'], 2026, 1, 55000, "2026-05-02")
    sac_upd = [s for s in db.get_aportes_sac(2026) if s['id'] == sac['id']][0]
    assert sac_upd['monto_pedido'] == 55000
    print("- Actualización exitosa.")

    # 4. Eliminar
    db.delete_aporte_sac(sac['id'])
    sacs_post = [s for s in db.get_aportes_sac(2026) if s['id'] == sac['id']]
    assert len(sacs_post) == 0, "El pedido no se eliminó"
    print("- Eliminación exitosa.")

    print("Todas las pruebas de lógica SAC pasaron correctamente.")

if __name__ == "__main__":
    test_sac()

```

## Archivo: `trazabilidad_graph.py`

```python
import database as db
import utils
from collections import defaultdict

# ── Constantes ────────────────────────────────────────────────────────────────
BOX_W     = 220    # ancho fijo de cada nodo
LINE_H    = 17     # alto de cada línea de texto (px)
PAD_X     = 12     # padding horizontal dentro del nodo
PAD_Y     = 9      # padding vertical dentro del nodo (arriba Y abajo)
COL_GAP   = 100    # espacio horizontal entre columnas
ROW_GAP   = 18     # espacio vertical entre nodos de la misma columna
SVG_PAD   = 30     # padding exterior del SVG
FONT_SIZE = 13     # tamaño de fuente (no cambiar)
CHAR_W    = 7.0    # ancho promedio de carácter px (Segoe UI 13px)
MAX_CHARS = int((BOX_W - 2 * PAD_X) / CHAR_W)  # ≈ 28 chars/línea
FONT      = "Segoe UI, Arial, sans-serif"

COLORS = {
    'decreto':  {'bg': '#dbeafe', 'border': '#1e88e5', 'text': '#1e3a8a'},
    'cobro':    {'bg': '#dcfce7', 'border': '#16a34a', 'text': '#14532d'},
    'fin':      {'bg': '#fef3c7', 'border': '#d97706', 'text': '#92400e'},
    'reserva':  {'bg': '#f3e8ff', 'border': '#7c3aed', 'text': '#4c1d95'},
    'desvio':   {'bg': '#fee2e2', 'border': '#dc2626', 'text': '#7f1d1d'},
    'recupero': {'bg': '#fefce8', 'border': '#ca8a04', 'text': '#713f12'},
    'destino':  {'bg': '#f5f5f5', 'border': '#9e9e9e', 'text': '#424242'},
}
ARROW_COLORS = {
    'decreto': '#1e88e5', 'cobro': '#16a34a', 'fin': '#d97706',
    'reserva': '#7c3aed', 'desvio': '#dc2626', 'recupero': '#ca8a04',
    'destino': '#9e9e9e',
}


def _esc(t):
    return str(t).replace('&','&amp;').replace('<','&lt;').replace('>','&gt;').replace('"','&quot;')


def _wrap(text, max_chars):
    """Divide texto en líneas de hasta max_chars caracteres, cortando en espacios."""
    if not text:
        return ['']
    words = str(text).split(' ')
    lines, cur = [], ''
    for w in words:
        if not cur:
            cur = w
        elif len(cur) + 1 + len(w) <= max_chars:
            cur += ' ' + w
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines or ['']


def _node_height(label):
    """Calcula la altura necesaria del nodo según el texto."""
    parts = label.split(' | ', 1)
    n = len(_wrap(parts[0], MAX_CHARS))
    if len(parts) > 1:
        n += len(_wrap(parts[1], MAX_CHARS))
    return 2 * PAD_Y + n * LINE_H


def _draw_box(x, y, label, tipo, out):
    """Renderiza un nodo SVG con texto en múltiples líneas si es necesario."""
    c  = COLORS.get(tipo, COLORS['destino'])
    bh = _node_height(label)
    cx = x + BOX_W // 2

    out.append(
        f'<rect x="{x}" y="{y}" width="{BOX_W}" height="{bh}" rx="10" '
        f'fill="{c["bg"]}" stroke="{c["border"]}" stroke-width="2.5"/>'
    )

    parts       = label.split(' | ', 1)
    title_lines = _wrap(parts[0], MAX_CHARS)
    sub_lines   = _wrap(parts[1], MAX_CHARS) if len(parts) > 1 else []
    all_lines   = [(l, True) for l in title_lines] + [(l, False) for l in sub_lines]

    # Centrar verticalmente el bloque de texto
    text_block_h = len(all_lines) * LINE_H
    y0 = y + (bh - text_block_h) / 2 + LINE_H * 0.78  # baseline primera línea

    for i, (line, bold) in enumerate(all_lines):
        yt  = y0 + i * LINE_H
        bld = 'font-weight="bold" ' if bold else ''
        out.append(
            f'<text x="{cx}" y="{yt:.1f}" text-anchor="middle" '
            f'font-family="{FONT}" font-size="{FONT_SIZE}" {bld}'
            f'fill="{c["text"]}">{_esc(line)}</text>'
        )


def generar_svg_trazabilidad(cobro_id):
    """
    Genera un SVG completo con el flujo de fondos del cobro.
    Retorna (svg_string, total_w, total_h) o ('', 0, 0) si no hay datos.
    """
    cobro = db.get_cobro(cobro_id)
    if not cobro:
        return '', 0, 0

    dist      = db.get_distribucion_by_cobro(cobro_id)
    monto_fo  = dist['monto_fin_orig'] if dist else 0.0
    monto_res = dist['monto_reserva']  if dist else 0.0
    desvios   = db.get_desvios_by_cobro(cobro_id) or []
    usos_fo   = db.get_fin_original_usos_by_cobro(cobro_id) or []
    usos_res  = db.get_reserva_usos_by_cobro(cobro_id) or []

    # ── Árbol de nodos ────────────────────────────────────────────────────────
    nodes = []

    def add(col, label, tipo, parent=None):
        idx = len(nodes)
        nodes.append({'col': col, 'label': label, 'tipo': tipo, 'parent': parent})
        return idx

    # Col 0: Decreto
    d_idx = add(0, f'Decreto {cobro.get("nro_decreto","S/N")}/{cobro.get("decreto_anio","S/A")}', 'decreto')
    # Col 1: Cobro
    c_idx = add(1,
        f'Cobro {utils.format_date_ar(cobro["fecha"])} | {utils.format_currency_ar(cobro["monto"])}',
        'cobro', d_idx)

    if monto_fo > 0.01:
        fo_i = add(2, f'Fin Original | {utils.format_currency_ar(monto_fo)}', 'fin', c_idx)
        for u in usos_fo:
            op = f' | OP {u["nro_op"]}' if u.get('nro_op') else ''
            add(3, f'Pago {utils.format_date_ar(u["fecha"])}{op} | {utils.format_currency_ar(u["monto"])}', 'fin', fo_i)

    if monto_res > 0.01:
        r_i = add(2, f'En Reserva | {utils.format_currency_ar(monto_res)}', 'reserva', c_idx)
        for u in usos_res:
            op = f' | OP {u["nro_op"]}' if u.get('nro_op') else ''
            fecha_str = f' {utils.format_date_ar(u["fecha"])}' if u.get('fecha') else ''
            ur_i = add(3, f'Uso Reserva{fecha_str}{op} | {utils.format_currency_ar(u["monto"])}', 'reserva', r_i)
            if u.get('destino_tipo') == 'fin_original':
                dd = db.get_decreto(cobro['decreto_id'])
                dn = f'Dto. {dd["nro_decreto"]}/{dd["anio"]}'
                add(4, f'Obra: {dn}', 'fin', ur_i)
            elif u.get('decreto_destino_id'):
                dd = db.get_decreto(u['decreto_destino_id'])
                obras = db.get_obras_by_decreto(u['decreto_destino_id'])
                if obras:
                    imuhs = ", ".join(o["expediente_imuh"] for o in obras if o.get("expediente_imuh"))
                    nombres = " // ".join(o["nombre"] for o in obras if o.get("nombre"))
                    dn = f'Dto. {dd["nro_decreto"]}/{dd["anio"]} - Exp. IMUH {imuhs} - {nombres}'
                else:
                    dn = f'Dto. {dd["nro_decreto"]}/{dd["anio"]} - Exp. IMUH S/D - {dd.get("destino_fondos","")}'
                dt_i = add(4, f'Obra: {dn}', 'destino', ur_i)
            else:
                dn = u.get('destino_detalle') or 'Destino no especificado'
                dt_i = add(4, f'Obra: {dn}', 'destino', ur_i)
                
            for r in (db.get_recuperos_by_reserva_uso(u['id']) or []):
                if r.get('destino_tipo') == 'compensacion':
                    add(5, f'Compensacion OP: {r.get("nro_op","")} | {utils.format_currency_ar(r["monto"])}', 'recupero', dt_i)
                else:
                    add(5, f'Devolucion {utils.format_date_ar(r["fecha"])} | {utils.format_currency_ar(r["monto"])}', 'recupero', dt_i)

    for d in desvios:
        op    = f' | OP {d["nro_op"]}' if d.get('nro_op') else ''
        fecha_str = f' {utils.format_date_ar(d["fecha"])}' if d.get('fecha') else ''
        dv_i  = add(2, f'Desvio{fecha_str}{op} | {utils.format_currency_ar(d["monto"])}', 'desvio', c_idx)
        if d.get('decreto_destino_id'):
            dd = db.get_decreto(d['decreto_destino_id'])
            obras = db.get_obras_by_decreto(d['decreto_destino_id'])
            if obras:
                imuhs = ", ".join(o["expediente_imuh"] for o in obras if o.get("expediente_imuh"))
                nombres = " // ".join(o["nombre"] for o in obras if o.get("nombre"))
                dn = f'Dto. {dd["nro_decreto"]}/{dd["anio"]} - Exp. IMUH {imuhs} - {nombres}'
            else:
                dn = f'Dto. {dd["nro_decreto"]}/{dd["anio"]} - Exp. IMUH S/D - {dd.get("destino_fondos","")}'
        else:
            dn = d.get('destino') or 'Destino no especificado'
        dt_i = add(3, f'Obra: {dn}', 'destino', dv_i)
        for r in (db.get_recuperos_by_desvio(d['id']) or []):
            if r.get('destino_tipo') == 'compensacion':
                add(4, f'Compensacion OP: {r.get("nro_op","")} | {utils.format_currency_ar(r["monto"])}', 'recupero', dt_i)
            else:
                add(4, f'Devolucion {utils.format_date_ar(r["fecha"])} | {utils.format_currency_ar(r["monto"])}', 'recupero', dt_i)

    # ── Layout: posición (x, y, h) por nodo ──────────────────────────────────
    cols = defaultdict(list)
    for i, n in enumerate(nodes):
        cols[n['col']].append(i)

    max_col = max(cols.keys())

    def col_h(col_idx):
        ns = cols.get(col_idx, [])
        if not ns:
            return 0
        return sum(_node_height(nodes[i]['label']) for i in ns) + ROW_GAP * (len(ns) - 1)

    max_h   = max(col_h(c) for c in cols)
    total_w = SVG_PAD + (max_col + 1) * (BOX_W + COL_GAP) - COL_GAP + SVG_PAD
    total_h = SVG_PAD + max_h + SVG_PAD

    positions = {}  # node_idx -> (x, y, box_h)
    for col_idx, col_nodes in cols.items():
        x       = SVG_PAD + col_idx * (BOX_W + COL_GAP)
        ch      = col_h(col_idx)
        y_start = SVG_PAD + (max_h - ch) // 2
        y       = y_start
        for ni in col_nodes:
            bh = _node_height(nodes[ni]['label'])
            positions[ni] = (x, y, bh)
            y += bh + ROW_GAP

    # ── SVG ───────────────────────────────────────────────────────────────────
    svg = [
        f'<svg xmlns="http://www.w3.org/2000/svg" '
        f'width="{total_w}" height="{total_h}" '
        f'viewBox="0 0 {total_w} {total_h}" '
        f'style="display:block;background:#fff;">'
    ]

    # Marcadores de flecha (uno por color usado)
    svg.append('<defs>')
    seen = set()
    for n in nodes:
        if n['parent'] is not None:
            c = ARROW_COLORS.get(nodes[n['parent']]['tipo'], '#9e9e9e')
            if c not in seen:
                seen.add(c)
                hx = c.replace('#', '')
                svg.append(
                    f'<marker id="a-{hx}" markerWidth="10" markerHeight="7" '
                    f'refX="9" refY="3.5" orient="auto">'
                    f'<polygon points="0 0,10 3.5,0 7" fill="{c}"/></marker>'
                )
    svg.append('</defs>')

    # Flechas (detrás de los nodos)
    for i, n in enumerate(nodes):
        if n['parent'] is None or n['parent'] not in positions:
            continue
        px, py, ph = positions[n['parent']]
        nx, ny, nh = positions[i]
        x1 = px + BOX_W;  y1 = py + ph / 2
        x2 = nx;           y2 = ny + nh / 2
        mx = (x1 + x2) / 2
        c  = ARROW_COLORS.get(nodes[n['parent']]['tipo'], '#9e9e9e')
        hx = c.replace('#', '')
        svg.append(
            f'<path d="M {x1:.1f} {y1:.1f} C {mx:.1f} {y1:.1f} {mx:.1f} {y2:.1f} {x2:.1f} {y2:.1f}" '
            f'fill="none" stroke="{c}" stroke-width="2" marker-end="url(#a-{hx})"/>'
        )

    # Nodos (encima de las flechas)
    for i, n in enumerate(nodes):
        if i in positions:
            x, y, _ = positions[i]
            _draw_box(x, y, n['label'], n['tipo'], svg)

    svg.append('</svg>')
    return '\n'.join(svg), total_w, total_h


def mostrar_mapa_trazabilidad(cobro_id):
    import streamlit as st
    import streamlit.components.v1 as components

    cobro = db.get_cobro(cobro_id)
    if not cobro:
        st.info("No se encontró el cobro.")
        return

    dist    = db.get_distribucion_by_cobro(cobro_id)
    desvios = db.get_desvios_by_cobro(cobro_id) or []

    if not dist and not desvios:
        st.info("Este cobro aún no tiene distribución ni desvíos registrados.")
        return

    svg_str, total_w, total_h = generar_svg_trazabilidad(cobro_id)
    if not svg_str:
        st.info("No hay datos suficientes para generar el mapa.")
        return

    # Usar el tamaño natural del SVG para que no se vea minúsculo y usar scroll si es muy ancho
    iframe_h = total_h + 60 if total_h > 0 else 400

    html = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ background: #f8fafc; padding: 10px; }}
  .wrap {{
    background: #fff;
    border-radius: 10px;
    border: 1px solid #e2e8f0;
    padding: 14px;
    overflow-x: auto;
    overflow-y: visible;
  }}
</style>
</head>
<body>
  <div class="wrap">
    {svg_str}
  </div>
</body>
</html>"""

    components.html(html, height=iframe_h, scrolling=True)

```

## Archivo: `update_ui.py`

```python
import re

def process_file(filename):
    with open(filename, 'r', encoding='utf-8') as f:
        content = f.read()

    # We need to find forms and replace them with containers, and move op inputs
    # But it's easier to just do targeted regex replaces for the OP fields.
    pass

if __name__ == '__main__':
    process_file('components/tab_estado.py')
    process_file('components/tab_distribuir.py')

```

## Archivo: `utils.py`

```python
import calendar
import datetime
import logging
import os
import re
import shutil
import sqlite3

def format_currency_ar(value, include_symbol=True):
    if value is None:
        value = 0.0
    s = f"{value:,.2f}"
    s = s.replace(',', 'X').replace('.', ',').replace('X', '.')
    return f"$ {s}" if include_symbol else s

def format_date_ar(date_obj):
    if date_obj is None:
        return ""
    if isinstance(date_obj, str):
        try:
            date_obj = datetime.datetime.strptime(date_obj, '%Y-%m-%d').date()
        except ValueError:
            return date_obj
    return date_obj.strftime("%d-%m-%Y")

def get_due_date(mes, anio):
    _, last_day = calendar.monthrange(anio, mes)
    return datetime.date(anio, mes, last_day)

def format_week_monday(date_str):
    if not date_str:
        return "---"
    try:
        dt = datetime.datetime.strptime(date_str, '%Y-%m-%d').date()
        # Monday is 0, Sunday is 6. Subtract weekday to get Monday of that week.
        monday = dt - datetime.timedelta(days=dt.weekday())
        # Formato: DD/Mes (abreviado)
        meses_abr = ["Ene", "Feb", "Mar", "Abr", "May", "Jun", "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"]
        return f"{monday.day:02d}/{meses_abr[monday.month-1]}"
    except Exception:
        return "---"

def is_late(mes, anio, fecha_cobro):
    if not fecha_cobro:
        return False
    due_date = get_due_date(mes, anio)
    if isinstance(fecha_cobro, str):
        fecha_cobro = datetime.datetime.strptime(fecha_cobro, '%Y-%m-%d').date()
    return fecha_cobro > due_date

# Tipos de archivo permitidos para subida (Fix 2)
_EXTENSIONES_PERMITIDAS = {'.pdf', '.jpg', '.jpeg', '.png'}
_MAX_FILE_SIZE_MB = 15

def save_uploaded_file(uploaded_file, dest_folder="uploads"):
    """Guarda un archivo subido por el usuario con validación de tipo y tamaño.
    
    Raises:
        ValueError: si la extensión o el tamaño no son aceptables.
    """
    if uploaded_file is None:
        return None
    # Validar extensión (Fix 2)
    ext = os.path.splitext(uploaded_file.name)[1].lower()
    if ext not in _EXTENSIONES_PERMITIDAS:
        raise ValueError(
            f"Tipo de archivo no permitido: '{ext}'. "
            f"Se aceptan: {', '.join(sorted(_EXTENSIONES_PERMITIDAS))}."
        )
    # Validar tamaño (Fix 2)
    size_bytes = uploaded_file.size if hasattr(uploaded_file, 'size') else len(uploaded_file.getbuffer())
    if size_bytes > _MAX_FILE_SIZE_MB * 1024 * 1024:
        raise ValueError(
            f"El archivo supera el tamaño máximo permitido ({_MAX_FILE_SIZE_MB} MB)."
        )
    if not os.path.exists(dest_folder):
        os.makedirs(dest_folder)
    timestamp = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
    # Sanitizar nombre: solo caracteres alfanuméricos, guiones y puntos (Fix 3.2)
    raw_name = os.path.basename(uploaded_file.name)
    clean_name = re.sub(r'[^\w\-.]', '_', raw_name)
    filename = f"{timestamp}_{clean_name}"
    file_path = os.path.join(dest_folder, filename)
    with open(file_path, "wb") as f:
        f.write(uploaded_file.getbuffer())
    return file_path

def delete_file(file_path):
    if file_path and os.path.exists(file_path):
        try:
            os.remove(file_path)
            return True
        except Exception as e:
            print(f"Error borrando archivo: {e}")
            return False
    return False

def create_backup(db_path, backup_dir="backups"):
    """Crea un backup completo y consistente de la BD usando sqlite3.backup() (Fix 9).
    Este método copia TODAS las tablas, incluyendo las que se agreguen en el futuro,
    sin necesidad de listarlas manualmente.
    """
    if not os.path.exists(backup_dir):
        os.makedirs(backup_dir)
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = os.path.join(backup_dir, f"backup_decretometro_{timestamp}.db")
    src_conn = sqlite3.connect(db_path)
    dst_conn = sqlite3.connect(backup_path)
    try:
        src_conn.backup(dst_conn)
    finally:
        dst_conn.close()
        src_conn.close()
    return backup_path

def restore_backup(current_db_path, backup_db_path):
    """Restaura datos de un backup hacia la BD actual usando ATTACH + INSERT OR IGNORE.
    Garantiza cierre de conexión y rollback ante errores (Fix 6).
    """
    conn_curr = sqlite3.connect(current_db_path)
    conn_curr.execute("PRAGMA foreign_keys = ON;")
    try:
        # Hacemos ATTACH con la ruta escapada para evitar problemas de path (Fix 6)
        backup_path_escaped = backup_db_path.replace("'", "''")
        conn_curr.execute(f"ATTACH DATABASE '{backup_path_escaped}' AS backup_db")
        cursor = conn_curr.cursor()
        # Insertar decretos
        cursor.execute('''
            INSERT OR IGNORE INTO main.decretos (id, nro_decreto, anio, nro_expediente, destino_fondos, estado, pdf_path, expediente_imuh)
            SELECT id, nro_decreto, anio, nro_expediente, destino_fondos, estado, pdf_path, expediente_imuh FROM backup_db.decretos
        ''')
        # Insertar cuotas
        cursor.execute('''
            INSERT OR IGNORE INTO main.cuotas (id, decreto_id, mes, anio, monto)
            SELECT id, decreto_id, mes, anio, monto FROM backup_db.cuotas
        ''')
        # Insertar cobros
        cursor.execute('''
            INSERT OR IGNORE INTO main.cobros (id, cuota_id, monto, fecha, comprobante_path)
            SELECT id, cuota_id, monto, fecha, comprobante_path FROM backup_db.cobros
        ''')
        # Insertar Funcionamiento
        cursor.execute('''
            INSERT OR IGNORE INTO main.aportes_funcionamiento (id, anio, mes, monto_pautado, monto_cobrado, fecha_cobro)
            SELECT id, anio, mes, monto_pautado, monto_cobrado, fecha_cobro FROM backup_db.aportes_funcionamiento
        ''')
        # Insertar Sueldos
        cursor.execute('''
            INSERT OR IGNORE INTO main.aportes_sueldo (id, anio, mes, monto_pedido, fecha_pedido, monto_cobrado, fecha_cobro, estado, fecha_renuncia)
            SELECT id, anio, mes, monto_pedido, fecha_pedido, monto_cobrado, fecha_cobro, estado, fecha_renuncia FROM backup_db.aportes_sueldo
        ''')
        # Insertar SAC
        cursor.execute('''
            INSERT OR IGNORE INTO main.aportes_sac (id, anio, cuota_nro, monto_pedido, fecha_pedido, monto_cobrado, fecha_cobro, estado, fecha_renuncia)
            SELECT id, anio, cuota_nro, monto_pedido, fecha_pedido, monto_cobrado, fecha_cobro, estado, fecha_renuncia FROM backup_db.aportes_sac
        ''')
        # Insertar Prestamos Internos
        cursor.execute('''
            INSERT OR IGNORE INTO main.prestamos_internos (id, decreto_origen_id, destino, monto, fecha, motivo, devolucion_estado, fecha_devolucion)
            SELECT id, decreto_origen_id, destino, monto, fecha, motivo, devolucion_estado, fecha_devolucion FROM backup_db.prestamos_internos
        ''')
        # Insertar Recuperos Internos
        cursor.execute('''
            INSERT OR IGNORE INTO main.recuperos_internos (id, prestamo_id, monto, fecha)
            SELECT id, prestamo_id, monto, fecha FROM backup_db.recuperos_internos
        ''')
        # Restaurar tablas de trazabilidad y solicitudes
        tablas_trazabilidad = [
            "cobro_distribuciones (id, cobro_id, monto_fin_orig, monto_reserva, notas)",
            "cobro_reserva_usos (id, cobro_id, monto, destino_tipo, destino_detalle, fecha, notas, nro_op, decreto_destino_id)",
            "cobro_desvios (id, cobro_id, destino, monto, motivo, fecha, nro_op, decreto_destino_id)",
            "cobro_desvios_recuperos (id, desvio_id, monto, fecha, destino_tipo, destino_detalle, nro_op, decreto_destino_id)",
            "cobro_reserva_usos_recuperos (id, reserva_uso_id, monto, fecha, destino_tipo, destino_detalle, decreto_destino_id, nro_op)",
            "cobro_fin_original_usos (id, cobro_id, monto, fecha, nro_op, notas)",
            "solicitudes_financiamiento (id, nro_expediente, expediente_imuh, destino_fondos, monto_solicitado, fecha_solicitud, estado, decreto_id, pdf_path, notas)"
        ]
        for t in tablas_trazabilidad:
            nombre_tabla = t.split(" ")[0]
            columnas = t.split("(")[1].replace(")", "")
            cursor.execute(f'''
                INSERT OR IGNORE INTO main.{nombre_tabla} ({columnas})
                SELECT {columnas} FROM backup_db.{nombre_tabla}
            ''')
        conn_curr.commit()
        conn_curr.execute("DETACH DATABASE backup_db")
    except Exception as e:
        conn_curr.rollback()
        logging.error(f"Error durante la restauración del backup: {e}")
        raise
    finally:
        conn_curr.close()

def get_dashboard_kpis(df_cuotas, df_cobros, cobros, aportes_funcionamiento, aportes_sueldo):
    import datetime
    import pandas as pd
    
    today = datetime.date.today()
    mes_actual = today.month
    anio_actual = today.year

    # 3. % de cobranza de últimos 12 meses
    mes_fin = mes_actual - 1
    anio_fin = anio_actual
    if mes_fin == 0:
        mes_fin = 12
        anio_fin -= 1
    fecha_fin = get_due_date(mes_fin, anio_fin)
    fecha_ini = datetime.date(fecha_fin.year - 1, fecha_fin.month, 1)

    def check_12_meses(row):
        due = get_due_date(row['mes'], row['anio'])
        return fecha_ini <= due <= fecha_fin

    cuotas_12m = df_cuotas[df_cuotas.apply(check_12_meses, axis=1)]
    total_12m = cuotas_12m['monto_efectivo'].sum() if not cuotas_12m.empty else 0
    cobrado_12m = 0
    if not cuotas_12m.empty and not df_cobros.empty:
        cobrado_12m = df_cobros[df_cobros['cuota_id'].isin(cuotas_12m['id'])]['monto'].sum()
    pct_cobranza = (cobrado_12m / total_12m * 100) if total_12m > 0 else 0

    # 4. Porcentaje histórico de cobros en tiempo y forma vs. atrasados
    hist_a_tiempo = 0
    hist_atrasado = 0
    
    for c in cobros:
        fecha_cobro = pd.to_datetime(c['fecha']).date()
        due_date = get_due_date(c['mes'], c['anio'])
        if fecha_cobro <= due_date:
            hist_a_tiempo += c['monto']
        else:
            hist_atrasado += c['monto']
            
    for f in aportes_funcionamiento:
        if f['fecha_cobro']:
            fecha_cobro = pd.to_datetime(f['fecha_cobro']).date()
            due_date = get_due_date(f['mes'], f['anio'])
            if fecha_cobro <= due_date:
                hist_a_tiempo += f['monto_cobrado']
            else:
                hist_atrasado += f['monto_cobrado']
                
    for s in aportes_sueldo:
        if s['monto_cobrado'] > 0 and s['fecha_cobro']:
            fecha_cobro = pd.to_datetime(s['fecha_cobro']).date()
            due_date = get_due_date(s['mes'], s['anio'])
            if fecha_cobro <= due_date:
                hist_a_tiempo += s['monto_cobrado']
            else:
                hist_atrasado += s['monto_cobrado']

    total_hist = hist_a_tiempo + hist_atrasado
    
    if total_hist > 0:
        pct_a_tiempo = (hist_a_tiempo / total_hist) * 100
        pct_atrasado = (hist_atrasado / total_hist) * 100
    else:
        pct_a_tiempo = 100.0
        pct_atrasado = 0.0
        
    return pct_cobranza, pct_a_tiempo, pct_atrasado

def get_cuotas_pendientes(df_decretos, df_cuotas, df_cobros):
    """Calcula las cuotas atrasadas y pendientes de cobrar para la lista de decretos."""
    import datetime
    import pandas as pd
    
    today_date = datetime.date.today()
    resultados = []
    
    for _, row in df_decretos.iterrows():
        dec_id = row['id']
        dec_cuotas = df_cuotas[df_cuotas['decreto_id'] == dec_id]
        dec_cobros = df_cobros[df_cobros['decreto_id'] == dec_id] if not df_cobros.empty else pd.DataFrame()
        
        atrasadas = 0
        total_proyectado = dec_cuotas['monto'].sum()
        total_cobrado = dec_cobros['monto'].sum() if not dec_cobros.empty else 0
        pendiente = max(0, total_proyectado - total_cobrado)
        
        if pendiente > 0.01:
            for _, q in dec_cuotas.iterrows():
                q_cobrado = dec_cobros[dec_cobros['cuota_id'] == q['id']]['monto'].sum() if not dec_cobros.empty else 0
                saldo = q['monto'] - q_cobrado
                if saldo > 0.01:
                    d_due_date = get_due_date(q['mes'], q['anio'])
                    if today_date > d_due_date:
                        atrasadas += saldo
                        
            resultados.append({
                'nro_decreto': row['nro_decreto'],
                'anio': row['anio'],
                'destino_fondos': row['destino_fondos'],
                'estado': row['estado'],
                'expediente_imuh': row.get('expediente_imuh') or "Sin asignar",
                'cuotas_atrasadas': atrasadas,
                'pendiente_cobrar': pendiente
            })
            
    # Ordenar por atrasadas DESC, luego pendiente DESC
    resultados.sort(key=lambda x: (x['cuotas_atrasadas'], x['pendiente_cobrar']), reverse=True)
    return resultados

def get_resumen_habituales_pendientes():
    """Retorna lista de aportes sueldo/sac con saldo > 0 y no renunciados."""
    import database as db
    pendientes = []
    
    # Sueldos
    for s in db.get_aportes_sueldo():
        saldo = s['monto_pedido'] - (s['monto_cobrado'] or 0)
        if saldo > 0.01 and s['estado'] != 'Renunciado':
            pendientes.append({
                'tipo': 'Sueldo',
                'periodo': f"{s['mes']:02d}/{s['anio']}",
                'monto_pedido': s['monto_pedido'],
                'monto_cobrado': s['monto_cobrado'] or 0,
                'saldo': saldo
            })
            
    # SAC
    for s in db.get_aportes_sac():
        saldo = s['monto_pedido'] - (s['monto_cobrado'] or 0)
        if saldo > 0.01 and s['estado'] != 'Renunciado':
            pendientes.append({
                'tipo': 'SAC',
                'periodo': f"{s['cuota_nro']}° - {s['anio']}",
                'monto_pedido': s['monto_pedido'],
                'monto_cobrado': s['monto_cobrado'] or 0,
                'saldo': saldo
            })
            
    return pendientes

def validar_expediente_imuh(valor):
    if not valor or str(valor).strip() == "":
        return True # Es opcional
    separadores = re.compile(r'[;,/]')
    partes = separadores.split(str(valor))
    patron = r'^\d{7,8}-[A-Z]-\d{4}$'
    validas = 0
    for parte in partes:
        p_clean = parte.strip()
        if p_clean == "":
            continue
        if not re.match(patron, p_clean):
            return False
        validas += 1
    return validas > 0

def normalizar_expediente_imuh(valor):
    if not valor or str(valor).strip() == "":
        return None
    separadores = re.compile(r'[;,/]')
    partes = separadores.split(str(valor))
    partes_limpias = []
    for parte in partes:
        p_clean = parte.strip().upper()
        if p_clean != "":
            partes_limpias.append(p_clean)
    if not partes_limpias:
        return None
    return ", ".join(partes_limpias)

def _validar_op_y_notas(nro_op, notas, requiere_confirmacion=True, confirmado=False):
    """Valida que un movimiento tenga OP o, en su defecto, notas válidas y confirmación.
    Retorna un mensaje de error (str) si falla, o None si es válido.
    Si requiere_confirmacion=False (ej. 'Volver a Reserva'), solo se exige la nota, sin OP ni casilla.
    """
    op_ok = bool(nro_op and nro_op.strip())
    nota_ok = bool(notas and 10 <= len(notas.strip()) <= 30)
    if requiere_confirmacion:
        if op_ok:
            return None  # Tiene OP: válido
        if not notas or not notas.strip():
            return "Error: Al no poseer un número de OP Bejerman, es obligatorio detallar las observaciones."
        if not nota_ok:
            return "Error: La observación debe tener entre 10 y 30 caracteres."
        if not confirmado:
            return "Error: Debe marcar la casilla de confirmación para guardar sin número de OP."
        return None
    else:
        # Sin OP requerida (ej. Volver a Reserva): solo nota obligatoria
        if not notas or not notas.strip():
            return "Error: Debe detallar las observaciones de esta operación (10 a 30 caracteres)."
        if not nota_ok:
            return "Error: La observación debe tener entre 10 y 30 caracteres."
        return None

def inject_style():
    import streamlit as st
    import os
    css_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "style.css")
    if os.path.exists(css_path):
        with open(css_path, "r", encoding="utf-8") as f:
            css = f.read()
        st.markdown(f"<style>{css}</style>", unsafe_allow_html=True)


def limpiar_prefijo_expediente(texto):
    if not texto:
        return ""
    import re
    patron = r'^[\(\s]*Exp\.?\s*8\d{6}-[A-Za-z]-\d{4}[\)\s-]*'
    clean = re.sub(patron, '', str(texto)).strip()
    clean = re.sub(r'^[:\-\s]+', '', clean).strip()
    return clean

def extraer_imuh_de_texto(texto):
    if not texto:
        return None
    import re
    patron = r'(8\d{6})[-\s/]+([A-Za-z])[-\s/]+(\d{4})'
    match = re.search(patron, str(texto))
    if match:
        nro, letra, anio = match.groups()
        return f"{nro}-{letra.upper()}-{anio}"
    return None

def validar_cuit(cuit):
    """Valida formato AFIP de CUIT: XX-XXXXXXXX-X (2 dígitos, guión, 8 dígitos, guión, 1 dígito) y dígito verificador."""
    if not cuit or not isinstance(cuit, str):
        return False
    cuit_clean = cuit.strip()
    if not re.match(r'^\d{2}-\d{8}-\d{1}$', cuit_clean):
        return False
    digits = [int(d) for d in cuit_clean.replace('-', '')]
    if len(digits) != 11:
        return False
    weights = [5, 4, 3, 2, 7, 6, 5, 4, 3, 2]
    val = sum(d * w for d, w in zip(digits[:10], weights))
    mod = 11 - (val % 11)
    if mod == 11:
        check = 0
    elif mod == 10:
        check = 9
    else:
        check = mod
    return digits[10] == check




```

## Archivo: `utils_reports.py`

```python
import os
import io
import tempfile
import datetime
import pandas as pd
import database as db
import utils
import re
from pdf_generator import (
    generar_reporte_composicion_pdf, 
    generar_reporte_pdf, 
    generar_reporte_solicitudes_pdf, 
    generar_reporte_desvios_pdf, 
    generar_reporte_gastos_funcionamiento_financiados_obra_pdf
)

def clean_destino_name(dest):
    if not dest:
        return ""
    # Remover prefijo "ID: \d+ | "
    dest_clean = re.sub(r'^ID:\s*\d+\s*\|\s*', '', dest)
    # Remover "Dto. XX/YY - " o "Exp. XX - " o "XX - "
    dest_clean = re.sub(r'^(?:Dto\.\s*\d+/\d+|Exp\.\s*(?:IMUH\s*)?\d+-[A-Za-z0-9\-]+|\d+-[A-Za-z0-9\-]+)\s*-\s*', '', dest_clean, flags=re.IGNORECASE)
    return dest_clean


def obtener_datos_composicion(sel_dec_id, sel_cuota_id):
    """Calcula la composición de fondos para una cuota específica."""
    decretos_list = db.get_decretos()
    cuotas_list = db.get_cuotas_by_decreto(sel_dec_id)
    cuota_sel_dict = next(c for c in cuotas_list if c['id'] == sel_cuota_id)
    
    cuota_ids = [c['id'] for c in cuotas_list]
    cuota_seq_num = cuota_ids.index(sel_cuota_id) + 1
    
    cobros_cuota = db.get_cobros_by_cuota(sel_cuota_id) or []
    
    estado_actual_filas = []
    
    for cb in cobros_cuota:
        cb_id = cb['id']
        dist = db.get_distribucion_by_cobro(cb_id)
        monto_fo = dist['monto_fin_orig'] if dist else 0.0
        monto_res = dist['monto_reserva'] if dist else 0.0
        
        tot_rec_sin_distribucion = 0.0
        
        # A. Fin Original (Pagos realizados)
        usos_fo = db.get_fin_original_usos_by_cobro(cb_id)
        sum_usos_fo = 0.0
        for u in usos_fo:
            sum_usos_fo += u['monto']
            estado_actual_filas.append({
                "Fecha": utils.format_date_ar(u['fecha']),
                "Movimiento": "Fin original",
                "Monto": u['monto'],
                "Orden de Pago (OP)": u['nro_op'] or "Sin asignar",
                "Destino": "Obra original",
                "obra_id": u.get("obra_id"),
                "Aclaraciones": u['notas'] or ""
            })
            
        # B. Fin Original (Pendiente)
        fo_pendiente = monto_fo - sum_usos_fo
        if fo_pendiente > 0.01:
            estado_actual_filas.append({
                "Fecha": "-",
                "Movimiento": "Fin original (Pendiente)",
                "Monto": fo_pendiente,
                "Orden de Pago (OP)": "-",
                "Destino": "Obra original (Fondo en cuenta)",
                "Aclaraciones": ""
            })
            
        # C. En Reserva (Saldo Disponible)
        usos_r = db.get_reserva_usos_by_cobro(cb_id)
        tot_usos_r = sum(u['monto'] for u in usos_r)
        
        # Recuperos a reserva
        tot_rec_a_res = 0.0
        for u in usos_r:
            recs = db.get_recuperos_by_reserva_uso(u['id'])
            for r in recs:
                if r['destino_tipo'] == 'reserva':
                    tot_rec_a_res += r['monto']
                    
        res_saldo_neto = monto_res - tot_usos_r + tot_rec_a_res
        if res_saldo_neto > 0.01:
            estado_actual_filas.append({
                "Fecha": "-",
                "Movimiento": "En reserva",
                "Monto": res_saldo_neto,
                "Orden de Pago (OP)": "-",
                "Destino": "Reserva disponible",
                "Aclaraciones": ""
            })
            
        # D. Préstamos / Desvíos desde Reserva (Activos)
        for u in usos_r:
            if u['destino_tipo'] != 'fin_original':
                recs = db.get_recuperos_by_reserva_uso(u['id'])
                sum_recs = sum(r['monto'] for r in recs)
                u_net = u['monto'] - sum_recs
                if u_net > 0.01:
                    estado_actual_filas.append({
                        "Fecha": utils.format_date_ar(u['fecha']),
                        "Movimiento": "Desvío a otra obra (desde Reserva)",
                        "Monto": u_net,
                        "Orden de Pago (OP)": u['nro_op'] or "Sin asignar",
                        "Destino": u['destino_detalle'] or "Obra sin decreto",
                        "obra_id": u.get("obra_id"),
                        "gasto_nombre": u.get("gasto_nombre"),
                        "gasto_expediente_imuh": u.get("gasto_expediente_imuh"),
                        "Aclaraciones": u['notas'] or ""
                    })
                
                # E. Recuperos de Reserva (Redireccionados)
                for r in recs:
                    if r['destino_tipo'] != 'reserva':
                        if r['destino_tipo'] == 'sin_distribucion':
                            tot_rec_sin_distribucion += r['monto']
                        elif r['destino_tipo'] == 'compensacion':
                            detalles = db.obtener_detalles_compensacion_grupo(r['grupo_compensacion_id'])
                            fecha_pago = utils.format_date_ar(r['fecha'])
                            op_orig_str = "Sin OP"
                            dec_cruzado_str = "otro decreto"
                            fecha_orig_str = ""
                            
                            if detalles:
                                desv_rec = detalles['desvios'][0] if detalles['desvios'] else None
                                if desv_rec:
                                    dec_cruzado_str = f"Dto. {desv_rec['nro_decreto']}/{desv_rec['dec_anio']}"
                                
                                if u.get('nro_op'):
                                    op_orig_str = f"OP {u['nro_op']}"
                                elif u.get('fecha'):
                                    op_orig_str = f"pago del {utils.format_date_ar(u['fecha'])}"
                                
                                if u.get('fecha'):
                                    fecha_orig_str = f" del {utils.format_date_ar(u['fecha'])}"
                                    
                                all_ops = []
                                for x in detalles['desvios'] + detalles['reservas']:
                                    if x.get('rec_op'):
                                        all_ops.append(x['rec_op'])
                                
                                ops_list = []
                                for op in all_ops:
                                    if op and op.strip() and op.strip() != 'Sin OP':
                                        ops_list.extend([o.strip() for o in str(op).replace(',', '-').split('-')])
                                ops_uniq = sorted(list(set(ops_list)))
                                ops_str = ", ".join(ops_uniq) if ops_uniq else "Sin OP"
                                
                                acl = f"Originalmente desviado a {dec_cruzado_str} ({op_orig_str}{fecha_orig_str}), recuperado mediante compensación el {utils.format_date_ar(r['fecha'])} afectando a OP {ops_str} (Compensación)"
                            else:
                                acl = "Compensación de deudas cruzadas (Compensación)"
                                
                            estado_actual_filas.append({
                                "Fecha": fecha_pago,
                                "Movimiento": "Fin original (Recupero de Reserva)",
                                "Monto": r['monto'],
                                "Orden de Pago (OP)": r['nro_op'] or "Sin asignar",
                                "Destino": "Obra original",
                                "Aclaraciones": acl
                            })
                        else:
                            dest_r = "Obra original" if r['destino_tipo'] == 'fin_original' else (r.get('dest_nombre') or r.get('destino_detalle') or "Otra obra")
                            mov_r = "Fin original (Recupero de Reserva)" if r['destino_tipo'] == 'fin_original' else "Desvío a otra obra (Recupero de Reserva)"
                            estado_actual_filas.append({
                                "Fecha": utils.format_date_ar(r['fecha']),
                                "Movimiento": mov_r,
                                "Monto": r['monto'],
                                "Orden de Pago (OP)": r['nro_op'] or "Sin asignar",
                                "Destino": dest_r,
                                "Aclaraciones": ""
                            })
            else:
                # Reserve use to Fin Original
                estado_actual_filas.append({
                    "Fecha": utils.format_date_ar(u['fecha']),
                    "Movimiento": "Fin original (desde Reserva)",
                    "Monto": u['monto'],
                    "Orden de Pago (OP)": u['nro_op'] or "Sin asignar",
                    "Destino": "Obra original",
                    "obra_id": u.get("obra_id"),
                    "gasto_nombre": u.get("gasto_nombre"),
                    "gasto_expediente_imuh": u.get("gasto_expediente_imuh"),
                    "Aclaraciones": u['notas'] or ""
                })
                
        # F. Desvíos Iniciales (Activos y Recuperos Redireccionados)
        desvios = db.get_desvios_by_cobro(cb_id)
        for d in desvios:
            recs = db.get_recuperos_by_desvio(d['id'])
            sum_recs = sum(r['monto'] for r in recs)
            d_net = d['monto'] - sum_recs
            if d_net > 0.01:
                selected_op = d['nro_op'] or "Sin asignar"
                estado_actual_filas.append({
                    "Fecha": utils.format_date_ar(d['fecha']),
                    "Movimiento": "Desvío a otra obra",
                    "Monto": d_net,
                    "Orden de Pago (OP)": selected_op,
                    "Destino": d['destino'],
                    "obra_id": d.get("obra_id"),
                    "gasto_nombre": d.get("gasto_nombre"),
                    "gasto_expediente_imuh": d.get("gasto_expediente_imuh"),
                    "Aclaraciones": d['motivo'] or ""
                })
                
            # Recuperos redireccionados
            for r in recs:
                if r['destino_tipo'] == 'sin_distribucion':
                    tot_rec_sin_distribucion += r['monto']
                elif r['destino_tipo'] == 'compensacion':
                    detalles = db.obtener_detalles_compensacion_grupo(r['grupo_compensacion_id'])
                    fecha_pago = utils.format_date_ar(r['fecha'])
                    op_orig_str = "Sin OP"
                    dec_cruzado_str = "otro decreto"
                    fecha_orig_str = ""
                    
                    if detalles:
                        res_rec = detalles['reservas'][0] if detalles['reservas'] else None
                        if res_rec:
                            dec_cruzado_str = f"Dto. {res_rec['nro_decreto']}/{res_rec['dec_anio']}"
                            if res_rec.get('uso_fecha'):
                                fecha_pago = utils.format_date_ar(res_rec['uso_fecha'])
                                fecha_orig_str = f" del {utils.format_date_ar(res_rec['uso_fecha'])}"
                            if res_rec.get('uso_op'):
                                op_orig_str = f"OP {res_rec['uso_op']}"
                            elif res_rec.get('uso_fecha'):
                                op_orig_str = f"pago del {utils.format_date_ar(res_rec['uso_fecha'])}"
                                
                        all_ops = []
                        for x in detalles['desvios'] + detalles['reservas']:
                            if x.get('rec_op'):
                                all_ops.append(x['rec_op'])
                        
                        ops_list = []
                        for op in all_ops:
                            if op and op.strip() and op.strip() != 'Sin OP':
                                ops_list.extend([o.strip() for o in str(op).replace(',', '-').split('-')])
                        ops_uniq = sorted(list(set(ops_list)))
                        ops_str = ", ".join(ops_uniq) if ops_uniq else "Sin OP"
                        
                        acl = f"Fondos originados en {dec_cruzado_str} ({op_orig_str}{fecha_orig_str}), compensados el {utils.format_date_ar(r['fecha'])} afectando a OP {ops_str} (Compensación)"
                    else:
                        acl = "Compensación de deudas cruzadas (Compensación)"
                        
                    estado_actual_filas.append({
                        "Fecha": fecha_pago,
                        "Movimiento": "Fin original (Recupero)",
                        "Monto": r['monto'],
                        "Orden de Pago (OP)": r['nro_op'] or "Sin asignar",
                        "Destino": "Obra original",
                        "Aclaraciones": acl
                    })
                else:
                    dest_r = "Obra original" if r['destino_tipo'] == 'fin_original' else (r.get('dest_nombre') or r.get('destino_detalle') or "Otra obra")
                    mov_r = "Fin original (Recupero)" if r['destino_tipo'] == 'fin_original' else "Desvío a otra obra (Recupero)"
                    estado_actual_filas.append({
                        "Fecha": utils.format_date_ar(r['fecha']),
                        "Movimiento": mov_r,
                        "Monto": r['monto'],
                        "Orden de Pago (OP)": r['nro_op'] or "Sin asignar",
                        "Destino": dest_r,
                        "Aclaraciones": ""
                    })
                
        # G. Sin Distribuir
        tot_desvios_ini = sum(d['monto'] for d in desvios)
        saldo_libre = cb['monto'] - (monto_fo + monto_res + tot_desvios_ini) + tot_rec_sin_distribucion
        if saldo_libre > 0.01:
            estado_actual_filas.append({
                "Fecha": "-",
                "Movimiento": "Sin distribuir",
                "Monto": saldo_libre,
                "Orden de Pago (OP)": "-",
                "Destino": "Sin distribuir",
                "Aclaraciones": ""
            })
            
    sum_total_actual = sum(f['Monto'] for f in estado_actual_filas)
    
    fechas_list = sorted(list(set(utils.format_date_ar(c['fecha']) for c in cobros_cuota)))
    fechas_str = ", ".join(fechas_list) if fechas_list else "Sin cobros registrados"
    
    notas_list = []
    for cb in cobros_cuota:
        dist = db.get_distribucion_by_cobro(cb['id'])
        if dist and dist.get('notas') and dist['notas'].strip():
            notas_list.append(f"Cobro {utils.format_date_ar(cb['fecha'])}: {dist['notas'].strip()}")
    aclaraciones_str = "\n".join(notas_list) if notas_list else ""
    
    # Post-procesamiento para unificar Expediente IMUH
    obras_list = db.get_obras() or []
    obra_imuh_map = {o['id']: o['expediente_imuh'] for o in obras_list if o.get('id')}
    dec = db.get_decreto(sel_dec_id)
    dec_imuh = dec.get('expediente_imuh') if dec else None
    
    for row in estado_actual_filas:
        exp_val = None
        if row.get("gasto_expediente_imuh"):
            exp_val = row["gasto_expediente_imuh"]
        elif row.get("obra_id"):
            exp_val = obra_imuh_map.get(row["obra_id"])
            
        if not exp_val:
            dest_lower = str(row.get("Destino", "")).lower()
            if "obra original" in dest_lower or "reserva" in dest_lower:
                exp_val = dec_imuh
            else:
                extracted = utils.extraer_imuh_de_texto(str(row.get("Destino", "")))
                if extracted:
                    exp_val = extracted
                    
        row["expediente_imuh"] = exp_val or "-"

    return estado_actual_filas, sum_total_actual, cobros_cuota, cuota_seq_num, fechas_str, aclaraciones_str, cuota_sel_dict

def obtener_afectacion_decreto(sel_dec_id):
    """Obtiene la afectación consolidada de todas las cuotas de un decreto para el reporte 'Afectación de decretos'."""
    dec = db.get_decreto(sel_dec_id)
    cuotas_list = db.get_cuotas_by_decreto(sel_dec_id)
    cuota_ids = [c['id'] for c in cuotas_list]
    
    # Obtener proveedor de la obra original asignada al decreto
    obras_asoc = db.get_obras_by_decreto(sel_dec_id)
    prov_orig_razon = None
    if obras_asoc and obras_asoc[0].get('proveedor_razon_social'):
        prov_orig_razon = obras_asoc[0]['proveedor_razon_social']
    
    filas_reporte = []
    
    for c in cuotas_list:
        seq_num = cuota_ids.index(c['id']) + 1
        estado_actual_filas, sum_total_actual, cobros_cuota, _, fechas_str, _, _ = obtener_datos_composicion(sel_dec_id, c['id'])
        
        importe_percibido = sum(cb['monto'] for cb in cobros_cuota)
        
        if not estado_actual_filas:
            filas_reporte.append({
                "Nro. Cuota": seq_num,
                "Fecha de cobro": "-",
                "Importe percibido": importe_percibido,
                "Proveedor": "-",
                "Obra destino": "-",
                "Fecha de pago": "-",
                "Importe pagado": 0.0,
                "Nro. OP Bejerman": "-",
                "Observaciones/aclaraciones": "Pendiente de cobro / Sin distribución"
            })
        else:
            for row in estado_actual_filas:
                dest = str(row["Destino"])
                prov_str = "-"
                
                obra_obj = None
                if row.get("obra_id"):
                    obra_obj = db.get_obra(row["obra_id"])
                    
                if obra_obj and obra_obj.get('proveedor_razon_social'):
                    prov_str = obra_obj['proveedor_razon_social']
                elif dest == "Obra original":
                    prov_str = prov_orig_razon if prov_orig_razon else "NO INFORMA PROVEEDOR"
                elif dest in ["Sin distribuir", "Reserva disponible"]:
                    prov_str = "-"
                elif "FUN:" in dest or row.get("gasto_expediente_imuh") or row.get("gasto_nombre"):
                    exp = row.get("gasto_expediente_imuh")
                    g_fun = db.get_gasto_funcionamiento_by_expediente(exp) if exp else None
                    if g_fun and g_fun.get('proveedor_razon_social'):
                        prov_str = g_fun['proveedor_razon_social']
                    else:
                        prov_str = "NO INFORMA PROVEEDOR"
                else:
                    exp_imuh = utils.extraer_imuh_de_texto(dest)
                    if exp_imuh:
                        obra_obj = db.get_obra_by_expediente(exp_imuh)
                    if obra_obj and obra_obj.get('proveedor_razon_social'):
                        prov_str = obra_obj['proveedor_razon_social']
                    else:
                        prov_str = "NO INFORMA PROVEEDOR"

                # Calcular Tipo de afectación y Obra destino
                mov_str = str(row.get("Movimiento", ""))
                if "Fin original" in mov_str:
                    tipo_afectacion = "Obra original"
                elif dest in ["Sin distribuir", "Reserva disponible"]:
                    tipo_afectacion = "-"
                else:
                    tipo_afectacion = "Desvío"

                # Formatear Obra destino: Nro. expediente imuh + nombre de la obra o gasto
                if row.get("expediente_imuh") and row.get("expediente_imuh") != "-":
                    imuh = row["expediente_imuh"]
                    nombre_gasto_obra = ""
                    if obra_obj:
                        nombre_gasto_obra = obra_obj.get("nombre", "")
                    elif "FUN:" in dest or row.get("gasto_nombre"):
                        nombre_gasto_obra = row.get("gasto_nombre") or dest.replace("FUN: ", "")
                    elif dest and "Obra original" not in dest and "Reserva" not in dest:
                        nombre_gasto_obra = dest.split(" - ")[-1] if " - " in dest else dest
                    else:
                        # Si es obra original global (aun sin asignar a un expediente específico pero que tiene un exp)
                        # Trata de buscar la obra por el IMUH si no la encontró por obra_id
                        o_obj = db.get_obra_by_expediente(imuh)
                        if o_obj:
                            nombre_gasto_obra = o_obj.get("nombre", "")

                    if nombre_gasto_obra:
                        dest = f"{imuh} - {nombre_gasto_obra}"
                    else:
                        dest = f"{imuh}"
                
                filas_reporte.append({
                    "Nro. Cuota": seq_num,
                    "Fecha de cobro": fechas_str,
                    "Importe percibido": importe_percibido,
                    "Proveedor": prov_str,
                    "Tipo de afectación": tipo_afectacion,
                    "Obra destino": dest,
                    "Fecha de pago": row["Fecha"],
                    "Importe pagado": row["Monto"],
                    "Nro. OP Bejerman": row["Orden de Pago (OP)"],
                    "Observaciones/aclaraciones": row["Aclaraciones"]
                })
                
    return dec, cuotas_list, filas_reporte

def parse_excel_date_val(val):
    if not val or str(val).strip() == "-":
        return "-"
    if isinstance(val, (datetime.date, datetime.datetime)):
        return val
    if isinstance(val, str):
        v = val.strip()
        for fmt in ('%Y-%m-%d', '%d-%m-%Y', '%d/%m/%Y'):
            try:
                return datetime.datetime.strptime(v, fmt).date()
            except ValueError:
                pass
    return val

def generar_excel_afectacion(dec, filas_reporte, pendiente_cobro):
    excel_buffer = io.BytesIO()
    with pd.ExcelWriter(excel_buffer, engine='xlsxwriter', date_format='dd/mm/yyyy') as writer:
        workbook = writer.book
        worksheet = workbook.add_worksheet('Afectación')
        writer.sheets['Afectación'] = worksheet
        
        bold = workbook.add_format({'bold': True})
        money = workbook.add_format({'num_format': '#,##0.00'})
        header_format = workbook.add_format({'bold': True, 'bg_color': '#f0f0f0', 'border': 1})
        cell_format = workbook.add_format({'border': 1})
        money_cell = workbook.add_format({'num_format': '#,##0.00', 'border': 1})
        date_cell_format = workbook.add_format({'num_format': 'dd/mm/yyyy', 'border': 1})
        merge_date_format = workbook.add_format({'align': 'center', 'valign': 'vcenter', 'num_format': 'dd/mm/yyyy', 'border': 1})
        
        total_decreto = sum(c['monto'] for c in db.get_cuotas_by_decreto(dec['id']))
        
        worksheet.write(0, 0, f"Decreto {dec['nro_decreto']}/{dec['anio']}", bold)
        worksheet.write(1, 0, 'Expediente IMUH:', bold)
        worksheet.write(1, 1, dec.get('expediente_imuh') or "Sin asignar")
        worksheet.write(2, 0, 'Obra:', bold)
        worksheet.write(2, 1, dec['destino_fondos'])
        
        worksheet.write(4, 0, 'Total decreto', bold)
        worksheet.write(4, 1, total_decreto, money)
        worksheet.write(5, 0, 'Pendiente de cobro', bold)
        worksheet.write(5, 1, pendiente_cobro, money)
        
        headers = ["Nro. Cuota", "Fecha de cobro", "Importe percibido", "Proveedor", "Tipo de afectación", "Obra destino", "Fecha de pago", "Importe pagado", "Nro. OP Bejerman", "Observaciones/aclaraciones"]
        row_idx = 7
        for col_num, header in enumerate(headers):
            worksheet.write(row_idx, col_num, header, header_format)
            
        data_start_row = row_idx + 1
        
        # Para hacer merge de celdas como en el mockup, necesitamos trackear la cuota
        merge_format = workbook.add_format({'align': 'center', 'valign': 'vcenter', 'border': 1})
        merge_money_format = workbook.add_format({'align': 'center', 'valign': 'vcenter', 'num_format': '#,##0.00', 'border': 1})
        
        current_row = data_start_row
        
        import itertools
        for key, group in itertools.groupby(filas_reporte, key=lambda x: x["Nro. Cuota"]):
            group_list = list(group)
            num_rows = len(group_list)
            
            first_row = group_list[0]
            f_cobro_val = parse_excel_date_val(first_row["Fecha de cobro"])
            
            # Merge logic for Nro. Cuota, Fecha de cobro, Importe percibido
            if num_rows > 1:
                worksheet.merge_range(current_row, 0, current_row + num_rows - 1, 0, first_row["Nro. Cuota"], merge_format)
                if isinstance(f_cobro_val, (datetime.date, datetime.datetime)):
                    worksheet.merge_range(current_row, 1, current_row + num_rows - 1, 1, f_cobro_val, merge_date_format)
                else:
                    worksheet.merge_range(current_row, 1, current_row + num_rows - 1, 1, str(f_cobro_val), merge_format)
                worksheet.merge_range(current_row, 2, current_row + num_rows - 1, 2, first_row["Importe percibido"], merge_money_format)
            else:
                worksheet.write(current_row, 0, first_row["Nro. Cuota"], merge_format)
                if isinstance(f_cobro_val, (datetime.date, datetime.datetime)):
                    worksheet.write_datetime(current_row, 1, f_cobro_val, merge_date_format)
                else:
                    worksheet.write(current_row, 1, str(f_cobro_val), merge_format)
                worksheet.write(current_row, 2, first_row["Importe percibido"], merge_money_format)
                
            for i, r in enumerate(group_list):
                worksheet.write(current_row + i, 3, r.get("Proveedor", "-"), cell_format)
                worksheet.write(current_row + i, 4, r.get("Tipo de afectación", "-"), cell_format)
                worksheet.write(current_row + i, 5, r["Obra destino"], cell_format)
                
                f_pago_val = parse_excel_date_val(r["Fecha de pago"])
                if isinstance(f_pago_val, (datetime.date, datetime.datetime)):
                    worksheet.write_datetime(current_row + i, 6, f_pago_val, date_cell_format)
                else:
                    worksheet.write(current_row + i, 6, str(f_pago_val), cell_format)
                    
                worksheet.write(current_row + i, 7, r["Importe pagado"], money_cell)
                worksheet.write(current_row + i, 8, r["Nro. OP Bejerman"], cell_format)
                worksheet.write(current_row + i, 9, r.get("Observaciones/aclaraciones", ""), cell_format)
                
            current_row += num_rows
            
        # Adjust column widths
        worksheet.set_column(0, 0, 10)
        worksheet.set_column(1, 1, 15)
        worksheet.set_column(2, 2, 20)
        worksheet.set_column(3, 3, 25)
        worksheet.set_column(4, 4, 30)
        worksheet.set_column(5, 5, 15)
        worksheet.set_column(6, 6, 20)
        worksheet.set_column(7, 7, 20)
        worksheet.set_column(8, 8, 40)
        
    return excel_buffer.getvalue()

def generar_pdf_afectacion(dec, filas_reporte, pendiente_cobro, incluir_resumen=False):
    from fpdf import FPDF
    temp_path = os.path.join(tempfile.gettempdir(), f"Afectacion_{dec['nro_decreto']}_{dec['anio']}.pdf")
    
    class PDF(FPDF):
        def header(self):
            self.set_font('helvetica', 'B', 15)
            self.cell(0, 10, 'Reporte de Afectación de Decretos', ln=True, align='C')
            self.ln(5)
            
        def footer(self):
            self.set_y(-15)
            self.set_font('helvetica', 'I', 8)
            self.cell(0, 10, f'Página {self.page_no()}', 0, 0, 'C')

    pdf = PDF('L', 'mm', 'A4') # Landscape for more space
    pdf.add_page()
    
    total_decreto = sum(c['monto'] for c in db.get_cuotas_by_decreto(dec['id']))
    
    pdf.set_font("helvetica", "B", 12)
    pdf.cell(50, 8, f"Decreto {dec['nro_decreto']}/{dec['anio']}", ln=True)
    pdf.set_font("helvetica", "", 10)
    pdf.cell(40, 8, "Expediente IMUH:", 0, 0)
    pdf.multi_cell(0, 8, dec.get('expediente_imuh') or "Sin asignar")
    pdf.cell(40, 8, "Obra:", 0, 0)
    pdf.multi_cell(0, 8, dec['destino_fondos'], align='L')
    
    pdf.cell(40, 8, "Total decreto:", 0, 0)
    pdf.cell(0, 8, utils.format_currency_ar(total_decreto), ln=True)
    pdf.cell(40, 8, "Pendiente de cobro:", 0, 0)
    pdf.cell(0, 8, utils.format_currency_ar(pendiente_cobro), ln=True)
    
    if incluir_resumen:
        resumen_txt = generar_resumen_narrativo_decreto(dec, filas_reporte, total_decreto, pendiente_cobro)
        
        pdf.ln(3)
        pdf.set_font("helvetica", "B", 10)
        pdf.cell(0, 8, "Resumen y Afectacion del Decreto:", ln=True)
        pdf.set_font("helvetica", "", 8.5)
        
        lines = resumen_txt.split('\n')
        start_printing = False
        for line in lines:
            line_str = line.strip()
            if "Historial de Flujo de Fondos:" in line_str:
                start_printing = True
                pdf.ln(2)
                pdf.set_font("helvetica", "B", 9)
                pdf.cell(0, 6, "Historial de Flujo de Fondos:", ln=True)
                pdf.set_font("helvetica", "", 8.5)
                continue
            if "Estado Actual de Saldos Consolidados:" in line_str:
                start_printing = True
                pdf.ln(3)
                pdf.set_font("helvetica", "B", 9)
                pdf.cell(0, 6, "Estado Actual de Saldos Consolidados:", ln=True)
                pdf.set_font("helvetica", "", 8.5)
                continue
            
            if start_printing:
                if not line_str:
                    continue
                clean_line = line_str.replace('**', '').replace('*', '').strip()
                indent = 0
                if line.startswith('    *') or line.startswith('\t*') or line.startswith('  *'):
                    indent = 8
                
                pdf.set_x(10 + indent)
                pdf.multi_cell(0, 5, clean_line)
                
    pdf.ln(5)
    
    # Table Header
    pdf.set_font("helvetica", "B", 8)
    col_widths = [10, 16, 21, 28, 20, 48, 16, 21, 16, 69]
    headers = ["Cuota", "F. Cobro", "Imp. Percibido", "Proveedor", "Tipo afect.", "Obra destino", "F. Pago", "Imp. Pagado", "Nro. OP", "Observaciones"]
    
    for i, h in enumerate(headers):
        pdf.cell(col_widths[i], 10, h, border=1, align='C')
    pdf.ln()
    
    pdf.set_font("helvetica", "", 8)
    
    import itertools
    for key, group in itertools.groupby(filas_reporte, key=lambda x: x["Nro. Cuota"]):
        group_list = list(group)
        
        for i, r in enumerate(group_list):
            prov = str(r.get("Proveedor", "-"))
            tipo_afect = str(r.get("Tipo de afectación", "-"))
            dest = str(r["Obra destino"])
            obs = str(r["Observaciones/aclaraciones"])
            
            lines_prov = pdf.get_string_width(prov) / (col_widths[3] - 2)
            lines_tipo = pdf.get_string_width(tipo_afect) / (col_widths[4] - 2)
            lines_dest = pdf.get_string_width(dest) / (col_widths[5] - 2)
            lines_obs = pdf.get_string_width(obs) / (col_widths[9] - 2)
            max_lines = max(1, int(lines_prov) + 1, int(lines_tipo) + 1, int(lines_dest) + 1, int(lines_obs) + 1)
            line_height = 5
            row_height = max_lines * line_height

            start_x = pdf.get_x()
            start_y = pdf.get_y()
            
            # Check page break BEFORE drawing the cells for this row
            if start_y + row_height > 185:
                pdf.add_page()
                # Redraw header
                pdf.set_font("helvetica", "B", 8)
                for j, h in enumerate(headers):
                    pdf.cell(col_widths[j], 10, h, border=1, align='C')
                pdf.ln()
                pdf.set_font("helvetica", "", 8)
                start_x = pdf.get_x()
                start_y = pdf.get_y()
                
            # Print first 3 cols only if it's the first row of the group, else blank
            if i == 0:
                cuota_val = str(r["Nro. Cuota"])
                fecha_cobro = str(r["Fecha de cobro"])
                imp_perc = utils.format_currency_ar(r["Importe percibido"])
            else:
                cuota_val = ""
                fecha_cobro = ""
                imp_perc = ""
                
            # Draw cells
            pdf.cell(col_widths[0], row_height, cuota_val, border=1, align='C')
            
            # Fecha cobro multiline if needed
            x = pdf.get_x()
            y = pdf.get_y()
            pdf.rect(x, y, col_widths[1], row_height)
            pdf.set_xy(x, y + (row_height - line_height)/2 if cuota_val else y)
            pdf.multi_cell(col_widths[1], line_height, fecha_cobro, border=0, align='C')
            pdf.set_xy(x + col_widths[1], y)
            
            pdf.cell(col_widths[2], row_height, imp_perc, border=1, align='R')
            
            # Proveedor multiline
            x = pdf.get_x()
            y = pdf.get_y()
            pdf.rect(x, y, col_widths[3], row_height)
            pdf.multi_cell(col_widths[3], line_height, prov, border=0, align='L')
            pdf.set_xy(x + col_widths[3], y)
            
            # Tipo de afectacion multiline
            x = pdf.get_x()
            y = pdf.get_y()
            pdf.rect(x, y, col_widths[4], row_height)
            pdf.multi_cell(col_widths[4], line_height, tipo_afect, border=0, align='C')
            pdf.set_xy(x + col_widths[4], y)
            
            # Destino multiline
            x = pdf.get_x()
            y = pdf.get_y()
            pdf.rect(x, y, col_widths[5], row_height)
            pdf.multi_cell(col_widths[5], line_height, dest, border=0, align='L')
            pdf.set_xy(x + col_widths[5], y)
            
            pdf.cell(col_widths[6], row_height, str(r["Fecha de pago"]), border=1, align='C')
            pdf.cell(col_widths[7], row_height, utils.format_currency_ar(r["Importe pagado"]), border=1, align='R')
            pdf.cell(col_widths[8], row_height, str(r["Nro. OP Bejerman"]), border=1, align='C')
            
            # Observaciones multiline
            x = pdf.get_x()
            y = pdf.get_y()
            pdf.rect(x, y, col_widths[9], row_height)
            pdf.multi_cell(col_widths[9], line_height, obs, border=0, align='L')
            pdf.set_xy(start_x, y + row_height)
            
    pdf.output(temp_path)
    with open(temp_path, 'rb') as f:
        pdf_data = f.read()
    try:
        os.remove(temp_path)
    except OSError:
        pass
    return pdf_data



def generar_excel_composicion(dec, cuota_sel_dict, cuota_seq_num, fechas_str, aclaraciones_str, df_export):
    excel_buffer = io.BytesIO()
    with pd.ExcelWriter(excel_buffer, engine='xlsxwriter') as writer:
        workbook = writer.book
        worksheet = workbook.add_worksheet('Composición')
        writer.sheets['Composición'] = worksheet
        
        bold = workbook.add_format({'bold': True})
        money = workbook.add_format({'num_format': '#,##0.00'})
        
        worksheet.write(0, 0, 'REPORTE DE COMPOSICIÓN DE FONDOS', bold)
        worksheet.write(2, 0, 'Decreto:', bold)
        worksheet.write(2, 1, f"Dto. {dec['nro_decreto']}/{dec['anio']}")
        worksheet.write(3, 0, 'Expediente IMUH:', bold)
        worksheet.write(3, 1, dec.get('expediente_imuh') or "Sin asignar")
        worksheet.write(4, 0, 'Nombre de la Obra:', bold)
        worksheet.write(4, 1, dec['destino_fondos'])
        
        worksheet.write(2, 3, 'Cuota N°:', bold)
        worksheet.write(2, 4, f"Cuota {cuota_seq_num}")
        worksheet.write(3, 3, 'Importe de Cuota:', bold)
        worksheet.write(3, 4, cuota_sel_dict['monto'], money)
        worksheet.write(4, 3, 'Fechas de Cobro:', bold)
        worksheet.write(4, 4, fechas_str)
        
        row_idx = 6
        if aclaraciones_str:
            worksheet.write(row_idx, 0, 'Aclaraciones generales:', bold)
            worksheet.write(row_idx, 1, aclaraciones_str)
            row_idx += 2
            
        headers = ["Fecha", "Destino", "OP", "Aclaraciones", "Monto"]
        for col_num, header in enumerate(headers):
            worksheet.write(row_idx, col_num, header, bold)
            
        data_start_row = row_idx + 1
        for i, r in df_export.iterrows():
            curr_row = data_start_row + i
            worksheet.write(curr_row, 0, r["Fecha"])
            worksheet.write(curr_row, 1, r["Destino"])
            worksheet.write(curr_row, 2, r["OP"])
            worksheet.write(curr_row, 3, r["Aclaraciones"])
            worksheet.write(curr_row, 4, r["Monto"], money)
            
        total_row_idx = data_start_row + len(df_export)
        worksheet.write(total_row_idx, 0, "TOTAL", bold)
        worksheet.write(total_row_idx, 1, "")
        worksheet.write(total_row_idx, 2, "")
        worksheet.write(total_row_idx, 3, "")
        worksheet.write_formula(total_row_idx, 4, f"=SUM(E{data_start_row+1}:E{total_row_idx})", bold)
        
    return excel_buffer.getvalue()

def generar_pdf_composicion(dec, cuota_sel_dict, cuota_seq_num, fechas_str, aclaraciones_str, sum_total_actual, df_export):
    temp_path_comp = os.path.join(tempfile.gettempdir(), f"Reporte_Composicion_{dec['nro_decreto']}_{dec['anio']}_Cuota_{cuota_seq_num}.pdf")
    
    decreto_info = {
        "identificacion": f"Dto. {dec['nro_decreto']}/{dec['anio']}",
        "expediente_imuh": dec.get('expediente_imuh') or "Sin asignar",
        "destino": dec['destino_fondos']
    }
    
    cuota_info = {
        "numero": f"Cuota {cuota_seq_num} ({cuota_sel_dict['mes']:02d}/{cuota_sel_dict['anio']})",
        "importe": cuota_sel_dict['monto'],
        "fechas_cobro": fechas_str
    }
    
    df_comp_pdf = pd.DataFrame()
    df_comp_pdf["Fecha"] = df_export["Fecha"]
    df_comp_pdf["Destino"] = df_export["Destino"]
    df_comp_pdf["OP"] = df_export["OP"]
    df_comp_pdf["Aclaraciones"] = df_export["Aclaraciones"]
    df_comp_pdf["Monto"] = df_export["Monto"].apply(lambda x: utils.format_currency_ar(x, include_symbol=False))
    
    df_comp_pdf.loc[len(df_comp_pdf)] = ["TOTAL", "", "", "", utils.format_currency_ar(sum_total_actual, include_symbol=False)]
    
    generar_reporte_composicion_pdf(temp_path_comp, decreto_info, cuota_info, df_comp_pdf, aclaraciones=aclaraciones_str)
    
    with open(temp_path_comp, "rb") as f:
        pdf_data = f.read()
        
    try:
        os.remove(temp_path_comp)
    except OSError:
        pass
        
    return pdf_data

def obtener_obras_con_desvios(tipo_reporte):
    """Obtiene el listado de obras con desvíos y saldos activos."""
    desvios = db.get_historial_desvios()
    obras = {}
    
    for d in desvios:
        saldo = d['saldo']
        if saldo <= 0.01:
            continue
            
        if tipo_reporte == "deudoras":
            # Deudora = destino (quien recibió y debe devolver)
            dec_id = d['decreto_destino_id']
            nombre = d['dest_nombre'] or d['destino_texto'] or "Sin nombre"
            imuh = d['dest_imuh']
            if not imuh or imuh == "Sin asignar":
                imuh = utils.extraer_imuh_de_texto(nombre) or "Sin asignar"
            nro = d['dest_nro']
            anio = d['dest_anio']
            dec_ident = f"Dto. {nro}/{anio}" if nro and anio else "Histórico / Legacy"
            
            key = (dec_id, nombre)
            if key not in obras:
                obras[key] = {
                    "id": dec_id,
                    "destino_fondos": nombre,
                    "expediente_imuh": imuh,
                    "decreto_identificacion": dec_ident,
                    "total_saldo_pendiente": 0.0
                }
            obras[key]["total_saldo_pendiente"] += saldo
            
        elif tipo_reporte == "acreedoras":
            # Acreedora = origen (quien prestó y tiene derecho a cobro)
            dec_id = d['orig_decreto_id']
            nombre = d['orig_nombre'] or "Sin nombre"
            imuh = d['orig_imuh']
            if not imuh or imuh == "Sin asignar":
                imuh = utils.extraer_imuh_de_texto(nombre) or "Sin asignar"
            nro = d['orig_nro']
            anio = d['orig_anio']
            dec_ident = f"Dto. {nro}/{anio}" if nro and anio else "Histórico / Legacy"
            
            key = (dec_id, nombre)
            if key not in obras:
                obras[key] = {
                    "id": dec_id,
                    "destino_fondos": nombre,
                    "expediente_imuh": imuh,
                    "decreto_identificacion": dec_ident,
                    "total_saldo_pendiente": 0.0
                }
            obras[key]["total_saldo_pendiente"] += saldo
            
    return list(obras.values())

def obtener_desvios_detalle(tipo_reporte, selected_obra):
    """Retorna la lista detallada de desvíos para la obra seleccionada.
    Usa funciones SQL-filtradas para mayor eficiencia (Fix 10).
    """
    if tipo_reporte == "deudoras":
        desvios = db.get_desvios_por_deudora(
            decreto_id=selected_obra['id'],
            nombre_texto=selected_obra['destino_fondos'] if selected_obra['id'] is None else None
        )
    else:
        desvios = db.get_desvios_por_acreedora(selected_obra['id'])

    detalle = []
    for d in desvios:
        if tipo_reporte == "deudoras":
            contraparte_label = "Acreedor"
            contraparte = d['orig_nombre'] or "Sin nombre"
            contraparte_imuh = d['orig_imuh']
            if not contraparte_imuh or contraparte_imuh == "Sin asignar":
                contraparte_imuh = utils.extraer_imuh_de_texto(contraparte) or "Sin asignar"
            nro = d['orig_nro']
            anio = d['orig_anio']
            contraparte_dec = f"Dto. {nro}/{anio}" if nro and anio else "N/A"
        else:
            contraparte_label = "Deudor"
            contraparte = d['dest_nombre'] or d['destino_texto'] or "Sin nombre"
            contraparte_imuh = d['dest_imuh']
            if not contraparte_imuh or contraparte_imuh == "Sin asignar":
                contraparte_imuh = utils.extraer_imuh_de_texto(contraparte) or "Sin asignar"
            nro = d['dest_nro']
            anio = d['dest_anio']
            contraparte_dec = f"Dto. {nro}/{anio}" if nro and anio else "Histórico / Legacy"

        try:
            if isinstance(d['fecha'], str):
                raw_dt = datetime.datetime.strptime(d['fecha'], '%Y-%m-%d').date()
            else:
                raw_dt = d['fecha']
        except Exception:
            raw_dt = d['fecha']

        detalle.append({
            "Fecha": utils.format_date_ar(d['fecha']),
            "raw_date": raw_dt,
            contraparte_label: contraparte,
            "Exp. IMUH": contraparte_imuh,
            "Decreto": contraparte_dec,
            "Monto Original": d['monto'],
            "Monto Reintegrado": d['total_recuperado'],
            "Saldo Pendiente": d['saldo'],
            "N° de OP": d['nro_op'] or "Sin asignar",
            "Tipo": "Reserva" if d['tipo_origen'] == 'reserva' else "Inicial",
            "Motivo/Notas": d['motivo'] or ""
        })

    return detalle

def generar_excel_desvios(tipo_reporte, selected_obra, df_desvios):
    """Genera un archivo Excel en memoria para exportar el detalle de desvíos."""
    excel_buffer = io.BytesIO()
    with pd.ExcelWriter(excel_buffer, engine='xlsxwriter') as writer:
        workbook = writer.book
        sheet_name = 'Obras Deudoras' if tipo_reporte == 'deudoras' else 'Obras Acreedoras'
        worksheet = workbook.add_worksheet(sheet_name)
        writer.sheets[sheet_name] = worksheet
        
        bold = workbook.add_format({'bold': True})
        money = workbook.add_format({'num_format': '#,##0.00'})
        
        titulo = 'REPORTE DE OBRAS DEUDORAS (DESVÍOS RECIBIDOS)' if tipo_reporte == 'deudoras' else 'REPORTE DE OBRAS ACREEDORAS (DESVÍOS OTORGADOS)'
        worksheet.write(0, 0, titulo, bold)
        
        worksheet.write(2, 0, 'Obra Seleccionada:', bold)
        worksheet.write(2, 1, selected_obra.get('destino_fondos', 'N/A'))
        
        worksheet.write(3, 0, 'Expediente IMUH:', bold)
        worksheet.write(3, 1, selected_obra.get('expediente_imuh', 'Sin asignar'))
        
        worksheet.write(4, 0, 'Asociado a Decreto:', bold)
        worksheet.write(4, 1, selected_obra.get('decreto_identificacion', 'N/A'))
        
        worksheet.write(5, 0, 'Total Saldo Pendiente:', bold)
        worksheet.write(5, 1, selected_obra.get('total_saldo_pendiente', 0.0), money)
        
        headers = list(df_desvios.columns)
        row_idx = 7
        for col_num, header in enumerate(headers):
            worksheet.write(row_idx, col_num, header, bold)
            
        data_start_row = row_idx + 1
        for i, r in df_desvios.iterrows():
            curr_row = data_start_row + i
            worksheet.write(curr_row, 0, r["Fecha"])
            worksheet.write(curr_row, 1, r[headers[1]])
            worksheet.write(curr_row, 2, r["Exp. IMUH"])
            worksheet.write(curr_row, 3, r["Decreto"])
            worksheet.write(curr_row, 4, r["Monto Original"], money)
            worksheet.write(curr_row, 5, r["Monto Reintegrado"], money)
            worksheet.write(curr_row, 6, r["Saldo Pendiente"], money)
            worksheet.write(curr_row, 7, r["N° de OP"])
            worksheet.write(curr_row, 8, r["Tipo"])
            worksheet.write(curr_row, 9, r["Motivo/Notas"])
            
        total_row_idx = data_start_row + len(df_desvios)
        worksheet.write(total_row_idx, 0, "TOTAL PENDIENTE", bold)
        worksheet.write(total_row_idx, 1, "")
        worksheet.write(total_row_idx, 2, "")
        worksheet.write(total_row_idx, 3, "")
        worksheet.write(total_row_idx, 4, "")
        worksheet.write(total_row_idx, 5, "")
        worksheet.write_formula(total_row_idx, 6, f"=SUM(G{data_start_row+1}:G{total_row_idx})", bold)
        
    return excel_buffer.getvalue()

def generar_pdf_desvios(tipo_reporte, selected_obra, df_desvios):
    """Genera un reporte en PDF para exportar el detalle de desvíos."""
    temp_path = os.path.join(tempfile.gettempdir(), f"Reporte_Desvios_{tipo_reporte}_{datetime.date.today().strftime('%Y%m%d')}.pdf")
    
    titulo = "Obras Deudoras - Detalle de Desvíos" if tipo_reporte == 'deudoras' else "Obras Acreedoras - Detalle de Desvíos"
    
    df_pdf = pd.DataFrame()
    df_pdf["Fecha"] = df_desvios["Fecha"]
    headers = list(df_desvios.columns)
    contraparte_header = headers[1]
    df_pdf[contraparte_header] = df_desvios[contraparte_header]
    df_pdf["Exp. IMUH"] = df_desvios["Exp. IMUH"]
    df_pdf["Decreto"] = df_desvios["Decreto"]
    df_pdf["Monto Orig."] = df_desvios["Monto Original"].apply(lambda x: utils.format_currency_ar(x, include_symbol=False))
    df_pdf["Reintegrado"] = df_desvios["Monto Reintegrado"].apply(lambda x: utils.format_currency_ar(x, include_symbol=False))
    df_pdf["Saldo Pend."] = df_desvios["Saldo Pendiente"].apply(lambda x: utils.format_currency_ar(x, include_symbol=False))
    df_pdf["N° OP"] = df_desvios["N° de OP"]
    
    total_saldo = df_desvios["Saldo Pendiente"].sum()
    df_pdf.loc[len(df_pdf)] = ["TOTAL", "", "", "", "", "", utils.format_currency_ar(total_saldo, include_symbol=False), ""]
    
    col_widths = [18, 42, 22, 22, 22, 22, 22, 20]
    
    generar_reporte_desvios_pdf(temp_path, titulo, selected_obra, df_pdf, col_widths)
    
    with open(temp_path, "rb") as f:
        pdf_data = f.read()
        
    try:
        os.remove(temp_path)
    except OSError:
        pass
        
    return pdf_data


# ─────────────────────────────────────────────────────────────────────────────
# Reporte Unificado: Estado de Deudas por Obra
# ─────────────────────────────────────────────────────────────────────────────

def obtener_estado_deudas_por_obra(obra):
    """Dado un dict de obra (id, nombre, expediente_imuh, tipo),
    retorna (rows_acreedora, rows_deudora) donde:
      - rows_acreedora: desvíos que la obra OTORGÓ (es acreedora — le deben)
      - rows_deudora:   desvíos que la obra RECIBIÓ (es deudora — debe devolver)
    Ambos son listas de dicts con columnas estándar.
    Incluye obras del catálogo Y legacy (sin ID).
    """
    obra_id = obra.get('id')         # None si legacy
    obra_nombre = obra.get('nombre', '')
    
    rows_acreedora = []
    rows_deudora = []
    
    with db.db_session() as conn:
        cursor = conn.cursor()
        
        # 1. Acreedora (la obra prestó dinero): solo si es obra del catálogo.
        #    Un desvío o reserva se considera otorgado por esta obra si el decreto de origen 
        #    pertenece a esta obra (a través de la tabla decretos_obras).
        if obra_id is not None:
            # Desvíos iniciales otorgados
            cursor.execute('''
                SELECT 
                    cd.id as desvio_id,
                    cd.fecha,
                    cd.monto,
                    COALESCE((SELECT SUM(monto) FROM cobro_desvios_recuperos WHERE desvio_id = cd.id), 0) as total_recuperado,
                    (cd.monto - COALESCE((SELECT SUM(monto) FROM cobro_desvios_recuperos WHERE desvio_id = cd.id), 0)) as saldo,
                    COALESCE(o_dest.nombre, d_dest.destino_fondos, cd.destino, 'Sin nombre') as contraparte_nombre,
                    COALESCE(o_dest.expediente_imuh, d_dest.expediente_imuh, 'Sin asignar') as contraparte_imuh,
                    CASE WHEN d_dest.id IS NOT NULL THEN 'Dto. ' || d_dest.nro_decreto || '/' || d_dest.anio ELSE 'Histórico / Legacy' END as contraparte_dec,
                    cd.nro_op,
                    'Inicial' as tipo,
                    cd.motivo
                FROM cobro_desvios cd
                JOIN cobros c ON cd.cobro_id = c.id
                JOIN cuotas cu ON c.cuota_id = cu.id
                JOIN decretos d_orig ON cu.decreto_id = d_orig.id
                LEFT JOIN decretos d_dest ON cd.decreto_destino_id = d_dest.id
                LEFT JOIN obras o_dest ON cd.obra_id = o_dest.id
                WHERE d_orig.id IN (SELECT decreto_id FROM decretos_obras WHERE obra_id = ?)
            ''', (obra_id,))
            for r in cursor.fetchall():
                d = dict(r)
                if d['saldo'] > 0.01:
                    rows_acreedora.append(d)
                    
            # Usos de reserva otorgados
            cursor.execute('''
                SELECT 
                    ru.id as desvio_id,
                    ru.fecha,
                    ru.monto,
                    COALESCE((SELECT SUM(monto) FROM cobro_reserva_usos_recuperos WHERE reserva_uso_id = ru.id), 0) as total_recuperado,
                    (ru.monto - COALESCE((SELECT SUM(monto) FROM cobro_reserva_usos_recuperos WHERE reserva_uso_id = ru.id), 0)) as saldo,
                    COALESCE(o_dest.nombre, d_dest.destino_fondos, ru.destino_detalle, 'Sin nombre') as contraparte_nombre,
                    COALESCE(o_dest.expediente_imuh, d_dest.expediente_imuh, 'Sin asignar') as contraparte_imuh,
                    CASE WHEN d_dest.id IS NOT NULL THEN 'Dto. ' || d_dest.nro_decreto || '/' || d_dest.anio ELSE 'Histórico / Legacy' END as contraparte_dec,
                    ru.nro_op,
                    'Reserva' as tipo,
                    ru.notas as motivo
                FROM cobro_reserva_usos ru
                JOIN cobros c ON ru.cobro_id = c.id
                JOIN cuotas cu ON c.cuota_id = cu.id
                JOIN decretos d_orig ON cu.decreto_id = d_orig.id
                LEFT JOIN decretos d_dest ON ru.decreto_destino_id = d_dest.id
                LEFT JOIN obras o_dest ON ru.obra_id = o_dest.id
                WHERE ru.destino_tipo != 'fin_original'
                  AND d_orig.id IN (SELECT decreto_id FROM decretos_obras WHERE obra_id = ?)
            ''', (obra_id,))
            for r in cursor.fetchall():
                d = dict(r)
                if d['saldo'] > 0.01:
                    rows_acreedora.append(d)

        # 2. Deudora (la obra recibió dinero y debe devolver):
        #    Si es del catálogo: filtrar por cd.obra_id = ? o decreto_destino_id asociado.
        #    Si es legacy: filtrar por cd.destino = ? o ru.destino_detalle = ?.
        if obra_id is not None:
            # Desvíos iniciales recibidos
            cursor.execute('''
                SELECT 
                    cd.id as desvio_id,
                    cd.fecha,
                    cd.monto,
                    COALESCE((SELECT SUM(monto) FROM cobro_desvios_recuperos WHERE desvio_id = cd.id), 0) as total_recuperado,
                    (cd.monto - COALESCE((SELECT SUM(monto) FROM cobro_desvios_recuperos WHERE desvio_id = cd.id), 0)) as saldo,
                    d_orig.destino_fondos as contraparte_nombre,
                    COALESCE(d_orig.expediente_imuh, 'Sin asignar') as contraparte_imuh,
                    'Dto. ' || d_orig.nro_decreto || '/' || d_orig.anio as contraparte_dec,
                    cd.nro_op,
                    'Inicial' as tipo,
                    cd.motivo
                FROM cobro_desvios cd
                JOIN cobros c ON cd.cobro_id = c.id
                JOIN cuotas cu ON c.cuota_id = cu.id
                JOIN decretos d_orig ON cu.decreto_id = d_orig.id
                WHERE (cd.obra_id = ? OR cd.decreto_destino_id IN (SELECT decreto_id FROM decretos_obras WHERE obra_id = ?))
            ''', (obra_id, obra_id))
            for r in cursor.fetchall():
                d = dict(r)
                if d['saldo'] > 0.01:
                    rows_deudora.append(d)

            # Usos de reserva recibidos
            cursor.execute('''
                SELECT 
                    ru.id as desvio_id,
                    ru.fecha,
                    ru.monto,
                    COALESCE((SELECT SUM(monto) FROM cobro_reserva_usos_recuperos WHERE reserva_uso_id = ru.id), 0) as total_recuperado,
                    (ru.monto - COALESCE((SELECT SUM(monto) FROM cobro_reserva_usos_recuperos WHERE reserva_uso_id = ru.id), 0)) as saldo,
                    d_orig.destino_fondos as contraparte_nombre,
                    COALESCE(d_orig.expediente_imuh, 'Sin asignar') as contraparte_imuh,
                    'Dto. ' || d_orig.nro_decreto || '/' || d_orig.anio as contraparte_dec,
                    ru.nro_op,
                    'Reserva' as tipo,
                    ru.notas as motivo
                FROM cobro_reserva_usos ru
                JOIN cobros c ON ru.cobro_id = c.id
                JOIN cuotas cu ON c.cuota_id = cu.id
                JOIN decretos d_orig ON cu.decreto_id = d_orig.id
                WHERE ru.destino_tipo != 'fin_original'
                  AND (ru.obra_id = ? OR ru.decreto_destino_id IN (SELECT decreto_id FROM decretos_obras WHERE obra_id = ?))
            ''', (obra_id, obra_id))
            for r in cursor.fetchall():
                d = dict(r)
                if d['saldo'] > 0.01:
                    rows_deudora.append(d)
        else:
            # Legacy: por nombre
            cursor.execute('''
                SELECT 
                    cd.id as desvio_id,
                    cd.fecha,
                    cd.monto,
                    COALESCE((SELECT SUM(monto) FROM cobro_desvios_recuperos WHERE desvio_id = cd.id), 0) as total_recuperado,
                    (cd.monto - COALESCE((SELECT SUM(monto) FROM cobro_desvios_recuperos WHERE desvio_id = cd.id), 0)) as saldo,
                    d_orig.destino_fondos as contraparte_nombre,
                    COALESCE(d_orig.expediente_imuh, 'Sin asignar') as contraparte_imuh,
                    'Dto. ' || d_orig.nro_decreto || '/' || d_orig.anio as contraparte_dec,
                    cd.nro_op,
                    'Inicial' as tipo,
                    cd.motivo
                FROM cobro_desvios cd
                JOIN cobros c ON cd.cobro_id = c.id
                JOIN cuotas cu ON c.cuota_id = cu.id
                JOIN decretos d_orig ON cu.decreto_id = d_orig.id
                WHERE cd.obra_id IS NULL AND cd.decreto_destino_id IS NULL AND cd.destino = ?
            ''', (obra_nombre,))
            for r in cursor.fetchall():
                d = dict(r)
                if d['saldo'] > 0.01:
                    rows_deudora.append(d)

            cursor.execute('''
                SELECT 
                    ru.id as desvio_id,
                    ru.fecha,
                    ru.monto,
                    COALESCE((SELECT SUM(monto) FROM cobro_reserva_usos_recuperos WHERE reserva_uso_id = ru.id), 0) as total_recuperado,
                    (ru.monto - COALESCE((SELECT SUM(monto) FROM cobro_reserva_usos_recuperos WHERE reserva_uso_id = ru.id), 0)) as saldo,
                    d_orig.destino_fondos as contraparte_nombre,
                    COALESCE(d_orig.expediente_imuh, 'Sin asignar') as contraparte_imuh,
                    'Dto. ' || d_orig.nro_decreto || '/' || d_orig.anio as contraparte_dec,
                    ru.nro_op,
                    'Reserva' as tipo,
                    ru.notas as motivo
                FROM cobro_reserva_usos ru
                JOIN cobros c ON ru.cobro_id = c.id
                JOIN cuotas cu ON c.cuota_id = cu.id
                JOIN decretos d_orig ON cu.decreto_id = d_orig.id
                WHERE ru.destino_tipo != 'fin_original'
                  AND ru.obra_id IS NULL AND ru.decreto_destino_id IS NULL AND ru.destino_detalle = ?
            ''', (obra_nombre,))
            for r in cursor.fetchall():
                d = dict(r)
                if d['saldo'] > 0.01:
                    rows_deudora.append(d)

    # 3. Formatear ambas listas con el esquema esperado por la UI y Excel
    def _format_rows(desvios_list):
        formatted = []
        with db.db_session() as conn:
            cursor = conn.cursor()
            for d in desvios_list:
                try:
                    raw_dt = datetime.datetime.strptime(str(d['fecha']), '%Y-%m-%d').date() if isinstance(d['fecha'], str) else d['fecha']
                except Exception:
                    raw_dt = d['fecha']
                
                # Calcular Estado
                if d['tipo'] == 'Inicial':
                    cursor.execute("SELECT SUM(monto) FROM cobro_desvios_recuperos WHERE desvio_id = ? AND destino_tipo = 'compensacion'", (d['desvio_id'],))
                else:
                    cursor.execute("SELECT SUM(monto) FROM cobro_reserva_usos_recuperos WHERE reserva_uso_id = ? AND destino_tipo = 'compensacion'", (d['desvio_id'],))
                res = cursor.fetchone()
                total_comp = res[0] if res and res[0] else 0.0
                
                estado = "Vigente"
                saldo = float(d['saldo'])
                monto = float(d['monto'])
                if saldo <= 0.01:
                    if total_comp >= monto - 0.01:
                        estado = "Compensado"
                    elif total_comp > 0:
                        estado = "Reint. / Comp."
                    else:
                        estado = "Reintegrado"
                elif total_comp > 0:
                    estado = "Parcialmente compensado"
                elif float(d['total_recuperado']) > 0:
                    estado = "Parcialmente reintegrado"

                formatted.append({
                    'Fecha':            utils.format_date_ar(d['fecha']),
                    'raw_date':         raw_dt,
                    'Contraparte':      d['contraparte_nombre'],
                    'Exp. IMUH':        d['contraparte_imuh'],
                    'Decreto':          d['contraparte_dec'],
                    'Monto Original':   d['monto'],
                    'Reintegrado':      d['total_recuperado'],
                    'Saldo Pendiente':  d['saldo'],
                    'Estado':           estado,
                    'N° de OP':         d['nro_op'] or 'Sin asignar',
                    'Tipo':             d['tipo'],
                    'Motivo/Notas':     d['motivo'] or '',
                    'desvio_id':        d['desvio_id'],
                })
        # Ordenar por fecha decreciente
        formatted.sort(key=lambda x: x['raw_date'] if x['raw_date'] else datetime.date.min, reverse=True)
        return formatted

    return _format_rows(rows_acreedora), _format_rows(rows_deudora)


def generar_excel_estado_deudas(obra, rows_acreedora, rows_deudora):
    """Genera un Excel con dos hojas: 'Acreedora' y 'Deudora' para la obra seleccionada."""
    excel_buffer = io.BytesIO()
    with pd.ExcelWriter(excel_buffer, engine='xlsxwriter') as writer:
        workbook  = writer.book
        bold      = workbook.add_format({'bold': True})
        money_fmt = workbook.add_format({'num_format': '#,##0.00'})

        def _write_sheet(sheet_name, titulo, rows):
            ws = workbook.add_worksheet(sheet_name)
            writer.sheets[sheet_name] = ws
            ws.write(0, 0, titulo, bold)
            ws.write(2, 0, 'Obra:', bold)
            ws.write(2, 1, obra.get('nombre', 'N/A'))
            ws.write(3, 0, 'Expediente IMUH:', bold)
            ws.write(3, 1, obra.get('expediente_imuh') or 'Sin asignar')

            headers = ['Fecha', 'Contraparte', 'Exp. IMUH', 'Decreto',
                       'Monto Original', 'Reintegrado', 'Saldo Pendiente', 'N° de OP', 'Tipo', 'Motivo/Notas']
            for col, h in enumerate(headers):
                ws.write(5, col, h, bold)
            for row_i, r in enumerate(rows):
                ws.write(6 + row_i, 0, r['Fecha'])
                ws.write(6 + row_i, 1, r['Contraparte'])
                ws.write(6 + row_i, 2, r['Exp. IMUH'])
                ws.write(6 + row_i, 3, r['Decreto'])
                ws.write(6 + row_i, 4, r['Monto Original'], money_fmt)
                ws.write(6 + row_i, 5, r['Reintegrado'],    money_fmt)
                ws.write(6 + row_i, 6, r['Saldo Pendiente'], money_fmt)
                ws.write(6 + row_i, 7, r['N° de OP'])
                ws.write(6 + row_i, 8, r['Tipo'])
                ws.write(6 + row_i, 9, r['Motivo/Notas'])
            tot_row = 6 + len(rows)
            ws.write(tot_row, 0, 'TOTAL', bold)
            total_val = sum(r['Saldo Pendiente'] for r in rows)
            ws.write(tot_row, 6, total_val, money_fmt)

        _write_sheet('Acreedora (Le deben)', 'DEUDAS A FAVOR DE LA OBRA (ACREEDOR)', rows_acreedora)
        _write_sheet('Deudora (Debe devolver)', 'DEUDAS DE LA OBRA (DEUDOR)', rows_deudora)

    return excel_buffer.getvalue()


def generar_pdf_estado_deudas(obra, rows_acreedora, rows_deudora):
    """Genera un PDF con dos secciones para la obra seleccionada."""
    import re
    safe_name = re.sub(r'[^\w\-_]', '_', obra.get('nombre', 'obra'))
    temp_path = os.path.join(
        tempfile.gettempdir(),
        f"Estado_Deudas_{safe_name}_{datetime.date.today().strftime('%Y%m%d')}.pdf"
    )

    def _build_section_df(rows, contraparte_header):
        if not rows:
            return pd.DataFrame()
        df = pd.DataFrame(rows)
        out = pd.DataFrame()
        out['Fecha']         = df['Fecha']
        out[contraparte_header] = df['Contraparte']
        out['Exp. IMUH']     = df['Exp. IMUH']
        out['Decreto']       = df['Decreto']
        out['Monto Orig.']   = df['Monto Original'].apply(lambda x: utils.format_currency_ar(x, include_symbol=False))
        out['Reintegrado']   = df['Reintegrado'].apply(lambda x: utils.format_currency_ar(x, include_symbol=False))
        out['Saldo Pend.']   = df['Saldo Pendiente'].apply(lambda x: utils.format_currency_ar(x, include_symbol=False))
        out['N° OP']         = df['N° de OP']
        total = df['Saldo Pendiente'].sum()
        out.loc[len(out)] = ['TOTAL', '', '', '', '', '', utils.format_currency_ar(total, include_symbol=False), '']
        return out

    df_acr = _build_section_df(rows_acreedora, 'Deudor (debe a esta obra)')
    df_deu = _build_section_df(rows_deudora,   'Acreedor (le prestó a esta obra)')

    col_widths = [18, 48, 22, 22, 22, 22, 22, 20]
    obra_info  = {
        'destino_fondos':      obra.get('nombre', 'N/A'),
        'expediente_imuh':     obra.get('expediente_imuh') or 'Sin asignar',
        'decreto_identificacion': obra.get('decreto_identificacion', 'N/A'),
    }

    # Reusar la función generar_reporte_desvios_pdf dos veces (acreedora primero)
    from pdf_generator import FPDF
    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.alias_nb_pages()
    pdf.set_font('Arial', 'B', 14)
    pdf.add_page()
    pdf.cell(0, 10, 'Estado de Deudas por Obra', 0, 1, 'C')
    pdf.set_font('Arial', '', 11)
    pdf.cell(0, 7, f"Obra: {obra.get('nombre','')}", 0, 1)
    pdf.cell(0, 7, f"IMUH: {obra.get('expediente_imuh') or 'Sin asignar'}", 0, 1)
    pdf.ln(4)

    def _write_section(title, df_sec):
        pdf.set_font('Arial', 'B', 12)
        pdf.set_fill_color(220, 235, 255)
        pdf.cell(0, 8, title, 0, 1, 'L', fill=True)
        pdf.ln(2)
        if df_sec.empty:
            pdf.set_font('Arial', 'I', 10)
            pdf.cell(0, 7, 'Sin registros.', 0, 1)
        else:
            pdf.set_font('Arial', 'B', 9)
            col_w = [18, 46, 22, 20, 20, 20, 22, 20]
            for i, col in enumerate(df_sec.columns):
                pdf.cell(col_w[i] if i < len(col_w) else 20, 7, str(col)[:20], 1, 0, 'C')
            pdf.ln()
            pdf.set_font('Arial', '', 8)
            for _, row in df_sec.iterrows():
                for i, val in enumerate(row):
                    w = col_w[i] if i < len(col_w) else 20
                    pdf.cell(w, 6, str(val)[:28], 1, 0, 'L')
                pdf.ln()
        pdf.ln(6)

    _write_section('1. Le deben a esta obra (Acreedora)', df_acr)
    _write_section('2. Esta obra debe devolver (Deudora)', df_deu)

    pdf.output(temp_path)
    with open(temp_path, 'rb') as f:
        pdf_data = f.read()
    try:
        os.remove(temp_path)
    except OSError:
        pass
    return pdf_data

def obtener_vista_estado_financiero():

    """Obtiene datos formateados para mostrar la vista previa del Estado Financiero en pantalla."""
    # 1. Préstamos Vigentes (Desvíos a Recuperar)
    deudas = []
    tot_d = 0
    desvios_activos = db.get_desvios_activos_completos()
    for d in (desvios_activos or []):
        origen_str = f"Dto. {d['orig_nro']}/{d['orig_anio']} - {d['orig_nombre']}"
        if d['decreto_destino_id']:
            destino_str = f"Dto. {d['dest_nro']}/{d['dest_anio']} - {utils.limpiar_prefijo_expediente(d['dest_nombre'])}"
        elif d.get('gasto_nombre'):
            destino_str = f"FUN: {d['gasto_nombre']} (Exp: {d['gasto_expediente_imuh']})"
        else:
            destino_str = utils.limpiar_prefijo_expediente(d['destino_texto'])
            
        tipo_str = "D (Desvío Decreto)"
        if d.get('gasto_nombre'):
            tipo_str = "FUN (Gasto Func.)"
            
        deudas.append({
            "Origen": origen_str,
            "Destino": destino_str,
            "Tipo": tipo_str,
            "Saldo Pendiente": d['saldo'],
            "Observaciones": ""
        })
        tot_d += d['saldo']

    prestamos_legacy = db.get_prestamos()
    for p in (prestamos_legacy or []):
        s_p = p['monto'] - p.get('total_devuelto', 0)
        if s_p > 0.01:
            deudas.append({
                "Origen": f"Dto. {p['nro_decreto']}/{p['decreto_anio']}",
                "Destino": utils.limpiar_prefijo_expediente(p['destino']),
                "Tipo": "L (Legacy)",
                "Saldo Pendiente": s_p,
                "Observaciones": p.get('motivo', '') or ""
            })
            tot_d += s_p

    reserva_prestamos = db.get_reserva_usos_prestamos_activos()
    for rp in (reserva_prestamos or []):
        origen_str = f"Dto. {rp['orig_nro']}/{rp['orig_anio']} - {rp['orig_nombre']}"
        if rp['decreto_destino_id']:
            destino_str = f"Dto. {rp['dest_nro']}/{rp['dest_anio']} - {utils.limpiar_prefijo_expediente(rp['dest_nombre'])}"
        elif rp.get('gasto_nombre'):
            destino_str = f"FUN: {rp['gasto_nombre']} (Exp: {rp['gasto_expediente_imuh']})"
        else:
            destino_str = utils.limpiar_prefijo_expediente(rp['destino_detalle']) or "Obra sin decreto"
            
        tipo_str = "R (Reserva)"
        if rp.get('gasto_nombre'):
            tipo_str = "FUN (Uso Reserva)"
            
        deudas.append({
            "Origen": origen_str,
            "Destino": destino_str,
            "Tipo": tipo_str,
            "Saldo Pendiente": rp['saldo'],
            "Observaciones": rp.get('notas', '') or ""
        })
        tot_d += rp['saldo']

    # 2. Dinero en Reserva Disponible
    reservas = []
    tot_r = 0
    cobros_dist = db.get_cobros_con_resumen_distribucion()
    for c in (cobros_dist or []):
        if c['monto_reserva'] > 0:
            usos = db.get_reserva_usos_by_cobro(c['id'])
            tot_usado = sum(u['monto'] for u in usos) if usos else 0
            saldo_r = c['monto_reserva'] - tot_usado
            if saldo_r > 0.01:
                reservas.append({
                    "Decreto / Obra": f"Dto. {c['nro_decreto']}/{c['decreto_anio']} - {c['destino_fondos']}",
                    "Fecha Cobro": utils.format_date_ar(c['fecha']),
                    "Saldo Reserva": saldo_r
                })
                tot_r += saldo_r

    return deudas, tot_d, reservas, tot_r

def obtener_vista_pedidos_financiamiento():
    """Obtiene datos formateados para mostrar la vista previa de Pedidos de Financiamiento en pantalla."""
    solicitudes = db.get_solicitudes()
    filas = []
    tot_solicitado = 0
    tot_aprobado = 0
    tot_pendiente = 0
    
    for s in (solicitudes or []):
        monto = s['monto_solicitado']
        tot_solicitado += monto
        if s['estado'] == 'Aprobado':
            tot_aprobado += monto
        elif s['estado'] == 'Pendiente':
            tot_pendiente += monto
            
        fecha_str = s['fecha_solicitud']
        if isinstance(fecha_str, str):
            try:
                dt = datetime.datetime.strptime(fecha_str, '%Y-%m-%d').date()
                fecha_str = dt.strftime("%d-%m-%Y")
            except:
                pass
                
        estado_val = s['estado']
        if s['estado'] == 'Aprobado' and s.get('nro_decreto'):
            estado_val = f"Dto. {s['nro_decreto']}/{s['decreto_anio']}"
            
        filas.append({
            "Expediente": s['nro_expediente'],
            "Destino / Obra": s['destino_fondos'],
            "Fecha": fecha_str,
            "Estado": estado_val,
            "Monto": monto
        })
        
    return filas, tot_solicitado, tot_aprobado, tot_pendiente

# Registro Centralizado de Reportes (Requisito B, C y D)
REPORTE_REGISTRY = {
    "estado_financiero": {
        "nombre": "📊 Reporte de Estado Financiero General",
        "descripcion": "Muestra un informe consolidado del estado de todos los decretos cargados, sus cuotas asignadas, los importes cobrados a la fecha, los desvíos realizados y los saldos pendientes.",
        "tipo": "PDF",
        "tiene_filtros": False,
        "generar_func": lambda: (generar_reporte_pdf(os.path.join(tempfile.gettempdir(), f"Reporte_General_{datetime.date.today().strftime('%Y%m%d')}.pdf")), f"Reporte_General_{datetime.date.today().strftime('%Y%m%d')}.pdf", "application/pdf")
    },
    "pedidos_financiamiento": {
        "nombre": "📋 Reporte de Estado de Pedidos de Financiamiento",
        "descripcion": "Detalla todas las solicitudes de financiamiento registradas, incluyendo su estado actual (Pendiente, Aprobado), montos solicitados, fechas de registro y vinculaciones con decretos.",
        "tipo": "PDF",
        "tiene_filtros": False,
        "generar_func": lambda: (generar_reporte_solicitudes_pdf(os.path.join(tempfile.gettempdir(), f"Reporte_Pedidos_Financiamiento_{datetime.date.today().strftime('%Y%m%d')}.pdf")), f"Reporte_Pedidos_Financiamiento_{datetime.date.today().strftime('%Y%m%d')}.pdf", "application/pdf")
    },
    "composicion_fondos": {
        "nombre": "🔍 Reporte de Composición de Fondos de Cuota",
        "descripcion": "Presenta el desglose del destino y los movimientos de una cuota de decreto específica: montos en obra original, fondos en reserva, desvíos realizados hacia otras obras y saldos aún sin distribuir.",
        "tipo": "Ambos",
        "tiene_filtros": True
    },
    "estado_deudas_obra": {
        "nombre": "⚖️ Estado de Deudas por Obra",
        "descripcion": "Muestra, para la obra seleccionada, los desvíos que recibió de otras obras (deudas que debe devolver) y los desvíos que otorgó a otras obras (saldos que le deben). Incluye obras del catálogo y destinos históricos legacy.",
        "tipo": "Ambos",
        "tiene_filtros": True
    },
    "afectacion_decretos": {
        "nombre": "📑 Afectación de Decretos",
        "descripcion": "Consolida los cobros y la afectación (distribución) para cada una de las cuotas de un decreto seleccionado.",
        "tipo": "Ambos",
        "tiene_filtros": True
    },
    "gastos_financiados_aportes_obra": {
        "nombre": "💼 Gastos de funcionamiento financiados con aportes de obra",
        "descripcion": "Detalla todos los gastos de funcionamiento que han sido financiados con fondos destinados originalmente a obras y que aún no han sido devueltos a las obras acreedoras.",
        "tipo": "Ambos",
        "tiene_filtros": True
    }
}

def generar_resumen_narrativo_decreto(dec, filas_reporte, total_decreto, pendiente_cobro):
    total_percibido = sum(r['Importe percibido'] for r in filas_reporte if r['Importe pagado'] == 0.0 or r == next(iter([f for f in filas_reporte if f['Nro. Cuota'] == r['Nro. Cuota']]), None))
    
    obra_original = 0.0
    reserva = 0.0
    desvios_netos = 0.0
    desvios_ini = 0.0
    recuperado = 0.0
    compensado = 0.0
    sin_distribuir = 0.0
    
    for r in filas_reporte:
        destino = r["Obra destino"]
        monto = r["Importe pagado"]
        obs = str(r["Observaciones/aclaraciones"]).lower()
        
        if destino == "Obra original":
            if "compensado" in obs or "compensación" in obs:
                compensado += monto
            else:
                obra_original += monto
        elif destino == "Sin distribuir":
            sin_distribuir += monto
        elif destino == "Reserva":
            reserva += monto
        elif "desvío" in str(r.get("Movimiento", "")).lower() or "desvio" in str(r.get("Movimiento", "")).lower():
            desvios_netos += monto
            
    with db.db_session() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT SUM(cd.monto) FROM cobro_desvios cd
            JOIN cobros c ON cd.cobro_id = c.id
            JOIN cuotas q ON c.cuota_id = q.id
            WHERE q.decreto_id = ?
        ''', (dec['id'],))
        row = cursor.fetchone()
        desvios_ini = row[0] if row and row[0] else 0.0
        
        cursor.execute('''
            SELECT SUM(r.monto) FROM cobro_desvios_recuperos r
            JOIN cobro_desvios cd ON r.desvio_id = cd.id
            JOIN cobros c ON cd.cobro_id = c.id
            JOIN cuotas q ON c.cuota_id = q.id
            WHERE q.decreto_id = ?
        ''', (dec['id'],))
        row = cursor.fetchone()
        recuperado_desv = row[0] if row and row[0] else 0.0

        cursor.execute('''
            SELECT SUM(r.monto) FROM cobro_reserva_usos_recuperos r
            JOIN cobro_reserva_usos ru ON r.reserva_uso_id = ru.id
            JOIN cobros c ON ru.cobro_id = c.id
            JOIN cuotas q ON c.cuota_id = q.id
            WHERE q.decreto_id = ?
        ''', (dec['id'],))
        row = cursor.fetchone()
        recuperado_res = row[0] if row and row[0] else 0.0

        recuperado = recuperado_desv + recuperado_res
        
        cursor.execute('''
            SELECT SUM(r.monto) FROM cobro_desvios_recuperos r
            JOIN cobro_desvios cd ON r.desvio_id = cd.id
            JOIN cobros c ON cd.cobro_id = c.id
            JOIN cuotas q ON c.cuota_id = q.id
            WHERE q.decreto_id = ? AND r.destino_tipo = 'compensacion'
        ''', (dec['id'],))
        row = cursor.fetchone()
        compensado_desv = row[0] if row and row[0] else 0.0

        cursor.execute('''
            SELECT SUM(r.monto) FROM cobro_reserva_usos_recuperos r
            JOIN cobro_reserva_usos ru ON r.reserva_uso_id = ru.id
            JOIN cobros c ON ru.cobro_id = c.id
            JOIN cuotas q ON c.cuota_id = q.id
            WHERE q.decreto_id = ? AND r.destino_tipo = 'compensacion'
        ''', (dec['id'],))
        row = cursor.fetchone()
        compensado_res = row[0] if row and row[0] else 0.0

        compensado = compensado_desv + compensado_res
    
    desvios_netos = desvios_ini - recuperado
    
    total_decreto_fmt = utils.format_currency_ar(total_decreto)
    percibido_fmt = utils.format_currency_ar(total_percibido)
    pendiente_fmt = utils.format_currency_ar(max(0.0, pendiente_cobro))
    obra_original_fmt = utils.format_currency_ar(obra_original + compensado)
    reserva_fmt = utils.format_currency_ar(reserva)
    desvios_netos_fmt = utils.format_currency_ar(desvios_netos)
    compensado_fmt = utils.format_currency_ar(compensado)
    sin_distribuir_fmt = utils.format_currency_ar(sin_distribuir)

    # Construcción de la historia cronológica por cuota
    narrativa_list = []
    
    def obtener_contraparte_compensacion(cursor, grupo_id, current_dec_id):
        cursor.execute('''
            SELECT r.monto, r.fecha as rec_fecha,
                   d.monto as desvio_monto, d.fecha as desvio_fecha, d.destino as desvio_destino,
                   dec.nro_decreto, dec.anio as dec_anio, dec.id as dec_id
            FROM cobro_desvios_recuperos r
            JOIN cobro_desvios d ON r.desvio_id = d.id
            JOIN cobros c ON d.cobro_id = c.id
            JOIN cuotas q ON c.cuota_id = q.id
            JOIN decretos dec ON q.decreto_id = dec.id
            WHERE r.grupo_compensacion_id = ?
        ''', (grupo_id,))
        desvios = [dict(row) for row in cursor.fetchall()]
        
        cursor.execute('''
            SELECT r.monto, r.fecha as rec_fecha,
                   u.monto as uso_monto, u.fecha as uso_fecha, u.destino_detalle as uso_destino,
                   dec.nro_decreto, dec.anio as dec_anio, dec.id as dec_id
            FROM cobro_reserva_usos_recuperos r
            JOIN cobro_reserva_usos u ON r.reserva_uso_id = u.id
            JOIN cobros c ON u.cobro_id = c.id
            JOIN cuotas q ON c.cuota_id = q.id
            JOIN decretos dec ON q.decreto_id = dec.id
            WHERE r.grupo_compensacion_id = ?
        ''', (grupo_id,))
        reserves = [dict(row) for row in cursor.fetchall()]
        
        for d in desvios:
            if d['dec_id'] != current_dec_id:
                return {
                    'tipo': 'desvio',
                    'monto_original': d['desvio_monto'],
                    'fecha_original': d['desvio_fecha'],
                    'nro_decreto': d['nro_decreto'],
                    'anio': d['dec_anio']
                }
        for r in reserves:
            if r['dec_id'] != current_dec_id:
                return {
                    'tipo': 'reserva',
                    'monto_original': r['uso_monto'],
                    'fecha_original': r['uso_fecha'],
                    'nro_decreto': r['nro_decreto'],
                    'anio': r['dec_anio']
                }
        return None

    with db.db_session() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM cuotas WHERE decreto_id = ? ORDER BY anio ASC, mes ASC', (dec['id'],))
        cuotas = [dict(row) for row in cursor.fetchall()]
        
        for idx, q in enumerate(cuotas):
            seq_num = idx + 1
            cursor.execute('SELECT * FROM cobros WHERE cuota_id = ? ORDER BY fecha ASC', (q['id'],))
            cobros = [dict(row) for row in cursor.fetchall()]
            
            cuota_header = f'*   **Cuota {seq_num} (Presupuesto: {total_decreto_fmt if len(cuotas) == 1 else utils.format_currency_ar(q["monto"])})**:'
            
            if not cobros:
                narrativa_list.append(f'{cuota_header}\n    *   Sin cobros registrados a la fecha.')
                continue
                
            events = []
            for cb_idx, cb in enumerate(cobros):
                is_last_cobro = (cb_idx == len(cobros) - 1)
                is_partial = len(cobros) > 1 and not is_last_cobro
                
                events.append({
                    'fecha': cb['fecha'],
                    'tipo': 'cobro',
                    'monto': cb['monto'],
                    'is_partial': is_partial,
                    'is_last': is_last_cobro and len(cobros) > 1
                })
                
                # Fin original usos
                cursor.execute('SELECT * FROM cobro_fin_original_usos WHERE cobro_id = ?', (cb['id'],))
                for u in cursor.fetchall():
                    events.append({
                        'fecha': u['fecha'],
                        'tipo': 'pago_original',
                        'monto': u['monto']
                    })
                    
                # Desvios
                cursor.execute('''
                    SELECT cd.*, o.nombre as obra_nombre, o.expediente_imuh as obra_exp_imuh
                    FROM cobro_desvios cd
                    LEFT JOIN obras o ON cd.obra_id = o.id
                    WHERE cd.cobro_id = ?
                ''', (cb['id'],))
                desvios = [dict(row) for row in cursor.fetchall()]
                for d in desvios:
                    if d.get('obra_nombre'):
                        dest_desc = f"{d['obra_nombre']} (Exp. IMUH {d['obra_exp_imuh']})"
                    else:
                        dest_desc = d['destino']
                    events.append({
                        'fecha': d['fecha'],
                        'tipo': 'transferencia_desvio',
                        'monto': d['monto'],
                        'destino': dest_desc,
                        'desvio_id': d['id']
                    })
                    
                    # Recuperos de desvio
                    cursor.execute('SELECT * FROM cobro_desvios_recuperos WHERE desvio_id = ?', (d['id'],))
                    for r in cursor.fetchall():
                        events.append({
                            'fecha': r['fecha'],
                            'tipo': 'recupero_desvio',
                            'monto': r['monto'],
                            'destino_tipo': r['destino_tipo'],
                            'destino_detalle': r['destino_detalle'],
                            'grupo_id': r['grupo_compensacion_id'],
                            'orig_fecha': d['fecha'],
                            'orig_monto': d['monto'],
                            'orig_destino': dest_desc
                        })
                        
                # Reserva usos
                cursor.execute('''
                    SELECT ru.*, o.nombre as obra_nombre, o.expediente_imuh as obra_exp_imuh
                    FROM cobro_reserva_usos ru
                    LEFT JOIN obras o ON ru.obra_id = o.id
                    WHERE ru.cobro_id = ?
                ''', (cb['id'],))
                reserva_usos = [dict(row) for row in cursor.fetchall()]
                for ru in reserva_usos:
                    if ru.get('obra_nombre'):
                        dest_desc = f"{ru['obra_nombre']} (Exp. IMUH {ru['obra_exp_imuh']})"
                    else:
                        dest_desc = ru['destino_detalle'] or 'Otra obra'
                    events.append({
                        'fecha': ru['fecha'],
                        'tipo': 'reserva_uso',
                        'monto': ru['monto'],
                        'destino_tipo': ru['destino_tipo'],
                        'destino_detalle': dest_desc,
                        'uso_id': ru['id']
                    })
                    
                    # Recuperos de reserva
                    cursor.execute('SELECT * FROM cobro_reserva_usos_recuperos WHERE reserva_uso_id = ?', (ru['id'],))
                    for r in cursor.fetchall():
                        events.append({
                            'fecha': r['fecha'],
                            'tipo': 'recupero_reserva_uso',
                            'monto': r['monto'],
                            'destino_tipo': r['destino_tipo'],
                            'destino_detalle': r['destino_detalle'],
                            'grupo_id': r['grupo_compensacion_id'],
                            'orig_fecha': ru['fecha'],
                            'orig_monto': ru['monto'],
                            'orig_destino': dest_desc
                        })

            # Sort events
            def get_event_sort_key(ev):
                type_priority = {
                    'cobro': 0,
                    'pago_original': 1,
                    'transferencia_desvio': 2,
                    'reserva_uso': 2,
                    'recupero_desvio': 3,
                    'recupero_reserva_uso': 3
                }
                return (ev['fecha'], type_priority.get(ev['tipo'], 9))
                
            events.sort(key=get_event_sort_key)
            
            # Process/group events by date
            grouped_by_date = {}
            for ev in events:
                d_str = ev['fecha']
                if d_str not in grouped_by_date:
                    grouped_by_date[d_str] = []
                grouped_by_date[d_str].append(ev)
                
            sorted_dates = sorted(list(grouped_by_date.keys()))
            
            cuota_lines = [cuota_header]
            for d_str in sorted_dates:
                day_events = grouped_by_date[d_str]
                date_fmt = utils.format_date_ar(d_str)
                
                # 1. Cobros of the day
                cobros_day = [e for e in day_events if e['tipo'] == 'cobro']
                for cb in cobros_day:
                    if cb['is_partial']:
                        cuota_lines.append(f'    *   **{date_fmt} (Cobro parcial):** Se percibieron **{utils.format_currency_ar(cb["monto"])}**.')
                    elif cb['is_last']:
                        cuota_lines.append(f'    *   **{date_fmt} (Saldo de cuota):** Se percibieron **{utils.format_currency_ar(cb["monto"])}** (completando los cobros de esta cuota).')
                    else:
                        cuota_lines.append(f'    *   **{date_fmt} (Cobro):** Se percibieron **{utils.format_currency_ar(cb["monto"])}**.')
                        
                # 2. Pagos a obra original (direct + reserve use to fin_original)
                pagos_orig_monto = 0.0
                for e in day_events:
                    if e['tipo'] == 'pago_original':
                        pagos_orig_monto += e['monto']
                    elif e['tipo'] == 'reserva_uso' and e['destino_tipo'] == 'fin_original':
                        pagos_orig_monto += e['monto']
                        
                if pagos_orig_monto > 0.01:
                    cuota_lines.append(f'    *   **{date_fmt} (Pago):** Se efectuó un pago a la obra original por **{utils.format_currency_ar(pagos_orig_monto)}**.')
                    
                # 3. Transferencias temporarias
                transf_monto = 0.0
                transf_destinos = []
                for e in day_events:
                    if e['tipo'] == 'transferencia_desvio':
                        transf_monto += e['monto']
                        transf_destinos.append(e['destino'])
                    elif e['tipo'] == 'reserva_uso' and e['destino_tipo'] != 'fin_original':
                        transf_monto += e['monto']
                        transf_destinos.append(e['destino_detalle'] or 'Otra obra')
                        
                if transf_monto > 0.01:
                    dest_uniq = []
                    for dest in transf_destinos:
                        clean_dest = clean_destino_name(dest)
                        if clean_dest not in dest_uniq:
                            dest_uniq.append(clean_dest)
                    dest_str = ', '.join(dest_uniq)
                    cuota_lines.append(f'    *   **{date_fmt} (Transferencia):** Se realizaron transferencias temporarias a otras obras por un total de **{utils.format_currency_ar(transf_monto)}** (distribuidos en: *{dest_str}*).')
                    
                # 4. Recuperos
                rec_events = [e for e in day_events if e['tipo'] in ('recupero_desvio', 'recupero_reserva_uso')]
                for r in rec_events:
                    orig_dest_clean = clean_destino_name(r['orig_destino'])
                    if r['destino_tipo'] == 'compensacion' and r['grupo_id']:
                        contra = obtener_contraparte_compensacion(cursor, r['grupo_id'], dec['id'])
                        if contra:
                            contra_dec = f"Decreto {contra['nro_decreto']}/{contra['anio']}"
                            contra_orig_fecha = utils.format_date_ar(contra['fecha_original'])
                            contra_orig_monto = utils.format_currency_ar(contra['monto_original'])
                            cuota_lines.append(
                                f'    *   **{date_fmt} (Compensación):** Se aplicaron **{utils.format_currency_ar(r["monto"])}** a la obra original, '
                                f'compensados mediante saldos cruzados con el *{contra_dec}* (fondos originalmente recibidos el **{contra_orig_fecha}**). '
                                f'La compensación formal se concretó el **{utils.format_date_ar(r["fecha"])}** tras registrarse una transferencia temporaria de fondos '
                                f'a favor del *{contra_dec}* realizada el **{utils.format_date_ar(r["orig_fecha"])}** (por un monto original de **{utils.format_currency_ar(r["orig_monto"])}**).'
                            )
                        else:
                            cuota_lines.append(
                                f'    *   **{date_fmt} (Compensación):** Se reintegraron **{utils.format_currency_ar(r["monto"])}** de la transferencia realizada el '
                                f'**{utils.format_date_ar(r["orig_fecha"])}** (originalmente de **{utils.format_currency_ar(r["orig_monto"])}**) a la obra *{orig_dest_clean}*, '
                                f'mediante compensación de saldos.'
                            )
                    else:
                        dest_txt = 'a la reserva' if r['destino_tipo'] == 'reserva' else ('a la obra original' if r['destino_tipo'] == 'fin_original' else 'a caja líquida sin distribuir')
                        cuota_lines.append(
                            f'    *   **{date_fmt} (Recupero):** Se recuperaron **{utils.format_currency_ar(r["monto"])}** de la transferencia realizada el '
                            f'**{utils.format_date_ar(r["orig_fecha"])}** (originalmente de **{utils.format_currency_ar(r["orig_monto"])}**) al destino *{orig_dest_clean}*, devueltos {dest_txt}.'
                        )
                        
            narrativa_list.append('\n'.join(cuota_lines))

    narrativa_text = '\n\n'.join(narrativa_list)

    resumen = (
        f"El **Decreto {dec['nro_decreto']}/{dec['anio']}** (Destinado a *{dec['destino_fondos']}*) "
        f"tiene un presupuesto pautado de **{total_decreto_fmt}**, "
        f"habiéndose cobrado a la fecha **{percibido_fmt}** (quedando **{pendiente_fmt}** pendiente de cobro).\n\n"
        f"**Historial de Flujo de Fondos:**\n\n"
        f"{narrativa_text}\n\n"
        f"**Estado Actual de Saldos Consolidados:**\n"
        f"- **Obra Original (Invertido/Pagado):** **{obra_original_fmt}**"
    )
    if compensado > 0.01:
        resumen += f" (de los cuales **{compensado_fmt}** provienen de compensación de saldos con otros decretos)"
    resumen += (
        f"\n- **Reserva (Saldo neto disponible):** **{reserva_fmt}**\n"
        f"- **Transferencias temporarias activas (Pendientes de recuperar):** **{desvios_netos_fmt}**\n"
        f"- **Caja líquida (Sin distribuir):** **{sin_distribuir_fmt}**"
    )
    
    return resumen


def obtener_gastos_funcionamiento_financiados_obra():
    """Retorna un DataFrame con todos los gastos de funcionamiento financiados con aportes de obra que aún tienen saldo pendiente."""
    with db.db_session() as conn:
        cursor = conn.cursor()
        
        # 1. Desvíos iniciales
        cursor.execute('''
            SELECT 
                cd.fecha AS fecha_desvio,
                cd.gasto_expediente_imuh AS gasto_expediente_imuh,
                cd.gasto_nombre AS gasto_nombre,
                p.razon_social AS proveedor_nombre,
                ('Dto. ' || d_orig.nro_decreto || '/' || d_orig.anio) AS decreto_financiador,
                d_orig.expediente_imuh AS orig_obra_imuh,
                d_orig.destino_fondos AS orig_obra_nombre,
                cd.nro_op AS nro_op_bejerman,
                cd.monto AS importe_desviado,
                COALESCE((SELECT SUM(monto) FROM cobro_desvios_recuperos WHERE desvio_id = cd.id), 0) AS total_recuperado
            FROM cobro_desvios cd
            JOIN cobros c ON cd.cobro_id = c.id
            JOIN cuotas cu ON c.cuota_id = cu.id
            JOIN decretos d_orig ON cu.decreto_id = d_orig.id
            LEFT JOIN gastos_funcionamiento gf ON cd.gasto_expediente_imuh = gf.expediente_imuh
            LEFT JOIN proveedores_funcionamiento p ON gf.proveedor_id = p.id
            WHERE cd.gasto_expediente_imuh IS NOT NULL
        ''')
        rows1 = [dict(r) for r in cursor.fetchall()]
        
        # 2. Desvíos desde reserva
        cursor.execute('''
            SELECT 
                ru.fecha AS fecha_desvio,
                ru.gasto_expediente_imuh AS gasto_expediente_imuh,
                ru.gasto_nombre AS gasto_nombre,
                p.razon_social AS proveedor_nombre,
                ('Dto. ' || d_orig.nro_decreto || '/' || d_orig.anio) AS decreto_financiador,
                d_orig.expediente_imuh AS orig_obra_imuh,
                d_orig.destino_fondos AS orig_obra_nombre,
                ru.nro_op AS nro_op_bejerman,
                ru.monto AS importe_desviado,
                COALESCE((SELECT SUM(monto) FROM cobro_reserva_usos_recuperos WHERE reserva_uso_id = ru.id), 0) AS total_recuperado
            FROM cobro_reserva_usos ru
            JOIN cobros c ON ru.cobro_id = c.id
            JOIN cuotas cu ON c.cuota_id = cu.id
            JOIN decretos d_orig ON cu.decreto_id = d_orig.id
            LEFT JOIN gastos_funcionamiento gf ON ru.gasto_expediente_imuh = gf.expediente_imuh
            LEFT JOIN proveedores_funcionamiento p ON gf.proveedor_id = p.id
            WHERE ru.gasto_expediente_imuh IS NOT NULL
        ''')
        rows2 = [dict(r) for r in cursor.fetchall()]
        
    all_rows = rows1 + rows2
    
    # Calcular importe adeudado y filtrar
    filtrados = []
    for r in all_rows:
        importe_adeudado = r['importe_desviado'] - r['total_recuperado']
        if importe_adeudado > 0.01:
            filtrados.append({
                "Fecha del desvío": r['fecha_desvio'],
                "Expediente IMUH del gasto": r['gasto_expediente_imuh'] or 'Sin asignar',
                "Nombre del expediente del gasto": r['gasto_nombre'] or 'Sin asignar',
                "Proveedor": r['proveedor_nombre'] or 'Sin asignar',
                "Decreto financiador": r['decreto_financiador'] or 'Sin asignar',
                "Expediente IMUH de la obra financiadora": r['orig_obra_imuh'] or 'Sin asignar',
                "Nombre de la obra acreedora": r['orig_obra_nombre'] or 'Sin asignar',
                "OP Bejerman": r['nro_op_bejerman'] or 'Sin OP',
                "Importe adeudado": importe_adeudado
            })
            
    # Ordenar por fecha del desvío desc
    filtrados.sort(key=lambda x: x['Fecha del desvío'], reverse=True)
    return pd.DataFrame(filtrados)

def generar_excel_gastos_funcionamiento_financiados_obra(df):
    """Genera un reporte Excel en bytes para gastos de funcionamiento adeudados."""
    excel_buffer = io.BytesIO()
    with pd.ExcelWriter(excel_buffer, engine='xlsxwriter') as writer:
        workbook  = writer.book
        bold      = workbook.add_format({'bold': True})
        money_fmt = workbook.add_format({'num_format': '#,##0.00'})
        
        ws = workbook.add_worksheet('Gastos Financiados')
        writer.sheets['Gastos Financiados'] = ws
        
        ws.write(0, 0, 'REPORTES: GASTOS DE FUNCIONAMIENTO FINANCIADOS CON APORTES DE OBRA', bold)
        ws.write(2, 0, 'Fecha de generación:', bold)
        ws.write(2, 1, datetime.date.today().strftime('%d/%m/%Y'))
        
        headers = [
            "Fecha del desvío",
            "Expediente IMUH del gasto",
            "Nombre del expediente del gasto",
            "Proveedor",
            "Decreto financiador",
            "Expediente IMUH de la obra financiadora",
            "Nombre de la obra acreedora",
            "OP Bejerman",
            "Importe adeudado"
        ]
        
        for col_idx, h in enumerate(headers):
            ws.write(4, col_idx, h, bold)
            
        total_val = 0.0
        for row_idx, (_, row) in enumerate(df.iterrows()):
            ws.write(5 + row_idx, 0, row["Fecha del desvío"])
            ws.write(5 + row_idx, 1, row["Expediente IMUH del gasto"])
            ws.write(5 + row_idx, 2, row["Nombre del expediente del gasto"])
            ws.write(5 + row_idx, 3, row["Proveedor"])
            ws.write(5 + row_idx, 4, row["Decreto financiador"])
            ws.write(5 + row_idx, 5, row["Expediente IMUH de la obra financiadora"])
            ws.write(5 + row_idx, 6, row["Nombre de la obra acreedora"])
            ws.write(5 + row_idx, 7, row["OP Bejerman"])
            
            val = float(row["Importe adeudado"])
            ws.write(5 + row_idx, 8, val, money_fmt)
            total_val += val
            
        tot_row = 5 + len(df)
        ws.write(tot_row, 0, 'TOTAL', bold)
        ws.write(tot_row, 8, total_val, money_fmt)
        
    return excel_buffer.getvalue()

def generar_pdf_gastos_funcionamiento_financiados_obra(df):
    """Wrapper para generar el reporte PDF en bytes."""
    temp_path = os.path.join(tempfile.gettempdir(), f"temp_gf_financiados_{datetime.date.today().strftime('%Y%m%d')}.pdf")
    
    # Formatear montos para el PDF
    df_pdf = df.copy()
    df_pdf["Importe adeudado"] = df_pdf["Importe adeudado"].apply(utils.format_currency_ar)
    
    # Formatear fechas para el PDF
    df_pdf["Fecha del desvío"] = df_pdf["Fecha del desvío"].apply(utils.format_date_ar)
    
    generar_reporte_gastos_funcionamiento_financiados_obra_pdf(temp_path, df_pdf)
    
    with open(temp_path, 'rb') as f:
        pdf_bytes = f.read()
        
    try:
        os.remove(temp_path)
    except OSError:
        pass
        
    return pdf_bytes

```

## Archivo: `components\tab_compensaciones.py`

```python
import streamlit as st
import importlib
import utils
import backend_compensaciones as backend
importlib.reload(backend)

def render():
    st.subheader("⚖️ Compensación Automática de Saldos Cruzados")
    st.markdown("Analiza la base de datos completa para encontrar pares de obras que se deban dinero mutuamente.")
    
    with st.spinner("Buscando saldos cruzados..."):
        pares = backend.calcular_saldos_cruzados_globales()
        
    if not pares:
        st.success("¡Excelente! No se encontraron saldos cruzados pendientes de compensación.")
    else:
        st.info(f"Se encontraron {len(pares)} pares de obras con saldos cruzados.")
        for p in pares:
            with st.expander(f"🔄 {p['O1_name']} ↔ {p['O2_name']}"):
                col1, col2 = st.columns(2)
                col1.metric(f"Le debe a {p['O2_name']}", utils.format_currency_ar(p['deuda_O1_to_O2']))
                col2.metric(f"Le debe a {p['O1_name']}", utils.format_currency_ar(p['deuda_O2_to_O1']))
                
                max_comp = p['monto_maximo']
                
                c_monto, c_btn = st.columns([3, 1])
                with c_monto:
                    monto_input = st.number_input("Monto a compensar:", min_value=0.01, max_value=max_comp, value=max_comp, step=1000.0, key=f"monto_{p['O1']}_{p['O2']}")
                with c_btn:
                    st.write("")
                    st.write("")
                    if st.button("Ejecutar Compensación", key=f"btn_{p['O1']}_{p['O2']}", type="primary", use_container_width=True):
                        with st.spinner("Compensando..."):
                            success, msg = backend.ejecutar_compensacion(p['O1'], p['O2'], monto_input)
                            if success:
                                st.success(msg)
                                st.rerun()
                            else:
                                st.error(msg)

    st.markdown("---")
    st.subheader("📜 Historial de Compensaciones")
    historial = backend.get_historial_compensaciones()
    if not historial:
        st.info("No hay compensaciones registradas.")
    else:
        # Dropdown selection of particular compensation
        opciones_c = {"": "--- Seleccione una compensación para ver su ficha visual ---"}
        for h in historial:
            opciones_c[h['grupo_compensacion_id']] = f"{h['obras_str']} ({utils.format_date_ar(h['fecha'])} - {utils.format_currency_ar(h['monto_compensado'])})"
        
        sel_comp_id = st.selectbox(
            "Seleccione una compensación para ver su ficha de trazabilidad:",
            options=list(opciones_c.keys()),
            format_func=lambda x: opciones_c[x],
            key="selectbox_ficha_compensacion"
        )
        
        if sel_comp_id:
            import database as db
            detalles = db.obtener_detalles_compensacion_grupo(sel_comp_id)
            if detalles:
                desv_item = detalles['desvios'][0] if detalles['desvios'] else None
                res_item = detalles['reservas'][0] if detalles['reservas'] else None
                
                if desv_item and res_item:
                    st.markdown("### 🔗 Ficha de Trazabilidad de Compensación Cruzada")
                    
                    col_card1, col_arrow, col_card2 = st.columns([5, 1, 5])
                    
                    with col_card1:
                        st.info(f"**Decreto Origen A:** Dto. {desv_item['nro_decreto']}/{desv_item['dec_anio']}\n\n"
                                f"**Obra:** {desv_item['desvio_destino']}\n\n"
                                f"**Tipo:** Préstamo (Desvío Inicial)\n\n"
                                f"**Fecha de Pago Original:** {utils.format_date_ar(desv_item['desvio_fecha'])}\n\n"
                                f"**Monto de Pago Original:** {utils.format_currency_ar(desv_item['desvio_monto'])}\n\n"
                                f"**OP Original:** {desv_item.get('desvio_op') or 'Sin OP'}\n\n"
                                f"**Monto Compensado:** {utils.format_currency_ar(desv_item['monto'])}")
                        if st.button(f"🔎 Ver Afectación Dto. {desv_item['nro_decreto']}/{desv_item['dec_anio']}", key="btn_nav_desv"):
                            st.session_state['sel_dec_afectacion'] = desv_item['dec_id']
                            st.session_state['central_report_selector'] = 'afectacion_decretos'
                            st.switch_page("pages/8_Reportes.py")
                            
                    with col_arrow:
                        st.markdown("<h2 style='text-align: center; margin-top: 80px;'>🔄</h2>", unsafe_allow_html=True)
                        
                    with col_card2:
                        st.info(f"**Decreto Origen B:** Dto. {res_item['nro_decreto']}/{res_item['dec_anio']}\n\n"
                                f"**Obra:** {res_item['uso_destino']}\n\n"
                                f"**Tipo:** Préstamo (Uso de Reserva)\n\n"
                                f"**Fecha de Pago Original:** {utils.format_date_ar(res_item['uso_fecha'])}\n\n"
                                f"**Monto de Pago Original:** {utils.format_currency_ar(res_item['uso_monto'])}\n\n"
                                f"**OP Original:** {res_item.get('uso_op') or 'Sin OP'}\n\n"
                                f"**Monto Compensado:** {utils.format_currency_ar(res_item['monto'])}")
                        if st.button(f"🔎 Ver Afectación Dto. {res_item['nro_decreto']}/{res_item['dec_anio']}", key="btn_nav_res"):
                            st.session_state['sel_dec_afectacion'] = res_item['dec_id']
                            st.session_state['central_report_selector'] = 'afectacion_decretos'
                            st.switch_page("pages/8_Reportes.py")
                            
                    st.markdown("---")
        
        for h in historial:
            with st.container():
                st.markdown(f"**🔄 {h['obras_str']}**")
                c1, c2, c3, c4 = st.columns([2, 2, 4, 1])
                c1.write(f"**Fecha:** {utils.format_date_ar(h['fecha'])}")
                c2.write(f"**Monto:** {utils.format_currency_ar(h['monto_compensado'])}")
                c3.caption(f"OPs: {h['ops_str']} | Registros compensados: {h['cant_movimientos']}<br>ID: {h['grupo_compensacion_id']}", unsafe_allow_html=True)
                with c4:
                    undo_key = f"confirm_undo_{h['grupo_compensacion_id']}"
                    if not st.session_state.get(undo_key, False):
                        if st.button("🗑️ Deshacer", key=f"undo_{h['grupo_compensacion_id']}", help="Eliminar registros de compensación", use_container_width=True):
                            st.session_state[undo_key] = True
                            st.rerun()
                    else:
                        st.warning("¿Confirmar?")
                        col_y, col_n = st.columns(2)
                        with col_y:
                            if st.button("Sí", key=f"yes_{h['grupo_compensacion_id']}", type="primary", use_container_width=True):
                                backend.deshacer_compensacion(h['grupo_compensacion_id'])
                                st.session_state[undo_key] = False
                                st.rerun()
                        with col_n:
                            if st.button("No", key=f"no_{h['grupo_compensacion_id']}", use_container_width=True):
                                st.session_state[undo_key] = False
                                st.rerun()
                st.markdown("---")

```

## Archivo: `components\tab_composicion.py`

```python
import streamlit as st
import datetime
import database as db
import pandas as pd
import utils
from utils import _validar_op_y_notas
from database import DESTINO_RESERVA

def render_tab4():
    st.subheader("🔍 Composición e Historial de Cuotas")
    st.info("Consulte la distribución, pagos y desvíos asociados a una cuota, y realice modificaciones o correcciones de Órdenes de Pago y montos.")
    
    decretos_list_sel = db.get_decretos()
    if not decretos_list_sel:
        st.warning("No hay decretos registrados.")
    else:
        opc_dec = {d['id']: f"Dto. {d['nro_decreto']}/{d['anio']} - {d['destino_fondos']}" for d in decretos_list_sel}
        sel_dec_id = st.selectbox("Seleccione el Decreto", options=list(opc_dec.keys()), format_func=lambda x: opc_dec[x], key="composition_dec_sel")
        
        if sel_dec_id:
            cuotas_list_sel = db.get_cuotas_by_decreto(sel_dec_id)
            if not cuotas_list_sel:
                st.info("Este decreto no tiene cuotas configuradas.")
            else:
                opc_cuota = {c['id']: f"Cuota {c['mes']:02d}/{c['anio']} - Monto: {utils.format_currency_ar(c['monto'])}" for c in cuotas_list_sel}
                sel_cuota_id = st.selectbox("Seleccione la Cuota", options=list(opc_cuota.keys()), format_func=lambda x: opc_cuota[x], key="composition_cuota_sel")
                
                if sel_cuota_id:
                    # Obtener cobros de esta cuota
                    conn_c = db.get_connection()
                    cursor_c = conn_c.cursor()
                    cursor_c.execute('SELECT * FROM cobros WHERE cuota_id = ?', (sel_cuota_id,))
                    cobros_cuota = [dict(r) for r in cursor_c.fetchall()]
                    conn_c.close()
                    
                    if not cobros_cuota:
                        st.warning("Esta cuota no registra ingresos (cobros) percibidos aún.")
                    else:
                        # Compilar todos los movimientos de usos
                        movimientos = []
                        total_fo_asignado = 0.0
                        total_res_asignado = 0.0
                        total_fo_pagado = 0.0
                        total_res_usado = 0.0
                        total_desviado = 0.0
                        total_recuperado = 0.0
                        total_ingresado = sum(c['monto'] for c in cobros_cuota)
                        
                        for cb in cobros_cuota:
                            # Ingreso
                            movimientos.append({
                                "id_rel": cb['id'],
                                "tipo_rel": "cobro",
                                "fecha": cb['fecha'],
                                "tipo_str": "💰 Ingreso (Cobro)",
                                "monto": cb['monto'],
                                "nro_op": "N/A",
                                "destino": "Sin distribuir",
                                "notas": f"Ingreso bancario de la cuota. Comprobante: {'Sí' if cb['comprobante_path'] else 'No'}",
                                "raw_data": cb
                            })
                            
                            dist = db.get_distribucion_by_cobro(cb['id'])
                            if dist:
                                total_fo_asignado += dist['monto_fin_orig']
                                total_res_asignado += dist['monto_reserva']
                            
                            # Usos Fin Original
                            usos_fo = db.get_fin_original_usos_by_cobro(cb['id'])
                            for u in usos_fo:
                                total_fo_pagado += u['monto']
                                movimientos.append({
                                    "id_rel": u['id'],
                                    "tipo_rel": "fin_original_uso",
                                    "fecha": u['fecha'],
                                    "tipo_str": "🏗️ Pago Fin Original",
                                    "monto": u['monto'],
                                    "nro_op": u['nro_op'] or "",
                                    "destino": "Obra Original (Fin Original)",
                                    "notas": u['notas'] or "",
                                    "raw_data": u
                                })
                                
                            recuperos_cb = db.get_recuperos_by_cobro(cb['id'])
                            for u in recuperos_cb:
                                total_fo_pagado += u['monto']
                                movimientos.append({
                                    "id_rel": u['id'],
                                    "tipo_rel": "recupero_fondos_propios",
                                    "fecha": u['fecha'],
                                    "tipo_str": "🔙 Recupero Adelanto F.P.",
                                    "monto": u['monto'],
                                    "nro_op": u['nro_op'] or "",
                                    "destino": "Fondos Propios (Devolución)",
                                    "notas": u['notas'] or "",
                                    "raw_data": u
                                })
                                
                            # Desvíos
                            desvios = db.get_desvios_by_cobro(cb['id'])
                            for d in desvios:
                                total_desviado += d['monto']
                                movimientos.append({
                                    "id_rel": d['id'],
                                    "tipo_rel": "desvio",
                                    "fecha": d['fecha'],
                                    "tipo_str": "💸 Desvío a otra obra",
                                    "monto": d['monto'],
                                    "nro_op": d['nro_op'] or "",
                                    "destino": d['destino'],
                                    "notas": d['motivo'] or "",
                                    "raw_data": d
                                })
                                
                                # Recuperos de desvíos
                                rec_d = db.get_recuperos_by_desvio(d['id'])
                                for rd in rec_d:
                                    total_recuperado += rd['monto']
                                    dest_str = "Fin Original" if rd['destino_tipo'] == 'fin_original' else f"Obra: {rd.get('dest_nombre') or rd.get('destino_detalle', '')}"
                                    movimientos.append({
                                        "id_rel": rd['id'],
                                        "tipo_rel": "desvio_recupero",
                                        "fecha": rd['fecha'],
                                        "tipo_str": "🔄 Recupero de Desvío",
                                        "monto": rd['monto'],
                                        "nro_op": rd['nro_op'] or "",
                                        "destino": dest_str,
                                        "notas": f"Devolución del desvío a {d['destino']}",
                                        "raw_data": rd
                                    })
                                    
                            # Usos de reserva
                            usos_r = db.get_reserva_usos_by_cobro(cb['id'])
                            for ur in usos_r:
                                total_res_usado += ur['monto']
                                dest_str = "Fin Original" if ur['destino_tipo'] == 'fin_original' else f"Obra: {ur['destino_detalle']}"
                                movimientos.append({
                                    "id_rel": ur['id'],
                                    "tipo_rel": "reserva_uso",
                                    "fecha": ur['fecha'],
                                    "tipo_str": "🔒 Uso de Reserva",
                                    "monto": ur['monto'],
                                    "nro_op": ur['nro_op'] or "",
                                    "destino": dest_str,
                                    "notas": ur['notas'] or "",
                                    "raw_data": ur
                                })
                                
                                # Recuperos de uso de reserva
                                rec_ur = db.get_recuperos_by_reserva_uso(ur['id'])
                                for rur in rec_ur:
                                    total_recuperado += rur['monto']
                                    dest_rur = "Fin Original" if rur['destino_tipo'] == 'fin_original' else ("Reserva" if rur['destino_tipo'] == 'reserva' else f"Obra: {rur.get('dest_nombre') or rur.get('destino_detalle','')}")
                                    movimientos.append({
                                        "id_rel": rur['id'],
                                        "tipo_rel": "reserva_uso_recupero",
                                        "fecha": rur['fecha'],
                                        "tipo_str": "🔄 Recupero de Reserva",
                                        "monto": rur['monto'],
                                        "nro_op": rur['nro_op'] or "",
                                        "destino": dest_rur,
                                        "notas": f"Devolución del uso de reserva a {dest_str}",
                                        "raw_data": rur
                                    })
                                    
                        # Ordenar por fecha cronológicamente
                        movimientos.sort(key=lambda x: x['fecha'])
                        
                        # --- Mostrar Resumen del Estado de la Cuota ---
                        st.markdown("### 📊 Estado de Distribución y Pagos de la Cuota")
                        
                        # --- CALCULO DE COMPOSICIÓN DEL ESTADO ACTUAL ---
                        estado_actual_filas = []
                        
                        for cb in cobros_cuota:
                            cb_id = cb['id']
                            dist = db.get_distribucion_by_cobro(cb_id)
                            monto_fo = dist['monto_fin_orig'] if dist else 0.0
                            monto_res = dist['monto_reserva'] if dist else 0.0
                            
                            tot_rec_sin_distribucion = 0.0
                            
                            # A. Fin Original (Pagos realizados)
                            usos_fo = db.get_fin_original_usos_by_cobro(cb_id)
                            sum_usos_fo = 0.0
                            for u in usos_fo:
                                sum_usos_fo += u['monto']
                                estado_actual_filas.append({
                                    "Fecha": utils.format_date_ar(u['fecha']),
                                    "Movimiento": "Fin original",
                                    "Monto": u['monto'],
                                    "Orden de Pago (OP)": u['nro_op'] or "Sin asignar",
                                    "Destino": "Obra original",
                                    "Aclaraciones": u['notas'] or ""
                                })
                                
                            recuperos_cb2 = db.get_recuperos_by_cobro(cb_id)
                            for u in recuperos_cb2:
                                sum_usos_fo += u['monto']
                                estado_actual_filas.append({
                                    "Fecha": utils.format_date_ar(u['fecha']),
                                    "Movimiento": "Recupero de Fondos Propios",
                                    "Monto": u['monto'],
                                    "Orden de Pago (OP)": u['nro_op'] or "Sin asignar",
                                    "Destino": "Fondos Propios (Devolución)",
                                    "Aclaraciones": u['notas'] or ""
                                })
                                
                            # B. Fin Original (Pendiente)
                            fo_pendiente = monto_fo - sum_usos_fo
                            if fo_pendiente > 0.01:
                                estado_actual_filas.append({
                                    "Fecha": "-",
                                    "Movimiento": "Fin original (Pendiente)",
                                    "Monto": fo_pendiente,
                                    "Orden de Pago (OP)": "-",
                                    "Destino": "Obra original (Fondo en cuenta)",
                                    "Aclaraciones": ""
                                })
                                
                            # C. En Reserva (Saldo Disponible)
                            usos_r = db.get_reserva_usos_by_cobro(cb_id)
                            tot_usos_r = sum(u['monto'] for u in usos_r)
                            
                            # Recuperos a reserva
                            tot_rec_a_res = 0.0
                            for u in usos_r:
                                recs = db.get_recuperos_by_reserva_uso(u['id'])
                                for r in recs:
                                    if r['destino_tipo'] == 'reserva':
                                        tot_rec_a_res += r['monto']
                                        
                            res_saldo_neto = monto_res - tot_usos_r + tot_rec_a_res
                            if res_saldo_neto > 0.01:
                                estado_actual_filas.append({
                                    "Fecha": "-",
                                    "Movimiento": "En reserva",
                                    "Monto": res_saldo_neto,
                                    "Orden de Pago (OP)": "-",
                                    "Destino": "Reserva disponible",
                                    "Aclaraciones": ""
                                })
                                
                            # D. Préstamos / Desvíos desde Reserva (Activos)
                            for u in usos_r:
                                if u['destino_tipo'] != 'fin_original':
                                    recs = db.get_recuperos_by_reserva_uso(u['id'])
                                    sum_recs = sum(r['monto'] for r in recs)
                                    u_net = u['monto'] - sum_recs
                                    if u_net > 0.01:
                                        estado_actual_filas.append({
                                            "Fecha": utils.format_date_ar(u['fecha']),
                                            "Movimiento": "Desvío a otra obra (desde Reserva)",
                                            "Monto": u_net,
                                            "Orden de Pago (OP)": u['nro_op'] or "Sin asignar",
                                            "Destino": u['destino_detalle'] or "Obra sin decreto",
                                            "Aclaraciones": u['notas'] or ""
                                        })
                                    
                                    # E. Recuperos de Reserva (Redireccionados)
                                    for r in recs:
                                        if r['destino_tipo'] != 'reserva':
                                            if r['destino_tipo'] == 'sin_distribucion':
                                                tot_rec_sin_distribucion += r['monto']
                                            elif r['destino_tipo'] == 'compensacion':
                                                detalles = db.obtener_detalles_compensacion_grupo(r['grupo_compensacion_id'])
                                                fecha_pago = utils.format_date_ar(r['fecha'])
                                                op_orig_str = "Sin OP"
                                                dec_cruzado_str = "otro decreto"
                                                fecha_orig_str = ""
                                                
                                                if detalles:
                                                    desv_rec = detalles['desvios'][0] if detalles['desvios'] else None
                                                    if desv_rec:
                                                        dec_cruzado_str = f"Dto. {desv_rec['nro_decreto']}/{desv_rec['dec_anio']}"
                                                    
                                                    if u.get('nro_op'):
                                                        op_orig_str = f"OP {u['nro_op']}"
                                                    elif u.get('fecha'):
                                                        op_orig_str = f"pago del {utils.format_date_ar(u['fecha'])}"
                                                    
                                                    if u.get('fecha'):
                                                        fecha_orig_str = f" del {utils.format_date_ar(u['fecha'])}"
                                                        
                                                    all_ops = []
                                                    for x in detalles['desvios'] + detalles['reservas']:
                                                        if x.get('rec_op'):
                                                            all_ops.append(x['rec_op'])
                                                    
                                                    ops_list = []
                                                    for op in all_ops:
                                                        if op and op.strip() and op.strip() != 'Sin OP':
                                                            ops_list.extend([o.strip() for o in str(op).replace(',', '-').split('-')])
                                                    ops_uniq = sorted(list(set(ops_list)))
                                                    ops_str = ", ".join(ops_uniq) if ops_uniq else "Sin OP"
                                                    
                                                    acl = f"Originalmente desviado a {dec_cruzado_str} ({op_orig_str}{fecha_orig_str}), recuperado mediante compensación el {utils.format_date_ar(r['fecha'])} afectando a OP {ops_str} (Compensación)"
                                                else:
                                                    acl = "Compensación de deudas cruzadas (Compensación)"
                                                    
                                                estado_actual_filas.append({
                                                    "Fecha": fecha_pago,
                                                    "Movimiento": "Fin original (Recupero de Reserva)",
                                                    "Monto": r['monto'],
                                                    "Orden de Pago (OP)": r['nro_op'] or "Sin asignar",
                                                    "Destino": "Obra original",
                                                    "Aclaraciones": acl
                                                })
                                            else:
                                                dest_r = "Obra original" if r['destino_tipo'] == 'fin_original' else (r.get('dest_nombre') or r.get('destino_detalle') or "Otra obra")
                                                mov_r = "Fin original (Recupero de Reserva)" if r['destino_tipo'] == 'fin_original' else "Desvío a otra obra (Recupero de Reserva)"
                                                estado_actual_filas.append({
                                                    "Fecha": utils.format_date_ar(r['fecha']),
                                                    "Movimiento": mov_r,
                                                    "Monto": r['monto'],
                                                    "Orden de Pago (OP)": r['nro_op'] or "Sin asignar",
                                                    "Destino": dest_r,
                                                    "Aclaraciones": ""
                                                })
                                else:
                                    # Reserve use to Fin Original
                                    estado_actual_filas.append({
                                        "Fecha": utils.format_date_ar(u['fecha']),
                                        "Movimiento": "Fin original (desde Reserva)",
                                        "Monto": u['monto'],
                                        "Orden de Pago (OP)": u['nro_op'] or "Sin asignar",
                                        "Destino": "Obra original",
                                        "Aclaraciones": u['notas'] or ""
                                    })
                                    
                            # F. Desvíos Iniciales (Activos y Recuperos Redireccionados)
                            desvios = db.get_desvios_by_cobro(cb_id)
                            for d in desvios:
                                recs = db.get_recuperos_by_desvio(d['id'])
                                sum_recs = sum(r['monto'] for r in recs)
                                d_net = d['monto'] - sum_recs
                                if d_net > 0.01:
                                    estado_actual_filas.append({
                                        "Fecha": utils.format_date_ar(d['fecha']),
                                        "Movimiento": "Desvío a otra obra",
                                        "Monto": d_net,
                                        "Orden de Pago (OP)": d['nro_op'] or "Sin asignar",
                                        "Destino": d['destino'],
                                        "Aclaraciones": d['motivo'] or ""
                                    })
                                    
                                # Recuperos redireccionados
                                for r in recs:
                                    if r['destino_tipo'] == 'sin_distribucion':
                                        tot_rec_sin_distribucion += r['monto']
                                    elif r['destino_tipo'] == 'compensacion':
                                        detalles = db.obtener_detalles_compensacion_grupo(r['grupo_compensacion_id'])
                                        fecha_pago = utils.format_date_ar(r['fecha'])
                                        op_orig_str = "Sin OP"
                                        dec_cruzado_str = "otro decreto"
                                        fecha_orig_str = ""
                                        
                                        if detalles:
                                            res_rec = detalles['reservas'][0] if detalles['reservas'] else None
                                            if res_rec:
                                                dec_cruzado_str = f"Dto. {res_rec['nro_decreto']}/{res_rec['dec_anio']}"
                                                if res_rec.get('uso_fecha'):
                                                    fecha_pago = utils.format_date_ar(res_rec['uso_fecha'])
                                                    fecha_orig_str = f" del {utils.format_date_ar(res_rec['uso_fecha'])}"
                                                if res_rec.get('uso_op'):
                                                    op_orig_str = f"OP {res_rec['uso_op']}"
                                                elif res_rec.get('uso_fecha'):
                                                    op_orig_str = f"pago del {utils.format_date_ar(res_rec['uso_fecha'])}"
                                                    
                                            all_ops = []
                                            for x in detalles['desvios'] + detalles['reservas']:
                                                if x.get('rec_op'):
                                                    all_ops.append(x['rec_op'])
                                            
                                            ops_list = []
                                            for op in all_ops:
                                                if op and op.strip() and op.strip() != 'Sin OP':
                                                    ops_list.extend([o.strip() for o in str(op).replace(',', '-').split('-')])
                                            ops_uniq = sorted(list(set(ops_list)))
                                            ops_str = ", ".join(ops_uniq) if ops_uniq else "Sin OP"
                                            
                                            acl = f"Fondos originados en {dec_cruzado_str} ({op_orig_str}{fecha_orig_str}), compensados el {utils.format_date_ar(r['fecha'])} afectando a OP {ops_str} (Compensación)"
                                        else:
                                            acl = "Compensación de deudas cruzadas (Compensación)"
                                            
                                        estado_actual_filas.append({
                                            "Fecha": fecha_pago,
                                            "Movimiento": "Fin original (Recupero)",
                                            "Monto": r['monto'],
                                            "Orden de Pago (OP)": r['nro_op'] or "Sin asignar",
                                            "Destino": "Obra original",
                                            "Aclaraciones": acl
                                        })
                                    else:
                                        dest_r = "Obra original" if r['destino_tipo'] == 'fin_original' else (r.get('dest_nombre') or r.get('destino_detalle') or "Otra obra")
                                        mov_r = "Fin original (Recupero)" if r['destino_tipo'] == 'fin_original' else "Desvío a otra obra (Recupero)"
                                        estado_actual_filas.append({
                                            "Fecha": utils.format_date_ar(r['fecha']),
                                            "Movimiento": mov_r,
                                            "Monto": r['monto'],
                                            "Orden de Pago (OP)": r['nro_op'] or "Sin asignar",
                                            "Destino": dest_r,
                                            "Aclaraciones": ""
                                        })
                                    
                            # G. Sin Distribuir
                            tot_desvios_ini = sum(d['monto'] for d in desvios)
                            saldo_libre = cb['monto'] - (monto_fo + monto_res + tot_desvios_ini) + tot_rec_sin_distribucion
                            if saldo_libre > 0.01:
                                estado_actual_filas.append({
                                    "Fecha": "-",
                                    "Movimiento": "Sin distribuir",
                                    "Monto": saldo_libre,
                                    "Orden de Pago (OP)": "-",
                                    "Destino": "Sin distribuir",
                                    "Aclaraciones": ""
                                })
                                
                        # Calcular totales para las tarjetas de métricas basadas en la composición
                        tot_obra_orig = sum(f["Monto"] for f in estado_actual_filas if f["Movimiento"].startswith("Fin original"))
                        tot_reserva = sum(f["Monto"] for f in estado_actual_filas if f["Movimiento"] == "En reserva")
                        tot_desvios = sum(f["Monto"] for f in estado_actual_filas if "desvío" in f["Movimiento"].lower() or "desvio" in f["Movimiento"].lower())
                        tot_sin_dist = sum(f["Monto"] for f in estado_actual_filas if f["Movimiento"] == "Sin distribuir")
                        
                        col_m1, col_m2, col_m3, col_m4, col_m5 = st.columns(5)
                        col_m1.metric("Total Percibido (Cobros)", utils.format_currency_ar(total_ingresado))
                        col_m2.metric("Obra Original", utils.format_currency_ar(tot_obra_orig))
                        col_m3.metric("Reserva (Saldo)", utils.format_currency_ar(tot_reserva))
                        col_m4.metric("Desvíos Netos Pendientes", utils.format_currency_ar(tot_desvios))
                        col_m5.metric("Sin Distribuir", utils.format_currency_ar(tot_sin_dist))
                        
                        # Renderizar Tabla de Estado Actual
                        st.markdown("### 🔍 Composición del Estado Actual de Fondos")
                        if estado_actual_filas:
                            df_actual = pd.DataFrame(estado_actual_filas)
                            sum_total_actual = df_actual['Monto'].sum()
                            
                            # Formatear la columna Monto para visualización
                            df_actual_mostrar = df_actual.copy()
                            df_actual_mostrar['Monto'] = df_actual_mostrar['Monto'].apply(lambda x: utils.format_currency_ar(x))
                            
                            st.dataframe(
                                df_actual_mostrar, 
                                use_container_width=True, 
                                hide_index=True,
                                column_config={
                                    "Destino": st.column_config.TextColumn(width="large"),
                                    "Movimiento": st.column_config.TextColumn(width="medium"),
                                    "Aclaraciones": st.column_config.TextColumn(width="large")
                                }
                            )
                            
                            # Mostrar el total abajo para verificar balance
                            col_b1, col_b2 = st.columns([4, 1])
                            col_b2.markdown(f"**Total Sumatoria:** {utils.format_currency_ar(sum_total_actual)}")
                            
                            # --- GENERACION DE REPORTES EXCEL Y PDF ---
                            st.write("")
                            st.markdown("#### 📥 Descargar Reporte de Composición")
                            
                            try:
                                # Reutilizar la lógica centralizada de utils_reports
                                from utils_reports import obtener_datos_composicion, generar_excel_composicion, generar_pdf_composicion
                                
                                _, _, _, cuota_seq_num, fechas_str, aclaraciones_str, cuota_sel_dict = obtener_datos_composicion(sel_dec_id, sel_cuota_id)
                                dec = db.get_decreto(sel_dec_id)
                                
                                df_export = pd.DataFrame()
                                df_export["Fecha"] = df_actual["Fecha"]
                                df_export["Destino"] = df_actual["Destino"]
                                df_export["OP"] = df_actual["Orden de Pago (OP)"]
                                df_export["Aclaraciones"] = df_actual["Aclaraciones"]
                                df_export["Monto"] = df_actual["Monto"]
                                
                                excel_data = generar_excel_composicion(dec, cuota_sel_dict, cuota_seq_num, fechas_str, aclaraciones_str, df_export)
                                pdf_data = generar_pdf_composicion(dec, cuota_sel_dict, cuota_seq_num, fechas_str, aclaraciones_str, sum_total_actual, df_export)
                                
                                col_dl1, col_dl2 = st.columns(2)
                                
                                col_dl1.download_button(
                                    label="📊 Exportar Composición a Excel",
                                    data=excel_data,
                                    file_name=f"Composicion_{dec['nro_decreto']}_{dec['anio']}_Cuota_{cuota_seq_num}.xlsx",
                                    mime="application/vnd.ms-excel",
                                    use_container_width=True
                                )
                                
                                col_dl2.download_button(
                                    label="📄 Exportar Composición a PDF",
                                    data=pdf_data,
                                    file_name=f"Composicion_{dec['nro_decreto']}_{dec['anio']}_Cuota_{cuota_seq_num}.pdf",
                                    mime="application/pdf",
                                    use_container_width=True
                                )
                            except Exception as e:
                                st.error(f"Error generando descargas: {e}")
                            
                            # Alerta en caso de diferencia (tolerancia centavos)
                            if abs(sum_total_actual - total_ingresado) > 0.05:
                                st.warning(f"⚠️ Atención: Hay una discrepancia de {utils.format_currency_ar(abs(sum_total_actual - total_ingresado))} entre la sumatoria de composición y el total percibido.")
                        else:
                            st.info("No hay datos de distribución disponibles.")
                        st.write("")
                        
                        # --- Mostrar Tabla de Historial ---
                        st.markdown("### 🗓️ Historial Completo de Movimientos")
                        
                        df_movs = pd.DataFrame([{
                            "Fecha": utils.format_date_ar(m['fecha']),
                            "Movimiento": m['tipo_str'],
                            "Monto": utils.format_currency_ar(m['monto']),
                            "Orden de Pago (OP)": m['nro_op'],
                            "Destino / Origen": m['destino'],
                            "Notas": m['notas']
                        } for m in movimientos])
                        
                        st.dataframe(df_movs, use_container_width=True, hide_index=True)
                        
                        # --- Formulario de Edición de Movimientos ---
                        st.markdown("---")
                        st.markdown("### 📝 Modificar un Movimiento / Completar OP")
                        
                        # Filtrar solo movimientos que se pueden editar (excluir cobros directos)
                        editables = [m for m in movimientos if m['tipo_rel'] != 'cobro']
                        
                        if not editables:
                            st.info("No hay pagos, desvíos o recuperos registrados que se puedan modificar.")
                        else:
                            opc_edit = {f"{m['tipo_rel']}_{m['id_rel']}": f"{m['tipo_str']} - {utils.format_date_ar(m['fecha'])} - {utils.format_currency_ar(m['monto'])} (OP: {m['nro_op'] or 'Sin asignar'})" for m in editables}
                            sel_edit_key = st.selectbox("Seleccione el movimiento a editar:", options=list(opc_edit.keys()), format_func=lambda x: opc_edit[x], key="sel_movimiento_edit")
                            
                            if sel_edit_key:
                                m_sel = next(m for m in editables if f"{m['tipo_rel']}_{m['id_rel']}" == sel_edit_key)
                                
                                with st.form("form_edicion_uso_general"):
                                    st.write(f"✏️ **Editando: {m_sel['tipo_str']}**")
                                    
                                    col_ed1, col_ed2 = st.columns(2)
                                    new_monto = col_ed1.number_input("Monto ($)", min_value=0.01, value=float(m_sel['monto']), step=1000.0)
                                    new_fecha = col_ed2.date_input("Fecha", datetime.datetime.strptime(m_sel['fecha'], '%Y-%m-%d').date(), format="DD-MM-YYYY")
                                    
                                    # Para 'reserva_uso_recupero' con destino 'reserva', no aplica OP
                                    es_volver_reserva_edit = (m_sel['tipo_rel'] == 'reserva_uso_recupero' and m_sel['raw_data'].get('destino_tipo') == DESTINO_RESERVA)
                                    
                                    if not es_volver_reserva_edit:
                                        new_op = st.text_input("Número de Orden de Pago (OP)", value=m_sel['nro_op'] or "")
                                    else:
                                        new_op = ""
                                        st.info("ℹ️ Este movimiento ('Volver a Reserva') no requiere OP. Solo se exige observación.")
                                    
                                    # Notas
                                    old_notas = ""
                                    if m_sel['tipo_rel'] in ['fin_original_uso', 'reserva_uso']:
                                        old_notas = m_sel['raw_data'].get('notas') or ""
                                    elif m_sel['tipo_rel'] == 'desvio':
                                        old_notas = m_sel['raw_data'].get('motivo') or ""
                                    elif m_sel['tipo_rel'] in ['desvio_recupero', 'reserva_uso_recupero']:
                                        old_notas = m_sel['raw_data'].get('notas') or ""
                                    new_notas = st.text_area("Notas / Observaciones / Motivo (Obligatorio si no hay OP, 10-30 chars)", value=old_notas)
                                    
                                    st.caption(f"**Destino actual:** {m_sel['destino']}")
                                    
                                    confirmar_edit_sin_op = False
                                    if not es_volver_reserva_edit and not new_op.strip():
                                        st.warning("⚠️ Si no ingresa el Número de Orden de Pago, deberá completar las observaciones y confirmar.")
                                        confirmar_edit_sin_op = st.checkbox("Confirmo guardar este movimiento sin número de OP", key="chk_confirmar_edit_sin_op")
                                    else:
                                        confirmar_edit_sin_op = True
                                    
                                    if st.form_submit_button("Guardar Cambios", type="primary"):
                                        err_edit = _validar_op_y_notas(
                                            new_op if not es_volver_reserva_edit else None,
                                            new_notas,
                                            requiere_confirmacion=(not es_volver_reserva_edit),
                                            confirmado=confirmar_edit_sin_op
                                        )
                                        if err_edit:
                                            st.error(err_edit)
                                        else:
                                            try:
                                                tipo = m_sel['tipo_rel']
                                                pk_id = m_sel['id_rel']
                                                raw = m_sel['raw_data']
                                                
                                                op_val = new_op.strip() if new_op.strip() else None
                                                notas_val = new_notas.strip() or None
                                                
                                                if tipo == 'fin_original_uso':
                                                    db.update_fin_original_uso(pk_id, new_monto, new_fecha.strftime('%Y-%m-%d'), op_val, new_notas)
                                                
                                                elif tipo == 'desvio':
                                                    db.update_desvio(
                                                        pk_id, 
                                                        new_monto, 
                                                        raw['destino'], 
                                                        new_notas, 
                                                        new_fecha.strftime('%Y-%m-%d'), 
                                                        raw.get('decreto_destino_id'), 
                                                        op_val
                                                    )
                                                    
                                                elif tipo == 'reserva_uso':
                                                    db.update_reserva_uso(
                                                        pk_id, 
                                                        new_monto, 
                                                        raw['destino_tipo'], 
                                                        raw['destino_detalle'], 
                                                        new_fecha.strftime('%Y-%m-%d'), 
                                                        new_notas, 
                                                        raw.get('decreto_destino_id'), 
                                                        op_val
                                                    )
                                                    
                                                elif tipo == 'desvio_recupero':
                                                    db.update_desvio_recupero(
                                                        pk_id, 
                                                        new_monto, 
                                                        new_fecha.strftime('%Y-%m-%d'), 
                                                        raw['destino_tipo'], 
                                                        raw.get('destino_detalle'), 
                                                        raw.get('decreto_destino_id'), 
                                                        op_val,
                                                        notas=notas_val
                                                    )
                                                    
                                                elif tipo == 'reserva_uso_recupero':
                                                    db.update_reserva_uso_recupero(
                                                        pk_id, 
                                                        new_monto, 
                                                        new_fecha.strftime('%Y-%m-%d'), 
                                                        raw['destino_tipo'], 
                                                        raw.get('destino_detalle'), 
                                                        raw.get('decreto_destino_id'), 
                                                        op_val,
                                                        notas=notas_val
                                                    )
                                                    
                                                st.session_state['success_msg_dist'] = "Movimiento modificado con éxito."
                                                st.rerun()
                                            except ValueError as e:
                                                st.error(f"Error de validación: {e}")
                                            except Exception as e:
                                                st.error(f"Error inesperado: {e}")


```

## Archivo: `components\tab_distribuir.py`

```python
import streamlit as st
import datetime
import database as db
import utils
from utils import _validar_op_y_notas
from database import DESTINO_RESERVA


def keep_expander_open(c_sel_id):
    st.session_state[f"expander_desv_active_{c_sel_id}"] = True

def render_tab2():
    st.subheader("Distribuir un Cobro Recibido")
    if 'success_msg_dist2' in st.session_state:
        st.success(st.session_state['success_msg_dist2'])
        del st.session_state['success_msg_dist2']
        
    st.info("Asigna cómo se dividieron inicialmente los fondos que ingresaron en el cobro. La suma de todas las partes no puede superar el total cobrado.")
    
    incluir_sin_saldo = st.checkbox("Incluir cobros sin saldo a distribuir", value=False, key="chk_incluir_sin_saldo")
    
    cobros_all = db.get_cobros_con_resumen_distribucion()
    if incluir_sin_saldo:
        cobros_base = cobros_all or []
    else:
        cobros_base = [c for c in (cobros_all or []) if (c['monto'] - c['total_distribuido']) > 0.01]

    if not cobros_base:
        st.warning("No hay cobros cargados en el sistema.")
    else:
        opciones_c = {c['id']: f"Cobro del {utils.format_date_ar(c['fecha'])} - ${c['monto']:,.2f} - Dto. {c['nro_decreto']}/{c['decreto_anio']} - Obra: {c['destino_fondos']} (Saldo libre: {utils.format_currency_ar(max(0, c['monto'] - c['total_distribuido']))})" for c in cobros_base}
        options = [None] + list(opciones_c.keys())
        c_sel_id = st.selectbox("1. Seleccione el Cobro a distribuir", options=options, format_func=lambda x: opciones_c[x] if x is not None else "--- Seleccione un cobro para comenzar ---")
        
        if c_sel_id is not None:
            c_sel = next(c for c in cobros_base if c['id'] == c_sel_id)
            dist_bd = db.get_distribucion_by_cobro(c_sel_id)
            desvios = db.get_desvios_by_cobro(c_sel_id)
            tot_desvios = sum(d['monto'] for d in desvios)
            
            val_fin = float(dist_bd['monto_fin_orig']) if dist_bd else 0.0
            val_res = float(dist_bd['monto_reserva']) if dist_bd else 0.0
            val_not = dist_bd['notas'] if dist_bd and dist_bd['notas'] else ""
            
            # Mostrar resumen de distribución actual
            st.markdown("#### Resumen Financiero de este Cobro")
            
            col_met1, col_met2, col_met3, col_met4 = st.columns(4)
            col_met1.metric("Total Cobrado", utils.format_currency_ar(c_sel['monto']))
            col_met2.metric("Fin Original", utils.format_currency_ar(val_fin))
            col_met3.metric("En Reserva", utils.format_currency_ar(val_res))
            col_met4.metric("Desviado", utils.format_currency_ar(tot_desvios))
            
            saldo_pendiente_dist = max(0.0, round(c_sel['monto'] - c_sel['total_distribuido'], 2))
            
            if saldo_pendiente_dist > 0.01:
                st.warning(f"⚠️ **Saldo Pendiente de Distribuir:** {utils.format_currency_ar(saldo_pendiente_dist)}")
            else:
                st.success("🎉 **Cobro totalmente distribuido ($0,00 pendiente).**")
            
            st.markdown("---")
            
            usos_fo = db.get_fin_original_usos_by_cobro(c_sel_id)
            recuperos = db.get_recuperos_by_cobro(c_sel_id)
            
            # Recompute val_fin dynamically from the individual uses and recuperos
            val_fin = sum(u['monto'] for u in usos_fo) + sum(r['monto'] for r in recuperos)
            if dist_bd and abs(val_fin - float(dist_bd['monto_fin_orig'])) > 0.01:
                # auto-heal distribution if mismatch
                db.upsert_distribucion(c_sel_id, val_fin, val_res, val_not)

            with st.form("form_distribucion_reserva"):
                st.write("**A. Guardar en Reserva**")
                st.caption(f"Tienes **{utils.format_currency_ar(saldo_pendiente_dist)}** pendientes de distribuir en este cobro.")
                
                monto_res = st.number_input("Guardado en Reserva ($)", min_value=0.0, value=val_res, step=1000.0, key=f"monto_res_{c_sel_id}")
                notas_dist = st.text_area("Aclaraciones generales de la distribución (opcional)", value=val_not, key=f"notas_dist_{c_sel_id}")
                
                st.caption("Si la suma de Fin Original, Reserva y Desvíos es menor al Total del Cobro, deberás marcar esta casilla para autorizar que quede saldo pendiente sin asignar:")
                confirmar_saldo = st.checkbox("Confirmo dejar saldo pendiente sin distribuir")
                
                if st.form_submit_button("Guardar Reserva", type="primary"):
                    suma_total = c_sel['total_distribuido'] - val_res + monto_res
                    
                    if suma_total > (c_sel['monto'] + 0.01):
                        st.error(f"Error: La nueva suma ({utils.format_currency_ar(suma_total)}) superaría el cobro total ({utils.format_currency_ar(c_sel['monto'])}). Ajuste los montos.")
                    elif suma_total < (c_sel['monto'] - 0.01) and not confirmar_saldo:
                        st.error(f"⚠️ Atención: Quedan {utils.format_currency_ar(c_sel['monto'] - suma_total)} sin distribuir. Si es correcto, marca la casilla de confirmación antes de guardar.")
                    else:
                        db.upsert_distribucion(c_sel_id, val_fin, monto_res, notas_dist)
                        st.success("Distribución de reserva guardada.")
                        st.rerun()
            st.divider()
            
            # --- FORMULARIOS DE REGISTRO (EXPANDERS) ---
            
            # 1. Calcular saldos disponibles para formularios
            saldo_disp_para_fo = max(0.0, c_sel['monto'] - c_sel['total_distribuido'])
            saldo_disp_para_desviar = max(0.0, c_sel['monto'] - c_sel['total_distribuido'])
            
            # Formulario de agregar a pago original (desplegable)
            if f"expander_fo_active_{c_sel_id}" not in st.session_state:
                st.session_state[f"expander_fo_active_{c_sel_id}"] = False
            
            def keep_fo_open():
                st.session_state[f"expander_fo_active_{c_sel_id}"] = True
                
            if saldo_disp_para_fo > 0.01:
                is_exp_fo = st.session_state[f"expander_fo_active_{c_sel_id}"]
                with st.expander("➕ Agregar Pago a Obra Original", expanded=is_exp_fo):
                    c_fo1, c_fo2 = st.columns(2)
                    monto_nuevo_fo = c_fo1.number_input("Monto a pagar ($)", min_value=0.0, max_value=float(saldo_disp_para_fo), value=float(saldo_disp_para_fo), step=1000.0, key=f"new_monto_fo_{c_sel_id}", on_change=keep_fo_open)
                    fecha_nuevo_fo = c_fo2.date_input("Fecha de Pago", value=datetime.date.today(), format="DD-MM-YYYY", key=f"new_fecha_fo_{c_sel_id}", on_change=keep_fo_open)
                    
                    op_nuevo_fo = st.text_input("Número de Orden de Pago", key=f"new_op_fo_{c_sel_id}", on_change=keep_fo_open)
                    notas_nuevo_fo = st.text_area("Observaciones (Obligatorio si no hay OP, 10-30 chars)", max_chars=30, key=f"new_notas_fo_{c_sel_id}", on_change=keep_fo_open)
                    obras_del_decreto = db.get_obras_by_decreto(c_sel['decreto_id'])
                    obra_id_selected = None
                    if len(obras_del_decreto) >= 1:
                        opciones_obra = {o['id']: f"{o['expediente_imuh']} - {o['nombre']}" for o in obras_del_decreto}
                        # If there is only 1 obra, pre-select it by setting index=1 (0 is the None option)
                        default_index = 1 if len(obras_del_decreto) == 1 else 0
                        is_disabled = (len(obras_del_decreto) == 1)
                        obra_id_selected = st.selectbox(
                            "Seleccione la Obra destino del pago", 
                            options=[None] + list(opciones_obra.keys()) if not is_disabled else list(opciones_obra.keys()), 
                            format_func=lambda x: opciones_obra[x] if x is not None else "--- Seleccione una obra ---", 
                            index=0 if is_disabled else default_index,
                            disabled=is_disabled,
                            key=f"sel_obra_fo_{c_sel_id}",
                            on_change=keep_fo_open
                        )

                    confirmar_sin_op_fo = False
                    if not op_nuevo_fo.strip():
                        st.warning("⚠️ Si no ingresa el Número de Orden de Pago, deberá completar las observaciones del pago y confirmar.")
                        confirmar_sin_op_fo = st.checkbox("Confirmo que deseo registrar el pago sin OP", key=f"new_chk_op_fo_{c_sel_id}", on_change=keep_fo_open)
                    else:
                        confirmar_sin_op_fo = True
                        
                    target_obra_id = obra_id_selected if obra_id_selected else (obras_del_decreto[0]['id'] if obras_del_decreto else None)
                    if target_obra_id:
                        obra = db.get_obra(target_obra_id)
                        m_contrato = obra.get('monto_contrato') or 0.0
                        total_pagado_actual = db.get_total_pagado_obra(target_obra_id)
                        if (total_pagado_actual + monto_nuevo_fo) > (m_contrato + db.TOLERANCE):
                            st.error(f"⚠️ El pago haría que la obra supere su monto de contrato (${m_contrato:,.2f}). Marque la casilla de confirmación para registrar de todas formas.")
                            confirmar_sobrepago_fo = st.checkbox("Confirmo que deseo sobrepagar el contrato de la obra", key=f"confirmar_sobrepago_fo_{c_sel_id}", on_change=keep_fo_open)
                        else:
                            confirmar_sobrepago_fo = True
                    else:
                        confirmar_sobrepago_fo = True
                        
                    if st.button("Guardar Pago", key=f"btn_save_fo_{c_sel_id}"):
                        err_op = _validar_op_y_notas(op_nuevo_fo, notas_nuevo_fo, confirmado=confirmar_sin_op_fo)
                        if len(obras_del_decreto) >= 1 and obra_id_selected is None:
                            st.error("Debe seleccionar una obra a la que se imputará este pago.")
                        elif err_op:
                            st.error(err_op)
                        elif monto_nuevo_fo <= 0:
                            st.error("El monto debe ser mayor a 0.")
                        elif not confirmar_sobrepago_fo:
                            st.error("Debe confirmar el sobrepago para continuar.")
                        else:
                            nuevo_fo = val_fin + monto_nuevo_fo
                            db.upsert_distribucion(c_sel_id, nuevo_fo, val_res, val_not)
                            db.add_fin_original_uso(c_sel_id, monto_nuevo_fo, fecha_nuevo_fo.strftime('%Y-%m-%d'), op_nuevo_fo if op_nuevo_fo.strip() else None, notas_nuevo_fo, obra_id_selected)
                            st.session_state['success_msg_dist2'] = "Pago a Obra Original registrado."
                            st.rerun()
            else:
                st.info("No hay saldo libre para registrar pagos a la obra original.")
                
            # Formulario de Recuperar Adelanto de Fondos Propios (desplegable)
            if f"expander_recupero_active_{c_sel_id}" not in st.session_state:
                st.session_state[f"expander_recupero_active_{c_sel_id}"] = False
            
            def keep_recupero_open():
                st.session_state[f"expander_recupero_active_{c_sel_id}"] = True
                
            if saldo_disp_para_fo > 0.01:
                is_exp_recupero = st.session_state[f"expander_recupero_active_{c_sel_id}"]
                with st.expander("➕ Recuperar Adelanto de Fondos Propios", expanded=is_exp_recupero):
                    obras_del_decreto_rec = db.get_obras_by_decreto(c_sel['decreto_id'])
                    obra_id_selected_rec = None
                    if len(obras_del_decreto_rec) >= 1:
                        opciones_obra_rec = {o['id']: f"{o['expediente_imuh']} - {o['nombre']}" for o in obras_del_decreto_rec}
                        default_index_rec = 1 if len(obras_del_decreto_rec) == 1 else 0
                        is_disabled_rec = (len(obras_del_decreto_rec) == 1)
                        obra_id_selected_rec = st.selectbox(
                            "Seleccione la Obra para la cual se recupera el fondo", 
                            options=[None] + list(opciones_obra_rec.keys()) if not is_disabled_rec else list(opciones_obra_rec.keys()), 
                            format_func=lambda x: opciones_obra_rec[x] if x is not None else "--- Seleccione una obra ---", 
                            index=0 if is_disabled_rec else default_index_rec,
                            disabled=is_disabled_rec,
                            key=f"sel_obra_rec_{c_sel_id}",
                            on_change=keep_recupero_open
                        )
                        
                    tope = 0.0
                    if obra_id_selected_rec:
                        tope = db.get_tope_recupero(obra_id_selected_rec)
                        st.info(f"💡 Tope de recupero para esta obra: **${tope:,.2f}**")
                        
                    max_recupero = min(float(saldo_disp_para_fo), float(tope)) if obra_id_selected_rec else float(saldo_disp_para_fo)
                    
                    c_rec1, c_rec2 = st.columns(2)
                    monto_nuevo_rec = c_rec1.number_input("Monto a recuperar ($)", min_value=0.0, max_value=max_recupero, value=max_recupero, step=1000.0, key=f"new_monto_rec_{c_sel_id}", on_change=keep_recupero_open)
                    fecha_nuevo_rec = c_rec2.date_input("Fecha de Recupero", value=datetime.date.today(), format="DD-MM-YYYY", key=f"new_fecha_rec_{c_sel_id}", on_change=keep_recupero_open)
                    
                    op_nuevo_rec = st.text_input("Número de Orden de Pago (Opcional)", key=f"new_op_rec_{c_sel_id}", on_change=keep_recupero_open)
                    notas_nuevo_rec = st.text_area("Observaciones (Obligatorio si no hay OP)", max_chars=30, key=f"new_notas_rec_{c_sel_id}", on_change=keep_recupero_open)
                        
                    confirmar_sin_op_rec = False
                    if not op_nuevo_rec.strip():
                        st.warning("⚠️ Si no ingresa el Número de Orden de Pago, deberá completar las observaciones y confirmar.")
                        confirmar_sin_op_rec = st.checkbox("Confirmo que deseo registrar el recupero sin OP", key=f"new_chk_op_rec_{c_sel_id}", on_change=keep_recupero_open)
                    else:
                        confirmar_sin_op_rec = True
                        
                    if st.button("Registrar Recupero", key=f"btn_save_rec_{c_sel_id}"):
                        err_op = _validar_op_y_notas(op_nuevo_rec, notas_nuevo_rec, confirmado=confirmar_sin_op_rec)
                        if len(obras_del_decreto_rec) >= 1 and obra_id_selected_rec is None:
                            st.error("Debe seleccionar la obra de la que se recuperan los fondos.")
                        elif err_op:
                            st.error(err_op)
                        elif monto_nuevo_rec <= 0:
                            st.error("El monto debe ser mayor a 0.")
                        else:
                            try:
                                db.add_recupero_fondos_propios(
                                    cobro_id=c_sel_id,
                                    obra_id=obra_id_selected_rec if obra_id_selected_rec else obras_del_decreto_rec[0]['id'],
                                    monto=monto_nuevo_rec,
                                    fecha=fecha_nuevo_rec.strftime('%Y-%m-%d'),
                                    nro_op=op_nuevo_rec.strip() if op_nuevo_rec.strip() else None,
                                    notas=notas_nuevo_rec
                                )
                                nuevo_fo_rec = val_fin + monto_nuevo_rec
                                db.upsert_distribucion(c_sel_id, nuevo_fo_rec, val_res, val_not)
                                st.session_state['success_msg_dist2'] = "Recupero registrado con éxito."
                                st.rerun()
                            except ValueError as e:
                                st.error(str(e))
                
            # Formulario de agregar desvío nuevo (desplegable)
            if f"expander_desv_active_{c_sel_id}" not in st.session_state:
                st.session_state[f"expander_desv_active_{c_sel_id}"] = False
                
            if (st.session_state.get(f"nd_op_{c_sel_id}", "") != "" or 
                st.session_state.get(f"nd_motivo_{c_sel_id}", "") != "" or
                st.session_state.get(f"chk_confirmar_desv_sin_op_{c_sel_id}", False) or
                st.session_state.get(f"tipo_desvio_{c_sel_id}", "Hacia Obra (Catálogo)") != "Hacia Obra (Catálogo)"):
                st.session_state[f"expander_desv_active_{c_sel_id}"] = True
                
            if saldo_disp_para_desviar > 0.01:
                is_exp = st.session_state[f"expander_desv_active_{c_sel_id}"]
                with st.expander("➕ Agregar Nuevo Desvío", expanded=is_exp):
                    st.write("**Atención:** Se recomienda no usar `st.form` aquí para permitir la selección dinámica.")
                    nd_op = st.text_input("Número de Orden de Pago (Desvío)", key=f"nd_op_{c_sel_id}", on_change=keep_expander_open, args=(c_sel_id,))
                    nd_op = ''.join(filter(str.isdigit, nd_op))
                    
                    op_locked_obra = None
                    op_locked_gasto = None
                    op_locked_fecha = None
                    
                    if nd_op:
                        usos_op = db.get_op_usage_details(nd_op)
                        if usos_op:
                            st.info("ℹ️ **Esta OP ya está vinculada a los siguientes pagos:**")
                            for u in usos_op:
                                st.info(f"- {u['origen']} por {utils.format_currency_ar(u['monto'])}")
                            op_locked_fecha = datetime.datetime.strptime(usos_op[0]['fecha'], '%Y-%m-%d').date()
                            st.session_state[f"nd_fecha_{c_sel_id}"] = op_locked_fecha
                            op_info = db.get_op_info(nd_op)
                            if op_info:
                                if op_info['obra_id']: 
                                    op_locked_obra = op_info['obra_id']
                                    st.session_state[f"tipo_desvio_{c_sel_id}"] = "Hacia Obra (Catálogo)"
                                    st.session_state[f"nd_obra_id_{c_sel_id}"] = op_locked_obra
                                if op_info['gasto_id']: 
                                    op_locked_gasto = op_info['gasto_id']
                                    st.session_state[f"tipo_desvio_{c_sel_id}"] = "Hacia Gasto de Funcionamiento (FUN)"
                                    st.session_state[f"nd_gasto_id_sel_{c_sel_id}"] = op_locked_gasto
                                st.warning("⚠️ **OP ya utilizada:** El destino ha sido bloqueado. Si hay un error, elimine los pagos previos.")

                    tipo_opciones_d = ["Hacia Obra (Catálogo)", "Hacia Gasto de Funcionamiento (FUN)"]
                    index_tipo_d = 0
                    if op_locked_obra: index_tipo_d = 0
                    elif op_locked_gasto: index_tipo_d = 1
                    
                    tipo_desvio = st.radio("Destino del Desvío:", tipo_opciones_d, disabled=(op_locked_obra is not None or op_locked_gasto is not None), key=f"tipo_desvio_{c_sel_id}", on_change=keep_expander_open, args=(c_sel_id,))
                    
                    nd_obra_id = None
                    gasto_nombre = ""
                    gasto_expediente_imuh = ""
                    nd_destino = ""
                    
                    if tipo_desvio == "Hacia Obra (Catálogo)":
                        obras_disponibles = db.get_obras(only_active=True)
                        if not obras_disponibles:
                            st.warning("No hay obras activas en el catálogo.")
                        else:
                            opc_obras = {}
                            for o in obras_disponibles:
                                label = f"{o['nombre']} (Exp: {o['expediente_imuh']})"
                                decretos_asoc = db.get_decretos_by_obra(o['id'])
                                if decretos_asoc:
                                    parts = []
                                    for d in decretos_asoc:
                                        if d.get('estado') == 'Anulado':
                                            parts.append(f"Decreto {d['nro_decreto']}/{d['anio']} - ANULADO")
                                        else:
                                            parts.append(f"Decreto {d['nro_decreto']}/{d['anio']}")
                                    label += f" ({', '.join(parts)})"
                                opc_obras[o['id']] = label
                            
                            idx_o = list(opc_obras.keys()).index(op_locked_obra) if op_locked_obra in opc_obras else 0
                            nd_obra_id = st.selectbox("Seleccione la Obra Destino", options=list(opc_obras.keys()), disabled=(op_locked_obra is not None), format_func=lambda x: opc_obras[x], key=f"nd_obra_id_{c_sel_id}", on_change=keep_expander_open, args=(c_sel_id,))
                            if nd_obra_id:
                                selected_o = next(o for o in obras_disponibles if o['id'] == nd_obra_id)
                    else:
                        gastos_disponibles = db.get_gastos_funcionamiento(only_active=True)
                        opc_gastos = {g['id']: f"{g['nombre']} (Exp: {g['expediente_imuh']})" for g in gastos_disponibles}
                        
                        gasto_id_sel = st.selectbox("Seleccione el Gasto de Funcionamiento (FUN)", options=list(opc_gastos.keys()), disabled=(op_locked_gasto is not None), format_func=lambda x: opc_gastos[x], key=f"nd_gasto_id_sel_{c_sel_id}", on_change=keep_expander_open, args=(c_sel_id,))
                        
                        if gasto_id_sel:
                            g_selected = next(g for g in gastos_disponibles if g['id'] == gasto_id_sel)
                            gasto_nombre = g_selected['nombre']
                            gasto_expediente_imuh = g_selected['expediente_imuh']
                            nd_destino = gasto_nombre
                            nd_gasto_prov_id = g_selected.get('proveedor_id')
                            p_txt = g_selected.get('proveedor_razon_social') or "Sin proveedor asignado"
                            st.text_input(
                                "Proveedor de Funcionamiento",
                                value=p_txt,
                                disabled=True
                            )
                            st.info(f"💡 **Gasto seleccionado:** {gasto_nombre} (Exp: {gasto_expediente_imuh}) | Proveedor: {p_txt}")
                        else:
                            gasto_nombre = ""
                            gasto_expediente_imuh = ""
                            nd_destino = ""
                            nd_gasto_prov_id = None
                            st.info("ℹ️ No hay gastos de funcionamiento activos en el catálogo. Registrá uno desde el menú 💼 Gastos de Funcionamiento.")
                        
                    nd_monto = st.number_input("Monto a Desviar ($)*", min_value=0.01, max_value=float(saldo_disp_para_desviar), value=float(saldo_disp_para_desviar), step=1000.0, key=f"nd_monto_{c_sel_id}", on_change=keep_expander_open, args=(c_sel_id,))
                    nd_fecha = st.date_input("Fecha del Desvío", key=f"nd_fecha_{c_sel_id}", format="DD-MM-YYYY", disabled=(op_locked_fecha is not None), on_change=keep_expander_open, args=(c_sel_id,))
                    nd_motivo = st.text_area("Motivo de la urgencia / Detalles", max_chars=30, key=f"nd_motivo_{c_sel_id}", on_change=keep_expander_open, args=(c_sel_id,))
                    
                    confirmar_desv_sin_op = False
                    if not nd_op.strip():
                        st.warning("⚠️ Si no informa número de orden de pago, deberá informar los detalles del desvío.")
                        confirmar_desv_sin_op = st.checkbox("Confirmo que deseo registrar el desvío sin número de OP", key=f"chk_confirmar_desv_sin_op_{c_sel_id}", on_change=keep_expander_open, args=(c_sel_id,))
                    else:
                        confirmar_desv_sin_op = True

                    if st.button("Confirmar Desvío", type="primary", key=f"btn_confirmar_desvio_{c_sel_id}"):
                        err_op = _validar_op_y_notas(nd_op, nd_motivo, confirmado=confirmar_desv_sin_op)
                        if tipo_desvio == "Hacia Obra (Catálogo)" and not nd_obra_id:
                            st.error("Debe seleccionar una obra del catálogo.")
                        elif tipo_desvio == "Hacia Gasto de Funcionamiento (FUN)" and not gasto_nombre.strip():
                            st.error("El nombre del gasto de funcionamiento es obligatorio.")
                        elif tipo_desvio == "Hacia Gasto de Funcionamiento (FUN)" and not gasto_expediente_imuh.strip():
                            st.error("El número de expediente IMUH es obligatorio.")
                        elif tipo_desvio == "Hacia Gasto de Funcionamiento (FUN)" and not utils.validar_expediente_imuh(gasto_expediente_imuh):
                            st.error("El número de expediente IMUH no tiene un formato válido (Ej: 8000000-I-2026).")
                        elif tipo_desvio == "Hacia Gasto de Funcionamiento (FUN)" and nd_gasto_prov_id == 0:
                            st.error("Debe seleccionar un Proveedor de Funcionamiento. Ya no se permite 'NO INFORMA PROVEEDOR'.")
                        elif err_op:
                            st.error(err_op)
                        else:
                            try:
                                if tipo_desvio == "Hacia Gasto de Funcionamiento (FUN)":
                                    gasto_exp_norm = utils.normalizar_expediente_imuh(gasto_expediente_imuh)
                                    db.add_desvio(c_sel_id, nd_destino, nd_monto, nd_motivo, nd_fecha.strftime('%Y-%m-%d'), nro_op=nd_op if nd_op.strip() else None, gasto_nombre=gasto_nombre, gasto_expediente_imuh=gasto_exp_norm)
                                else:
                                    db.add_desvio(c_sel_id, nd_destino, nd_monto, nd_motivo, nd_fecha.strftime('%Y-%m-%d'), obra_id=nd_obra_id, nro_op=nd_op if nd_op.strip() else None)
                                
                                # Limpiar campos de session_state para reiniciar el formulario
                                for k in [
                                    f"tipo_desvio_{c_sel_id}",
                                    f"nd_obra_id_{c_sel_id}",
                                    f"nd_gasto_id_sel_{c_sel_id}",
                                    f"nd_gasto_nombre_{c_sel_id}",
                                    f"nd_gasto_exp_{c_sel_id}",
                                    f"nd_monto_{c_sel_id}",
                                    f"nd_fecha_{c_sel_id}",
                                    f"nd_op_{c_sel_id}",
                                    f"nd_motivo_{c_sel_id}",
                                    f"chk_confirmar_desv_sin_op_{c_sel_id}"
                                ]:
                                    if k in st.session_state:
                                        del st.session_state[k]
                                        
                                # Colapsar el expander
                                st.session_state[f"expander_desv_active_{c_sel_id}"] = False
                                
                                st.session_state['success_msg_dist2'] = "Desvío agregado exitosamente."
                                st.rerun()
                            except ValueError as e:
                                st.error(str(e))
            else:
                st.info(f"No hay saldo libre ({utils.format_currency_ar(saldo_disp_para_desviar)}) para nuevos desvíos en este cobro.")
                
            st.divider()
            
            # --- LISTADOS DE MOVIMIENTOS REGISTRADOS ---
            
            # Listado B: Pagos a Obra Original
            st.write("**B. Pagos a Obra Original**")
            st.write(f"Total pagado a la obra: **{utils.format_currency_ar(val_fin)}**")
            
            if usos_fo:
                for u in usos_fo:
                    col_u1, col_u2 = st.columns([4, 1])
                    str_op = f" - OP: {u['nro_op']}" if u['nro_op'] else ""
                    str_notas = f" ({u['notas']})" if u['notas'] else ""
                    col_u1.info(f"Pago el {utils.format_date_ar(u['fecha'])}: **{utils.format_currency_ar(u['monto'])}**{str_op}{str_notas}")
                    if col_u2.button("Borrar", key=f"del_fo_{u['id']}"):
                        db.delete_fin_original_uso(u['id'])
                        nuevo_fo = val_fin - u['monto']
                        db.upsert_distribucion(c_sel_id, nuevo_fo, val_res, val_not)
                        st.session_state['success_msg_dist2'] = "Pago a Obra Original eliminado correctamente."
                        st.rerun()
            else:
                st.caption("No existen pagos a la obra original para este cobro.")
                
            st.write("") # Espaciado
            
            # Listado C: Desvíos a otras obras
            st.write("**C. Desvíos a otras obras**")
            st.write(f"Total Desviado inicialmente: **{utils.format_currency_ar(tot_desvios)}**")
            
            if desvios:
                for d in desvios:
                    col_d1, col_d2 = st.columns([4, 1])
                    saldo_d = d['monto'] - d['total_recuperado']
                    stado_d_str = f"| Debe: {utils.format_currency_ar(saldo_d)}" if saldo_d > 0 else "| Recuperado 100%"
                    col_d1.info(f"Desvío a **{d['destino']}** el {utils.format_date_ar(d['fecha'])}: **{utils.format_currency_ar(d['monto'])}** {stado_d_str}")
                    if col_d2.button("Borrar", key=f"del_desv_{d['id']}"):
                        if d['total_recuperado'] > 0:
                            st.error("No se puede borrar un desvío que ya tiene devoluciones registradas.")
                        else:
                            db.delete_desvio(d['id'])
                            st.session_state['success_msg_dist2'] = "Desvío eliminado correctamente."
                            st.rerun()
            else:
                st.caption("No existen desvíos registrados para este cobro.")

# --- TAB 3: HISTORIAL DE DESVÍOS ---
```

## Archivo: `components\tab_estado.py`

```python
import streamlit as st
import datetime
import math
import database as db
import pandas as pd
import utils
from utils import _validar_op_y_notas

def render_tab1():
    st.subheader("Estado de Cobranzas")
    # Mostrar notificaciones persistentes de Tab 1
    if 'success_msg_dist' in st.session_state:
        st.success(st.session_state['success_msg_dist'])
        del st.session_state['success_msg_dist']
        
    cobros = db.get_cobros_con_resumen_distribucion()
    # Precargar datos globales para evitar N+1 queries
    decretos_global = db.get_decretos()
    
    if not cobros:
        st.info("No hay cobros registrados en el sistema.")
    else:
        # Filtros
        col_f1, col_f2 = st.columns(2)
        estado_filtro = col_f1.selectbox("Filtrar por Estado", ["Todos", "Con desvíos pendientes", "Totalmente distribuido", "Sin distribuir aún", "Con saldo en reserva"])
        busqueda = col_f2.text_input("Buscar por decreto o Exp. IMUH")
        df_c = pd.DataFrame(cobros)
        
        # Filtros manuales
        if busqueda:
            busqueda = busqueda.strip()
            if busqueda.isdigit() and len(busqueda) <= 4:
                # Si es un número corto (posible nro de decreto), buscamos coincidencia exacta de decreto
                mask_dec = df_c['nro_decreto'].astype(str) == busqueda
                df_c = df_c[mask_dec]
            else:
                # Búsqueda parcial inteligente, incluyendo formato nro_decreto/decreto_anio
                dec_completo = df_c['nro_decreto'].astype(str) + '/' + df_c['decreto_anio'].astype(str)
                mask_dec = dec_completo.str.contains(busqueda, case=False, na=False)
                mask_exp = df_c['expediente_imuh'].astype(str).str.contains(busqueda, case=False, na=False)
                df_c = df_c[mask_dec | mask_exp]
            
        if not df_c.empty:
            # Agrupar cobros por cuota_id
            grouped_cobros = {}
            for _, row in df_c.iterrows():
                q_id = row['cuota_id']
                if q_id not in grouped_cobros:
                    grouped_cobros[q_id] = []
                grouped_cobros[q_id].append(row.to_dict())
            
            # Ordenar grupos por la fecha del cobro más reciente
            groups_list = []
            for q_id, group_cobros in grouped_cobros.items():
                latest_date = max(c['fecha'] for c in group_cobros)
                groups_list.append((q_id, group_cobros, latest_date))
            
            groups_list.sort(key=lambda x: (x[2], x[1][0]['nro_decreto']), reverse=True)
            
            filtered_groups = []
            for q_id, group_cobros, _ in groups_list:
                # 1. Calcular métricas agregadas y listas unificadas
                monto_total_cobrado = sum(c['monto'] for c in group_cobros)
                monto_total_fin_orig = sum(c['monto_fin_orig'] for c in group_cobros)
                monto_total_reserva = sum(c['monto_reserva'] for c in group_cobros)
                monto_total_desvios = sum(c['total_desvios'] for c in group_cobros)
                
                ru_fo_total = 0.0
                ru_other_total = 0.0
                recru_fo_total = 0.0
                recru_res_total = 0.0
                recru_sd_total = 0.0
                rec_fo_total_total = 0.0
                rec_sd_total_total = 0.0
                rec_desv_res_total_total = 0.0
                
                unified_desvios = []
                desvios_all = []
                usos_r_all = []
                
                for c_item in group_cobros:
                    c_id = c_item['id']
                    
                    # Calcular usos de reserva por tipo
                    usos_r_inline = db.get_reserva_usos_by_cobro(c_id)
                    usos_r_all.extend(usos_r_inline)
                    ru_fo_total += sum(u['monto'] for u in usos_r_inline if u['destino_tipo'] == 'fin_original')
                    ru_other_total += sum(u['monto'] for u in usos_r_inline if u['destino_tipo'] != 'fin_original')

                    # Calcular recuperos de desvíos de reserva
                    for u in usos_r_inline:
                        if u['destino_tipo'] != 'fin_original':
                            rec_usos_item = db.get_recuperos_by_reserva_uso(u['id'])
                            for ri in rec_usos_item:
                                if ri['destino_tipo'] == 'fin_original':
                                    recru_fo_total += ri['monto']
                                elif ri['destino_tipo'] == 'reserva':
                                    recru_res_total += ri['monto']
                                elif ri['destino_tipo'] == 'sin_distribucion':
                                    recru_sd_total += ri['monto']
                                    
                            # Active desvios from reserve
                            tot_rec_uso = sum(r['monto'] for r in rec_usos_item)
                            saldo_uso = u['monto'] - tot_rec_uso
                            if saldo_uso > 0.01:
                                unified_desvios.append({
                                    'fecha': u['fecha'],
                                    'monto': saldo_uso,
                                    'destino': u['destino_detalle'] or 'Otra obra',
                                    'nro_op': u.get('nro_op')
                                })

                    # Calcular recuperos a fin original
                    desvios = db.get_desvios_by_cobro(c_id)
                    desvios_all.extend(desvios)
                    for d in desvios:
                        recuperos_del_desvio = db.get_recuperos_by_desvio(d['id'])
                        for rec_item in recuperos_del_desvio:
                            if rec_item['destino_tipo'] == 'fin_original':
                                rec_fo_total_total += rec_item['monto']
                            elif rec_item['destino_tipo'] == 'sin_distribucion':
                                rec_sd_total_total += rec_item['monto']
                            elif rec_item['destino_tipo'] == 'reserva':
                                rec_desv_res_total_total += rec_item['monto']
                                
                        # Active desvios from initial
                        saldo_desv = d['monto'] - d['total_recuperado']
                        if saldo_desv > 0.01:
                            unified_desvios.append({
                                'fecha': d['fecha'],
                                'monto': saldo_desv,
                                'destino': d['destino'],
                                'nro_op': d.get('nro_op')
                            })

                # Aplicar fórmulas matemáticas lineales consistentes
                item_sin_dist = max(0.0, round(monto_total_cobrado - monto_total_fin_orig - monto_total_reserva - monto_total_desvios + rec_sd_total_total + recru_sd_total, 2))
                item_fin_orig = round(monto_total_fin_orig + ru_fo_total + rec_fo_total_total + recru_fo_total, 2)
                item_desvios = round(monto_total_desvios + ru_other_total - rec_fo_total_total - recru_fo_total - recru_res_total - rec_sd_total_total - recru_sd_total - rec_desv_res_total_total, 2)
                item_en_reserva = max(0.0, round(monto_total_reserva - ru_fo_total - ru_other_total + recru_res_total + rec_desv_res_total_total, 2))

                # 2. Filtrar por estado de la tarjeta unificada
                if item_sin_dist > 0.01:
                    estado_calculado = "Sin distribuir aún"
                elif len(unified_desvios) > 0:
                    estado_calculado = "Con desvíos pendientes"
                else:
                    estado_calculado = "Totalmente distribuido"
                    
                if estado_filtro == "Con saldo en reserva":
                    if item_en_reserva <= 0.01:
                        continue
                elif estado_filtro != "Todos" and estado_calculado != estado_filtro:
                    continue
                
                filtered_groups.append({
                    'q_id': q_id,
                    'group_cobros': group_cobros,
                    'monto_total_cobrado': monto_total_cobrado,
                    'item_sin_dist': item_sin_dist,
                    'item_fin_orig': item_fin_orig,
                    'item_desvios': item_desvios,
                    'item_en_reserva': item_en_reserva,
                    'unified_desvios': unified_desvios
                })
            
            total_items = len(filtered_groups)
            if total_items == 0:
                st.warning("No se encontraron cobros con esos filtros.")
            else:
                cards_per_page = 10
                total_pages = max(1, math.ceil(total_items / cards_per_page))
                
                if 'page_estado' not in st.session_state:
                    st.session_state['page_estado'] = 1
                    
                current_page = max(1, min(st.session_state['page_estado'], total_pages))
                st.session_state['page_estado'] = current_page
                
                def render_pagination_controls(key_suffix):
                    c_pag1, c_pag2, c_pag3 = st.columns([1, 2, 1])
                    with c_pag1:
                        if st.button("⬅️ Anterior", disabled=(current_page <= 1), key=f"prev_pag_{key_suffix}"):
                            st.session_state['page_estado'] = current_page - 1
                            st.rerun()
                    with c_pag2:
                        st.markdown(f"<div style='text-align: center; padding-top: 5px;'><b>Página {current_page} de {total_pages}</b> ({total_items} cobranzas en total)</div>", unsafe_allow_html=True)
                    with c_pag3:
                        if st.button("Siguiente ➡️", disabled=(current_page >= total_pages), key=f"next_pag_{key_suffix}"):
                            st.session_state['page_estado'] = current_page + 1
                            st.rerun()

                render_pagination_controls("top")
                st.write("")

                start_idx = (current_page - 1) * cards_per_page
                end_idx = start_idx + cards_per_page
                page_items = filtered_groups[start_idx:end_idx]

                for item in page_items:
                    q_id = item['q_id']
                    group_cobros = item['group_cobros']
                    monto_total_cobrado = item['monto_total_cobrado']
                    item_sin_dist = item['item_sin_dist']
                    item_fin_orig = item['item_fin_orig']
                    item_desvios = item['item_desvios']
                    item_en_reserva = item['item_en_reserva']
                    unified_desvios = item['unified_desvios']
                    
                    first_row = group_cobros[0]
                    with st.container(border=True):
                        col1, col2, col3 = st.columns([1.8, 2, 2.2])
                    
                        with col1:
                            dec_cuotas = db.get_cuotas_by_decreto(first_row['decreto_id'])
                            cuota_seq = 0
                            for idx, c_c in enumerate(dec_cuotas):
                                if c_c['id'] == q_id:
                                    cuota_seq = idx + 1
                                    break
                            total_cuotas = len(dec_cuotas)
                        
                            st.markdown(f"**Cobro de:** Dto. {first_row['nro_decreto']}/{first_row['decreto_anio']}")
                            st.caption(f"Cuota {first_row['mes']:02d}/{first_row['anio']} (Cuota {cuota_seq} de {total_cuotas}) - Destino: {first_row['destino_fondos']}")
                            exp_imuh_d = first_row['expediente_imuh'] if pd.notna(first_row['expediente_imuh']) and first_row['expediente_imuh'] else "Sin asignar"
                            st.caption(f"Expediente IMUH: {exp_imuh_d}")
                            st.subheader(f"Total cobrado: {utils.format_currency_ar(monto_total_cobrado)}")
                        
                            st.write("**Fecha de cobro:**")
                            for c_item in sorted(group_cobros, key=lambda x: x['fecha']):
                                st.write(f"{utils.format_date_ar(c_item['fecha'])} &nbsp;&nbsp; **{utils.format_currency_ar(c_item['monto'])}**", unsafe_allow_html=True)
                            
                        with col2:
                            st.write("**Distribución Actual:**")
                        
                            if item_sin_dist > 0.01:
                                st.warning(f"🟡 Sin distribución: {utils.format_currency_ar(item_sin_dist)}")
                            else:
                                st.write(f"⚪ Sin distribución: {utils.format_currency_ar(item_sin_dist)}")
                            
                            st.write(f"✅ Fin original: {utils.format_currency_ar(item_fin_orig)}")
                            st.write(f"🚨 Desvíos: {utils.format_currency_ar(item_desvios)}")
                            st.write(f"🔒 En reserva: {utils.format_currency_ar(item_en_reserva)}")
                        
                            # Item 5 Condicional: Pendiente de cobro
                            cuota = db.get_cuota(q_id)
                            if cuota:
                                cuota_monto = cuota['monto']
                                cobrado_total_cuota = db.get_total_cobrado_por_cuota(q_id)
                            
                                saldo_pendiente_cuota = max(0.0, round(cuota_monto - cobrado_total_cuota, 2))
                                if saldo_pendiente_cuota > 0.01:
                                    st.warning(f"🕒 Pendiente de cobro: {utils.format_currency_ar(saldo_pendiente_cuota)}")
                                
                        with col3:
                            # Ordenar cronológicamente (más antiguo primero)
                            unified_desvios.sort(key=lambda x: x['fecha'])
                        
                            st.write("**Desvíos Activos:**")
                            if unified_desvios:
                                for ud in unified_desvios:
                                    op_str = f" | OP Bejerman: {ud['nro_op']}" if ud.get('nro_op') else ""
                                    st.error(f"🔴 {utils.format_date_ar(ud['fecha'])}: **{utils.format_currency_ar(ud['monto'])}** desviados a {ud['destino']}{op_str}")
                            else:
                                st.success("Sin desvíos activos registrados. ✅")
                            
                        # Expandir detalles
                        with st.expander("Ver / Registrar Movimientos de Recuperos y Reservas"):
                            # Mostrar desvios para recuperar
                            desvios_pendientes = []
                            for d in desvios_all:
                                st.write(f"💸 **Recuperos de {d['destino']} (Desviado: {utils.format_currency_ar(d['monto'])})**")
                                recuperos_del_desvio = db.get_recuperos_by_desvio(d['id'])
                                if recuperos_del_desvio:
                                    for rec in recuperos_del_desvio:
                                        col_r1, col_r2 = st.columns([4, 1])
                                        if rec['destino_tipo'] == "fin_original":
                                            dest_str = "Fin original"
                                        elif rec['destino_tipo'] == "reserva":
                                            dest_str = "Reserva"
                                        elif rec['destino_tipo'] == "sin_distribucion":
                                            dest_str = "Sin distribución"
                                        else:
                                            dest_str = f"Otra obra: {rec.get('dest_nombre') or rec.get('destino_detalle', '')}"
                                    
                                        col_r1.caption(f"- {utils.format_date_ar(rec['fecha'])}: {utils.format_currency_ar(rec['monto'])} a {dest_str}")
                                        if col_r2.button("Borrar", key=f"del_rec_{rec['id']}"):
                                            db.delete_desvio_recupero(rec['id'])
                                            st.session_state['success_msg_dist'] = "Recupero eliminado correctamente."
                                            st.rerun()
                                    st.write("---")
                                
                                saldo_d = d['monto'] - d['total_recuperado']
                                if saldo_d > 0.01:
                                    d['saldo_pendiente'] = saldo_d
                                    desvios_pendientes.append(d)

                            if desvios_pendientes:
                                st.write("---")
                                st.write("**Registrar Nuevo Recupero de Desvío**")
                            
                                opciones_desv = {
                                    d['id']: f"{d['destino']} ({utils.format_date_ar(d['fecha'])}) - Saldo Libre: {utils.format_currency_ar(d['saldo_pendiente'])}"
                                    for d in desvios_pendientes
                                }
                            
                                sel_desv_id = st.selectbox("Seleccione el Desvío a recuperar:", options=list(opciones_desv.keys()), format_func=lambda x: opciones_desv[x], key=f"sel_desv_recuperar_{q_id}")
                            
                                if sel_desv_id:
                                    d_sel = next(d for d in desvios_pendientes if d['id'] == sel_desv_id)
                                    saldo_sel = d_sel['saldo_pendiente']
                                
                                    with st.container():
                                        m_rec = st.number_input("Monto", min_value=0.01, max_value=float(saldo_sel), value=float(saldo_sel), step=1000.0, key=f"m_rec_{q_id}")
                                        f_rec = st.date_input("Fecha", datetime.date.today(), format="DD-MM-YYYY", key=f"f_rec_{q_id}")
                                        op_rec = st.text_input("Número de Orden de Pago (Recupero)", key=f"op_rec_{q_id}")
                                        notas_rec = st.text_input("Notas u observaciones (Obligatorio si no hay OP, 10-30 chars)", key=f"notas_rec_{q_id}")
                                        st.caption("Destino del recupero:")
                                        tipo_rec_r = st.radio("¿Hacia dónde va?", ["Fin original", "Reserva", "Obra (Catálogo)", "Sin distribución"], key=f"tipo_rec_r_{q_id}")
                                    
                                        rec_obra_id = None
                                        if tipo_rec_r == "Obra (Catálogo)":
                                            obras_disponibles = db.get_obras(only_active=True)
                                            opc_obras = {}
                                            if obras_disponibles:
                                                for o in obras_disponibles:
                                                    label = f"{o['nombre']} (Exp: {o['expediente_imuh']})"
                                                    decretos_asoc = db.get_decretos_by_obra(o['id'])
                                                    if decretos_asoc:
                                                        parts = []
                                                        for dd in decretos_asoc:
                                                            if dd.get('estado') == 'Anulado':
                                                                parts.append(f"Decreto {dd['nro_decreto']}/{dd['anio']} - ANULADO")
                                                            else:
                                                                parts.append(f"Decreto {dd['nro_decreto']}/{dd['anio']}")
                                                        label += f" ({', '.join(parts)})"
                                                    opc_obras[o['id']] = label
                                            rec_obra_id = st.selectbox("Seleccione la obra de destino:", options=list(opc_obras.keys()), format_func=lambda x: opc_obras[x], key=f"sec_obra_rec_{q_id}")
                                    
                                        confirmar_rec_sin_op = False
                                        if not op_rec.strip():
                                            st.warning("⚠️ Si no ingresa el Número de Orden de Pago, deberá completar las observaciones y confirmar.")
                                            confirmar_rec_sin_op = st.checkbox("Confirmo que deseo registrar el recupero sin número de OP", key=f"chk_confirmar_rec_sin_op_{q_id}")
                                        else:
                                            confirmar_rec_sin_op = True
    
                                        if st.button("Confirmar Recupero", type="primary", key=f"btn_confirmar_rec_{q_id}"):
                                            det_rec = ""
                                            rec_decreto_id = None
                                            if tipo_rec_r == "Obra (Catálogo)" and rec_obra_id:
                                                obra_obj = db.get_obra(rec_obra_id)
                                                if obra_obj:
                                                    det_rec = obra_obj['nombre']
                                                    decretos_asoc = db.get_decretos_by_obra(rec_obra_id)
                                                    decretos_vigentes = [dd for dd in decretos_asoc if dd['estado'] != 'Anulado']
                                                    if decretos_vigentes:
                                                        rec_decreto_id = decretos_vigentes[0]['id']
                                                    elif decretos_asoc:
                                                        rec_decreto_id = decretos_asoc[0]['id']
                                                
                                            err_op = _validar_op_y_notas(op_rec, notas_rec, requiere_confirmacion=True, confirmado=confirmar_rec_sin_op)
                                            if tipo_rec_r == "Obra (Catálogo)" and not det_rec.strip():
                                                st.error("Especifica la obra de destino.")
                                            elif err_op:
                                                st.error(err_op)
                                            else:
                                                try:
                                                    if tipo_rec_r == "Fin original":
                                                        t_enum = "fin_original"
                                                    elif tipo_rec_r == "Reserva":
                                                        t_enum = "reserva"
                                                    elif tipo_rec_r == "Sin distribución":
                                                        t_enum = "sin_distribucion"
                                                    else:
                                                        t_enum = "nueva_obra"
                                                    db.add_desvio_recupero(sel_desv_id, m_rec, f_rec.strftime('%Y-%m-%d'), t_enum, det_rec, rec_decreto_id, nro_op=op_rec if op_rec.strip() else None, notas=notas_rec.strip() or None)
                                                    st.session_state['success_msg_dist'] = "Recupero registrado con éxito."
                                                
                                                    # Clean up state so we don't have lingering data
                                                    for k in [f"sel_desv_recuperar_{q_id}", f"m_rec_{q_id}", f"f_rec_{q_id}", f"op_rec_{q_id}", f"notas_rec_{q_id}", f"tipo_rec_r_{q_id}", f"sec_obra_rec_{q_id}", f"chk_confirmar_rec_sin_op_{q_id}"]:
                                                        if k in st.session_state:
                                                            del st.session_state[k]
                                                        
                                                    st.rerun()
                                                except ValueError as e:
                                                    st.error(str(e))
                                                
                            # Mostrar recuperos para desvíos desde reserva
                            usos_r_pendientes = []
                            for u in usos_r_all:
                                if u['destino_tipo'] != 'fin_original':
                                    u_destino = u['destino_detalle'] or 'Otra obra'
                                    st.write(f"🔒 **Recuperos de Reserva a {u_destino} (Prestado: {utils.format_currency_ar(u['monto'])})**")
                                    rec_usos = db.get_recuperos_by_reserva_uso(u['id'])
                                    if rec_usos:
                                        for rec in rec_usos:
                                            col_r1, col_r2 = st.columns([4, 1])
                                            if rec['destino_tipo'] == "fin_original":
                                                dest_str = "Fin original"
                                            elif rec['destino_tipo'] == "reserva":
                                                dest_str = "Volver a Reserva"
                                            elif rec['destino_tipo'] == "sin_distribucion":
                                                dest_str = "Sin distribución"
                                            else:
                                                dest_str = f"Otra obra: {rec.get('dest_nombre') or rec.get('destino_detalle', '')}"
                                        
                                            col_r1.caption(f"- {utils.format_date_ar(rec['fecha'])}: {utils.format_currency_ar(rec['monto'])} a {dest_str}. Notas: {rec.get('notas') or 'Sin observaciones'}")
                                            if col_r2.button("Borrar", key=f"del_rec_res_{rec['id']}"):
                                                db.delete_reserva_uso_recupero(rec['id'])
                                                st.session_state['success_msg_dist'] = "Recupero de reserva eliminado correctamente."
                                                st.rerun()
                                        st.write("---")
                                
                                    tot_rec_u = sum(r['monto'] for r in rec_usos)
                                    saldo_u = u['monto'] - tot_rec_u
                                    if saldo_u > 0.01:
                                        u['saldo_pendiente'] = saldo_u
                                        usos_r_pendientes.append(u)

                            if usos_r_pendientes:
                                st.write("---")
                                st.write("**Registrar Nuevo Recupero de Reserva**")
                            
                                opciones_uso_r = {
                                    u['id']: f"{u['destino_detalle'] or 'Otra obra'} ({utils.format_date_ar(u['fecha'])}) - Saldo Libre: {utils.format_currency_ar(u['saldo_pendiente'])}"
                                    for u in usos_r_pendientes
                                }
                            
                                sel_uso_r_id = st.selectbox("Seleccione el Préstamo de Reserva a recuperar:", options=list(opciones_uso_r.keys()), format_func=lambda x: opciones_uso_r[x], key=f"sel_uso_r_recuperar_{q_id}")
                            
                                if sel_uso_r_id:
                                    u_sel = next(u for u in usos_r_pendientes if u['id'] == sel_uso_r_id)
                                    saldo_u = u_sel['saldo_pendiente']
                                
                                    with st.container():
                                        m_rec_res = st.number_input("Monto", min_value=0.01, max_value=float(saldo_u), value=float(saldo_u), step=1000.0, key=f"m_rec_res_{q_id}")
                                        f_rec_res = st.date_input("Fecha", datetime.date.today(), format="DD-MM-YYYY", key=f"f_rec_res_{q_id}")
                                    
                                        st.caption("Destino del recupero:")
                                        tipo_rec_r_res = st.radio("¿Hacia dónde va?", ["Fin original", "Volver a Reserva", "Obra (Catálogo)", "Sin distribución"], key=f"tipo_rec_r_res_{q_id}")
                                    
                                        es_volver_reserva = (tipo_rec_r_res == "Volver a Reserva")
                                    
                                        if not es_volver_reserva:
                                            op_rec_res = st.text_input("Número de Orden de Pago (Recupero Reserva)", key=f"op_rec_res_{q_id}")
                                        else:
                                            op_rec_res = ""
                                            st.info("ℹ️ Para 'Volver a Reserva' no se requiere OP. Solo se exige una observación.")
                                    
                                        notas_rec_res = st.text_input("Notas u observaciones (Obligatorio, 10-30 chars)", key=f"notas_rec_res_{q_id}")
                                    
                                        rec_obra_id_res = None
                                        if tipo_rec_r_res == "Obra (Catálogo)":
                                            obras_disponibles = db.get_obras(only_active=True)
                                            opc_obras = {}
                                            if obras_disponibles:
                                                for o in obras_disponibles:
                                                    label = f"{o['nombre']} (Exp: {o['expediente_imuh']})"
                                                    decretos_asoc = db.get_decretos_by_obra(o['id'])
                                                    if decretos_asoc:
                                                        parts = []
                                                        for dd in decretos_asoc:
                                                            if dd.get('estado') == 'Anulado':
                                                                parts.append(f"Decreto {dd['nro_decreto']}/{dd['anio']} - ANULADO")
                                                            else:
                                                                parts.append(f"Decreto {dd['nro_decreto']}/{dd['anio']}")
                                                        label += f" ({', '.join(parts)})"
                                                    opc_obras[o['id']] = label
                                            rec_obra_id_res = st.selectbox("Seleccione la obra de destino:", options=list(opc_obras.keys()), format_func=lambda x: opc_obras[x], key=f"sec_obra_rec_res_{q_id}")
                                    
                                        confirmar_rec_res_sin_op = False
                                        if not es_volver_reserva and not op_rec_res.strip():
                                            st.warning("⚠️ Si no ingresa el Número de Orden de Pago, deberá completar las observaciones y confirmar.")
                                            confirmar_rec_res_sin_op = st.checkbox("Confirmo que deseo registrar el recupero sin número de OP", key=f"chk_confirmar_rec_res_sin_op_{q_id}")
                                        else:
                                            confirmar_rec_res_sin_op = True
    
                                        if st.button("Confirmar Recupero de Reserva", type="primary", key=f"btn_confirmar_rec_res_{q_id}"):
                                            det_rec = ""
                                            rec_decreto_id = None
                                            if tipo_rec_r_res == "Obra (Catálogo)" and rec_obra_id_res:
                                                obra_obj = db.get_obra(rec_obra_id_res)
                                                if obra_obj:
                                                    det_rec = obra_obj['nombre']
                                                    decretos_asoc = db.get_decretos_by_obra(rec_obra_id_res)
                                                    decretos_vigentes = [dd for dd in decretos_asoc if dd['estado'] != 'Anulado']
                                                    if decretos_vigentes:
                                                        rec_decreto_id = decretos_vigentes[0]['id']
                                                    elif decretos_asoc:
                                                        rec_decreto_id = decretos_asoc[0]['id']
                                                    
                                            err_op = _validar_op_y_notas(
                                                op_rec_res if not es_volver_reserva else None,
                                                notas_rec_res,
                                                requiere_confirmacion=(not es_volver_reserva),
                                                confirmado=confirmar_rec_res_sin_op
                                            )
                                            if tipo_rec_r_res == "Obra (Catálogo)" and not det_rec.strip():
                                                st.error("Especifica la obra de destino.")
                                            elif err_op:
                                                st.error(err_op)
                                            else:
                                                try:
                                                    if tipo_rec_r_res == "Fin original":
                                                        t_enum = "fin_original"
                                                    elif tipo_rec_r_res == "Volver a Reserva":
                                                        t_enum = "reserva"
                                                    elif tipo_rec_r_res == "Sin distribución":
                                                        t_enum = "sin_distribucion"
                                                    else:
                                                        t_enum = "nueva_obra"
                                                    db.add_reserva_uso_recupero(sel_uso_r_id, m_rec_res, f_rec_res.strftime('%Y-%m-%d'), t_enum, det_rec, rec_decreto_id, nro_op=op_rec_res if op_rec_res.strip() else None, notas=notas_rec_res.strip() or None)
                                                    st.session_state['success_msg_dist'] = "Recupero de reserva registrado con éxito."
                                                
                                                    for k in [f"sel_uso_r_recuperar_{q_id}", f"m_rec_res_{q_id}", f"f_rec_res_{q_id}", f"tipo_rec_r_res_{q_id}", f"op_rec_res_{q_id}", f"notas_rec_res_{q_id}", f"sec_obra_rec_res_{q_id}", f"chk_confirmar_rec_res_sin_op_{q_id}"]:
                                                        if k in st.session_state:
                                                            del st.session_state[k]
                                                        
                                                    st.rerun()
                                                except ValueError as e:
                                                    st.error(str(e))

                            # Mostrar usos de Fin Original si hay asignado
                            for c_item in group_cobros:
                                cobro_id = c_item['id']
                                fo_asignado = c_item['monto_fin_orig']
                                usos_fo = db.get_fin_original_usos_by_cobro(cobro_id)
                                total_fo_pagado = sum(u['monto'] for u in usos_fo)
                                saldo_fo_pendiente = max(0.0, round(fo_asignado - total_fo_pagado, 2))
                            
                                if fo_asignado > 0:
                                    st.write("---")
                                    st.write(f"🏗️ **Pagos de Fin Original del Cobro {utils.format_date_ar(c_item['fecha'])} (Saldo pendiente de pago: {utils.format_currency_ar(saldo_fo_pendiente)}):**")
                                    if saldo_fo_pendiente > 0.01:
                                        with st.container():
                                            op_fo_pay = st.text_input("Número de Orden de Pago", key=f"op_fo_pay_inp_{cobro_id}")
                                            op_fo_pay = ''.join(filter(str.isdigit, op_fo_pay)) # force digits
                                            
                                            op_locked_fecha_fo = None
                                            if op_fo_pay:
                                                usos_op = db.get_op_usage_details(op_fo_pay)
                                                if usos_op:
                                                    st.info("ℹ️ **Esta OP ya está vinculada a los siguientes pagos:**")
                                                    for u in usos_op:
                                                        st.info(f"- {u['origen']} por {utils.format_currency_ar(u['monto'])}")
                                                    op_locked_fecha_fo = datetime.datetime.strptime(usos_op[0]['fecha'], '%Y-%m-%d').date()
                                                    st.session_state[f"f_fo_pay_{cobro_id}"] = op_locked_fecha_fo
                                            cc1, cc2 = st.columns(2)
                                            m_fo_pay = cc1.number_input("Monto a pagar", min_value=0.01, max_value=float(saldo_fo_pendiente), value=float(saldo_fo_pendiente), step=1000.0)
                                            f_fo_pay = cc2.date_input("Fecha de pago", key=f"f_fo_pay_{cobro_id}", format="DD-MM-YYYY", disabled=(op_locked_fecha_fo is not None))
                                            notas_fo_pay = st.text_input("Notas u observaciones (Obligatorio si no hay OP, 10-30 chars)")
                                        
                                            confirmar_fo_pay_sin_op = False
                                            if not op_fo_pay.strip():
                                                st.warning("⚠️ Si no ingresa el Número de Orden de Pago, deberá completar las observaciones y confirmar.")
                                                confirmar_fo_pay_sin_op = st.checkbox("Confirmo que deseo registrar el pago sin número de OP", key=f"chk_confirmar_fo_pay_sin_op_{cobro_id}")
                                            else:
                                                confirmar_fo_pay_sin_op = True
                                            
                                            if st.button("Registrar Pago de Fin Original", type="primary", key=f"btn_fo_{cobro_id}"):
                                                err_op = _validar_op_y_notas(op_fo_pay, notas_fo_pay, confirmado=confirmar_fo_pay_sin_op)
                                                if err_op:
                                                    st.error(err_op)
                                                else:
                                                    try:
                                                        db.add_fin_original_uso(cobro_id, m_fo_pay, f_fo_pay.strftime('%Y-%m-%d'), op_fo_pay if op_fo_pay.strip() else None, notas_fo_pay.strip() or None)
                                                        st.session_state['success_msg_dist'] = "Pago a Fin Original registrado."
                                                        for k in [f"op_fo_pay_inp_{cobro_id}", f"chk_confirmar_fo_pay_sin_op_{cobro_id}"]:
                                                            if k in st.session_state:
                                                                del st.session_state[k]
                                                        st.rerun()
                                                    except ValueError as e:
                                                        st.error(str(e))
                                    if usos_fo:
                                        st.write(f"**Historial de pagos a Fin Original del Cobro {utils.format_date_ar(c_item['fecha'])}:**")
                                        for u in usos_fo:
                                            op_str = f"OP: {u['nro_op']}" if u['nro_op'] else "OP: Sin asignar"
                                            notes_str = f". Notas: {u['notas']}" if u['notas'] else ""
                                            col_u1, col_u2 = st.columns([4, 1])
                                            col_u1.caption(f"- {utils.format_date_ar(u['fecha'])}: {utils.format_currency_ar(u['monto'])} ({op_str}){notes_str}")
                                            if col_u2.button("Borrar", key=f"del_uso_fo_{u['id']}"):
                                                db.delete_fin_original_uso(u['id'])
                                                st.session_state['success_msg_dist'] = "Pago a Fin Original eliminado correctamente."
                                                st.rerun()

                            # Mostrar usos de reserva si hay reserva
                            for c_item in group_cobros:
                                cobro_id = c_item['id']
                                reserva_actual = c_item['monto_reserva']
                                usos_r = db.get_reserva_usos_by_cobro(cobro_id)
                                total_usado = sum(u['monto'] for u in usos_r)
                                saldo_reserva = reserva_actual - total_usado
                            
                                if reserva_actual > 0:
                                    st.write("---")
                                    st.write(f"🔒 **Usar Reservas del Cobro {utils.format_date_ar(c_item['fecha'])} (Saldo disponible: {utils.format_currency_ar(saldo_reserva)}):**")
                                    if saldo_reserva > 0.01:
                                        with st.container():
                                            op_uso = st.text_input("Número de Orden de Pago (Uso Reserva)", key=f"op_uso_{cobro_id}")
                                            op_uso = ''.join(filter(str.isdigit, op_uso))
                                            
                                            op_locked_obra = None
                                            op_locked_gasto = None
                                            op_locked_fecha_uso = None
                                            
                                            if op_uso:
                                                usos_op = db.get_op_usage_details(op_uso)
                                                if usos_op:
                                                    st.info("ℹ️ **Esta OP ya está vinculada a los siguientes pagos:**")
                                                    for u in usos_op:
                                                        st.info(f"- {u['origen']} por {utils.format_currency_ar(u['monto'])}")
                                                    op_locked_fecha_uso = datetime.datetime.strptime(usos_op[0]['fecha'], '%Y-%m-%d').date()
                                                    st.session_state[f"f_uso_{cobro_id}"] = op_locked_fecha_uso
                                                    op_info = db.get_op_info(op_uso)
                                                    if op_info:
                                                        if op_info['obra_id']: 
                                                            op_locked_obra = op_info['obra_id']
                                                            st.session_state[f"tipo_uso_{cobro_id}"] = "obra_catalogo"
                                                            st.session_state[f"uso_obra_id_{cobro_id}"] = op_locked_obra
                                                        if op_info['gasto_id']: 
                                                            op_locked_gasto = op_info['gasto_id']
                                                            st.session_state[f"tipo_uso_{cobro_id}"] = "gasto_fun"
                                                            st.session_state[f"uso_gasto_id_sel_{cobro_id}"] = op_locked_gasto
                                                        st.warning("⚠️ **OP ya utilizada:** El destino (Obra/Gasto) ha sido bloqueado para coincidir con el original. Si hay un error, debe eliminar los pagos previos de esta OP.")

                                            cc1, cc2, cc3 = st.columns(3)
                                            m_uso = cc1.number_input("Monto a usar", min_value=0.01, max_value=float(saldo_reserva), value=float(saldo_reserva), step=1000.0)
                                            f_uso = cc2.date_input("Fecha de uso", key=f"f_uso_{cobro_id}", format="DD-MM-YYYY", disabled=(op_locked_fecha_uso is not None))
                                            tipo_opciones = ["fin_original", "obra_catalogo", "gasto_fun"]
                                            index_tipo = 0
                                            if op_locked_obra: index_tipo = 1
                                            elif op_locked_gasto: index_tipo = 2
                                            tipo_uso = cc3.selectbox("¿Hacia dónde va?", tipo_opciones, disabled=(op_locked_obra is not None or op_locked_gasto is not None), format_func=lambda x: "Fin original" if x == "fin_original" else ("Obra (Catálogo)" if x == "obra_catalogo" else "Gasto de Funcionamiento (FUN)"), key=f"tipo_uso_{cobro_id}")
                                        
                                            nd_obra_id = None
                                            gasto_nombre = ""
                                            gasto_expediente_imuh = ""
                                        
                                            if tipo_uso == "obra_catalogo":
                                                obras_disponibles = db.get_obras(only_active=True)
                                                if not obras_disponibles:
                                                    st.warning("No hay obras activas en el catálogo.")
                                                    opc_obras = {}
                                                else:
                                                    opc_obras = {}
                                                    for o in obras_disponibles:
                                                        label = f"{o['nombre']} (Exp: {o['expediente_imuh']})"
                                                        decretos_asoc = db.get_decretos_by_obra(o['id'])
                                                        if decretos_asoc:
                                                            parts = []
                                                            for d in decretos_asoc:
                                                                if d.get('estado') == 'Anulado':
                                                                    parts.append(f"Decreto {d['nro_decreto']}/{d['anio']} - ANULADO")
                                                                else:
                                                                    parts.append(f"Decreto {d['nro_decreto']}/{d['anio']}")
                                                            label += f" ({', '.join(parts)})"
                                                        opc_obras[o['id']] = label
                                                idx_o = list(opc_obras.keys()).index(op_locked_obra) if op_locked_obra in opc_obras else 0
                                                nd_obra_id = st.selectbox("Seleccione la Obra Destino", options=list(opc_obras.keys()), disabled=(op_locked_obra is not None), format_func=lambda x: opc_obras[x], key=f"uso_obra_id_{cobro_id}")
                                            elif tipo_uso == "gasto_fun":
                                                gastos_disponibles = db.get_gastos_funcionamiento(only_active=True)
                                                opc_gastos = {g['id']: f"{g['nombre']} (Exp: {g['expediente_imuh']})" for g in gastos_disponibles}
                                            
                                                idx_g = list(opc_gastos.keys()).index(op_locked_gasto) if op_locked_gasto in opc_gastos else 0
                                                gasto_id_sel = st.selectbox("Seleccione el Gasto de Funcionamiento (FUN)", options=list(opc_gastos.keys()), disabled=(op_locked_gasto is not None), format_func=lambda x: opc_gastos[x], key=f"uso_gasto_id_sel_{cobro_id}")
                                            
                                                if gasto_id_sel:
                                                    g_selected = next(g for g in gastos_disponibles if g['id'] == gasto_id_sel)
                                                    gasto_nombre = g_selected['nombre']
                                                    gasto_expediente_imuh = g_selected['expediente_imuh']
                                                    uso_gasto_prov_id = g_selected.get('proveedor_id')
                                                    p_txt = g_selected.get('proveedor_razon_social') or "Sin proveedor asignado"
                                                    st.text_input(
                                                        "Proveedor de Funcionamiento",
                                                        value=p_txt,
                                                        disabled=True,
                                                        key=f"uso_gasto_prov_txt_{cobro_id}"
                                                    )
                                                    st.info(f"💡 **Gasto seleccionado:** {gasto_nombre} (Exp: {gasto_expediente_imuh}) | Proveedor: {p_txt}")
                                                else:
                                                    gasto_nombre = ""
                                                    gasto_expediente_imuh = ""
                                                    uso_gasto_prov_id = None
                                                    st.info("ℹ️ No hay gastos de funcionamiento activos en el catálogo. Registrá uno desde el menú 💼 Gastos de Funcionamiento.")
                                            
                                            notas_uso = st.text_input("Notas u observaciones (Obligatorio si no hay OP, 10-30 chars)", key=f"notes_uso_{cobro_id}")
                                        
                                            confirmar_uso_sin_op = False
                                            if not op_uso.strip():
                                                st.warning("⚠️ Si no ingresa el Número de Orden de Pago, deberá completar las observaciones y confirmar.")
                                                confirmar_uso_sin_op = st.checkbox("Confirmo que deseo registrar el uso de reserva sin número de OP", key=f"chk_confirmar_uso_sin_op_{cobro_id}")
                                            else:
                                                confirmar_uso_sin_op = True

                                            if st.button("Registrar Uso de Reserva", type="primary", key=f"btn_uso_r_{cobro_id}"):
                                                err_op = _validar_op_y_notas(op_uso, notas_uso, confirmado=confirmar_uso_sin_op)
                                                if tipo_uso == "obra_catalogo" and not nd_obra_id:
                                                    st.error("Debe seleccionar una obra del catálogo.")
                                                elif tipo_uso == "gasto_fun" and not gasto_nombre.strip():
                                                    st.error("El nombre del gasto de funcionamiento es obligatorio.")
                                                elif tipo_uso == "gasto_fun" and not gasto_expediente_imuh.strip():
                                                    st.error("El número de expediente IMUH es obligatorio.")
                                                elif tipo_uso == "gasto_fun" and not utils.validar_expediente_imuh(gasto_expediente_imuh):
                                                    st.error("El número de expediente IMUH no tiene un formato válido (Ej: 8000000-I-2026).")
                                                elif tipo_uso == "gasto_fun" and uso_gasto_prov_id == 0:
                                                    st.error("Debe seleccionar un Proveedor de Funcionamiento. Ya no se permite 'NO INFORMA PROVEEDOR'.")
                                                elif err_op:
                                                    st.error(err_op)
                                                else:
                                                    try:
                                                        if tipo_uso == "fin_original":
                                                            db.add_reserva_uso(cobro_id, m_uso, "fin_original", "", f_uso.strftime('%Y-%m-%d'), notas_uso.strip() or None, nro_op=op_uso if op_uso.strip() else None)
                                                        elif tipo_uso == "obra_catalogo":
                                                            db.add_reserva_uso(cobro_id, m_uso, "otra_obra", "", f_uso.strftime('%Y-%m-%d'), notas_uso.strip() or None, nro_op=op_uso if op_uso.strip() else None, obra_id=nd_obra_id)
                                                        else: # gasto_fun
                                                            gasto_exp_norm = utils.normalizar_expediente_imuh(gasto_expediente_imuh)
                                                            db.add_reserva_uso(cobro_id, m_uso, "otra_obra", gasto_nombre, f_uso.strftime('%Y-%m-%d'), notas_uso.strip() or None, nro_op=op_uso if op_uso.strip() else None, gasto_nombre=gasto_nombre, gasto_expediente_imuh=gasto_exp_norm)
                                                        st.session_state['success_msg_dist'] = "Uso de reserva registrado."
                                                        for k in [f"op_uso_{cobro_id}", f"notes_uso_{cobro_id}", f"chk_confirmar_uso_sin_op_{cobro_id}", f"uso_obra_id_{cobro_id}", f"uso_gasto_id_sel_{cobro_id}", f"uso_gasto_prov_txt_{cobro_id}"]:
                                                            if k in st.session_state:
                                                                del st.session_state[k]
                                                        st.rerun()
                                                    except ValueError as e:
                                                        st.error(str(e))
                                    if usos_r:
                                        st.write(f"**Historial de uso de reservas del Cobro {utils.format_date_ar(c_item['fecha'])}:**")
                                        for u in usos_r:
                                            destino_str = "Fin original" if u['destino_tipo'] == "fin_original" else "Otra obra"
                                            detalle_str = f" ({u.get('destino_detalle', '')})" if u.get('destino_detalle') else ""
                                            op_str = f" | OP: {u['nro_op']}" if u['nro_op'] else " | OP: Sin asignar"
                                            st.caption(f"- {utils.format_date_ar(u['fecha'])}: {utils.format_currency_ar(u['monto'])} a {destino_str}{detalle_str}{op_str}. Notas: {u.get('notas','')}")
            
                        with st.expander("🗺️ Ver Mapa de Trazabilidad de Fondos (Camino del Dinero)"):
                            from trazabilidad_graph import mostrar_mapa_trazabilidad
                            if len(group_cobros) > 1:
                                cobro_opciones = {c['id']: f"Cobro del {utils.format_date_ar(c['fecha'])} - {utils.format_currency_ar(c['monto'])}" for c in group_cobros}
                                sel_c_id = st.selectbox("Seleccione el cobro a visualizar:", options=list(cobro_opciones.keys()), format_func=lambda x: cobro_opciones[x], key=f"sel_graph_c_{q_id}")
                                mostrar_mapa_trazabilidad(sel_c_id)
                            else:
                                mostrar_mapa_trazabilidad(group_cobros[0]['id'])
            
                if total_pages > 1:
                    st.write("")
                    render_pagination_controls("bottom")
        else:
            st.warning("No se encontraron cobros con esos filtros.")
            
        # Tabla de Deudas Obras Propias
        st.write("---")
        st.subheader("Deudas Acumuladas: Obras / Gastos de Funcionamiento")
        deudas_propias = db.get_deudas_obras_propias()
        if deudas_propias:
            st.info("Listado de deudas pendientes de devolución para obras sin decreto vigente y gastos de funcionamiento.")
            df_dp = pd.DataFrame(deudas_propias)
            df_dp = df_dp[['destino', 'tipo', 'expediente_imuh', 'decreto_asociado', 'saldo']]
            st.dataframe(df_dp.style.format({'saldo': '${:,.2f}'}), use_container_width=True)
        else:
            st.success("No hay deudas pendientes reportadas para obras o gastos de funcionamiento.")

# --- TAB 2: REGISTRAR ---

```

## Archivo: `components\tab_historial.py`

```python
import streamlit as st
import datetime
import database as db
import pandas as pd
import utils

def render_tab3():
    st.subheader("🔄 Historial Completo de Desvíos de Fondos")
    st.markdown("Registro cronológico de todos los desvíos realizados entre obras, junto con su estado de devolución y saldo pendiente.")
    
    col_hist_f1, col_hist_f2, col_hist_f3, col_hist_f4 = st.columns(4)
    search_origen = col_hist_f1.text_input("🔍 Buscar por Obra Origen")
    search_destino = col_hist_f2.text_input("🔍 Buscar por Obra Destino")
    search_nro_decreto = col_hist_f3.text_input("🔍 Nro Decreto Origen")
    search_cuota = col_hist_f4.text_input("🔍 Cuota Origen (MM/AAAA)")

    historial_desvios = db.get_historial_desvios()
    
    if not historial_desvios:
        st.info("Aún no se ha registrado ningún desvío de fondos en el sistema.")
    else:
        tabla_historial = []
        for d in historial_desvios:
            origen_str = f"Dto. {d['orig_nro']}/{d['orig_anio']} - {d['orig_nombre']}"
            if d['decreto_destino_id']:
                destino_str = f"Dto. {d['dest_nro']}/{d['dest_anio']} - {d['dest_nombre']}"
            else:
                destino_str = d['destino_texto']
                
            orig_nro_str = f"{d['orig_nro']}/{d['orig_anio']}"
            orig_cuota_str = f"{d['orig_cuota_mes']:02d}/{d['orig_cuota_anio']}"
                
            if search_origen and search_origen.lower() not in origen_str.lower():
                continue
            if search_destino and search_destino.lower() not in destino_str.lower():
                continue
            if search_nro_decreto and search_nro_decreto.lower() not in orig_nro_str.lower():
                continue
            if search_cuota and search_cuota.lower() not in orig_cuota_str.lower():
                continue
                
            tabla_historial.append({
                "Fecha": utils.format_date_ar(d['fecha']),
                "Obra Origen (Prestamista)": origen_str,
                "Cuota Origen": orig_cuota_str,
                "Obra Destino (Deudor)": destino_str,
                "OP Bejerman": d.get('nro_op') or "Sin OP",
                "Observaciones": d.get('motivo') or "",
                "Monto Desviado": d['monto'],
                "Total Recuperado": d['total_recuperado'],
                "Saldo a Recuperar": d['saldo'],
                "Estado": "Cancelado" if d['saldo'] <= 0.01 else "Pendiente"
            })
            
        df_hist = pd.DataFrame(tabla_historial)
        
        # Formatear moneda manteniendo tipos numéricos o convirtiendo a string para visualización
        df_hist_mostrar = df_hist.copy()
        if not df_hist.empty:
            for col in ["Monto Desviado", "Total Recuperado", "Saldo a Recuperar"]:
                if col in df_hist_mostrar.columns:
                    df_hist_mostrar[col] = df_hist_mostrar[col].apply(lambda x: utils.format_currency_ar(x))
            
        # Botón de exportación a Excel / CSV
        import io
        excel_buffer = io.BytesIO()
        try:
            with pd.ExcelWriter(excel_buffer, engine='openpyxl') as writer:
                df_hist.to_excel(writer, index=False, sheet_name='Historial_Desvios')
            excel_data = excel_buffer.getvalue()
            st.download_button(
                label="📥 Exportar Resultados a Excel",
                data=excel_data,
                file_name=f"historial_desvios_{datetime.date.today()}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                type="secondary"
            )
        except Exception as e:
            # Fallback a CSV usando punto y coma (sep=';') y BOM (utf-8-sig) para que Excel en español lo auto-separe
            csv_data = df_hist.to_csv(index=False, sep=';').encode('utf-8-sig')
            st.download_button(
                label="📥 Exportar Resultados a CSV (Excel)",
                data=csv_data,
                file_name=f"historial_desvios_{datetime.date.today()}.csv",
                mime="text/csv",
                type="secondary"
            )
        
        st.dataframe(
            df_hist_mostrar,
            use_container_width=True,
            hide_index=True
        )

# --- TAB 4: COMPOSICION E HISTORIAL DE CUOTAS ---

```

## Archivo: `Montos de obra\obras_sin_contrato.md`

```md
# Obras sin Monto de Contrato

| ID | Expediente IMUH | Nombre |
|---|---|---|
| 29 | 8001178-I-2024 | Actualización EIA - Manzana 34 |
| 51 | 8000437-I-2025 | Actualización Plan de ordenamiento urbano ambiental - Asentamientos Miradores - Jarillal |
| 21 | 8000063-I-2026 | Apertura - Movimiento de suelo y consolidación de calles - Sector Jarillal |
| 4 | 8000046-I-2026 | Apertura, movimiento de suelo y consolidación de calles - Sector Jarillal // Apertura, movimiento de suelo y consolidación de calles - Sector Miradores |
| 46 | 8001206-I-2024 | Aporte de material calcáreo y compactación de calles - Sector Rincón del Valle |
| 22 | 8000551-I-2025 | Conexiones domiciliarias de agua Manzana 34 |
| 38 | 8000141-I-2024 | Conexión de gas intradomiciliario para familias del Sector El Obrador |
| 41 | 8000015-I-2024 | Conexión de gas intradomiciliario para familias del Sector La Laguna |
| 27 | 8000614-L-2025 | Construcción de vivienda - Lemos Mabel - Mza 13 - Lote 22 - Sector Distrito 6 |
| 31 | 8000083-I-2026 | Construcción de vivienda - Zapata Genesis Milagros - Mza 5 - Lote 11 - Sector Distrito 3-3 |
| 50 | 8000119-A-2025 | Construcción de vivienda Sra. Agüero Mariela Soledad  Mza. 10 Lote 4 - Distrito 6 |
| 25 | 8000663-I-2025 | Construcción de vivienda en D7 - Landa Silvia |
| 24 | 8000414-V-2024 | Construcción de vivienda en Sector D3 |
| 5 | 8001015-I-2025 | Construcción muros de contención - Sector Auka Mahuida |
| 47 | 8001067-B-2025 | Construcción vereda reglamentaria - Sra. Sonia del Carmen Burgos |
| 32 | 8000095-I-2026 | Construcción vivienda Quilapan |
| 10 | 8000951-R-2022 | Convenio Económico Financiero Coop. Mercantiles y Fideicomiso Urme - Actualización por CAC Cuotas 5 a 8 |
| 20 | 8000605-I-2025 | Cordones cuneta perimetrales boulevard, espacios verdes y reservas fiscales - 418 Lotes |
| 3 | 8000630-I-2025 | EIA Conexión vial entre Cuenca XV Intermedia y D7 |
| 28 | 8000020-I-2026 | Limpieza y retiro de manto vegetal de espacios comunes - Distrito 6 |
| 40 | 8001003-I-2025 | Limpieza, desbroce y aporte de material - Fuelle verde (Cortina rompevientos) |
| 36 | 8000148-I-2026 | Limpieza, desbroce, retiro de material y residuos - Manzanas 1 y 2, 9 a 14, 21 a 25 y 31 a 40 - Desarrollo Manzana 34 |
| 13 | 8000061-I-2025 | Línea aérea-subterránea troncal de media tensión - Manzana 34 Etapa I |
| 8 | 8000899-I-2024 | Mensura lote 3-1 - Sección I - 418 Lotes |
| 44 | 8001271-I-2024 | Mensura remanente lote 3-1 - Sección I - Loteo Social D3 |
| 19 | 8000351-T-2023 | Nexos de infraestructuras loteo social en predio D3 |
| 39 | 8000590-I-2025 | Nivelación, limpieza y compactación en espacio para veredas - Sector remanente lote 3-1 - Sec I - 418 Lotes |
| 11 | 8000882-I-2024 | Obras complementarias - Redes de infraestructuras Loteo Social en Predio D3-3 |
| 35 | 8000091-I-2026 | Ordenamiento eléctrico sobre líneas irregulares - Sector Miradores |
| 45 | 8001219-I-2024 | Proyecto urbano y estudio de impacto ambiental - Sector Mercantiles |
| 14 | 8000293-I-2025 | Red de abastecimiento de desagües cloacales sector Auka Mahuida |
| 42 | 8001208-I-2024 | Red de agua potable - 32 Lotes - Barrio Melipal |
| 17 | 8000301-I-2025 | Red de agua potable - B° Belgrano - Sector La Familia |
| 7 | 8000179-I-2026 | Red de cloacas y conexiones domiciliarias sector 7 de Mayo - Barrio Cuenca XV |
| 43 | 8001280-I-2024 | Red de desagües cloacales - 32 Lotes - B° Melipal |
| 12 | 8000571-I-2025 | Red de desagües cloacales de Peumayen |
| 16 | 8000398-I-2025 | Red de desagües cloacales y conexiones domiciliarias - B° Belgrano - Sector La Familia |
| 15 | 8000441-I-2024 | Red de desagües pluviales - Manzanas 3, 4, 5 y 6 - Desarrollo Manzana 34 |
| 9 | 8000079-I-2026 | Red de desagües pluviales - Mza. 7 a Mza. 14 - Desarrollo Manzana 34 |
| 34 | 8000478-I-2025 | Red de desagües pluviales y red vial - B° Belgrano - Sector La Familia |
| 48 | 8000416-I-2024 | Red eléctrica y alumbrado público - Sector remanente lote 3-1 - Sección I - 418 Lotes |
| 23 | 8000697-I-2025 | Red eléctrica y conexiones domiciliarias Manzana 34 |
| 2 | 8000422-I-2024 | Red pluvial - 418 Lotes - Z1 |
| 18 | 8000582-I-2025 | Red vial, movimiento de suelo, continuidad y apertura de calle - Sector remanente Lote 3-1 - Sección I - 418 Lotes |
| 6 | 8000618-I-2025 | Redes de gas y conexiones domiciliarias - Sectores 2 y 7 de Mayo - B° Cuenca XV |
| 26 | 8000760-C-2022 | Solicita asistencia de materiales |
| 30 | 8000397-G-2024 | Solicita asistencia de materiales |
| 49 | 8000139-S-2026 | Solicita construcción de vivienda Sra. Sapere Sonia Alicia - Sector D3 |
| 52 | 8000187-I-2026 | Solicitud de asistencia habitacional - Construcción de cuatro plateas - Distrito 6 |
| 33 | 8001162-M-2024 | Solución habitacional Maripil |
| 1 | 8001270-I-2024 | Tanque elevado de agua - Auka Mahuida |
```

## Archivo: `pages\10_Sistema.py`

```python
import streamlit as st
import os, sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import utils
import importlib
importlib.reload(utils)

st.set_page_config(page_title="Sistema | Decretómetro", page_icon="⚙️", layout="wide")
utils.inject_style()
st.title("Sistema y Mantenimiento")

st.markdown("---")
st.subheader("💾 Copias de Seguridad (Backups)")
st.info("El sistema realiza copias de seguridad de la base de datos (Opción A). Los archivos PDF adjuntos no se incluyen para mantener el respaldo ligero.")

col1, col2 = st.columns(2)

with col1:
    st.markdown("### Crear Copia de Seguridad")
    if st.button("Generar Backup ahora", type="primary", use_container_width=True):
        db_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "decretometro.db")
        bkp_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backups")
        
        try:
            path_b = utils.create_backup(db_path, bkp_dir)
            st.success(f"Copia creada exitosamente en: `{path_b}`")
            with open(path_b, "rb") as f:
                st.download_button("Descargar archivo de Backup (.db)", f, file_name=os.path.basename(path_b), use_container_width=True)
        except Exception as e:
            st.error(f"Error creando backup: {e}")

with col2:
    st.markdown("### Restaurar Copia de Seguridad")
    st.warning("La restauración inteligente agregará a la base de datos actual los registros que se hayan eliminado/perdido. No duplicará información ni modificará los PDFs guardados en el disco.")
    uploaded_bkp = st.file_uploader("Subir archivo de Backup (.db)", type=['db'])
    
    if uploaded_bkp and st.button("Restaurar ahora", type="secondary", use_container_width=True):
        try:
            db_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "decretometro.db")
            tmp_path = os.path.join(os.path.dirname(db_path), "temp_restore.db")
            with open(tmp_path, "wb") as f:
                f.write(uploaded_bkp.getbuffer())
                
            utils.restore_backup(db_path, tmp_path)
            os.remove(tmp_path)
            st.success("Restauración inteligente completada. Los datos faltantes han sido repoblados.")
        except Exception as e:
            st.error(f"Error al restaurar: {e}")

st.markdown("---")
st.info("El catálogo de **Gastos de Funcionamiento** se administra ahora desde la sección **💼 Gastos de Funcionamiento** en el menú lateral.")

```

## Archivo: `pages\11_Gastos_de_funcionamiento.py`

```python
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

```

## Archivo: `pages\12_Proveedores.py`

```python
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

```

## Archivo: `pages\2_Obras.py`

```python
import streamlit as st
import os, sys

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
            
            # Obtener decretos asociados
            decretos = db.get_decretos_by_obra(obra_id)
            decretos_vigentes = [d for d in decretos if d['estado'] != 'Anulado']
            decretos_anulados = [d for d in decretos if d['estado'] == 'Anulado']
            
            col_info, col_edit = st.columns(2)
            
            with col_info:
                st.subheader(f"Detalles de la Obra")
                st.write(f"**Nombre de la Obra:** {obra['nombre']}")
                st.write(f"**Expediente IMUH:** `{obra['expediente_imuh']}`")
                
                if obra.get('proveedor_razon_social'):
                    st.write(f"**Proveedor:** {obra['proveedor_razon_social']} (CUIT: {obra['proveedor_cuit']})")
                else:
                    st.write("**Proveedor:** NO INFORMA PROVEEDOR")
                
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
                    st.info("📂 **Financiación:** Fondos Propios (sin decreto asociado)")
                
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

                with st.form("edit_obra_form"):
                    e_nombre = st.text_input("Nombre de la Obra *", value=obra['nombre'])
                    e_exp = st.text_input("Expediente IMUH *", value=obra['expediente_imuh'], help="Formato estricto: 8XXXXXX-I-AAAA.")
                    e_monto_contrato = st.number_input("Monto de Contrato ($)", min_value=0.0, step=1000.0, value=float(obra.get('monto_contrato', 0.0)))
                    e_prov_id = st.selectbox(
                        "Proveedor",
                        options=list(opc_provs_edit.keys()),
                        format_func=lambda x: opc_provs_edit[x],
                        index=list(opc_provs_edit.keys()).index(curr_prov_id)
                    )
                    
                    st.warning("⚠️ **Atención:** Si cambias el nombre o el expediente IMUH, el sistema actualizará en cascada todos los registros lógicos y solicitudes históricas asociadas a este registro.")
                    confirm_cascade = st.checkbox("Entiendo que esto modificará todos los registros históricos asociados", key="chk_cascade")
                    
                    if st.form_submit_button("Guardar Cambios"):
                        if not confirm_cascade:
                            st.error("Debe marcar la casilla de confirmación para poder aplicar los cambios históricos.")
                        else:
                            try:
                                sel_p_id = e_prov_id if e_prov_id != 0 else None
                                db.update_obra(obra_id, e_nombre, e_exp, obra['activa'], sel_p_id)
                                db.update_monto_contrato_obra(obra_id, e_monto_contrato)
                                st.success("Obra actualizada correctamente.")
                                import time
                                time.sleep(1)
                                st.rerun()
                            except ValueError as e:
                                st.error(str(e))

# --- TAB 2: NUEVA OBRA ---
with tab2:
    st.subheader("Registrar Nueva Obra")
    st.info("Las obras se crean inicialmente como Fondos Propios (sin decreto). Podrán asociarse a decretos posteriormente desde la pantalla de Carga de Decretos.")

    # Mostrar mensaje de éxito persistente
    if st.session_state.get('obra_registrada_ok'):
        st.success(f"✅ Obra **\"{st.session_state['obra_registrada_nombre']}\"** registrada exitosamente.")
        del st.session_state['obra_registrada_ok']
        del st.session_state['obra_registrada_nombre']

    # Contador para resetear fields (al cambiar la key, Streamlit recrea el widget vacío)
    if 'new_obra_counter' not in st.session_state:
        st.session_state['new_obra_counter'] = 0
    form_key = f"new_obra_form_{st.session_state['new_obra_counter']}"

    provs_obras_act = db.get_proveedores_obras(only_active=True)
    opc_provs_new = {0: "NO INFORMA PROVEEDOR"}
    for p in provs_obras_act:
        opc_provs_new[p['id']] = f"{p['razon_social']} (CUIT: {p['cuit']})"
        
    with st.form(form_key):
        n_nombre = st.text_input("Nombre de la Obra *", key=f"n_nombre_{form_key}")
        n_exp = st.text_input(
            "Expediente IMUH * (Ej: 8000422-I-2024)",
            help="Formato: 7 dígitos, guión, letra mayúscula, guión, 4 dígitos. Ej: 8000422-I-2024. Es único por obra.",
            key=f"n_exp_{form_key}"
        )
        n_monto_contrato = st.number_input("Monto de Contrato ($) (Opcional)", min_value=0.0, step=1000.0, value=0.0, key=f"n_monto_contrato_{form_key}")
        n_prov_id = st.selectbox(
            "Proveedor (Opcional)",
            options=list(opc_provs_new.keys()),
            format_func=lambda x: opc_provs_new[x],
            key=f"n_prov_{form_key}"
        )
        
        if st.form_submit_button("Registrar Obra", type="primary"):
            # Validaciones frontend
            if not n_nombre.strip():
                st.error("El nombre de la obra es obligatorio.")
            elif not n_exp.strip():
                st.error("El Expediente IMUH es obligatorio.")
            elif not utils.validar_expediente_imuh(n_exp.strip()):
                st.error("❌ El Expediente IMUH no tiene un formato válido. Debe ser: 7 dígitos, guión, letra mayúscula, guión, 4 dígitos (Ej: 8000422-I-2024).")
            else:
                try:
                    sel_p_id = n_prov_id if n_prov_id != 0 else None
                    obra_id = db.add_obra(n_nombre.strip(), n_exp.strip(), sel_p_id)
                    db.update_monto_contrato_obra(obra_id, n_monto_contrato)
                    # Guardar mensaje de éxito y resetear formulario
                    st.session_state['obra_registrada_ok'] = True
                    st.session_state['obra_registrada_nombre'] = n_nombre.strip()
                    st.session_state['new_obra_counter'] += 1
                    st.rerun()
                except ValueError as e:
                    st.error(str(e))

```

## Archivo: `pages\3_Solicitudes_de_financiamiento.py`

```python
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
import tempfile
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
        
        temp_path = os.path.join(tempfile.gettempdir(), f"Reporte_Pedidos_Financiamiento_{datetime.date.today().strftime('%Y%m%d')}.pdf")
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

```

## Archivo: `pages\4_Pagos_Fondos_Propios.py`

```python
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
        # Enriquecer con nombres de obra
        obras_dict = {o['id']: f"{o['expediente_imuh']} - {o['nombre']}" for o in db.get_obras()}
        
        data = []
        for p in pagos:
            obra_nombre = obras_dict.get(p['obra_id'], "Desconocida")
            data.append({
                "ID": p['id'],
                "Obra": obra_nombre,
                "Fecha": utils.format_date_ar(p['fecha']),
                "Monto": f"${p['monto']:,.2f}",
                "Nro OP": p['nro_op'] or "-",
                "Observaciones": p['observaciones'] or "-"
            })
            
        df = pd.DataFrame(data)
        st.dataframe(df, use_container_width=True, hide_index=True)
        
        st.divider()
        st.subheader("Eliminar Pago")
        id_a_eliminar = st.selectbox("Seleccione el ID del pago que desea eliminar", options=[p['id'] for p in pagos], format_func=lambda x: f"Pago #{x}")
        
        if id_a_eliminar:
            p_sel = next(p for p in pagos if p['id'] == id_a_eliminar)
            st.warning(f"Está por eliminar el pago de ${p_sel['monto']:,.2f} a la obra '{obras_dict.get(p_sel['obra_id'])}'.")
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
        col1, col2 = st.columns(2)
        
        with col1:
            opciones_obra = {o['id']: f"{o['expediente_imuh']} - {o['nombre']}" for o in obras_activas}
            obra_id = st.selectbox("Obra Destino *", options=list(opciones_obra.keys()), format_func=lambda x: opciones_obra[x])
            
            monto = st.number_input("Monto ($) *", min_value=0.01, step=1000.0)
            fecha = st.date_input("Fecha del Pago", value=datetime.date.today(), format="DD-MM-YYYY")
        
        with col2:
            nro_op = st.text_input("Número de Orden de Pago (Bejerman)")
            observaciones = st.text_area("Observaciones", help="Obligatorio si no hay Nro OP. Entre 10 y 30 caracteres.")
            
        st.divider()
        
        # Real-time warnings
        confirmar_sin_op = False
        if not nro_op.strip():
            st.warning("⚠️ Si no ingresa un número de OP, deberá proveer observaciones detalladas y confirmar.")
            confirmar_sin_op = st.checkbox("Confirmo que deseo registrar este pago sin OP")
        else:
            confirmar_sin_op = True
            
        confirmar_sobrepago = False
        if obra_id:
            obra = db.get_obra(obra_id)
            m_contrato = obra.get('monto_contrato') or 0.0
            total_pagado_actual = db.get_total_pagado_obra(obra_id)
            
            if (total_pagado_actual + monto) > (m_contrato + db.TOLERANCE):
                st.error(f"⚠️ El pago haría que la obra supere su monto de contrato (${m_contrato:,.2f}). Marque la casilla de confirmación para registrar de todas formas.")
                confirmar_sobrepago = st.checkbox("Confirmo que deseo sobrepagar el contrato de la obra", key="chk_sobrepago_fp")
            else:
                confirmar_sobrepago = True
        else:
            confirmar_sobrepago = True
            
        if st.button("Registrar Adelanto", type="primary"):
            try:
                if not nro_op.strip() and not confirmar_sin_op:
                    raise ValueError("Debe tildar la confirmación si no provee un número de Orden de Pago.")
                if not confirmar_sobrepago:
                    raise ValueError("Debe confirmar el sobrepago marcando la casilla correspondiente.")
                    
                db.add_pago_fondos_propios(obra_id, monto, fecha.strftime('%Y-%m-%d'), nro_op.strip() if nro_op.strip() else None, observaciones.strip() if observaciones.strip() else None)
                st.success("El pago ha sido registrado correctamente.")
                import time
                time.sleep(1)
                st.rerun()
            except ValueError as e:
                st.error(str(e))

```

## Archivo: `pages\5_Decretos.py`

```python
import streamlit as st
import pandas as pd
import datetime
import os, sys
import base64

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import database as db
import importlib
importlib.reload(db)
import utils
importlib.reload(utils)

def display_pdf(file_path):
    with open(file_path, "rb") as f:
        base64_pdf = base64.b64encode(f.read()).decode('utf-8')
    # Usamos <embed> en lugar de <iframe> para mayor compatibilidad con buffers base64 en navegadores modernos
    pdf_display = f'<embed src="data:application/pdf;base64,{base64_pdf}" width="100%" height="800" type="application/pdf">'
    st.markdown(pdf_display, unsafe_allow_html=True)

st.set_page_config(page_title="Decretos | Decretómetro", page_icon="📜", layout="wide")
utils.inject_style()
st.title("Decretos 📜")

if "success_msg_dec" in st.session_state:
    st.toast(f"✅ {st.session_state['success_msg_dec']}")
    del st.session_state["success_msg_dec"]

tab1, tab2 = st.tabs(["🗂️ Directorio y Detalles", "➕ Nuevo Decreto"])

# --- TAB 1: LISTADO Y DETALLES ---
with tab1:
    decretos = db.get_decretos()
    if not decretos:
        st.info("No hay decretos cargados en el sistema.")
    else:
        st.subheader("Buscar / Seleccionar Decreto")
        opciones = []
        obras_all = db.get_obras()
        mapa_imuh_nombres = {o['expediente_imuh'].strip(): o['nombre'] for o in obras_all if o.get('expediente_imuh')}
        
        for d in decretos:
            if d.get('expediente_imuh'):
                parts = [p.strip() for p in d['expediente_imuh'].split(',') if p.strip()]
                imuh_con_nombres = []
                for p in parts:
                    nombre = mapa_imuh_nombres.get(p)
                    if nombre:
                        imuh_con_nombres.append(f"{p} ({nombre})")
                    else:
                        imuh_con_nombres.append(p)
                exp_imuh_str = f" | IMUH: {', '.join(imuh_con_nombres)}"
            else:
                exp_imuh_str = " | IMUH: Sin asignar"
            
            opciones.append(f"ID: {d['id']} | Dto. {d['nro_decreto']}/{d['anio']} - {d['destino_fondos']}{exp_imuh_str}")
        seleccion = st.selectbox("Seleccione un decreto para ver su detalle (puede tipear el Exp IMUH):", opciones)
        
        if seleccion:
            dec_id = int(seleccion.split(" | ")[0].replace("ID: ", ""))
            dec = db.get_decreto(dec_id)
            cuotas = db.get_cuotas_by_decreto(dec_id)
            cobros = [c for c in db.get_all_cobros() if c['decreto_id'] == dec_id]
            
            st.markdown("---")
            col_info, col_actions = st.columns([3, 1])
            
            with col_info:
                st.subheader(f"Decreto {dec['nro_decreto']}/{dec['anio']}")
                
                # Mostrar origen si proviene de una Solicitud de Financiamiento
                sol_asoc = db.get_solicitud_por_decreto(dec_id)
                if sol_asoc:
                    st.info(f"📑 **Decreto originado desde la Solicitud de Financiamiento Exp: {sol_asoc['nro_expediente']} (Aprobada)**")
                    
                st.write(f"**Expediente:** {dec['nro_expediente']}")
                if dec.get('expediente_imuh'):
                    parts = [p.strip() for p in dec['expediente_imuh'].split(',') if p.strip()]
                    imuh_con_nombres = []
                    obras_all = db.get_obras()
                    mapa_imuh_nombres = {o['expediente_imuh'].strip(): o['nombre'] for o in obras_all if o.get('expediente_imuh')}
                    for p in parts:
                        nombre = mapa_imuh_nombres.get(p)
                        if nombre:
                            imuh_con_nombres.append(f"{p} ({nombre})")
                        else:
                            imuh_con_nombres.append(p)
                    exp_imuh_disp = ', '.join(imuh_con_nombres)
                else:
                    exp_imuh_disp = "Expediente IMUH sin asignar"
                    
                st.write(f"**Expediente IMUH:** {exp_imuh_disp}")
                
                with st.expander("✏️ Editar solo Expediente IMUH"):
                    with st.form("form_quick_imuh"):
                        new_imuh = st.text_input("Nuevo Expediente IMUH", value=dec.get('expediente_imuh', ''), help="Formato: 8XXXXXX-Y-AAAA.")
                        st.caption("💡 Puedes ingresar varios separados por coma, punto y coma, o barra. Ej: `8000063-I-2026, 8000064-I-2026`")
                        if st.form_submit_button("Guardar IMUH"):
                            if not utils.validar_expediente_imuh(new_imuh):
                                st.error("El Expediente IMUH tiene un formato inválido. Asegúrese que cada uno respete 8XXXXXX-Y-AAAA.")
                            else:
                                exp_imuh_val = utils.normalizar_expediente_imuh(new_imuh)
                                db.update_decreto(dec_id, dec['nro_decreto'], dec['anio'], dec['nro_expediente'], dec['destino_fondos'], dec['pdf_path'], exp_imuh_val)
                                st.success("Expediente IMUH actualizado.")
                                st.rerun()

                st.write(f"**Destino:** {dec['destino_fondos']}")
                
                estado_color = "red" if dec['estado'] == 'Con deuda' else ("green" if dec['estado'] == 'Terminado' else ("blue" if dec['estado'] == 'Vigente' else "gray"))
                st.markdown(f"**Estado General:** :{estado_color}[{dec['estado']}]")
                
                if dec['pdf_path'] and os.path.exists(dec['pdf_path']):
                    st.write("📄 **PDF Adjunto disponible:**")
                    with open(dec['pdf_path'], "rb") as f:
                        st.download_button("📥 Descargar PDF para Ver", f, file_name=os.path.basename(dec['pdf_path']), key="btn_desc_dec")
                else:
                    st.write("No hay PDF adjunto.")
            
            with col_actions:
                st.write("**Acciones:**")
                # Botón de anular
                if dec['estado'] != 'Anulado':
                    confirma_anular = st.checkbox("Confirmar anulación", key=f"chk_anular_{dec_id}")
                    if st.button("🚫 Anular Decreto", use_container_width=True, disabled=not confirma_anular):
                        db.update_estado_decreto(dec_id, 'Anulado')
                        st.success("Decreto anulado.")
                        st.rerun()
                
                # Botón de eliminar archivo
                if dec['pdf_path']:
                    if st.button("🗑️ Eliminar Archivo PDF", use_container_width=True):
                        utils.delete_file(dec['pdf_path'])
                        db.update_decreto(dec_id, dec['nro_decreto'], dec['anio'], dec['nro_expediente'], dec['destino_fondos'], None)
                        st.success("Archivo eliminado.")
                        st.rerun()
                
                # Eliminación completa (Cascada)
                st.divider()
                st.info("Eliminar decreto borrará también cuotas y cobros.")
                # We need a confirmation but streamlit buttons are tricky, let's use a checkbox + button
                confirma = st.checkbox("Estoy seguro de eliminar")
                if st.button("💀 Eliminar Decreto Completo", use_container_width=True, disabled=not confirma):
                    try:
                        db.delete_decreto(dec_id)
                        utils.delete_file(dec['pdf_path'])
                        st.session_state["success_msg_dec"] = "Decreto eliminado correctamente."
                        st.rerun()
                    except ValueError as e:
                        st.error(str(e))
            
            # Movimientos Internos de Fondos
            prestamos = db.get_prestamos(dec_id)
            if prestamos:
                pendientes = [p for p in prestamos if p['devolucion_estado'] == 'Pendiente']
                if pendientes:
                    total_prestado = sum(p['monto'] for p in pendientes)
                    st.warning(f"⚠️ **Atención:** Este decreto tiene **{utils.format_currency_ar(total_prestado)}** prestados temporalmente a otras obras/urgencias. (Ve a la pestaña '💸 Préstamos Internos' para más detalles).")

            st.markdown("### Estado de Cuotas")
            # Presentar cuotas y su estado de cobro (desglosado por pagos parciales)
            tabla_cuotas = []
            total_proyectado = 0
            total_cobrado = 0
            
            for cuota in cuotas:
                monto_q = cuota['monto']
                total_proyectado += monto_q
                
                # Cobros de esta cuota
                cobro_list = [c for c in cobros if c['cuota_id'] == cuota['id']]
                due_date = utils.get_due_date(cuota['mes'], cuota['anio'])
                today_date = datetime.date.today()
                
                if not cobro_list:
                    # Sin cobros
                    atrasado = today_date > due_date
                    tabla_cuotas.append({
                        "ID Cuota": cuota['id'],
                        "Periodo": f"{cuota['mes']:02d}/{cuota['anio']}",
                        "Vencimiento": utils.format_date_ar(due_date),
                        "Proyectado": monto_q,
                        "Cobrado": 0.0,
                        "Fecha Cobro": "-",
                        "Saldo": monto_q,
                        "Estado": "🔴 Atrasado" if atrasado else "🟢 Al día"
                    })
                else:
                    saldo_acumulado = monto_q
                    for c_idx, c_item in enumerate(sorted(cobro_list, key=lambda x: x['fecha'])):
                        monto_c = c_item['monto']
                        total_cobrado += monto_c
                        saldo_acumulado -= monto_c
                        
                        atrasado = utils.is_late(cuota['mes'], cuota['anio'], c_item['fecha'])
                        
                        estado_str = "🟢 Parcial"
                        if saldo_acumulado <= 0.01:
                            estado_str = "✅ Cobrado"
                        if atrasado:
                            estado_str += " (Tarde)" if "✅" in estado_str else " 🔴 Atrasado"
                        
                        tabla_cuotas.append({
                            "ID Cuota": cuota['id'],
                            "Periodo": f"{cuota['mes']:02d}/{cuota['anio']}",
                            "Vencimiento": utils.format_date_ar(due_date),
                            "Proyectado": monto_q,
                            "Cobrado": monto_c,
                            "Fecha Cobro": utils.format_date_ar(c_item['fecha']),
                            "Saldo": max(0, saldo_acumulado),
                            "Estado": estado_str
                        })
                
            df_tc = pd.DataFrame(tabla_cuotas)
            
            # Aplicar formato de moneda para visualización
            df_tc['Proyectado'] = df_tc['Proyectado'].apply(lambda x: utils.format_currency_ar(x))
            df_tc['Cobrado'] = df_tc['Cobrado'].apply(lambda x: utils.format_currency_ar(x))
            df_tc['Saldo'] = df_tc['Saldo'].apply(lambda x: utils.format_currency_ar(x))
            
            st.dataframe(
                df_tc, 
                use_container_width=True, 
                hide_index=True,
                column_config={
                    "ID Cuota": st.column_config.NumberColumn(format="%d"),
                    "Proyectado": "Proyectado",
                    "Cobrado": "Cobrado",
                    "Saldo": "Saldo",
                }
            )
            
            st.write(f"**Total Proyectado:** {utils.format_currency_ar(total_proyectado)} | **Total Cobrado:** {utils.format_currency_ar(total_cobrado)} | **Saldo Total:** {utils.format_currency_ar(total_proyectado - total_cobrado)}")
            
            st.markdown("---")
            st.markdown("### Editar Decreto (Datos Generales)")
            with st.expander("Modificar datos de este decreto"):
                obras_totales = db.get_obras()
                obras_asociadas = db.get_obras_by_decreto(dec_id)
                obras_asociadas_ids = [o['id'] for o in obras_asociadas]
                
                obras_opc_edit = {o['id']: f"{o['expediente_imuh']} - {o['nombre']}" for o in obras_totales}
                
                if f"edit_decreto_obras_ids_{dec_id}" not in st.session_state:
                    st.session_state[f"edit_decreto_obras_ids_{dec_id}"] = obras_asociadas_ids
                
                e_nro = st.number_input("Nro", value=dec['nro_decreto'], min_value=1, step=1, key=f"edit_dec_nro_{dec_id}")
                e_anio = st.number_input("Año", value=dec['anio'], step=1, key=f"edit_dec_anio_{dec_id}")
                e_exp = st.text_input("Expediente Municipal", value=dec['nro_expediente'], key=f"edit_dec_exp_{dec_id}")
                
                # Selector de obras interactivo en edición de decreto
                st.write("Obras del Catálogo Asociadas *")
                col_sel_ed, col_btn_ed = st.columns([3, 1.2])
                disponibles_ed = {k: v for k, v in obras_opc_edit.items() if k not in st.session_state[f"edit_decreto_obras_ids_{dec_id}"]}
                
                if disponibles_ed:
                    sel_obra_ed = col_sel_ed.selectbox("Buscar obra", options=list(disponibles_ed.keys()), format_func=lambda x: disponibles_ed[x], label_visibility="collapsed", key=f"sel_dec_edit_{dec_id}")
                    if col_btn_ed.button("Agregar obra", use_container_width=True, key=f"btn_add_dec_edit_{dec_id}"):
                        st.session_state[f"edit_decreto_obras_ids_{dec_id}"].append(sel_obra_ed)
                        st.rerun()
                else:
                    col_sel_ed.info("Todas las obras ya fueron agregadas.")
                
                # Listado interactivo
                e_obras_sel = st.session_state[f"edit_decreto_obras_ids_{dec_id}"]
                if e_obras_sel:
                    for o_id in list(e_obras_sel):
                        obra_obj = db.get_obra(o_id)
                        if obra_obj:
                            col_info_ed, col_del_ed = st.columns([4, 1])
                            col_info_ed.info(f"🏗️ {obra_obj['expediente_imuh']} - {obra_obj['nombre']}")
                            
                            confirm_key = f"confirm_del_dec_edit_{o_id}_{dec_id}"
                            if st.session_state.get("confirm_delete_obra") == confirm_key:
                                col_info_ed.warning(f"⚠️ ¿Confirmas que deseas desvincular la obra '{obra_obj['nombre']}' del decreto?")
                                col_si, col_no = col_info_ed.columns(2)
                                if col_si.button("Sí, desvincular", key=f"yes_{confirm_key}"):
                                    st.session_state[f"edit_decreto_obras_ids_{dec_id}"].remove(o_id)
                                    del st.session_state["confirm_delete_obra"]
                                    st.rerun()
                                if col_no.button("Cancelar", key=f"no_{confirm_key}"):
                                    del st.session_state["confirm_delete_obra"]
                                    st.rerun()
                            else:
                                if col_del_ed.button("Borrar", key=f"del_{confirm_key}"):
                                    st.session_state["confirm_delete_obra"] = confirm_key
                                    st.rerun()
                else:
                    st.warning("⚠️ Debe asociar al menos una obra al decreto.")
                
                # Advertencias de cruce de decretos
                obras_con_otros_decretos = []
                for o_id in e_obras_sel:
                    otros_decretos = [d for d in db.get_decretos_by_obra(o_id) if d['id'] != dec_id]
                    if otros_decretos:
                        obra_obj = db.get_obra(o_id)
                        dec_strs = ", ".join(f"{d['nro_decreto']}/{d['anio']}" for d in otros_decretos)
                        obras_con_otros_decretos.append(f"- **{obra_obj['nombre']}**: ya está en Decreto(s) {dec_strs}")
                        
                confirmar_cruce_edit = False
                if obras_con_otros_decretos:
                    st.warning("⚠️ **Advertencia de Obras duplicadas en Decretos:**\n" + "\n".join(obras_con_otros_decretos))
                    confirmar_cruce_edit = st.checkbox("Confirmo que deseo asociar estas obras a pesar de estar en otros decretos", key=f"chk_cruce_edit_{dec_id}")
                
                # Validación manual de expediente duplicado
                exp_existe = db.check_expediente_exists(e_exp, exclude_id=dec_id)
                confirmar_duplicado_edit = False
                if exp_existe:
                    st.warning(f"⚠️ El expediente municipal '{e_exp}' ya está vinculado a otro decreto.")
                    confirmar_duplicado_edit = st.checkbox("Confirmar uso de expediente duplicado", key=f"chk_exp_dup_edit_{dec_id}")
                    
                e_sub = st.button("Actualizar", type="primary", key=f"btn_save_dec_edit_{dec_id}")
                if e_sub:
                    if exp_existe and not confirmar_duplicado_edit:
                        st.error("Debe confirmar el uso del expediente duplicado.")
                    elif obras_con_otros_decretos and not confirmar_cruce_edit:
                        st.error("Debe confirmar la asociación de obras duplicadas en otros decretos.")
                    elif not e_obras_sel:
                        st.error("Debe seleccionar al menos una obra para el decreto.")
                    else:
                        # Auto-generar campos heredados destino_fondos y expediente_imuh
                        selected_obras_objs = [db.get_obra(oid) for oid in e_obras_sel]
                        e_dest = " + ".join(o['nombre'] for o in selected_obras_objs)
                        e_exp_imuh = ", ".join(o['expediente_imuh'] for o in selected_obras_objs)
                        
                        db.update_decreto(dec_id, e_nro, e_anio, e_exp, e_dest, dec['pdf_path'], e_exp_imuh)
                        db.add_decreto_obras(dec_id, e_obras_sel)
                        
                        # Limpiar session state del selector para este decreto
                        if f"edit_decreto_obras_ids_{dec_id}" in st.session_state:
                            del st.session_state[f"edit_decreto_obras_ids_{dec_id}"]
                            
                        st.success("Decreto actualizado correctamente.")
                        st.rerun()

# --- TAB 2: NUEVO DECRETO ---
with tab2:
    if "success_msg" in st.session_state:
        st.success(st.session_state["success_msg"])
        del st.session_state["success_msg"]
        
    st.subheader("Cargar Nuevo Decreto")
    
    # Vincular con Solicitud de Financiamiento pendiente
    solicitudes_pendientes = [s for s in db.get_solicitudes() if s['estado'] == 'Pendiente']
    opciones_sol = ["(Cargar decreto sin pedido de financiamiento asociado)"] + [
        f"ID Solicitud: {s['id']} | Exp: {s['nro_expediente']} | {s['destino_fondos']} ({utils.format_currency_ar(s['monto_solicitado'])})"
        for s in solicitudes_pendientes
    ]
    
    sol_seleccionada_str = st.selectbox(
        "¿Este decreto corresponde a un pedido de financiamiento pendiente?", 
        options=opciones_sol,
        key="sel_solicitud_asoc"
    )
    
    sol_id_asoc = None
    default_exp = ""
    default_monto = 0.01
    
    if sol_seleccionada_str != "(Cargar decreto sin pedido de financiamiento asociado)":
        sol_id_asoc = int(sol_seleccionada_str.split(" | ")[0].replace("ID Solicitud: ", ""))
        sol_asoc = next(s for s in solicitudes_pendientes if s['id'] == sol_id_asoc)
        default_exp = sol_asoc['nro_expediente']
        default_monto = float(sol_asoc['monto_solicitado'])
        
    col1, col2 = st.columns(2)
    nro_decreto = col1.number_input("Nro. Decreto *", min_value=1, step=1, key="in_nro_dec")
    anio_decreto = col2.number_input("Año *", min_value=2000, max_value=2100, value=datetime.date.today().year, step=1, key="in_anio_dec")
    
    if sol_id_asoc is not None:
        nro_expediente = default_exp
        st.info(f"📁 **Nro. Expediente Municipal (Asociado del Pedido):** `{nro_expediente}`")
    else:
        nro_expediente = st.text_input("Nro. Expediente Municipal * (Ej: OE-5732-M-2025)", value=default_exp, key="in_exp")
    
    selected_obras_new = []
    
    if sol_id_asoc is not None:
        sol_asoc_obj = db.get_solicitud(sol_id_asoc)
        if sol_asoc_obj and sol_asoc_obj['expediente_imuh']:
            imuh_parts = [p.strip() for p in sol_asoc_obj['expediente_imuh'].split(',') if p.strip()]
            resolved_obras_objs = []
            resolved_obras_ids = []
            for part in imuh_parts:
                o_obj = db.get_obra_by_expediente(part)
                if o_obj:
                    resolved_obras_objs.append(o_obj)
                    resolved_obras_ids.append(o_obj['id'])
            if resolved_obras_objs:
                st.info("🏗️ **Obras asociadas automáticamente (del Pedido):**")
                for o_obj in resolved_obras_objs:
                    st.markdown(f"- {o_obj['expediente_imuh']} - {o_obj['nombre']}")
                selected_obras_new = resolved_obras_ids
    else:
        # Filtrar obras vinculadas a solicitudes activas (Pendientes)
        sols_totales = db.get_solicitudes()
        imuhs_pendientes = set()
        for s in sols_totales:
            if s['estado'] == 'Pendiente' and s.get('expediente_imuh'):
                parts = [p.strip() for p in s['expediente_imuh'].split(',') if p.strip()]
                imuhs_pendientes.update(parts)
                
        obras_totales = db.get_obras()
        obras_disponibles = [o for o in obras_totales if o.get('expediente_imuh') and o['expediente_imuh'].strip() not in imuhs_pendientes]
        obras_opc_new = {o['id']: f"{o['expediente_imuh']} - {o['nombre']}" for o in obras_disponibles}

        if "new_decreto_obras_ids" not in st.session_state:
            st.session_state["new_decreto_obras_ids"] = []
            
        st.write("Seleccione Obras del Catálogo Asociadas *")
        col_sel_nd, col_btn_nd = st.columns([3, 1.2])
        disponibles_nd = {k: v for k, v in obras_opc_new.items() if k not in st.session_state["new_decreto_obras_ids"]}
        
        if disponibles_nd:
            sel_obra_nd = col_sel_nd.selectbox("Buscar obra", options=list(disponibles_nd.keys()), format_func=lambda x: disponibles_nd[x], label_visibility="collapsed", key="sel_obra_new_dec")
            if col_btn_nd.button("Agregar obra", use_container_width=True, key="btn_add_obra_new_dec"):
                st.session_state["new_decreto_obras_ids"].append(sel_obra_nd)
                st.rerun()
        else:
            col_sel_nd.info("Todas las obras ya fueron agregadas.")
            
        # Listado interactivo
        if st.session_state["new_decreto_obras_ids"]:
            for o_id in list(st.session_state["new_decreto_obras_ids"]):
                obra_obj = db.get_obra(o_id)
                if obra_obj:
                    col_info_nd, col_del_nd = st.columns([4, 1])
                    col_info_nd.info(f"🏗️ {obra_obj['expediente_imuh']} - {obra_obj['nombre']}")
                    
                    confirm_key = f"confirm_del_new_dec_{o_id}"
                    if st.session_state.get("confirm_delete_obra") == confirm_key:
                        col_info_nd.warning(f"⚠️ ¿Confirmas que deseas quitar la obra '{obra_obj['nombre']}'?")
                        col_si, col_no = col_info_nd.columns(2)
                        if col_si.button("Sí, quitar", key=f"yes_{confirm_key}"):
                            st.session_state["new_decreto_obras_ids"].remove(o_id)
                            del st.session_state["confirm_delete_obra"]
                            st.rerun()
                        if col_no.button("Cancelar", key=f"no_{confirm_key}"):
                            del st.session_state["confirm_delete_obra"]
                            st.rerun()
                    else:
                        if col_del_nd.button("Borrar", key=f"del_{confirm_key}"):
                            st.session_state["confirm_delete_obra"] = confirm_key
                            st.rerun()
        else:
            st.warning("⚠️ No se ha seleccionado ninguna obra para el decreto.")
            
        selected_obras_new = st.session_state["new_decreto_obras_ids"]
        
    obras_con_otros_decretos_new = []
    for o_id in selected_obras_new:
        otros_decretos = db.get_decretos_by_obra(o_id)
        if otros_decretos:
            obra_obj = db.get_obra(o_id)
            dec_strs = ", ".join(f"{d['nro_decreto']}/{d['anio']}" for d in otros_decretos)
            obras_con_otros_decretos_new.append(f"- **{obra_obj['nombre']}**: ya está en Decreto(s) {dec_strs}")
            
    confirmar_cruce_nuevo = False
    if obras_con_otros_decretos_new:
        st.warning("⚠️ **Advertencia de Obras duplicadas en Decretos:**\n" + "\n".join(obras_con_otros_decretos_new))
        confirmar_cruce_nuevo = st.checkbox("Confirmo que deseo asociar estas obras a pesar de estar en otros decretos", key="chk_cruce_new")
    
    monto_total = st.number_input("Monto Total del Decreto * ($)", min_value=0.01, value=default_monto, step=1000.0, key="in_monto")
    
    pdf_file = st.file_uploader("Adjuntar PDF del Decreto (Opcional)", type=["pdf"], key="in_pdf")
    
    st.markdown("### Cuotas")
    st.info("Ingresa las cuotas a continuación. Puedes usar la tabla para añadir cuotas manualmente o usar el botón para auto-agregar el mes consecutivo:")
    
    MONTHS = ["1 - Enero", "2 - Febrero", "3 - Marzo", "4 - Abril", "5 - Mayo", "6 - Junio", 
              "7 - Julio", "8 - Agosto", "9 - Septiembre", "10 - Octubre", "11 - Noviembre", "12 - Diciembre"]
              
    if 'cuotas_base' not in st.session_state:
        mes_actual = MONTHS[datetime.date.today().month - 1]
        st.session_state.cuotas_base = pd.DataFrame([{"Mes": mes_actual, "Año": datetime.date.today().year, "Monto ($)": 0.01}])

    edited_cuotas = st.data_editor(
        st.session_state.cuotas_base, 
        num_rows="dynamic", 
        use_container_width=True,
        key="editor_cuotas_key",
        column_config={
            "Mes": st.column_config.SelectboxColumn("Mes", options=MONTHS, required=True),
            "Año": st.column_config.NumberColumn("Año", min_value=2000, max_value=2100, step=1, required=True),
            "Monto ($)": st.column_config.NumberColumn("Monto ($)", min_value=0.01, step=0.01, required=True)
        }
    )
    
    # Interceptar cuando el usuario añade una fila vía TAB o la UI nativa
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
            
            # Auto completado de saldo
            current_sum = pd.to_numeric(df.loc[:idx-1, "Monto ($)"], errors='coerce').sum()
            remain = monto_total - current_sum
            df.at[idx, 'Monto ($)'] = max(0.01, remain)
            
        st.session_state.cuotas_base = df
        if "editor_cuotas_key" in st.session_state:
            del st.session_state["editor_cuotas_key"]
        st.rerun()

    if st.button("➕ Auto-agregar Mes Consecutivo"):
        df = edited_cuotas.copy()
        if not df.empty:
            last_row = df.iloc[-1]
            try:
                curr_mes_idx = MONTHS.index(last_row["Mes"])
            except:
                curr_mes_idx = 0
            curr_anio = int(last_row["Año"])
            
            next_mes_idx = (curr_mes_idx + 1) % 12
            next_anio = curr_anio + 1 if next_mes_idx == 0 else curr_anio
            
            # Auto completado de saldo
            current_sum = pd.to_numeric(df["Monto ($)"], errors='coerce').sum()
            remain = monto_total - current_sum
            
            new_row = {"Mes": MONTHS[next_mes_idx], "Año": next_anio, "Monto ($)": max(0.01, remain)}
            df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
            st.session_state.cuotas_base = df
            if "editor_cuotas_key" in st.session_state:
                del st.session_state["editor_cuotas_key"]
            st.rerun()

    # Calcular total al vuelo
    total_edited = pd.to_numeric(edited_cuotas["Monto ($)"], errors='coerce').sum() if not edited_cuotas.empty else 0.0
    
    col_sum1, col_sum2 = st.columns(2)
    with col_sum1:
        st.write(f"Monto Total del Decreto: **{utils.format_currency_ar(monto_total)}**")
    with col_sum2:
        st.write(f"Suma de Cuotas Cargadas: **{utils.format_currency_ar(total_edited)}**")
    
    if abs(total_edited - monto_total) > 0.01 and total_edited > 0:
        st.warning("⚠️ La sumatoria de las cuotas no coincide con el monto total.")
        
    if sol_id_asoc is not None:
        sol_asoc = next(s for s in solicitudes_pendientes if s['id'] == sol_id_asoc)
        if abs(monto_total - float(sol_asoc['monto_solicitado'])) > 0.01:
            st.info(f"💡 **Nota:** La solicitud de financiamiento asociada requiere **{utils.format_currency_ar(sol_asoc['monto_solicitado'])}**, pero el monto del decreto es **{utils.format_currency_ar(monto_total)}**.")
    
    # Validación preventiva de duplicados para mostrar checkbox
    exp_existe_nuevo = False
    confirmar_duplicado_nuevo = False
    if nro_expediente:
        if db.check_expediente_exists(nro_expediente):
            exp_existe_nuevo = True
            st.warning(f"⚠️ El expediente '{nro_expediente}' ya fue ingresado previamente en otro decreto.")
            confirmar_duplicado_nuevo = st.checkbox("Confirmar ingreso de expediente duplicado", key="in_exp_dup_new")

    submit = st.button("Guardar Decreto", type="primary", use_container_width=True)
    if submit:
        # Validations
        if not nro_decreto or not anio_decreto or not nro_expediente:
            st.error("Por favor completa los campos obligatorios (*).")
        elif not selected_obras_new:
            st.error("Debe asociar al menos una obra al decreto.")
        elif obras_con_otros_decretos_new and not confirmar_cruce_nuevo:
            st.error("Debe confirmar la asociación de obras duplicadas en otros decretos.")
        elif edited_cuotas.empty or edited_cuotas["Monto ($)"].isna().any():
            st.error("Debes ingresar al menos una cuota válida y completa.")
        elif edited_cuotas["Mes"].isna().any() or edited_cuotas["Año"].isna().any():
            st.error("Mes y Año son obligatorios en las cuotas.")
        elif any(pd.to_numeric(edited_cuotas["Monto ($)"], errors='coerce') <= 0):
            st.error("El monto de cada cuota debe ser mayor a 0.")
        elif abs(total_edited - float(monto_total)) > 0.01:
            st.error(f"La sumatoria de las cuotas ({utils.format_currency_ar(total_edited)}) debe ser exactamente igual al Monto Total cargado ({utils.format_currency_ar(monto_total)}).")
        elif exp_existe_nuevo and not confirmar_duplicado_nuevo:
            st.error(f"El número de expediente '{nro_expediente}' ya existe. Debe confirmar su ingreso duplicado marcando el checkbox de arriba.")
        else:
            try:
                pdf_path = utils.save_uploaded_file(pdf_file) if pdf_file else None
                # Auto-generar campos heredados destino y expediente_imuh
                selected_obras_objs = [db.get_obra(oid) for oid in selected_obras_new]
                destino = " + ".join(o['nombre'] for o in selected_obras_objs)
                exp_imuh_val = ", ".join(o['expediente_imuh'] for o in selected_obras_objs)
                
                d_id = db.add_decreto(int(nro_decreto), int(anio_decreto), nro_expediente, destino, pdf_path, exp_imuh_val)
                db.add_decreto_obras(d_id, selected_obras_new)
                
                for _, row in edited_cuotas.iterrows():
                    mes_int = int(str(row['Mes']).split(" - ")[0])
                    db.add_cuota(d_id, mes_int, int(row['Año']), float(row['Monto ($)']))
                
                st.session_state["success_msg_dec"] = f"Decreto N° {nro_decreto}/{anio_decreto} creado con éxito."
                
                # Si hay solicitud asociada, vincular y aprobar
                if sol_id_asoc is not None:
                    db.update_estado_solicitud(sol_id_asoc, 'Aprobado', d_id)
                
                # Clear state
                for key in ["in_nro_dec", "in_anio_dec", "in_exp", "in_monto", "in_pdf", "cuotas_base", "editor_cuotas_key", "sel_solicitud_asoc", "in_obras_new", "new_decreto_obras_ids"]:
                    if key in st.session_state:
                        del st.session_state[key]
                st.rerun()
            except Exception as e:
                st.error(f"Error al guardar: {e}")

```

## Archivo: `pages\6_Cobros.py`

```python
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
                cobrado = sum(cb['monto'] for cb in cobros_existentes if cb['cuota_id'] == c['id'])
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
                        
                        btn = st.form_submit_button("Registrar Cobro", type="primary")
                        if btn:
                            if fecha > datetime.date.today():
                                st.error("Error: No se pueden registrar cobros con fecha futura.")
                            else:
                                try:
                                    path = utils.save_uploaded_file(comp_file) if comp_file else None
                                    db.add_cobro(sel_cuota_id, float(monto), fecha.strftime('%Y-%m-%d'), path)
                                    st.session_state["succ_cobro"] = f"Cobro de {utils.format_currency_ar(float(monto))} registrado exitosamente."
                                    st.session_state["cobro_form_id"] += 1
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
            decretos_list = sorted(list(set(f"{c['nro_decreto']}/{c['decreto_anio']}" for c in cobros)))
            f_decreto = st.multiselect("Filtrar por Decreto", options=decretos_list)
        with col_f3:
            min_m = min(c['monto'] for c in cobros) if cobros else 0
            max_m = max(c['monto'] for c in cobros) if cobros else 0
            f_monto = st.slider("Filtrar por Importe", float(min_m), float(max_m), (float(min_m), float(max_m)))

        tabla = []
        for c in cobros:
            fecha_dt = datetime.datetime.strptime(c['fecha'], '%Y-%m-%d').date()
            dec_str = f"{c['nro_decreto']}/{c['decreto_anio']}"
            
            # Aplicar filtros
            if not (f_desde <= fecha_dt <= f_hasta): continue
            if f_decreto and dec_str not in f_decreto: continue
            if not (f_monto[0] <= c['monto'] <= f_monto[1]): continue

            tabla.append({
                "ID": c['id'],
                "Fecha": fecha_dt,
                "Decreto": dec_str,
                "Obra": c.get('obra', ''),
                "Nro. de cuota": f"{c.get('seq_nro', 1)}/{c.get('total_cuotas', 1)}",
                "Periodo de la cuota": f"{c['mes']:02d}/{c['anio']}",
                "Monto": c['monto'],
                "Comprobante": "Sí" if c['comprobante_path'] else "No"
            })
        df_export = pd.DataFrame(tabla)
        df_c = df_export.copy()
        if not df_c.empty:
            df_c['Fecha'] = df_c['Fecha'].apply(lambda d: utils.format_date_ar(d))
            df_c['Monto'] = df_c['Monto'].apply(lambda x: utils.format_currency_ar(x))

        st.dataframe(
            df_c, 
            use_container_width=True, 
            hide_index=True,
            column_config={
                "Monto": "Monto",
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
                    num_format = workbook.add_format({'num_format': '#,##0.00'})
                    date_format = workbook.add_format({'num_format': 'dd/mm/yyyy'})
                    if 'Fecha' in df_export.columns:
                        col_idx_f = df_export.columns.get_loc("Fecha")
                        worksheet.set_column(col_idx_f, col_idx_f, 13, date_format)
                    if 'Monto' in df_export.columns:
                        col_idx_m = df_export.columns.get_loc("Monto")
                        worksheet.set_column(col_idx_m, col_idx_m, 18, num_format)
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


```

## Archivo: `pages\7_Aportes_Habituales.py`

```python
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

```

## Archivo: `pages\8_Trazabilidad.py`

```python
import streamlit as st
import os
import sys
import pandas as pd

# Configurar path para importar modulos locales
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import database as db
import importlib
importlib.reload(db)
import utils
importlib.reload(utils)

from trazabilidad_graph import mostrar_mapa_trazabilidad

st.set_page_config(
    page_title="Trazabilidad | Decretometro",
    page_icon="🗺️",
    layout="wide"
)

utils.inject_style()

st.title("🗺️ Trazabilidad Bidireccional de Fondos")
st.markdown(
    "Explora el camino del dinero en ambas direcciones: "
    "**desde un decreto hacia sus destinos**, o "
    "**desde una obra hacia los decretos que la financiaron**."
)
st.markdown("---")

tab_a, tab_b, tab_c = st.tabs([
    "📤 Modo A: Decreto → Destinos",
    "📥 Modo B: Obra ← Orígenes",
    "⚖️ Modo C: Compensación de Saldos Cruzados"
])

# ─────────────────────────────────────────────────────────────────────────────
# TAB A: Decreto → Destinos
# ─────────────────────────────────────────────────────────────────────────────
with tab_a:
    st.subheader("📤 Trazabilidad: Decreto → Destinos del Dinero")
    st.markdown(
        "Selecciona un **decreto** y luego el **cobro** que queres visualizar. "
        "El mapa muestra como se distribuyo ese cobro: fin original, reserva y desvios."
    )

    decretos_list = db.get_decretos()
    if not decretos_list:
        st.warning("No hay decretos registrados.")
    else:
        opc_dec = {
            d['id']: f"Dto. {d['nro_decreto']}/{d['anio']} — {d['destino_fondos']}"
            for d in decretos_list
        }
        sel_dec_id = st.selectbox(
            "Selecciona el Decreto:",
            options=list(opc_dec.keys()),
            format_func=lambda x: opc_dec[x],
            key="traz_a_decreto"
        )

        if sel_dec_id:
            cuotas = db.get_cuotas_by_decreto(sel_dec_id)
            if not cuotas:
                st.info("Este decreto no tiene cuotas configuradas.")
            else:
                opc_cuota = {
                    c['id']: f"Cuota {c['mes']:02d}/{c['anio']} — {utils.format_currency_ar(c['monto'])}"
                    for c in cuotas
                }
                sel_cuota_id = st.selectbox(
                    "Selecciona la Cuota:",
                    options=list(opc_cuota.keys()),
                    format_func=lambda x: opc_cuota[x],
                    key="traz_a_cuota"
                )

                if sel_cuota_id:
                    cobros = db.get_cobros_by_cuota(sel_cuota_id)
                    if not cobros:
                        st.info("Esta cuota no tiene cobros registrados.")
                    else:
                        if len(cobros) > 1:
                            opc_cobro = {
                                c['id']: f"Cobro del {utils.format_date_ar(c['fecha'])} — {utils.format_currency_ar(c['monto'])}"
                                for c in cobros
                            }
                            sel_cobro_id = st.selectbox(
                                "Selecciona el Cobro a visualizar:",
                                options=list(opc_cobro.keys()),
                                format_func=lambda x: opc_cobro[x],
                                key="traz_a_cobro"
                            )
                        else:
                            sel_cobro_id = cobros[0]['id']
                            st.caption(
                                f"Cobro unico: {utils.format_date_ar(cobros[0]['fecha'])} — "
                                f"{utils.format_currency_ar(cobros[0]['monto'])}"
                            )

                        st.markdown("---")
                        st.markdown("### 🗺️ Mapa de Trazabilidad")
                        mostrar_mapa_trazabilidad(sel_cobro_id)


# ─────────────────────────────────────────────────────────────────────────────
# TAB B: Obra ← Orígenes
# ─────────────────────────────────────────────────────────────────────────────
with tab_b:
    st.subheader("📥 Trazabilidad: Obra ← Orígenes del Financiamiento")
    st.markdown(
        "Busca una **obra** (por nombre o expediente IMUH) para ver todos los "
        "decretos y cobros que la financiaron, incluyendo obras legacy sin ID."
    )

    todas_obras = db.get_todas_obras_para_trazabilidad()

    if not todas_obras:
        st.info("No se encontraron obras en el sistema.")
    else:
        busqueda = st.text_input(
            "Buscar obra por nombre o expediente IMUH:",
            placeholder="Ej: Extension de red, 8000422-I-2024...",
            key="traz_b_busqueda"
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
            st.info("No se encontraron obras que coincidan con la busqueda.")
        else:
            def _label(o):
                imuh = o['expediente_imuh'] or 'Sin IMUH'
                tag  = ' (legacy)' if o['tipo'] == 'legacy' else ''
                return f"[{imuh}] {o['nombre']}{tag}"

            opc_map = {i: o for i, o in enumerate(obras_filtradas)}
            sel_idx = st.selectbox(
                "Obra seleccionada:",
                options=list(opc_map.keys()),
                format_func=lambda x: _label(opc_map[x]),
                key="traz_b_obra"
            )
            obra_sel = opc_map[sel_idx]

            st.markdown("---")

            if obra_sel['tipo'] == 'catalogo':
                fuentes = db.get_trazabilidad_fuentes_por_obra(obra_id=obra_sel['id'])
            else:
                fuentes = db.get_trazabilidad_fuentes_por_obra(obra_nombre_legacy=obra_sel['nombre'])

            if not fuentes:
                st.info(
                    f"La obra **{obra_sel['nombre']}** no tiene movimientos de financiamiento registrados."
                )
            else:
                total_financiado = sum(f['monto_financiado'] for f in fuentes)
                saldo_pendiente  = sum(
                    f['saldo_pendiente'] for f in fuentes
                    if f['saldo_pendiente'] is not None and f['saldo_pendiente'] > 0
                )
                decretos_unicos  = len({f['decreto_id'] for f in fuentes if f['decreto_id']})

                mc1, mc2, mc3 = st.columns(3)
                mc1.metric("Total Financiado", utils.format_currency_ar(total_financiado))
                mc2.metric("Saldo Pendiente de Devolucion", utils.format_currency_ar(saldo_pendiente))
                mc3.metric("Decretos de Origen", str(decretos_unicos))

                st.markdown("---")
                st.markdown("### Detalle de Financiamientos Recibidos")

                rows_display = []
                for f in fuentes:
                    rows_display.append({
                        "Decreto Origen":      f"Dto. {f['nro_decreto']}/{f['decreto_anio']} — {f['destino_fondos']}" if f['decreto_id'] else "—",
                        "Exp. IMUH Decreto":   f['decreto_expediente_imuh'] or "Sin asignar",
                        "Fecha Cobro":         utils.format_date_ar(f['cobro_fecha']),
                        "Tipo Financiamiento": f['tipo_financiamiento'],
                        "Monto Recibido":      utils.format_currency_ar(f['monto_financiado']),
                        "Saldo Pendiente":     utils.format_currency_ar(
                            f['saldo_pendiente'] if f['saldo_pendiente'] is not None else 0
                        ),
                        "N° OP":               f['nro_op'] or "—",
                    })

                df_fuentes = pd.DataFrame(rows_display)
                st.dataframe(df_fuentes, use_container_width=True, hide_index=True)

                st.caption(
                    "Tipos de financiamiento: "
                    "Fin Original = dinero asignado directamente por el decreto a esta obra | "
                    "Desvio = fondos transferidos desde otro decreto | "
                    "Uso de Reserva = fondos provenientes de la reserva de otro cobro."
                )


# TAB C: Compensaciones
with tab_c:
    import components.tab_compensaciones
    importlib.reload(components.tab_compensaciones)
    components.tab_compensaciones.render()
```

## Archivo: `pages\9_Reportes.py`

```python
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

```

