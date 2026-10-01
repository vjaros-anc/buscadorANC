# -*- coding: utf-8 -*-
"""
Mergea la salida del extractor de PDFs (firmadas3.xlsx) dentro de firm.xlsx,
el maestro del buscador.

Circuito completo:

    python extraer_firmadas3.py nuevas firmadas3.xlsx
    python mergear_firmadas.py                          # <-- este script
    python extraer_productos.py                         # completa productos/sector
    python generar_pagina.py                            # escribe index.html

Que hace, en orden:

  1. Deja una copia de firm.xlsx en ./respaldos/firm_<fecha>-<hora>.xlsx ANTES
     de tocar nada.
  2. Para cada fila de firmadas3.xlsx busca su expediente en el maestro:
       - si lo encuentra  -> completa SOLO las celdas vacias (nunca pisa lo que
         ya esta cargado, ni a mano ni de antes).
       - si no lo encuentra -> agrega la fila al final.
  3. Corrige el autofiltro para que cubra las filas nuevas.

Como identifica un expediente: la clave es la MISMA que usa el buscador
(nomenclador_mercados.parse_carpeta), asi que 'CONC. 2124 (PROSUM)',
'CONC-2124' y 'CONC 2124' son el mismo expediente. Pero la clave sola no
alcanza: una misma carpeta puede tener varias resoluciones firmadas (los
incidentes 'INC. I. CONC. 1663' son cuatro), y a veces una fila del maestro tiene
la carpeta mal cargada. Por eso el desempate es por numero de resolucion:

    1. misma clave + mismo nº de resolucion (o de dictamen)  -> es la misma fila
    2. misma clave + misma fecha de firma                    -> es la misma fila
    3. misma clave + la fila del maestro no tiene ningun nº de resolucion ni de
       dictamen (fila cargada a medias)                      -> es la misma fila
    4. misma clave, todas las filas tienen nº y ninguno coincide, y ninguna
       fecha coincide                                        -> fila NUEVA + aviso
    5. la clave no existe en firm4                           -> fila NUEVA

El caso 4 es el que hay que mirar: normalmente es otra resolucion del mismo
expediente (un incidente, y esta bien que se agregue), pero tambien puede ser
una carpeta mal cargada en firm4.

Cuando una fila coincide pero algun dato NO coincide (fecha de firma, nº de
resolucion o decision distintos), el script NO pisa lo que ya esta cargado: lo
lista al final como DISCREPANCIA para que lo resuelvas a mano. Asi aparecen los
errores de tipeo, p.ej. 'DISF-2025-26' en el maestro contra 'DISFC-2025-26' en el
PDF.

Escribe con openpyxl sobre el archivo existente, asi que conserva encabezados,
anchos, autofiltro y paneles. La columna `meses` de firmadas3 se ignora porque
firm4 no la tiene.

Uso:
    python mergear_firmadas.py                      # firmadas3.xlsx -> firm.xlsx
    python mergear_firmadas.py --dry-run            # no escribe, solo informa
    python mergear_firmadas.py --nuevas otro.xlsx
    python mergear_firmadas.py --maestro copia.xlsx
"""
from __future__ import annotations

import argparse
import datetime as dt
import re
import shutil
import sys
from copy import copy
from pathlib import Path

import openpyxl

import nomenclador_mercados as nm

AQUI = Path(__file__).parent
MAESTRO = AQUI / "firm.xlsx"
NUEVAS = AQUI / "firmadas3.xlsx"          # salida de extraer_firmadas3.py
VIEJAS = "respaldos"                      # subcarpeta, al lado del maestro

# El maestro unificado tiene las 20 columnas, incluidas meses y DIAS, asi que
# ya no hay nada que descartar de firmadas3.
COLS_IGNORAR: set[str] = set()

C_CARPETA = "Carpeta"
C_RES = "Número de Resolución"
C_DICT = "Número de Dictamen"
C_FIRMA = "Fecha_firma"
COLS_FECHA = {"Fecha_Ingreso", "Fecha_firma"}

