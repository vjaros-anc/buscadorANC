# -*- coding: utf-8 -*-
"""
Publica el buscador de OPIs en /opis/ sin tocar el original ni su pipeline.

Copia el original a /opis/ con la barra común y la presentación de assets/opis-ui.js:
decisión destacada, extracto literal de la respuesta, filtros etiquetados y enlace al PDF.
Con --aviso agrega el cartel de extracción automática sin validar.

Deshace todos los cambios de presentación y comprueba que recupera el original byte a byte.
Los registros (const DATA), los valores de los filtros y sus condiciones quedan idénticos.

Si volves a generar el original con pdf/lectura_opi/04_html.py, corre este script de nuevo.

Uso:
    python -B integrar_opis.py
    python -B integrar_opis.py --aviso
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

AQUI = Path(__file__).parent
ORIGEN = AQUI / "pdf" / "lectura_opi" / "buscador_opis.html"
SALIDA = AQUI / "opis" / "index.html"

AVISO = ('<div class="anc-banner anc-info" role="note" style="max-width:1100px;margin:10px auto 0">'
         '<b>Extracción automática, sin validación humana.</b> Los campos de cada dictamen los extrae un modelo de '
         'lenguaje; usalos como orientación y verificá siempre en el documento original.</div>\n')


def contar_registros(html: str) -> int:
    marca = "const DATA = "
    i = html.index(marca) + len(marca)
    datos, _ = json.JSONDecoder().raw_decode(html[i:])
    return len(datos)


# Cambios de presentación reversibles; const DATA y el filtrado se conservan.
CAMBIOS_UI = [
    ("  <div class=\"filters\">\n    <select id=\"f-sent\"><option value=\"\">Todos los sentidos de respuesta</option></select>\n    <select id=\"f-tipo\"><option value=\"\">Todos los tipos de pregunta</option></select>\n    <select id=\"f-crit\"><option value=\"\">Todos los criterios</option></select>\n    <select id=\"f-ley\"><option value=\"\">Todas las leyes</option></select>\n  </div>\n", "  <div class=\"filters opi-filters\">\n    <label class=\"opi-filter\">Sentido de la respuesta<select id=\"f-sent\"><option value=\"\">Todos los sentidos de respuesta</option></select></label>\n    <label class=\"opi-filter\">Tipo de consulta<select id=\"f-tipo\"><option value=\"\">Todos los tipos de pregunta</option></select></label>\n    <label class=\"opi-filter\">Criterio<select id=\"f-crit\"><option value=\"\">Todos los criterios</option></select></label>\n    <label class=\"opi-filter\">Ley<select id=\"f-ley\"><option value=\"\">Todas las leyes</option></select></label>\n  </div>\n"),
    ("<input id=\"q\" type=\"search\"", "<input id=\"q\" type=\"search\" aria-label=\"Buscar opiniones consultivas\""),
    ("<div id=\"count\"></div>", "<div id=\"count\" role=\"status\" aria-live=\"polite\"></div>"),
    ("<main id=\"list\"></main>", "<main id=\"contenido\"><div id=\"list\"></div></main>"),
    ("o.textContent=v;", "o.textContent=OPIUI.label(v);"),
    ("res.map(d=>`\n    <div class=\"card\">\n      <div class=\"head\">\n        <div class=\"num\">OPI ${esc(d.OPI)}<small>${esc(d.confianza)}</small></div>\n        <div class=\"summary\">\n          <p class=\"preg\">${hl(d.pregunta_texto,terms)}</p>\n          <div class=\"tags\">\n            ${split(d.respuesta_sentido).map(x=>`<span class=\"tag s\">${esc(x)}</span>`).join('')}\n            ${split(d.pregunta_tipo).map(x=>`<span class=\"tag\">${esc(x)}</span>`).join('')}\n            ${split(d.ley).map(x=>`<span class=\"tag\">Ley ${esc(x)}</span>`).join('')}\n            ${d.expediente?`<span class=\"tag\">${esc(d.expediente)}</span>`:''}\n          </div>\n        </div>\n        <div class=\"chev\">▾</div>\n      </div>\n      <div class=\"body\">\n        ${field('Argumento del consultante', d.argumento_consultante, terms)}\n        ${field('Respuesta de la CNDC', d.respuesta_texto, terms)}\n        ${field('Medidas accesorias', d.medidas_accesorias.replace(/\\|/g,' · '), terms)}\n        ${field('Ratio decidendi', d.CAUSA_ratio_decidendi, terms)}\n        ${field('Criterio', d.causa_criterio.replace(/\\|/g,' · '), terms)}\n        ${field('Hecho determinante', d.hecho_determinante, terms)}\n        ${field('Fundamento normativo', d.fundamento_normativo.replace(/\\|/g,' · '), terms)}\n        ${listField('Precedentes citados', split(d.precedentes), terms)}\n        ${listField('Normas invocadas', d.normas_lista, terms)}\n        ${field('Párrafos fuente', d.parrafos.replace(/\\|/g,', '), terms)}\n        ${field('Archivo', d.archivo, terms)}\n      </div>\n    </div>`).join('')", "res.map(d=>OPIUI.card(d, terms, { split, esc, hl, field, listField })).join('')"),
    ("$('#list').addEventListener('click', e=>{\n  const h = e.target.closest('.head'); if(h) h.parentElement.classList.toggle('open');\n});\n", "// Los detalles de cada ficha se abren con el elemento nativo <details>.\n"),
]


def integrar(html: str, rel_assets: str, aviso: bool) -> tuple[str, list[str]]:
    ins_head = f'<link rel="stylesheet" href="{rel_assets}/anc.css">\n'
    ins_nav = '<div id="anc-nav"></div>\n' + (AVISO if aviso else "")
    ins_script = f'<script src="{rel_assets}/nav.js" defer></script>\n'
    ins_ui = f'<script src="{rel_assets}/opis-ui.js"></script>\n'
    for ancla in ("</head>", "<body>\n", "</body>"):
        if html.count(ancla) != 1:
            raise SystemExit(f"El original no tiene exactamente un {ancla!r}: revisar antes de integrar.")
    for ins in (ins_head, ins_nav, ins_script, ins_ui):
        if ins in html:
            raise SystemExit("El original ya contiene algo de lo que se iba a insertar.")
    out = html
    for original, nuevo in CAMBIOS_UI:
        if out.count(original) != 1:
            raise SystemExit("Cambió una plantilla de presentación OPI: revisar antes de integrar.")
        out = out.replace(original, nuevo, 1)
    out = out.replace("</head>", ins_head + ins_ui + "</head>", 1)
    out = out.replace("<body>\n", "<body>\n" + ins_nav, 1)
    out = out.replace("</body>", ins_script + "</body>", 1)
    return out, [ins_head, ins_nav, ins_script, ins_ui]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--origen", default=str(ORIGEN))
    ap.add_argument("--salida", default=str(SALIDA))
    ap.add_argument("--aviso", action="store_true", help="agrega el cartel de 'sin validar' (apagado por defecto)")
    args = ap.parse_args()

    origen, salida = Path(args.origen), Path(args.salida)
    if not origen.exists():
        sys.exit(f"No existe el original: {origen}")
    html = origen.read_bytes().decode("utf-8")          # bytes: no se tocan los saltos de linea
    rel = os.path.relpath(AQUI / "assets", salida.parent).replace(os.sep, "/")
    out, insertados = integrar(html, rel, args.aviso)

    # control: quitando lo insertado se tiene que recuperar el original exacto
    chequeo = out
    for ins in insertados:
        chequeo = chequeo.replace(ins, "", 1)
    for original, nuevo in reversed(CAMBIOS_UI):
        chequeo = chequeo.replace(nuevo, original, 1)
    if chequeo != html:
        sys.exit("Control fallido: la copia difiere del original en algo mas que lo insertado.")

    salida.parent.mkdir(parents=True, exist_ok=True)
    salida.write_bytes(out.encode("utf-8"))
    n = contar_registros(out)
    print(f"OK -> {salida.relative_to(AQUI) if salida.is_relative_to(AQUI) else salida}  ({n} OPI, "
          f"registros identicos al original{', con aviso' if args.aviso else ''})")


if __name__ == "__main__":
    main()
