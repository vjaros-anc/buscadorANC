# -*- coding: utf-8 -*-
"""
Publica el buscador de OPIs en /opis/ sin tocar el original ni su pipeline.

Copia  pdf/lectura_opi/buscador_opis.html  ->  opis/index.html  insertando SOLO tres fragmentos:
    1. <link> a assets/anc.css           (antes de </head>)
    2. <div id="anc-nav"></div>          (despues de <body>)
    3. <script> de assets/nav.js         (antes de </body>)
Con --aviso agrega ademas un cartel "extraccion automatica, sin validar" (apagado por defecto).

Despues comprueba que, quitando lo insertado, se recupera el original byte a byte: los registros
(const DATA) quedan identicos, sin correcciones ni cambios de contenido.

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


def integrar(html: str, rel_assets: str, aviso: bool) -> tuple[str, list[str]]:
    ins_head = f'<link rel="stylesheet" href="{rel_assets}/anc.css">\n'
    ins_nav = '<div id="anc-nav"></div>\n' + (AVISO if aviso else "")
    ins_script = f'<script src="{rel_assets}/nav.js" defer></script>\n'
    for ancla in ("</head>", "<body>\n", "</body>"):
        if html.count(ancla) != 1:
            raise SystemExit(f"El original no tiene exactamente un {ancla!r}: no se puede integrar sin riesgo.")
    for ins in (ins_head, ins_nav, ins_script):
        if ins in html:
            raise SystemExit("El original ya contiene algo de lo que se iba a insertar.")
    out = html.replace("</head>", ins_head + "</head>", 1)
    out = out.replace("<body>\n", "<body>\n" + ins_nav, 1)
    out = out.replace("</body>", ins_script + "</body>", 1)
    return out, [ins_head, ins_nav, ins_script]


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
    if chequeo != html:
        sys.exit("Control fallido: la copia difiere del original en algo mas que lo insertado.")

    salida.parent.mkdir(parents=True, exist_ok=True)
    salida.write_bytes(out.encode("utf-8"))
    n = contar_registros(out)
    print(f"OK -> {salida.relative_to(AQUI) if salida.is_relative_to(AQUI) else salida}  ({n} OPI, "
          f"registros identicos al original{', con aviso' if args.aviso else ''})")


if __name__ == "__main__":
    main()
