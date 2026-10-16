# 🏛️ INFORME DE AUDITORÍA INTEGRAL 360°: ARQUITECTURA, LÓGICA FINANCIERA Y SEGURIDAD
# SISTEMA: DECRETÓMETRO 2.0 (ESQUEMA v48)

- **Fecha de Auditoría:** 16/10/2026[cite: 1]
- **Destinatario:** Martín Rodríguez (Contador Público - UBA)[cite: 1]
- **Stack Auditado:** Python 3.x, Streamlit, SQLite (`decretometro.db` - 29 tablas, `schema_version` 48), ReportLab / FPDF, XlsxWriter[cite: 1].

---

## Sección 1: Resumen Ejecutivo y Diagnóstico General

El sistema **Decretómetro 2.0** (Esquema `v48`, 29 tablas operativas) presenta un modelado funcional alineado con las necesidades de control de gestión pública municipal: abarca desde la solicitud de financiamiento, promulgación de decretos y convenios multiobra bimonetarios (ARS, USD, UVIs Ley 27.271), hasta el cobro bancario, su distribución (Fin Original, Reserva, Desvíos), compensaciones y vínculo con Órdenes de Pago (`op_bejerman`)[cite: 1].

### 📊 Puntuación de Madurez del Sistema

| Dimensión Evaluada | Calificación | Nivel de Riesgo | Resumen del Estado Actual |
| :--- | :---: | :---: | :--- |
| **1. Arquitectura y Mantenibilidad** | **4.0 / 10** | 🟠 Alto | Monolito severo en `database.py`, funciones duplicadas que se pisan en memoria (`update_desvio`, `update_reserva_uso`) y acoplamiento directo entre UI y SQL[cite: 1]. |
| **2. Concurrencia, Transacciones y Seguridad** | **4.5 / 10** | 🔴 Crítico | Transacciones no atómicas (lecturas fuera de bloqueo `BEGIN IMMEDIATE`), `commits` intermedios prematuros, restauración de backups rota para la versión 48 y sobrecarga en el ciclo de `Inicio.py`[cite: 1]. |
| **3. Precisión Contable y Lógica Financiera** | **5.5 / 10** | 🔴 Crítico | Uso de coma flotante binaria (`REAL` / `float`) con tolerancias acumulables, desfasajes en ecuaciones de distribución/reserva, falta de control de tope en `recuperos_fondos_propios` y valuación UVI distorsionada en desvíos y fondos propios[cite: 1]. |

### 🔍 Diagnóstico Cualitativo General

* **Fortalezas Principales:**
  * **Activación de integridad referencial base:** La función `get_connection()` activa explícitamente `PRAGMA foreign_keys = ON;` en cada conexión creada y define un `CHECK` de exclusión mutua (`check_origen_exclusivo`) en la tabla `cobros` para impedir que un desembolso pertenezca simultáneamente a un decreto y a un convenio[cite: 1].
  * **Algoritmo FIFO para obras bimonetarias:** El diseño conceptual de `get_resumen_contrato_obra()` para imputar pagos cronológicamente contra el Contrato Base y los Adicionales de Obra en UVIs/USD separando el *Costo Base Histórico* del *Resultado por Indexación* es contablemente sólido[cite: 1].
  * **Trazabilidad documental obligatoria:** La exigencia a nivel base de datos (`_validar_op_o_nota_db`) de contar con un número de OP Bejerman o una observación justificada acota el registro de movimientos huérfanos[cite: 1].

* **Debilidades Críticas de Mayor Impacto:**
  * **Ecuaciones patrimoniales abiertas:** Un mismo cobro bancario puede distribuirse al 100% en Fin Original/Reserva/Desvíos y, al mismo tiempo, imputarse en `recuperos_fondos_propios` sin que el sistema descuente ni valide dicho recupero contra el monto del cobro, permitiendo **duplicar artificialmente la aplicación de un mismo ingreso bancario**[cite: 1].
  * **Discrepancia entre Dashboard y Reportes de Rendición:** La fórmula de saldo de reserva en `utils_reports.py` (`obtener_datos_composicion`) omite sumar los recuperos de desvíos iniciales que vuelven a reserva (`destino_tipo = 'reserva'`), provocando que el reporte PDF/Excel de composición de cuota no cuadre con el monto cobrado ni con el tablero principal[cite: 1].
  * **Restauración de Backups destructiva (`restore_backup`):** Mientras que `create_backup` copia las 29 tablas de la versión 48, `restore_backup` quedó congelada en una versión antigua de 15 tablas: si hoy se restaura un backup, **se pierden todos los convenios, UVIs, obras, proveedores y pagos con fondos propios**, o la operación aborta por violación de `CHECK` en `cobros`[cite: 1].

---

## Sección 2: Matriz de Hallazgos y Vulnerabilidades (Clasificada por Severidad)

### 🔴 Severidad Crítica (P0)

#### [HALLAZGO-01] Doble imputación de cobros por omisión de `recuperos_fondos_propios` y asimetría contable en saldos de Reserva y "Sin Distribuir"
- **Severidad:** Crítica (P0)
- **Categoría:** Lógica Financiera y UVIs
- **Ubicación:** `database.py` (`upsert_distribucion`, `add_desvio`, `update_desvio`, `add_recupero_fondos_propios`, `get_cobros_con_resumen_distribucion`) y `utils_reports.py` (`obtener_datos_composicion`)[cite: 1].
- **Impacto Contable / Financiero:** En contabilidad pública, la ecuación fundamental de todo ingreso bancario es:
  `Monto Cobrado = Fin Original + Reserva + Desvíos Netos + Recuperos Fondos Propios + Saldo Sin Distribuir`
  Actualmente existen **tres rupturas graves** de esta partida doble:
  1. **Doble gasto con Fondos Propios:** La tabla `recuperos_fondos_propios` vincula un `cobro_id` para reembolsar al municipio adelantos hechos con recursos propios[cite: 1]. Sin embargo, ni `upsert_distribucion`, ni `add_desvio`, ni `get_cobros_con_resumen_distribucion` descuentan `recuperos_fondos_propios` del disponible del cobro[cite: 1]. Un operador puede cobrar \$10.000.000, aplicarlos en un 100% a pagar certificados en Fin Original y, simultáneamente, usar ese mismo `cobro_id` para recuperar \$10.000.000 hacia Fondos Propios (aplicando \$20.000.000 sobre un ingreso real de \$10.000.000)[cite: 1].
  2. **Bloqueo de fondos devueltos a "Sin Distribuir":** Cuando un desvío se recupera con `destino_tipo = 'sin_distribucion'`, el dinero vuelve a la bolsa libre del cobro (`upsert_distribucion` resta `tot_recuperos_sd`)[cite: 1]. Pero `add_desvio` y `update_desvio` verifican `(fin_orig + reserva + tot_desvios + monto) > cobro.monto` **sin restar `tot_recuperos_sd`**[cite: 1]. El dinero figura disponible en el Dashboard, pero el sistema impide volver a prestarlo[cite: 1].
  3. **Descuadre en el Reporte de Composición de Cuota y Afectación de Decretos:** En `utils_reports.py` (`obtener_datos_composicion`), el cálculo del saldo en reserva (`res_saldo_neto`) suma los recuperos provenientes de usos de reserva (`cobro_reserva_usos_recuperos`), pero **olvida sumar los recuperos de desvíos iniciales que ingresaron a reserva** (`cobro_desvios_recuperos` con `destino_tipo = 'reserva'`)[cite: 1]. Ante el Tribunal de Cuentas, la suma de las filas del reporte PDF/Excel de Afectación dará **menos que el importe percibido en el banco**[cite: 1].
