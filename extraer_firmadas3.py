#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
extraer_firmadas3.py  —  Extractor CNDC mejorado (solo CONC).

Versión 3 del extractor de dictámenes. Reutiliza EXACTAMENTE las utilidades de
`extraer_firmadas2.py` (se importa como módulo, no se copia) y REEMPLAZA solo la
extracción de "Empresas involucradas" y "Mercados relevantes", que eran las que
más fallaban. Diagnóstico y correcciones (ver informe):

  FIX 1 — Marcador de rol inline. Cuando la tabla marca el rol dentro de la
          celda del nombre, p.ej. "GAS LINK S.A. (Objeto)", ahora ese marcador
          se usa también para el mercado (antes solo lo leía 'empresas').

  FIX 2 — Fila de encabezado. Una fila de una sola celda que NO es un rótulo de
          rol reconocido (p.ej. "Empresa", "Actividad", "Razón social") ya NO
          apaga la sección 'objeto' activa. Antes, ese header reseteaba la
          recolección y el mercado quedaba vacío aunque el rótulo fuera 'objeto'.

  FIX 3 — Empresas sin rol. Si la tabla de empresas no se divide en
          comprador/objeto y no hay marcador de rol, las empresas ya NO se
          descartan: se listan con rol vacío (rol=null). Antes se perdían todas.

  FIX 4 — Mercado = actividad del 'objeto'. Si NO se puede identificar ninguna
          empresa 'objeto', el mercado se deja VACÍO (no se inventa mezclando
          comprador + objeto). Decisión de precisión sobre completitud.

  FIX 5 — Limpieza de glifos de la Private Use Area (U+E000..U+F8FF), típicos de
          viñetas Wingdings ("") que se colaban al texto de mercados/empresas.

  FIX 8 (v3.1) — Empresas involucradas en el formato NUEVO (dictámenes/
          resoluciones/informes/disposiciones 2024-2026). El parser
          `empresas_afectadas` lee la tabla "Actividades de las empresas
          afectadas" por capa de texto: une nombres partidos en varios
          renglones (sufijo societario + salto vertical), toma el ROL de los
          rótulos de sección ("Grupo comprador", "Objeto", "Empresa Objeto",
          "Grupo vendedor"), descarta palabras de la actividad que se colaban al
          nombre y corta la tabla en Fuente/Conclusiones. Un suplemento por
          prosa (`_af_partes_prosa`) agrega las partes citadas en la frase de la
          operación (objeto adquirido, vendedora) que ninguna tabla lista. Un
          gate por cobertura de rol adopta el parser nuevo sólo en el formato
          moderno; el resto conserva el comportamiento anterior (sin regresión).

  Formato viejo en prosa (0 tablas, dictámenes ~pre-2015): NO se intenta
  adivinar por prosa. Se deja vacío y esos casos se listan aparte en un .txt
  ("*_no_extraibles.txt") para revisión manual.

El resto de campos (Carátula, Grupo/Empresa, fechas, Decisión, Nº Resolución,
Nº Dictamen, Relaciones económicas) usa la misma lógica del original.

Uso:
    python extraer_firmadas3.py                 # ./pdf  -> firmadas3.xlsx
    python extraer_firmadas3.py <carpeta>       # carpeta con PDFs
    python extraer_firmadas3.py <carpeta> <salida.xlsx>

