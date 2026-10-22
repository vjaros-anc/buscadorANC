# -*- coding: utf-8 -*-
"""
Etapa 1 de la biblioteca de remedios UE: arma remedios_ue/casos.csv con las
concentraciones que la Comision Europea autorizo CON CONDICIONES entre DESDE y
HASTA (fecha de adopcion de la decision condicionada, ambas inclusive).

Criterio de inclusion (ver README.md, punto 1.1):
  - Reglamento 139/2004, decision de la Comision.
  - Fase I : art. 6(1)(b) en relacion con el 6(2)  ("Art. 6(1)(b) with conditions & obligations")
  - Fase II: art. 8(2) con condiciones              ("Art. 8(2) with conditions & obligations")

Fuentes que cruza:
  A) Datos abiertos de DG COMP: case-data-M.json (data.europa.eu, se actualiza a
     diario). Es la fuente principal: trae tipo y fecha de cada decision.
  C) Comunicados de prensa (API publica de Presscorner) cuyo titulo dice
     "subject to conditions" o similar. Es una lista independiente para control.
  (B, el buscador de casos, usa la misma base que A y su API no es accesible
   desde todas las redes; no se usa.)

Que hace, en orden:
  1. Baja case-data-M.json a datos_crudos/ y guarda fecha y sha256 de la copia.
  2. Filtra la lista A y arma la lista C.
  3. Cruza A y C por numero de caso e informa los que estan en una sola lista.
  4. Actualiza casos.csv completando SOLO celdas vacias: nunca pisa lo que se
     cargo a mano (tipo_remedio_preliminar, notas, correcciones de partes...).
     Si un dato automatico no coincide con lo cargado, lo informa como
     DISCREPANCIA y no lo toca.
  5. Imprime el conteo por anio y fase (para conciliar con las estadisticas
     oficiales) y corre los chequeos de consistencia.
  6. Arma el anexo revisiones_remedios.csv: casos autorizados con condiciones
     ANTES de DESDE que tuvieron, dentro del periodo, decisiones que revisan,
     modifican o aplican sus remedios. Misma regla: solo completa celdas vacias.

Uso:
    python inventario_casos.py                 # descarga todo y actualiza casos.csv
    python inventario_casos.py --sin-descarga  # reusa datos_crudos/ (no baja nada)

Solo usa la biblioteca estandar de Python.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import html
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from collections import Counter
from datetime import date, datetime, timedelta
from pathlib import Path

AQUI = Path(__file__).parent
CRUDOS = AQUI / "datos_crudos"
CASOS_CSV = AQUI / "casos.csv"
REVISIONES_CSV = AQUI / "revisiones_remedios.csv"

DESDE = "2021-10-22"
HASTA = "2026-10-22"

URL_JSON = "https://compcases-open-data-portal-files-prod.s3.eu-west-1.amazonaws.com/case-data-M.json"
URL_PRESS = "https://ec.europa.eu/commission/presscorner/api/"
URL_CASO = "https://competition-cases.ec.europa.eu/cases/{}"
URL_COMUNICADO = "https://ec.europa.eu/commission/presscorner/detail/en/{}"

# tipo de decision (etiqueta del JSON) -> (fase, base legal)
TIPOS_INCLUIDOS = {
    "Art. 6(1)(b) with conditions & obligations": ("I", "6(1)(b)+6(2)"),
    "Art. 8(2) with conditions & obligations": ("II", "8(2)"),
}

# decisiones posteriores a la autorizacion que interesan para el remedio
EVENTOS_POSTERIORES = {
    "Purchaser approval": "aprobación de comprador",
    "Decision on the implementation of remedies": "decisión sobre implementación de remedios",
    "Decision under remedy review clause": "decisión por cláusula de revisión",
    "Modification of Art. 6(1)(b) with conditions & obligations": "modificación de compromisos",
    "Modification of Art. 8(2) with conditions & obligations": "modificación de compromisos",
    "Art. 8(4)": "medidas art. 8(4)",
    "Art. 8(4)(b)": "medidas art. 8(4)(b)",
    "Art. 8(5)(c)": "medidas provisionales art. 8(5)(c)",
    "Art. 8(6)": "revocación art. 8(6)",
    "Art. 14": "multa art. 14",
}

# decisiones que revisan o aplican remedios: definen el anexo de revisiones
REVISION_REMEDIOS = {
    "Decision on the implementation of remedies",
    "Decision under remedy review clause",
    "Modification of Art. 6(1)(b) with conditions & obligations",
    "Modification of Art. 8(2) with conditions & obligations",
}

# hechos del procedimiento previos a la decision que conviene anotar
ANTECEDENTES = {
    "Art. 22 Full referral": "llegó por remisión del art. 22",
    "Withdrawn": "notificación anterior retirada",
    "Aborted / withdrawn (N/2)": "notificación anterior retirada en fase II",
    "Art. 4(5) - Referral": "remisión previa del art. 4(5)",
    "Art. 4(4) - No referral": "art. 4(4): no se remitió",
    "Art. 9(3) refusal of referral": "art. 9(3): rechazo de remisión a Estado miembro",
    "Art. 9(3) partial referral": "art. 9(3): remisión parcial a Estado miembro",
}

# titulos de comunicados que se buscan para la lista C
TITULOS_PRENSA = [
    "subject to conditions",
    "conditionally",
    "with conditions",
    "subject to commitments",
    "conditional approval",
]

COLUMNAS = [
    "caso_id",
    "titulo",
    "adquirentes",
    "objetivos",
    "fecha_notificacion",
    "fecha_decision",
    "fase",
    "base_legal",
    "sector_nace",
    "tipo_remedio_preliminar",
    "eventos_posteriores",
    "url_caso",
    "url_comunicado",
    "fuentes_identificacion",
    "notas",
]
# columnas que calcula el script: si difieren de lo cargado, se avisa
AUTOMATICAS = {
    "titulo", "fecha_notificacion", "fecha_decision", "fase", "base_legal",
    "sector_nace", "eventos_posteriores", "url_caso", "url_comunicado",
    "fuentes_identificacion",
}
OBLIGATORIAS = ["caso_id", "titulo", "fecha_decision", "fase", "base_legal", "url_caso"]

COLUMNAS_REVISIONES = [
    "caso_id",
    "titulo",
    "fecha_autorizacion_original",
    "base_legal_original",
    "decisiones_en_periodo",
    "url_caso",
    "notas",
]
AUTOMATICAS_REVISIONES = set(COLUMNAS_REVISIONES) - {"caso_id", "notas"}


# ---------------------------------------------------------------- descarga --

def bajar(url: str, intentos: int = 4, timeout: int = 120) -> bytes:
    """GET con reintentos (2, 4, 8 s)."""
    for i in range(intentos):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "remedios-ue/1.0"})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read()
        except Exception as e:  # noqa: BLE001 - se reintenta cualquier error de red
            if i == intentos - 1:
                raise
            print(f"  reintento {i + 1} ({e})")
            time.sleep(2 ** (i + 1))
    raise RuntimeError("inalcanzable")


def descargar_json() -> Path:
    CRUDOS.mkdir(exist_ok=True)
    destino = CRUDOS / "case-data-M.json"
    print(f"Bajando {URL_JSON} ...")
    datos = bajar(URL_JSON, timeout=300)
    destino.write_bytes(datos)
    meta = {
        "url": URL_JSON,
        "descargado": datetime.now().isoformat(timespec="seconds"),
        "bytes": len(datos),
        "sha256": hashlib.sha256(datos).hexdigest(),
    }
    (CRUDOS / "case-data-M.meta.json").write_text(json.dumps(meta, indent=1), encoding="utf-8")
    print(f"  {len(datos):,} bytes  sha256={meta['sha256'][:16]}...")
    return destino


def prensa(ruta: str, **params) -> dict:
    return json.loads(bajar(URL_PRESS + ruta + "?" + urllib.parse.urlencode(params), timeout=60))


# ----------------------------------------------------------------- lista A --

def _etiquetas(valores: list[str]) -> list[str]:
    return [json.loads(v)["label"] for v in valores or []]


def _primero(valores: list[str] | None) -> str:
    return (valores or [""])[0]


def _items(valores: list[str] | None) -> list[dict]:
    out = []
    for v in valores or []:
        out += [it for it in json.loads(v).get("items", []) if it]
    return out


def partes_desde_titulo(titulo: str) -> tuple[str, str]:
    """Convencion de la Comision: 'ADQUIRENTE / OBJETIVO'. Se corrige a mano
    en casos.csv cuando no aplica (empresas en participacion, control conjunto)."""
    trozos = [t.strip() for t in titulo.split(" / ") if t.strip()]
    if len(trozos) < 2:
        return titulo.strip(), ""
    return trozos[0], "; ".join(trozos[1:])


def ref_a_url(ref: str) -> str:
    return URL_COMUNICADO.format(ref.lower().replace("/", "_"))


def decisiones_de(caso: dict) -> list[tuple[str, str, dict]]:
    """(fecha de adopcion, etiqueta del tipo, decision completa) de cada decision del caso."""
    out = []
    for dec in caso.get("decisions", []):
        m = dec["metadata"]
        out.append((_primero(m.get("decisionAdoptionDate")), _primero(_etiquetas(m.get("decisionTypes"))), dec))
    return out


def lista_a(datos: dict) -> dict[str, dict]:
    casos = {}
    for caso_id, caso in datos.items():
        md = caso["metadata"]
        decisiones = [(f, t, dec["metadata"]) for f, t, dec in decisiones_de(caso)]
        condicionadas = [d for d in decisiones if d[1] in TIPOS_INCLUIDOS and DESDE <= d[0] <= HASTA]
        if not condicionadas:
            continue
        if len(condicionadas) > 1:
            print(f"  AVISO {caso_id}: {len(condicionadas)} decisiones condicionadas en el período; se toma la primera")
        fecha, tipo, m = sorted(condicionadas, key=lambda d: d[0])[0]
        fase, base = TIPOS_INCLUIDOS[tipo]

        posteriores = sorted(
            f"{EVENTOS_POSTERIORES[t]} ({f})" for f, t, _ in decisiones
            if t in EVENTOS_POSTERIORES and f >= fecha
        )
        for tribunal in md.get("caseCourtCases") or []:
            posteriores.append(f"causa judicial: {tribunal}")
        antecedentes = sorted(
            f"{ANTECEDENTES[t]} ({f})" for f, t, _ in decisiones
            if t in ANTECEDENTES and f <= fecha
        )
        comunicados = [it["reference"] for it in _items(m.get("decisionPressReleases")) if it.get("reference")]
        titulo = _primero(md.get("caseTitle")).strip()
        adq, obj = partes_desde_titulo(titulo)
        casos[caso_id] = {
            "caso_id": caso_id,
            "titulo": titulo,
            "adquirentes": adq,
            "objetivos": obj,
            "fecha_notificacion": _primero(md.get("caseNotificationDate")),
            "fecha_decision": fecha,
            "fase": fase,
            "base_legal": base,
            "sector_nace": "; ".join(_etiquetas(md.get("caseSectors"))),
            "eventos_posteriores": "; ".join(posteriores),
            "url_caso": URL_CASO.format(caso_id),
            "url_comunicado": ref_a_url(comunicados[0]) if comunicados else "",
            "notas": "; ".join(antecedentes),
        }
    return casos


def lista_revisiones(datos: dict) -> dict[str, dict]:
    """Casos autorizados con condiciones antes de DESDE con decisiones de
    revision o aplicacion de remedios dentro del periodo (anexo)."""
    casos = {}
    for caso_id, caso in datos.items():
        decisiones = decisiones_de(caso)
        originales = sorted((f, t) for f, t, _ in decisiones if t in TIPOS_INCLUIDOS)
        en_periodo = sorted((f, t) for f, t, _ in decisiones
                            if t in REVISION_REMEDIOS and DESDE <= f <= HASTA)
        if not originales or not en_periodo or originales[-1][0] >= DESDE:
            continue
        fecha, tipo = originales[-1]
        casos[caso_id] = {
            "caso_id": caso_id,
            "titulo": _primero(caso["metadata"].get("caseTitle")).strip(),
            "fecha_autorizacion_original": fecha,
            "base_legal_original": TIPOS_INCLUIDOS[tipo][1],
            "decisiones_en_periodo": "; ".join(f"{EVENTOS_POSTERIORES[t]} ({f})" for f, t in en_periodo),
            "url_caso": URL_CASO.format(caso_id),
        }
    return casos


def conteo_por_anio(datos: dict, desde: int = 2019) -> Counter:
    """Decisiones condicionadas por (anio, fase) en todo el JSON, para conciliar."""
    c = Counter()
    for caso in datos.values():
        for dec in caso.get("decisions", []):
            m = dec["metadata"]
            tipo = _primero(_etiquetas(m.get("decisionTypes")))
            fecha = _primero(m.get("decisionAdoptionDate"))
            if tipo in TIPOS_INCLUIDOS and fecha[:4].isdigit() and int(fecha[:4]) >= desde:
                c[(fecha[:4], TIPOS_INCLUIDOS[tipo][0])] += 1
    return c


# ----------------------------------------------------------------- lista C --

def lista_c(descargar: bool) -> dict[str, dict]:
    cache = CRUDOS / "comunicados.json"
    if not descargar and cache.exists():
        return json.loads(cache.read_text(encoding="utf-8"))

    print("Buscando comunicados de prensa ...")
    vistos = {}
    for titulo in TITULOS_PRENSA:
        pagina = 1
        while True:
            r = prensa("search", title=titulo, pagesize=100, pagenumber=pagina, language="en")
            items = r.get("docuLanguageListResources", [])
            for it in items:
                vistos[it["refCode"]] = it
            if not items or pagina * 100 >= r.get("totalNumber", 0):
                break
            pagina += 1

    # margen de una semana: el comunicado puede salir dias despues de la decision
    hasta = (date.fromisoformat(HASTA) + timedelta(days=7)).isoformat()
    candidatos = [it for it in vistos.values()
                  if it["docutype"]["code"] == "IP" and DESDE <= it["eventDate"] <= hasta
                  and "unconditional" not in it["title"].lower()]

    casos = {}
    for it in sorted(candidatos, key=lambda x: x["eventDate"]):
        doc = prensa("documents", reference=it["refCode"], language="en")
        cuerpo = (doc.get("docuLanguageResource") or {}).get("htmlContent") or ""
        texto = html.unescape(re.sub(r"<[^>]+>", " ", cuerpo))
        numeros = list(dict.fromkeys(n.replace(" ", "") for n in re.findall(r"M\.\s?\d{4,5}", texto)))
        if not numeros:
            print(f"  sin número de caso (otro régimen, p. ej. FSR): {it['refCode']} {it['title'][:70]}")
            continue
        if len(numeros) > 1:
            print(f"  AVISO {it['refCode']} menciona varios casos {numeros}; se toma {numeros[0]}")
        casos.setdefault(numeros[0], {"ref": it["refCode"], "fecha": it["eventDate"], "titulo": it["title"]})
        time.sleep(0.2)

    CRUDOS.mkdir(exist_ok=True)
    cache.write_text(json.dumps(casos, ensure_ascii=False, indent=1), encoding="utf-8")
    return casos


# ------------------------------------------------------------- casos.csv --

def leer_csv(ruta: Path) -> dict[str, dict]:
    if not ruta.exists():
        return {}
    with ruta.open(encoding="utf-8-sig", newline="") as f:
        return {r["caso_id"]: r for r in csv.DictReader(f)}


def escribir_csv(ruta: Path, filas: list[dict], columnas: list[str] = COLUMNAS) -> None:
    with ruta.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=columnas, extrasaction="ignore")
        w.writeheader()
        for fila in filas:
            w.writerow({c: fila.get(c, "") for c in columnas})


def mergear(existentes: dict[str, dict], nuevos: dict[str, dict], columnas: list[str] = COLUMNAS,
            automaticas: set[str] = AUTOMATICAS, orden=lambda f: (f.get("fecha_decision", ""), f["caso_id"]),
            archivo: str = "casos.csv") -> tuple[list[dict], list[str]]:
    """Completa solo celdas vacias. Devuelve filas y discrepancias."""
    discrepancias = []
    filas = {}
    for k, nuevo in nuevos.items():
        fila = dict(existentes.get(k, {}))
        for col in columnas:
            cargado = (fila.get(col) or "").strip()
            calculado = (nuevo.get(col) or "").strip()
            if not cargado:
                fila[col] = calculado
            elif col in automaticas and calculado and cargado != calculado:
                discrepancias.append(f"{k} {col}: cargado={cargado!r} / fuente={calculado!r}")
        filas[k] = fila
    for k, fila in existentes.items():
        if k not in filas:
            discrepancias.append(f"{k}: está en {archivo} pero ya no surge de las fuentes (se conserva)")
            filas[k] = fila
    return sorted(filas.values(), key=orden), discrepancias


def chequear(filas: list[dict]) -> list[str]:
    problemas = []
    ids = Counter(f["caso_id"] for f in filas)
    problemas += [f"caso duplicado: {k}" for k, n in ids.items() if n > 1]
    bases = {b for _, b in TIPOS_INCLUIDOS.values()}
    for f in filas:
        if not DESDE <= f.get("fecha_decision", "") <= HASTA:
            problemas.append(f"{f['caso_id']}: fecha_decision fuera del período ({f.get('fecha_decision')})")
        if f.get("base_legal") not in bases:
            problemas.append(f"{f['caso_id']}: base_legal no permitida ({f.get('base_legal')})")
        for col in OBLIGATORIAS:
            if not (f.get(col) or "").strip():
                problemas.append(f"{f['caso_id']}: falta {col}")
    return problemas


# ------------------------------------------------------------------ main --

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--sin-descarga", action="store_true", help="reusar datos_crudos/ sin bajar nada")
    args = ap.parse_args()

    ruta_json = CRUDOS / "case-data-M.json"
    if not args.sin_descarga or not ruta_json.exists():
        ruta_json = descargar_json()
    datos = json.loads(ruta_json.read_text(encoding="utf-8"))
    print(f"JSON: {len(datos):,} casos de concentraciones")

    a = lista_a(datos)
    c = lista_c(descargar=not args.sin_descarga)
    print(f"\nLista A (JSON DG COMP): {len(a)} casos | Lista C (comunicados): {len(c)} casos")

    solo_a = sorted(set(a) - set(c))
    solo_c = sorted(set(c) - set(a))
    if solo_a:
        print("  Solo en A (revisar a mano):", ", ".join(solo_a))
    if solo_c:
        print("  Solo en C (revisar a mano; no se agregan):")
        for k in solo_c:
            print(f"    {k} {c[k]['fecha']} {c[k]['ref']} {c[k]['titulo'][:80]}")

    for caso_id, fila in a.items():
        fila["fuentes_identificacion"] = "A;C" if caso_id in c else "A"
        if caso_id in c:
            fila["url_comunicado"] = ref_a_url(c[caso_id]["ref"])

    filas, discrepancias = mergear(leer_csv(CASOS_CSV), a)
    escribir_csv(CASOS_CSV, filas)
    print(f"\nEscrito {CASOS_CSV.name}: {len(filas)} casos")

    if discrepancias:
        print("\nDISCREPANCIAS (no se pisó nada; resolver a mano):")
        for d in discrepancias:
            print("  " + d)

    conteo = conteo_por_anio(datos)
    print("\nDecisiones condicionadas por año calendario (todo el JSON, para conciliar):")
    print("  año   fase I  fase II  total")
    for anio in sorted({k[0] for k in conteo}):
        i, ii = conteo[(anio, "I")], conteo[(anio, "II")]
        print(f"  {anio}  {i:6d}  {ii:7d}  {i + ii:5d}")

    en_periodo = Counter((f["fecha_decision"][:4], f["fase"]) for f in filas)
    print("\nEn el período", DESDE, "a", HASTA, "por año:",
          ", ".join(f"{y}: {en_periodo[(y, 'I')]}+{en_periodo[(y, 'II')]}"
                    for y in sorted({k[0] for k in en_periodo})), "(fase I + fase II)")

    revisiones, disc_rev = mergear(
        leer_csv(REVISIONES_CSV), lista_revisiones(datos), COLUMNAS_REVISIONES, AUTOMATICAS_REVISIONES,
        orden=lambda f: (f.get("fecha_autorizacion_original", ""), f["caso_id"]), archivo=REVISIONES_CSV.name)
    escribir_csv(REVISIONES_CSV, revisiones, COLUMNAS_REVISIONES)
    print(f"\nAnexo {REVISIONES_CSV.name}: {len(revisiones)} casos anteriores con revisiones de remedios en el período")
    for d in disc_rev:
        print("  DISCREPANCIA " + d)

    problemas = chequear(filas)
    print("\nChequeos:", "OK" if not problemas else f"{len(problemas)} problemas")
    for p in problemas:
        print("  " + p)
    return 1 if problemas else 0


if __name__ == "__main__":
    sys.exit(main())