# columnas donde, si el dato ya esta cargado y NO coincide con el del PDF, se
# avisa al final (nunca se pisa lo que ya esta en firm4). `Decisión` queda
# afuera a proposito: en firm4 esta redactada mas fina ("Disposición - Autoriza
# Art.14 a)...") que la forma canonica que devuelve el extractor, asi que
# difiere siempre y solo haria ruido.
COLS_COTEJO = {"Fecha_firma", "Fecha_Ingreso", "Número de Resolución",
               "Número de Dictamen"}


def _p(*args) -> None:
    """print tolerante con consolas sin UTF-8 (cp850/cp437)."""
    txt = " ".join(str(a) for a in args)
    try:
        print(txt)
    except UnicodeEncodeError:
        enc = sys.stdout.encoding or "ascii"
        print(txt.encode(enc, "replace").decode(enc))


# --------------------------------------------------------------------------- #
# Identificacion de expedientes
# --------------------------------------------------------------------------- #
def clave(carpeta) -> str:
    """Clave de cotejo, la misma que usa el buscador para los PDFs."""
    tipo, numero, _ = nm.parse_carpeta(_txt(carpeta))
    return f"{tipo} {numero}" if numero else ""


def _txt(v) -> str:
    if v is None:
        return ""
    if isinstance(v, (dt.datetime, dt.date)):
        return v.strftime("%Y-%m-%d")
    s = str(v).strip()
    return "" if s.lower() == "nan" else s


def norm_res(v) -> str:
    """Nº de resolucion/dictamen normalizado: mayusculas, sin espacios ni puntos."""
    return re.sub(r"[\s.]", "", _txt(v).upper())


def _vacia(v) -> bool:
    return not _txt(v)


def _comparable(v, nombre: str) -> str:
    """Valor normalizado para decidir si dos celdas dicen lo mismo."""
    if nombre in COLS_FECHA:
        return _fecha(v)
    if nombre in (C_RES, C_DICT):
        return norm_res(v)
    return re.sub(r"\s+", " ", _txt(v)).strip().lower()


def _fecha(v) -> str:
    """Fecha comparable (solo el dia), venga como fecha o como texto."""
    if isinstance(v, (dt.datetime, dt.date)):
        return v.strftime("%Y-%m-%d")
    s = _txt(v)
    m = re.search(r"(\d{4})-(\d{2})-(\d{2})", s)
    if m:
        return m.group(0)
    m = re.search(r"(\d{1,2})/(\d{1,2})/(\d{4})", s)
    if m:
        return f"{m.group(3)}-{int(m.group(2)):02d}-{int(m.group(1)):02d}"
    return ""


# --------------------------------------------------------------------------- #
# Excel
# --------------------------------------------------------------------------- #
def mapa_columnas(ws) -> dict[str, int]:
    return {
        str(ws.cell(row=1, column=c).value).strip(): c
        for c in range(1, ws.max_column + 1)
        if ws.cell(row=1, column=c).value is not None
    }


def leer_nuevas(ruta: Path) -> tuple[list[dict], list[str]]:
    """Filas de firmadas3.xlsx como dicts {encabezado: valor}."""
    wb = openpyxl.load_workbook(ruta, data_only=True)
    ws = wb.worksheets[0]
    cols = mapa_columnas(ws)
    filas = []
    for r in range(2, ws.max_row + 1):
        fila = {n: ws.cell(row=r, column=c).value for n, c in cols.items()}
        if any(not _vacia(v) for v in fila.values()):
            filas.append(fila)
    wb.close()
    return filas, list(cols)


