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
    st.warning("La restauración reemplazará la base de datos con el respaldo completo seleccionado (las 29 tablas). Antes de proceder, el sistema creará automáticamente una copia de resguardo de seguridad en 'backups/pre_restore'.")
    uploaded_bkp = st.file_uploader("Subir archivo de Backup (.db)", type=['db'])
    
    if uploaded_bkp and st.button("Restaurar ahora", type="secondary", use_container_width=True):
        db_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "decretometro.db")
        tmp_path = os.path.join(os.path.dirname(db_path), f"temp_restore_{os.getpid()}.db")
        try:
            with open(tmp_path, "wb") as f:
                f.write(uploaded_bkp.getbuffer())
                
            utils.restore_backup(db_path, tmp_path)
            st.success("Restauración completada con éxito. La base de datos y todas sus tablas han sido restauradas y actualizadas.")
        except Exception as e:
            st.error(f"Error al restaurar: {e}")
        finally:
            if os.path.exists(tmp_path):
                try:
                    os.remove(tmp_path)
                except Exception:
                    pass

st.markdown("---")
st.info("El catálogo de **Gastos de Funcionamiento** se administra ahora desde la sección **💼 Gastos de Funcionamiento** en el menú lateral.")
