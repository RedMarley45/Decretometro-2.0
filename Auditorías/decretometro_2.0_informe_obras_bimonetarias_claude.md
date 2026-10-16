# 📋 INFORME DE IMPLEMENTACIÓN Y EVIDENCIA DE AUDITORÍA: CATÁLOGO DE OBRAS BIMONETARIO Y CONTROL DE PAGOS
## DECRETÓMETRO 2.0 — SUBSISTEMA DE OBRAS PÚBLICAS Y TRAZABILIDAD FIFO

**Documento Técnico, Contable y de Evidencia Empírica para Dictamen de Auditoría de Claude**

---

## 👤 1. METADATOS Y RESPONSABILIDAD

* **Responsable de Gestión y Dominio Contable:** Martín Rodríguez
  * Contador Público (Universidad de Buenos Aires - UBA).
  * Diplomado en Administración y Marketing de PyMEs (UNSAM).
  * Administrador de Finanzas de Obras Públicas — IMUH (Neuquén, Argentina).
* **Asistente de Desarrollo y Arquitectura:** Antigravity IDE (DeepMind).
* **Auditor Externo Destinatario:** Claude (Anthropic).
* **Auditoría Secundaria de Referencia:** Codex (OpenAI).
* **Fecha de Emisión del Informe:** 25 de Septiembre de 2026.
* **Repositorio / Sistema:** [Decretómetro 2.0](file:///c:/Users/bornemanns/.gemini/antigravity-ide/scratch/decretometro_2.0) (Streamlit / SQLite / Vanilla CSS).
* **Línea de Base:** `schema_version = 47` $\rightarrow$ `schema_version = 48` (Migración 48).

---

## 🎯 2. CONTEXTO, PROBLEMÁTICA Y RESOLUCIÓN DE DICTÁMENES PREVIOS

### 2.1 El Desafío Financiero
En la administración pública de obras de infraestructura, los contratos suelen pactarse en **Unidades de Vivienda (UVIs - Ley 27.271 / ICC)** o en **Dólares Estadounidenses (USD)** para resguardar la ecuación económico-financiera ante la inflación. No obstante, los pagos a contratistas se ejecutan **siempre en Pesos ($ ARS)** mediante Órdenes de Pago (OP) del sistema contable municipal (Bejerman), respaldadas por certificados de avance de obra periódicos.

Hasta la versión 47 del sistema:
1. El Catálogo de Obras (`obras`) registraba un escalar estático en pesos (`monto_contrato`), provocando que las obras licitadas en UVIs aparecieran en "sobrepago" financiero ficticio en pesos cuando simplemente se actualizaban por la cotización oficial de la UVI.
2. Los Adicionales de Obra autorizados por Resolución Municipal no tenían modelado relacional propio con su cotización base al dictado del acto administrativo.
3. No existía un desglose contable comprobante por comprobante que diferenciara el **Costo Base Histórico** del contrato respecto al **Resultado por Indexación** generado por la variación del índice de actualización.

### 2.2 Cuadro de Concordancia con las Observaciones Previas de Claude y Codex

| Observación Previa de Auditoría | Dictamen Auditor | Solución Definitiva Implementada en Fase 1 a 5 | Evidencia en este Informe |
| :--- | :--- | :--- | :--- |
| **Discrepancia Numérica en Test 3** | Claude señaló que un promedio ponderado arrojaba \$5.250.000 ARS en vez de \$5.000.000 ARS. | Se adoptó la **atribución cronológica FIFO por tramos**. El pago de 20.000 UVIs amortiza primero el Tramo 0 (Contrato Base @ \$1.000 = \$20M base). Resultado por Indexación: **\$5.000.000 ARS exactos**. | Ver Sección 5.2 (Test 3) y Log de Pytest (Sección 6.2). |
| **Derivación de UVIs en Pagos** | Codex advirtió no inferir UVIs sin trazabilidad de certificados. | En `add_fin_original_uso`, si el cobro proviene de convenio con certificado, **copia automáticamente las UVIs y la cotización del certificado** sin reescritura manual. | Ver Sección 4.1 (`add_fin_original_uso`). |
| **Modelado de Adicionales** | Claude y Codex requirieron tramos independientes para ampliaciones. | Se creó la tabla `obra_adicionales`, donde cada Resolución Municipal posee su fecha, cantidad y cotización base propia. | Ver Sección 3.1 (DDL Migración 48) y Sección 4.1 (CRUD). |
| **Guardas de Sobrepago** | Codex exigió no duplicar validaciones y Claude pidió justificación obligatoria. | **Guardas bifurcadas y excluyentes:** Si la obra es en UVIs, valida contra UVIs; si es en pesos, contra pesos. Si hay exceso, exige tildar confirmación y registrar obligatoriamente `motivo_sobrepago` en la BD. | Ver Sección 4.1 (`check_sobrepago_obra`). |
| **Inmutabilidad de Obras Históricas** | Martín Rodríguez y Claude exigieron 100% retrocompatibilidad. | Las 52 obras históricas fueron sincronizadas como `moneda_id = 1` (ARS), `cotizacion_base_contrato = 1.0` y `monto_contrato_moneda = monto_contrato`. Cero rotura de PKs. | Ver Sección 3.2 (Evidencia PRAGMA SQLite). |
| **Fallback Cotización Certificado** | Claude detectó que la UI enviaba cotiz fija 1.0 bloqueando fallback en backend si `cotizacion_cobro` venía vacío. | En convenios bimonetarios, la UI delega pasando `None` a `cotizacion_pago` y `cantidad_moneda_amortizada`, activando el fallback del backend a `cotizacion_solicitud`. | Ver Sección 5.2 (`tab_distribuir.py`), Sección 4.1 (`add_fin_original_uso`) y Test 7. |
| **Guarda Reducción Contrato UVIs** | Claude señaló que la guarda contra reducir contrato por debajo de lo pagado solo evaluaba `moneda_id == 1`. | Se incorporó la guarda bimonetaria en `update_monto_contrato_obra` y `update_obra`, comparando `monto_moneda + adicionales` contra `total_moneda_amortizada`. | Ver Sección 4.1.A y Test 8. |
| **Origen `cotizacion_solicitud` en UI** | Claude pidió confirmar que `get_cobros_con_resumen_distribucion` traiga `cotizacion_solicitud` para no caer a 1.0 en la pantalla. | Se confirmó y validó la presencia de `cs.cotizacion_solicitud` en el `SELECT` SQL de la función. | Ver Sección 4.1.A y Test 11. |
| **Bloqueo de Cambio de Moneda** | Claude recomendó bloquear el cambio de moneda en obras con pagos para evitar inconsistencias contables. | `update_obra` bloquea con `ValueError` cualquier cambio de `moneda_id` si la obra tiene pagos, y la UI desactiva el selector con mensaje de candado. | Ver Sección 4.1.A, Sección 5.1 y Test 9. |
| **Rectificación de Cotización Base** | Claude advirtió que alterar la cotización base reescribe retroactivamente la indexación de pagos pasados ante el Tribunal de Cuentas. | Se bloquea el cambio por defecto; solo se permite si el usuario confirma y provee justificación obligatoria, asentando constancia en `notas_contrato`. | Ver Sección 4.1.A, Sección 5.1 y Test 10. |
| **Atomicidad en `update_monto_contrato_obra`** | Claude detectó que la constancia se grababa antes de evaluar la guarda de reducción, dejando notas fantasma ante rechazos. | Se preparó la constancia en memoria y se unificó la persistencia en un único `UPDATE` atómico tras validar todas las guardas de reducción. | Ver Sección 4.1.A y Test 12. |

---

## 🗄️ 3. EVIDENCIA DE PERSISTENCIA Y MIGRACIÓN 48 (BASE DE DATOS)

### 3.1 DDL de la Migración 48 en `database.py`

La migración 48 fue añadida a la lista `MIGRACIONES` y su bloque ejecutor implementado con idempotencia:

```python
# Migración 48: Soporte Bimonetario en Catálogo de Obras y Control de Pagos
elif version == 48:
    # 1. Ampliación de la tabla 'obras'
    for col_sql in [
        "ALTER TABLE obras ADD COLUMN monto_contrato REAL DEFAULT 0.0",
        "ALTER TABLE obras ADD COLUMN moneda_id INTEGER DEFAULT 1",
        "ALTER TABLE obras ADD COLUMN monto_contrato_moneda REAL DEFAULT 0.0",
        "ALTER TABLE obras ADD COLUMN cotizacion_base_contrato REAL DEFAULT 1.0",
        "ALTER TABLE obras ADD COLUMN fecha_contrato DATE",
        "ALTER TABLE obras ADD COLUMN notas_contrato TEXT"
    ]:
        try:
            cursor.execute(col_sql)
        except sqlite3.OperationalError:
            pass

    # 2. Tabla para Adicionales / Ampliaciones de Obra
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS obra_adicionales (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            obra_id INTEGER NOT NULL REFERENCES obras(id) ON DELETE CASCADE,
            nro_resolucion TEXT NOT NULL,
            fecha DATE NOT NULL,
            cantidad_moneda REAL NOT NULL,
            cotizacion_base REAL NOT NULL DEFAULT 1.0,
            monto_equivalente_ars REAL NOT NULL,
            motivo TEXT
        )
    ''')

    # 3. Ampliación de tablas de pagos a contratistas
    for pcol_sql in [
        "ALTER TABLE cobro_fin_original_usos ADD COLUMN cantidad_moneda_amortizada REAL",
        "ALTER TABLE cobro_fin_original_usos ADD COLUMN cotizacion_pago REAL DEFAULT 1.0",
        "ALTER TABLE cobro_fin_original_usos ADD COLUMN convenio_solicitud_id INTEGER",
        "ALTER TABLE cobro_fin_original_usos ADD COLUMN motivo_sobrepago TEXT",
        "ALTER TABLE pagos_fondos_propios ADD COLUMN cantidad_moneda_amortizada REAL",
        "ALTER TABLE pagos_fondos_propios ADD COLUMN cotizacion_pago REAL DEFAULT 1.0",
        "ALTER TABLE pagos_fondos_propios ADD COLUMN convenio_solicitud_id INTEGER",
        "ALTER TABLE pagos_fondos_propios ADD COLUMN motivo_sobrepago TEXT"
    ]:
        try:
            cursor.execute(pcol_sql)
        except sqlite3.OperationalError:
            pass

    # 4. Sincronización inmutable de registros históricos:
    cursor.execute('''
        UPDATE obras 
        SET moneda_id = 1,
            monto_contrato_moneda = COALESCE(monto_contrato, 0.0),
            cotizacion_base_contrato = 1.0
        WHERE moneda_id IS NULL OR moneda_id = 1
    ''')
```

### 3.2 Evidencia Empírica de Inspección del Esquema en `decretometro.db`

Ejecución directa sobre la base de datos viva del sistema:

```text
======================= EVIDENCIA DE MOTOR SQLITE =======================
SCHEMA_VERSION: 48
OBRAS_COUNT: total=52, ars_synced=52

OBRAS_COLS:
  - ('id', 'INTEGER', None)
  - ('nombre', 'TEXT', None)
  - ('expediente_imuh', 'TEXT', None)
  - ('activa', 'INTEGER', '1')
  - ('proveedor_id', 'INTEGER', None)
  - ('monto_contrato', 'REAL', '0')
  - ('monto_contrato_moneda', 'REAL', '0.0')
  - ('cotizacion_base_contrato', 'REAL', '1.0')
  - ('fecha_contrato', 'DATE', None)
  - ('notas_contrato', 'TEXT', None)
  - ('moneda_id', 'INTEGER', '1')

ADIC_COLS (obra_adicionales):
  - ('id', 'INTEGER')
  - ('obra_id', 'INTEGER')
  - ('nro_resolucion', 'TEXT')
  - ('fecha', 'DATE')
  - ('cantidad_moneda', 'REAL')
  - ('cotizacion_base', 'REAL')
  - ('monto_equivalente_ars', 'REAL')
  - ('motivo', 'TEXT')

FO_COLS (cobro_fin_original_usos - últimos 4 campos):
  - ('cantidad_moneda_amortizada', 'REAL')
  - ('cotizacion_pago', 'REAL')
  - ('convenio_solicitud_id', 'INTEGER')
  - ('motivo_sobrepago', 'TEXT')

PFP_COLS (pagos_fondos_propios - últimos 4 campos):
  - ('cantidad_moneda_amortizada', 'REAL')
  - ('cotizacion_pago', 'REAL')
  - ('convenio_solicitud_id', 'INTEGER')
  - ('motivo_sobrepago', 'TEXT')
=========================================================================
```

**Conclusión de persistencia:** Se ratifica al 100% que las 52 obras históricas conservaron sus registros y fueron vinculadas automáticamente como moneda ARS (`moneda_id = 1`), con cotización base 1.0 y sincronización nominal en pesos.

---

## ⚙️ 4. EXPOSICIÓN DEL CÓDIGO FUENTE IMPLEMENTADO

A continuación se transcribe textualmente el código desarrollado e integrado en los módulos de backend y frontend.

### 4.1 Backend y Lógica de Negocio (`database.py`)

#### A. CRUD de Obras con Sincronización Inmutable de Escritura

```python
def add_obra(nombre, expediente_imuh, proveedor_id=None, moneda_id=1, monto_contrato_moneda=0.0, cotizacion_base_contrato=1.0, fecha_contrato=None, notas_contrato=None):
    if not nombre or not nombre.strip():
        raise ValueError("El nombre de la obra no puede estar vacío.")
    if not expediente_imuh or not expediente_imuh.strip():
        raise ValueError("El expediente IMUH no puede estar vacío.")
    import utils
    if not utils.validar_expediente_imuh(expediente_imuh):
        raise ValueError("El Expediente IMUH tiene un formato inválido (debe ser 8XXXXXX-I-AAAA o similar).")
        
    exp_normalizado = utils.normalizar_expediente_imuh(expediente_imuh)
    
    if get_obra_by_expediente(exp_normalizado):
        raise ValueError(f"Ya existe una obra registrada con el expediente {exp_normalizado}.")
    
    # Sincronización inmutable del camino de escritura
    m_id = int(moneda_id or 1)
    monto_mon = float(monto_contrato_moneda or 0.0)
    cotiz_base = float(cotizacion_base_contrato or 1.0)
    if m_id == 1:
        cotiz_base = 1.0
        monto_pesos = monto_mon
    else:
        monto_pesos = monto_mon * cotiz_base

    with db_session() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO obras (
                nombre, expediente_imuh, activa, proveedor_id,
                moneda_id, monto_contrato_moneda, cotizacion_base_contrato,
                monto_contrato, fecha_contrato, notas_contrato
            )
            VALUES (?, ?, 1, ?, ?, ?, ?, ?, ?, ?)
        ''', (nombre.strip(), exp_normalizado, proveedor_id,
              m_id, monto_mon, cotiz_base,
              monto_pesos, fecha_contrato, notas_contrato.strip() if notas_contrato else None))
        obra_id = cursor.lastrowid
        conn.commit()
        return obra_id


def update_obra(obra_id, nombre, expediente_imuh, activa, proveedor_id=None,
                moneda_id=None, monto_contrato_moneda=None, cotizacion_base_contrato=None,
                fecha_contrato=None, notas_contrato=None, motivo_rectificacion=None):
    if not nombre or not nombre.strip():
        raise ValueError("El nombre de la obra no puede estar vacío.")
    if not expediente_imuh or not expediente_imuh.strip():
        raise ValueError("El expediente IMUH no puede estar vacío.")
    import utils
    if not utils.validar_expediente_imuh(expediente_imuh):
        raise ValueError("El Expediente IMUH tiene un formato inválido.")
        
    exp_normalizado = utils.normalizar_expediente_imuh(expediente_imuh)

    with db_session() as conn:
        cursor = conn.cursor()
        # Verificar duplicados del expediente excluyendo la obra actual
        cursor.execute('SELECT id FROM obras WHERE expediente_imuh = ? AND id != ?', (exp_normalizado, obra_id))
        if cursor.fetchone():
            raise ValueError(f"Ya existe otra obra registrada con el expediente IMUH '{exp_normalizado}'.")
            
        cursor.execute('SELECT moneda_id, monto_contrato_moneda, cotizacion_base_contrato, monto_contrato, fecha_contrato, notas_contrato FROM obras WHERE id = ?', (obra_id,))
        cur_row = cursor.fetchone()
        
        old_m_id = int(cur_row['moneda_id'] or 1)
        m_id = int(moneda_id if moneda_id is not None else old_m_id)
        monto_mon = float(monto_contrato_moneda if monto_contrato_moneda is not None else (cur_row['monto_contrato_moneda'] or cur_row['monto_contrato'] or 0.0))
        old_cotiz = float(cur_row['cotizacion_base_contrato'] or 1.0)
        cotiz_base = float(cotizacion_base_contrato if cotizacion_base_contrato is not None else old_cotiz)
        f_contrato = fecha_contrato if fecha_contrato is not None else cur_row['fecha_contrato']
        n_contrato = notas_contrato if notas_contrato is not None else cur_row['notas_contrato']

        pagos_existentes = get_pagos_detalle_por_obra(obra_id)
        tiene_pagos = (len(pagos_existentes) > 0 or get_total_pagado_obra(obra_id) > 0)

        # Guarda 1: Bloqueo terminante de cambio de moneda si ya hay pagos
        if m_id != old_m_id and tiene_pagos:
            raise ValueError("No se puede modificar la moneda de contratación de una obra que ya registra pagos u órdenes de pago emitidas.")

        # Guarda 2: Rectificación de cotización base inicial si ya hay pagos
        if m_id != 1 and abs(cotiz_base - old_cotiz) > 0.0001 and tiene_pagos:
            if not motivo_rectificacion or not str(motivo_rectificacion).strip():
                raise ValueError("Debe ingresar un motivo / justificación obligatoria para rectificar la cotización base de una obra con pagos registrados.")
            import datetime
            fecha_hoy = datetime.date.today().strftime('%Y-%m-%d')
            constancia = f"\n[Rectificación Cotiz. Base: ${old_cotiz:,.2f} -> ${cotiz_base:,.2f} | Motivo: {str(motivo_rectificacion).strip()} | Fecha: {fecha_hoy}]"
            n_contrato = (n_contrato or "") + constancia

        if m_id == 1:
            cotiz_base = 1.0
            monto_pesos = monto_mon
            total_pagado = get_total_pagado_obra(obra_id)
            if monto_pesos > 0 and monto_pesos < (total_pagado - TOLERANCE):
                raise ValueError(f"No se puede reducir el monto de contrato por debajo del total ya pagado a la contratista (${total_pagado:,.2f})")
        else:
            monto_pesos = monto_mon * cotiz_base
            resumen = get_resumen_contrato_obra(obra_id)
            if resumen:
                total_amortizado = float(resumen.get('total_moneda_amortizada') or 0.0)
                cant_adic = float(resumen.get('cantidad_adicionales_moneda') or 0.0)
                nuevo_tope_moneda = monto_mon + cant_adic
                cod_mon = resumen.get('moneda_codigo') or 'UVI'
                if monto_mon > 0 and nuevo_tope_moneda < (total_amortizado - 0.0001):
                    raise ValueError(f"No se puede reducir el contrato en {cod_mon} ({nuevo_tope_moneda:,.2f}) por debajo del total ya amortizado ({total_amortizado:,.2f} {cod_mon}).")

        cursor.execute('''
            UPDATE obras
            SET nombre = ?, expediente_imuh = ?, activa = ?, proveedor_id = ?,
                moneda_id = ?, monto_contrato_moneda = ?, cotizacion_base_contrato = ?,
                monto_contrato = ?, fecha_contrato = ?, notas_contrato = ?
            WHERE id = ?
        ''', (nombre.strip(), exp_normalizado, activa, proveedor_id,
              m_id, monto_mon, cotiz_base,
              monto_pesos, f_contrato, n_contrato, obra_id))
        
        cursor.execute('''
            UPDATE solicitudes_financiamiento
            SET expediente_imuh = ?
            WHERE obra_id = ?
        ''', (exp_normalizado, obra_id))
        
        conn.commit()


def update_monto_contrato_obra(obra_id, nuevo_monto, nuevo_monto_moneda=None, nueva_cotizacion_base=None, motivo_rectificacion=None):
    obra = get_obra(obra_id)
    if not obra:
        raise ValueError("Obra no encontrada.")
    m_id = obra.get('moneda_id') or 1
    
    if m_id == 1:
        monto_moneda = float(nuevo_monto or 0.0)
        cotiz = 1.0
        monto_pesos = float(nuevo_monto or 0.0)
    else:
        monto_moneda = float(nuevo_monto_moneda if nuevo_monto_moneda is not None else (obra.get('monto_contrato_moneda') or 0.0))
        cotiz = float(nueva_cotizacion_base if nueva_cotizacion_base is not None else (obra.get('cotizacion_base_contrato') or 1.0))
        monto_pesos = float(nuevo_monto if nuevo_monto is not None else (monto_moneda * cotiz))

    old_cotiz = float(obra.get('cotizacion_base_contrato') or 1.0)
    pagos_existentes = get_pagos_detalle_por_obra(obra_id)
    tiene_pagos = (len(pagos_existentes) > 0 or get_total_pagado_obra(obra_id) > 0)
    
    # Preparación en memoria de la constancia de rectificación (no se escribe hasta que pasen las guardas)
    nueva_constancia = None
    if m_id != 1 and nueva_cotizacion_base is not None and abs(cotiz - old_cotiz) > 0.0001 and tiene_pagos:
        if not motivo_rectificacion or not str(motivo_rectificacion).strip():
            raise ValueError("Debe ingresar un motivo / justificación obligatoria para rectificar la cotización base de una obra con pagos registrados.")
        import datetime
        fecha_hoy = datetime.date.today().strftime('%Y-%m-%d')
        nueva_constancia = f"\n[Rectificación Cotiz. Base: ${old_cotiz:,.2f} -> ${cotiz:,.2f} | Motivo: {str(motivo_rectificacion).strip()} | Fecha: {fecha_hoy}]"

    # Guardas de reducción contra importes ya amortizados / pagados
    resumen = get_resumen_contrato_obra(obra_id)
    if m_id == 1:
        total_pagado = get_total_pagado_obra(obra_id)
        if monto_pesos > 0 and monto_pesos < (total_pagado - TOLERANCE):
            raise ValueError(f"No se puede reducir el monto de contrato por debajo del total ya pagado a la contratista (${total_pagado:,.2f})")
    else:
        if resumen:
            total_amortizado = float(resumen.get('total_moneda_amortizada') or 0.0)
            cant_adic = float(resumen.get('cantidad_adicionales_moneda') or 0.0)
            nuevo_tope_moneda = monto_moneda + cant_adic
            cod_mon = resumen.get('moneda_codigo') or 'UVI'
            if monto_moneda > 0 and nuevo_tope_moneda < (total_amortizado - 0.0001):
                raise ValueError(f"No se puede reducir el contrato en {cod_mon} ({nuevo_tope_moneda:,.2f}) por debajo del total ya amortizado ({total_amortizado:,.2f} {cod_mon}).")
    
    # Escritura atómica única en base de datos
    with db_session() as conn:
        if nueva_constancia:
            notas_actuales = obra.get('notas_contrato') or ""
            nuevas_notas = notas_actuales + nueva_constancia
            conn.execute("""
                UPDATE obras 
                SET monto_contrato = ?, monto_contrato_moneda = ?, cotizacion_base_contrato = ?, notas_contrato = ?
                WHERE id = ?
            """, (monto_pesos, monto_moneda, cotiz, nuevas_notas, obra_id))
        else:
            conn.execute("""
                UPDATE obras 
                SET monto_contrato = ?, monto_contrato_moneda = ?, cotizacion_base_contrato = ?
                WHERE id = ?
            """, (monto_pesos, monto_moneda, cotiz, obra_id))
```

#### B. CRUD de Adicionales de Obra (`obra_adicionales`)

```python
def add_obra_adicional(obra_id, nro_resolucion, fecha, cantidad_moneda, cotizacion_base=1.0, motivo=None):
    if not obra_id:
        raise ValueError("Debe especificar la obra.")
    if not nro_resolucion or not str(nro_resolucion).strip():
        raise ValueError("El N° de Resolución del adicional no puede estar vacío.")
    if not fecha:
        raise ValueError("La fecha del adicional es obligatoria.")
    try:
        cant_mon = float(cantidad_moneda)
    except (ValueError, TypeError):
        raise ValueError("La cantidad en moneda debe ser un número válido.")
    if cant_mon <= 0:
        raise ValueError("La cantidad en moneda debe ser mayor a 0.")
        
    try:
        cotiz = float(cotizacion_base)
    except (ValueError, TypeError):
        cotiz = 1.0
    if cotiz <= 0:
        cotiz = 1.0
        
    monto_ars = round(cant_mon * cotiz, 2)
    
    with db_session() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT id, moneda_id FROM obras WHERE id = ?', (obra_id,))
        o_row = cursor.fetchone()
        if not o_row:
            raise ValueError("Obra no encontrada.")
            
        cursor.execute('''
            INSERT INTO obra_adicionales (obra_id, nro_resolucion, fecha, cantidad_moneda, cotizacion_base, monto_equivalente_ars, motivo)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (obra_id, str(nro_resolucion).strip(), str(fecha), cant_mon, cotiz, monto_ars, motivo.strip() if motivo else None))
        new_id = cursor.lastrowid
        conn.commit()
        return new_id


def get_obra_adicionales(obra_id):
    with db_session() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT * FROM obra_adicionales
            WHERE obra_id = ?
            ORDER BY fecha ASC, id ASC
        ''', (obra_id,))
        return [dict(r) for r in cursor.fetchall()]


def delete_obra_adicional(adicional_id):
    with db_session() as conn:
        cursor = conn.cursor()
        cursor.execute('DELETE FROM obra_adicionales WHERE id = ?', (adicional_id,))
        conn.commit()
```

#### C. Lógica de Costeo e Indexación FIFO (`get_resumen_contrato_obra`)

```python
def get_resumen_contrato_obra(obra_id):
    """
    Consolida la posición contractual y financiera de una obra.
    Para obras bimonetarias (UVIs, USD, etc.), aplica costeo cronológico FIFO sobre los tramos
    (Contrato Base + Adicionales por Resolución) y determina el Costo Base Histórico
    y el Resultado por Indexación acumulado.
    """
    obra = get_obra(obra_id)
    if not obra:
        return None
        
    moneda_id = obra.get('moneda_id') or 1
    es_bimonetaria = (moneda_id != 1)
    
    # 1. Definición de Tramos Contractuales (FIFO)
    # Tramo 0: Contrato Base
    monto_base_moneda = float(obra.get('monto_contrato_moneda') or 0.0)
    cotiz_base_contrato = float(obra.get('cotizacion_base_contrato') or 1.0)
    if not es_bimonetaria:
        monto_base_moneda = float(obra.get('monto_contrato') or 0.0)
        cotiz_base_contrato = 1.0
    costo_base_contrato_ars = monto_base_moneda * cotiz_base_contrato
    
    tramos = [{
        'tipo': 'Contrato Base',
        'nro_resolucion': 'Original',
        'fecha': obra.get('fecha_contrato') or 'Inicial',
        'cantidad_moneda': monto_base_moneda,
        'cotizacion_base': cotiz_base_contrato,
        'monto_ars': costo_base_contrato_ars,
        'moneda_amortizada': 0.0,
        'costo_base_amortizado_ars': 0.0,
        'saldo_moneda': monto_base_moneda
    }]
    
    # Tramos 1..N: Adicionales ordenados cronológicamente
    adicionales = get_obra_adicionales(obra_id)
    cant_adicionales_moneda = 0.0
    costo_adicionales_ars = 0.0
    for adic in adicionales:
        cant_adic = float(adic.get('cantidad_moneda') or 0.0)
        cotiz_adic = float(adic.get('cotizacion_base') or 1.0)
        monto_adic_ars = float(adic.get('monto_equivalente_ars') or (cant_adic * cotiz_adic))
        cant_adicionales_moneda += cant_adic
        costo_adicionales_ars += monto_adic_ars
        tramos.append({
            'tipo': 'Adicional',
            'nro_resolucion': adic.get('nro_resolucion') or '',
            'fecha': str(adic.get('fecha') or ''),
            'cantidad_moneda': cant_adic,
            'cotizacion_base': cotiz_adic,
            'monto_ars': monto_adic_ars,
            'moneda_amortizada': 0.0,
            'costo_base_amortizado_ars': 0.0,
            'saldo_moneda': cant_adic
        })
        
    total_contratado_moneda = monto_base_moneda + cant_adicionales_moneda
    total_costo_base_contratado_ars = costo_base_contrato_ars + costo_adicionales_ars
    
    # 2. Pagos efectivos imputados a la obra
    with db_session() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT id, fecha, monto, cantidad_moneda_amortizada, cotizacion_pago, 'Fin Original' as fuente
            FROM cobro_fin_original_usos
            WHERE obra_id = ?
            ORDER BY fecha ASC, id ASC
        ''', (obra_id,))
        pagos_fo = [dict(r) for r in cursor.fetchall()]
        
        cursor.execute('''
            SELECT id, fecha, monto, cantidad_moneda_amortizada, cotizacion_pago, 'Fondos Propios' as fuente
            FROM pagos_fondos_propios
            WHERE obra_id = ?
            ORDER BY fecha ASC, id ASC
        ''', (obra_id,))
        pagos_fp = [dict(r) for r in cursor.fetchall()]
        
        cursor.execute('''
            SELECT id, fecha, monto, NULL as cantidad_moneda_amortizada, 1.0 as cotizacion_pago, 'Desvío Fin Original' as fuente
            FROM cobro_desvios
            WHERE obra_id = ?
            ORDER BY fecha ASC, id ASC
        ''', (obra_id,))
        pagos_desv = [dict(r) for r in cursor.fetchall()]
        
        cursor.execute('''
            SELECT id, fecha, monto, NULL as cantidad_moneda_amortizada, 1.0 as cotizacion_pago, 'Uso Reserva' as fuente
            FROM cobro_reserva_usos
            WHERE obra_id = ?
            ORDER BY fecha ASC, id ASC
        ''', (obra_id,))
        pagos_res = [dict(r) for r in cursor.fetchall()]
        
    todos_pagos = pagos_fo + pagos_fp + pagos_desv + pagos_res
    todos_pagos.sort(key=lambda x: (str(x.get('fecha') or ''), x.get('id') or 0))
    
    total_pagado_efectivo_ars = sum(float(p.get('monto') or 0.0) for p in todos_pagos)
    
    # Cálculo de moneda amortizada
    total_moneda_amortizada = 0.0
    for p in todos_pagos:
        monto_ars = float(p.get('monto') or 0.0)
        if not es_bimonetaria:
            cant = monto_ars
        else:
            cant_raw = p.get('cantidad_moneda_amortizada')
            if cant_raw is not None and float(cant_raw) > 0:
                cant = float(cant_raw)
            else:
                cotiz_p = float(p.get('cotizacion_pago') or 1.0)
                cant = (monto_ars / cotiz_p) if cotiz_p > 0 else 0.0
        total_moneda_amortizada += cant
        
    # 3. Aplicación del algoritmo FIFO sobre los tramos
    rem_amortizar = total_moneda_amortizada
    costo_base_amortizado_ars = 0.0
    last_cotiz = cotiz_base_contrato
    
    for tramo in tramos:
        last_cotiz = tramo['cotizacion_base']
        if rem_amortizar <= 0:
            break
        capacidad = tramo['cantidad_moneda']
        tomar = min(rem_amortizar, capacidad)
        tramo['moneda_amortizada'] = tomar
        tramo_costo = tomar * tramo['cotizacion_base']
        tramo['costo_base_amortizado_ars'] = tramo_costo
        tramo['saldo_moneda'] = max(0.0, capacidad - tomar)
        costo_base_amortizado_ars += tramo_costo
        rem_amortizar -= tomar
        
    if rem_amortizar > 0:
        costo_base_amortizado_ars += (rem_amortizar * last_cotiz)
        
    resultado_indexacion_ars = total_pagado_efectivo_ars - costo_base_amortizado_ars
    saldo_moneda_remanente = max(0.0, total_contratado_moneda - total_moneda_amortizada)
    porcentaje_avance = (total_moneda_amortizada / total_contratado_moneda * 100.0) if total_contratado_moneda > 0 else 0.0
    
    return {
        'obra_id': obra_id,
        'nombre': obra.get('nombre'),
        'expediente_imuh': obra.get('expediente_imuh'),
        'moneda_id': moneda_id,
        'moneda_codigo': obra.get('moneda_codigo') or 'ARS',
        'moneda_simbolo': obra.get('moneda_simbolo') or '$',
        'moneda_nombre': obra.get('moneda_nombre') or 'Peso Argentino',
        'es_bimonetaria': es_bimonetaria,
        'monto_contrato_base_moneda': monto_base_moneda,
        'cotizacion_base_contrato': cotiz_base_contrato,
        'costo_base_contrato_ars': costo_base_contrato_ars,
        'cantidad_adicionales_moneda': cant_adicionales_moneda,
        'costo_adicionales_ars': costo_adicionales_ars,
        'total_contratado_moneda': total_contratado_moneda,
        'total_costo_base_contratado_ars': total_costo_base_contratado_ars,
        'total_moneda_amortizada': total_moneda_amortizada,
        'saldo_moneda_remanente': saldo_moneda_remanente,
        'porcentaje_avance_moneda': min(100.0, porcentaje_avance),
        'total_pagado_efectivo_ars': total_pagado_efectivo_ars,
        'costo_base_amortizado_ars': costo_base_amortizado_ars,
        'resultado_indexacion_ars': resultado_indexacion_ars,
        'tramos': tramos
    }
```

#### D. Trazabilidad Comprobante por Comprobante (`get_pagos_detalle_por_obra`)

```python
def get_pagos_detalle_por_obra(obra_id):
    """
    Retorna el detalle cronológico de órdenes de pago imputadas a la obra
    con su desglose bimonetario y la imputación FIFO al Costo Base y Resultado por Indexación.
    """
    obra = get_obra(obra_id)
    if not obra:
        return []
        
    moneda_id = obra.get('moneda_id') or 1
    es_bimonetaria = (moneda_id != 1)
    
    resumen = get_resumen_contrato_obra(obra_id)
    tramos_base = []
    if resumen and resumen.get('tramos'):
        for t in resumen['tramos']:
            tramos_base.append({
                'tipo': t['tipo'],
                'cantidad_moneda': t['cantidad_moneda'],
                'cotizacion_base': t['cotizacion_base'],
                'disponible': t['cantidad_moneda']
            })
    last_cotiz_base = resumen.get('cotizacion_base_contrato') or 1.0 if resumen else 1.0
    
    with db_session() as conn:
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT fu.id, fu.fecha, fu.nro_op, fu.monto as monto_ars,
                   fu.cantidad_moneda_amortizada, fu.cotizacion_pago,
                   fu.convenio_solicitud_id, fu.motivo_sobrepago, fu.notas,
                   c.origen_tipo, cs.nro_certificado, conv.nombre_convenio,
                   'Fin Original' as tipo_fuente
            FROM cobro_fin_original_usos fu
            LEFT JOIN cobros c ON fu.cobro_id = c.id
            LEFT JOIN convenio_solicitudes cs ON (fu.convenio_solicitud_id = cs.id OR c.convenio_solicitud_id = cs.id)
            LEFT JOIN convenios conv ON cs.convenio_id = conv.id
            WHERE fu.obra_id = ?
        ''', (obra_id,))
        pagos_fo = [dict(r) for r in cursor.fetchall()]
        
        cursor.execute('''
            SELECT pfp.id, pfp.fecha, pfp.nro_op, pfp.monto as monto_ars,
                   pfp.cantidad_moneda_amortizada, pfp.cotizacion_pago,
                   pfp.convenio_solicitud_id, pfp.motivo_sobrepago, pfp.observaciones as notas,
                   'fondos_propios' as origen_tipo, cs.nro_certificado, conv.nombre_convenio,
                   'Fondos Propios' as tipo_fuente
            FROM pagos_fondos_propios pfp
            LEFT JOIN convenio_solicitudes cs ON pfp.convenio_solicitud_id = cs.id
            LEFT JOIN convenios conv ON cs.convenio_id = conv.id
            WHERE pfp.obra_id = ?
        ''', (obra_id,))
        pagos_fp = [dict(r) for r in cursor.fetchall()]
        
    todos = pagos_fo + pagos_fp
    todos.sort(key=lambda x: (str(x.get('fecha') or ''), x.get('id') or 0))
    
    for p in todos:
        monto_ars = float(p.get('monto_ars') or 0.0)
        if not es_bimonetaria:
            cant_mon = monto_ars
            cotiz = 1.0
        else:
            cant_raw = p.get('cantidad_moneda_amortizada')
            cotiz_raw = p.get('cotizacion_pago')
            cotiz = float(cotiz_raw) if (cotiz_raw and float(cotiz_raw) > 0) else 1.0
            if cant_raw is not None and float(cant_raw) > 0:
                cant_mon = float(cant_raw)
            else:
                cant_mon = round(monto_ars / cotiz, 6) if cotiz > 0 else 0.0
                
        p['cantidad_moneda_amortizada'] = cant_mon
        p['cotizacion_pago'] = cotiz
        
        rem = cant_mon
        costo_base_pago_ars = 0.0
        for tr in tramos_base:
            last_cotiz_base = tr['cotizacion_base']
            if rem <= 0:
                break
            if tr['disponible'] > 0:
                take = min(rem, tr['disponible'])
                costo_base_pago_ars += (take * tr['cotizacion_base'])
                tr['disponible'] -= take
                rem -= take
        if rem > 0:
            costo_base_pago_ars += (rem * last_cotiz_base)
            
        p['costo_base_ars'] = costo_base_pago_ars
        p['resultado_indexacion_ars'] = monto_ars - costo_base_pago_ars
        
        if p.get('nombre_convenio') or p.get('nro_certificado'):
            cert_txt = f" (Cert. {p['nro_certificado']})" if p.get('nro_certificado') else ""
            conv_txt = f" - {p['nombre_convenio']}" if p.get('nombre_convenio') else ""
            p['fuente_descripcion'] = f"Convenio{conv_txt}{cert_txt}"
        else:
            p['fuente_descripcion'] = p.get('tipo_fuente')
            
    return todos
```

#### E. Guarda de Sobrepago Bifurcada y Excluyente (`check_sobrepago_obra`)

```python
def check_sobrepago_obra(obra_id, nuevo_monto_pesos=0.0, nueva_cantidad_moneda=0.0):
    """
    Verifica si un pago propuesto excede el tope de contrato.
    Retorna un diccionario de control con indicador booleano y mensaje explicativo.
    """
    obra = get_obra(obra_id)
    if not obra:
        return {'es_sobrepago': False, 'mensaje': ''}
        
    resumen = get_resumen_contrato_obra(obra_id)
    if not resumen:
        return {'es_sobrepago': False, 'mensaje': ''}
        
    es_bimonetaria = resumen['es_bimonetaria']
    simbolo = resumen['moneda_simbolo']
    codigo = resumen['moneda_codigo']
    
    if es_bimonetaria:
        tope = resumen['total_contratado_moneda']
        acumulado_previo = resumen['total_moneda_amortizada']
        nuevo_total = acumulado_previo + float(nueva_cantidad_moneda or 0.0)
        es_sobrepago = (tope > 0 and nuevo_total > (tope + 0.001))
        exceso = max(0.0, nuevo_total - tope)
        unidad = codigo
        msg = f"El total amortizado alcanzará {nuevo_total:,.2f} {codigo}, superando el contrato total ({tope:,.2f} {codigo}) por {exceso:,.2f} {codigo}."
    else:
        tope = resumen['total_costo_base_contratado_ars']
        acumulado_previo = resumen['total_pagado_efectivo_ars']
        nuevo_total = acumulado_previo + float(nuevo_monto_pesos or 0.0)
        es_sobrepago = (tope > 0 and nuevo_total > (tope + TOLERANCE))
        exceso = max(0.0, nuevo_total - tope)
        unidad = 'ARS'
        msg = f"El total pagado alcanzará ${nuevo_total:,.2f} ARS, superando el monto de contrato (${tope:,.2f} ARS) por ${exceso:,.2f} ARS."
        
    return {
        'es_sobrepago': es_sobrepago,
        'es_bimonetaria': es_bimonetaria,
        'tope': tope,
        'acumulado_previo': acumulado_previo,
        'nuevo_total': nuevo_total,
        'exceso': exceso,
        'unidad': unidad,
        'mensaje': msg if es_sobrepago else ''
    }
```

#### F. Derivación Automática en Registro de Pagos

```python
def add_fin_original_uso(cobro_id, monto, fecha, nro_op=None, notas=None, obra_id=None, gasto_nombre=None, gasto_expediente_imuh=None,
                         cantidad_moneda_amortizada=None, cotizacion_pago=None, convenio_solicitud_id=None, motivo_sobrepago=None):
    _validar_op_o_nota_db(nro_op, notas, contexto="pago de Fin Original")
    if monto <= 0:
        raise ValueError("El monto a pagar debe ser mayor a 0.")
    
    with db_session() as conn:
        cursor = conn.cursor()
    
        cursor.execute('SELECT monto_fin_orig FROM cobro_distribuciones WHERE cobro_id = ?', (cobro_id,))
        row_dist = cursor.fetchone()
        fin_orig_presupuesto = row_dist['monto_fin_orig'] if row_dist else 0.0
    
        cursor.execute('SELECT COALESCE(SUM(monto), 0) as tot_pagado FROM cobro_fin_original_usos WHERE cobro_id = ?', (cobro_id,))
        ya_pagado = cursor.fetchone()['tot_pagado']
    
        if (ya_pagado + monto) > (fin_orig_presupuesto + TOLERANCE):
            raise ValueError(f"El monto a pagar ({monto:.2f}) supera el saldo disponible asignado a Fin Original ({fin_orig_presupuesto - ya_pagado:.2f}).")
        
        # Obtener información del cobro para auto-derivación de convenio si corresponde
        cursor.execute('''
            SELECT c.*, cs.id as cs_id, cs.obra_id as cs_obra_id, cs.cotizacion_solicitud, cs.cantidad_moneda, cs.nro_certificado
            FROM cobros c
            LEFT JOIN convenio_solicitudes cs ON c.convenio_solicitud_id = cs.id
            WHERE c.id = ?
        ''', (cobro_id,))
        c_row = cursor.fetchone()
        
        target_obra_id = obra_id
        if not target_obra_id and c_row:
            target_obra_id = c_row['obra_id'] or c_row['cs_obra_id']
            
        c_sol_id = convenio_solicitud_id
        if c_sol_id is None and c_row and c_row['convenio_solicitud_id']:
            c_sol_id = c_row['convenio_solicitud_id']
            
        cotiz = cotizacion_pago
        cant_mon = cantidad_moneda_amortizada
        
        if target_obra_id:
            cursor.execute('SELECT moneda_id FROM obras WHERE id = ?', (target_obra_id,))
            o_row = cursor.fetchone()
            if o_row:
                o_moneda_id = o_row['moneda_id'] or 1
                if o_moneda_id == 1:
                    cotiz = 1.0
                    cant_mon = float(monto)
                else:
                    if cotiz is None or cotiz <= 0:
                        cotiz_sol = c_row['cotizacion_solicitud'] if (c_row and 'cotizacion_solicitud' in c_row.keys()) else None
                        if not cotiz_sol and c_sol_id:
                            cursor.execute('SELECT cotizacion_solicitud FROM convenio_solicitudes WHERE id = ?', (c_sol_id,))
                            cs_f = cursor.fetchone()
                            if cs_f:
                                cotiz_sol = cs_f['cotizacion_solicitud']

                        if c_row and c_row['cotizacion_cobro'] and float(c_row['cotizacion_cobro']) > 1.0:
                            cotiz = float(c_row['cotizacion_cobro'])
                        elif cotiz_sol and float(cotiz_sol) > 1.0:
                            cotiz = float(cotiz_sol)
                        else:
                            cotiz = 1.0
                    if cant_mon is None:
                        cant_mon = round(monto / cotiz, 6) if cotiz > 0 else 0.0

        cursor.execute('''
            INSERT INTO cobro_fin_original_usos (
                cobro_id, monto, fecha, nro_op, notas, obra_id, gasto_nombre, gasto_expediente_imuh,
                cantidad_moneda_amortizada, cotizacion_pago, convenio_solicitud_id, motivo_sobrepago
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (cobro_id, monto, fecha, nro_op, notas, target_obra_id, gasto_nombre, gasto_expediente_imuh,
              cant_mon, cotiz, c_sol_id, motivo_sobrepago))
        new_id = cursor.lastrowid
        conn.commit()
        
    if nro_op:
        g_id = None
        if gasto_expediente_imuh:
            with db_session() as c:
                r = c.execute("SELECT id FROM gastos_funcionamiento WHERE expediente_imuh = ?", (gasto_expediente_imuh,)).fetchone()
                if r: g_id = r['id']
        register_or_update_op(nro_op, obra_id=target_obra_id, gasto_id=g_id)
        
    return new_id


def add_pago_fondos_propios(obra_id, monto, fecha, nro_op, observaciones,
                            cantidad_moneda_amortizada=None, cotizacion_pago=None,
                            convenio_solicitud_id=None, motivo_sobrepago=None):
    _validar_op_o_nota_db(nro_op, observaciones, "pago con fondos propios")
    if monto <= 0:
        raise ValueError("El monto a pagar debe ser mayor a 0.")
        
    with db_session() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT moneda_id FROM obras WHERE id = ?', (obra_id,))
        o_row = cursor.fetchone()
        o_moneda_id = o_row['moneda_id'] if o_row else 1
        
        cotiz = cotizacion_pago
        cant_mon = cantidad_moneda_amortizada
        if o_moneda_id == 1:
            cotiz = 1.0
            cant_mon = float(monto)
        else:
            if cotiz is None or cotiz <= 0:
                cotiz = 1.0
            if cant_mon is None:
                cant_mon = round(monto / cotiz, 6) if cotiz > 0 else 0.0

        cursor.execute('''
            INSERT INTO pagos_fondos_propios (
                obra_id, monto, fecha, nro_op, observaciones,
                cantidad_moneda_amortizada, cotizacion_pago, convenio_solicitud_id, motivo_sobrepago
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (obra_id, monto, fecha, nro_op, observaciones,
              cant_mon, cotiz, convenio_solicitud_id, motivo_sobrepago))
              
    if nro_op:
        register_or_update_op(nro_op, obra_id=obra_id)
```

---

## 💻 5. EXPOSICIÓN DEL CÓDIGO FUENTE DE LAS PÁGINAS (UI STREAMLIT)

### 5.1 Catálogo de Obras (`pages/2_Obras.py`)

A continuación se expone la estructura de tarjetas métricas, adicionales y tabla de trazabilidad OP por OP:

```python
# Extracto de pages/2_Obras.py: Tarjetas métricas bimonetarias
st.markdown("#### Posición Contractual y Financiera")
c_m1, c_m2, c_m3, c_m4 = st.columns(4)
if es_bimon:
    c_m1.metric(
        label=f"Contrato Total ({m_codigo})",
        value=f"{resumen['total_contratado_moneda']:,.2f} {m_simbolo}",
        help=f"Base: {resumen['monto_contrato_base_moneda']:,.2f} | Adicionales: {resumen['cantidad_adicionales_moneda']:,.2f}"
    )
    c_m2.metric(
        label="% Avance Contractual",
        value=f"{resumen['porcentaje_avance_moneda']:.1f}%",
        help=f"Amortizado: {resumen['total_moneda_amortizada']:,.2f} {m_codigo}"
    )
    c_m3.metric(
        label=f"Saldo Remanente ({m_codigo})",
        value=f"{resumen['saldo_moneda_remanente']:,.2f} {m_simbolo}",
        help="Pendiente de amortizar / certificar"
    )
    c_m4.metric(
        label="Desembolsos Totales (Banco)",
        value=utils.format_currency_ar(resumen['total_pagado_efectivo_ars']),
        delta=f"Indexación: {utils.format_currency_ar(resumen['resultado_indexacion_ars'])}",
        delta_color="normal",
        help="El badge muestra el Resultado por Indexación acumulado (Total Pagado - Costo Base Histórico FIFO)."
    )
else:
    c_m1.metric(
        label="Monto Contrato ($)",
        value=utils.format_currency_ar(resumen['total_costo_base_contratado_ars'])
    )
    c_m2.metric(
        label="% Avance Financiero",
        value=f"{resumen['porcentaje_avance_moneda']:.1f}%"
    )
    c_m3.metric(
        label="Saldo Disponible ($)",
        value=utils.format_currency_ar(resumen['saldo_moneda_remanente'])
    )
    c_m4.metric(
        label="Total Pagado ($)",
        value=utils.format_currency_ar(resumen['total_pagado_efectivo_ars'])
    )
```

```python
# Extracto de pages/2_Obras.py: Sección de Tramos Contractuales y Trazabilidad OP por OP
if es_bimon:
    st.markdown("---")
    st.subheader(f"📑 Tramos Contractuales y Posición FIFO ({m_codigo})")
    st.caption("Consolidación cronológica de tramos y amortización bajo regla estricta FIFO.")
    if resumen and resumen.get('tramos'):
        tramos_data = []
        for t in resumen['tramos']:
            tramos_data.append({
                "Tramo": t['tipo'],
                "Resolución": t['nro_resolucion'],
                "Fecha": t['fecha'],
                f"Total ({m_codigo})": f"{t['cantidad_moneda']:,.2f}",
                "Cotiz. Base": f"${t['cotizacion_base']:,.2f}",
                "Costo Base ($ ARS)": utils.format_currency_ar(t['monto_ars']),
                f"Amortizado ({m_codigo})": f"{t['moneda_amortizada']:,.2f}",
                "Costo Base Amortizado ($)": utils.format_currency_ar(t['costo_base_amortizado_ars']),
                f"Saldo Remanente ({m_codigo})": f"{t['saldo_moneda']:,.2f}"
            })
        st.dataframe(tramos_data, use_container_width=True)

st.markdown("---")
st.subheader("🔍 Trazabilidad de Pagos e Indexación por Orden de Pago")
st.caption("Detalle comprobante por comprobante de los desembolsos imputados al contrato de la obra.")
pagos_detalle = db.get_pagos_detalle_por_obra(obra_id)
if pagos_detalle:
    tabla_pagos = []
    for p in pagos_detalle:
        tabla_pagos.append({
            "Fecha": p.get('fecha'),
            "N° OP": p.get('nro_op') or 'Sin OP',
            "Fuente": p.get('fuente_descripcion') or p.get('tipo_fuente'),
            "Total Pagado ($ ARS)": utils.format_currency_ar(p.get('monto_ars') or 0.0),
            f"Amortizado ({m_codigo})": f"{p.get('cantidad_moneda_amortizada', 0.0):,.2f}",
            "Cotización OP": f"${p.get('cotizacion_pago', 1.0):,.2f}",
            "Costo Base FIFO ($)": utils.format_currency_ar(p.get('costo_base_ars') or 0.0),
            "Resultado por Indexación ($)": utils.format_currency_ar(p.get('resultado_indexacion_ars') or 0.0),
            "Motivo Sobrepago / Notas": p.get('motivo_sobrepago') or p.get('notas') or '-'
        })
    st.dataframe(tabla_pagos, use_container_width=True)
```

```python
# Extracto de pages/2_Obras.py: Bloqueo de cambio de moneda y rectificación de cotización base
tiene_pagos_obra = bool(resumen and (resumen.get('total_pagado_efectivo_ars', 0.0) > 0 or resumen.get('total_moneda_amortizada', 0.0) > 0))

# 1. Bloqueo de selectbox de Moneda Contractual si ya registra pagos
e_moneda_id = st.selectbox(
    "Moneda Contractual",
    options=list(monedas_dict.keys()),
    format_func=lambda x: monedas_dict[x],
    index=list(monedas_dict.keys()).index(curr_mon_id),
    disabled=tiene_pagos_obra,
    help="Bloqueado porque la obra ya registra pagos u órdenes de pago emitidas." if tiene_pagos_obra else None,
    key="edit_moneda_obra"
)
if tiene_pagos_obra:
    st.caption("🔒 *La moneda contractual no puede modificarse porque la obra ya registra pagos u órdenes de pago.*")

# 2. Guarda UI para rectificación de Cotización Base Inicial
cambia_cotiz = (abs(e_cotiz_base - old_cotiz_base) > 0.0001)
if tiene_pagos_obra and cambia_cotiz:
    st.warning("⚠️ **Atención:** Modificar la cotización base inicial recalculará retroactivamente el Costo Base y el Resultado por Indexación de todos los pagos registrados.")
    confirmar_rectif_cotiz = st.checkbox("Confirmo la rectificación de la cotización base inicial", key=f"chk_rectif_{obra_id}")
    motivo_rectif = st.text_input("Motivo / Justificación obligatoria de la rectificación *", key=f"motivo_rectif_{obra_id}")

# 3. Invocación segura en guardado persistiendo motivo en notas_contrato
if st.button("Guardar Cambios", key="btn_save_obra_edit", type="primary"):
    if tiene_pagos_obra and cambia_cotiz and not confirmar_rectif_cotiz:
        st.error("Debe confirmar la rectificación de la cotización base para continuar.")
    elif tiene_pagos_obra and cambia_cotiz and (not motivo_rectif or not motivo_rectif.strip()):
        st.error("Debe ingresar el motivo / justificación obligatoria de la rectificación.")
    else:
        db.update_obra(
            ...,
            motivo_rectificacion=motivo_rectif.strip() if motivo_rectif else None
        )
        db.update_monto_contrato_obra(
            ...,
            motivo_rectificacion=motivo_rectif.strip() if motivo_rectif else None
        )
```

### 5.2 Fin Original (`components/tab_distribuir.py`)

Fragmento de la integración bimonetaria y guarda de sobrepago:

```python
# Verificaciones Bimonetarias y Sobrepago en Fin Original
cant_mon_pago = monto_nuevo_fo
cotiz_pago = 1.0
chk_sp = {'es_sobrepago': False, 'mensaje': ''}

if target_obra_id:
    resumen_ob = db.get_resumen_contrato_obra(target_obra_id)
    if resumen_ob and resumen_ob['es_bimonetaria']:
        cod_m = resumen_ob['moneda_codigo']
        is_conv = (c_sel.get('origen_tipo') == 'convenio' or c_sel.get('convenio_solicitud_id') is not None)
        if is_conv:
            cotiz_display = float(c_sel.get('cotizacion_cobro') or c_sel.get('cotizacion_solicitud') or 1.0)
            cant_mon_pago = round(monto_nuevo_fo / cotiz_display, 6) if cotiz_display > 0 else 0.0
            st.info(f"ℹ️ **Imputación automática:** Amortiza **{cant_mon_pago:,.2f} {cod_m}** a cotización **${cotiz_display:,.2f}** heredada del Certificado de Convenio.")
        else:
            c_cot1, c_cot2 = st.columns(2)
            cotiz_pago = c_cot1.number_input(
                f"Cotización OP ($ ARS por {cod_m}) *",
                min_value=0.0001,
                step=10.0,
                value=float(resumen_ob.get('cotizacion_base_contrato') or 1.0),
                key=f"cotiz_fo_input_{c_sel_id}",
                on_change=keep_fo_open
            )
            cant_mon_pago = round(monto_nuevo_fo / cotiz_pago, 6) if cotiz_pago > 0 else 0.0
            c_cot2.write(f"**Amortiza contractualmente:**\n\n`{cant_mon_pago:,.2f} {cod_m}`")
            
        chk_sp = db.check_sobrepago_obra(target_obra_id, nuevo_monto_pesos=monto_nuevo_fo, nueva_cantidad_moneda=cant_mon_pago)
    else:
        chk_sp = db.check_sobrepago_obra(target_obra_id, nuevo_monto_pesos=monto_nuevo_fo)

confirmar_sobrepago_fo = True
motivo_sp_fo = None
if chk_sp.get('es_sobrepago'):
    st.error(f"⚠️ **Atención:** {chk_sp['mensaje']}")
    confirmar_sobrepago_fo = st.checkbox("Confirmo que deseo sobrepagar el contrato de la obra", key=f"confirmar_sobrepago_fo_{c_sel_id}", on_change=keep_fo_open)
    motivo_sp_fo = st.text_input("Motivo / Justificación obligatoria del Sobrepago *", key=f"motivo_sp_fo_{c_sel_id}", on_change=keep_fo_open)

if st.button("Guardar Pago", key=f"btn_save_fo_{c_sel_id}"):
    err_op = _validar_op_y_notas(op_nuevo_fo, notas_nuevo_fo, confirmado=confirmar_sin_op_fo)
    if not target_obra_id and len(obras_del_decreto) >= 1:
        st.error("Debe seleccionar una obra a la que se imputará este pago.")
    elif err_op:
        st.error(err_op)
    elif monto_nuevo_fo <= 0:
        st.error("El monto debe ser mayor a 0.")
    elif chk_sp.get('es_sobrepago') and not confirmar_sobrepago_fo:
        st.error("Debe confirmar el sobrepago para continuar.")
    elif chk_sp.get('es_sobrepago') and (not motivo_sp_fo or not motivo_sp_fo.strip()):
        st.error("Debe ingresar el motivo / justificación obligatoria del sobrepago.")
    else:
        nuevo_fo = val_fin + monto_nuevo_fo
        db.upsert_distribucion(c_sel_id, nuevo_fo, val_res, val_not)
        is_conv_bim = bool(resumen_ob and resumen_ob['es_bimonetaria'] and is_conv)
        db.add_fin_original_uso(
            cobro_id=c_sel_id,
            monto=monto_nuevo_fo,
            fecha=fecha_nuevo_fo.strftime('%Y-%m-%d'),
            nro_op=op_nuevo_fo.strip() if op_nuevo_fo.strip() else None,
            notas=notas_nuevo_fo,
            obra_id=target_obra_id,
            cantidad_moneda_amortizada=None if is_conv_bim else cant_mon_pago,
            cotizacion_pago=None if is_conv_bim else cotiz_pago,
            motivo_sobrepago=motivo_sp_fo.strip() if motivo_sp_fo else None
        )
        st.session_state['success_msg_dist2'] = "Pago a Obra Original registrado."
        st.rerun()
```

### 5.3 Pagos con Fondos Propios (`pages/4_Pagos_Fondos_Propios.py`)

A continuación se transcribe la sección de imputación bimonetaria, cotización de la OP, amortización en unidades contractuales, guarda de sobrepago y persistencia con motivo obligatorio en la base de datos:

```python
# Extracto de pages/4_Pagos_Fondos_Propios.py: Formulario bimonetario y guarda de sobrepago
# Parámetros bimonetarios si la obra no es en Pesos
obra_sel = db.get_obra(obra_id) if obra_id else None
resumen_obra = db.get_resumen_contrato_obra(obra_id) if obra_id else None
es_bimon = resumen_obra['es_bimonetaria'] if resumen_obra else False

cant_moneda_amort = monto
cotiz_pago = 1.0

if es_bimon and resumen_obra:
    cod_mon = resumen_obra['moneda_codigo']
    st.markdown("---")
    st.markdown(f"#### Imputación Contractual en Moneda de Origen ({cod_mon})")
    c_bim1, c_bim2 = st.columns(2)
    cotiz_pago = c_bim1.number_input(
        f"Cotización de la OP ($ ARS por {cod_mon}) *",
        min_value=0.0001,
        step=10.0,
        value=float(resumen_obra.get('cotizacion_base_contrato') or 1.0),
        help="Cotización vigente al momento del libramiento de la Orden de Pago para amortizar unidades contractuales."
    )
    cant_moneda_amort = round(monto / cotiz_pago, 6) if cotiz_pago > 0 else 0.0
    c_bim2.info(f"💡 **Amortización Contractual:** `{cant_moneda_amort:,.2f} {cod_mon}`")

st.divider()

# Verificación estricta de sobrepago bifurcada
chk_sp = {'es_sobrepago': False, 'mensaje': ''}
if obra_id:
    if es_bimon:
        chk_sp = db.check_sobrepago_obra(obra_id, nuevo_monto_pesos=monto, nueva_cantidad_moneda=cant_moneda_amort)
    else:
        chk_sp = db.check_sobrepago_obra(obra_id, nuevo_monto_pesos=monto)
        
confirmar_sobrepago = True
motivo_sobrepago = None
if chk_sp.get('es_sobrepago'):
    st.error(f"⚠️ **Atención:** {chk_sp['mensaje']}")
    confirmar_sobrepago = st.checkbox("Confirmo que deseo sobrepagar el contrato de la obra", key="chk_sobrepago_fp")
    motivo_sobrepago = st.text_input("Motivo / Justificación obligatoria del Sobrepago *", key="motivo_sp_fp")
    
if st.button("Registrar Adelanto", type="primary"):
    try:
        if not nro_op.strip() and not confirmar_sin_op:
            raise ValueError("Debe tildar la confirmación si no provee un número de Orden de Pago.")
        if chk_sp.get('es_sobrepago') and not confirmar_sobrepago:
            raise ValueError("Debe confirmar el sobrepago marcando la casilla correspondiente.")
        if chk_sp.get('es_sobrepago') and (not motivo_sobrepago or not motivo_sobrepago.strip()):
            raise ValueError("Debe ingresar el motivo / justificación obligatoria del sobrepago.")
            
        db.add_pago_fondos_propios(
            obra_id=obra_id,
            monto=monto,
            fecha=fecha.strftime('%Y-%m-%d'),
            nro_op=nro_op.strip() if nro_op.strip() else None,
            observaciones=observaciones.strip() if observaciones.strip() else None,
            cantidad_moneda_amortizada=cant_moneda_amort,
            cotizacion_pago=cotiz_pago,
            motivo_sobrepago=motivo_sobrepago.strip() if motivo_sobrepago else None
        )
        st.session_state['pago_fp_registrado_ok'] = True
        st.rerun()
    except ValueError as e:
        st.error(str(e))
```

---

## 🧪 6. EVIDENCIA DE PRUEBAS AUTOMATIZADAS (SUITE DE INTEGRACIÓN)

### 6.1 Código de la Suite de Pruebas `test_obras_bimonetarias.py`

La suite cubre rigurosamente los 6 casos de prueba acordados:

```python
import os
import sys
import unittest
import datetime
import database as db

ORIGINAL_DB_PATH = db.DB_PATH
TEST_DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "test_decretometro_bimonetario.db")

class TestObrasBimonetarias(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if os.path.exists(TEST_DB_PATH):
            try: os.remove(TEST_DB_PATH)
            except OSError: pass
        db.DB_PATH = TEST_DB_PATH
        db.init_db()

    @classmethod
    def tearDownClass(cls):
        db.DB_PATH = ORIGINAL_DB_PATH
        if os.path.exists(TEST_DB_PATH):
            try: os.remove(TEST_DB_PATH)
            except OSError: pass

    def test_01_alta_obra_uvis(self):
        """1. Alta de Obra en UVIs: 50.000 UVIs a cotización base $1.000 (Base inicial: $50.000.000 ARS)."""
        obra_id = db.add_obra(
            nombre="Obra Bimonetaria UVI Test",
            expediente_imuh="8009901-I-2026",
            moneda_id=3, # UVI
            monto_contrato_moneda=50000.0,
            cotizacion_base_contrato=1000.0,
            fecha_contrato="2026-01-15",
            notas_contrato="Licitación pública en UVIs Ley 27.271"
        )
        self.assertIsNotNone(obra_id)
        
        obra = db.get_obra(obra_id)
        self.assertEqual(obra['moneda_id'], 3)
        self.assertEqual(obra['moneda_codigo'], 'UVI')
        self.assertEqual(obra['monto_contrato_moneda'], 50000.0)
        self.assertEqual(obra['cotizacion_base_contrato'], 1000.0)
        self.assertEqual(obra['monto_contrato'], 50000000.0)
        
        resumen = db.get_resumen_contrato_obra(obra_id)
        self.assertTrue(resumen['es_bimonetaria'])
        self.assertEqual(resumen['total_contratado_moneda'], 50000.0)
        self.assertEqual(resumen['total_costo_base_contratado_ars'], 50000000.0)
        self.assertEqual(resumen['total_moneda_amortizada'], 0.0)
        self.assertEqual(resumen['saldo_moneda_remanente'], 50000.0)
        self.assertEqual(resumen['resultado_indexacion_ars'], 0.0)
        self.assertEqual(len(resumen['tramos']), 1)
        self.assertEqual(resumen['tramos'][0]['tipo'], 'Contrato Base')

    def test_02_adicional_obra(self):
        """2. Adicional de Obra: 5.000 UVIs a cotización $1.400 por Resol. N° 10/2026."""
        obra = db.get_obra_by_expediente("8009901-I-2026")
        obra_id = obra['id']
        
        adic_id = db.add_obra_adicional(
            obra_id=obra_id,
            nro_resolucion="Resol. 10/2026",
            fecha="2026-04-10",
            cantidad_moneda=5000.0,
            cotizacion_base=1400.0,
            motivo="Ampliación de obra y redeterminación de ítems"
        )
        self.assertIsNotNone(adic_id)
        
        adicionales = db.get_obra_adicionales(obra_id)
        self.assertEqual(len(adicionales), 1)
        self.assertEqual(adicionales[0]['nro_resolucion'], "Resol. 10/2026")
        self.assertEqual(adicionales[0]['cantidad_moneda'], 5000.0)
        self.assertEqual(adicionales[0]['cotizacion_base'], 1400.0)
        self.assertEqual(adicionales[0]['monto_equivalente_ars'], 7000000.0)
        
        resumen = db.get_resumen_contrato_obra(obra_id)
        self.assertEqual(resumen['total_contratado_moneda'], 55000.0)
        self.assertEqual(resumen['total_costo_base_contratado_ars'], 57000000.0)
        self.assertEqual(len(resumen['tramos']), 2)

    def test_03_pago_desde_convenio_fifo_test3(self):
        """3. Pago desde Convenio (Test 3 exacto):
        Pago de 20.000 UVIs a cotización de certificado $1.250 ($25.000.000 ARS pagados).
        Bajo FIFO: Amortiza 20.000 UVIs del Tramo 0 ($1.000). Costo base = $20.000.000 ARS.
        Resultado por Indexación verificado: $25.000.000 - $20.000.000 = $5.000.000 ARS exactos.
        """
        obra = db.get_obra_by_expediente("8009901-I-2026")
        obra_id = obra['id']
        
        conv_id = db.add_convenio(
            nro_convenio="CONV-UVI-TEST",
            ente_financiador="Nación / Hábitat",
            nombre_convenio="Financiamiento Obra Test",
            nro_expediente="8009901-I-2026",
            fecha_firma="2026-01-20",
            moneda_id=3,
            monto_pactado_moneda=50000.0,
            cotizacion_base=1000.0,
            monto_equivalente_ars=50000000.0
        )
        
        db.add_obra_to_convenio(
            convenio_id=conv_id,
            obra_id=obra_id,
            monto_pactado_moneda=50000.0,
            monto_equivalente_ars=50000000.0,
            porcentaje=100.0
        )
        
        sol_id = db.add_solicitud_convenio(
            convenio_id=conv_id,
            obra_id=obra_id,
            nro_certificado="Certif. 01",
            periodo="2026-02",
            cantidad_moneda=20000.0,
            cotizacion_solicitud=1250.0,
            monto_solicitado_ars=25000000.0,
            fecha_solicitud="2026-02-15"
        )
        
        cobro_id = db.add_cobro(
            monto=25000000.0,
            fecha="2026-02-28",
            convenio_solicitud_id=sol_id,
            origen_tipo='convenio',
            moneda_origen_id=3,
            cantidad_moneda_origen=20000.0,
            cotizacion_cobro=1250.0
        )
        
        db.upsert_distribucion(cobro_id, 25000000.0, 0.0, "Distribución a obra original")
        
        uso_id = db.add_fin_original_uso(
            cobro_id=cobro_id,
            monto=25000000.0,
            fecha="2026-03-05",
            nro_op="OP-1001",
            obra_id=obra_id
        )
        self.assertIsNotNone(uso_id)
        
        resumen = db.get_resumen_contrato_obra(obra_id)
        self.assertEqual(resumen['total_moneda_amortizada'], 20000.0)
        self.assertEqual(resumen['saldo_moneda_remanente'], 35000.0)
        self.assertEqual(resumen['total_pagado_efectivo_ars'], 25000000.0)
        self.assertEqual(resumen['costo_base_amortizado_ars'], 20000000.0)
        
        # EXACTITUD CLAUDE TEST 3: $25.000.000 - $20.000.000 = $5.000.000 ARS
        self.assertEqual(resumen['resultado_indexacion_ars'], 5000000.0)
        
        detalle_ops = db.get_pagos_detalle_por_obra(obra_id)
        self.assertEqual(len(detalle_ops), 1)
        op1 = detalle_ops[0]
        self.assertEqual(op1['nro_op'], "OP-1001")
        self.assertEqual(op1['cantidad_moneda_amortizada'], 20000.0)
        self.assertEqual(op1['cotizacion_pago'], 1250.0)
        self.assertEqual(op1['costo_base_ars'], 20000000.0)
        self.assertEqual(op1['resultado_indexacion_ars'], 5000000.0)

    def test_04_pago_desde_fondos_propios(self):
        """4. Pago desde Fondos Propios:
        Pago de $13.000.000 ARS a cotización $1.300 (amortiza 10.000 UVIs del Tramo 0).
        """
        obra = db.get_obra_by_expediente("8009901-I-2026")
        obra_id = obra['id']
        
        db.add_pago_fondos_propios(
            obra_id=obra_id,
            monto=13000000.0,
            fecha="2026-03-20",
            nro_op="OP-FP-2001",
            observaciones="Adelanto por fondos propios certificado 2",
            cantidad_moneda_amortizada=10000.0,
            cotizacion_pago=1300.0
        )
        
        resumen = db.get_resumen_contrato_obra(obra_id)
        self.assertEqual(resumen['total_moneda_amortizada'], 30000.0)
        self.assertEqual(resumen['saldo_moneda_remanente'], 25000.0)
        self.assertEqual(resumen['total_pagado_efectivo_ars'], 38000000.0)
        self.assertEqual(resumen['costo_base_amortizado_ars'], 30000000.0)
        self.assertEqual(resumen['resultado_indexacion_ars'], 8000000.0)

    def test_05_guarda_sobrepago_uvis(self):
        """5. Guarda de Sobrepago en UVIs:
        Intentar pagar 30.000 UVIs cuando el remanente total es de 25.000 UVIs.
        Verificar bloqueo y registro con motivo obligatorio.
        """
        obra = db.get_obra_by_expediente("8009901-I-2026")
        obra_id = obra['id']
        
        chk = db.check_sobrepago_obra(obra_id, nuevo_monto_pesos=45000000.0, nueva_cantidad_moneda=30000.0)
        self.assertTrue(chk['es_sobrepago'])
        self.assertTrue(chk['es_bimonetaria'])
        self.assertEqual(chk['unidad'], 'UVI')
        self.assertEqual(chk['tope'], 55000.0)
        self.assertEqual(chk['acumulado_previo'], 30000.0)
        self.assertEqual(chk['nuevo_total'], 60000.0)
        self.assertEqual(chk['exceso'], 5000.0)
        self.assertIn("superando el contrato total", chk['mensaje'])
        
        motivo = "Mayor obra imprevista autorizada en trámite de redeterminación"
        db.add_pago_fondos_propios(
            obra_id=obra_id,
            monto=45000000.0,
            fecha="2026-05-10",
            nro_op="OP-FP-2002",
            observaciones="Pago con sobrepago justificado",
            cantidad_moneda_amortizada=30000.0,
            cotizacion_pago=1500.0,
            motivo_sobrepago=motivo
        )
        
        pagos = db.get_pagos_fondos_propios(obra_id)
        pago_sp = next(p for p in pagos if p['nro_op'] == "OP-FP-2002")
        self.assertEqual(pago_sp['motivo_sobrepago'], motivo)

    def test_06_obra_en_pesos_inmutabilidad(self):
        """6. Prueba de Obras en Pesos:
        Crear y editar obra en ARS, ratificar que monto_contrato_moneda = monto_contrato
        y que la guarda valida contra pesos sin disparar cálculos de UVIs.
        """
        obra_ars_id = db.add_obra(
            nombre="Obra Tradicional Pesos",
            expediente_imuh="8009902-I-2026",
            moneda_id=1,
            monto_contrato_moneda=10000000.0
        )
        self.assertIsNotNone(obra_ars_id)
        
        obra_ars = db.get_obra(obra_ars_id)
        self.assertEqual(obra_ars['moneda_id'], 1)
        self.assertEqual(obra_ars['moneda_codigo'], 'ARS')
        self.assertEqual(obra_ars['monto_contrato'], 10000000.0)
        self.assertEqual(obra_ars['monto_contrato_moneda'], 10000000.0)
        self.assertEqual(obra_ars['cotizacion_base_contrato'], 1.0)
        
        resumen_ars = db.get_resumen_contrato_obra(obra_ars_id)
        self.assertFalse(resumen_ars['es_bimonetaria'])
        self.assertEqual(resumen_ars['total_costo_base_contratado_ars'], 10000000.0)
        self.assertEqual(resumen_ars['resultado_indexacion_ars'], 0.0)
        
        chk_ars_ok = db.check_sobrepago_obra(obra_ars_id, nuevo_monto_pesos=8000000.0)
        self.assertFalse(chk_ars_ok['es_sobrepago'])
        
        chk_ars_exceso = db.check_sobrepago_obra(obra_ars_id, nuevo_monto_pesos=12000000.0)
        self.assertTrue(chk_ars_exceso['es_sobrepago'])
        self.assertFalse(chk_ars_exceso['es_bimonetaria'])
        self.assertEqual(chk_ars_exceso['unidad'], 'ARS')
        self.assertEqual(chk_ars_exceso['exceso'], 2000000.0)

    def test_07_fallback_cotizacion_solicitud_cobro_vacio(self):
        """7. Prueba solicitada por Claude:
        Cobro de convenio con cotizacion_cobro vacía (None) y cotizacion_solicitud cargada ($1.350).
        Al invocar add_fin_original_uso con cantidad_moneda_amortizada=None y cotizacion_pago=None
        (como hace la UI para pagos de convenio bimonetario), el backend deriva exitosamente
        cotizacion_pago = 1350.0 y amortiza exactamente 10.000 UVIs ($13.500.000 / $1.350).
        """
        obra_id = db.add_obra(
            nombre="Obra Convenio Fallback UVI",
            expediente_imuh="8009903-I-2026",
            moneda_id=3,
            monto_contrato_moneda=50000.0,
            cotizacion_base_contrato=1000.0
        )
        conv_id = db.add_convenio(
            nro_convenio="CONV-FALLBACK-01",
            ente_financiador="Provincia",
            nombre_convenio="Convenio UVI Fallback",
            nro_expediente="8009903-I-2026",
            fecha_firma="2026-03-01",
            moneda_id=3,
            monto_pactado_moneda=50000.0,
            cotizacion_base=1000.0,
            monto_equivalente_ars=50000000.0
        )
        db.add_obra_to_convenio(
            convenio_id=conv_id,
            obra_id=obra_id,
            monto_pactado_moneda=50000.0,
            monto_equivalente_ars=50000000.0,
            porcentaje=100.0
        )
        sol_id = db.add_solicitud_convenio(
            convenio_id=conv_id,
            obra_id=obra_id,
            nro_certificado="Certif. Fallback 01",
            periodo="2026-03",
            cantidad_moneda=10000.0,
            cotizacion_solicitud=1350.0,
            monto_solicitado_ars=13500000.0,
            fecha_solicitud="2026-03-15"
        )
        # Cobro con cotizacion_cobro = None (vacío)
        cobro_id = db.add_cobro(
            monto=13500000.0,
            fecha="2026-03-25",
            convenio_solicitud_id=sol_id,
            origen_tipo='convenio',
            moneda_origen_id=3,
            cantidad_moneda_origen=10000.0,
            cotizacion_cobro=None
        )
        db.upsert_distribucion(cobro_id, 13500000.0, 0.0, "Distribución completa")

        # Simular guardado desde tab_distribuir.py con is_conv_bim=True
        uso_id = db.add_fin_original_uso(
            cobro_id=cobro_id,
            monto=13500000.0,
            fecha="2026-03-28",
            nro_op="OP-FALLBACK-01",
            obra_id=obra_id,
            cantidad_moneda_amortizada=None,
            cotizacion_pago=None
        )
        self.assertIsNotNone(uso_id)

        # Verificar derivación en base de datos
        with db.db_session() as conn:
            row = conn.execute("SELECT cotizacion_pago, cantidad_moneda_amortizada FROM cobro_fin_original_usos WHERE id = ?", (uso_id,)).fetchone()
            self.assertEqual(row['cotizacion_pago'], 1350.0)
            self.assertEqual(row['cantidad_moneda_amortizada'], 10000.0)

        # Verificar resumen del contrato
        resumen = db.get_resumen_contrato_obra(obra_id)
        self.assertEqual(resumen['total_moneda_amortizada'], 10000.0)
        self.assertEqual(resumen['saldo_moneda_remanente'], 40000.0)

    def test_08_guarda_reducir_contrato_uvis(self):
        """8. Guarda contra reducir contrato en UVIs por debajo de lo amortizado:
        Obra con 50.000 UVIs contratadas y 10.000 UVIs ya amortizadas.
        Intentar reducir a 8.000 UVIs debe arrojar ValueError en update_monto_contrato_obra
        y en update_obra. Actualizar a 40.000 UVIs debe permitirse.
        """
        obra = db.get_obra_by_expediente("8009903-I-2026")
        obra_id = obra['id']

        # 1. Intentar reducir a 8.000 UVIs en update_monto_contrato_obra
        with self.assertRaises(ValueError) as ctx:
            db.update_monto_contrato_obra(
                obra_id=obra_id,
                nuevo_monto=8000000.0,
                nuevo_monto_moneda=8000.0,
                nueva_cotizacion_base=1000.0
            )
        self.assertIn("por debajo del total ya amortizado", str(ctx.exception))

        # 2. Intentar reducir a 8.000 UVIs en update_obra
        with self.assertRaises(ValueError) as ctx2:
            db.update_obra(
                obra_id=obra_id,
                nombre=obra['nombre'],
                expediente_imuh=obra['expediente_imuh'],
                activa=1,
                moneda_id=3,
                monto_contrato_moneda=8000.0,
                cotizacion_base_contrato=1000.0
            )
        self.assertIn("por debajo del total ya amortizado", str(ctx2.exception))

        # 3. Actualizar a 40.000 UVIs (> 10.000 amortizadas) -> debe permitirse
        db.update_monto_contrato_obra(
            obra_id=obra_id,
            nuevo_monto=40000000.0,
            nuevo_monto_moneda=40000.0,
            nueva_cotizacion_base=1000.0
        )
        resumen = db.get_resumen_contrato_obra(obra_id)
        self.assertEqual(resumen['total_contratado_moneda'], 40000.0)
        self.assertEqual(resumen['saldo_moneda_remanente'], 30000.0)

    def test_09_bloqueo_cambio_moneda_con_pagos(self):
        """9. Bloqueo de cambio de moneda si la obra ya tiene pagos:
        La obra 8009903-I-2026 ya posee 10.000 UVIs amortizadas.
        Intentar cambiar moneda_id a 1 (ARS) debe arrojar ValueError.
        """
        obra = db.get_obra_by_expediente("8009903-I-2026")
        obra_id = obra['id']

        with self.assertRaises(ValueError) as ctx:
            db.update_obra(
                obra_id=obra_id,
                nombre=obra['nombre'],
                expediente_imuh=obra['expediente_imuh'],
                activa=1,
                moneda_id=1, # Intentar cambiar a ARS
                monto_contrato_moneda=40000.0,
                cotizacion_base_contrato=1000.0
            )
        self.assertIn("No se puede modificar la moneda de contratación", str(ctx.exception))

    def test_10_rectificacion_cotizacion_base_con_justificacion(self):
        """10. Rectificación de cotización base con pagos registrados:
        La obra posee pagos. Cambiar cotizacion_base_contrato sin motivo debe fallar.
        Con motivo justificado debe registrarse y asentar constancia en notas_contrato.
        """
        obra = db.get_obra_by_expediente("8009903-I-2026")
        obra_id = obra['id']

        # 1. Fallar si no se provee motivo
        with self.assertRaises(ValueError) as ctx:
            db.update_obra(
                obra_id=obra_id,
                nombre=obra['nombre'],
                expediente_imuh=obra['expediente_imuh'],
                activa=1,
                moneda_id=3,
                monto_contrato_moneda=40000.0,
                cotizacion_base_contrato=1050.0 # Cambia de 1000 a 1050
            )
        self.assertIn("motivo / justificación obligatoria", str(ctx.exception))

        # 2. Exitoso con motivo
        motivo = "Corrección de error material en transcripción del acta de licitación"
        db.update_obra(
            obra_id=obra_id,
            nombre=obra['nombre'],
            expediente_imuh=obra['expediente_imuh'],
            activa=1,
            moneda_id=3,
            monto_contrato_moneda=40000.0,
            cotizacion_base_contrato=1050.0,
            motivo_rectificacion=motivo
        )
        obra_mod = db.get_obra(obra_id)
        self.assertEqual(obra_mod['cotizacion_base_contrato'], 1050.0)
        self.assertIn("Rectificación Cotiz. Base", obra_mod['notas_contrato'])
        self.assertIn(motivo, obra_mod['notas_contrato'])

    def test_11_cotizacion_solicitud_presente_en_resumen_distribucion(self):
        """11. Verificación de columna cotizacion_solicitud en get_cobros_con_resumen_distribucion():
        Garantiza que la UI reciba la cotización de la solicitud para que no caiga a 1.0 en la guarda de sobrepago.
        """
        cobros = db.get_cobros_con_resumen_distribucion()
        self.assertTrue(len(cobros) > 0)
        cobro_conv = next((c for c in cobros if c.get('convenio_solicitud_id') is not None), None)
        self.assertIsNotNone(cobro_conv)
        self.assertIn('cotizacion_solicitud', cobro_conv)
        self.assertEqual(cobro_conv['cotizacion_solicitud'], 1350.0)

    def test_12_atomicidad_rectificacion_y_guarda_reduccion(self):
        """12. Atomicidad de orden de operaciones en update_monto_contrato_obra:
        Si se intenta rectificar la cotización base pero la operación es rechazada por la guarda de
        reducción (ej. contrato menor a lo ya amortizado), la constancia de auditoría NO debe escribirse
        ni dejar notas fantasma en la base de datos.
        """
        obra = db.get_obra_by_expediente("8009903-I-2026")
        obra_id = obra['id']
        notas_antes = obra['notas_contrato'] or ""
        cotiz_antes = obra['cotizacion_base_contrato']

        # 1. Intentar rectificar a 1.100 y reducir a 5.000 UVIs (< 10.000 amortizadas) -> debe fallar
        motivo_rechazado = "Intento inválido que no debe registrar constancia"
        with self.assertRaises(ValueError) as ctx:
            db.update_monto_contrato_obra(
                obra_id=obra_id,
                nuevo_monto=5500000.0,
                nuevo_monto_moneda=5000.0,
                nueva_cotizacion_base=1100.0,
                motivo_rectificacion=motivo_rechazado
            )
        self.assertIn("por debajo del total ya amortizado", str(ctx.exception))

        # Verificar que la base de datos NO fue modificada (cero constancia fantasma)
        obra_post_fallo = db.get_obra(obra_id)
        self.assertEqual(obra_post_fallo['notas_contrato'], notas_antes)
        self.assertEqual(obra_post_fallo['cotizacion_base_contrato'], cotiz_antes)
        self.assertNotIn(motivo_rechazado, obra_post_fallo['notas_contrato'] or "")

        # 2. Rectificación válida con contrato permitido (35.000 UVIs > 10.000 amortizadas)
        motivo_valido = "Rectificación atómica válida con contrato permitido"
        db.update_monto_contrato_obra(
            obra_id=obra_id,
            nuevo_monto=38500000.0,
            nuevo_monto_moneda=35000.0,
            nueva_cotizacion_base=1100.0,
            motivo_rectificacion=motivo_valido
        )
        obra_post_ok = db.get_obra(obra_id)
        self.assertEqual(obra_post_ok['cotizacion_base_contrato'], 1100.0)
        self.assertIn(motivo_valido, obra_post_ok['notas_contrato'])
        self.assertIn("1,100.00", obra_post_ok['notas_contrato'])

if __name__ == '__main__':
    unittest.main()
```

### 6.2 Log Verbatim de Ejecución Completa de Pytest

```text
PS C:\Users\bornemanns\.gemini\antigravity-ide\scratch\decretometro_2.0> python -m pytest test_obras_bimonetarias.py test_compensacion_convenio.py test_convenios_flujo.py -v
============================= test session starts =============================
platform win32 -- Python 3.13.5, pytest-9.1.1, pluggy-1.6.0 -- C:\Users\bornemanns\AppData\Local\Programs\Python\Python313\python.exe
cachedir: .pytest_cache
rootdir: C:\Users\bornemanns\.gemini\antigravity-ide\scratch\decretometro_2.0
plugins: anyio-4.14.2
collecting ... collected 14 items

test_obras_bimonetarias.py::TestObrasBimonetarias::test_01_alta_obra_uvis PASSED [  7%]
test_obras_bimonetarias.py::TestObrasBimonetarias::test_02_adicional_obra PASSED [ 14%]
test_obras_bimonetarias.py::TestObrasBimonetarias::test_03_pago_desde_convenio_fifo_test3 PASSED [ 21%]
test_obras_bimonetarias.py::TestObrasBimonetarias::test_04_pago_desde_fondos_propios PASSED [ 28%]
test_obras_bimonetarias.py::TestObrasBimonetarias::test_05_guarda_sobrepago_uvis PASSED [ 35%]
test_obras_bimonetarias.py::TestObrasBimonetarias::test_06_obra_en_pesos_inmutabilidad PASSED [ 42%]
test_obras_bimonetarias.py::TestObrasBimonetarias::test_07_fallback_cotizacion_solicitud_cobro_vacio PASSED [ 50%]
test_obras_bimonetarias.py::TestObrasBimonetarias::test_08_guarda_reducir_contrato_uvis PASSED [ 57%]
test_obras_bimonetarias.py::TestObrasBimonetarias::test_09_bloqueo_cambio_moneda_con_pagos PASSED [ 64%]
test_obras_bimonetarias.py::TestObrasBimonetarias::test_10_rectificacion_cotizacion_base_con_justificacion PASSED [ 71%]
test_obras_bimonetarias.py::TestObrasBimonetarias::test_11_cotizacion_solicitud_presente_en_resumen_distribucion PASSED [ 78%]
test_obras_bimonetarias.py::TestObrasBimonetarias::test_12_atomicidad_rectificacion_y_guarda_reduccion PASSED [ 85%]
test_compensacion_convenio.py::TestCompensacionConvenio::test_flujo_completo_convenio_y_compensacion_cruzada PASSED [ 92%]
test_convenios_flujo.py::test_flujo_convenios_bimonetario PASSED         [100%]

============================= 14 passed in 11.58s =============================
```

---

## 🔎 7. GUÍA Y LISTA DE VERIFICACIÓN PARA LA AUDITORÍA DE CLAUDE

A fin de facilitar la emisión del dictamen de auditoría calificado, se pone a disposición de Claude el siguiente checklist técnico:

1. **Alineación de Metadatos y Schema:**
   - [x] Schema Version en producción es estrictamente `48`.
   - [x] La tabla `obra_adicionales` posee clave foránea hacia `obras(id)` con `ON DELETE CASCADE`.
   - [x] Las columnas `cantidad_moneda_amortizada`, `cotizacion_pago`, `convenio_solicitud_id` y `motivo_sobrepago` se integraron en `cobro_fin_original_usos` y `pagos_fondos_propios`.
2. **Gobernanza de Datos Históricos:**
   - [x] Las 52 obras históricas tienen `moneda_id = 1` (ARS) y cotización 1.0.
   - [x] Cero rotura en claves foráneas o relaciones preexistentes.
3. **Exactitud Matemática Contable:**
   - [x] Test 3 de Claude comprobado: Ante 20.000 UVIs a cotización \$1.250 (\$25M ARS), el Resultado por Indexación arroja **\$5.000.000 ARS exactos**.
   - [x] Suma algebraica de `resultado_indexacion_ars` de cada Orden de Pago coincide al centavo con el consolidado en `get_resumen_contrato_obra`.
4. **Control de Sobrefacturación y Reducción Indebida:**
   - [x] Las guardas bifurcadas no bloquean obras en UVIs por desfases nominales en pesos, evaluando estrictamente el cupo en unidades de contratación.
   - [x] El campo `motivo_sobrepago` persiste con valor no nulo cuando se autoriza un libramiento en exceso.
   - [x] **Guarda bimonetaria de reducción:** `update_monto_contrato_obra` y `update_obra` impiden reducir el contrato en UVIs por debajo del total ya amortizado (comprobado en Test 8).
5. **Robustez de Derivación e Integración UI-Backend:**
   - [x] **Fallback en Convenios Bimonetarios:** `tab_distribuir.py` delega pasando `None` a `cotizacion_pago` y `cantidad_moneda_amortizada`, permitiendo que el backend tome `cotizacion_solicitud` si `cotizacion_cobro` está vacía (comprobado en Test 7).
6. **Resolución de Observaciones Menores de Auditoría:**
   - [x] **Disponibilidad de `cotizacion_solicitud` en UI:** La consulta `get_cobros_con_resumen_distribucion()` proyecta explícitamente `cs.cotizacion_solicitud`, garantizando que la UI no caiga a 1.0 en la guarda de sobrepago (verificado en Test 11).
   - [x] **Inmutabilidad de Moneda Contractual con Pagos:** `update_obra` bloquea cualquier cambio de `moneda_id` en obras que ya registran pagos, deshabilitando también el control en el frontend (verificado en Test 9).
   - [x] **Pista de Auditoría para Rectificación de Cotización Base:** Modificar `cotizacion_base_contrato` en obras con pagos exige confirmación explícita y justificación obligatoria, asentando constancia en `notas_contrato` para el Tribunal de Cuentas (verificado en Test 10).
   - [x] **Atomicidad Transaccional de Rectificación:** `update_monto_contrato_obra` prepara la constancia en memoria y valida primero todas las guardas de reducción. Si se rechaza la operación, no se asienta ninguna constancia fantasma; si se aprueba, se persiste en un único `UPDATE` atómico (verificado en Test 12).
7. **No-Regresión:**
   - [x] La suite completa de 14 pruebas arroja `PASSED` al 100% (incluyendo convenios, compensaciones cruzadas, atomicidad y observaciones de auditoría).

---

*Fin del Informe de Implementación. Archivo generado para auditoría de Claude.*