- **Diagnóstico Técnico:** Las reglas de validación del saldo disponible de un cobro están dispersas y reescritas manualmente en 6 funciones distintas en lugar de centralizarse en una única función de cálculo de estado de cobro dentro de la transacción[cite: 1].
- **Código Problemático Actual:**
```python
# En database.py -> add_desvio() (Omite restar tot_recuperos_sd y recuperos_fondos_propios)
cursor.execute('SELECT COALESCE(SUM(monto), 0) as tot_desvios FROM cobro_desvios WHERE cobro_id = ?', (cobro_id,))
tot_desvios = cursor.fetchone()['tot_desvios']

if (fin_orig + reserva + tot_desvios + monto) > (c_row['monto'] + TOLERANCE):
    raise ValueError("El monto del desvío supera el saldo libre disponible sin distribuir.")

# En utils_reports.py -> obtener_datos_composicion() (Omite recuperos de desvíos iniciales hacia reserva)
tot_rec_a_res = 0.0
for u in usos_r:
    recs = db.get_recuperos_by_reserva_uso(u['id'])
    for r in recs:
        if r['destino_tipo'] == 'reserva':
            tot_rec_a_res += r['monto']
            
res_saldo_neto = monto_res - tot_usos_r + tot_rec_a_res
```
- **Solución Propuesta y Código Corregido:** Crear una función auxiliar canónica `_calcular_saldos_cobro_tx(cursor, cobro_id)` en `database.py` que centralice la ecuación patrimonial exacta (incluyendo `recuperos_fondos_propios` y `tot_recuperos_sd`) y corregir `obtener_datos_composicion` en `utils_reports.py`[cite: 1]:
```python
# 1. En database.py: Función centralizada de control de saldos de un cobro (dentro de transacción activa)
def _calcular_saldos_cobro_tx(cursor, cobro_id):
    cursor.execute('SELECT monto, fecha FROM cobros WHERE id = ?', (cobro_id,))
    c_row = cursor.fetchone()
    if not c_row:
        raise ValueError("Cobro no encontrado.")
        
    cursor.execute('SELECT monto_fin_orig, monto_reserva FROM cobro_distribuciones WHERE cobro_id = ?', (cobro_id,))
    dist = cursor.fetchone()
    fin_orig = dist['monto_fin_orig'] if dist else 0.0
    reserva = dist['monto_reserva'] if dist else 0.0

    cursor.execute('SELECT COALESCE(SUM(monto), 0) as tot FROM cobro_desvios WHERE cobro_id = ?', (cobro_id,))
    tot_desvios = cursor.fetchone()['tot']

    cursor.execute('SELECT COALESCE(SUM(monto), 0) as tot FROM recuperos_fondos_propios WHERE cobro_id = ?', (cobro_id,))
    tot_rec_fp = cursor.fetchone()['tot']

    cursor.execute('''
        SELECT COALESCE(SUM(cdr.monto), 0) as tot 
        FROM cobro_desvios_recuperos cdr
        JOIN cobro_desvios cd ON cdr.desvio_id = cd.id
        WHERE cd.cobro_id = ? AND cdr.destino_tipo = 'sin_distribucion'
    ''', (cobro_id,))
    rec_desv_sd = cursor.fetchone()['tot']

    cursor.execute('''
        SELECT COALESCE(SUM(crur.monto), 0) as tot 
        FROM cobro_reserva_usos_recuperos crur
        JOIN cobro_reserva_usos cru ON crur.reserva_uso_id = cru.id
        WHERE cru.cobro_id = ? AND crur.destino_tipo = 'sin_distribucion'
    ''', (cobro_id,))
    rec_res_sd = cursor.fetchone()['tot']

    tot_recuperos_sd = rec_desv_sd + rec_res_sd
    total_comprometido = fin_orig + reserva + tot_desvios + tot_rec_fp - tot_recuperos_sd
    saldo_sin_distribuir = c_row['monto'] - total_comprometido

    return {
        'monto_cobro': c_row['monto'],
        'fecha_cobro': c_row['fecha'],
        'fin_orig': fin_orig,
        'reserva': reserva,
        'tot_desvios': tot_desvios,
        'tot_rec_fp': tot_rec_fp,
        'tot_recuperos_sd': tot_recuperos_sd,
        'total_comprometido': total_comprometido,
        'saldo_sin_distribuir': saldo_sin_distribuir
    }

# 2. En utils_reports.py -> obtener_datos_composicion(): Incluir recuperos de desvíos iniciales que van a Reserva
        # C. En Reserva (Saldo Disponible)
        usos_r = db.get_reserva_usos_by_cobro(cb_id)
        tot_usos_r = sum(u['monto'] for u in usos_r)
        
        tot_rec_a_res = 0.0
        for u in usos_r:
            for r in db.get_recuperos_by_reserva_uso(u['id']):
                if r['destino_tipo'] == 'reserva':
                    tot_rec_a_res += r['monto']
                    
        # CORRECCIÓN: Sumar también los recuperos de desvíos iniciales cuyo destino fue 'reserva'
        desvios_cb = db.get_desvios_by_cobro(cb_id)
        for d_item in desvios_cb:
            for r_desv in db.get_recuperos_by_desvio(d_item['id']):
                if r_desv['destino_tipo'] == 'reserva':
                    tot_rec_a_res += r_desv['monto']
                    
        res_saldo_neto = monto_res - tot_usos_r + tot_rec_a_res
```

---

#### [HALLAZGO-02] Pérdida masiva de datos y falla de integridad al restaurar copias de seguridad (`restore_backup`)
- **Severidad:** Crítica (P0)
- **Categoría:** Arquitectura / Concurrencia y Transacciones
- **Ubicación:** `utils.py`, función `restore_backup(current_db_path, backup_db_path)`[cite: 1].
- **Impacto Contable / Financiero:** Si ante una contingencia operativa o auditoría se ejecuta la restauración de un backup, **el sistema destruye u omite la mitad de la contabilidad municipal**[cite: 1]. `restore_backup` fue escrita para una versión antigua de la base de datos (aprox. `v23`) y nunca se actualizó hasta la `v48`[cite: 1]. En consecuencia:
  1. Ignora por completo 14 tablas críticas: `obras`, `obra_adicionales`, `decretos_obras`, `convenios`, `convenio_obras`, `convenio_solicitudes`, `monedas_indices`, `proveedores_obras`, `proveedores_funcionamiento`, `gastos_funcionamiento`, `op_bejerman`, `pagos_fondos_propios` y `recuperos_fondos_propios`[cite: 1].
  2. En la tabla `cobros`, intenta copiar únicamente `(id, cuota_id, monto, fecha, comprobante_path)`, descartando todas las columnas de Convenios y UVIs (`convenio_solicitud_id`, `origen_tipo`, `moneda_origen_id`, `cantidad_moneda_origen`, `cotizacion_cobro`, `diferencia_ajuste_ars`, `obra_id`)[cite: 1].
  3. Al insertar un cobro de convenio donde `cuota_id` es `NULL` sin copiar `origen_tipo = 'convenio'`, SQLite asigna el default `origen_tipo = 'decreto'` con `cuota_id = NULL`, lo que dispara inmediatamente un error fatal por violación del constraint `check_origen_exclusivo` y aborta toda la restauración[cite: 1].
