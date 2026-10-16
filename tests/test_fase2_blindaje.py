import os
import sqlite3
import pytest
import conftest  # noqa: F401
import database as db
import utils_reports
import utils

def test_ajuste1_1_isolation_y_rollback_atomico():
    """Ajuste 1.1: BEGIN IMMEDIATE con isolation_level=None y rollback atómico ante fallos."""
    nombre_obra_test = "Obra Test Rollback Atómico"
    
    # 1. Comprobar que una excepción dentro del bloque db_session realiza rollback total
    with pytest.raises(RuntimeError):
        with db.db_session() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO obras (nombre, expediente_imuh, activa, moneda_id, monto_contrato_moneda, monto_contrato, cotizacion_base_contrato)
                VALUES (?, '8008801-I-2026', 1, 1, 1000000.0, 1000000.0, 1.0)
            ''', (nombre_obra_test,))
            # Forzar fallo posterior
            raise RuntimeError("Fallo deliberado para probar rollback")
            
    # Verificar que el registro no existe
    with db.db_session() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) as cnt FROM obras WHERE nombre = ?", (nombre_obra_test,))
        assert cursor.fetchone()['cnt'] == 0


def test_ajuste1_2_ultima_cotizacion_info():
    """Ajuste 1.2: Retorno estructurado de cotización con fecha y origen para evitar sesgo de confirmación."""
    monedas = db.get_monedas_indices()
    uvis = [m for m in monedas if m['codigo'] == 'UVI']
    uvis_id = uvis[0]['id'] if uvis else db.add_moneda_indice('UVI', 'Unidad de Vivienda', 'UVI', tipo='Índice', decimales=2)

    obra_id = db.add_obra(
        nombre="Obra Info Cotizacion Test",
        expediente_imuh="8008802-I-2026",
        moneda_id=uvis_id,
        monto_contrato_moneda=5000.0,
        cotizacion_base_contrato=1000.0,
        fecha_contrato="2026-01-01"
    )

    db.add_pago_fondos_propios(
        obra_id=obra_id,
        monto=200000.0,
        fecha="2099-05-15",
        nro_op="OP-INFO-TEST",
        observaciones="Pago para registrar info cotizacion",
        cotizacion_pago=1250.75
    )

    info = db.get_ultima_cotizacion_info(uvis_id)
    assert info is not None
    assert info['cotizacion'] == 1250.75
    assert info['fecha'] == "2099-05-15"
    assert "Pago Fondos Propios" in info['origen']
    assert db.get_ultima_cotizacion(uvis_id) == 1250.75


def test_ajuste1_3_kpis_convenios_transito_exacto():
    """Ajuste 1.3: Certificados en tránsito calculados como (moneda - cobrada) * cotizacion_solicitud."""
    monedas = db.get_monedas_indices()
    uvis = [m for m in monedas if m['codigo'] == 'UVI']
    uvis_id = uvis[0]['id'] if uvis else db.add_moneda_indice('UVI', 'Unidad de Vivienda', 'UVI', tipo='Índice', decimales=2)

    kpis_antes = db.get_kpis_convenios_global()

    conv_id = db.add_convenio(
        nro_convenio="CONV-KPIS-01",
        ente_financiador="Nación",
        nombre_convenio="Convenio Test KPIs Tránsito",
        nro_expediente="EXP-KPIS-001",
        fecha_firma="2026-01-01",
        moneda_id=uvis_id,
        monto_pactado_moneda=10000.0,
        cotizacion_base=1000.0,
        monto_equivalente_ars=10000000.0
    )

    obra_id = db.add_obra(
        nombre="Obra Asociada Convenio KPIs",
        expediente_imuh="8008803-I-2026",
        moneda_id=uvis_id,
        monto_contrato_moneda=10000.0,
        cotizacion_base_contrato=1000.0
    )
    db.add_obra_to_convenio(conv_id, obra_id, monto_pactado_moneda=10000.0, monto_equivalente_ars=10000000.0, porcentaje=100.0)

    # Solicitud de 2.000 UVIs a $1.200 = $2.400.000 solicitados
    sol_id = db.add_solicitud_convenio(
        convenio_id=conv_id,
        obra_id=obra_id,
        nro_certificado="1",
        periodo="Enero 2026",
        cantidad_moneda=2000.0,
        cotizacion_solicitud=1200.0,
        monto_solicitado_ars=2400000.0,
        fecha_solicitud="2026-01-10"
    )

    # Cobro parcial de 800 UVIs a $1.200 = $960.000
    db.add_cobro(
        monto=960000.0,
        fecha="2026-02-01",
        origen_tipo="convenio",
        convenio_solicitud_id=sol_id,
        cantidad_moneda_origen=800.0,
        cotizacion_cobro=1200.0
    )

    # Remanente en tránsito: 1.200 UVIs a $1.200 = $1.440.000 (NO $2.400.000)
    kpis_despues = db.get_kpis_convenios_global()
    delta_moneda = round(kpis_despues['total_transito_moneda'] - kpis_antes['total_transito_moneda'], 2)
    delta_ars = round(kpis_despues['total_transito_ars'] - kpis_antes['total_transito_ars'], 2)
    assert delta_moneda == 1200.0
    assert delta_ars == 1440000.0


def test_tarea2_1_ecuacion_canonica_y_bloqueo_delete_cobro():
    """Tarea 2.1: Ecuación canónica _calcular_saldos_cobro_tx y guarda en delete_cobro."""
    dec_id = db.add_decreto(nro_decreto=901, anio=2026, nro_expediente="EXP-DEC-901", destino_fondos="Test Canónico")
    cuota_id = db.add_cuota(decreto_id=dec_id, mes=1, anio=2026, monto=100000.0)
    cobro_id = db.add_cobro(cuota_id=cuota_id, monto=100000.0, fecha="2026-01-20")

    obra_id = db.add_obra(nombre="Obra Recupero FP Test", expediente_imuh="8008804-I-2026", monto_contrato_moneda=500000.0)
    pago_fp_id = db.add_pago_fondos_propios(obra_id=obra_id, monto=40000.0, fecha="2026-01-05", nro_op="OP-FP-01", observaciones="Adelanto previo")

    # Registrar recupero de fondos propios desde este cobro por $30.000
    db.add_recupero_fondos_propios(cobro_id=cobro_id, obra_id=obra_id, monto=30000.0, fecha="2026-01-25", nro_op="OP-REC-01", notas="Recupero a fondos propios")

    # Quedan $70.000 disponibles. Intentar asignar $80.000 a Fin Original debe fallar por ecuación canónica
    with pytest.raises(ValueError, match="supera el monto total del cobro"):
        db.upsert_distribucion(cobro_id=cobro_id, monto_fin_orig=80000.0, monto_reserva=0.0)

    # Asignar $50.000 a Fin Original debe ser exitoso (30k FP + 50k FO = 80k <= 100k)
    db.upsert_distribucion(cobro_id=cobro_id, monto_fin_orig=50000.0, monto_reserva=0.0)

    # Intentar eliminar el cobro teniendo recuperos de fondos propios debe ser bloqueado
    with pytest.raises(ValueError, match="recuperos de fondos propios"):
        db.delete_cobro(cobro_id)


def test_tarea2_2_cuadre_composicion_con_recuperos_reserva_y_fp():
    """Tarea 2.2: Cuadre exacto en obtener_datos_composicion de cuota."""
    dec_id = db.add_decreto(nro_decreto=902, anio=2026, nro_expediente="EXP-DEC-902", destino_fondos="Test Cuadre")
    cuota_id = db.add_cuota(decreto_id=dec_id, mes=1, anio=2026, monto=200000.0)
    cobro_id = db.add_cobro(cuota_id=cuota_id, monto=200000.0, fecha="2026-01-20")

    # Distribución inicial: 50k FO, 100k Reserva. Desvío inicial de 30k. Saldo libre: 20k
    db.upsert_distribucion(cobro_id=cobro_id, monto_fin_orig=50000.0, monto_reserva=100000.0)
    desvio_id = db.add_desvio(cobro_id=cobro_id, monto=30000.0, fecha="2026-01-22", destino="Obra Prestada", nro_op="OP-DESV-INI", motivo="Prestamo de prueba inicial")

    # Recupero del desvío con destino_tipo == 'reserva' por 15.000
    db.add_desvio_recupero(desvio_id=desvio_id, monto=15000.0, fecha="2026-01-25", destino_tipo="reserva", nro_op="OP-REC-01", notas="Devolución a reserva")

    # Recupero de fondos propios por 10.000
    obra_id = db.add_obra(nombre="Obra Adelanto Cuadre", expediente_imuh="8008805-I-2026", monto_contrato_moneda=100000.0)
    p_id = db.add_pago_fondos_propios(obra_id=obra_id, monto=10000.0, fecha="2026-01-02", nro_op="OP-PREV-01", observaciones="Adelanto cuadre")
    db.add_recupero_fondos_propios(cobro_id=cobro_id, obra_id=obra_id, monto=10000.0, fecha="2026-01-26", nro_op="OP-REC-02", notas="Recupero adelanto cuadre")

    # Comprobar la composición
    filas, sum_total, cobros, *_ = utils_reports.obtener_datos_composicion(dec_id, cuota_id)
    assert round(sum_total, 2) == 200000.0
    
    # Comprobar que existe la fila de Reintegro a Fondos Propios
    fp_filas = [f for f in filas if f['Movimiento'] == "Recupero a Fondos Propios"]
    assert len(fp_filas) == 1
    assert fp_filas[0]['Monto'] == 10000.0


def test_tarea2_3_atribucion_exacta_acreencias_convenio_multiobra():
    """Tarea 2.3: Un desvío originado en un Convenio Multiobra se atribuye únicamente a la obra de ese certificado."""
    monedas = db.get_monedas_indices()
    uvis_id = [m['id'] for m in monedas if m['codigo'] == 'UVI'][0]

    conv_id = db.add_convenio(
        nro_convenio="CONV-MULTI-01",
        ente_financiador="Provincia",
        nombre_convenio="Convenio Multiobra Acreencias Test",
        nro_expediente="EXP-MULTI-001",
        fecha_firma="2026-01-01",
        moneda_id=uvis_id,
        monto_pactado_moneda=50000.0,
        cotizacion_base=1000.0,
        monto_equivalente_ars=50000000.0
    )

    obra1_id = db.add_obra(nombre="Obra Alfa Acreedora", expediente_imuh="8008806-I-2026", moneda_id=uvis_id, monto_contrato_moneda=25000.0, cotizacion_base_contrato=1000.0)
    obra2_id = db.add_obra(nombre="Obra Beta No Acreedora", expediente_imuh="8008807-I-2026", moneda_id=uvis_id, monto_contrato_moneda=25000.0, cotizacion_base_contrato=1000.0)
    obra3_id = db.add_obra(nombre="Obra Gamma Deudora", expediente_imuh="8008808-I-2026", monto_contrato_moneda=5000000.0)

    db.add_obra_to_convenio(conv_id, obra1_id, monto_pactado_moneda=25000.0, monto_equivalente_ars=25000000.0, porcentaje=50.0)
    db.add_obra_to_convenio(conv_id, obra2_id, monto_pactado_moneda=25000.0, monto_equivalente_ars=25000000.0, porcentaje=50.0)

    # Certificado para Obra Alfa
    sol_id = db.add_solicitud_convenio(
        convenio_id=conv_id,
        obra_id=obra1_id,
        nro_certificado="Cert-Alfa-1",
        periodo="Febrero 2026",
        cantidad_moneda=5000.0,
        cotizacion_solicitud=1000.0,
        monto_solicitado_ars=5000000.0,
        fecha_solicitud="2026-02-01"
    )
    cobro_id = db.add_cobro(
        monto=5000000.0,
        fecha="2026-02-15",
        origen_tipo="convenio",
        convenio_solicitud_id=sol_id,
        cantidad_moneda_origen=5000.0,
        cotizacion_cobro=1000.0
    )

    # Desvío de fondos prestados hacia Obra Gamma
    db.add_desvio(
        cobro_id=cobro_id,
        monto=1000000.0,
        fecha="2026-02-18",
        destino="8008808-I-2026 - Obra Gamma Deudora",
        obra_id=obra3_id,
        nro_op="OP-CONV-DESV",
        motivo="Préstamo entre obras convenio"
    )

    o1 = db.get_obra(obra1_id)
    o2 = db.get_obra(obra2_id)

    rows_acr1, _ = utils_reports.obtener_estado_deudas_por_obra(o1)
    rows_acr2, _ = utils_reports.obtener_estado_deudas_por_obra(o2)

    # Obra 1 es la legítima acreedora
    assert len(rows_acr1) == 1
    assert rows_acr1[0]['Saldo Pendiente'] == 1000000.0

    # Obra 2 NO debe tener acreencias (se eliminó la falsa duplicación)
    assert len(rows_acr2) == 0


def test_tarea2_4_validaciones_piso_techo_solicitud_convenio():
    """Tarea 2.4: Validaciones de piso, techo y recálculo de estado en solicitudes de convenio."""
    monedas = db.get_monedas_indices()
    uvis_id = [m['id'] for m in monedas if m['codigo'] == 'UVI'][0]

    conv_id = db.add_convenio(
        nro_convenio="CONV-CUPOS-01",
        ente_financiador="Nación",
        nombre_convenio="Convenio Cupos Piso Techo",
        nro_expediente="EXP-CUPOS-001",
        fecha_firma="2026-01-01",
        moneda_id=uvis_id,
        monto_pactado_moneda=10000.0,
        cotizacion_base=1000.0,
        monto_equivalente_ars=10000000.0
    )

    obra_id = db.add_obra(nombre="Obra Piso Techo", expediente_imuh="8008809-I-2026", moneda_id=uvis_id, monto_contrato_moneda=10000.0, cotizacion_base_contrato=1000.0)
    db.add_obra_to_convenio(conv_id, obra_id, monto_pactado_moneda=10000.0, monto_equivalente_ars=10000000.0, porcentaje=100.0)

    sol_id = db.add_solicitud_convenio(
        convenio_id=conv_id,
        obra_id=obra_id,
        nro_certificado="Cert-1",
        periodo="Marzo 2026",
        cantidad_moneda=4000.0,
        cotizacion_solicitud=1000.0,
        monto_solicitado_ars=4000000.0,
        fecha_solicitud="2026-03-01"
    )

    # Cobro parcial de 2.000 UVIs
    db.add_cobro(
        monto=2000000.0,
        fecha="2026-03-10",
        origen_tipo="convenio",
        convenio_solicitud_id=sol_id,
        cantidad_moneda_origen=2000.0,
        cotizacion_cobro=1000.0
    )

    # 1. Validación de piso: intentar reducir a 1.500 UVIs (< 2.000 cobradas) debe fallar
    with pytest.raises(ValueError, match="por debajo de lo ya percibido"):
        db.update_solicitud_convenio(
            solicitud_id=sol_id,
            nro_certificado="Cert-1",
            periodo="Marzo 2026",
            cantidad_moneda=1500.0,
            cotizacion_solicitud=1000.0,
            monto_solicitado_ars=1500000.0,
            fecha_solicitud="2026-03-01"
        )

    # 2. Validación de techo: intentar aumentar a 15.000 UVIs (> 10.000 convenio) debe fallar
    with pytest.raises(ValueError, match="excede el cupo disponible"):
        db.update_solicitud_convenio(
            solicitud_id=sol_id,
            nro_certificado="Cert-1",
            periodo="Marzo 2026",
            cantidad_moneda=15000.0,
            cotizacion_solicitud=1000.0,
            monto_solicitado_ars=15000000.0,
            fecha_solicitud="2026-03-01"
        )

    # 3. Reducción válida al importe cobrado (2.000 UVIs) -> estado pasa a 'Cobrado'
    db.update_solicitud_convenio(
        solicitud_id=sol_id,
        nro_certificado="Cert-1",
        periodo="Marzo 2026",
        cantidad_moneda=2000.0,
        cotizacion_solicitud=1000.0,
        monto_solicitado_ars=2000000.0,
        fecha_solicitud="2026-03-01"
    )

    with db.db_session() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT estado FROM convenio_solicitudes WHERE id = ?", (sol_id,))
        assert cursor.fetchone()['estado'] == 'Cobrado'


def test_tarea2_5_simetria_compensaciones_cruzadas():
    """Tarea 2.5: Borrado y actualización simétrica en compensaciones cruzadas."""
    dec1_id = db.add_decreto(nro_decreto=903, anio=2026, nro_expediente="EXP-DEC-903", destino_fondos="Dec 1")
    cuota1_id = db.add_cuota(decreto_id=dec1_id, mes=1, anio=2026, monto=100000.0)
    cobro1_id = db.add_cobro(cuota_id=cuota1_id, monto=100000.0, fecha="2026-01-20")

    dec2_id = db.add_decreto(nro_decreto=904, anio=2026, nro_expediente="EXP-DEC-904", destino_fondos="Dec 2")
    cuota2_id = db.add_cuota(decreto_id=dec2_id, mes=1, anio=2026, monto=100000.0)
    cobro2_id = db.add_cobro(cuota_id=cuota2_id, monto=100000.0, fecha="2026-01-20")

    # Desvío inicial de Cobro 1 a Dec 2
    desvio_id = db.add_desvio(cobro_id=cobro1_id, monto=40000.0, fecha="2026-01-22", destino="Dto. 904/2026", decreto_destino_id=dec2_id, nro_op="OP-DESV-01", motivo="Prestamo inicial")
    
    # Uso de Reserva de Cobro 2 a Dec 1
    db.upsert_distribucion(cobro_id=cobro2_id, monto_fin_orig=0.0, monto_reserva=100000.0)
    res_uso_id = db.add_reserva_uso(cobro_id=cobro2_id, monto=40000.0, fecha="2026-01-23", destino_tipo="otra_obra", destino_detalle="Dto. 903/2026", decreto_destino_id=dec1_id, nro_op="OP-RES-01", notas="Prestamo reserva")

    grupo_id = "GRUPO-TEST-SIMETRIA-1"

    # Insertar par compensado con grupo_compensacion_id
    with db.db_session() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO cobro_desvios_recuperos (desvio_id, monto, fecha, destino_tipo, destino_detalle, nro_op, notas, grupo_compensacion_id)
            VALUES (?, 25000.0, '2026-01-28', 'compensacion', 'Compensación automática', 'OP-COMP-01', 'Compensación de deudas cruzadas', ?)
        ''', (desvio_id, grupo_id))
        rec_desvio_id = cursor.lastrowid

        cursor.execute('''
            INSERT INTO cobro_reserva_usos_recuperos (reserva_uso_id, monto, fecha, destino_tipo, destino_detalle, nro_op, notas, grupo_compensacion_id)
            VALUES (?, 25000.0, '2026-01-28', 'compensacion', 'Compensación automática', 'OP-COMP-01', 'Compensación de deudas cruzadas', ?)
        ''', (res_uso_id, grupo_id))
        rec_reserva_id = cursor.lastrowid

    # 1. Probar actualización simétrica con update_desvio_recupero
    db.update_desvio_recupero(
        recupero_id=rec_desvio_id,
        monto=20000.0,
        fecha="2026-01-29",
        destino_tipo="compensacion",
        nro_op="OP-COMP-02",
        notas="Compensación ajustada"
    )

    with db.db_session() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT monto FROM cobro_reserva_usos_recuperos WHERE id = ?", (rec_reserva_id,))
        assert cursor.fetchone()['monto'] == 20000.0

    # 2. Probar eliminación simétrica con delete_desvio_recupero
    db.delete_desvio_recupero(rec_desvio_id)

    with db.db_session() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) as cnt FROM cobro_desvios_recuperos WHERE grupo_compensacion_id = ?", (grupo_id,))
        assert cursor.fetchone()['cnt'] == 0
        cursor.execute("SELECT COUNT(*) as cnt FROM cobro_reserva_usos_recuperos WHERE grupo_compensacion_id = ?", (grupo_id,))
        assert cursor.fetchone()['cnt'] == 0


