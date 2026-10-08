# -*- coding: utf-8 -*-
"""
OPCIONAL. Arma dist/ con una LISTA BLANCA de lo que se publica, sin mover ni cambiar nada del repo.

Hoy Cloudflare Pages publica la RAIZ del repo tal cual: firm.xlsx, los .py, PROTOCOLO.md, varios/, viejos/...
quedan servidos por URL. Con este script, Cloudflare publica solo dist/:

    Build command:           python3 build_site.py
    Build output directory:  dist

El flujo del buscador no cambia: seguis generando index.html en la raiz y subiendo con git como siempre.
Para probarlo SIN tocar el proyecto real, crea un segundo proyecto de Pages (ver SITIO.md).

Que se publica:
  - sitio:   index.html, googlea22b4e4d6a289f30.html, 404.html, _headers, _redirects, robots.txt,
             assets/, opis/, conc/, herramientas/, data/   (solo extensiones web: no .py ni .md)
  - pdf:     los pdf/*.pdf de primer nivel (no los CSV, ni escaneados/, ni lectura_opi/)
  - legado:  URLs que hoy sirven y alguien puede usar: productos buscador/index.html,
             pdf/lectura_opi/buscador_opis.html   (--sin-legado las saca)
  - demo:    demo-interno/ (prototipo con datos de ejemplo). NO entra cuando CF_PAGES_BRANCH == "main",
             asi nunca llega a produccion.

Antes de armar corre verificar_sitio.py y aborta si falla (en Cloudflare, un build fallido deja el deploy
anterior). Solo biblioteca estandar, compatible con Python 3.7+.

Uso:
    python -B build_site.py --reporte        # solo muestra que se publicaria y que dejaria de publicarse
    python -B build_site.py                  # arma dist/
    python -B build_site.py --salida ../dist_prueba --sin-legado
"""
from __future__ import annotations

import argparse
import collections
import os
import shutil
import sys
from pathlib import Path

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI))
import verificar_sitio as vs  # noqa: E402

ARCHIVOS_RAIZ = ["index.html", "googlea22b4e4d6a289f30.html", "404.html", "_headers", "_redirects", "robots.txt"]
CARPETAS = ["assets", "opis", "conc", "herramientas", "data"]
CARPETA_DEMO = "demo-interno"
LEGADO = ["productos buscador/index.html", "pdf/lectura_opi/buscador_opis.html"]
EXT_WEB = {".html", ".css", ".js", ".json", ".csv", ".txt", ".png", ".jpg", ".jpeg", ".svg", ".ico", ".xml",
           ".webmanifest", ".woff", ".woff2"}
# nombres de primer nivel que este script puede haber generado: solo en ese caso se borra una salida existente
GENERABLES = set(ARCHIVOS_RAIZ + CARPETAS + [CARPETA_DEMO, "pdf", "productos buscador"])


def contiene(padre: Path, hijo: Path) -> bool:
    """True si hijo es padre o esta dentro de padre."""
    try:
        hijo.relative_to(padre)
        return True
    except ValueError:
        return False


def todos_los_archivos(raiz: Path, salida: Path):
    out = []
    for dp, dn, fn in os.walk(str(raiz)):
        dn[:] = [d for d in dn if d != ".git" and Path(dp, d).resolve() != salida]
        for f in fn:
            out.append(os.path.relpath(os.path.join(dp, f), str(raiz)).replace(os.sep, "/"))
    return sorted(out)


def seleccionar(raiz: Path, todos, con_demo: bool, con_legado: bool):
    """ruta relativa -> categoria."""
    existen = set(todos)
    sel = {}
    for f in ARCHIVOS_RAIZ:
        if f in existen:
            sel[f] = "sitio"
    carpetas = list(CARPETAS) + ([CARPETA_DEMO] if con_demo else [])
    for rel in todos:
        partes = rel.split("/")
        if partes[0] in carpetas and os.path.splitext(rel)[1].lower() in EXT_WEB:
            sel[rel] = "demo" if partes[0] == CARPETA_DEMO else "sitio"
        elif len(partes) == 2 and partes[0] == "pdf" and rel.lower().endswith(".pdf"):
            sel[rel] = "pdf"
    if con_legado:
        for rel in LEGADO:
            if rel in existen:
                sel[rel] = "legado"
    return sel


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


