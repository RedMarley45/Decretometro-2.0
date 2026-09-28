import sqlite3
import pandas as pd
import shutil
import os
import sys

sys.stdout.reconfigure(encoding='utf-8')

p1_dir = r"c:\Users\bornemanns\.gemini\antigravity-ide\scratch\decretometro"
p2_dir = r"c:\Users\bornemanns\.gemini\antigravity\scratch\decretometro"

p1_db = os.path.join(p1_dir, "decretometro.db")
p2_db = os.path.join(p2_dir, "decretometro.db")

csv_path = os.path.join(p1_dir, "Asignación de obras.csv")

conn = sqlite3.connect(p1_db)
conn.row_factory = sqlite3.Row
cursor = conn.cursor()

# Ensure nro_op exists on cobro_desvios_recuperos to avoid migration error if init_db is called
try:
    cursor.execute("ALTER TABLE cobro_desvios_recuperos ADD COLUMN nro_op TEXT")
    conn.commit()
except Exception:
    pass

# Load CSV
df_csv = pd.read_csv(csv_path, sep=';')

# Load Obras map
cursor.execute("SELECT id, expediente_imuh, nombre FROM obras")
obras_map = {r['expediente_imuh']: dict(r) for r in cursor.fetchall()}

# Load cobro_fin_original_usos unassigned records
query = """
SELECT 
    fu.id as uso_id,
    c.id as cobro_id,
    d.nro_decreto || '/' || d.anio as decreto_str,
    fu.fecha as fecha_uso,
    fu.monto as monto_uso
FROM cobro_fin_original_usos fu
JOIN cobros c ON fu.cobro_id = c.id
JOIN cuotas q ON c.cuota_id = q.id
JOIN decretos d ON q.decreto_id = d.id
WHERE fu.obra_id IS NULL
ORDER BY fu.fecha DESC, d.anio DESC, d.nro_decreto DESC
"""

cursor.execute(query)
db_records = [dict(r) for r in cursor.fetchall()]
print(f"\n2. Registros pendientes en cobro_fin_original_usos en la BD: {len(db_records)}")

used_uso_ids = set()
updated_count = 0

print("\n3. Procesando las 40 filas del CSV...")
for idx, row in df_csv.iterrows():
    line_num = idx + 2
    dec_str = str(row['Decreto']).strip()
    fecha_str = str(row['Fecha de Pago']).strip()
    monto_str = str(row['Monto']).strip().replace('$', '').replace('.', '').replace(',', '.').strip()
    monto_val = float(monto_str) if monto_str else 0.0
    op_str = str(row['Nro. OP']).strip()
    exp_imuh = str(row['Expediente IMUH de la obra o gasto de funcionamiento']).strip()
    extra_op = str(row.get('Unnamed: 5')).strip() if pd.notna(row.get('Unnamed: 5')) else ""

    # OP selection logic
    if line_num == 20:
        final_op = "3504/3505"
    elif line_num == 23:
        final_op = "3464"
    elif extra_op:
        final_op = extra_op
    else:
        final_op = op_str

    obra_info = obras_map.get(exp_imuh)
    if not obra_info:
        raise ValueError(f"Línea {line_num}: Expediente IMUH {exp_imuh} no encontrado en tabla obras.")

    obra_id = obra_info['id']

    # Match db record
    matched_rec = None
    for rec in db_records:
        if rec['uso_id'] in used_uso_ids:
            continue
        if rec['decreto_str'] == dec_str and abs(rec['monto_uso'] - monto_val) < 0.05:
            matched_rec = rec
            break

    if not matched_rec:
        raise ValueError(f"Línea {line_num}: No se encontró registro coincidente en BD para {dec_str} por ${monto_val}.")

    uso_id = matched_rec['uso_id']
    used_uso_ids.add(uso_id)

    # Perform UPDATE
    cursor.execute("""
        UPDATE cobro_fin_original_usos
        SET obra_id = ?, nro_op = ?
        WHERE id = ?
    """, (obra_id, final_op, uso_id))

    updated_count += 1
    print(f"   [✓] Línea {line_num:2d} | Dec {dec_str:8s} | Monto ${monto_val:14,.2f} | OP: {final_op:12s} -> Obra ID {obra_id:2d} ({exp_imuh}) [uso_id={uso_id}]")

conn.commit()
print(f"\n4. ¡Actualización masiva completada! Registros actualizados: {updated_count}")

# Verification
cursor.execute("SELECT COUNT(*) FROM cobro_fin_original_usos WHERE obra_id IS NULL")
pending_remaining = cursor.fetchone()[0]
print(f"\n5. Control final: Registros en cobro_fin_original_usos sin obra asignada: {pending_remaining}")

if pending_remaining == 0:
    print("-> VERIFICACIÓN EXITOSA: 100% de los pagos tienen obra asignada.")
else:
    print(f"-> ADVERTENCIA: Aún quedan {pending_remaining} registros sin obra asignada.")

conn.close()