Dependencias: pip install pymupdf openpyxl
"""
import os, re, sys, glob, json, importlib.util

import fitz

# --- Importar el extractor original como base de utilidades ------------------
SCRIPT_ORIG = r"C:\Users\Admin\Documents\ANC\descargas_cndc\extraer_firmadas2.py"

def _cargar_base():
    spec = importlib.util.spec_from_file_location("extraer_firmadas2", SCRIPT_ORIG)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

ext = _cargar_base()


# --- FIX 5: limpieza de glifos Private Use Area (viñetas Wingdings, etc.) -----
_RE_PUA = re.compile("[-]")

def _limpiar_pua(s):
    if not s:
        return s
    s = _RE_PUA.sub(" ", s)
    return re.sub(r"\s+", " ", s).strip(" -–·•\t")


# --------------------------------------------------------------------------- #
# FIX 7: tabla de empresas dibujada con TEXTO (formato nuevo de los dictamenes/
# disposiciones: "Empresa | Actividad", agrupada por "Grupo X", con celdas que
# se parten en varios renglones).  find_tables() de PyMuPDF NO ve estas tablas
# (no tienen lineas vectoriales) -> el extractor por tablas las pierde.  Aca se
# lee la capa de texto con coordenadas: se separa la columna izquierda (Empresa)
# de la derecha (Actividad) por posicion X y se reconstruye cada nombre uniendo
# sus renglones (los nombres van en MAYUSCULAS; la actividad en minusculas).
# --------------------------------------------------------------------------- #
_TT_LEGAL_END = re.compile(
    r"(S\.?\s?A\.?(\.?U|\.?S|\.?I\.?C\.?)?|S\.?R\.?L\.?|S\.?A\.?S\.?|S\.?C\.?A\.?|"
    r"S\.?\s*EN\s*C\.?|L\.?L\.?C\.?|GMBH|(&\s*CO\.?\s*)?KG|B\.?V\.?|N\.?V\.?|"
    r"LTDA?\.?|LTD\.?|INC\.?|CORP\.?|PLC|"
    r"S\.?\s*DE\s*R\.?L\.?(\s*DE\s*C\.?V\.?)?|C\.?V\.?|S\.?A\.?P\.?I\.?)\s*$",
    re.I,
)
_TT_HEADER = re.compile(r"^(empresas?|actividad(es)?|raz[oó]n\s+social|rubro|nombre)\s*$", re.I)
_TT_STOP = re.compile(r"^(IF-\d|P[aá]gina\s+\d|[IVX]{1,4}\.?$|\d{1,3}\.?\s*$)", re.I)


def _tt_activity_left(words, y0):
    """x0 de la columna Actividad = min x0 de palabras de prosa (minusculas, largas)."""
    xs = [w[0] for w in words if w[1] > y0 and re.fullmatch(r"[a-záéíóúñ]{6,}[.,]?", w[4])]
    return (min(xs) - 15) if xs else 300.0


def _tt_filas(words, y0, y1):
    filas = {}
    for w in words:
        if y0 - 1 <= w[1] <= y1 + 1:
            filas.setdefault(round(w[1] / 2.0), []).append(w)
    return [sorted(filas[k]) for k in sorted(filas)]


def _tt_celda_izq(row_words, x_thresh):
    """Texto de la celda IZQUIERDA (Empresa); corta la columna Actividad."""
    if not row_words or row_words[0][0] > x_thresh:
        return ""
    tomar = [row_words[0]]
    for prev, w in zip(row_words, row_words[1:]):
        gap = w[0] - prev[2]
        if gap > 28 and w[0] >= x_thresh - 10:
            break
        if re.match(r"[a-záéíóúñ]", w[4]):        # minuscula = empieza la actividad
            break
        tomar.append(w)
    return re.sub(r"\s+", " ", " ".join(w[4] for w in tomar)).strip()


def _tt_join(buf):
    return re.sub(r"\s+", " ", " ".join(buf)).strip(" ,;-")


def empresas_desde_tabla_texto(path):
    """[{grupo, nombre}] leyendo la tabla 'Empresa|Actividad' de texto. Vacio si no hay."""
    doc = fitz.open(path)
    npag = doc.page_count
    resultados, pag = [], 0
    while pag < npag:
        words = doc[pag].get_text("words")
        hdr = None
        emp = [w for w in words if re.fullmatch(r"empresas?", w[4].strip(), re.I)]
        act = [w for w in words if re.fullmatch(r"actividad(es)?", w[4].strip(), re.I)]
        for e in emp:
            for a in act:
                if abs(e[1] - a[1]) < 4 and e[0] < a[0]:
                    hdr = (e, a)
        if not hdr:
            pag += 1
            continue
        e, a = hdr
        y_start = a[1] + 4
        x_thresh = _tt_activity_left(words, y_start)
        grupo, buffer, prev_y = "", [], None

        def emitir():
            if buffer:
                resultados.append({"grupo": grupo, "nombre": _tt_join(buffer)})

        p, detener = pag, False
        while p < npag and not detener:
            ws = doc[p].get_text("words")
            y0 = y_start if p == pag else 0
            for row in _tt_filas(ws, y0, doc[p].rect.height):
                txt = _tt_celda_izq(row, x_thresh)
                if not txt or _TT_HEADER.match(txt):
                    continue
                y = row[0][1]
                fin_prosa = (re.match(r"(Fuente|An[aá]lisis|Nota)\b", txt, re.I)
                             or (len(txt) > 55 and not _TT_LEGAL_END.search(txt)
                                 and re.search(r"\b(que|de|en|los|las|se|una|por)\b", txt)))
                if (_TT_STOP.match(txt) or fin_prosa) and not _TT_LEGAL_END.search(txt):
                    emitir(); buffer = []; detener = True; break
                gm = re.match(r"Grupo\s+(.+)", txt, re.I)
                if gm:
                    emitir(); buffer = []; grupo = txt.strip(); prev_y = None
                    continue
                if re.match(r"[a-záéíóúñ]|\d", txt):
                    continue
                gap = (y - prev_y) if prev_y is not None else 999
                if buffer and (gap > 24 or _TT_LEGAL_END.search(buffer[-1])):
                    emitir(); buffer = []
                buffer.append(txt); prev_y = y
                if _TT_LEGAL_END.search(txt):
                    emitir(); buffer = []; prev_y = None
            p += 1
        emitir(); buffer = []
        pag = p
    doc.close()
    vistos, out = set(), []
    for r in resultados:
        n = re.sub(r"^[^A-ZÁÉÍÓÚÑ]+", "", r["nombre"]).strip()
        letras = [c for c in n if c.isalpha()]
        if len(n) < 6 or not letras or sum(c.isupper() for c in letras) / len(letras) < 0.7:
            continue
        if _TT_HEADER.match(n) or re.search(
            r"\bLEY\b|\bART[ÍI]CULO\b|\bANEXO\b|EFECTOS|OPERACI[ÓO]N|RELACI[ÓO]N|"
            r"DESCRIPCI[ÓO]N|AN[ÁA]LISIS|ENCUADR|PROCEDIMIENTO|CONSIDER|MERCADO|"
            r"CONCENTRACI[ÓO]N|ECON[ÓO]MIC|NOTIFICAC", n):
            continue
        k = re.sub(r"[^a-z0-9]", "", n.lower())
        if k and k not in vistos:
            vistos.add(k); out.append({"grupo": r["grupo"], "nombre": n})
    return out


# --------------------------------------------------------------------------- #
# FIX 8 (v3.1): parser role-aware de la tabla "Actividades de las empresas
# afectadas" (formato moderno de dictámenes/resoluciones/informes/disposiciones).
# Resuelve los errores concretos observados en los CONC nuevos:
#   * nombres partidos en varios renglones ("TERMINAL INVESTMENTS" + "LIMITED
#     S.A.", "PAREXEL INTERNATIONAL (MA)" + "CORPORATION", "NEW PGA S.R.L. (EX
#     PROCTER" + "& GAMBLE ARGENTINA" + "S.R.L.)") -> se unen por sufijo
#     societario + salto vertical.
#   * rol nulo -> se toma de los rótulos de sección ("Grupo comprador", "Objeto",
#     "Empresa Objeto", "Grupo vendedor", "Grupo Comprador AISA", etc.).
#   * palabras de la actividad que se colaban al nombre ("Prestación DEUTSCHE...")
#     -> la celda de nombre descarta tokens Title-case fuera de paréntesis.
#   * corte de la tabla (Fuente / Conclusiones / segunda sub-tabla).
# Un suplemento por prosa agrega las partes que sólo figuran en el texto (el
# objeto adquirido, la vendedora), que ninguna tabla lista.
# El gate en ex_empresas3 sólo activa esto cuando hay tabla moderna, dejando el
# comportamiento anterior intacto para el corpus histórico (sin regresión).
# --------------------------------------------------------------------------- #
_AF_LEGAL_END = re.compile(
    r"(?:S\.?\s?A\.?(?:\.?[UICF])*\.?|S\.?R\.?L\.?|S\.?A\.?S\.?|S\.?C\.?A\.?|"
    r"S\.?A\.?P\.?I\.?(?:\.?\s*DE\s*C\.?V\.?)?|S\.?\s*EN\s*C\.?|"
    r"L\.?L\.?C\.?|GMBH(?:\s*&\s*CO\.?\s*KG)?|(?:&\s*CO\.?\s*)?KG|"
    r"B\.?V\.?|N\.?V\.?|LTDA\.?|LTD\.?|INC\.?|CORP(?:ORATION)?\.?|PLC|"
    r"A\.?B\.?|A/S|\bOY\b|APS|PTE\.?(?:\s*LTD\.?)?|S\.?L\.?U?\.?|S\.?p\.?A\.?|"
    r"S\.?[àa]\s*r\.?l\.?|SARL|SAS|BHD|SPA)\s*[\.,)]*\s*$",
    re.I)
_AF_CONECTOR = re.compile(r"^(y|e|de|del|la|las|los|en|&|-|–|/|al|el)$", re.I)
_AF_HDR   = re.compile(r"^(empresas?|actividad(es)?|raz[oó]n\s+social|nombre|rubro)\s*$", re.I)
_AF_FUENTE = re.compile(r"^fuente\b", re.I)
_AF_STOPH = re.compile(
    r"^(an[aá]lisis\b|referencias?\b|conclusion|IV\b|V\b|VI\b|III\.\s*\d|"
    r"el\s+presente\s+informe|en\s+consecuencia)", re.I)
_AF_SKIP = re.compile(
    r"^(IF-|RE-|DI-|RESFC-|RESOL|EX-|P[aá]gina\b|Rep[uú]blica Argentina|"
    r"A[nñ]o de|CIUDAD DE|\d{1,3}\s*$)", re.I)


def _af_rol_seccion(txt):
    """rol si la línea ES un rótulo de sección; None si no."""
    t = ext.strip_acentos(txt or "").lower().strip(" .:-–")
    if not t or len(t) > 55:
        return None
    if not re.match(r"^(grupo|empresas?|parte|lado|activos?|bienes|objeto|sociedad)\b", t):
        return None
    if "vendedor" in t:                                              return "vendedor"
    if "objeto" in t or "adquirid" in t or "transferid" in t:       return "objeto"
    if "comprador" in t or "adquirent" in t or "adquirient" in t:   return "comprador"
    if re.match(r"^grupo\b", t):                                     return "comprador"
    return None


def _af_activity_x(words, y0, a_x0):
    """Borde izquierdo de la columna Actividad, medido con palabras de prosa
    (minúsculas) CERCA del encabezado -> ignora la prosa del margen izquierdo
    (notas al pie) que contaminaba el corte."""
    xs = [w[0] for w in words
          if w[1] > y0 and w[0] > a_x0 - 55
          and re.fullmatch(r"[a-záéíóúñü]{5,}[.,;)]?", w[4])]
    return (min(xs) - 12) if len(xs) >= 4 else a_x0 - 6


def _af_anchor(doc):
    """(page, y_start, a_x0) del encabezado 'Empresa | Actividad' validado
    exigiendo una razón social (o rótulo) en la columna izquierda debajo."""
    for p in range(doc.page_count):
        words = doc[p].get_text("words")
        W = doc[p].rect.width
        emp = [w for w in words if re.fullmatch(r"empresas?", w[4], re.I)]
        act = [w for w in words if re.fullmatch(r"actividad(es)?", w[4], re.I)]
        cands = []
        for e in emp:
            for a in act:
                if abs(e[1] - a[1]) < 6 and a[0] > e[0] + 40 \
                   and e[0] < W * 0.55 and a[0] > W * 0.30:
                    cands.append((min(e[1], a[1]), a))
        cands.sort()
        for y, a in cands:
            xt = a[0] - 6
            for w in words:
                if y + 6 < w[1] < y + 95 and w[0] < xt:
                    linea = " ".join(x[4] for x in words
                                     if abs(x[1] - w[1]) < 3 and x[0] < xt)
                    if ext._RE_LEGAL.search(linea) or _af_rol_seccion(linea):
                        return p, a[1] + 4, a[0]
    return None


def _af_raw_izq(row, x_thresh):
    toks = [w[4] for w in sorted(row, key=lambda w: w[0])
            if (w[0] + w[2]) / 2 < x_thresh]
    return re.sub(r"\s+", " ", " ".join(toks)).strip()


def _af_raw_full(row):
    toks = [w[4] for w in sorted(row, key=lambda w: w[0])]
    return re.sub(r"\s+", " ", " ".join(toks)).strip()


def _af_celda_izq(row, x_thresh):
    """Columna Empresa: descarta palabras de la actividad (Title-case a nivel 0
    de paréntesis).  Conserva MAYÚSCULAS, conectores y todo lo que va dentro de
    paréntesis, p.ej. '(anteriormente, FIELDFARE ARGENTINA S.R.L.)'."""
    toks, depth = [], 0
    for w in sorted(row, key=lambda w: w[0]):
        if (w[0] + w[2]) / 2 >= x_thresh:
            continue
        t = w[4]
        if depth > 0:
            toks.append(t)
        else:
            up = [c for c in t if c.isalpha()]
            es_may = up and all(c.isupper() for c in up)
            if es_may or _AF_CONECTOR.match(t) \
               or re.fullmatch(r"[\d.,;:&/()\-–\"'°ºNª]+", t) or re.match(r"^[(\"']", t):
                toks.append(t)
        depth = max(0, depth + t.count("(") - t.count(")"))
    return re.sub(r"\s+", " ", " ".join(toks)).strip()


_AF_KW_BLACK = re.compile(
    r"\bLEY\b|\bART[ÍI]CULO\b|\bANEXO\b|EFECTOS|OPERACI[ÓO]N|RELACI[ÓO]N|"
    r"DESCRIPCI[ÓO]N|AN[ÁA]LISIS|ENCUADR|PROCEDIMIENTO|CONSIDER|MERCADO|"
    r"CONCENTRACI[ÓO]N|NOTIFICAC|FUENTE|TABLA|PESOS|D[óo]lar", re.I)


def _af_es_junk(n):
    """True si el ítem es ruido (referencia de sección, alias suelto '(EDET)',
    o fragmento de prosa con varias palabras en minúscula).  NUNCA descarta algo
    con forma societaria (para no perder nombres reales con una fuga pegada)."""
    if re.match(r"^[IVX]{1,4}[.\)]", n) or re.match(r"^\d+\.\d", n):
        return True
    if ext._RE_LEGAL.search(n):
        return False
    # alias/acrónimo suelto: pocas letras, sin forma societaria
    if len(n.split()) <= 2 and re.fullmatch(r"\(?[A-ZÁÉÍÓÚÑ0-9&.\- ]{1,10}\)?", n):
        return True
    # varias palabras en minúscula FUERA de paréntesis -> fragmento de prosa
    fuera = re.sub(r"\([^)]*\)", "", n)
    if len(re.findall(r"\b[a-záéíóúñ]{2,}\b", fuera)) >= 2:
        return True
    return False


def empresas_afectadas(path):
    """[{rol, grupo, nombre}] leyendo la tabla moderna 'Actividades de las
    empresas afectadas'.  [] si el PDF no la tiene (formato viejo)."""
    doc = fitz.open(path)
    anc = _af_anchor(doc)
    if not anc:
        doc.close(); return []
    p0, y_start, a_x0 = anc

    rol, grupo = None, ""
    buffer, prev_y = [], None
    resultados = []
    fuentes, objeto_visto, stop = 0, False, False

    def emitir():
        nonlocal buffer, objeto_visto
        if buffer:
            resultados.append({"rol": rol, "grupo": grupo,
                               "nombre": re.sub(r"\s+", " ", " ".join(buffer)).strip(" ,;-")})
            if rol == "objeto":
                objeto_visto = True
        buffer = []

    for p in range(p0, doc.page_count):
        if stop:
            break
        ws = doc[p].get_text("words")
        y0 = y_start if p == p0 else 0
        x_thresh = _af_activity_x(ws, y0, a_x0)
        for row in _tt_filas(ws, y0, doc[p].rect.height):
            raw = _af_raw_izq(row, x_thresh)
            full = _af_raw_full(row)
            if _AF_SKIP.match(raw) or _AF_SKIP.match(full):
                continue
            if raw and _AF_STOPH.match(raw):
                emitir(); stop = True; break
            if raw and _AF_FUENTE.match(raw):
                emitir(); fuentes += 1
                if objeto_visto or fuentes >= 2:
                    stop = True; break
                rol = None; prev_y = None; continue
            rs = _af_rol_seccion(full) if len(full) < 45 else None
            if rs:
                # una palabra-clave de rol (no aparece en nombres de empresas)
                # confirma el rótulo aunque el tag de grupo termine tipo "...SA"
                # (p.ej. "Grupo Comprador AISA"); si es sólo "Grupo X" se exige
                # que no parezca una razón social.
                kw = re.search(r"comprador|adquirent|adquirient|vendedor|objeto|"
                               r"adquirid|transferid", ext.strip_acentos(full).lower())
                if kw or not _AF_LEGAL_END.search(full):
                    emitir(); rol = rs; grupo = full.strip(); prev_y = None
                    continue
            if not raw or _AF_HDR.match(raw):
                continue
            txt = _af_celda_izq(row, x_thresh)
            if not txt or re.match(r"[a-záéíóúñü]", txt):
                continue
            y = row[0][1]
            gap = (y - prev_y) if prev_y is not None else 999
            if buffer and (gap > 22 or _AF_LEGAL_END.search(buffer[-1])):
                emitir()
            buffer.append(txt); prev_y = y
            if _AF_LEGAL_END.search(txt):
                emitir(); prev_y = None
    emitir()
    doc.close()

    vistos, out = set(), []
    for r in resultados:
        n = r["nombre"]
        # fuga de nota al pie pegada al inicio: monto/porcentaje ("AR$ 1450,05).")
        n = re.sub(r"^(?:AR\$|US\$|\$)\s?[\d.,]+\)?\.?\s+", "", n)
        # conector suelto en minúscula al final (", la", " en", ...) de una fuga
        n = re.sub(r"[\s,]+(?:la|el|en|de|del|y|e|las|los|al)\s*$", "", n, flags=re.I)
        n = re.sub(r"^[^A-ZÁÉÍÓÚÑ0-9]+", "", n).strip()
        n = _limpiar_pua(ext._limpiar_empresa(n))
        if not n or len(n) < 4:
            continue
        letras = [c for c in n if c.isalpha()]
        if not letras or sum(c.isupper() for c in letras) / len(letras) < 0.55:
            continue
        if _AF_HDR.match(n) or _AF_KW_BLACK.search(n) or not ext._parece_empresa(n):
            continue
        if _af_es_junk(n):
            continue
        k = (r["rol"], re.sub(r"[^a-z0-9]", "", ext.strip_acentos(n).lower()))
        if k[1] and k not in vistos:
            vistos.add(k)
            out.append({"rol": r["rol"], "grupo": r["grupo"], "nombre": n})
    return out