def buscar_destino(fila: dict, candidatos: list[int], ws, cols: dict[str, int]) -> tuple[int | None, str]:
    """Fila de firm4 que corresponde a esta fila nueva (ver reglas del docstring)."""
    res_n = norm_res(fila.get(C_RES)) or norm_res(fila.get(C_DICT))
    firma_n = _fecha(fila.get(C_FIRMA))

    def val(r, nombre):
        return ws.cell(row=r, column=cols[nombre]).value if nombre in cols else None

    # 1. mismo numero de resolucion o de dictamen
    if res_n:
        for r in candidatos:
            if res_n in ({norm_res(val(r, C_RES)), norm_res(val(r, C_DICT))} - {""}):
                return r, "resolución"
    # 2. misma fecha de firma (aunque el nº de resolucion este mal tipeado)
    if firma_n:
        for r in candidatos:
            if _fecha(val(r, C_FIRMA)) == firma_n:
                return r, "fecha de firma"
    # 3. fila del maestro sin ningun nº cargado: esta a medias, es la misma
    for r in candidatos:
        if not ({norm_res(val(r, C_RES)), norm_res(val(r, C_DICT))} - {""}):
            return r, "carpeta (fila sin nº de resolución)"
    return None, ""


def copiar_estilo(ws, destino: int, modelo: int, ncols: int) -> None:
    for c in range(1, ncols + 1):
        ref = ws.cell(row=modelo, column=c)
        cel = ws.cell(row=destino, column=c)
        cel.font = copy(ref.font)
        cel.fill = copy(ref.fill)
        cel.border = copy(ref.border)
        cel.alignment = copy(ref.alignment)


def escribir(cel, valor, nombre: str) -> None:
    cel.value = valor
    if nombre in COLS_FECHA and isinstance(valor, (dt.datetime, dt.date)):
        cel.number_format = "DD/MM/YYYY"


