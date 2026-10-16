# Auditoría integral: Decretómetro 2.0

**Destinatario:** Martín Rodríguez
**Fecha del informe:** 16/10/2026
**Base auditada:** `decretometro.db`, `schema_version` 48, 29 tablas, 38 archivos fuente

**Alcance y límites.** Revisé el esquema completo, `database.py` (rutas críticas), `backend_compensaciones.py`, `utils.py` (archivos y backup), `pages/11_Sistema.py` y varios tests. No leí línea por línea las páginas de Streamlit, `utils_reports.py` ni `pdf_generator.py`, y no ejecuté nada: todo surge de lectura de código. Las líneas son aproximadas (±5) respecto de cada archivo.

---

## Sección 1: Resumen ejecutivo y diagnóstico general

| Dimensión | Puntaje | Comentario breve |
|---|---|---|
| Arquitectura | **4/10** | Monolito de ~4.900 líneas, reglas de negocio repetidas, pero con un patrón de sesión razonable |
| Concurrencia y seguridad | **5/10** | Buen SQL parametrizado y `foreign_keys=ON`; transacciones frágiles |
| Precisión contable | **4/10** | Dinero en `REAL`, cotización UVI sin tabla propia, sin bitácora |

### Lo que está bien

- `PRAGMA foreign_keys = ON` se activa en cada conexión (`get_connection`).
- El SQL de usuario va parametrizado. Los 8 f-strings en SQL interpolan solo la constante `TOLERANCE`. No encontré inyección SQL.
- La subida de comprobantes valida extensión, tamaño y sanea el nombre.
- Los backups usan `sqlite3.backup()`, que es la forma correcta.
- Hay guardas de negocio útiles: tope del desvío contra el cobro, tope del recupero contra el desvío, y un CHECK de origen exclusivo en `cobros`.

### Lo más grave

1. El sistema promete trazabilidad "inalterable", pero hoy se puede borrar casi todo sin dejar rastro. No existe bitácora de cambios.
2. Si una obra está en UVI y falta la cotización, el sistema asume cotización 1,0 sin avisar. Eso anota pesos como si fueran UVIs.
3. La función de "restaurar backup" no restaura lo que dice y puede fallar a mitad de camino.
4. Las reglas de topes viven solo en Python, en lecturas y escrituras separadas. Cualquier camino que se las saltee (la compensación lo hace) deja saldos incoherentes.

### Respuestas directas a los 6 focos

- **Sobre-desvío:** en uso normal de un solo usuario no se puede desviar más de lo disponible, porque la guarda existe. Con dos sesiones simultáneas sí podría (H-05).
- **Compensación sobre un desvío ya recuperado:** el camino manual valida el tope. El camino de compensación automática inserta directo, sin esa validación (H-06).
- **Deudas circulares:** solo se detectan cruces de a pares (A↔B). Un ciclo A→B→C→A no se detecta.
- **UVI en feriados y fines de semana:** no hay tabla de cotizaciones diarias. La cotización se tipea en cada operación, así que no hay regla de "cotización faltante".
- **Inyección SQL:** riesgo bajo.
- **Tests:** varios son scripts con `print` que no fallan nunca (H-10).

---

## Sección 2: Matriz de hallazgos y vulnerabilidades

| ID | Severidad | Título |
|---|---|---|
| H-01 | 🔴 Crítica | Sin bitácora de auditoría y con borrados físicos |
| H-02 | 🔴 Crítica | Cotización UVI/USD que cae silenciosamente a 1,0 |
| H-03 | 🔴 Crítica | La restauración de backup no restaura lo que promete y puede abortar |
| H-04 | 🟠 Alta | Operaciones compuestas que no son atómicas |
| H-05 | 🟠 Alta | Lectura-y-escritura sin bloqueo (condición de carrera) |
| H-06 | 🟠 Alta | La compensación automática puede dejar asientos descuadrados |
| H-07 | 🟠 Alta | Las reglas de integridad viven solo en Python |
| H-08 | 🟠 Alta | Dinero en `REAL` con tolerancia de 1 centavo |
| H-09 | 🟠 Alta | El destino del desvío se reemplaza silenciosamente |
| H-10 | 🟠 Alta | Tests que no verifican nada |
| H-11 | 🟡 Media | Monolito `database.py` y lógica duplicada |
| H-12 | 🟡 Media | Destinos como texto libre |
| H-13 a H-15 | 🟢 Baja | Comprobantes, autenticación, limpieza |