# --- Suplemento por prosa: partes nombradas en la frase de la operación -------
_AF_LEGAL_TOK = (r"(?:S\.?A\.?(?:\.?[UICF])*|S\.?R\.?L|S\.?A\.?S|"
                 r"L\.?L\.?C|LTDA?|LTD|INC|GMBH|N\.?V|B\.?V|PLC|"
                 r"S\.?p\.?A|S\.?[àa]\s*r\.?l|CORPORATION|HOLDINGS?)\.?")
_AF_NOMBRE = re.compile(
    r"[A-ZÁÉÍÓÚÑ][\wÁÉÍÓÚÑÜáéíóúñü.&/\-]*"
    r"(?:\s+(?:[A-ZÁÉÍÓÚÑ0-9][\wÁÉÍÓÚÑÜáéíóúñü.&/\-]*|de|del|la|las|los|y|e|en|&))*?"
    r"\s+" + _AF_LEGAL_TOK + r"(?![A-Za-zÁÉÍÓÚÑáéíóúñ])",
    re.U)


def _af_nombres(span):
    out = []
    for m in _AF_NOMBRE.finditer(span or ""):
        n = re.sub(r"\s+", " ", ext._limpiar_empresa(m.group(0))).strip(" ,;")
        if n and ext._parece_empresa(n) and len(n) >= 5:
            out.append(n)
    return out


