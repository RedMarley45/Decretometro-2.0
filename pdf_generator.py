import os
from fpdf import FPDF
import datetime
import database as db
import pandas as pd
from utils import format_currency_ar, get_dashboard_kpis, get_cuotas_pendientes, get_resumen_habituales_pendientes, limpiar_prefijo_expediente

class ReporteFinancieroPDF(FPDF):
    def header(self):
        # Título
        self.set_font('Arial', 'B', 15)
        self.cell(0, 10, 'Reporte de Estado Financiero - Decretómetro', 0, 1, 'C')
        
        # Fecha
        self.set_font('Arial', 'I', 10)
        ahora = datetime.datetime.now()
        self.cell(0, 10, f'Generado el: {ahora.strftime("%d-%m-%Y %H:%M")}', 0, 1, 'C')
        self.ln(5)

    def footer(self):
        self.set_y(-15)
        self.set_font('Arial', 'I', 8)
        self.cell(0, 10, f'Página {self.page_no()}/{{nb}}', 0, 0, 'C')

    def chapter_title(self, title):
        self.set_font('Arial', 'B', 12)
        self.set_fill_color(200, 220, 255)
        self.cell(0, 8, title, 0, 1, 'L', fill=True)
        self.ln(4)

    def chapter_body(self, text):
        self.set_font('Arial', '', 10)
        self.multi_cell(0, 6, text)
        self.ln()

    def chapter_note(self, text):
        """Texto pequeño para leyendas y notas al pie de tabla."""
        self.set_font('Arial', 'I', 8)
        self.set_text_color(80, 80, 80)
        self.multi_cell(0, 5, text)
        self.set_text_color(0, 0, 0)
        self.ln(2)

    def split_text_to_lines(self, text, width, padding=4):
        paragraphs = text.split('\n')
        lines = []
        max_w = width - padding
        for para in paragraphs:
            words = para.split(' ')
            current_line = ""
            for word in words:
                test_line = current_line + " " + word if current_line else word
                if self.get_string_width(test_line) <= max_w:
                    current_line = test_line
                else:
                    if current_line:
                        lines.append(current_line)
                    current_line = word
            if current_line:
                lines.append(current_line)
        return lines

    def add_table(self, df, col_widths):
        # Header
        self.set_font('Arial', 'B', 10)
        self.set_fill_color(230, 230, 230)
        
        # Calculate header height and lines
        header_lines = [self.split_text_to_lines(str(col), col_widths[idx]) for idx, col in enumerate(df.columns)]
        max_header_lines = max(len(lines) for lines in header_lines)
        header_line_height = 5.0
        header_row_height = max(8.0, max_header_lines * header_line_height)
        
        x_start = self.get_x()
        y_start = self.get_y()
        
        for idx, lines in enumerate(header_lines):
            w = col_widths[idx]
            self.set_xy(x_start + sum(col_widths[:idx]), y_start)
            self.cell(w, header_row_height, '', border=1, fill=True)
            
            padding_y = (header_row_height - (len(lines) * header_line_height)) / 2.0
            for line_idx, line in enumerate(lines):
                self.set_xy(x_start + sum(col_widths[:idx]), y_start + padding_y + (line_idx * header_line_height))
                self.cell(w, header_line_height, line, border=0, align='L')
                
        self.set_xy(x_start, y_start + header_row_height)
        
        # Rows
        self.set_font('Arial', '', 9)
        for _, row in df.iterrows():
            is_total = str(row.iloc[0]).upper() == 'TOTAL'
            if is_total:
                self.set_font('Arial', 'B', 9)
            
            x_start = self.get_x()
            y_start = self.get_y()
            
            # Split items into lines
            cell_lines = [self.split_text_to_lines(str(item), col_widths[idx]) for idx, item in enumerate(row)]
            max_lines = max(len(lines) for lines in cell_lines)
            line_height = 4.5
            row_height = max(8.0, max_lines * line_height)
            
            # Page break check
            if y_start + row_height > self.page_break_trigger:
                self.add_page()
                x_start = self.get_x()
                y_start = self.get_y()
                
            for idx, lines in enumerate(cell_lines):
                w = col_widths[idx]
                self.set_xy(x_start + sum(col_widths[:idx]), y_start)
                
                fill_cell = is_total and idx == 0
                if fill_cell:
                    self.set_fill_color(240, 240, 240)
                
                self.cell(w, row_height, '', border=1, fill=fill_cell)
                
                padding_y = (row_height - (len(lines) * line_height)) / 2.0
                for line_idx, line in enumerate(lines):
                    self.set_xy(x_start + sum(col_widths[:idx]), y_start + padding_y + (line_idx * line_height))
                    self.cell(w, line_height, line, border=0, align='L')
                    
            self.set_xy(x_start, y_start + row_height)
            
            if is_total:
                self.set_font('Arial', '', 9)
        self.ln(5)

