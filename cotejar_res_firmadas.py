# -*- coding: utf-8 -*-
"""
Coteja el insumo del buscador (firm.xlsx) contra el seguimiento de gestion
(Res_firmadas.xlsm) y escribe un informe explicativo en Excel.

Responde dos preguntas:
  1) toda resolucion FIRMADA registrada en Res_firmadas, esta publicada en el
     buscador?
  2) lo que NO esta en el buscador, es exactamente lo que Res_firmadas marca
     EN PROCESO?

Alcance: solo CONC (se incluyen los incidentes "INC. I. CONC. NNNN" porque son
incidentes de una concentracion y figuran en los dos archivos). OPI y DP quedan
fuera del cotejo y solo se informan como filas excluidas.

Los dos Excel de entrada se abren en SOLO LECTURA; el unico archivo que este
script escribe es el informe de salida.

Uso:
    python cotejar_res_firmadas.py
"""
from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

import pandas as pd
from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

import nomenclador_mercados as nm

AQUI = Path(__file__).parent
BUSCADOR = AQUI / "firm.xlsx"          # insumo de generar_pagina.py -> index.html
SEGUIMIENTO = AQUI / "Res_firmadas.xlsm"
SALIDA = AQUI / "cotejo_buscador_vs_res_firmadas.xlsx"

# Corte acordado: Res_firmadas se completa principalmente desde 2024, asi que lo
# anterior no se reclama; se lista aparte como anexo informativo.
CORTE = pd.Timestamp("2024-01-01")

# Estados de evol_conc POSTERIORES a la firma: es correcto que esos expedientes
# esten publicados en el buscador.
ESTADOS_POST_FIRMA = {"Firmada", "Apelada", "Subordinada en cumplimiento"}

FUENTE = "Arial"


# --------------------------------------------------------------------------- #
# Claves
# --------------------------------------------------------------------------- #
def clave(carpeta) -> str:
    """Clave de cotejo: la MISMA normalizacion que usa el buscador para los PDFs
    (nomenclador_mercados.parse_carpeta). 'CONC. 2124 (PROSUM)' -> 'CONC 2124'."""
    tipo, numero, _ = nm.parse_carpeta(nm.clean(carpeta))
    return f"{tipo} {numero}" if numero else ""


def norm_res(valor) -> str:
    """Numero de resolucion/dictamen normalizado, para el control cruzado."""
    return re.sub(r"[\s.]", "", nm.clean(valor).upper())


def es_conc(cl: str) -> bool:
    return cl.startswith("CONC ") or cl.startswith("INC ")


# --------------------------------------------------------------------------- #
# Carga (solo lectura)
# --------------------------------------------------------------------------- #
def cargar():
    bus = pd.read_excel(BUSCADOR, sheet_name=0, dtype=str)
    fir = pd.read_excel(SEGUIMIENTO, sheet_name="firmadas", dtype=str)
    evo = pd.read_excel(SEGUIMIENTO, sheet_name="evol_conc", dtype=str)

    bus["clave"] = bus["Carpeta"].map(clave)
    fir["clave"] = fir["Carpeta"].map(clave)
    evo["clave"] = evo["Clave"].map(clave)

    for df in (bus, fir, evo):
        df["f_firma"] = pd.to_datetime(df["Fecha_firma"], errors="coerce")
        df["f_ingreso"] = pd.to_datetime(df["Fecha_Ingreso"], errors="coerce")

    for df in (bus, fir):
        df["res_n"] = df["Número de Resolución"].map(norm_res)
        df["dic_n"] = df["Número de Dictamen"].map(norm_res)
    return bus, fir, evo


