# Decretómetro 2.0 — Plan de Implementación Definitivo: Catálogo de Obras Bimonetarias y Control de Pagos

**Autor:** Martín Rodríguez (Contador Público - UBA)  
**Sistema:** Decretómetro 2.0 (Streamlit + SQLite + Python)  
**Auditoría y Revisión:** Claude (Auditor Externo) & Codex  
**Fecha:** Septiembre 2026  
**Documento:** Especificación Técnica y Plan de Implementación Definitivo (Versión Consensuada)  
**Estado de Base de Datos:** Schema Version 47 Activa ➔ **Próxima: Migración 48**

---

## 🏛️ 1. CONTEXTO, MOTIVACIÓN Y RECONCILIACIÓN DE VERSIONES

### 1.1 Antecedentes y Necesidad Operativa
En la etapa previa de desarrollo del **Decretómetro 2.0**, se aprobó formalmente con **Dictamen CONFORME de Auditoría** el subsistema de financiamiento bimonetario (Convenios Multiobra en UVIs/USD/Pesos, cobros bancarios, resolución de compensaciones cruzadas y bandeja downstream unificada).

En la gestión cotidiana de obras del **Instituto Municipal de Urbanismo y Hábitat (IMUH)** se presenta un escenario contractual complementario:
* **Múltiples contratos de obra se licitan, adjudican y firman en UVIs** (Ley 27.271, índice basado en el ICC publicado por el BCRA).
* Actualmente, en el Catálogo de Obras (`pages/2_Obras.py`), el campo `monto_contrato` es un escalar estático en Pesos ($ ARS). A medida que las obras se ejecutan en un contexto inflacionario y la cotización de la UVI aumenta, los desembolsos acumulados en pesos superan el importe inicial pactado a la fecha de licitación.
* **El Punto Ciego Contable:** Los módulos de pagos (`tab_distribuir.py` y `pages/4_Pagos_Fondos_Propios.py`) disparan falsas alertas de *"sobrepago de contrato"*, entorpeciendo la gestión cuando en realidad la obra se encuentra dentro del cupo físico de UVIs legalmente contratado.

### 1.2 Reconciliación de Versiones del Código y Base de Datos
Para disipar cualquier duda sobre la línea de base técnica:
* La base de datos de producción `decretometro.db` se encuentra verificada y activa en la **versión 47** del esquema relacional (con el `CONSTRAINT check_origen_exclusivo` verificado y 55 cobros históricos intactos).
* El archivo `database.py` contiene todas las migraciones del 1 al 47 operativas.
* La siguiente migración a aplicar es **unívocamente la Migración 48**.

---

## 🎯 2. REGLAS DE NEGOCIO Y CONSENSOS DE DISEÑO DEFINITIVOS

1. **Pagos Bancarios Exclusivamente en Pesos ($ ARS):**
   * Las transferencias bancarias y Órdenes de Pago (OP de Bejerman) se cancelan en moneda de curso legal ($ ARS). La UVI es la **unidad de cuenta contractual y de avance físico**.
2. **Fuentes de Financiamiento Abiertas y Mixtas:**
   * Una obra en UVIs puede financiarse mediante Convenios en UVIs, Decretos provinciales en pesos, Fondos Propios municipales en pesos o esquemas mixtos.
3. **Fuente Única de la Verdad en Pagos (Derivación Estricta):**
   * **Pagos desde Cobros de Convenio (Fin Original):** Si el pago se imputa a una obra en UVIs y proviene de un cobro con certificado de convenio, la cantidad de UVIs amortizadas y la cotización **se derivan automáticamente** de la solicitud/certificado. El operador no tipea cotizaciones en esta pantalla, erradicando discrepancias numéricas entre la contabilidad del convenio y la de la obra.
   * **Pagos desde Fondos Propios (sin certificado de convenio):** El operador ingresa el importe en pesos de la OP y la cotización de la UVI a la fecha de pago para computar las UVIs amortizadas (`UVIs = $ ARS / Cotización`).
4. **Adicionales de Obra con Cotizaciones Propias (Tabla `obra_adicionales`):**
   * En lugar de sobrescribir el contrato base, cada ampliación contractual (adicional en UVIs) se registra como una fila independiente en `obra_adicionales`, preservando su número de resolución, fecha y cotización base de ese momento. Esto evita subvaluar el costo histórico de la obra o distorsionar el cálculo de la indexación.
