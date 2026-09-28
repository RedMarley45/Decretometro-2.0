import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
import database as db

def test_sac():
    print("Iniciando prueba de lógica SAC...")
    
    # 1. Agregar pedido
    db.add_aporte_sac(2026, 1, 50000, "2026-05-01")
    sacs = db.get_aportes_sac(2026)
    assert len(sacs) > 0, "No se encontró el pedido de SAC"
    sac = [s for s in sacs if s['monto_pedido'] == 50000][0]
    assert sac['cuota_nro'] == 1
    assert sac['monto_pedido'] == 50000
    assert sac['monto_cobrado'] == 0
    print("- Creación de pedido exitosa.")

    # 2. Registrar cobro
    db.registrar_cobro_sac(sac['id'], 50000, "2026-05-15")
    sac_cobrado = [s for s in db.get_aportes_sac(2026) if s['id'] == sac['id']][0]
    assert sac_cobrado['monto_cobrado'] == 50000
    assert sac_cobrado['fecha_cobro'] == "2026-05-15"
    print("- Registro de cobro exitoso.")

    # 3. Actualizar
    db.update_aporte_sac(sac['id'], 2026, 1, 55000, "2026-05-02")
    sac_upd = [s for s in db.get_aportes_sac(2026) if s['id'] == sac['id']][0]
    assert sac_upd['monto_pedido'] == 55000
    print("- Actualización exitosa.")

    # 4. Eliminar
    db.delete_aporte_sac(sac['id'])
    sacs_post = [s for s in db.get_aportes_sac(2026) if s['id'] == sac['id']]
    assert len(sacs_post) == 0, "El pedido no se eliminó"
    print("- Eliminación exitosa.")

    print("Todas las pruebas de lógica SAC pasaron correctamente.")

if __name__ == "__main__":
    test_sac()
