# Decretómetro 2.0 (Bimonetario)

Sistema integral de gestión, trazabilidad y rendición de fondos para financiamiento, obras bimonetarias, aportes habituales y proveedores.

## 📚 Documentación Técnica y Arquitectura
* [Reporte Técnico de Incidencias y Guía Preventiva](Auditor%C3%ADas/reporte_incidencia_recuperos_v2.md): Análisis de fuga de ámbito de variables (*scope leak*) y directrices para componentes Streamlit y ViewModels.
* [Informe de Obras Bimonetarias](Auditor%C3%ADas/decretometro_2.0_informe_obras_bimonetarias_claude.md): Especificación del modelo ARS/USD y rebalanceos financieros.

## 🗂️ Estructura del Proyecto
* `Inicio.py`, `pages/`, `components/`: aplicación Streamlit (se inicia con `run_decretometro.bat`).
* `database.py`, `utils.py`, `utils_reports.py`, `pdf_generator.py`, `backend_compensaciones.py`, `trazabilidad_graph.py`: lógica de negocio, datos y reportes.
* `scripts/`: scripts de mantenimiento (`dev/`, `migrations/`) y utilitarios (`export_codebase.py`, `get_html.py`, accesos directos de Windows).
* `tests/`: pruebas. Se ejecutan con `python -m pytest tests` desde la raíz. Trabajan sobre una **copia** de `decretometro.db` guardada en `tests/.tmp/`; la base real no se modifica.
* `Auditorías/`: informes, planes y volcados de código generados por Claude y otros agentes (incluye `decretometro_codigo_completo.md`, que genera `scripts/export_codebase.py`).

