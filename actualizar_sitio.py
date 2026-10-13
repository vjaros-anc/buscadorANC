# -*- coding: utf-8 -*-
"""
Actualizacion del sitio en un solo comando (en la rama del area interna, ver SITIO.md).

Corre en este orden y corta en el primer error (codigo de salida 1):

  1. generar_pagina.py        firm.xlsx -> index.html (el buscador)
  2. generar_tablero.py       firm.xlsx -> conc/index.html y data/conc.json (estadisticas)
  3. generar_seguimiento.py   Res_firmadas.xlsm (la carpeta de Drive) -> demo-interno/data/seguimiento.json
     monitor (con --monitor)  el monitor.json que baja el artefacto -> demo-interno/data/monitor.json
  4. verificar_sitio.py       compuerta de publicacion
  5. pruebas                  tests/test_sitio.py
  6. comparar_index.py        contra el index.html de antes de empezar: PERDIDOS tiene que dar 0

Reemplaza los pasos 8 y 9 del PROTOCOLO.md; los pasos 0 a 7 (cargar filas, PDFs, extraer, mergear, empresas,
productos, mover PDFs) siguen igual. No toca git: al final dice que cambio y con que comandos subirlo.

Donde esta Res_firmadas.xlsm (gana el primero que este):
  --res-firmadas RUTA        y la recuerda en ~/.anc_sitio.json para las proximas veces
  variable ANC_RES_FIRMADAS
  ~/.anc_sitio.json          {"res_firmadas": "G:\\Mi unidad\\...\\Res_firmadas.xlsm"}
  Res_firmadas.xlsm          junto a este script

Uso:
  python -B actualizar_sitio.py --res-firmadas "G:\\Mi unidad\\ANC\\Res_firmadas.xlsm"   (la primera vez)
  python -B actualizar_sitio.py                                                       (las siguientes)
  python -B actualizar_sitio.py --monitor "C:\\Users\\yo\\Downloads\\monitor.json"     (con un monitor nuevo)
  python -B actualizar_sitio.py --cotejar      paso 0 del protocolo (cotejar_res_firmadas.py) con el Excel de Drive

En la rama main (cuando se mergee) no se generan el seguimiento ni el monitor: son datos internos.
"""
from __future__ import annotations

import argparse
import datetime as dt
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI))

import verificar_sitio as vs  # noqa: E402  (solo biblioteca estandar)

CONFIG = Path.home() / ".anc_sitio.json"
EXCEL_JUNTO = AQUI / "Res_firmadas.xlsm"
INDEX = AQUI / "index.html"
INDEX_PREVIO = AQUI / "respaldos" / "index_previo.html"
MONITOR = AQUI / "demo-interno" / "data" / "monitor.json"
MONITOR_SCHEMA = vs.MONITOR_SCHEMA
DIAS_MONITOR_VIEJO = 15
GENERADOS = ["index.html", "conc", "data", "demo-interno/data"]
RX_FECHA = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _p(*args) -> None:
    """print tolerante con consolas sin UTF-8 (cp850/cp437)."""
    txt = " ".join(str(a) for a in args)
    try:
        print(txt, flush=True)
    except UnicodeEncodeError:
        enc = sys.stdout.encoding or "ascii"
        print(txt.encode(enc, "replace").decode(enc), flush=True)


