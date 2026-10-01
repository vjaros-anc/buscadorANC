# -*- coding: utf-8 -*-
"""
Funde las cuatro copias sueltas del maestro en un unico firm.xlsx de 20 columnas.

Se corre UNA SOLA VEZ, para salir de la bifurcacion que dejo el pipeline partido
en dos arboles (raiz con firm.xlsx / carpeta "productos buscador" con firm4.xlsx).
Despues de esto, el circuito mensual vuelve a ser uno solo y este script no se
usa mas (ver PROTOCOLO.md).

De donde sale cada cosa:

    firm.xlsx                      BASE. Tiene las empresas que completo la IA
                                   (750 celdas) y los duplicados legitimos
                                   (OPI-232 x2, INC. 1663 x3).
    firm4_b.xlsx                   Las 15 filas nuevas de septiembre y 393
                                   "Mercados relevantes" que la base no tiene.
    productos buscador/firm4.xlsx  Las 3 columnas de productos, ya corregidas a
                                   mano, y las 10 filas que pegaste de
                                   Res_firmadas y todavia no tienen PDF.
    .../respaldos/firm4_2026...    El backup de agosto: es el unico que conserva
                                   los productos de los 45 expedientes que esa
                                   copia perdio despues.

REGLA DE ESCRITURA, la misma de siempre: solo se completan celdas VACIAS. Lo que
ya esta cargado en la base no se pisa nunca. Cuando las dos puntas tienen dato y
no coinciden, no se toca nada y se lista al final como DISCREPANCIA. Por eso los
16 choques de "Empresas involucradas" los gana firm.xlsx (son las celdas que la
IA ya habia corregido) y los 13 de "productos" los gana la copia de productos
buscador (es donde los arreglaste a mano).

Como identifica un expediente: la misma clave que usa el buscador
(nomenclador_mercados.parse_carpeta), con desempate por numero de resolucion.
Se reutiliza entera la logica de mergear_firmadas.py, no se duplica.

Las filas basura (las ~40 duplicadas que arrastra productos buscador/firm4.xlsx:
sin nº de resolucion, sin datos, con Fecha_firma 2017-01-01 de relleno) no se
agregan: si la carpeta ya existe en la base y la fila no aporta nada, se descarta
y se informa.

A las filas que SI se agregan se les normaliza la carpeta:
'CONC. 2139 (PROSUM)' -> 'CONC-2139'. El sufijo PROSUM ya lo lleva la columna
`tipo`.

No pisa ninguna de las cuatro entradas: escribe un archivo nuevo,
firm_unificado.xlsx. Mirá ese archivo, y recien cuando estes conforme lo
renombras a firm.xlsx (el comando esta al final del reporte). Si algo sale mal,
borras firm_unificado.xlsx y volves a correr: nada se perdio.

Uso:
    python unificar_maestro.py --dry-run     # no escribe, solo informa
    python unificar_maestro.py               # escribe firm_unificado.xlsx
    python unificar_maestro.py --salida otro.xlsx
"""
from __future__ import annotations

import argparse
import datetime as dt
import shutil
import sys
from pathlib import Path

import openpyxl

import nomenclador_mercados as nm
import mergear_firmadas as mg
from mergear_firmadas import (
    _p, _txt, _vacia, clave, norm_res, mapa_columnas, buscar_destino,
    copiar_estilo, escribir, C_CARPETA, C_RES, C_DICT,
)

AQUI = Path(__file__).parent
MAESTRO = AQUI / "firm.xlsx"
SALIDA = AQUI / "firm_unificado.xlsx"
REPORTE = AQUI / "unificacion_reporte.txt"

COLS_PRODUCTOS = ["productos", "productos_sector", "productos_sugeridos"]

# (etiqueta, ruta, columnas a las que se limita esta fuente o None = todas)
FUENTES = [
    ("firm4_b",
     AQUI / "firm4_b.xlsx",
     None),
    ("productos",
     AQUI / "productos buscador" / "firm4.xlsx",
     None),
    ("agosto",
     AQUI / "productos buscador" / "respaldos" / "firm4_20260816-203047.xlsx",
     COLS_PRODUCTOS),
]

