# -*- coding: utf-8 -*-
"""
Compuertas de contenido del sitio (solo biblioteca estandar; el ultimo grupo usa pandas y se saltea si no esta).

Responden "¿lo que se va a publicar es coherente?" y fallan con un mensaje que dice que script volver a correr:

  - el tablero (data/conc.json y conc/index.html) corresponde al index.html publicado del buscador
  - los agregados del tablero salen del detalle por expediente
  - /opis/ es el buscador de OPIs original mas tres fragmentos de la barra, nada mas
  - el buscador y su plantilla llevan la barra comun
  - los fixtures estan marcados como ejemplo; el seguimiento y el monitor reales solo pasan fuera de main
  - la lista blanca de build_site.py no deja pasar el Excel, los scripts ni los insumos internos
  - la biblioteca de remedios (remedios/) es la que sale de las fichas de remedios_ue/, y --aditivo acepta
    .gitignore con lineas nuevas y lo que main ya no tiene
  - actualizar_sitio.py: orden de los pasos, de donde sale el Excel (Descargas), que monitor.json acepta
    y que frena si hay un Excel interno suelto en la carpeta del repo
  - (si hay openpyxl y el Excel) regenerar el seguimiento desde Res_firmadas.xlsm da lo que esta versionado
  - (si hay pandas) regenerar el tablero desde firm.xlsx da lo que esta versionado

Uso (desde la raiz del repo):
    python -B -m unittest discover -s tests -v
"""
import collections
import contextlib
import datetime as dt
import io as _io
import json
import math
import os
import re
import shutil
import statistics
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.dont_write_bytecode = True      # los .pyc versionados no se reescriben
RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

import actualizar_sitio as aus      # noqa: E402
import build_site as bs             # noqa: E402
import generar_remedios as gr       # noqa: E402
import generar_seguimiento as gs    # noqa: E402
import integrar_opis as io          # noqa: E402
import verificar_sitio as vs        # noqa: E402


def leer_json(ruta):
    return json.loads((RAIZ / ruta).read_text(encoding="utf-8"))


def pct1(n, t):
    return math.floor(1000.0 * n / t + 0.5) / 10 if t else 0.0


def mediana(xs):
    return int(math.floor(statistics.median(xs) + 0.5))


class TableroTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.conc = leer_json("data/conc.json")
        cls.corpus = vs.corpus_del_buscador(RAIZ / "index.html")
        cls.detalle = cls.conc["detalle"]

    def test_corresponde_al_buscador_publicado(self):
        self.assertIsNotNone(self.corpus, "index.html no trae el bloque bm-data")
        self.assertEqual(len(self.detalle), len(self.corpus), "otra cantidad de expedientes: correr generar_tablero.py")
        self.assertEqual(self.conc["corpus"]["huella"], vs.huella_corpus(self.corpus),
                         "el tablero no corresponde al index.html: correr 'python -B generar_tablero.py'")
        for fila, reg in zip(self.detalle, self.corpus):
            self.assertEqual(fila["carpeta"], reg["carpeta"])
            self.assertEqual(fila["tipo"], reg["tipo_cat"], fila["carpeta"])
            self.assertEqual(fila["decision"], reg["decision"] or "", fila["carpeta"])
            self.assertEqual(fila["sectores"], reg["sectores"], fila["carpeta"])
            self.assertEqual(fila["relaciones"], reg["rel_tags"], fila["carpeta"])
            f = str(reg["fsort"] or "")
            self.assertEqual(fila["fecha"], "%s-%s-%s" % (f[:4], f[4:6], f[6:8]) if f else None, fila["carpeta"])

    def test_la_pagina_lleva_los_mismos_datos(self):
        html = (RAIZ / "conc" / "index.html").read_text(encoding="utf-8")
        m = re.search(r'<script id="anc-data" type="application/json">(.*?)</script>', html, re.S)
        self.assertIsNotNone(m)
        self.assertEqual(json.loads(m.group(1).replace("<\\/", "</")), self.conc,
                         "conc/index.html y data/conc.json difieren: correr generar_tablero.py")

    def test_agregados_salen_del_detalle(self):
        c, filas = self.conc, self.detalle
        n = len(filas)
        self.assertEqual(c["registros"], n)
        clave_de = {t: k["clave"] for k in c["anio_tipo"]["claves"] for t in k["tipos"]}
        anios = c["anio_tipo"]["anios"]
        # firmas por año y tipo (la ultima columna es «sin fecha»)
        esperado = {k["clave"]: [0] * (len(anios) + 1) for k in c["anio_tipo"]["claves"]}
        for f in filas:
            y = int(f["fecha"][:4]) if f["fecha"] else None
            i = y - anios[0] if y and anios[0] <= y <= anios[-1] else len(anios)
            esperado[clave_de.get(f["tipo"], "otros")][i] += 1
        for s in c["anio_tipo"]["series"]:
            self.assertEqual(s["valores"], esperado[s["clave"]], s["clave"])
        # decisiones
        cd = collections.Counter(f["grupo"] for f in filas)
        for g in c["decisiones"]["grupos"]:
            self.assertEqual(g["n"], cd.get(g["grupo"], 0), g["grupo"])
        self.assertEqual(sum(cd.values()), n)
        self.assertEqual(sum(v["n"] for v in c["decisiones"]["variantes"]), sum(1 for f in filas if f["decision"]))
        # sectores y relaciones
        cs = collections.Counter(s for f in filas for s in f["sectores"])
        for x in c["sectores"]["items"]:
            self.assertEqual(x["n"], cs[x["sector"]], x["sector"])
        self.assertEqual(c["sectores"]["total_sectores"], len(cs))
        self.assertEqual([x["n"] for x in c["sectores"]["catalogo"]][:-1], sorted([x["n"] for x in c["sectores"]["catalogo"]][:-1], reverse=True))
        cr = collections.Counter(t for f in filas for t in f["relaciones"])
        for x in c["relaciones"]:
            esp = sum(1 for f in filas if not f["relaciones"]) if x["relacion"] == "Sin dato" else cr[x["relacion"]]
            self.assertEqual(x["n"], esp, x["relacion"])
        # cobertura
        for x in c["cobertura"]:
            i = c["campos_cobertura"].index(x["campo"])
            self.assertEqual(x["n"], sum(1 for f in filas if (f["cob"] >> i) & 1), x["campo"])
        # tiempos
        dias = [f["dias"] for f in filas if f["dias"] is not None]
        self.assertTrue(all(d > 0 for d in dias))
        self.assertEqual(c["tiempos"]["n_global"], len(dias))
        self.assertEqual(c["tiempos"]["mediana_global"], mediana(dias))
        self.assertEqual(c["tiempos"]["cobertura_pct"], pct1(len(dias), n))
        self.assertEqual(c["kpi"]["mediana_dias"], mediana(dias))

    def test_el_detalle_es_publico(self):
        """Solo lo que el buscador ya publica: nada de empresas ni de texto libre ademas de la decision."""
        claves = {"carpeta", "fecha", "tipo", "decision", "grupo", "sectores", "relaciones", "dias", "cob"}
        for f in self.detalle:
            self.assertEqual(set(f), claves)


