import calendar
import datetime
import logging
import os
import re
import shutil
import sqlite3

def format_currency_ar(value, include_symbol=True, symbol="$", codigo="ARS"):
    if value is None:
        value = 0.0
    s = f"{value:,.2f}"
    s = s.replace(',', 'X').replace('.', ',').replace('X', '.')
    if not include_symbol:
        return s
    if codigo and str(codigo).upper() == 'UVI':
        return f"{s} UVI"
    if symbol:
        return f"{symbol} {s}"
    return s

def format_moneda_custom(value, simbolo="$", codigo="ARS", decimales=2, include_symbol=True):
    if value is None:
        value = 0.0
    fmt = f"{{:,.{decimales}f}}"
    s = fmt.format(value)
    s = s.replace(',', 'X').replace('.', ',').replace('X', '.')
    if not include_symbol:
        return s
    if codigo and str(codigo).upper() == 'UVI':
        return f"{s} UVI"
    if simbolo:
        return f"{simbolo} {s}"
    return f"{codigo} {s}"


def format_date_ar(date_obj):
    if date_obj is None:
        return ""
    if isinstance(date_obj, str):
        try:
            date_obj = datetime.datetime.strptime(date_obj, '%Y-%m-%d').date()
        except ValueError:
            return date_obj
    return date_obj.strftime("%d-%m-%Y")

def get_due_date(mes, anio):
    if not mes or not anio:
        return None
    _, last_day = calendar.monthrange(int(anio), int(mes))
    return datetime.date(int(anio), int(mes), last_day)

def format_week_monday(date_str):
    if not date_str:
        return "---"
    try:
        dt = datetime.datetime.strptime(date_str, '%Y-%m-%d').date()
        # Monday is 0, Sunday is 6. Subtract weekday to get Monday of that week.
        monday = dt - datetime.timedelta(days=dt.weekday())
        # Formato: DD/Mes (abreviado)
        meses_abr = ["Ene", "Feb", "Mar", "Abr", "May", "Jun", "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"]
        return f"{monday.day:02d}/{meses_abr[monday.month-1]}"
    except Exception:
        return "---"

def is_late(mes, anio, fecha_cobro):
    if not fecha_cobro:
        return False
    due_date = get_due_date(mes, anio)
    if isinstance(fecha_cobro, str):
        fecha_cobro = datetime.datetime.strptime(fecha_cobro, '%Y-%m-%d').date()
    return fecha_cobro > due_date

# Tipos de archivo permitidos para subida (Fix 2)
_EXTENSIONES_PERMITIDAS = {'.pdf', '.jpg', '.jpeg', '.png'}
_MAX_FILE_SIZE_MB = 15

def save_uploaded_file(uploaded_file, dest_folder="uploads"):
    """Guarda un archivo subido por el usuario con validación de tipo y tamaño.
    
    Raises:
        ValueError: si la extensión o el tamaño no son aceptables.
    """
    if uploaded_file is None:
        return None
    # Validar extensión (Fix 2)
    ext = os.path.splitext(uploaded_file.name)[1].lower()
    if ext not in _EXTENSIONES_PERMITIDAS:
        raise ValueError(
            f"Tipo de archivo no permitido: '{ext}'. "
            f"Se aceptan: {', '.join(sorted(_EXTENSIONES_PERMITIDAS))}."
        )
    # Validar tamaño (Fix 2)
    size_bytes = uploaded_file.size if hasattr(uploaded_file, 'size') else len(uploaded_file.getbuffer())
    if size_bytes > _MAX_FILE_SIZE_MB * 1024 * 1024:
        raise ValueError(
            f"El archivo supera el tamaño máximo permitido ({_MAX_FILE_SIZE_MB} MB)."
        )
    if not os.path.exists(dest_folder):
        os.makedirs(dest_folder)
    timestamp = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
    # Sanitizar nombre: solo caracteres alfanuméricos, guiones y puntos (Fix 3.2)
    raw_name = os.path.basename(uploaded_file.name)
    clean_name = re.sub(r'[^\w\-.]', '_', raw_name)
    filename = f"{timestamp}_{clean_name}"
    file_path = os.path.join(dest_folder, filename)
    with open(file_path, "wb") as f:
        f.write(uploaded_file.getbuffer())
    return file_path

def delete_file(file_path):
    if file_path and os.path.exists(file_path):
        try:
            os.remove(file_path)
            return True
        except Exception as e:
            print(f"Error borrando archivo: {e}")
            return False
    return False