---

### 🔴 Severidad Crítica (P0)

#### [H-01] Sin bitácora de auditoría y con borrados físicos

- **Severidad:** Crítica
- **Categoría:** Lógica Financiera y UVIs / Arquitectura
- **Ubicación:** `database.py`: `delete_fin_original_uso`, `delete_desvio_recupero`, `delete_cobro`, `delete_decreto` (~L536); `backend_compensaciones.deshacer_compensacion`. Esquema: 29 tablas, ninguna de auditoría.
- **Impacto contable / financiero:** si alguien borra un pago a Fin Original o un recupero, el saldo cambia y no queda constancia de quién, cuándo ni qué se borró. Ante el Tribunal de Cuentas no podés demostrar que el historial no fue alterado. Además `delete_decreto` borra del disco los PDF del decreto y los comprobantes bancarios. Esa evidencia no se recupera.
- **Diagnóstico técnico:** `DELETE` directo sobre tablas de movimientos, más `ON DELETE CASCADE` en cadena (desvío → recuperos). `os.remove` se ejecuta dentro de la transacción, antes de saber si el `DELETE` va a prosperar.
- **Código problemático actual:**

```python
def delete_desvio_recupero(recupero_id):
    with db_session() as conn:
        conn.cursor().execute('DELETE FROM cobro_desvios_recuperos WHERE id = ?', (recupero_id,))
        conn.commit()
```

- **Solución propuesta:** (1) tabla de auditoría alimentada por triggers, para que aplique a cualquier camino de código; (2) pasar de borrar a **anular** (con motivo) en las tablas de movimientos; (3) no borrar archivos nunca, y guardar su hash.

```sql
CREATE TABLE IF NOT EXISTS audit_log (
  id INTEGER PRIMARY KEY, ts TEXT DEFAULT (datetime('now','localtime')),
  tabla TEXT NOT NULL, operacion TEXT NOT NULL, fila_id INTEGER, datos_previos TEXT);

CREATE TRIGGER trg_aud_del_fin_original BEFORE DELETE ON cobro_fin_original_usos
BEGIN
  INSERT INTO audit_log(tabla, operacion, fila_id, datos_previos)
  VALUES ('cobro_fin_original_usos','DELETE',OLD.id,
          json_object('cobro_id',OLD.cobro_id,'monto',OLD.monto,'fecha',OLD.fecha,'nro_op',OLD.nro_op));
END;
-- Repetir (DELETE y UPDATE) para: cobros, cobro_desvios, cobro_desvios_recuperos,
-- cobro_reserva_usos, cobro_reserva_usos_recuperos, cobro_distribuciones.
```

Sumá a la app el usuario de Windows (`getpass.getuser()`) en una columna `usuario`, y en `delete_decreto` quitá los `os.remove`.

---

#### [H-02] Cotización UVI/USD que cae silenciosamente a 1,0

- **Severidad:** Crítica
- **Categoría:** Lógica Financiera y UVIs
- **Ubicación:** `database.py`: `add_fin_original_uso` (~L2316), `add_cobro` (~L637). Esquema: no existe tabla de cotizaciones.
- **Impacto contable / financiero:** si pagás una obra en UVI y no hay cotización válida, el sistema usa 1,0 y calcula `cantidad_moneda_amortizada = monto / 1`. Un pago de $10.000.000 queda anotado como 10.000.000 UVIs amortizadas, en lugar de unas pocas miles. Es un error de varios órdenes de magnitud, sin ningún aviso. El saldo del contrato en UVIs queda mal para siempre.
- **Diagnóstico técnico:** la "cotización válida" se decide con `> 1.0` y, si ninguna cumple, `else: cotiz = 1.0`. Las cotizaciones son campos sueltos tipeados por operación, sin fuente ni fecha verificable.
- **Código problemático actual:**

```python
elif cotiz_sol and float(cotiz_sol) > 1.0:
    cotiz = float(cotiz_sol)
else:
    cotiz = 1.0          # <- silencioso
if cant_mon is None:
    cant_mon = round(monto / cotiz, 6) if cotiz > 0 else 0.0
```

