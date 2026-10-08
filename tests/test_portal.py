"""Compuertas de contenido para la entrega independiente del portal."""
import hashlib
import json
import re
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = "f7e4ce9f826cc8d24ad13fa35727a8341c5ec6e4"


class PortalContentTest(unittest.TestCase):
    def test_sources_and_existing_monthly_pipeline_are_unchanged(self):
        sources = ["index.html", "firm.xlsx", "generar_pagina.py", "comparar_index.py", "estado.py", "PROTOCOLO.md",
                   "nomenclador_mercados.py", "pdf/lectura_opi/buscador_opis.html", "pdf/lectura_opi/04_html.py"]
        for path in sources:
            with self.subTest(path=path):
                original = subprocess.check_output(["git", "show", f"{BASE}:{path}"], cwd=ROOT)
                self.assertEqual(original, (ROOT / path).read_bytes())

    def test_dashboard_represents_the_published_corpus(self):
        source = (ROOT / "index.html").read_text()
        original = json.loads(re.search(r'<script id="bm-data" type="application/json">(.*?)</script>', source, re.S).group(1))
        data = json.loads((ROOT / "data/conc.json").read_text())
        self.assertEqual(data["index_sha256"], hashlib.sha256((ROOT / "index.html").read_bytes()).hexdigest())
        self.assertEqual(len(original), len(data["registros"]))
        for published, actual in zip(original, data["registros"]):
            self.assertEqual(published["decision"], actual["decision"])
            self.assertEqual(published["tipo_cat"], actual["tipo"])
            self.assertEqual(published["sectores"], actual["sectores"])
            self.assertTrue(actual["dias"] is None or actual["dias"] >= 0)

    def test_opis_retains_its_own_data_and_search_logic(self):
        original = (ROOT / "pdf/lectura_opi/buscador_opis.html").read_text()
        integrated = (ROOT / "opis/index.html").read_text()
        original_scripts = re.findall(r'<script[^>]*>(.*?)</script>', original, re.S)
        integrated_scripts = re.findall(r'<script[^>]*>(.*?)</script>', integrated, re.S)
        self.assertEqual(original_scripts, integrated_scripts)
        self.assertIn('aria-current="page">OPIs</a>', integrated)

    def test_preview_excludes_internal_and_processing_files(self):
        output = ROOT / "public"
        self.assertTrue(output.is_dir(), "Ejecutar scripts/preparar_preview.py antes de verificar")
        allowed = {"index.html", "404.html", "googlea22b4e4d6a289f30.html", "_headers",
                   "assets/portal.css", "assets/portal.js", "herramientas/index.html", "opis/index.html",
                   "conc/index.html", "noticias/index.html", "seguimiento/index.html", "data/conc.json",
                   "data/monitor.sample.json", "data/seguimiento.sample.json"}
        for path in output.rglob("*"):
            if path.is_file():
                relative = path.relative_to(output).as_posix()
                self.assertTrue(relative in allowed or (path.parent == output / "pdf" and path.suffix.lower() == ".pdf"), relative)
        self.assertEqual((output / "index.html").read_bytes(), (ROOT / "index.html").read_bytes())
        for path in ["monitor.sample.json", "seguimiento.sample.json"]:
            self.assertIs(json.loads((output / "data" / path).read_text())["demo"], True)


if __name__ == "__main__":
    unittest.main()
