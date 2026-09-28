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
        # Aislar en base de datos temporal
        if os.path.exists(TEST_DB_PATH):
            try:
                os.remove(TEST_DB_PATH)
            except OSError:
                pass
        db.DB_PATH = TEST_DB_PATH
        db.init_db()

    @classmethod
    def tearDownClass(cls):
        db.DB_PATH = ORIGINAL_DB_PATH
        if os.path.exists(TEST_DB_PATH):
            try:
                os.remove(TEST_DB_PATH)
            except OSError:
                pass

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
        self.assertEqual(obra['monto_contrato'], 50000000.0) # 50.000 * 1.000
        
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
        # Total contratado: 50.000 + 5.000 = 55.000 UVIs
        self.assertEqual(resumen['total_contratado_moneda'], 55000.0)
        # Costo base total: $50.000.000 + $7.000.000 = $57.000.000 ARS
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
        
        # 1. Crear Convenio en UVIs
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
        
        # Vincular a la obra
        db.add_obra_to_convenio(
            convenio_id=conv_id,
            obra_id=obra_id,
            monto_pactado_moneda=50000.0,
            monto_equivalente_ars=50000000.0,
            porcentaje=100.0
        )
        
        # 2. Crear Solicitud / Certificado N° 1
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
        
        # 3. Registrar Cobro del Certificado (20.000 UVIs @ $1.250 = $25.000.000 ARS)
        cobro_id = db.add_cobro(
            monto=25000000.0,
            fecha="2026-02-28",
            convenio_solicitud_id=sol_id,
            origen_tipo='convenio',
            moneda_origen_id=3,
            cantidad_moneda_origen=20000.0,
            cotizacion_cobro=1250.0
        )
        
        # 4. Asignar distribución a Fin Original
        db.upsert_distribucion(cobro_id, monto_fin_orig=25000000.0, monto_reserva=0.0)
        
        # 5. Ejecutar Pago a Contratista (Orden de Pago OP-1001)
        # add_fin_original_uso auto-deriva UVIs (20.000) y cotización ($1.250) del cobro del convenio
        uso_id = db.add_fin_original_uso(
            cobro_id=cobro_id,
            monto=25000000.0,
            fecha="2026-03-05",
            nro_op="OP-1001",
            obra_id=obra_id
        )
        self.assertIsNotNone(uso_id)
        
        # 6. Verificación Contable y Algoritmo FIFO
        resumen = db.get_resumen_contrato_obra(obra_id)
        self.assertEqual(resumen['total_moneda_amortizada'], 20000.0)
        self.assertEqual(resumen['saldo_moneda_remanente'], 35000.0) # 55.000 - 20.000
        self.assertEqual(resumen['total_pagado_efectivo_ars'], 25000000.0)
        
        # Costo base de las 20.000 UVIs amortizadas del Tramo 0 (@ $1.000):
        # 20.000 * 1.000 = $20.000.000 ARS
        self.assertEqual(resumen['costo_base_amortizado_ars'], 20000000.0)
        
        # EXACTITUD CLAUDE TEST 3: Resultado por Indexación = $25.000.000 - $20.000.000 = $5.000.000 ARS
        self.assertEqual(resumen['resultado_indexacion_ars'], 5000000.0)
        
        # Verificar trazabilidad OP comprobante por comprobante
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
        # Amortizado total: 20.000 (de convenio) + 10.000 (fondos propios) = 30.000 UVIs
        self.assertEqual(resumen['total_moneda_amortizada'], 30000.0)
        self.assertEqual(resumen['saldo_moneda_remanente'], 25000.0) # 55.000 - 30.000
        
        # Total pagado efectivo: $25.000.000 + $13.000.000 = $38.000.000 ARS
        self.assertEqual(resumen['total_pagado_efectivo_ars'], 38000000.0)
        
        # Ambas amortizaciones (20.000 y 10.000) caen dentro del Tramo 0 (50.000 UVIs @ $1.000)
        # Costo base amortizado: 30.000 * 1.000 = $30.000.000 ARS
        self.assertEqual(resumen['costo_base_amortizado_ars'], 30000000.0)
        
        # Resultado por Indexación: $38.000.000 - $30.000.000 = $8.000.000 ARS
        self.assertEqual(resumen['resultado_indexacion_ars'], 8000000.0)

    def test_05_guarda_sobrepago_uvis(self):
        """5. Guarda de Sobrepago en UVIs:
        Intentar pagar 30.000 UVIs cuando el remanente total es de 25.000 UVIs.
        Verificar bloqueo y registro con motivo obligatorio.
        """
        obra = db.get_obra_by_expediente("8009901-I-2026")
        obra_id = obra['id']
        
        # Remanente actual: 25.000 UVIs. Intentamos pagar 30.000 UVIs
        chk = db.check_sobrepago_obra(obra_id, nuevo_monto_pesos=45000000.0, nueva_cantidad_moneda=30000.0)
        self.assertTrue(chk['es_sobrepago'])
        self.assertTrue(chk['es_bimonetaria'])
        self.assertEqual(chk['unidad'], 'UVI')
        self.assertEqual(chk['tope'], 55000.0)
        self.assertEqual(chk['acumulado_previo'], 30000.0)
        self.assertEqual(chk['nuevo_total'], 60000.0)
        self.assertEqual(chk['exceso'], 5000.0)
        self.assertIn("superando el contrato total", chk['mensaje'])
        
        # Registrar con motivo de sobrepago
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
        
        # Verificar que el motivo quedó persistido en la base de datos
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
            monto_contrato_moneda=10000000.0 # Ingresado como pesos
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
        
        # Test guarda de sobrepago en pesos
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

