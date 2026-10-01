#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
03_excel.py — Etapa 4: consolida opi_extraido.jsonl en un Excel de trabajo.

Genera opi_causas.xlsx con 4 hojas:
  1. CAUSAS      — una fila por OPI: pregunta, respuesta, causa. Es la hoja
                   de trabajo para el protocolo de validación (trae columnas
                   vacías VAL_* para completar a mano).
  2. RESUMEN     — conteos por sentido, tipo de pregunta y criterio.
  3. NORMAS      — una fila por artículo citado (para cruzar con Referencia).
  4. CONTROLES   — chequeos automáticos que marcan qué revisar primero.

Uso:
    python 03_excel.py [-o opi_causas.xlsx]
"""
import json, os, re, argparse, collections
from openpyxl import Workbook
from openpyxl.styles import Font, Alignment, PatternFill
from openpyxl.utils import get_column_letter

CAB = Font(bold=True, color="FFFFFF", size=10)
FILL = PatternFill("solid", fgColor="1F4E79")
ALERTA = PatternFill("solid", fgColor="FFF2CC")


def g(d, *ruta, default=None):
    for k in ruta:
        if not isinstance(d, dict):
            return default
        d = d.get(k)
        if d is None:
            return default
    return d


def lista(v):
    if v is None:
        return ""
    if isinstance(v, list):
        return " | ".join(str(x) for x in v)
    return str(v)


def uno(v):
    """El modelo a veces devuelve los enums como lista de un elemento."""
    if isinstance(v, list):
        return str(v[0]) if v else ""
    return str(v) if v is not None else ""


def empresas_txt(v, con_detalle=True):
    """Lista de empresas de un rol -> texto legible para la celda."""
    if not isinstance(v, list):
        return lista(v)
    out = []
    for e in v:
        if not isinstance(e, dict):
            out.append(str(e)); continue
        n = str(e.get('nombre') or '').strip()
        if not n:
            continue
        if con_detalle:
            extra = [str(e[k]) for k in ('pais', 'actividad') if e.get(k)]
            if extra:
                n += " (" + "; ".join(extra) + ")"
        out.append(n)
    return " | ".join(out)


def norma_txt(n):
    if not isinstance(n, dict):
        return str(n)
    p = [str(n.get('norma') or '')]
    if n.get('articulo'):
        p.append("art. " + str(n['articulo']))
    if n.get('inciso'):
        p.append("inc. " + str(n['inciso']))
    return " ".join(x for x in p if x)


def controles(r):
    """Chequeos baratos que priorizan la revisión humana."""
    av = []
    ratio = uno(g(r, 'causa', 'ratio_decidendi')).lower()
    if not ratio:
        av.append("sin ratio_decidendi")
    # La causa no puede ser el resultado repetido.
    elif re.search(r'^(la operaci[oó]n )?no se encuentra sujeta|^se encuentra sujeta', ratio):
        av.append("ratio parece ser el resultado, no la causa")
    elif len(ratio) < 60:
        av.append("ratio muy corta")

    crit = g(r, 'causa', 'criterio')
    crit = [crit] if isinstance(crit, str) else (crit or [])
    if not crit or set(crit) == {'otro'}:
        av.append("criterio = otro")
    if not (g(r, 'empresas', 'compradoras') or g(r, 'empresas', 'objeto')):
        av.append("sin empresas identificadas")
    if not g(r, 'causa', 'fundamento_normativo'):
        av.append("sin fundamento normativo")
    if not g(r, 'trazabilidad', 'parrafos'):
        av.append("sin parrafos citados")
    if g(r, 'trazabilidad', 'confianza') == 'baja':
        av.append("confianza baja")
    if g(r, 'trazabilidad', 'requiere_revision_humana'):
        av.append("voto particular / complementario")

    # Cruce con el campo Referencia de la Hoja de Firmas: etiqueta gratis.
    ref = " ".join(r.get('_referencias') or []).lower()
    sent = uno(g(r, 'respuesta_cndc', 'sentido')).lower()
    if ref:
        dice_no = bool(re.search(r'no sujeta|no notifica|no se encuentra sujeta', ref))
        dice_si = bool(re.search(r'\bsujeta a notificaci|sujeto a obligaci', ref)) and not dice_no
        if dice_no and sent.startswith('sujeta'):
            av.append("CONTRADICE Referencia (dice 'no sujeta')")
        if dice_si and sent.startswith('no_sujeta'):
            av.append("CONTRADICE Referencia (dice 'sujeta')")
    return av


def hoja(wb, titulo, cabeceras, filas, anchos):
    ws = wb.create_sheet(titulo)
    ws.append(cabeceras)
    for c in ws[1]:
        c.font, c.fill = CAB, FILL
        c.alignment = Alignment(vertical="center", wrap_text=True)
    for f in filas:
        ws.append(f)
    for i, w in enumerate(anchos, 1):
        ws.column_dimensions[get_column_letter(i)].width = w
    ws.freeze_panes = "A2"
    if ws.max_row > 1:
        ws.auto_filter.ref = ws.dimensions
    for row in ws.iter_rows(min_row=2):
        for c in row:
            c.alignment = Alignment(vertical="top", wrap_text=True)
    return ws


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--entrada', default='opi_extraido.jsonl')
    ap.add_argument('-o', '--out', default='opi_causas.xlsx')
    a = ap.parse_args()

    if not os.path.exists(a.entrada):
        raise SystemExit("No existe " + a.entrada + ". Corré antes 02_extraer.py")
    R = [json.loads(l) for l in open(a.entrada, encoding='utf-8') if l.strip()]
    R.sort(key=lambda r: int(r.get('_opi') or 0))

    wb = Workbook()
    wb.remove(wb.active)

    # ---- 1. CAUSAS ----------------------------------------------------
    filas = []
    for r in R:
        av = controles(r)
        filas.append([
            r.get('_opi'), r.get('_archivo'), r.get('_expediente'),
            lista(r.get('_ley')),
            g(r, 'empresas', 'consultante'),
            empresas_txt(g(r, 'empresas', 'compradoras')),
            empresas_txt(g(r, 'empresas', 'objeto')),
            empresas_txt(g(r, 'empresas', 'vendedoras')),
            lista(g(r, 'pregunta_partes', 'tipo')),
            g(r, 'pregunta_partes', 'texto'),
            g(r, 'pregunta_partes', 'argumento_central_consultante'),
            lista(g(r, 'respuesta_cndc', 'sentido')),
            g(r, 'respuesta_cndc', 'texto'),
            lista(g(r, 'respuesta_cndc', 'medidas_accesorias')),
            g(r, 'causa', 'ratio_decidendi'),
            lista(g(r, 'causa', 'criterio')),
            g(r, 'causa', 'hecho_determinante'),
            " | ".join(norma_txt(n) for n in (g(r, 'causa', 'fundamento_normativo') or [])),
            lista(g(r, 'causa', 'precedentes_citados')),
            lista(g(r, 'trazabilidad', 'parrafos')),
            g(r, 'trazabilidad', 'confianza'),
            " ; ".join(av),
            "", "", "",     # VAL_ok / VAL_causa_corregida / VAL_notas
        ])
    cab = ["OPI", "archivo", "expediente", "ley",
           "consultante", "EMPRESAS_compradoras", "EMPRESAS_objeto",
           "EMPRESAS_vendedoras",
           "pregunta_tipo", "pregunta_texto", "argumento_consultante",
           "respuesta_sentido", "respuesta_texto", "medidas_accesorias",
           "CAUSA_ratio_decidendi", "causa_criterio", "hecho_determinante",
           "fundamento_normativo", "precedentes", "parrafos", "confianza",
           "alertas_automaticas",
           "VAL_ok (s/n)", "VAL_causa_corregida", "VAL_notas"]
    ws = hoja(wb, "CAUSAS", cab, filas,
              [7, 16, 26, 10, 26, 42, 42, 36, 22, 50, 45, 22, 55, 28, 60, 30,
               45, 28, 20, 12, 11, 34, 12, 50, 40])
    # Resalta las filas con alertas.
    for i, r in enumerate(R, start=2):
        if controles(r):
            for c in ws[i]:
                c.fill = ALERTA

    # ---- 2. RESUMEN ---------------------------------------------------
    def valores(v):
        return v if isinstance(v, list) else [v]

    filas = []
    dims = (
        ("respuesta_sentido", lambda r: valores(g(r, 'respuesta_cndc', 'sentido'))),
        ("pregunta_tipo",     lambda r: valores(g(r, 'pregunta_partes', 'tipo'))),
        ("causa_criterio",    lambda r: valores(g(r, 'causa', 'criterio'))),
    )
    for campo, fn in dims:
        c = collections.Counter(v for r in R for v in fn(r) if v)
        for k, v in c.most_common():
            filas.append([campo, k, v, round(100 * v / max(1, len(R)), 1)])
        filas.append(["", "", "", ""])
    hoja(wb, "RESUMEN", ["dimension", "valor", "casos", "% del corpus"],
         filas, [22, 45, 10, 14])

    # ---- 3. NORMAS ----------------------------------------------------
    filas = []
    for r in R:
        for n in (g(r, 'causa', 'fundamento_normativo') or []):
            if isinstance(n, dict):
                filas.append([r.get('_opi'), n.get('norma'), n.get('articulo'),
                              n.get('inciso'), lista(r.get('_referencias'))])
    hoja(wb, "NORMAS", ["OPI", "norma", "articulo", "inciso", "referencia_GEDO"],
         filas, [7, 18, 11, 9, 70])

    # ---- 3b. EMPRESAS (formato largo: una fila por empresa) -----------
    filas = []
    for r in R:
        for rol in ('compradoras', 'objeto', 'vendedoras'):
            for e in (g(r, 'empresas', rol) or []):
                if not isinstance(e, dict):
                    e = {'nombre': e}
                filas.append([r.get('_opi'), rol[:-1] if rol.endswith('s') else rol,
                              e.get('nombre'), e.get('pais'), e.get('actividad'),
                              e.get('grupo_economico')])
    hoja(wb, "EMPRESAS", ["OPI", "rol", "nombre", "pais", "actividad", "grupo_economico"],
         filas, [7, 14, 42, 18, 45, 30])

    # ---- 4. CONTROLES -------------------------------------------------
    c = collections.Counter(x for r in R for x in controles(r))
    filas = [[k, v] for k, v in c.most_common()]
    filas += [["", ""],
              ["TOTAL OPI", len(R)],
              ["OPI con alguna alerta", sum(1 for r in R if controles(r))],
              ["OPI limpias", sum(1 for r in R if not controles(r))]]
    hoja(wb, "CONTROLES", ["control", "casos"], filas, [50, 10])

    wb.save(a.out)
    print(str(len(R)) + " OPI -> " + a.out)
    print("  con alertas: " + str(sum(1 for r in R if controles(r))) +
          "   limpias: " + str(sum(1 for r in R if not controles(r))))


if __name__ == '__main__':
    main()
