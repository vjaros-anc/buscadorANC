# -*- coding: utf-8 -*-
"""
Tablero de la actualizacion en curso: en que paso del mes estas.

Solo lee. No mueve ni escribe nada. Es lo que se corre cuando no te acordas si
ya extrajiste, si falta mover PDFs o si hay que regenerar el index.

Informa:
  - PDFs en nuevas/ que YA estan cargados en el maestro -> listos para mover a pdf/
  - PDFs en nuevas/ SIN fila en el maestro              -> falta correr el extractor
  - Expedientes del maestro sin PDF en ninguna carpeta  -> esperando PDF
  - PDFs en pdf/ sin fila en el maestro                 -> huerfanos
  - Celdas vacias por columna, para saber que falta completar
  - Si index.html quedo mas viejo que el maestro        -> hay que regenerar

Al final imprime el comando de PowerShell para mover los PDFs que esten listos.
Mover es decision tuya: el script no toca archivos.

Uso:
    python estado.py
    python estado.py --maestro firm_unificado.xlsx
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

import nomenclador_mercados as nm

AQUI = Path(__file__).parent
MAESTRO = AQUI / "firm.xlsx"
INDEX = AQUI / "index.html"
DIR_PDF = AQUI / "pdf"
DIR_NUEVAS = AQUI / "nuevas"

# columnas que interesa ver cuan completas estan
COLS_SEGUIMIENTO = [
    "Fecha_firma", "Decisión", "Número de Resolución", "Mercados relevantes",
    "Grupo/Empresa", "Empresas involucradas", "productos",
]


def _p(*args) -> None:
    """print tolerante con consolas sin UTF-8 (cp850/cp437)."""
    txt = " ".join(str(a) for a in args)
    try:
        print(txt)
    except UnicodeEncodeError:
        enc = sys.stdout.encoding or "ascii"
        print(txt.encode(enc, "replace").decode(enc))


def clave(valor) -> str:
    """La misma clave que usa el buscador: 'CONC. 2139 (PROSUM)' -> 'CONC-2139'."""
    tipo, numero, _ = nm.parse_carpeta("" if valor is None else str(valor))
    return f"{tipo}-{numero}" if tipo and numero else ""


def pdfs_de(carpeta: Path) -> dict[str, list[str]]:
    """clave -> nombres de archivo. Une las variantes CONC-1090_2, (2), etc."""
    salida: dict[str, list[str]] = {}
    if not carpeta.is_dir():
        return salida
    for f in carpeta.iterdir():
        if f.suffix.lower() != ".pdf":
            continue
        k = clave(f.stem)
        if k:
            salida.setdefault(k, []).append(f.name)
    return salida


def bloque(titulo: str, items: list[str], pista: str = "", tope: int = 25) -> None:
    _p("")
    _p(f"{titulo}: {len(items)}")
    if pista and items:
        _p(f"   {pista}")
    for x in items[:tope]:
        _p(f"     {x}")
    if len(items) > tope:
        _p(f"     ... y {len(items) - tope} mas")


def main() -> None:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--maestro", default=str(MAESTRO), help="xlsx a revisar (default: firm.xlsx)")
    args = ap.parse_args()

    ruta = Path(args.maestro)
    if not ruta.exists():
        _p(f"No existe el maestro: {ruta}")
        sys.exit(1)

    df = pd.read_excel(ruta, sheet_name=0)
    df["_k"] = df["Carpeta"].map(clave)
    en_maestro = {k for k in df["_k"] if k}

    en_pdf = pdfs_de(DIR_PDF)
    en_nuevas = pdfs_de(DIR_NUEVAS)

    _p(f"Maestro : {ruta.name}   {len(df)} filas, {len(en_maestro)} expedientes, "
       f"{len(df.columns) - 1} columnas")
    _p(f"PDFs    : pdf/ {sum(len(v) for v in en_pdf.values())} archivos "
       f"({len(en_pdf)} expedientes)  |  nuevas/ {sum(len(v) for v in en_nuevas.values())} archivos")

    listos = sorted(k for k in en_nuevas if k in en_maestro)
    sin_cargar = sorted(k for k in en_nuevas if k not in en_maestro)
    esperando = sorted(k for k in en_maestro if k not in en_pdf and k not in en_nuevas)
    huerfanos = sorted(k for k in en_pdf if k not in en_maestro)

    bloque("LISTOS PARA MOVER a pdf/ (ya cargados en el maestro)", listos,
           "el expediente ya tiene su fila; falta el archivo donde el buscador lo busca")
    bloque("EN nuevas/ SIN FILA en el maestro", sin_cargar,
           "falta correr: python extraer_firmadas3.py nuevas firmadas3.xlsx  y despues mergear")
    bloque("ESPERANDO PDF (fila cargada, archivo no esta)", esperando,
           "se publican igual, pero sin link al PDF hasta que lo bajes")
    bloque("PDFs HUERFANOS en pdf/ (sin fila en el maestro)", huerfanos,
           "o falta cargarlos, o la Carpeta de su fila esta mal escrita")

    _p("")
    _p("Celdas vacias por columna:")
    for c in COLS_SEGUIMIENTO:
        if c in df.columns:
            faltan = int(df[c].isna().sum())
            _p(f"  {c:24s} {len(df) - faltan:5d} cargadas / {faltan:5d} vacias")

    _p("")
    if not INDEX.exists():
        _p("index.html NO existe -> correr: python generar_pagina.py")
    elif INDEX.stat().st_mtime < ruta.stat().st_mtime:
        _p(f"index.html es MAS VIEJO que {ruta.name} -> hay que regenerar:")
        _p("    python generar_pagina.py")
    else:
        _p(f"index.html esta al dia respecto de {ruta.name}.")

    if listos:
        _p("")
        _p("Para mover los que estan listos (revisalo antes de pegarlo):")
        _p("    Move-Item " + ", ".join(f"nuevas\\{en_nuevas[k][0]}" for k in listos[:8])
           + (" , ..." if len(listos) > 8 else "") + " pdf\\")


if __name__ == "__main__":
    main()
