# -*- coding: utf-8 -*-
"""
Genera un index.html AUTOCONTENIDO (self-contained) para GitHub Pages a partir
de firm.xlsx. Reutiliza la logica de clasificacion del nomenclador existente
(nomenclador_mercados.py) -> ese archivo .py es el unico lugar donde se editan
sectores/sinonimos; el HTML no contiene logica de clasificacion.

Uso:
    python generar_pagina.py            # escribe index.html

Caracteristicas:
  - 50 tarjetas a primera vista, resto por scroll (carga incremental).
  - Filtro por DECISION (articulo de la ley) via desplegable.
  - Dos definiciones de mercado diferenciadas (V1 vigente / V2 referencial) y
    las dos relaciones economicas (V1 / V2).
  - Empresas involucradas agrupadas: Compradoras (primero) y Objeto, con
    buscador dedicado por empresa (boton).
  - Filtro por rango de fecha de firma y orden por fecha (asc/desc).
  - Tabla "Nomenclador por sector" al final (generada en Python).
  - Al hacer clic en la carpeta del expediente se abre su PDF (ver PDF_DIR).
"""
from __future__ import annotations

import html as htmllib
import json
import re
from collections import Counter
from pathlib import Path

import pandas as pd

import nomenclador_mercados as nm

AQUI = Path(__file__).parent
ARCHIVO = AQUI / "firm.xlsx"
SALIDA = AQUI / "index.html"

# --------------------------------------------------------------------------- #
# PDFs: cada expediente enlaza a  <PDF_DIR>/<TIPO>-<NUMERO>.pdf  (ruta relativa
# a index.html). Ej: pdf/CONC-1884.pdf  ->  subi los PDFs a esa carpeta del repo.
# Cambia PDF_DIR si usas otra carpeta.
# --------------------------------------------------------------------------- #
PDF_DIR = "pdf"

# Carpeta de PDFs en GitHub para el boton "Archivo" (se abre en pestaña nueva).
ARCHIVO_URL = "https://github.com/vjaros-anc/buscadorANC/tree/main/pdf"

# nombres reales de columnas en firm.xlsx
C_CARPETA = "Carpeta"
C_CARATULA = "Carátula"
C_FECHA = "Fecha_firma"
C_DECISION = "Decisión"
C_RES = "Número de Resolución"
C_DICT = "Número de Dictamen"
C_MERC_V1 = "Mercados relevantes"
C_MERC_V2 = "mercado_relev_V2"
C_REL_V1 = "Relaciones económicas"
C_REL_V2 = "relaciones_econ_V2"
C_GRUPO = "Grupo/Empresa"
C_EMPRESAS = "Empresas involucradas"
C_TIPO = "tipo"

# --------------------------------------------------------------------------- #
# Categorias del filtro por TIPO. La columna `tipo` del Excel mezcla codigos
# numericos (1..6) y texto ("CONC"/"OPI"), y a veces viene vacia; clasificar_tipo
# la unifica en UNA sola categoria por expediente. Editar aca los codigos/labels.
# --------------------------------------------------------------------------- #
TIPO_LABELS = {
    "1": "Conc. ordinaria",
    "2": "DP",
    "3": "Otros",
    "4": "PROSUM",
    "5": "OPI",
    "6": "Conc. condicionada",
}
# orden en que aparecen los chips (los que no esten se agregan al final)
TIPO_ORDEN = ["Conc. ordinaria", "Conc. condicionada", "PROSUM", "DP", "OPI", "Otros"]


def clasificar_tipo(tipo_raw, carpeta: str) -> str:
    """Unifica la columna `tipo` (numeros 1-6 y/o texto) en una sola categoria."""
    t = nm.clean(tipo_raw).strip()
    # los enteros pueden venir como "1.0" desde pandas
    if re.fullmatch(r"\d+(\.0+)?", t):
        code = t.split(".")[0]
        if code in TIPO_LABELS:
            return TIPO_LABELS[code]
    tl = t.lower()
    if tl.startswith("opi"):
        return "OPI"
    if tl.startswith("dp"):
        return "DP"
    if tl.startswith("inc"):
        return "Otros"
    if tl.startswith("conc"):
        return "Conc. ordinaria"
    # tipo vacio/desconocido -> inferir de la carpeta
    c = (carpeta or "").upper()
    if "PROSUM" in c:
        return "PROSUM"
    if "OPI" in c:
        return "OPI"
    if re.search(r"\bDP\b", c):
        return "DP"
    if re.search(r"\bINC\b", c):
        return "Otros"
    return "Conc. ordinaria"


