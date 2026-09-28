import os, sys, sqlite3
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
import database as db

def clean():
    conn = db.get_connection()
    c = conn.cursor()
    
    # 1. Identificar Decretos STRESS
    c.execute("SELECT id FROM decretos WHERE nro_decreto IN (9901, 9902) OR nro_expediente LIKE '%STRESS%'")
    decretos = [row['id'] for row in c.fetchall()]
    print("Decretos a limpiar:", decretos)

    # 2. Identificar cobros asociados a las cuotas de estos decretos
    c.execute("SELECT id FROM cuotas WHERE decreto_id IN ({})".format(','.join('?'*len(decretos))), decretos)
    cuotas = [row['id'] for row in c.fetchall()]
    
    if cuotas:
        c.execute("SELECT id FROM cobros WHERE cuota_id IN ({})".format(','.join('?'*len(cuotas))), cuotas)
        cobros = [row['id'] for row in c.fetchall()]
        print("Cobros a limpiar:", cobros)
        
        if cobros:
            # Eliminar recuperos manuales huérfanos asociados a esos cobros
            c.execute("SELECT id FROM cobro_desvios WHERE cobro_id IN ({})".format(','.join('?'*len(cobros))), cobros)
            desvios = [row['id'] for row in c.fetchall()]
            if desvios:
                c.execute("DELETE FROM cobro_desvios_recuperos WHERE desvio_id IN ({})".format(','.join('?'*len(desvios))), desvios)
                print("Recuperos eliminados.")
                
            # Eliminar desvios
            c.execute("DELETE FROM cobro_desvios WHERE cobro_id IN ({})".format(','.join('?'*len(cobros))), cobros)
            print("Desvios eliminados.")
            
            # Eliminar usos
            c.execute("DELETE FROM cobro_reserva_usos WHERE cobro_id IN ({})".format(','.join('?'*len(cobros))), cobros)
            print("Usos de reserva eliminados.")
            
            # Eliminar distribucion
            c.execute("DELETE FROM cobro_distribuciones WHERE cobro_id IN ({})".format(','.join('?'*len(cobros))), cobros)
            print("Distribuciones eliminadas.")
            
            # Eliminar cobros
            c.execute("DELETE FROM cobros WHERE id IN ({})".format(','.join('?'*len(cobros))), cobros)
            print("Cobros eliminados.")
            
    # Eliminar cuotas
    if decretos:
        c.execute("DELETE FROM cuotas WHERE decreto_id IN ({})".format(','.join('?'*len(decretos))), decretos)
        print("Cuotas eliminadas.")
        
        # Eliminar Decretos (forzamos sin restricciones para limpiar los de estrés)
        c.execute("DELETE FROM decretos WHERE id IN ({})".format(','.join('?'*len(decretos))), decretos)
        print("Decretos eliminados.")
        
    conn.commit()
    conn.close()

if __name__ == "__main__":
    try:
        clean()
        print("Limpieza completada y sin base de datos bloqueada.")
    except Exception as e:
        print("Error crítico limpiando:", e)
