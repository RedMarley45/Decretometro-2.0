import os
import sys

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

import database as db
import utils
import utils_reports

def run_tests():
    print("--- INICIANDO PRUEBAS DE PROVEEDORES ---")
    
    # 1. Inicializar DB
    db.init_db()
    print("[OK] init_db() completado correctamente.")
    
    # 2. Probar validación CUIT AFIP en utils.py
    assert utils.validar_cuit("20-12345678-6") == True, "CUIT 20-12345678-6 deberia ser valido"
    assert utils.validar_cuit("30-71111111-2") == False, "CUIT con digito verificador erroneo deberia ser invalido"
    assert utils.validar_cuit("123456789") == False, "CUIT sin guiones debe ser invalido"
    assert utils.validar_cuit("20-123456-9") == False, "CUIT con menos digitos debe ser invalido"
    print("[OK] Pruebas de validar_cuit() pasaron.")

    # 3. Alta de proveedor de obra y funcionamiento con CUIT válido
    cuit1 = "20-12345678-6"
    cuit2 = "30-98765432-1"
    
    # Limpiar test data previos si existen
    with db.db_session() as conn:
        conn.execute("UPDATE obras SET proveedor_id = NULL WHERE proveedor_id IN (SELECT id FROM proveedores_obras WHERE razon_social IN ('Test Obra SA', 'Test Obra 2 SA'))")
        conn.execute("UPDATE gastos_funcionamiento SET proveedor_id = NULL WHERE proveedor_id IN (SELECT id FROM proveedores_funcionamiento WHERE razon_social IN ('Test FUN SRL', 'Test FUN 2 SRL', 'Test Obra SA'))")
        conn.commit()

    provs_obras = db.get_proveedores_obras()
    for p in provs_obras:
        if p['razon_social'] in ["Test Obra SA", "Test Obra 2 SA"]:
            try:
                db.delete_proveedor_obra(p['id'])
            except:
                pass
                
    provs_fun = db.get_proveedores_funcionamiento()
    for p in provs_fun:
        if p['razon_social'] in ["Test FUN SRL", "Test FUN 2 SRL", "Test Obra SA"]:
            try:
                db.delete_proveedor_funcionamiento(p['id'])
            except:
                pass

    p_obra_id = db.add_proveedor_obra("Test Obra SA", cuit1)
    print(f"[OK] Creado Proveedor Obra ID {p_obra_id}")
    
    p_fun_id = db.add_proveedor_funcionamiento("Test FUN SRL", cuit2)
    print(f"[OK] Creado Proveedor FUN ID {p_fun_id}")

    # 4. Probar Opción A: Unicidad por tipo (mismo CUIT en Proveedor FUN debe ser aceptado)
    p_fun_mismo_cuit_id = db.add_proveedor_funcionamiento("Test Obra SA", cuit1)
    print(f"[OK] Opcion A verificada: CUIT {cuit1} registrado independientemente en Funcionamiento (ID {p_fun_mismo_cuit_id}).")

    # 5. Probar error por duplicado dentro del mismo tipo
    try:
        db.add_proveedor_obra("Test Obra SA Duplicada", cuit1)
        assert False, "Debería haber fallado por CUIT duplicado en Obras"
    except ValueError as e:
        print(f"[OK] Capturado error esperado de CUIT duplicado en Obras: {e}")

    # 6. Asignar proveedor a Obra
    obras = db.get_obras()
    if obras:
        o = obras[0]
        db.update_obra(o['id'], o['nombre'], o['expediente_imuh'], o['activa'], p_obra_id)
        o_actualizada = db.get_obra(o['id'])
        assert o_actualizada['proveedor_id'] == p_obra_id, "El proveedor_id de la obra debe coincidir"
        assert o_actualizada['proveedor_razon_social'] == "Test Obra SA", "La razón social traída debe coincidir"
        print(f"[OK] Asignacion de proveedor {p_obra_id} a Obra '{o['nombre']}' exitosa.")
        
        # 7. Verificar bloqueo de eliminación
        try:
            db.delete_proveedor_obra(p_obra_id)
            assert False, "Debería haber bloqueado la eliminación del proveedor vinculado a obra"
        except ValueError as e:
            print(f"[OK] Bloqueo de eliminacion verificado: {e}")

    # 8. Asignar proveedor a Gasto FUN
    gastos_fun = db.get_gastos_funcionamiento()
    if gastos_fun:
        g = gastos_fun[0]
        db.update_gasto_funcionamiento_proveedor(g['id'], p_fun_id)
        g_actualizado = db.get_gasto_funcionamiento(g['id'])
        assert g_actualizado['proveedor_id'] == p_fun_id, "El proveedor_id del gasto FUN debe coincidir"
        assert g_actualizado['proveedor_razon_social'] == "Test FUN SRL", "La razón social traída del gasto FUN debe coincidir"
        print(f"[OK] Asignacion de proveedor {p_fun_id} a Gasto FUN '{g['nombre']}' exitosa.")

    # 9. Probar Afectación de Decretos
    decretos = db.get_decretos()
    if decretos:
        dec, cuotas_list, filas_reporte = utils_reports.obtener_afectacion_decreto(decretos[0]['id'])
        if filas_reporte:
            assert "Proveedor" in filas_reporte[0], "La clave 'Proveedor' debe estar presente en filas_reporte"
            print(f"[OK] Reporte de afectacion de decretos contiene la columna Proveedor: Ejemplo = '{filas_reporte[0]['Proveedor']}'")

    # Tear down test data
    with db.db_session() as conn:
        conn.execute("UPDATE obras SET proveedor_id = NULL WHERE proveedor_id IN (SELECT id FROM proveedores_obras WHERE razon_social IN ('Test Obra SA', 'Test Obra 2 SA'))")
        conn.execute("UPDATE gastos_funcionamiento SET proveedor_id = NULL WHERE proveedor_id IN (SELECT id FROM proveedores_funcionamiento WHERE razon_social IN ('Test FUN SRL', 'Test FUN 2 SRL', 'Test Obra SA'))")
        conn.execute("DELETE FROM proveedores_obras WHERE razon_social IN ('Test Obra SA', 'Test Obra 2 SA')")
        conn.execute("DELETE FROM proveedores_funcionamiento WHERE razon_social IN ('Test FUN SRL', 'Test FUN 2 SRL', 'Test Obra SA')")
        conn.commit()

    print("\n--- TODAS LAS PRUEBAS DE VERIFICACION PASARON CON EXITO ---")

if __name__ == '__main__':
    run_tests()