- **Diagnóstico Técnico:** Mientras `create_backup` usa correctamente la API nativa `sqlite3.Connection.backup()` (que clona páginas binarias de todas las tablas sin importar la versión del esquema)[cite: 1], `restore_backup` intenta hacer un `ATTACH DATABASE` con `INSERT OR IGNORE` manual y estático de un subconjunto obsoleto de tablas y columnas, además de interpolar la ruta mediante un f-string (`f"ATTACH DATABASE '{backup_path_escaped}' AS backup_db"`)[cite: 1].
- **Código Problemático Actual:**
```python
def restore_backup(current_db_path, backup_db_path):
    conn_curr = sqlite3.connect(current_db_path)
    conn_curr.execute("PRAGMA foreign_keys = ON;")
    try:
        backup_path_escaped = backup_db_path.replace("'", "''")
        conn_curr.execute(f"ATTACH DATABASE '{backup_path_escaped}' AS backup_db")
        cursor = conn_curr.cursor()
        # ... Solo copia 15 tablas viejas y omite columnas de v24 a v48 ...
        cursor.execute('''
            INSERT OR IGNORE INTO main.cobros (id, cuota_id, monto, fecha, comprobante_path)
            SELECT id, cuota_id, monto, fecha, comprobante_path FROM backup_db.cobros
        ''')
```
- **Solución Propuesta y Código Corregido:** Utilizar la API nativa `sqlite3.backup()` en sentido inverso (previa verificación de integridad del archivo de backup con `PRAGMA integrity_check`), e invocar `init_db()` inmediatamente después para aplicar cualquier migración pendiente si el backup proviniera de una versión anterior[cite: 1]:
```python
def restore_backup(current_db_path, backup_db_path):
    """Restaura de forma atómica e íntegra un backup completo usando la API nativa de SQLite,
    preservando las 29 tablas y ejecutando migraciones si el backup fuera de un esquema anterior.
    """
    if not os.path.exists(backup_db_path):
        raise FileNotFoundError(f"No se encontró el archivo de backup: {backup_db_path}")

    # 1. Validar que el archivo sea una base SQLite sana antes de pisar producción
    chk_conn = sqlite3.connect(backup_db_path)
    try:
        res = chk_conn.execute("PRAGMA integrity_check;").fetchone()
        if not res or res[0].lower() != "ok":
            raise ValueError(f"El archivo de backup está corrupto: {res}")
    finally:
        chk_conn.close()

    # 2. Crear resguardo preventivo automático del estado actual antes de restaurar
    create_backup(current_db_path, backup_dir="backups/pre_restore")

    # 3. Copia atómica a nivel páginas de motor SQLite (incluye las 29 tablas e índices)
    src_conn = sqlite3.connect(backup_db_path)
    dst_conn = sqlite3.connect(current_db_path, timeout=20.0)
    try:
        src_conn.backup(dst_conn)
    except Exception as e:
        logging.error(f"Error crítico durante la restauración del backup: {e}")
        raise
    finally:
        dst_conn.close()
        src_conn.close()

    # 4. Asegurar que el esquema restaurado quede actualizado a la última versión (v48+)
    import database as db
    db.init_db()
```

---

#### [HALLAZGO-03] Definición duplicada (Shadowing) de funciones `update_desvio` y `update_reserva_uso` en `database.py` y error en validación de Reserva
- **Severidad:** Crítica (P0)
- **Categoría:** Arquitectura / Lógica Financiera
- **Ubicación:** `database.py`, funciones `update_desvio` (definida dos veces) y `update_reserva_uso` (definida dos veces)[cite: 1].
- **Impacto Contable / Financiero:**
  1. En Python, definir dos funciones con el mismo nombre en el mismo archivo hace que la segunda sobrescriba silenciosamente a la primera en memoria[cite: 1]. Cualquier pantalla del sistema que invoque la primera firma de 5 argumentos (`update_desvio(desvio_id, nuevo_monto, nuevo_motivo, nueva_fecha, nuevo_nro_op)`) sufrirá una caída inmediata (`TypeError: missing 2 required positional arguments`)[cite: 1].
  2. La segunda definición de `update_reserva_uso` valida el tope disponible haciendo `(otros_usos + monto) > (reserva_original + TOLERANCE)` **sin restar los recuperos que regresaron a la reserva** (`recru_res_total` y `rec_desv_res_total`), contradiciendo la lógica de `add_reserva_uso` y `get_saldo_reserva_cobro`[cite: 1]. Si una reserva de \$1.000.000 se prestó, se recuperó a reserva y se volvió a prestar, al intentar editar el segundo uso el sistema arrojará un falso error de saldo insuficiente[cite: 1].
  3. Ninguna de las funciones `update_desvio`, `update_reserva_uso` ni `update_fin_original_uso` actualiza el padrón `op_bejerman` (`register_or_update_op`) ni sincroniza `obra_id` cuando se edita un movimiento[cite: 1].
- **Diagnóstico Técnico:** Código legado fusionado sin limpieza durante la evolución del monolito `database.py`[cite: 1]. Además, en `add_reserva_uso` quedó código basura de depuración en producción: `(cobro_id, user_auth_id if 'user_auth_id' in locals() else None) if False else (cobro_id,)`[cite: 1].
- **Código Problemático Actual:**
```python
# Primera definición en database.py:
def update_desvio(desvio_id, nuevo_monto, nuevo_motivo, nueva_fecha, nuevo_nro_op):
    ...
# Segunda definición más abajo en database.py (Pisa a la primera y omite obra_id / register_or_update_op):
def update_desvio(desvio_id, monto, destino, motivo, fecha, decreto_destino_id, nro_op):
    ...

# En la segunda definición de update_reserva_uso (Fórmula de saldo rota: no descuenta recuperos a reserva):
cursor.execute('SELECT COALESCE(SUM(monto), 0) as tot_usado FROM cobro_reserva_usos WHERE cobro_id = ? AND id != ?', (cobro_id, uso_id))
otros_usos = cursor.fetchone()['tot_usado']
if (otros_usos + monto) > (reserva_original + TOLERANCE):
    raise ValueError(f"El monto a usar editado ({monto:.2f}) supera el saldo disponible de reserva...")
```
- **Solución Propuesta y Código Corregido:** Eliminar las definiciones duplicadas y unificar cada operación en una única función con parámetros opcionales retrocompatibles, utilizando la fórmula completa de saldo neto de reserva y registrando la OP en la misma transacción[cite: 1]:
```python
def update_reserva_uso(uso_id, monto, nuevas_notas_o_tipo=None, nueva_fecha=None, nuevo_nro_op=None,
                       destino_detalle=None, fecha=None, notas=None, decreto_destino_id=None, nro_op=None, obra_id=None):
    """Firma unificada retrocompatible para edición de uso de reserva (5 u 8+ argumentos)."""
    if fecha is not None:
        destino_tipo_val = nuevas_notas_o_tipo
        fecha_val = fecha
        notas_val = notas
        op_val = nro_op
    else:
        destino_tipo_val = None
        fecha_val = nueva_fecha
        notas_val = nuevas_notas_o_tipo
        op_val = nuevo_nro_op

    _validar_op_o_nota_db(op_val, notas_val, contexto="uso de reserva")
    if monto <= 0:
        raise ValueError("El monto debe ser mayor a 0.")

    with db_session() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM cobro_reserva_usos WHERE id = ?', (uso_id,))
        uso_row = cursor.fetchone()
        if not uso_row:
            raise ValueError("Uso de reserva no encontrado.")
        cobro_id = uso_row['cobro_id']

        cursor.execute('SELECT COALESCE(SUM(monto), 0) as tot_rec FROM cobro_reserva_usos_recuperos WHERE reserva_uso_id = ?', (uso_id,))
        tot_rec = cursor.fetchone()['tot_rec']
        if monto < (tot_rec - TOLERANCE):
            raise ValueError(f"No se puede reducir el monto por debajo del total ya recuperado ({tot_rec:.2f}).")

        cursor.execute('SELECT monto_reserva FROM cobro_distribuciones WHERE cobro_id = ?', (cobro_id,))
        row_dist = cursor.fetchone()
        reserva_original = row_dist['monto_reserva'] if row_dist else 0.0

        cursor.execute('SELECT COALESCE(SUM(monto), 0) as tot FROM cobro_reserva_usos WHERE cobro_id = ? AND id != ?', (cobro_id, uso_id))
        otros_usos = cursor.fetchone()['tot']

        cursor.execute('''
            SELECT COALESCE(SUM(crur.monto), 0) as tot
            FROM cobro_reserva_usos_recuperos crur
            JOIN cobro_reserva_usos cru ON crur.reserva_uso_id = cru.id
            WHERE cru.cobro_id = ? AND crur.destino_tipo = 'reserva'
        ''', (cobro_id,))
        rec_res_a_res = cursor.fetchone()['tot']

        cursor.execute('''
            SELECT COALESCE(SUM(cdr.monto), 0) as tot
            FROM cobro_desvios_recuperos cdr
            JOIN cobro_desvios cd ON cdr.desvio_id = cd.id
            WHERE cd.cobro_id = ? AND cdr.destino_tipo = 'reserva'
        ''', (cobro_id,))
        rec_desv_a_res = cursor.fetchone()['tot']

        disponible_para_este_uso = reserva_original - otros_usos + rec_res_a_res + rec_desv_a_res
        if monto > (disponible_para_este_uso + TOLERANCE):
            raise ValueError(f"El monto editado ({monto:.2f}) supera el saldo disponible de reserva ({disponible_para_este_uso:.2f}).")

        final_tipo = destino_tipo_val if destino_tipo_val is not None else uso_row['destino_tipo']
        final_det = destino_detalle if destino_detalle is not None else uso_row['destino_detalle']
        final_dec = decreto_destino_id if decreto_destino_id is not None else uso_row['decreto_destino_id']
        final_obra = obra_id if obra_id is not None else uso_row['obra_id']

        cursor.execute('''
            UPDATE cobro_reserva_usos
            SET monto = ?, destino_tipo = ?, destino_detalle = ?, fecha = ?, notas = ?,
                decreto_destino_id = ?, nro_op = ?, obra_id = ?
            WHERE id = ?
        ''', (monto, final_tipo, final_det, fecha_val, notas_val, final_dec, op_val, final_obra, uso_id))

        if op_val and str(op_val).strip():
            cursor.execute('''
                INSERT INTO op_bejerman (nro_op, obra_id, gasto_id) VALUES (?, ?, NULL)
                ON CONFLICT(nro_op) DO UPDATE SET obra_id = COALESCE(excluded.obra_id, op_bejerman.obra_id)
            ''', (str(op_val).strip(), final_obra))
```

