# -*- coding: utf-8 -*-
"""
Compuertas de contenido del sitio (solo biblioteca estandar; el ultimo grupo usa pandas y se saltea si no esta).

Responden "¿lo que se va a publicar es coherente?" y fallan con un mensaje que dice que script volver a correr:

  - el tablero (data/conc.json y conc/index.html) corresponde al index.html publicado del buscador
  - los agregados del tablero salen del detalle por expediente
  - /opis/ es el buscador de OPIs original mas tres fragmentos de la barra, nada mas
  - el buscador y su plantilla llevan la barra comun
  - los datos de las demos estan marcados como ejemplo y el verificador rechaza datos reales
  - la lista blanca de build_site.py no deja pasar el Excel, los scripts ni los insumos internos
  - (si hay pandas) regenerar el tablero desde firm.xlsx da lo que esta versionado

Uso (desde la raiz del repo):
    python -B -m unittest discover -s tests -v
"""
import collections
import datetime as dt
import json
import math
import os
import re
import shutil
import statistics
import sys
import tempfile
import unittest
from pathlib import Path

sys.dont_write_bytecode = True      # los .pyc versionados no se reescriben
RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

import build_site as bs             # noqa: E402
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
            (raiz / "demo-interno" / "data" / "monitor.json").write_text(
                json.dumps({"schema_version": 1, "origen": "artefacto", "operaciones": []}), encoding="utf-8")
            (raiz / "Res_firmadas.xlsm").write_bytes(b"x")
            (raiz / "notas.txt").write_text("clave sk-ant-" + "a" * 30, encoding="utf-8")
            # el origen desconocido, el monitor real y las claves son error en cualquier rama; el .xlsm, en main
            for rama in ("main", "otra-rama"):
                errores = self.errores(vs.verificar(raiz, rama=rama))
                for esperado in ("seguimiento_real.json", "monitor.json", "notas.txt"):
                    self.assertIn(esperado, errores, rama)
            self.assertIn("Res_firmadas.xlsm", self.errores(vs.verificar(raiz, rama="main")))

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
                    "opis/index.html", "conc/index.html", "herramientas/index.html", "data/conc.json"):
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
            for carpeta in ("assets", "herramientas", "opis", "conc", "data"):
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


@unittest.skipUnless(__import__("importlib").util.find_spec("openpyxl")
                     and (RAIZ / "Res_firmadas.xlsm").exists() and (RAIZ / "demo-interno" / "data" / "seguimiento.json").exists(),
                     "requiere openpyxl, Res_firmadas.xlsm y demo-interno/data/seguimiento.json (rama del \u00e1rea interna)")
class RegenerarSeguimientoTest(unittest.TestCase):
    def test_el_seguimiento_versionado_es_el_que_sale_del_excel(self):
        viejo = leer_json("demo-interno/data/seguimiento.json")
        filas, total, corte_excel = gs.leer_excel(RAIZ / "Res_firmadas.xlsm")
        nuevo = json.loads(json.dumps(gs.construir(filas, dt.date.fromisoformat(viejo["corte"]), total, corte_excel)))
        self.assertEqual(nuevo, viejo, "Res_firmadas.xlsm cambi\u00f3: correr 'python -B generar_seguimiento.py'")


@unittest.skipUnless(os.environ.get("ANC_TEST_REGENERAR") or __import__("importlib").util.find_spec("pandas"),
                     "requiere pandas (y firm.xlsx) para regenerar el tablero")
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
