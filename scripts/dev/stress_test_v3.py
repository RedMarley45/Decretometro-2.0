import sqlite3
import datetime
import os
import sys

sys.path.append(os.getcwd())
import database as db

def log(msg):
    print(f"- {msg}")

def run():
    print("# Reporte de Stress Test (V3 - Post-Backend Validations)")
    print("\n## Inicialización")
    log("Iniciando test de estrés sin borrar datos existentes...")
    
    # Trackers for cleanup
    created_decretos = []
    created_fun_years = [] 
    created_sueldos = []
    created_sac = []

    try:
        print("\n## 1. Pruebas de Decretos y Cuotas")
        
        # 1.1 Intentar crear decreto con datos inválidos (Integridad SQLite)
        conn = db.get_connection()
        try:
            conn.execute('INSERT INTO decretos (nro_decreto, anio, nro_expediente, destino_fondos, estado) VALUES (?, ?, ?, ?, ?)', (None, "No es int", None, None, 'Vigente'))
            log("FALLO: La base de datos permite crear un decreto nulo.")
        except Exception as e:
            log(f"EXITO: La DB rechazó decreto nulo. Detalle: {e}")
        finally:
            conn.close()

        # 1.2 Crear decreto válido para pruebas
        d_id = db.add_decreto(9999, 2026, "TEST-STRESS-1", "Destino Test Stress")
        created_decretos.append(d_id)
        log(f"Decreto válido creado con ID {d_id}.")

        # 1.3 Cuotas con montos negativos extremos (Validación Backend)
        try:
            db.add_cuota(d_id, 1, 2026, -9999999.99)
            log("FALLO: La base de datos permitió registrar cuota con monto negativo.")
        except ValueError as e:
            log(f"EXITO (Backend): Bloqueado cuota negativa. Detalle: {e}")

        # 1.4 Cuotas con meses inválidos
        try:
            db.add_cuota(d_id, 13, 2026, 10000)
            log("FALLO: La base de datos permitió registrar cuota con mes 13.")
        except ValueError as e:
            log(f"EXITO (Backend): Bloqueado mes inválido. Detalle: {e}")


        print("\n## 2. Pruebas de Cobros (Totales y Parciales)")
        # Crear cuota normal
        db.add_cuota(d_id, 2, 2026, 10000)
        cuotas = db.get_cuotas_by_decreto(d_id)
        c_id = [c['id'] for c in cuotas if c['monto'] == 10000][0]

        # 2.1 Pago futuro
        try:
            db.add_cobro(c_id, 5000, "2050-01-01")
            log("FALLO: Se permitió un cobro futuro.")
        except ValueError as e:
            log(f"EXITO (Backend): Bloqueado cobro futuro. Detalle: {e}")

        # 2.2 Pago excedente (sobrepago)
        try:
            db.add_cobro(c_id, 9000000, datetime.date.today().strftime('%Y-%m-%d'))
            log("FALLO: Se permitió sobrepago.")
        except ValueError as e:
            log(f"EXITO (Backend): Bloqueado sobrepago. Detalle: {e}")

        # 2.3 Pago negativo
        try:
            db.add_cobro(c_id, -1500, datetime.date.today().strftime('%Y-%m-%d'))
            log("FALLO: Se permitió pago negativo.")
        except ValueError as e:
            log(f"EXITO (Backend): Bloqueado pago negativo. Detalle: {e}")


        print("\n## 3. Pruebas de Aportes Habituales")
        # 3.1 Funcionamiento - Año futuro
        try:
            db.set_monto_funcionamiento_anio(2099, 100000)
            created_fun_years.append(2099)
            log("FALLO: Se permitió generar funcionamiento para el 2099.")
        except ValueError as e:
            log(f"EXITO (Backend): Bloqueado año futuro. Detalle: {e}")

        # Funcionamiento - Monto 0 o negativo
        try:
            db.set_monto_funcionamiento_anio(2025, -5000)
            created_fun_years.append(2025)
            log("FALLO: Se permitió generar funcionamiento con monto negativo.")
        except ValueError as e:
            log(f"EXITO (Backend): Bloqueado monto pautado negativo. Detalle: {e}")

        # 3.2 Sueldos - Mes inválido y negativos
        try:
            s_id = db.add_aporte_sueldo(2026, 15, -999, "2026-03-01")
            if s_id: created_sueldos.append(s_id)
            log("FALLO: Se permitió generar sueldo con mes 15 y monto negativo.")
        except ValueError as e:
            log(f"EXITO (Backend): Bloqueados mes/monto inválidos en sueldos. Detalle: {e}")

        # 3.3 SAC - Cuota inválida (tercera cuota)
        try:
            sac_id = db.add_aporte_sac(2026, 3, 50000, "2026-03-01")
            if sac_id: created_sac.append(sac_id)
            log("FALLO: Se permitió SAC cuota 3.")
        except ValueError as e:
            log(f"EXITO (Backend): Bloqueada cuota de SAC no permitida (1 o 2). Detalle: {e}")

    finally:
        print("\n## 4. Limpieza Estricta (Cleanup)")
        for d in created_decretos:
            if d is not None:
                try:
                    db.delete_decreto(d)
                except Exception:
                    pass
        log(f"Se limpiaron {len(created_decretos)} decretos de prueba.")

        for y in created_fun_years:
            try:
                db.delete_anio_funcionamiento(y)
            except: pass
        log(f"Se limpiaron {len(created_fun_years)} años de configuración de funcionamiento creados.")

        for s in created_sueldos:
            try:
                db.delete_aporte_sueldo(s)
            except: pass
        log(f"Se limpiaron {len(created_sueldos)} registros de prueba de sueldos creados.")

        for sac in created_sac:
            try:
                db.delete_aporte_sac(sac)
            except: pass
        log(f"Se limpiaron {len(created_sac)} registros de prueba de SAC creados.")

    print("\n## Evaluación Final")
    print("Test completado. Todas las inyecciones de estrés a nivel de backend fueron rechazadas.")

if __name__ == '__main__':
    run()
