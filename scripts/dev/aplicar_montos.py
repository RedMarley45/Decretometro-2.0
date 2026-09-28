import sqlite3
import re
import os

md_file = r"C:\Users\bornemanns\.gemini\antigravity-ide\scratch\decretometro\Montos de obra\obras_sin_contrato.md"
backup_db = r"C:\Users\bornemanns\.gemini\antigravity-ide\scratch\decretometro\Montos de obra\obras_backup_15-09-2026_10-56.db"
decretometro_db = r"C:\Users\bornemanns\.gemini\antigravity-ide\scratch\decretometro\decretometro.db"

def main():
    # 1. Parse markdown
    expedientes_to_update = set()
    with open(md_file, 'r', encoding='utf-8') as f:
        for line in f:
            if line.startswith('|') and not line.startswith('| ID |') and not line.startswith('|---|'):
                parts = line.split('|')
                if len(parts) >= 3:
                    expediente = parts[2].strip()
                    expedientes_to_update.add(expediente)

    print(f"Encontrados {len(expedientes_to_update)} expedientes en el archivo markdown.")

    # 2. Get monto_contrato from backup
    montos_by_expediente = {}
    conn_b = sqlite3.connect(backup_db)
    cursor_b = conn_b.cursor()
    for exp in expedientes_to_update:
        cursor_b.execute("SELECT monto_contrato FROM obra WHERE nro_expediente = ?", (exp,))
        row = cursor_b.fetchone()
        if row:
            montos_by_expediente[exp] = row[0]
        else:
            print(f"ADVERTENCIA: No se encontró el expediente {exp} en la base de datos de respaldo.")
    conn_b.close()

    print(f"Se obtuvieron {len(montos_by_expediente)} montos de contrato de la base de datos de respaldo.")

    # 3. Update decretometro
    conn_d = sqlite3.connect(decretometro_db)
    cursor_d = conn_d.cursor()
    updated_count = 0
    for exp, monto in montos_by_expediente.items():
        cursor_d.execute("SELECT id FROM obras WHERE expediente_imuh = ?", (exp,))
        row = cursor_d.fetchone()
        if row:
            obra_id = row[0]
            cursor_d.execute("UPDATE obras SET monto_contrato = ? WHERE id = ?", (monto, obra_id))
            updated_count += 1
            print(f"Actualizado: {exp} -> ${monto:,.2f}")
        else:
            print(f"ADVERTENCIA: No se encontró el expediente {exp} en el decretómetro.")
    
    conn_d.commit()
    conn_d.close()
    
    print(f"\nFinalizado. Se actualizaron {updated_count} obras.")

if __name__ == "__main__":
    main()
