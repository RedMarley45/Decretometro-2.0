import sqlite3

def sync_decretos_obras():
    conn = sqlite3.connect('decretometro.db')
    c = conn.cursor()
    
    # Get all decrees with their expediente_imuh string
    c.execute("SELECT id, expediente_imuh FROM decretos WHERE expediente_imuh IS NOT NULL AND expediente_imuh != ''")
    decretos = c.fetchall()
    
    # Get all obras and their imuh codes
    c.execute("SELECT id, expediente_imuh FROM obras")
    obras = c.fetchall()
    obra_map = {row[1].strip(): row[0] for row in obras if row[1]}
    
    for dec_id, imuh_str in decretos:
        # Split by comma
        parts = [p.strip() for p in imuh_str.split(",")]
        
        # Check existing mappings
        c.execute("SELECT obra_id FROM decretos_obras WHERE decreto_id = ?", (dec_id,))
        existing = {row[0] for row in c.fetchall()}
        
        # Insert missing mappings
        for part in parts:
            if part in obra_map:
                oid = obra_map[part]
                if oid not in existing:
                    print(f"Adding missing mapping: Decreto {dec_id} -> Obra {oid} ({part})")
                    c.execute("INSERT OR IGNORE INTO decretos_obras (decreto_id, obra_id) VALUES (?, ?)", (dec_id, oid))
                    
    conn.commit()
    conn.close()
    print("Done syncing.")

if __name__ == '__main__':
    sync_decretos_obras()