def generar_reporte_pdf(filepath):
    pdf = ReporteFinancieroPDF()
    pdf.alias_nb_pages()
    pdf.add_page()

    # --- DATOS DE PRESTAMOS Y DESVIOS ---
    pdf.chapter_title('1. Préstamos Vigentes (Desvíos a Recuperar)')
    
    deudas = []
    tot_d = 0
    tipo_codigos = {
        "Decreto":  "D",
        "Propios":  "P",
        "Legacy":   "L",
        "Reserva":  "R",
    }

    desvios_activos = db.get_desvios_activos_completos()
    for d in (desvios_activos or []):
        origen_str = f"Dto. {d['orig_nro']}/{d['orig_anio']} - {d['orig_nombre']}"
        if d['decreto_destino_id']:
            destino_str = f"Dto. {d['dest_nro']}/{d['dest_anio']} - {limpiar_prefijo_expediente(d['dest_nombre'])}"
        elif d.get('gasto_nombre'):
            destino_str = f"FUN: {d['gasto_nombre']} (Exp: {d['gasto_expediente_imuh']})"
        else:
            destino_str = limpiar_prefijo_expediente(d['destino_texto'])
        tipo_cod = "FUN" if d.get('gasto_nombre') else tipo_codigos["Decreto" if d['decreto_destino_id'] else "Propios"]
        deudas.append([origen_str, destino_str, tipo_cod, format_currency_ar(d['saldo']), ""])
        tot_d += d['saldo']

    prestamos_legacy = db.get_prestamos()
    for p in (prestamos_legacy or []):
        s_p = p['monto'] - p.get('total_devuelto', 0)
        if s_p > 0.01:
            deudas.append([f"Dto. {p['nro_decreto']}/{p['decreto_anio']}", limpiar_prefijo_expediente(p['destino']), tipo_codigos["Legacy"], format_currency_ar(s_p), p.get('motivo', '') or ""])
            tot_d += s_p

    # Préstamos desde Reserva (cobro_reserva_usos a otras obras)
    reserva_prestamos = db.get_reserva_usos_prestamos_activos()
    for rp in (reserva_prestamos or []):
        origen_str = f"Dto. {rp['orig_nro']}/{rp['orig_anio']} - {rp['orig_nombre']}"
        if rp['decreto_destino_id']:
            destino_str = f"Dto. {rp['dest_nro']}/{rp['dest_anio']} - {limpiar_prefijo_expediente(rp['dest_nombre'])}"
        elif rp.get('gasto_nombre'):
            destino_str = f"FUN: {rp['gasto_nombre']} (Exp: {rp['gasto_expediente_imuh']})"
        else:
            destino_str = limpiar_prefijo_expediente(rp['destino_detalle']) or "Obra sin decreto"
        notas_str = rp.get('notes_str') if 'notes_str' in locals() else (rp.get('notas') or "")
        tipo_cod = "FUN" if rp.get('gasto_nombre') else tipo_codigos["Reserva"]
        deudas.append([origen_str, destino_str, tipo_cod, format_currency_ar(rp['saldo']), notas_str])
        tot_d += rp['saldo']
            
    if deudas:
        deudas.append(["TOTAL", "", "", format_currency_ar(tot_d), ""])
        df_d = pd.DataFrame(deudas, columns=["Origen", "Destino", "T", "Saldo Pendiente", "Observaciones"])
        # Ajustado a 190mm totales para alinear con los márgenes por defecto de FPDF (barras celestes)
        pdf.add_table(df_d, col_widths=[55, 55, 10, 30, 40])
        pdf.chapter_note("Leyenda - T (Tipo):  D = Desvio a Obra con Decreto  |  R = Prestamo desde Reserva  |  P = Obra de Fondos Propios  |  L = Prestamo Legado  |  FUN = Gasto de Funcionamiento")
    else:
        pdf.chapter_body("No hay desvíos ni préstamos pendientes de devolución.")

    # --- DATOS DE RESERVAS ---
    pdf.chapter_title('2. Dinero en Reserva Disponible')
    reservas = []
    tot_r = 0
    cobros_dist = db.get_cobros_con_resumen_distribucion()
    for c in (cobros_dist or []):
        if c['monto_reserva'] > 0:
            usos = db.get_reserva_usos_by_cobro(c['id'])
            tot_usado = sum(u['monto'] for u in usos) if usos else 0
            saldo_r = c['monto_reserva'] - tot_usado
            if saldo_r > 0.01:
                reservas.append([f"Dto. {c['nro_decreto']}/{c['decreto_anio']} - {c['destino_fondos']}", c['fecha'], format_currency_ar(saldo_r)])
                tot_r += saldo_r
                
    if reservas:
        reservas.append(["TOTAL", "", format_currency_ar(tot_r)])
        df_r = pd.DataFrame(reservas, columns=["Decreto Origen", "Fecha Cobro", "Saldo Disponible"])
        pdf.add_table(df_r, col_widths=[120, 30, 40])
    else:
        pdf.chapter_body("No hay fondos guardados en reserva actualmente.")

    # --- DATOS DE CUOTAS PENDIENTES ---
    pdf.chapter_title('3. Cuotas Pendientes de Cobro')
    
    decretos = db.get_decretos()
    cuotas = []
    # Filtrar solo vigentes
    decretos_vigentes = {d['id']: d for d in decretos if d['estado'] != 'Anulado'}
    
    for d_id, d in decretos_vigentes.items():
        for c in db.get_cuotas_by_decreto(d_id):
            c['estado_decreto'] = d['estado']
            c['destino_fondos'] = d['destino_fondos']
            c['nro_decreto'] = d['nro_decreto']
            c['anio_decreto'] = d['anio']
            cuotas.append(c)
            
    cobros = db.get_all_cobros()
    df_cobros = pd.DataFrame(cobros) if cobros else pd.DataFrame()
    
    pendientes_filas = []
    tot_pendiente = 0
    
    for q in cuotas:
        # Calcular cobrado para esta cuota específica
        q_cobrado = df_cobros[df_cobros['cuota_id'] == q['id']]['monto'].sum() if not df_cobros.empty else 0
        saldo = q['monto'] - q_cobrado
        
        if saldo > 0.01:
            nombre_corto = q['destino_fondos']
            decreto_str = f"Dto. {q['nro_decreto']}/{q['anio_decreto']} - {nombre_corto}"
            periodo_str = f"{q['mes']:02d}/{q['anio']}"
            
            # Usamos anio * 100 + mes para ordenar cronológicamente
            sort_key_periodo = q['anio'] * 100 + q['mes']
            
            pendientes_filas.append({
                'decreto': decreto_str,
                'periodo': periodo_str,
                'sort_periodo': sort_key_periodo,
                'saldo': saldo,
                'saldo_str': format_currency_ar(saldo)
            })
            tot_pendiente += saldo
            
    if pendientes_filas:
        # Ordenar por Periodo (ASC), luego Saldo (ASC)
        pendientes_filas.sort(key=lambda x: (x['sort_periodo'], x['saldo']))
        
        filas_tabla = []
        for p in pendientes_filas:
            filas_tabla.append([p['decreto'], p['periodo'], p['saldo_str']])
            
        # Fila TOTAL
        filas_tabla.append(["TOTAL", "", format_currency_ar(tot_pendiente)])
        
        df_p = pd.DataFrame(filas_tabla, columns=["Decreto", "Periodo", "A Percibir"])
        # Ancho total 190mm
        pdf.add_table(df_p, col_widths=[130, 25, 35])
    else:
        pdf.chapter_body("No hay cuotas pendientes ni atrasadas.")

    # --- DATOS DE APORTES HABITUALES PENDIENTES ---
    pdf.chapter_title('4. Seguimiento de solicitudes de aportes para haberes')
    
    habituales = get_resumen_habituales_pendientes()
    if habituales:
        filas_h = []
        tot_h = 0
        for h in habituales:
            filas_h.append([h['tipo'], h['periodo'], format_currency_ar(h['monto_pedido']), format_currency_ar(h['monto_cobrado']), format_currency_ar(h['saldo'])])
            tot_h += h['saldo']
        
        filas_h.append(["TOTAL", "", "", "", format_currency_ar(tot_h)])
        df_h = pd.DataFrame(filas_h, columns=["Tipo", "Periodo", "Pedido", "Ingresado", "Saldo"])
        pdf.add_table(df_h, col_widths=[30, 40, 40, 40, 40])
    else:
        pdf.chapter_body("No hay aportes de Sueldos o SAC con saldo pendiente.")

    # --- DATOS DE INDICADORES (KPIs) ---
    pdf.chapter_title('5. Indicadores Generales')
    
    # KPIs requieren los DataFrames completos, no filtrados por vigentes
    df_decretos = pd.DataFrame(decretos)
    df_cuotas = pd.DataFrame(cuotas)
    
    if not df_cuotas.empty and not df_decretos.empty:
        # Requerido por get_dashboard_kpis
        def calc_monto_efectivo(row):
            if row['estado_decreto'] == 'Anulado':
                cobrado = df_cobros[df_cobros['cuota_id'] == row['id']]['monto'].sum() if not df_cobros.empty else 0
                return cobrado
            return row['monto']
        df_cuotas['monto_efectivo'] = df_cuotas.apply(calc_monto_efectivo, axis=1)
        
        fun = db.get_aportes_funcionamiento()
        sueldos = db.get_aportes_sueldo()
        pct_cobranza, pct_a_tiempo, pct_atrasado = get_dashboard_kpis(df_cuotas, df_cobros, cobros, fun, sueldos)
        
        pdf.set_font('Arial', 'B', 10)
        pdf.cell(60, 8, "% Cobranza ult. 12m:", 0, 0, 'L')
        pdf.set_font('Arial', '', 10)
        pdf.cell(0, 8, f"{pct_cobranza:.1f}%", 0, 1, 'L')
        
        pdf.set_font('Arial', 'B', 10)
        pdf.cell(60, 8, "Histórico en Tiempo y Forma:", 0, 0, 'L')
        pdf.set_font('Arial', '', 10)
        pdf.cell(0, 8, f"{pct_a_tiempo:.1f}%", 0, 1, 'L')
        
        pdf.set_font('Arial', 'B', 10)
        pdf.cell(60, 8, "Histórico Atrasado:", 0, 0, 'L')
        pdf.set_font('Arial', '', 10)
        pdf.cell(0, 8, f"{pct_atrasado:.1f}%", 0, 1, 'L')
        pdf.ln(5)
    else:
        pdf.chapter_body("No hay datos suficientes para calcular indicadores.")
        
    # Guardar en disco
    pdf.output(filepath, 'F')
    return filepath