def _parse_empresas(val) -> tuple[list[str], list[str]]:
    """Devuelve (compradores, objeto) conservando el orden de aparicion."""
    compradores: list[str] = []
    objeto: list[str] = []
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return compradores, objeto
    try:
        arr = json.loads(val)
    except Exception:
        return compradores, objeto
    for e in arr:
        nombre = nm.clean(e.get("nombre", ""))
        rol = (e.get("rol", "") or "").strip().lower()
        if not nombre:
            continue
        if rol == "comprador":
            compradores.append(nombre)
        elif rol == "objeto":
            objeto.append(nombre)
        else:  # rol desconocido -> lo tratamos como objeto para no perderlo
            objeto.append(nombre)
    return compradores, objeto


def build_records() -> list[dict]:
    df = pd.read_excel(ARCHIVO, sheet_name=0, header=0)

    registros: list[dict] = []
    for i, row in df.iterrows():
        carpeta = nm.clean(row.get(C_CARPETA))
        caratula = nm.clean(row.get(C_CARATULA))
        merc_v1 = nm.clean(row.get(C_MERC_V1))
        merc_v2 = nm.clean(row.get(C_MERC_V2))
        if not carpeta and not merc_v1 and not merc_v2 and not caratula:
            continue

        tipo, numero, prosum = nm.parse_carpeta(carpeta)

        # fecha
        fecha_disp, fecha_sort = "", 0
        try:
            dt = pd.to_datetime(row.get(C_FECHA))
            if pd.notna(dt):
                fecha_disp = dt.strftime("%d/%m/%Y")
                fecha_sort = int(dt.strftime("%Y%m%d"))
        except Exception:
            pass

        # Clasificacion por sector. La V1 manda cuando esta disponible; si esta
        # vacia, se usa la V2. Ademas, si la V1 esta pero no permite clasificar
        # (no matchea ningun sector) y existe V2, se reintenta con la V2.
        merc_ref = merc_v1 if merc_v1 else merc_v2
        base_norm = nm.norm(merc_ref + " " + caratula)
        sectores = nm.clasificar_sectores(base_norm)
        if not sectores and merc_v1 and merc_v2:
            sectores = nm.clasificar_sectores(nm.norm(merc_v2 + " " + caratula))
        if not sectores:
            sectores = ["Otros / sin clasificar"]

        # relaciones: V1 manda para las etiquetas de filtro; mostramos ambas crudas
        rel_v1_raw = nm.clean(row.get(C_REL_V1))
        rel_v2_raw = nm.clean(row.get(C_REL_V2))
        rel_tags = nm.normalizar_relaciones(rel_v1_raw if rel_v1_raw else rel_v2_raw)

        cadena = nm.etiquetas_cadena(base_norm)
        geografia = nm.etiquetas_geografia(base_norm)
        sinonimos = nm.extraer_sinonimos(base_norm)

        compradores, objeto = _parse_empresas(row.get(C_EMPRESAS))
        grupo = nm.clean(row.get(C_GRUPO))

        # blobs de busqueda normalizados
        search = nm.norm(" ".join([
            carpeta, caratula, merc_v1, merc_v2,
            " ".join(sectores), " ".join(rel_tags),
            " ".join(cadena), " ".join(geografia), " ".join(sinonimos),
        ]))
        search_emp = nm.norm(" ".join(compradores + objeto + [grupo]))

        # ruta al PDF (relativa a index.html). Vacia si no hay numero de expte.
        pdf = f"{PDF_DIR}/{tipo}-{numero}.pdf" if numero else ""

        registros.append({
            "id": int(i),
            "carpeta": carpeta,
            "tipo": tipo,
            "tipo_cat": clasificar_tipo(row.get(C_TIPO), carpeta),
            "numero": numero,
            "prosum": bool(prosum),
            "excluible": nm.clean(row.get("Excluible")).upper() == "SI",
            "caratula": caratula,
            "fecha": fecha_disp,
            "fsort": fecha_sort,
            "decision": nm.clean(row.get(C_DECISION)),
            "resolucion": nm.clean(row.get(C_RES)),
            "dictamen": nm.clean(row.get(C_DICT)),
            "merc_v1": merc_v1,
            "merc_v2": merc_v2,
            "rel_v1": rel_v1_raw,
            "rel_v2": rel_v2_raw,
            "rel_tags": rel_tags,
            "compradores": compradores,
            "objeto": objeto,
            "grupo": grupo,
            "cadena": cadena,
            "geografia": geografia,
            "sectores": sectores,
            "pdf": pdf,
            "search": search,
            "search_emp": search_emp,
        })
    return registros