---

### 🟠 Severidad Alta (P1)

#### [HALLAZGO-04] Condiciones de Carrera (TOCTOU), falta de `BEGIN IMMEDIATE` y transacciones fragmentadas en SQLite bajo Streamlit
- **Severidad:** Alta (P1)
- **Categoría:** Concurrencia y Transacciones
- **Ubicación:** `database.py` (`get_connection`, `db_session`, `init_db`, `add_cobro`, `add_desvio`, `add_reserva_uso`, `add_fin_original_uso`, `add_pago_fondos_propios`)[cite: 1].
- **Impacto Contable / Financiero:** En Streamlit, cada clic o cambio de filtro dispara una re-ejecución del script (`st.rerun()`)[cite: 1]. Si un usuario hace doble clic en "Guardar Cobro" o tiene dos pestañas abiertas:
  1. Ambas ejecuciones leen al mismo tiempo el saldo pendiente mediante un `SELECT SUM(monto)` **antes** de que SQLite bloquee la base para escritura[cite: 1]. Ambas ven que hay saldo disponible y ambas insertan el registro, **duplicando un cobro o sobre-ejecutando una reserva** (vulnerabilidad *Time-Of-Check to Time-Of-Use* o TOCTOU)[cite: 1].
  2. Funciones como `add_cobro`, `add_desvio` y `add_fin_original_uso` ejecutan `conn.commit()` a mitad de camino y luego abren **una segunda transacción separada** para actualizar el estado del decreto (`check_estado_decreto_by_cuota`) o registrar la Orden de Pago (`register_or_update_op`)[cite: 1]. Si el segundo paso falla, el cobro o pago queda grabado pero el decreto queda en estado inconsistente o la OP no se registra en `op_bejerman`[cite: 1].
  3. En `init_db()`, las migraciones 44 y 47 ejecutan `conn.execute("PRAGMA foreign_keys = OFF;")` cuando la transacción ya está abierta por sentencias previas[cite: 1]. En SQLite, cambiar `PRAGMA foreign_keys` dentro de una transacción abierta **es ignorado silenciosamente por el motor**, lo que pone en riesgo de borrado en cascada (`ON DELETE CASCADE`) a todas las tablas hijas al ejecutar `DROP TABLE cobros`[cite: 1].
- **Diagnóstico Técnico:** El conector `sqlite3.connect(DB_PATH, timeout=10.0)` usa el modo por defecto de Python (`DEFERRED`), que no adquiere un bloqueo de escritura hasta el primer `INSERT/UPDATE/DELETE`, dejando los `SELECT` de validación desprotegidos[cite: 1]. Además, no se activa `PRAGMA journal_mode = WAL;` (Write-Ahead Logging)[cite: 1].
- **Código Problemático Actual:**
```python
def get_connection():
    conn = sqlite3.connect(DB_PATH, timeout=10.0)
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.row_factory = sqlite3.Row
    return conn

@contextmanager
def db_session():
    conn = get_connection()
    try:
        yield conn
        conn.commit()
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()
```
- **Solución Propuesta y Código Corregido:** Configurar `isolation_level=None`, habilitar `PRAGMA journal_mode = WAL;` y `PRAGMA busy_timeout = 15000;`, y abrir explícitamente `BEGIN IMMEDIATE` en transacciones de escritura[cite: 1]:
```python
def get_connection():
    conn = sqlite3.connect(DB_PATH, timeout=15.0, isolation_level=None)
    conn.execute("PRAGMA journal_mode = WAL;")
    conn.execute("PRAGMA synchronous = NORMAL;")
    conn.execute("PRAGMA busy_timeout = 15000;")
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.row_factory = sqlite3.Row
    return conn

@contextmanager
def db_session(write=True):
    """Maneja transacciones atómicas con bloqueo inmediato de escritura (BEGIN IMMEDIATE)
    para evitar condiciones de carrera (TOCTOU) en validaciones de saldos.
    """
    conn = get_connection()
    try:
        if write:
            conn.execute("BEGIN IMMEDIATE;")
        else:
            conn.execute("BEGIN DEFERRED;")
        yield conn
        conn.execute("COMMIT;")
    except Exception:
        if conn.in_transaction:
            conn.execute("ROLLBACK;")
        raise
    finally:
        conn.close()
```

---

#### [HALLAZGO-05] Distorsión en Valuación Bimonetaria (UVIs / USD): Fallback a cotización `1.0`, desvíos valuados a cotización histórica y desfasaje en KPIs de Convenios
- **Severidad:** Alta (P1)
- **Categoría:** Lógica Financiera y UVIs
- **Ubicación:** `database.py` (`add_pago_fondos_propios`, `update_fin_original_uso`, `get_resumen_contrato_obra`, `get_pagos_detalle_por_obra`, `get_kpis_convenios_global`) e `Inicio.py`[cite: 1].
- **Impacto Contable / Financiero:**
  1. **Destrucción del cupo en UVIs por fallback a `cotiz = 1.0`:** En `add_pago_fondos_propios` y `update_fin_original_uso`, si una obra está contratada en UVIs (`moneda_id != 1`) y no se envía explícitamente `cotizacion_pago`, el código asigna `cotiz = 1.0` y calcula `cant_mon = round(monto / 1.0, 6)`[cite: 1]. Si se registra un pago de \$15.000.000 ARS sin cotización UVI cargada, el sistema asume que 1 UVI = \$1 ARS y descuenta **15.000.000 de UVIs** del contrato, dejando el contrato sobre-ejecutado artificialmente[cite: 1].
  2. **Imputación de Desvíos y Reservas a cotización histórica en obras UVI:** Cuando una obra pactada en UVIs recibe pagos desde un **Desvío** (`cobro_desvios`) o un **Uso de Reserva** (`cobro_reserva_usos`), las consultas de `get_resumen_contrato_obra` y `get_pagos_detalle_por_obra` seleccionan `NULL as cantidad_moneda_amortizada, NULL as cotizacion_pago` y dividen los pesos pagados hoy por la `cotizacion_base_contrato` (la cotización histórica del contrato)[cite: 1]. En un contexto inflacionario donde la UVI sube diariamente por CER, dividir pesos nominales actuales por la UVI histórica **sobrestima artificialmente las UVIs amortizadas** y subestima el Resultado por Indexación[cite: 1].
  3. **Doble métrica contradictoria de "Certificados en Tránsito" en `Inicio.py`:** En `get_kpis_convenios_global()`, la consulta suma el 100% de `monto_solicitado_ars` de cualquier certificado en estado `'Parcial'`, sin descontar la porción ya cobrada[cite: 1]. En cambio, el segundo bloque de Convenios en `Inicio.py` calcula `(cantidad_moneda - cantidad_moneda_cobrada) * cotizacion_solicitud`[cite: 1]. Si un certificado fue cobrado parcialmente, **el Dashboard muestra dos importes en Pesos distintos para el mismo concepto en la misma pantalla**[cite: 1].
  4. **Acumulación de tolerancias en punto flotante (`REAL`):** Al validar `cant_amortizar > (saldo_moneda_sol + 0.01)` en `add_cobro`[cite: 1], se permite cobrar hasta `0.01 UVI` de más en cada cobro parcial[cite: 1].