def generar_reporte_solicitudes_pdf(filepath):
    pdf = ReporteFinancieroPDF()
    pdf.alias_nb_pages()
    pdf.add_page()
    
    # Titulo de la sección principal
    pdf.chapter_title('Estado de Solicitudes de Financiamiento')
    
    # Obtener todas las solicitudes
    solicitudes = db.get_solicitudes()
    
    filas = []
    tot_solicitado = 0
    tot_aprobado = 0
    tot_pendiente = 0
    
    for s in (solicitudes or []):
        monto = s['monto_solicitado']
        tot_solicitado += monto
        if s['estado'] == 'Aprobado':
            tot_aprobado += monto
        elif s['estado'] == 'Pendiente':
            tot_pendiente += monto
            
        monto_str = format_currency_ar(monto, include_symbol=False)
        fecha_str = s['fecha_solicitud']
        if isinstance(fecha_str, str):
            try:
                dt = datetime.datetime.strptime(fecha_str, '%Y-%m-%d').date()
                fecha_str = dt.strftime("%d-%m-%Y")
            except:
                pass
                
        # Destino
        destino = s['destino_fondos']
        
        # Estado o Nro Decreto
        estado_val = s['estado']
        if s['estado'] == 'Aprobado' and s.get('nro_decreto'):
            estado_val = f"Dto. {s['nro_decreto']}/{s['decreto_anio']}"
            
        filas.append([
            s['nro_expediente'],
            destino,
            fecha_str,
            estado_val,
            monto_str
        ])
        
    if filas:
        filas.append(["TOTAL", "", "", "", format_currency_ar(tot_solicitado, include_symbol=False)])
        df_sol = pd.DataFrame(filas, columns=["Expediente", "Destino / Obra", "Fecha", "Estado", "Monto"])
        # Ancho total 190mm: 45 (Expediente) + 70 (Destino) + 25 (Fecha) + 20 (Estado) + 30 (Monto) = 190
        pdf.add_table(df_sol, col_widths=[45, 70, 25, 20, 30])
        
        # Mostrar resumen ejecutivo
        pdf.ln(5)
        pdf.chapter_title('Resumen de Financiamiento')
        pdf.set_font('Arial', 'B', 10)
        pdf.cell(60, 8, "Total Solicitado:", 0, 0, 'L')
        pdf.set_font('Arial', '', 10)
        pdf.cell(0, 8, format_currency_ar(tot_solicitado, include_symbol=False), 0, 1, 'L')
        
        pdf.set_font('Arial', 'B', 10)
        pdf.cell(60, 8, "Total Aprobado (Decretado):", 0, 0, 'L')
        pdf.set_font('Arial', '', 10)
        pdf.cell(0, 8, format_currency_ar(tot_aprobado, include_symbol=False), 0, 1, 'L')
        
        pdf.set_font('Arial', 'B', 10)
        pdf.cell(60, 8, "Total Pendiente:", 0, 0, 'L')
        pdf.set_font('Arial', '', 10)
        pdf.cell(0, 8, format_currency_ar(tot_pendiente, include_symbol=False), 0, 1, 'L')
        
        tasa = (tot_aprobado / tot_solicitado * 100) if tot_solicitado > 0 else 0
        pdf.set_font('Arial', 'B', 10)
        pdf.cell(60, 8, "Tasa de Aprobación:", 0, 0, 'L')
        pdf.set_font('Arial', '', 10)
        pdf.cell(0, 8, f"{tasa:.1f}%", 0, 1, 'L')
    else:
        pdf.chapter_body("No hay solicitudes de financiamiento registradas en el sistema.")
        
    pdf.output(filepath, 'F')
    return filepath

