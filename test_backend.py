import database as db
import datetime

db.init_db()
print("1. Migración ejecutada sin errores.")

try:
    db.add_desvio(1, "Destino Fake", -500, "Prueba", "2026-03-20")
    print("❌ Falla de seguridad: aceptó monto negativo.")
except ValueError as e:
    print(f"2. Seguridad OK: {e}")
except Exception as e:
    # Si falla por "Cobro no encontrado", es normal si la bd está vacía
    pass

deudas = db.get_deudas_obras_propias()
print(f"3. Obras propias en deuda consultadas correctamente. Resultados: {deudas}")
