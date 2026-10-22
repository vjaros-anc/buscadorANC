# -*- coding: utf-8 -*-
"""
Arma dist/ con una LISTA BLANCA de lo que publica Cloudflare Pages, sin mover ni cambiar nada del repo.

Sin esto Cloudflare publicaria la RAIZ entera del repo: firm.xlsx, los .py, PROTOCOLO.md, varios/, viejos/...
quedarian servidos por URL. En el proyecto de Pages (Settings -> Builds):

    Build command:           python3 build_site.py
    Build output directory:  dist

El flujo del buscador no cambia: seguis generando index.html en la raiz y subiendo con git como siempre.

Que se publica:
  - sitio:    index.html, googlea22b4e4d6a289f30.html, 404.html, _headers, _redirects, robots.txt (los que existan)
  - pdf:      los pdf/*.pdf de primer nivel y pdf/index.html (el listado del boton "Archivo"); no los CSV,
              ni escaneados/, ni lectura_opi/
  - interna:  interna/ (solo extensiones web). La protege Cloudflare Access (path /interna).
              Todo lo interno va DENTRO de interna/: lo que este afuera es publico.
  - legado:   URLs que hoy sirven y alguien puede usar: productos buscador/index.html,
              pdf/lectura_opi/buscador_opis.html   (--sin-legado las saca)

Al terminar revisa dist/ y falla si aparece un Excel, un .py, un .md o un insumo interno (en Cloudflare, un
build fallido deja el deploy anterior). Solo biblioteca estandar, compatible con Python 3.7+.

Uso:
    python -B build_site.py --reporte        # solo muestra que se publicaria y que dejaria de publicarse
    python -B build_site.py                  # arma dist/
    python -B build_site.py --salida ../dist_prueba --sin-legado
"""
from __future__ import annotations

import argparse
import collections
import fnmatch
import os
import shutil
import sys
from pathlib import Path

AQUI = Path(__file__).resolve().parent

ARCHIVOS_RAIZ = ["index.html", "googlea22b4e4d6a289f30.html", "404.html", "_headers", "_redirects", "robots.txt"]
CARPETAS = ["interna"]
LISTADO_PDF = "pdf/index.html"
LEGADO = ["productos buscador/index.html", "pdf/lectura_opi/buscador_opis.html"]
EXT_WEB = {".html", ".css", ".js", ".json", ".csv", ".txt", ".png", ".jpg", ".jpeg", ".svg", ".ico", ".xml",
           ".webmanifest", ".woff", ".woff2", ".pdf"}
# lo que nunca puede salir publicado, aunque alguien lo agregue a la lista blanca por error
PROHIBIDOS = ["*.xlsx", "*.xlsm", "*.xls", "*.py", "*.pyc", "*.md", "*.jsonl", "*.key", ".env",
              "res_firmadas*", "cotejo_*", "evol_conc*", "*api_key*", "secrets*"]
# nombres de primer nivel que este script puede haber generado: solo en ese caso se borra una salida existente
GENERABLES = set(ARCHIVOS_RAIZ + CARPETAS + ["pdf", "productos buscador"])


def contiene(padre: Path, hijo: Path) -> bool:
    """True si hijo es padre o esta dentro de padre."""
    try:
        hijo.relative_to(padre)
        return True
    except ValueError:
        return False


def todos_los_archivos(raiz: Path, excluir: Path | None = None):
    """Archivos bajo raiz (rutas relativas con /), sin .git ni la carpeta excluir."""
    out = []
    for dp, dn, fn in os.walk(str(raiz)):
        dn[:] = [d for d in dn if d != ".git" and Path(dp, d).resolve() != excluir]
        for f in fn:
            out.append(os.path.relpath(os.path.join(dp, f), str(raiz)).replace(os.sep, "/"))
    return sorted(out)


def seleccionar(todos, con_legado: bool):
    """ruta relativa -> categoria."""
    existen = set(todos)
    sel = {}
    for f in ARCHIVOS_RAIZ:
        if f in existen:
            sel[f] = "sitio"
    for rel in todos:
        partes = rel.split("/")
        if partes[0] in CARPETAS and os.path.splitext(rel)[1].lower() in EXT_WEB:
            sel[rel] = partes[0]
        elif len(partes) == 2 and partes[0] == "pdf" and rel.lower().endswith(".pdf"):
            sel[rel] = "pdf"
    if LISTADO_PDF in existen:
        sel[LISTADO_PDF] = "pdf"
    if con_legado:
        for rel in LEGADO:
            if rel in existen:
                sel[rel] = "legado"
    return sel