def _af_partes_prosa(flat):
    """[(rol, nombre)] de comprador/objeto/vendedor citados en el texto."""
    res = []
    m = re.search(
        r"adquisici[óo]n\s+(?:del?\s+)?"
        r"(?:control\s+\w+(?:\s+e?\s*indirecto)?\s+|"
        r"(?:del?\s+)?100\s*%\s+de\s+las\s+acciones\s+(?:de\s+)?|"
        r"del\s+inmueble\s+|de\s+determinados\s+[^,]*?\s+de\s+)?"
        r"(?:sobre\s+|de\s+)?(?P<obj>.{5,220}?)\s+"
        r"por\s+parte\s+(?:del?\s+grupo\s+econ[óo]mico\s+que\s+integran\s+|de\s+)"
        r"(?P<comp>.{5,220}?)"
        r"(?:[\.,]|\s+instrumentad|\s+mediante|\s+celebr|\s+\(|\s+La\s+venta|"
        r"\s+Se\s+instrument|\s+en\s+virtud|$)",
        flat, re.I)
    if m:
        res += [("objeto", n) for n in _af_nombres(m.group("obj"))]
        res += [("comprador", n) for n in _af_nombres(m.group("comp"))]
    for mm in re.finditer(r"([A-ZÁÉÍÓÚÑ][^.;]{3,120}?)\s*(?:\([^)]*\)\s*)?,?\s+"
                          r"(?:una\s+de\s+las\s+vendedoras|la\s+vendedora|"
                          r"es\s+la\s+vendedora)\b", flat, re.I):
        res += [("vendedor", n) for n in _af_nombres(mm.group(1))]
    m2 = re.search(r"[Ll]a\s+venta\s+fue\s+realizada\s+por\s+(.{5,160}?)[\.,]\s", flat)
    if m2:
        res += [("vendedor", n) for n in _af_nombres(m2.group(1))]
    vistos, out = set(), []
    for rol, n in res:
        k = re.sub(r"[^a-z0-9]", "", ext.strip_acentos(n).lower())
        if k and k not in vistos:
            vistos.add(k); out.append((rol, n))
    return out