# --------------------------------------------------------------------------- #
# Cotejo
# --------------------------------------------------------------------------- #
def cotejar(bus, fir, evo):
    excluidas = {
        "buscador": int((~bus["clave"].map(es_conc)).sum()),
        "firmadas": int((~fir["clave"].map(es_conc)).sum()),
        "evol_conc": int((~evo["clave"].map(es_conc)).sum()),
    }
    b = bus[bus["clave"].map(es_conc)].copy()
    f = fir[fir["clave"].map(es_conc)].copy()
    e = evo[evo["clave"].map(es_conc)].copy()

    claves_bus = set(b["clave"])
    claves_fir = set(f["clave"])
    claves_evol = set(e["clave"])
    estado_evol = dict(zip(e["clave"], e["ESTADO"].fillna("")))

    # numeros de resolucion/dictamen ya publicados, por clave
    res_por_clave: dict[str, set[str]] = {}
    for _, r in b.iterrows():
        s = res_por_clave.setdefault(r["clave"], set())
        s.update(x for x in (r["res_n"], r["dic_n"]) if x)

    # ---- 1) firmadas que no estan en el buscador --------------------------- #
    filas1 = []
    for _, r in f.iterrows():
        cl = r["clave"]
        publicada = cl in claves_bus
        enmascarada = False
        if publicada and r["res_n"]:
            # la clave figura en el buscador, pero ninguna fila con esa clave
            # tiene este numero de resolucion ni este dictamen -> la carpeta del
            # buscador esta mal cargada y el expediente real NO esta publicado.
            ya = res_por_clave.get(cl, set())
            if r["res_n"] not in ya and (not r["dic_n"] or r["dic_n"] not in ya):
                enmascarada = True
        if publicada and not enmascarada:
            continue
        completo = bool(nm.clean(r["Decisión"]) and nm.clean(r["Número de Resolución"]))
        if enmascarada:
            obs = ("El buscador tiene una fila con esta clave pero con OTRA resolución: "
                   "la carpeta está mal cargada en firm.xlsx y este expediente no está publicado.")
        elif completo:
            obs = "Falta cargar en firm.xlsx."
        else:
            obs = ("Falta cargar en firm.xlsx; antes hay que completar decisión y "
                   "nº de resolución en Res_firmadas.")
        filas1.append({
            "Clave": cl,
            "Carpeta (Res_firmadas)": nm.clean(r["Carpeta"]),
            "Tipo de trámite": nm.clean(r["tipo"]),
            "Carátula": nm.clean(r["Carátula"]),
            "Fecha_Ingreso": r["f_ingreso"],
            "Fecha_firma": r["f_firma"],
            "Decisión": nm.clean(r["Decisión"]),
            "Número de Resolución": nm.clean(r["Número de Resolución"]),
            "Número de Dictamen": nm.clean(r["Número de Dictamen"]),
            "Mercados relevantes": nm.clean(r["Mercados relevantes"]),
            "Relaciones económicas": nm.clean(r["Relaciones económicas"]),
            "Origen": "firmadas + evol_conc" if cl in claves_evol else "solo hoja firmadas",
            "ESTADO en evol_conc": estado_evol.get(cl, ""),
            "¿Datos completos para publicar?": "SI" if completo else "NO",
            "Observación": obs,
        })
    claves1 = {x["Clave"] for x in filas1}

    # firmadas segun evol_conc que ni siquiera estan en la hoja 'firmadas'
    for _, r in e[e["ESTADO"] == "Firmada"].iterrows():
        cl = r["clave"]
        if cl in claves_bus or cl in claves1:
            continue
        filas1.append({
            "Clave": cl,
            "Carpeta (Res_firmadas)": nm.clean(r["Clave"]),
            "Tipo de trámite": "",
            "Carátula": nm.clean(r["Caratula"]),
            "Fecha_Ingreso": r["f_ingreso"],
            "Fecha_firma": r["f_firma"],
            "Decisión": "",
            "Número de Resolución": "",
            "Número de Dictamen": "",
            "Mercados relevantes": "",
            "Relaciones económicas": "",
            "Origen": "solo evol_conc",
            "ESTADO en evol_conc": "Firmada",
            "¿Datos completos para publicar?": "NO",
            "Observación": ("Figura FIRMADA en evol_conc pero no está cargada en la hoja "
                            "'firmadas' ni en el buscador: faltan decisión y nº de resolución."),
        })
    h1 = pd.DataFrame(filas1).sort_values(["Fecha_firma", "Clave"], na_position="last")

    # ---- 2) en el buscador y sin registro en Res_firmadas ------------------ #
    universo_seg = claves_fir | claves_evol
    fuera = b[~b["clave"].isin(universo_seg)].copy()

    def _fila2(r, motivo=None):
        d = {
            "Clave": r["clave"],
            "Carpeta (buscador)": nm.clean(r["Carpeta"]),
            "tipo": nm.clean(r["tipo"]),
            "Carátula": nm.clean(r["Carátula"]),
            "Fecha_firma": r["f_firma"],
            "Decisión": nm.clean(r["Decisión"]),
            "Número de Resolución": nm.clean(r["Número de Resolución"]),
            "Número de Dictamen": nm.clean(r["Número de Dictamen"]),
            "Mercados relevantes": nm.clean(r["Mercados relevantes"]),
            "Relaciones económicas": nm.clean(r["Relaciones económicas"]),
            "Grupo/Empresa": nm.clean(r["Grupo/Empresa"]),
        }
        if motivo:
            d["Motivo fuera de alcance"] = motivo
        return d

    en_corte = fuera["f_firma"] >= CORTE
    h2 = pd.DataFrame([_fila2(r) for _, r in fuera[en_corte].iterrows()])
    if not h2.empty:
        h2 = h2.sort_values("Fecha_firma")

    filas2b = []
    for _, r in fuera[~en_corte].iterrows():
        if pd.isna(r["f_firma"]):
            motivo = "Sin fecha de firma"
        elif r["f_firma"] >= pd.Timestamp("2023-01-01"):
            motivo = "Firmada en 2023"
        else:
            motivo = "Firmada antes de 2023"
        filas2b.append(_fila2(r, motivo))
    h2b = pd.DataFrame(filas2b).sort_values(["Fecha_firma", "Clave"], na_position="last")

    # ---- 3) publicadas pero "en proceso" en evol_conc ---------------------- #
    filas3 = []
    for _, r in e[e["ESTADO"] != "Firmada"].iterrows():
        cl = r["clave"]
        if cl not in claves_bus:
            continue
        est = nm.clean(r["ESTADO"])
        esperable = est in ESTADOS_POST_FIRMA
        bb = b[b["clave"] == cl].sort_values("f_firma", na_position="first")
        b0 = bb.iloc[-1] if len(bb) else None
        filas3.append({
            "Clave": cl,
            "ESTADO en evol_conc": est or "(vacío)",
            "Observaciones (evol_conc)": nm.clean(r["Observaciones"]),
            "Carátula": nm.clean(r["Caratula"]),
            "Fecha_firma (evol_conc)": r["f_firma"],
            "Fecha_firma (buscador)": b0["f_firma"] if b0 is not None else pd.NaT,
            "Número de Resolución (buscador)": nm.clean(b0["Número de Resolución"]) if b0 is not None else "",
            "¿Esperable?": "SI" if esperable else "REVISAR",
            "Comentario": ("Estado posterior a la firma: es correcto que esté publicada."
                           if esperable else
                           "Está publicada en el buscador pero el seguimiento no la da por firmada: "
                           "hay que definir cuál de los dos archivos está desactualizado."),
        })
    h3 = pd.DataFrame(filas3).sort_values(["¿Esperable?", "Clave"])

    # ---- 4) en proceso y correctamente ausentes (el cierre) ---------------- #
    filas4 = []
    for _, r in e[e["ESTADO"] != "Firmada"].iterrows():
        if r["clave"] in claves_bus:
            continue
        filas4.append({
            "Clave": r["clave"],
            "ESTADO en evol_conc": nm.clean(r["ESTADO"]) or "(vacío)",
            "Carátula": nm.clean(r["Caratula"]),
            "Fecha_Ingreso": r["f_ingreso"],
            "Meses en trámite": nm.clean(r["MESES"]),
            "Observaciones": nm.clean(r["Observaciones"]),
        })
    h4 = pd.DataFrame(filas4).sort_values(["ESTADO en evol_conc", "Clave"])

    # ---- 5) discrepancias de datos entre ambos archivos -------------------- #
    # Los incidentes de una misma CONC comparten clave, asi que se comparan
    # CONJUNTOS de valores por clave y no fila contra fila.
    filas5 = []
    gb = b.groupby("clave").agg(
        f_bus=("f_firma", lambda s: sorted({x.date() for x in s if pd.notna(x)})),
        r_bus=("res_n", lambda s: sorted({x for x in s if x})),
    )
    gf = f.groupby("clave").agg(
        f_seg=("f_firma", lambda s: sorted({x.date() for x in s if pd.notna(x)})),
        r_seg=("res_n", lambda s: sorted({x for x in s if x})),
    )
    for cl, r in gb.join(gf, how="inner").iterrows():
        if r["f_bus"] and r["f_seg"] and r["f_bus"] != r["f_seg"]:
            filas5.append({
                "Clave": cl,
                "Campo": "Fecha de firma",
                "Valor en el buscador": ", ".join(d.strftime("%d/%m/%Y") for d in r["f_bus"]),
                "Valor en Res_firmadas": ", ".join(d.strftime("%d/%m/%Y") for d in r["f_seg"]),
                "Comentario": "Misma carpeta con distinta fecha de firma en cada archivo.",
            })
        if r["r_bus"] and r["r_seg"] and r["r_bus"] != r["r_seg"]:
            filas5.append({
                "Clave": cl,
                "Campo": "Número de resolución",
                "Valor en el buscador": ", ".join(r["r_bus"]),
                "Valor en Res_firmadas": ", ".join(r["r_seg"]),
                "Comentario": "Misma carpeta con distinto nº de resolución: revisar cuál corresponde.",
            })
    dup = b[b["res_n"] != ""]
    dup = dup[dup.duplicated("res_n", keep=False)]
    for _, grupo in dup.groupby("res_n"):
        if grupo["clave"].nunique() < 2:
            continue
        filas5.append({
            "Clave": " / ".join(sorted(set(grupo["clave"]))),
            "Campo": "Nº de resolución duplicado en el buscador",
            "Valor en el buscador": nm.clean(grupo.iloc[0]["Número de Resolución"]),
            "Valor en Res_firmadas": "",
            "Comentario": "La misma resolución está cargada en dos expedientes distintos de firm.xlsx.",
        })
    h5 = pd.DataFrame(filas5)

    # ---- 6) datos incompletos dentro de Res_firmadas ----------------------- #
    filas6 = []
    for _, r in f.iterrows():
        falta = []
        if not nm.clean(r["Decisión"]):
            falta.append("decisión")
        if not nm.clean(r["Número de Resolución"]):
            falta.append("nº de resolución")
        if falta:
            filas6.append({
                "Clave": r["clave"],
                "Problema": "Fila de 'firmadas' incompleta",
                "Detalle": "Falta " + " y ".join(falta) + ".",
                "Fecha_firma": r["f_firma"],
                "ESTADO en evol_conc": estado_evol.get(r["clave"], ""),
                "Carátula": nm.clean(r["Carátula"]),
            })
    for _, r in e[(e["ESTADO"] == "Firmada") & (e["f_firma"].isna())].iterrows():
        filas6.append({
            "Clave": r["clave"],
            "Problema": "Firmada sin fecha de firma",
            "Detalle": "evol_conc la marca Firmada pero no tiene Fecha_firma.",
            "Fecha_firma": pd.NaT,
            "ESTADO en evol_conc": "Firmada",
            "Carátula": nm.clean(r["Caratula"]),
        })
    for _, r in e[(e["ESTADO"] == "Firmada") & (~e["clave"].isin(claves_fir))].iterrows():
        filas6.append({
            "Clave": r["clave"],
            "Problema": "Firmada en evol_conc sin fila en 'firmadas'",
            "Detalle": "No tiene decisión ni nº de resolución cargados en ninguna hoja.",
            "Fecha_firma": r["f_firma"],
            "ESTADO en evol_conc": "Firmada",
            "Carátula": nm.clean(r["Caratula"]),
        })
    for _, r in f[~f["clave"].isin(claves_evol)].iterrows():
        filas6.append({
            "Clave": r["clave"],
            "Problema": "En 'firmadas' sin fila en evol_conc (informativo)",
            "Detalle": "evol_conc no cubre este expediente; no afecta al buscador.",
            "Fecha_firma": r["f_firma"],
            "ESTADO en evol_conc": "",
            "Carátula": nm.clean(r["Carátula"]),
        })
    h6 = pd.DataFrame(filas6).sort_values(["Problema", "Fecha_firma", "Clave"], na_position="last")

    ctx = {
        "excluidas": excluidas,
        "claves_bus": len(claves_bus),
        "claves_fir": len(claves_fir),
        "claves_evol": len(claves_evol),
        "filas_bus": len(b),
        "filas_fir": len(f),
        "filas_evol": len(e),
    }
    return {"h1": h1, "h2": h2, "h2b": h2b, "h3": h3, "h4": h4, "h5": h5, "h6": h6}, ctx