def excluir_en_git(salida: Path, raiz: Path):
    """dist/ no esta en .gitignore y el protocolo usa 'git add -A': se lo excluye solo en local (.git/info/exclude)."""
    try:
        rel = salida.relative_to(raiz).as_posix().rstrip("/") + "/"
    except ValueError:
        return
    ex = raiz / ".git" / "info" / "exclude"
    if not ex.parent.is_dir():
        return
    actual = ex.read_text(encoding="utf-8") if ex.exists() else ""
    if rel not in actual.splitlines():
        with open(str(ex), "a", encoding="utf-8") as fh:
            fh.write(("\n" if actual and not actual.endswith("\n") else "") + rel + "\n")
        print("  (se agregó %s a .git/info/exclude: es local, no se versiona; así 'git add -A' no sube dist/)" % rel)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--salida", default="dist", help="carpeta de salida (por defecto dist, junto a este script)")
    ap.add_argument("--reporte", action="store_true", help="no arma nada: solo informa")
    ap.add_argument("--sin-legado", action="store_true", help="no publica las URLs heredadas")
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--con-demo", action="store_true", help="incluye demo-interno/ aunque sea la rama main")
    g.add_argument("--sin-demo", action="store_true", help="excluye demo-interno/")
    ap.add_argument("--sin-verificar", action="store_true", help="saltea verificar_sitio.py (no recomendado)")
    ap.add_argument("--enlazar", action="store_true", help="usa hardlinks en vez de copiar (mas rapido, mismo disco)")
    args = ap.parse_args()

    salida = Path(args.salida)
    salida = (AQUI / salida if not salida.is_absolute() else salida).resolve()
    if contiene(salida, AQUI):
        print("La carpeta de salida no puede ser el repo ni una carpeta que lo contenga.", file=sys.stderr)
        return 2

    rama = os.environ.get("CF_PAGES_BRANCH", "")
    con_demo = True if args.con_demo else (False if args.sin_demo else rama != "main")
    todos = todos_los_archivos(AQUI, salida)
    sel = seleccionar(AQUI, todos, con_demo, not args.sin_legado)
    total_mb = sum((AQUI / r).stat().st_size for r in sel) / 1048576.0
    cats = collections.Counter(sel.values())
    print("Rama de Cloudflare: %s | demo-interno: %s | legado: %s" % (rama or "(local)", "sí" if con_demo else "no",
                                                                    "no" if args.sin_legado else "sí"))
    print("Se publicarían %d archivos (%.0f MB): %s" % (len(sel), total_mb, ", ".join("%s %d" % kv for kv in sorted(cats.items()))))
    legado = [r for r, c in sel.items() if c == "legado"]
    if legado:
        print("  legado (se mantiene para no cortar URLs): " + ", ".join(legado))
    ex = agrupar_excluidos(todos, sel)
    print("DEJARÍA de publicarse (hoy se sirve por ser la raíz del repo): %d archivos" % sum(ex.values()))
    for k, n in sorted(ex.items(), key=lambda kv: -kv[1]):
        print("  %-34s %5d" % (k, n))
    if args.reporte:
        return 0

    if not args.sin_verificar:
        res = vs.verificar(AQUI)
        for n, m in res:
            print("[%s] %s" % (n, m))
        if any(n == "ERROR" for n, _ in res):
            print("\nverificar_sitio encontró errores: no se arma dist/.", file=sys.stderr)
            return 1

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
        if args.enlazar:
            try:
                os.link(str(AQUI / rel), str(dst))
                continue
            except OSError:
                pass
        shutil.copy2(str(AQUI / rel), str(dst))
    excluir_en_git(salida, AQUI)

    res = vs.verificar(salida, solo_dist=True)
    errores = [m for n, m in res if n == "ERROR"]
    for n, m in res:
        print("[%s] %s" % (n, m))
    if errores:
        print("\nEl dist/ armado tiene errores.", file=sys.stderr)
        return 1
    print("\nOK -> %s  (%d archivos, %.0f MB)" % (salida, len(sel), total_mb))
    return 0


if __name__ == "__main__":
    sys.exit(main())
