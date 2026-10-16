"""
db_core/repo_obras.py - Gestión de Obras Civiles, Contratación Bimonetaria y Pagos con Fondos Propios
"""
import datetime
from db_core.connection import db_session, TOLERANCE
from db_core.repo_auditoria import register_or_update_op, _validar_op_o_nota_db

def add_obra(nombre, expediente_imuh, proveedor_id=None, moneda_id=1, monto_contrato_moneda=0.0, cotizacion_base_contrato=1.0, fecha_contrato=None, notas_contrato=None):
    if not nombre or not nombre.strip():
        raise ValueError("El nombre de la obra no puede estar vacío.")
    if not expediente_imuh or not expediente_imuh.strip():
        raise ValueError("El expediente IMUH no puede estar vacío.")
    import utils
    if not utils.validar_expediente_imuh(expediente_imuh):
        raise ValueError("El Expediente IMUH tiene un formato inválido (debe ser 8XXXXXX-I-AAAA o similar).")
        
    exp_normalizado = utils.normalizar_expediente_imuh(expediente_imuh)
    
    if get_obra_by_expediente(exp_normalizado):
        raise ValueError(f"Ya existe una obra registrada con el expediente {exp_normalizado}.")
    
    # Sincronización inmutable del camino de escritura
    m_id = int(moneda_id or 1)
    monto_mon = float(monto_contrato_moneda or 0.0)
    cotiz_base = float(cotizacion_base_contrato or 1.0)
    if m_id == 1:
        cotiz_base = 1.0
        monto_pesos = monto_mon
    else:
        monto_pesos = monto_mon * cotiz_base

    with db_session() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO obras (
                nombre, expediente_imuh, activa, proveedor_id,
                moneda_id, monto_contrato_moneda, cotizacion_base_contrato,
                monto_contrato, fecha_contrato, notas_contrato
            )
            VALUES (?, ?, 1, ?, ?, ?, ?, ?, ?, ?)
        ''', (nombre.strip(), exp_normalizado, proveedor_id,
              m_id, monto_mon, cotiz_base,
              monto_pesos, fecha_contrato, notas_contrato.strip() if notas_contrato else None))
        obra_id = cursor.lastrowid
        return obra_id


def update_obra(obra_id, nombre, expediente_imuh, activa, proveedor_id=None,
                moneda_id=None, monto_contrato_moneda=None, cotizacion_base_contrato=None,
                fecha_contrato=None, notas_contrato=None, motivo_rectificacion=None):
    if not nombre or not nombre.strip():
        raise ValueError("El nombre de la obra no puede estar vacío.")
    if not expediente_imuh or not expediente_imuh.strip():
        raise ValueError("El expediente IMUH no puede estar vacío.")
    import utils
    if not utils.validar_expediente_imuh(expediente_imuh):
        raise ValueError("El Expediente IMUH tiene un formato inválido.")
        
    exp_normalizado = utils.normalizar_expediente_imuh(expediente_imuh)

    with db_session() as conn:
        cursor = conn.cursor()
        # Verificar duplicados del expediente excluyendo la obra actual
        cursor.execute('SELECT id FROM obras WHERE expediente_imuh = ? AND id != ?', (exp_normalizado, obra_id))
        if cursor.fetchone():
            raise ValueError(f"Ya existe otra obra registrada con el expediente IMUH '{exp_normalizado}'.")
            
        cursor.execute('SELECT moneda_id, monto_contrato_moneda, cotizacion_base_contrato, monto_contrato, fecha_contrato, notas_contrato FROM obras WHERE id = ?', (obra_id,))
        cur_row = cursor.fetchone()
        
        old_m_id = int(cur_row['moneda_id'] or 1)
        m_id = int(moneda_id if moneda_id is not None else old_m_id)
        monto_mon = float(monto_contrato_moneda if monto_contrato_moneda is not None else (cur_row['monto_contrato_moneda'] or cur_row['monto_contrato'] or 0.0))
        old_cotiz = float(cur_row['cotizacion_base_contrato'] or 1.0)
        cotiz_base = float(cotizacion_base_contrato if cotizacion_base_contrato is not None else old_cotiz)
        f_contrato = fecha_contrato if fecha_contrato is not None else cur_row['fecha_contrato']
        n_contrato = notas_contrato if notas_contrato is not None else cur_row['notas_contrato']

        pagos_existentes = get_pagos_detalle_por_obra(obra_id)
        tiene_pagos = (len(pagos_existentes) > 0 or get_total_pagado_obra(obra_id) > 0)

        # Guarda 1: Bloqueo terminante de cambio de moneda si ya hay pagos
        if m_id != old_m_id and tiene_pagos:
            raise ValueError("No se puede modificar la moneda de contratación de una obra que ya registra pagos u órdenes de pago emitidas.")

        # Guarda 2: Rectificación de cotización base inicial si ya hay pagos
        if m_id != 1 and abs(cotiz_base - old_cotiz) > 0.0001 and tiene_pagos:
            if not motivo_rectificacion or not str(motivo_rectificacion).strip():
                raise ValueError("Debe ingresar un motivo / justificación obligatoria para rectificar la cotización base de una obra con pagos registrados.")
            import datetime
            fecha_hoy = datetime.date.today().strftime('%Y-%m-%d')
            constancia = f"\n[Rectificación Cotiz. Base: ${old_cotiz:,.2f} -> ${cotiz_base:,.2f} | Motivo: {str(motivo_rectificacion).strip()} | Fecha: {fecha_hoy}]"
            n_contrato = (n_contrato or "") + constancia

        if m_id == 1:
            cotiz_base = 1.0
            monto_pesos = monto_mon
            total_pagado = get_total_pagado_obra(obra_id)
            if monto_pesos > 0 and monto_pesos < (total_pagado - TOLERANCE):
                raise ValueError(f"No se puede reducir el monto de contrato por debajo del total ya pagado a la contratista (${total_pagado:,.2f})")
        else:
            monto_pesos = monto_mon * cotiz_base
            resumen = get_resumen_contrato_obra(obra_id)
            if resumen:
                total_amortizado = float(resumen.get('total_moneda_amortizada') or 0.0)
                cant_adic = float(resumen.get('cantidad_adicionales_moneda') or 0.0)
                nuevo_tope_moneda = monto_mon + cant_adic
                cod_mon = resumen.get('moneda_codigo') or 'UVI'
                if monto_mon > 0 and nuevo_tope_moneda < (total_amortizado - 0.0001):
                    raise ValueError(f"No se puede reducir el contrato en {cod_mon} ({nuevo_tope_moneda:,.2f}) por debajo del total ya amortizado ({total_amortizado:,.2f} {cod_mon}).")

        cursor.execute('''
            UPDATE obras
            SET nombre = ?, expediente_imuh = ?, activa = ?, proveedor_id = ?,
                moneda_id = ?, monto_contrato_moneda = ?, cotizacion_base_contrato = ?,
                monto_contrato = ?, fecha_contrato = ?, notas_contrato = ?
            WHERE id = ?
        ''', (nombre.strip(), exp_normalizado, activa, proveedor_id,
              m_id, monto_mon, cotiz_base,
              monto_pesos, f_contrato, n_contrato, obra_id))
        
        # Sincronizar campo expediente_imuh en solicitudes_financiamiento por consistencia
        cursor.execute('''
            UPDATE solicitudes_financiamiento
            SET expediente_imuh = ?
            WHERE obra_id = ?
        ''', (exp_normalizado, obra_id))

def delete_obra(obra_id):
    with db_session() as conn:
        cursor = conn.cursor()
        
        # Verificar si tiene movimientos asociados
        cursor.execute('SELECT COUNT(*) as cnt FROM cobro_desvios WHERE obra_id = ?', (obra_id,))
        if cursor.fetchone()['cnt'] > 0:
            raise ValueError("No se puede eliminar la obra porque tiene desvíos directos asociados. Pruebe inhabilitándola.")
            
        cursor.execute('SELECT COUNT(*) as cnt FROM cobro_reserva_usos WHERE obra_id = ?', (obra_id,))
        if cursor.fetchone()['cnt'] > 0:
            raise ValueError("No se puede eliminar la obra porque tiene desvíos desde reserva asociados. Pruebe inhabilitándola.")
            
        cursor.execute('SELECT COUNT(*) as cnt FROM solicitudes_financiamiento WHERE obra_id = ?', (obra_id,))
        if cursor.fetchone()['cnt'] > 0:
            raise ValueError("No se puede eliminar la obra porque tiene solicitudes de financiamiento asociadas. Pruebe inhabilitándola.")

        cursor.execute('SELECT COUNT(*) as cnt FROM decretos_obras WHERE obra_id = ?', (obra_id,))
        if cursor.fetchone()['cnt'] > 0:
            raise ValueError("No se puede eliminar la obra porque está asociada a decretos. Pruebe inhabilitándola.")

        cursor.execute('DELETE FROM obras WHERE id = ?', (obra_id,))

def get_obras(only_active=False):
    with db_session() as conn:
        cursor = conn.cursor()
        query = '''
            SELECT o.*, p.razon_social as proveedor_razon_social, p.cuit as proveedor_cuit,
                   COALESCE(m.codigo, 'ARS') as moneda_codigo,
                   COALESCE(m.simbolo, '$') as moneda_simbolo,
                   COALESCE(m.nombre, 'Peso Argentino') as moneda_nombre
            FROM obras o
            LEFT JOIN proveedores_obras p ON o.proveedor_id = p.id
            LEFT JOIN monedas_indices m ON o.moneda_id = m.id
        '''
        if only_active:
            query += ' WHERE o.activa = 1'
        query += ' ORDER BY o.nombre ASC'
        cursor.execute(query)
        rows = cursor.fetchall()
        return [dict(ix) for ix in rows]


def get_obra(obra_id):
    with db_session() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT o.*, p.razon_social as proveedor_razon_social, p.cuit as proveedor_cuit,
                   COALESCE(m.codigo, 'ARS') as moneda_codigo,
                   COALESCE(m.simbolo, '$') as moneda_simbolo,
                   COALESCE(m.nombre, 'Peso Argentino') as moneda_nombre
            FROM obras o
            LEFT JOIN proveedores_obras p ON o.proveedor_id = p.id
            LEFT JOIN monedas_indices m ON o.moneda_id = m.id
            WHERE o.id = ?
        ''', (obra_id,))
        row = cursor.fetchone()
        return dict(row) if row else None


