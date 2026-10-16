import os
import sqlite3
import datetime

def generate_audit_file():
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    output_path = os.path.join(base_dir, "Auditorías", "auditoria_integral_decretometro_2.0.md")
    db_path = os.path.join(base_dir, "decretometro.db")
    
    print(f"Generando archivo de auditoría en: {output_path}")
    print(f"Base de datos de origen: {db_path}")
    
    # 1. Obtener DDL y métricas de la base de datos
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    cursor.execute("SELECT version FROM schema_version WHERE id = 1")
    row_ver = cursor.fetchone()
    schema_version = row_ver[0] if row_ver else "Desconocida"
    
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")
    tables = [r[0] for r in cursor.fetchall()]
    
    table_stats = []
    for t in tables:
        try:
            cursor.execute(f'SELECT count(*) FROM "{t}"')
            cnt = cursor.fetchone()[0]
            table_stats.append((t, cnt))
        except Exception as e:
            table_stats.append((t, f"Error: {e}"))
            
    cursor.execute("SELECT type, name, tbl_name, sql FROM sqlite_master WHERE sql IS NOT NULL AND name NOT LIKE 'sqlite_%' ORDER BY type, name")
    schema_ddl_rows = cursor.fetchall()
    
    conn.close()
    
    # 2. Lista de archivos de código a consolidar
    archivos_raiz = [
        "Inicio.py",
        "database.py",
        "utils.py",
        "utils_reports.py",
        "pdf_generator.py",
        "backend_compensaciones.py",
        "trazabilidad_graph.py",
        "style.css"
    ]
    
    archivos_pages = sorted([
        f"pages/{f}" for f in os.listdir(os.path.join(base_dir, "pages"))
        if f.endswith(".py")
    ])
    
    archivos_components = sorted([
        f"components/{f}" for f in os.listdir(os.path.join(base_dir, "components"))
        if f.endswith(".py")
    ])
    
    archivos_tests = sorted([
        f"tests/{f}" for f in os.listdir(os.path.join(base_dir, "tests"))
        if f.endswith(".py")
    ])
    
    todos_los_archivos = archivos_raiz + archivos_pages + archivos_components + archivos_tests
    
    with open(output_path, "w", encoding="utf-8") as out:
        # Encabezado
        out.write("# 🏛️ AUDITORÍA INTEGRAL DE ARQUITECTURA, LÓGICA FINANCIERA Y SEGURIDAD\n")
        out.write("# PROYECTO: DECRETÓMETRO 2.0 (SISTEMA DE GESTIÓN Y TRAZABILIDAD DE FONDOS PÚBLICOS)\n\n")
        out.write("---\n\n")
        
        out.write("## 📌 METADATOS DEL DOCUMENTO\n")
        out.write(f"- **Fecha de Generación:** {datetime.datetime.now().strftime('%d/%m/%Y %H:%M:%S')}\n")
        out.write("- **Destinatario del Informe:** Martín Rodríguez\n")
        out.write("- **Perfil del Destinatario:** Contador Público (UBA), diplomado en administración de PyMEs, visión contable, financiera y de control de gestión. Posee conocimientos básicos/intermedios de programación; requiere explicaciones conceptuales en 'castellano claro', rigurosas en lo financiero y con soluciones técnicas paso a paso.\n")
        out.write("- **Lenguaje y Stack Tecnológico:** Python 3.x, Streamlit (Frontend/Fullstack Web local), SQLite embebida (`decretometro.db`), CSS personalizado (`style.css`), ReportLab (Generación de PDF).\n")
        out.write(f"- **Versión del Esquema de Base de Datos (`schema_version`):** {schema_version}\n")
        out.write(f"- **Archivos de Código Consolidados:** {len(todos_los_archivos)} archivos fuente (Runtime operativo completo + Suite de Pruebas automatizadas).\n\n")
        out.write("---\n\n")
        
        # Rol y Mandato para la IA Auditora
        out.write("## 🎯 MANDATO Y ROL PARA LA IA AUDITORA\n\n")
        out.write("Actúa como un **Arquitecto de Software Principal** y **Auditor Financiero/Forense de Sistemas de Gestión Pública**. Tu misión es realizar una **Auditoría Integral 360°** del código fuente y del esquema de datos provistos en este archivo.\n\n")
        out.write("### Principios de Comportamiento:\n")
        out.write("1. **Rigor Técnico y Financiero Brutal:** Sé directo, objetivo y sin lenguaje edulcorado. Señala los puntos ciegos, vulnerabilidades ocultas, fallas de diseño, malas prácticas y riesgos de pérdida de trazabilidad o desfasaje monetario.\n")
        out.write("2. **Traducción a 'Castellano Claro':** Para cada hallazgo técnico (ej. transaccionalidad, condiciones de carrera, normalización, inyecciones), explica en términos llanos su impacto práctico para un Contador Público responsable de rendiciones de cuentas ante organismos de contralor (Tribunal de Cuentas, Concejo Deliberante).\n")
        out.write("3. **Soluciones Concretas y Accionables:** No te limites a decir 'esto se puede mejorar'. Proporciona el código corregido (antes vs después) o el patrón de refactorización específico a aplicar.\n\n")
        out.write("---\n\n")
        
        # Contexto del Negocio y Ciclo Financiero
        out.write("## 💼 CONTEXTO DEL NEGOCIO Y CICLO FINANCIERO DEL DECRETÓMETRO 2.0\n\n")
        out.write("### Propósito Institucional:\n")
        out.write("El objetivo central de la aplicación es **llevar la trazabilidad exacta e inalterable del origen y aplicación de los fondos públicos**, garantizando que ante cualquier requerimiento de auditoría o rendición de cuentas se pueda responder fehacientemente:\n")
        out.write("- *¿De qué norma o convenio provino cada peso ingresado?*\n")
        out.write("- *¿A qué obra o gasto operativo fue asignado originalmente?*\n")
        out.write("- *¿Se realizaron desvíos transitorios (préstamos internos entre obras)? ¿Quién le debe a quién, cuánto y cómo se compensaron o devolvieron esas deudas?*\n")
        out.write("- *¿Qué facturas u órdenes de pago (OP del ERP Bejerman) cancelaron esos fondos?*\n\n")
        
        out.write("### El Ciclo Financiero en 7 Etapas:\n")
        out.write("1. **Instrumentos de Financiamiento:**\n")
        out.write("   - **Decretos Municipales:** Normas que aprueban financiamiento con un cronograma de cuotas mensuales en Pesos ($ ARS).\n")
        out.write("   - **Convenios Multiobra:** Acuerdos marco (provinciales o nacionales) que financian múltiples obras simultáneamente. Pueden estar pactados en Pesos, Dólares o **Unidades de Vivienda (UVIs - Ley Nacional 27.271)**.\n")
        out.write("2. **Cuotas y Cronogramas:** Cuotas pactadas con fecha de vencimiento y monto original (en la moneda o índice pactado).\n")
        out.write("3. **Cobros Bancarios (Desembolsos Efectivos):** Ingresos reales de dinero en cuenta bancaria. Si el cobro proviene de una cuota en UVIs o USD, se liquida a Pesos según la cotización a la fecha de cobro y se adjunta el comprobante bancario.\n")
        out.write("4. **Distribución del Cobro:** El dinero efectivamente percibido se reparte entre tres destinos:\n")
        out.write("   - **Fin Original:** Pago a contratistas de la obra asignada originalmente (asociado a Órdenes de Pago `op_bejerman`).\n")
        out.write("   - **Reserva:** Fondos que quedan transitoriamente en cuenta a la espera de afectación.\n")
        out.write("   - **Desvíos (Préstamos Internos):** Fondos prestados a otra obra con urgencia financiera, generando una acreencia y una deuda contable interna entre obras.\n")
        out.write("5. **Compensación y Recupero de Desvíos:** Mecanismo donde se registran las devoluciones de préstamos entre obras (incluyendo compensaciones cruzadas de deudas mutuas).\n")
        out.write("6. **Aportes Habituales:** Fondos mensuales para Funcionamiento, Sueldos y SAC (Sueldo Anual Complementario / Aguinaldos).\n")
        out.write("7. **Rendición y Trazabilidad:** Visualización bidireccional mediante grafos y tablas (Decreto/Convenio ➔ Cobros ➔ Destinos / OP; y a la inversa, Obra ➔ Fuentes de Financiamiento) y generación de reportes ejecutivos en PDF.\n\n")
        out.write("---\n\n")
        
        # Puntos Críticos y Focos de Atención
        out.write("## 🔍 PUNTOS CRÍTICOS Y FOCOS DE ATENCIÓN PRIORITARIOS PARA LA AUDITORÍA\n\n")
        out.write("La IA auditora debe evaluar minuciosamente los siguientes 6 aspectos neurálgicos:\n\n")
        out.write("### 1. Monolito en `database.py` (>236 KB, más de 5.000 líneas de código)\n")
        out.write("- **Problema:** Toda la persistencia, DDL, 48 versiones de migraciones acumuladas secuencialmente, consultas complejas, cálculos de negocio y formateos están concentrados en un único archivo.\n")
        out.write("- **Puntos a auditar:** ¿Cómo estructurar un plan de desacoplamiento modular sin romper la compatibilidad? ¿Qué responsabilidades deben extraerse primero (ej. repositorios por entidad, gestor de conexiones, migraciones independientes)?\n\n")
        
        out.write("### 2. Concurrencia y Transaccionalidad en SQLite bajo el ciclo de vida de Streamlit\n")
        out.write("- **Problema:** Streamlit reejecuta el script completo ante cada interacción del usuario (`st.rerun()`). Si múltiples pestañas están abiertas o hay operaciones compuestas (ej. distribuir un cobro en Fin Original, Reserva y 3 Desvíos simultáneos), ¿están protegidas bajo una única transacción atómica `BEGIN IMMEDIATE` / `COMMIT` / `ROLLBACK`?\n")
        out.write("- **Riesgo:** Inconsistencias de datos a medio guardar si un paso intermedio falla o la base queda bloqueada (`sqlite3.OperationalError: database is locked`). ¿Está activo `PRAGMA foreign_keys = ON;` en todas y cada una de las conexiones creadas por `db_session()`?\n\n")
        
        out.write("### 3. Precisión Numérica y Valuación Bimonetaria / Multimoneda (UVIs / USD)\n")
        out.write("- **Problema:** Las UVIs se actualizan diariamente según el Coeficiente de Estabilización de Referencia (CER). En SQLite, las columnas numéricas suelen ser `REAL` (coma flotante IEEE 754 de 64 bits).\n")
        out.write("- **Puntos a auditar:** ¿Existen riesgos de pérdida de precisión por redondeo en operaciones repetidas? ¿Cómo se determina la fecha de cotización aplicable al transformar cuotas pactadas en UVIs a cobros en Pesos y pagos a contratistas? ¿Qué pasa ante cotizaciones faltantes en feriados o fines de semana?\n\n")
        
        out.write("### 4. Trazabilidad de Compensaciones y Desvíos Cruzados\n")
        out.write("- **Problema:** Cuando la Obra A le presta a la Obra B, y luego B le transfiere a C o A compensa saldos con B.\n")
        out.write("- **Puntos a auditar:** ¿Puede una compensación anular un desvío que ya fue recuperado? ¿Se puede desviar más dinero del disponible en el cobro? ¿Existe riesgo de deudas circulares sin detectar?\n\n")
        
        out.write("### 5. Robustez de la Suite de Tests (`tests/`)\n")
        out.write("- **Puntos a auditar:** ¿Qué cobertura real tienen los casos límite (edge cases)? ¿Se prueban fallas simuladas de transacciones (rollback)? ¿Se verifican saldos negativos o concurrencia?\n\n")
        
        out.write("### 6. Seguridad, Inyecciones SQL y Manejo de Rutas\n")
        out.write("- **Puntos a auditar:** ¿Existen interpolaciones directas de cadenas (f-strings) en sentencias SQL dinámicas? ¿Cómo se gestionan las subidas de archivos comprobantes y rutas en Windows?\n\n")
        out.write("---\n\n")
        
        # Formato de Salida Exigido a la IA
        out.write("## 📋 FORMATO REQUERIDO PARA EL INFORME DE LA IA AUDITORA\n\n")
        out.write("El informe que elabores como respuesta debe estructurarse estrictamente bajo las siguientes tres secciones:\n\n")
        out.write("### Sección 1: Resumen Ejecutivo y Diagnóstico General\n")
        out.write("- Puntuación de madurez del sistema (1 a 10) en Arquitectura, Concurrencia/Seguridad y Precisión Contable.\n")
        out.write("- Diagnóstico cualitativo general de fortalezas y debilidades de mayor impacto.\n\n")
        
        out.write("### Sección 2: Matriz de Hallazgos y Vulnerabilidades (Clasificada por Severidad)\n")
        out.write("Clasifica cada hallazgo bajo una de las 4 categorías:\n")
        out.write("- 🔴 **Severidad Crítica (P0):** Riesgo de pérdida o corrupción de datos financieros, inconsistencias contables graves, bloqueos fatales o fallas de integridad referencial.\n")
        out.write("- 🟠 **Severidad Alta (P1):** Ausencia de transaccionalidad atómica en operaciones multi-tabla, desfasajes monetarios en UVIs, falta de constraints estrictos.\n")
        out.write("- 🟡 **Severidad Media (P2):** Monolito y deuda técnica en `database.py`, duplicación de lógica de negocio, ausencia de tipado y validaciones de bordes.\n")
        out.write("- 🟢 **Severidad Baja (P3):** Mejoras de estilo, optimización de queries SQL no críticas, limpieza de código muerto y documentación.\n\n")
        out.write("Para **cada hallazgo**, debes completar la siguiente ficha estandarizada:\n")
        out.write("```markdown\n")
        out.write("#### [ID_HALLAZGO] Título descriptivo del hallazgo\n")
        out.write("- **Severidad:** [Crítica / Alta / Media / Baja]\n")
        out.write("- **Categoría:** [Arquitectura / Concurrencia y Transacciones / Lógica Financiera y UVIs / Seguridad / Testing]\n")
        out.write("- **Ubicación:** Archivo(s), función(es) y líneas afectadas.\n")
        out.write("- **Impacto Contable / Financiero:** Explicación en castellano claro de qué perjuicio o inconsistencia produce esto en las cuentas públicas o en la operación diaria.\n")
        out.write("- **Diagnóstico Técnico:** Explicación técnica de la causa raíz en el código o base de datos.\n")
        out.write("- **Código Problemático Actual:** Fragmento de código extraído del volcado.\n")
        out.write("- **Solución Propuesta y Código Corregido:** Implementación recomendada lista para ser aplicada.\n")
        out.write("```\n\n")
        
        out.write("### Sección 3: Hoja de Ruta Priorizada (Plan de Acción)\n")
        out.write("- **Fase 1: Quick Wins Inmediatos (1 a 3 días):** Parcheos de seguridad, atomicidad en transacciones y correcciones de alta rentabilidad/bajo esfuerzo.\n")
        out.write("- **Fase 2: Blindaje Financiero y de Datos (1 a 2 semanas):** Validaciones contra sobre-imputación, cálculo preciso de UVIs y refuerzo de claves foráneas.\n")
        out.write("- **Fase 3: Refactorización Arquitectónica Estructural (Mediano plazo):** Plan paso a paso para modularizar `database.py` sin interrumpir la operación ni romper la base de datos.\n\n")
        out.write("---\n\n")
        
        # Diagnóstico del Estado Real de la Base de Datos SQLite
        out.write("## 🗄️ ESTADO REAL DE LA BASE DE DATOS SQLITE (`decretometro.db`)\n\n")
        out.write(f"- **Versión del Esquema (`schema_version`):** `{schema_version}`\n")
        out.write(f"- **Total de Tablas:** `{len(tables)}`\n\n")
        
        out.write("### Estadísticas de Registros por Tabla:\n")
        out.write("| Tabla | Cantidad de Registros | Descripción Funcional |\n")
        out.write("| :--- | :--- | :--- |\n")
        
        descripciones = {
            "aportes_funcionamiento": "Aportes mensuales municipales para gastos corrientes de funcionamiento",
            "aportes_sac": "Aportes percibidos para Sueldo Anual Complementario (Aguinaldos)",
            "aportes_sueldo": "Aportes percibidos para masa salarial mensual",
            "cobro_desvios": "Préstamos transitorios de fondos entre obras o destinos operativos",
            "cobro_desvios_recuperos": "Devoluciones o recuperos aplicados a desvíos de fondos",
            "cobro_distribuciones": "Distribución general de cobros entre Fin Original, Reserva y Desvíos",
            "cobro_fin_original_usos": "Afectación de fondos originales al pago de Órdenes de Pago (OP Bejerman)",
            "cobro_reserva_usos": "Aplicación posterior de fondos guardados en reserva",
            "cobro_reserva_usos_recuperos": "Recuperos de fondos aplicados desde reservas",
            "cobros": "Ingresos efectivos de fondos bancarios asociados a cuotas",
            "convenio_obras": "Vinculación N a M entre Convenios de Financiamiento y Obras públicas",
            "convenio_solicitudes": "Vinculación entre solicitudes de fondos y convenios marco",
            "convenios": "Convenios marco multiobra (en ARS, USD o UVIs)",
            "cuotas": "Cronograma de vencimientos y cuotas programadas por decreto o convenio",
            "decretos": "Decretos municipales de financiamiento",
            "decretos_obras": "Relación entre decretos y obras financiadas",
            "gastos_funcionamiento": "Egresos y pagos operativos de funcionamiento",
            "monedas_indices": "Catálogo de monedas e índices de actualización diaria (ARS, USD, UVI)",
            "obra_adicionales": "Adicionales de obra o ampliaciones presupuestarias",
            "obras": "Padrón general de obras públicas del municipio",
            "op_bejerman": "Órdenes de Pago registradas y sincronizadas con el ERP contable Bejerman",
            "pagos_fondos_propios": "Pagos a obras ejecutados directamente con recursos propios municipales",
            "prestamos_internos": "Préstamos directos entre fondos",
            "proveedores_funcionamiento": "Padrón de proveedores de servicios y gastos de funcionamiento",
            "proveedores_obras": "Padrón de contratistas y proveedores de obras públicas",
            "recuperos_fondos_propios": "Devoluciones hacia la cuenta de fondos propios",
            "recuperos_internos": "Recuperos internos generales",
            "schema_version": "Control de versión de migraciones aplicadas",
            "solicitudes_financiamiento": "Expedientes de solicitudes previas a la promulgación del decreto/convenio"
        }
        
        for t, cnt in table_stats:
            desc = descripciones.get(t, "Tabla del sistema")
            out.write(f"| `{t}` | {cnt} | {desc} |\n")
        out.write("\n")
        
        out.write("### Definiciones de Estructura DDL (`sqlite_master`):\n")
        out.write("```sql\n")
        for tipo, name, tbl_name, sql in schema_ddl_rows:
            out.write(f"-- {tipo.upper()}: {name} (Tabla: {tbl_name})\n")
            out.write(f"{sql.strip()};\n\n")
        out.write("```\n\n")
        out.write("---\n\n")
        
        # Volcado de Código Consolidado
        out.write("## 💻 VOLCADO COMPLETO DEL CÓDIGO FUENTE CONSOLIDADO\n\n")
        out.write("A continuación se presenta el código fuente íntegro de todos los módulos del sistema y de su batería de pruebas automatizadas.\n\n")
        
        archivos_procesados = 0
        for rel_path in todos_los_archivos:
            abs_path = os.path.join(base_dir, rel_path)
            if not os.path.exists(abs_path):
                print(f"Advertencia: Archivo no encontrado: {abs_path}")
                continue
                
            out.write(f"### Archivo: `{rel_path}`\n\n")
            ext = os.path.splitext(rel_path)[1].lower()
            lang = "python" if ext == ".py" else ("css" if ext == ".css" else "text")
            
            out.write(f"```{lang}\n")
            try:
                with open(abs_path, "r", encoding="utf-8") as f:
                    contenido = f.read()
                    out.write(contenido)
                    if not contenido.endswith("\n"):
                        out.write("\n")
            except Exception as e:
                out.write(f"# Error al leer archivo: {e}\n")
            out.write("```\n\n")
            out.write("---\n\n")
            archivos_procesados += 1
            
    tamano_kb = os.path.getsize(output_path) / 1024
    print(f"Exportación completada con éxito:")
    print(f"- Archivos procesados: {archivos_procesados}")
    print(f"- Tamaño generado: {tamano_kb:.2f} KB ({tamano_kb/1024:.2f} MB)")

if __name__ == "__main__":
    generate_audit_file()
