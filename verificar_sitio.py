# -*- coding: utf-8 -*-
"""
Compuerta de publicacion del sitio (solo lectura: no modifica nada).

Revisa lo que se va a publicar y devuelve codigo de salida 1 si hay algun ERROR:
  - links y recursos locales de las paginas del sitio (el buscador incluido), con el nombre EXACTO
    (Cloudflare distingue mayusculas)
  - archivos de datos que las paginas piden con fetch / DATA_URL
  - destinos de la barra de navegacion (assets/nav.js)
  - ningun archivo > 20 MiB ni mas de 20.000 archivos (limites de Cloudflare Pages)
  - nada de la lista negra (Res_firmadas, *.xlsm, cotejo_*, evol_conc*, claves de API)
  - los JSON de data/ son validos y traen schema_version
  - la demo del monitor esta marcada como ejemplo y NO hay un monitor.json real en el arbol
  - las paginas del area interna no cargan Analytics y piden noindex
  - que el buscador (index.html) lleve la barra comun (aviso si no)
  - (opcional, --aditivo) que la rama solo agregue archivos respecto de main; unica excepcion: index.html y
    generar_pagina.py pueden recibir lineas nuevas (la barra), nunca perder ninguna

No usa nada fuera de la biblioteca estandar (Python 3.7+): sirve tambien como paso de build en Cloudflare.

Uso:
    python -B verificar_sitio.py
    python -B verificar_sitio.py --aditivo          # ademas: git diff main...HEAD solo con altas (ver arriba)
    python -B verificar_sitio.py --raiz dist        # verifica una carpeta ya armada (build_site.py)
"""
from __future__ import annotations

import argparse
import fnmatch
import json
import os
import re
import subprocess
import sys
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlsplit

AQUI = Path(__file__).resolve().parent

# Paginas cuyos links y recursos se revisan. index.html (el buscador) entra por la barra comun; sus links
# a PDF los revisa comparar_index.py.
PAGINAS = ["index.html", "404.html", "herramientas/index.html", "opis/index.html", "conc/index.html",
           "demo-interno/noticias/index.html"]
PUBLICAS = ("index.html", "conc/index.html", "opis/index.html", "herramientas/index.html")
BARRA = ("assets/anc.css", 'id="anc-nav"', "assets/nav.js")
# Unicos archivos que ya existian en main y esta rama puede cambiar, y solo agregando lineas: el buscador
# recibe la barra comun (3 lineas en la plantilla y en su salida).
MODIFICABLES = ("index.html", "generar_pagina.py")
LIMITE_BYTES = 20 * 1024 * 1024        # Cloudflare Pages: 25 MiB por archivo; se avisa antes
LIMITE_ARCHIVOS = 20000
LISTA_NEGRA = ["*.xlsm", "Res_firmadas*", "cotejo_*", "evol_conc*", "api_key*", "*.key", ".env", "~$*", "*.db"]
RX_CLAVE = re.compile(r"sk-ant-[A-Za-z0-9_\-]{20,}")
ESQUEMAS_EXTERNOS = ("http:", "https:", "mailto:", "tel:", "data:", "javascript:", "blob:")


class _Refs(HTMLParser):
    def __init__(self):
        HTMLParser.__init__(self)
        self.refs = []

    def handle_starttag(self, tag, attrs):
        d = dict(attrs)
        for k in ("href", "src"):
            if d.get(k):
                self.refs.append(d[k])


def existe_exacto(base: Path, rel: str) -> bool:
    """True si la ruta existe respetando mayusculas en CADA tramo (aunque el disco no las distinga)."""
    p = base
    for parte in Path(rel).parts:
        if parte in ("", ".", "/"):
            continue
        if parte == "..":
            p = p.parent
            continue
        try:
            nombres = os.listdir(str(p))
        except OSError:
            return False
        if parte not in nombres:
            return False
        p = p / parte
    return p.exists()