# --------------------------------------------------------------------------- #
# Escritura del informe
# --------------------------------------------------------------------------- #
AZUL_OSC = PatternFill("solid", fgColor="1F3864")
ROJO = PatternFill("solid", fgColor="F8CBAD")
AMAR = PatternFill("solid", fgColor="FFE699")
VERDE = PatternFill("solid", fgColor="C6E0B4")
AZUL = PatternFill("solid", fgColor="DDEBF7")
BORDE = Border(*[Side(style="thin", color="BFBFBF")] * 4)

# fila donde arranca el encabezado de cada tabla de detalle (debajo de la nota)
FILA_CAB = 3

ANCHOS = {
    "Clave": 12, "Carátula": 60, "Mercados relevantes": 45, "Observación": 60,
    "Observaciones": 50, "Observaciones (evol_conc)": 45, "Comentario": 60,
    "Detalle": 45, "Decisión": 34, "Número de Resolución": 30,
    "Número de Dictamen": 30, "Carpeta (Res_firmadas)": 22, "Carpeta (buscador)": 20,
    "Grupo/Empresa": 40, "Relaciones económicas": 22, "Origen": 20,
    "Tipo de trámite": 15, "ESTADO en evol_conc": 20, "Problema": 40,
    "¿Datos completos para publicar?": 16, "¿Esperable?": 12, "Campo": 32,
    "Valor en el buscador": 30, "Valor en Res_firmadas": 30,
    "Motivo fuera de alcance": 22, "Meses en trámite": 12,
    "Número de Resolución (buscador)": 30, "Fecha_firma (evol_conc)": 16,
    "Fecha_firma (buscador)": 16,
}
WRAP = {"Carátula", "Mercados relevantes", "Observación", "Observaciones",
        "Observaciones (evol_conc)", "Comentario", "Detalle", "Decisión"}


