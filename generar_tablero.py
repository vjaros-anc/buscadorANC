# -*- coding: utf-8 -*-
"""
Genera el tablero publico de resoluciones firmadas:

    conc/index.html     pagina autocontenida (usa assets/ del sitio)
    data/conc.json      los mismos agregados, para reutilizar (schema_version 1)

Lee el mismo maestro que el buscador (firm.xlsx) y reutiliza generar_pagina.build_records()
por import: no modifica ni duplica la logica del buscador. Todo sale AGREGADO: el tablero no
republica nombres de empresas.

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

    # ---- 3. sectores (un expediente puede estar en varios) ----
    cont_sec = collections.Counter(s for r in recs for s in r["sectores"])
    top = [(s, n) for s, n in cont_sec.most_common() if s != SIN_CLASIFICAR][:TOP_SECTORES]
    sectores = [{"sector": s, "n": n, "pct": _pct(n, total), "sin_dato": False} for s, n in top]
    sectores.append({"sector": SIN_CLASIFICAR, "n": cont_sec.get(SIN_CLASIFICAR, 0),
                     "pct": _pct(cont_sec.get(SIN_CLASIFICAR, 0), total), "sin_dato": True})

    # ---- 4. relaciones económicas ----
    cont_rel = collections.Counter(t for r in recs for t in r["rel_tags"])
    relaciones = [{"relacion": t, "n": cont_rel.get(t, 0), "pct": _pct(cont_rel.get(t, 0), total), "sin_dato": False}
                  for t in ("Horizontal", "Vertical", "Conglomerado", "Efectos de cartera")]
    relaciones.sort(key=lambda d: -d["n"])
    sin_rel = sum(1 for r in recs if not r["rel_tags"])
    relaciones.append({"relacion": "Sin dato", "n": sin_rel, "pct": _pct(sin_rel, total), "sin_dato": True})

    # ---- 5. tiempo ingreso -> firma, ordinarias vs PROSUM ----
    dias_por = collections.defaultdict(list)
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

    # ---- 6. cobertura de campos ----
    def cuenta(f):
        return sum(1 for r in recs if f(r))
    campos = [
        ("Fecha de firma", cuenta(lambda r: r["fsort"])),
        ("Número de resolución", cuenta(lambda r: r["resolucion"])),
        ("Número de dictamen", cuenta(lambda r: r["dictamen"])),
        ("PDF enlazado", cuenta(lambda r: r["pdf"])),
        ("Empresas involucradas", cuenta(lambda r: r["compradores"] or r["objeto"])),
        ("Decisión", cuenta(lambda r: r["decision"])),
        ("Grupo / empresa", cuenta(lambda r: r["grupo"])),
        ("Mercado relevante", cuenta(lambda r: r["merc_v1"] or r["merc_v2"])),
        ("Fecha de ingreso", sum(1 for r in recs if ingreso[r["id"]])),
        ("Relaciones económicas", cuenta(lambda r: r["rel_v1"] or r["rel_v2"])),
    ]
    cobertura = sorted([{"campo": c, "n": n, "pct": _pct(n, total)} for c, n in campos], key=lambda d: -d["n"])
    pct_de = {c["campo"]: c["pct"] for c in cobertura}

    tipos = collections.Counter(r["tipo_cat"] for r in recs)
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
        "anio_tipo": {"categorias": categorias, "nombres": nombres,
                      "series": [{"clave": k, "nombre": nombre, "valores": por_clave[k]} for k, nombre, _ in claves]},
        "decisiones": {"grupos": decisiones, "variantes_texto": variantes},
        "sectores": {"items": sectores, "total_sectores": len(cont_sec), "top": TOP_SECTORES},
        "relaciones": relaciones,
        "tiempos": tiempos,
        "cobertura": cobertura,
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
<meta name="description" content="Estadísticas agregadas de las resoluciones, dictámenes y opiniones consultivas publicados: firmas por año, decisiones, sectores y tiempos de trámite.">
<link rel="icon" href="data:,">
<link rel="stylesheet" href="../assets/anc.css">
</head>
<body class="anc">
<div id="anc-nav"></div>
<header class="anc-head"><div class="anc-head-in">
  <h1>Estadísticas de concentraciones</h1>
  <p class="anc-lead">Resoluciones, dictámenes y opiniones consultivas del <a href="../">Buscador de Mercados Relevantes</a>, contados
  sobre el mismo maestro de datos. Todo es agregado: no se muestran nombres de empresas. Los datos llegan hasta el
  <b id="hasta"></b>.</p>
</div></header>

<main class="anc-main">
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
<script src="../assets/nav.js" defer></script>
<script>
(function () {
  var D = JSON.parse(document.getElementById('anc-data').textContent);
  var A = window.ANCCharts, h = A.h, fmt = A.fmt, pct = A.pct;
  var COLOR = { ordinaria: 'var(--anc-s1)', prosum: 'var(--anc-s2)', opi: 'var(--anc-s3)', otros: 'var(--anc-other)' };
  function dmy(iso) { var p = iso.split('-'); return p[2] + '/' + p[1] + '/' + p[0]; }
  function $(id) { return document.getElementById(id); }

  $('hasta').textContent = dmy(D.firmas.ultima);

  /* ---- indicadores ---- */
  var t = D.por_tipo, otros = (t['Otros'] || 0) + (t['Conc. condicionada'] || 0) + (t['DP'] || 0);
  var tiles = [
    { hero: true, l: 'Expedientes en el buscador', v: fmt(D.registros),
      n: fmt(t['Conc. ordinaria'] || 0) + ' ordinarias · ' + fmt(t['PROSUM'] || 0) + ' PROSUM · ' + fmt(t['OPI'] || 0) + ' OPI · ' + fmt(otros) + ' otros' },
    { l: 'Con fecha de firma', v: fmt(D.firmas.con_fecha),
      n: dmy(D.firmas.primera) + ' a ' + dmy(D.firmas.ultima) + ' · ' + fmt(D.firmas.sin_fecha) + ' sin fecha' },
    { l: 'Con decisión cargada', v: pct(D.kpi.pct_decision), n: 'El resto figura como «Sin dato»' },
    { l: 'Con empresas identificadas', v: pct(D.kpi.pct_empresas), n: 'Compradores u objeto' },
    { l: 'Mediana ingreso → firma', v: fmt(D.kpi.mediana_dias) + ' días', n: 'n = ' + fmt(D.kpi.n_dias) + ' · cobertura ' + pct(D.kpi.cobertura_dias_pct) }
  ];
  tiles.forEach(function (x) {
    $('tiles').appendChild(h('div', { class: 'anc-tile' + (x.hero ? ' hero' : '') }, [
      h('div', { class: 'anc-tile-l' }, [x.l]), h('div', { class: 'anc-tile-v' }, [x.v]), h('div', { class: 'anc-tile-n' }, [x.n])]));
  });

  /* ---- firmas por año y tipo ---- */
  A.stackedColumns($('ch-anio'), {
    title: 'Firmas por año y tipo de expediente',
    subtitle: 'Cantidad según la fecha de firma' + (D.firmas.anio_parcial ? '. El último año llega hasta el ' + dmy(D.firmas.ultima) + '.' : '.'),
    categories: D.anio_tipo.categorias, catNames: D.anio_tipo.nombres, catHeader: 'Año de firma', unit: 'expedientes',
    series: D.anio_tipo.series.map(function (s) { return { label: s.nombre, color: COLOR[s.clave], values: s.valores }; }),
    note: 'PROSUM (procedimiento simplificado) aparece recién desde 2024. «s/f» agrupa los expedientes sin fecha de firma cargada.'
  });

  /* ---- decisiones ---- */
  A.hbars($('ch-dec'), {
    title: 'Decisiones', unit: 'expedientes',
    subtitle: 'El texto libre de la columna Decisión (' + D.decisiones.variantes_texto + ' variantes) se agrupa en categorías; la celda vacía cuenta como «Sin dato».',
    items: D.decisiones.grupos.map(function (g) {
      return { label: g.grupo, value: g.n, pct: g.pct, muted: g.sin_dato, note: g.regla };
    })
  });

  /* ---- sectores ---- */
  A.hbars($('ch-sec'), {
    title: 'Sectores', unit: 'expedientes',
    subtitle: 'Un expediente puede figurar en más de un sector. Se muestran los ' + D.sectores.top + ' con más expedientes (el catálogo tiene ' + D.sectores.total_sectores + ').',
    items: D.sectores.items.map(function (x) {
      return { label: x.sector, value: x.n, pct: x.pct, muted: x.sin_dato, note: x.sin_dato ? 'Sin clasificar en el nomenclador de mercados.' : null };
    })
  });

  /* ---- tiempos ---- */
  var T = D.tiempos;
  A.lines($('ch-tiempos'), {
    title: 'Tiempo entre ingreso y firma',
    subtitle: 'Mediana de días corridos según el año de firma. Solo se dibujan los años con ' + T.min_n + ' o más expedientes.',
    categories: T.anios, catHeader: 'Año de firma', valueSuffix: ' d', height: 290,
    series: T.series.map(function (s) {
      return { label: s.nombre, color: COLOR[s.clave], values: s.valores, n: s.n,
        legendExtra: s.mediana_total === null ? '' : '· mediana total ' + fmt(s.mediana_total) + ' d (n = ' + fmt(s.n_total) + ')' };
    }),
    note: 'No es el plazo legal ni descuenta suspensiones: resta la fecha de ingreso a la de firma tal como están cargadas. Solo ' +
      pct(T.cobertura_pct) + ' de los expedientes tiene ambas fechas; en PROSUM, todos.'
  });

  /* ---- relaciones y cobertura ---- */
  A.hbars($('ch-rel'), {
    title: 'Relaciones económicas', unit: 'expedientes',
    subtitle: 'Un expediente puede tener más de una relación. Cuando falta el dato queda «Sin dato».',
    items: D.relaciones.map(function (x) { return { label: x.relacion, value: x.n, pct: x.pct, muted: x.sin_dato }; })
  });
  A.hbars($('ch-cob'), {
    title: 'Cobertura de datos', unit: 'expedientes',
    subtitle: 'Porcentaje de expedientes con cada campo cargado en el maestro.',
    items: D.cobertura.map(function (x) { return { label: x.campo, value: x.n, pct: x.pct }; })
  });

  /* ---- notas ---- */
  var notas = $('notas');
  var ul = h('ul', null, [
    h('li', null, ['Fuente: maestro ', h('code', null, ['firm.xlsx']), ' (' + fmt(D.registros) + ' expedientes publicados en el buscador). Generado el ' + dmy(D.generado) + '.']),
    h('li', null, ['Los datos son los que están cargados: los campos vacíos se muestran como «Sin dato» o como cobertura, nunca se completan.']),
    h('li', null, ['La clasificación por sector y por relación económica sale del nomenclador del buscador (automática); verificar siempre en el documento original.']),
    h('li', null, ['«Tipo» sigue la columna del Excel: ordinarias, PROSUM, OPI y otros (condicionadas, incidentes). Los incidentes y disposiciones cuentan como expedientes propios.'])
  ]);
  notas.appendChild(ul);
  var tbody = D.decisiones.grupos.map(function (g) {
    return h('tr', null, [h('th', { scope: 'row' }, [g.grupo]), h('td', null, [g.regla]), h('td', { class: 'num' }, [fmt(g.n)])]);
  });
  notas.appendChild(h('details', { class: 'anc-det' }, [
    h('summary', null, ['Cómo se agrupan las decisiones (para revisar)']),
    h('div', { class: 'anc-tablewrap' }, [h('table', { class: 'anc-table' }, [
      h('caption', null, ['Reglas de agrupación de la columna Decisión']),
      h('thead', null, [h('tr', null, [h('th', { scope: 'col' }, ['Grupo']), h('th', { scope: 'col' }, ['Regla']), h('th', { scope: 'col', class: 'num' }, ['Expedientes'])])]),
      h('tbody', null, tbody)])])
  ]));
  $('pie').textContent = 'Herramienta de consulta basada en resoluciones y dictámenes publicados. Datos extraídos y clasificados de forma automática; no reemplazan el documento original.';
})();
</script>
</body>
</html>
"""


