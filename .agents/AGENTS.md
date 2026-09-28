# Reglas e Instrucciones del Proyecto: Decretometro

## 👤 Perfil del Proyecto
* **Nombre:** Decretometro
* **Propósito:** Sistema de gestión, seguimiento y trazabilidad de solicitudes de financiamiento, obras, aportes habituales y proveedores. El fin último es saber en qué utilizamos los fondos, a fin de poder realizar las rendiciones correspondientes a los organismos de contralor.

---

## 🛠️ Tecnologías y Librerías
* **Lenguaje:** Python 3.x
* **Frontend / Framework:** Streamlit
* **Base de Datos:** SQLite (`decretometro.db`)
* **Estilos:** Vanilla CSS personalizado cargado mediante `style.css`

---

## 🏗️ Arquitectura y Organización del Código
* **Acceso a Datos:** Toda la interacción, consultas y operaciones SQL con la base de datos se centralizan en `database.py`.
* **Páginas:** Cada módulo principal de la aplicación reside en la carpeta `pages/` (ej. `2_Obras.py`, `3_Solicitudes_de_financiamiento.py`, etc.).
* **Componentes UI:** Las pestañas y componentes reutilizables de la interfaz residen en `components/` (ej. `tab_estado.py`, `tab_distribuir.py`, etc.).
* **Reportes y Utilidades:** Generación de PDF y funciones auxiliares en `pdf_generator.py` y `utils.py`.

---

## ⚠️ Reglas de Desarrollo
1. **Preservar Esquema de BD:** Consultar antes de realizar cambios estructurales o alterar tablas en `decretometro.db`.
2. **Modularidad:** Mantener la separación limpia entre lógica de base de datos (`database.py`), interfaz de usuario (`pages/` y `components/`) y reportes.
3. **Estilos:** Mantener la coherencia estética de Streamlit utilizando `style.css`.
