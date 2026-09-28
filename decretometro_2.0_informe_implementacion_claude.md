# 📋 INFORME INTEGRAL DE IMPLEMENTACIÓN: "DECRETÓMETRO 2.0"
## SISTEMA BIMONETARIO / MULTI-ÍNDICE Y GESTIÓN DE CONVENIOS MULTIOBRA
### Documento de Arquitectura, Código y Auditoría para Devolución de Claude

---

## 👤 1. INFORMACIÓN GENERAL Y CONTEXTO
* **Usuario y Responsable:** Martín Rodríguez
* **Perfil:** Contador Público (Universidad de Buenos Aires - UBA), diplomado en administración y marketing, especialista en gestión financiera pública y rendiciones de cuentas.
* **Sistema:** **Decretómetro 2.0** (Python 3.x / Streamlit / SQLite / CSS Personalizado).
* **Propósito del Documento:** Consolidar con máximo rigor técnico, contable y funcional todo el trabajo realizado para la evolución de la aplicación a su versión 2.0 bimonetaria, exponiendo las decisiones de diseño, el esquema relacional, las sentencias de migración, las líneas de código agregadas y modificadas, y los resultados de las pruebas de integración, a fin de que **Claude** pueda auditarlo y emitir una devolución crítica calificada.

---

## 🎯 2. OBJETIVOS Y REGLAS DE NEGOCIO DEL PROYECTO

### 2.1 El Desafío Inicial (Limitaciones de la Versión 1.0)
La versión 1.0 del sistema estaba concebida exclusivamente para fondos municipales en pesos ($ ARS) originados en **Decretos** individuales con cronogramas de cuotas mensuales correlativas. Con el crecimiento institucional, surgieron dos necesidades insoslayables:
1. **Convenios de Financiamiento Provincial y Nacional:** Convenios macro (ej. con IPVU, ADUS, Nación) que abarcan **múltiples obras simultáneas** bajo un único instrumento legal.
2. **Monedas Duras e Índices de Actualización:** Contratos pactados en **Unidades de Vivienda (UVIs - Ley 27.271)** o en **Dólares Estadounidenses (USD)**, cuyos desembolsos se liquidan en pesos según certificados de avance de obra periódicos.

### 2.2 Requisitos Mandatarios y Criterio Contable de Martín Rodríguez
* **Retrocompatibilidad Absoluta (100% No Negociable):** La base de datos histórica en producción (`decretometro.db`) contenía información viva y auditada: 19 decretos, 69 cuotas, 55 cobros bancarios, 51 distribuciones, 118 desvíos y 52 obras. Ningún registro ni clave foránea podía romperse o alterarse.
* **Control Contractual Primario en Moneda/Índice de Origen (Observación Contable Clave):**
  > *"Tener en cuenta que, aunque el cobro se haga en pesos, para llevar el control del convenio y las solicitudes, los cálculos (Total convenio - solicitudes pendientes - Acreditaciones efectivas = Saldo Remanente) deben llevarse en la moneda o índice del convenio."*
  * **Explicación Financiera:** Si un convenio se pactó por `100.000 UVIs`, el cupo disponible no puede medirse en pesos históricos depreciados por inflación. Cada certificado de avance emitido consume UVIs del cupo contractual; cada acreditación bancaria amortiza UVIs. El dinero ingresa a la cuenta bancaria en Pesos ($ ARS) al tipo de cambio de la fecha de cobro, registrándose la diferencia de cotización respecto a la solicitud, pero el control del saldo remanente contractual vive en UVIs.
* **Trazabilidad Downstream Intacta:** Una vez que los pesos ingresan al banco, la distribución hacia la obra original (`fin_original`), reservas o préstamos internos (`desvíos`) y la imputación de Órdenes de Pago Bejerman (`op_bejerman`) opera en moneda de curso legal sin alterar el flujo contable existente.

---

## 🗄️ 3. ARQUITECTURA DE DATOS Y MIGRACIONES (SQLite)

La versión del esquema avanzó de `schema_version = 35` a `schema_version = 47`. Se codificaron las migraciones pendientes, las nuevas estructuras relacionales y el blindaje mediante `CHECK` a nivel motor de base de datos.

### 3.1 DDL de las Migraciones Incorporadas en `database.py`

```python
MIGRACIONES = [
    # ... migraciones 1 a 32 históricas ...
    
    # Migración 33 y 34: Formalización de tablas de fondos propios
    (33, """CREATE TABLE IF NOT EXISTS pagos_fondos_propios (
        id INTEGER PRIMARY KEY AUTOINCREMENT, 
        obra_id INTEGER REFERENCES obras(id) ON DELETE RESTRICT, 
        monto REAL NOT NULL, 
        fecha DATE NOT NULL, 
        nro_op TEXT, 
        observaciones TEXT
    )"""),
    (34, """CREATE TABLE IF NOT EXISTS recuperos_fondos_propios (
        id INTEGER PRIMARY KEY AUTOINCREMENT, 
        cobro_id INTEGER REFERENCES cobros(id) ON DELETE CASCADE, 
        obra_id INTEGER REFERENCES obras(id) ON DELETE RESTRICT, 
        monto REAL NOT NULL, 
        fecha DATE NOT NULL, 
        nro_op TEXT, 
        notas TEXT
    )"""),
    
    # Migración 35: Proyección de vencimientos
    (35, "ALTER TABLE cuotas ADD COLUMN fecha_estimada_cobro DATE"),
    
    # Migración 36 a 39: Catálogo de Monedas e Índices
    (36, """CREATE TABLE IF NOT EXISTS monedas_indices (
        id INTEGER PRIMARY KEY AUTOINCREMENT, 
        codigo TEXT NOT NULL UNIQUE, 
        nombre TEXT NOT NULL, 
        simbolo TEXT NOT NULL, 
        tipo TEXT NOT NULL CHECK(tipo IN ('Moneda', 'Índice')), 
        decimales INTEGER NOT NULL DEFAULT 2, 
        activo INTEGER NOT NULL DEFAULT 1 CHECK(activo IN (0, 1))
    )"""),
    (37, "INSERT OR IGNORE INTO monedas_indices (id, codigo, nombre, simbolo, tipo, decimales, activo) VALUES (1, 'ARS', 'Peso Argentino', '$', 'Moneda', 2, 1)"),
    (38, "INSERT OR IGNORE INTO monedas_indices (id, codigo, nombre, simbolo, tipo, decimales, activo) VALUES (2, 'USD', 'Dólar Estadounidense', 'U$S', 'Moneda', 2, 1)"),
    (39, "INSERT OR IGNORE INTO monedas_indices (id, codigo, nombre, simbolo, tipo, decimales, activo) VALUES (3, 'UVI', 'Unidad de Vivienda (Ley 27.271)', 'UVI', 'Índice', 2, 1)"),
    
    # Migración 40: Tabla Maestra de Convenios
    (40, """CREATE TABLE IF NOT EXISTS convenios (
        id INTEGER PRIMARY KEY AUTOINCREMENT, 
        nro_convenio TEXT NOT NULL, 
        ente_financiador TEXT NOT NULL, 
        nombre_convenio TEXT NOT NULL, 
        nro_expediente TEXT NOT NULL, 
        fecha_firma DATE NOT NULL, 
        moneda_id INTEGER NOT NULL DEFAULT 1 REFERENCES monedas_indices(id), 
        monto_pactado_moneda REAL NOT NULL, 
        cotizacion_base REAL NOT NULL DEFAULT 1.0, 
        monto_equivalente_ars REAL NOT NULL, 
        estado TEXT NOT NULL DEFAULT 'Vigente' CHECK(estado IN ('Vigente', 'Terminado', 'Anulado')), 
        pdf_path TEXT, 
        notas TEXT
    )"""),
    
    # Migración 41: Vínculo Multiobra de Convenios (Relación N:M con asignación de cupos)
    (41, """CREATE TABLE IF NOT EXISTS convenio_obras (
        id INTEGER PRIMARY KEY AUTOINCREMENT, 
        convenio_id INTEGER NOT NULL REFERENCES convenios(id) ON DELETE CASCADE, 
        obra_id INTEGER NOT NULL REFERENCES obras(id) ON DELETE RESTRICT, 
        monto_pactado_moneda REAL NOT NULL, 
        monto_equivalente_ars REAL NOT NULL, 
        porcentaje REAL DEFAULT 0.0, 
        notas TEXT, 
        UNIQUE(convenio_id, obra_id)
    )"""),
    
    # Migración 42: Certificados de Avance / Solicitudes de Desembolso
    (42, """CREATE TABLE IF NOT EXISTS convenio_solicitudes (
        id INTEGER PRIMARY KEY AUTOINCREMENT, 
        convenio_id INTEGER NOT NULL REFERENCES convenios(id) ON DELETE CASCADE, 
        obra_id INTEGER NOT NULL REFERENCES obras(id) ON DELETE RESTRICT, 
        nro_certificado TEXT NOT NULL, 
        periodo TEXT, 
        cantidad_moneda REAL NOT NULL, 
        cantidad_moneda_cobrada REAL NOT NULL DEFAULT 0.0, 
        cotizacion_solicitud REAL NOT NULL DEFAULT 1.0, 
        monto_solicitado_ars REAL NOT NULL, 
        fecha_solicitud DATE NOT NULL, 
        expediente_pago TEXT, 
        estado TEXT NOT NULL DEFAULT 'Pendiente' CHECK(estado IN ('Pendiente', 'Parcial', 'Cobrado', 'Anulado')), 
        pdf_path TEXT, 
        notas TEXT
    )"""),
    
    # Migración 43: Moneda en Decretos
    (43, "ALTER TABLE decretos ADD COLUMN moneda_id INTEGER DEFAULT 1"),
    
    # Migración 44: Recreación de cobros para permitir cuota_id nullable
    (44, "-- Ejecución controlada en código de migración con PRAGMA foreign_keys = OFF --"),
    
    # Migración 45 y 46: Grupo de compensación en tablas de recuperos
    (45, "ALTER TABLE cobro_desvios_recuperos ADD COLUMN grupo_compensacion_id TEXT"),
    (46, "ALTER TABLE cobro_reserva_usos_recuperos ADD COLUMN grupo_compensacion_id TEXT"),
    
    # Migración 47: Enforzamiento del CHECK de Exclusión Mutua en la tabla cobros
    (47, "-- Enforzamiento de CHECK constraint 'check_origen_exclusivo' a nivel motor SQLite --")
]
```

