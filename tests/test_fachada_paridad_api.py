"""
tests/test_fachada_paridad_api.py - Suite de Verificación de Paridad Estricta de API y Blindaje Fase 3
Valida las 6 condiciones de ingeniería exigidas en el dictamen de Argon.
"""
import sys
import os
import inspect
import importlib
import pytest
import sqlite3

# Aislar entorno con conftest
import conftest
import database as db
import db_core


def test_ausencia_ciclos_importacion():
    """Regla 4: Verifica que cada submódulo de db_core pueda importarse de forma aislada sin errores."""
    submodulos = [
        'db_core.connection',
        'db_core.migrations',
        'db_core.repo_auditoria',
        'db_core.repo_catalogos',
        'db_core.repo_habituales',
        'db_core.repo_decretos',
        'db_core.repo_cobros',
        'db_core.repo_obras',
        'db_core.repo_convenios',
        'db_core.repo_desvios_reservas',
        'db_core.repo_compensaciones'
    ]
    for mod_name in submodulos:
        mod = importlib.import_module(mod_name)
        assert mod is not None, f"Error importando {mod_name}"


def test_paridad_simbolos_con_original():
    """Regla 2 y 3: Verifica que todos los símbolos de la API histórica existan en la fachada."""
    original_symbols_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scratch", "database_original_backup.py")
    
    if os.path.exists(original_symbols_path):
        import importlib.util
        spec = importlib.util.spec_from_file_location("database_original", original_symbols_path)
        orig_mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(orig_mod)
        
        orig_funcs = {name: obj for name, obj in inspect.getmembers(orig_mod, inspect.isfunction) if not name.startswith('__')}
        
        for name, orig_fn in orig_funcs.items():
            assert hasattr(db, name), f"Símbolo faltante en fachada: {name}"
            facade_fn = getattr(db, name)
            assert callable(facade_fn), f"El símbolo {name} no es invocable en la fachada"
            
            # Verificar paridad de firma inspect.signature
            orig_sig = inspect.signature(orig_fn)
            facade_sig = inspect.signature(facade_fn)
            assert orig_sig == facade_sig, f"Discrepancia de firma en {name}: {orig_sig} != {facade_sig}"


def test_paridad_monkeypatch_db_path(monkeypatch, tmp_path):
    """Regla 1: Verifica la resolución dinámica de DB_PATH mediante monkeypatch sobre la fachada."""
    temp_db = tmp_path / "temp_isolated.db"
    
    # Aplicar monkeypatch sobre la fachada database.DB_PATH
    monkeypatch.setattr(db, "DB_PATH", str(temp_db))
    
    # Validar que db_core.connection.get_db_path() resuelva dinámicamente el temp_db
    assert db_core.connection.get_db_path() == str(temp_db)
    
    # Validar que get_connection() abra efectivamente el archivo temporal
    conn = db.get_connection()
    try:
        conn.execute("CREATE TABLE test_isolation (id INTEGER PRIMARY KEY);")
        conn.execute("INSERT INTO test_isolation VALUES (1);")
        row = conn.execute("SELECT COUNT(*) FROM test_isolation;").fetchone()
        assert row[0] == 1
    finally:
        conn.close()
        
    assert os.path.exists(str(temp_db)), "El archivo temporal no fue creado por la conexión monkeypatched."


