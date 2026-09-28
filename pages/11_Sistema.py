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
