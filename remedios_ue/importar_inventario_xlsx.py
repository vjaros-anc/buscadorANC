# -*- coding: utf-8 -*-
"""
Incorpora a la biblioteca el inventario de la ANC en Excel
("ANC – Concentraciones UE con compromisos – Inventario 2021–2026"):

  1. Control del universo: compara caso, fecha de autorizacion y fase de la
     hoja 'Casos' con casos.csv e informa las diferencias.
  2. casos.csv: completa la columna resena_remedio con la 'Resena orientativa
     del remedio' del Excel (solo celdas vacias).
  3. documentos.csv: agrega como filas MANUALES los documentos de la hoja
     'Documentos' que todavia no figuran para ese caso: Merger Briefs,
     sentencias y autos, avisos del Diario Oficial con su enlace preciso y actos
     que el JSON de DG COMP no trae. No importa fuentes secundarias, fichas de
     buscadores ni copias de documentos que ya figuran (la version EUR-Lex de
     una decision que el JSON ya trae, el mismo comunicado en otro idioma o
     sitio). Verifica cada enlace nuevo (EUR-Lex y curia no se pueden
     verificar automaticamente).
  4. Compara la ubicacion de los compromisos que informa el Excel con las
     paginas que ubico relevar_documentos.py, para revisar a mano.

relevar_documentos.py reconoce estas filas como manuales (fuente "Inventario
ANC ...") y no las toca. Correrlo dos veces no duplica filas.

El Excel es un insumo interno: no se versiona.

Uso:
    python importar_inventario_xlsx.py <inventario.xlsx>
    python importar_inventario_xlsx.py <inventario.xlsx> --sin-verificar

Dependencias: pip install openpyxl
"""
from __future__ import annotations

import argparse
import re
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path
from urllib.parse import urlparse

import openpyxl

import inventario_casos as inv
import relevar_documentos as rd

# 'Tipo documental' del Excel -> tipo_doc de documentos.csv
TIPOS_XLSX = {
    "Decisión completa": "DEC",
    "Compromisos finales": "COMP",
    "Compromisos integrados": "COMP",
    "Compromisos — versión pública provisional": "COMP",
    "Compromisos finales de pasajeros": "COMP",
    "Compromisos finales de carga": "COMP",
    "Compromisos": "COMP",
    "Comunicado": "CP",
    "Republicación de comunicado": "CP",
    "Página del comunicado": "CP",
    "Comunicado de aprobación de comprador": "CP",
    "Comunicado de representación de la Comisión": "CP",
    "Noticia oficial": "CP",
    "Apertura de fase II": "RES_DO",  # en el Excel son avisos del Diario Oficial, no comunicados
    "Publicación del Diario Oficial": "RES_DO",
    "Resumen oficial de decisión": "RES_DO",
    "Aviso de no oposición del Diario Oficial": "RES_DO",
    "Ficha bibliográfica de decisión": "RES_DO",
    "Aprobación de comprador": "POST",
    "Decisión de implementación": "POST",
    "Dispensa": "POST",
    "Prórroga": "POST",
    "Otra decisión procesal": "OTRO",
    "Anuncio de notificación": "NOT_PREVIA",
    "Descripción de notificación": "NOT_PREVIA",
    "Retirada de notificación previa": "NOT_PREVIA",
    "Dictamen del comité consultivo": "DICT",
    "Informe del consejero auditor": "DICT",
    "Artículo de Merger Brief": "MB",
    "Sentencia relacionada": "SENT",
    "Auto judicial procesal": "SENT",
    "Ficha de recurso judicial": "SENT",
    "Anuncio de recurso judicial": "SENT",
    "Información del supervisor": "OTRO",
}
# fuentes secundarias, fichas de buscadores y rastros de busqueda: no son documentos del caso
NO_IMPORTAR = {
    "Informe anual",
    "Ficha del registro", "Cronología oficial de control", "Pista secundaria sobre publicación",
    "Listado oficial de noticias", "Decisión reproducida por fuente secundaria",
    "Compromisos reproducidos por fuente secundaria", "Intento de acceso a ficha de decisión",
    "Estado ante otra autoridad", "Expediente relacionado", "Cita secundaria de decisión original",
    "Referencia a actos relacionados", "Comunicado de autoridad remitente",
}
# tipos que el JSON ya trae completos: lo del Excel suele ser la copia en EUR-Lex
COPIAS = {"DEC", "NOT_PREVIA", "DICT"}
# hosts que bloquean la verificacion automatica
NO_VERIFICABLES = {"eur-lex.europa.eu", "curia.europa.eu", "publications.europa.eu", "webgate.ec.europa.eu"}