class BuscadorYOpisTest(unittest.TestCase):
    TRES_LINEAS = ('<link rel="stylesheet" href="assets/anc.css">', '<div id="anc-nav"></div>', '<script src="assets/nav.js" defer></script>')

    def test_buscador_y_plantilla_llevan_la_barra(self):
        html = (RAIZ / "index.html").read_text(encoding="utf-8")
        plantilla = (RAIZ / "generar_pagina.py").read_text(encoding="utf-8")
        for linea in self.TRES_LINEAS:
            self.assertEqual(html.count(linea), 1, "index.html: " + linea)
            self.assertEqual(plantilla.count(linea), 1, "generar_pagina.py: " + linea)
        # la barra va arriba del encabezado del buscador, antes que el contenido
        self.assertLess(html.index('<div id="anc-nav">'), html.index('<div class="bm-header">'))

    def test_opis_es_el_original_mas_tres_fragmentos(self):
        original = (RAIZ / "pdf" / "lectura_opi" / "buscador_opis.html").read_bytes().decode("utf-8")
        esperado, _ = io.integrar(original, "../assets", aviso=False)
        actual = (RAIZ / "opis" / "index.html").read_bytes().decode("utf-8")
        self.assertEqual(actual, esperado, "opis/index.html no es el original + la barra: correr 'python -B integrar_opis.py'")
        self.assertEqual(io.contar_registros(actual), io.contar_registros(original))