- **Diagnóstico Técnico:** Las tablas `cobro_desvios` y `cobro_reserva_usos` carecen de las columnas `cantidad_moneda_amortizada` y `cotizacion_pago` que sí fueron agregadas en la Migración 48 a `cobro_fin_original_usos` y `pagos_fondos_propios`[cite: 1]. Asimismo, se utiliza `float` binario en vez de `decimal.Decimal` con redondeo contable `ROUND_HALF_UP`[cite: 1].
- **Código Problemático Actual:**
```python
# 1. En database.py -> add_pago_fondos_propios() (Fallback silencioso a cotiz = 1.0 en obras UVI/USD!)
if o_moneda_id == 1:
    cotiz = 1.0
    cant_mon = float(monto)
else:
    if cotiz is None or cotiz <= 0:
        cotiz = 1.0  # <-- PELIGRO CONTABLE: 1 UVI = $1 ARS!
    if cant_mon is None:
        cant_mon = round(monto / cotiz, 6) if cotiz > 0 else 0.0

# 2. En database.py -> get_kpis_convenios_global() (Toma monto_solicitado_ars total aunque sea 'Parcial')
SELECT 
    COUNT(*) as cant_pendientes,
    COALESCE(SUM(monto_solicitado_ars), 0) as total_solicitado_ars,
    COALESCE(SUM(cantidad_moneda - cantidad_moneda_cobrada), 0) as total_transito_moneda
FROM convenio_solicitudes cs
JOIN convenios cv ON cs.convenio_id = cv.id
WHERE cs.estado IN ('Pendiente', 'Parcial') AND cv.estado = 'Vigente'
```
- **Solución Propuesta y Código Corregido:**
```python
from decimal import Decimal, ROUND_HALF_UP

def round_ars(val):
    return float(Decimal(str(val or 0.0)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP))

def round_uvi(val):
    return float(Decimal(str(val or 0.0)).quantize(Decimal('0.000001'), rounding=ROUND_HALF_UP))

# En add_pago_fondos_propios y add_fin_original_uso / update_fin_original_uso:
if o_moneda_id == 1:
    cotiz = 1.0
    cant_mon = round_ars(monto)
else:
    if cotiz is None or float(cotiz) <= 0:
        raise ValueError(
            "Para obras contratadas en UVIs o moneda extranjera es obligatorio informar "
            "la cotización de pago vigente a la fecha de la Orden de Pago."
        )
    cotiz = float(cotiz)
    cant_mon = round_uvi(cant_mon) if (cant_mon is not None and float(cant_mon) > 0) else round_uvi(float(monto) / cotiz)

# En get_kpis_convenios_global() -> Cálculo exacto del saldo en tránsito en ARS:
cursor.execute('''
    SELECT 
        COUNT(*) as cant_pendientes,
        COALESCE(SUM((cs.cantidad_moneda - cs.cantidad_moneda_cobrada) * cs.cotizacion_solicitud), 0) as total_solicitado_ars,
        COALESCE(SUM(cs.cantidad_moneda - cs.cantidad_moneda_cobrada), 0) as total_transito_moneda
    FROM convenio_solicitudes cs
    JOIN convenios cv ON cs.convenio_id = cv.id
    WHERE cs.estado IN ('Pendiente', 'Parcial') AND cv.estado = 'Vigente'
''')
```

---

#### [HALLAZGO-06] Ruptura de trazabilidad en Compensaciones Cruzadas, atribución errónea en Convenios Multiobra y edición sin guardas en Convenios
- **Severidad:** Alta (P1)
- **Categoría:** Lógica Financiera y UVIs
- **Ubicación:** `database.py` (`delete_desvio_recupero`, `delete_reserva_uso_recupero`, `add_desvio`, `add_reserva_uso`, `update_solicitud_convenio`, `update_convenio`) y `utils_reports.py` (`obtener_estado_deudas_por_obra`)[cite: 1].
- **Impacto Contable / Financiero:**
  1. **Ruptura de Compensaciones Cruzadas (Deudas Huérfanas):** Cuando la Obra A y la Obra B compensan deudas mutuas, se vinculan mediante `grupo_compensacion_id` en `cobro_desvios_recuperos` y `cobro_reserva_usos_recuperos`[cite: 1]. Sin embargo, `delete_desvio_recupero(recupero_id)` y `delete_reserva_uso_recupero(recupero_id)` borran una sola pata de la compensación sin eliminar ni revertir la contraparte del mismo `grupo_compensacion_id`[cite: 1]. Esto permite anular la cancelación de deuda de la Obra A dejando cancelada gratuitamente la deuda de la Obra B[cite: 1].
  2. **Duplicación de acreencias en Convenios Multiobra (`obtener_estado_deudas_por_obra`):** En `utils_reports.py`, para determinar si una obra es acreedora de un desvío originado en un Convenio Multiobra, la consulta SQL hace: `WHERE (... OR conv.id IN (SELECT convenio_id FROM convenio_obras WHERE obra_id = ?))`[cite: 1]. Como un Convenio Multiobra financia múltiples obras simultáneamente, **cualquier préstamo otorgado con fondos del convenio se le computa como "crédito a cobrar" a TODAS las obras vinculadas a ese convenio**, multiplicando artificialmente los créditos en los reportes de deuda por obra[cite: 1].
  3. **Asignación arbitraria de decreto destino (`decretos_vigentes[0]`):** En `add_desvio` y `add_reserva_uso`, si una obra destino está financiada por más de un decreto vigente, el código toma silenciosamente el primero de la lista (`decreto_destino_id = decretos_vigentes[0]['id']`) sin permitir especificar a cuál decreto se imputa la deuda[cite: 1].
  4. **Bypass de topes al editar Convenios y Certificados:** Mientras `add_solicitud_convenio` valida rigurosamente no superar el cupo del convenio, `update_solicitud_convenio` y `update_convenio` **no tienen ninguna validación de tope ni de piso**[cite: 1]. Un usuario puede editar un certificado para superar el monto del convenio, o reducir su cantidad en UVIs por debajo de lo que ya fue cobrado en el banco (`cantidad_moneda < cantidad_moneda_cobrada`)[cite: 1].
