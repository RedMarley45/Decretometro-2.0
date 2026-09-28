import database as db
import utils_reports
import re
import datetime
import uuid

def get_imuh_base(exp_str):
    m = re.search(r'(8\d{6})', str(exp_str))
    return m.group(1) if m else str(exp_str).strip().lower()

def calcular_saldos_cruzados_globales():
    obras = db.get_todas_obras_para_trazabilidad()
    
    saldos = {}
    
    nombres_imuh = {}
    for o in obras:
        b = get_imuh_base(o['expediente_imuh'])
        if b != 'sin asignar' and b.startswith('8'):
            if b not in nombres_imuh or len(o['nombre']) < len(nombres_imuh[b]):
                nombres_imuh[b] = o['nombre']

    for o in obras:
        base_o = get_imuh_base(o['expediente_imuh'])
        if base_o == 'sin asignar' or not base_o.startswith('8'):
            base_o = str((base_o, o['nombre'].strip().lower()[:15]))
            
        nombre_o = nombres_imuh.get(base_o, o['nombre']) if isinstance(base_o, str) else o['nombre']

        rows_acr, _ = utils_reports.obtener_estado_deudas_por_obra(o)
        
        for r in rows_acr:
            base_c = get_imuh_base(r.get('Exp. IMUH', 'Sin asignar'))
            if base_c == 'sin asignar' or not base_c.startswith('8'):
                base_c = str((base_c, r['Contraparte'].strip().lower()[:15]))
            
            nombre_c = nombres_imuh.get(base_c, r['Contraparte']) if isinstance(base_c, str) else r['Contraparte']
            
            key = tuple(sorted([str(base_o), str(base_c)]))
            if key not in saldos:
                saldos[key] = {'O1': str(base_o), 'O2': str(base_c), 'O1_name': nombre_o, 'O2_name': nombre_c, 'deuda_O1_to_O2': 0.0, 'deuda_O2_to_O1': 0.0}
            
            if str(base_o) == saldos[key]['O1']:
                saldos[key]['deuda_O2_to_O1'] += float(r.get('Saldo Pendiente', 0.0))
            else:
                saldos[key]['deuda_O1_to_O2'] += float(r.get('Saldo Pendiente', 0.0))
        
    pares_cruzados = []
    for k, v in saldos.items():
        if v['deuda_O1_to_O2'] > 0 and v['deuda_O2_to_O1'] > 0:
            v['monto_maximo'] = min(v['deuda_O1_to_O2'], v['deuda_O2_to_O1'])
            pares_cruzados.append(v)
            
    return pares_cruzados

def ejecutar_compensacion(obra_1_imuh, obra_2_imuh, monto_compensar):
    obras = db.get_todas_obras_para_trazabilidad()
    
    def get_obras_by_base(base):
        matches = []
        for o in obras:
            b = get_imuh_base(o['expediente_imuh'])
            if b == 'sin asignar' or not b.startswith('8'):
                b = str((b, o['nombre'].strip().lower()[:15]))
            if str(b) == str(base):
                matches.append(o)
        return matches

    obras_1 = get_obras_by_base(obra_1_imuh)
    obras_2 = get_obras_by_base(obra_2_imuh)
    
    if not obras_1 or not obras_2:
        return False, "Obras no encontradas"

    desvios_1_to_2 = []
    for o1 in obras_1:
        acr, _ = utils_reports.obtener_estado_deudas_por_obra(o1)
        for r in acr:
            c_base = get_imuh_base(r.get('Exp. IMUH', 'Sin asignar'))
            if c_base == 'sin asignar' or not c_base.startswith('8'):
                c_base = str((c_base, r['Contraparte'].strip().lower()[:15]))
            if str(c_base) == str(obra_2_imuh) and float(r.get('Saldo Pendiente', 0.0)) > 0:
                desvios_1_to_2.append(r)

    desvios_2_to_1 = []
    for o2 in obras_2:
        acr, _ = utils_reports.obtener_estado_deudas_por_obra(o2)
        for r in acr:
            c_base = get_imuh_base(r.get('Exp. IMUH', 'Sin asignar'))
            if c_base == 'sin asignar' or not c_base.startswith('8'):
                c_base = str((c_base, r['Contraparte'].strip().lower()[:15]))
            if str(c_base) == str(obra_1_imuh) and float(r.get('Saldo Pendiente', 0.0)) > 0:
                desvios_2_to_1.append(r)

    def sort_key(r):
        dt = r['raw_date']
        if isinstance(dt, str):
            try:
                dt = datetime.datetime.strptime(dt, '%Y-%m-%d').date()
            except:
                dt = datetime.date.min
        return dt

    desvios_1_to_2.sort(key=sort_key)
    desvios_2_to_1.sort(key=sort_key)
    
    ops_1_to_2 = set(str(r['N° de OP']) for r in desvios_1_to_2 if str(r['N° de OP']).strip() and str(r['N° de OP']).strip() != 'Sin asignar')
    ops_2_to_1 = set(str(r['N° de OP']) for r in desvios_2_to_1 if str(r['N° de OP']).strip() and str(r['N° de OP']).strip() != 'Sin asignar')
    
    str_ops_1_to_2 = "-".join(sorted(list(ops_1_to_2))) if ops_1_to_2 else "Sin OP"
    str_ops_2_to_1 = "-".join(sorted(list(ops_2_to_1))) if ops_2_to_1 else "Sin OP"
    
    max_date = datetime.date.min
    for r in desvios_1_to_2 + desvios_2_to_1:
        if sort_key(r) > max_date:
            max_date = sort_key(r)
    
    if max_date == datetime.date.min:
        max_date = datetime.date.today()

    grupo_id = str(uuid.uuid4())
    
    def procesar_fifo(desvios, monto_total, ops_contraparte):
        monto_restante = float(monto_total)
        insertos = []
        for r in desvios:
            if monto_restante <= 0.01:
                break
            saldo_row = float(r['Saldo Pendiente'])
            a_compensar = min(saldo_row, monto_restante)
            
            tipo = r['Tipo'] 
            db_id = r.get('desvio_id', 0)
            
            insertos.append({
                'tipo_original': tipo,
                'id_original': db_id,
                'monto': a_compensar,
                'nro_op': ops_contraparte
            })
            monto_restante -= a_compensar
        return insertos

    ins_1_to_2 = procesar_fifo(desvios_1_to_2, monto_compensar, str_ops_2_to_1)
    ins_2_to_1 = procesar_fifo(desvios_2_to_1, monto_compensar, str_ops_1_to_2)
    
    with db.db_session() as conn:
        cursor = conn.cursor()
        for ins in ins_1_to_2 + ins_2_to_1:
            if ins['id_original'] == 0:
                continue
            if ins['tipo_original'] == 'Inicial':
                cursor.execute('''
                    INSERT INTO cobro_desvios_recuperos 
                    (desvio_id, monto, fecha, destino_tipo, destino_detalle, nro_op, notas, grupo_compensacion_id)
                    VALUES (?, ?, ?, 'compensacion', 'Compensación automática', ?, 'Compensación de deudas cruzadas', ?)
                ''', (ins['id_original'], ins['monto'], max_date.strftime('%Y-%m-%d'), ins['nro_op'], grupo_id))
            else:
                cursor.execute('''
                    INSERT INTO cobro_reserva_usos_recuperos 
                    (reserva_uso_id, monto, fecha, destino_tipo, destino_detalle, nro_op, notas, grupo_compensacion_id)
                    VALUES (?, ?, ?, 'compensacion', 'Compensación automática', ?, 'Compensación de deudas cruzadas', ?)
                ''', (ins['id_original'], ins['monto'], max_date.strftime('%Y-%m-%d'), ins['nro_op'], grupo_id))

    return True, "Compensación registrada correctamente"

