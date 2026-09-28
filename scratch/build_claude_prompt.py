import os
import sqlite3

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTPUT_FILE = os.path.join(BASE_DIR, "prompt_para_claude.md")
DB_PATH = os.path.join(BASE_DIR, "decretometro.db")

PROMPT_HEADER = """# SOLICITUD DE ASESORAMIENTO ARQUITECTÓNICO Y FINANCIERO: EVOLUCIÓN A "DECRETÓMETRO 2.0"
# (SISTEMA MULTIMONEDA, ÍNDICES DIARIOS UVI Y GESTIÓN DE CONVENIOS MULTIOBRA)

---

## 👤 PERFIL DEL USUARIO Y DESTINATARIO DEL ANÁLISIS
* **Nombre:** Martín Rodríguez
* **Formación y Perfil:** Contador Público (Universidad de Buenos Aires - UBA), diplomado en administración, con visión estratégica, financiera y de control de gestión.
* **Rol:** Responsable de la gestión financiera, trazabilidad de fondos públicos y rendiciones de cuentas ante organismos de contralor (Tribunal de Cuentas, Concejo Deliberante, etc.).
* **Nivel técnico de desarrollo:** Conocimientos básicos/intermedios de programación. Se requiere un lenguaje riguroso en lo contable y financiero, pero en "castellano claro" y didáctico en lo técnico, con explicaciones paso a paso de los conceptos de desarrollo y arquitectura.

---

## 🏛️ CONTEXTO DEL SISTEMA: "DECRETÓMETRO 1.0"
"Decretómetro" es una aplicación web local desarrollada en **Python 3.x**, con frontend en **Streamlit** y base de datos relacional embebida en **SQLite** (`decretometro.db`). Su diseño estilístico utiliza un CSS personalizado (`style.css`).

### Propósito Central del Sistema:
Llevar la trazabilidad exacta de los fondos públicos afectados a obras y funcionamiento:
1. **Solicitudes de Financiamiento:** Pedidos formales para financiar obras públicas.
2. **Decretos:** Normas que aprueban el financiamiento, especificando montos y un cronograma de cuotas mensuales.
3. **Cobros Bancarios:** Desembolsos efectivos ingresados al banco contra cuotas de decretos.
4. **Distribución de Fondos:** Cada cobro se distribuye entre:
   - *Fin Original:* Pagos a la obra de destino original (vinculados a Órdenes de Pago `op_bejerman`).
   - *Reserva:* Fondos disponibles temporalmente en cuenta.
   - *Desvíos / Préstamos Internos:* Fondos prestados transitoriamente a otras obras o urgencias.
5. **Aportes Habituales:** Aportes mensuales del Municipio para Funcionamiento, Sueldos y SAC (Aguinaldos).
6. **Rendición de Cuentas:** Módulos de Trazabilidad bidireccional (Decreto → Destinos, y Obra ← Orígenes), compensación de deudas cruzadas y generación de reportes ejecutivos en PDF con ReportLab.

### Estado Actual:
El sistema se encuentra **100% funcional y en producción**. La base de datos histórica cuenta actualmente con:
- 19 decretos aprobados
- 69 cuotas programadas
- 55 cobros bancarios registrados
- 51 distribuciones de cobro
- 118 desvíos de fondos entre obras
- 52 obras en catálogo
- 30 vínculos decretos-obras
- 180 órdenes de pago de Bejerman imputadas
- Versión actual del esquema (`schema_version`): 35

---

## 🚀 LA NUEVA VISIÓN: "DECRETÓMETRO 2.0"
Se busca dar un salto cualitativo en la madurez financiera del sistema para adaptarse a la realidad contractual y económica actual, incorporando tres grandes pilares:

### 1. Sistema Multimoneda y Multíndice Flexible (UVIs, USD, etc.)
- **Catálogo de Monedas e Índices:** Una sección/interfaz donde el usuario pueda dar de alta no sólo monedas tradicionales (ARS, USD), sino también **índices financieros o de vivienda**, en particular las **Unidades de Vivienda (UVIs)** (creadas por la Ley Nacional 27.271 de la República Argentina, cuyo valor en pesos se actualiza diariamente según el Coeficiente de Estabilización de Referencia - CER publicado por el Banco Central de la República Argentina - BCRA).
- **Valuación y Cotizaciones Diarias:** Posibilidad de registrar o cargar el valor diario en pesos ($ ARS) para cada moneda o índice (ej: fecha, valor de la UVI, tipo de cambio USD oficial/BNA).

### 2. Módulo de Convenios Multiobra
- **Evolución del Instrumento Legal:** En la administración pública, las obras no siempre se financian mediante decretos municipales aislados; frecuentemente se firman **Convenios de Financiamiento o de Ejecución** (con Nación, Provincia u otros entes).
- **Relación Multiobra:** Un único Convenio suele contemplar y financiar **múltiples obras** a la vez (relación 1 a N o N a M).
- **Presupuesto y Desembolsos:** El Convenio se pacta con un monto total que puede estar expresado en una moneda o índice específico (por ejemplo: `1.500.000 UVIs` o `USD 500.000`), estructurado en un cronograma de desembolsos / cuotas / certificados de avance de obra expresados en ese índice o moneda.

### 3. Cobros (Desembolsos) contra Convenios y Liquidación a Obras
- **Cobros contra Convenios:** Los desembolsos bancarios que ingresan a la cuenta institucional se registran e imputan **contra las cuotas del Convenio**.
- **Mecánica de Conversión:** Si una cuota del convenio estaba prevista en `100.000 UVIs`, al momento del cobro efectivo se liquida en Pesos ($ ARS) según el valor de la UVI a la fecha de cobro (o según la cotización pactada en el desembolso bancario).
- **Distribución hacia las Obras del Convenio:** El importe percibido se distribuye entre las obras que integran el convenio, manteniendo la trazabilidad posterior (fin original, reserva, desvíos y pagos a contratistas con OP Bejerman).

### 4. REQUISITO OBLIGATORIO: Retrocompatibilidad e Integración Histórica
- La base de datos existente (`decretometro.db`) contiene información real y crítica en pesos nominales bajo el esquema de decretos.
- **La nueva versión DEBE ser 100% retrocompatible y capaz de integrar la información histórica.** No se puede perder ni distorsionar ningún registro preexistente.
- Los decretos históricos deben convivir pacíficamente con los nuevos convenios (o representarse conceptualmente como una variante de financiamiento sin alterar sus cálculos ni IDs).

---

## 🎯 QUÉ SE TE SOLICITA EN ESTE ANÁLISIS (CONSIGNA PARA CLAUDE)
Como Arquitecto de Software y Consultor Financiero Senior, te pedimos un informe exhaustivo, crítico y estructurado que responda a los siguientes puntos:

### 1. Diagnóstico del Estado Actual del Código y Arquitectura
- Analizá el código consolidado adjunto. Identificá dónde se encuentran los acoplamientos más fuertes a la entidad `decretos` y a la moneda implícita (pesos).
- Evaluá los puntos críticos de falla o riesgo si se introdujeran monedas/índices sin una refactorización adecuada.

### 2. Propuesta de Modelo de Datos Relacional (SQLite)
- **Tablas para Monedas e Índices:** Proponé la estructura DDL para gestionar monedas/índices y sus cotizaciones diarias (`monedas_indices`, `cotizaciones_diarias`).
- **Modelado de Convenios y Decretos:**
  - *Dilema arquitectónico:* ¿Conviene crear una tabla `convenios` paralela a `decretos`, o conviene una entidad común de mayor jerarquía (ej. `instrumentos_financiamiento` o `fuentes_financiamiento`), o asociar Decretos a Convenios (dado que en derecho público un Convenio suele ser ratificado por Decreto)?
  - Explicá los pros y contras de cada alternativa considerando la compatibilidad con los 19 decretos y 69 cuotas históricas.
- **Evolución de Cuotas, Cobros y Distribuciones:**
  - Cómo deben modificarse las tablas `cuotas`, `cobros` y `cobro_distribuciones` para registrar la moneda/índice de origen, cantidad pactada, cotización aplicada y monto liquidado efectivo en pesos.
- **Estrategia de Migración no destructiva:** Plan de sentencias `ALTER TABLE` o migraciones ordenadas manteniendo íntegra la historia existente (`schema_version >= 36`).

### 3. Mecánica Financiera, Conversión de Índices (UVIs) y Trazabilidad
- Diseñá el flujo contable-financiero completo:
  1. Definición del Convenio en UVIs (con N obras asignadas y porcentajes/montos por obra).
  2. Cronograma de Cuotas en UVIs.
  3. Registro del Cobro (liquidación en ARS según cotización de la UVI).
  4. Distribución del cobro a las obras del convenio.
  5. Imputación de pagos a contratistas (OP Bejerman) y desvíos transitorios.
- ¿Cómo deben tratarse las diferencias de valuación o descalces entre el presupuesto de obra pactado en UVIs y la ejecución real en pesos?
- ¿Cómo impacta esto en el cálculo de saldos y en la pantalla de "Compensaciones de Saldos Cruzados"?

### 4. Propuesta de Interfaz de Usuario (Streamlit)
- ¿Qué nuevas páginas o pestañas recomendarías crear en `pages/` y `components/`?
- ¿Cómo diseñar la experiencia del usuario (UX) para que la carga de cotizaciones, la vinculación de obras a convenios y la liquidación de cobros en UVIs sea simple, intuitiva y a prueba de errores operativos?

### 5. Roadmap / Plan de Acción Priorizado
- Un plan de implementación por etapas (Fase 1: Base de Datos y Catálogos; Fase 2: Convenios y Obras; Fase 3: Cobros y Distribución; Fase 4: Reportes y Trazabilidad).
- Indicaciones claras sobre qué validar en cada fase antes de avanzar a la siguiente.

---

A continuación se adjunta el **código fuente completo y consolidado** de la aplicación Decretómetro para tu análisis integral.
"""