- **Diagnóstico Técnico:** Falta de simetría entre las validaciones de inserción (`add_*`) y actualización/borrado (`update_*` / `delete_*`), y filtrado por `convenio_id` en vez de `csol.obra_id` / `c.obra_id` en las consultas de trazabilidad de convenios multiobra[cite: 1].
- **Código Problemático Actual:**
```python
# 1. En database.py -> delete_desvio_recupero (Borra una pata dejando huérfano el grupo de compensación)
def delete_desvio_recupero(recupero_id):
    with db_session() as conn:
        cursor = conn.cursor()
        cursor.execute('DELETE FROM cobro_desvios_recuperos WHERE id = ?', (recupero_id,))
        conn.commit()

# 2. En utils_reports.py -> obtener_estado_deudas_por_obra (Atribuye el desvío a TODAS las obras del convenio!)
WHERE (
    d_orig.id IN (SELECT decreto_id FROM decretos_obras WHERE obra_id = ?)
    OR conv.id IN (SELECT convenio_id FROM convenio_obras WHERE obra_id = ?)
)
```
- **Solución Propuesta y Código Corregido:**
```python
# 1. En database.py: Borrado atómico de ambos lados si pertenece a un grupo de compensación
def delete_desvio_recupero(recupero_id):
    with db_session() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT grupo_compensacion_id FROM cobro_desvios_recuperos WHERE id = ?', (recupero_id,))
        row = cursor.fetchone()
        if not row:
            return
        grupo_id = row['grupo_compensacion_id']
        if grupo_id:
            cursor.execute('DELETE FROM cobro_desvios_recuperos WHERE grupo_compensacion_id = ?', (grupo_id,))
            cursor.execute('DELETE FROM cobro_reserva_usos_recuperos WHERE grupo_compensacion_id = ?', (grupo_id,))
        else:
            cursor.execute('DELETE FROM cobro_desvios_recuperos WHERE id = ?', (recupero_id,))

# 2. En database.py -> update_solicitud_convenio: Blindar contra reducción bajo lo cobrado y exceso de cupo
def update_solicitud_convenio(solicitud_id, nro_certificado, periodo,
                              cantidad_moneda, cotizacion_solicitud, monto_solicitado_ars,
                              fecha_solicitud, expediente_pago=None, pdf_path=None, notas=None):
    if float(cantidad_moneda) <= 0 or float(cotizacion_solicitud) <= 0 or float(monto_solicitado_ars) <= 0:
        raise ValueError("La cantidad en moneda, cotización y monto en pesos deben ser mayores a 0.")
    with db_session() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM convenio_solicitudes WHERE id = ?', (solicitud_id,))
        actual = cursor.fetchone()
        if not actual:
            raise ValueError("Solicitud de convenio no encontrada.")
        cobrada = float(actual['cantidad_moneda_cobrada'] or 0.0)
        if float(cantidad_moneda) < (cobrada - TOLERANCE):
            raise ValueError(f"No se puede reducir el certificado a {cantidad_moneda:,.2f} porque ya se cobraron {cobrada:,.2f}.")

        cursor.execute('SELECT monto_pactado_moneda FROM convenios WHERE id = ?', (actual['convenio_id'],))
        total_pactado = cursor.fetchone()['monto_pactado_moneda']
        cursor.execute('''
            SELECT COALESCE(SUM(cantidad_moneda), 0) as otros_sol
            FROM convenio_solicitudes
            WHERE convenio_id = ? AND id != ? AND estado != 'Anulado'
        ''', (actual['convenio_id'], solicitud_id))
        otros_sol = cursor.fetchone()['otros_sol']
        if (otros_sol + float(cantidad_moneda)) > (total_pactado + TOLERANCE):
            raise ValueError("La cantidad editada supera el remanente disponible del convenio.")

        nuevo_estado = 'Cobrado' if cobrada >= (float(cantidad_moneda) - TOLERANCE) and cobrada > 0 else ('Parcial' if cobrada > 0 else actual['estado'])
        cursor.execute('''
            UPDATE convenio_solicitudes
            SET nro_certificado = ?, periodo = ?, cantidad_moneda = ?,
                cotizacion_solicitud = ?, monto_solicitado_ars = ?, fecha_solicitud = ?,
                expediente_pago = ?, pdf_path = ?, notas = ?, estado = ?
            WHERE id = ?
        ''', (
            str(nro_certificado).strip(), periodo, float(cantidad_moneda),
            float(cotizacion_solicitud), float(monto_solicitado_ars), fecha_solicitud,
            expediente_pago, pdf_path, notas.strip() if notas else None, nuevo_estado, solicitud_id
        ))
        check_estado_convenio(conn, actual['convenio_id'])

# 3. En utils_reports.py -> obtener_estado_deudas_por_obra: Filtrar por la obra específica del cobro/certificado de convenio
WHERE (
    d_orig.id IN (SELECT decreto_id FROM decretos_obras WHERE obra_id = ?)
    OR COALESCE(c.obra_id, csol.obra_id) = ?
)
```

---

### 🟡 Severidad Media (P2)

#### [HALLAZGO-07] Sobrecarga de I/O, Fuga de Archivos Temporales y `importlib.reload()` en cada interacción de `Inicio.py`
- **Severidad:** Media (P2)
- **Categoría:** Arquitectura / Concurrencia y Transacciones
- **Ubicación:** `Inicio.py` (líneas 12-54 y sección de Convenios duplicada en líneas 295-338 vs 445-492)[cite: 1].
- **Impacto Contable / Financiero:**
  1. **Lentitud progresiva y bloqueos innecesarios:** En `Inicio.py`, en cada clic del usuario (incluso al escribir una letra en el buscador de alertas o cambiar una fecha del gráfico), el script ejecuta `generar_reporte_pdf(temp_path)` de manera incondicional arriba de todo solo para alimentar el botón `st.download_button`, y **jamás borra el archivo PDF temporal creado en disco**[cite: 1]. Esto ejecuta decenas de consultas a la base de datos y escribe un PDF en el disco duro en cada interacción, saturando el sistema y dejando miles de archivos huérfanos en la carpeta `TEMP` de Windows[cite: 1].
  2. **Recarga forzada de módulos en caliente (`importlib.reload`):** Las líneas `importlib.reload(db)` e `importlib.reload(utils)` al inicio de `Inicio.py` obligan al intérprete de Python a recompilar y recargar `database.py` en cada clic[cite: 1].
  3. **Sección de Convenios duplicada en la misma pantalla:** `Inicio.py` renderiza **dos veces** el panel de Convenios Multiobra: una vez en las líneas 295-338 (`📜 Convenios Multiobra y Control Indexado (UVIs / USD)`) y otra vez al final en las líneas 445-492 (`📜 Convenios Multiobra y Financiamiento Externo`)[cite: 1].
- **Diagnóstico Técnico:** En Streamlit, `st.download_button` evalúa su parámetro `data` al renderizar la página[cite: 1]. Para reportes pesados, debe generarse bajo demanda o cachearse, y eliminarse el archivo temporal inmediatamente después de leer sus bytes en memoria[cite: 1].
- **Código Problemático Actual:**
```python
# En Inicio.py (Se ejecuta en CADA clic de la aplicación y nunca borra temp_path):
import database as db
import importlib
importlib.reload(db)
import utils
importlib.reload(utils)
...
with col_t2:
    st.write("")
    try:
        temp_path = os.path.join(tempfile.gettempdir(), f"Reporte_Financiero_{datetime.date.today().strftime('%Y%m%d')}_{uuid.uuid4().hex[:8]}.pdf")
        generar_reporte_pdf(temp_path)
        with open(temp_path, "rb") as f:
            pdf_bytes = f.read()
        st.download_button(...)
```
- **Solución Propuesta y Código Corregido:** Eliminar `importlib.reload()`, borrar el archivo temporal inmediatamente en un bloque `finally`, cachear el PDF por 60 segundos con `@st.cache_data(ttl=60)` y unificar las dos secciones de Convenios en `Inicio.py`[cite: 1]:
```python
@st.cache_data(ttl=60, show_spinner="Preparando reporte ejecutivo...")
def obtener_bytes_reporte_general(fecha_str):
    temp_path = os.path.join(tempfile.gettempdir(), f"Reporte_Financiero_{fecha_str}_{uuid.uuid4().hex[:8]}.pdf")
    try:
        generar_reporte_pdf(temp_path)
        with open(temp_path, "rb") as f:
            return f.read()
    finally:
        if os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except OSError:
                pass
```

---

#### [HALLAZGO-08] Monolito en `database.py`, anomalías de esquema (`notes` vs `notas`) y falta de sincronización con `op_bejerman`
- **Severidad:** Media (P2)
- **Categoría:** Arquitectura
- **Ubicación:** `database.py` (estructura global) y definición DDL de `cobro_fin_original_usos` y `op_bejerman`[cite: 1].
- **Impacto Contable / Financiero:**
  1. Concentrar más de 120 funciones en un único archivo hace que cualquier modificación para agregar un reporte o ajustar una validación de UVI tenga alto riesgo de romper funciones vecinas[cite: 1].
  2. La tabla `cobro_fin_original_usos` en la base de datos real posee dos columnas para lo mismo: `notes TEXT` y `notas TEXT`[cite: 1].
  3. Los pagos con Fondos Propios (`pagos_fondos_propios`) y los Recuperos de Fondos Propios (`recuperos_fondos_propios`) **no se contabilizan en `get_op_usage_count(nro_op)` ni en `get_op_usage_details(nro_op)`**[cite: 1]. Si el Contador consulta en qué movimientos se utilizó una Orden de Pago de Bejerman, el sistema oculta sus usos en Fondos Propios[cite: 1].