# --- Extracción unificada empresas + actividades -----------------------------
def _empresas_y_actividades(ctx):
    """Recorre las tablas UNA vez y devuelve [{rol, nombre, actividad}].
    rol ∈ {'comprador','objeto', None}.  Aplica FIX 1/2/3/5."""
    res = []
    for tabla in ctx["tablas"]:
        heading = tabla.get("heading")     # rótulo suelto sobre la tabla (rol de sección)
        rol_sec = heading                  # arrastra el rol de sección
        activo = ext._es_tabla_empresas(tabla["rows"])
        for row in tabla["rows"]:
            if not row:
                continue
            cells = [(c or "").replace("\n", " ").strip() for c in row]
            nov = [(i, c) for i, c in enumerate(cells) if c]
            if not nov:
                continue
            # FIX 2: el header "Empresa/Actividad" activa la tabla pero NO cambia el rol
            if ext._es_header_empresas(cells):
                activo = True
                continue
            hay_prosa = any(ext._es_prosa(c) for _, c in nov)
            if not hay_prosa and ext._es_fila_participacion(cells):
                activo = False
                continue
            first_i, first_c = nov[0]
            lbl = ext._label_de_seccion(first_c, len(nov) == 1)
            if lbl:                        # rótulo de rol -> cambia sección
                rol_sec, activo = lbl, True
                resto = nov[1:]
                if not resto:
                    continue               # fila-etiqueta pura
                name_c = resto[0][1]
                act_cells = [c for _, c in resto[1:]]
            else:
                name_c = first_c
                act_cells = [c for _, c in nov[1:]]
            if not activo:
                continue
            nombre = _limpiar_pua(ext._limpiar_empresa(name_c))
            valido = any(ext._es_prosa(c) for c in act_cells) or bool(ext._RE_LEGAL.search(nombre))
            if not valido or not ext._parece_empresa(nombre):
                continue
            # FIX 1: el marcador inline "(Objeto)" gana sobre el rol de sección
            rol = ext._rol_parentesis(name_c) or rol_sec
            act = " ".join(a for a in act_cells if a and not ext._celda_numerica(a)).strip()
            act = _limpiar_pua(act)
            res.append({"rol": rol, "nombre": nombre, "actividad": act})

    # Fallback por geometría (tablas sin bordes): ya trae (rol, nombre, actividad)
    if not res:
        for rol, nombre, act in ctx.get("geo", []):
            for n in ext._split_multi_empresa(_limpiar_pua(ext._limpiar_empresa(nombre))):
                if ext._parece_empresa(n):
                    res.append({"rol": rol, "nombre": n, "actividad": _limpiar_pua(act)})

    # dedup por (rol, nombre)
    vistos, out = set(), []
    for e in res:
        k = (e["rol"], ext.strip_acentos(e["nombre"]).lower())
        if k not in vistos:
            vistos.add(k)
            out.append(e)
    return out