def create_backup(db_path, backup_dir="backups"):
    """Crea un backup completo y consistente de la BD usando sqlite3.backup() (Fix 9).
    Este método copia TODAS las tablas, incluyendo las que se agreguen en el futuro,
    sin necesidad de listarlas manualmente.
    """
    if not os.path.exists(backup_dir):
        os.makedirs(backup_dir)
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = os.path.join(backup_dir, f"backup_decretometro_{timestamp}.db")
    src_conn = sqlite3.connect(db_path)
    dst_conn = sqlite3.connect(backup_path)
    try:
        src_conn.backup(dst_conn)
    finally:
        dst_conn.close()
        src_conn.close()
    return backup_path

def restore_backup(current_db_path, backup_db_path):
    """Restaura de forma atómica e íntegra un backup completo usando la API nativa de SQLite,
    preservando las 29 tablas y ejecutando migraciones si el backup fuera de un esquema anterior.
    """
    if not os.path.exists(backup_db_path):
        raise FileNotFoundError(f"No se encontró el archivo de backup: {backup_db_path}")

    # 1. Validar que el archivo sea una base SQLite íntegra antes de tocar producción
    chk_conn = sqlite3.connect(backup_db_path)
    try:
        res = chk_conn.execute("PRAGMA integrity_check;").fetchone()
        if not res or res[0].lower() != "ok":
            raise ValueError(f"El archivo de backup está dañado o corrupto: {res}")
        v = chk_conn.execute("SELECT version FROM schema_version WHERE id=1;").fetchone()
        if not v:
            raise ValueError("El archivo no corresponde a una base de datos válida de Decretómetro.")
    finally:
        chk_conn.close()

    # 2. Resguardo preventivo automático del estado actual antes de pisar la base
    pre_restore_dir = os.path.join(os.path.dirname(current_db_path), "backups", "pre_restore")
    create_backup(current_db_path, backup_dir=pre_restore_dir)

    # Rotación automática: conservar como máximo los últimos 5 resguardos preventivos
    try:
        if os.path.exists(pre_restore_dir):
            existing_backups = sorted(
                [os.path.join(pre_restore_dir, f) for f in os.listdir(pre_restore_dir) if f.endswith('.db')],
                key=os.path.getmtime
            )
            while len(existing_backups) > 5:
                oldest = existing_backups.pop(0)
                try:
                    os.remove(oldest)
                except Exception:
                    pass
    except Exception:
        pass

    # 3. Restauración binaria a nivel páginas de SQLite (clona todas las tablas e índices)
    src_conn = sqlite3.connect(backup_db_path)
    dst_conn = sqlite3.connect(current_db_path, timeout=30.0)
    try:
        src_conn.backup(dst_conn)
    except Exception as e:
        logging.error(f"Error crítico durante la restauración de páginas SQLite: {e}")
        raise
    finally:
        dst_conn.close()
        src_conn.close()

    # 4. Asegurar que el esquema restaurado quede actualizado a la última versión
    import database as db
    db.init_db()

