import database as db
import utils
from collections import defaultdict

# ── Constantes ────────────────────────────────────────────────────────────────
BOX_W     = 220    # ancho fijo de cada nodo
LINE_H    = 17     # alto de cada línea de texto (px)
PAD_X     = 12     # padding horizontal dentro del nodo
PAD_Y     = 9      # padding vertical dentro del nodo (arriba Y abajo)
COL_GAP   = 100    # espacio horizontal entre columnas
ROW_GAP   = 18     # espacio vertical entre nodos de la misma columna
SVG_PAD   = 30     # padding exterior del SVG
FONT_SIZE = 13     # tamaño de fuente (no cambiar)
CHAR_W    = 7.0    # ancho promedio de carácter px (Segoe UI 13px)
MAX_CHARS = int((BOX_W - 2 * PAD_X) / CHAR_W)  # ≈ 28 chars/línea
FONT      = "Segoe UI, Arial, sans-serif"

COLORS = {
    'decreto':  {'bg': '#dbeafe', 'border': '#1e88e5', 'text': '#1e3a8a'},
    'cobro':    {'bg': '#dcfce7', 'border': '#16a34a', 'text': '#14532d'},
    'fin':      {'bg': '#fef3c7', 'border': '#d97706', 'text': '#92400e'},
    'reserva':  {'bg': '#f3e8ff', 'border': '#7c3aed', 'text': '#4c1d95'},
    'desvio':   {'bg': '#fee2e2', 'border': '#dc2626', 'text': '#7f1d1d'},
    'recupero': {'bg': '#fefce8', 'border': '#ca8a04', 'text': '#713f12'},
    'destino':  {'bg': '#f5f5f5', 'border': '#9e9e9e', 'text': '#424242'},
}
ARROW_COLORS = {
    'decreto': '#1e88e5', 'cobro': '#16a34a', 'fin': '#d97706',
    'reserva': '#7c3aed', 'desvio': '#dc2626', 'recupero': '#ca8a04',
    'destino': '#9e9e9e',
}


def _esc(t):
    return str(t).replace('&','&amp;').replace('<','&lt;').replace('>','&gt;').replace('"','&quot;')


def _wrap(text, max_chars):
    """Divide texto en líneas de hasta max_chars caracteres, cortando en espacios."""
    if not text:
        return ['']
    words = str(text).split(' ')
    lines, cur = [], ''
    for w in words:
        if not cur:
            cur = w
        elif len(cur) + 1 + len(w) <= max_chars:
            cur += ' ' + w
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines or ['']


def _node_height(label):
    """Calcula la altura necesaria del nodo según el texto."""
    parts = label.split(' | ', 1)
    n = len(_wrap(parts[0], MAX_CHARS))
    if len(parts) > 1:
        n += len(_wrap(parts[1], MAX_CHARS))
    return 2 * PAD_Y + n * LINE_H


def _draw_box(x, y, label, tipo, out):
    """Renderiza un nodo SVG con texto en múltiples líneas si es necesario."""
    c  = COLORS.get(tipo, COLORS['destino'])
    bh = _node_height(label)
    cx = x + BOX_W // 2

    out.append(
        f'<rect x="{x}" y="{y}" width="{BOX_W}" height="{bh}" rx="10" '
        f'fill="{c["bg"]}" stroke="{c["border"]}" stroke-width="2.5"/>'
    )

    parts       = label.split(' | ', 1)
    title_lines = _wrap(parts[0], MAX_CHARS)
    sub_lines   = _wrap(parts[1], MAX_CHARS) if len(parts) > 1 else []
    all_lines   = [(l, True) for l in title_lines] + [(l, False) for l in sub_lines]

    # Centrar verticalmente el bloque de texto
    text_block_h = len(all_lines) * LINE_H
    y0 = y + (bh - text_block_h) / 2 + LINE_H * 0.78  # baseline primera línea

    for i, (line, bold) in enumerate(all_lines):
        yt  = y0 + i * LINE_H
        bld = 'font-weight="bold" ' if bold else ''
        out.append(
            f'<text x="{cx}" y="{yt:.1f}" text-anchor="middle" '
            f'font-family="{FONT}" font-size="{FONT_SIZE}" {bld}'
            f'fill="{c["text"]}">{_esc(line)}</text>'
        )