def get_obra_by_expediente(expediente_imuh):
    with db_session() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT o.*, p.razon_social as proveedor_razon_social, p.cuit as proveedor_cuit,
                   COALESCE(m.codigo, 'ARS') as moneda_codigo,
                   COALESCE(m.simbolo, '$') as moneda_simbolo,
                   COALESCE(m.nombre, 'Peso Argentino') as moneda_nombre
            FROM obras o
            LEFT JOIN proveedores_obras p ON o.proveedor_id = p.id
            LEFT JOIN monedas_indices m ON o.moneda_id = m.id
            WHERE o.expediente_imuh = ?
        ''', (expediente_imuh,))
        row = cursor.fetchone()
        return dict(row) if row else None


def update_monto_contrato_obra(obra_id, nuevo_monto, nuevo_monto_moneda=None, nueva_cotizacion_base=None, motivo_rectificacion=None):
    obra = get_obra(obra_id)
    if not obra:
        raise ValueError("Obra no encontrada.")
    m_id = obra.get('moneda_id') or 1
    
    if m_id == 1:
        monto_moneda = float(nuevo_monto or 0.0)
        cotiz = 1.0
        monto_pesos = float(nuevo_monto or 0.0)
    else:
        monto_moneda = float(nuevo_monto_moneda if nuevo_monto_moneda is not None else (obra.get('monto_contrato_moneda') or 0.0))
        cotiz = float(nueva_cotizacion_base if nueva_cotizacion_base is not None else (obra.get('cotizacion_base_contrato') or 1.0))
        monto_pesos = float(nuevo_monto if nuevo_monto is not None else (monto_moneda * cotiz))

    old_cotiz = float(obra.get('cotizacion_base_contrato') or 1.0)
    pagos_existentes = get_pagos_detalle_por_obra(obra_id)
    tiene_pagos = (len(pagos_existentes) > 0 or get_total_pagado_obra(obra_id) > 0)
    
    # Preparación en memoria de la constancia de rectificación (no se escribe hasta que pasen las guardas)
    nueva_constancia = None
    if m_id != 1 and nueva_cotizacion_base is not None and abs(cotiz - old_cotiz) > 0.0001 and tiene_pagos:
        if not motivo_rectificacion or not str(motivo_rectificacion).strip():
            raise ValueError("Debe ingresar un motivo / justificación obligatoria para rectificar la cotización base de una obra con pagos registrados.")
        import datetime
        fecha_hoy = datetime.date.today().strftime('%Y-%m-%d')
        nueva_constancia = f"\n[Rectificación Cotiz. Base: ${old_cotiz:,.2f} -> ${cotiz:,.2f} | Motivo: {str(motivo_rectificacion).strip()} | Fecha: {fecha_hoy}]"

    # Guardas de reducción contra importes ya amortizados / pagados
    resumen = get_resumen_contrato_obra(obra_id)
    if m_id == 1:
        total_pagado = get_total_pagado_obra(obra_id)
        if monto_pesos > 0 and monto_pesos < (total_pagado - TOLERANCE):
            raise ValueError(f"No se puede reducir el monto de contrato por debajo del total ya pagado a la contratista (${total_pagado:,.2f})")
    else:
        if resumen:
            total_amortizado = float(resumen.get('total_moneda_amortizada') or 0.0)
            cant_adic = float(resumen.get('cantidad_adicionales_moneda') or 0.0)
            nuevo_tope_moneda = monto_moneda + cant_adic
            cod_mon = resumen.get('moneda_codigo') or 'UVI'
            if monto_moneda > 0 and nuevo_tope_moneda < (total_amortizado - 0.0001):
                raise ValueError(f"No se puede reducir el contrato en {cod_mon} ({nuevo_tope_moneda:,.2f}) por debajo del total ya amortizado ({total_amortizado:,.2f} {cod_mon}).")
    
    # Escritura atómica única en base de datos
    with db_session() as conn:
        if nueva_constancia:
            notas_actuales = obra.get('notas_contrato') or ""
            nuevas_notas = notas_actuales + nueva_constancia
            conn.execute("""
                UPDATE obras 
                SET monto_contrato = ?, monto_contrato_moneda = ?, cotizacion_base_contrato = ?, notas_contrato = ?
                WHERE id = ?
            """, (monto_pesos, monto_moneda, cotiz, nuevas_notas, obra_id))
        else:
            conn.execute("""
                UPDATE obras 
                SET monto_contrato = ?, monto_contrato_moneda = ?, cotizacion_base_contrato = ?
                WHERE id = ?
            """, (monto_pesos, monto_moneda, cotiz, obra_id))


def add_obra_adicional(obra_id, nro_resolucion, fecha, cantidad_moneda, cotizacion_base=1.0, motivo=None):
    if not obra_id:
        raise ValueError("Debe especificar la obra.")
    if not nro_resolucion or not str(nro_resolucion).strip():
        raise ValueError("El N° de Resolución del adicional no puede estar vacío.")
    if not fecha:
        raise ValueError("La fecha del adicional es obligatoria.")
    try:
        cant_mon = float(cantidad_moneda)
    except (ValueError, TypeError):
        raise ValueError("La cantidad en moneda debe ser un número válido.")
    if cant_mon <= 0:
        raise ValueError("La cantidad en moneda debe ser mayor a 0.")
        
    try:
        cotiz = float(cotizacion_base)
    except (ValueError, TypeError):
        cotiz = 1.0
    if cotiz <= 0:
        cotiz = 1.0
        
    monto_ars = round(cant_mon * cotiz, 2)
    
    with db_session() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT id, moneda_id FROM obras WHERE id = ?', (obra_id,))
        o_row = cursor.fetchone()
        if not o_row:
            raise ValueError("Obra no encontrada.")
            
        cursor.execute('''
            INSERT INTO obra_adicionales (obra_id, nro_resolucion, fecha, cantidad_moneda, cotizacion_base, monto_equivalente_ars, motivo)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (obra_id, str(nro_resolucion).strip(), str(fecha), cant_mon, cotiz, monto_ars, motivo.strip() if motivo else None))
        new_id = cursor.lastrowid
        return new_id


