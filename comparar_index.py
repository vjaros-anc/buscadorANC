# -*- coding: utf-8 -*-
"""
Compara dos index.html y avisa si el nuevo perdio expedientes.

Es la compuerta del paso 9 del protocolo: antes de pushear, se corre contra el
index del mes pasado. Si aparece aunque sea UN expediente perdido, no se sube.

Los dos archivos traen los registros embebidos en
<script id="bm-data" type="application/json">, asi que la comparacion es exacta:
no hay que parsear HTML ni adivinar nada.

Ademas del alta/baja de expedientes informa:
  - conteo por sector, por tipo y por producto, con el delta
  - cuantos expedientes tienen empresas, mercados y productos cargados
  - links a PDF que apuntan a un archivo que no existe en pdf/

Devuelve codigo de salida 1 si hay expedientes perdidos, para poder encadenarlo.

Uso:
    python comparar_index.py viejo.html nuevo.html
    python comparar_index.py viejo.html            # compara contra ./index.html
"""
from __future__ import annotations

import ast
import collections
import json
import re
import sys
from pathlib import Path

AQUI = Path(__file__).parent
PDF_DIR = AQUI / "pdf"

RX_DATOS = re.compile(
    r'<script id="bm-data"[^>]*>(.*?)</script>', re.DOTALL)


def _p(*args) -> None:
    """print tolerante con consolas sin UTF-8 (cp850/cp437)."""
    txt = " ".join(str(a) for a in args)
    try:
        print(txt)
    except UnicodeEncodeError:
        enc = sys.stdout.encoding or "ascii"
        print(txt.encode(enc, "replace").decode(enc))


def cargar(ruta: Path) -> list[dict]:
    """Registros embebidos en el <script id="bm-data"> del index."""
    m = RX_DATOS.search(ruta.read_text(encoding="utf-8"))
    if not m:
        raise SystemExit(f"{ruta.name}: no encontre el bloque <script id=\"bm-data\">. "
                         "¿Es un index.html generado por generar_pagina.py?")
    return json.loads(m.group(1))


def base(r: dict) -> str:
    """El expediente, sin el nº de resolucion: tipo+numero y no el texto de
    Carpeta, asi 'CONC 1981', 'CONC-1981' y 'CONC. 1981 (PROSUM)' son el mismo."""
    tipo = str(r.get("tipo") or "").strip().upper()
    num = str(r.get("numero") or "").strip()
    return f"{tipo}-{num}" if num else str(r.get("carpeta") or "?").strip().upper()


def etiqueta(r: dict) -> str:
    return str(r.get("carpeta") or "?").strip()


def lista(v) -> list[str]:
    """Los campos multivaluados viajan como repr de lista ("['Pesca', 'Mar']").
    Devuelve sus elementos; si es un escalar, devuelve [escalar]."""
    if isinstance(v, (list, tuple)):
        return [str(x).strip() for x in v if str(x).strip()]
    s = str(v or "").strip()
    if s.startswith("[") and s.endswith("]"):
        try:
            return [str(x).strip() for x in ast.literal_eval(s) if str(x).strip()]
        except (ValueError, SyntaxError):
            return []
    return [s] if s and s != "-" else []


def lleno(r: dict, *campos: str) -> bool:
    return any(lista(r.get(c)) for c in campos)


def contar(recs: list[dict], campo: str) -> collections.Counter:
    c: collections.Counter = collections.Counter()
    for r in recs:
        for x in lista(r.get(campo)):
            c[x] += 1
    return c


def tabla_delta(titulo: str, viejo: collections.Counter, nuevo: collections.Counter,
                top: int = 0) -> None:
    filas = []
    for k in sorted(set(viejo) | set(nuevo)):
        a, b = viejo.get(k, 0), nuevo.get(k, 0)
        if a != b or not top:
            filas.append((b - a, a, b, k))
    if not filas:
        return
    filas.sort(key=lambda t: (-abs(t[0]), t[3]))
    _p("")
    _p(f"{titulo}   (viejo -> nuevo)")
    for d, a, b, k in filas[:top or len(filas)]:
        marca = "  " if d == 0 else ("+ " if d > 0 else "- ")
        _p(f"  {marca}{k:52.52s} {a:5d} -> {b:5d}   {d:+d}" if d else
           f"  {marca}{k:52.52s} {a:5d} -> {b:5d}")