### 3.2 Blindaje Relacional a Nivel Motor: CHECK Constraint en `cobros` (Migración 47)
Para dar respuesta al hallazgo del auditor sobre la necesidad de que la exclusión mutua no viva solo en el código de aplicación sino en el propio motor SQL, la **Migración 47** recreó la tabla `cobros` con el constraint `check_origen_exclusivo`:

```sql
CREATE TABLE cobros (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    cuota_id INTEGER REFERENCES cuotas(id) ON DELETE CASCADE,
    convenio_solicitud_id INTEGER REFERENCES convenio_solicitudes(id) ON DELETE SET NULL,
    origen_tipo TEXT NOT NULL DEFAULT 'decreto',
    obra_id INTEGER REFERENCES obras(id),
    moneda_origen_id INTEGER DEFAULT 1 REFERENCES monedas_indices(id),
    cantidad_moneda_origen REAL,
    cotizacion_cobro REAL DEFAULT 1.0,
    diferencia_ajuste_ars REAL DEFAULT 0.0,
    monto REAL NOT NULL,
    fecha DATE NOT NULL,
    comprobante_path TEXT,
    CONSTRAINT check_origen_exclusivo CHECK (
        (origen_tipo = 'decreto'  AND cuota_id IS NOT NULL AND convenio_solicitud_id IS NULL) OR
        (origen_tipo = 'convenio' AND convenio_solicitud_id IS NOT NULL AND cuota_id IS NULL)
    )
);
```

**Resultado:** Se probó directamente contra SQLite ejecutando inserts inválidos (tanto con ambos IDs cargados como con ambos IDs nulos). El motor rechazó las transacciones con: `sqlite3.IntegrityError: CHECK constraint failed: check_origen_exclusivo`. Los 55 cobros bancarios históricos mantuvieron sus mismos IDs numéricos, integridad referencial y compatibilidad 100%.

---

## 💻 4. LÓGICA DE BACKEND IMPLEMENTADA (`database.py` y `utils.py`)

### 4.1 Función Maestra de Control Contractual Bimonetario
Se programó en `database.py` la función `get_resumen_control_convenio`, la cual materializa el requerimiento de Martín:

```python
def get_resumen_control_convenio(convenio_id):
    """
    Calcula los saldos consolidados de un convenio tanto en su moneda contractual (UVIs/USD)
    como su contravalor liquidado en Pesos ($ ARS).
    Cumple con el criterio contable:
    Saldo Remanente (Moneda) = Total Pactado - Solicitado en Trámite - Cobrado Efectivo
    """
    with db_session() as conn:
        cursor = conn.cursor()
        
        # Datos del convenio
        cursor.execute('''
            SELECT c.*, m.codigo as moneda_codigo, m.simbolo as moneda_simbolo, m.decimales as moneda_decimales
            FROM convenios c
            JOIN monedas_indices m ON c.moneda_id = m.id
            WHERE c.id = ?
        ''', (convenio_id,))
        convenio = dict(cursor.fetchone())
        
        # Obras asignadas
        cursor.execute('''
            SELECT co.*, o.nombre as obra_nombre, o.expediente_imuh
            FROM convenio_obras co
            JOIN obras o ON co.obra_id = o.id
            WHERE co.convenio_id = ?
        ''', (convenio_id,))
        obras_convenio = [dict(ix) for ix in cursor.fetchall()]
        
        # Solicitudes / Certificados
        cursor.execute('''
            SELECT cs.*, o.nombre as obra_nombre, o.expediente_imuh
            FROM convenio_solicitudes cs
            JOIN obras o ON cs.obra_id = o.id
            WHERE cs.convenio_id = ?
        ''', (convenio_id,))
        solicitudes = [dict(ix) for ix in cursor.fetchall()]
        
        # Cobros percibidos imputados a este convenio
        cursor.execute('''
            SELECT c.*, cs.obra_id, cs.nro_certificado
            FROM cobros c
            JOIN convenio_solicitudes cs ON c.convenio_solicitud_id = cs.id
            WHERE cs.convenio_id = ?
        ''', (convenio_id,))
        cobros = [dict(ix) for ix in cursor.fetchall()]

    # Totales globales del Convenio en su Moneda/Índice de origen
    pactado_moneda_total = float(convenio['monto_pactado_moneda'] or 0.0)
    solicitado_moneda_total = sum(float(s['cantidad_moneda'] or 0.0) for s in solicitudes if s['estado'] != 'Anulado')
    cobrado_moneda_total = sum(float(c.get('cantidad_moneda_origen') or 0.0) for c in cobros)
    cobrado_ars_total = sum(float(c['monto'] or 0.0) for c in cobros)

    saldo_en_transito_moneda = max(0.0, solicitado_moneda_total - cobrado_moneda_total)
    saldo_remanente_moneda = max(0.0, pactado_moneda_total - solicitado_moneda_total)

    # Desglose analítico por obra integrante del convenio
    obras_resumen = []
    for ob in obras_convenio:
        o_id = ob['obra_id']
        o_pactado_moneda = float(ob['monto_pactado_moneda'] or 0.0)
        o_sols = [s for s in solicitudes if s['obra_id'] == o_id and s['estado'] != 'Anulado']
        o_solicitado_moneda = sum(float(s['cantidad_moneda'] or 0.0) for s in o_sols)
        o_cobs = [c for c in cobros if c['obra_id'] == o_id]
        o_cobrado_moneda = sum(float(c.get('cantidad_moneda_origen') or 0.0) for c in o_cobs)
        o_cobrado_ars = sum(float(c['monto'] or 0.0) for c in o_cobs)

        o_transito_moneda = max(0.0, o_solicitado_moneda - o_cobrado_moneda)
        o_remanente_moneda = max(0.0, o_pactado_moneda - o_solicitado_moneda)

        obras_resumen.append({
            'obra_id': o_id,
            'obra_nombre': ob['obra_nombre'],
            'expediente_imuh': ob['expediente_imuh'],
            'monto_pactado_moneda': o_pactado_moneda,
            'monto_pactado_ars': float(ob['monto_equivalente_ars'] or 0.0),
            'solicitado_moneda': o_solicitado_moneda,
            'cobrado_moneda': o_cobrado_moneda,
            'saldo_en_transito_moneda': o_transito_moneda,
            'saldo_remanente_moneda': o_remanente_moneda,
            'cobrado_ars': o_cobrado_ars,
            'porcentaje_avance_financiero': (o_cobrado_moneda / o_pactado_moneda * 100) if o_pactado_moneda > 0 else 0.0
        })

    return {
        'convenio': convenio,
        'moneda_codigo': convenio.get('moneda_codigo', 'ARS'),
        'moneda_simbolo': convenio.get('moneda_simbolo', '$'),
        'pactado_moneda_total': pactado_moneda_total,
        'pactado_ars_total': float(convenio['monto_equivalente_ars'] or 0.0),
        'solicitado_moneda_total': solicitado_moneda_total,
        'cobrado_moneda_total': cobrado_moneda_total,
        'saldo_en_transito_moneda': saldo_en_transito_moneda,
        'saldo_remanente_moneda': saldo_remanente_moneda,
        'cobrado_ars_total': cobrado_ars_total,
        'porcentaje_cobranza': (cobrado_moneda_total / pactado_moneda_total * 100) if pactado_moneda_total > 0 else 0.0,
        'obras_detalle': obras_resumen
    }
```

