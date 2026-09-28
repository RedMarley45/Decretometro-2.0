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