def escribir_tabla(ws, df, nota):
    ws.sheet_view.showGridLines = False
    c = ws.cell(row=1, column=1, value=nota)
    c.font = Font(name=FUENTE, size=9, italic=True, color="595959")
    c.alignment = Alignment(vertical="top", wrap_text=True)
    ws.row_dimensions[1].height = 28

    if df is None or df.empty:
        v = ws.cell(row=FILA_CAB, column=1, value="(sin casos)")
        v.font = Font(name=FUENTE, size=10, bold=True)
        ws.column_dimensions["A"].width = 40
        return

    cols = list(df.columns)
    for j, col in enumerate(cols, start=1):
        cel = ws.cell(row=FILA_CAB, column=j, value=col)
        cel.font = Font(name=FUENTE, size=10, bold=True, color="FFFFFF")
        cel.fill = AZUL_OSC
        cel.alignment = Alignment(vertical="center", wrap_text=True)
        cel.border = BORDE
    for i, (_, r) in enumerate(df.iterrows(), start=FILA_CAB + 1):
        for j, col in enumerate(cols, start=1):
            v = r[col]
            if isinstance(v, pd.Timestamp):
                v = None if pd.isna(v) else v.to_pydatetime()
            elif v is None or (isinstance(v, float) and pd.isna(v)):
                v = None
            cel = ws.cell(row=i, column=j, value=v)
            cel.font = Font(name=FUENTE, size=10)
            cel.border = BORDE
            cel.alignment = Alignment(vertical="top", wrap_text=col in WRAP)
            if isinstance(v, datetime):
                cel.number_format = "DD/MM/YYYY"
            if col == "¿Datos completos para publicar?":
                cel.fill = VERDE if v == "SI" else ROJO
            elif col == "¿Esperable?":
                cel.fill = VERDE if v == "SI" else AMAR
    for j, col in enumerate(cols, start=1):
        ws.column_dimensions[get_column_letter(j)].width = ANCHOS.get(col, 18)
    ws.auto_filter.ref = f"A{FILA_CAB}:{get_column_letter(len(cols))}{FILA_CAB + len(df)}"
    ws.freeze_panes = ws.cell(row=FILA_CAB + 1, column=1)