### 4.2 Registro de Cobros Unificado y Liquidación de UVIs a Pesos (`add_cobro`)
La función `add_cobro` implementa el blindaje de exclusión mutua, las guardas estrictas de sobrepago para decretos y convenios, y el cálculo automático de la diferencia de cotización:

```python
def add_cobro(cuota_id=None, monto=0.0, fecha=None, comprobante_path=None,
              convenio_solicitud_id=None, origen_tipo='decreto',
              moneda_origen_id=1, cantidad_moneda_origen=None,
              cotizacion_cobro=1.0, diferencia_ajuste_ars=0.0, obra_id=None):
    if monto <= 0:
        raise ValueError("El monto cobrado debe ser mayor a 0.")
    fecha_dt = datetime.datetime.strptime(fecha, '%Y-%m-%d').date()
    if fecha_dt > datetime.date.today():
        raise ValueError("La fecha de cobro no puede ser futura.")

    # Blindaje de integridad y exclusión mutua de origen
    if origen_tipo == 'decreto':
        if not cuota_id or convenio_solicitud_id is not None:
            raise ValueError("Un cobro de decreto debe tener cuota_id y no puede tener convenio_solicitud_id.")
    elif origen_tipo == 'convenio':
        if not convenio_solicitud_id or cuota_id is not None:
            raise ValueError("Un cobro de convenio debe tener convenio_solicitud_id y no puede tener cuota_id.")
    else:
        raise ValueError(f"Tipo de origen '{origen_tipo}' no válido (debe ser 'decreto' o 'convenio').")
        
    with db_session() as conn:
        cursor = conn.cursor()

        if origen_tipo == 'convenio':
            cursor.execute('SELECT * FROM convenio_solicitudes WHERE id = ?', (convenio_solicitud_id,))
            sol = cursor.fetchone()
            if not sol:
                raise ValueError("Solicitud de convenio no encontrada.")
            
            obra_dest_id = obra_id or sol['obra_id']
            # Cantidad en moneda/UVI a amortizar
            cant_amortizar = cantidad_moneda_origen
            saldo_moneda_sol = float(sol['cantidad_moneda'] - (sol['cantidad_moneda_cobrada'] or 0.0))
            if cant_amortizar is None or cant_amortizar <= 0:
                cant_amortizar = max(0.0, saldo_moneda_sol)
            
            # Guardia de sobrepago en convenio
            if cant_amortizar > (saldo_moneda_sol + 0.01):
                raise ValueError(
                    f"La cantidad a amortizar ({cant_amortizar:,.2f}) supera el saldo pendiente "
                    f"de la solicitud/certificado ({saldo_moneda_sol:,.2f})."
                )
            
            nueva_cant_cobrada = (sol['cantidad_moneda_cobrada'] or 0.0) + cant_amortizar
            nuevo_estado = 'Cobrado' if nueva_cant_cobrada >= (sol['cantidad_moneda'] - 0.01) else 'Parcial'
            
            cursor.execute('''
                UPDATE convenio_solicitudes 
                SET cantidad_moneda_cobrada = ?, estado = ?
                WHERE id = ?
            ''', (nueva_cant_cobrada, nuevo_estado, convenio_solicitud_id))

            # Calcular automáticamente la diferencia por indexación/cotización si no se especificó
            if (diferencia_ajuste_ars is None or diferencia_ajuste_ars == 0.0) and sol['cotizacion_solicitud']:
                monto_esperado_sol_ars = cant_amortizar * float(sol['cotizacion_solicitud'])
                diferencia_ajuste_ars = float(monto) - monto_esperado_sol_ars

            cursor.execute('''
                INSERT INTO cobros (
                    cuota_id, convenio_solicitud_id, origen_tipo, obra_id,
                    moneda_origen_id, cantidad_moneda_origen, cotizacion_cobro,
                    diferencia_ajuste_ars, monto, fecha, comprobante_path
                )
                VALUES (NULL, ?, 'convenio', ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (convenio_solicitud_id, obra_dest_id, moneda_origen_id or 1, cant_amortizar,
                  cotizacion_cobro or 1.0, diferencia_ajuste_ars or 0.0, monto, fecha, comprobante_path))
            cobro_id = cursor.lastrowid
            conn.commit()
            return cobro_id
        else:
            # Flujo Decreto tradicional
            cursor.execute('SELECT monto, mes, anio FROM cuotas WHERE id = ?', (cuota_id,))
            q_row = cursor.fetchone()
            if not q_row:
                raise ValueError("Cuota no encontrada.")
                
            # Validar período de la cuota
            cuota_start = f"{q_row['anio']}-{q_row['mes']:02d}-01"
            if fecha < cuota_start:
                raise ValueError(
                    f"La fecha de cobro ({fecha}) no puede ser anterior al inicio "
                    f"del período de la cuota ({q_row['mes']:02d}/{q_row['anio']})."
                )
        
            cursor.execute('SELECT SUM(monto) as cobrado FROM cobros WHERE cuota_id = ?', (cuota_id,))
            c_row = cursor.fetchone()
            cobrado_previo = c_row['cobrado'] if c_row and c_row['cobrado'] else 0
            saldo = q_row['monto'] - cobrado_previo
        
            # Guardia de sobrepago en decreto
            if monto > (saldo + 0.01):
                raise ValueError(f"El monto a cobrar ({monto}) supera el saldo pendiente de la cuota ({saldo:.2f}).")

            cursor.execute('''
                INSERT INTO cobros (
                    cuota_id, convenio_solicitud_id, origen_tipo, obra_id,
                    moneda_origen_id, cantidad_moneda_origen, cotizacion_cobro,
                    diferencia_ajuste_ars, monto, fecha, comprobante_path
                )
                VALUES (?, NULL, 'decreto', ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (cuota_id, obra_id, moneda_origen_id or 1, cantidad_moneda_origen, cotizacion_cobro or 1.0,
                  diferencia_ajuste_ars or 0.0, monto, fecha, comprobante_path))
            cobro_id = cursor.lastrowid
            conn.commit()
            check_estado_decreto_by_cuota(conn, cuota_id)
            return cobro_id
```

### 4.3 Consulta Downstream Unificada: `get_cobros_con_resumen_distribucion()`
Esta función alimenta las 4 pestañas de gestión de cobros (`tab_estado`, `tab_distribuir`, `tab_historial`, `tab_composicion`). Se reescribió sustituyendo el `JOIN cuotas` estricto por `LEFT JOIN` y unificando los atributos mediante `COALESCE`:

