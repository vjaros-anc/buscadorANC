# -*- coding: utf-8 -*-
"""
Etapa 4 de la biblioteca de remedios UE: controla las fichas problema-remedio
(fichas/M.xxxxx.md) y fichas/relaciones.csv contra las reglas de fichas/PLANTILLA.md.

Chequeos:
  - relaciones.csv tiene las columnas de la plantilla y una fila por par
    caso/problema/remedio, sin repetidos.
  - Cada caso_id existe en casos.csv y tiene su ficha; cada ficha tiene filas.
  - Los valores de las columnas con vocabulario estan en las listas de
    PLANTILLA.md (se leen de ahi; dos valores van separados por ';').
  - Los P1, R1... del CSV son los mismos que los encabezados de la ficha.
  - Las citas, en el CSV y en el texto de la ficha, tienen el formato
    'DEC parr. n [p. x]', 'DEC tabla n [p. x]', 'COMP cl. n [p. x]' o 'doc_id [p. x]'.

Con --texto (la carpeta texto_extraido/ de extraer_texto.py) ademas verifica
cada cita contra el texto de los PDF:
  - DEC: el parrafo "(n)" de la decision esta, al menos en parte, en alguna de
    las paginas citadas (error si no).
  - DEC tabla: el titulo "Table n" (o "Tableau n") esta en esas paginas (aviso si no).
  - COMP: las paginas estan dentro del anexo de compromisos (error si no) y la
    clausula n aparece en ellas (aviso si no la encuentra).
  - doc_id: el documento existe y tiene esas paginas.
  - Avisa cuando la pagina citada se leyo por OCR: las cifras se verifican
    contra la imagen del PDF.

Uso:
    python validar_fichas.py
    python validar_fichas.py --texto ../descargas_anc/texto_extraido

Devuelve 1 si hay errores (los avisos no cuentan).
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

import inventario_casos as inv

FICHAS = inv.AQUI / "fichas"
PLANTILLA = FICHAS / "PLANTILLA.md"
RELACIONES_CSV = FICHAS / "relaciones.csv"

COLUMNAS = [
    "caso_id", "problema_id", "mercado", "ambito_geografico", "tipo_efecto", "mecanismo",
    "remedio_id", "tipo_remedio", "subtipo_remedio", "obligacion", "duracion",
    "comprador_previo", "trustee", "clausula_revision",
    "cita_problema", "cita_remedio", "cita_suficiencia", "notas",
]
OBLIGATORIAS = [c for c in COLUMNAS if c != "notas"]
COLUMNAS_CITA = ["cita_problema", "cita_remedio", "cita_suficiencia"]

# numero o rango ("166", "166–172", "2.1"); listas separadas por coma
NUM = r"\d+(?:\.\d+)*(?:\s*[–-]\s*\d+(?:\.\d+)*)?"
LISTA = rf"{NUM}(?:\s*,\s*{NUM})*"
GRUPO = re.compile(rf"\s*(?P<nums>{LISTA})?\s*\[(?P<pp>pp?\.)\s*(?P<pags>{LISTA})\]")
DOC_ID = r"M\.\d{4,5}_[A-Z]+(?:_[A-Z]+)?_M?\d{2}"
FUENTE = re.compile(rf"(?<![\"“`])(?P<src>DEC párrs?\.|DEC tablas?|COMP cl\.|`?(?P<doc>{DOC_ID})`?(?P<sub>\s+(?:cl\.|párrs?\.))?(?=\s*\S*\s*\[pp?\.))")
ENCABEZADO = re.compile(r"(?m)^###\s+(?P<id>[PR]\d+)\b")
VOCABULARIO = re.compile(r"^\*\*[^*]*\(`(?P<col>\w+)`\)[^*]*\*\*(?P<resto>.*)$")


def leer_vocabularios(ruta: Path = PLANTILLA) -> dict[str, set[str]]:
    """Listas de PLANTILLA.md: '**Titulo (`columna`)**' seguido de '- `valor`: ...' o con
    los valores en la misma linea."""
    vocab: dict[str, set[str]] = {}
    actual = None
    for linea in ruta.read_text(encoding="utf-8").splitlines():
        m = VOCABULARIO.match(linea.strip())
        if m:
            actual = m["col"]
            vocab[actual] = set(re.findall(r"`([\w]+)`", m["resto"]))
        elif actual and linea.startswith("- `"):
            vocab[actual].add(re.match(r"- `(\w+)`", linea)[1])
        elif linea.strip() and not linea.startswith("  "):
            actual = None
    return vocab


def expandir(lista: str) -> list[str]:
    """'166–168, 177' -> ['166', '167', '168', '177']; los rangos con puntos quedan en sus extremos."""
    salida = []
    for parte in re.split(r"\s*,\s*", lista.strip()):
        extremos = [x for x in re.split(r"\s*[–-]\s*", parte) if x]
        if len(extremos) == 2 and all(x.isdigit() for x in extremos) and int(extremos[0]) <= int(extremos[1]):
            salida += [str(n) for n in range(int(extremos[0]), int(extremos[1]) + 1)]
        else:
            salida += extremos
    return salida


def parsear_citas(texto: str) -> tuple[list[dict], list[str]]:
    """Citas de un texto. Cada una: fuente (DEC, COMP o doc_id), numeros (parrafos o
    clausulas) y paginas. Devuelve tambien las citas mal formadas."""
    citas, errores = [], []
    for m in FUENTE.finditer(texto):
        fuente = ("TABLA" if m["src"].startswith("DEC tabla") else "DEC" if m["src"].startswith("DEC")
                  else "COMP" if m["src"].startswith("COMP") else m["doc"])
        pos, grupos = m.end(), 0
        while True:
            g = GRUPO.match(texto, pos)
            if not g or (grupos and not g["nums"]):
                break
            if fuente in ("DEC", "TABLA", "COMP") and not g["nums"]:
                break
            if g["pp"] == "p." and len(expandir(g["pags"])) > 1:
                errores.append(f"'p.' con varias páginas, va 'pp.': {texto[m.start():g.end()]!r}")
            citas.append({"fuente": fuente, "numeros": expandir(g["nums"]) if g["nums"] else [],
                          "paginas": [int(p) for p in expandir(g["pags"]) if p.isdigit()],
                          "texto": texto[m.start():g.end()].strip()})
            grupos += 1
            pos = g.end()
            separador = re.match(r"\s*(?:,|y\b)", texto[pos:])  # "177 [p. 48], 180 [p. 49]" o "... y 192 [p. 50]"
            if not separador:
                break
            pos += separador.end()
        if not grupos:
            errores.append(f"cita sin número o sin página: {texto[m.start():m.end() + 30]!r}")
    return citas, errores


def ids_ficha(texto: str) -> set[str]:
    return {m["id"] for m in ENCABEZADO.finditer(texto)}


def chequear_filas(filas: list[dict], columnas: list[str], vocab: dict[str, set[str]],
                   casos: set[str], fichas: dict[str, str]) -> list[str]:
    errores = []
    if columnas != COLUMNAS:
        errores.append(f"relaciones.csv: columnas {columnas} distintas de {COLUMNAS}")
        return errores
    for clave, n in Counter((f["caso_id"], f["problema_id"], f["remedio_id"]) for f in filas).items():
        if n > 1:
            errores.append(f"{'/'.join(clave)}: fila repetida ({n} veces)")
    for i, f in enumerate(filas, 2):
        donde = f"relaciones.csv fila {i} ({f['caso_id']} {f['problema_id']}-{f['remedio_id']})"
        for c in OBLIGATORIAS:
            if not f[c].strip():
                errores.append(f"{donde}: '{c}' vacío")
        if f["caso_id"] not in casos:
            errores.append(f"{donde}: el caso no está en casos.csv")
        if not re.fullmatch(r"P\d+", f["problema_id"]) or not re.fullmatch(r"R\d+", f["remedio_id"]):
            errores.append(f"{donde}: problema_id/remedio_id deben ser P1, R1...")
        for c, valores in vocab.items():
            if c not in f:
                continue
            for v in (x.strip() for x in f[c].split(";")):
                if v and v not in valores:
                    errores.append(f"{donde}: '{c}' = {v!r} no está en el vocabulario de PLANTILLA.md")
        for c in COLUMNAS_CITA:
            citas, mal = parsear_citas(f[c])
            errores += [f"{donde}: {c}: {e}" for e in mal]
            if f[c].strip() and not citas:
                errores.append(f"{donde}: {c} sin citas reconocibles: {f[c]!r}")
    por_caso = defaultdict(set)
    for f in filas:
        por_caso[f["caso_id"]] |= {f["problema_id"], f["remedio_id"]}
    for caso in sorted(set(por_caso) | set(fichas)):
        if caso not in fichas:
            errores.append(f"{caso}: tiene filas en relaciones.csv pero no ficha {caso}.md")
            continue
        if caso not in por_caso:
            errores.append(f"{caso}.md: no tiene filas en relaciones.csv")
            continue
        en_ficha = ids_ficha(fichas[caso])
        for i in sorted(por_caso[caso] - en_ficha):
            errores.append(f"{caso}: {i} está en relaciones.csv pero no como encabezado '### {i}' en la ficha")
        for i in sorted(en_ficha - por_caso[caso]):
            errores.append(f"{caso}: '### {i}' de la ficha no aparece en relaciones.csv")
    return errores


def es_nota_al_pie(texto: str, inicio: int, numero: str) -> bool:
    """En algunas decisiones las notas al pie tambien se numeran "(n)" al comienzo de linea.
    La nota n esta en la misma pagina que su llamada "(n)" dentro del texto y despues del
    parrafo (n) si los dos estan en esa pagina: es el ultimo "(n)" de comienzo de linea de
    una pagina que tiene la llamada."""
    if re.search(rf"(?m)^\s{{0,12}}\({numero}\)\s", texto[inicio + 1:]):
        return False
    for llamada in re.finditer(rf"(?<!\w)\({numero}\)", texto[:inicio]):  # no "Article 8(2)"
        if texto[texto.rfind("\n", 0, llamada.start()) + 1:llamada.start()].strip():
            return True
    return False


def cadena_de_parrafos(candidatos: list[tuple[int, int]], salto: int = 5) -> list[tuple[int, int]]:
    """De los "(n)" de comienzo de linea (numero, pagina), en orden, elige la cadena creciente
    mas larga con saltos de hasta `salto` (parrafos que el texto no separo bien). Asi una
    llamada a nota que cae al comienzo de una linea no corta la numeracion, como pasaria
    tomando siempre el primer numero que sigue."""
    largo, previo, mejor = [0] * len(candidatos), [None] * len(candidatos), {}
    for k, (n, _) in enumerate(candidatos):
        base = max((mejor[m] for m in range(n - salto, n) if m in mejor), default=None)
        if base is None and n > salto:
            continue  # la numeracion empieza en (1)
        largo[k], previo[k] = (base[0] + 1, base[1]) if base else (1, None)
        if largo[k] > mejor.get(n, (0, None))[0]:
            mejor[n] = (largo[k], k)
    if not any(largo):
        return []
    k, cadena = max(range(len(candidatos)), key=lambda i: (largo[i], -i)), []
    while k is not None:
        cadena.append(candidatos[k])
        k = previo[k]
    return cadena[::-1]


class Texto:
    """Acceso al texto_extraido/ de extraer_texto.py por documento_id."""

    def __init__(self, carpeta: Path):
        self.carpeta = carpeta
        with (carpeta / "documentos.csv").open(encoding="utf-8-sig", newline="") as f:
            self.docs = {r["documento_id"]: r for r in csv.DictReader(f) if r.get("json")}
        self._paginas: dict[str, list[dict]] = {}
        self._parrafos: dict[str, dict[str, tuple[int, int]]] = {}

    def paginas(self, doc_id: str) -> list[dict] | None:
        if doc_id not in self.docs:
            return None
        if doc_id not in self._paginas:
            datos = json.loads((self.carpeta / self.docs[doc_id]["json"]).read_text(encoding="utf-8"))
            self._paginas[doc_id] = datos["paginas"]
        return self._paginas[doc_id]

    def rango_compromisos(self, caso: str) -> tuple[int, int] | None:
        valor = self.docs.get(f"{caso}_COMP_01", {}).get("paginas_compromisos", "")
        m = re.fullmatch(r"(\d+)\s*[–-]\s*(\d+)", valor.strip())
        return (int(m[1]), int(m[2])) if m else None

    def parrafos(self, caso: str) -> dict[str, tuple[int, int]]:
        """Parrafo n -> (pagina donde empieza, pagina donde empieza el siguiente), en la
        decision y antes del anexo de compromisos. Descarta las notas al pie "(n)" y sigue la
        numeracion (cadena_de_parrafos) para no confundir anios o llamadas entre parentesis
        con numeros de parrafo."""
        doc_id = f"{caso}_DEC_01"
        if doc_id in self._parrafos:
            return self._parrafos[doc_id]
        paginas = self.paginas(doc_id) or []
        comp = self.rango_compromisos(caso)
        hasta = comp[0] - 1 if comp else len(paginas)
        candidatos = [(int(m[1]), i) for i, p in enumerate(paginas[:hasta], 1)
                      for m in re.finditer(r"(?m)^\s{0,12}\((\d{1,4})\)\s", p["texto"])
                      if not es_nota_al_pie(p["texto"], m.start(), m[1])]
        inicios = cadena_de_parrafos(candidatos)
        rangos = {}
        for k, (n, pag) in enumerate(inicios):
            fin = inicios[k + 1][1] if k + 1 < len(inicios) else pag
            rangos[str(n)] = (pag, fin)
        self._parrafos[doc_id] = rangos
        return rangos

    def es_ocr(self, doc_id: str, pagina: int) -> bool:
        paginas = self.paginas(doc_id) or []
        return 0 < pagina <= len(paginas) and paginas[pagina - 1].get("origen_texto") == "ocr"


def verificar_cita(cita: dict, caso: str, texto: Texto) -> tuple[list[str], list[str]]:
    errores, avisos = [], []
    fuente, pags = cita["fuente"], cita["paginas"]
    doc_id = f"{caso}_DEC_01" if fuente in ("DEC", "TABLA", "COMP") else fuente
    if fuente not in ("DEC", "TABLA", "COMP") and not fuente.startswith(caso + "_"):
        avisos.append(f"{cita['texto']!r}: cita un documento de otro caso")
    paginas = texto.paginas(doc_id)
    if paginas is None:
        return [f"{cita['texto']!r}: {doc_id} no está en texto_extraido"], avisos
    fuera = [p for p in pags if not 1 <= p <= len(paginas)]
    if fuera:
        return [f"{cita['texto']!r}: {doc_id} tiene {len(paginas)} páginas"], avisos
    if fuente == "DEC":
        rangos = texto.parrafos(caso)
        for n in cita["numeros"]:
            if n not in rangos:
                avisos.append(f"{cita['texto']!r}: no ubico el párrafo ({n}) en el texto")
            elif not any(rangos[n][0] <= p <= rangos[n][1] for p in pags):
                desde, hasta = rangos[n]
                donde = f"p. {desde}" if desde == hasta else f"pp. {desde}–{hasta}"
                errores.append(f"{cita['texto']!r}: el párrafo ({n}) está en {donde}")
    elif fuente == "COMP":
        comp = texto.rango_compromisos(caso)
        if not comp:
            avisos.append(f"{cita['texto']!r}: no hay páginas de compromisos para {caso}")
        elif any(not comp[0] <= p <= comp[1] for p in pags):
            errores.append(f"{cita['texto']!r}: fuera del anexo de compromisos (pp. {comp[0]}–{comp[1]})")
    if fuente != "DEC" and cita["numeros"]:
        bloque = "\n".join(paginas[p - 1]["texto"] for p in range(max(1, min(pags) - 1), max(pags) + 1))
        for n in cita["numeros"]:
            if fuente == "TABLA":
                if not re.search(rf"(?i)\b(?:table|tableau|tabla)\s+{re.escape(n)}\b", bloque):
                    avisos.append(f"{cita['texto']!r}: no encuentro la tabla {n} en esas páginas")
            elif not re.search(rf"(?m)^\s*\(?{re.escape(n)}[.)]?\s", bloque):
                avisos.append(f"{cita['texto']!r}: no encuentro la cláusula {n} en esas páginas")
    for p in pags:
        if texto.es_ocr(doc_id, p):
            avisos.append(f"{cita['texto']!r}: la p. {p} se leyó por OCR; verificar cifras contra el PDF")
    return errores, avisos


def citas_de_caso(caso: str, ficha: str, filas: list[dict]) -> tuple[list[dict], list[str]]:
    citas, errores = parsear_citas(ficha)
    errores = [f"{caso}.md: {e}" for e in errores]
    for f in filas:
        if f["caso_id"] == caso:
            for c in COLUMNAS_CITA:
                citas += parsear_citas(f[c])[0]
    return citas, errores


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--texto", type=Path, help="carpeta texto_extraido/ para verificar las citas contra los PDF")
    args = ap.parse_args()

    vocab = leer_vocabularios(PLANTILLA)
    casos = set(inv.leer_csv(inv.CASOS_CSV))
    fichas = {p.stem: p.read_text(encoding="utf-8") for p in sorted(FICHAS.glob("M.*.md"))}
    with RELACIONES_CSV.open(encoding="utf-8-sig", newline="") as f:
        lector = csv.DictReader(f)
        filas = list(lector)
        columnas = lector.fieldnames or []

    errores = chequear_filas(filas, columnas, vocab, casos, fichas)
    avisos: list[str] = []
    texto = Texto(args.texto) if args.texto else None
    verificadas = 0
    for caso, ficha in fichas.items():
        citas, mal = citas_de_caso(caso, ficha, filas)
        errores += mal
        if not texto:
            continue
        vistas = set()
        for cita in citas:
            clave = (cita["fuente"], tuple(cita["numeros"]), tuple(cita["paginas"]))
            if clave in vistas:
                continue
            vistas.add(clave)
            e, a = verificar_cita(cita, caso, texto)
            errores += [f"{caso}: {x}" for x in e]
            avisos += [f"{caso}: {x}" for x in a]
            verificadas += 1

    print(f"{len(fichas)} fichas, {len(filas)} filas en relaciones.csv, "
          f"vocabularios: {', '.join(f'{k} ({len(v)})' for k, v in vocab.items())}")
    if texto:
        print(f"{verificadas} citas verificadas contra {args.texto}")
    else:
        print("Citas: solo formato (con --texto se verifican contra los PDF)")
    if avisos:
        print(f"\nAvisos ({len(avisos)}):")
        for a in avisos:
            print("  " + a)
    print("\nChequeos:", "OK" if not errores else f"{len(errores)} errores")
    for e in errores:
        print("  " + e)
    return 1 if errores else 0


if __name__ == "__main__":
    sys.exit(main())