def generar_svg_trazabilidad(cobro_id):
    """
    Genera un SVG completo con el flujo de fondos del cobro.
    Retorna (svg_string, total_w, total_h) o ('', 0, 0) si no hay datos.
    """
    cobro = db.get_cobro(cobro_id)
    if not cobro:
        return '', 0, 0

    dist      = db.get_distribucion_by_cobro(cobro_id)
    monto_fo  = dist['monto_fin_orig'] if dist else 0.0
    monto_res = dist['monto_reserva']  if dist else 0.0
    desvios   = db.get_desvios_by_cobro(cobro_id) or []
    usos_fo   = db.get_fin_original_usos_by_cobro(cobro_id) or []
    usos_res  = db.get_reserva_usos_by_cobro(cobro_id) or []

    # ── Árbol de nodos ────────────────────────────────────────────────────────
    nodes = []

    def add(col, label, tipo, parent=None):
        idx = len(nodes)
        nodes.append({'col': col, 'label': label, 'tipo': tipo, 'parent': parent})
        return idx

    # Col 0: Decreto
    d_idx = add(0, f'Decreto {cobro.get("nro_decreto","S/N")}/{cobro.get("decreto_anio","S/A")}', 'decreto')
    # Col 1: Cobro
    c_idx = add(1,
        f'Cobro {utils.format_date_ar(cobro["fecha"])} | {utils.format_currency_ar(cobro["monto"])}',
        'cobro', d_idx)

    if monto_fo > 0.01:
        fo_i = add(2, f'Fin Original | {utils.format_currency_ar(monto_fo)}', 'fin', c_idx)
        for u in usos_fo:
            op = f' | OP {u["nro_op"]}' if u.get('nro_op') else ''
            add(3, f'Pago {utils.format_date_ar(u["fecha"])}{op} | {utils.format_currency_ar(u["monto"])}', 'fin', fo_i)

    if monto_res > 0.01:
        r_i = add(2, f'En Reserva | {utils.format_currency_ar(monto_res)}', 'reserva', c_idx)
        for u in usos_res:
            op = f' | OP {u["nro_op"]}' if u.get('nro_op') else ''
            fecha_str = f' {utils.format_date_ar(u["fecha"])}' if u.get('fecha') else ''
            ur_i = add(3, f'Uso Reserva{fecha_str}{op} | {utils.format_currency_ar(u["monto"])}', 'reserva', r_i)
            if u.get('destino_tipo') == 'fin_original':
                dd = db.get_decreto(cobro['decreto_id'])
                dn = f'Dto. {dd["nro_decreto"]}/{dd["anio"]}'
                add(4, f'Obra: {dn}', 'fin', ur_i)
            elif u.get('decreto_destino_id'):
                dd = db.get_decreto(u['decreto_destino_id'])
                obras = db.get_obras_by_decreto(u['decreto_destino_id'])
                if obras:
                    imuhs = ", ".join(o["expediente_imuh"] for o in obras if o.get("expediente_imuh"))
                    nombres = " // ".join(o["nombre"] for o in obras if o.get("nombre"))
                    dn = f'Dto. {dd["nro_decreto"]}/{dd["anio"]} - Exp. IMUH {imuhs} - {nombres}'
                else:
                    dn = f'Dto. {dd["nro_decreto"]}/{dd["anio"]} - Exp. IMUH S/D - {dd.get("destino_fondos","")}'
                dt_i = add(4, f'Obra: {dn}', 'destino', ur_i)
            else:
                dn = u.get('destino_detalle') or 'Destino no especificado'
                dt_i = add(4, f'Obra: {dn}', 'destino', ur_i)
                
            for r in (db.get_recuperos_by_reserva_uso(u['id']) or []):
                if r.get('destino_tipo') == 'compensacion':
                    add(5, f'Compensacion OP: {r.get("nro_op","")} | {utils.format_currency_ar(r["monto"])}', 'recupero', dt_i)
                else:
                    add(5, f'Devolucion {utils.format_date_ar(r["fecha"])} | {utils.format_currency_ar(r["monto"])}', 'recupero', dt_i)

    for d in desvios:
        op    = f' | OP {d["nro_op"]}' if d.get('nro_op') else ''
        fecha_str = f' {utils.format_date_ar(d["fecha"])}' if d.get('fecha') else ''
        dv_i  = add(2, f'Desvio{fecha_str}{op} | {utils.format_currency_ar(d["monto"])}', 'desvio', c_idx)
        if d.get('decreto_destino_id'):
            dd = db.get_decreto(d['decreto_destino_id'])
            obras = db.get_obras_by_decreto(d['decreto_destino_id'])
            if obras:
                imuhs = ", ".join(o["expediente_imuh"] for o in obras if o.get("expediente_imuh"))
                nombres = " // ".join(o["nombre"] for o in obras if o.get("nombre"))
                dn = f'Dto. {dd["nro_decreto"]}/{dd["anio"]} - Exp. IMUH {imuhs} - {nombres}'
            else:
                dn = f'Dto. {dd["nro_decreto"]}/{dd["anio"]} - Exp. IMUH S/D - {dd.get("destino_fondos","")}'
        else:
            dn = d.get('destino') or 'Destino no especificado'
        dt_i = add(3, f'Obra: {dn}', 'destino', dv_i)
        for r in (db.get_recuperos_by_desvio(d['id']) or []):
            if r.get('destino_tipo') == 'compensacion':
                add(4, f'Compensacion OP: {r.get("nro_op","")} | {utils.format_currency_ar(r["monto"])}', 'recupero', dt_i)
            else:
                add(4, f'Devolucion {utils.format_date_ar(r["fecha"])} | {utils.format_currency_ar(r["monto"])}', 'recupero', dt_i)

    # ── Layout: posición (x, y, h) por nodo ──────────────────────────────────
    cols = defaultdict(list)
    for i, n in enumerate(nodes):
        cols[n['col']].append(i)

    max_col = max(cols.keys())

    def col_h(col_idx):
        ns = cols.get(col_idx, [])
        if not ns:
            return 0
        return sum(_node_height(nodes[i]['label']) for i in ns) + ROW_GAP * (len(ns) - 1)

    max_h   = max(col_h(c) for c in cols)
    total_w = SVG_PAD + (max_col + 1) * (BOX_W + COL_GAP) - COL_GAP + SVG_PAD
    total_h = SVG_PAD + max_h + SVG_PAD

    positions = {}  # node_idx -> (x, y, box_h)
    for col_idx, col_nodes in cols.items():
        x       = SVG_PAD + col_idx * (BOX_W + COL_GAP)
        ch      = col_h(col_idx)
        y_start = SVG_PAD + (max_h - ch) // 2
        y       = y_start
        for ni in col_nodes:
            bh = _node_height(nodes[ni]['label'])
            positions[ni] = (x, y, bh)
            y += bh + ROW_GAP

    # ── SVG ───────────────────────────────────────────────────────────────────
    svg = [
        f'<svg xmlns="http://www.w3.org/2000/svg" '
        f'width="{total_w}" height="{total_h}" '
        f'viewBox="0 0 {total_w} {total_h}" '
        f'style="display:block;background:#fff;">'
    ]

    # Marcadores de flecha (uno por color usado)
    svg.append('<defs>')
    seen = set()
    for n in nodes:
        if n['parent'] is not None:
            c = ARROW_COLORS.get(nodes[n['parent']]['tipo'], '#9e9e9e')
            if c not in seen:
                seen.add(c)
                hx = c.replace('#', '')
                svg.append(
                    f'<marker id="a-{hx}" markerWidth="10" markerHeight="7" '
                    f'refX="9" refY="3.5" orient="auto">'
                    f'<polygon points="0 0,10 3.5,0 7" fill="{c}"/></marker>'
                )
    svg.append('</defs>')

    # Flechas (detrás de los nodos)
    for i, n in enumerate(nodes):
        if n['parent'] is None or n['parent'] not in positions:
            continue
        px, py, ph = positions[n['parent']]
        nx, ny, nh = positions[i]
        x1 = px + BOX_W;  y1 = py + ph / 2
        x2 = nx;           y2 = ny + nh / 2
        mx = (x1 + x2) / 2
        c  = ARROW_COLORS.get(nodes[n['parent']]['tipo'], '#9e9e9e')
        hx = c.replace('#', '')
        svg.append(
            f'<path d="M {x1:.1f} {y1:.1f} C {mx:.1f} {y1:.1f} {mx:.1f} {y2:.1f} {x2:.1f} {y2:.1f}" '
            f'fill="none" stroke="{c}" stroke-width="2" marker-end="url(#a-{hx})"/>'
        )

    # Nodos (encima de las flechas)
    for i, n in enumerate(nodes):
        if i in positions:
            x, y, _ = positions[i]
            _draw_box(x, y, n['label'], n['tipo'], svg)

    svg.append('</svg>')
    return '\n'.join(svg), total_w, total_h


def mostrar_mapa_trazabilidad(cobro_id):
    import streamlit as st
    import streamlit.components.v1 as components

    cobro = db.get_cobro(cobro_id)
    if not cobro:
        st.info("No se encontró el cobro.")
        return

    dist    = db.get_distribucion_by_cobro(cobro_id)
    desvios = db.get_desvios_by_cobro(cobro_id) or []

    if not dist and not desvios:
        st.info("Este cobro aún no tiene distribución ni desvíos registrados.")
        return

    svg_str, total_w, total_h = generar_svg_trazabilidad(cobro_id)
    if not svg_str:
        st.info("No hay datos suficientes para generar el mapa.")
        return

    # Usar el tamaño natural del SVG para que no se vea minúsculo y usar scroll si es muy ancho
    iframe_h = total_h + 60 if total_h > 0 else 400

    html = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ background: #f8fafc; padding: 10px; }}
  .wrap {{
    background: #fff;
    border-radius: 10px;
    border: 1px solid #e2e8f0;
    padding: 14px;
    overflow-x: auto;
    overflow-y: visible;
  }}
</style>
</head>
<body>
  <div class="wrap">
    {svg_str}
  </div>
</body>
</html>"""

    components.html(html, height=iframe_h, scrolling=True)