def get_obra_adicionales(obra_id):
    with db_session() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT * FROM obra_adicionales
            WHERE obra_id = ?
            ORDER BY fecha ASC, id ASC
        ''', (obra_id,))
        return [dict(r) for r in cursor.fetchall()]


def delete_obra_adicional(adicional_id):
    with db_session() as conn:
        cursor = conn.cursor()
        cursor.execute('DELETE FROM obra_adicionales WHERE id = ?', (adicional_id,))


def get_resumen_contrato_obra(obra_id):
    """
    Consolida la posición contractual y financiera de una obra.
    Para obras bimonetarias (UVIs, USD, etc.), aplica costeo cronológico FIFO sobre los tramos
    (Contrato Base + Adicionales por Resolución) y determina el Costo Base Histórico
    y el Resultado por Indexación acumulado.
    """
    obra = get_obra(obra_id)
    if not obra:
        return None
        
    moneda_id = obra.get('moneda_id') or 1
    es_bimonetaria = (moneda_id != 1)
    
    # 1. Definición de Tramos Contractuales (FIFO)
    # Tramo 0: Contrato Base
    monto_base_moneda = float(obra.get('monto_contrato_moneda') or 0.0)
    cotiz_base_contrato = float(obra.get('cotizacion_base_contrato') or 1.0)
    if not es_bimonetaria:
        monto_base_moneda = float(obra.get('monto_contrato') or 0.0)
        cotiz_base_contrato = 1.0
    costo_base_contrato_ars = monto_base_moneda * cotiz_base_contrato
    
    tramos = [{
        'tipo': 'Contrato Base',
        'nro_resolucion': 'Original',
        'fecha': obra.get('fecha_contrato') or 'Inicial',
        'cantidad_moneda': monto_base_moneda,
        'cotizacion_base': cotiz_base_contrato,
        'monto_ars': costo_base_contrato_ars,
        'moneda_amortizada': 0.0,
        'costo_base_amortizado_ars': 0.0,
        'saldo_moneda': monto_base_moneda
    }]
    
    # Tramos 1..N: Adicionales ordenados cronológicamente
    adicionales = get_obra_adicionales(obra_id)
    cant_adicionales_moneda = 0.0
    costo_adicionales_ars = 0.0
    for adic in adicionales:
        cant_adic = float(adic.get('cantidad_moneda') or 0.0)
        cotiz_adic = float(adic.get('cotizacion_base') or 1.0)
        monto_adic_ars = float(adic.get('monto_equivalente_ars') or (cant_adic * cotiz_adic))
        cant_adicionales_moneda += cant_adic
        costo_adicionales_ars += monto_adic_ars
        tramos.append({
            'tipo': 'Adicional',
            'nro_resolucion': adic.get('nro_resolucion') or '',
            'fecha': str(adic.get('fecha') or ''),
            'cantidad_moneda': cant_adic,
            'cotizacion_base': cotiz_adic,
            'monto_ars': monto_adic_ars,
            'moneda_amortizada': 0.0,
            'costo_base_amortizado_ars': 0.0,
            'saldo_moneda': cant_adic
        })
        
    total_contratado_moneda = monto_base_moneda + cant_adicionales_moneda
    total_costo_base_contratado_ars = costo_base_contrato_ars + costo_adicionales_ars
    
    # 2. Pagos efectivos imputados a la obra
    with db_session() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT id, fecha, monto, cantidad_moneda_amortizada, cotizacion_pago, 'Fin Original' as fuente
            FROM cobro_fin_original_usos
            WHERE obra_id = ?
            ORDER BY fecha ASC, id ASC
        ''', (obra_id,))
        pagos_fo = [dict(r) for r in cursor.fetchall()]
        
        cursor.execute('''
            SELECT id, fecha, monto, cantidad_moneda_amortizada, cotizacion_pago, 'Fondos Propios' as fuente
            FROM pagos_fondos_propios
            WHERE obra_id = ?
            ORDER BY fecha ASC, id ASC
        ''', (obra_id,))
        pagos_fp = [dict(r) for r in cursor.fetchall()]
        
        cursor.execute('''
            SELECT id, fecha, monto, cantidad_moneda_amortizada, cotizacion_pago, 'Desvío Fin Original' as fuente
            FROM cobro_desvios
            WHERE obra_id = ?
            ORDER BY fecha ASC, id ASC
        ''', (obra_id,))
        pagos_desv = [dict(r) for r in cursor.fetchall()]
        
        cursor.execute('''
            SELECT id, fecha, monto, cantidad_moneda_amortizada, cotizacion_pago, 'Uso Reserva' as fuente
            FROM cobro_reserva_usos
            WHERE obra_id = ?
            ORDER BY fecha ASC, id ASC
        ''', (obra_id,))
        pagos_res = [dict(r) for r in cursor.fetchall()]
        
    todos_pagos = pagos_fo + pagos_fp + pagos_desv + pagos_res
    todos_pagos.sort(key=lambda x: (str(x.get('fecha') or ''), x.get('id') or 0))
    
    total_pagado_efectivo_ars = sum(float(p.get('monto') or 0.0) for p in todos_pagos)
    
    # Cálculo de moneda amortizada
    total_moneda_amortizada = 0.0
    for p in todos_pagos:
        monto_ars = float(p.get('monto') or 0.0)
        if not es_bimonetaria:
            cant = monto_ars
        else:
            cant_raw = p.get('cantidad_moneda_amortizada')
            if cant_raw is not None and float(cant_raw) > 0:
                cant = float(cant_raw)
            else:
                cotiz_p = float(p.get('cotizacion_pago') or 0.0)
                if cotiz_p <= 1.0 and cotiz_base_contrato > 1.0:
                    cotiz_p = cotiz_base_contrato
                elif cotiz_p <= 0.0:
                    cotiz_p = 1.0
                cant = (monto_ars / cotiz_p) if cotiz_p > 0 else 0.0
        total_moneda_amortizada += cant
        
    # 3. Aplicación del algoritmo FIFO sobre los tramos
    rem_amortizar = total_moneda_amortizada
    costo_base_amortizado_ars = 0.0
    last_cotiz = cotiz_base_contrato
    
    for tramo in tramos:
        last_cotiz = tramo['cotizacion_base']
        if rem_amortizar <= 0:
            break
        capacidad = tramo['cantidad_moneda']
        tomar = min(rem_amortizar, capacidad)
        tramo['moneda_amortizada'] = tomar
        tramo_costo = tomar * tramo['cotizacion_base']
        tramo['costo_base_amortizado_ars'] = tramo_costo
        tramo['saldo_moneda'] = max(0.0, capacidad - tomar)
        costo_base_amortizado_ars += tramo_costo
        rem_amortizar -= tomar
        
    if rem_amortizar > 0:
        costo_base_amortizado_ars += (rem_amortizar * last_cotiz)
        
    resultado_indexacion_ars = total_pagado_efectivo_ars - costo_base_amortizado_ars
    saldo_moneda_remanente = max(0.0, total_contratado_moneda - total_moneda_amortizada)
    porcentaje_avance = (total_moneda_amortizada / total_contratado_moneda * 100.0) if total_contratado_moneda > 0 else 0.0
    
    return {
        'obra_id': obra_id,
        'nombre': obra.get('nombre'),
        'expediente_imuh': obra.get('expediente_imuh'),
        'moneda_id': moneda_id,
        'moneda_codigo': obra.get('moneda_codigo') or 'ARS',
        'moneda_simbolo': obra.get('moneda_simbolo') or '$',
        'moneda_nombre': obra.get('moneda_nombre') or 'Peso Argentino',
        'es_bimonetaria': es_bimonetaria,
        'monto_contrato_base_moneda': monto_base_moneda,
        'cotizacion_base_contrato': cotiz_base_contrato,
        'costo_base_contrato_ars': costo_base_contrato_ars,
        'cantidad_adicionales_moneda': cant_adicionales_moneda,
        'costo_adicionales_ars': costo_adicionales_ars,
        'total_contratado_moneda': total_contratado_moneda,
        'total_costo_base_contratado_ars': total_costo_base_contratado_ars,
        'total_moneda_amortizada': total_moneda_amortizada,
        'saldo_moneda_remanente': saldo_moneda_remanente,
        'porcentaje_avance_moneda': min(100.0, porcentaje_avance),
        'total_pagado_efectivo_ars': total_pagado_efectivo_ars,
        'costo_base_amortizado_ars': costo_base_amortizado_ars,
        'resultado_indexacion_ars': resultado_indexacion_ars,
        'tramos': tramos
    }