def get_dashboard_kpis(df_cuotas, df_cobros, cobros, aportes_funcionamiento, aportes_sueldo):
    import datetime
    import pandas as pd
    
    today = datetime.date.today()
    mes_actual = today.month
    anio_actual = today.year

    # 3. % de cobranza de últimos 12 meses
    mes_fin = mes_actual - 1
    anio_fin = anio_actual
    if mes_fin == 0:
        mes_fin = 12
        anio_fin -= 1
    fecha_fin = get_due_date(mes_fin, anio_fin)
    fecha_ini = datetime.date(fecha_fin.year - 1, fecha_fin.month, 1)

    def check_12_meses(row):
        due = get_due_date(row.get('mes', row['mes'] if 'mes' in row else None), row.get('anio', row['anio'] if 'anio' in row else None))
        if not due:
            return False
        return fecha_ini <= due <= fecha_fin

    cuotas_12m = df_cuotas[df_cuotas.apply(check_12_meses, axis=1)]
    total_12m = cuotas_12m['monto_efectivo'].sum() if not cuotas_12m.empty else 0
    cobrado_12m = 0
    if not cuotas_12m.empty and not df_cobros.empty:
        cobrado_12m = df_cobros[df_cobros['cuota_id'].isin(cuotas_12m['id'])]['monto'].sum()
    pct_cobranza = (cobrado_12m / total_12m * 100) if total_12m > 0 else 0

    # 4. Porcentaje histórico de cobros en tiempo y forma vs. atrasados
    hist_a_tiempo = 0
    hist_atrasado = 0
    
    for c in cobros:
        fecha_cobro = pd.to_datetime(c['fecha']).date()
        due_date = get_due_date(c.get('mes'), c.get('anio'))
        if due_date and fecha_cobro <= due_date:
            hist_a_tiempo += c.get('monto', 0)
        else:
            hist_atrasado += c.get('monto', 0)
            
    for f in aportes_funcionamiento:
        if f.get('fecha_cobro'):
            fecha_cobro = pd.to_datetime(f['fecha_cobro']).date()
            due_date = get_due_date(f.get('mes'), f.get('anio'))
            if due_date and fecha_cobro <= due_date:
                hist_a_tiempo += f.get('monto_cobrado', 0)
            else:
                hist_atrasado += f.get('monto_cobrado', 0)
                
    for s in aportes_sueldo:
        if s.get('monto_cobrado', 0) > 0 and s.get('fecha_cobro'):
            fecha_cobro = pd.to_datetime(s['fecha_cobro']).date()
            due_date = get_due_date(s.get('mes'), s.get('anio'))
            if due_date and fecha_cobro <= due_date:
                hist_a_tiempo += s.get('monto_cobrado', 0)
            else:
                hist_atrasado += s.get('monto_cobrado', 0)

    total_hist = hist_a_tiempo + hist_atrasado
    
    if total_hist > 0:
        pct_a_tiempo = (hist_a_tiempo / total_hist) * 100
        pct_atrasado = (hist_atrasado / total_hist) * 100
    else:
        pct_a_tiempo = 100.0
        pct_atrasado = 0.0
        
    return pct_cobranza, pct_a_tiempo, pct_atrasado

def get_cuotas_pendientes(df_decretos, df_cuotas, df_cobros):
    """Calcula las cuotas atrasadas y pendientes de cobrar para la lista de decretos."""
    import datetime
    import pandas as pd
    
    today_date = datetime.date.today()
    resultados = []
    
    for _, row in df_decretos.iterrows():
        dec_id = row['id']
        dec_cuotas = df_cuotas[df_cuotas['decreto_id'] == dec_id]
        dec_cobros = df_cobros[df_cobros['decreto_id'] == dec_id] if not df_cobros.empty else pd.DataFrame()
        
        atrasadas = 0
        total_proyectado = dec_cuotas['monto'].sum()
        total_cobrado = dec_cobros['monto'].sum() if not dec_cobros.empty else 0
        pendiente = max(0, total_proyectado - total_cobrado)
        
        if pendiente > 0.01:
            for _, q in dec_cuotas.iterrows():
                q_cobrado = dec_cobros[dec_cobros['cuota_id'] == q['id']]['monto'].sum() if not dec_cobros.empty else 0
                saldo = q['monto'] - q_cobrado
                if saldo > 0.01:
                    d_due_date = get_due_date(q['mes'], q['anio'])
                    if today_date > d_due_date:
                        atrasadas += saldo
                        
            resultados.append({
                'nro_decreto': row['nro_decreto'],
                'anio': row['anio'],
                'destino_fondos': row['destino_fondos'],
                'estado': row['estado'],
                'expediente_imuh': row.get('expediente_imuh') or "Sin asignar",
                'cuotas_atrasadas': atrasadas,
                'pendiente_cobrar': pendiente
            })
            
    # Ordenar por atrasadas DESC, luego pendiente DESC
    resultados.sort(key=lambda x: (x['cuotas_atrasadas'], x['pendiente_cobrar']), reverse=True)
    return resultados

def get_resumen_habituales_pendientes():
    """Retorna lista de aportes sueldo/sac con saldo > 0 y no renunciados."""
    import database as db
    pendientes = []
    
    # Sueldos
    for s in db.get_aportes_sueldo():
        saldo = s['monto_pedido'] - (s['monto_cobrado'] or 0)
        if saldo > 0.01 and s['estado'] != 'Renunciado':
            pendientes.append({
                'tipo': 'Sueldo',
                'periodo': f"{s['mes']:02d}/{s['anio']}",
                'monto_pedido': s['monto_pedido'],
                'monto_cobrado': s['monto_cobrado'] or 0,
                'saldo': saldo
            })
            
    # SAC
    for s in db.get_aportes_sac():
        saldo = s['monto_pedido'] - (s['monto_cobrado'] or 0)
        if saldo > 0.01 and s['estado'] != 'Renunciado':
            pendientes.append({
                'tipo': 'SAC',
                'periodo': f"{s['cuota_nro']}° - {s['anio']}",
                'monto_pedido': s['monto_pedido'],
                'monto_cobrado': s['monto_cobrado'] or 0,
                'saldo': saldo
            })
            
    return pendientes

