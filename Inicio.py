import streamlit as st
import os, sys
import datetime
import pandas as pd
import plotly.express as px
import tempfile
import uuid

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
    get_reserva_usos_by_cobro, get_reserva_usos_prestamos_activos,
    get_convenios, get_solicitudes_convenio_pendientes, get_resumen_control_convenio,
    get_kpis_convenios_global
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
        temp_path = os.path.join(tempfile.gettempdir(), f"Reporte_Financiero_{datetime.date.today().strftime('%Y%m%d')}_{uuid.uuid4().hex[:8]}.pdf")
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

# 5. Convenios (Certificados de Avance y Solicitudes en trámite)
solicitudes_conv = get_solicitudes_convenio_pendientes()
for sc in solicitudes_conv:
    try:
        f_sol = datetime.datetime.strptime(sc['fecha_solicitud'], '%Y-%m-%d').date() if sc.get('fecha_solicitud') else today
        f_est = datetime.datetime.strptime(sc['fecha_estimada_cobro'], '%Y-%m-%d').date() if sc.get('fecha_estimada_cobro') else (f_sol + datetime.timedelta(days=30))
        moneda_codigo = sc.get('moneda_codigo') or 'ARS'
        
        cant_moneda = float(sc.get('cantidad_moneda') or 0.0)
        cant_cobrada = float(sc.get('cantidad_moneda_cobrada') or 0.0)
        saldo_moneda = max(0.0, cant_moneda - cant_cobrada)
        cotiz = float(sc.get('cotizacion_solicitud') or 1.0)
        monto_ars = sc.get('monto_ars_estimado') if sc.get('monto_ars_estimado') is not None else ((saldo_moneda * cotiz) if saldo_moneda > 0 else float(sc.get('monto_solicitado_ars') or 0.0))
        
        nro_conv = sc.get('nro_convenio') or sc.get('convenio_numero') or 'S/N'
        ente_fin = sc.get('ente_financiador') or 'Sin ente'
        exp_imuh = sc.get('expediente_imuh') or sc.get('obra_expediente_imuh') or "Sin asignar"
        nro_cert = sc.get('nro_certificado', '-')
        obra_nom = sc.get('obra_nombre', 'Obra')
        periodo_str = sc.get('periodo') or f_sol.strftime('%m/%Y')
        sem_cobro = utils.format_week_monday(f_est.strftime('%Y-%m-%d')) if f_est else "---"

        item = {
            "Tipo": f"Convenio ({moneda_codigo})",
            "Decreto/Referencia": f"Conv. {nro_conv} ({ente_fin})",
            "Exp. IMUH": exp_imuh,
            "Destino/Concepto": f"Cert. #{nro_cert} - {obra_nom}",
            "Periodo": periodo_str,
            "Nro. Cuota": f"Cert. #{nro_cert}",
            "Importe": monto_ars,
            "Semana estimada de cobro": sem_cobro
        }
        if today > f_est:
            atrasos.append(item)
        elif f_est.month == today.month and f_est.year == today.year:
            pendientes_mes.append(item)
    except Exception:
        continue

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

    # --- SECCIÓN: CONVENIOS MULTIOBRA Y CONTROL INDEXADO (UVIS / USD) ---
    st.markdown("---")
    st.subheader("📜 Convenios Multiobra y Control Indexado (UVIs / USD)")
    
    kpis_conv = get_kpis_convenios_global()
    convenios_vig = get_convenios()
    
    col_c1, col_c2, col_c3, col_c4 = st.columns(4)
    with col_c1:
        st.metric("Convenios Vigentes", f"{kpis_conv['total_vigentes']}", help="Convenios activos suscritos con Provincia, Nación u otros entes.")
    with col_c2:
        st.metric("En Tránsito (Pendiente Cobro)", format_currency_ar(kpis_conv['total_transito_ars']), help=f"Importe equivalente de {kpis_conv['cant_certificados_transito']} certificados emitidos pendientes de acreditación bancaria.")
    with col_c3:
        st.metric("Cobrado en Banco", format_currency_ar(kpis_conv['total_cobrado_ars']), help="Fondos de convenios efectivamente ingresados en cuenta bancaria municipal.")
    with col_c4:
        dif_tot = kpis_conv['total_diferencia_ars']
        st.metric(
            "Resultado por Indexación / Cotiz.", 
            format_currency_ar(dif_tot), 
            delta=f"{format_currency_ar(dif_tot)}",
            help="Variación neta acumulada en pesos por diferencia entre cotización al certificar y cotización al cobro bancario efectivo."
        )

    if convenios_vig:
        filas_c_dash = []
        for cv in convenios_vig:
            res_cv = get_resumen_control_convenio(cv['id'])
            m_cod = res_cv['moneda_codigo']
            m_sim = res_cv['moneda_simbolo']
            dif_cv = res_cv.get('diferencia_ajuste_ars_total', 0.0)
            dif_str = f"+{format_currency_ar(dif_cv)}" if dif_cv >= 0 else f"-{format_currency_ar(abs(dif_cv))}"
            fecha_f_str = format_date_ar(cv['fecha_firma'])
            filas_c_dash.append({
                "Convenio": f"{cv['nro_convenio']} - {cv['nombre_convenio']}",
                "Ente Financiador": cv['ente_financiador'],
                f"Cupo ({m_sim})": utils.format_moneda_custom(res_cv['pactado_moneda_total'], simbolo=m_sim, codigo=m_cod),
                f"Cupo ($ Firma {fecha_f_str})": format_currency_ar(res_cv['pactado_ars_total']),
                f"Cobrado ({m_sim})": utils.format_moneda_custom(res_cv['cobrado_moneda_total'], simbolo=m_sim, codigo=m_cod),
                "Percibido ($ ARS)": format_currency_ar(res_cv['cobrado_ars_total']),
                "Ajuste Cotiz. ($)": dif_str,
                "Cobranza (%)": f"{res_cv['porcentaje_cobranza']:.1f}%"
            })
        st.dataframe(pd.DataFrame(filas_c_dash), use_container_width=True, hide_index=True)
    else:
        st.info("No hay convenios multiobra registrados aún. Puede crearlos desde la página 'Convenios'.")

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
            if c.get('origen_tipo') == 'convenio':
                orig_label = f"Conv. {c['nro_decreto']} - {c['destino_fondos']} (IMUH: {o_imuh})"
            else:
                orig_label = f"Dto. {c['nro_decreto']}/{c['decreto_anio']} - {c['destino_fondos']} (IMUH: {o_imuh})"
            saldos_sin_dist.append({
                "Origen (Decreto / Convenio)": orig_label,
                "Fecha de cobro": format_date_ar(c['fecha']),
                "Saldo a distribuir": saldo_sd
            })
            
    if saldos_sin_dist:
        df_sd = pd.DataFrame(saldos_sin_dist)
        tot_sd = df_sd['Saldo a distribuir'].sum()
        df_sd = pd.concat([df_sd, pd.DataFrame([{"Origen (Decreto / Convenio)": "TOTAL", "Fecha de cobro": "", "Saldo a distribuir": tot_sd}])], ignore_index=True)
        df_sd['Saldo a distribuir'] = df_sd['Saldo a distribuir'].apply(lambda x: format_currency_ar(x))
        st.dataframe(
            df_sd,
            use_container_width=True,
            hide_index=True,
            column_config={
                "Origen (Decreto / Convenio)": st.column_config.TextColumn(width="large")
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
                if c.get('origen_tipo') == 'convenio':
                    orig_label = f"Conv. {c['nro_decreto']} - {c['destino_fondos']} (IMUH: {o_imuh})"
                else:
                    orig_label = f"Dto. {c['nro_decreto']}/{c['decreto_anio']} - {c['destino_fondos']} (IMUH: {o_imuh})"
                reservas.append({
                    "Origen (Decreto / Convenio)": orig_label,
                    "Fecha Cobro": format_date_ar(c['fecha']),
                    "Saldo Disponible": saldo_r
                })
                
    if reservas:
        df_r = pd.DataFrame(reservas)
        tot_r = df_r['Saldo Disponible'].sum()
        df_r = pd.concat([df_r, pd.DataFrame([{"Origen (Decreto / Convenio)": "TOTAL", "Fecha Cobro": "", "Saldo Disponible": tot_r}])], ignore_index=True)
        df_r['Saldo Disponible'] = df_r['Saldo Disponible'].apply(lambda x: format_currency_ar(x))
        st.dataframe(
            df_r, 
            use_container_width=True, 
            hide_index=True,
            column_config={
                "Origen (Decreto / Convenio)": st.column_config.TextColumn(width="large")
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

    # TABLA 4: SEGUIMIENTO DE CONVENIOS MULTIOBRA Y FONDOS EXTERNOS
    convenios_list = get_convenios()
    if convenios_list:
        st.markdown("---")
        st.subheader("📜 Convenios Multiobra y Financiamiento Externo")
        
        col_c1, col_c2, col_c3, col_c4 = st.columns(4)
        total_conv_activos = len([c for c in convenios_list if c.get('estado') in ('Activo', 'Vigente')])
        
        # Solicitudes pendientes de cobro bancario
        sols_conv_pend = get_solicitudes_convenio_pendientes()
        tot_sol_pend_ars = sum(
            sc.get('monto_ars_estimado') if sc.get('monto_ars_estimado') is not None
            else (max(0.0, float(sc.get('cantidad_moneda') or 0.0) - float(sc.get('cantidad_moneda_cobrada') or 0.0)) * float(sc.get('cotizacion_solicitud') or 1.0))
            for sc in sols_conv_pend
        )
        
        # Cobros de convenios registrados
        cobros_conv = [c for c in cobros if c.get('origen_tipo') == 'convenio']
        total_cobrado_conv_ars = sum(c['monto'] for c in cobros_conv)
        
        col_c1.metric("Convenios Activos", f"{total_conv_activos}", help="Convenios vigentes con Provincia o Nación")
        col_c2.metric("Total Convenios", f"{len(convenios_list)}")
        col_c3.metric("Certificados en Trámite", format_currency_ar(tot_sol_pend_ars), help="Monto estimado en Pesos de solicitudes presentadas pendientes de acreditación")
        col_c4.metric("Total Cobrado Convenios", format_currency_ar(total_cobrado_conv_ars), help="Total percibido en cuenta bancaria por convenios")
        
        # Tabla comparativa de control de convenios
        tabla_res_conv = []
        for cv in convenios_list:
            res_ctrl = get_resumen_control_convenio(cv['id'])
            cod_mon = cv.get('moneda_codigo') or 'ARS'
            simb_mon = cv.get('moneda_simbolo') or '$'
            dec_mon = cv.get('moneda_decimales', 2)
            
            tabla_res_conv.append({
                "Convenio": f"{cv['nro_convenio']} - {cv['nombre_convenio']}",
                "Ente Financiador": cv.get('ente_financiador', '-'),
                "Moneda / Índice": f"{cod_mon} ({simb_mon})",
                "Cupo Total Contratado": utils.format_moneda_custom(res_ctrl['pactado_moneda_total'], simb_mon, dec_mon),
                "Cobrado Efectivo": utils.format_moneda_custom(res_ctrl['cobrado_moneda_total'], simb_mon, dec_mon),
                "En Trámite": utils.format_moneda_custom(res_ctrl['saldo_en_transito_moneda'], simb_mon, dec_mon),
                "Saldo Remanente": utils.format_moneda_custom(res_ctrl['saldo_remanente_moneda'], simb_mon, dec_mon),
                "Total Cobrado ($ ARS)": format_currency_ar(res_ctrl['cobrado_ars_total']),
                "Estado": cv['estado']
            })
            
        st.dataframe(
            pd.DataFrame(tabla_res_conv),
            use_container_width=True,
            hide_index=True
        )
else:
    st.info("No hay datos suficientes para mostrar el Dashboard. Ve a la pestaña de Decretos para comenzar a cargar información.")
