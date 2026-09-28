import sqlite3
import os

DB_PATH = 'decretometro.db'

def run_migration():
    print(f"Connecting to database: {DB_PATH}")
    if not os.path.exists(DB_PATH):
        print("Database file does not exist. Please run database.py first to initialize it.")
        return

    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON;")
    cursor = conn.cursor()

    # 1. Add nro_op column to existing tables if not present
    tables_to_update = [
        'cobro_desvios',
        'cobro_reserva_usos',
        'cobro_desvios_recuperos',
        'cobro_reserva_usos_recuperos'
    ]

    for table in tables_to_update:
        # Check columns
        cursor.execute(f"PRAGMA table_info({table})")
        columns = [row[1] for row in cursor.fetchall()]
        if 'nro_op' not in columns:
            print(f"Adding column 'nro_op' to table '{table}'...")
            try:
                cursor.execute(f"ALTER TABLE {table} ADD COLUMN nro_op TEXT")
                print(f"Column 'nro_op' added to table '{table}' successfully.")
            except Exception as e:
                print(f"Error adding column to '{table}': {e}")
        else:
            print(f"Column 'nro_op' already exists in table '{table}'.")

    # 2. Create cobro_fin_original_usos table
    print("Creating table 'cobro_fin_original_usos'...")
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS cobro_fin_original_usos (
            id                  INTEGER PRIMARY KEY AUTOINCREMENT,
            cobro_id            INTEGER NOT NULL,
            monto               REAL NOT NULL,
            fecha               DATE NOT NULL,
            nro_op              TEXT,
            notes               TEXT, -- naming column 'notes' or 'notas' to match schema? Let's check: cobro_reserva_usos has 'notas'
            notas               TEXT,
            FOREIGN KEY (cobro_id) REFERENCES cobros(id) ON DELETE CASCADE
        )
    ''')
    print("Table 'cobro_fin_original_usos' created or verified.")

    # 3. Migrate historical data
    # We select all distributions to Fin Original
    cursor.execute('''
        SELECT cd.cobro_id, cd.monto_fin_orig, c.fecha
        FROM cobro_distribuciones cd
        JOIN cobros c ON cd.cobro_id = c.id
        WHERE cd.monto_fin_orig > 0
    ''')
    distributions = cursor.fetchall()
    print(f"Found {len(distributions)} historical distributions to Fin Original.")

    migrated_count = 0
    for cobro_id, monto_fin_orig, fecha in distributions:
        # Check if we already migrated this cobro_id
        cursor.execute("SELECT id FROM cobro_fin_original_usos WHERE cobro_id = ?", (cobro_id,))
        exists = cursor.fetchone()
        if not exists:
            # Create a default usage record
            cursor.execute('''
                INSERT INTO cobro_fin_original_usos (cobro_id, monto, fecha, nro_op, notas)
                VALUES (?, ?, ?, NULL, 'Migrado automáticamente')
            ''', (cobro_id, monto_fin_orig, fecha))
            migrated_count += 1

    conn.commit()
    conn.close()
    print(f"Migration completed. Migrated {migrated_count} records to 'cobro_fin_original_usos'.")

if __name__ == '__main__':
    run_migration()