def tabla_nomenclador(recs: list[dict]) -> str:
    """Tabla HTML 'Nomenclador por sector' (equivalente a la del .qmd)."""
    cont: Counter = Counter()
    detalle: dict[str, list[str]] = {}
    for r in recs:
        for s in r["sectores"]:
            cont[s] += 1
            detalle.setdefault(s, []).append(f"{r['tipo']} {r['numero']}".strip())

    filas = []
    for s, n in cont.most_common():
        exps = ", ".join(detalle[s])
        filas.append(
            "<tr>"
            f'<td><a href="#bm-top" class="bm-sec-link" data-sec="{htmllib.escape(s)}">'
            f'{htmllib.escape(s)}</a></td>'
            f'<td class="num">{n}</td>'
            f'<td class="bm-exp">{htmllib.escape(exps)}</td>'
            "</tr>"
        )
    return (
        '<table class="bm-tabla"><thead><tr>'
        "<th>Sector</th><th class=\"num\">N.º expedientes</th><th>Expedientes</th>"
        "</tr></thead><tbody>" + "".join(filas) + "</tbody></table>"
    )


def main() -> None:
    recs = build_records()
    sectores = sorted({s for r in recs for s in r["sectores"]})
    relaciones = ["Horizontal", "Vertical", "Conglomerado", "Efectos de cartera"]

    # tipos presentes, en el orden preferido; los inesperados van al final
    tipo_cont = Counter(r["tipo_cat"] for r in recs if r["tipo_cat"])
    tipos = [[t, tipo_cont[t]] for t in TIPO_ORDEN if t in tipo_cont]
    tipos += [[t, tipo_cont[t]] for t in sorted(tipo_cont) if t not in TIPO_ORDEN]

    # decisiones (articulo de la ley) agrupadas ignorando may/min, acentos y
    # espacios: la clave es norm(decision); la etiqueta visible es la variante
    # mas frecuente del grupo. En el HTML se filtra comparando norm(r.decision).
    dec_groups: dict[str, dict] = {}
    for r in recs:
        d = r["decision"]
        if not d:
            continue
        g = dec_groups.setdefault(nm.norm(d), {"labels": Counter(), "total": 0})
        g["labels"][d] += 1
        g["total"] += 1
    decisiones = [
        [k, g["labels"].most_common(1)[0][0], g["total"]]
        for k, g in dec_groups.items()
    ]
    decisiones.sort(key=lambda x: -x[2])

    html = TEMPLATE
    html = html.replace("__DATA__", json.dumps(recs, ensure_ascii=False))
    html = html.replace("__SEC__", json.dumps(sectores, ensure_ascii=False))
    html = html.replace("__REL__", json.dumps(relaciones, ensure_ascii=False))
    html = html.replace("__TIPO__", json.dumps(tipos, ensure_ascii=False))
    html = html.replace("__DEC__", json.dumps(decisiones, ensure_ascii=False))
    html = html.replace("__ARCHIVO__", ARCHIVO_URL)
    html = html.replace("__TABLA__", tabla_nomenclador(recs))
    html = html.replace("__TOTAL__", str(len(recs)))

    SALIDA.write_text(html, encoding="utf-8")

    cont = Counter(s for r in recs for s in r["sectores"])
    print(f"OK -> {SALIDA.name}  ({len(recs)} expedientes)")
    print(f"  {len(decisiones)} decisiones distintas | PDFs esperados en ./{PDF_DIR}/")
    print("  Tipos:", ", ".join(f"{t}={n}" for t, n in tipos))
    for s, n in cont.most_common():
        print(f"  {n:3d}  {s}")