def escribir(hojas, ctx):
    wb = Workbook()
    # openpyxl no guarda el valor calculado de las formulas del Resumen: esto le
    # pide a Excel que recalcule al abrir el archivo.
    wb.calculation.fullCalcOnLoad = True
    resumen = wb.active
    resumen.title = "Resumen"

    detalle = [
        ("1_Faltan_en_buscador", hojas["h1"],
         "Firmadas registradas en Res_firmadas que NO están publicadas en el buscador. Es lo que hay "
         "que cargar en firm.xlsx (y después correr generar_pagina.py)."),
        ("2_Faltan_en_Res_firmadas", hojas["h2"],
         "Expedientes publicados en el buscador, con fecha de firma desde el "
         f"{CORTE.strftime('%d/%m/%Y')}, que no tienen ninguna fila en Res_firmadas."),
        ("2b_Anexo_pre2024", hojas["h2b"],
         "INFORMATIVO / fuera de alcance: publicados en el buscador y sin fila en Res_firmadas, pero "
         "firmados antes de 2024 o sin fecha de firma. No se reclaman."),
        ("3_En_buscador_en_proceso", hojas["h3"],
         "Publicados en el buscador que evol_conc NO marca como Firmada. 'Apelada' y 'Subordinada en "
         "cumplimiento' son estados posteriores a la firma (esperable); el resto hay que revisarlo."),
        ("4_En_proceso_OK", hojas["h4"],
         "El cierre del cotejo: expedientes en proceso en evol_conc que correctamente NO están en el "
         "buscador. Junto con la solapa 1, agotan las razones por las que algo puede no estar publicado."),
        ("5_Discrepancias_de_datos", hojas["h5"],
         "El expediente está en los dos archivos pero con datos distintos, o el buscador repite un "
         "número de resolución en dos expedientes."),
        ("6_Datos_incompletos_Res_firm", hojas["h6"],
         "Faltantes dentro del propio Res_firmadas. Los dos primeros grupos bloquean la carga al "
         "buscador; el último es solo informativo."),
    ]
    for nombre, df, nota in detalle:
        escribir_tabla(wb.create_sheet(nombre), df, nota)

    # ---------------- Resumen ---------------- #
    resumen.sheet_view.showGridLines = False
    resumen["A1"] = "Cotejo buscador (firm.xlsx) vs. seguimiento (Res_firmadas.xlsm)"
    resumen["A1"].font = Font(name=FUENTE, size=14, bold=True, color="1F3864")
    resumen.row_dimensions[1].height = 22

    meta = [
        ("Informe generado", datetime.now().strftime("%d/%m/%Y %H:%M")),
        ("firm.xlsx (insumo del buscador)",
         datetime.fromtimestamp(BUSCADOR.stat().st_mtime).strftime("%d/%m/%Y %H:%M")),
        ("Res_firmadas.xlsm (seguimiento)",
         datetime.fromtimestamp(SEGUIMIENTO.stat().st_mtime).strftime("%d/%m/%Y %H:%M")),
        ("Alcance",
         "Solo CONC (incluye los incidentes INC de una CONC). Filas OPI/DP excluidas: "
         f"{ctx['excluidas']['buscador']} del buscador, {ctx['excluidas']['firmadas']} de 'firmadas', "
         f"{ctx['excluidas']['evol_conc']} de 'evol_conc'."),
        ("Universo cotejado",
         f"{ctx['claves_bus']} carpetas en el buscador · {ctx['claves_fir']} en 'firmadas' · "
         f"{ctx['claves_evol']} en 'evol_conc'."),
        ("Corte", "El reclamo a Res_firmadas se limita a firmas desde el "
                  f"{CORTE.strftime('%d/%m/%Y')}; lo anterior va al anexo 2b."),
    ]
    fila = 3
    for k, v in meta:
        resumen.cell(row=fila, column=1, value=k).font = Font(name=FUENTE, size=10, bold=True)
        c = resumen.cell(row=fila, column=2, value=v)
        c.font = Font(name=FUENTE, size=10)
        c.alignment = Alignment(wrap_text=True, vertical="top")
        fila += 1

    fila += 1
    cab = fila
    for j, h in enumerate(["#", "Chequeo", "Casos", "Semáforo", "Solapa",
                           "Qué significa / qué hacer"], start=1):
        c = resumen.cell(row=cab, column=j, value=h)
        c.font = Font(name=FUENTE, size=10, bold=True, color="FFFFFF")
        c.fill = AZUL_OSC
        c.border = BORDE
        c.alignment = Alignment(vertical="center", horizontal="center", wrap_text=True)

    filas_resumen = [
        ("1", "Firmadas en Res_firmadas que faltan en el buscador", "1_Faltan_en_buscador",
         hojas["h1"], True,
         "Es el hueco principal. Cargarlas en firm.xlsx y regenerar index.html. Las marcadas con NO "
         "en '¿Datos completos para publicar?' necesitan que antes se complete Res_firmadas."),
        ("2", f"En el buscador (firma ≥ {CORTE.year}) sin registro en Res_firmadas",
         "2_Faltan_en_Res_firmadas", hojas["h2"], True,
         "Están publicadas pero el seguimiento no las tiene. Hay que darlas de alta en Res_firmadas."),
        ("2b", "Ídem, firmadas antes de 2024 o sin fecha (fuera de alcance)", "2b_Anexo_pre2024",
         hojas["h2b"], None,
         "Informativo. Res_firmadas se completa desde 2024, así que no se reclaman."),
        ("3", "En el buscador pero 'en proceso' en evol_conc", "3_En_buscador_en_proceso",
         hojas["h3"], False,
         "Casi todas son Apeladas o Subordinadas en cumplimiento (estados posteriores a la firma: es "
         "correcto que estén publicadas). Mirar solo las marcadas REVISAR."),
        ("4", "En proceso y correctamente ausentes del buscador", "4_En_proceso_OK",
         hojas["h4"], None,
         "Es el cierre buscado: lo que falta en el buscador y está justificado porque sigue en trámite."),
        ("5", "Mismo expediente con datos distintos en cada archivo", "5_Discrepancias_de_datos",
         hojas["h5"], False,
         "Fechas de firma o números de resolución que no coinciden, y resoluciones repetidas en firm4."),
        ("6", "Registros incompletos dentro de Res_firmadas", "6_Datos_incompletos_Res_firm",
         hojas["h6"], False,
         "Filas firmadas sin decisión o sin nº de resolución, y firmadas que no están cargadas en la "
         "hoja 'firmadas'."),
    ]
    for k, (num, desc, hoja, df, critico, quehacer) in enumerate(filas_resumen, start=1):
        r = cab + k
        for j, v in enumerate([num, desc, None, None, hoja, quehacer], start=1):
            c = resumen.cell(row=r, column=j, value=v)
            c.font = Font(name=FUENTE, size=10)
            c.border = BORDE
            c.alignment = Alignment(vertical="top", wrap_text=j in (2, 6),
                                    horizontal="center" if j in (1, 3, 4) else "left")
        # el conteo sale de la propia solapa: si se edita el detalle, el resumen acompaña
        resumen.cell(row=r, column=3).value = (
            f"=COUNTA('{hoja}'!$A${FILA_CAB + 1}:$A$5000)")
        if critico is None:
            txt, fill = "INFO", AZUL
        elif df is None or df.empty:
            txt, fill = "OK", VERDE
        else:
            txt, fill = ("ACCIÓN", ROJO) if critico else ("REVISAR", AMAR)
        c = resumen.cell(row=r, column=4, value=txt)
        c.fill = fill
        c.font = Font(name=FUENTE, size=10, bold=True)
        c.alignment = Alignment(horizontal="center", vertical="center")
        c.border = BORDE

    nota = resumen.cell(row=cab + len(filas_resumen) + 2, column=1,
                        value="La columna 'Casos' cuenta las filas de cada solapa con una fórmula, "
                              "así que si se edita el detalle el resumen acompaña.")
    nota.font = Font(name=FUENTE, size=9, italic=True, color="595959")
    for j, w in enumerate([5, 52, 9, 11, 30, 75], start=1):
        resumen.column_dimensions[get_column_letter(j)].width = w

    # ---------------- Metodologia ---------------- #
    met = wb.create_sheet("Metodologia")
    met.sheet_view.showGridLines = False
    texto = [
        ("Metodología del cotejo", True),
        ("", False),
        ("Fuentes", True),
        ("firm.xlsx, hoja 'firmadas': es el único insumo del buscador. generar_pagina.py lo lee y escribe "
         "index.html, así que lo que no está en este Excel no está publicado.", False),
        ("Res_firmadas.xlsm, hoja 'firmadas': resoluciones firmadas, con decisión, nº de resolución y dictamen.", False),
        ("Res_firmadas.xlsm, hoja 'evol_conc': seguimiento por expediente, con la columna ESTADO.", False),
        ("Los dos archivos se abren en solo lectura: este informe es lo único que el script escribe.", False),
        ("", False),
        ("Clave de cotejo", True),
        ("Se usa nomenclador_mercados.parse_carpeta(), la misma función con la que el buscador arma los "
         "enlaces a PDF. Normaliza 'CONC. 2124 (PROSUM)', 'CONC-2124' y 'CONC 2124' a la misma clave "
         "'CONC 2124'.", False),
        ("Control cruzado por número de resolución/dictamen (en mayúsculas, sin espacios ni puntos): si la "
         "clave figura en el buscador pero ninguna fila con esa clave tiene la resolución registrada en "
         "Res_firmadas, el expediente se cuenta como faltante y se explica en la columna Observación.", False),
        ("", False),
        ("Alcance", True),
        ("Solo CONC. Se incluyen los incidentes 'INC. I. CONC. NNNN' porque son incidentes de una "
         "concentración y figuran en los dos archivos. OPI y DP quedan fuera (el Resumen informa cuántas "
         "filas se excluyeron de cada hoja).", False),
        ("El reclamo a Res_firmadas se limita a expedientes firmados desde el "
         f"{CORTE.strftime('%d/%m/%Y')}; lo anterior va al anexo informativo 2b.", False),
        ("", False),
        ("Limitaciones conocidas", True),
        ("parse_carpeta toma el primer número de 3 o 4 dígitos de la carpeta. Si en la columna Carpeta se "
         "cargó un año (por ejemplo 'CONC-2024' para una resolución de 2024), la clave queda mal; el "
         "control por número de resolución es el que lo detecta.", False),
        ("Los incidentes de una misma CONC comparten clave (todos los 'INC. I. CONC. 1663' son 'INC 1663'), "
         "por eso las comparaciones de fecha y resolución se hacen entre conjuntos de valores y no fila "
         "contra fila.", False),
        ("evol_conc no cubre todos los expedientes de la hoja 'firmadas'; esas filas se informan en la "
         "solapa 6 pero no afectan al buscador.", False),
    ]
    for i, (t, bold) in enumerate(texto, start=1):
        c = met.cell(row=i, column=1, value=t)
        c.font = Font(name=FUENTE, size=11 if bold else 10, bold=bold,
                      color="1F3864" if bold else "000000")
        c.alignment = Alignment(wrap_text=True, vertical="top")
    met.column_dimensions["A"].width = 120

    wb.save(SALIDA)