class DatosDeEjemploTest(unittest.TestCase):
    def test_los_fixtures_estan_marcados(self):
        for ruta in ("demo-interno/data/monitor.sample.json", "demo-interno/data/seguimiento.sample.json"):
            d = leer_json(ruta)
            self.assertEqual(d["origen"], "ejemplo", ruta)
            self.assertIn("EJEMPLO", d["aviso"], ruta)
            self.assertEqual(d["schema_version"], 2 if "seguimiento" in ruta else 1, ruta)
        for e in leer_json("demo-interno/data/seguimiento.sample.json")["expedientes"]:
            self.assertIn("(ejemplo)", e["operacion"])
            for persona in e["abogados"] + e["economistas"]:
                self.assertIn("(ejemplo)", persona)
        for o in leer_json("demo-interno/data/monitor.sample.json")["operaciones"]:
            self.assertIn("(ejemplo)", o["partes"])

    def sitio_chico(self, tmp):
        raiz = Path(tmp)
        (raiz / "data").mkdir()
        (raiz / "demo-interno" / "data").mkdir(parents=True)
        (raiz / "404.html").write_text("<!doctype html>", encoding="utf-8")
        return raiz

    def errores(self, res):
        return " | ".join(m for n, m in res if n == "ERROR")

    def test_el_verificador_rechaza_datos_reales_y_la_lista_negra(self):
        with tempfile.TemporaryDirectory() as tmp:
            raiz = self.sitio_chico(tmp)
            (raiz / "demo-interno" / "data" / "seguimiento_real.json").write_text(
                json.dumps({"schema_version": 2, "origen": "excel", "expedientes": []}), encoding="utf-8")
            (raiz / "demo-interno" / "data" / "monitor_raro.json").write_text(
                json.dumps({"schema_version": 1, "origen": "inventado", "operaciones": []}), encoding="utf-8")
            (raiz / "Res_firmadas.xlsm").write_bytes(b"x")
            (raiz / "notas.txt").write_text("clave sk-ant-" + "a" * 30, encoding="utf-8")
            # los origenes desconocidos y las claves son error en cualquier rama; el .xlsm, en main
            for rama in ("main", "otra-rama"):
                errores = self.errores(vs.verificar(raiz, rama=rama))
                for esperado in ("seguimiento_real.json", "monitor_raro.json", "notas.txt"):
                    self.assertIn(esperado, errores, rama)
            self.assertIn("Res_firmadas.xlsm", self.errores(vs.verificar(raiz, rama="main")))

    def test_el_monitor_real_solo_puede_estar_fuera_de_main(self):
        real = {"schema_version": 1, "origen": "artefacto", "exportado_el": "2026-10-15", "operaciones": [], "informes": []}
        with tempfile.TemporaryDirectory() as tmp:
            raiz = self.sitio_chico(tmp)
            (raiz / "demo-interno" / "data" / "monitor.json").write_text(json.dumps(real), encoding="utf-8")
            res = vs.verificar(raiz, rama="area-interna")
            self.assertEqual(self.errores(res), "")
            self.assertIn("monitor.json", " | ".join(m for n, m in res if n == "INFO"))
            self.assertIn("monitor.json", self.errores(vs.verificar(raiz, rama="main")))
            # el dist/ de la rama del area interna lo publica (detras de Access)
            self.assertNotIn("monitor.json", self.errores(vs.verificar(raiz, solo_dist=True, rama="area-interna")))
            # la pagina lee la version 1
            real["schema_version"] = 2
            (raiz / "demo-interno" / "data" / "monitor.json").write_text(json.dumps(real), encoding="utf-8")
            self.assertIn("schema_version", self.errores(vs.verificar(raiz, rama="area-interna")))

    def test_el_seguimiento_real_solo_puede_estar_fuera_de_main(self):
        real = {"schema_version": 2, "origen": "interno", "expedientes": []}
        with tempfile.TemporaryDirectory() as tmp:
            raiz = self.sitio_chico(tmp)
            (raiz / "demo-interno" / "data" / "seguimiento.json").write_text(json.dumps(real), encoding="utf-8")
            (raiz / "Res_firmadas.xlsm").write_bytes(b"x")
            # rama del area interna: pasa, y avisa con notas (INFO), no con errores ni avisos
            res = vs.verificar(raiz, rama="area-interna")
            self.assertEqual(self.errores(res), "")
            notas = " | ".join(m for n, m in res if n == "INFO")
            self.assertIn("seguimiento.json", notas)
            self.assertIn("Res_firmadas.xlsm", notas)
            # main: las dos cosas son error
            errores = self.errores(vs.verificar(raiz, rama="main"))
            self.assertIn("seguimiento.json", errores)
            self.assertIn("Res_firmadas.xlsm", errores)
            # dist/ armado (aunque no sea main): el JSON es lo que se publica detras de Access, el .xlsm jamas
            errores = self.errores(vs.verificar(raiz, solo_dist=True, rama="area-interna"))
            self.assertNotIn("seguimiento.json", errores)
            self.assertIn("Res_firmadas.xlsm", errores)

    def test_el_seguimiento_exige_la_version_que_lee_la_pagina(self):
        with tempfile.TemporaryDirectory() as tmp:
            raiz = self.sitio_chico(tmp)
            (raiz / "demo-interno" / "data" / "seguimiento.json").write_text(
                json.dumps({"schema_version": 1, "origen": "interno", "expedientes": []}), encoding="utf-8")
            self.assertIn("schema_version", self.errores(vs.verificar(raiz, rama="area-interna")))

    def test_el_sitio_pasa_la_compuerta(self):
        res = vs.verificar(RAIZ)
        self.assertEqual([m for n, m in res if n == "ERROR"], [])
        self.assertEqual([m for n, m in res if n == "AVISO"], [], "avisos de verificar_sitio.py (¿falta regenerar algo?)")


class PublicacionTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        salida = Path(tempfile.gettempdir()) / "dist_no_creado"
        cls.todos = bs.todos_los_archivos(RAIZ, salida)

    def seleccion(self, con_demo, con_legado=True):
        return bs.seleccionar(RAIZ, self.todos, con_demo, con_legado)

    def test_lista_blanca(self):
        sel = self.seleccion(con_demo=True)
        prohibido = re.compile(r"(\.py|\.md|\.xlsx|\.xlsm|\.jsonl|\.pyc|\.txt)$|(^|/)(\.git|varios|viejos|bot noticias|tests|escaneados)(/|$)")
        for rel in sel:
            if rel == "robots.txt":
                continue
            self.assertIsNone(prohibido.search(rel), rel + " no debería publicarse")
        for rel in ("index.html", "404.html", "_headers", "assets/anc.css", "assets/nav.js", "assets/charts.js", "assets/csv.js",
                    "opis/index.html", "conc/index.html", "herramientas/index.html", "data/conc.json",
                    "remedios/index.html", "remedios/relaciones.csv"):
            self.assertIn(rel, sel)

    def test_la_demo_no_llega_a_produccion(self):
        con = self.seleccion(con_demo=True)
        sin = self.seleccion(con_demo=False)
        self.assertTrue(any(r.startswith("demo-interno/") for r in con))
        self.assertFalse(any(r.startswith("demo-interno/") for r in sin))
        self.assertNotIn("demo-interno/data/seguimiento.json", sin)

    def test_sin_area_interna_en_produccion(self):
        nav = (RAIZ / "assets" / "nav.js").read_text(encoding="utf-8")
        self.assertEqual(nav.count("var INTERNO = true;"), 1)
        self.assertIn("var INTERNO = false;", bs.parchar_nav(nav, False))
        with self.assertRaises(SystemExit):
            bs.parchar_nav(nav.replace("var INTERNO = true;", ""), False)
        # un sitio chico sin la demo: con INTERNO = false pasa la compuerta; con INTERNO = true faltan sus paginas
        with tempfile.TemporaryDirectory() as tmp:
            raiz = Path(tmp)
            for carpeta in ("assets", "herramientas", "opis", "conc", "remedios", "data"):
                shutil.copytree(RAIZ / carpeta, raiz / carpeta)
            for archivo in ("index.html", "404.html"):
                shutil.copy(str(RAIZ / archivo), str(raiz / archivo))
            (raiz / "assets" / "nav.js").write_text(bs.parchar_nav(nav, False), encoding="utf-8")
            self.assertEqual([m for n, m in vs.verificar(raiz, solo_dist=True) if n == "ERROR"], [])
            (raiz / "assets" / "nav.js").write_text(nav, encoding="utf-8")
            self.assertTrue([m for n, m in vs.verificar(raiz, solo_dist=True) if n == "ERROR"])

    def test_urls_heredadas(self):
        sel = self.seleccion(con_demo=False)
        for rel in bs.LEGADO:
            if (RAIZ / rel).exists():
                self.assertIn(rel, sel)
        self.assertNotIn("pdf/lectura_opi/buscador_opis.html", self.seleccion(False, con_legado=False))


