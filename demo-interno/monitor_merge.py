# -*- coding: utf-8 -*-
"""
Junta lo que exporta ArtifactData del artefacto "Monitor de concentraciones" en UN solo archivo,
el contrato de datos que lee la pagina (ver SCHEMA.md):

    <salida>/monitor.json        { schema_version, origen, exportado_el, operaciones, informes, parametros }
    <salida>/operaciones.csv     las mismas operaciones, para Excel (separador ; y UTF-8 con BOM)

Entrada: la carpeta que se usa como out_dir al exportar con ArtifactData (action "list"), que contiene
    operaciones/<id>.json    informes/<id>.json    parametros/umbrales.json

Sin red, solo biblioteca estandar (Python 3.7+). NO sube nada: el monitor.json real contiene el analisis
interno del area y NO debe entrar al repo publico; vive solo en el repo privado del area interna.

Uso:
    python -B demo-interno/monitor_merge.py CARPETA_EXPORTADA --salida CARPETA_DESTINO
"""
import argparse
import csv
import datetime as dt
import io
import json
import sys
from pathlib import Path

SCHEMA_VERSION = 1
CAMPOS_CSV = ["fecha", "partes", "tipo", "sector", "alcance", "vinculoAR", "estado", "etapa", "prioridad",
              "relevanteANC", "umbralArt9", "excepcion11e", "analisisUmbral", "motivoANC", "verificacion",
              "verificadoEl", "fuente", "links"]
OBLIGATORIOS = ["fecha", "partes", "tipo", "estado"]
VALORES = {
    "estado": {"confirmada", "rumor"},
    "verificacion": {"pendiente", "notificada", "no_notificada", "descartada"},
}


def leer_dir(carpeta: Path) -> list:
    docs = []
    if not carpeta.is_dir():
        return docs
    for f in sorted(carpeta.glob("*.json")):
        d = json.loads(f.read_text(encoding="utf-8"))
        if isinstance(d, dict):
            d.setdefault("id", f.stem)
            docs.append(d)
    return docs


def celda(v) -> str:
    s = "" if v is None else str(v)
    if s[:1] in ("=", "+", "-", "@", "\t", "\r"):      # texto de la prensa no debe ejecutarse como formula en Excel
        s = "'" + s
    return s


def a_csv(ops: list) -> str:
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=";", lineterminator="\r\n", quoting=csv.QUOTE_MINIMAL)
    w.writerow(CAMPOS_CSV)
    for o in ops:
        fila = []
        for c in CAMPOS_CSV:
            if c == "links":
                fila.append(celda(" | ".join("%s <%s>" % (l.get("fuente", "Fuente"), l.get("url", ""))
                                             for l in (o.get("links") or []))))
            elif c == "relevanteANC":
                fila.append("sí" if o.get("relevanteANC") else "no")
            else:
                fila.append(celda(o.get(c)))
        w.writerow(fila)
    return "﻿" + buf.getvalue()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("exportada", help="carpeta exportada con ArtifactData (out_dir)")
    ap.add_argument("--salida", required=True, help="carpeta donde se escriben monitor.json y operaciones.csv")
    ap.add_argument("--origen", default="artefacto", help='"artefacto" (real) o "ejemplo"')
    args = ap.parse_args()

    base, salida = Path(args.exportada), Path(args.salida)
    ops = leer_dir(base / "operaciones")
    infs = leer_dir(base / "informes")
    par_dir = leer_dir(base / "parametros")
    par = next((d for d in par_dir if d.get("id") == "umbrales"), par_dir[0] if par_dir else {})
    par = {k: v for k, v in par.items() if k != "id"}
    if not ops and not infs:
        print("No encontre operaciones/ ni informes/ en %s" % base, file=sys.stderr)
        return 2

    avisos = []
    for o in ops:
        for c in OBLIGATORIOS:
            if not o.get(c):
                avisos.append("%s: falta %s" % (o["id"], c))
        for c, ok in VALORES.items():
            if o.get(c) and o[c] not in ok:
                avisos.append("%s: %s=%r no es un valor conocido" % (o["id"], c, o[c]))
        if o.get("relevanteANC") and not o.get("verificacion"):
            avisos.append("%s: marcada relevanteANC sin verificacion (la pagina la toma como 'pendiente')" % o["id"])
    ops.sort(key=lambda o: o.get("fecha") or "", reverse=True)
    infs.sort(key=lambda i: i.get("fecha") or "", reverse=True)

    salida.mkdir(parents=True, exist_ok=True)
    doc = {"schema_version": SCHEMA_VERSION, "origen": args.origen, "exportado_el": dt.date.today().isoformat(),
           "operaciones": ops, "informes": infs, "parametros": par}
    (salida / "monitor.json").write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    (salida / "operaciones.csv").write_bytes(a_csv(ops).encode("utf-8"))
    print("OK -> %s  (%d operaciones, %d informes)" % (salida / "monitor.json", len(ops), len(infs)))
    for a in avisos:
        print("  AVISO:", a)
    return 0


if __name__ == "__main__":
    sys.exit(main())