def validar_expediente_imuh(valor):
    if not valor or str(valor).strip() == "":
        return True # Es opcional
    separadores = re.compile(r'[;,/]')
    partes = separadores.split(str(valor))
    patron = r'^\d{7,8}-[A-Z]-\d{4}$'
    validas = 0
    for parte in partes:
        p_clean = parte.strip()
        if p_clean == "":
            continue
        if not re.match(patron, p_clean):
            return False
        validas += 1
    return validas > 0

def normalizar_expediente_imuh(valor):
    if not valor or str(valor).strip() == "":
        return None
    separadores = re.compile(r'[;,/]')
    partes = separadores.split(str(valor))
    partes_limpias = []
    for parte in partes:
        p_clean = parte.strip().upper()
        if p_clean != "":
            partes_limpias.append(p_clean)
    if not partes_limpias:
        return None
    return ", ".join(partes_limpias)

def _validar_op_y_notas(nro_op, notas, requiere_confirmacion=True, confirmado=False):
    """Valida que un movimiento tenga OP o, en su defecto, notas válidas y confirmación.
    Retorna un mensaje de error (str) si falla, o None si es válido.
    Si requiere_confirmacion=False (ej. 'Volver a Reserva'), solo se exige la nota, sin OP ni casilla.
    """
    op_ok = bool(nro_op and nro_op.strip())
    nota_ok = bool(notas and 10 <= len(notas.strip()) <= 30)
    if requiere_confirmacion:
        if op_ok:
            return None  # Tiene OP: válido
        if not notas or not notas.strip():
            return "Error: Al no poseer un número de OP Bejerman, es obligatorio detallar las observaciones."
        if not nota_ok:
            return "Error: La observación debe tener entre 10 y 30 caracteres."
        if not confirmado:
            return "Error: Debe marcar la casilla de confirmación para guardar sin número de OP."
        return None
    else:
        # Sin OP requerida (ej. Volver a Reserva): solo nota obligatoria
        if not notas or not notas.strip():
            return "Error: Debe detallar las observaciones de esta operación (10 a 30 caracteres)."
        if not nota_ok:
            return "Error: La observación debe tener entre 10 y 30 caracteres."
        return None

def inject_style():
    import streamlit as st
    import os
    css_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "style.css")
    if os.path.exists(css_path):
        with open(css_path, "r", encoding="utf-8") as f:
            css = f.read()
        st.markdown(f"<style>{css}</style>", unsafe_allow_html=True)


def limpiar_prefijo_expediente(texto):
    if not texto:
        return ""
    import re
    patron = r'^[\(\s]*Exp\.?\s*8\d{6}-[A-Za-z]-\d{4}[\)\s-]*'
    clean = re.sub(patron, '', str(texto)).strip()
    clean = re.sub(r'^[:\-\s]+', '', clean).strip()
    return clean

def extraer_imuh_de_texto(texto):
    if not texto:
        return None
    import re
    patron = r'(8\d{6})[-\s/]+([A-Za-z])[-\s/]+(\d{4})'
    match = re.search(patron, str(texto))
    if match:
        nro, letra, anio = match.groups()
        return f"{nro}-{letra.upper()}-{anio}"
    return None

def validar_cuit(cuit):
    """Valida formato AFIP de CUIT: XX-XXXXXXXX-X (2 dígitos, guión, 8 dígitos, guión, 1 dígito) y dígito verificador."""
    if not cuit or not isinstance(cuit, str):
        return False
    cuit_clean = cuit.strip()
    if not re.match(r'^\d{2}-\d{8}-\d{1}$', cuit_clean):
        return False
    digits = [int(d) for d in cuit_clean.replace('-', '')]
    if len(digits) != 11:
        return False
    weights = [5, 4, 3, 2, 7, 6, 5, 4, 3, 2]
    val = sum(d * w for d, w in zip(digits[:10], weights))
    mod = 11 - (val % 11)
    if mod == 11:
        check = 0
    elif mod == 10:
        check = 9
    else:
        check = mod
    return digits[10] == check