def hoja(wb, nombre: str) -> list[dict]:
    filas = list(wb[nombre].iter_rows(values_only=True))
    encabezado = filas[0]
    return [dict(zip(encabezado, f)) for f in filas[1:] if any(v not in (None, "") for v in f)]


def texto(v) -> str:
    return "" if v is None else str(v).strip()


def normalizar(url: str) -> str:
    return url.strip().lower().replace("http://", "https://").rstrip("/")


def ref_comunicado(url: str) -> str:
    m = re.search(r"/(ip|mex|statement|speech)[_-](\d{2})[_-](\d+)", url.lower())
    return f"{m.group(1).upper()}/{m.group(2)}/{m.group(3)}" if m else ""


def es_copia(tipo: str, caso: str, url: str, documentos: dict[str, dict]) -> bool:
    """Otra copia de un documento que ya figura: la version EUR-Lex de una
    decision, aviso o dictamen que el JSON ya trae, o el mismo comunicado en
    PDF, en otro idioma o en el sitio de una representacion de la Comision."""
    del_caso = [f for f in documentos.values() if f["caso_id"] == caso]
    if tipo in COPIAS:
        return any(f["tipo_doc"] == tipo and f.get("estado") == "localizado_verificado" for f in del_caso)
    if tipo == "CP":
        ref = ref_comunicado(url)
        return not ref or any(f.get("ref") == ref for f in del_caso)
    return False


def verificar(url: str) -> tuple[dict, str]:
    """Medida de verificacion y nota, segun el sitio."""
    host = urlparse(url).netloc.lower()
    if host in NO_VERIFICABLES:
        return {}, f"{host} no se puede verificar automáticamente."
    if "presscorner" in url and ref_comunicado(url):
        return rd.verificar_comunicado(ref_comunicado(url)), ""
    return rd.verificar_enlace(url), ""