def generar_reporte_composicion_pdf(filepath, decreto_info, cuota_info, df_comp, aclaraciones=None):
    pdf = ReporteFinancieroPDF()
    pdf.alias_nb_pages()
    pdf.add_page()
    
    pdf.chapter_title('Composición del Estado Actual de Fondos')
    
    # 1. Información General
    pdf.set_font('Arial', 'B', 10)
    pdf.cell(50, 6, "Decreto:", 0, 0, 'L')
    pdf.set_font('Arial', '', 10)
    pdf.cell(0, 6, decreto_info['identificacion'], 0, 1, 'L')
    
    pdf.set_font('Arial', 'B', 10)
    pdf.cell(50, 6, "Expediente IMUH:", 0, 0)
    pdf.set_font('Arial', '', 10)
    pdf.multi_cell(0, 6, decreto_info['expediente_imuh'])
    
    pdf.set_font('Arial', 'B', 10)
    pdf.cell(50, 6, "Nombre de la Obra:", 0, 0, 'L')
    pdf.set_font('Arial', '', 10)
    pdf.multi_cell(0, 6, decreto_info['destino'])
    pdf.ln(2)
    
    # 2. Identificación de la Cuota
    pdf.set_font('Arial', 'B', 10)
    pdf.cell(50, 6, "Cuota N°:", 0, 0, 'L')
    pdf.set_font('Arial', '', 10)
    pdf.cell(0, 6, str(cuota_info['numero']), 0, 1, 'L')
    
    pdf.set_font('Arial', 'B', 10)
    pdf.cell(50, 6, "Importe de la Cuota:", 0, 0, 'L')
    pdf.set_font('Arial', '', 10)
    pdf.cell(0, 6, format_currency_ar(cuota_info['importe'], include_symbol=False), 0, 1, 'L')
    
    pdf.set_font('Arial', 'B', 10)
    pdf.cell(50, 6, "Fechas de Cobro:", 0, 0, 'L')
    pdf.set_font('Arial', '', 10)
    pdf.multi_cell(0, 6, cuota_info['fechas_cobro'])
    pdf.ln(4)
    
    # 3. Aclaraciones generales si existen
    if aclaraciones and aclaraciones.strip():
        pdf.set_font('Arial', 'B', 10)
        pdf.cell(0, 6, "Aclaraciones generales de la distribución:", 0, 1, 'L')
        pdf.set_font('Arial', 'I', 9)
        pdf.multi_cell(0, 5, aclaraciones.strip())
        pdf.ln(4)
        
    # 4. Tabla de composición (Fecha, Destino, OP, Aclaraciones, Monto)
    pdf.add_table(df_comp, col_widths=[25, 65, 25, 50, 25])
    
    pdf.output(filepath, 'F')
    return filepath

