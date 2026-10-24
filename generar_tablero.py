# -*- coding: utf-8 -*-
"""
Genera el tablero publico de resoluciones firmadas:

    conc/index.html     pagina autocontenida (usa assets/ del sitio), con filtros por año, tipo y sector
    data/conc.json      agregados + detalle por expediente, para reutilizar (schema_version 1)

Lee el mismo maestro que el buscador (firm.xlsx) y reutiliza generar_pagina.build_records()
por import: no modifica ni duplica la logica del buscador. El detalle por expediente trae solo lo
que el buscador ya publica (carpeta, fecha de firma, tipo, decision, sectores, relaciones, dias):
el tablero no republica nombres de empresas.

Los agregados que salen de aca (anio_tipo, decisiones, sectores, ...) son la referencia: la pagina
recalcula lo mismo en el navegador a partir del detalle cuando se filtra, y verificar_sitio / los tests
comprueban que sin filtros dan lo mismo.

Uso:
    python -B generar_tablero.py

(-B evita reescribir los .pyc versionados.)
"""
from __future__ import annotations

import collections
import datetime as dt
import json
import math
import re
import statistics
import sys
from pathlib import Path

import pandas as pd

AQUI = Path(__file__).parent
sys.path.insert(0, str(AQUI))

import generar_pagina as gp          # noqa: E402  (solo se usa build_records / clasificar_tipo / ARCHIVO)
import nomenclador_mercados as nm    # noqa: E402
from verificar_sitio import huella_corpus  # noqa: E402  (stdlib: la misma huella la recalcula el verificador)

SALIDA_HTML = AQUI / "conc" / "index.html"
SALIDA_JSON = AQUI / "data" / "conc.json"

SCHEMA_VERSION = 1
MIN_N = 5                      # una mediana con menos de MIN_N expedientes no se dibuja
ANIO_DESDE = 2016
TOP_SECTORES = 12
SIN_CLASIFICAR = "Otros / sin clasificar"

# --------------------------------------------------------------------------- #
# Decision (texto libre del Excel) -> grupo. El ORDEN de las reglas importa.
# --------------------------------------------------------------------------- #
GRUPOS_DECISION = [
    ("Autoriza", "«Autoriza», Art. 13 a) Ley 25.156, Art. 14 a) Ley 27.442 o disposición PROSUM que autoriza."),
    ("Autoriza con multa", "Lo anterior, con multa (Art. 55 inc. d Ley 27.442 / Art. 46 inc. d Ley 25.156)."),
    ("Subordina", "«Subordina», Art. 13 b) Ley 25.156 o Art. 14 b) Ley 27.442."),
    ("No sujeta a notificación", "«No sujeta a notificación»."),
    ("Art. 10, primer párrafo", "Resoluciones del Art. 10, primer párrafo, Ley 27.442 (incluye «no notificar» y «ordena notificar»)."),
    ("Arts. 7 y 9", "Resoluciones sobre los Arts. 7 y 9 Ley 27.442 y «sujeta a notificación»."),
    ("Incidentes y disposiciones", "Disposiciones TDC (Arts. 66 y 67) e incidentes dentro de una concentración."),
    ("Archivo", "Cualquier texto que diga «archivo»."),
    ("Otras", "Texto que ninguna regla reconoce (hoy: ninguno)."),
    ("Sin dato", "Celda de decisión vacía en el Excel."),
]


def categoria_decision(texto) -> str:
    t = nm.norm(texto or "")
    if not t:
        return "Sin dato"
    if "archivo" in t:
        return "Archivo"
    if re.search(r"\binc\.? ?i\b|\binc\.? conc|disposicion tdc|arts?\.? 66", t) and "autoriza" not in t:
        return "Incidentes y disposiciones"
    if "subordina" in t or re.search(r"14,? inc\.? b\)|13 b\)", t):
        return "Subordina"
    if re.search(r"\bno sujeta\b", t):
        return "No sujeta a notificación"
    if re.search(r"\bsujeta a notificacion|7[ºo°]? y 9", t):
        return "Arts. 7 y 9"
    if re.search(r"art(iculo|\.)? ?10\b", t):
        return "Art. 10, primer párrafo"
    if re.search(r"multa|\b55,? inc", t):
        return "Autoriza con multa"
    if re.search(r"autoriza|14,? inc\.? a\)|13,? inc\.? a\)|art(iculo|\.)? ?14 inc\.? a|prosum", t):
        return "Autoriza"
    return "Otras"


def _redondeo(x: float) -> int:
    """Redondeo convencional (.5 hacia arriba); round() de Python redondea 312,5 a 312."""
    return int(math.floor(x + 0.5))


def _pct(n: int, total: int) -> float:
    return round(100.0 * n / total, 1) if total else 0.0


def _vacio(v) -> bool:
    return v is None or (isinstance(v, float) and pd.isna(v)) or str(v).strip() == ""