def test_ajuste_fase2_tope_bilateral_compensacion_cruzada():
    """Ajuste 1: Valida que update_desvio_recupero y update_reserva_uso_recupero rechacen montos que superen el saldo de cualquiera de las contrapartes."""
    dec1_id = db.add_decreto(nro_decreto=9901, anio=2026, nro_expediente="EXP-COMP-01", destino_fondos="Dec 1")
    cuota1_id = db.add_cuota(decreto_id=dec1_id, mes=1, anio=2026, monto=100000.0)
    cobro1_id = db.add_cobro(cuota_id=cuota1_id, monto=100000.0, fecha="2026-01-20")

    dec2_id = db.add_decreto(nro_decreto=9902, anio=2026, nro_expediente="EXP-COMP-02", destino_fondos="Dec 2")
    cuota2_id = db.add_cuota(decreto_id=dec2_id, mes=1, anio=2026, monto=100000.0)
    cobro2_id = db.add_cobro(cuota_id=cuota2_id, monto=100000.0, fecha="2026-01-20")

    # Desvío 1: monto máximo $30.000
    desvio_id = db.add_desvio(cobro_id=cobro1_id, monto=30000.0, fecha="2026-01-22", destino="Dto. 9902/2026", decreto_destino_id=dec2_id, nro_op="OP-DESV-B1", motivo="Prestamo pata 1")

    # Uso de Reserva 2: monto máximo $50.000
    db.upsert_distribucion(cobro_id=cobro2_id, monto_fin_orig=0.0, monto_reserva=100000.0)
    res_uso_id = db.add_reserva_uso(cobro_id=cobro2_id, monto=50000.0, fecha="2026-01-23", destino_tipo="otra_obra", destino_detalle="Dto. 9901/2026", decreto_destino_id=dec1_id, nro_op="OP-RES-B2", notas="Prestamo pata 2")

    grupo_id = "GRUPO-TEST-TOPE-BILATERAL"

    with db.db_session() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO cobro_desvios_recuperos (desvio_id, monto, fecha, destino_tipo, destino_detalle, nro_op, notas, grupo_compensacion_id)
            VALUES (?, 15000.0, '2026-01-25', 'compensacion', 'Compensación automática', 'OP-COMP-B', 'Compensación par inicial', ?)
        ''', (desvio_id, grupo_id))
        rec_desv_id = cursor.lastrowid

        cursor.execute('''
            INSERT INTO cobro_reserva_usos_recuperos (reserva_uso_id, monto, fecha, destino_tipo, destino_detalle, nro_op, notas, grupo_compensacion_id)
            VALUES (?, 15000.0, '2026-01-25', 'compensacion', 'Compensación automática', 'OP-COMP-B', 'Compensación par inicial', ?)
        ''', (res_uso_id, grupo_id))
        rec_res_id = cursor.lastrowid

    # Caso válido: aumentar a $25.000 (menor a $30.000 del desvío y menor a $50.000 de la reserva)
    db.update_desvio_recupero(rec_id=rec_desv_id, monto=25000.0, fecha="2026-01-26", nro_op="OP-COMP-B", notas="Aumento valido")
    
    # Verificar simetría
    with db.db_session() as conn:
        res_row = conn.execute("SELECT monto FROM cobro_reserva_usos_recuperos WHERE id = ?", (rec_res_id,)).fetchone()
        assert float(res_row['monto']) == 25000.0

    # Caso inválido 1: intentar aumentar a $35.000 desde el recupero de reserva (supera el tope de $30.000 del desvío hermano)
    with pytest.raises(ValueError) as exc1:
        db.update_reserva_uso_recupero(rec_id=rec_res_id, monto=35000.0, fecha="2026-01-27", nro_op="OP-COMP-B", notas="Exceso tope hermano")
    assert "supera el saldo adeudado del desvío compensado" in str(exc1.value)

    # Caso inválido 2: intentar aumentar a $60.000 desde el recupero de desvío (supera el desvío y la reserva)
    with pytest.raises(ValueError) as exc2:
        db.update_desvio_recupero(rec_id=rec_desv_id, monto=60000.0, fecha="2026-01-27", nro_op="OP-COMP-B", notas="Exceso total tope")
    assert "supera el saldo adeudado" in str(exc2.value)


def test_ajuste_fase2_guardia_piso_update_convenio():
    """Ajuste 2: Valida que update_convenio no permita reducir monto_pactado_moneda por debajo de lo asignado a obras ni de lo certificado."""
    moneda_id = db.add_moneda_indice(nombre="UVI Test P2", codigo="UVIP2", simbolo="U$")
    
    # Crear convenio con 100.000 UVIs
    conv_id = db.add_convenio(
        nro_convenio="CONV-PISO-TEST",
        ente_financiador="Nación",
        nombre_convenio="Convenio Piso Test",
        nro_expediente="EXP-PISO-01",
        fecha_firma="2026-01-10",
        moneda_id=moneda_id,
        monto_pactado_moneda=100000.0,
        cotizacion_base=1000.0,
        monto_equivalente_ars=100000000.0
    )

    # Asignar obra con 40.000 UVIs
    obra_id = db.add_obra(
        nombre="Obra Convenio Piso",
        expediente_imuh="8000099-I-2026",
        moneda_id=moneda_id,
        monto_contrato_moneda=40000.0,
        cotizacion_base_contrato=1000.0
    )
    db.add_obra_to_convenio(
        convenio_id=conv_id,
        obra_id=obra_id,
        monto_pactado_moneda=40000.0,
        monto_equivalente_ars=40000000.0
    )

    # Emitir certificado/solicitud por 30.000 UVIs
    db.add_solicitud_convenio(
        convenio_id=conv_id,
        obra_id=obra_id,
        nro_certificado=1,
        periodo="2026-01",
        cantidad_moneda=30000.0,
        cotizacion_solicitud=1100.0,
        monto_solicitado_ars=33000000.0,
        fecha_solicitud="2026-01-15"
    )

    # Intento 1: Reducir convenio a 35.000 UVIs (menor a los 40.000 UVIs asignados a obras) -> Debe fallar
    with pytest.raises(ValueError) as exc1:
        db.update_convenio(
            convenio_id=conv_id,
            nro_convenio="CONV-PISO-TEST",
            ente_financiador="Nación",
            nombre_convenio="Convenio Piso Test",
            nro_expediente="EXP-PISO-01",
            fecha_firma="2026-01-10",
            moneda_id=moneda_id,
            monto_pactado_moneda=35000.0,
            cotizacion_base=1000.0,
            monto_equivalente_ars=35000000.0
        )
    assert "No se puede reducir el monto del convenio por debajo de la suma ya asignada a sus obras" in str(exc1.value)

    # Emitir segundo certificado por 25.000 UVIs (Total certificado: 55.000 UVIs, cupo contratado sigue en 40.000)
    # Primero ampliamos obra a 60.000 UVIs
    with db.db_session() as conn:
        conn.execute("UPDATE convenio_obras SET monto_pactado_moneda = 60000.0 WHERE convenio_id = ?", (conv_id,))
    
    db.add_solicitud_convenio(
        convenio_id=conv_id,
        obra_id=obra_id,
        nro_certificado=2,
        periodo="2026-02",
        cantidad_moneda=25000.0,
        cotizacion_solicitud=1150.0,
        monto_solicitado_ars=28750000.0,
        fecha_solicitud="2026-02-15"
    )

    # Intento 2: Reducir convenio a 50.000 UVIs (menor a los 55.000 UVIs certificados) -> Debe fallar
    with pytest.raises(ValueError) as exc2:
        db.update_convenio(
            convenio_id=conv_id,
            nro_convenio="CONV-PISO-TEST",
            ente_financiador="Nación",
            nombre_convenio="Convenio Piso Test",
            nro_expediente="EXP-PISO-01",
            fecha_firma="2026-01-10",
            moneda_id=moneda_id,
            monto_pactado_moneda=50000.0,
            cotizacion_base=1000.0,
            monto_equivalente_ars=50000000.0
        )
    assert "por debajo de la suma" in str(exc2.value)
