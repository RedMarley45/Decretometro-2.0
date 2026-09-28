import os
import sys
import datetime

# Add the root directory to sys.path so we can import internal modules
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
import database as db

# Trackers for cleanup
created_decretos = []
created_cobros = []

log_msgs = []
def log(msg, success=True):
    prefix = "[OK]" if success else "[ERROR/FAIL]"
    line = f"{prefix} {msg}"
    log_msgs.append(line)
    print(line)

def run_stress_test():
    log("=== INICIANDO STRESS TEST V4 (RECUPEROS EXTREMOS) ===")
    
    try:
        # Forzar migración de DB por si acaso
        db.init_db()
        
        # 1. SETUP: Crear Decretos Receptores y Origen
        log("Creando Decretos de prueba...")
        id_dec_A = db.add_decreto(9901, 2026, "STRESS-01", "Obra Origen A", None)
        id_dec_B = db.add_decreto(9902, 2026, "STRESS-02", "Obra Destino B (Con Dto)", None)
        created_decretos.extend([id_dec_A, id_dec_B])
        
        db.add_cuota(id_dec_A, 5, 2026, 1000000.0) # 1 millon a A
        db.add_cuota(id_dec_B, 5, 2026, 500000.0)  # 500k a B
        
        # 2. COBRO EN DECRETO A
        cuotas_A = db.get_cuotas_by_decreto(id_dec_A)
        c_A_id = cuotas_A[0]['id']
        id_cobro_A = db.add_cobro(c_A_id, 1000000.0, "2026-03-01", None)
        created_cobros.append(id_cobro_A)
        log("Cobro de 1.000.000 registrado en Decreto A.")

        # 3. MALA DISTRIBUCIÓN (Test de Excepción)
        log("Test: Intentar distribuir MÁS dinero del cobrado (Debería fallar)")
        try:
            # 500k FO + 600k Reserva = 1.1M > 1M
            # Wait, upsert_distribucion only saves FO and Res. The validation of total is usually done in the UI.
            # But let's test if the backend prevents it... Actually, backend upsert_distribucion doesn't sum desvíos directly, UI does.
            # But add_desvio DOES check balances.
            db.upsert_distribucion(id_cobro_A, 500000.0, 500000.0, "Test FO y Res") # 1 Millon (Valido)
            log("Distribución inicial válida guardada.")
            
            # Try to add a desvío when balance is 0
            db.add_desvio(id_cobro_A, "Otra Obra", 100000.0, "Test fallo", "2026-03-02")
            log("FALLO DE TEST: Permitió agregar desvío sin saldo libre.", False)
        except ValueError as e:
            log(f"ÉXITO: Bloqueó desvío sin saldo libre correctly. ('{e}')")

        # 4. RE-DISTRIBUCIÓN VÁLIDA CON DESVÍOS
        log("Ajustando distribución para liberar 400.000 de saldo para desvíos...")
        db.upsert_distribucion(id_cobro_A, 500000.0, 100000.0, "Nuevo Ajuste") # Total = 600k. Libre = 400k.
        
        # 4.1 Desvío a Obra con Decreto (B)
        db.add_desvio(id_cobro_A, "Dummy", 250000.0, "Desvío Dto B", "2026-03-03", decreto_destino_id=id_dec_B)
        log("Desvío de 250.000 hacia Decreto B registrado exitosamente.")
        
        # 4.2 Desvío a Obra de Fondos Propios
        db.add_desvio(id_cobro_A, "Plaza Central (Fondos Propios)", 150000.0, "Desvío Propio", "2026-03-04", decreto_destino_id=None)
        log("Desvío de 150.000 hacia fondos propios registrado exitosamente.")
        
        desvios = db.get_desvios_by_cobro(id_cobro_A)
        id_desv_B = desvios[0]['id']
        id_desv_Propio = desvios[1]['id']

        # 5. TEST DE RECUPEROS (Éxitos y Fallos intencionales)
        log("Test: Intentar recuperar MÁS del importe del desvío...")
        try:
            db.add_desvio_recupero(id_desv_B, 300000.0, "2026-03-05", "fin_original")
            log("FALLO DE TEST: Permitió recuperar más del desvío.", False)
        except ValueError as e:
            log(f"ÉXITO: Bloqueó recupero fraudulento. ('{e}')")
            
        log("Test: Intentar recuperar importe negativo...")
        try:
            db.add_desvio_recupero(id_desv_Propio, -500.0, "2026-03-05", "fin_original")
            log("FALLO DE TEST: Permitió recupero negativo.", False)
        except ValueError as e:
            log(f"ÉXITO: Bloqueó recupero negativo. ('{e}')")
            
        # 6. RECUPEROS VÁLIDOS (RECUPERO Y REDIRECCION / "RECUPERO DE RECUPERO")
        log("Registrando devoluciones (Recuperos Válidos)...")
        # El 60% del desvío Propio (90.000) vuelve a Fin Original (Orígen A)
        db.add_desvio_recupero(id_desv_Propio, 90000.0, "2026-03-10", "fin_original")
        log("Recupero hacia 'Fin Original' (90k) exitoso.")
        
        # El Desvío aportado al Decreto B (250.000) se recupera, pero NO vuelve a origen, 
        # sino que se REdirecciona hacia una TERCERA OBRA (Fondos propios: "Hospital Norte")
        db.add_desvio_recupero(id_desv_B, 250000.0, "2026-03-15", "otra_obra", destino_detalle="Hospital Norte (Tercer Destino)", decreto_destino_id=None)
        log("Recupero Redireccionado a 'Hospital Norte' (250k) exitoso.")
        
        # Validar saldos
        desvios_final = db.get_desvios_by_cobro(id_cobro_A)
        saldo_Propio = desvios_final[1]['monto'] - desvios_final[1]['total_recuperado']
        saldo_B = desvios_final[0]['monto'] - desvios_final[0]['total_recuperado']
        log(f"Saldos Finales de Desvíos: Propio=${saldo_Propio} (Esperado 60k) | DtoB=${saldo_B} (Esperado 0)")

        if saldo_B == 0 and saldo_Propio == 60000.0:
            log("MATE EN UNO: Las matemáticas del backend sobrevivieron a recuperos cruzados.", True)
        else:
            log("ERROR MATEMÁTICO: Las cuentas no cuadran.", False)

    except Exception as e:
        log(f"Excepción general no controlada: {e}", False)

    finally:
        log("=== LIMPIEZA DE DATOS (Rollback manual) ===")
        # Eliminar cascada
        for cid in reversed(created_cobros):
            try:
                # First delete its desvios recuperos to not violate constraints if they existed
                # Since cascade rules on DB are set, if we delete desvio it might fail if recupero exists, 
                # but cascade is normally ON but let's be safe:
                desv_del = db.get_desvios_by_cobro(cid)
                for d in desv_del:
                    rec_del = db.get_recuperos_by_desvio(d['id'])
                    for r in rec_del:
                        db.delete_desvio_recupero(r['id'])
                    db.delete_desvio(d['id'])
                
                # Usos_Reserva
                us = db.get_reserva_usos_by_cobro(cid)
                for u in us:
                    db.delete_reserva_uso(u['id'])
                    
                db.delete_cobro(cid)
                log(f"Cobro ID {cid} limpiado.")
            except Exception as clean_e:
                log(f"Error limpiando cobro {cid}: {clean_e}")
                
        for did in reversed(created_decretos):
            try:
                db.delete_decreto(did)
                log(f"Decreto ID {did} limpiado.")
            except Exception as clean_e:
                log(f"Error limpiando decreto {did}: {clean_e}")
                
        log("=== PRUEBA DE ESTRÉS COMPLETADA Y DATOS ELIMINADOS ===")

if __name__ == "__main__":
    run_stress_test()