def get_pagos_detalle_por_obra(obra_id):
    """
    Retorna el detalle cronológico de órdenes de pago imputadas a la obra
    con su desglose bimonetario y la imputación FIFO al Costo Base y Resultado por Indexación.
    """
    obra = get_obra(obra_id)
    if not obra:
        return []
        
    moneda_id = obra.get('moneda_id') or 1
    es_bimonetaria = (moneda_id != 1)
    
    resumen = get_resumen_contrato_obra(obra_id)
    tramos_base = []
    if resumen and resumen.get('tramos'):
        for t in resumen['tramos']:
            tramos_base.append({
                'tipo': t['tipo'],
                'cantidad_moneda': t['cantidad_moneda'],
                'cotizacion_base': t['cotizacion_base'],
                'disponible': t['cantidad_moneda']
            })
    last_cotiz_base = resumen.get('cotizacion_base_contrato') or 1.0 if resumen else 1.0
    
    with db_session() as conn:
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT fu.id, fu.fecha, fu.nro_op, fu.monto as monto_ars,
                   fu.cantidad_moneda_amortizada, fu.cotizacion_pago,
                   fu.convenio_solicitud_id, fu.motivo_sobrepago, fu.notas,
                   c.origen_tipo, cs.nro_certificado, conv.nombre_convenio,
                   'Fin Original' as tipo_fuente
            FROM cobro_fin_original_usos fu
            LEFT JOIN cobros c ON fu.cobro_id = c.id
            LEFT JOIN convenio_solicitudes cs ON (fu.convenio_solicitud_id = cs.id OR c.convenio_solicitud_id = cs.id)
            LEFT JOIN convenios conv ON cs.convenio_id = conv.id
            WHERE fu.obra_id = ?
        ''', (obra_id,))
        pagos_fo = [dict(r) for r in cursor.fetchall()]
        
        cursor.execute('''
            SELECT pfp.id, pfp.fecha, pfp.nro_op, pfp.monto as monto_ars,
                   pfp.cantidad_moneda_amortizada, pfp.cotizacion_pago,
                   pfp.convenio_solicitud_id, pfp.motivo_sobrepago, pfp.observaciones as notas,
                   'fondos_propios' as origen_tipo, cs.nro_certificado, conv.nombre_convenio,
                   'Fondos Propios' as tipo_fuente
            FROM pagos_fondos_propios pfp
            LEFT JOIN convenio_solicitudes cs ON pfp.convenio_solicitud_id = cs.id
            LEFT JOIN convenios conv ON cs.convenio_id = conv.id
            WHERE pfp.obra_id = ?
        ''', (obra_id,))
        pagos_fp = [dict(r) for r in cursor.fetchall()]
        
        cursor.execute('''
            SELECT cd.id, cd.fecha, cd.nro_op, cd.monto as monto_ars,
                   cd.cantidad_moneda_amortizada, cd.cotizacion_pago,
                   NULL as convenio_solicitud_id, NULL as motivo_sobrepago, cd.motivo as notas,
                   'decreto' as origen_tipo, NULL as nro_certificado, NULL as nombre_convenio,
                   'Desvío Fin Original' as tipo_fuente
            FROM cobro_desvios cd
            WHERE cd.obra_id = ?
        ''', (obra_id,))
        pagos_desv = [dict(r) for r in cursor.fetchall()]
        
        cursor.execute('''
            SELECT cr.id, cr.fecha, cr.nro_op, cr.monto as monto_ars,
                   cr.cantidad_moneda_amortizada, cr.cotizacion_pago,
                   NULL as convenio_solicitud_id, NULL as motivo_sobrepago, cr.notas,
                   'decreto' as origen_tipo, NULL as nro_certificado, NULL as nombre_convenio,
                   'Uso Reserva' as tipo_fuente
            FROM cobro_reserva_usos cr
            WHERE cr.obra_id = ?
        ''', (obra_id,))
        pagos_res = [dict(r) for r in cursor.fetchall()]
        
    todos = pagos_fo + pagos_fp + pagos_desv + pagos_res
    todos.sort(key=lambda x: (str(x.get('fecha') or ''), x.get('id') or 0))
    
    for p in todos:
        monto_ars = float(p.get('monto_ars') or 0.0)
        if not es_bimonetaria:
            cant_mon = monto_ars
            cotiz = 1.0
        else:
            cant_raw = p.get('cantidad_moneda_amortizada')
            cotiz_raw = p.get('cotizacion_pago')
            if cotiz_raw and float(cotiz_raw) > 1.0:
                cotiz = float(cotiz_raw)
            elif last_cotiz_base > 1.0:
                cotiz = last_cotiz_base
            else:
                cotiz = 1.0
            if cant_raw is not None and float(cant_raw) > 0:
                cant_mon = float(cant_raw)
            else:
                cant_mon = round(monto_ars / cotiz, 6) if cotiz > 0 else 0.0
                
        p['cantidad_moneda_amortizada'] = cant_mon
        p['cotizacion_pago'] = cotiz
        
        rem = cant_mon
        costo_base_pago_ars = 0.0
        for tr in tramos_base:
            last_cotiz_base = tr['cotizacion_base']
            if rem <= 0:
                break
            if tr['disponible'] > 0:
                take = min(rem, tr['disponible'])
                costo_base_pago_ars += (take * tr['cotizacion_base'])
                tr['disponible'] -= take
                rem -= take
        if rem > 0:
            costo_base_pago_ars += (rem * last_cotiz_base)
            
        p['costo_base_ars'] = costo_base_pago_ars
        p['resultado_indexacion_ars'] = monto_ars - costo_base_pago_ars
        
        if p.get('nombre_convenio') or p.get('nro_certificado'):
            cert_txt = f" (Cert. {p['nro_certificado']})" if p.get('nro_certificado') else ""
            conv_txt = f" - {p['nombre_convenio']}" if p.get('nombre_convenio') else ""
            p['fuente_descripcion'] = f"Convenio{conv_txt}{cert_txt}"
        else:
            p['fuente_descripcion'] = p.get('tipo_fuente')
            
    return todos


def check_sobrepago_obra(obra_id, nuevo_monto_pesos=0.0, nueva_cantidad_moneda=0.0):
    """
    Verifica si un pago propuesto excede el tope de contrato.
    Retorna un diccionario de control con indicador booleano y mensaje explicativo.
    """
    obra = get_obra(obra_id)
    if not obra:
        return {'es_sobrepago': False, 'mensaje': ''}
        
    resumen = get_resumen_contrato_obra(obra_id)
    if not resumen:
        return {'es_sobrepago': False, 'mensaje': ''}
        
    es_bimonetaria = resumen['es_bimonetaria']
    simbolo = resumen['moneda_simbolo']
    codigo = resumen['moneda_codigo']
    
    if es_bimonetaria:
        tope = resumen['total_contratado_moneda']
        acumulado_previo = resumen['total_moneda_amortizada']
        nuevo_total = acumulado_previo + float(nueva_cantidad_moneda or 0.0)
        es_sobrepago = (tope > 0 and nuevo_total > (tope + 0.001))
        exceso = max(0.0, nuevo_total - tope)
        unidad = codigo
        msg = f"El total amortizado alcanzará {nuevo_total:,.2f} {codigo}, superando el contrato total ({tope:,.2f} {codigo}) por {exceso:,.2f} {codigo}."
    else:
        tope = resumen['total_costo_base_contratado_ars']
        acumulado_previo = resumen['total_pagado_efectivo_ars']
        nuevo_total = acumulado_previo + float(nuevo_monto_pesos or 0.0)
        es_sobrepago = (tope > 0 and nuevo_total > (tope + TOLERANCE))
        exceso = max(0.0, nuevo_total - tope)
        unidad = 'ARS'
        msg = f"El total pagado alcanzará ${nuevo_total:,.2f} ARS, superando el monto de contrato (${tope:,.2f} ARS) por ${exceso:,.2f} ARS."
        
    return {
        'es_sobrepago': es_sobrepago,
        'es_bimonetaria': es_bimonetaria,
        'tope': tope,
        'acumulado_previo': acumulado_previo,
        'nuevo_total': nuevo_total,
        'exceso': exceso,
        'unidad': unidad,
        'mensaje': msg if es_sobrepago else ''
    }


def get_total_pagado_obra(obra_id):
    with db_session() as conn:
        pagos_fp = sum(row['monto'] for row in conn.execute("SELECT monto FROM pagos_fondos_propios WHERE obra_id = ?", (obra_id,)).fetchall())
        fin_orig = sum(row['monto'] for row in conn.execute("SELECT monto FROM cobro_fin_original_usos WHERE obra_id = ?", (obra_id,)).fetchall())
        desvios = sum(row['monto'] for row in conn.execute("SELECT monto FROM cobro_desvios WHERE obra_id = ?", (obra_id,)).fetchall())
        reservas = sum(row['monto'] for row in conn.execute("SELECT monto FROM cobro_reserva_usos WHERE obra_id = ?", (obra_id,)).fetchall())
        return pagos_fp + fin_orig + desvios + reservas


def get_tope_recupero(obra_id):
    with db_session() as conn:
        pagos_fp = sum(row['monto'] for row in conn.execute("SELECT monto FROM pagos_fondos_propios WHERE obra_id = ?", (obra_id,)).fetchall())
        recuperos = sum(row['monto'] for row in conn.execute("SELECT monto FROM recuperos_fondos_propios WHERE obra_id = ?", (obra_id,)).fetchall())
        return max(0.0, pagos_fp - recuperos)


def get_pagos_fondos_propios(obra_id=None):
    with db_session() as conn:
        query = "SELECT * FROM pagos_fondos_propios"
        params = []
        if obra_id:
            query += " WHERE obra_id = ?"
            params.append(obra_id)
        query += " ORDER BY fecha DESC"
        return [dict(row) for row in conn.execute(query, params).fetchall()]


def add_pago_fondos_propios(obra_id, monto, fecha, nro_op, observaciones,
                            cantidad_moneda_amortizada=None, cotizacion_pago=None,
                            convenio_solicitud_id=None, motivo_sobrepago=None):
    _validar_op_o_nota_db(nro_op, observaciones, "pago con fondos propios")
    if monto <= 0:
        raise ValueError("El monto a pagar debe ser mayor a 0.")
        
    with db_session() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT moneda_id FROM obras WHERE id = ?', (obra_id,))
        o_row = cursor.fetchone()
        o_moneda_id = o_row['moneda_id'] if o_row else 1
        
        cotiz = cotizacion_pago
        cant_mon = cantidad_moneda_amortizada
        if o_moneda_id == 1:
            cotiz = 1.0
            cant_mon = float(monto)
        else:
            if cotiz is None or float(cotiz) <= 0:
                raise ValueError(
                    "Para obras pactadas en UVIs u otra moneda extranjera es obligatorio especificar una cotización de pago válida."
                )
            cotiz = float(cotiz)
            if cant_mon is None:
                cant_mon = round(float(monto) / cotiz, 6)

        cursor.execute('''
            INSERT INTO pagos_fondos_propios (
                obra_id, monto, fecha, nro_op, observaciones,
                cantidad_moneda_amortizada, cotizacion_pago, convenio_solicitud_id, motivo_sobrepago
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (obra_id, monto, fecha, nro_op, observaciones,
              cant_mon, cotiz, convenio_solicitud_id, motivo_sobrepago))
              
        if nro_op:
            register_or_update_op(nro_op, obra_id=obra_id, conn=conn)


def delete_pago_fondos_propios(pago_id):
    with db_session() as conn:
        pago = conn.execute("SELECT * FROM pagos_fondos_propios WHERE id = ?", (pago_id,)).fetchone()
        if not pago: return
        obra_id = pago['obra_id']
        monto_pago = pago['monto']
        
        # Validar si ya se recuperó algo de esta obra
        total_pagado_fp = sum(p['monto'] for p in conn.execute("SELECT monto FROM pagos_fondos_propios WHERE obra_id = ?", (obra_id,)).fetchall())
        total_recuperado = sum(r['monto'] for r in conn.execute("SELECT monto FROM recuperos_fondos_propios WHERE obra_id = ?", (obra_id,)).fetchall())
        
        if (total_pagado_fp - monto_pago) < (total_recuperado - TOLERANCE):
            raise ValueError(f"No se puede eliminar. Al hacerlo, el total de adelantos sería menor a los fondos que ya recuperó la gestión (${total_recuperado:,.2f}). Elimine los recuperos primero.")
            
        conn.execute("DELETE FROM pagos_fondos_propios WHERE id = ?", (pago_id,))


