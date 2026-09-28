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