def prohibidos(rutas):
    """Las rutas cuyo nombre coincide con PROHIBIDOS (sin distinguir mayusculas)."""
    return [r for r in rutas if any(fnmatch.fnmatch(r.rsplit("/", 1)[-1].lower(), p) for p in PROHIBIDOS)]


def agrupar_excluidos(todos, sel):
    grupos = collections.Counter()
    for rel in todos:
        if rel in sel:
            continue
        partes = rel.split("/")
        if len(partes) == 1:
            grupos["raíz: *" + (os.path.splitext(rel)[1] or rel)] += 1
        elif partes[0] == "pdf":
            grupos["pdf/" + (partes[1] + "/" if len(partes) > 2 else "(no PDF: csv, py…)")] += 1
        else:
            grupos[partes[0] + "/"] += 1
    return grupos


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--salida", default="dist", help="carpeta de salida (por defecto dist, junto a este script)")
    ap.add_argument("--reporte", action="store_true", help="no arma nada: solo informa")
    ap.add_argument("--sin-legado", action="store_true", help="no publica las URLs heredadas")
    args = ap.parse_args()

    salida = Path(args.salida)
    salida = (AQUI / salida if not salida.is_absolute() else salida).resolve()
    if contiene(salida, AQUI):
        print("La carpeta de salida no puede ser el repo ni una carpeta que lo contenga.", file=sys.stderr)
        return 2

    todos = todos_los_archivos(AQUI, salida)
    sel = seleccionar(todos, not args.sin_legado)
    total_mb = sum((AQUI / r).stat().st_size for r in sel) / 1048576.0
    cats = collections.Counter(sel.values())
    print("Rama de Cloudflare: %s | legado: %s" % (os.environ.get("CF_PAGES_BRANCH") or "(local)",
                                                  "no" if args.sin_legado else "sí"))
    print("Se publicarían %d archivos (%.0f MB): %s" % (len(sel), total_mb, ", ".join("%s %d" % kv for kv in sorted(cats.items()))))
    legado = [r for r, c in sel.items() if c == "legado"]
    if legado:
        print("  legado (se mantiene para no cortar URLs): " + ", ".join(legado))
    ex = agrupar_excluidos(todos, sel)
    print("NO se publica: %d archivos" % sum(ex.values()))
    for k, n in sorted(ex.items(), key=lambda kv: -kv[1]):
        print("  %-34s %5d" % (k, n))

    errores = []
    if "index.html" not in sel:
        errores.append("falta index.html en la raíz del repo")
    malos = prohibidos(sel)
    if malos:
        errores.append("la lista blanca incluye archivos que no se pueden publicar: " + ", ".join(malos[:10]))
    if errores:
        for e in errores:
            print("[ERROR] " + e, file=sys.stderr)
        return 1
    if args.reporte:
        return 0

    if salida.exists():
        raros = sorted(e.name for e in salida.iterdir() if e.name not in GENERABLES)
        if raros:
            print("%s existe y trae cosas que este script no genera (%s): borralo a mano o elegí otra carpeta."
                  % (salida, ", ".join(raros[:5])), file=sys.stderr)
            return 2
        shutil.rmtree(str(salida))
    salida.mkdir(parents=True)
    for rel in sorted(sel):
        dst = salida / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(str(AQUI / rel), str(dst))

    # control final sobre lo que quedo armado (no sobre la seleccion): es lo que Cloudflare va a servir
    armados = todos_los_archivos(salida)
    malos = prohibidos(armados)
    if malos:
        print("[ERROR] dist/ quedó con archivos que no se pueden publicar: " + ", ".join(malos[:10]), file=sys.stderr)
        return 1
    if len(armados) != len(sel):
        print("[ERROR] dist/ tiene %d archivos y se seleccionaron %d." % (len(armados), len(sel)), file=sys.stderr)
        return 1
    print("\nOK -> %s  (%d archivos, %.0f MB)" % (salida, len(sel), total_mb))
    return 0


if __name__ == "__main__":
    sys.exit(main())
