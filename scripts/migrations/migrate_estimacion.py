import sqlite3
import os

DB_PATH = 'decretometro.db'

def migrate():
    if not os.path.exists(DB_PATH):
        print(f"Error: {DB_PATH} not found.")
        return

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    try:
        print("Añadiendo columna 'fecha_estimada_cobro' a la tabla 'cuotas'...")
        cursor.execute("ALTER TABLE cuotas ADD COLUMN fecha_estimada_cobro DATE")
        conn.commit()
        print("Migración completada con éxito.")
    except sqlite3.OperationalError as e:
        if "duplicate column name" in str(e).lower():
            print("La columna ya existe. No se requiere migración.")
        else:
            print(f"Error durante la migración: {e}")
    except Exception as e:
        print(f"Error inesperado: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    migrate()
