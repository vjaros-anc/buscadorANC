#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
opi_segmentar.py — Etapa 1-2 del protocolo de extracción de OPI (CNDC).

Determinístico, sin LLM. Toma los PDF OPI-*.pdf y produce un JSONL con el texto
limpio y segmentado en secciones canónicas, listo para la Etapa 3 (extracción
LLM de causa / pregunta / respuesta).

Uso:
    python opi_segmentar.py <dir_pdfs> [-o opi_segmentado.jsonl]
"""
import fitz, glob, re, json, os, sys, argparse

# --- Ruido GEDO: membretes, sellos, paginado, firmas digitales ------------
RX_RUIDO = re.compile(
    r'(IF-\d{4}-\d+-APN-\S+'
    r'|RESOL-\d{4}-\d+-APN-\S+'
    r'|P[áa]gina \d+ de \d+'
    r'|Rep[úu]blica Argentina - Poder Ejecutivo Nacional'
    r'|Digitally signed by.*'
    r'|Date: \d{4}\.\d.*'
    r'|Location: Ciudad.*'
    r'|GESTION DOCUMENTAL ELECTRONICA.*'
    r'|\d{4} ?[–-] ?A[ÑN]O DE .*'
    r'|A[ÑN]O DE LA DEFENSA DE LA VIDA.*'
    r'|CIUDAD DE BUENOS AIRES)', re.I)

# --- Encabezado de sección en numeración romana ---------------------------
RX_H = re.compile(
    r'^[ \t]*([IVX]{1,5})\.?\s*-?\s*'
    r'([A-ZÁÉÍÓÚÑ][A-ZÁÉÍÓÚÑ \.,ºª°\-–\d]{4,70})\s*$', re.M)

RX_EXPTE  = re.compile(r'(EX-\d{4}-\d+[- ]*-?APN-\S+|EXP-S01:\d+/\d+)')
RX_REF    = re.compile(r'Referencia:\s*(.+)')
RX_NUM    = re.compile(r'OPI[\s.ºN°Nº]*(\d{2,4})', re.I)
RX_HOJA   = re.compile(r'Hoja Adicional de Firmas')
RX_FIRMA  = re.compile(r'Digitally signed by ([^\n]+)')
RX_LEY    = re.compile(r'Ley\s*N?[°ºo]?\s*(25\.156|27\.442|26\.993)')
RX_ART    = re.compile(r'[Aa]rt[íi]culo\s*(\d{1,2})\s*[°ºo]?\s*(?:inc(?:iso)?\.?\s*([a-h]))?')


def clase(titulo: str) -> str:
    """Mapea el título literal a una sección canónica."""
    t = titulo.upper()
    if 'CONCLUSI' in t:                              return 'conclusion'
    if 'REMISI' in t:                                return 'remision'
    if 'CONFIDENCIAL' in t:                          return 'confidencialidad'
    if re.search(r'AN[AÁ]LISIS|CUESTI[OÓ]N', t):     return 'analisis'
    if re.search(r'SUJETOS|INTERVINIENTES', t):      return 'partes'
    if 'PROCEDIMIENTO' in t:                         return 'procedimiento'
    if re.search(r'CONSULTA|OPERACI[OÓ]N|ANTECEDENTES|CONSIDERANDO', t):
        return 'hechos'
    return 'otras'


def limpiar(t: str) -> str:
    t = RX_RUIDO.sub('', t)
    t = re.sub(r'[ \t]+', ' ', t)
    t = re.sub(r'\n{3,}', '\n\n', t)
    return t.strip()


def procesar(path: str) -> dict:
    doc = fitz.open(path)
    crudo = "\n".join(p.get_text() for p in doc)
    npag = len(doc)
    doc.close()

    refs   = [m.group(1).strip() for m in RX_REF.finditer(crudo)]
    firmas = sorted({m.group(1).strip() for m in RX_FIRMA.finditer(crudo)
                     if 'GESTION DOCUMENTAL' not in m.group(1).upper()})
    exptes = sorted(set(RX_EXPTE.findall(crudo)))

    t = limpiar(crudo)
    hs = [(m.start(), m.end(), m.group(2).strip()) for m in RX_H.finditer(t)]
    secciones, titulos = {}, []
    for i, (s, e, titulo) in enumerate(hs):
        fin = hs[i + 1][0] if i + 1 < len(hs) else len(t)
        k = clase(titulo)
        cuerpo = t[e:fin].strip()
        secciones[k] = (secciones.get(k, '') + '\n\n' + cuerpo).strip()
        titulos.append(titulo)

    m = RX_NUM.search(os.path.basename(path)) or RX_NUM.search(crudo)
    return {
        'archivo':        os.path.basename(path),
        'opi':            m.group(1) if m else None,
        'paginas':        npag,
        'chars':          len(t),
        # ¿Cuántas piezas GEDO trae el PDF? (dictamen + complementario + votos)
        'piezas':         max(1, len(RX_HOJA.findall(crudo))),
        'expedientes':    exptes,
        'referencias':    refs,
        'firmantes':      firmas,
        'ley':            sorted({x for x in RX_LEY.findall(crudo)}),
        'titulos_literales': titulos,
        'secciones':      secciones,
        'tiene_conclusion': 'conclusion' in secciones,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('dir', nargs='?', default='.')
    ap.add_argument('-o', '--out', default='opi_segmentado.jsonl')
    ap.add_argument('--patron', default='OPI-*.pdf')
    a = ap.parse_args()

    files = sorted(glob.glob(os.path.join(a.dir, a.patron)))
    ok = sin_conc = 0
    with open(a.out, 'w', encoding='utf-8') as fh:
        for f in files:
            try:
                r = procesar(f)
            except Exception as e:
                print(f'ERROR {f}: {e}', file=sys.stderr)
                continue
            ok += 1
            sin_conc += not r['tiene_conclusion']
            fh.write(json.dumps(r, ensure_ascii=False) + '\n')
    print(f'{ok}/{len(files)} procesados -> {a.out}  (sin conclusión: {sin_conc})')


if __name__ == '__main__':
    main()
