import os
import sqlite3
import pytest
import conftest  # noqa: F401
import database as db
import utils

def test_get_ultima_cotizacion_y_precarga():
    # Obtener una moneda distinta a ARS o crear una temporal si no existe
    monedas = db.get_monedas_indices()
    uvis = [m for m in monedas if m['codigo'] == 'UVI']
    if not uvis:
        uvis_id = db.add_moneda_indice('UVI', 'Unidad de Vivienda', 'UVI', tipo='Índice', decimales=2)
    else:
        uvis_id = uvis[0]['id']

    # Crear una obra en UVIs
    obra_id = db.add_obra(
        nombre="Obra Cotizacion Test Ultima",
        expediente_imuh="8009988-I-2026",
        moneda_id=uvis_id,
        monto_contrato_moneda=5000.0,
        cotizacion_base_contrato=1000.0,
        fecha_contrato="2026-01-01"
    )

    # Registrar un pago con una fecha futura deliberada para comprobar que retorna la más reciente
    db.add_pago_fondos_propios(
        obra_id=obra_id,
        monto=150000.0,
        fecha="2099-12-31",
        nro_op="OP-COTIZ-TEST-MAX",
        observaciones="Pago fecha mas reciente para prueba",
        cotizacion_pago=9999.50
    )

    # Debe retornar la cotización de la fecha más reciente (2099-12-31 -> 9999.50)
    ult_cotiz = db.get_ultima_cotizacion(uvis_id)
    assert ult_cotiz == 9999.50

def test_cotiz_none_raises_value_error_en_pago():
    monedas = db.get_monedas_indices()
    uvis = [m for m in monedas if m['codigo'] == 'UVI']
    uvis_id = uvis[0]['id'] if uvis else db.add_moneda_indice('UVI', 'Unidad de Vivienda', 'UVI', tipo='Índice', decimales=2)

    # Crear obra bimonetaria con expediente válido normalizado
    obra_id = db.add_obra(
        nombre="Obra Test UVIs Fallback",
        expediente_imuh="8009999-I-2026",
        moneda_id=uvis_id,
        monto_contrato_moneda=1000.0,
        cotizacion_base_contrato=1000.0,
        fecha_contrato="2026-01-01"
    )

    # Intentar registrar pago con fondos propios sin cotización debe lanzar ValueError explícito
    with pytest.raises(ValueError, match="cotización"):
        db.add_pago_fondos_propios(
            obra_id=obra_id,
            monto=50000.0,
            fecha="2026-03-20",
            nro_op="OP-TEST-FALLBACK",
            observaciones="Pago prueba sin cotiz",
            cotizacion_pago=None
        )

def test_backup_restore_binario():
    os.makedirs(conftest.TMP_DIR, exist_ok=True)
    temp_target = os.path.join(conftest.TMP_DIR, "test_target_restore.db")
    corrupt_file = os.path.join(conftest.TMP_DIR, "corrupt.db")

    for p in [temp_target, corrupt_file]:
        if os.path.exists(p):
            try:
                os.remove(p)
            except Exception:
                pass
    
    # 1. Crear un backup real a partir de la base de prueba actual
    backup_file = utils.create_backup(db.DB_PATH, backup_dir=conftest.TMP_DIR)
    assert os.path.exists(backup_file)

    # 2. Inicializar base destino vacía
    conn_t = sqlite3.connect(temp_target)
    conn_t.execute("CREATE TABLE dummy (id INTEGER PRIMARY KEY);")
    conn_t.commit()
    conn_t.close()

    # 3. Restaurar backup sobre temp_target
    utils.restore_backup(current_db_path=temp_target, backup_db_path=backup_file)

    # 4. Verificar integridad y tablas en la base restaurada
    conn_v = sqlite3.connect(temp_target)
    cursor = conn_v.cursor()
    cursor.execute("PRAGMA integrity_check;")
    check = cursor.fetchone()[0]
    assert check.lower() == "ok"

    cursor.execute("SELECT version FROM schema_version WHERE id=1;")
    ver = cursor.fetchone()[0]
    assert ver >= 48
    conn_v.close()

    # 5. Probar que rechaza un archivo corrupto sin destruir la base de datos
    with open(corrupt_file, "wb") as f:
        f.write(b"NOT A SQLITE DATABASE FILE GARBAGE CONTENT")

    with pytest.raises(Exception):
        utils.restore_backup(current_db_path=temp_target, backup_db_path=corrupt_file)

    # Limpieza
    for p in [temp_target, backup_file, corrupt_file]:
        if os.path.exists(p):
            try:
                os.remove(p)
            except Exception:
                pass