5. **Método Contable de Atribución e Indexación: FIFO por Tramo (Resuelve Hallazgo de Claude):**
   * Los pagos en UVIs se imputan cronológicamente por tramos:
     * **1° Tramo:** Contrato Base (a su cotización de licitación / firma).
     * **2° Tramo en adelante:** Adicionales de obra en el orden cronológico de sus resoluciones (a su cotización de adjudicación respectiva).
   * La fórmula contable de cálculo es tramo por tramo:
     $$\text{Resultado por Indexación} = \text{Monto Pagado (\$ ARS)} - \sum (\text{UVIs Amortizadas Tramo } i \times \text{Cotización Base Tramo } i)$$
   * Esto garantiza exactitud matemática absoluta y concordancia plena con el caso de prueba de la suite.
6. **Guardas de Sobrepago Unificadas con Motivo Obligatorio:**
   * Si un pago supera el contrato (sea en UVIs o en pesos), el sistema muestra una advertencia bloqueante pero permite registrar la operación si el usuario marca el tilde `"Confirmo sobrepago"` e ingresa obligatoriamente un **motivo/justificación legal**, el cual queda registrado en la base de datos como pista de auditoría.
7. **Rótulo Oficial:**
   * La métrica de variación de valor se denomina oficialmente: **`Resultado por Indexación`**.
8. **Marco Legal y Técnico de Índices:**
   * La **UVI** se rige por la **Ley Nacional 27.271** (vinculada al Índice del Costo de la Construcción - ICC y publicada por el BCRA). Se mantiene diferenciada de la UVA (vinculada al CER).

---

## 🗄️ 3. ESQUEMA DE BASE DE DATOS PROPUESTO (MIGRACIÓN 48)

```sql
-- =============================================================================
-- MIGRACIÓN 48: SOPORTE BIMONETARIO EN CATÁLOGO DE OBRAS Y CONTROL DE PAGOS
-- =============================================================================

-- 1. Ampliación de la tabla 'obras'
ALTER TABLE obras ADD COLUMN moneda_id INTEGER DEFAULT 1 REFERENCES monedas_indices(id);
ALTER TABLE obras ADD COLUMN monto_contrato_moneda REAL DEFAULT 0.0;
ALTER TABLE obras ADD COLUMN cotizacion_base_contrato REAL DEFAULT 1.0;
ALTER TABLE obras ADD COLUMN fecha_contrato DATE;
ALTER TABLE obras ADD COLUMN notas_contrato TEXT;

-- 2. Tabla para Adicionales / Ampliaciones de Obra
CREATE TABLE IF NOT EXISTS obra_adicionales (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    obra_id INTEGER NOT NULL REFERENCES obras(id) ON DELETE CASCADE,
    nro_resolucion TEXT NOT NULL,
    fecha DATE NOT NULL,
    cantidad_moneda REAL NOT NULL,
    cotizacion_base REAL NOT NULL DEFAULT 1.0,
    monto_equivalente_ars REAL NOT NULL,
    motivo TEXT
);

-- 3. Ampliación de tablas de pagos a contratistas para registrar amortización de UVIs
-- A) Pagos de Fin Original desde Cobros
ALTER TABLE cobro_fin_original_usos ADD COLUMN cantidad_moneda_amortizada REAL;
ALTER TABLE cobro_fin_original_usos ADD COLUMN cotizacion_pago REAL DEFAULT 1.0;
ALTER TABLE cobro_fin_original_usos ADD COLUMN convenio_solicitud_id INTEGER REFERENCES convenio_solicitudes(id) ON DELETE SET NULL;
ALTER TABLE cobro_fin_original_usos ADD COLUMN motivo_sobrepago TEXT;

-- B) Pagos directos con Fondos Propios
ALTER TABLE pagos_fondos_propios ADD COLUMN cantidad_moneda_amortizada REAL;
ALTER TABLE pagos_fondos_propios ADD COLUMN cotizacion_pago REAL DEFAULT 1.0;
ALTER TABLE pagos_fondos_propios ADD COLUMN convenio_solicitud_id INTEGER REFERENCES convenio_solicitudes(id) ON DELETE SET NULL;
ALTER TABLE pagos_fondos_propios ADD COLUMN motivo_sobrepago TEXT;

-- 4. Sincronización inmutable de registros históricos:
-- Las 52 obras preexistentes quedan tipificadas en Pesos (moneda_id = 1),
-- garantizando que monto_contrato_moneda = monto_contrato y cotizacion_base = 1.0.
UPDATE obras 
SET moneda_id = 1,
    monto_contrato_moneda = COALESCE(monto_contrato, 0.0),
    cotizacion_base_contrato = 1.0
WHERE moneda_id IS NULL OR moneda_id = 1;
```

