import unittest
import os
import sys

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
import database as db
import utils

class TestFunCatalog(unittest.TestCase):
    def setUp(self):
        # We work directly on the test database or connection
        pass
        
    def test_gasto_fun_flow(self):
        # 1. Add Gasto FUN
        nombre_test = "Gasto Test Unitario FUN"
        expediente_test = "8009999-I-2026"
        
        # Clean up if exists from previous crashed runs
        with db.db_session() as conn:
            cursor = conn.cursor()
            cursor.execute('DELETE FROM gastos_funcionamiento WHERE expediente_imuh = ?', (expediente_test,))
            conn.commit()
            
        gasto_id = db.add_gasto_funcionamiento(nombre_test, expediente_test)
        self.assertIsNotNone(gasto_id)
        
        # 2. Get and verify
        g_fun = db.get_gasto_funcionamiento(gasto_id)
        self.assertEqual(g_fun['nombre'], nombre_test)
        self.assertEqual(g_fun['expediente_imuh'], expediente_test)
        self.assertEqual(g_fun['activo'], 1)
        
        # 3. Retrieve list and verify it is there
        active_list = db.get_gastos_funcionamiento(only_active=True)
        self.assertTrue(any(g['id'] == gasto_id for g in active_list))
        
        # 4. Inactivate Gasto
        db.update_gasto_funcionamiento_estado(gasto_id, 0)
        g_fun_inactive = db.get_gasto_funcionamiento(gasto_id)
        self.assertEqual(g_fun_inactive['activo'], 0)
        
        # 5. Verify it's no longer in active list, but remains in full list
        active_list_after = db.get_gastos_funcionamiento(only_active=True)
        self.assertFalse(any(g['id'] == gasto_id for g in active_list_after))
        
        all_list = db.get_gastos_funcionamiento(only_active=False)
        self.assertTrue(any(g['id'] == gasto_id for g in all_list))
        
        # 6. Reactivate by adding again (duplicate handling reactivates)
        new_id = db.add_gasto_funcionamiento("Gasto Test Unitario FUN Reactivado", expediente_test)
        self.assertEqual(new_id, gasto_id)
        
        g_fun_active = db.get_gasto_funcionamiento(gasto_id)
        self.assertEqual(g_fun_active['activo'], 1)
        self.assertEqual(g_fun_active['nombre'], "Gasto Test Unitario FUN Reactivado")
        
        # Clean up
        with db.db_session() as conn:
            cursor = conn.cursor()
            cursor.execute('DELETE FROM gastos_funcionamiento WHERE id = ?', (gasto_id,))
            conn.commit()

if __name__ == '__main__':
    unittest.main()