def generar_reporte_desvios_pdf(filepath, titulo_reporte, obra_info, df_desvios, col_widths=None):
    pdf = ReporteFinancieroPDF()
    pdf.alias_nb_pages()
    pdf.add_page()
    
    pdf.chapter_title(titulo_reporte)
    
    # 1. Información General de la Obra
    pdf.set_font('Arial', 'B', 10)
    pdf.cell(50, 6, "Obra Seleccionada:", 0, 0, 'L')
    pdf.set_font('Arial', '', 10)
    pdf.cell(0, 6, obra_info.get('destino_fondos', 'N/A'), 0, 1, 'L')
    
    pdf.set_font('Arial', 'B', 10)
    pdf.cell(50, 6, "Expediente IMUH:", 0, 0, 'L')
    pdf.set_font('Arial', '', 10)
    pdf.cell(0, 6, obra_info.get('expediente_imuh', 'Sin asignar'), 0, 1, 'L')
    
    pdf.set_font('Arial', 'B', 10)
    pdf.cell(50, 6, "Asociado a Decreto:", 0, 0, 'L')
    pdf.set_font('Arial', '', 10)
    pdf.cell(0, 6, obra_info.get('decreto_identificacion', 'N/A'), 0, 1, 'L')
    
    pdf.set_font('Arial', 'B', 10)
    pdf.cell(50, 6, "Total Saldo Pendiente:", 0, 0, 'L')
    pdf.set_font('Arial', 'B', 10)
    pdf.cell(0, 6, format_currency_ar(obra_info.get('total_saldo_pendiente', 0.0)), 0, 1, 'L')
    pdf.ln(5)
    
    # 2. Tabla de desvíos
    if col_widths is None:
        col_widths = [18, 40, 22, 22, 22, 22, 16, 28] # Suma = 190
    
    pdf.add_table(df_desvios, col_widths)
    
    pdf.output(filepath, 'F')
    return filepath