- **Solución propuesta:** tabla de cotizaciones diarias y una función única que falle ruidosamente.

```sql
CREATE TABLE cotizaciones (
  moneda_id INTEGER NOT NULL REFERENCES monedas_indices(id),
  fecha DATE NOT NULL, valor REAL NOT NULL CHECK(valor > 0),
  fuente TEXT, PRIMARY KEY (moneda_id, fecha));
```

```python
def get_cotizacion(conn, moneda_id, fecha):
    r = conn.execute("""SELECT valor FROM cotizaciones
                        WHERE moneda_id=? AND fecha<=? ORDER BY fecha DESC LIMIT 1""",
                     (moneda_id, fecha)).fetchone()
    if not r:
        raise ValueError(f"Falta cotización para moneda {moneda_id} al {fecha}. Cargala antes de operar.")
    return r['valor']
```

Reemplazá el `else: cotiz = 1.0` por `cotiz = get_cotizacion(conn, o_moneda_id, fecha)`. La regla "última cotización anterior o igual a la fecha" cubre feriados y fines de semana. Tenés que confirmar con el texto de cada convenio si aplica la fecha de cobro, de pago o de certificación. Eso es decisión contable, no técnica.

---

#### [H-03] La restauración de backup no restaura lo que promete y puede abortar

- **Severidad:** Crítica
- **Categoría:** Arquitectura / Lógica Financiera
- **Ubicación:** `utils.py: restore_backup`; `pages/11_Sistema.py`.
- **Impacto contable / financiero:** si se pierde la base, el backup es tu única red de seguridad. Esta función copia columnas parciales y deja afuera tablas enteras: `obras`, `convenios`, `convenio_solicitudes`, `convenio_obras`, `op_bejerman`, `pagos_fondos_propios`, `monedas_indices`, proveedores y gastos. De las tablas que sí copia, pierde datos: `cobros` sin `obra_id`, cotización ni origen de convenio; `cobro_desvios` sin `obra_id` ni gasto; `fin_original_usos` sin cotización ni amortización.
- **Diagnóstico técnico:** un cobro de convenio tiene `cuota_id` NULL. Al restaurarlo con el origen por defecto `'decreto'`, el CHECK `check_origen_exclusivo` falla y la restauración entera hace rollback. Además usa `INSERT OR IGNORE` con IDs, que no corrige filas modificadas. No valida que el `.db` subido sea del Decretómetro ni de la misma versión de esquema. Usa un nombre fijo `temp_restore.db` que queda huérfano ante un error.
- **Código problemático actual:**

```python
cursor.execute('''
    INSERT OR IGNORE INTO main.cobros (id, cuota_id, monto, fecha, comprobante_path)
    SELECT id, cuota_id, monto, fecha, comprobante_path FROM backup_db.cobros
''')
```

- **Solución propuesta:** restaurar el archivo completo, con verificación y copia previa del estado actual.

```python
def restore_backup(current_db_path, backup_db_path):
    chk = sqlite3.connect(backup_db_path)
    try:
        if chk.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise ValueError("El backup está dañado.")
        v = chk.execute("SELECT version FROM schema_version WHERE id=1").fetchone()
        if not v:
            raise ValueError("No es una base del Decretómetro.")
    finally:
        chk.close()
    create_backup(current_db_path, "backups")          # red de seguridad
    src, dst = sqlite3.connect(backup_db_path), sqlite3.connect(current_db_path)
    try:
        src.backup(dst)
    finally:
        src.close(); dst.close()
```

Agregá además backup automático diario y antes de cada migración. Hoy el backup es solo manual, por botón.

---

### 🟠 Severidad Alta (P1)

#### [H-04] Operaciones compuestas que no son atómicas

- **Severidad:** Alta
- **Categoría:** Concurrencia y Transacciones
- **Ubicación:** `add_desvio` (~L1498) y `add_fin_original_uso` (~L2316): el movimiento se commitea y luego `register_or_update_op` abre **otra** sesión. `add_cobro` (rama convenio): `commit()` y recién después `check_estado_convenio_by_solicitud`. `delete_cobro`: `commit()` y luego `check_estado_decreto_by_cuota`.
- **Impacto contable / financiero:** si falla el segundo paso, queda un desvío o un pago registrado sin su OP en `op_bejerman`. Para el contralor, ese pago existe pero no se puede vincular a una orden de pago. Un cobro de convenio puede quedar con el estado de la solicitud desactualizado.
- **Diagnóstico técnico:** commits intermedios dentro de `db_session()` más sesiones anidadas. `db_session` ya hace commit al salir, así que cada `conn.commit()` interno es redundante y rompe la atomicidad.
- **Código problemático actual:**