# --------------------------------------------------------------------------- #
def main():
    bus, fir, evo = cargar()
    hojas, ctx = cotejar(bus, fir, evo)
    escribir(hojas, ctx)

    revisar = int((hojas["h3"]["¿Esperable?"] == "REVISAR").sum()) if len(hojas["h3"]) else 0
    print(f"Buscador: {ctx['filas_bus']} filas CONC ({ctx['claves_bus']} carpetas)")
    print(f"Res_firmadas: {ctx['filas_fir']} filas en 'firmadas' / {ctx['filas_evol']} en 'evol_conc'")
    print()
    print(f"1)  Firmadas que faltan en el buscador ......... {len(hojas['h1'])}")
    print(f"2)  En el buscador sin registro (>= {CORTE.year}) ..... {len(hojas['h2'])}")
    print(f"2b) Anexo informativo pre-2024 ................. {len(hojas['h2b'])}")
    print(f"3)  Publicadas pero 'en proceso' ............... {len(hojas['h3'])} (a revisar: {revisar})")
    print(f"4)  En proceso y correctamente ausentes ........ {len(hojas['h4'])}")
    print(f"5)  Discrepancias de datos ..................... {len(hojas['h5'])}")
    print(f"6)  Datos incompletos en Res_firmadas .......... {len(hojas['h6'])}")
    print()
    print(f"Informe: {SALIDA}")


if __name__ == "__main__":
    main()