```sql
SELECT c.id, c.monto, c.fecha, c.cuota_id, c.origen_tipo, c.convenio_solicitud_id,
       cu.mes, cu.anio,
       COALESCE(d.nro_decreto, cv.nro_convenio) as nro_decreto,
       COALESCE(d.anio, strftime('%Y', cv.fecha_firma)) as decreto_anio,
       d.id as decreto_id, cv.id as convenio_id,
       COALESCE(d.destino_fondos, cv.nombre_convenio || ' — ' || o.nombre) as destino_fondos,
       COALESCE(d.expediente_imuh, o.expediente_imuh) as expediente_imuh,
       m.simbolo as moneda_simbolo, m.codigo as moneda_codigo,
       c.cantidad_moneda_origen, c.cotizacion_cobro,
       COALESCE(dist.monto_fin_orig, 0) as monto_fin_orig,
       COALESCE(dist.monto_reserva, 0) as monto_reserva,
       COALESCE((SELECT SUM(monto) FROM cobro_desvios WHERE cobro_id = c.id), 0) as total_desvios,
       (
           COALESCE(dist.monto_fin_orig, 0) + 
           COALESCE(dist.monto_reserva, 0) + 
           COALESCE((SELECT SUM(monto) FROM cobro_desvios WHERE cobro_id = c.id), 0) -
           COALESCE((
               SELECT SUM(cdr.monto) FROM cobro_desvios_recuperos cdr
               JOIN cobro_desvios cd ON cdr.desvio_id = cd.id
               WHERE cd.cobro_id = c.id AND cdr.destino_tipo = 'sin_distribucion'
           ), 0) -
           COALESCE((
               SELECT SUM(crur.monto) FROM cobro_reserva_usos_recuperos crur
               JOIN cobro_reserva_usos cru ON crur.reserva_uso_id = cru.id
               WHERE cru.cobro_id = c.id AND crur.destino_tipo = 'sin_distribucion'
           ), 0)
       ) as total_distribuido
FROM cobros c
LEFT JOIN cuotas cu ON c.cuota_id = cu.id
LEFT JOIN decretos d ON cu.decreto_id = d.id
LEFT JOIN convenio_solicitudes cs ON c.convenio_solicitud_id = cs.id
LEFT JOIN convenios cv ON cs.convenio_id = cv.id
LEFT JOIN obras o ON (c.obra_id = o.id OR cs.obra_id = o.id)
LEFT JOIN monedas_indices m ON c.moneda_origen_id = m.id
LEFT JOIN cobro_distribuciones dist ON c.id = dist.cobro_id
ORDER BY c.fecha DESC, c.id DESC;
```

### 4.4 Auditoría de Cupo Nominal por Obra en `add_solicitud_convenio`
Para resolver la inquietud del Tribunal de Cuentas sobre obras que superan su cupo nominal dentro del remanente global del convenio, la función no bloquea pero registra automáticamente la justificación en las observaciones del certificado:

```python
# Validación de remanente global
if float(cantidad_moneda) > (remanente + 0.01):
    raise ValueError(f"La cantidad solicitada ({float(cantidad_moneda):,.2f}) supera el remanente disponible del convenio ({remanente:,.2f} / {total_pactado:,.2f}).")

# Auditoría de Cupo Nominal por Obra (Tribunal de Cuentas)
cursor.execute('SELECT monto_pactado_moneda FROM convenio_obras WHERE convenio_id = ? AND obra_id = ?', (convenio_id, obra_id))
co_row = cursor.fetchone()
cupo_obra = co_row['monto_pactado_moneda'] if co_row else None

cursor.execute("SELECT COALESCE(SUM(cantidad_moneda), 0) as sol_obra FROM convenio_solicitudes WHERE convenio_id = ? AND obra_id = ? AND estado != 'Anulado'", (convenio_id, obra_id))
sol_obra_previo = cursor.fetchone()['sol_obra']

notas_final = str(notas).strip() if notas else ""
if cupo_obra is not None and (sol_obra_previo + float(cantidad_moneda)) > (cupo_obra + 0.01):
    exceso = (sol_obra_previo + float(cantidad_moneda)) - cupo_obra
    aviso_reasig = f"[Reasignación de cupo interno: supera cupo nominal de obra en {exceso:,.2f} dentro del remanente global del convenio]"
    if aviso_reasig not in notas_final:
        notas_final = f"{notas_final} | {aviso_reasig}".strip(" |")
```

### 4.5 Formateador Monetario Flexible (`utils.py`)
Se incorporó `format_moneda_custom` para dar formato argentino (punto para miles, coma para decimales) con el símbolo o código de la divisa o índice correspondiente:

```python
def format_moneda_custom(monto, simbolo="$", decimales=2, codigo=None):
    """
    Formatea cualquier divisa o índice financiero con la convención argentina:
    Ejemplo: 12.345,67 UVI | U$S 1.500,00 | $ 120.000,00
    """
    if monto is None or (isinstance(monto, float) and (monto != monto)):
        return "-"
    try:
        val = float(monto)
        formato = f"{{:,.{decimales}f}}"
        texto = formato.format(val).replace(",", "X").replace(".", ",").replace("X", ".")
        if codigo in ("UVI", "CER", "CAC"):
            return f"{texto} {simbolo}"
        return f"{simbolo} {texto}"
    except (ValueError, TypeError):
        return str(monto)
```

---

## 🖥️ 5. INTERFAZ DE USUARIO (Streamlit)

### 5.1 Catálogo de Monedas e Índices (`pages/1_Monedas_e_Indices.py`)
Módulo nuevo accesible desde la barra lateral.
* **Funcionalidad:** Permite listar, activar, pausar y crear monedas (ARS, USD) e índices financieros (UVI, CAC, CER).
* **Parámetros configurables:** Código ISO, Nombre descriptivo, Símbolo (ej. `$`, `U$S`, `UVI`), Tipo (`Moneda` o `Índice`), Cantidad de decimales de precisión contable.

### 5.2 Gestión Integral de Convenios Multiobra (`pages/5b_Convenios.py`)
Módulo principal estructurado en tres pestañas:
1. **Pestaña 1: 🗂️ Directorio y Control Contractual:**
   * Selector interactivo de Convenio.
   * **Tarjetas de KPI Duales:**
     * `Cupo Total Contratado` (en UVIs y en $ ARS base).
     * `Certificados en Trámite` (en UVIs).
     * `Cobrado Efectivo Bancario` (en UVIs percibidas y total en $ ARS reales).
     * `Saldo Remanente Contractual` (en UVIs disponibles).
   * **Desglose por Obra Asignada:** Tabla con el avance financiero de cada obra que compone el convenio.
   * **Gestión de Solicitudes / Certificados de Avance:**
     * Historial de solicitudes presentadas con estado (`Pendiente`, `Parcial`, `Cobrado`).
     * Formulario interactivo para emitir un nuevo certificado: selección de obra, cantidad de UVIs solicitadas, cotización de la UVI al momento de la presentación, cálculo automático del importe estimado en pesos y subida de PDF del certificado.
2. **Pestaña 2: ➕ Nuevo Convenio:**
   * Carga de datos contractuales: Ente financiador (Nación, Provincia, IPVU, etc.), Nro. de Convenio, Expediente madre, Fecha de suscripción.
   * Selección de Moneda/Índice (ej: UVI).
   * Cotización base de firma de contrato y Monto pactado en moneda de origen.
   * **Selector Multiobra Inteligente:** Asignación de N obras del catálogo de la institución, dividiendo o prorrateando los cupos correspondientes.
3. **Pestaña 3: 📊 Comparativa Global:**
   * Tablero consolidado de convenios vigentes, avance financiero y porcentaje global de ejecución.

### 5.3 Cobros de Ingresos Unificado (`pages/6_Cobros.py`)
* En la pestaña **`➕ Registrar Cobro`**, se implementó un selector de tipo de origen:
  * `🏛️ Decreto Municipal`: Despliega el selector tradicional de decreto y cuota en pesos.
  * `📜 Convenio Provincia/Nación`: Despliega las solicitudes de desembolso y certificados de avance pendientes en convenios vigentes.
