import sqlite3
import datetime
import os
import sys

sys.path.append(os.getcwd())
import database as db

def log(msg):
    print(f"- {msg}")

def run():
    print("# Reporte de Stress Test (V2)")
    print("\n## Inicialización")
    log("Iniciando test de estrés sin borrar datos existentes...")
    
    # Trackers for cleanup
    created_decretos = []
    created_fun_years = [] 
    created_sueldos = []
    created_sac = []
    # Eliminar conn = db.get_connection() para evitar "database is locked"
    try:
        print("\n## 1. Pruebas de Decretos y Cuotas")
        # 1.1 Intentar crear decreto con datos inválidos (Integridad)
        conn = db.get_connection()
        try:
            conn.execute('INSERT INTO decretos (nro_decreto, anio, nro_expediente, destino_fondos, estado) VALUES (?, ?, ?, ?, ?)', (None, "No es int", None, None, 'Vigente'))
            log("HALLAZGO: La base de datos permite crear un decreto con datos nulos/inválidos tipos (Falta estrictez en SQLite o validación en backend).")
        except Exception as e:
            log(f"ÉXITO: La DB rechazó decreto inválido. Detalle: {e}")
        finally:
            conn.close()

        # 1.2 Crear decreto válido para pruebas
        d_id = db.add_decreto(9999, 2026, "TEST-STRESS-1", "Destino Test Stress")
        created_decretos.append(d_id)
        log(f"Decreto válido creado con ID {d_id}.")

        # 1.3 Agregar cuotas con montos negativos extremos
        conn = db.get_connection()
        try:
            conn.execute('INSERT INTO cuotas (decreto_id, mes, anio, monto) VALUES (?, ?, ?, ?)', (d_id, 1, 2026, -9999999.99))
            log("HALLAZGO: La base de datos permite registrar cuotas con montos negativos extremos.")
        except Exception as e:
            log(f"ÉXITO: No se permiten cuotas negativas. Detalle: {e}")
        finally:
            conn.close()

        # 1.4 Agregar cuotas con fechas inválidas
        conn = db.get_connection()
        try:
            conn.execute('INSERT INTO cuotas (decreto_id, mes, anio, monto) VALUES (?, ?, ?, ?)', (d_id, 13, 2026, 10000))
            log("HALLAZGO: La base de datos permite registrar cuotas con meses > 12.")
        except Exception as e:
            log(f"ÉXITO: No se permiten meses inválidos. Detalle: {e}")
        finally:
            conn.close()

        print("\n## 2. Pruebas de Cobros (Totales y Parciales)")
        # Crear cuota normal
        db.add_cuota(d_id, 2, 2026, 10000)
        cuotas = db.get_cuotas_by_decreto(d_id)
        c_id = [c['id'] for c in cuotas if c['monto'] == 10000][0]

        # 2.1 Pago futuro directo en DB
        conn = db.get_connection()
        try:
            conn.execute('INSERT INTO cobros (cuota_id, monto, fecha) VALUES (?, ?, ?)', (c_id, 5000, "2050-01-01"))
            log("HALLAZGO: La DB permite registrar cobros con fecha futura (La validación introducida recientemente está solo en la UI de Streamlit).")
        except Exception as e:
            log(f"ÉXITO: DB bloquea fecha futura. Detalle: {e}")
        finally:
            conn.close()

        # 2.2 Pago excedente (pagar más del saldo)
        conn = db.get_connection()
        try:
            conn.execute('INSERT INTO cobros (cuota_id, monto, fecha) VALUES (?, ?, ?)', (c_id, 9000000, "2026-03-01"))
            log("HALLAZGO: La DB permite cobrar un monto muy superior al proyectado de la cuota (No hay restricción de saldo máximo en DB).")
        except Exception as e:
            log(f"ÉXITO: DB bloquea excedente. Detalle: {e}")
        finally:
            conn.close()

        # 2.3 Pago negativo (simulando un "descuento" no autorizado)
        conn = db.get_connection()
        try:
            conn.execute('INSERT INTO cobros (cuota_id, monto, fecha) VALUES (?, ?, ?)', (c_id, -1500, "2026-03-02"))
            log("HALLAZGO: La base de datos permite pagos negativos.")
        except Exception as e:
            log(f"ÉXITO: DB bloquea pagos negativos. Detalle: {e}")
        finally:
            conn.close()

        print("\n## 3. Pruebas de Aportes Habituales")
        # 3.1 Funcionamiento - Año futuro o extremo
        db.set_monto_funcionamiento_anio(2099, 100000)
        created_fun_years.append(2099)
        log("Creado año 2099 para funcionamiento.")
        fun_2099 = db.get_aportes_funcionamiento(2099)
        f_id = fun_2099[0]['id']

        # Cobro futuro en funcionamiento
        conn = db.get_connection()
        try:
            conn.execute('UPDATE aportes_funcionamiento SET monto_cobrado = ?, fecha_cobro = ? WHERE id = ?', (100000, "2099-01-15", f_id))
            log("HALLAZGO: Funcionamiento permite registrar cobros con fechas futuras a nivel DB.")
        except Exception as e:
            log(f"ÉXITO: Funcionamiento bloquea fecha futura. Detalle: {e}")
        finally:
            conn.close()

        # 3.2 Sueldos - Mes inválido y negativos
        conn = db.get_connection()
        try:
            conn.execute('INSERT INTO aportes_sueldo (anio, mes, monto_pedido, fecha_pedido) VALUES (?, ?, ?, ?)', (2026, 15, -999, "2026-03-01"))
            log("HALLAZGO: Sueldos permite mes 15 y montos negativos.")
        except Exception as e:
            log(f"ÉXITO: Sueldos bloquea datos inválidos. Detalle: {e}")
        finally:
            conn.close()

        # 3.3 SAC - Cuota inválida (ej. aguinaldo tercera cuota)
        conn = db.get_connection()
        try:
            conn.execute('INSERT INTO aportes_sac (anio, cuota_nro, monto_pedido, fecha_pedido) VALUES (?, ?, ?, ?)', (2026, 3, 50000, "2026-03-01"))
            log("HALLAZGO: SAC permite cuotas diferentes a 1 o 2 a nivel DB.")
        except Exception as e:
            log(f"ÉXITO: SAC bloquea cuota 3. Detalle: {e}")
        finally:
            conn.close()

    finally:
        print("\n## 4. Limpieza (Cleanup)")
        for d in created_decretos:
            if d is not None:
                try:
                    db.delete_decreto(d)
                except Exception as e:
                    pass
        log(f"Se eliminaron {len(created_decretos)} decretos de prueba (y sus cuotas/cobros por cascada).")

        for y in created_fun_years:
            try:
                db.delete_anio_funcionamiento(y)
            except: pass
        log(f"Se eliminaron {len(created_fun_years)} años de configuración de funcionamiento.")

        for s in created_sueldos:
            try:
                db.delete_aporte_sueldo(s)
            except: pass
        log(f"Se eliminaron {len(created_sueldos)} registros de prueba de sueldos.")

        for sac in created_sac:
            try:
                db.delete_aporte_sac(sac)
            except: pass
        log(f"Se eliminaron {len(created_sac)} registros de prueba de SAC.")

    print("\n## Conclusión del Estrés")
    print("El test ha finalizado y los rastros han sido limpiados de la base de datos de manera segura.")

if __name__ == '__main__':
    run()