def generar_reporte_gastos_funcionamiento_financiados_obra_pdf(filepath, df_gastos):
    pdf = ReporteFinancieroPDF(orientation='L')
    pdf.alias_nb_pages()
    pdf.add_page()
    
    pdf.chapter_title("Gastos de Funcionamiento Financiados con Aportes de Obra")
    
    # 1. Resumen
    total_adeudado = 0.0
    for _, row in df_gastos.iterrows():
        val = str(row['Importe adeudado']).replace('$', '').replace('.', '').replace(',', '.').strip()
        try:
            total_adeudado += float(val)
        except ValueError:
            pass
            
    pdf.set_font('Arial', 'B', 10)
    pdf.cell(50, 6, "Total Adeudado Pendiente:", 0, 0, 'L')
    pdf.set_font('Arial', 'B', 10)
    pdf.cell(0, 6, format_currency_ar(total_adeudado), 0, 1, 'L')
    pdf.cell(50, 6, "Cantidad de Registros:", 0, 0, 'L')
    pdf.set_font('Arial', '', 10)
    pdf.cell(0, 6, str(len(df_gastos)), 0, 1, 'L')
    pdf.ln(5)
    
    # 9 columns. Printable width in landscape = 277mm.
    col_widths = [22, 28, 50, 40, 25, 32, 40, 20, 20]
    
    pdf.add_table(df_gastos, col_widths)
    pdf.output(filepath, 'F')
    return filepath

if __name__ == '__main__':
    generar_reporte_pdf("test_report.pdf")
    print("Reporte generado exitosamente.")