# --------------------------------------------------------------------------- #
def main() -> None:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--nuevas", default=str(NUEVAS),
                    help="xlsx que sale de extraer_firmadas3.py (default: firmadas3.xlsx)")
    ap.add_argument("--maestro", "--firm4", dest="maestro", default=str(MAESTRO),
                    help="xlsx destino (default: firm.xlsx)")
    ap.add_argument("--dry-run", action="store_true", help="no escribe nada, solo informa")
    args = ap.parse_args()

    ruta_nuevas = Path(args.nuevas)
    ruta_firm4 = Path(args.maestro)
    for r in (ruta_nuevas, ruta_firm4):
        if not r.exists():
            _p(f"No existe el archivo: {r}")
            sys.exit(1)

    nuevas, cols_nuevas = leer_nuevas(ruta_nuevas)
    _p(f"Nuevas   : {ruta_nuevas}  ({len(nuevas)} filas)")
    _p(f"Destino  : {ruta_firm4}")

    wb = openpyxl.load_workbook(ruta_firm4)
    ws = wb.worksheets[0]
    cols = mapa_columnas(ws)

    mapeables = [c for c in cols_nuevas if c in cols and c not in COLS_IGNORAR]
    ignoradas = [c for c in cols_nuevas if c not in cols and c not in COLS_IGNORAR]
    _p(f"Columnas : {len(mapeables)} se copian"
       + (f" | sin equivalente en firm4 (se ignoran): {', '.join(ignoradas)}" if ignoradas else ""))
    if C_CARPETA not in cols:
        _p(f"El destino no tiene la columna '{C_CARPETA}'.")
        sys.exit(1)

    # indice de firm4 por clave
    indice: dict[str, list[int]] = {}
    for r in range(2, ws.max_row + 1):
        cl = clave(ws.cell(row=r, column=cols[C_CARPETA]).value)
        if cl:
            indice.setdefault(cl, []).append(r)

    fila_modelo = ws.max_row
    prox_fila = ws.max_row + 1
    agregadas, completadas, sin_cambios, sin_clave, avisos = [], [], [], [], []
    discrepancias: list[str] = []
    celdas_completadas = 0

    for fila in nuevas:
        cl = clave(fila.get(C_CARPETA))
        etiqueta = _txt(fila.get(C_CARPETA)) or "(sin carpeta)"
        if not cl:
            sin_clave.append(etiqueta)
            continue

        candidatos = indice.get(cl, [])
        destino, motivo = buscar_destino(fila, candidatos, ws, cols)

        if destino is None:
            if candidatos:
                avisos.append(
                    f"{cl}: el maestro ya tiene {len(candidatos)} fila(s) con esa carpeta pero con otra "
                    f"resolución; se agrega como fila nueva (fila {prox_fila}). Revisar si es otro "
                    f"trámite del mismo expediente o una carpeta mal cargada.")
            if not args.dry_run:
                for nombre in mapeables:
                    escribir(ws.cell(row=prox_fila, column=cols[nombre]), fila.get(nombre), nombre)
                copiar_estilo(ws, prox_fila, fila_modelo, ws.max_column)
            indice.setdefault(cl, []).append(prox_fila)
            agregadas.append(f"{cl}  (fila {prox_fila})")
            prox_fila += 1
            continue

        # expediente ya cargado: completar solo celdas vacias
        puestas = []
        for nombre in mapeables:
            valor = fila.get(nombre)
            if _vacia(valor):
                continue
            cel = ws.cell(row=destino, column=cols[nombre])
            if not _vacia(cel.value):
                # ya esta cargado: no se pisa, pero si no coincide se avisa
                if nombre in COLS_COTEJO and _comparable(cel.value, nombre) != _comparable(valor, nombre):
                    discrepancias.append(
                        f"{cl} (fila {destino}) · {nombre}: maestro '{_txt(cel.value)}' vs PDF '{_txt(valor)}'")
                continue
            if not args.dry_run:
                escribir(cel, valor, nombre)
            puestas.append(nombre)
        if puestas:
            celdas_completadas += len(puestas)
            completadas.append(f"{cl}  (fila {destino}, match por {motivo}): {', '.join(puestas)}")
        else:
            sin_cambios.append(f"{cl}  (fila {destino}, match por {motivo})")

    # el autofiltro tiene que cubrir las filas nuevas
    if ws.auto_filter.ref and not args.dry_run:
        inicio = ws.auto_filter.ref.split(":")[0]
        ultima_col = ws.cell(row=1, column=ws.max_column).column_letter
        ws.auto_filter.ref = f"{inicio}:{ultima_col}{ws.max_row}"

    # ---- guardar ---------------------------------------------------------- #
    if not args.dry_run and (agregadas or celdas_completadas):
        viejas = ruta_firm4.parent / VIEJAS
        viejas.mkdir(exist_ok=True)
        copia = viejas / f"{ruta_firm4.stem}_{dt.datetime.now():%Y%m%d-%H%M%S}{ruta_firm4.suffix}"
        shutil.copy2(ruta_firm4, copia)
        _p(f"\nCopia de la version anterior -> {copia}")
        wb.save(ruta_firm4)
    wb.close()

    # ---- informe ---------------------------------------------------------- #
    _p("")
    _p("DRY-RUN (no se escribio nada)" if args.dry_run else f"OK -> {ruta_firm4.name}")
    _p(f"  Filas agregadas    : {len(agregadas)}")
    for x in agregadas:
        _p(f"      + {x}")
    _p(f"  Filas completadas  : {len(completadas)}  ({celdas_completadas} celdas)")
    for x in completadas:
        _p(f"      ~ {x}")
    _p(f"  Ya estaban completas: {len(sin_cambios)}")
    for x in sin_cambios:
        _p(f"      = {x}")
    if sin_clave:
        _p(f"  Sin carpeta reconocible (se saltearon): {len(sin_clave)}")
        for x in sin_clave:
            _p(f"      ! {x}")
    if avisos:
        _p(f"\n  AVISOS ({len(avisos)}):")
        for x in avisos:
            _p(f"      * {x}")
    if discrepancias:
        _p(f"\n  DISCREPANCIAS ({len(discrepancias)}) - no se pisó nada, resolver a mano:")
        for x in discrepancias:
            _p(f"      ! {x}")
    if agregadas or celdas_completadas:
        _p("\n  Siguiente paso: python extraer_productos.py  y despues  python generar_pagina.py")


if __name__ == "__main__":
    main()
