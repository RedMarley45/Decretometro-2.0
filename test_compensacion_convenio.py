import os
import sys
import unittest
import datetime
import sqlite3

# Import project modules
import database as db
import utils_reports
import backend_compensaciones

ORIGINAL_DB_PATH = db.DB_PATH
TEST_DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "test_decretometro_compensacion.db")

class TestCompensacionConvenio(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Point database to isolated test DB
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

    def test_flujo_completo_convenio_y_compensacion_cruzada(self):
        # 1. Crear Obras con expedientes normalizados válidos
        obra_a_id = db.add_obra(nombre="Obra Decreto A", expediente_imuh="8001001-I-2026")
        obra_b_id = db.add_obra(nombre="Obra Convenio B", expediente_imuh="8002002-I-2026")

        self.assertIsNotNone(obra_a_id)
        self.assertIsNotNone(obra_b_id)

        # 2. Configurar Decreto para Obra A
        dec_id = db.add_decreto(
            nro_decreto=101, anio=2026, nro_expediente="EXP-DEC-101",
            destino_fondos="Pavimento Sector A", expediente_imuh="8001001-I-2026"
        )
        db.add_decreto_obras(dec_id, [obra_a_id])
        cuota_a_id = db.add_cuota(
            decreto_id=dec_id, mes=1, anio=2026, monto=500000.0
        )
        self.assertIsNotNone(cuota_a_id)

        # Cobro bancario del Decreto de Obra A
        cobro_a_id = db.add_cobro(
            cuota_id=cuota_a_id, monto=500000.0, fecha="2026-02-01",
            origen_tipo="decreto"
        )
        self.assertIsNotNone(cobro_a_id)

        # Distribuir cobro A: 400.000 Fin Original, 100.000 Reserva
        db.upsert_distribucion(cobro_id=cobro_a_id, monto_fin_orig=400000.0, monto_reserva=100000.0, notas="Distribución Cobro A")

        # 3. Configurar Convenio en UVIs para Obra B
        # Moneda UVI es ID 2 (creada por migración)
        monedas = db.get_monedas_indices()
        uvi_moneda = next((m for m in monedas if m['codigo'] == 'UVI'), None)
        self.assertIsNotNone(uvi_moneda)

        conv_id = db.add_convenio(
            nro_convenio="CONV-UVI-2026", ente_financiador="Provincia de Neuquén",
            nombre_convenio="Plan Hábitat e Infraestructura", nro_expediente="EX-2026-9999",
            fecha_firma="2026-01-10", moneda_id=uvi_moneda['id'],
            monto_pactado_moneda=1000.0, cotizacion_base=1000.0,
            monto_equivalente_ars=1000000.0
        )
        self.assertIsNotNone(conv_id)

        # Validar guard de cupo en add_obra_to_convenio
        with self.assertRaises(ValueError):
            # No puede asignar 1500 UVIs si el convenio es de 1000 UVIs
            db.add_obra_to_convenio(conv_id, obra_b_id, monto_pactado_moneda=1500.0, monto_equivalente_ars=1500000.0)

        # Asignar 1000 UVIs a Obra B
        db.add_obra_to_convenio(conv_id, obra_b_id, monto_pactado_moneda=1000.0, monto_equivalente_ars=1000000.0)

        # Validar guard de cupo en add_solicitud_convenio
        with self.assertRaises(ValueError):
            # No puede pedir 1200 UVIs
            db.add_solicitud_convenio(
                convenio_id=conv_id, obra_id=obra_b_id, nro_certificado="Certificado N° 0",
                periodo="Enero 2026", cantidad_moneda=1200.0, cotizacion_solicitud=1000.0,
                monto_solicitado_ars=1200000.0, fecha_solicitud="2026-01-20"
            )

        # Emitir certificado válido de 200 UVIs @ $1.000 = $200.000
        sol_id = db.add_solicitud_convenio(
            convenio_id=conv_id, obra_id=obra_b_id, nro_certificado="Certificado N° 1",
            periodo="Enero 2026", cantidad_moneda=200.0, cotizacion_solicitud=1000.0,
            monto_solicitado_ars=200000.0, fecha_solicitud="2026-01-20"
        )

        # Validar guards de integridad en add_cobro
        with self.assertRaises(ValueError):
            # origen_tipo 'convenio' con cuota_id seteada debe fallar
            db.add_cobro(
                cuota_id=cuota_a_id, convenio_solicitud_id=sol_id, monto=100000.0,
                fecha="2026-02-10", origen_tipo="convenio"
            )

        with self.assertRaises(ValueError):
            # No puede amortizar más de 200 UVIs
            db.add_cobro(
                convenio_solicitud_id=sol_id, monto=300000.0, fecha="2026-02-10",
                origen_tipo="convenio", cantidad_moneda_origen=250.0, cotizacion_cobro=1100.0
            )

        # Cobro bancario efectivo: Cobro de 200 UVIs a cotización $1.100 = $220.000 ($20.000 ganancia indexación)
        cobro_b_id = db.add_cobro(
            convenio_solicitud_id=sol_id, monto=220000.0, fecha="2026-02-10",
            origen_tipo="convenio", cantidad_moneda_origen=200.0, cotizacion_cobro=1100.0,
            obra_id=obra_b_id
        )
        self.assertIsNotNone(cobro_b_id)

        # Verificar diferencia_ajuste_ars en cobro
        cobro_b = db.get_cobro(cobro_b_id)
        self.assertAlmostEqual(cobro_b['diferencia_ajuste_ars'], 20000.0, places=2)

        # Distribuir cobro B: 190.000 Fin Original, quedando 30.000 para Desvío Inicial
        db.upsert_distribucion(cobro_id=cobro_b_id, monto_fin_orig=190000.0, monto_reserva=0.0, notas="Distribución Cobro B")

        # 4. Generar Préstamos Cruzados (Desvíos entre Obra A y Obra B)
        # Obra A presta $50.000 a Obra B (desde su reserva)
        uso_res_id = db.add_reserva_uso(
            cobro_id=cobro_a_id, monto=50000.0, destino_tipo="prestamo_obra",
            destino_detalle="Préstamo a Obra Convenio B", fecha="2026-02-15",
            notas="Préstamo a Obra Convenio B", obra_id=obra_b_id, nro_op="OP-A-100"
        )
        self.assertIsNotNone(uso_res_id)

        # Obra B presta $30.000 a Obra A (desvío desde cobro del Convenio)
        desvio_id = db.add_desvio(
            cobro_id=cobro_b_id, destino="Préstamo a Obra Decreto A", monto=30000.0,
            motivo="Préstamo a Obra Decreto A", fecha="2026-02-20",
            obra_id=obra_a_id, nro_op="OP-B-200"
        )
        self.assertIsNotNone(desvio_id)

        # 5. Probar detección en backend_compensaciones
        pares = backend_compensaciones.calcular_saldos_cruzados_globales()
        self.assertEqual(len(pares), 1, "Debe detectar exactamente 1 par de obras con deudas cruzadas")
        par = pares[0]
        self.assertAlmostEqual(par['monto_maximo'], 30000.0, places=2)

        # 6. Ejecutar Compensación Cruzada por $30.000
        ok, msg = backend_compensaciones.ejecutar_compensacion("8001001", "8002002", 30000.0)
        self.assertTrue(ok, f"La compensación falló: {msg}")

        # 7. Verificar saldos remanentes
        # Obra B debía 50.000 a Obra A, ahora debe 20.000
        # Obra A debía 30.000 a Obra B, ahora debe 0.00
        pares_post = backend_compensaciones.calcular_saldos_cruzados_globales()
        self.assertEqual(len(pares_post), 0, "No deben quedar saldos cruzados compensables")

        # Verificar desvío inicial de Obra B a Obra A (debería quedar en 0)
        historial_desv = db.get_historial_desvios()
        desv_b = next((d for d in historial_desv if d['desvio_id'] == desvio_id and d['tipo_origen'] == 'inicial'), None)
        self.assertIsNotNone(desv_b)
        self.assertAlmostEqual(desv_b['saldo'], 0.0, places=2)

        # Verificar uso de reserva de Obra A a Obra B (debería quedar en 20.000)
        res_a = next((d for d in historial_desv if d['desvio_id'] == uso_res_id and d['tipo_origen'] == 'reserva'), None)
        self.assertIsNotNone(res_a)
        self.assertAlmostEqual(res_a['saldo'], 20000.0, places=2)

        # 8. Verificar trazabilidad por obra
        traz_b = db.get_trazabilidad_fuentes_por_obra(obra_id=obra_b_id)
        # Obra B tiene Fin Original por Convenio y Préstamo (Uso Reserva) recibido
        tipos_b = [t['tipo_financiamiento'] for t in traz_b]
        self.assertIn("Fin Original", tipos_b)
        self.assertIn("Uso de Reserva", tipos_b)

        # 9. Verificar KPIs Convenios Global
        kpis_conv = db.get_kpis_convenios_global()
        self.assertEqual(kpis_conv['total_vigentes'], 1)
        self.assertAlmostEqual(kpis_conv['total_cobrado_ars'], 220000.0, places=2)
        self.assertAlmostEqual(kpis_conv['total_diferencia_ars'], 20000.0, places=2)

        print("\n--> TEST INTEGRAL DE COMPENSACIÓN CRUZADA CONVENIO <-> DECRETO EXITOSO <--\n")

if __name__ == '__main__':
    unittest.main()
