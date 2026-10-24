# -*- coding: utf-8 -*-
"""
Publica la biblioteca de remedios UE en /remedios/ a partir de las fichas, sin tocar remedios_ue/.

    remedios/index.html            una tarjeta por ficha, con filtros por tipo y subtipo de remedio, efecto y fase
    remedios/M-xxxxx/index.html    cada ficha (remedios_ue/fichas/M.xxxxx.md) convertida a HTML con el estilo del sitio
    remedios/relaciones.csv        remedios_ue/fichas/relaciones.csv con separador ; para abrir en Excel
    remedios/documentos/index.html los documentos de los 47 casos (y de las revisiones): nuestra copia en PDF y el original
    remedios/pdf/                  las copias de los PDF y catalogo.csv (los trae --pdf-desde, ver abajo)

Lee remedios_ue/casos.csv (fecha, fase, reseña del remedio, enlaces de la Comisión), las fichas y relaciones.csv.
Las carpetas usan guion (M-11253) y no punto, para que Cloudflare no tome ".11253" como extension.

La salida no lleva fecha de generacion: correrlo dos veces da lo mismo. remedios/index.html lleva la huella de
las entradas (verificar_sitio.huella_remedios): si cambia una ficha, verificar_sitio avisa que hay que correr
este script de nuevo.

Los PDF salen de la rama del corpus (corpus-remedios-ue), sin checkout: --pdf-desde lee su reporte.csv con git show,
copia cada PDF a remedios/pdf/ con su nombre sin el hash (M.9969_DEC_01.pdf), verifica el SHA-256 y escribe
remedios/pdf/catalogo.csv (una fila por doc_id: los compromisos que van dentro de la decision apuntan a ese PDF, desde
su primera pagina). Con el catalogo, las fichas enlazan cada doc_id a su PDF y cada cita [p. x] a esa pagina.

El Markdown de las fichas es el de remedios_ue/fichas/PLANTILLA.md: titulos, tablas, listas anidadas, parrafos,
**negrita**, *cursiva* y `codigo`. No hay enlaces ni HTML propio; todo el texto se escapa.

Uso:
    python -B generar_remedios.py
    python -B generar_remedios.py --comprobar     # no escribe; sale con 1 si remedios/ no esta al dia
    git fetch origin corpus-remedios-ue
    python -B generar_remedios.py --pdf-desde origin/corpus-remedios-ue   # copia los PDF y regenera

(-B evita reescribir los .pyc versionados.) Solo biblioteca estandar.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import html
import io
import re
import shutil
import subprocess
import sys
import unicodedata
from pathlib import Path

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI))
from verificar_sitio import huella_remedios  # noqa: E402  (stdlib: la misma huella la recalcula el verificador)

CARPETA = "remedios"
RX_CARPETA_FICHA = re.compile(r"^M-\d+$")
CATALOGO = CARPETA + "/pdf/catalogo.csv"
COLUMNAS_CATALOGO = ["doc_id", "caso_id", "tipo_doc", "titulo", "fecha_doc", "idioma", "archivo", "pagina_inicial",
                     "paginas", "bytes", "sha256", "url_original"]
RX_HASH = re.compile(r"_[0-9a-f]{12}\.pdf$")
# tipos de documentos.csv, en el orden en que se listan
TIPOS_DOC = {
    "DEC": "Decisión", "COMP": "Compromisos", "POST": "Decisión posterior", "CP": "Comunicado",
    "CP_APERTURA": "Apertura de fase II", "MB": "Merger Brief", "DICT": "Comité Consultivo / Consejero Auditor",
    "NOT_PREVIA": "Notificación previa", "RES_DO": "Diario Oficial", "OTRO": "Otro", "SENT": "Tribunal",
}

TIPOS = {"estructural": "Estructural", "conductual": "Conductual", "mixto": "Mixto"}
SUBTIPOS = {
    "desinversion_negocio": "Venta de un negocio",
    "desinversion_activos": "Venta de activos",
    "cesion_espectro_slots": "Espectro o slots",
    "reduccion_participacion": "Reducción de participación",
    "acceso": "Acceso",
    "licencia": "Licencia",
    "interoperabilidad": "Interoperabilidad",
    "no_discriminacion": "No discriminación",
    "separacion": "Separación",
    "suministro": "Suministro",
    "abstencion": "Abstención",
}
EFECTOS = {
    "horizontal_no_coordinado": "Horizontal no coordinado",
    "horizontal_coordinado": "Horizontal coordinado",
    "vertical_cierre_insumos": "Vertical: cierre de insumos",
    "vertical_cierre_clientes": "Vertical: cierre de clientes",
    "conglomerado": "Conglomerado",
    "competencia_potencial": "Competencia potencial",
    "innovacion": "Innovación",
    "informacion_sensible": "Información sensible",
}


def etiqueta(codigo: str, nombres: dict) -> str:
    return nombres.get(codigo) or codigo.replace("_", " ").capitalize()


def valores(celda: str) -> list:
    """'acceso;no_discriminacion' -> ['acceso', 'no_discriminacion'] (regla del ';' de PLANTILLA.md)."""
    return [v.strip() for v in (celda or "").split(";") if v.strip()]


def sin_acentos(texto: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", texto) if not unicodedata.combining(c)).lower()


def dmy(iso: str) -> str:
    p = (iso or "").split("-")
    return "%s/%s/%s" % (p[2], p[1], p[0]) if len(p) == 3 else iso


def carpeta_de(caso_id: str) -> str:
    return caso_id.replace(".", "-")


# ---------- Markdown de las fichas -> HTML ----------

RX_TITULO = re.compile(r"^(#{1,3}) +(.*)$")
RX_ITEM = re.compile(r"^( *)[-*] +(.*)$")
RX_FILA = re.compile(r"^\|.*\|\s*$")
RX_SEPARADOR = re.compile(r"^\|(\s*:?-+:?\s*\|)+\s*$")


def inline(texto: str, citas=None) -> str:
    """Escapa el texto y aplica `codigo`, **negrita** y *cursiva*. El codigo no se interpreta, pero puede quedar
    dentro de una negrita (**29/05/2026 (`doc_id`):**): se reemplaza por una marca y se repone al final.
    citas: funcion que enlaza las citas del resultado a los PDF (ver enlazador); se aplica a cada parrafo, celda
    o item por separado."""
    codigos = []

    def guardar(m):
        codigos.append("<code>%s</code>" % html.escape(m.group(1), quote=False))
        return "\x00%d\x00" % (len(codigos) - 1)

    s = html.escape(re.sub(r"`([^`]+)`", guardar, texto), quote=False)
    s = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", s)
    s = re.sub(r"(?<![\w*])\*(?=\S)([^*]+?)(?<=\S)\*(?![\w*])", r"<em>\1</em>", s)
    s = re.sub(r"\x00(\d+)\x00", lambda m: codigos[int(m.group(1))], s)
    return citas(s) if citas else s


# un doc_id en codigo, DEC o COMP sueltos, o una pagina [p. x] / [pp. x–y] (se enlaza la primera)
RX_CITA = re.compile(r"<code>(M\.\d+_[A-Z0-9_]+)</code>|\b(DEC|COMP)\b|\[pp?\.\s*(\d+)[^\]]*\]")


def enlazador(caso_id: str, documentos: dict, prefijo: str = "../pdf/"):
    """Devuelve la funcion que, en un parrafo ya convertido, enlaza cada doc_id a su PDF y cada [p. x] a la pagina x
    del ultimo documento nombrado antes en ese parrafo: DEC es la decision (DEC_01) y COMP los compromisos (COMP_01,
    que casi siempre son el anexo de la decision: sus paginas son las del PDF de la decision). Sin documento nombrado
    antes, o si no hay copia, la cita queda como texto. documentos: {doc_id: (archivo publicado en remedios/pdf/,
    pagina donde empieza el documento: la de los compromisos dentro de la decision, si no "")}."""
    def enlazar(s: str) -> str:
        actual = [None]

        def cambiar(m):
            if m.group(1):
                archivo, inicio = documentos.get(m.group(1), ("", ""))
                actual[0] = archivo
                if not archivo:
                    return m.group(0)
                return '<a href="%s%s%s">%s</a>' % (prefijo, esc(archivo), "#page=" + inicio if inicio else "", m.group(0))
            if m.group(2):
                actual[0] = documentos.get("%s_%s_01" % (caso_id, m.group(2)), ("", ""))[0]
                if not actual[0] and m.group(2) == "COMP":
                    actual[0] = documentos.get(caso_id + "_DEC_01", ("", ""))[0]
                return m.group(0)
            if not actual[0]:
                return m.group(0)
            return '<a class="anc-cita" href="%s%s#page=%s">%s</a>' % (prefijo, esc(actual[0]), m.group(3), m.group(0))

        return RX_CITA.sub(cambiar, s)
    return enlazar


def _sangria(linea: str) -> int:
    return len(linea) - len(linea.lstrip(" "))


def _tabla(filas: list, citas=None) -> str:
    celdas = [[c.strip() for c in f.strip().strip("|").split("|")] for f in filas]
    cabecera = celdas[0]
    cuerpo = celdas[2:] if len(filas) > 1 and RX_SEPARADOR.match(filas[1].strip()) else celdas[1:]
    out = ['<div class="anc-tablewrap"><table class="anc-table">']
    clave_valor = not any(cabecera)                 # encabezado vacio (| | |): tabla de dato y valor
    if not clave_valor:
        out.append("<thead><tr>%s</tr></thead>" % "".join('<th scope="col">%s</th>' % inline(c, citas) for c in cabecera))
    out.append("<tbody>")
    for fila in cuerpo:
        tds = []
        for j, c in enumerate(fila):
            if clave_valor and j == 0:
                tds.append('<th scope="row">%s</th>' % inline(c.replace("**", "")))
            else:
                tds.append("<td>%s</td>" % inline(c, citas))
        out.append("<tr>%s</tr>" % "".join(tds))
    out.append("</tbody></table></div>")
    return "".join(out)


def _lista(lineas: list, citas=None) -> str:
    """Listas con '- ', anidadas por sangria; una linea sangrada sin '- ' continua el item que la contiene
    (despues de una linea en blanco, como parrafo aparte)."""
    raiz = {"sangria": -2, "hijos": []}           # contenido: ('p', [lineas]) o ('ul', [items])
    pila = [raiz]
    blanco = False
    for linea in lineas:
        if not linea.strip():
            blanco = True
            continue
        m = RX_ITEM.match(linea)
        if m:
            sangria = len(m.group(1))
            while len(pila) > 1 and pila[-1]["sangria"] >= sangria:
                pila.pop()
            padre = pila[-1]
            if not padre["hijos"] or padre["hijos"][-1][0] != "ul":
                padre["hijos"].append(("ul", []))
            item = {"sangria": sangria, "hijos": [("p", [m.group(2).strip()])]}
            padre["hijos"][-1][1].append(item)
            pila.append(item)
        else:
            sangria = _sangria(linea)
            while len(pila) > 2 and pila[-1]["sangria"] + 2 > sangria:
                pila.pop()
            item = pila[-1]
            if blanco or item["hijos"][-1][0] != "p":
                item["hijos"].append(("p", [linea.strip()]))
            else:
                item["hijos"][-1][1].append(linea.strip())
        blanco = False

    def ul(items):
        out = ["<ul>"]
        for it in items:
            partes, primero = [], True
            for tipo, cont in it["hijos"]:
                if tipo == "ul":
                    partes.append(ul(cont))
                elif primero:
                    partes.append(inline(" ".join(cont), citas))
                else:
                    partes.append("<p>%s</p>" % inline(" ".join(cont), citas))
                primero = False
            out.append("<li>%s</li>" % "".join(partes))
        out.append("</ul>")
        return "".join(out)

    return "".join(ul(cont) for _, cont in raiz["hijos"])


def md_a_html(texto: str, nivel_base: int = 0, citas=None) -> str:
    """Markdown de una ficha -> HTML. nivel_base suma a los titulos (## -> h2 con 0); citas, ver inline."""
    lineas = texto.replace("\r\n", "\n").split("\n")
    out, i, n = [], 0, len(lineas)
    while i < n:
        linea = lineas[i]
        if not linea.strip():
            i += 1
            continue
        m = RX_TITULO.match(linea)
        if m:
            h = min(6, len(m.group(1)) + nivel_base)
            ancla = re.match(r"([PR]\d+)\b", m.group(2))
            id_ = ' id="%s"' % ancla.group(1).lower() if ancla else ""
            out.append("<h%d%s>%s</h%d>" % (h, id_, inline(m.group(2).strip()), h))
            i += 1
        elif RX_FILA.match(linea):
            j = i
            while j < n and RX_FILA.match(lineas[j]):
                j += 1
            out.append(_tabla(lineas[i:j], citas))
            i = j
        elif RX_ITEM.match(linea):
            j = i
            while j < n:
                if lineas[j].strip():
                    if RX_TITULO.match(lineas[j]) or RX_FILA.match(lineas[j]):
                        break
                    if not RX_ITEM.match(lineas[j]) and _sangria(lineas[j]) == 0:
                        break
                    j += 1
                    continue
                k = j                               # linea en blanco: sigue la lista si lo proximo es item o sangria
                while k < n and not lineas[k].strip():
                    k += 1
                if k < n and (RX_ITEM.match(lineas[k]) or _sangria(lineas[k]) > 0) and not RX_TITULO.match(lineas[k]):
                    j = k
                    continue
                break
            out.append(_lista(lineas[i:j], citas))
            i = j
        else:
            j = i
            while j < n and lineas[j].strip() and not (RX_TITULO.match(lineas[j]) or RX_FILA.match(lineas[j])
                                                       or RX_ITEM.match(lineas[j])):
                j += 1
            out.append("<p>%s</p>" % inline(" ".join(l.strip() for l in lineas[i:j]), citas))
            i = j
    return "\n".join(out)


# ---------- datos ----------

def leer_csv(ruta: Path) -> list:
    with open(str(ruta), encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def leer_ficha(ruta: Path) -> dict:
    """caso_id, nombre (del titulo '# M.xxxxx — Nombre'), encabezado {dato: valor} y secciones [(titulo, md)]."""
    texto = ruta.read_text(encoding="utf-8").replace("\r\n", "\n")
    lineas = texto.split("\n")
    m = re.match(r"^# +(M\.\d+)\s+[—-]\s+(.+)$", lineas[0])
    if not m:
        raise SystemExit("%s: la primera línea no es '# M.xxxxx — Nombre'" % ruta)
    if m.group(1) != ruta.stem:
        raise SystemExit("%s: el título dice %s" % (ruta, m.group(1)))
    encabezado, secciones, actual = {}, [], None
    previo = []
    for linea in lineas[1:]:
        if linea.startswith("## "):
            actual = [linea[3:].strip(), []]
            secciones.append(actual)
        elif actual is None:
            previo.append(linea)
            c = [x.strip() for x in linea.strip().strip("|").split("|")] if RX_FILA.match(linea) else []
            if len(c) == 2 and c[0].startswith("**"):
                encabezado[c[0].strip("*")] = c[1]
        else:
            actual[1].append(linea)
    return {"caso_id": m.group(1), "nombre": m.group(2).strip(), "encabezado": encabezado,
            "previo": "\n".join(previo).strip(), "secciones": [(t, "\n".join(ls).strip()) for t, ls in secciones]}


def construir_fichas(raiz: Path) -> list:
    base = raiz / "remedios_ue"
    casos = {r["caso_id"]: r for r in leer_csv(base / "casos.csv")}
    relaciones = leer_csv(base / "fichas" / "relaciones.csv")
    fichas = []
    for ruta in sorted((base / "fichas").glob("M.*.md")):
        f = leer_ficha(ruta)
        caso = casos.get(f["caso_id"])
        if caso is None:
            raise SystemExit("%s: %s no está en remedios_ue/casos.csv" % (ruta, f["caso_id"]))
        filas = [r for r in relaciones if r["caso_id"] == f["caso_id"]]
        tipos = sorted({t for r in filas for t in valores(r["tipo_remedio"])})
        f.update({
            "caso": caso,
            "tipo": tipos[0] if len(tipos) == 1 else ("mixto" if tipos else ""),
            "subtipos": sorted({s for r in filas for s in valores(r["subtipo_remedio"])}),
            "efectos": sorted({e for r in filas for e in valores(r["tipo_efecto"])}),
            "problemas": len({r["problema_id"] for r in filas}),
            "remedios": len({r["remedio_id"] for r in filas}),
            "mercados": sorted({r["mercado"] for r in filas}),
        })
        fichas.append(f)
    # las mas recientes primero
    fichas.sort(key=lambda f: (f["caso"]["fecha_decision"], f["caso_id"]), reverse=True)
    return fichas


# ---------- paginas ----------

def esc(texto) -> str:
    return html.escape(str(texto), quote=True)


def pagina(titulo: str, descripcion: str, clase: str, prefijo: str, cabeza: str, cuerpo: str, extra_head: str = "",
           scripts: str = "") -> str:
    return """<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{titulo} — Herramientas ANC</title>
<meta name="description" content="{descripcion}">
{extra_head}<link rel="icon" href="data:,">
<link rel="stylesheet" href="{prefijo}assets/anc.css">
</head>
<body class="anc {clase}">
<div id="anc-nav"></div>
<header class="anc-head"><div class="anc-head-in">
{cabeza}
</div></header>
<main class="anc-main" id="contenido">
{cuerpo}
</main>
<script src="{prefijo}assets/nav.js" defer></script>
{scripts}</body>
</html>
""".format(titulo=esc(titulo), descripcion=esc(descripcion), extra_head=extra_head, prefijo=prefijo, clase=clase,
           cabeza=cabeza, cuerpo=cuerpo, scripts=scripts)


def opciones(fichas: list, campo: str, nombres: dict, todas: str) -> str:
    cuenta = {}
    for f in fichas:
        for v in (f[campo] if isinstance(f[campo], list) else [f[campo]]):
            if v:
                cuenta[v] = cuenta.get(v, 0) + 1
    orden = sorted(cuenta, key=lambda v: etiqueta(v, nombres))
    return '<option value="">%s</option>' % esc(todas) + "".join(
        '<option value="%s">%s (%d)</option>' % (esc(v), esc(etiqueta(v, nombres)), cuenta[v]) for v in orden)


def tarjeta(f: dict) -> str:
    caso = f["caso"]
    texto = " ".join([f["caso_id"], f["nombre"], caso.get("adquirentes", ""), caso.get("objetivos", ""),
                      f["encabezado"].get("Sector", ""), caso.get("resena_remedio", "")] + f["mercados"])
    pills = []
    if f["tipo"]:
        pills.append('<span class="anc-pill">%s</span>' % esc(etiqueta(f["tipo"], TIPOS)))
    pills += ['<span class="anc-pill mute">%s</span>' % esc(etiqueta(s, SUBTIPOS)) for s in f["subtipos"]]
    conteo = "%d problema%s · %d remedio%s" % (f["problemas"], "" if f["problemas"] == 1 else "s",
                                               f["remedios"], "" if f["remedios"] == 1 else "s")
    return """      <a class="anc-tool" href="{href}/" data-tipo="{tipo}" data-subtipos="{subtipos}" data-efectos="{efectos}" data-fase="{fase}" data-texto="{texto}">
        <span class="anc-tool-kind">{caso_id} · Fase {fase} · {fecha}</span>
        <h3>{nombre}</h3>
        <p>{resena}</p>
        <div class="anc-meta">{pills}<span>{conteo}</span></div>
      </a>""".format(
        href=carpeta_de(f["caso_id"]), tipo=esc(f["tipo"]), subtipos=esc(" ".join(f["subtipos"])),
        efectos=esc(" ".join(f["efectos"])), fase=esc(caso.get("fase", "")), texto=esc(sin_acentos(texto)),
        caso_id=esc(f["caso_id"]), fecha=esc(dmy(caso.get("fecha_decision", ""))), nombre=esc(f["nombre"]),
        resena=esc(caso.get("resena_remedio", "")), pills="".join(pills), conteo=esc(conteo))


FILTRAR_JS = """<script>
(function () {
  'use strict';
  var $ = function (id) { return document.getElementById(id); };
  var cards = [].slice.call(document.querySelectorAll('#fichas .anc-tool'));
  var campos = { tipo: $('f-tipo'), subtipos: $('f-subtipo'), efectos: $('f-efecto'), fase: $('f-fase') };
  function norm(s) { return s.normalize('NFD').replace(/[\\u0300-\\u036f]/g, '').toLowerCase(); }
  function aplicar() {
    var q = norm($('f-texto').value.trim()), n = 0;
    cards.forEach(function (c) {
      var ok = !q || q.split(/\\s+/).every(function (w) { return c.dataset.texto.indexOf(w) >= 0; });
      Object.keys(campos).forEach(function (k) {
        var v = campos[k].value;
        if (ok && v) ok = (' ' + c.dataset[k] + ' ').indexOf(' ' + v + ' ') >= 0;
      });
      c.hidden = !ok;
      if (ok) n++;
    });
    $('vacio').hidden = n > 0;
    $('estado').textContent = n === cards.length ? 'Se muestran las ' + n + ' fichas.' : 'Se muestran ' + n + ' de ' + cards.length + ' fichas.';
  }
  $('filtros').addEventListener('input', aplicar);
  $('filtros').addEventListener('submit', function (e) { e.preventDefault(); });
  $('f-limpiar').addEventListener('click', function () { $('filtros').reset(); aplicar(); });
  aplicar();
})();
</script>
"""


def indice(fichas: list, total_casos: int, huella: str, pdfs: int = 0) -> str:
    n = len(fichas)
    cabeza = """  <p class="anc-crumb">Herramientas ANC · Antecedentes internacionales</p>
  <h1>Biblioteca de remedios (UE)</h1>
  <p class="anc-lead">Concentraciones que la Comisión Europea autorizó con condiciones entre el 22/10/2021 y el 22/10/2026: qué
  problema de competencia encontró, qué remedio aceptó y por qué lo consideró suficiente. Cada afirmación cita la decisión con
  la página del PDF.</p>"""
    cuerpo = """  <div class="anc-banner anc-section"><b>Piloto en revisión.</b> {n} de los {total} casos tienen ficha; el resto se suma después
  de la revisión del área. Las fichas resumen la decisión para el trabajo de la ANC: ante cualquier duda, vale el documento original.</div>
  <section class="anc-section anc-filter-panel" aria-label="Filtros y descarga">
    <form class="anc-filters" id="filtros" autocomplete="off">
      <label class="anc-field anc-field-wide">Buscar<input type="search" id="f-texto" placeholder="Empresa, mercado o sector"></label>
      <label class="anc-field">Tipo de remedio<select id="f-tipo">{o_tipo}</select></label>
      <label class="anc-field">Subtipo<select id="f-subtipo">{o_subtipo}</select></label>
      <label class="anc-field">Efecto<select id="f-efecto">{o_efecto}</select></label>
      <label class="anc-field">Fase<select id="f-fase">{o_fase}</select></label>
      <button type="button" class="anc-btn" id="f-limpiar">Limpiar filtros</button>
      <a class="anc-btn" href="relaciones.csv" download title="Una fila por par problema–remedio. CSV con separador ; y UTF-8, listo para abrir en Excel">Descargar CSV</a>
      <a class="anc-btn" href="documentos/">{docs}</a>
    </form>
    <p class="anc-filter-status" id="estado" role="status" aria-live="polite">Se muestran las {n} fichas.</p>
  </section>
  <section class="anc-section" aria-labelledby="h-fichas">
    <h2 id="h-fichas" class="anc-sr">Fichas</h2>
    <div class="anc-cards" id="fichas">
{tarjetas}
    </div>
    <p class="anc-empty" id="vacio" hidden>Ninguna ficha coincide con los filtros.</p>
  </section>
  <section class="anc-section" aria-labelledby="h-leer">
    <h2 id="h-leer">Cómo leer las fichas</h2>
    <div class="anc-card anc-note"><ul>
      <li><b>Problemas (P1, P2…)</b> son los mercados donde la Comisión tuvo serias dudas (fase I) u obstaculización significativa
      (fase II). <b>Remedios (R1, R2…)</b> son los compromisos que aceptó; la ficha dice qué problema resuelve cada uno.</li>
      <li><b>Citas:</b> <code>DEC párr. 192 [p. 50]</code> es el párrafo 192 de la decisión, en la página 50 del PDF (la posición en el
      archivo, no el número impreso). <code>COMP cl. 4</code> es la cláusula 4 de los compromisos. <code>M.11253_POST_01</code> y
      similares son documentos posteriores (aprobación del comprador, dispensas). En la ficha, cada cita abre nuestra copia del
      PDF en esa página.</li>
      <li>La sección <b>Para la ANC</b> es análisis propio, no texto de la Comisión.</li>
      <li>Los rangos como <code>[80-90]%</code> son los de la versión pública; lo tachado en la decisión figura como tachado.</li>
    </ul></div>
  </section>
  <p class="anc-foot">Fuente: decisiones, compromisos y comunicados de la Comisión Europea (competition-cases.ec.europa.eu). Fichas
  elaboradas para la ANC; no son documentos oficiales de la Comisión.</p>""".format(
        n=n, total=total_casos, docs="Documentos (%d PDF)" % pdfs if pdfs else "Documentos",
        o_tipo=opciones(fichas, "tipo", TIPOS, "Todos"), o_subtipo=opciones(fichas, "subtipos", SUBTIPOS, "Todos"),
        o_efecto=opciones(fichas, "efectos", EFECTOS, "Todos"), o_fase=opciones([dict(fase=f["caso"].get("fase", "")) for f in fichas], "fase", {"I": "Fase I", "II": "Fase II"}, "Todas"),
        tarjetas="\n".join(tarjeta(f) for f in fichas))
    return pagina("Biblioteca de remedios (UE)",
                  "Concentraciones autorizadas con condiciones por la Comisión Europea (2021–2026): problema de competencia, "
                  "remedio aceptado y por qué alcanzó, con citas a la decisión.",
                  "anc-remedios", "../", cabeza, cuerpo,
                  extra_head='<meta name="remedios-huella" content="%s">\n' % huella, scripts=FILTRAR_JS)


def pagina_ficha(f: dict, documentos: dict = None) -> str:
    """documentos: ver documentos_de; con ellos se enlazan los doc_id y las citas a los PDF."""
    caso = f["caso"]
    citas = enlazador(f["caso_id"], documentos) if documentos else None
    enlaces = []
    if caso.get("url_caso"):
        enlaces.append('<a href="%s" rel="noopener">caso en la Comisión</a>' % esc(caso["url_caso"]))
    if caso.get("url_comunicado"):
        enlaces.append('<a href="%s" rel="noopener">comunicado</a>' % esc(caso["url_comunicado"]))
    enlaces.append('<a href="../documentos/#%s">documentos del caso</a>' % carpeta_de(f["caso_id"]))
    cabeza = """  <p class="anc-crumb"><a href="../">← Biblioteca de remedios (UE)</a></p>
  <h1>{nombre}</h1>
  <p class="anc-lead">{caso_id} · Fase {fase} · decisión del {fecha}{enlaces}</p>""".format(
        nombre=esc(f["nombre"]), caso_id=esc(f["caso_id"]), fase=esc(caso.get("fase", "")),
        fecha=esc(dmy(caso.get("fecha_decision", ""))), enlaces="".join(" · " + e for e in enlaces))
    partes = ['  <article class="anc-card anc-ficha">', md_a_html(f["previo"], citas=citas)]
    for titulo, md in f["secciones"]:
        propio = titulo.startswith("Para la ANC")
        partes.append('<section class="anc-ficha-sec%s">' % (" propio" if propio else ""))
        partes.append("<h2>%s</h2>" % inline(titulo))
        partes.append(md_a_html(md, citas=citas))
        partes.append("</section>")
    partes.append("  </article>")
    partes.append("""  <p class="anc-foot">Ficha de trabajo de la ANC (piloto en revisión), no es un documento de la Comisión. DEC = decisión;
  COMP = compromisos; [p. x] = página del PDF (abre nuestra copia en esa página). <a href="../">Volver a la biblioteca</a>.</p>""")
    return pagina("%s — %s" % (f["caso_id"], f["nombre"]),
                  "%s: %s. Problema de competencia, remedio y suficiencia según la Comisión Europea." % (f["caso_id"], f["nombre"]),
                  "anc-remedios", "../../", cabeza, "\n".join(partes))


def csv_excel(ruta: Path) -> bytes:
    """relaciones.csv con separador ; (Excel en castellano) y BOM."""
    filas = list(csv.reader(io.StringIO(ruta.read_text(encoding="utf-8-sig"))))
    buf = io.StringIO()
    csv.writer(buf, delimiter=";", lineterminator="\r\n").writerows(filas)
    return ("﻿" + buf.getvalue()).encode("utf-8")


# ---------- biblioteca de PDF ----------

def leer_catalogo(raiz: Path) -> list:
    """Filas de remedios/pdf/catalogo.csv (vacio si todavia no se trajeron los PDF)."""
    ruta = raiz / CATALOGO
    if not ruta.exists():
        return []
    return list(csv.DictReader(io.StringIO(ruta.read_text(encoding="utf-8-sig")), delimiter=";"))


def importar_pdf(raiz: Path, ref: str) -> tuple:
    """Copia los PDF de la rama del corpus (ref, p. ej. origin/corpus-remedios-ue) a remedios/pdf/ y escribe el
    catalogo. Devuelve (PDF publicados, filas del catalogo). Se detiene si un SHA-256 no coincide con el reporte."""
    def git_show(ruta: str) -> bytes:
        r = subprocess.run(["git", "-C", str(raiz), "show", "%s:%s" % (ref, ruta)], capture_output=True)
        if r.returncode:
            raise SystemExit("no puedo leer %s:%s (¿git fetch origin corpus-remedios-ue?)\n%s"
                             % (ref, ruta, r.stderr.decode("utf-8", "replace")))
        return r.stdout

    reporte = [r for r in csv.DictReader(io.StringIO(git_show("reporte.csv").decode("utf-8-sig"))) if r["archivo"]]
    paginas = {}
    for r in csv.DictReader(io.StringIO(git_show("texto_extraido/documentos.csv").decode("utf-8-sig"))):
        if r.get("archivo") and r.get("paginas"):
            paginas[r["archivo"]] = r["paginas"]
    inventario = {d["doc_id"]: d for d in leer_csv(raiz / "remedios_ue" / "documentos.csv")}

    publicado, sha = {}, {}                         # archivo del corpus -> nombre publicado / sha256 esperado
    for r in reporte:
        nombre = RX_HASH.sub(".pdf", r["archivo"].rsplit("/", 1)[-1])
        if nombre in publicado.values() and publicado.get(r["archivo"]) != nombre:
            raise SystemExit("dos PDF distintos se publicarían como %s" % nombre)
        publicado[r["archivo"]] = nombre
        if sha.setdefault(r["archivo"], r["sha256"]) != r["sha256"]:
            raise SystemExit("%s: el reporte trae dos SHA-256 distintos" % r["archivo"])

    destino = raiz / CARPETA / "pdf"
    destino.mkdir(parents=True, exist_ok=True)
    tamanos = {}
    for archivo, nombre in sorted(publicado.items()):
        datos = git_show(archivo)
        if hashlib.sha256(datos).hexdigest() != sha[archivo]:
            raise SystemExit("%s: el SHA-256 no coincide con reporte.csv" % archivo)
        tamanos[archivo] = len(datos)
        if not _igual(destino / nombre, datos):
            (destino / nombre).write_bytes(datos)
    for viejo in destino.glob("*.pdf"):             # PDF que ya no estan en el corpus
        if viejo.name not in publicado.values():
            viejo.unlink()

    filas = []
    for r in reporte:
        d = inventario.get(r["documento_id"], {})
        pc = re.match(r"\d+", r.get("paginas_compromisos") or "")
        filas.append({
            "doc_id": r["documento_id"], "caso_id": r["caso"], "tipo_doc": d.get("tipo_doc") or r["tipo_documental"],
            "titulo": d.get("titulo") or r["titulo"], "fecha_doc": d.get("fecha_doc", ""),
            "idioma": d.get("idioma") or r["idioma"], "archivo": publicado[r["archivo"]],
            "pagina_inicial": pc.group(0) if pc else "", "paginas": paginas.get(r["archivo"], ""),
            "bytes": str(tamanos[r["archivo"]]), "sha256": r["sha256"],
            "url_original": d.get("url") or r.get("url_referencia") or r.get("url_origen", ""),
        })
    filas.sort(key=lambda f: f["doc_id"])
    buf = io.StringIO()
    w = csv.DictWriter(buf, COLUMNAS_CATALOGO, delimiter=";", lineterminator="\r\n")
    w.writeheader()
    w.writerows(filas)
    datos = ("﻿" + buf.getvalue()).encode("utf-8")
    if not _igual(raiz / CATALOGO, datos):
        (raiz / CATALOGO).write_bytes(datos)
    return len(publicado), len(filas)


def documentos_de(catalogo: list, caso_id: str) -> dict:
    """{doc_id: (archivo publicado, pagina inicial)} de un caso, para enlazar desde su ficha."""
    return {f["doc_id"]: (f["archivo"], f["pagina_inicial"]) for f in catalogo if f["caso_id"] == caso_id}


def megas(n) -> str:
    return ("%.1f MB" % (int(n) / 1048576.0)).replace(".", ",")


FILTRAR_DOCS_JS = """<script>
(function () {
  'use strict';
  var $ = function (id) { return document.getElementById(id); };
  var casos = [].slice.call(document.querySelectorAll('.anc-doc-caso'));
  function norm(s) { return s.normalize('NFD').replace(/[\\u0300-\\u036f]/g, '').toLowerCase(); }
  function aplicar() {
    var q = norm($('f-texto').value.trim()), tipo = $('f-tipo').value, copia = $('f-copia').checked, nc = 0, nd = 0;
    casos.forEach(function (c) {
      var ok = !q || q.split(/\\s+/).every(function (w) { return c.dataset.texto.indexOf(w) >= 0; }), filas = 0;
      [].forEach.call(c.querySelectorAll('tbody tr'), function (tr) {
        var ver = ok && (!tipo || tr.dataset.tipo === tipo) && (!copia || tr.dataset.copia === '1');
        tr.hidden = !ver;
        if (ver) filas++;
      });
      c.hidden = filas === 0;
      if (filas) { nc++; nd += filas; }
    });
    [].forEach.call(document.querySelectorAll('.anc-doc-grupo'), function (g) {
      g.hidden = !g.querySelector('.anc-doc-caso:not([hidden])');
    });
    $('vacio').hidden = nc > 0;
    $('estado').textContent = 'Se muestran ' + nd + ' documentos de ' + nc + ' casos.';
  }
  $('filtros').addEventListener('input', aplicar);
  $('filtros').addEventListener('submit', function (e) { e.preventDefault(); });
  $('f-limpiar').addEventListener('click', function () { $('filtros').reset(); aplicar(); });
  aplicar();
})();
</script>
"""


def _nombre_revision(docs: list, caso_id: str) -> str:
    for d in sorted(docs, key=lambda d: d["tipo_doc"] != "DEC"):
        if " — " in d["titulo"]:
            return d["titulo"].split(" — ", 1)[1].strip()
    return caso_id


def pagina_documentos(raiz: Path, catalogo: list, fichas: list) -> str:
    casos = leer_csv(raiz / "remedios_ue" / "casos.csv")
    inventario = leer_csv(raiz / "remedios_ue" / "documentos.csv")
    copia = {f["doc_id"]: f for f in catalogo}
    con_ficha = {f["caso_id"]: f["nombre"] for f in fichas}
    orden = {k: i for i, k in enumerate(TIPOS_DOC)}
    por_caso = {}
    for d in inventario:
        if d["url"] or d["doc_id"] in copia:
            por_caso.setdefault(d["caso_id"], []).append(d)

    def fila(d):
        c = copia.get(d["doc_id"])
        if c:
            pag = "#page=%s" % c["pagina_inicial"] if c["pagina_inicial"] else ""
            if c["pagina_inicial"] and not c["archivo"].startswith(d["doc_id"]):
                txt = "PDF (en %s, p. %s)" % (esc(c["archivo"].rsplit(".", 1)[0]), esc(c["pagina_inicial"]))
            else:
                txt = "PDF"
            detalle = " · ".join(x for x in ("%s p." % c["paginas"] if c["paginas"] and not pag else "",
                                            megas(c["bytes"]) if not pag else "") if x)
            nuestra = '<a href="../pdf/%s%s">%s</a>%s' % (esc(c["archivo"]), pag, txt,
                                                        ' <span class="anc-doc-det">%s</span>' % detalle if detalle else "")
        else:
            nuestra = '<span class="anc-doc-det">—</span>'
        url = d["url"] or (c or {}).get("url_original", "")
        original = '<a href="%s" rel="noopener">original</a>' % esc(url) if url else ""
        return ('<tr data-tipo="{tipo}" data-copia="{tiene}"><td><span class="anc-pill mute">{etq}</span> {titulo}'
                '<br><code>{doc_id}</code></td><td>{fecha}</td><td>{idioma}</td><td>{nuestra}</td><td>{original}</td></tr>').format(
            tipo=esc(d["tipo_doc"]), tiene="1" if c else "0", etq=esc(etiqueta(d["tipo_doc"], TIPOS_DOC)),
            titulo=esc(d["titulo"]), doc_id=esc(d["doc_id"]), fecha=esc(dmy(d["fecha_doc"])), idioma=esc(d["idioma"]),
            nuestra=nuestra, original=original)

    def bloque(caso_id, nombre, meta, docs):
        docs = sorted(docs, key=lambda d: (orden.get(d["tipo_doc"], 99), d["doc_id"]))
        texto = sin_acentos(" ".join([caso_id, nombre] + [d["titulo"] + " " + d["doc_id"] for d in docs]))
        return """      <section class="anc-card anc-doc-caso" id="{ancla}" data-texto="{texto}">
        <h3>{caso_id} · {nombre}</h3>
        <p class="anc-doc-meta">{meta}</p>
        <div class="anc-tablewrap"><table class="anc-table anc-docs">
          <thead><tr><th scope="col">Documento</th><th scope="col">Fecha</th><th scope="col">Idioma</th><th scope="col">Nuestra copia</th><th scope="col">Comisión</th></tr></thead>
          <tbody>{filas}</tbody>
        </table></div>
      </section>""".format(ancla=carpeta_de(caso_id), texto=esc(texto), caso_id=esc(caso_id), nombre=esc(nombre),
                             meta=meta, filas="".join(fila(d) for d in docs))

    principales = []
    for c in sorted(casos, key=lambda c: (c["fecha_decision"], c["caso_id"]), reverse=True):
        meta = ["Fase %s" % esc(c["fase"]), "decisión del %s" % esc(dmy(c["fecha_decision"]))]
        if c["caso_id"] in con_ficha:
            meta.append('<a href="../%s/">ver ficha</a>' % carpeta_de(c["caso_id"]))
        if c.get("url_caso"):
            meta.append('<a href="%s" rel="noopener">caso en la Comisión</a>' % esc(c["url_caso"]))
        principales.append(bloque(c["caso_id"], con_ficha.get(c["caso_id"]) or c["titulo"], " · ".join(meta),
                                  por_caso.get(c["caso_id"], [])))
    ids_casos = {c["caso_id"] for c in casos}
    revisiones = []
    for caso_id in sorted(set(por_caso) - ids_casos, key=lambda x: int(re.sub(r"\D", "", x) or 0), reverse=True):
        docs = por_caso[caso_id]
        revisiones.append(bloque(caso_id, _nombre_revision(docs, caso_id),
                                 "Caso anterior cuyos remedios se revisaron entre 2021 y 2026", docs))

    tipos_presentes = sorted({d["tipo_doc"] for ds in por_caso.values() for d in ds}, key=lambda k: orden.get(k, 99))
    o_tipo = '<option value="">Todos</option>' + "".join(
        '<option value="%s">%s</option>' % (esc(k), esc(etiqueta(k, TIPOS_DOC))) for k in tipos_presentes)
    pdfs = len({f["archivo"] for f in catalogo})
    cabeza = """  <p class="anc-crumb"><a href="../">← Biblioteca de remedios (UE)</a></p>
  <h1>Documentos de los casos</h1>
  <p class="anc-lead">Decisiones, compromisos, decisiones posteriores, comunicados y Merger Briefs de los {n} casos y de las
  revisiones de remedios anteriores: nuestra copia en PDF ({pdfs} archivos, los mismos de los que salen las fichas) y el enlace
  al original de la Comisión.</p>""".format(n=len(casos), pdfs=pdfs)
    cuerpo = """  <section class="anc-section anc-filter-panel" aria-label="Filtros">
    <form class="anc-filters" id="filtros" autocomplete="off">
      <label class="anc-field anc-field-wide">Buscar<input type="search" id="f-texto" placeholder="Caso, empresa o título"></label>
      <label class="anc-field">Tipo de documento<select id="f-tipo">{o_tipo}</select></label>
      <label class="anc-check"><input type="checkbox" id="f-copia"> Solo con copia en PDF</label>
      <button type="button" class="anc-btn" id="f-limpiar">Limpiar filtros</button>
      <a class="anc-btn" href="../pdf/catalogo.csv" download title="Una fila por documento con copia: archivo, páginas, tamaño, SHA-256 y original. Separador ;">Catálogo CSV</a>
    </form>
    <p class="anc-filter-status" id="estado" role="status" aria-live="polite"></p>
  </section>
  <section class="anc-section anc-doc-grupo" aria-labelledby="h-casos">
    <h2 id="h-casos">Casos autorizados con condiciones (22/10/2021–22/10/2026)</h2>
{principales}
  </section>
  <section class="anc-section anc-doc-grupo" aria-labelledby="h-revisiones">
    <h2 id="h-revisiones">Revisiones de remedios de casos anteriores</h2>
{revisiones}
  </section>
  <p class="anc-empty" id="vacio" hidden>Ningún documento coincide con los filtros.</p>
  <p class="anc-foot">Documentos de la Comisión Europea (© Unión Europea), reproducidos según su política de reutilización
  (Decisión 2011/833/UE). La versión oficial es la del enlace «original»; nuestras copias son las versiones públicas descargadas el
  22/10/2026 y verificadas por SHA-256. Las páginas que citan las fichas son las de estos PDF.</p>""".format(
        o_tipo=o_tipo, principales="\n".join(principales), revisiones="\n".join(revisiones))
    return pagina("Documentos de los casos — Biblioteca de remedios (UE)",
                  "Copias en PDF y enlaces a los originales de los documentos de la Comisión Europea usados en la biblioteca de remedios.",
                  "anc-remedios", "../../", cabeza, cuerpo, scripts=FILTRAR_DOCS_JS)


def construir(raiz: Path = AQUI) -> dict:
    """{ruta relativa: bytes} de todo lo que va en remedios/."""
    fichas = construir_fichas(raiz)
    catalogo = leer_catalogo(raiz)
    total = len(leer_csv(raiz / "remedios_ue" / "casos.csv"))
    pdfs = len({c["archivo"] for c in catalogo})
    salida = {CARPETA + "/index.html": indice(fichas, total, huella_remedios(raiz), pdfs).encode("utf-8"),
              CARPETA + "/relaciones.csv": csv_excel(raiz / "remedios_ue" / "fichas" / "relaciones.csv"),
              CARPETA + "/documentos/index.html": pagina_documentos(raiz, catalogo, fichas).encode("utf-8")}
    for f in fichas:
        salida["%s/%s/index.html" % (CARPETA, carpeta_de(f["caso_id"]))] = pagina_ficha(
            f, documentos_de(catalogo, f["caso_id"])).encode("utf-8")
    return salida


def _igual(ruta: Path, datos: bytes) -> bool:
    """Mismo contenido, sin contar fines de linea (una copia de Windows con autocrlf trae CRLF)."""
    return ruta.exists() and ruta.read_bytes().replace(b"\r\n", b"\n") == datos.replace(b"\r\n", b"\n")


def diferencias(raiz: Path, salida: dict) -> list:
    """Rutas que cambiarian al escribir (incluidas las fichas viejas que se borrarian)."""
    cambios = [rel for rel, datos in sorted(salida.items()) if not _igual(raiz / rel, datos)]
    base = raiz / CARPETA
    if base.is_dir():
        for d in sorted(base.iterdir()):
            if d.is_dir() and RX_CARPETA_FICHA.match(d.name) and "%s/%s/index.html" % (CARPETA, d.name) not in salida:
                cambios.append("%s/%s/ (se borra)" % (CARPETA, d.name))
    return cambios


def escribir(raiz: Path, salida: dict) -> None:
    base = raiz / CARPETA
    if base.is_dir():
        for d in base.iterdir():
            if d.is_dir() and RX_CARPETA_FICHA.match(d.name) and "%s/%s/index.html" % (CARPETA, d.name) not in salida:
                shutil.rmtree(str(d))
    for rel, datos in salida.items():
        p = raiz / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        if not _igual(p, datos):
            p.write_bytes(datos)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0].strip())
    ap.add_argument("--comprobar", action="store_true", help="no escribe; sale con 1 si remedios/ no está al día")
    ap.add_argument("--pdf-desde", metavar="REF", help="copia los PDF de esa rama del corpus (origin/corpus-remedios-ue) a remedios/pdf/")
    args = ap.parse_args()
    if args.pdf_desde:
        pdfs, filas = importar_pdf(AQUI, args.pdf_desde)
        print("generar_remedios: %d PDF en %s/pdf/ (%d documentos en el catálogo)" % (pdfs, CARPETA, filas))
    salida = construir(AQUI)
    cambios = diferencias(AQUI, salida)
    if args.comprobar:
        for c in cambios:
            print("desactualizado: " + c)
        print("generar_remedios: %s" % ("al día" if not cambios else "%d archivo(s) por regenerar" % len(cambios)))
        return 1 if cambios else 0
    escribir(AQUI, salida)
    fichas = sum(1 for r in salida if RX_CARPETA_FICHA.match(r.split("/")[1]))
    print("generar_remedios: %d fichas en %s/ (%d archivo(s) cambiaron)" % (fichas, CARPETA, len(cambios)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