def _destino(raiz: Path, pagina: Path, ref: str):
    """Resuelve un link a una ruta relativa a `raiz` (None si es externo o solo un ancla)."""
    if ref.startswith(ESQUEMAS_EXTERNOS) or ref.startswith("//"):
        return None
    sp = urlsplit(ref)
    ruta = unquote(sp.path)
    if not ruta:
        return None
    if ruta.startswith("/"):
        rel = ruta.lstrip("/")
    else:
        rel = os.path.relpath(str(pagina.parent / ruta), str(raiz)).replace(os.sep, "/")
    if rel.endswith("/") or rel in ("", "."):
        rel = rel.rstrip("/") + "/index.html" if rel not in ("", ".") else "index.html"
    return rel


def archivos_publicables(raiz: Path):
    """Archivos que se publicarian. Si es un repo git, los versionados; si no, todo lo que hay."""
    try:
        out = subprocess.run(["git", "-C", str(raiz), "ls-files", "-z"], capture_output=True, check=True).stdout
        lista = [x for x in out.decode("utf-8", "replace").split("\0") if x]
        if lista:
            return lista, True
    except (OSError, subprocess.CalledProcessError):
        pass
    todos = []
    for dp, dn, fn in os.walk(str(raiz)):
        dn[:] = [d for d in dn if d != ".git"]
        for f in fn:
            todos.append(os.path.relpath(os.path.join(dp, f), str(raiz)).replace(os.sep, "/"))
    return todos, False