---

## ⚙️ 4. PLAN DE IMPLEMENTACIÓN POR FASES DETALLADO

---

### 🔹 FASE 1: Base de Datos y Modelo Relacional
* **Tareas:**
  1. Registrar e implementar la **Migración 48** en `database.py`.
  2. Crear la tabla `obra_adicionales`.
  3. Agregar las columnas de trazabilidad bimonetaria en `cobro_fin_original_usos` y `pagos_fondos_propios`.
  4. Ejecutar el script de verificación para ratificar que las 52 obras históricas conservan intactas sus claves primarias, datos y saldos.

---

### 🔹 FASE 2: Backend, Lógica de Negocio y Reglas Contables (`database.py`)
* **Tareas:**
  1. **Sincronización del Camino de Escritura (`add_obra` y `update_obra`):**
     * Admitir los parámetros: `moneda_id`, `monto_contrato_moneda`, `cotizacion_base_contrato`, `fecha_contrato`, `notas_contrato`.
     * **Regla estricta:** Si `moneda_id == 1` (Pesos): el backend fuerza automáticamente:
       `monto_contrato_moneda = monto_contrato` y `cotizacion_base_contrato = 1.0`.
       Elimina el riesgo de obras nuevas en pesos con saldo contractual bimonetario en cero.
  2. **Módulo CRUD de Adicionales de Obra:**
     * `add_obra_adicional(obra_id, nro_resolucion, fecha, cantidad_moneda, cotizacion_base, motivo)`
     * `get_obra_adicionales(obra_id)`
     * `delete_obra_adicional(adicional_id)`
  3. **Lógica de Costeo e Indexación FIFO (`get_resumen_contrato_obra`):**
     * Consolida los tramos de la obra:
       * Tramo 0: Contrato Base (`monto_contrato_moneda`, `cotizacion_base_contrato`).
       * Tramos 1..N: Adicionales ordenados por fecha ascendente (`cantidad_moneda`, `cotizacion_base`).
     * Asigna las UVIs amortizadas acumuladas a los tramos en estricto orden cronológico (FIFO).
     * Computa:
       * Total UVIs contratadas (Base + Adicionales).
       * Total UVIs amortizadas / certificadas.
       * Saldo remanente en UVIs.
       * % de Avance Contractual.
       * Costo Base Histórico de las UVIs amortizadas ($ ARS).
       * Total Pagado Efectivo en Banco ($ ARS).
       * **`Resultado por Indexación` ($ ARS)** = Total Pagado − Costo Base Histórico.
  4. **Derivación Automática en Registro de Pagos:**
     * En `add_fin_original_uso`: Si el cobro proviene de un convenio con certificado, copia automáticamente las UVIs y la cotización de liquidación del certificado sin intervención manual del operador.
  5. **Consulta de Trazabilidad Comprobante por Comprobante (`get_pagos_detalle_por_obra`):**
     * Retorna cada Orden de Pago con fecha, N° OP, fuente (Convenio o Fondos Propios), pesos abonados, UVIs amortizadas, cotización y su aporte al Resultado por Indexación.

---