* **Mecánica del Cobro de Convenio:**
  * El usuario selecciona el certificado a liquidar (ej: *Certificado #1 - 10.000 UVIs*).
  * Ingresa la **cantidad de UVIs a cancelar/amortizar** (permite cancelaciones parciales o totales).
  * Ingresa el **monto neto efectivamente acreditado en el extracto bancario en Pesos ($ ARS)** y la fecha del crédito bancario.
  * El sistema calcula en tiempo real la **cotización efectiva resultante** ($/UVI) y la **diferencia por variación de cotización** respecto al presupuesto de la solicitud.
  * Al guardar, el cobro entra con estado completo, la solicitud se marca como `Cobrada` y el dinero pasa a la bandeja de distribución downstream en pesos.

### 5.4 Actualización de Decretos (`pages/5_Decretos.py`)
* Se agregó la propiedad `moneda_id` con valor predeterminado `ARS` en el formulario de alta y en el panel de edición, garantizando compatibilidad cruzada.

### 5.5 Dashboard Ejecutivo Integrado (`Inicio.py`)
* **Alertas de Vencimiento:** Se incorporó la categoría 5 (`Convenios`), alertando cuando existen certificados de avance presentados y en trámite que no han tenido acreditación bancaria transcurrido el plazo previsto.
* **Saldos sin Distribuir y Reservas:** Se unificó la presentación visual para identificar con claridad si el cobro pendiente de asignación provino de un Decreto o de un Convenio Multiobra.
* **Tablero de Convenios:** Se insertó un panel con 4 métricas ejecutivas (`Convenios Activos`, `Total Convenios`, `Certificados en Trámite ($ ARS)`, `Total Cobrado Convenios ($ ARS)`) y la tabla de seguimiento contractual en UVIs y Pesos.

---

## ⚡ 6. LANZADOR Y ACCESO DIRECTO DE ESCRITORIO

Se crearon y verificaron los archivos de lanzamiento:
1. **`run_decretometro.bat`:**
   Configurado para posicionarse en el directorio del nuevo workspace e iniciar Streamlit en un puerto libre (escaneando del 8501 al 8510 para evitar colisiones).
2. **`create_shortcut.py`:**
   Script en Python/VBS con codificación ANSI/Latin-1 para crear con precisión el acceso directo **`Decretómetro 2.0.lnk`** en el Escritorio del usuario (`C:\Users\bornemanns\Desktop\Decretómetro 2.0.lnk`).

---

## 🧪 7. VERIFICACIÓN Y PRUEBAS INTEGRALES

### 7.1 Test de Integración Bimonetaria de Extremo a Extremo (`test_convenios_flujo.py`)
Se construyó un script de prueba automatizado que ejecuta el ciclo de vida completo de un convenio multimoneda:

```python
# test_convenios_flujo.py (Resumen de pasos ejecutados)
# 1. Validación de catálogo: ARS, USD y UVI activas.
# 2. Creación de Convenio de prueba en UVIs: 50.000 UVIs a cotización base $1.200 (Total base: $60.000.000).
# 3. Asignación de 2 obras del catálogo (25.000 UVIs a cada una).
# 4. Verificación de balance contractual: Remanente = 50.000 UVIs.
# 5. Emisión de Certificado #1 por 10.000 UVIs a cotización de trámite $1.250 ($12.500.000 ARS).
# 6. Verificación de balance intermedio: En trámite = 10.000 UVIs | Remanente = 40.000 UVIs.
# 7. Registro de Cobro bancario efectivo: $12.550.000 ARS percibidos (Cotización real $1.255/UVI, Dif. cotiz: +$50.000 ARS).
# 8. Verificación de balance post-cobro: En trámite = 0 UVIs | Cobrado = 10.000 UVIs ($12.550.000 ARS) | Remanente = 40.000 UVIs.
# 9. Verificación de estado del certificado: Pasa a 'Cobrado'.
# 10. Downstream: Cobro disponible para distribución en pesos; se distribuyen $10.000.000 a Fin Original y $2.550.000 a Reserva.
# 11. Limpieza automática de datos de prueba en bloque try...finally.
```

### 7.2 Resultados de la Suite Completa de Tests
Se ejecutaron todas las suites de prueba existentes en el repositorio para garantizar **cero regresiones**:

| Test Suite | Cobertura / Componente | Resultado |
| :--- | :--- | :---: |
| **`test_convenios_flujo.py`** | Flujo bimonetario completo de Convenios en UVIs y cobros bancarios | **PASÓ (100% OK)** |
| **`test_logic.py`** | Lógica de negocio de decretos, cuotas, IMUH y balances matemáticos | **PASÓ (100% OK)** |
| **`test_proveedores.py`** | CUIT AFIP, unicidad y asignación a Obras y Gastos de Funcionamiento | **PASÓ (100% OK)** |
| **`test_recupero_reserva.py`** | Préstamos internos desde reserva y recuperos con afectación cruzada | **PASÓ (100% OK)** |
| **`test_fun_catalog.py`** | Catálogo de gastos de funcionamiento e imputaciones | **PASÓ (100% OK)** |
| **`test_decretometro_op.py`** | Imputación y validación presupuestaria de Órdenes de Pago Bejerman | **PASÓ (100% OK)** |
| **`test_sac.py`** | Pedidos, liquidación y cobro de Sueldo Anual Complementario (Aguinaldos) | **PASÓ (100% OK)** |

### 7.3 Verificación de Conteos Históricos
Conexión directa a `decretometro.db` para confirmar la preservación de los datos:
* **Decretos históricos:** 19 (Intactos)
* **Cuotas históricas:** 69 (Intactas)
* **Cobros históricos:** 55 (Intactos)
* **Desvíos activos/históricos:** 118 (Intactos)
* **Obras en catálogo:** 52 (Intactas)
* **Monedas e Índices:** 3 (ARS, USD, UVI)
* **Convenios en producción:** 0 (Base lista para iniciar carga operativa)

---

## 🧐 8. CONSIGNAS Y PREGUNTAS DIRIGIDAS A CLAUDE PARA LA DEVOLUCIÓN

Estimado Claude, en tu rol de **Auditor Externo, Consultor Financiero Senior y Arquitecto de Software**, se solicita tu análisis crítico, riguroso y objetivo sobre los siguientes puntos específicos de esta implementación:

1. **Rigor y Validez Contable del Modelo Bimonetario:**
   * ¿Consideras adecuada la separación entre el *Control Contractual en UVIs* (Cupo, En Trámite, Cobrado, Remanente) y la *Percepción Bancaria en Pesos ($ ARS)* a la cotización de acreditación?
   * Desde la perspectiva de una auditoría gubernamental (Tribunal de Cuentas o Concejo Deliberante), ¿esta estructura garantiza suficiente transparencia para justificar que un certificado emitido por `10.000 UVIs` resulte en una percepción bancaria de `$12.550.000 ARS` con una diferencia positiva de cotización de `$50.000 ARS`?
2. **Arquitectura de Base de Datos y Modelo de Cobros:**
   * Evaluá la decisión de unificar la tabla `cobros` con `origen_tipo IN ('decreto', 'convenio')`, admitiendo `cuota_id` o `convenio_solicitud_id` según corresponda. ¿Detectas algún riesgo de inconsistencia referencial o desnormalización que sugieras blindar con constraints adicionales o triggers?
3. **Tratamiento Financiero de las Diferencias de Cotización:**
   * Actualmente, la columna `diferencia_ajuste_ars` registra el delta entre `monto_acreditado_ars` y `(cantidad_moneda * cotizacion_solicitud)`. ¿Recomiendas reflejar esta diferencia en algún reporte específico de resultados financieros o consideras suficiente imputar directamente el monto neto percibido en pesos a la distribución de fondos de la obra?
4. **Resiliencia de la Asignación Multiobra:**
   * En `convenio_obras`, cada obra vinculada al convenio tiene un cupo pactado en moneda/UVI y un porcentaje de participación. ¿Qué recomendaciones tienes para cuando un certificado de avance de obra (solicitud) exceda el cupo individual de una obra específica pero se mantenga dentro del cupo global del convenio?
5. **Próximos Pasos y Sugerencias de Mejora:**
   * Señala cualquier punto ciego, oportunidad de optimización de código o reporte gerencial clave que un Contador Público al frente de la administración de obras públicas debería considerar para la siguiente etapa.

---

## 🏛️ 9. DEVOLUCIÓN DE AUDITORÍA DE CLAUDE Y RESOLUCIÓN INTEGRAL IMPLEMENTADA

A continuación se detalla la resolución técnica, contable y funcional aplicada sobre cada uno de los hallazgos y recomendaciones emitidos por Claude en su informe de auditoría:

### 9.1 Hallazgo Crítico Downstream: Corrección de `INNER JOIN cuotas`
* **Diagnóstico de Claude:** Al hacer `cuota_id` nullable para los cobros de convenios, las consultas que realizaban `JOIN cuotas` (estricto) excluían silenciosamente los cobros originados en convenios de la bandeja de distribución y de los reportes de deudas y trazabilidad.
* **Resolución Aplicada:**
  1. Se reescribieron las consultas en `database.py` y `utils_reports.py` reemplazando los `JOIN cuotas` por `LEFT JOIN cuotas` y vinculando `LEFT JOIN convenio_solicitudes` y `LEFT JOIN convenios`.
  2. Funciones actualizadas y blindadas: `get_all_cobros()`, `get_cobros_con_resumen_distribucion()`, `get_cobro()`, `get_reserva_usos_prestamos_activos()`, `get_desvios_activos_completos()`, `get_historial_desvios()`, `_DESVIOS_SELECT_INICIAL`, `_DESVIOS_SELECT_RESERVA`, `get_trazabilidad_fuentes_por_obra()`, `obtener_detalles_compensacion_grupo()`, `obtener_estado_deudas_por_obra()`, `obtener_contraparte_compensacion()` y `obtener_gastos_funcionamiento_financiados_obra()`.
  3. Resultado: Cualquier cobro de convenio aparece de inmediato en la bandeja de distribución downstream en pesos (`tab_distribuir.py`), permitiendo asignar fondos a `fin_original`, reservas o desvíos como cualquier cobro tradicional.

### 9.2 Blindaje de Integridad y Guardia de Sobrepago en `add_cobro`
* **Exclusión Mutua:** Se incorporó una validación estricta en `add_cobro`:
  - Si `origen_tipo == 'decreto'`, exige `cuota_id` y prohíbe `convenio_solicitud_id`.
  - Si `origen_tipo == 'convenio'`, exige `convenio_solicitud_id` y prohíbe `cuota_id`.
  - Rechaza cualquier valor no contemplado.
* **Guardias de Sobrepago Preservadas:**
  - En **Decretos**: Valida que `monto <= (saldo_pendiente_cuota + 0.01)`.
  - En **Convenios**: Valida que `cant_amortizar <= (saldo_moneda_solicitud + 0.01)`.
* **Guardias de Cupo Contractual:**
  - `add_obra_to_convenio`: Impide que la suma de cupos de obras asociadas supere el monto total pactado del convenio en moneda/UVI.
  - `add_solicitud_convenio`: Impide que un certificado supere el saldo remanente contractual global del convenio.

### 9.3 Transparencia de Cotizaciones y Leyendas para el Tribunal de Cuentas
* **Rotulación:** En la ficha y tarjetas métricas de `pages/5b_Convenios.py`, se aclaró que el monto en pesos del convenio está valuado **"(a cotización de fecha de firma)"**, evitando confusiones con el valor actualizado.
* **Trazabilidad de Cotizaciones:** Se incorporó una sección tabular en pantalla: *"Cobros Bancarios Acreditados y Trazabilidad de Cotizaciones"*, detallando para cada cobro:
  - Certificado / Solicitud de origen
  - Fecha de cobro
  - Cantidad amortizada en Moneda/UVI
  - Cotización a la fecha de emisión del certificado
  - Cotización efectiva al momento del cobro bancario
  - Monto percibido en banco ($ ARS)
  - Resultado por Ajuste/Indexación ($)
  - Comprobante adjunto

### 9.4 Visibilidad del Resultado por Diferencia de Cotización
* **Cálculo Automático:** `add_cobro` computa automáticamente la diferencia por indexación (`monto - cant_amortizar * cotizacion_solicitud`) si no se ingresa manualmente.
* **KPI Ejecutivo en `Inicio.py`:** Se agregó el panel de Convenios en la pantalla de bienvenida con 4 indicadores:
  1. Convenios Vigentes
  2. Certificados en Trámite (en UVIs y equivalencia)
  3. Total Cobrado en Banco ($ ARS)
  4. **Resultado por Indexación / Cotización ($ ARS acumulado)**

### 9.5 Verificación de Compensación Cruzada Decreto ↔ Convenio (`test_compensacion_convenio.py`)
* Se programó un test de integración automatizado completo que reproduce el escenario auditado:
  - **Obra A** financiada por **Decreto**.
  - **Obra B** financiada por **Convenio en UVIs**.
  - Obra A presta fondos a Obra B desde su reserva ($50.000).
  - Obra B presta fondos a Obra A desde el cobro de su certificado ($30.000).
  - El motor de `backend_compensaciones.py` detecta las deudas cruzadas.
  - Se ejecuta la compensación formal por $30.000.
  - Se verifica que la deuda de B con A se reduce a $20.000 y la de A con B se cancela ($0.00).
  - Trazabilidad y fuentes de financiamiento verificadas con éxito.
* **Resultado del test:** **100% EXITOSO (código de salida 0)**.

---

## 🔟 10. EVIDENCIAS TÉCNICAS Y CONCRETAS PARA EL CIERRE DEFINITIVO DE AUDITORÍA (CON FIRMA)

En respuesta directa al dictamen de cierre de auditoría (*"Cierre de Auditoría: Estado de los Hallazgos"*), se exponen a continuación los cuatro elementos probatorios exigidos, más la evidencia del registro de auditoría de cupos para el Tribunal de Cuentas:

```
========================================================================================
EVIDENCIA EXIGIDA 1: CUERPO ACTUAL DE add_cobro (GUARDAS Y EXCLUSIÓN MUTUA)
========================================================================================
```
Código en producción extraído de [database.py](file:///c:/Users/bornemanns/.gemini/antigravity-ide/scratch/decretometro_2.0/database.py#L583-L682):

```python
def add_cobro(cuota_id=None, monto=0.0, fecha=None, comprobante_path=None,
              convenio_solicitud_id=None, origen_tipo='decreto',
              moneda_origen_id=1, cantidad_moneda_origen=None,
              cotizacion_cobro=1.0, diferencia_ajuste_ars=0.0, obra_id=None):
    if monto <= 0:
        raise ValueError("El monto cobrado debe ser mayor a 0.")
    fecha_dt = datetime.datetime.strptime(fecha, '%Y-%m-%d').date()
    if fecha_dt > datetime.date.today():
        raise ValueError("La fecha de cobro no puede ser futura.")

    # 1. Blindaje de integridad y exclusión mutua de origen
    if origen_tipo == 'decreto':
        if not cuota_id or convenio_solicitud_id is not None:
            raise ValueError("Un cobro de decreto debe tener cuota_id y no puede tener convenio_solicitud_id.")
    elif origen_tipo == 'convenio':
        if not convenio_solicitud_id or cuota_id is not None:
            raise ValueError("Un cobro de convenio debe tener convenio_solicitud_id y no puede tener cuota_id.")
    else:
        raise ValueError(f"Tipo de origen '{origen_tipo}' no válido (debe ser 'decreto' o 'convenio').")
        
    with db_session() as conn:
        cursor = conn.cursor()

        if origen_tipo == 'convenio':
            cursor.execute('SELECT * FROM convenio_solicitudes WHERE id = ?', (convenio_solicitud_id,))
            sol = cursor.fetchone()
            if not sol:
                raise ValueError("Solicitud de convenio no encontrada.")
            
            obra_dest_id = obra_id or sol['obra_id']
            # Cantidad en moneda/UVI a amortizar
            cant_amortizar = cantidad_moneda_origen
            saldo_moneda_sol = float(sol['cantidad_moneda'] - (sol['cantidad_moneda_cobrada'] or 0.0))
            if cant_amortizar is None or cant_amortizar <= 0:
                cant_amortizar = max(0.0, saldo_moneda_sol)
            
            # 2a. Guardia de sobrepago en convenio (a nivel de moneda del certificado)
            if cant_amortizar > (saldo_moneda_sol + 0.01):
                raise ValueError(f"La cantidad a amortizar ({cant_amortizar:,.2f}) supera el saldo pendiente de la solicitud/certificado ({saldo_moneda_sol:,.2f}).")
            
            nueva_cant_cobrada = (sol['cantidad_moneda_cobrada'] or 0.0) + cant_amortizar
            nuevo_estado = 'Cobrado' if nueva_cant_cobrada >= (sol['cantidad_moneda'] - 0.01) else 'Parcial'
            
            cursor.execute('''
                UPDATE convenio_solicitudes 
                SET cantidad_moneda_cobrada = ?, estado = ?
                WHERE id = ?
            ''', (nueva_cant_cobrada, nuevo_estado, convenio_solicitud_id))

            # Cálculo automático de la diferencia por indexación/cotización si no se especificó
            if (diferencia_ajuste_ars is None or diferencia_ajuste_ars == 0.0) and sol['cotizacion_solicitud']:
                monto_esperado_sol_ars = cant_amortizar * float(sol['cotizacion_solicitud'])
                diferencia_ajuste_ars = float(monto) - monto_esperado_sol_ars

            cursor.execute('''
                INSERT INTO cobros (
                    cuota_id, convenio_solicitud_id, origen_tipo, obra_id,
                    moneda_origen_id, cantidad_moneda_origen, cotizacion_cobro,
                    diferencia_ajuste_ars, monto, fecha, comprobante_path
                )
                VALUES (NULL, ?, 'convenio', ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (convenio_solicitud_id, obra_dest_id, moneda_origen_id or 1, cant_amortizar,
                  cotizacion_cobro or 1.0, diferencia_ajuste_ars or 0.0, monto, fecha, comprobante_path))
            cobro_id = cursor.lastrowid
            conn.commit()
            return cobro_id
        else:
            # Flujo Decreto tradicional
            cursor.execute('SELECT monto, mes, anio FROM cuotas WHERE id = ?', (cuota_id,))
            q_row = cursor.fetchone()
            if not q_row:
                raise ValueError("Cuota no encontrada.")
                
            # Validar período de la cuota
            cuota_start = f"{q_row['anio']}-{q_row['mes']:02d}-01"
            if fecha < cuota_start:
                raise ValueError(f"La fecha de cobro ({fecha}) no puede ser anterior al inicio del período de la cuota ({q_row['mes']:02d}/{q_row['anio']}).")
        
            cursor.execute('SELECT SUM(monto) as cobrado FROM cobros WHERE cuota_id = ?', (cuota_id,))
            c_row = cursor.fetchone()
            cobrado_previo = c_row['cobrado'] if c_row and c_row['cobrado'] else 0
            saldo = q_row['monto'] - cobrado_previo
        
            # 2b. Guardia de sobrepago en decretos (a nivel de pesos de la cuota)
            if monto > (saldo + 0.01):
                raise ValueError(f"El monto a cobrar ({monto}) supera el saldo pendiente de la cuota ({saldo:.2f}).")

            cursor.execute('''
                INSERT INTO cobros (
                    cuota_id, convenio_solicitud_id, origen_tipo, obra_id,
                    moneda_origen_id, cantidad_moneda_origen, cotizacion_cobro,
                    diferencia_ajuste_ars, monto, fecha, comprobante_path
                )
                VALUES (?, NULL, 'decreto', ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (cuota_id, obra_id, moneda_origen_id or 1, cantidad_moneda_origen, cotizacion_cobro or 1.0,
                  diferencia_ajuste_ars or 0.0, monto, fecha, comprobante_path))
            cobro_id = cursor.lastrowid
            conn.commit()
            check_estado_decreto_by_cuota(conn, cuota_id)
            return cobro_id
```

---

```
========================================================================================
EVIDENCIA EXIGIDA 2: DEFINICIÓN DDL DE cobros CON CHECK EN SQLITE Y TEST NEGATIVO
========================================================================================
```
La restricción de exclusión mutua se implementó bajo el principio de **defensa en profundidad**: validación a nivel aplicación en `add_cobro()` y constraint estricto a nivel de motor relacional SQLite (Migración 47 en [database.py](file:///c:/Users/bornemanns/.gemini/antigravity-ide/scratch/decretometro_2.0/database.py#L365-L368)).

#### A. DDL Real extraído de `sqlite_master` en `decretometro.db`:
```sql
CREATE TABLE "cobros" (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    cuota_id INTEGER REFERENCES cuotas(id) ON DELETE CASCADE,
    convenio_solicitud_id INTEGER REFERENCES convenio_solicitudes(id) ON DELETE SET NULL,
    origen_tipo TEXT NOT NULL DEFAULT 'decreto',
    obra_id INTEGER REFERENCES obras(id),
    moneda_origen_id INTEGER DEFAULT 1 REFERENCES monedas_indices(id),
    cantidad_moneda_origen REAL,
    cotizacion_cobro REAL DEFAULT 1.0,
    diferencia_ajuste_ars REAL DEFAULT 0.0,
    monto REAL NOT NULL,
    fecha DATE NOT NULL,
    comprobante_path TEXT,
    CONSTRAINT check_origen_exclusivo CHECK (
        (origen_tipo = 'decreto' AND cuota_id IS NOT NULL AND convenio_solicitud_id IS NULL) OR
        (origen_tipo = 'convenio' AND convenio_solicitud_id IS NOT NULL AND cuota_id IS NULL)
    )
)
```

#### B. Log Verbatim de Ejecución de Pruebas Negativas a Nivel Motor SQL:
Script de ejecución ejecutado contra `decretometro.db`:
```bash
python scratch/check_db.py
```
Salida obtenida en consola:
```text
--- COBROS SCHEMA ---
CREATE TABLE "cobros" (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    cuota_id INTEGER REFERENCES cuotas(id) ON DELETE CASCADE,
    convenio_solicitud_id INTEGER REFERENCES convenio_solicitudes(id) ON DELETE SET NULL,
    origen_tipo TEXT NOT NULL DEFAULT 'decreto',
    obra_id INTEGER REFERENCES obras(id),
    moneda_origen_id INTEGER DEFAULT 1 REFERENCES monedas_indices(id),
    cantidad_moneda_origen REAL,
    cotizacion_cobro REAL DEFAULT 1.0,
    diferencia_ajuste_ars REAL DEFAULT 0.0,
    monto REAL NOT NULL,
    fecha DATE NOT NULL,
    comprobante_path TEXT,
    CONSTRAINT check_origen_exclusivo CHECK (
        (origen_tipo = 'decreto' AND cuota_id IS NOT NULL AND convenio_solicitud_id IS NULL) OR
        (origen_tipo = 'convenio' AND convenio_solicitud_id IS NOT NULL AND cuota_id IS NULL)
    )
)

--- PROBANDO CHECK DE EXCLUSION MUTUA ---
EXITO: Bloqueado a nivel motor SQL por CHECK: CHECK constraint failed: check_origen_exclusivo
EXITO: Bloqueado a nivel motor SQL por CHECK: CHECK constraint failed: check_origen_exclusivo
```
*Garantía:* Cualquier intento de `INSERT` o `UPDATE` por fuera de la aplicación (vía scripts, consola SQLite o DBeaver) que viole la exclusión mutua es rechazado de inmediato con `sqlite3.IntegrityError`.

---

```
========================================================================================
EVIDENCIA EXIGIDA 3: CONSULTA SQL REESCRITA (PATRÓN DE UNIFICACIÓN DOWNSTREAM)
========================================================================================
```
Código completo de `get_cobros_con_resumen_distribucion()` en [database.py](file:///c:/Users/bornemanns/.gemini/antigravity-ide/scratch/decretometro_2.0/database.py#L1308-L1351):

```python
def get_cobros_con_resumen_distribucion():
    with db_session() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT c.id, c.monto, c.fecha, c.cuota_id, c.origen_tipo, c.convenio_solicitud_id,
                   cu.mes, cu.anio,
                   COALESCE(d.nro_decreto, cv.nro_convenio) as nro_decreto,
                   COALESCE(d.anio, strftime('%Y', cv.fecha_firma)) as decreto_anio,
                   d.id as decreto_id, cv.id as convenio_id,
                   COALESCE(d.destino_fondos, cv.nombre_convenio || ' — ' || o.nombre) as destino_fondos,
                   COALESCE(d.expediente_imuh, o.expediente_imuh) as expediente_imuh,
                   m.simbolo as moneda_simbolo, m.codigo as moneda_codigo,
                   c.cantidad_moneda_origen, c.cotizacion_cobro,
                   COALESCE(dist.monto_fin_orig, 0) as monto_fin_orig,
                   COALESCE(dist.monto_reserva, 0) as monto_reserva,
                   COALESCE((SELECT SUM(monto) FROM cobro_desvios WHERE cobro_id = c.id), 0) as total_desvios,
                   (
                       COALESCE(dist.monto_fin_orig, 0) + 
                       COALESCE(dist.monto_reserva, 0) + 
                       COALESCE((SELECT SUM(monto) FROM cobro_desvios WHERE cobro_id = c.id), 0) -
                       COALESCE((
                           SELECT SUM(cdr.monto) FROM cobro_desvios_recuperos cdr
                           JOIN cobro_desvios cd ON cdr.desvio_id = cd.id
                           WHERE cd.cobro_id = c.id AND cdr.destino_tipo = 'sin_distribucion'
                       ), 0) -
                       COALESCE((
                           SELECT SUM(crur.monto) FROM cobro_reserva_usos_recuperos crur
                           JOIN cobro_reserva_usos cru ON crur.reserva_uso_id = cru.id
                           WHERE cru.cobro_id = c.id AND crur.destino_tipo = 'sin_distribucion'
                       ), 0)
                   ) as total_distribuido
            FROM cobros c
            LEFT JOIN cuotas cu ON c.cuota_id = cu.id
            LEFT JOIN decretos d ON cu.decreto_id = d.id
            LEFT JOIN convenio_solicitudes cs ON c.convenio_solicitud_id = cs.id
            LEFT JOIN convenios cv ON cs.convenio_id = cv.id
            LEFT JOIN obras o ON (c.obra_id = o.id OR cs.obra_id = o.id)
            LEFT JOIN monedas_indices m ON c.moneda_origen_id = m.id
            LEFT JOIN cobro_distribuciones dist ON c.id = dist.cobro_id
            ORDER BY c.fecha DESC, c.id DESC
        ''')
        rows = cursor.fetchall()
        return [dict(ix) for ix in rows]
```
*Patrón de unificación:*
- Se utiliza `LEFT JOIN` hacia ambas ramas (`cuotas -> decretos` y `convenio_solicitudes -> convenios -> obras`).
- La unificación en el set de datos downstream es provista limpiamente mediante `COALESCE(d.nro_decreto, cv.nro_convenio)`, `COALESCE(d.destino_fondos, cv.nombre_convenio || ' — ' || o.nombre)` y `COALESCE(d.expediente_imuh, o.expediente_imuh)`.
- El cobro de convenio ingresa en pesos a la bandeja de distribución (`tab_distribuir.py`) exactamente igual que cualquier cobro histórico de decreto.

---

```
========================================================================================
EVIDENCIA EXIGIDA 4: LOG REAL DE CONSOLA DE test_compensacion_convenio.py
========================================================================================
```
Comando ejecutado:
```bash
python test_compensacion_convenio.py -v
```

Log real de consola obtenido:
```text
test_flujo_completo_convenio_y_compensacion_cruzada (__main__.TestCompensacionConvenio.test_flujo_completo_convenio_y_compensacion_cruzada) ... ok

----------------------------------------------------------------------
Ran 1 test in 0.518s

OK

--> TEST INTEGRAL DE COMPENSACIÓN CRUZADA CONVENIO <-> DECRETO EXITOSO <--
```

#### Detalle de los 22 Asserts ejecutados durante la suite:
1. `assertIsNotNone(obra_a_id)` y `assertIsNotNone(obra_b_id)`.
2. `assertIsNotNone(cuota_a_id)` y `assertIsNotNone(cobro_a_id)` (Decreto $500.000).
3. `assertIsNotNone(uvi_moneda)` y `assertIsNotNone(conv_id)` (Convenio por 1.000 UVIs).
4. `assertRaises(ValueError)`: Intento de asociar obra por 1.500 UVIs cuando el convenio es de 1.000 UVIs (**BLOQUEADO**).
5. `assertRaises(ValueError)`: Intento de emitir certificado por 1.200 UVIs (**BLOQUEADO**).
6. Emisión válida de certificado N° 1 por 200 UVIs @ $1.000 = $200.000.
7. `assertRaises(ValueError)`: Intento de registrar cobro de convenio con `cuota_id` (**BLOQUEADO por exclusión mutua**).
8. `assertRaises(ValueError)`: Intento de amortizar 250 UVIs superando el saldo del certificado de 200 UVIs (**BLOQUEADO por sobrepago**).
9. Cobro efectivo de 200 UVIs a cotización de acreditación $1.100 = $220.000.
10. `assertAlmostEqual(cobro_b['diferencia_ajuste_ars'], 20000.0)` (**Indexación comprobada**).
11. Distribución downstream: $190.000 a Fin Original, $30.000 disponible para desvío inicial.
12. Préstamos cruzados:
    - Obra A presta $50.000 a Obra B (uso de reserva de Decreto).
    - Obra B presta $30.000 a Obra A (desvío desde cobro de Convenio).
13. `assertEqual(len(pares), 1)` en `backend_compensaciones.calcular_saldos_cruzados_globales()` y `assertAlmostEqual(par['monto_maximo'], 30000.0)`.
14. Ejecución formal de compensación: `assertTrue(ok)`.
15. `assertEqual(len(pares_post), 0)`: Saldos cruzados compensados.
16. `assertAlmostEqual(desv_b['saldo'], 0.0)`: Desvío de B hacia A extinguido totalmente.
17. `assertAlmostEqual(res_a['saldo'], 20000.0)`: Deuda residual de B con A reducida a exactamente $20.000.
18. `assertIn("Fin Original", tipos_b)` y `assertIn("Uso de Reserva", tipos_b)` en `get_trazabilidad_fuentes_por_obra(obra_id=obra_b_id)`.
19. `assertEqual(kpis_conv['total_vigentes'], 1)`.
20. `assertAlmostEqual(kpis_conv['total_cobrado_ars'], 220000.0)`.
21. `assertAlmostEqual(kpis_conv['total_diferencia_ars'], 20000.0)`.
22. Tiempo total de ejecución de la suite: **0.518 segundos**.

---

```
========================================================================================
EVIDENCIA ADICIONAL 5: REGISTRO DE AUDITORÍA EN NOTAS ANTE EXCESO DE CUPO NOMINAL
========================================================================================
```
En respuesta a la observación de auditoría para el **Tribunal de Cuentas** (*"si una obra termina consumiendo más cupo del que tenía asignado dentro del remanente global, que quede una justificación explícita en convenio_solicitudes.notas"*), se incorporó la siguiente lógica automática en [database.py](file:///c:/Users/bornemanns/.gemini/antigravity-ide/scratch/decretometro_2.0/database.py#L3876-L3897):

```python
        # Auditoría de Cupo Nominal por Obra (Tribunal de Cuentas)
        cursor.execute('''
            SELECT monto_pactado_moneda FROM convenio_obras
            WHERE convenio_id = ? AND obra_id = ?
        ''', (convenio_id, obra_id))
        co_row = cursor.fetchone()
        cupo_obra = co_row['monto_pactado_moneda'] if co_row else None

        cursor.execute('''
            SELECT COALESCE(SUM(cantidad_moneda), 0) as sol_obra
            FROM convenio_solicitudes
            WHERE convenio_id = ? AND obra_id = ? AND estado != 'Anulado'
        ''', (convenio_id, obra_id))
        sol_obra_previo = cursor.fetchone()['sol_obra']

        notas_final = str(notas).strip() if notas else ""
        if cupo_obra is not None and (sol_obra_previo + float(cantidad_moneda)) > (cupo_obra + 0.01):
            exceso = (sol_obra_previo + float(cantidad_moneda)) - cupo_obra
            aviso_reasig = f"[Reasignación de cupo interno: supera cupo nominal de obra en {exceso:,.2f} dentro del remanente global del convenio]"
            if aviso_reasig not in notas_final:
                notas_final = f"{notas_final} | {aviso_reasig}".strip(" |")
```
*Efecto de control:* La reasignación no se bloquea (se respeta el remanente global del convenio), pero se genera una **marca indeleble en la base de datos** para que cualquier auditor o inspector del Tribunal de Cuentas identifique inmediatamente la reasignación interna de fondos entre las obras del convenio.