def links_rotos(recs: list[dict]) -> list[str]:
    rotos = []
    for r in recs:
        pdf = str(r.get("pdf") or "").strip()
        if pdf and not (AQUI / pdf).exists():
            rotos.append(f"{etiqueta(r)} -> {pdf}")
    return rotos


def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    if not args:
        _p(__doc__)
        return 2
    viejo_p = Path(args[0])
    nuevo_p = Path(args[1]) if len(args) > 1 else AQUI / "index.html"
    for r in (viejo_p, nuevo_p):
        if not r.exists():
            _p(f"No existe: {r}")
            return 2

    viejo, nuevo = cargar(viejo_p), cargar(nuevo_p)

    # Se compara por expediente y por CANTIDAD de fichas, no por nº de
    # resolucion: una carpeta puede tener varias (OPI-232, INC-1663, CONC-2024)
    # y a la vez una ficha puede ganar el nº que antes le faltaba. Perder una
    # ficha es que el expediente aparezca menos veces que antes.
    cv, cn = collections.Counter(map(base, viejo)), collections.Counter(map(base, nuevo))
    perdidos = sorted((k, cv[k] - cn.get(k, 0)) for k in cv if cn.get(k, 0) < cv[k])
    nuevos = sorted((k, cn[k] - cv.get(k, 0)) for k in cn if cv.get(k, 0) < cn[k])

    _p(f"viejo : {viejo_p}   {len(viejo)} expedientes")
    _p(f"nuevo : {nuevo_p}   {len(nuevo)} expedientes   ({len(nuevo) - len(viejo):+d})")
    _p("")
    _p(f"PERDIDOS (estaban y ya no): {sum(n for _, n in perdidos)}")
    for k, n in perdidos:
        _p(f"    - {k}" + (f"   ({n} fichas)" if n > 1 else ""))
    _p(f"NUEVOS                    : {sum(n for _, n in nuevos)}")
    for k, n in nuevos:
        _p(f"    + {k}" + (f"   ({n} fichas)" if n > 1 else ""))

    _p("")
    _p("Campos cargados:")
    for campos, nombre in ((("compradores", "objeto"), "con empresas"),
                           (("grupo",), "con grupo/empresa"),
                           (("merc_v1", "merc_v2"), "con mercado relevante"),
                           (("productos",), "con productos"),
                           (("rel_v1", "rel_v2"), "con relaciones economicas"),
                           (("pdf",), "con link a PDF")):
        a = sum(1 for r in viejo if lleno(r, *campos))
        b = sum(1 for r in nuevo if lleno(r, *campos))
        if a or b:
            _p(f"  {nombre:26s} {a:5d} -> {b:5d}   {b - a:+d}")

    for campo, titulo in (("sectores", "Por sector"), ("tipo_cat", "Por tipo"),
                          ("productos", "Por producto (solo los que cambian)")):
        tabla_delta(titulo, contar(viejo, campo), contar(nuevo, campo),
                    top=30 if campo == "productos" else 0)

    rotos = links_rotos(nuevo)
    _p("")
    _p(f"Links a PDF que no existen en pdf/: {len(rotos)}")
    for x in rotos[:20]:
        _p(f"    ! {x}")
    if len(rotos) > 20:
        _p(f"    ... y {len(rotos) - 20} mas")

    _p("")
    if perdidos:
        _p(f"NO SUBIR: se perdieron {sum(n for _, n in perdidos)} fichas. "
           "Revisar la columna Carpeta de las filas que tocaste.")
        return 1
    _p("OK: no se perdio ningun expediente.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