```python
        new_id = cursor.lastrowid
        conn.commit()

    if nro_op:
        ...
        register_or_update_op(nro_op, obra_id=obra_id, gasto_id=g_id)   # otra sesión
```

- **Solución propuesta:** una sola sesión por operación. Pasá `conn` a las funciones auxiliares y quitá los commits internos.

```python
def register_or_update_op(nro_op, obra_id=None, gasto_id=None, conn=None):
    if conn is None:
        with db_session() as c:
            return register_or_update_op(nro_op, obra_id, gasto_id, conn=c)
    # ...mismo cuerpo, usando conn...

# dentro de add_desvio, antes de salir del with:
if nro_op:
    register_or_update_op(nro_op, obra_id=obra_id, gasto_id=g_id, conn=conn)
```

---

#### [H-05] Lectura-y-escritura sin bloqueo (condición de carrera)

- **Severidad:** Alta
- **Categoría:** Concurrencia y Transacciones
- **Ubicación:** `get_connection` / `db_session` (~L25-45); `upsert_distribucion`, `add_desvio`, `add_fin_original_uso`, `add_desvio_recupero`.
- **Impacto contable / financiero:** dos pestañas o dos usuarios que desvían contra el mismo cobro a la vez pueden pasar ambos la validación y sumar más que el cobro. Pasa raramente, pero cuando pasa nadie lo advierte.
- **Diagnóstico técnico:** `sqlite3` de Python abre transacciones *diferidas* (deferred): el `SELECT SUM(...)` de validación no toma bloqueo de escritura. No hay `BEGIN IMMEDIATE`, ni WAL, y el timeout es 10 s.
- **Código problemático actual:**

```python
def get_connection():
    conn = sqlite3.connect(DB_PATH, timeout=10.0)
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.row_factory = sqlite3.Row
    return conn
```

- **Solución propuesta:**

```python
def get_connection():
    conn = sqlite3.connect(DB_PATH, timeout=30.0, isolation_level=None)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA busy_timeout = 30000")
    conn.row_factory = sqlite3.Row
    return conn

@contextmanager
def db_session():
    conn = get_connection()
    try:
        conn.execute("BEGIN IMMEDIATE")
        yield conn
        conn.execute("COMMIT")
    except Exception:
        if conn.in_transaction:
            conn.execute("ROLLBACK")
        raise
    finally:
        conn.close()
```

Esto **depende de H-04**: hay que sacar todos los `conn.commit()` internos antes, porque cerrarían la transacción explícita. El migrador de `init_db` necesita su propia conexión sin `BEGIN`, porque `PRAGMA foreign_keys` no tiene efecto dentro de una transacción.

---

#### [H-06] La compensación automática puede dejar asientos descuadrados

- **Severidad:** Alta
- **Categoría:** Lógica Financiera y UVIs
- **Ubicación:** `backend_compensaciones.py: ejecutar_compensacion`.
- **Impacto contable / financiero:** una compensación cruzada debería saldar el mismo monto en ambos sentidos. El código no verifica que ambos lados sumen lo mismo ni que sumen `monto_compensar`. Además inserta recuperos sin pasar por las validaciones de `add_desvio_recupero` (tope contra el saldo y OP o nota), y con la fecha del desvío más reciente en lugar de la de hoy. Si un lado tiene menos deuda que el monto pedido, el otro se compensa de más.
- **Diagnóstico técnico:** `procesar_fifo` corta cuando se acaban los desvíos de cada lado, por separado. Los saldos se leen vía `utils_reports` (otras conexiones) y luego se escribe en otra sesión, sin revalidar. Las filas con `id_original == 0` se saltean sin avisar. Las obras se identifican por regex `8\d{6}` o por los primeros 15 caracteres del nombre.
- **Código problemático actual:**