def construir() -> dict:
    recs = gp.build_records()
    df = pd.read_excel(gp.ARCHIVO, sheet_name=0, header=0)
    total = len(recs)

    # ---- fecha de ingreso (solo la lee este tablero; el buscador no la exporta) ----
    ingreso = {}
    for r in recs:
        v = df.loc[r["id"], "Fecha_Ingreso"]
        d = pd.to_datetime(v, errors="coerce") if not _vacio(v) else pd.NaT
        ingreso[r["id"]] = None if pd.isna(d) else d.date()

    def fecha_firma(r):
        if not r["fsort"]:
            return None
        s = str(r["fsort"])
        return dt.date(int(s[:4]), int(s[4:6]), int(s[6:8]))

    firmas = [fecha_firma(r) for r in recs]
    con_fecha = [f for f in firmas if f]
    ultima = max(con_fecha)
    primera = min(con_fecha)

    # ---- 1. firmas por año y tipo ----
    anios = list(range(ANIO_DESDE, ultima.year + 1))
    claves = [("ordinaria", "Conc. ordinaria", ["Conc. ordinaria"]),
              ("prosum", "PROSUM", ["PROSUM"]),
              ("opi", "OPI", ["OPI"]),
              ("otros", "Otros (condicionadas, incidentes)", ["Conc. condicionada", "Otros", "DP"])]
    claves_json = [{"clave": k, "nombre": n, "tipos": ts} for k, n, ts in claves]
    por_clave = {k: [0] * (len(anios) + 1) for k, _, _ in claves}      # último lugar = sin fecha
    tipo_de = {t: k for k, _, ts in claves for t in ts}
    for r, f in zip(recs, firmas):
        k = tipo_de.get(r["tipo_cat"], "otros")
        i = (f.year - ANIO_DESDE) if (f and ANIO_DESDE <= f.year <= ultima.year) else len(anios)
        por_clave[k][i] += 1
    parcial = ultima < dt.date(ultima.year, 12, 15)
    categorias = [f"{a}*" if (parcial and a == ultima.year) else str(a) for a in anios] + ["s/f"]
    nombres = [f"{a} (parcial: hasta {ultima.strftime('%d/%m/%Y')})" if (parcial and a == ultima.year) else str(a)
               for a in anios] + ["Sin fecha de firma"]

    # ---- 2. decisiones normalizadas ----
    cont_dec = collections.Counter(categoria_decision(r["decision"]) for r in recs)
    decisiones = []
    for g, regla in GRUPOS_DECISION:
        n = cont_dec.get(g, 0)
        if n == 0 and g in ("Otras",):
            continue
        decisiones.append({"grupo": g, "n": n, "pct": _pct(n, total), "regla": regla, "sin_dato": g == "Sin dato"})
    con_dato = sorted([d for d in decisiones if not d["sin_dato"]], key=lambda d: -d["n"])
    decisiones = con_dato + [d for d in decisiones if d["sin_dato"]]
    variantes = len({nm.norm(r["decision"]) for r in recs if r["decision"]})
    cont_var = collections.Counter(r["decision"] for r in recs if r["decision"])
    lista_variantes = sorted(({"texto": t_, "grupo": categoria_decision(t_), "n": n_} for t_, n_ in cont_var.items()),
                             key=lambda v: (-v["n"], v["texto"]))

    # ---- 3. sectores (un expediente puede estar en varios) ----
    cont_sec = collections.Counter(s for r in recs for s in r["sectores"])
    top = [(s, n) for s, n in cont_sec.most_common() if s != SIN_CLASIFICAR][:TOP_SECTORES]
    sectores = [{"sector": s, "n": n, "pct": _pct(n, total), "sin_dato": False} for s, n in top]
    sectores.append({"sector": SIN_CLASIFICAR, "n": cont_sec.get(SIN_CLASIFICAR, 0),
                     "pct": _pct(cont_sec.get(SIN_CLASIFICAR, 0), total), "sin_dato": True})
    catalogo_sec = [{"sector": s_, "n": n} for s_, n in cont_sec.most_common() if s_ != SIN_CLASIFICAR]
    catalogo_sec.append({"sector": SIN_CLASIFICAR, "n": cont_sec.get(SIN_CLASIFICAR, 0)})

    # ---- 4. relaciones económicas ----
    cont_rel = collections.Counter(t for r in recs for t in r["rel_tags"])
    relaciones = [{"relacion": t, "n": cont_rel.get(t, 0), "pct": _pct(cont_rel.get(t, 0), total), "sin_dato": False}
                  for t in ("Horizontal", "Vertical", "Conglomerado", "Efectos de cartera")]
    relaciones.sort(key=lambda d: -d["n"])
    sin_rel = sum(1 for r in recs if not r["rel_tags"])
    relaciones.append({"relacion": "Sin dato", "n": sin_rel, "pct": _pct(sin_rel, total), "sin_dato": True})

    # ---- 5. tiempo ingreso -> firma, ordinarias vs PROSUM ----
    dias_por = collections.defaultdict(list)
    dias_de = {}
    todos = []
    descartados = 0
    for r, f in zip(recs, firmas):
        ing = ingreso[r["id"]]
        if not (f and ing):
            continue
        d = (f - ing).days
        if d <= 0:
            descartados += 1
            continue
        todos.append(d)
        dias_de[r["id"]] = d
        k = tipo_de.get(r["tipo_cat"], "otros")
        if k in ("ordinaria", "prosum"):
            dias_por[(k, f.year)].append(d)
    series_t = []
    for k, nombre in (("ordinaria", "Conc. ordinaria"), ("prosum", "PROSUM")):
        valores, ns = [], []
        for a in anios:
            xs = dias_por.get((k, a), [])
            ns.append(len(xs))
            valores.append(_redondeo(statistics.median(xs)) if len(xs) >= MIN_N else None)
        total_k = sum(ns)
        series_t.append({"clave": k, "nombre": nombre, "valores": valores, "n": ns, "n_total": total_k,
                         "mediana_total": _redondeo(statistics.median([d for (kk, _), xs in dias_por.items() if kk == k for d in xs])) if total_k else None})
    tiempos = {
        "anios": [f"{a}*" if (parcial and a == ultima.year) else str(a) for a in anios],
        "series": series_t, "min_n": MIN_N,
        "mediana_global": _redondeo(statistics.median(todos)), "n_global": len(todos),
        "cobertura_pct": _pct(len(todos), total), "descartados_no_positivos": descartados,
    }

    # ---- 6. cobertura de campos (el orden de CAMPOS define los bits de "cob" en el detalle) ----
    CAMPOS = [
        ("Fecha de firma", lambda r: r["fsort"]),
        ("Número de resolución", lambda r: r["resolucion"]),
        ("Número de dictamen", lambda r: r["dictamen"]),
        ("PDF enlazado", lambda r: r["pdf"]),
        ("Empresas involucradas", lambda r: r["compradores"] or r["objeto"]),
        ("Decisión", lambda r: r["decision"]),
        ("Grupo / empresa", lambda r: r["grupo"]),
        ("Mercado relevante", lambda r: r["merc_v1"] or r["merc_v2"]),
        ("Fecha de ingreso", lambda r: ingreso[r["id"]]),
        ("Relaciones económicas", lambda r: r["rel_v1"] or r["rel_v2"]),
    ]
    campos = [(nombre, sum(1 for r in recs if fn(r))) for nombre, fn in CAMPOS]
    cobertura = sorted([{"campo": c, "n": n, "pct": _pct(n, total)} for c, n in campos], key=lambda d: -d["n"])
    pct_de = {c["campo"]: c["pct"] for c in cobertura}

    tipos = collections.Counter(r["tipo_cat"] for r in recs)
    orden_tipos = [t for t in gp.TIPO_ORDEN if t in tipos] + sorted(t for t in tipos if t not in gp.TIPO_ORDEN)

    # ---- 7. detalle por expediente: lo que usan los filtros de la pagina y el CSV ----
    detalle = []
    for r, f in zip(recs, firmas):
        detalle.append({
            "carpeta": r["carpeta"],
            "fecha": f.isoformat() if f else None,
            "tipo": r["tipo_cat"],
            "decision": r["decision"] or "",
            "grupo": categoria_decision(r["decision"]),
            "sectores": list(r["sectores"]),
            "relaciones": list(r["rel_tags"]),
            "dias": dias_de.get(r["id"]),
            "cob": sum(1 << i for i, (_, fn) in enumerate(CAMPOS) if fn(r)),
        })
    hoy = dt.date.today().isoformat()
    return {
        "schema_version": SCHEMA_VERSION,
        "generado": hoy,
        "fuente": "firm.xlsx (hoja 1) vía generar_pagina.build_records()",
        "registros": total,
        "firmas": {"primera": primera.isoformat(), "ultima": ultima.isoformat(),
                   "con_fecha": len(con_fecha), "sin_fecha": total - len(con_fecha), "anio_parcial": parcial},
        "por_tipo": dict(tipos),
        "kpi": {"pct_decision": pct_de["Decisión"], "pct_empresas": pct_de["Empresas involucradas"],
                "mediana_dias": tiempos["mediana_global"], "n_dias": tiempos["n_global"],
                "cobertura_dias_pct": tiempos["cobertura_pct"]},
        "anio_tipo": {"anios": anios, "categorias": categorias, "nombres": nombres, "claves": claves_json,
                      "series": [{"clave": k, "nombre": nombre, "valores": por_clave[k]} for k, nombre, _ in claves]},
        "tipos": [{"nombre": t, "n": tipos[t]} for t in orden_tipos],
        "decisiones": {"grupos": decisiones, "variantes_texto": variantes, "variantes": lista_variantes},
        "sectores": {"items": sectores, "total_sectores": len(cont_sec), "top": TOP_SECTORES,
                     "sin_clasificar": SIN_CLASIFICAR, "catalogo": catalogo_sec},
        "relaciones": relaciones,
        "relaciones_orden": ["Horizontal", "Vertical", "Conglomerado", "Efectos de cartera"],
        "tiempos": tiempos,
        "cobertura": cobertura,
        "campos_cobertura": [nombre for nombre, _ in CAMPOS],
        "corpus": {"registros": total, "huella": huella_corpus(recs),
                   "nota": "Huella de (carpeta, fecha de firma, decisión) de cada expediente, en orden. "
                           "verificar_sitio.py la compara con el index.html publicado: si no coincide, volver a correr generar_tablero.py."},
        "detalle": detalle,
    }