def verificar(raiz: Path, aditivo: bool = False, solo_dist: bool = False):
    """Devuelve una lista de (nivel, mensaje); nivel = 'ERROR' o 'AVISO'."""
    res = []
    err = lambda m: res.append(("ERROR", m))
    avi = lambda m: res.append(("AVISO", m))

    # 1. links y recursos de las paginas del sitio
    paginas = [p for p in PAGINAS if (raiz / p).exists()]
    if not paginas:
        avi("no hay paginas para revisar")
    for rel in paginas:
        pag = raiz / rel
        txt = pag.read_text(encoding="utf-8", errors="replace")
        pr = _Refs()
        pr.feed(txt)
        refs = list(pr.refs)
        refs += re.findall(r"fetch\(\s*['\"]([^'\"]+)['\"]", txt)
        refs += re.findall(r"DATA_URL\s*=\s*['\"]([^'\"]+)['\"]", txt)
        for ref in refs:
            d = _destino(raiz, pag, ref)
            if d is None:
                continue
            if not existe_exacto(raiz, d):
                err("%s: el link '%s' no existe (se buscó %s, respetando mayúsculas)" % (rel, ref, d))
        if rel.startswith("demo-interno/"):
            if "googletagmanager" in txt or "gtag(" in txt:
                err("%s: una página del área interna no debe cargar Analytics" % rel)
            if 'name="robots"' not in txt or "noindex" not in txt:
                err("%s: falta <meta name=\"robots\" content=\"noindex…\">" % rel)
        if rel in PUBLICAS:
            if re.search(r"fetch\(\s*['\"][^'\"]*(interno|monitor)[^'\"]*['\"]", txt):
                err("%s: una página pública no debe pedir datos del área interna" % rel)
        if rel == "index.html" and not all(s in txt for s in BARRA):
            avi("index.html no lleva la barra común (¿se regeneró con un generar_pagina.py anterior a la barra?)")

    # 2. destinos de la barra
    nav = raiz / "assets" / "nav.js"
    if nav.exists():
        for h in re.findall(r"\bh:\s*'([^']*)'", nav.read_text(encoding="utf-8")):
            destino = "index.html" if h == "" else h.rstrip("/") + "/index.html"
            if not existe_exacto(raiz, destino):
                err("assets/nav.js: el destino '%s' de la barra no existe" % (h or "/"))

    # 3. JSON de datos
    for carpeta in ("data", "demo-interno/data"):
        d = raiz / carpeta
        if not d.is_dir():
            continue
        for f in sorted(d.glob("*.json")):
            try:
                obj = json.loads(f.read_text(encoding="utf-8"))
            except ValueError as e:
                err("%s/%s: JSON inválido (%s)" % (carpeta, f.name, e))
                continue
            if not isinstance(obj, dict) or "schema_version" not in obj:
                err("%s/%s: falta schema_version" % (carpeta, f.name))

    # 4. demo del monitor: marcada como ejemplo y sin datos reales
    for f in raiz.glob("**/monitor*.json"):
        rel = f.relative_to(raiz).as_posix()
        if ".git/" in rel:
            continue
        try:
            obj = json.loads(f.read_text(encoding="utf-8"))
        except ValueError:
            continue
        if obj.get("origen") != "ejemplo":
            err("%s: es un monitor con datos reales (origen != 'ejemplo'): no puede estar en el repo ni en el sitio público" % rel)
        else:
            if "EJEMPLO" not in (obj.get("aviso") or ""):
                err("%s: el fixture no trae el aviso de EJEMPLO" % rel)
            sin_marca = [o.get("id") for o in obj.get("operaciones", []) if "(ejemplo)" not in (o.get("partes") or "")]
            if sin_marca:
                err("%s: operaciones sin la marca '(ejemplo)' en partes: %s" % (rel, ", ".join(map(str, sin_marca))))

    # 5. 404.html
    if not (raiz / "404.html").exists():
        avi("no hay 404.html: Cloudflare Pages respondería 200 con el buscador ante cualquier ruta inexistente")

    # 6. tamaño, cantidad y lista negra
    archivos, desde_git = archivos_publicables(raiz)
    if len(archivos) > LIMITE_ARCHIVOS:
        err("%d archivos: supera el límite de %d de Cloudflare Pages" % (len(archivos), LIMITE_ARCHIVOS))
    elif len(archivos) > 0.9 * LIMITE_ARCHIVOS:
        avi("%d archivos: cerca del límite de %d" % (len(archivos), LIMITE_ARCHIVOS))
    for rel in archivos:
        p = raiz / rel
        try:
            tam = p.stat().st_size
        except OSError:
            continue
        if tam > LIMITE_BYTES:
            err("%s: pesa %.1f MiB (el límite de Pages es 25 MiB)" % (rel, tam / 1048576.0))
        nombre = rel.rsplit("/", 1)[-1]
        for patron in LISTA_NEGRA:
            if fnmatch.fnmatch(nombre, patron) or fnmatch.fnmatch(rel, patron):
                err("%s: coincide con la lista negra (%s)" % (rel, patron))
                break
        if tam < 2 * 1024 * 1024 and p.suffix.lower() in (".txt", ".md", ".py", ".json", ".html", ".js", ".csv", ".yml", ".yaml"):
            try:
                if RX_CLAVE.search(p.read_text(encoding="utf-8", errors="ignore")):
                    err("%s: parece contener una clave de API (sk-ant-…)" % rel)
            except OSError:
                pass

    # 7. aditivo respecto de main (solo en un repo git): todo es alta, salvo MODIFICABLES con 0 lineas borradas
    if aditivo and not solo_dist:
        try:
            out = subprocess.run(["git", "-C", str(raiz), "diff", "--name-status", "main...HEAD"],
                                 capture_output=True, check=True).stdout.decode("utf-8", "replace")
            for l in out.splitlines():
                if not l or l.startswith("A"):
                    continue
                estado, _, ruta = l.partition("\t")
                if estado == "M" and ruta in MODIFICABLES:
                    num = subprocess.run(["git", "-C", str(raiz), "diff", "--numstat", "main...HEAD", "--", ruta],
                                         capture_output=True, check=True).stdout.decode("utf-8", "replace").split()
                    if num[:2] and num[1] != "0":
                        err("%s: la rama borra o reemplaza %s líneas de main (solo puede agregar)" % (ruta, num[1]))
                    continue
                err("la rama modifica o borra algo que ya existía en main: %s" % l)
        except (OSError, subprocess.CalledProcessError) as e:
            avi("no se pudo comparar con main (%s)" % e)
    return res


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--raiz", default=str(AQUI), help="carpeta a verificar (por defecto, el repo)")
    ap.add_argument("--aditivo", action="store_true", help="comprueba que la rama solo agregue archivos respecto de main")
    args = ap.parse_args()
    raiz = Path(args.raiz).resolve()
    res = verificar(raiz, aditivo=args.aditivo, solo_dist=(raiz != AQUI))
    errores = [m for n, m in res if n == "ERROR"]
    for n, m in res:
        print("[%s] %s" % (n, m))
    print("\nverificar_sitio: %d error(es), %d aviso(s) en %s" % (len(errores), len(res) - len(errores), raiz))
    return 1 if errores else 0


if __name__ == "__main__":
    sys.exit(main())