# --------------------------------------------------------------------------- #
# Donde esta Res_firmadas.xlsm
# --------------------------------------------------------------------------- #
def leer_config(ruta: Path = CONFIG) -> dict:
    try:
        d = json.loads(ruta.read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def guardar_config(datos: dict, ruta: Path = CONFIG) -> None:
    ruta.write_text(json.dumps(datos, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


def resolver_res_firmadas(arg=None, entorno=None, config=None, defecto: Path = EXCEL_JUNTO):
    """-> (Path, de donde salio). Gana el argumento, despues la variable ANC_RES_FIRMADAS, despues ~/.anc_sitio.json
    y por ultimo el Excel junto al script."""
    entorno = os.environ if entorno is None else entorno
    config = leer_config() if config is None else config
    for valor, fuente in ((arg, "--res-firmadas"), (entorno.get("ANC_RES_FIRMADAS"), "variable ANC_RES_FIRMADAS"),
                          (config.get("res_firmadas"), str(CONFIG))):
        if valor:
            return Path(valor).expanduser(), fuente
    return defecto, "junto al script"


# --------------------------------------------------------------------------- #
# Monitor (el monitor.json que baja el boton del artefacto)
# --------------------------------------------------------------------------- #
def _monitor_merge():
    """demo-interno/monitor_merge.py (la carpeta tiene guion: se importa por ruta). Sus reglas de campos son las mismas."""
    ruta = AQUI / "demo-interno" / "monitor_merge.py"
    spec = importlib.util.spec_from_file_location("monitor_merge", str(ruta))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def validar_monitor(doc):
    """-> (errores, avisos). Errores: no es el contrato `operaciones` v1 de un monitor real. Avisos: los mismos
    controles de campos que monitor_merge.py."""
    if not isinstance(doc, dict):
        return ["no es un objeto JSON"], []
    errores = []
    if doc.get("schema_version") != MONITOR_SCHEMA:
        errores.append("schema_version %r (la página de noticias lee la %d)" % (doc.get("schema_version"), MONITOR_SCHEMA))
    if doc.get("origen") != "artefacto":
        errores.append("origen %r: tiene que ser 'artefacto' (el que baja el botón del artefacto)" % doc.get("origen"))
    if not RX_FECHA.match(str(doc.get("exportado_el") or "")):
        errores.append("exportado_el %r no es AAAA-MM-DD" % doc.get("exportado_el"))
    for clave in ("operaciones", "informes"):
        if not isinstance(doc.get(clave), list):
            errores.append("falta la lista '%s'" % clave)
    if not isinstance(doc.get("parametros", {}), dict):
        errores.append("'parametros' no es un objeto")
    if errores:
        return errores, []

    mm = _monitor_merge()
    avisos = []
    for o in doc["operaciones"]:
        if not isinstance(o, dict):
            errores.append("una operación no es un objeto")
            continue
        oid = o.get("id") or "(sin id)"
        if not o.get("id"):
            avisos.append("operación sin id: %s" % (o.get("partes") or "?"))
        for c in mm.OBLIGATORIOS:
            if not o.get(c):
                avisos.append("%s: falta %s" % (oid, c))
        for c, ok in mm.VALORES.items():
            if o.get(c) and o[c] not in ok:
                avisos.append("%s: %s=%r no es un valor conocido" % (oid, c, o[c]))
        if o.get("relevanteANC") and not o.get("verificacion"):
            avisos.append("%s: marcada relevanteANC sin verificacion (la página la toma como 'pendiente')" % oid)
    return errores, avisos


def copiar_monitor(origen: Path, destino: Path = MONITOR) -> int:
    try:
        doc = json.loads(origen.read_text(encoding="utf-8-sig"))
    except OSError as e:
        _p("  ERROR: no puedo leer %s (%s)" % (origen, e))
        return 1
    except ValueError as e:
        _p("  ERROR: %s no es un JSON válido (%s)" % (origen, e))
        return 1
    errores, avisos = validar_monitor(doc)
    for e in errores:
        _p("  ERROR:", e)
    if errores:
        return 1
    previo = _exportado_el(destino)
    if previo and doc["exportado_el"] < previo:
        avisos.insert(0, "este monitor (%s) es más viejo que el publicado (%s)" % (doc["exportado_el"], previo))
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    _p("  OK -> %s  (%d operaciones, %d informes, exportado el %s)"
       % (_rel(destino), len(doc["operaciones"]), len(doc["informes"]), doc["exportado_el"]))
    for a in avisos:
        _p("  AVISO:", a)
    return 0


def _rel(ruta: Path) -> str:
    try:
        return ruta.resolve().relative_to(AQUI).as_posix()
    except ValueError:
        return str(ruta)


def _exportado_el(ruta: Path):
    try:
        return json.loads(ruta.read_text(encoding="utf-8")).get("exportado_el")
    except (OSError, ValueError, AttributeError):
        return None


def recordatorio_monitor(hoy: dt.date, ruta: Path = MONITOR):
    """Texto para recordar bajar el monitor del artefacto, o None si esta al dia."""
    exp = _exportado_el(ruta)
    if not exp:
        return "No hay monitor real: la pestaña de noticias muestra el ejemplo. Bajalo del artefacto y corré con --monitor RUTA."
    try:
        dias = (hoy - dt.date.fromisoformat(exp)).days
    except ValueError:
        return None
    if dias > DIAS_MONITOR_VIEJO:
        return ("El monitor publicado es del %s (hace %d días). Si hubo un informe nuevo, bajalo del artefacto y corré con "
                "--monitor RUTA." % (exp, dias))
    return None


# --------------------------------------------------------------------------- #
# Pasos
# --------------------------------------------------------------------------- #
def pasos(en_main: bool, excel: Path, monitor=None, con_seguimiento: bool = True):
    """Lista de (clave, titulo, accion). accion: lista de argumentos para Python, o una funcion sin argumentos que
    devuelve el codigo de salida."""
    py = [sys.executable, "-B"]
    lista = [("pagina", "Buscador: generar_pagina.py", py + ["generar_pagina.py"]),
             ("tablero", "Estadísticas: generar_tablero.py", py + ["generar_tablero.py"])]
    if not en_main:
        if con_seguimiento:
            lista.append(("seguimiento", "Seguimiento: generar_seguimiento.py",
                          py + ["generar_seguimiento.py", "--excel", str(excel)]))
        if monitor:
            lista.append(("monitor", "Noticias: copiar el monitor del artefacto", lambda: copiar_monitor(Path(monitor))))
    lista += [("verificar", "Compuerta: verificar_sitio.py", py + ["verificar_sitio.py"]),
              ("pruebas", "Pruebas: tests/test_sitio.py", py + ["-m", "unittest", "discover", "-s", "tests"]),
              ("comparar", "Comparar con el index anterior: comparar_index.py",
               py + ["comparar_index.py", str(INDEX_PREVIO.relative_to(AQUI)), "index.html"])]
    return lista


def correr(accion, entorno) -> int:
    if callable(accion):
        return accion()
    return subprocess.run(accion, cwd=str(AQUI), env=entorno).returncode


def cotejar(excel: Path) -> int:
    """Paso 0 del protocolo con el Excel de Drive, sin tocar cotejar_res_firmadas.py: el modulo lee SEGUIMIENTO al correr."""
    import cotejar_res_firmadas as cr
    cr.SEGUIMIENTO = excel
    cr.main()
    return 0


def resumen(rama: str) -> None:
    try:
        out = subprocess.run(["git", "-C", str(AQUI), "status", "--short", "--"] + GENERADOS,
                             capture_output=True, check=True).stdout.decode("utf-8", "replace").strip()
    except (OSError, subprocess.CalledProcessError):
        out = "(no se pudo leer git status)"
    _p("\nArchivos del sitio que cambiaron:")
    _p(out or "  ninguno (los datos no cambiaron)")
    _p("\nPara subir (mirá antes 'git status': que no entre nada de nuevas/ ni respaldos):")
    _p("  git add -A")
    _p('  git commit -m "act %s"' % dt.date.today().strftime("%d-%m"))
    _p("  git push origin %s" % (rama or "<rama>"))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--res-firmadas", metavar="RUTA", help="Res_firmadas.xlsm (p. ej. en G:\\Mi unidad\\...); se recuerda")
    ap.add_argument("--monitor", metavar="RUTA", help="monitor.json bajado con el botón del artefacto")
    ap.add_argument("--sin-seguimiento", action="store_true", help="no regenera el seguimiento")
    ap.add_argument("--cotejar", action="store_true", help="solo el paso 0: cotejar_res_firmadas.py con ese Excel")
    args = ap.parse_args()

    rama = vs.rama_actual(AQUI)
    en_main = rama == "main"
    excel, fuente = resolver_res_firmadas(args.res_firmadas)
    necesita_excel = args.cotejar or (not en_main and not args.sin_seguimiento)
    _p("Rama: %s | Res_firmadas: %s (%s)" % (rama or "?", excel, fuente))
    if necesita_excel and not excel.is_file():
        _p("ERROR: no encuentro %s.\n  ¿Está abierto Drive para escritorio y sincronizado? ¿La carpeta compartida tiene un acceso "
           "directo en Mi unidad?\n  Indicá la ruta con --res-firmadas \"G:\\Mi unidad\\...\\Res_firmadas.xlsm\" "
           "(o --sin-seguimiento para no regenerarlo)." % excel)
        return 1
    if args.res_firmadas:
        cfg = leer_config()
        if cfg.get("res_firmadas") != str(excel):
            cfg["res_firmadas"] = str(excel)
            guardar_config(cfg)
            _p("Ruta guardada en %s: la próxima vez no hace falta --res-firmadas." % CONFIG)

    if args.cotejar:
        return cotejar(excel)

    if en_main:
        _p("En main no se generan el seguimiento ni el monitor (datos internos)%s."
           % ("; se ignora --monitor" if args.monitor else ""))
    if not INDEX.is_file():
        _p("ERROR: no existe index.html")
        return 1
    INDEX_PREVIO.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(str(INDEX), str(INDEX_PREVIO))

    entorno = dict(os.environ)
    entorno.setdefault("PYTHONIOENCODING", ":replace")      # que un caracter raro en la consola no corte un paso
    entorno["ANC_RES_FIRMADAS"] = str(excel)                 # la prueba del seguimiento regenera desde este Excel

    lista = pasos(en_main, excel, args.monitor, con_seguimiento=not args.sin_seguimiento)
    for i, (clave, titulo, accion) in enumerate(lista, 1):
        _p("\n=== %d/%d  %s" % (i, len(lista), titulo))
        rc = correr(accion, entorno)
        if rc != 0:
            _p("\nFALLÓ: %s (código %s). No subas nada hasta resolverlo." % (titulo, rc))
            if clave == "comparar":
                _p("Se perdieron expedientes respecto de %s: revisá la columna Carpeta de las filas que tocaste."
                   % INDEX_PREVIO.relative_to(AQUI).as_posix())
            return 1

    if not en_main and not args.monitor:
        aviso = recordatorio_monitor(dt.date.today())
        if aviso:
            _p("\nAVISO:", aviso)
    _p("\nOK: el sitio está actualizado y pasó la verificación, las pruebas y la comparación.")
    resumen(rama)
    return 0


if __name__ == "__main__":
    sys.exit(main())