# --------------------------------------------------------------------------- #
# Pagina
# --------------------------------------------------------------------------- #
TEMPLATE = r"""<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Estadísticas de concentraciones — Herramientas ANC</title>
<meta name="description" content="Estadísticas de las resoluciones, dictámenes y opiniones consultivas publicados: firmas por año, decisiones, sectores y tiempos de trámite, con filtros por año, tipo y sector.">
<link rel="icon" href="data:,">
<link rel="stylesheet" href="../assets/anc.css">
</head>
<body class="anc">
<div id="anc-nav"></div>
<header class="anc-head"><div class="anc-head-in">
  <h1>Estadísticas de concentraciones</h1>
  <p class="anc-lead">Resoluciones, dictámenes y opiniones consultivas del <a href="../">Buscador de Mercados Relevantes</a>, contados
  sobre el mismo maestro de datos. Filtrá por año, tipo o sector: todo se recalcula y la selección se puede bajar en CSV. No se
  muestran nombres de empresas. Los datos llegan hasta el <b id="hasta"></b>.</p>
</div></header>

<main class="anc-main" id="contenido">
  <noscript><div class="anc-banner" style="margin-top:1.2rem">Esta página necesita JavaScript para mostrar los indicadores, los gráficos y los filtros.</div></noscript>
  <section class="anc-section" aria-label="Filtros">
    <form class="anc-filters" id="filtros" autocomplete="off">
      <label class="anc-field">Año de firma<select id="f-anio"></select></label>
      <label class="anc-field">Tipo de expediente<select id="f-tipo"></select></label>
      <label class="anc-field anc-field-wide">Sector<select id="f-sector"></select></label>
      <button type="button" class="anc-btn" id="f-limpiar">Limpiar filtros</button>
      <button type="button" class="anc-btn" id="f-csv" title="CSV con separador ; y UTF-8, listo para abrir en Excel">Descargar CSV</button>
    </form>
    <p class="anc-filter-status" id="estado" role="status" aria-live="polite"></p>
  </section>
  <section class="anc-section" aria-label="Indicadores"><div class="anc-tiles" id="tiles"></div></section>
  <section class="anc-section"><div class="anc-card" id="ch-anio"></div></section>
  <section class="anc-section anc-grid2"><div class="anc-card" id="ch-dec"></div><div class="anc-card" id="ch-sec"></div></section>
  <section class="anc-section"><div class="anc-card" id="ch-tiempos"></div></section>
  <section class="anc-section anc-grid2"><div class="anc-card" id="ch-rel"></div><div class="anc-card" id="ch-cob"></div></section>
  <section class="anc-section">
    <h2>Notas metodológicas</h2>
    <div class="anc-card anc-note" id="notas"></div>
  </section>
  <p class="anc-foot" id="pie"></p>
</main>

<script id="anc-data" type="application/json">__DATOS__</script>
<script src="../assets/charts.js"></script>
<script src="../assets/csv.js"></script>
<script src="../assets/nav.js" defer></script>
<script>
(function () {
  'use strict';
  var D = JSON.parse(document.getElementById('anc-data').textContent);
  var A = window.ANCCharts, h = A.h, fmt = A.fmt, pct = A.pct;
  var COLOR = { ordinaria: 'var(--anc-s1)', prosum: 'var(--anc-s2)', opi: 'var(--anc-s3)', otros: 'var(--anc-other)' };
  var ROWS = D.detalle, TOTAL = ROWS.length, SF = 's/f';
  var YEARS = D.anio_tipo.anios, Y0 = YEARS[0], Y1 = YEARS[YEARS.length - 1];
  var SIN_CLASIF = D.sectores.sin_clasificar, TOP = D.sectores.top, MIN_N = D.tiempos.min_n;
  var CAMPOS = D.campos_cobertura, CLAVES = D.anio_tipo.claves, CLAVE = {};
  CLAVES.forEach(function (c) { c.tipos.forEach(function (t) { CLAVE[t] = c.clave; }); });
  var F = { anio: '', tipo: '', sector: '' };

  function $(id) { return document.getElementById(id); }
  function dmy(iso) { var p = iso.split('-'); return p[2] + '/' + p[1] + '/' + p[0]; }
  function p1(n, t) { return t ? Math.round(1000 * n / t) / 10 : 0; }          // % con 1 decimal
  function redondeo(x) { return Math.floor(x + 0.5); }                          // .5 hacia arriba, como el generador
  function mediana(xs) {
    var a = xs.slice().sort(function (x, y) { return x - y; }), m = a.length >> 1;
    return a.length % 2 ? a[m] : (a[m - 1] + a[m]) / 2;
  }
  // año de firma dentro del rango que se grafica; fuera de rango o sin fecha va a "s/f"
  function bucket(r) {
    if (!r.fecha) return SF;
    var y = +r.fecha.slice(0, 4);
    return y >= Y0 && y <= Y1 ? String(y) : SF;
  }
  function seleccion() {
    return ROWS.filter(function (r) {
      return (!F.anio || bucket(r) === F.anio) && (!F.tipo || r.tipo === F.tipo) && (!F.sector || r.sectores.indexOf(F.sector) >= 0);
    });
  }

  /* ---------- agregados de la selección (misma lógica que generar_tablero.py) ---------- */
  function agregar(sel) {
    var n = sel.length, G = { n: n }, i;
    var fechas = sel.map(function (r) { return r.fecha; }).filter(Boolean).sort();
    G.conFecha = fechas.length; G.primera = fechas[0] || null; G.ultima = fechas[fechas.length - 1] || null;

    // por año y tipo
    G.porClave = {}; G.anioTipo = {};
    CLAVES.forEach(function (c) { G.porClave[c.clave] = 0; G.anioTipo[c.clave] = YEARS.map(function () { return 0; }).concat([0]); });
    sel.forEach(function (r) {
      var k = CLAVE[r.tipo] || 'otros', b = bucket(r);
      G.porClave[k]++;
      G.anioTipo[k][b === SF ? YEARS.length : +b - Y0]++;
    });

    // decisiones (agrupadas); "Sin dato" siempre al final
    var cd = {};
    sel.forEach(function (r) { cd[r.grupo] = (cd[r.grupo] || 0) + 1; });
    var gr = D.decisiones.grupos.map(function (g) {
      var k = cd[g.grupo] || 0;
      return { grupo: g.grupo, regla: g.regla, n: k, pct: p1(k, n), sin_dato: g.sin_dato };
    }).filter(function (g) { return g.n > 0; });
    G.decisiones = gr.filter(function (g) { return !g.sin_dato; }).sort(function (a, b) { return b.n - a.n; })
      .concat(gr.filter(function (g) { return g.sin_dato; }));

    // sectores: los TOP con más expedientes (sin el "sin clasificar", que va al final)
    var cs = {}, orden = [];
    sel.forEach(function (r) { r.sectores.forEach(function (s) { if (!(s in cs)) { cs[s] = 0; orden.push(s); } cs[s]++; }); });
    G.totalSectores = orden.length;
    G.sectores = orden.filter(function (s) { return s !== SIN_CLASIF; })
      .sort(function (a, b) { return cs[b] - cs[a]; }).slice(0, TOP)
      .map(function (s) { return { sector: s, n: cs[s], pct: p1(cs[s], n), sin_dato: false }; });
    if (cs[SIN_CLASIF]) G.sectores.push({ sector: SIN_CLASIF, n: cs[SIN_CLASIF], pct: p1(cs[SIN_CLASIF], n), sin_dato: true });

    // relaciones económicas
    var cr = {}, sinRel = 0;
    sel.forEach(function (r) {
      if (!r.relaciones.length) sinRel++;
      r.relaciones.forEach(function (t) { cr[t] = (cr[t] || 0) + 1; });
    });
    G.relaciones = D.relaciones_orden.map(function (t) { return { relacion: t, n: cr[t] || 0, pct: p1(cr[t] || 0, n), sin_dato: false }; })
      .sort(function (a, b) { return b.n - a.n; });
    G.relaciones.push({ relacion: 'Sin dato', n: sinRel, pct: p1(sinRel, n), sin_dato: true });

    // tiempo ingreso -> firma: mediana por año de firma, ordinarias vs PROSUM
    var todos = [], porAnio = { ordinaria: {}, prosum: {} }, totalK = { ordinaria: [], prosum: [] };
    sel.forEach(function (r) {
      if (r.dias === null) return;
      todos.push(r.dias);
      var k = CLAVE[r.tipo] || 'otros';
      if (k !== 'ordinaria' && k !== 'prosum') return;
      totalK[k].push(r.dias);
      var b = bucket(r);
      if (b !== SF) (porAnio[k][b] = porAnio[k][b] || []).push(r.dias);
    });
    G.tiempos = {
      series: ['ordinaria', 'prosum'].map(function (k) {
        var ns = YEARS.map(function (y) { return (porAnio[k][y] || []).length; });
        return {
          clave: k, nombre: k === 'ordinaria' ? 'Conc. ordinaria' : 'PROSUM', n: ns, n_total: totalK[k].length,
          valores: YEARS.map(function (y, j) { return ns[j] >= MIN_N ? redondeo(mediana(porAnio[k][y])) : null; }),
          mediana_total: totalK[k].length ? redondeo(mediana(totalK[k])) : null
        };
      }),
      mediana_global: todos.length ? redondeo(mediana(todos)) : null, n_global: todos.length, cobertura_pct: p1(todos.length, n)
    };

    // cobertura de campos (un bit por campo en "cob")
    G.cobertura = CAMPOS.map(function (c, j) {
      var k = 0;
      sel.forEach(function (r) { if ((r.cob >> j) & 1) k++; });
      return { campo: c, n: k, pct: p1(k, n) };
    }).sort(function (a, b) { return b.n - a.n; });
    function pc(campo) { return G.cobertura.filter(function (x) { return x.campo === campo; })[0].pct; }
    G.pctDecision = pc('Decisión'); G.pctEmpresas = pc('Empresas involucradas');
    return G;
  }

  /* ---------- pintar ---------- */
  var NOTA_PARCIAL = D.firmas.anio_parcial ? '. El último año llega hasta el ' + dmy(D.firmas.ultima) + '.' : '.';

  function pintarEstado(n, filtrado) {
    var partes = [];
    if (F.anio) partes.push(F.anio === SF ? 'sin fecha de firma' : 'año ' + F.anio);
    if (F.tipo) partes.push('tipo ' + F.tipo);
    if (F.sector) partes.push('sector ' + F.sector);
    $('estado').textContent = filtrado
      ? 'Mostrando ' + fmt(n) + ' de ' + fmt(TOTAL) + ' expedientes · ' + partes.join(' · ')
      : 'Mostrando los ' + fmt(TOTAL) + ' expedientes, sin filtros.';
    $('f-csv').textContent = 'Descargar CSV (' + fmt(n) + ')';
    $('f-csv').disabled = n === 0;
    $('f-limpiar').disabled = !filtrado;
  }

  function pintarTiles(G, filtrado) {
    var pc = G.porClave, T = G.tiempos, n = G.n;
    var tiles = [
      { hero: true, l: filtrado ? 'Expedientes en la selección' : 'Expedientes en el buscador', v: fmt(n),
        n: fmt(pc.ordinaria) + ' ordinarias · ' + fmt(pc.prosum) + ' PROSUM · ' + fmt(pc.opi) + ' OPI · ' + fmt(pc.otros) + ' otros' +
           (filtrado ? ' · de ' + fmt(TOTAL) + ' en total' : '') },
      { l: 'Con fecha de firma', v: fmt(G.conFecha),
        n: (G.primera ? dmy(G.primera) + ' a ' + dmy(G.ultima) + ' · ' : '') + fmt(n - G.conFecha) + ' sin fecha' },
      { l: 'Con decisión cargada', v: n ? pct(G.pctDecision) : '—', n: 'El resto figura como «Sin dato»' },
      { l: 'Con empresas identificadas', v: n ? pct(G.pctEmpresas) : '—', n: 'Compradores u objeto' },
      { l: 'Mediana ingreso → firma', v: T.mediana_global === null ? '—' : fmt(T.mediana_global) + ' días',
        n: 'n = ' + fmt(T.n_global) + (n ? ' · cobertura ' + pct(T.cobertura_pct) : '') }
    ];
    var box = $('tiles');
    box.textContent = '';
    tiles.forEach(function (x) {
      box.appendChild(h('div', { class: 'anc-tile' + (x.hero ? ' hero' : '') }, [
        h('div', { class: 'anc-tile-l' }, [x.l]), h('div', { class: 'anc-tile-v' }, [x.v]), h('div', { class: 'anc-tile-n' }, [x.n])]));
    });
  }

  function pintarGraficos(G, filtrado) {
    var vacio = 'Ningún expediente cumple estos filtros.';
    var delTotal = filtrado ? 'de la selección' : 'del total';

    A.stackedColumns($('ch-anio'), {
      title: 'Firmas por año y tipo de expediente',
      subtitle: 'Cantidad según la fecha de firma' + NOTA_PARCIAL,
      categories: D.anio_tipo.categorias, catNames: D.anio_tipo.nombres, catHeader: 'Año de firma', unit: 'expedientes',
      series: CLAVES.map(function (c) { return { label: c.nombre, color: COLOR[c.clave], values: G.anioTipo[c.clave] }; }),
      note: 'PROSUM (procedimiento simplificado) aparece recién desde 2024. «s/f» agrupa los expedientes sin fecha de firma cargada.',
      emptyMsg: vacio
    });

    A.hbars($('ch-dec'), {
      title: 'Decisiones', unit: 'expedientes', pctLabel: delTotal, emptyMsg: vacio,
      subtitle: 'El texto libre de la columna Decisión (' + D.decisiones.variantes_texto + ' variantes) se agrupa en categorías; la celda vacía cuenta como «Sin dato».',
      items: G.decisiones.map(function (g) { return { label: g.grupo, value: g.n, pct: g.pct, muted: g.sin_dato, note: g.regla }; })
    });

    A.hbars($('ch-sec'), {
      title: 'Sectores', unit: 'expedientes', pctLabel: delTotal, emptyMsg: vacio,
      subtitle: 'Un expediente puede figurar en más de un sector. Se muestran los ' + TOP + ' con más expedientes (' +
        (filtrado ? 'en la selección hay ' + G.totalSectores : 'el catálogo tiene ' + D.sectores.total_sectores) + ').',
      items: G.sectores.map(function (x) {
        return { label: x.sector, value: x.n, pct: x.pct, muted: x.sin_dato, note: x.sin_dato ? 'Sin clasificar en el nomenclador de mercados.' : null };
      })
    });

    var T = G.tiempos;
    A.lines($('ch-tiempos'), {
      title: 'Tiempo entre ingreso y firma',
      subtitle: 'Mediana de días corridos según el año de firma. Solo se dibujan los años con ' + MIN_N + ' o más expedientes.',
      categories: D.tiempos.anios, catHeader: 'Año de firma', valueSuffix: ' d', height: 290,
      emptyMsg: G.n ? 'Con estos filtros no hay ningún año con ' + MIN_N + ' o más expedientes ordinarios o PROSUM que tengan fecha de ingreso y de firma.' : vacio,
      series: T.series.map(function (s) {
        return { label: s.nombre, color: COLOR[s.clave], values: s.valores, n: s.n,
          legendExtra: s.mediana_total === null ? '' : '· mediana total ' + fmt(s.mediana_total) + ' d (n = ' + fmt(s.n_total) + ')' };
      }),
      note: 'No es el plazo legal ni descuenta suspensiones: resta la fecha de ingreso a la de firma tal como están cargadas. ' +
        (G.n ? 'Solo ' + pct(T.cobertura_pct) + ' de los expedientes ' + (filtrado ? 'de la selección ' : '') + 'tiene ambas fechas; en PROSUM, todos.' : '')
    });

    A.hbars($('ch-rel'), {
      title: 'Relaciones económicas', unit: 'expedientes', pctLabel: delTotal, emptyMsg: vacio,
      subtitle: 'Un expediente puede tener más de una relación. Cuando falta el dato queda «Sin dato».',
      items: G.n ? G.relaciones.map(function (x) { return { label: x.relacion, value: x.n, pct: x.pct, muted: x.sin_dato }; }) : []
    });
    A.hbars($('ch-cob'), {
      title: 'Cobertura de datos', unit: 'expedientes', pctLabel: delTotal, emptyMsg: vacio,
      subtitle: 'Porcentaje de expedientes con cada campo cargado en el maestro.',
      items: G.n ? G.cobertura.map(function (x) { return { label: x.campo, value: x.n, pct: x.pct }; }) : []
    });
  }

  /* ---------- notas y tablas de decisiones (se arman una vez; los conteos se actualizan) ---------- */
  var T_REGLAS, T_VARIANTES;
  function armarNotas() {
    var notas = $('notas');
    notas.appendChild(h('ul', null, [
      h('li', null, ['Fuente: maestro ', h('code', null, ['firm.xlsx']), ' (' + fmt(D.registros) + ' expedientes publicados en el buscador). Generado el ' + dmy(D.generado) + '.']),
      h('li', null, ['Los datos son los que están cargados: los campos vacíos se muestran como «Sin dato» o como cobertura, nunca se completan.']),
      h('li', null, ['La clasificación por sector y por relación económica sale del nomenclador del buscador (automática); verificar siempre en el documento original.']),
      h('li', null, ['«Tipo» sigue la columna del Excel: ordinarias, PROSUM, OPI y otros (condicionadas, incidentes). Los incidentes y disposiciones cuentan como expedientes propios.']),
      h('li', null, ['Los filtros, los gráficos y el CSV se calculan en este navegador con los mismos datos de ', h('code', null, ['data/conc.json']), '; la dirección de la página guarda los filtros elegidos, así se puede compartir una vista.'])
    ]));
    T_REGLAS = h('tbody');
    T_VARIANTES = h('tbody');
    function tabla(cap, heads, tb) {
      return h('div', { class: 'anc-tablewrap' }, [h('table', { class: 'anc-table' }, [
        h('caption', null, [cap]),
        h('thead', null, [h('tr', null, heads.map(function (t, i) { return h('th', { scope: 'col', class: i === heads.length - 1 ? 'num' : null }, [t]); }))]),
        tb])]);
    }
    notas.appendChild(h('details', { class: 'anc-det' }, [
      h('summary', null, ['Cómo se agrupan las decisiones (para revisar)']),
      tabla('Reglas de agrupación de la columna Decisión', ['Grupo', 'Regla', 'Expedientes'], T_REGLAS),
      h('p', { class: 'anc-fig-n' }, ['Texto original de la columna Decisión, tal como está en el maestro y el grupo en el que cae cada variante.']),
      tabla('Variantes del texto de la decisión', ['Texto original', 'Grupo', 'Expedientes'], T_VARIANTES)
    ]));
  }
  function pintarDecisiones(sel) {
    var cg = {}, cv = {};
    sel.forEach(function (r) {
      cg[r.grupo] = (cg[r.grupo] || 0) + 1;
      if (r.decision) cv[r.decision] = (cv[r.decision] || 0) + 1;
    });
    T_REGLAS.textContent = '';
    D.decisiones.grupos.forEach(function (g) {
      T_REGLAS.appendChild(h('tr', null, [h('th', { scope: 'row' }, [g.grupo]), h('td', null, [g.regla]), h('td', { class: 'num' }, [fmt(cg[g.grupo] || 0)])]));
    });
    T_VARIANTES.textContent = '';
    D.decisiones.variantes.forEach(function (v) {
      T_VARIANTES.appendChild(h('tr', null, [h('th', { scope: 'row' }, [v.texto]), h('td', null, [v.grupo]), h('td', { class: 'num' }, [fmt(cv[v.texto] || 0)])]));
    });
  }

  /* ---------- CSV de la selección ---------- */
  var CSV_COLS = ['Expediente', 'Fecha de firma', 'Tipo', 'Decisión (texto del maestro)', 'Grupo de decisión', 'Sectores',
                  'Relaciones económicas', 'Días de ingreso a firma'];
  function cmp(a, b) { return a < b ? -1 : a > b ? 1 : 0; }
  function descargarCsv() {
    var sel = seleccion().sort(function (a, b) { return cmp(b.fecha || '', a.fecha || '') || cmp(a.carpeta, b.carpeta); });
    var filas = sel.map(function (r) {
      return [r.carpeta, r.fecha || '', r.tipo, r.decision, r.grupo, r.sectores.join(' | '), r.relaciones.join(' | '), r.dias === null ? '' : r.dias];
    });
    var sufijo = [F.anio && 'anio-' + F.anio, F.tipo && 'tipo-' + F.tipo, F.sector && 'sector-' + F.sector]
      .filter(Boolean).join('_').replace(/[^A-Za-z0-9_-]+/g, '-');
    ANCCsv.download('estadisticas_concentraciones' + (sufijo ? '_' + sufijo : '') + '.csv', ANCCsv.build(CSV_COLS, filas));
  }

  /* ---------- filtros ---------- */
  function opciones(sel, lista) {
    lista.forEach(function (o) { sel.appendChild(h('option', { value: o[0] }, [o[1]])); });
  }
  function armarFiltros() {
    var porAnio = {};
    ROWS.forEach(function (r) { var b = bucket(r); porAnio[b] = (porAnio[b] || 0) + 1; });
    opciones($('f-anio'), [['', 'Todos los años']]
      .concat(YEARS.map(function (y) { return [String(y), y + (D.firmas.anio_parcial && y === Y1 ? ' (parcial)' : '') + ' · ' + fmt(porAnio[y] || 0)]; }))
      .concat([[SF, 'Sin fecha de firma · ' + fmt(porAnio[SF] || 0)]]));
    opciones($('f-tipo'), [['', 'Todos los tipos']].concat(D.tipos.map(function (t) { return [t.nombre, t.nombre + ' · ' + fmt(t.n)]; })));
    opciones($('f-sector'), [['', 'Todos los sectores']].concat(D.sectores.catalogo.map(function (s) { return [s.sector, s.sector + ' · ' + fmt(s.n)]; })));
  }
  function leerHash() {
    var m = {};
    location.hash.replace(/^#/, '').split('&').forEach(function (kv) {
      var i = kv.indexOf('=');
      if (i < 1) return;
      try { m[kv.slice(0, i)] = decodeURIComponent(kv.slice(i + 1)); } catch (e) { /* valor mal formado: se ignora */ }
    });
    return m;
  }
  function aplicarHash() {
    var m = leerHash();
    [['a', 'f-anio', 'anio'], ['t', 'f-tipo', 'tipo'], ['s', 'f-sector', 'sector']].forEach(function (k) {
      var sel = $(k[1]), v = m[k[0]] || '';
      var ok = Array.prototype.some.call(sel.options, function (o) { return o.value === v; });
      sel.value = ok ? v : '';
      F[k[2]] = sel.value;
    });
  }
  function guardarHash() {
    var parts = [];
    if (F.anio) parts.push('a=' + encodeURIComponent(F.anio));
    if (F.tipo) parts.push('t=' + encodeURIComponent(F.tipo));
    if (F.sector) parts.push('s=' + encodeURIComponent(F.sector));
    try { history.replaceState(null, '', location.pathname + location.search + (parts.length ? '#' + parts.join('&') : '')); } catch (e) { /* file:// o iframe */ }
  }

  function render() {
    var sel = seleccion(), G = agregar(sel), filtrado = !!(F.anio || F.tipo || F.sector);
    pintarEstado(G.n, filtrado);
    pintarTiles(G, filtrado);
    pintarGraficos(G, filtrado);
    pintarDecisiones(sel);
    guardarHash();
  }

  $('hasta').textContent = dmy(D.firmas.ultima);
  armarFiltros();
  armarNotas();
  aplicarHash();
  $('filtros').addEventListener('submit', function (e) { e.preventDefault(); });
  ['f-anio', 'f-tipo', 'f-sector'].forEach(function (id) {
    $(id).addEventListener('input', function () {
      F.anio = $('f-anio').value; F.tipo = $('f-tipo').value; F.sector = $('f-sector').value;
      render();
    });
  });
  $('f-limpiar').addEventListener('click', function () {
    ['f-anio', 'f-tipo', 'f-sector'].forEach(function (id) { $(id).value = ''; });
    F.anio = F.tipo = F.sector = '';
    render();
  });
  $('f-csv').addEventListener('click', descargarCsv);
  window.addEventListener('hashchange', function () { aplicarHash(); render(); });
  $('pie').textContent = 'Herramienta de consulta basada en resoluciones y dictámenes publicados. Datos extraídos y clasificados de forma automática; no reemplazan el documento original.';
  render();
})();
</script>
</body>
</html>
"""