class SeguimientoTest(unittest.TestCase):
    """generar_seguimiento.py: lo que sale de la hoja evol_conc (casos ficticios; no se necesita el Excel)."""

    def test_caratula_resumida(self):
        casos = [
            ('ACME S.A. y OTRA S.A. S/ NOTIFICACION ART. 8\u00b0 DE LA LEy 25.156 (CONC. N\u00b0 1169)', "ACME S.A. y OTRA S.A."),
            ('"\xa0FOO S.A. S/NOTIFICACI\u00d3N ART.9 DE LA LEY 27.442\xa0" (CONC\xa02081)', "FOO S.A."),
            ("CONC.1711 - FOO S.A. e YPF S.A., S/NOTIFICACI\u00d3N ART. 9 DE LA LEY N\u00b0 27.442", "FOO S.A. e YPF S.A."),
            ('FOO ARGENTINA S.A.S/ NOTIFICACI\u00d3N ART.9 DE LA LEY 27.442 " (CONC 2118)', "FOO ARGENTINA S.A."),
            ('VISA X S/NOTIFICACI\u00d3N ART.9 DE LA LEY 27.442 (VISA OPEN LIMITED) " (CONC 2146)', "VISA X (VISA OPEN LIMITED)"),
            ("FOO S.A. S/NOTIF. ART. 8 LEY 25.156", "FOO S.A."),
            ("FOO S.A. (CONC. 1000)", "FOO S.A."),
            ("THE BAR\u2019S COMPANY S/NOTIFICACI\u00d3N ART.9 DE LA LEY 27.442", "THE BAR\u2019S COMPANY"),
        ]
        for original, esperado in casos:
            self.assertEqual(gs.resumir_caratula(original), esperado, original)
        largo = gs.resumir_caratula("EMPRESA NUMERO %s S.A. S/NOTIFICACI\u00d3N ART.9 DE LA LEY 27.442" % " ".join(["UNO"] * 60))
        self.assertTrue(largo.endswith("\u2026") and len(largo) <= gs.MAX_CARATULA, largo)
        self.assertEqual(gs.resumir_caratula(None), "")

    def test_apellidos_unificados(self):
        filas = [{"Abogado_1": "ZUVIRIA", "Abogado_2": "ROSOSZKA"}, {"Abogado_1": "ZUVIR\u00cdA", "Abogado_2": "ROSOZKA"},
                 {"Abogado_1": "ZUVIRIA", "Abogado_2": "Rososzka"}, {"Abogado_1": "ROZOSKA", "Abogado_2": "ROZOSKA"}]
        mostrar = gs.nombres_unicos(filas, ("Abogado_1", "Abogado_2"))
        self.assertEqual(sorted(mostrar.values()), ["Rososzka", "Zuvir\u00eda"])
        self.assertEqual(gs.equipo(filas[3], ("Abogado_1", "Abogado_2"), mostrar), ["Rososzka"])    # dos tipeos = una persona
        self.assertEqual(gs.equipo(filas[0], ("Abogado_1", "Abogado_2"), mostrar), ["Zuvir\u00eda", "Rososzka"])

    def test_en_tramite_es_la_definicion_del_excel(self):
        self.assertEqual(len(gs.ESTADOS_ACTIVOS), 8)
        for estado in ("En instrucci\u00f3n", "Suspendida", "TDC", "Para resoluci\u00f3n"):
            self.assertIn(estado, gs.ESTADOS_ACTIVOS)
        for estado in ("Firmada", "Apelada", "Subordinada en cumplimiento", "Archivo", "Desistida", "Acumulado"):
            self.assertNotIn(estado, gs.ESTADOS_ACTIVOS)

    def fila(self, **kw):
        base = {"ESTADO": "En instrucci\u00f3n", "Clave": "CONC 9001", "Carpeta": "9001",
                "Caratula": '"FOO S.A. S/NOTIFICACI\u00d3N ART.9 DE LA LEY 27.442" (CONC 9001)',
                "Fecha_Ingreso": dt.datetime(2026, 1, 15), "Fecha_firma": None, "Abogado_1": "PEREZ", "Abogado_2": "P\u00e9rez",
                "Economista_1": "GOMEZ", "Economista_2": None, "ES FT": "SI"}
        base.update(kw)
        return base

    def test_construir(self):
        filas = [
            self.fila(),
            self.fila(Clave="CONC 9002", ESTADO="TDC", Fecha_Ingreso=dt.datetime(2025, 5, 1), **{"ES FT": "NO"}),
            self.fila(Clave="CONC 9003", ESTADO="Firmada"),
            self.fila(Clave="CONC 9004", ESTADO="Apelada"),
            self.fila(Clave="CONC 9005", ESTADO=None),
            self.fila(Clave="CONC 9006", Fecha_Ingreso=None),
            self.fila(Clave="CONC 9007", ESTADO="Suspendida", Fecha_firma=dt.datetime(2026, 6, 30), **{"ES FT": None}),
        ]
        d = gs.construir(filas, dt.date(2026, 10, 9), total_excel=3, corte_excel=dt.date(2026, 10, 1))
        self.assertEqual((d["schema_version"], d["origen"], d["corte"], d["excel_corte"]), (2, "interno", "2026-10-09", "2026-10-01"))
        self.assertEqual([e["id"] for e in d["expedientes"]], ["CONC-9002", "CONC-9001", "CONC-9007"])     # por ingreso
        por_id = {e["id"]: e for e in d["expedientes"]}
        self.assertEqual(por_id["CONC-9001"], {"id": "CONC-9001", "operacion": "FOO S.A.", "abogados": ["P\u00e9rez"],
                                               "economistas": ["Gomez"], "tipo": "PROSUM", "estado": "En instrucci\u00f3n",
                                               "ingreso": "2026-01-15"})
        self.assertEqual(por_id["CONC-9002"]["tipo"], "Ordinario")
        self.assertEqual(por_id["CONC-9007"]["tipo"], "Sin dato")
        avisos = " | ".join(d["avisos"])
        self.assertIn("CONC-9005", avisos)           # sin estado: no se cuenta, pero se avisa
        self.assertIn("CONC-9006", avisos)           # sin fecha de ingreso: no se muestra, pero se avisa
        self.assertIn("CONC-9007", avisos)           # en tramite con fecha de firma: se cuenta, pero se avisa
        self.assertIn("guard\u00f3 3 activas", avisos)   # el Excel dice 3 y hay 4 con estado activo (9006 incluida)

    def test_escribir_un_expediente_por_linea(self):
        d = gs.construir([self.fila(), self.fila(Clave="CONC 9002")], dt.date(2026, 10, 9))
        with tempfile.TemporaryDirectory() as tmp:
            destino = Path(tmp) / "sub" / "seguimiento.json"
            gs.escribir(d, destino)
            texto = destino.read_text(encoding="utf-8")
            self.assertEqual(json.loads(texto), json.loads(json.dumps(d)))
            self.assertEqual(sum(1 for l in texto.splitlines() if '"operacion"' in l), 2)

    def test_el_seguimiento_versionado_es_coherente(self):
        ruta = RAIZ / "demo-interno" / "data" / "seguimiento.json"
        if not ruta.exists():
            self.skipTest("no hay seguimiento.json (solo existe en la rama del \u00e1rea interna)")
        d = leer_json("demo-interno/data/seguimiento.json")
        self.assertEqual((d["schema_version"], d["origen"]), (2, "interno"))
        ids = [e["id"] for e in d["expedientes"]]
        self.assertEqual(len(ids), len(set(ids)), "expedientes repetidos")
        for e in d["expedientes"]:
            self.assertIn(e["estado"], d["estados"], e["id"])
            self.assertIn(e["tipo"], ("PROSUM", "Ordinario", "Sin dato"), e["id"])
            self.assertRegex(e["ingreso"], r"^\d{4}-\d{2}-\d{2}$")
            self.assertTrue(e["abogados"] or e["economistas"], e["id"] + " sin equipo")
            self.assertLessEqual(len(e["operacion"]), gs.MAX_CARATULA, e["id"])
            self.assertNotRegex(e["operacion"].upper(), r"NOTIF|LEY\s*\d|CONC\.?\s*\d", e["id"] + ": la car\u00e1tula conserva texto de la notificaci\u00f3n")
            for persona in e["abogados"] + e["economistas"]:
                self.assertEqual(persona, persona.strip())