def get_historial_compensaciones():
    with db.db_session() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT 
                grupo_compensacion_id, 
                MAX(fecha) as fecha,
                SUM(monto)/2 as monto_compensado,
                GROUP_CONCAT(DISTINCT nro_op) as ops_involucradas,
                COUNT(*) as cant_movimientos
            FROM (
                SELECT grupo_compensacion_id, fecha, monto, nro_op FROM cobro_desvios_recuperos WHERE destino_tipo = 'compensacion'
                UNION ALL
                SELECT grupo_compensacion_id, fecha, monto, nro_op FROM cobro_reserva_usos_recuperos WHERE destino_tipo = 'compensacion'
            )
            WHERE grupo_compensacion_id IS NOT NULL
            GROUP BY grupo_compensacion_id
            ORDER BY MAX(fecha) DESC
        ''')
        historial = [dict(r) for r in cursor.fetchall()]
        
        for h in historial:
            grupo_id = h['grupo_compensacion_id']
            # Obras desde desvios
            cursor.execute('''
                SELECT DISTINCT COALESCE(o.nombre, d.gasto_nombre) as obra_nombre
                FROM cobro_desvios_recuperos r
                JOIN cobro_desvios d ON r.desvio_id = d.id
                LEFT JOIN obras o ON d.obra_id = o.id
                WHERE r.grupo_compensacion_id = ?
            ''', (grupo_id,))
            obras_desvios = [row[0] for row in cursor.fetchall() if row[0]]
            
            # Obras desde reserva usos
            cursor.execute('''
                SELECT DISTINCT COALESCE(o.nombre, u.gasto_nombre) as obra_nombre
                FROM cobro_reserva_usos_recuperos r
                JOIN cobro_reserva_usos u ON r.reserva_uso_id = u.id
                LEFT JOIN obras o ON u.obra_id = o.id
                WHERE r.grupo_compensacion_id = ?
            ''', (grupo_id,))
            obras_reservas = [row[0] for row in cursor.fetchall() if row[0]]
            
            todas_obras = list(set(obras_desvios + obras_reservas))
            
            ops_list = []
            if h['ops_involucradas']:
                raw_ops = str(h['ops_involucradas']).replace(',', '-').split('-')
                ops_list = list(set([op.strip() for op in raw_ops if op.strip() and op.strip() != 'Sin OP']))
            
            h['obras_str'] = " ↔ ".join(todas_obras) if todas_obras else "No identificadas"
            h['ops_str'] = ", ".join(ops_list) if ops_list else "Sin OP"
            
        return historial

def deshacer_compensacion(grupo_id):
    with db.db_session() as conn:
        cursor = conn.cursor()
        cursor.execute('DELETE FROM cobro_desvios_recuperos WHERE grupo_compensacion_id = ?', (grupo_id,))
        cursor.execute('DELETE FROM cobro_reserva_usos_recuperos WHERE grupo_compensacion_id = ?', (grupo_id,))
    return True
