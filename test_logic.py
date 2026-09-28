import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
import database as db

TEMP_DB = 'test_temp_logic.db'
if os.path.exists(TEMP_DB):
    try: os.remove(TEMP_DB)
    except: pass
db.DB_PATH = TEMP_DB
db.init_db()

def run_tests():
    # Use main DB or test DB? Let's use the main one since it's empty right now
    # We will delete them after
    d_id = db.add_decreto(9999, 2026, "TEST-EXP", "Obra de prueba")
    c1 = db.add_cuota(d_id, 1, 2026, 500)
    c2 = db.add_cuota(d_id, 2, 2026, 500)
    
    # Recalculate status manually since cuota creation doesn't trigger automatic updates
    conn = db.get_connection()
    db.check_estado_decreto(conn, d_id)
    conn.close()
    
    d = db.get_decreto(d_id)
    assert d['estado'] == 'Con deuda', f"Expected Con deuda, got {d['estado']}"
    
    # Pay partial
    cob1 = db.add_cobro(c1, 200, "2026-01-10")
    d = db.get_decreto(d_id)
    assert d['estado'] == 'Con deuda', f"Expected Con deuda after partial, got {d['estado']}"
    
    # Pay rest of c1
    cob2 = db.add_cobro(c1, 300, "2026-01-15")
    
    # Pay c2
    cob3 = db.add_cobro(c2, 500, "2026-02-10")
    d = db.get_decreto(d_id)
    assert d['estado'] == 'Terminado', f"Expected Terminado after full pay, got {d['estado']}"
    
    # Test Anulado
    d_id2 = db.add_decreto(8888, 2026, "TEST-EXP-2", "Obra anulada test")
    c3 = db.add_cuota(d_id2, 3, 2026, 1000)
    db.update_estado_decreto(d_id2, 'Anulado')
    
    # Test delete protections (cannot delete decree with cobros)
    try:
        db.delete_decreto(d_id)
        assert False, "Expected ValueError when deleting decree with cobros"
    except ValueError:
        pass
        
    # Delete them in correct order
    db.delete_cobro(cob1)
    db.delete_cobro(cob2)
    db.delete_cobro(cob3)
    db.delete_decreto(d_id)
    db.delete_decreto(d_id2)
    
    # 2. Test IMUH Multiple Validations
    import utils
    # Valid single IMUHs
    assert utils.validar_expediente_imuh("8000063-I-2026") is True
    assert utils.validar_expediente_imuh("  8000063-I-2026   ") is True
    assert utils.validar_expediente_imuh("") is True
    assert utils.validar_expediente_imuh(None) is True
    
    # Valid multiple IMUHs with various separators
    assert utils.validar_expediente_imuh("8000063-I-2026, 8000064-I-2026") is True
    assert utils.validar_expediente_imuh("8000063-I-2026; 8000064-I-2026;8000065-A-2025") is True
    assert utils.validar_expediente_imuh("8000063-I-2026 / 8000064-I-2026") is True
    
    # Invalid IMUHs
    assert utils.validar_expediente_imuh("8000063-I-26") is False
    assert utils.validar_expediente_imuh("8000063-I-2026, invalid_imuh") is False
    assert utils.validar_expediente_imuh("8000063-I-2026; ") is True  # empty segments are skipped
    assert utils.validar_expediente_imuh("invalid") is False

    # Test IMUH Normalization
    assert utils.normalizar_expediente_imuh("8000063-I-2026; 8000064-I-2026 / 8000065-B-2024 ") == "8000063-I-2026, 8000064-I-2026, 8000065-B-2024"
    assert utils.normalizar_expediente_imuh("   ") is None
    assert utils.normalizar_expediente_imuh(None) is None
    
    # 3. Test mathematical consistency of grouped payment distribution
    # Let's create a decree, cuota, and two payments to verify aggregated distribution formulas
    d_group_id = db.add_decreto(7777, 2026, "8000063-I-2026, 8000064-I-2026", "Obra Grupo Test")
    cuota_g_id = db.add_cuota(d_group_id, 5, 2026, 1000000.0)
    
    # Register two payments
    p1_id = db.add_cobro(cuota_g_id, 300000.0, "2026-05-13")
    p2_id = db.add_cobro(cuota_g_id, 400000.0, "2026-05-15")
    
    # Distribute p1: 200k fin_orig, 50k reserve, 50k desvio
    db.upsert_distribucion(p1_id, 200000.0, 50000.0, "p1 dist")
    db.add_desvio(p1_id, "Pavimentación", 50000.0, "Préstamo obra", "2026-05-13")
    
    # Distribute p2: 150k fin_orig, 200k reserve, 50k desvio
    db.upsert_distribucion(p2_id, 150000.0, 200000.0, "p2 dist")
    db.add_desvio(p2_id, "Hidráulica", 50000.0, "Préstamo obra", "2026-05-15")
    
    # Now simulate the card aggregation logic from pages/7_Distribucion.py
    # Load the payments
    cobros_list = db.get_cobros_con_resumen_distribucion()
    group_cobros = [c for c in cobros_list if c['cuota_id'] == cuota_g_id]
    
    monto_total_cobrado = sum(c['monto'] for c in group_cobros)
    monto_total_fin_orig = sum(c['monto_fin_orig'] for c in group_cobros)
    monto_total_reserva = sum(c['monto_reserva'] for c in group_cobros)
    monto_total_desvios = sum(c['total_desvios'] for c in group_cobros)
    
    # Reserve uses and recoveries
    ru_fo_total = 0.0
    ru_other_total = 0.0
    recru_fo_total = 0.0
    recru_res_total = 0.0
    rec_fo_total_total = 0.0
    recru_sd_total = 0.0
    rec_sd_total_total = 0.0
    rec_desv_res_total_total = 0.0
    
    # Add a reserve use to p1: 30k used for fin_original
    db.add_reserva_uso(p1_id, 30000.0, "fin_original", "Uso Reserva", "2026-05-14", "Notas de uso")
    # Add a reserve use to p2: 100k to another_obra (desvio)
    res_uso_other_id = db.add_reserva_uso(p2_id, 100000.0, "otra_obra", "Uso Reserva 2", "2026-05-16", "Notas de uso 2")
    # Recover 40k from that reserve desvio back to fin_original
    db.add_reserva_uso_recupero(res_uso_other_id, 40000.0, "2026-05-17", "fin_original", notas="Recupero de reserva")
    
    # Re-calculate reserve usage and recoveries over the group
    for c_item in group_cobros:
        c_id = c_item['id']
        usos_r_inline = db.get_reserva_usos_by_cobro(c_id)
        ru_fo_total += sum(u['monto'] for u in usos_r_inline if u['destino_tipo'] == 'fin_original')
        ru_other_total += sum(u['monto'] for u in usos_r_inline if u['destino_tipo'] != 'fin_original')
        
        for u in usos_r_inline:
            if u['destino_tipo'] != 'fin_original':
                rec_usos_item = db.get_recuperos_by_reserva_uso(u['id'])
                for ri in rec_usos_item:
                    if ri['destino_tipo'] == 'fin_original':
                        recru_fo_total += ri['monto']
                    elif ri['destino_tipo'] == 'reserva':
                        recru_res_total += ri['monto']
                    elif ri['destino_tipo'] == 'sin_distribucion':
                        recru_sd_total += ri['monto']
                        
        desvios = db.get_desvios_by_cobro(c_id)
        for d in desvios:
            recuperos_del_desvio = db.get_recuperos_by_desvio(d['id'])
            for rec_item in recuperos_del_desvio:
                if rec_item['destino_tipo'] == 'fin_original':
                    rec_fo_total_total += rec_item['monto']
                elif rec_item['destino_tipo'] == 'sin_distribucion':
                    rec_sd_total_total += rec_item['monto']
                elif rec_item['destino_tipo'] == 'reserva':
                    rec_desv_res_total_total += rec_item['monto']
                    
    # Math formulas
    item_sin_dist = max(0.0, round(monto_total_cobrado - monto_total_fin_orig - monto_total_reserva - monto_total_desvios + rec_sd_total_total + recru_sd_total, 2))
    item_fin_orig = round(monto_total_fin_orig + ru_fo_total + rec_fo_total_total + recru_fo_total, 2)
    item_desvios = round(monto_total_desvios + ru_other_total - rec_fo_total_total - recru_fo_total - recru_res_total - rec_sd_total_total - recru_sd_total - rec_desv_res_total_total, 2)
    item_en_reserva = max(0.0, round(monto_total_reserva - ru_fo_total - ru_other_total + recru_res_total + rec_desv_res_total_total, 2))
    
    # Assert linear combination holds: Item 1 + Item 2 + Item 3 + Item 4 == Total Cobrado
    total_distributed_sum = round(item_sin_dist + item_fin_orig + item_desvios + item_en_reserva, 2)
    assert total_distributed_sum == monto_total_cobrado, f"Math inconsistency! {total_distributed_sum} != {monto_total_cobrado}"
    
    # 4. Test Funding Requests (Solicitudes de Financiamiento)
    # Add a new request
    sol_id = db.add_solicitud("OE-9999-I-2026", "8000063-I-2026, 8000064-I-2026", "Obra Vial Test", 1500000.0, "2026-05-21", "uploads/test.pdf", "Notas de prueba")
    
    # Retrieve it
    sol = db.get_solicitud(sol_id)
    assert sol is not None
    assert sol['nro_expediente'] == "OE-9999-I-2026"
    assert sol['expediente_imuh'] == "8000063-I-2026, 8000064-I-2026"
    assert sol['monto_solicitado'] == 1500000.0
    assert sol['estado'] == "Pendiente"
    assert sol['notas'] == "Notas de prueba"
    
    # Get all solicitudes
    all_sols = db.get_solicitudes()
    assert len(all_sols) >= 1
    assert any(s['id'] == sol_id for s in all_sols)
    
    # Edit the request
    db.update_solicitud(sol_id, "OE-9999-I-2026", "8000063-I-2026, 8000064-I-2026", "Obra Vial Test Editada", 1600000.0, "2026-05-21", "uploads/test.pdf", "Notas editadas")
    sol = db.get_solicitud(sol_id)
    assert sol['destino_fondos'] == "Obra Vial Test Editada"
    assert sol['monto_solicitado'] == 1600000.0
    assert sol['notas'] == "Notas editadas"
    
    # Approve and convert to a Decree
    d_conv_id = db.add_decreto(8888, 2026, "OE-9999-I-2026", "Obra Vial Test Editada", "uploads/test.pdf", "8000063-I-2026, 8000064-I-2026")
    
    # Link it and change state to Approved
    db.update_estado_solicitud(sol_id, "Aprobado", d_conv_id)
    sol = db.get_solicitud(sol_id)
    assert sol['estado'] == "Aprobado"
    assert sol['decreto_id'] == d_conv_id
    
    # Test reverse lookup
    sol_lookup = db.get_solicitud_por_decreto(d_conv_id)
    assert sol_lookup is not None
    assert sol_lookup['id'] == sol_id
    
    # Clean up request & decree
    db.delete_solicitud(sol_id)
    db.delete_decreto(d_conv_id)
    
    assert db.get_solicitud(sol_id) is None
    
    # Clean up
    try:
        db.delete_decreto(d_group_id)
        assert False, "Expected ValueError when deleting decree with cobros"
    except ValueError:
        pass
    
    # Remove temp DB
    if os.path.exists(TEMP_DB):
        try: os.remove(TEMP_DB)
        except: pass
        
    print("All backend logic, IMUH validations, and aggregated mathematical balance checks passed successfully.")

if __name__ == "__main__":
    run_tests()