# El Excel llega por mail y se guarda fuera del repo: se busca igual que actualizar_sitio.py (variable ANC_RES_FIRMADAS,
# ~/.anc_sitio.json, el mas nuevo de Descargas o junto a los scripts).
EXCEL_SEGUIMIENTO = aus.resolver_res_firmadas()[0]


@unittest.skipUnless(__import__("importlib").util.find_spec("openpyxl")
                     and EXCEL_SEGUIMIENTO.is_file() and (RAIZ / "demo-interno" / "data" / "seguimiento.json").exists(),
                     "requiere openpyxl, Res_firmadas.xlsm (ANC_RES_FIRMADAS o ~/.anc_sitio.json) y demo-interno/data/seguimiento.json")
class RegenerarSeguimientoTest(unittest.TestCase):
    def test_el_seguimiento_versionado_es_el_que_sale_del_excel(self):
        viejo = leer_json("demo-interno/data/seguimiento.json")
        filas, total, corte_excel = gs.leer_excel(EXCEL_SEGUIMIENTO)
        nuevo = json.loads(json.dumps(gs.construir(filas, dt.date.fromisoformat(viejo["corte"]), total, corte_excel)))
        self.assertEqual(nuevo, viejo, "Res_firmadas.xlsm cambi\u00f3: correr 'python -B generar_seguimiento.py'")