- **Diagnóstico Técnico:** `get_op_usage_count` y `get_op_usage_details` solo consultan las 5 tablas de distribución de cobros (`cobro_fin_original_usos`, `cobro_desvios`, `cobro_desvios_recuperos`, `cobro_reserva_usos`, `cobro_reserva_usos_recuperos`), omitiendo `pagos_fondos_propios` y `recuperos_fondos_propios`[cite: 1].
- **Código Problemático Actual:**
```python
def get_op_usage_count(nro_op):
    ...
    with db_session() as conn:
        cursor = conn.cursor()
        count = 0
        cursor.execute("SELECT COUNT(*) FROM cobro_fin_original_usos WHERE nro_op = ?", (nro_op_str,))
        count += cursor.fetchone()[0]
        # ... faltan pagos_fondos_propios y recuperos_fondos_propios ...
```
- **Solución Propuesta y Código Corregido:** Incluir `pagos_fondos_propios` y `recuperos_fondos_propios` en ambas funciones de auditoría de OPs[cite: 1]:
```python
def get_op_usage_details(nro_op):
    nro_op_str = str(nro_op).strip()
    if not nro_op_str:
        return []
    usages = []
    tablas_op = [
        ("cobro_fin_original_usos", "Fin Original"),
        ("cobro_desvios", "Desvío"),
        ("cobro_desvios_recuperos", "Recupero de Desvío"),
        ("cobro_reserva_usos_recuperos", "Recupero de Reserva"),
        ("cobro_reserva_usos", "Pago desde Reserva"),
        ("pagos_fondos_propios", "Pago Fondos Propios"),
        ("recuperos_fondos_propios", "Recupero Fondos Propios"),
    ]
    with db_session(write=False) as conn:
        cursor = conn.cursor()
        for tabla, etiqueta in tablas_op:
            cursor.execute(f"SELECT monto, fecha FROM {tabla} WHERE nro_op = ?", (nro_op_str,))
            for row in cursor.fetchall():
                usages.append({'origen': etiqueta, 'monto': row['monto'], 'fecha': row['fecha']})
    return usages
```

---

#### [HALLAZGO-09] Seguridad en Subida de Comprobantes (Colisión de nombres, falta de validación de firma binaria y rutas relativas)
- **Severidad:** Media (P2)
- **Categoría:** Seguridad
- **Ubicación:** `utils.py` (`save_uploaded_file`) y `database.py` (consultas con f-strings `f"... > {TOLERANCE}"`)[cite: 1].
- **Impacto Contable / Financiero:**
  1. **Sobrescritura de comprobantes bancarios:** `save_uploaded_file` genera el nombre del archivo usando resolución de segundos (`%Y%m%d%H%M%S`)[cite: 1]. Si en un proceso de carga rápida se suben dos archivos con igual nombre dentro del mismo segundo, o si un archivo `.exe` es renombrado como `.pdf`, el sistema no verifica los *magic bytes* (encabezado real del archivo `%PDF-`, `\xff\xd8\xff` para JPEG o `\x89PNG`)[cite: 1].
  2. **Portabilidad de rutas en Windows vs Linux:** Guardar `os.path.join("uploads", filename)` almacena barras invertidas (`uploads\...`) en Windows[cite: 1].
  3. **Interpolación f-string en SQL:** En `database.py` (`get_todas_obras_para_trazabilidad`, `get_trazabilidad_fuentes_por_obra`), se interpola `f"... > {TOLERANCE}"` dentro del string SQL en lugar de pasarlo como parámetro `?`[cite: 1].
- **Diagnóstico Técnico:** Validación superficial basada únicamente en `os.path.splitext` y falta de normalización POSIX (`replace("\\", "/")`) para las rutas persistidas en SQLite[cite: 1].
- **Código Problemático Actual:**
```python
def save_uploaded_file(uploaded_file, dest_folder="uploads"):
    ...
    ext = os.path.splitext(uploaded_file.name)[1].lower()
    if ext not in _EXTENSIONES_PERMITIDAS:
        raise ValueError(...)
    ...
    timestamp = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
    raw_name = os.path.basename(uploaded_file.name)
    clean_name = re.sub(r'[^\w\-.]', '_', raw_name)
    filename = f"{timestamp}_{clean_name}"
    file_path = os.path.join(dest_folder, filename)
```
- **Solución Propuesta y Código Corregido:** Validar la firma binaria (*magic bytes*) del contenido real del archivo, agregar un sufijo único (`uuid4().hex[:6]`) para impedir colisiones y normalizar la ruta con barras `/` estándar[cite: 1]:
```python
import uuid

_MAGIC_SIGNATURES = {
    '.pdf': (b'%PDF-',),
    '.jpg': (b'\xff\xd8\xff',),
    '.jpeg': (b'\xff\xd8\xff',),
    '.png': (b'\x89PNG\r\n\x1a\n',),
}

def save_uploaded_file(uploaded_file, dest_folder="uploads"):
    if uploaded_file is None:
        return None
    ext = os.path.splitext(uploaded_file.name)[1].lower()
    if ext not in _EXTENSIONES_PERMITIDAS:
        raise ValueError(f"Tipo de archivo no permitido: '{ext}'.")

    buf = uploaded_file.getbuffer()
    size_bytes = len(buf)
    if size_bytes == 0:
        raise ValueError("El archivo subido está vacío.")
    if size_bytes > _MAX_FILE_SIZE_MB * 1024 * 1024:
        raise ValueError(f"El archivo supera el tamaño máximo permitido ({_MAX_FILE_SIZE_MB} MB).")

    # Validar firma binaria real (Magic Bytes) para evitar ejecutables camuflados
    header_bytes = bytes(buf[:16])
    valid_sigs = _MAGIC_SIGNATURES.get(ext, ())
    if not any(header_bytes.startswith(sig) for sig in valid_sigs):
        raise ValueError(f"El contenido real del archivo no corresponde a un formato '{ext}' válido.")

    os.makedirs(dest_folder, exist_ok=True)
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    uid = uuid.uuid4().hex[:6]
    clean_name = re.sub(r'[^\w\-.]', '_', os.path.basename(uploaded_file.name))
    filename = f"{timestamp}_{uid}_{clean_name}"
    file_path = os.path.join(dest_folder, filename).replace("\\", "/")
    with open(file_path, "wb") as f:
        f.write(buf)
    return file_path
```

---

### 🟢 Severidad Baja (P3)

#### [HALLAZGO-10] Puntos ciegos en la Batería de Pruebas (`tests/`) y Consultas N+1 en Reportes
- **Severidad:** Baja (P3)
- **Categoría:** Testing / Optimización SQL
- **Ubicación:** Suite `tests/`, `Inicio.py` (bucles de `get_cuotas_by_decreto`) y `utils_reports.py` (`obtener_datos_composicion`)[cite: 1].
- **Impacto Contable / Financiero:**
  1. La existencia en producción de los Hallazgos 01, 02, 03, 05 y 06 demuestra que la suite de pruebas actual testea los "caminos felices" (*happy paths*) individuales, pero **no verifica invariantes contables cruzados**: no existe un test que compruebe que `create_backup` + `restore_backup` conserve las 29 tablas en `v48`, ni que la suma del Reporte de Composición cuadre al centavo con el cobro tras múltiples ciclos de desvíos y recuperos a reserva[cite: 1].
  2. En `Inicio.py`, se llama a `get_cuotas_by_decreto(d['id'])` dentro de un bucle `for d in decretos:` dos veces en el mismo script (una para alertas y otra para el gráfico), abriendo decenas de conexiones SQLite sucesivas en cada recarga[cite: 1].