# Una fila que no trae nada de esto no aporta: si su carpeta ya esta en la base,
# es una duplicada de relleno y se descarta.
COLS_SUSTANCIA = [
    "Carátula", "Decisión", "Número de Resolución", "Número de Dictamen",
    "Mercados relevantes", "Relaciones económicas", "mercado_relev_V2",
    "relaciones_econ_V2", "Grupo/Empresa", "Empresas involucradas",
    "productos", "productos_sector", "productos_sugeridos",
]

# Valores de relleno que NO cuentan como dato propio: el sector que pone el
# extractor cuando no clasifico nada, y la fecha de firma comodin que arrastran
# las filas viejas de 2017.
SECTOR_RELLENO = "Otros / sin clasificar"
FIRMA_RELLENO = "2017-01-01"

# Donde avisar si el dato ya cargado no coincide con el de la fuente.
COLS_COTEJO = mg.COLS_COTEJO | {"productos", "productos_sector", "Empresas involucradas"}


# --------------------------------------------------------------------------- #
def carpeta_canonica(valor) -> str:
    """'CONC. 2139 (PROSUM)' -> 'CONC-2139'. Si no parsea, devuelve el original."""
    tipo, numero, _ = nm.parse_carpeta(_txt(valor))
    return f"{tipo}-{numero}" if tipo and numero else _txt(valor)


def leer_filas(ruta: Path) -> tuple[list[dict], list[str]]:
    """Filas de un xlsx como dicts {encabezado: valor}, salteando las vacias."""
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


def sin_numero(fila: dict) -> bool:
    return not (norm_res(fila.get(C_RES)) or norm_res(fila.get(C_DICT)))


def aporta(fila: dict) -> bool:
    """Si la fila trae algun dato propio. El sector 'Otros / sin clasificar' no
    cuenta: lo pone el extractor solo, no es informacion cargada."""
    for c in COLS_SUSTANCIA:
        v = fila.get(c)
        if _vacia(v):
            continue
        if c == "productos_sector" and _txt(v) == SECTOR_RELLENO:
            continue
        return True
    return False


def agregar_columnas(ws, cols: dict[str, int], faltantes: list[str], dry_run: bool) -> None:
    """Suma columnas al final de la hoja, copiando el estilo del encabezado vecino.

    En dry-run no se escribe el encabezado, asi que ws.max_column no crece: hay
    que llevar el indice a mano o las tres columnas caerian en la misma.
    """
    c = ws.max_column
    for nombre in faltantes:
        c += 1
        if not dry_run:
            ref = ws.cell(row=1, column=c - 1)
            cel = ws.cell(row=1, column=c, value=nombre)
            cel.font = mg.copy(ref.font)
            cel.fill = mg.copy(ref.fill)
            cel.border = mg.copy(ref.border)
            cel.alignment = mg.copy(ref.alignment)
            ws.column_dimensions[cel.column_letter].width = 28
        cols[nombre] = c