class ActualizarSitioTest(unittest.TestCase):
    """actualizar_sitio.py: el orden de los pasos, de donde sale el Excel y que monitor acepta."""

    def test_orden_de_los_pasos(self):
        claves = [c for c, _, _ in aus.pasos(False, Path("x.xlsm"), monitor="m.json")]
        self.assertEqual(claves, ["pagina", "tablero", "seguimiento", "monitor", "verificar", "pruebas", "comparar"])
        claves = [c for c, _, _ in aus.pasos(False, Path("x.xlsm"), con_seguimiento=False)]
        self.assertEqual(claves, ["pagina", "tablero", "verificar", "pruebas", "comparar"])
        # en main no se generan datos internos, aunque se pida
        claves = [c for c, _, _ in aus.pasos(True, Path("x.xlsm"), monitor="m.json")]
        self.assertEqual(claves, ["pagina", "tablero", "verificar", "pruebas", "comparar"])
        seg = [a for c, _, a in aus.pasos(False, Path("C:/Users/yo/Downloads/Res.xlsm")) if c == "seguimiento"][0]
        self.assertEqual(seg[-2:], ["--excel", str(Path("C:/Users/yo/Downloads/Res.xlsm"))])

    def bajados(self, carpeta, nombres):
        """Crea archivos vacios con fechas de modificacion crecientes (el ultimo es el mas nuevo)."""
        carpeta.mkdir(parents=True, exist_ok=True)
        for i, nombre in enumerate(nombres):
            f = carpeta / nombre
            f.write_bytes(b"x")
            os.utime(str(f), (1_700_000_000 + i * 3600,) * 2)
        return carpeta

    def test_el_excel_mas_nuevo_de_descargas(self):
        with tempfile.TemporaryDirectory() as tmp:
            dl = self.bajados(Path(tmp) / "Downloads",
                              ["Res_firmadas.xlsm", "res_firmadas (1).xlsm", "Res_firmadas_13-10.xlsx",
                               "otro.xlsm", "Res_firmadas.pdf", "~$Res_firmadas.xlsm"])
            self.assertEqual(aus.ultimo_descargado([dl]).name, "Res_firmadas_13-10.xlsx")
            os.utime(str(dl / "res_firmadas (1).xlsm"), (1_800_000_000,) * 2)          # el adjunto de hoy
            self.assertEqual(aus.ultimo_descargado([dl, Path(tmp) / "Descargas"]).name, "res_firmadas (1).xlsm")
            self.assertIsNone(aus.ultimo_descargado([Path(tmp) / "no-existe"]))
            vacia = Path(tmp) / "vacia"
            vacia.mkdir()
            self.assertIsNone(aus.ultimo_descargado([vacia]))

    def test_de_donde_sale_el_excel(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            dl = self.bajados(tmp / "Downloads", ["Res_firmadas (2).xlsm"])
            guardado = self.bajados(tmp / "ANC", ["Res_firmadas.xlsm"]) / "Res_firmadas.xlsm"
            cfg = {"res_firmadas": str(guardado)}
            env = {"ANC_RES_FIRMADAS": "/otra/env.xlsm"}
            defecto = Path("/repo/Res_firmadas.xlsm")

            def r(arg, env, cfg, descargas=(dl,)):
                return aus.resolver_res_firmadas(arg, env, cfg, defecto, list(descargas))
            self.assertEqual(r("/otra/arg.xlsm", env, cfg)[0], Path("/otra/arg.xlsm"))
            self.assertEqual(r(None, env, cfg)[0], Path("/otra/env.xlsm"))
            self.assertEqual(r(None, {}, cfg)[0], guardado)
            self.assertEqual(r(None, {}, {}), (dl / "Res_firmadas (2).xlsm", "el más nuevo de Descargas"))
            # la ruta guardada ya no existe: avisa y sigue con Descargas
            ruta, fuente = r(None, {}, {"res_firmadas": str(tmp / "borrado.xlsm")})
            self.assertEqual(ruta, dl / "Res_firmadas (2).xlsm")
            self.assertIn("ya no existe", fuente)
            self.assertEqual(r(None, {}, {}, descargas=()), (defecto, "junto al script"))
            # un archivo de Descargas no se recuerda (taparía al próximo adjunto); uno de otra carpeta, sí
            self.assertTrue(aus.en_descargas(dl / "Res_firmadas (2).xlsm", [dl]))
            self.assertFalse(aus.en_descargas(guardado, [dl]))

    def test_frena_datos_internos_sueltos_en_el_repo(self):
        entradas = ["?? Res_firmadas (1).xlsm", "?? varios/cotejo_x.xlsx", "?? notas.txt", " M index.html",
                    "?? res_firmadas_13-10.XLSM", "?? conc/index.html", ""]
        self.assertEqual(aus.internos_sueltos(entradas),
                         ["Res_firmadas (1).xlsm", "varios/cotejo_x.xlsx", "res_firmadas_13-10.XLSM"])
        self.assertEqual(aus.internos_sueltos([" M Res_firmadas.xlsm", "A  evol_conc.csv"]), [], "solo los sin versionar")

    def monitor(self, **cambios):
        doc = {"schema_version": 1, "origen": "artefacto", "exportado_el": "2026-10-15", "parametros": {},
               "informes": [{"id": "2026-10-15", "fecha": "2026-10-15", "total": 1}],
               "operaciones": [{"id": "a-b-2026", "fecha": "2026-10-10", "partes": "A / B", "tipo": "Adquisición",
                                "estado": "confirmada", "relevanteANC": True, "verificacion": "pendiente"}]}
        doc.update(cambios)
        return doc

    def test_que_monitor_acepta(self):
        self.assertEqual(aus.validar_monitor(self.monitor()), ([], []))
        for malo in (self.monitor(origen="ejemplo"), self.monitor(schema_version=2), self.monitor(exportado_el="15/10/2026"),
                     self.monitor(operaciones=None), [1, 2]):
            self.assertTrue(aus.validar_monitor(malo)[0], malo)
        # campos faltantes o valores raros: se copia igual, con avisos (las mismas reglas que monitor_merge.py)
        dudoso = self.monitor(operaciones=[{"id": "x", "fecha": "2026-10-10", "partes": "X", "tipo": "Otra",
                                            "estado": "probable", "relevanteANC": True}])
        errores, avisos = aus.validar_monitor(dudoso)
        self.assertEqual(errores, [])
        self.assertTrue(any("estado" in a for a in avisos) and any("verificacion" in a for a in avisos), avisos)

    def test_copiar_monitor(self):
        with tempfile.TemporaryDirectory() as tmp:
            origen, destino = Path(tmp) / "bajado.json", Path(tmp) / "data" / "monitor.json"
            origen.write_text(json.dumps(self.monitor()), encoding="utf-8-sig")      # con BOM, como lo puede dejar Windows
            with contextlib.redirect_stdout(_io.StringIO()):
                self.assertEqual(aus.copiar_monitor(origen, destino), 0)
            self.assertEqual(json.loads(destino.read_text(encoding="utf-8")), self.monitor())
            origen.write_text(json.dumps(self.monitor(origen="ejemplo")), encoding="utf-8")
            with contextlib.redirect_stdout(_io.StringIO()):
                self.assertEqual(aus.copiar_monitor(origen, destino), 1)
            self.assertEqual(json.loads(destino.read_text(encoding="utf-8"))["origen"], "artefacto", "no se pisa con uno malo")

    def test_recordatorio_del_monitor(self):
        with tempfile.TemporaryDirectory() as tmp:
            ruta = Path(tmp) / "monitor.json"
            self.assertIn("ejemplo", aus.recordatorio_monitor(dt.date(2026, 10, 20), ruta))
            ruta.write_text(json.dumps(self.monitor()), encoding="utf-8")
            self.assertIsNone(aus.recordatorio_monitor(dt.date(2026, 10, 20), ruta))
            self.assertIn("hace 17 días", aus.recordatorio_monitor(dt.date(2026, 11, 1), ruta))

    def test_la_pagina_de_noticias_pide_el_monitor_real_y_cae_al_ejemplo(self):
        txt = (RAIZ / "demo-interno" / "noticias" / "index.html").read_text(encoding="utf-8")
        self.assertIn("var DATA_REAL = '../data/monitor.json';", txt)
        self.assertIn("var DATA_URL = '../data/monitor.sample.json';", txt)
        self.assertRegex(txt, r"pedir\(DATA_REAL\)\.catch\(function \(e\) \{\s*if \(e\.status === 404\) return pedir\(DATA_URL\);")

    def test_el_monitor_versionado_es_coherente(self):
        ruta = RAIZ / "demo-interno" / "data" / "monitor.json"
        if not ruta.exists():
            self.skipTest("todavía no se subió un monitor real")
        self.assertEqual(aus.validar_monitor(leer_json("demo-interno/data/monitor.json"))[0], [])


@unittest.skipUnless(os.environ.get("ANC_TEST_REGENERAR") or __import__("importlib").util.find_spec("pandas"),
                     "requiere pandas (y firm.xlsx) para regenerar el tablero")
class RemediosTest(unittest.TestCase):
    def test_markdown_de_las_fichas(self):
        md = ("| | |\n|---|---|\n| **Partes** | A <b> & B |\n\n"
              "- uno **dos** *tres* `M.1_DEC_01`\n  sigue\n  - hijo\n    continúa\n\n  Párrafo del item.\n"
              "- **29/05 (`x`):** fin\n\n### P1 — Mercado\n\nTexto *market test*.")
        h = gr.md_a_html(md)
        self.assertIn('<th scope="row">Partes</th><td>A &lt;b&gt; &amp; B</td>', h)
        self.assertNotIn("<thead>", h)
        self.assertIn("<li>uno <strong>dos</strong> <em>tres</em> <code>M.1_DEC_01</code> sigue"
                      "<ul><li>hijo continúa</li></ul><p>Párrafo del item.</p></li>", h)
        self.assertIn("<li><strong>29/05 (<code>x</code>):</strong> fin</li>", h)
        self.assertIn('<h3 id="p1">P1 — Mercado</h3>', h)
        self.assertIn("<p>Texto <em>market test</em>.</p>", h)
        self.assertNotRegex(h, r"[*`]")

    def test_remedios_versionado_es_el_que_sale_de_las_fichas(self):
        salida = gr.construir(RAIZ)
        self.assertEqual(gr.diferencias(RAIZ, salida), [], "correr 'python -B generar_remedios.py'")
        self.assertEqual(salida, gr.construir(RAIZ), "la salida no es determinista")
        fichas = sorted(p.stem for p in (RAIZ / "remedios_ue" / "fichas").glob("M.*.md"))
        paginas = sorted(r.split("/")[1].replace("-", ".") for r in salida if r.count("/") == 2)
        self.assertEqual(paginas, fichas)
        indice = salida["remedios/index.html"].decode("utf-8")
        self.assertEqual(indice.count('class="anc-tool"'), len(fichas))
        self.assertIn('<meta name="remedios-huella" content="%s">' % vs.huella_remedios(RAIZ), indice)

    def test_aviso_si_cambia_una_ficha(self):
        with tempfile.TemporaryDirectory() as tmp:
            raiz = Path(tmp)
            (raiz / "remedios_ue" / "fichas").mkdir(parents=True)
            shutil.copy(str(RAIZ / "remedios_ue" / "casos.csv"), str(raiz / "remedios_ue" / "casos.csv"))
            for f in (RAIZ / "remedios_ue" / "fichas").glob("*.*"):
                shutil.copy(str(f), str(raiz / "remedios_ue" / "fichas" / f.name))
            shutil.copytree(str(RAIZ / "remedios"), str(raiz / "remedios"))
            aviso = lambda: [m for n, m in vs.verificar(raiz, solo_dist=True) if "generar_remedios" in m]
            self.assertEqual(aviso(), [])
            ficha = next((raiz / "remedios_ue" / "fichas").glob("M.*.md"))
            ficha.write_text(ficha.read_text(encoding="utf-8") + "\nUna línea nueva.\n", encoding="utf-8")
            self.assertEqual(len(aviso()), 1)

    def test_barra_mapa_y_publicacion(self):
        nav = (RAIZ / "assets" / "nav.js").read_text(encoding="utf-8")
        self.assertIn("h: 'remedios/'", nav)
        self.assertIn("rel.indexOf('remedios/') === 0) best = 'remedios'", nav)
        self.assertIn('href="../remedios/"', (RAIZ / "herramientas" / "index.html").read_text(encoding="utf-8"))
        self.assertIn("remedios", bs.CARPETAS)

    @unittest.skipUnless(shutil.which("git"), "sin git")
    def test_aditivo_gitignore_y_lo_que_main_revirtio(self):
        with tempfile.TemporaryDirectory() as tmp:
            raiz = Path(tmp)

            def git(*args):
                subprocess.run(["git", "-C", tmp, "-c", "user.name=t", "-c", "user.email=t@t", *args],
                               check=True, capture_output=True)

            def commit(**archivos):
                for nombre, texto in archivos.items():
                    (raiz / nombre.replace("_", ".")).write_text(texto, encoding="utf-8")
                git("add", "-A")
                git("commit", "-q", "-m", "x")

            git("init", "-q")
            git("checkout", "-q", "-b", "main")
            commit(_gitignore="a\n", viejo_txt="x\n")
            git("checkout", "-q", "-b", "rama")
            commit(nuevo_txt="1\n")
            git("checkout", "-q", "main")
            git("merge", "-q", "--no-ff", "rama", "-m", "merge")
            git("rm", "-q", "nuevo.txt")
            git("commit", "-q", "-m", "revertir")          # main revierte el merge de la rama
            git("checkout", "-q", "rama")
            commit(_gitignore="a\nb\n", nuevo_txt="2\n")
            errores = lambda: [m for n, m in vs.verificar(raiz, aditivo=True, rama="rama") if n == "ERROR"]
            self.assertEqual(errores(), [])
            commit(viejo_txt="y\n")
            self.assertEqual(len(errores()), 1)
            commit(_gitignore="b\n", viejo_txt="x\n")
            self.assertEqual(len(errores()), 1)
            self.assertIn(".gitignore", errores()[0])
            commit(_gitignore="a\nb\n")
            git("mv", "viejo.txt", "otro.txt")
            git("commit", "-q", "-m", "renombrar")         # renombrar algo de main tambien lo modifica
            self.assertEqual(len(errores()), 1)
            self.assertIn("viejo.txt", errores()[0])


class RegenerarTest(unittest.TestCase):
    def test_el_tablero_versionado_es_el_que_sale_de_firm_xlsx(self):
        import generar_tablero as gt
        nuevo = gt.construir()
        viejo = leer_json("data/conc.json")
        for d in (nuevo, viejo):
            d.pop("generado", None)
        nuevo = json.loads(json.dumps(nuevo, ensure_ascii=False))     # mismo tratamiento que al escribir el archivo
        self.assertEqual(nuevo["corpus"], viejo["corpus"], "firm.xlsx cambió: correr 'python -B generar_tablero.py'")
        self.assertEqual(nuevo, viejo, "data/conc.json no es el que sale de firm.xlsx: correr 'python -B generar_tablero.py'")


if __name__ == "__main__":
    unittest.main()
