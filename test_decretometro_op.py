import os
import sys
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
import database as db

TEMP_DB = 'test_temp_op.db'
if os.path.exists(TEMP_DB):
    try: os.remove(TEMP_DB)
    except: pass
db.DB_PATH = TEMP_DB
db.init_db()

def run_tests():
    print("Running OP and Payment Modification Tests...")
    
    # 1. Setup Decreto and Cuota
    d_id = db.add_decreto(5555, 2026, "TEST-EXP-OP", "Obra OP Test")
    c_id = db.add_cuota(d_id, 1, 2026, 100000.0)
    
    # 2. Add Cobro
    cobro_id = db.add_cobro(c_id, 100000.0, "2026-06-08")
    
    # 3. Distribute initially: 80k Fin Original, 20k Reserva
    db.upsert_distribucion(cobro_id, 80000.0, 20000.0, "Distribucion inicial")
    
    # 4. Register a payment to Fin Original (representing the 80k) with OP
    uso_fo_id = db.add_fin_original_uso(cobro_id, 80000.0, "2026-06-08", "OP-100", "Primer pago")
    
    # 5. Check it exists and contains OP
    usos_fo = db.get_fin_original_usos_by_cobro(cobro_id)
    assert len(usos_fo) == 1
    assert usos_fo[0]['monto'] == 80000.0
    assert usos_fo[0]['nro_op'] == "OP-100"
    
    # 6. Test update of Fin Original usage (modifying OP and notes)
    db.update_fin_original_uso(uso_fo_id, 80000.0, "2026-06-08", "OP-100-EDITED", "Primer pago editado")
    usos_fo = db.get_fin_original_usos_by_cobro(cobro_id)
    assert usos_fo[0]['nro_op'] == "OP-100-EDITED"
    assert usos_fo[0]['notas'] == "Primer pago editado"
    
    # 7. Test validation when editing Fin Original usage monto exceeds allocated
    try:
        db.update_fin_original_uso(uso_fo_id, 90000.0, "2026-06-08", "OP-100-EDITED", "Excedente")
        assert False, "Expected ValueError when exceeding budget"
    except ValueError as e:
        print("Success: Caught expected ValueError when exceeding Fin Original budget.")
        
    # 8. Test adding a desvio with OP
    # Currently, Fin Original (80k) + Reserva (20k) = 100k, so there is 0 free balance. Let's decrease Reserva to 10k so we have 10k free
    db.upsert_distribucion(cobro_id, 80000.0, 10000.0, "Distribucion editada")
    # Now we add a desvio of 10k since we have 10k free balance
    db.add_desvio(cobro_id, "Obras Viales", 10000.0, "Préstamo", "2026-06-08", nro_op="OP-DESV-200")
    
    desvios = db.get_desvios_by_cobro(cobro_id)
    assert len(desvios) == 1
    assert desvios[0]['monto'] == 10000.0
    assert desvios[0]['nro_op'] == "OP-DESV-200"
    
    # 9. Try updating desvio
    db.update_desvio(desvios[0]['id'], 5000.0, "Obras Viales", "Préstamo modificado", "2026-06-08", None, "OP-DESV-200-EDITED")
    desvios = db.get_desvios_by_cobro(cobro_id)
    assert desvios[0]['monto'] == 5000.0
    assert desvios[0]['nro_op'] == "OP-DESV-200-EDITED"
    
    # Clean up test DB
    if os.path.exists(TEMP_DB):
        try: os.remove(TEMP_DB)
        except: pass
        
    print("All OP and Payment Modification tests passed successfully!")

if __name__ == "__main__":
    run_tests()
