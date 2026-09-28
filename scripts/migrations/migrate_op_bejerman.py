import sqlite3
import re
from database import get_connection, init_db

def clean_op(nro_op):
    if not nro_op:
        return None
    # Keep only digits
    cleaned = re.sub(r'\D', '', str(nro_op))
    return cleaned if cleaned else None

def migrate_ops():
    # Ensure DB is initialized to latest version (schema 32)
    init_db()
    
    with get_connection() as conn:
        cursor = conn.cursor()
        
        # We will iterate over all 4 tables that have nro_op
        tables = [
            "cobro_fin_original_usos",
            "cobro_desvios",
            "cobro_desvios_recuperos",
            "cobro_reserva_usos_recuperos"
        ]
        
        for table in tables:
            # 1. Clean existing nro_op in the table
            cursor.execute(f"SELECT id, nro_op FROM {table} WHERE nro_op IS NOT NULL AND nro_op != ''")
            rows = cursor.fetchall()
            for r in rows:
                cleaned = clean_op(r['nro_op'])
                if cleaned != r['nro_op']:
                    cursor.execute(f"UPDATE {table} SET nro_op = ? WHERE id = ?", (cleaned, r['id']))
        
        conn.commit()
        
        # 2. Extract unique OPs and their obra_id / gasto_id
        op_map = {} # nro_op -> {'obra_id': x, 'gasto_id': y}
        
        # From cobro_fin_original_usos
        cursor.execute("SELECT nro_op, obra_id, gasto_expediente_imuh FROM cobro_fin_original_usos WHERE nro_op IS NOT NULL AND nro_op != ''")
        for r in cursor.fetchall():
            op = r['nro_op']
            if op not in op_map:
                op_map[op] = {'obra_id': None, 'gasto_id': None}
            if r['obra_id'] and not op_map[op]['obra_id']:
                op_map[op]['obra_id'] = r['obra_id']
            if r['gasto_expediente_imuh'] and not op_map[op]['gasto_id']:
                # Lookup gasto_id
                cursor.execute("SELECT id FROM gastos_funcionamiento WHERE expediente_imuh = ?", (r['gasto_expediente_imuh'],))
                g_row = cursor.fetchone()
                if g_row:
                    op_map[op]['gasto_id'] = g_row['id']
                    
        # From cobro_desvios
        # First check if cobro_desvios has obra_id and gasto_expediente_imuh
        cursor.execute("PRAGMA table_info(cobro_desvios)")
        cols = [c['name'] for c in cursor.fetchall()]
        if 'obra_id' in cols and 'gasto_expediente_imuh' in cols:
            cursor.execute("SELECT nro_op, obra_id, gasto_expediente_imuh FROM cobro_desvios WHERE nro_op IS NOT NULL AND nro_op != ''")
            for r in cursor.fetchall():
                op = r['nro_op']
                if op not in op_map:
                    op_map[op] = {'obra_id': None, 'gasto_id': None}
                if r['obra_id'] and not op_map[op]['obra_id']:
                    op_map[op]['obra_id'] = r['obra_id']
                if r['gasto_expediente_imuh'] and not op_map[op]['gasto_id']:
                    cursor.execute("SELECT id FROM gastos_funcionamiento WHERE expediente_imuh = ?", (r['gasto_expediente_imuh'],))
                    g_row = cursor.fetchone()
                    if g_row:
                        op_map[op]['gasto_id'] = g_row['id']
        else:
            # Maybe fallback to getting everything just as keys
            cursor.execute("SELECT nro_op FROM cobro_desvios WHERE nro_op IS NOT NULL AND nro_op != ''")
            for r in cursor.fetchall():
                op = r['nro_op']
                if op not in op_map:
                    op_map[op] = {'obra_id': None, 'gasto_id': None}
                    
        # For recuperos, just add the OP if not exists
        for table in ["cobro_desvios_recuperos", "cobro_reserva_usos_recuperos"]:
            cursor.execute(f"SELECT nro_op FROM {table} WHERE nro_op IS NOT NULL AND nro_op != ''")
            for r in cursor.fetchall():
                op = r['nro_op']
                if op not in op_map:
                    op_map[op] = {'obra_id': None, 'gasto_id': None}
                    
        # 3. Insert into op_bejerman
        for op, data in op_map.items():
            cursor.execute("SELECT 1 FROM op_bejerman WHERE nro_op = ?", (op,))
            if not cursor.fetchone():
                cursor.execute("INSERT INTO op_bejerman (nro_op, obra_id, gasto_id) VALUES (?, ?, ?)", 
                               (op, data['obra_id'], data['gasto_id']))
            else:
                # Update if missing
                cursor.execute("UPDATE op_bejerman SET obra_id = COALESCE(obra_id, ?), gasto_id = COALESCE(gasto_id, ?) WHERE nro_op = ?",
                               (data['obra_id'], data['gasto_id'], op))
                
        conn.commit()
        print(f"Migrated {len(op_map)} unique OPs to op_bejerman.")

if __name__ == "__main__":
    migrate_ops()