def get_db_summary():
    if not os.path.exists(DB_PATH):
        return "Base de datos no encontrada."
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name;")
    tables = [r[0] for r in cur.fetchall() if not r[0].startswith('sqlite')]
    summary_lines = ["\n### Resumen Actual de Tablas y Registros en decretometro.db:"]
    summary_lines.append("| Tabla | Registros |")
    summary_lines.append("|---|---|")
    for t in tables:
        count = cur.execute(f"SELECT count(*) FROM {t}").fetchone()[0]
        summary_lines.append(f"| `{t}` | {count} |")
    
    # Version
    v = cur.execute("SELECT version FROM schema_version WHERE id=1").fetchone()
    summary_lines.append(f"\n*Versión del esquema actual:* `{v[0] if v else 'N/A'}`\n")
    conn.close()
    return "\n".join(summary_lines)

def build_prompt():
    print("Construyendo prompt consolidado para Claude...")
    
    target_files = [
        ('AGENTS.md', 'markdown'),
        ('database.py', 'python'),
        ('Inicio.py', 'python'),
        ('utils.py', 'python'),
        ('utils_reports.py', 'python'),
        ('pdf_generator.py', 'python'),
        ('backend_compensaciones.py', 'python'),
        ('trazabilidad_graph.py', 'python'),
        ('style.css', 'css')
    ]
    
    pages_dir = os.path.join(BASE_DIR, 'pages')
    if os.path.exists(pages_dir):
        for f in sorted(os.listdir(pages_dir)):
            if f.endswith('.py'):
                target_files.append((os.path.join('pages', f), 'python'))
                
    comp_dir = os.path.join(BASE_DIR, 'components')
    if os.path.exists(comp_dir):
        for f in sorted(os.listdir(comp_dir)):
            if f.endswith('.py'):
                target_files.append((os.path.join('components', f), 'python'))
                
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as out:
        out.write(PROMPT_HEADER)
        out.write("\n\n---\n\n")
        out.write("## 📊 ESTADO ACTUAL DE LA BASE DE DATOS LOCAL\n")
        out.write(get_db_summary())
        out.write("\n\n---\n\n")
        out.write("## 💻 CÓDIGO FUENTE CONSOLIDADO DEL SISTEMA DECRETÓMETRO\n\n")
        
        for rel_path, lang in target_files:
            abs_path = os.path.join(BASE_DIR, rel_path)
            if not os.path.exists(abs_path):
                continue
            
            out.write(f"### Archivo: `{rel_path}`\n\n")
            out.write(f"```{lang}\n")
            try:
                with open(abs_path, 'r', encoding='utf-8') as f:
                    out.write(f.read())
            except Exception as e:
                out.write(f"# Error al leer archivo: {e}\n")
            out.write("\n```\n\n")
            print(f"  + Agregado: {rel_path}")
            
    print(f"\n¡Listo! Archivo generado con éxito en: {OUTPUT_FILE}")
    size_mb = os.path.getsize(OUTPUT_FILE) / (1024 * 1024)
    print(f"Tamaño total del archivo: {size_mb:.2f} MB")

if __name__ == '__main__':
    build_prompt()