def ex_empresas3(ctx):
    """FIX 8: si el PDF trae la tabla moderna "Actividades de las empresas
    afectadas" con secciones de rol, se usa el parser role-aware
    (`empresas_afectadas`).  Si no (formato viejo / tabla sin roles), se conserva
    EXACTAMENTE el comportamiento anterior (tablas vectoriales -> tabla-texto),
    sin regresión.  En AMBOS casos se agregan, si faltan, las partes citadas en
    la frase de la operación (objeto/vendedor/comprador) vía `_af_partes_prosa`
    —de alta precisión y aditivas— que ninguna tabla lista (p.ej. el objeto
    adquirido o la vendedora extranjera)."""
    tab = []
    if ctx.get("path"):
        try:
            tab = empresas_afectadas(ctx["path"])
        except Exception:
            tab = []

    # Gate de calidad: sólo se adopta el parser nuevo cuando asignó rol a la
    # mayoría de los ítems.  Esa cobertura de rol es la firma del formato moderno
    # (secciones "Grupo comprador"/"Objeto"); los dictámenes viejos usan
    # marcadores inline y el parser nuevo les daría rol nulo -> se conserva el
    # comportamiento anterior (sin regresión sobre el corpus histórico).
    roled = (sum(1 for e in tab if e["rol"]) / len(tab)) if tab else 0.0
    if len(tab) >= 2 and roled >= 0.6:        # --- tabla moderna con roles ---
        emp = [dict(e) for e in tab]
    else:                                     # --- formato viejo: intacto ---
        emp = ctx.get("_empresas") or _empresas_y_actividades(ctx)
        if not emp and ctx.get("path"):
            try:
                tt = empresas_desde_tabla_texto(ctx["path"])
            except Exception:
                tt = []
            emp = [{"rol": None, "nombre": e["nombre"], "grupo": e["grupo"]} for e in tt]

    # Suplemento por prosa (aditivo, no pisa lo ya listado por nombre).
    nombres = {re.sub(r"[^a-z0-9]", "", ext.strip_acentos(e["nombre"]).lower()) for e in emp}
    try:
        prosa = _af_partes_prosa(ctx.get("flat") or "")
    except Exception:
        prosa = []
    for rol, n in prosa:
        k = re.sub(r"[^a-z0-9]", "", ext.strip_acentos(n).lower())
        if k and k not in nombres:
            emp.append({"rol": rol, "nombre": n, "grupo": ""})
            nombres.add(k)

    return json.dumps([{"rol": e["rol"], "nombre": e["nombre"]} for e in emp],
                      ensure_ascii=False) if emp else None