- **Diagnóstico Técnico:** Falta de pruebas basadas en invariantes patrimoniales (*Property/Invariant Testing*) y ausencia de una función `get_all_cuotas()` para evitar el patrón N+1 en `Inicio.py`[cite: 1].
- **Código Problemático Actual:**
```python
# En Inicio.py (Patrón N+1 repetido dos veces en la misma carga de página):
for d in decretos:
    for c in get_cuotas_by_decreto(d['id']):
        c['estado_decreto'] = d['estado']
        cuotas_totales.append(c)
```
- **Solución Propuesta y Código Corregido:** Agregar `get_all_cuotas()` en `database.py` (una sola consulta SQL con `JOIN decretos`) e incorporar en `tests/` pruebas de invariantes patrimoniales[cite: 1]:
```python
# Test de invariante contable para agregar a tests/test_auditoria_forense.py:
def test_invariante_composicion_cuota_con_recupero_desvio_a_reserva(temp_db):
    """Verifica que si un desvío inicial se recupera hacia Reserva, el reporte de composición
    de cuota cuadre exactamente con el monto cobrado (ni un centavo de menos ni de más)."""
    dec_id = db.add_decreto(101, 2026, "EXP-1", "Obra Pavimento")
    cuota_id = db.add_cuota(dec_id, 1, 2026, 1000000.0)
    cobro_id = db.add_cobro(cuota_id=cuota_id, monto=1000000.0, fecha="2026-01-15")
    
    # Distribuir $500k a Fin Original, $200k a Reserva y desviar $300k a otra obra
    db.upsert_distribucion(cobro_id, monto_fin_orig=500000.0, monto_reserva=200000.0)
    desv_id = db.add_desvio(cobro_id, "Obra Cloacas", 300000.0, "Préstamo urgente", "2026-01-16", nro_op="OP-1")
    
    # Recuperar $100k del desvío enviándolos a Reserva
    db.add_desvio_recupero(desv_id, 100000.0, "2026-01-20", destino_tipo="reserva", notas="Reintegro a reserva")
    
    filas, suma_reporte, *_ = utils_reports.obtener_datos_composicion(dec_id, cuota_id)
    assert round(suma_reporte, 2) == 1000000.00, f"Descuadre contable en reporte: {suma_reporte} != 1000000.00"
```

---

## Sección 3: Hoja de Ruta Priorizada (Plan de Acción)

### 🚀 Fase 1: Quick Wins Inmediatos (1 a 3 días) — *Parcheo de Riesgos Críticos P0*
1. **Reemplazar `restore_backup` en `utils.py` (Hallazgo 02):** Sustituir inmediatamente la función obsoleta por la implementación basada en `src_conn.backup(dst_conn)` + `db.init_db()` para evitar pérdidas de datos en las 14 tablas nuevas del esquema `v48`[cite: 1].
2. **Eliminar las definiciones duplicadas en `database.py` (Hallazgo 03):** Unificar `update_desvio` y `update_reserva_uso`, corrigiendo la fórmula de validación de saldo de reserva en `update_reserva_uso` y limpiando la expresión muerta `user_auth_id` en `add_reserva_uso`[cite: 1].
3. **Activar `WAL` y `BEGIN IMMEDIATE` en `db_session()` (Hallazgo 04):** Modificar `get_connection()` y `db_session()` en `database.py` y quitar los `conn.commit()` intermedios para blindar todas las operaciones contra doble clic y condiciones de carrera[cite: 1].
4. **Optimizar `Inicio.py` (Hallazgo 07):** Quitar `importlib.reload()`, encapsular la generación del PDF en una función cacheada con borrado de `temp_path` en `finally`, y eliminar la tabla duplicada de Convenios al final de la página[cite: 1].

### 🛡️ Fase 2: Blindaje Financiero y de Datos (1 a 2 semanas) — *Precisión Contable y UVIs*
1. **Cerrar la Ecuación Patrimonial de Cobros (Hallazgo 01):**
   * Implementar `_calcular_saldos_cobro_tx(cursor, cobro_id)` en `database.py` para que `upsert_distribucion`, `add_desvio`, `update_desvio` y `add_recupero_fondos_propios` validen contra la misma bolsa única del cobro[cite: 1].
   * Corregir `obtener_datos_composicion` en `utils_reports.py` sumando los recuperos de desvíos iniciales con `destino_tipo == 'reserva'` al saldo neto de reserva[cite: 1].
2. **Blindar Valuación de Obras y Convenios en UVIs/USD (Hallazgo 05 y 06):**
   * Prohibir el fallback `cotiz = 1.0` cuando `moneda_id != 1` en `add_pago_fondos_propios`, `add_fin_original_uso` y `update_fin_original_uso`[cite: 1].
   * Agregar la **Migración 49** para incorporar `cantidad_moneda_amortizada REAL` y `cotizacion_pago REAL` en `cobro_desvios` y `cobro_reserva_usos`, de modo que los pagos a obras en UVIs desde desvíos o reservas amorticen UVIs a la cotización real de la fecha de pago y no a la cotización base histórica del contrato[cite: 1].
   * Corregir la consulta de `get_kpis_convenios_global()` para que `total_transito_ars` calcule el saldo remanente `(cantidad_moneda - cantidad_moneda_cobrada) * cotizacion_solicitud`[cite: 1].
   * Agregar validaciones de piso y techo en `update_solicitud_convenio` y `update_convenio`, y borrado simétrico por `grupo_compensacion_id` en `delete_desvio_recupero` y `delete_reserva_uso_recupero`[cite: 1].

### 🏗️ Fase 3: Refactorización Arquitectónica Estructural (Mediano Plazo) — *Desacoplamiento del Monolito sin Romper Compatibilidad*

Para desacoplar las más de 5.000 líneas de `database.py` **sin tener que modificar ni un solo `import database as db` en `Inicio.py`, `pages/` ni `tests/`**[cite: 1], aplica el **Patrón Fachada (Facade Pattern)** creando un paquete `db_core/` y dejando a `database.py` como re-exportador limpio:

1. **Estructura de paquetes propuesta:**
```text
decretometro/
├── db_core/
│   ├── __init__.py
│   ├── connection.py        # get_connection(), db_session(), constantes TOLERANCE
│   ├── migrations.py        # init_db() y diccionario MIGRACIONES (v1 a v49)
│   ├── repo_catalogos.py    # obras, obra_adicionales, proveedores, gastos_fun, monedas_indices, op_bejerman
│   ├── repo_decretos.py     # decretos, cuotas, solicitudes_financiamiento, check_estado_decreto
│   ├── repo_convenios.py    # convenios, convenio_obras, convenio_solicitudes, métricas UVI/USD
│   ├── repo_cobros.py       # cobros, distribuciones, fin_original_usos, reservas, desvios, compensaciones
│   ├── repo_habituales.py   # aportes_funcionamiento, aportes_sueldo, aportes_sac, fondos_propios
│   └── repo_trazabilidad.py # get_resumen_contrato_obra (FIFO), grafos y consultas para reportes
└── database.py              # Fachada compatible: from db_core.connection import *; from db_core.repo_... import *
```
2. **Secuencia de extracción segura (Paso a Paso):**
   * **Paso 1:** Extraer `connection.py` y `migrations.py` primero. En `migrations.py`, separar la ejecución de las migraciones que requieren `PRAGMA foreign_keys = OFF` (como recreación de tablas) fuera del bloque transaccional antes de ejecutar `BEGIN IMMEDIATE`[cite: 1].
   * **Paso 2:** Extraer `repo_catalogos.py` y `repo_habituales.py` (son los módulos con menor acoplamiento cruzado) e importarlos dentro de `database.py`[cite: 1].
   * **Paso 3:** Extraer `repo_convenios.py` y `repo_decretos.py`, seguidos por `repo_cobros.py` y `repo_trazabilidad.py`, corriendo `pytest` tras cada extracción individual para garantizar cero regresiones en la interfaz pública de `database.py`[cite: 1].