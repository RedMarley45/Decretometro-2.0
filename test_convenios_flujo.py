import sys
import os
import datetime

import database as db
import utils

def cleanup_test_data():
    with db.db_session() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM convenios WHERE nro_convenio LIKE 'TEST-CONV%'")
        rows = cursor.fetchall()
        for r in rows:
            cid = r['id']
            cursor.execute("SELECT id FROM convenio_solicitudes WHERE convenio_id = ?", (cid,))
            sols = cursor.fetchall()
            for s in sols:
                cursor.execute("""
                    DELETE FROM cobro_distribuciones 
                    WHERE cobro_id IN (SELECT id FROM cobros WHERE convenio_solicitud_id = ?)
                """, (s['id'],))
                cursor.execute("DELETE FROM cobros WHERE convenio_solicitud_id = ?", (s['id'],))
            cursor.execute("DELETE FROM convenio_solicitudes WHERE convenio_id = ?", (cid,))
            cursor.execute("DELETE FROM convenio_obras WHERE convenio_id = ?", (cid,))
            cursor.execute("DELETE FROM convenios WHERE id = ?", (cid,))
        conn.commit()

def test_flujo_convenios_bimonetario():
    print("=== INICIANDO TEST DE INTEGRACIÓN: FLUJO BIMONETARIO DE CONVENIOS ===")
    cleanup_test_data()
    
    # 1. Verificar catálogo de monedas
    monedas = db.get_monedas_indices()
    codigos = [m['codigo'] for m in monedas]
    print(f"1. Monedas disponibles: {codigos}")
    assert 'ARS' in codigos, "Falta ARS"
    assert 'USD' in codigos, "Falta USD"
    assert 'UVI' in codigos, "Falta UVI"
    
    uvi_info = next(m for m in monedas if m['codigo'] == 'UVI')
    uvi_id = uvi_info['id']
    
    # Obtener obras existentes
    obras = db.get_obras()
    assert len(obras) >= 2, "Se requieren al menos 2 obras en el catálogo"
    obra1 = obras[0]
    obra2 = obras[1]
    
    conv_id = None
    sol_id = None
    cobro_id = None

    try:
        # 2. Crear Convenio de prueba en UVIs
        nro_conv = f"TEST-CONV-{datetime.date.today().strftime('%Y%m%d%H%M%S')}"
        monto_total_uvis = 50000.0   # 50.000 UVIs
        cotiz_base = 1200.0          # 1.200 ARS / UVI
        monto_equiv_ars = monto_total_uvis * cotiz_base # 60.000.000 ARS
        
        conv_id = db.add_convenio(
            nro_convenio=nro_conv,
            ente_financiador="Provincia del Neuquén - IPVU",
            nombre_convenio="Convenio Provincial Plan Hábitat Test",
            nro_expediente="EXP-CONV-2026-001",
            fecha_firma=str(datetime.date.today()),
            moneda_id=uvi_id,
            monto_pactado_moneda=monto_total_uvis,
            cotizacion_base=cotiz_base,
            monto_equivalente_ars=monto_equiv_ars,
            pdf_path=None,
            notas="Convenio de prueba para verificación automatizada"
        )
        print(f"2. Convenio creado ID: {conv_id} ({nro_conv}) por {monto_total_uvis:,.2f} UVIs (${monto_equiv_ars:,.2f} ARS)")
        
        # Asignar obras al convenio
        db.add_obra_to_convenio(conv_id, obra1['id'], monto_pactado_moneda=25000.0, monto_equivalente_ars=30000000.0, porcentaje=50.0)
        db.add_obra_to_convenio(conv_id, obra2['id'], monto_pactado_moneda=25000.0, monto_equivalente_ars=30000000.0, porcentaje=50.0)
        
        obras_asoc = db.get_obras_by_convenio(conv_id)
        assert len(obras_asoc) == 2, f"Deben haber 2 obras asociadas, hay {len(obras_asoc)}"
        print(f"   Obras asociadas: {[o['obra_nombre'] for o in obras_asoc]}")
        
        # 3. Control contractual inicial
        res_ctrl = db.get_resumen_control_convenio(conv_id)
        assert abs(res_ctrl['pactado_moneda_total'] - monto_total_uvis) < 0.01
        assert abs(res_ctrl['saldo_en_transito_moneda'] - 0.0) < 0.01
        assert abs(res_ctrl['cobrado_moneda_total'] - 0.0) < 0.01
        assert abs(res_ctrl['saldo_remanente_moneda'] - monto_total_uvis) < 0.01
        print(f"3. Control inicial OK -> Remanente: {res_ctrl['saldo_remanente_moneda']:,.2f} UVIs")
        
        # 4. Crear Solicitud de Desembolso / Certificado de Avance
        cant_solicitada_uvis = 10000.0
        cotiz_cert = 1250.0
        monto_ars_est = cant_solicitada_uvis * cotiz_cert # 12.500.000 ARS
        
        sol_id = db.add_solicitud_convenio(
            convenio_id=conv_id,
            obra_id=obra1['id'],
            nro_certificado="1",
            periodo="09/2026",
            cantidad_moneda=cant_solicitada_uvis,
            cotizacion_solicitud=cotiz_cert,
            monto_solicitado_ars=monto_ars_est,
            fecha_solicitud=str(datetime.date.today()),
            expediente_pago="EXP-TEST-001",
            pdf_path=None,
            notas="Certificado N° 1 de Avance de Obra"
        )
        print(f"4. Solicitud/Certificado N° 1 creada ID: {sol_id} por {cant_solicitada_uvis:,.2f} UVIs (~${monto_ars_est:,.2f} ARS)")
        
        # 5. Control contractual tras solicitud
        res_ctrl_2 = db.get_resumen_control_convenio(conv_id)
        assert abs(res_ctrl_2['saldo_en_transito_moneda'] - cant_solicitada_uvis) < 0.01
        assert abs(res_ctrl_2['saldo_remanente_moneda'] - (monto_total_uvis - cant_solicitada_uvis)) < 0.01
        print(f"5. Control tras solicitud OK -> En Trámite: {res_ctrl_2['saldo_en_transito_moneda']:,.2f} UVIs | Remanente: {res_ctrl_2['saldo_remanente_moneda']:,.2f} UVIs")
        
        # 6. Registrar Cobro Bancario en Pesos contra la Solicitud
        monto_cobrado_ars = 12550000.0
        cotiz_cobro = 1255.0
        dif_ajuste = monto_cobrado_ars - (cant_solicitada_uvis * cotiz_cert) # +50.000 ARS diferencia
        
        cobro_id = db.add_cobro(
            monto=monto_cobrado_ars,
            fecha=str(datetime.date.today()),
            cuota_id=None,
            convenio_solicitud_id=sol_id,
            origen_tipo='convenio',
            obra_id=obra1['id'],
            moneda_origen_id=uvi_id,
            cantidad_moneda_origen=cant_solicitada_uvis,
            cotizacion_cobro=cotiz_cobro,
            diferencia_ajuste_ars=dif_ajuste
        )
        print(f"6. Cobro bancario registrado ID: {cobro_id} por ${monto_cobrado_ars:,.2f} ARS (Ajuste cotiz: ${dif_ajuste:,.2f})")
        
        # 7. Control contractual post-cobro
        res_ctrl_3 = db.get_resumen_control_convenio(conv_id)
        assert abs(res_ctrl_3['saldo_en_transito_moneda'] - 0.0) < 0.01, "Las solicitudes en trámite deben ser 0"
        assert abs(res_ctrl_3['cobrado_moneda_total'] - cant_solicitada_uvis) < 0.01, f"Cobrado en UVIs debe ser {cant_solicitada_uvis}"
        assert abs(res_ctrl_3['cobrado_ars_total'] - monto_cobrado_ars) < 0.01, f"Cobrado en ARS debe ser {monto_cobrado_ars}"
        assert abs(res_ctrl_3['saldo_remanente_moneda'] - (monto_total_uvis - cant_solicitada_uvis)) < 0.01, "Remanente contractual en UVIs correcto"
        print(f"7. Control post-cobro OK -> Total Cobrado: {res_ctrl_3['cobrado_moneda_total']:,.2f} UVIs (${res_ctrl_3['cobrado_ars_total']:,.2f} ARS) | Remanente: {res_ctrl_3['saldo_remanente_moneda']:,.2f} UVIs")
        
        # 8. Verificar que la solicitud pasó a Cobrado
        sols = db.get_solicitudes_by_convenio(conv_id)
        sol_actualizada = next(s for s in sols if s['id'] == sol_id)
        assert sol_actualizada['estado'] in ('Cobrado', 'Cobrada'), f"Estado de solicitud debe ser 'Cobrado', es {sol_actualizada['estado']}"
        assert abs(sol_actualizada['cantidad_moneda_cobrada'] - cant_solicitada_uvis) < 0.01
        print(f"8. Estado de la solicitud: {sol_actualizada['estado']} (Cobrado: {sol_actualizada['cantidad_moneda_cobrada']:,.2f} UVIs)")
        
        # 9. Verificar integración con downstream (distribución de fondos del cobro)
        cobros_con_dist = db.get_cobros_con_resumen_distribucion()
        cobro_reciente = next((c for c in cobros_con_dist if c['id'] == cobro_id), None)
        assert cobro_reciente is not None, "El nuevo cobro de convenio debe aparecer en el resumen de distribución"
        assert cobro_reciente['origen_tipo'] == 'convenio'
        assert abs(cobro_reciente['monto'] - monto_cobrado_ars) < 0.01
        assert abs(cobro_reciente['total_distribuido'] - 0.0) < 0.01
        print(f"9. Cobro presente en distribución: Monto ${cobro_reciente['monto']:,.2f}, Total Distribuido: ${cobro_reciente['total_distribuido']:,.2f}")
        
        # Distribuir el cobro: $10.000.000 fin original, $2.550.000 reserva
        db.upsert_distribucion(
            cobro_id=cobro_id,
            monto_fin_orig=10000000.0,
            monto_reserva=2550000.0,
            notas="Reserva contractual certificada para materiales"
        )
        
        cobros_con_dist_post = db.get_cobros_con_resumen_distribucion()
        cobro_post = next(c for c in cobros_con_dist_post if c['id'] == cobro_id)
        assert abs(cobro_post['monto_fin_orig'] - 10000000.0) < 0.01
        assert abs(cobro_post['monto_reserva'] - 2550000.0) < 0.01
        assert abs(cobro_post['total_distribuido'] - monto_cobrado_ars) < 0.01
        print(f"   Distribución guardada OK: Fin Original ${cobro_post['monto_fin_orig']:,.2f}, Reserva ${cobro_post['monto_reserva']:,.2f}, Saldo a Distribuir: ${cobro_post['monto'] - cobro_post['total_distribuido']:,.2f}")

    finally:
        cleanup_test_data()
        print("10. Limpieza de datos de prueba completada con éxito.")
    
    print("\n=== TODAS LAS PRUEBAS DEL FLUJO BIMONETARIO PASARON EXITOSAMENTE ===")

if __name__ == "__main__":
    test_flujo_convenios_bimonetario()