```python
ins_1_to_2 = procesar_fifo(desvios_1_to_2, monto_compensar, str_ops_2_to_1)
ins_2_to_1 = procesar_fifo(desvios_2_to_1, monto_compensar, str_ops_1_to_2)
with db.db_session() as conn:
    for ins in ins_1_to_2 + ins_2_to_1:
        if ins['id_original'] == 0:
            continue
        ...INSERT INTO cobro_desvios_recuperos ...
```

- **Solución propuesta:**

```python
tot1 = round(sum(i['monto'] for i in ins_1_to_2), 2)
tot2 = round(sum(i['monto'] for i in ins_2_to_1), 2)
if tot1 != tot2 or abs(tot1 - round(float(monto_compensar), 2)) > 0.005:
    return False, f"Compensación asimétrica ({tot1:,.2f} vs {tot2:,.2f}); se cancela."
# y dentro de la transacción, antes de cada INSERT, revalidar el tope (ver H-07)
```

---

#### [H-07] Las reglas de integridad viven solo en Python

- **Severidad:** Alta
- **Categoría:** Lógica Financiera y UVIs / Arquitectura
- **Ubicación:** esquema (`cobro_desvios`, `*_recuperos`, `cobro_distribuciones`, `cobro_fin_original_usos`).
- **Impacto contable / financiero:** nada impide, a nivel base de datos, un monto negativo, un recupero mayor que el desvío o un destino mal tipeado. Cualquier camino que no pase por la función "correcta" (la compensación, una restauración, un script de mantenimiento) rompe las cuentas.
- **Diagnóstico técnico:** no hay CHECK de monto positivo ni de dominio de `destino_tipo`, ni triggers de tope. SQLite no permite agregar CHECK con `ALTER`, pero sí triggers.
- **Código problemático actual:**

```sql
CREATE TABLE cobro_desvios_recuperos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    desvio_id INTEGER NOT NULL,
    monto REAL NOT NULL,           -- sin CHECK(monto > 0), sin tope
    ...
```

- **Solución propuesta** (ejemplo para desvíos; replicar en `cobro_reserva_usos_recuperos`):

```sql
CREATE TRIGGER trg_recupero_tope BEFORE INSERT ON cobro_desvios_recuperos
BEGIN
  SELECT RAISE(ABORT,'Monto de recupero inválido') WHERE NEW.monto <= 0;
  SELECT RAISE(ABORT,'Recupero supera el saldo del desvío')
  WHERE (SELECT COALESCE(SUM(monto),0) FROM cobro_desvios_recuperos WHERE desvio_id = NEW.desvio_id)
        + NEW.monto > (SELECT monto FROM cobro_desvios WHERE id = NEW.desvio_id) + 0.005;
END;
```

---

#### [H-08] Dinero en `REAL` con tolerancia de 1 centavo

- **Severidad:** Alta
- **Categoría:** Lógica Financiera y UVIs
- **Ubicación:** todo el esquema (`monto REAL`) y `TOLERANCE = 0.01` (`database.py` L12).
- **Impacto contable / financiero:** los números de coma flotante no representan exactamente los centavos. Con sumas repetidas aparecen diferencias de fracciones de centavo, y la tolerancia las tapa en vez de eliminarlas. En un balance de rendición, un saldo "0,00" que en realidad es 0,0000001 genera estados incorrectos y filas fantasma.
- **Diagnóstico técnico:** IEEE 754 doble, comparaciones con tolerancia en vez de aritmética exacta.
- **Código problemático actual:**

```python
TOLERANCE = 0.01
...
if (ya_pagado + monto) > (fin_orig_presupuesto + TOLERANCE):
    raise ValueError(...)
```

- **Solución propuesta (migración gradual):** agregar columnas `monto_cent INTEGER` (pesos × 100), rellenarlas con `CAST(ROUND(monto*100) AS INTEGER)` y comparar contra los datos actuales antes de cambiar las consultas. Una vez migrado, `TOLERANCE` pasa a 0. Las cantidades de UVI pueden quedar en `REAL` con redondeo explícito a 6 decimales al escribir. Mientras tanto, redondeá con `round(x, 2)` en cada escritura.

---

#### [H-09] El destino del desvío se reemplaza silenciosamente

