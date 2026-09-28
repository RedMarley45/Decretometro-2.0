import sqlite3
import os

DB_PATH = 'c:\\Users\\bornemanns\\.gemini\\antigravity\\scratch\\decretometro\\decretometro.db'
UPLOADS_DIR = 'c:\\Users\\bornemanns\\.gemini\\antigravity\\scratch\\decretometro\\uploads'

def clean_db():
    print("WARNING: Estás a punto de borrar los datos de la base de datos de producción/desarrollo.")
    respuesta = input("¿Estás seguro de continuar? (escribe 'SI' para proceder): ")
    if respuesta != 'SI':
        print("Operación cancelada.")
        return
        
    print("Cleaning database...")
    if os.path.exists(DB_PATH):
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        # Disable foreign keys temporarily to avoid issues while deleting if needed, 
        # though TRUNCATE/DELETE should work fine if done in order.
        # But here we just want to clear everything.
        tables = ['cobros', 'cuotas', 'decretos', 'aportes_funcionamiento', 'aportes_sueldo']
        for table in tables:
            try:
                cursor.execute(f"DELETE FROM {table}")
                print(f"Cleared table: {table}")
            except sqlite3.OperationalError as e:
                print(f"Table {table} does not exist or error: {e}")
        
        conn.commit()
        conn.close()
        print("Database tables cleared.")
    else:
        print("Database file not found.")

    print("Cleaning uploads directory...")
    if os.path.exists(UPLOADS_DIR):
        for root, dirs, files in os.walk(UPLOADS_DIR):
            for file in files:
                file_path = os.path.join(root, file)
                try:
                    os.remove(file_path)
                    print(f"Removed file: {file_path}")
                except Exception as e:
                    print(f"Error removing file {file_path}: {e}")
    else:
        print("Uploads directory not found.")

if __name__ == '__main__':
    clean_db()