def _json_archivo(datos: dict) -> str:
    """data/conc.json: agregados con sangria y UN expediente por linea en "detalle" (diffs legibles en git)."""
    resto = {k: v for k, v in datos.items() if k != "detalle"}
    cuerpo = json.dumps(resto, ensure_ascii=False, indent=1)
    filas = ",\n".join("  " + json.dumps(r, ensure_ascii=False, separators=(",", ":")) for r in datos["detalle"])
    return cuerpo[:-2] + ',\n "detalle": [\n' + filas + "\n ]\n}\n"


def _json_para_script(obj) -> str:
    txt = json.dumps(obj, ensure_ascii=False, separators=(",", ":"))
    # U+2028/2029 romperian el <script>; "</script" cerraria el bloque antes de tiempo
    return txt.replace("\u2028", "\\u2028").replace("\u2029", "\\u2029").replace("</", "<\\/")


def main() -> None:
    datos = construir()
    SALIDA_HTML.parent.mkdir(parents=True, exist_ok=True)
    SALIDA_JSON.parent.mkdir(parents=True, exist_ok=True)
    SALIDA_JSON.write_text(_json_archivo(datos), encoding="utf-8")
    SALIDA_HTML.write_text(TEMPLATE.replace("__DATOS__", _json_para_script(datos)), encoding="utf-8")
    print(f"OK -> {SALIDA_HTML.relative_to(AQUI)} y {SALIDA_JSON.relative_to(AQUI)}")
    print(f"  {datos['registros']} expedientes | firmas {datos['firmas']['primera']} a {datos['firmas']['ultima']} "
          f"({datos['firmas']['sin_fecha']} sin fecha)")
    print("  Decisiones:", ", ".join(f"{g['grupo']}={g['n']}" for g in datos["decisiones"]["grupos"]))
    t = datos["tiempos"]
    print(f"  Ingreso->firma: mediana {t['mediana_global']} d (n={t['n_global']}, cobertura {t['cobertura_pct']} %)")


if __name__ == "__main__":
    main()