def ex_mercados3(ctx):
    """Mercado relevante = descripción/actividad de la sección 'Objeto'.

    Paso independiente (NO se gatilla por la tabla de empresas): recorre las
    tablas arrastrando el estado 'recolectando' que abre la sección 'objeto'.
    Mejoras sobre el original:
      FIX 2 — una fila-etiqueta que NO es un rol reconocido (p.ej. 'Empresa',
              'Actividad', un nombre suelto) NO apaga la recolección.
      FIX 1 — un marcador inline '(Objeto)' recolecta esa fila aunque la sección
              sea de comprador; '(Comprador)' la excluye.
      FIX 5 — limpieza de glifos PUA.
      FIX 6 — al tomar la fila completa de 'rest', quedan cubiertas también las
              descripciones de activos ('Un inmueble...') que no son empresas.
    FIX 4 — si nunca se abre una sección 'objeto', devuelve None (no mezcla)."""
    descs = []
    recolectando = False
    for tabla in ctx["tablas"]:
        heading = tabla.get("heading")
        if heading is not None:                      # rótulo suelto sobre la tabla
            recolectando = (heading == "objeto")
        for row in tabla["rows"]:
            if not row:
                continue
            cells = [_limpiar_pua((c or "").replace("\n", " ").strip()) for c in row]
            first = cells[0] if cells else ""
            rest = cells[1:]
            rest_txt = " ".join(x for x in rest if x).strip()
            es_label = bool(first) and not rest_txt
            if es_label:                             # fila de una sola celda
                r = ext._clasificar_label(first)     # 'objeto'/'comprador'/None
                if r == "objeto":
                    recolectando = True
                elif r == "comprador":
                    recolectando = False
                # FIX 2: header ('Empresa'...) o nombre suelto -> NO cambia estado
                continue
            rp = ext._rol_parentesis(first)          # FIX 1: marcador inline
            if rp == "comprador":
                continue
            en_objeto = recolectando or (rp == "objeto")
            if not en_objeto:
                continue
            if ext._es_fila_participacion(cells) and rp != "objeto":
                recolectando = False                 # tabla de participaciones/IHH corta
                continue
            desc = " ".join(x for x in rest if x and not ext._celda_numerica(x)).strip()
            desc = _limpiar_pua(desc)
            if desc and re.search(r"[A-Za-zÁÉÍÓÚáéíóúÑñ]{3,}", desc):
                descs.append(re.sub(r"\s+", " ", desc).strip())
    # Fallback por geometría (tablas sin bordes)
    if not descs:
        for rol, _n, act in ctx.get("geo", []):
            if rol == "objeto" and act and re.search(r"[A-Za-zÁÉÍÓÚáéíóúÑñ]{3,}", act):
                descs.append(_limpiar_pua(re.sub(r"\s+", " ", act).strip()))
    if not descs:
        return None
    return "; ".join(dict.fromkeys(descs))[:400].strip(" ;")