def test_tarea2_6_bimonetario_desvios_y_auditoria_ops():
    """Tarea 2.6: Parámetros bimonetarios en desvíos y auditoría de OPs en pagos y recuperos de fondos propios."""
    monedas = db.get_monedas_indices()
    uvis_id = [m['id'] for m in monedas if m['codigo'] == 'UVI'][0]

    obra_id = db.add_obra(nombre="Obra Bimonetaria Desvío", expediente_imuh="8008810-I-2026", moneda_id=uvis_id, monto_contrato_moneda=10000.0, cotizacion_base_contrato=1000.0)

    dec_id = db.add_decreto(nro_decreto=905, anio=2026, nro_expediente="EXP-DEC-905", destino_fondos="Dec Bimon")
    cuota_id = db.add_cuota(decreto_id=dec_id, mes=1, anio=2026, monto=3000000.0)
    cobro_id = db.add_cobro(cuota_id=cuota_id, monto=3000000.0, fecha="2026-01-20")

    # Desvío bimonetario amortizando 1.000 UVIs a cotización $1.200 = $1.200.000
    desvio_id = db.add_desvio(
        cobro_id=cobro_id,
        monto=1200000.0,
        fecha="2026-01-25",
        destino="8008810-I-2026 - Obra Bimonetaria Desvío",
        obra_id=obra_id,
        nro_op="OP-DESV-BIM-01",
        motivo="Préstamo bimonetario",
        cantidad_moneda_amortizada=1000.0,
        cotizacion_pago=1200.0
    )

    # Verificar que get_pagos_detalle_por_obra retorna las columnas reales
    pagos_det = db.get_pagos_detalle_por_obra(obra_id)
    assert len(pagos_det) == 1
    assert pagos_det[0]['cantidad_moneda_amortizada'] == 1000.0
    assert pagos_det[0]['cotizacion_pago'] == 1200.0

    # Registrar un pago y un recupero con OP especial para validar get_op_usage_count y details
    op_especial = "OP-AUDIT-FP-99"
    pago_fp_id = db.add_pago_fondos_propios(obra_id=obra_id, monto=50000.0, fecha="2026-01-02", nro_op=op_especial, observaciones="Pago FP para op audit", cotizacion_pago=1200.0)
    db.add_recupero_fondos_propios(cobro_id=cobro_id, obra_id=obra_id, monto=50000.0, fecha="2026-01-26", nro_op=op_especial, notas="Recupero de adelanto propio")

    usage_count = db.get_op_usage_count(op_especial)
    assert usage_count >= 2
    usage_details = db.get_op_usage_details(op_especial)
    tablas_auditadas = [u['origen'] for u in usage_details]
    assert "Pago Fondos Propios" in tablas_auditadas
    assert "Recupero Fondos Propios" in tablas_auditadas