def _json_para_script(obj) -> str:
    txt = json.dumps(obj, ensure_ascii=False, separators=(",", ":"))
    # U+2028/2029 romperian el <script>; "</script" cerraria el bloque antes de tiempo
    return txt.replace("\u2028", "\\u2028").replace("\u2029", "\\u2029").replace("</", "<\\/")


def main() -> None:
    datos = construir()
    SALIDA_HTML.parent.mkdir(parents=True, exist_ok=True)
    SALIDA_JSON.parent.mkdir(parents=True, exist_ok=True)
    SALIDA_JSON.write_text(json.dumps(datos, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    SALIDA_HTML.write_text(TEMPLATE.replace("__DATOS__", _json_para_script(datos)), encoding="utf-8")
    print(f"OK -> {SALIDA_HTML.relative_to(AQUI)} y {SALIDA_JSON.relative_to(AQUI)}")
    print(f"  {datos['registros']} expedientes | firmas {datos['firmas']['primera']} a {datos['firmas']['ultima']} "
          f"({datos['firmas']['sin_fecha']} sin fecha)")
    print("  Decisiones:", ", ".join(f"{g['grupo']}={g['n']}" for g in datos["decisiones"]["grupos"]))
    t = datos["tiempos"]
    print(f"  Ingreso->firma: mediana {t['mediana_global']} d (n={t['n_global']}, cobertura {t['cobertura_pct']} %)")


if __name__ == "__main__":
    main()