# --------------------------------------------------------------------------- #
def main() -> None:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--maestro", default=str(MAESTRO),
                    help="xlsx base, se usa de molde y NO se modifica (default: firm.xlsx)")
    ap.add_argument("--salida", default=str(SALIDA),
                    help="xlsx que se escribe (default: firm_unificado.xlsx)")
    ap.add_argument("--dry-run", action="store_true", help="no escribe nada, solo informa")
    args = ap.parse_args()

    base = Path(args.maestro)
    if not base.exists():
        _p(f"No existe el maestro: {base}")
        sys.exit(1)

    # Se trabaja sobre una copia: firm.xlsx es una de las entradas y tiene que
    # quedar intacto para poder repetir la corrida y comparar los resultados.
    ruta = Path(args.salida)
    if not args.dry_run:
        shutil.copy2(base, ruta)
    else:
        ruta = base

    fuentes = [(n, p, lim) for n, p, lim in FUENTES if p.exists()]
    for n, p, _lim in FUENTES:
        if not p.exists():
            _p(f"AVISO: no se encontro la fuente '{n}': {p}")
    if not fuentes:
        _p("No hay ninguna fuente para fundir.")
        sys.exit(1)

    wb = openpyxl.load_workbook(ruta)
    ws = wb.worksheets[0]
    cols = mapa_columnas(ws)
    _p(f"Base     : {base}  (hoja '{ws.title}', {ws.max_row - 1} filas, {len(cols)} columnas)")
    _p(f"Salida   : {'(dry-run, no se escribe)' if args.dry_run else ruta}")

    faltantes = [c for c in COLS_PRODUCTOS if c not in cols]
    if faltantes:
        agregar_columnas(ws, cols, faltantes, args.dry_run)
        _p(f"Columnas nuevas: {', '.join(faltantes)}")

    # indice de la base por clave
    indice: dict[str, list[int]] = {}
    for r in range(2, ws.max_row + 1):
        cl = clave(ws.cell(row=r, column=cols[C_CARPETA]).value)
        if cl:
            indice.setdefault(cl, []).append(r)

    fila_modelo = ws.max_row
    prox_fila = ws.max_row + 1

    total_celdas = 0
    lineas: list[str] = []
    resumen: list[str] = []
    discrepancias: list[str] = []
    descartadas: list[str] = []
    sin_clave: list[str] = []

    for etiqueta, ruta_f, limite in fuentes:
        filas, cols_f = leer_filas(ruta_f)
        mapeables = [c for c in cols_f if c in cols]
        if limite is not None:
            mapeables = [c for c in mapeables if c in limite]
        ignoradas = [c for c in cols_f if c not in cols]

        _p("")
        _p(f"--- {etiqueta}: {ruta_f.name}  ({len(filas)} filas, {len(mapeables)} columnas se copian)")
        if ignoradas:
            _p(f"    sin equivalente en el maestro (se ignoran): {', '.join(ignoradas)}")

        n_celdas = n_agregadas = n_completadas = n_descartadas = 0
        lineas.append("")
        lineas.append(f"=== FUENTE: {etiqueta}  ({ruta_f}) ===")

        for fila in filas:
            cl = clave(fila.get(C_CARPETA))
            original = _txt(fila.get(C_CARPETA)) or "(sin carpeta)"
            if not cl:
                sin_clave.append(f"{etiqueta}: {original}")
                continue

            candidatos = indice.get(cl, [])

            # Fila sin nº de resolucion y sin ningun dato propio, con la carpeta
            # ya cargada: es relleno (las ~219 que arrastra productos buscador).
            # Se saltea antes de buscar destino para que no ensucie el cotejo.
            if candidatos and sin_numero(fila) and not aporta(fila):
                descartadas.append(f"{etiqueta}: {original} (sin nº de resolución y sin datos)")
                n_descartadas += 1
                continue

            destino, motivo = buscar_destino(fila, candidatos, ws, cols)

            # sin nº de resolucion pero con datos: es la misma fila, cargada a medias
            if destino is None and candidatos and sin_numero(fila):
                destino, motivo = candidatos[0], "carpeta (fila sin nº de resolución)"

            if destino is None:
                canon = carpeta_canonica(fila.get(C_CARPETA))
                if candidatos:
                    lineas.append(
                        f"  AVISO {cl}: el maestro ya tiene {len(candidatos)} fila(s) con esa "
                        f"carpeta pero con otra resolución; se agrega como fila nueva "
                        f"(fila {prox_fila}). Revisar si es otro trámite del mismo expediente.")
                if not args.dry_run:
                    for nombre in mapeables:
                        valor = carpeta_canonica(fila.get(nombre)) if nombre == C_CARPETA \
                            else fila.get(nombre)
                        escribir(ws.cell(row=prox_fila, column=cols[nombre]), valor, nombre)
                    copiar_estilo(ws, prox_fila, fila_modelo, ws.max_column)
                indice.setdefault(cl, []).append(prox_fila)
                nota = f" [carpeta normalizada: '{original}' -> '{canon}']" if original != canon else ""
                lineas.append(f"  + {canon}  (fila {prox_fila}){nota}")
                n_agregadas += 1
                prox_fila += 1
                continue

            # expediente ya cargado: completar solo celdas vacias
            puestas = []
            for nombre in mapeables:
                valor = fila.get(nombre)
                if _vacia(valor) or nombre == C_CARPETA:
                    continue
                # la fecha comodin de las filas viejas no es un dato: no se copia
                if nombre in mg.COLS_FECHA and mg._fecha(valor) == FIRMA_RELLENO:
                    continue
                cel = ws.cell(row=destino, column=cols[nombre])
                if not _vacia(cel.value):
                    if nombre in COLS_COTEJO and \
                            mg._comparable(cel.value, nombre) != mg._comparable(valor, nombre):
                        discrepancias.append(
                            f"{cl} (fila {destino}) · {nombre}: maestro '{_txt(cel.value)[:70]}' "
                            f"vs {etiqueta} '{_txt(valor)[:70]}'")
                    continue
                if not args.dry_run:
                    escribir(cel, valor, nombre)
                puestas.append(nombre)
            if puestas:
                n_celdas += len(puestas)
                n_completadas += 1
                lineas.append(f"  ~ {cl}  (fila {destino}, match por {motivo}): {', '.join(puestas)}")

        total_celdas += n_celdas
        resumen.append(
            f"  {etiqueta:10s} filas agregadas {n_agregadas:4d} | filas completadas "
            f"{n_completadas:4d} ({n_celdas} celdas) | descartadas {n_descartadas:3d}")
        _p(resumen[-1].strip())

    # el autofiltro tiene que cubrir las filas nuevas
    if ws.auto_filter.ref and not args.dry_run:
        inicio = ws.auto_filter.ref.split(":")[0]
        ultima_col = ws.cell(row=1, column=ws.max_column).column_letter
        ws.auto_filter.ref = f"{inicio}:{ultima_col}{ws.max_row}"

    # ---- guardar ---------------------------------------------------------- #
    # No hay respaldo: la salida es un archivo nuevo y las cuatro entradas
    # quedan como estaban.
    if not args.dry_run:
        wb.save(ruta)
    filas_finales = ws.max_row - 1
    cols_finales = ws.max_column
    wb.close()

    # ---- informe ----------------------------------------------------------- #
    cab = [
        "DRY-RUN (no se escribio nada)" if args.dry_run else f"OK -> {ruta.name}  (el maestro original quedo intacto)",
        f"  Maestro final      : {filas_finales} filas x {cols_finales} columnas",
        f"  Celdas completadas : {total_celdas}",
        f"  Discrepancias      : {len(discrepancias)}  (no se piso nada, revisar a mano)",
        f"  Filas sin aporte   : {len(descartadas)}  (sin nº de resolución y sin datos)",
        f"  Sin carpeta legible: {len(sin_clave)}",
        "",
        "Por fuente:",
        *resumen,
    ]
    _p("")
    for x in cab:
        _p(x)

    if discrepancias:
        _p("")
        _p(f"DISCREPANCIAS ({len(discrepancias)}) - las primeras 15:")
        for x in discrepancias[:15]:
            _p(f"  ! {x}")
        _p(f"  (el detalle completo queda en {REPORTE.name})")

    texto = "\n".join(
        cab
        + ["", f"--- SIN APORTE, NO SE AGREGARON ({len(descartadas)}) ---",
           *[f"  - {x}" for x in descartadas]]
        + ["", f"--- SIN CARPETA LEGIBLE ({len(sin_clave)}) ---", *[f"  - {x}" for x in sin_clave]]
        + ["", f"--- DISCREPANCIAS ({len(discrepancias)}) ---", *[f"  ! {x}" for x in discrepancias]]
        + ["", "--- DETALLE ---", *lineas]
    )
    reporte = ruta.parent / REPORTE.name
    reporte.write_text(texto, encoding="utf-8")
    _p("")
    _p(f"Reporte completo -> {reporte}")


if __name__ == "__main__":
    main()