- **Severidad:** Alta
- **Categoría:** Lógica Financiera y UVIs
- **Ubicación:** `add_desvio` (~L1498).
- **Impacto contable / financiero:** si cargás un desvío a una obra financiada por varios decretos, el sistema ignora el decreto que elegiste y pone el primero vigente. La deuda queda imputada a un decreto que quizá no corresponde, y el reporte "quién le debe a quién" por decreto sale mal.
- **Diagnóstico técnico:** el parámetro `decreto_destino_id` se sobrescribe con `decretos_vigentes[0]['id']`.
- **Código problemático actual:**

```python
if decretos_vigentes:
    decreto_destino_id = decretos_vigentes[0]['id']
elif decretos_asoc:
    decreto_destino_id = decretos_asoc[0]['id']
```

- **Solución propuesta:**

```python
if obra_id:
    vigentes = [d for d in get_decretos_by_obra(obra_id) if d['estado'] != 'Anulado']
    if decreto_destino_id is None:
        if len(vigentes) == 1:
            decreto_destino_id = vigentes[0]['id']
        elif len(vigentes) > 1:
            raise ValueError("La obra tiene varios decretos vigentes: indicá a cuál se imputa el desvío.")
```

---

#### [H-10] Tests que no verifican nada

- **Severidad:** Alta
- **Categoría:** Testing
- **Ubicación:** `tests/test_recupero_reserva.py`, `tests/test_backend.py`, y la mecánica general de `conftest.py`.
- **Impacto contable / financiero:** el test de recuperos de reserva imprime "Esperado: 2" y "Esperado: 120000", pero no tiene `assert`. Si el cálculo se rompe, el test sigue "pasando". En `test_backend.py` el `except Exception: pass` también oculta fallas. Además `conftest.py` copia la base **real** para cada test, así que los resultados dependen de tus datos de hoy.
- **Diagnóstico técnico:** scripts con `print`, sin asserts; ausencia de pruebas de rollback, concurrencia y saldos límite.
- **Código problemático actual:**

```python
print(f"\n6. Préstamos activos después (Esperado: 1 - Poli debe desaparecer): {len(activos_despues)}")
```

- **Solución propuesta:**

```python
def test_recupero_cancela_deuda(base_vacia):
    ...
    assert len(db.get_reserva_usos_prestamos_activos()) == 2
    assert db.get_deuda_desvios_by_decreto(dec_dest_id) == pytest.approx(120000.0)

def test_desvio_hace_rollback_si_falla_op(monkeypatch, base_vacia):
    monkeypatch.setattr(db, "register_or_update_op", lambda *a, **k: (_ for _ in ()).throw(RuntimeError()))
    with pytest.raises(RuntimeError):
        db.add_desvio(cobro_id, "X", 1000, "prueba de rollback", "2026-05-16", nro_op="123")
    assert db.get_historial_desvios() == []     # nada quedó a medias
```

Armá una base **vacía** con el esquema, en vez de copiar la real, y agregá un test con dos threads desviando sobre el mismo cobro.

---

### 🟡 Severidad Media (P2)

#### [H-11] Monolito `database.py` y lógica duplicada

- **Severidad:** Media
- **Categoría:** Arquitectura
- **Ubicación:** `database.py` completo (169 funciones, 48 migraciones inline).
- **Impacto contable / financiero:** cada cambio toca un archivo gigante, y el cálculo de "saldo libre de un cobro" está repetido en `upsert_distribucion`, `add_desvio`, `add_reserva_uso` y otras. Si corregís una y olvidás otra, los reportes dejan de coincidir entre sí.
- **Diagnóstico técnico:** persistencia, reglas de negocio y consultas de reporte mezcladas; migraciones con `if version == 44/47/48` dentro del loop y `except OperationalError` que ignora cualquier error que contenga "already exists".
- **Código problemático actual:**

```python
except sqlite3.OperationalError as e:
    err_msg = str(e).lower()
    if "duplicate column name" in err_msg or "already exists" in err_msg:
        pass
    else:
        raise e
```

- **Solución propuesta:** ver Fase 3. Para las migraciones, además de separarlas, cerrar cada una con `PRAGMA foreign_key_check` y no tragar errores genéricos.

---

#### [H-12] Destinos como texto libre

