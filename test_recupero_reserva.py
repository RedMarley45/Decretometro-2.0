import os
import database as db

def run_tests():
    # Redirigir a una base de datos temporal
    TEMP_DB = 'test_temp.db'
    if os.path.exists(TEMP_DB):
        os.remove(TEMP_DB)

    db.DB_PATH = TEMP_DB
    db.init_db()

    print("1. Base de datos de prueba inicializada.")

    # Crear datos de prueba
    # 1. Decreto origen
    dec_orig_id = db.add_decreto(272, 2026, "EXP-272/2026", "Obras Hidricas")
    print(f"   Decreto Origen creado con ID: {dec_orig_id}")

    # 2. Decreto destino
    dec_dest_id = db.add_decreto(296, 2026, "EXP-296/2026", "Pavimentacion Calle Mitre")
    print(f"   Decreto Destino creado con ID: {dec_dest_id}")

    # 3. Cuota y Cobro
    cuota_id = db.add_cuota(dec_orig_id, 5, 2026, 1000000.0)
    cobro_id = db.add_cobro(cuota_id, 1000000.0, "2026-05-15")
    print(f"   Cuota ({cuota_id}) y Cobro ({cobro_id}) creados.")

    # 4. Distribución: Poner 300,000 en Reserva y 700,000 en Fin Original
    db.upsert_distribucion(cobro_id, 700000.0, 300000.0, "Distribucion inicial de prueba")
    print("   Distribución cargada: 700k Fin Original, 300k Reserva.")

    # 5. Desviar dinero de la reserva (préstamo) a otra obra
    # Prestamo 1: A Obra Pavimentación Mitre (Decreto) -> $200,000
    db.add_reserva_uso(cobro_id, 200000.0, "otra_obra", "Pavimentacion Mitre", "2026-05-16", "Prestamo reserva 1", decreto_destino_id=dec_dest_id)
    print("   Uso de Reserva (Préstamo) registrado: 200k a Pavimentacion Mitre (con decreto).")

    # Prestamo 2: A Obra Propedias (Fondos Propios) -> $50,000
    db.add_reserva_uso(cobro_id, 50000.0, "otra_obra", "Refaccion Polideportivo", "2026-05-17", "Prestamo reserva 2")
    print("   Uso de Reserva (Préstamo) registrado: 50k a Refaccion Polideportivo (sin decreto).")

    # Verificar préstamos activos
    activos = db.get_reserva_usos_prestamos_activos()
    print(f"\n2. Préstamos activos iniciales (Esperados: 2): {len(activos)}")
    for a in activos:
        print(f"   - ID: {a['id']}, Destino: {a['destino_detalle'] or a['dest_nombre']}, Monto: {a['monto']}, Saldo: {a['saldo']}")

    # Verificar deudas de obras de fondos propios
    deudas_propias = db.get_deudas_obras_propias()
    print(f"\n3. Deudas de obras de fondos propios (Esperado: 1): {deudas_propias}")

    # Registrar recupero parcial del Préstamo 1 (Mitre): $80,000 a Fin Original
    prestamo_mitre = [a for a in activos if a['decreto_destino_id'] == dec_dest_id][0]
    db.add_reserva_uso_recupero(prestamo_mitre['id'], 80000.0, "2026-05-20", "fin_original", notas="Recupero de Mitre")
    print(f"\n4. Recupero de $80,000 registrado para Préstamo {prestamo_mitre['id']} (Destino: Fin original).")

    # Registrar recupero parcial del Préstamo 2 (Polideportivo): $50,000 a Reserva (Cancela deuda)
    prestamo_poli = [a for a in activos if a['decreto_destino_id'] is None][0]
    db.add_reserva_uso_recupero(prestamo_poli['id'], 50000.0, "2026-05-21", "reserva", notas="Recupero de Poli")
    print(f"5. Recupero de $50,000 registrado para Préstamo {prestamo_poli['id']} (Destino: Reserva).")

    # Volver a verificar activos
    activos_despues = db.get_reserva_usos_prestamos_activos()
    print(f"\n6. Préstamos activos después (Esperado: 1 - Poli debe desaparecer): {len(activos_despues)}")
    for a in activos_despues:
        print(f"   - ID: {a['id']}, Destino: {a['destino_detalle'] or a['dest_nombre']}, Monto: {a['monto']}, Saldo: {a['saldo']} (Esperado: 120000)")

    # Verificar deudas de fondos propios nuevamente
    deudas_propias_despues = db.get_deudas_obras_propias()
    print(f"\n7. Deudas de fondos propios después (Esperado: vacío/0): {deudas_propias_despues}")

    # Verificar historial de desvíos
    historial = db.get_historial_desvios()
    print(f"\n8. Historial de desvíos (Esperado: 2 items): {len(historial)}")
    for h in historial:
        print(f"   - Tipo: {h['tipo_origen']}, Monto: {h['monto']}, Recuperado: {h['total_recuperado']}, Saldo: {h['saldo']}")

    # Verificar deudas por decreto
    deuda_dec = db.get_deuda_desvios_by_decreto(dec_dest_id)
    print(f"\n9. Deuda del Decreto Destino ({dec_dest_id}) (Esperado: 120,000): {deuda_dec}")

    # Limpieza
    os.remove(TEMP_DB)
    print("\n10. Base de datos de prueba eliminada. Test finalizado exitosamente!")

if __name__ == "__main__":
    run_tests()