# --------------------------------------------------------------------------- #
# Plantilla HTML (self-contained). Tokens: __DATA__ __SEC__ __REL__ __TIPO__
#                             __DEC__ __ARCHIVO__ __TABLA__ __TOTAL__
# --------------------------------------------------------------------------- #
TEMPLATE = r"""<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Buscador de Mercados Relevantes — ANC</title>
<style>
  :root { --azul:#08519c; --azul2:#2c7fb8; --naranja:#d95f0e; }
  * { box-sizing: border-box; }
  body { font-family: system-ui, -apple-system, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
    margin: 0; color: #1a1a1a; background: #f7f8fa; line-height: 1.45; }
  .bm-header { background: #fff; border-bottom: 1px solid #e2e2e2; padding: 1.1rem 1.2rem .4rem; }
  .bm-header h1 { margin: 0 0 .15rem; font-size: 1.5rem; color: var(--azul); }
  .bm-header p { margin: 0; font-size: .9rem; color: #555; max-width: 70ch; }
  .bm-main { max-width: 1100px; margin: 0 auto; padding: 0 1.2rem 2rem; }

  .bm-controls { background: #f7f8fa; padding: .9rem 0 .7rem;
    border-bottom: 1px solid #e6e6e6; }
  .bm-search { width: 100%; font-size: 1.1rem; padding: .7rem .9rem; border: 2px solid var(--azul2);
    border-radius: 8px; }
  .bm-search:focus { outline: none; border-color: var(--azul); box-shadow: 0 0 0 3px rgba(8,81,156,.15); }

  .bm-row { display: flex; flex-wrap: wrap; gap: .5rem; margin-top: .55rem; align-items: center; }
  .bm-field { display: flex; gap: .3rem; align-items: center; flex: 1 1 260px; }
  .bm-field input[type=search], .bm-field input[type=text] { flex: 1; font-size: .92rem;
    padding: .45rem .6rem; border: 1px solid #bbb; border-radius: 6px; min-width: 0; }
  .bm-field.emp input { border-color: #1a7a3a; }
  .bm-field.dec select { flex: 1; font-size: .9rem; padding: .45rem .5rem; border: 1px solid #6a51a3;
    border-radius: 6px; min-width: 0; max-width: 100%; background: #fff; }
  .bm-btn { cursor: pointer; font-size: .85rem; font-weight: 600; padding: .45rem .8rem;
    border: none; border-radius: 6px; background: var(--azul); color: #fff; white-space: nowrap;
    text-decoration: none; display: inline-block; }
  .bm-btn:hover { background: #063a70; }
  .bm-btn.emp { background: #1a7a3a; } .bm-btn.emp:hover { background: #12572a; }
  .bm-btn.ghost { background: #eee; color: #333; } .bm-btn.ghost:hover { background: #ddd; }
  .bm-btn.arch { background: #08807e; } .bm-btn.arch:hover { background: #05605e; }

  .bm-dates { display: flex; gap: .35rem; align-items: center; font-size: .85rem; color: #555; }
  .bm-dates input[type=date] { font-size: .85rem; padding: .35rem .4rem; border: 1px solid #bbb; border-radius: 6px; }
  .bm-dates select { font-size: .85rem; padding: .38rem .4rem; border: 1px solid #bbb; border-radius: 6px; }

  .bm-filtros { display: flex; flex-wrap: wrap; gap: .3rem; margin-top: .5rem; align-items: center; }
  .bm-lbl { font-size: .75rem; color: #666; margin-right: .2rem; font-weight: 700; letter-spacing: .3px; }
  .bm-chip { cursor: pointer; user-select: none; font-size: .78rem; padding: .16rem .55rem;
    border-radius: 999px; border: 1px solid #bbb; background: #fff; color: #333; white-space: nowrap; }
  .bm-chip:hover { background: #e8f0f7; }
  .bm-chip.on { background: var(--azul2); color: #fff; border-color: var(--azul2); }
  .bm-chip.rel.on { background: var(--naranja); border-color: var(--naranja); }
  .bm-chip.tipo.on { background: #08807e; color: #fff; border-color: #08807e; }

  .bm-count { font-size: .85rem; color: #555; margin: .7rem 0 .4rem; }
  .bm-count b { color: var(--azul); }

  /* resultados: fluyen en la pagina (sin caja con scroll propio); ~50 a primera
     vista y el resto se carga al bajar con el scroll normal de la pagina. */
  .bm-scroll { }

  .bm-card { border: 1px solid #e2e2e2; border-left: 4px solid var(--azul2); border-radius: 8px;
    padding: .75rem .9rem; margin: .6rem; background: #fff; }
  .bm-card.excl { border-left-color: #999; }
  .bm-card h3 { margin: 0 0 .1rem; font-size: 1.02rem; color: var(--azul); display: flex;
    align-items: baseline; gap: .5rem; flex-wrap: wrap; }
  .bm-pdf-link { color: var(--azul); text-decoration: none; border-bottom: 1px dotted var(--azul2); }
  .bm-pdf-link:hover { color: #063a70; border-bottom-style: solid; }
  .bm-pdf-ico { font-size: .8rem; }
  .bm-badge { font-size: .66rem; font-weight: 700; padding: .1rem .45rem; border-radius: 4px;
    background: var(--azul); color: #fff; letter-spacing: .3px; }
  .bm-badge.opi { background: #6a51a3; } .bm-badge.inc { background: #08807e; }
  .bm-badge.dp { background: #b5651d; } .bm-badge.prosum { background: #737373; }
  .bm-badge.excl { background: #b30000; }
  .bm-carat { font-size: .82rem; color: #444; margin: .1rem 0 .3rem; font-style: italic; }
  .bm-decision { font-size: .8rem; color: #4a3a6b; background: #f1ecf9; border-radius: 5px;
    padding: .18rem .5rem; display: inline-block; margin: .1rem 0 .35rem; font-weight: 600; }
  .bm-tags { display: flex; flex-wrap: wrap; gap: .3rem; margin: .35rem 0; }
  .bm-tag { font-size: .71rem; padding: .11rem .5rem; border-radius: 999px; background: #e8f0f7; color: var(--azul); }
  .bm-tag.rel { background: #fde6d3; color: #a63603; }
  .bm-tag.cad { background: #e5f5e0; color: #1a7a3a; }

  .bm-def { margin: .45rem 0; padding: .4rem .6rem; border-radius: 6px; background: #f4f7fb; border-left: 3px solid var(--azul2); }
  .bm-def.v2 { background: #f7f5fb; border-left-color: #8c7bc0; }
  .bm-def-lbl { font-size: .68rem; font-weight: 700; text-transform: uppercase; letter-spacing: .4px;
    color: var(--azul2); margin-bottom: .12rem; }
  .bm-def.v2 .bm-def-lbl { color: #8c7bc0; }
  .bm-def-txt { font-size: .88rem; color: #222; }
  .bm-def-none { color: #aaa; font-style: italic; font-size: .85rem; }

  .bm-emp { margin: .5rem 0; display: flex; flex-direction: column; gap: .3rem; }
  .bm-emp-group { font-size: .84rem; }
  .bm-emp-lbl { display: inline-block; font-size: .66rem; font-weight: 700; text-transform: uppercase;
    letter-spacing: .3px; padding: .08rem .4rem; border-radius: 4px; margin-right: .4rem; vertical-align: middle; }
  .bm-emp-group.compra .bm-emp-lbl { background: #1a7a3a; color: #fff; }
  .bm-emp-group.obj .bm-emp-lbl { background: #a63603; color: #fff; }
  .bm-emp-name { display: inline-block; padding: .08rem .4rem; margin: .1rem .2rem .1rem 0;
    border-radius: 4px; background: #eef3ee; }
  .bm-emp-group.obj .bm-emp-name { background: #faede4; }

  .bm-ids { font-size: .78rem; color: #555; margin-top: .5rem; display: flex; flex-wrap: wrap; gap: 1rem;
    border-top: 1px dashed #ddd; padding-top: .45rem; }
  .bm-ids code { background: #f2f2f2; padding: .05rem .3rem; border-radius: 4px; color: #b30000; }
  .bm-none { padding: 1.6rem; text-align: center; color: #999; }
  .bm-more { padding: 1rem .7rem 1.6rem; text-align: center; color: #888; font-size: .82rem; }
  .bm-more .bm-btn { margin-top: .45rem; font-size: .95rem; padding: .6rem 1.6rem; }
  mark { background: #fff3b0; padding: 0 .05rem; }

  /* Nomenclador por sector */
  .bm-nomen { margin-top: 2rem; }
  .bm-nomen h2 { color: var(--azul); font-size: 1.2rem; border-bottom: 2px solid #e2e2e2; padding-bottom: .3rem; }
  .bm-nomen p { font-size: .85rem; color: #555; }
  .bm-tabla { width: 100%; border-collapse: collapse; font-size: .82rem; }
  .bm-tabla th, .bm-tabla td { text-align: left; padding: .4rem .5rem; border-bottom: 1px solid #eee; vertical-align: top; }
  .bm-tabla th { background: #f0f3f7; color: var(--azul); position: sticky; top: 0; }
  .bm-tabla th.num, .bm-tabla td.num { text-align: right; white-space: nowrap; }
  .bm-tabla .bm-exp { color: #777; font-size: .76rem; }
  .bm-sec-link { color: var(--azul2); text-decoration: none; font-weight: 600; cursor: pointer; }
  .bm-sec-link:hover { text-decoration: underline; }

  @media (max-width: 640px) {
    .bm-field { flex-basis: 100%; }
    .bm-dates { flex-wrap: wrap; }
  }
</style>
</head>
<body>
<div class="bm-header">
  <h1>Buscador de Mercados Relevantes</h1>
  <p>Nomenclador de resoluciones y dictámenes firmados — ANC. Encontrá en qué expediente se
  definió un mercado a partir de un término coloquial (sector, producto, servicio), las
  empresas involucradas o el artículo de la ley. Hacé clic en la carpeta de un expediente
  para abrir su PDF. Búsqueda insensible a acentos y mayúsculas.</p>
</div>

<div class="bm-main">
  <div class="bm-controls" id="bm-top">
    <input id="bm-q" class="bm-search" type="search" autocomplete="off"
      placeholder="Buscar mercado… (ej: leche, eléctrica, audiovisual, petróleo, farma, agro)">

    <div class="bm-row">
      <div class="bm-field emp">
        <input id="bm-emp" type="search" autocomplete="off" placeholder="Buscar por empresa involucrada…">
        <button class="bm-btn emp" id="bm-emp-btn">Buscar empresa</button>
      </div>
      <div class="bm-field dec">
        <span class="bm-lbl">DECISIÓN:</span>
        <select id="bm-dec"><option value="">Todas las decisiones (artículo de la ley)</option></select>
      </div>
    </div>

    <div class="bm-row">
      <div class="bm-dates">
        <span class="bm-lbl">FIRMA:</span>
        <label>desde <input type="date" id="bm-desde"></label>
        <label>hasta <input type="date" id="bm-hasta"></label>
        <span class="bm-lbl" style="margin-left:.4rem">ORDEN:</span>
        <select id="bm-orden">
          <option value="desc">Más reciente primero</option>
          <option value="asc">Más antigua primero</option>
        </select>
      </div>
      <button class="bm-btn ghost" id="bm-reset">Limpiar filtros</button>
      <a class="bm-btn arch" id="bm-archivo" href="__ARCHIVO__" target="_blank"
        rel="noopener" title="Abrir la carpeta de PDFs en GitHub">📁 Archivo (PDFs)</a>
    </div>

    <div class="bm-filtros" id="bm-tipos"><span class="bm-lbl">TIPO:</span></div>
    <div class="bm-filtros" id="bm-sectores"><span class="bm-lbl">SECTOR:</span></div>
    <div class="bm-filtros" id="bm-relaciones"><span class="bm-lbl">RELACIÓN:</span></div>
  </div>

  <div class="bm-count" id="bm-count"></div>
  <div class="bm-scroll" id="bm-scroll"><div id="bm-resultados"></div></div>

  <div class="bm-nomen">
    <h2>Nomenclador por sector</h2>
    <p>Cantidad de expedientes firmados en cada sector del nomenclador (un expediente puede
    figurar en más de un sector). Hacé clic en un sector para filtrar el buscador por él.</p>
    __TABLA__
  </div>
</div>

<script id="bm-data" type="application/json">__DATA__</script>
<script>
(function(){
  const DATA = JSON.parse(document.getElementById('bm-data').textContent);
  const SECTORES = __SEC__;
  const RELACIONES = __REL__;
  const TIPOS = __TIPO__;
  const DECISIONES = __DEC__;
  const BATCH = 50;

  const norm = s => (s||'').normalize('NFD').replace(/[̀-ͯ]/g,'').toLowerCase();
  const esc = s => (s||'').replace(/[&<>]/g, m=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[m]));

  const el = id => document.getElementById(id);
  const q = el('bm-q'), empI = el('bm-emp'), decI = el('bm-dec');
  const desdeI = el('bm-desde'), hastaI = el('bm-hasta'), ordenI = el('bm-orden');
  const cont = el('bm-resultados'), scroll = el('bm-scroll'), countEl = el('bm-count');
  const selSec = new Set(), selRel = new Set(), selTipo = new Set();

  let filtered = [], rendered = 0;

  // desplegable de decisiones (articulo de la ley). El value es la clave
  // normalizada del grupo (norm) y el texto es la variante mas frecuente; asi el
  // desplegable agrupa opciones que solo difieren en may/min, acentos o espacios.
  DECISIONES.forEach(([k, label, n]) => {
    const o = document.createElement('option');
    o.value = k; o.textContent = label + '  (' + n + ')';
    decI.appendChild(o);
  });

  // chips de TIPO (categoria unica por expediente)
  TIPOS.forEach(([t, n]) => {
    const c = document.createElement('span');
    c.className = 'bm-chip tipo'; c.textContent = t + ' (' + n + ')';
    c.onclick = () => { c.classList.toggle('on'); selTipo.has(t)?selTipo.delete(t):selTipo.add(t); render(); };
    el('bm-tipos').appendChild(c);
  });

  // chips
  SECTORES.forEach(s => {
    const c = document.createElement('span');
    c.className = 'bm-chip'; c.textContent = s;
    c.onclick = () => { c.classList.toggle('on'); selSec.has(s)?selSec.delete(s):selSec.add(s); render(); };
    el('bm-sectores').appendChild(c);
  });
  RELACIONES.forEach(s => {
    const c = document.createElement('span');
    c.className = 'bm-chip rel'; c.textContent = s;
    c.onclick = () => { c.classList.toggle('on'); selRel.has(s)?selRel.delete(s):selRel.add(s); render(); };
    el('bm-relaciones').appendChild(c);
  });

  function toInt(dstr){ return dstr ? parseInt(dstr.replace(/-/g,''),10) : 0; }

  function badge(r){
    let cls = ''; const t = r.tipo;
    if(t==='OPI') cls='opi'; else if(t==='INC') cls='inc'; else if(t==='DP') cls='dp';
    let out = '<span class="bm-badge '+cls+'">'+esc(t)+' '+esc(r.numero)+'</span>';
    if(r.prosum) out += '<span class="bm-badge prosum">PROSUM</span>';
    if(r.excluible) out += '<span class="bm-badge excl">EXCLUIBLE</span>';
    return out;
  }
  function hl(txt, terms){
    let out = esc(txt);
    terms.filter(t=>t.length>=3).forEach(t=>{
      try{ const re = new RegExp('('+t.replace(/[.*+?^${}()|[\]\\]/g,'\\$&')+')','gi');
        out = out.replace(re,'<mark>$1</mark>'); }catch(e){}
    });
    return out;
  }

  function compute(){
    const mTerms = norm(q.value).split(/\s+/).filter(Boolean);
    const eTerms = norm(empI.value).split(/\s+/).filter(Boolean);
    const dec = decI.value;
    const dDesde = toInt(desdeI.value), dHasta = toInt(hastaI.value);

    let res = DATA.filter(r => {
      if(mTerms.length && !mTerms.every(t => r.search.includes(t))) return false;
      if(eTerms.length && !eTerms.every(t => r.search_emp.includes(t))) return false;
      if(dec && norm(r.decision) !== dec) return false;
      if(selTipo.size && !selTipo.has(r.tipo_cat)) return false;
      if(selSec.size && !r.sectores.some(s=>selSec.has(s))) return false;
      if(selRel.size && !r.rel_tags.some(x=>selRel.has(x))) return false;
      if((dDesde || dHasta) && !r.fsort) return false;
      if(dDesde && r.fsort < dDesde) return false;
      if(dHasta && r.fsort > dHasta) return false;
      return true;
    });

    const asc = ordenI.value === 'asc';
    res.sort((a,b) => {
      if(!a.fsort && !b.fsort) return 0;
      if(!a.fsort) return 1;
      if(!b.fsort) return -1;
      return asc ? a.fsort - b.fsort : b.fsort - a.fsort;
    });
    return res;
  }

  function cardHTML(r){
    const mHl = q.value.split(/\s+/).filter(Boolean);
    const eHl = empI.value.split(/\s+/).filter(Boolean);

    // titulo: si hay PDF, la carpeta es un enlace que lo abre
    const titulo = r.pdf
      ? '<a class="bm-pdf-link" href="'+esc(r.pdf)+'" target="_blank" rel="noopener" '
        + 'title="Abrir PDF del expediente">'+esc(r.carpeta)+' <span class="bm-pdf-ico">📄↗</span></a>'
      : esc(r.carpeta);

    const secTags = r.sectores.map(s=>'<span class="bm-tag">'+esc(s)+'</span>').join('');
    const relTags = r.rel_tags.map(s=>'<span class="bm-tag rel">'+esc(s)+'</span>').join('');
    const cadTags = r.cadena.map(s=>'<span class="bm-tag cad">'+esc(s)+'</span>').join('');
    const geoTags = r.geografia.map(s=>'<span class="bm-tag cad">'+esc(s)+'</span>').join('');

    const decLine = r.decision ? '<div class="bm-decision">⚖️ '+esc(r.decision)+'</div>' : '';

    let defs = '';
    if(r.merc_v1){
      defs += '<div class="bm-def"><div class="bm-def-lbl">Definición de mercado · V1 (vigente)</div>'
        + '<div class="bm-def-txt">'+hl(r.merc_v1, mHl)+'</div></div>';
    }
    if(r.merc_v2){
      defs += '<div class="bm-def v2"><div class="bm-def-lbl">Definición V2 (referencial)</div>'
        + '<div class="bm-def-txt">'+hl(r.merc_v2, mHl)+'</div></div>';
    }
    if(!r.merc_v1 && !r.merc_v2){
      defs = '<div class="bm-def-none">(sin definición de mercado registrada)</div>';
    }

    let emp = '';
    if(r.compradores.length){
      emp += '<div class="bm-emp-group compra"><span class="bm-emp-lbl">Compradoras</span>'
        + r.compradores.map(n=>'<span class="bm-emp-name">'+hl(n, eHl)+'</span>').join('') + '</div>';
    }
    if(r.objeto.length){
      emp += '<div class="bm-emp-group obj"><span class="bm-emp-lbl">Objeto</span>'
        + r.objeto.map(n=>'<span class="bm-emp-name">'+hl(n, eHl)+'</span>').join('') + '</div>';
    }
    const empBlock = emp ? '<div class="bm-emp">'+emp+'</div>' : '';

    let relLine = '';
    if(r.rel_v1) relLine += '<span>Relación V1: '+esc(r.rel_v1)+'</span>';
    if(r.rel_v2) relLine += '<span>Relación V2: '+esc(r.rel_v2)+'</span>';

    return '<div class="bm-card'+(r.excluible?' excl':'')+'">'
      + '<h3>'+badge(r)+' '+titulo+'</h3>'
      + '<div class="bm-carat">'+hl(r.caratula, mHl)+'</div>'
      + decLine
      + '<div class="bm-tags">'+secTags+relTags+cadTags+geoTags+'</div>'
      + defs
      + empBlock
      + '<div class="bm-ids">'
      +   '<span>📄 Resolución: <code>'+(esc(r.resolucion)||'—')+'</code></span>'
      +   '<span>📝 Dictamen: <code>'+(esc(r.dictamen)||'—')+'</code></span>'
      +   '<span>📅 Firma: '+(esc(r.fecha)||'—')+'</span>'
      +   relLine
      + '</div></div>';
  }

  function appendBatch(){
    const slice = filtered.slice(rendered, rendered + BATCH);
    const wrap = document.createElement('div');
    wrap.innerHTML = slice.map(cardHTML).join('');
    while(wrap.firstChild) cont.appendChild(wrap.firstChild);
    rendered += slice.length;
    updateMore();
  }

  // pie de la lista: contador + boton "Mostrar todo" (queda antes del nomenclador)
  function updateMore(){
    let more = el('bm-more'); if(more) more.remove();
    if(rendered < filtered.length){
      const restan = filtered.length - rendered;
      const m = document.createElement('div');
      m.id = 'bm-more'; m.className = 'bm-more';
      const info = document.createElement('div');
      info.textContent = 'Mostrando ' + rendered + ' de ' + filtered.length;
      const btn = document.createElement('button');
      btn.className = 'bm-btn'; btn.id = 'bm-showall';
      btn.textContent = 'Mostrar todo (' + restan + ' restantes)';
      btn.onclick = showAll;
      m.appendChild(info);
      m.appendChild(btn);
      cont.appendChild(m);
    }
  }

  // muestra de una vez todos los resultados restantes
  function showAll(){
    const slice = filtered.slice(rendered);
    const wrap = document.createElement('div');
    wrap.innerHTML = slice.map(cardHTML).join('');
    while(wrap.firstChild) cont.appendChild(wrap.firstChild);
    rendered = filtered.length;
    updateMore();
  }

  function render(){
    filtered = compute();
    rendered = 0;
    cont.innerHTML = '';
    countEl.innerHTML = '<b>'+filtered.length+'</b> resultado(s) de '+DATA.length+' expedientes firmados';
    if(!filtered.length){
      cont.innerHTML = '<div class="bm-none">Sin resultados. Probá otro término o quitá filtros.</div>';
      return;
    }
    appendBatch();
  }

  // eventos
  q.addEventListener('input', render);
  decI.addEventListener('change', render);
  ordenI.addEventListener('change', render);
  desdeI.addEventListener('change', render);
  hastaI.addEventListener('change', render);
  el('bm-emp-btn').addEventListener('click', render);
  empI.addEventListener('keydown', e => { if(e.key==='Enter') render(); });
  empI.addEventListener('search', render);  // limpiar con la X
  el('bm-reset').addEventListener('click', () => {
    q.value=''; empI.value=''; decI.value=''; desdeI.value=''; hastaI.value=''; ordenI.value='desc';
    selSec.clear(); selRel.clear(); selTipo.clear();
    document.querySelectorAll('.bm-chip.on').forEach(c=>c.classList.remove('on'));
    render();
  });

  // clic en un sector de la tabla "Nomenclador por sector" -> filtra por ese sector
  document.querySelectorAll('.bm-sec-link').forEach(a => {
    a.addEventListener('click', () => {
      const s = a.dataset.sec;
      selSec.clear();
      document.querySelectorAll('#bm-sectores .bm-chip').forEach(c => {
        const on = c.textContent === s;
        c.classList.toggle('on', on);
        if(on) selSec.add(s);
      });
      render();
    });
  });

  render();
})();
</script>
</body>
</html>
"""


if __name__ == "__main__":
    main()