def controlar_universo(casos_xlsx: list[dict], casos: dict[str, dict]) -> list[str]:
    avisos = []
    xl = {texto(c["Caso"]): c for c in casos_xlsx}
    for k in sorted(set(xl) - set(casos)):
        avisos.append(f"{k}: está en el Excel pero no en casos.csv")
    for k in sorted(set(casos) - set(xl)):
        avisos.append(f"{k}: está en casos.csv pero no en el Excel")
    for k in sorted(set(xl) & set(casos)):
        fecha, fase = texto(xl[k]["Autorización"])[:10], texto(xl[k]["Fase"])
        if fecha != casos[k]["fecha_decision"] or fase != casos[k]["fase"]:
            avisos.append(f"{k}: Excel {fecha} fase {fase} / casos.csv {casos[k]['fecha_decision']} fase {casos[k]['fase']}")
    return avisos


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("xlsx", type=Path)
    ap.add_argument("--sin-verificar", action="store_true", help="no consultar la red")
    args = ap.parse_args()

    wb = openpyxl.load_workbook(args.xlsx, data_only=True, read_only=True)
    casos_xlsx, docs_xlsx = hoja(wb, "Casos"), hoja(wb, "Documentos")
    casos = inv.leer_csv(inv.CASOS_CSV)
    revisiones = inv.leer_csv(inv.REVISIONES_CSV)
    documentos = inv.leer_csv(rd.DOCUMENTOS_CSV, clave="doc_id")
    if not documentos:
        print("Falta documentos.csv: corré antes relevar_documentos.py")
        return 1

    # 1. control del universo
    avisos = controlar_universo(casos_xlsx, casos)
    print(f"Universo: {len(casos_xlsx)} casos en el Excel, {len(casos)} en casos.csv —",
          "coinciden caso, fecha y fase" if not avisos else f"{len(avisos)} diferencias")
    for a in avisos:
        print("  " + a)

    # 2. resena del remedio
    completadas = 0
    for c in casos_xlsx:
        k, resena = texto(c["Caso"]), texto(c.get("Reseña orientativa del remedio"))
        if k in casos and resena and not casos[k].get("resena_remedio"):
            casos[k]["resena_remedio"] = resena
            completadas += 1
    filas_casos = sorted(casos.values(), key=lambda f: (f["fecha_decision"], f["caso_id"]))
    inv.escribir_csv(inv.CASOS_CSV, filas_casos, inv.COLUMNAS)
    print(f"casos.csv: {completadas} reseñas de remedio completadas")

    # 3. documentos que faltan
    presentes = {(f["caso_id"], normalizar(f["url"])) for f in documentos.values() if f.get("url")}
    usados = Counter(re.sub(r"\d+$", "", k) for k in documentos if re.search(r"_M\d+$", k))
    importados, salteados = Counter(), Counter()
    for d in docs_xlsx:
        caso, url, tipo_xlsx = texto(d["Caso"]), texto(d["URL del documento"]), texto(d["Tipo documental"])
        if tipo_xlsx in NO_IMPORTAR or tipo_xlsx not in TIPOS_XLSX:
            salteados["fuente secundaria o rastro de búsqueda"] += 1
            continue
        if not url.startswith("http"):
            salteados["sin URL"] += 1
            continue
        if caso not in casos and caso not in revisiones:
            salteados["caso fuera del universo"] += 1
            continue
        if (caso, normalizar(url)) in presentes:
            salteados["ya figura"] += 1
            continue
        tipo = TIPOS_XLSX[tipo_xlsx]
        if es_copia(tipo, caso, url, documentos):
            salteados["copia de un documento que ya figura"] += 1
            continue
        prefijo = f"{caso}_{tipo}_M"
        usados[prefijo] += 1
        notas = "; ".join(x for x in (
            f"{tipo_xlsx} según el Excel",
            f"localización: {texto(d.get('Páginas / localización'))}" if texto(d.get("Páginas / localización")) else "",
            texto(d.get("Notas")),
        ) if x)
        fila = {
            "doc_id": f"{prefijo}{usados[prefijo]:02d}", "caso_id": caso,
            "universo": "principal" if caso in casos else "revisiones",
            "tipo_doc": tipo, "prioridad": rd.PRIORIDAD[tipo], "titulo": texto(d["Título"]),
            "fecha_doc": texto(d.get("Fecha registrada"))[:10], "idioma": texto(d.get("Idioma")),
            "url": url, "fuente": f"Inventario ANC (xlsx) {texto(d['Documento ID'])}",
            "ref": ref_comunicado(url) if tipo == "CP" else "",
        }
        medida, nota = ({}, "") if args.sin_verificar else verificar(url)
        fila.update(medida)
        ok = rd.respuesta_valida(url, medida.get("http_status", ""), medida.get("tipo_contenido", ""))
        fila["estado"] = "localizado_verificado" if ok else "localizado_no_verificado"
        fila["notas"] = "; ".join(x for x in (notas, nota) if x)
        documentos[fila["doc_id"]] = fila
        presentes.add((caso, normalizar(url)))
        importados[tipo] += 1
        time.sleep(0.1)
    inv.escribir_csv(rd.DOCUMENTOS_CSV, sorted(documentos.values(), key=lambda f: f["doc_id"]), rd.COLUMNAS)
    print(f"documentos.csv: {sum(importados.values())} filas manuales nuevas —",
          ", ".join(f"{t}: {n}" for t, n in sorted(importados.items())) or "ninguna")
    print("  no importadas:", ", ".join(f"{m}: {n}" for m, n in salteados.items()))

    # 4. ubicacion de compromisos: Excel vs paginas ubicadas
    comp = defaultdict(list)
    for f in documentos.values():
        if f["tipo_doc"] == "COMP" and f.get("paginas_compromisos"):
            comp[(f["caso_id"], normalizar(f["url"]))].append(f["paginas_compromisos"])
    comparar = [(texto(d["Caso"]), texto(d.get("Páginas / localización")), comp.get((texto(d["Caso"]), normalizar(texto(d["URL del documento"])))))
                for d in docs_xlsx if texto(d["Tipo documental"]) == "Compromisos integrados"]
    if comparar:
        print("\nUbicación de compromisos integrados (Excel / relevar_documentos.py), para revisar a mano:")
        for caso, loc_xlsx, loc in comparar:
            print(f"  {caso}: {loc_xlsx or '—'}  /  {', '.join(loc) if loc else 'sin páginas ubicadas'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