### 🔹 FASE 3: Guardas de Sobrepago Bifurcadas y Excluyentes
* **Tareas:**
  1. En `components/tab_distribuir.py` y `pages/4_Pagos_Fondos_Propios.py`:
     * **Obra en UVIs / Moneda extranjera (`moneda_id != 1`):**
       Valida contra el total de UVIs contratadas (Base + Adicionales):
       `if (uvis_amortizadas_previas + uvis_nuevo_pago) > (total_uvis_contratadas + 0.001):`
       Muestra advertencia de sobrepago en UVIs y exige tildar `"Confirmo sobrepago"` e ingresar campo de texto `"Motivo de Sobrepago"`.
     * **Obra en Pesos tradicional (`moneda_id == 1`):**
       Valida contra `monto_contrato` en pesos:
       `if (pesos_pagados_previos + pesos_nuevo_pago) > (monto_contrato + TOLERANCE):`
       Muestra advertencia de sobrepago en pesos y exige tildar `"Confirmo sobrepago"` e ingresar campo de texto `"Motivo de Sobrepago"`.
  2. En el backend (`database.py`):
     * Al registrar el pago, si hubo sobrepago confirmado, se guarda el texto en la columna `motivo_sobrepago` para fiscalización del Tribunal de Cuentas.

---

### 🔹 FASE 4: Experiencia de Usuario (UI en Streamlit)
* **Pantallas a Modificar:**
  1. **`pages/2_Obras.py` (Catálogo de Obras):**
     * En formularios de alta y edición: selector de Moneda Contractual (`ARS`, `UVI`, `USD`, `CAC`). Si es UVI, solicita cantidad y cotización base de licitación, calculando el equivalente en pesos en vivo.
     * En la ficha de detalle de la obra:
       * **4 Tarjetas Métricas:** Contrato Total en UVIs, % de Avance en UVIs, Saldo Remanente en UVIs, Desembolsos Totales en Pesos (con badge de Resultado por Indexación).
       * **Sección "Adicionales de Obra":** Formulario para registrar ampliaciones por Resolución con su fecha y cotización.
       * **Tabla de Trazabilidad e Indexación:** Detalle cronológico por N° OP listo para auditar.
  2. **`components/tab_distribuir.py` (Fin Original):**
     * Si la obra es en UVIs y el cobro viene de convenio, muestra el banner:  
       *`ℹ️ Imputación automática: Amortiza X UVIs a cotización $Y heredada del Certificado de Convenio.`*
  3. **`pages/4_Pagos_Fondos_Propios.py`:**
     * Si la obra es en UVIs, solicita cotización de la OP para amortizar las UVIs exactas correspondientes.

---

### 🔹 FASE 5: Pruebas de Integración y Verificación Contable
* **Crear suite automatizada `test_obras_bimonetarias.py`:**
  1. **Alta de Obra en UVIs:** 50.000 UVIs a cotización base $1.000 (Base inicial: $50.000.000 ARS).
  2. **Adicional de Obra:** 5.000 UVIs a cotización $1.400 por Resolución N° 10/2026 (Total: 55.000 UVIs, Costo Base: $57.000.000 ARS).
  3. **Pago desde Convenio (Test 3 exacto):** Pago de 20.000 UVIs a cotización de certificado $1.250 ($25.000.000 ARS pagados).
     * Bajo FIFO: Amortiza 20.000 UVIs del Tramo 0 ($1.000). Costo base = $20.000.000 ARS.
     * **Resultado por Indexación verificado:** `$25.000.000 − $20.000.000 = $5.000.000 ARS exactos**.
  4. **Pago desde Fondos Propios:** Pago de $13.000.000 ARS a cotización $1.300 (amortiza 10.000 UVIs del Tramo 0).
  5. **Prueba de Guardia de Sobrepago:** Intentar pagar 30.000 UVIs cuando el remanente total es de 25.000 UVIs. Verificar bloqueo y requerimiento de confirmación con motivo.
  6. **Prueba de Obras en Pesos:** Crear y editar obra en ARS, ratificar que `monto_contrato_moneda = monto_contrato` y que no dispara cálculos en UVIs.
  7. **No-Regresión Histórica:** Ejecutar `test_compensacion_convenio.py` y `test_convenios_flujo.py` asegurando 100% OK.

---

## 🚦 5. ESTADO DE APROBACIÓN

Este plan integra y subsana el 100% de los hallazgos técnicos señalados por Claude y las consideraciones de Codex.  
**Estado:** Listo para ser ejecutado tras la confirmación de inicio del usuario.