# --- Lista de extractores (igual al original, salvo empresas y mercados) -----
EXTRACTORES = [
    ("tipo",                  ext.ex_tipo),
    ("Carpeta",               ext.ex_carpeta),
    ("Carátula",              ext.ex_caratula),
    ("Grupo/Empresa",         ext.ex_grupo),
    ("Empresas involucradas", ex_empresas3),          # <-- nuevo
    ("Fecha_Ingreso",         ext.ex_fecha_ingreso),
    ("Fecha_firma",           ext.ex_fecha_firma),
    ("Decisión",              ext.ex_decision),
    ("Número de Resolución",  ext.ex_num_resolucion),
    ("Número de Dictamen",    ext.ex_num_dictamen),
    ("Mercados relevantes",   ex_mercados3),           # <-- nuevo
    ("Relaciones económicas", ext.ex_relaciones),
]


def procesar_pdf(path):
    raw, tablas, geo = ext.leer_pdf(path)
    reso_raw, dict_raw = ext.segmentar(raw)
    ctx = {
        "raw": raw, "flat": ext.flat(raw),
        "reso_raw": reso_raw, "reso_flat": ext.flat(reso_raw),
        "dict_raw": dict_raw, "dict_flat": ext.flat(dict_raw),
        "tablas": tablas, "geo": geo,
        "archivo": os.path.basename(path),
        "path": path,
    }
    # se calcula UNA sola vez y lo comparten empresas y mercados
    ctx["_empresas"] = _empresas_y_actividades(ctx)
    fila = {"Excluible": None, "_sin_tablas": (not tablas and not geo)}
    for nombre, fn in EXTRACTORES:
        try:
            val = fn(ctx)
        except Exception as e:
            val = None
            print(f"    [warn] {ctx['archivo']}: fallo en '{nombre}': {e}")
        fila[nombre] = val
        if nombre == "Carátula":
            ctx["caratula"] = val
    return fila


def main():
    carpeta = sys.argv[1] if len(sys.argv) > 1 else "pdf"
    salida = sys.argv[2] if len(sys.argv) > 2 else "firmadas3.xlsx"
    pdfs = sorted(glob.glob(os.path.join(carpeta, "*.pdf")))
    # solo CONC
    pdfs = [p for p in pdfs if os.path.basename(p).upper().startswith("CONC")]
    if not pdfs:
        print(f"No se encontraron PDFs CONC en '{carpeta}'.")
        sys.exit(1)

    filas, resumen, sin_tablas = [], [], []
    for p in pdfs:
        print(f"[proc] {os.path.basename(p)}")
        try:
            fila = procesar_pdf(p)
        except Exception as e:
            print(f"    [ERROR] no se pudo procesar: {e}")
            continue
        if fila.pop("_sin_tablas", False):
            sin_tablas.append(os.path.basename(p))
        filas.append(fila)
        vacios = [n for n in ext.COLUMNS if n not in ("Excluible", "meses") and not fila.get(n)]
        resumen.append((fila.get("Carpeta") or os.path.basename(p), vacios))

    def keyn(f):
        m = re.search(r"(\d+)", f.get("Carpeta") or "")
        return int(m.group(1)) if m else 0
    filas.sort(key=keyn)

    ext.escribir_excel(filas, salida)
    print(f"\nOK -> {salida}  ({len(filas)} filas)")

    # PDFs sin ninguna tabla (formato viejo en prosa): no extraíbles por tablas
    if sin_tablas:
        noext = os.path.splitext(salida)[0] + "_no_extraibles.txt"
        with open(noext, "w", encoding="utf-8") as fh:
            fh.write("PDFs sin tablas (formato viejo en prosa) - revisar a mano:\n")
            for n in sorted(sin_tablas):
                fh.write(f"  {n}\n")
        print(f"\n{len(sin_tablas)} PDFs sin tablas (prosa pura) -> {noext}")

    print("\nCampos en blanco por caso (para revisar a mano):")
    for carpeta_id, vacios in resumen:
        print(f"  {carpeta_id}: {', '.join(vacios) if vacios else '— completo —'}")


if __name__ == "__main__":
    main()
