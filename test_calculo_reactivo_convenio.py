import pytest
import datetime
import database as db

def test_calculo_teorico_y_discrepancias():
    """
    Verifica las reglas de negocio acordadas con el usuario Martín Rodríguez:
    1. Cálculo teórico: Cantidad × Cotización.
    2. Clasificación de discrepancias porcentuales:
       - < 0.10%: redondeo normal / nivel informativo.
       - 0.10% a 0.99%: alerta amarilla (moderada).
       - >= 1.00%: alerta roja (significativa) con confirmación obligatoria.
    """
    cant = 303837.59
    cotiz = 1512.96
    teorico = round(cant * cotiz, 2)
    
    # 1. Verificación del producto teórico
    # 303.837,59 * 1.512,96 = 459.694.120,1664 -> 459.694.120,17
    assert teorico == 459694120.17

    def clasificar_discrepancia(monto_ingresado, monto_teorico):
        if monto_teorico <= 0:
            return "NORMAL", 0.0, 0.0
        dif = round(monto_ingresado - monto_teorico, 2)
        pct = abs(dif) / monto_teorico * 100.0
        if pct < 0.10:
            nivel = "NORMAL"
        elif pct < 1.00:
            nivel = "AMARILLA"
        else:
            nivel = "ROJA"
        return nivel, dif, pct

    # Caso 1: Exacto
    nivel, dif, pct = clasificar_discrepancia(459694120.17, teorico)
    assert nivel == "NORMAL"
    assert dif == 0.0
    assert pct == 0.0

    # Caso 2: Pequeña diferencia de centavos (ej: +$0,38 del certificado oficial)
    nivel, dif, pct = clasificar_discrepancia(459694120.55, teorico)
    assert nivel == "NORMAL"
    assert dif == 0.38
    assert pct < 0.10

    # Caso 3: Discrepancia del 0.20% (Alerta Amarilla)
    monto_amarilla = round(teorico * 1.002, 2)
    nivel, dif, pct = clasificar_discrepancia(monto_amarilla, teorico)
    assert nivel == "AMARILLA"
    assert 0.10 <= pct < 1.00

    # Caso 4: Discrepancia del 1.50% (Alerta Roja)
    monto_roja = round(teorico * 1.015, 2)
    nivel, dif, pct = clasificar_discrepancia(monto_roja, teorico)
    assert nivel == "ROJA"
    assert pct >= 1.00


def test_add_solicitud_con_redondeo_en_bd():
    """
    Verifica que la base de datos almacene correctamente el monto con diferencia de centavos
    y conserve tanto la cantidad en UVI, la cotización y el monto solicitado en pesos acordado.
    """
    monedas = db.get_monedas_indices()
    uvi = next((m for m in monedas if m['codigo'] == 'UVI'), None)
    if not uvi:
        pytest.skip("No existe la moneda UVI en la base de datos.")
        
    obras = db.get_obras()
    creada_obra_temporal = False
    if not obras:
        obra_id = db.add_obra(
            nombre="Obra Test Reactiva",
            expediente_imuh="8009988-I-2026",
            moneda_id=uvi['id'],
            monto_contrato_moneda=50000.0,
            cotizacion_base_contrato=1500.0
        )
        obra = db.get_obra(obra_id)
        creada_obra_temporal = True
    else:
        obra = obras[0]

    # Crear convenio de prueba temporal
    nro_conv_test = f"TEST-REACTIVO-{int(datetime.datetime.now().timestamp())}"
    conv_id = db.add_convenio(
        nro_convenio=nro_conv_test,
        ente_financiador="Ente Test",
        nombre_convenio="Convenio Test Reactivo",
        nro_expediente="EXP-TEST-999",
        fecha_firma=str(datetime.date.today()),
        moneda_id=uvi['id'],
        monto_pactado_moneda=100000.0,
        cotizacion_base=1500.0,
        monto_equivalente_ars=150000000.0,
        pdf_path=None,
        notas="Test temporal"
    )
    
    # Asignar obra al convenio
    db.add_obra_to_convenio(conv_id, obra['id'], monto_pactado_moneda=50000.0, monto_equivalente_ars=75000000.0)

    cant = 10.0
    cotiz = 1500.0
    monto_teorico = cant * cotiz # 15.000,00
    monto_con_redondeo = 15000.45 # +45 centavos

    nro_cert = f"TEST-CERT-{int(datetime.datetime.now().timestamp())}"
    sol_id = db.add_solicitud_convenio(
        convenio_id=conv_id,
        obra_id=obra['id'],
        nro_certificado=nro_cert,
        periodo="Septiembre 2026",
        cantidad_moneda=cant,
        cotizacion_solicitud=cotiz,
        monto_solicitado_ars=monto_con_redondeo,
        fecha_solicitud=str(datetime.date.today()),
        expediente_pago="EXP-TEST-REDONDEO",
        pdf_path=None,
        notas="Test de tolerancia por redondeo"
    )

    sol_creada = db.get_solicitud_convenio(sol_id)
    assert sol_creada is not None
    assert sol_creada['cantidad_moneda'] == cant
    assert sol_creada['cotizacion_solicitud'] == cotiz
    assert sol_creada['monto_solicitado_ars'] == monto_con_redondeo

    # Limpieza total del convenio y solicitud de prueba
    with db.db_session() as conn:
        conn.cursor().execute("DELETE FROM convenio_solicitudes WHERE convenio_id = ?", (conv_id,))
        conn.cursor().execute("DELETE FROM convenio_obras WHERE convenio_id = ?", (conv_id,))
        conn.cursor().execute("DELETE FROM convenios WHERE id = ?", (conv_id,))
        if creada_obra_temporal:
            conn.cursor().execute("DELETE FROM obras WHERE id = ?", (obra['id'],))
        conn.commit()


def test_sugerencia_cotizacion_obra():
    """
    Verifica que la sugerencia de cotización obtenga:
    1. La cotización de la última solicitud emitida para la obra específica.
    2. Si la obra no tiene solicitudes previas, la cotización base del convenio.
    """
    solicitudes_mock = [
        {"id": 2, "obra_id": 10, "cotizacion_solicitud": 1531.65, "estado": "Pendiente"},
        {"id": 1, "obra_id": 10, "cotizacion_solicitud": 1512.96, "estado": "Cobrado"},
        {"id": 3, "obra_id": 20, "cotizacion_solicitud": 1400.00, "estado": "Pendiente"}
    ]
    cotizacion_base_convenio = 1339.69

    def obtener_cotizacion_sugerida(obra_id, solicitudes, base_convenio):
        if not obra_id:
            return 0.0
        sols = [s for s in solicitudes if s['obra_id'] == obra_id and s.get('estado') != 'Anulado']
        if sols:
            return float(sols[0]['cotizacion_solicitud'])
        return float(base_convenio or 1.0)

    # Obra 10: debe sugerir la última (1531.65)
    assert obtener_cotizacion_sugerida(10, solicitudes_mock, cotizacion_base_convenio) == 1531.65

    # Obra 20: debe sugerir su última (1400.00)
    assert obtener_cotizacion_sugerida(20, solicitudes_mock, cotizacion_base_convenio) == 1400.00

    # Obra 30 (sin solicitudes previas): debe sugerir la base del convenio (1339.69)
    assert obtener_cotizacion_sugerida(30, solicitudes_mock, cotizacion_base_convenio) == 1339.69

    # Sin obra seleccionada (None): debe retornar 0.0
    assert obtener_cotizacion_sugerida(None, solicitudes_mock, cotizacion_base_convenio) == 0.0

