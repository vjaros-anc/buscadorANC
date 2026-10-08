#!/usr/bin/env python3
"""Copia únicamente archivos publicables a public/, sin tocar el flujo mensual.

Este comando NO despliega ni modifica la configuración de Cloudflare.
"""
from __future__ import annotations

import hashlib
import json
import re
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "public"
FILES = ["index.html", "googlea22b4e4d6a289f30.html", "assets/portal.css", "assets/portal.js",
         "herramientas/index.html", "opis/index.html", "conc/index.html", "noticias/index.html", "seguimiento/index.html",
         "data/conc.json", "data/monitor.sample.json", "data/seguimiento.sample.json"]


def main() -> None:
    if OUTPUT.is_symlink():
        raise SystemExit("public/ no puede ser un enlace simbólico")
    # No se incorpora monitor.json ni ninguna carpeta de insumos internos.
    for path in FILES:
        source = ROOT / path
        if not source.is_file() or source.is_symlink():
            raise SystemExit(f"Archivo publicable ausente o no regular: {path}")
    dashboard = json.loads((ROOT / "data/conc.json").read_text())
    if dashboard["index_sha256"] != hashlib.sha256((ROOT / "index.html").read_bytes()).hexdigest():
        raise SystemExit("El corpus cambió: ejecutá primero scripts/generar_portal.py")
    for path in ["data/monitor.sample.json", "data/seguimiento.sample.json"]:
        if json.loads((ROOT / path).read_text()).get("demo") is not True:
            raise SystemExit(f"La salida de prueba solo admite datos ficticios: {path}")
    if OUTPUT.exists():
        shutil.rmtree(OUTPUT)
    OUTPUT.mkdir()
    files = list(FILES)
    # Se mantienen los nombres actuales de PDFs, incluidas las extensiones .PDF.
    # No se corrigen enlaces ni se incorporan scripts de pdf/lectura_opi/.
    files += [str(path.relative_to(ROOT)) for path in sorted((ROOT / "pdf").iterdir())
              if path.is_file() and not path.is_symlink() and re.fullmatch(r"(?:CONC|OPI|DP|INC)-[\w-]+\.(?:pdf|PDF)", path.name)]
    for relative in files:
        target = OUTPUT / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / relative, target)
    (OUTPUT / "404.html").write_text('<!doctype html><html lang="es"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
                                      '<title>Página no encontrada · ANC</title><h1>Página no encontrada</h1><p>La dirección solicitada no existe.</p>'
                                      '<a href="/herramientas/">Volver al portal</a></html>', encoding="utf-8")
    (OUTPUT / "_headers").write_text('/*\n  X-Content-Type-Options: nosniff\n  Referrer-Policy: strict-origin-when-cross-origin\n'
                                     '  X-Robots-Tag: noindex, nofollow\n/data/*\n  Cache-Control: no-store\n', encoding="utf-8")
    print(f"Preview preparado en {OUTPUT}: {len(files)+2} archivos. Entrada: /herramientas/")
    print("No se copiaron Excel, scripts, insumos internos ni claves. El index original se copió sin cambios.")


if __name__ == "__main__":
    main()