- **Severidad:** Media
- **Categoría:** Lógica Financiera y UVIs
- **Ubicación:** `cobro_desvios.destino`, `cobro_reserva_usos.destino_detalle`, `get_obras_propias_nombres`.
- **Impacto contable / financiero:** "Refacción Polideportivo" y "Refaccion polideportivo" son dos deudas distintas para el sistema. Los saldos de fondos propios y la compensación pueden fragmentarse.
- **Diagnóstico técnico:** el destino de fondos propios se agrupa con `SELECT DISTINCT destino ...` sobre texto.
- **Código problemático actual:**

```python
cursor.execute('SELECT DISTINCT destino FROM cobro_desvios WHERE decreto_destino_id IS NULL AND destino IS NOT NULL ...')
```

- **Solución propuesta:** exigir `obra_id` siempre. Dejar el texto libre solo para registros históricos (`legacy`), sin permitir nuevos.

---

### 🟢 Severidad Baja (P3)

- **[H-13] Comprobantes con ruta relativa.** `save_uploaded_file(dest_folder="uploads")` guarda rutas relativas al directorio desde el cual se lanza Streamlit. Si lo arrancás desde otra carpeta, los comprobantes "desaparecen". Guardá la ruta relativa a una raíz fija y un hash SHA-256 en la base. También validá el contenido real (firma del archivo), no solo la extensión.
- **[H-14] Sin autenticación visible.** En lo que leí no hay login. La página Sistema permite descargar y restaurar la base completa. Si el servidor se expone en red, cualquiera con la URL accede. Lanzalo con `--server.address 127.0.0.1` o agregá un acceso con contraseña.
- **[H-15] Limpieza.** `except:` pelado en `sort_key`; `print` en lugar de `logging` en `delete_file`; f-strings con `TOLERANCE` en SQL (inofensivos, pero conviene parametrizar); `cobro_fin_original_usos` con las columnas duplicadas `notes` y `notas`.

---

## Sección 3: Hoja de ruta priorizada

### Fase 1: Quick wins inmediatos (1 a 3 días)

1. Backup automático diario y antes de cada migración. Probar una restauración real una vez.
2. H-04: quitar commits internos y sesiones anidadas (empezar por `add_desvio`, `add_fin_original_uso`, `add_cobro`, `delete_cobro`).
3. H-02: convertir el `else: cotiz = 1.0` en un error explícito. Es un parche de 5 líneas que evita el daño más grave.
4. H-01 parcial: triggers de auditoría sobre los `DELETE` y sacar los `os.remove` de `delete_decreto`.
5. H-14: lanzar Streamlit solo en localhost.
6. H-10 parcial: convertir los `print("Esperado")` en `assert`.

### Fase 2: Blindaje financiero y de datos (1 a 2 semanas)

1. H-05: activar WAL y `BEGIN IMMEDIATE` (después de la Fase 1.2).
2. H-02 completo: tabla `cotizaciones`, función `get_cotizacion` y carga de la serie UVI/USD histórica. Decidir con cada convenio la fecha aplicable.
3. H-07: triggers de tope y de monto positivo en todas las tablas de movimientos.
4. H-06 y H-09: validación simétrica de compensaciones y respeto del decreto elegido.
5. H-03: reemplazar `restore_backup` por la restauración completa con verificación.
6. Conciliación previa a H-08: calcular `monto_cent` en paralelo y comparar contra los totales actuales de cada cobro, antes de migrar consultas.

### Fase 3: Refactorización arquitectónica estructural (mediano plazo)

1. **Antes de tocar nada:** fijar el comportamiento actual con tests de "foto". Generar reportes con una base de prueba y guardar los resultados como referencia.
2. Crear el paquete `decretometro/db/` con: `connection.py` (sesión), `migrations/` (un archivo por versión y un runner con `foreign_key_check`), `repositories/` (cobros, desvíos, reservas, convenios, obras, aportes) y `services/` (reglas de negocio como saldo libre, compensación y cotización).
3. Dejar `database.py` como fachada que re-exporta las funciones: `from decretometro.db.repositories.cobros import *`. Así las páginas de Streamlit no cambian.
4. Mover en este orden, corriendo la suite completa después de cada paso: conexión → migraciones → lecturas (`get_*`) → escrituras por entidad (cobros, luego desvíos, luego reservas) → compensaciones.
5. Recién con todo movido, migrar a montos enteros (H-08) y eliminar la duplicación del cálculo de saldo libre.