def test_tarea2_7_y_2_8_audit_log_y_preservacion_archivos(tmp_path):
    """Tarea 2.7 y 2.8: Bitácora forense audit_log con triggers JSON y preservación física de comprobantes."""
    # 1. Crear y actualizar una obra para verificar disparo de trigger en audit_log
    obra_id = db.add_obra(nombre="Obra Test Forense", expediente_imuh="8008811-I-2026", monto_contrato_moneda=2000000.0)
    db.update_obra(obra_id=obra_id, nombre="Obra Test Forense Modificada", expediente_imuh="8008811-I-2026", activa=1)

    historial = db.get_historial_cambios_registro("obras", obra_id)
    assert len(historial) >= 1
    assert historial[0]['accion'] == 'UPDATE'
    assert "Obra Test Forense" in historial[0]['valores_anteriores']

    # 2. Preservación física de comprobantes en delete_decreto
    archivo_falso = tmp_path / "comprobante_decreto_no_borrar.pdf"
    archivo_falso.write_text("Contenido crítico que nunca debe ser eliminado físicamente por base de datos")
    
    dec_id = db.add_decreto(nro_decreto=906, anio=2026, nro_expediente="EXP-DEC-906", destino_fondos="Preservar", pdf_path=str(archivo_falso))
    db.delete_decreto(dec_id)

    # El archivo físico DEBE seguir existiendo en el disco
    assert os.path.exists(str(archivo_falso))
