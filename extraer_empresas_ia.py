#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
extraer_empresas_ia.py — completa y sanea la columna "Empresas involucradas"
de firm.xlsx leyendo los PDF con la API de Claude.

Por que existe
--------------
`extraer_firmadas3.py` lee la TABLA "Actividades de las empresas afectadas" con
regex sobre coordenadas. Cuando el PDF no la trae o la tabla no cae donde el
parser espera, deja la celda vacia (353 expedientes CONC) o mete parrafos y
fragmentos como razon social (10 expedientes). Y cuando la lee, apila varias
sociedades en un mismo item ("LUZ DEL CERRO S.A. LUZ DEL LEON S.A. LUZ DEL RIO
S.A. LUZ DEL VALLE S.A." en una sola celda: 88 expedientes).

El objetivo es tener el GRUPO ECONOMICO COMPLETO, que es lo que sirve para
buscar. De donde sale, por orden de preferencia:

  1. La TABLA de empresas afectadas, cuando esta en la capa de texto (177 de los
     428 del lote). Lista el grupo entero agrupado por "Grupo Comprador" /
     "Objeto". En CONC-1713 son 38 sociedades del grupo YPF; el parser viejo
     habia sacado 30, con 5 items apilados y un "COMPAÑIA DE desarrollo NO
     CONVENCIONAL" roto por el OCR.
  2. La PROSA, cuando no hay tabla legible (251 de 428): el CONSIDERANDO de la
     Resolucion o la seccion "I. DESCRIPCION DE LA OPERACION" del informe.
     Ahi solo estan las partes de la operacion, no el grupo, pero es lo unico
     que hay. Ejemplo (CONC-418, p.27):

        "...la adquisicion por parte de la firma GRUPO BIMBO S.A. DE C.V., de
         manera indirecta, del control de la firma COMPANIA DE ALIMENTOS
         FARGO S.A."

Cuatro hallazgos que explican el diseno
---------------------------------------
1. Un PDF escaneado SI tiene capa de texto: ~43 caracteres por pagina, que son
   el sello GEDO (IF-2017-..., "Pagina 3 de 30"). Medido por caracteres totales,
   CONC-418 parece tener 14.881 caracteres "de texto" y es una imagen. El
   criterio correcto es caracteres POR PAGINA (>250 = pagina real).
2. La mitad del lote son PDF mixtos: el dictamen viejo esta escaneado pero la
   Resolucion adjunta es digital, y su CONSIDERANDO narra la operacion entera.
   Descartar el PDF completo por "escaneado" perderia 170 expedientes.
3. Hay que unir las variantes de un mismo expediente: CONC-1090.pdf tiene 0
   texto, pero CONC-1090_2..5.pdf tienen 52k caracteres entre todos.
4. La ventana de recorte TIENE que incluir la tabla. Recortando solo el
   CONSIDERANDO, CONC-1713 devolvia 2 empresas en vez de 38: la prosa nombra a
   YPF y a la concesion, el grupo economico esta solo en la tabla.

Etapas (las tres corren por defecto)
------------------------------------
  0. clasificar()  — decide que celda ya cargada esta defectuosa. Deterministico.
  1. segmentar()   — saca la ventana de texto relevante de cada PDF. Sin costo.
  2. extraer()     — llama a la API. Reanudable.
  3. volcar()      — escribe firm.xlsx, con respaldo previo.

Uso
---
    python extraer_empresas_ia.py --solo-extraer     # etapas 0+1, no gasta nada
    python extraer_empresas_ia.py --limite 15        # calibracion
    python extraer_empresas_ia.py --solo 418,697,1299
    python extraer_empresas_ia.py                    # todo
    python extraer_empresas_ia.py --solo-volcar --dry-run

Dependencias: pip install pymupdf openpyxl anthropic
"""
from __future__ import annotations

import argparse
import datetime as dt
import glob
import json
import os
import re
import shutil
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import fitz
import openpyxl

sys.path.insert(0, str(Path(__file__).parent))
import nomenclador_mercados as nm

AQUI = Path(__file__).parent
FIRM = AQUI / "firm.xlsx"
HOJA = "firmadas"
COL_EMPRESAS = "Empresas involucradas"
COL_CARPETA = "Carpeta"

SEGMENTADO = AQUI / "empresas_ia_segmentado.jsonl"
EXTRAIDO = AQUI / "empresas_ia.jsonl"
REPORTE = AQUI / "empresas_ia_reporte.txt"
RESPALDOS = AQUI / "respaldos"

CARPETAS_PDF = ("pdf", "nuevas")

MODELO = "claude-sonnet-5"
EFFORT = "low"
MAX_TOKENS = 8000                           # una tabla de 30 sociedades necesita aire
REINTENTOS = 3
PRECIO_IN, PRECIO_OUT = 2.0, 10.0          # US$ por millon de tokens (Sonnet 5)

MIN_CHARS_PAGINA = 250                      # debajo de esto la pagina es el sello GEDO
TOPE_CONSIDERANDO = 14000
TOPE_DESCRIPCION = 10000
TOPE_SIN_ANCLA = 12000


def _p(*args) -> None:
    """print tolerante con consolas sin UTF-8 (cp850/cp437)."""
    txt = " ".join(str(a) for a in args)
    try:
        print(txt)
    except UnicodeEncodeError:
        enc = sys.stdout.encoding or "ascii"
        print(txt.encode(enc, "replace").decode(enc))


# --------------------------------------------------------------------------- #
# Etapa 0 — clasificador de celdas ya cargadas
# --------------------------------------------------------------------------- #
# OJO con la tentacion de marcar por largo o por "tiene muchas minusculas": el
# objeto de una concentracion puede ser un ACTIVO y no una sociedad, y esas
# descripciones estan cargadas a mano y son largas y en prosa a proposito
# ("Marca, permisos, formulas y licencias del aperitivo Hesperidina", "Inmueble
# en Otto Krause 4211: 162.663,14 m2 de terreno"). Marcarlas como defecto y
# pisarlas destruye trabajo manual. Por eso solo se marca lo que es
# inequivocamente un recorte mal hecho: un fragmento de prosa que quedo colgado.
LEGALTOK = re.compile(
    r"\b(S\.?A\.?[A-Z.]{0,6}|S\.?R\.?L|S\.?A\.?S|LLC|LTDA?|INC|CORP(ORATION)?|"
    r"GMBH|B\.?V|N\.?V|PLC|LIMITED|LIMITADA|S\.?P\.?A|SASU|AG|KG)\b\.?", re.I)

# restos de OCR vistos en el corpus: "Actillidad", "inwrsion", "senales", "SAtabletas"
RX_OCR = re.compile(r"inwrs|Actillidad|senales|[a-z]{3}[A-Z]{3}")

# "Inmueble", "Planta", "Activos", "Empresas", "Participacion": sustantivo comun
# en Title case al inicio = descripcion de un activo, no una razon social.
RX_DESCRIPTIVO = re.compile(r"^[A-ZÁÉÍÓÚÑ][a-záéíóúñ]{2,}\b")


def clasificar(nombre: str) -> str | None:
    """None si el nombre esta bien; 'grave' o 'leve' si no."""
    n = (nombre or "").strip()
    if RX_OCR.search(n):
        return "grave"
    if len(n) < 4:                                            # "YPF", "SAB", "S.A"
        return "grave"
    palabras = n.split()
    # empieza en minuscula = recorte colgado ("distribuye televisores en..."),
    # salvo que sea un nombre corto que termina en forma societaria, porque hay
    # razones sociales reales asi ("gA Ventures Accelerator S.A.").
    if re.match(r"^[a-záéíóúñ]", n) and not (
            len(palabras) <= 4 and LEGALTOK.search(palabras[-1])):
        return "grave"
    legales = list(LEGALTOK.finditer(n))
    # razon social + prosa pegada detras ("SONY ARGENTINA S.A .. tabletas,
    # televisores y equipos de television"). No aplica a las descripciones de
    # activos, que empiezan con sustantivo comun.
    if legales and not RX_DESCRIPTIVO.match(n):
        cola = re.sub(r"\([^)]*\)", "", n[legales[-1].end():])
        if len(re.findall(r"\b[a-záéíóúñ]{3,}\b", cola)) >= 4:
            return "grave"
    if len(n) > 70 and len(legales) >= 2:                     # varias empresas en un item
        return "leve"
    return None


def motivo_celda(valor) -> str | None:
    """'vacio' | 'grave' | 'leve' | None (la celda esta bien, no entra al lote)."""
    s = "" if valor is None else str(valor).strip()
    if not s or s in ("[]", "null", "None", "nan"):
        return "vacio"
    try:
        arr = json.loads(s)
    except Exception:
        return "grave"                                        # JSON roto
    if not isinstance(arr, list) or not arr:
        return "vacio"
    defectos = {clasificar(e.get("nombre") or "") for e in arr}
    if "grave" in defectos:
        return "grave"
    if "leve" in defectos:
        return "leve"
    if any((e.get("rol") or "") not in ("comprador", "objeto", "vendedor") for e in arr):
        return "leve"                                         # rol null o desconocido
    return None


# --------------------------------------------------------------------------- #
# Etapa 1 — texto de los PDF (deterministico, sin costo)
# --------------------------------------------------------------------------- #
# Ruido GEDO. Base: RX_RUIDO de pdf/lectura_opi/01_segmentar.py, mas DI-... y
# "DN: cn=..." que aparecen en este corpus (disposiciones y firmas digitales) y
# en el de OPI no.
RX_RUIDO = re.compile(
    r"(IF-\d{4}-\d+-APN-\S+"
    r"|RESOL-\d{4}-\d+-APN-\S+"
    r"|DI-\d{4}-\d+-APN-\S+"
    r"|RESFC-\d{4}-\d+-APN-\S+"
    r"|P[áa]gina \d+ de \d+"
    r"|Rep[úu]blica Argentina - Poder Ejecutivo Nacional"
    r"|Digitally signed by.*"
    r"|DN: cn=.*"
    r"|Date: \d{4}\.\d.*"
    r"|Location: Ciudad.*"
    r"|GESTION DOCUMENTAL ELECTRONICA.*"
    r"|\d{4} ?[–-] ?A[ÑN]O DE .*"
    r"|A[ÑN]O DE LA DEFENSA DE LA VIDA.*"
    r"|CIUDAD DE BUENOS AIRES)", re.I)

RX_CONSIDERANDO = re.compile(r"\bCONSIDERANDO\b", re.I)
RX_FIN_CONS = re.compile(r"\bPor ello,|\bEL\s+SECRETARIO|\bRESUELVE\b|\bDISPONE\b", re.I)
RX_DESCRIPCION = re.compile(
    r"(?:^|\n)\s*(?:I+\.|1\.)?\s*DESCRIPCI[ÓO]N DE LA OPERACI[ÓO]N.{0,60}", re.I)
RX_SIG_SECCION = re.compile(r"(?:^|\n)\s*(?:II+\.|2\.)\s*[A-ZÁÉÍÓÚ]", re.M)

# La tabla "Actividades de las Empresas Afectadas" lista el GRUPO ECONOMICO
# entero (en CONC-1713 son 29 sociedades del grupo YPF), agrupado por rotulos
# "Grupo Comprador" / "Objeto" / "Grupo Vendedor". La prosa del CONSIDERANDO
# solo nombra a las partes de la operacion. Cuando la tabla esta en la capa de
# texto hay que mandarla SI O SI: es la unica fuente del grupo completo, y es lo
# que el buscador quiere poder encontrar.
RX_TABLA = re.compile(
    r"(?:Tabla\s+N[º°o]?\s*\d+\s*:?\s*)?Actividades?\s+de\s+las\s+Empresas\s+Afectadas"
    r"|empresas\s+afectadas\s+y\s+las\s+actividades"
    r"|Actividad(?:es)?\s+Econ[óo]mica"
    r"|Grupo\s+Comprador", re.I)
RX_FIN_TABLA = re.compile(
    r"\n\s*Fuente\s*:|\n\s*[IVX]{2,}\.\s*[-–]?\s*[A-ZÁÉÍÓÚ]{4,}|\bCONCLUSI[ÓO]N", re.I)
TOPE_TABLA = 16000


def clave(carpeta) -> tuple[str, str]:
    tipo, numero, _ = nm.parse_carpeta(str(carpeta or ""))
    return (tipo, numero)


def indexar_pdfs() -> dict[tuple[str, str], list[str]]:
    """{(tipo, numero): [rutas]}. Une TODAS las variantes del expediente."""
    idx: dict[tuple[str, str], set[str]] = {}
    for carpeta in CARPETAS_PDF:
        for patron in ("*.pdf", "*.PDF"):
            for p in glob.glob(str(AQUI / carpeta / patron)):
                # en Windows *.pdf y *.PDF devuelven el mismo archivo dos veces
                idx.setdefault(clave(os.path.basename(p)), set()).add(
                    os.path.abspath(p).lower())
    return {k: sorted(v) for k, v in idx.items() if k[1]}


def texto_util(rutas: list[str]) -> str:
    """Texto de las paginas reales (>250 caracteres), de todas las variantes."""
    trozos = []
    for ruta in rutas:
        try:
            doc = fitz.open(ruta)
        except Exception as e:
            _p(f"    [warn] no se pudo abrir {os.path.basename(ruta)}: {e}")
            continue
        for i in range(doc.page_count):
            t = doc[i].get_text("text")
            if len(t.strip()) > MIN_CHARS_PAGINA:
                trozos.append(t)
        doc.close()
    if not trozos:
        return ""
    t = RX_RUIDO.sub("", "\n".join(trozos))
    t = re.sub(r"[ \t]+", " ", t)
    return re.sub(r"\n{3,}", "\n\n", t).strip()


def ventana(util: str) -> tuple[str, str]:
    """(texto, fuente). fuente = 'tabla' si el recorte incluye la tabla de
    empresas afectadas (grupo economico completo), 'prosa' si no."""
    partes = []
    m = RX_CONSIDERANDO.search(util)
    if m:
        fin = RX_FIN_CONS.search(util, m.end())
        corte = fin.start() if fin else m.start() + TOPE_CONSIDERANDO
        partes.append(util[m.start():corte][:TOPE_CONSIDERANDO])
    d = RX_DESCRIPCION.search(util)
    if d:
        sig = RX_SIG_SECCION.search(util, d.end() + 200)
        corte = sig.start() if sig else d.end() + TOPE_DESCRIPCION
        partes.append(util[d.start():corte][:TOPE_DESCRIPCION])

    t = RX_TABLA.search(util)
    fuente = "prosa"
    if t:
        ini = max(0, t.start() - 300)                # el rotulo suele venir arriba
        fin_t = RX_FIN_TABLA.search(util, t.end())
        corte = fin_t.start() if fin_t else t.start() + TOPE_TABLA
        trozo = util[ini:corte][:TOPE_TABLA]
        # si el CONSIDERANDO ya se la llevo entera, no la repetimos
        if not any(trozo[:400] in p for p in partes):
            partes.append("TABLA DE EMPRESAS AFECTADAS:\n" + trozo)
        fuente = "tabla"

    if not partes:
        return util[:TOPE_SIN_ANCLA], fuente
    return "\n\n[...]\n\n".join(partes), fuente


def cabecera_columnas(ws) -> dict[str, int]:
    return {str(ws.cell(row=1, column=c).value).strip(): c
            for c in range(1, ws.max_column + 1)
            if ws.cell(row=1, column=c).value is not None}


def segmentar(args) -> int:
    wb = openpyxl.load_workbook(FIRM, data_only=True)
    ws = wb[HOJA] if HOJA in wb.sheetnames else wb.worksheets[0]
    cols = cabecera_columnas(ws)
    c_carp, c_emp = cols[COL_CARPETA], cols[COL_EMPRESAS]
    n_filas = ws.max_row - 1

    # {(tipo,numero): {"filas": [[fila, motivo], ...], "carpeta": str, "viejo": str}}
    lote: dict[tuple[str, str], dict] = {}
    for r in range(2, ws.max_row + 1):
        carpeta = ws.cell(row=r, column=c_carp).value
        if not carpeta:
            continue
        k = clave(carpeta)
        if k[0] != "CONC" or not k[1]:
            continue
        val = ws.cell(row=r, column=c_emp).value
        mot = motivo_celda(val)
        if mot is None:
            continue
        d = lote.setdefault(k, {"filas": [], "carpeta": str(carpeta), "viejo": None})
        d["filas"].append([r, mot])
        if mot != "vacio" and d["viejo"] is None:
            d["viejo"] = str(val)
    wb.close()

    pdfs = indexar_pdfs()
    _p(f"Excel    : {FIRM.name}  ({n_filas} filas)")
    _p(f"PDFs     : {len(pdfs)} expedientes indexados en {', '.join(c + '/' for c in CARPETAS_PDF)}")
    _p(f"Lote     : {len(lote)} expedientes CONC a procesar")

    orden = ("vacio", "grave", "leve")
    conteo = {m: 0 for m in orden}
    for d in lote.values():
        conteo[min((m for _, m in d["filas"]), key=orden.index)] += 1
    _p(f"           por vacio: {conteo['vacio']} | por defecto grave: {conteo['grave']}"
       f" | por defecto leve: {conteo['leve']}")

    filtro = {s.strip() for s in args.solo.split(",")} if args.solo else None
    ok = imagen = sin_pdf = 0
    conteo_fuente = {"tabla": 0, "prosa": 0}
    registros = []
    for k in sorted(lote, key=lambda x: int(x[1])):
        if filtro and k[1] not in filtro:
            continue
        d = lote[k]
        rutas = pdfs.get(k)
        base = {"expediente": f"{k[0]}-{k[1]}", "tipo": k[0], "numero": k[1],
                "carpeta": d["carpeta"], "filas": d["filas"],
                "motivos": sorted({m for _, m in d["filas"]}), "viejo": d["viejo"]}
        if not rutas:
            sin_pdf += 1
            registros.append({**base, "motivo_salteo": "sin_pdf"})
            continue
        util = texto_util(rutas)
        if not util:
            imagen += 1
            registros.append({**base, "motivo_salteo": "imagen",
                              "pdfs": [os.path.basename(p) for p in rutas]})
            continue
        ok += 1
        txt, fuente = ventana(util)
        conteo_fuente[fuente] += 1
        registros.append({**base,
                          "pdfs": [os.path.basename(p) for p in rutas],
                          "chars_utiles": len(util),
                          "fuente": fuente,
                          "ventana": txt})

    with open(SEGMENTADO, "w", encoding="utf-8") as fh:
        for reg in registros:
            fh.write(json.dumps(reg, ensure_ascii=False) + "\n")

    chars = sum(len(r.get("ventana", "")) for r in registros)
    _p("")
    _p(f"OK -> {SEGMENTADO.name}")
    _p(f"  con texto util : {ok}")
    _p(f"     con tabla del grupo economico : {conteo_fuente['tabla']}")
    _p(f"     solo prosa (partes nomas)     : {conteo_fuente['prosa']}")
    _p(f"  imagen pura    : {imagen}  (se saltean, necesitan OCR)")
    _p(f"  sin PDF        : {sin_pdf}")
    _p(f"  ~{chars:,} caracteres de ventana -> ~{int(chars / 3.3):,} tokens de entrada"
       f"  (~US$ {chars / 3.3 / 1e6 * PRECIO_IN:.2f} de input)")
    return ok


# --------------------------------------------------------------------------- #
# Etapa 2 — extraccion con la API
# --------------------------------------------------------------------------- #
SYSTEM = """Sos un analista de la Comision Nacional de Defensa de la Competencia (Argentina).
Te paso el texto de un dictamen o resolucion de una operacion de concentracion
economica (CONC) y extraes las EMPRESAS INVOLUCRADAS.

LO MAS IMPORTANTE: si el documento trae la TABLA DE EMPRESAS AFECTADAS
("Actividades de las Empresas Afectadas", "Actividad Economica", con rotulos de
seccion tipo "Grupo Comprador", "Objeto", "Grupo Vendedor"), esa tabla es la
fuente principal y tenes que listar TODAS Y CADA UNA de las sociedades que
figuran ahi, no solamente las que aparecen en la frase de la operacion. El
objetivo es el GRUPO ECONOMICO COMPLETO. Si la tabla lista 29 sociedades del
grupo comprador, devolves las 29. El rol sale del rotulo de la seccion en que
cae cada fila: "Grupo Comprador"/"Grupo Adquirente" -> comprador;
"Objeto"/"Empresa Objeto"/"Grupo Objeto" -> objeto; "Grupo Vendedor" -> se OMITE.
Si el documento NO trae esa tabla, recien ahi sacas las partes de la frase que
describe la operacion.

Reglas:
1. Solo usas lo que dice el texto. Nunca inferis desde tu conocimiento general
   del mercado ni completas con lo que sabes de esas empresas.
2. Dos roles, y solo dos:
   - `comprador`: quien adquiere el control o la participacion. Incluis la
     controlante ultima del grupo comprador si el texto la nombra, y los
     vehiculos intermedios que ADQUIEREN.
   - `objeto`: la empresa, activo o participacion ADQUIRIDA, junto con sus
     subsidiarias argentinas afectadas y los vehiculos intermedios que SON
     adquiridos.
3. NO listas vendedoras. Si el texto dice "adquirio de la firma X" o "X es la
   vendedora", X NO va en la lista. Este punto es importante: el error mas
   comun es meter a la vendedora como objeto.
4. Las personas fisicas cuentan como parte: las listas con su nombre completo
   tal como figura en el texto, con el rol que les corresponda.
5. UN ITEM POR EMPRESA. Nunca pongas dos razones sociales en un mismo `nombre`.
   En la tabla, una celda puede traer varias sociedades apiladas en renglones
   sucesivos: "LUZ DEL CERRO S.A. / LUZ DEL LEON S.A. / LUZ DEL RIO S.A. /
   LUZ DEL VALLE S.A." son CUATRO items, no uno.
6. Razon social completa y textual (S.A., S.A. DE C.V., S.R.L., LLC, LIMITED,
   LTDA.), sin abreviar, sin traducir y sin normalizar. NUNCA pegues al nombre
   la actividad de la empresa, la descripcion del mercado ni porcentajes.
   El campo `nombre` es solo el nombre. La columna "Actividad Economica" de la
   tabla NO se copia: sirve para saber donde termina el nombre, nada mas.
   Ojo con los nombres partidos en dos renglones por el ancho de la celda
   ("YPF" + "SERVICIOS PETROLEROS S.A." es UNA empresa:
   "YPF SERVICIOS PETROLEROS S.A.").
7. Si el objeto es un activo y no una sociedad (una marca, un inmueble, una
   concesion, una linea de negocio), lo describis en pocas palabras con
   rol `objeto`. Eso es valido y esperado.
8. No incluyas organismos (CNDC, Ministerio, Secretaria, Poder Ejecutivo) ni
   nombres de mercados o de marcas ajenas a la operacion.
9. Si del texto no surge ninguna parte identificable, devolves `empresas` vacio
   y `confianza` en "baja". Es preferible vacio a inventado.
10. En `fuente` poner "tabla" si sacaste las empresas de la tabla de empresas
    afectadas, o "prosa" si las sacaste del relato de la operacion.
11. En `cita` copias el fragmento textual (maximo 300 caracteres) del que
    sacaste la operacion. Es la trazabilidad para revisar a mano."""

PLANTILLA = """<documento expediente="{expediente}" caratula="{caratula}">
{texto}
</documento>

Extrae las empresas involucradas en la operacion de concentracion economica."""

ESQUEMA = {
    "type": "object",
    "properties": {
        "empresas": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "rol": {"type": "string", "enum": ["comprador", "objeto"]},
                    "nombre": {"type": "string"},
                },
                "required": ["rol", "nombre"],
                "additionalProperties": False,
            },
        },
        "fuente": {"type": "string", "enum": ["tabla", "prosa"]},
        "confianza": {"type": "string", "enum": ["alta", "media", "baja"]},
        "cita": {"type": "string"},
    },
    "required": ["empresas", "fuente", "confianza", "cita"],
    "additionalProperties": False,
}

_lock = threading.Lock()


def api_key() -> str:
    """Variable de entorno primero; si no esta, la clave guardada en lectura_opi."""
    k = os.environ.get("ANTHROPIC_API_KEY")
    if k:
        return k
    guardada = AQUI / "pdf" / "lectura_opi" / "api_key.txt"
    if guardada.exists():
        m = re.search(r"sk-ant-[A-Za-z0-9_\-]+",
                      guardada.read_text(encoding="utf-8", errors="replace"))
        if m:
            return m.group(0)
    sys.exit('Falta la clave de API. Pone  $env:ANTHROPIC_API_KEY="sk-ant-..."  '
             "o dejala en pdf/lectura_opi/api_key.txt")


def _extraer_una(cli, reg, args):
    msg = cli.messages.create(
        model=args.modelo,
        max_tokens=MAX_TOKENS,
        system=SYSTEM,
        thinking={"type": "adaptive"},
        output_config={"effort": args.effort,
                       "format": {"type": "json_schema", "schema": ESQUEMA}},
        messages=[{"role": "user", "content": PLANTILLA.format(
            expediente=reg["expediente"],
            caratula=(reg.get("carpeta") or "")[:120],
            texto=reg["ventana"],
        )}],
    )
    # output_config.format garantiza que el bloque de texto es JSON valido
    txt = "".join(b.text for b in msg.content if getattr(b, "type", None) == "text")
    if not txt:
        raise ValueError("respuesta sin bloque de texto")
    out = json.loads(txt)
    out["_expediente"] = reg["expediente"]
    out["_fuente_ventana"] = reg.get("fuente")
    out["_motivos"] = reg["motivos"]
    out["_filas"] = reg["filas"]
    out["_viejo"] = reg.get("viejo")
    out["_tokens"] = (msg.usage.input_tokens, msg.usage.output_tokens)
    return out


def extraer(args) -> int:
    try:
        import anthropic
    except ImportError:
        sys.exit("Falta la libreria: pip install anthropic")
    if not SEGMENTADO.exists():
        sys.exit(f"No existe {SEGMENTADO.name}. Corre primero --solo-extraer.")

    regs = [json.loads(l) for l in open(SEGMENTADO, encoding="utf-8")]
    regs = [r for r in regs if r.get("ventana")]
    if args.solo:
        pedidos = {s.strip() for s in args.solo.split(",")}
        regs = [r for r in regs if r["numero"] in pedidos]

    hechos = set()
    if EXTRAIDO.exists() and not args.rehacer:
        for l in open(EXTRAIDO, encoding="utf-8"):
            try:
                hechos.add(json.loads(l)["_expediente"])
            except Exception:
                pass
        antes = len(regs)
        regs = [r for r in regs if r["expediente"] not in hechos]
        if hechos:
            _p(f"Reanudando: {antes - len(regs)} ya extraidos, faltan {len(regs)}.")
    if args.limite:
        regs = regs[:args.limite]
    if not regs:
        _p("Nada para extraer.")
        return 0

    cli = anthropic.Anthropic(api_key=api_key())
    fh = open(EXTRAIDO, "a" if hechos and not args.rehacer else "w", encoding="utf-8")
    ok = err = tin = tout = 0

    def tarea(reg):
        nonlocal ok, err, tin, tout
        ultimo = None
        for intento in range(REINTENTOS):
            try:
                r = _extraer_una(cli, reg, args)
                break
            except Exception as e:
                ultimo = e
                time.sleep(1.5 * (intento + 1))
        else:
            with _lock:
                err += 1
                _p(f"  ERROR {reg['expediente']}: {type(ultimo).__name__}: {ultimo}")
            return
        with _lock:
            ok += 1
            tin += r["_tokens"][0]
            tout += r["_tokens"][1]
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
            fh.flush()
            nombres = ", ".join(e["nombre"] for e in r["empresas"][:3])
            _p(f"  [{ok + err}/{len(regs)}] {r['_expediente']:<10} "
               f"{len(r['empresas'])} emp - {r['confianza']:<5} - {nombres[:70]}")

    _p(f"Extrayendo {len(regs)} expedientes con {args.modelo} "
       f"(effort={args.effort}, {args.hilos} hilos)...")
    with ThreadPoolExecutor(max_workers=args.hilos) as ex:
        list(ex.map(tarea, regs))
    fh.close()

    costo = tin / 1e6 * PRECIO_IN + tout / 1e6 * PRECIO_OUT
    _p(f"\nListo: {ok} ok, {err} errores -> {EXTRAIDO.name}")
    _p(f"Tokens: {tin:,} in / {tout:,} out  (~US$ {costo:.2f})")
    return ok


# --------------------------------------------------------------------------- #
# Etapa 3 — volcado a firm.xlsx
# --------------------------------------------------------------------------- #
def volcar(args) -> None:
    if not EXTRAIDO.exists():
        sys.exit(f"No existe {EXTRAIDO.name}. Corre primero la extraccion.")
    resultados = [json.loads(l) for l in open(EXTRAIDO, encoding="utf-8")]
    # si un expediente quedo repetido (reanudaciones), gana el ultimo
    por_exp = {r["_expediente"]: r for r in resultados}

    if not args.dry_run:
        RESPALDOS.mkdir(exist_ok=True)
        copia = RESPALDOS / f"{FIRM.stem}_{dt.datetime.now():%Y%m%d-%H%M%S}{FIRM.suffix}"
        shutil.copy2(FIRM, copia)
        _p(f"Respaldo -> {copia}")

    wb = openpyxl.load_workbook(FIRM)
    ws = wb[HOJA] if HOJA in wb.sheetnames else wb.worksheets[0]
    c_emp = cabecera_columnas(ws)[COL_EMPRESAS]

    def n_items(valor) -> int:
        try:
            return len(json.loads(str(valor)))
        except Exception:
            return 0

    completadas, pisadas, vacias, saltadas, bajas, retenidas = [], [], [], [], [], []
    for exp, r in sorted(por_exp.items(), key=lambda kv: int(kv[0].split("-")[1])):
        empresas = [{"rol": e["rol"], "nombre": e["nombre"]} for e in r["empresas"]]
        if r.get("confianza") == "baja":
            bajas.append(exp)
        if not empresas:
            # guarda 1: mejor el dato viejo, aunque este sucio, que ningun dato
            vacias.append(exp)
            continue
        nuevo = json.dumps(empresas, ensure_ascii=False)
        for fila, motivo in r["_filas"]:
            actual = ws.cell(row=fila, column=c_emp).value
            if motivo_celda(actual) == "vacio":        # guarda 2: celda vacia -> completar
                if not args.dry_run:
                    ws.cell(row=fila, column=c_emp).value = nuevo
                completadas.append(f"{exp} (fila {fila}): {len(empresas)} empresas")
            elif motivo in ("grave", "leve"):
                # guarda 3: no degradar. Si el PDF no tenia tabla legible, lo
                # nuevo sale de la prosa y trae solo las partes de la operacion,
                # no el grupo economico. Si ademas es mas corto que lo que ya
                # habia, pisarlo PIERDE empresas (el caso CONC-1713: 2 items
                # nuevos contra 30 viejos). En ese caso se conserva el viejo y
                # se marca para revision manual.
                if r.get("fuente") != "tabla" and len(empresas) < n_items(actual):
                    retenidas.append(f"{exp} (fila {fila}): {len(empresas)} nuevas "
                                     f"< {n_items(actual)} viejas y sin tabla -> se conserva")
                    continue
                if not args.dry_run:
                    ws.cell(row=fila, column=c_emp).value = nuevo
                pisadas.append(f"{exp} (fila {fila}, {motivo}, fuente={r.get('fuente')}) "
                               f"{n_items(actual)} -> {len(empresas)} empresas\n"
                               f"       viejo: {str(actual)[:150]}\n"
                               f"       nuevo: {nuevo[:150]}")
            else:
                saltadas.append(f"{exp} (fila {fila}): celda limpia, no se toca")

    if not args.dry_run:
        wb.save(FIRM)
    wb.close()

    lineas = [
        "DRY-RUN (no se escribio nada)" if args.dry_run else f"OK -> {FIRM.name}",
        f"  Celdas completadas (estaban vacias) : {len(completadas)}",
        f"  Celdas pisadas (estaban defectuosas): {len(pisadas)}",
        f"  Sin resultado (no se toco nada)     : {len(vacias)}",
        f"  Retenidas (lo nuevo era mas pobre)  : {len(retenidas)}",
        f"  Celdas limpias respetadas           : {len(saltadas)}",
        f"  Marcadas confianza=baja (revisar)   : {len(bajas)}",
        "",
        "--- COMPLETADAS ---", *(f"    + {x}" for x in completadas),
        "", "--- PISADAS (auditar viejo -> nuevo) ---", *(f"    ~ {x}" for x in pisadas),
        "", "--- RETENIDAS (revisar a mano) ---", *(f"    ! {x}" for x in retenidas),
        "", "--- SIN RESULTADO ---", f"    {', '.join(vacias) or '(ninguno)'}",
        "", "--- CONFIANZA BAJA ---", f"    {', '.join(bajas) or '(ninguno)'}",
    ]
    # expedientes que nunca llegaron a la API
    if SEGMENTADO.exists():
        salteados: dict[str, list[str]] = {}
        for l in open(SEGMENTADO, encoding="utf-8"):
            reg = json.loads(l)
            if reg.get("motivo_salteo"):
                salteados.setdefault(reg["motivo_salteo"], []).append(reg["expediente"])
        for mot, exps in sorted(salteados.items()):
            lineas += ["", f"--- SALTEADOS: {mot} ({len(exps)}) ---",
                       f"    {', '.join(exps)}"]

    REPORTE.write_text("\n".join(lineas), encoding="utf-8")
    for x in lineas[:6]:
        _p(x)
    _p(f"\nDetalle completo -> {REPORTE.name}")


# --------------------------------------------------------------------------- #
def main() -> None:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--solo-extraer", action="store_true",
                    help="solo etapas 0+1 (texto): no llama a la API, no gasta")
    ap.add_argument("--solo-api", action="store_true", help="solo etapa 2 (API)")
    ap.add_argument("--solo-volcar", action="store_true", help="solo etapa 3 (Excel)")
    ap.add_argument("--limite", type=int, help="procesar solo los primeros N")
    ap.add_argument("--solo", help="numeros de expediente separados por coma: 418,697")
    ap.add_argument("--hilos", type=int, default=4)
    ap.add_argument("--rehacer", action="store_true", help="ignorar lo ya extraido")
    ap.add_argument("--modelo", default=MODELO)
    ap.add_argument("--effort", default=EFFORT,
                    choices=["low", "medium", "high", "xhigh", "max"])
    ap.add_argument("--dry-run", action="store_true", help="el volcado no escribe")
    args = ap.parse_args()

    todo = not (args.solo_extraer or args.solo_api or args.solo_volcar)

    if todo or args.solo_extraer:
        _p("=== Etapa 0+1: clasificar y segmentar ===")
        segmentar(args)
    if todo or args.solo_api:
        _p("\n=== Etapa 2: extraccion con la API ===")
        extraer(args)
    if todo or args.solo_volcar:
        _p("\n=== Etapa 3: volcado a firm.xlsx ===")
        volcar(args)


if __name__ == "__main__":
    main()
