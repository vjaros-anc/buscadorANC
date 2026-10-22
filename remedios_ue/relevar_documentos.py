# -*- coding: utf-8 -*-
"""
Etapa 2 de la biblioteca de remedios UE: arma remedios_ue/documentos.csv con
los documentos de cada caso de casos.csv y del anexo revisiones_remedios.csv.

Documentos por caso (tipo_doc / prioridad), ver README.md:
  DEC          nucleo          decision condicionada, version publica (PDF del JSON)
  COMP         nucleo          compromisos: anexo dentro de la DEC (con paginas) o
                               version no confidencial publicada aparte
  CP           complementario  comunicado de la autorizacion (Presscorner)
  CP_APERTURA  complementario  comunicado de apertura de fase II
  RES_DO       complementario  resumen o aviso en el Diario Oficial (ref. del JSON)
  POST         complementario  decisiones posteriores (comprador, revision, ...)
  NOT_PREVIA   contexto        aviso de notificacion previa
  DICT         contexto        dictamen del Comite Consultivo / informe del Consejero Auditor
  OTRO         contexto        otros documentos publicados (p. ej. datos del trustee)
  MB, SENT     contexto        Merger Briefs y sentencias: se cargan a mano o con
                               importar_inventario_xlsx.py (filas manuales)

Que hace, en orden:
  1. Arma las filas automaticas desde el JSON de DG COMP (datos_crudos/) y los
     comunicados que guardo inventario_casos.py.
  2. Baja los PDF de las decisiones (DEC) a datos_crudos/pdf/ (no se versiona),
     cuenta paginas, calcula sha256 y ubica el anexo de compromisos.
  3. Verifica el resto de los enlaces (codigo HTTP, tipo de contenido, tamanio)
     sin guardarlos. Los resultados quedan en datos_crudos/ para no repetirlos.
  4. Actualiza documentos.csv completando SOLO celdas vacias: lo cargado a mano
     (filas MB y SENT, notas, correcciones) no se pisa. Si un dato automatico
     cambia, lo informa como DISCREPANCIA y no lo toca.
  5. Imprime la cobertura y corre los chequeos.

EUR-Lex bloquea las consultas automaticas, asi que los RES_DO quedan como
'localizado_no_verificado' con la URL armada desde la referencia del JSON.

Uso:
    python relevar_documentos.py                  # arma, baja las decisiones y verifica
    python relevar_documentos.py --sin-descarga   # no baja PDF (no ubica compromisos)
    python relevar_documentos.py --sin-verificar  # no consulta la red

Dependencias: pip install pymupdf
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

import inventario_casos as inv

try:
    import pymupdf
except ImportError:  # PyMuPDF < 1.24
    import fitz as pymupdf

DOCUMENTOS_CSV = inv.AQUI / "documentos.csv"
DIR_PDF = inv.CRUDOS / "pdf"
CACHE_PDF = inv.CRUDOS / "analisis_pdf.json"
CACHE_ENLACES = inv.CRUDOS / "verificaciones.json"

COLUMNAS = [
    "doc_id", "caso_id", "universo", "tipo_doc", "prioridad",
    "titulo", "fecha_doc", "idioma", "otros_idiomas", "version",
    "url", "fuente", "ref", "estado",
    "http_status", "tipo_contenido", "tamano_bytes", "verificado_el",
    "sha256", "paginas", "paginas_compromisos", "notas",
]
# lo que se recalcula en cada corrida: si cambia, se avisa (no se pisa)
AUTOMATICAS = {
    "caso_id", "universo", "tipo_doc", "prioridad", "titulo", "fecha_doc", "idioma",
    "otros_idiomas", "version", "url", "fuente", "ref", "estado",
}
MANUALES = {"MB", "SENT"}
# filas que no salen del JSON: se cargan a mano o con importar_inventario_xlsx.py
FUENTES_MANUALES = ("manual", "Inventario ANC")


def es_manual(f: dict) -> bool:
    return f.get("tipo_doc") in MANUALES or (f.get("fuente") or "").startswith(FUENTES_MANUALES)

PRIORIDAD = {
    "DEC": "núcleo", "COMP": "núcleo",
    "CP": "complementario", "CP_APERTURA": "complementario", "RES_DO": "complementario",
    "POST": "complementario",
    "NOT_PREVIA": "contexto", "DICT": "contexto", "OTRO": "contexto", "MB": "contexto", "SENT": "contexto",
}
ORDEN_TIPOS = list(PRIORIDAD)

CAT_DECISION = "Decision - web publication"
CAT_NOTIFICACION = "Description of the concentration"
CAT_COMITE = "Opinion of the Advisory Committee"
CAT_AUDITOR = "Final report of the Hearing Officer"
CAT_OTRO = "Other document for publication"

FUENTE_JSON = "JSON DG COMP"
FUENTE_PRENSA = "Presscorner"
FUENTE_DO = "EUR-Lex (ref. del JSON)"

# titulo del anexo de compromisos, en los idiomas en que se publican decisiones
ANEXO_COMPROMISOS = [
    r"COMMITMENTS\s+TO\s+THE\s+EUROPEAN\s+COMMISSION",
    r"ENGAGEMENTS\s+(?:À|A)\s+[Ll]\W{0,2}\s*(?:É|E)GARD\s+DE\s+LA\s+COMMISSION",
    r"VERPFLICHTUNGSZUSAGEN\s+GEGEN(?:Ü|UE)BER\s+DER\s+EUROP(?:Ä|AE)ISCHEN\s+KOMMISSION",
    r"COMPROMISOS\s+(?:ANTE|FRENTE\s+A|CON)\s+LA\s+COMISI(?:Ó|O)N\s+EUROPEA",
    r"IMPEGNI\s+(?:NEI\s+CONFRONTI\s+DELLA|ALLA|DINANZI\s+ALLA)\s+COMMISSIONE\s+EUROPEA",
]
ANEXO_MAYUS = [re.compile(p) for p in ANEXO_COMPROMISOS]
ANEXO_CUALQUIERA = [re.compile(p, re.IGNORECASE) for p in ANEXO_COMPROMISOS]

NOTA_NO_PUBLICADA = "La Comisión publica la versión pública meses después de la decisión."
NOTA_EURLEX = "EUR-Lex bloquea las consultas automáticas; URL armada con la referencia del JSON."


# ------------------------------------------------------------- JSON DG COMP --

def adjunto(a: dict) -> dict:
    m = a["metadata"]
    return {
        "cat": inv._primero(inv._etiquetas(m.get("attachmentCategory"))),
        "url": inv._primero(m.get("attachmentLink")),
        "idioma": inv._primero(m.get("attachmentLanguage")),
        "fecha": inv._primero(m.get("attachmentDocumentDate")),
        "desc": inv._primero(m.get("attachmentPublicationDescription")).strip(),
    }


def agrupar_idiomas(adjuntos: list[dict]) -> list[dict]:
    """Un documento publicado en varios idiomas queda en una sola fila: se
    prefiere el ingles y el resto va a otros_idiomas."""
    if len({a["idioma"] for a in adjuntos}) <= 1:
        return [dict(a, otros="") for a in adjuntos]
    principal = next((a for a in adjuntos if a["idioma"] == "EN"), adjuntos[0])
    otros = "; ".join(f"{a['idioma']} {a['url']}" for a in adjuntos if a is not principal)
    return [dict(principal, otros=otros)]


def referencias_do(m: dict) -> list[tuple[str, str, str]]:
    """(referencia legible, url, fecha) de cada publicacion en el Diario Oficial."""
    out = []
    for it in inv._items(m.get("decisionOfficialJournalPublications")):
        partes = [p for p in (it.get("reference") or "").split(":") if p]
        if len(partes) < 3:
            continue
        serie, anio, numero = partes[:3]
        publicado = it.get("publishedDate") or ""
        if publicado >= "2023-10-01":  # desde octubre de 2023 el DO C se publica acto por acto
            ref = f"DO {serie}/{anio}/{int(numero)}"
            url = f"https://eur-lex.europa.eu/eli/{serie}/{anio}/{int(numero)}/oj"
        else:
            ref = f"DO {serie} {numero} de {anio}"
            url = f"https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=OJ:{serie}:{anio}:{numero}:TOC"
        out.append((ref, url, publicado))
    return out


def comunicados_de(m: dict) -> list[str]:
    return [it["reference"].replace("_", "/") for it in inv._items(m.get("decisionPressReleases")) if it.get("reference")]


# ------------------------------------------------------------------ filas --

def fila(tipo: str, titulo: str, **kw) -> dict:
    return {"tipo_doc": tipo, "prioridad": PRIORIDAD[tipo], "titulo": titulo, **kw}


def filas_decision(dec: dict, base: str, titulo: str, publicada_aun: bool) -> list[dict]:
    """DEC y COMP (anexo) de una decision condicionada."""
    adjuntos = [adjunto(a) for a in dec.get("decisionAttachments", [])]
    adjuntos = agrupar_idiomas([a for a in adjuntos if a["cat"] == CAT_DECISION])
    if not adjuntos:
        estado, nota = ("no_publicado_aun", NOTA_NO_PUBLICADA) if publicada_aun else ("no_encontrado", "")
        return [fila("DEC", f"Decisión art. {base} — {titulo}", estado=estado, notas=nota, version="pública")]
    out = []
    for a in adjuntos:
        comun = dict(fecha_doc=a["fecha"], idioma=a["idioma"], otros_idiomas=a["otros"], url=a["url"], fuente=FUENTE_JSON)
        out.append(fila("DEC", f"Decisión art. {base} — {titulo}", version="pública", **comun))
        out.append(fila("COMP", f"Compromisos (anexo de la decisión) — {titulo}", version="anexo de la decisión", **comun))
    return out


def filas_adjuntos_caso(caso: dict, titulo: str, fase: str) -> list[dict]:
    """NOT_PREVIA, DICT, COMP aparte y OTRO, desde los adjuntos del caso."""
    adjuntos = [adjunto(a) for a in caso.get("caseAttachments", [])]
    out = []
    for a in adjuntos:
        comun = dict(fecha_doc=a["fecha"], idioma=a["idioma"], url=a["url"], fuente=FUENTE_JSON)
        if a["cat"] == CAT_NOTIFICACION:
            out.append(fila("NOT_PREVIA", f"Aviso de notificación previa — {titulo}", **comun))
        elif a["cat"] == CAT_COMITE:
            out.append(fila("DICT", f"Dictamen del Comité Consultivo — {titulo}", **comun))
        elif a["cat"] == CAT_AUDITOR:
            out.append(fila("DICT", f"Informe final del Consejero Auditor — {titulo}", **comun))
        elif a["cat"] == CAT_OTRO and "commitment" in a["desc"].lower():
            out.append(fila("COMP", f"Compromisos, versión no confidencial — {titulo}", version="no confidencial", **comun))
        elif a["cat"] == CAT_OTRO:
            out.append(fila("OTRO", f"{a['desc'] or 'Otro documento publicado'} — {titulo}", **comun))
    if fase == "II":
        for cat, nombre in ((CAT_COMITE, "Dictamen del Comité Consultivo"), (CAT_AUDITOR, "Informe final del Consejero Auditor")):
            if not any(a["cat"] == cat for a in adjuntos):
                out.append(fila("DICT", f"{nombre} — {titulo}", estado="no_encontrado"))
    else:
        out.append(fila("DICT", f"Dictamen del Comité Consultivo / informe del Consejero Auditor — {titulo}",
                        estado="no_aplica", notas="Solo existen en fase II."))
    return out


def filas_post(decisiones, desde: str, tipos: dict[str, str] | set[str], titulo: str, excluir: dict) -> list[dict]:
    out = []
    for f, t, dec in decisiones:
        if t not in tipos or f < desde or dec is excluir:
            continue
        nombre = inv.EVENTOS_POSTERIORES.get(t, t)
        adjuntos = agrupar_idiomas([a for a in map(adjunto, dec.get("decisionAttachments", []))])
        if not adjuntos:
            out.append(fila("POST", f"{nombre.capitalize()} — {titulo}", fecha_doc=f, estado="no_encontrado"))
        for a in adjuntos:
            out.append(fila("POST", f"{nombre.capitalize()} — {titulo}", fecha_doc=f, idioma=a["idioma"],
                            otros_idiomas=a["otros"], url=a["url"], fuente=FUENTE_JSON))
    return out


def filas_caso_principal(c: dict, caso: dict, comunicados: dict) -> list[dict]:
    titulo, fase = c["titulo"], c["fase"]
    decisiones = inv.decisiones_de(caso)
    cond = next(dec for f, t, dec in decisiones if f == c["fecha_decision"] and t in inv.TIPOS_INCLUIDOS)
    m = cond["metadata"]
    out = filas_decision(cond, c["base_legal"], titulo, publicada_aun=True)

    if not any(r["tipo_doc"] == "COMP" for r in out) and not any(
            a["cat"] == CAT_OTRO and "commitment" in a["desc"].lower()
            for a in map(adjunto, caso.get("caseAttachments", []))):
        out.append(fila("COMP", f"Compromisos — {titulo}", estado="no_publicado_aun",
                        notas="Se publican como anexo de la decisión."))

    cp = comunicados.get(c["caso_id"])
    if cp:
        out.append(fila("CP", cp["titulo"], fecha_doc=cp["fecha"], idioma="EN", url=inv.ref_a_url(cp["ref"]),
                        fuente=FUENTE_PRENSA, ref=cp["ref"]))
    else:
        out.append(fila("CP", f"Comunicado de la autorización — {titulo}", estado="no_encontrado"))

    if fase == "II":
        aperturas = [(f, dec) for f, t, dec in decisiones if t == "Art. 6(1)(c)"]
        refs = [(f, r) for f, dec in aperturas for r in comunicados_de(dec["metadata"])]
        for f, r in refs:
            out.append(fila("CP_APERTURA", f"Comunicado de apertura de fase II — {titulo}", fecha_doc=f, idioma="EN",
                            url=inv.ref_a_url(r), fuente=FUENTE_PRENSA, ref=r))
        if not refs:
            out.append(fila("CP_APERTURA", f"Comunicado de apertura de fase II — {titulo}", estado="no_encontrado"))

    refs_do = referencias_do(m)
    for ref, url, publicado in refs_do:
        out.append(fila("RES_DO", f"Diario Oficial: {ref} — {titulo}", fecha_doc=publicado, idioma="EN", url=url,
                        fuente=FUENTE_DO, ref=ref, notas=NOTA_EURLEX))
    if not refs_do:
        out.append(fila("RES_DO", f"Diario Oficial — {titulo}", estado="no_encontrado",
                        notas="El JSON no trae referencia al Diario Oficial."))

    out += filas_post(decisiones, c["fecha_decision"], inv.EVENTOS_POSTERIORES, titulo, excluir=cond)
    out += filas_adjuntos_caso(caso, titulo, fase)
    return out


def filas_revision(r: dict, caso: dict) -> list[dict]:
    titulo = r["titulo"]
    decisiones = inv.decisiones_de(caso)
    cond = next(dec for f, t, dec in decisiones
                if f == r["fecha_autorizacion_original"] and t in inv.TIPOS_INCLUIDOS)
    out = filas_decision(cond, r["base_legal_original"], titulo, publicada_aun=False)
    out += [x for x in filas_post(decisiones, inv.DESDE, inv.REVISION_REMEDIOS, titulo, excluir=cond)
            if x.get("fecha_doc", "") <= inv.HASTA]
    return out


def numerar(caso_id: str, universo: str, filas: list[dict]) -> list[dict]:
    """doc_id = <caso>_<tipo>_<nn>, en orden de fecha y URL (estable entre corridas)."""
    por_tipo = defaultdict(list)
    for f in filas:
        por_tipo[f["tipo_doc"]].append(f)
    out = []
    for tipo in ORDEN_TIPOS:
        grupo = sorted(por_tipo.get(tipo, []), key=lambda f: (f.get("fecha_doc", ""), f.get("url", ""), f["titulo"]))
        for i, f in enumerate(grupo, 1):
            out.append({**f, "doc_id": f"{caso_id}_{tipo}_{i:02d}", "caso_id": caso_id, "universo": universo})
    return out


# ------------------------------------------------- descarga y verificacion --

def leer_cache(ruta: Path) -> dict:
    return json.loads(ruta.read_text(encoding="utf-8")) if ruta.exists() else {}


def guardar_cache(ruta: Path, datos: dict) -> None:
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text(json.dumps(datos, ensure_ascii=False, indent=1, sort_keys=True), encoding="utf-8")


def pedir_cabeceras(url: str, intentos: int = 4, timeout: int = 60) -> tuple[str, str, str]:
    """GET con reintentos que solo lee las cabeceras: (status, content-type, content-length)."""
    for i in range(intentos):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "remedios-ue/1.0"})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return str(r.status), r.headers.get("Content-Type", ""), r.headers.get("Content-Length", "")
        except urllib.error.HTTPError as e:
            return str(e.code), e.headers.get("Content-Type", ""), ""
        except Exception as e:  # noqa: BLE001 - se reintenta cualquier error de red
            if i == intentos - 1:
                return "error", str(e)[:80], ""
            time.sleep(2 ** (i + 1))
    raise RuntimeError("inalcanzable")


def bajar_pdf(url: str) -> dict:
    destino = DIR_PDF / Path(urllib.parse.urlparse(url).path).name
    if not destino.exists():
        DIR_PDF.mkdir(parents=True, exist_ok=True)
        try:
            datos = inv.bajar(url, timeout=300)
        except Exception as e:  # noqa: BLE001 - el fallo queda registrado en la fila
            status = str(getattr(e, "code", "error"))
            return {"http_status": status, "tipo_contenido": "", "tamano_bytes": "",
                    "verificado_el": date.today().isoformat()}
        destino.write_bytes(datos)
    datos = destino.read_bytes()
    paginas, inicio = contar_y_ubicar(destino)
    return {
        "http_status": "200", "tipo_contenido": "application/pdf", "tamano_bytes": str(len(datos)),
        "verificado_el": date.today().isoformat(), "sha256": hashlib.sha256(datos).hexdigest(),
        "paginas": str(paginas), "inicio_compromisos": str(inicio or ""),
    }


def contar_y_ubicar(ruta: Path) -> tuple[int, int | None]:
    """Paginas del PDF y pagina (1-based) donde empieza el anexo de compromisos.
    Primero busca el titulo en mayusculas; si no aparece, lo busca sin importar
    mayusculas al comienzo de una pagina de la segunda mitad del documento."""
    with pymupdf.open(ruta) as doc:
        textos = [p.get_text() for p in doc]
    for i, t in enumerate(textos):
        if any(p.search(t) for p in ANEXO_MAYUS):
            return len(textos), i + 1
    for i, t in enumerate(textos[len(textos) // 2:], len(textos) // 2):
        if any(p.search(t[:400]) for p in ANEXO_CUALQUIERA):
            return len(textos), i + 1
    return len(textos), None


def verificar_enlace(url: str) -> dict:
    status, tipo, largo = pedir_cabeceras(url)
    return {"http_status": status, "tipo_contenido": tipo.split(";")[0], "tamano_bytes": largo,
            "verificado_el": date.today().isoformat()}


def respuesta_valida(url: str, http_status: str, tipo_contenido: str) -> bool:
    """200 con PDF o HTML; si la URL es de un PDF, tiene que llegar un PDF (una URL
    vieja puede redirigir a una pagina HTML y responder 200)."""
    if http_status != "200":
        return False
    p = urllib.parse.urlparse(url)
    es_pdf = p.path.lower().endswith(".pdf") or ".pdf" in p.query.lower()
    return "pdf" in tipo_contenido or (not es_pdf and "html" in tipo_contenido)


def verificar_comunicado(ref: str) -> dict:
    """Los comunicados se verifican con la API de Presscorner (la pagina de
    detalle es una aplicacion que siempre responde 200)."""
    try:
        doc = json.loads(inv.bajar(inv.URL_PRESS + "documents?" + urllib.parse.urlencode(
            {"reference": ref, "language": "en"}), timeout=60))
        ok = bool((doc.get("docuLanguageResource") or {}).get("title"))
    except Exception:  # noqa: BLE001
        ok = False
    return {"http_status": "200" if ok else "no encontrado", "tipo_contenido": "text/html", "tamano_bytes": "",
            "verificado_el": date.today().isoformat()}


def medir(filas: list[dict], descargar: bool, verificar: bool) -> None:
    """Completa las columnas de verificacion y el estado de cada fila."""
    # lo que falla por la red no se guarda en el cache, para reintentarlo en la proxima corrida
    pdfs, enlaces, fallidos = leer_cache(CACHE_PDF), leer_cache(CACHE_ENLACES), {}
    a_bajar = sorted({f["url"] for f in filas if f["tipo_doc"] in ("DEC", "COMP") and f.get("url")})
    for i, url in enumerate(a_bajar, 1):
        if url not in pdfs and descargar:
            print(f"  [{i}/{len(a_bajar)}] {Path(url).name}")
            medida = bajar_pdf(url)
            if medida["http_status"] == "200":
                pdfs[url] = medida
                guardar_cache(CACHE_PDF, pdfs)
            else:
                fallidos[url] = medida
    for f in filas:
        url = f.get("url")
        if not url or f.get("estado") or f["tipo_doc"] in ("DEC", "COMP", "RES_DO"):
            continue
        if url not in enlaces and verificar:
            medida = verificar_comunicado(f["ref"]) if f["tipo_doc"] in ("CP", "CP_APERTURA") else verificar_enlace(url)
            (enlaces if medida["http_status"] != "error" else fallidos)[url] = medida
            time.sleep(0.1)
    guardar_cache(CACHE_ENLACES, enlaces)

    for f in filas:
        if f.get("estado"):  # no_publicado_aun / no_encontrado / no_aplica
            continue
        medida = pdfs.get(f["url"]) or enlaces.get(f["url"]) or fallidos.get(f["url"])
        if not medida:
            f["estado"] = "localizado_no_verificado"
            continue
        for col in ("http_status", "tipo_contenido", "tamano_bytes", "verificado_el"):
            f[col] = medida.get(col, "")
        if f["tipo_doc"] == "DEC" or (f["tipo_doc"] == "COMP" and f.get("version") == "no confidencial"):
            f["sha256"], f["paginas"] = medida.get("sha256", ""), medida.get("paginas", "")
        ok = respuesta_valida(f["url"], f["http_status"], f["tipo_contenido"])
        if f["tipo_doc"] == "COMP" and f.get("version") == "anexo de la decisión":
            inicio = medida.get("inicio_compromisos", "")
            if f.get("paginas_compromisos"):
                pass  # cargadas a mano: decisiones viejas sin anexo con el titulo estandar
            elif inicio:
                f["paginas_compromisos"] = f"{inicio}–{medida['paginas']}"
            else:
                ok = False
                f["notas"] = "No se encontró el título del anexo de compromisos; revisar a mano."
        f["estado"] = "localizado_verificado" if ok else "localizado_no_verificado"


# ------------------------------------------------------------------- main --

def chequear(filas: list[dict], casos: list[dict]) -> list[str]:
    problemas = []
    ids = Counter(f["doc_id"] for f in filas)
    problemas += [f"doc_id duplicado: {k}" for k, n in ids.items() if n > 1]
    # entre casos distintos si puede repetirse: dos avisos en el mismo numero del Diario Oficial
    urls = Counter((f["caso_id"], f["url"], f["tipo_doc"]) for f in filas if f.get("url"))
    problemas += [f"{c}: URL repetida para {t}: {u}" for (c, u, t), n in urls.items() if n > 1]
    por_caso = defaultdict(list)
    for f in filas:
        por_caso[f["caso_id"]].append(f)
    for c in casos:
        tipos = Counter(f["tipo_doc"] for f in por_caso[c["caso_id"]])
        for t in ("DEC", "COMP"):
            if not tipos[t]:
                problemas.append(f"{c['caso_id']}: sin fila {t}")
        if c["fase"] == "II":
            dict_ok = [f for f in por_caso[c["caso_id"]] if f["tipo_doc"] == "DICT" and f.get("url")]
            if len(dict_ok) < 2:
                problemas.append(f"{c['caso_id']}: fase II con {len(dict_ok)} de 2 documentos DICT")
            if not tipos["CP_APERTURA"]:
                problemas.append(f"{c['caso_id']}: fase II sin CP_APERTURA")
    for f in filas:
        if f.get("estado") == "localizado_verificado" and not respuesta_valida(
                f.get("url", ""), f.get("http_status", ""), f.get("tipo_contenido", "")):
            problemas.append(f"{f['doc_id']}: verificado sin respuesta válida (200 con PDF, o HTML si no es un PDF)")
    return problemas


def resumen(filas: list[dict], casos: list[dict]) -> None:
    print("\nCobertura por tipo y estado:")
    estados = ["localizado_verificado", "localizado_no_verificado", "no_publicado_aun", "no_publico", "no_encontrado", "no_aplica"]
    print("  " + "tipo".ljust(12) + "".join(e[:14].rjust(16) for e in estados) + "       MB")
    for tipo in ORDEN_TIPOS:
        grupo = [f for f in filas if f["tipo_doc"] == tipo]
        if not grupo:
            continue
        c = Counter(f.get("estado", "") for f in grupo)
        # cada archivo una vez: un Merger Brief cubre varios casos y el anexo COMP es el PDF de la DEC
        unicos = {f["url"]: int(f["tamano_bytes"]) for f in grupo if (f.get("tamano_bytes") or "").isdigit()
                  and not (tipo == "COMP" and f.get("version") == "anexo de la decisión")}
        mb = sum(unicos.values()) / 1e6
        print("  " + tipo.ljust(12) + "".join(str(c[e]).rjust(16) for e in estados) + f"{mb:9.1f}")

    principales = {c["caso_id"] for c in casos}
    def con(tipo, cond):
        return {f["caso_id"] for f in filas if f["caso_id"] in principales and f["tipo_doc"] == tipo and cond(f)}
    dec = con("DEC", lambda f: f.get("estado") == "localizado_verificado")
    comp = con("COMP", lambda f: f.get("estado") == "localizado_verificado")
    print(f"\nCasos principales con decisión verificada: {len(dec)}/{len(principales)}"
          f" | con compromisos ubicados: {len(comp)}/{len(principales)}")
    faltan = sorted(principales - comp)
    if faltan:
        print("  Sin compromisos ubicados:", ", ".join(faltan))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--sin-descarga", action="store_true", help="no bajar PDF (no ubica compromisos)")
    ap.add_argument("--sin-verificar", action="store_true", help="no consultar la red para verificar enlaces")
    args = ap.parse_args()

    ruta_json = inv.CRUDOS / "case-data-M.json"
    if not ruta_json.exists():
        inv.descargar_json()
    datos = json.loads(ruta_json.read_text(encoding="utf-8"))
    comunicados = leer_cache(inv.CRUDOS / "comunicados.json")
    if not comunicados:
        print("Falta datos_crudos/comunicados.json: corré antes inventario_casos.py")
        return 1

    casos = list(inv.leer_csv(inv.CASOS_CSV).values())
    revisiones = list(inv.leer_csv(inv.REVISIONES_CSV).values())
    filas = []
    for c in casos:
        filas += numerar(c["caso_id"], "principal", filas_caso_principal(c, datos[c["caso_id"]], comunicados))
    for r in revisiones:
        filas += numerar(r["caso_id"], "revisiones", filas_revision(r, datos[r["caso_id"]]))
    print(f"{len(filas)} documentos armados para {len(casos)} casos + {len(revisiones)} del anexo")

    existentes = inv.leer_csv(DOCUMENTOS_CSV, clave="doc_id")
    for f in filas:  # paginas de compromisos cargadas a mano cuando el anexo no tiene el titulo estandar
        previa = existentes.get(f["doc_id"], {})
        if previa.get("url") == f.get("url") and previa.get("paginas_compromisos"):
            f["paginas_compromisos"] = previa["paginas_compromisos"]

    medir(filas, descargar=not args.sin_descarga, verificar=not args.sin_verificar)

    # las filas manuales no surgen de las fuentes y se conservan tal cual
    manuales = [f for f in existentes.values() if es_manual(f)]
    automaticas = {k: f for k, f in existentes.items() if not es_manual(f)}
    combinadas, discrepancias = inv.mergear(
        automaticas, {f["doc_id"]: f for f in filas}, COLUMNAS, AUTOMATICAS,
        orden=lambda f: f["doc_id"], archivo=DOCUMENTOS_CSV.name)
    combinadas = sorted(combinadas + manuales, key=lambda f: f["doc_id"])
    inv.escribir_csv(DOCUMENTOS_CSV, combinadas, COLUMNAS)
    print(f"Escrito {DOCUMENTOS_CSV.name}: {len(combinadas)} filas")

    if discrepancias:
        print("\nDISCREPANCIAS (no se pisó nada; resolver a mano):")
        for d in discrepancias:
            print("  " + d)

    resumen(combinadas, casos)
    problemas = chequear(combinadas, casos)
    print("\nChequeos:", "OK" if not problemas else f"{len(problemas)} problemas")
    for p in problemas:
        print("  " + p)
    return 1 if problemas else 0


if __name__ == "__main__":
    sys.exit(main())
