"""Pruebas con PDF reales generados en memoria, sin red ni API."""
from __future__ import annotations

import csv
import importlib.util
import io
import json
import shutil
import tempfile
import unittest
from collections import Counter
from contextlib import redirect_stdout, redirect_stderr
from email.message import Message
from pathlib import Path
from unittest.mock import patch

import pymupdf

SPEC = importlib.util.spec_from_file_location("extraer_texto", Path(__file__).resolve().parents[1] / "extraer_texto.py")
extractor = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(extractor)


class ExtractionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "descargas_anc"
        self.root.mkdir()
        self.out = self.root / "texto_extraido"
        self.rows = []

    def pdf(self, name="uno.pdf", pages=None, image_page=False, encrypted=False):
        path = self.root / "archivos" / "M_10646" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        with pymupdf.open() as doc:
            for text in pages or ["The Commission examined the competition concerns and the proposed commitments."]:
                page = doc.new_page(width=600, height=800)
                if text:
                    page.insert_text((50, 50), text)
            if image_page:
                # Imagen que ocupa la página: un escaneo con encabezado digital breve.
                page = doc.new_page(width=600, height=800)
                pixmap = pymupdf.Pixmap(pymupdf.csRGB, (0, 0, 8, 8), False)
                pixmap.clear_with(200)
                page.insert_image(page.rect, stream=pixmap.tobytes("png"), keep_proportion=False)
                page.insert_text((40, 40), "Public version")
            doc.set_page_labels([{"startpage": 0, "prefix": "", "style": "r", "firstpagenum": 1}])
            kwargs = {"encryption": pymupdf.PDF_ENCRYPT_AES_256, "owner_pw": "owner", "user_pw": "user"} if encrypted else {}
            doc.save(path, **kwargs)
        return path

    def row(self, path, key="doc-1", case="M.10646", **values):
        row = {"documento_id": key, "caso": case, "estado": "descargado",
               "archivo": path.relative_to(self.root).as_posix(), "sha256": extractor.digest(path),
               "formato_real": "pdf", "titulo": "Decisión y compromisos",
               "url_origen": "https://example.org/decision.pdf", "url_final": "https://example.org/decision.pdf",
               "idioma": "EN", "grupo": "nucleo", "tipo_documental": "decision"}
        row.update(values)
        self.rows.append(row)
        return row

    def report(self):
        fields = sorted(set().union(*(r.keys() for r in self.rows)))
        with (self.root / "reporte.csv").open("w", encoding="utf-8-sig", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fields)
            writer.writeheader()
            writer.writerows(self.rows)

    def run_cli(self, *args):
        self.report()
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            return extractor.main(["--entrada", str(self.root), *args])

    def documents(self):
        with (self.out / "documentos.csv").open(encoding="utf-8-sig", newline="") as f:
            return list(csv.DictReader(f))

    def data(self):
        return json.loads(next((self.out / "documentos").glob("*.json")).read_text())

    def test_pages_labels_source_and_text_are_preserved(self):
        self.row(self.pdf(pages=["Competition concerns in the relevant market.", "The remedy provides access for ten years."]))
        self.assertEqual(self.run_cli(), 0)
        data = self.data()
        self.assertEqual([p["pagina_pdf"] for p in data["paginas"]], [1, 2])
        self.assertEqual([p["etiqueta_pdf"] for p in data["paginas"]], ["i", "ii"])
        self.assertIn("Competition concerns", data["paginas"][0]["texto"])
        self.assertEqual(data["referencias"][0]["documento_id"], "doc-1")
        self.assertEqual(data["referencias"][0]["url_origen"], "https://example.org/decision.pdf")
        text = next((self.out / "documentos").glob("*.txt")).read_text()
        self.assertIn("[PÁGINA PDF 2 | etiqueta PDF: ii]", text)

    def test_shared_and_identical_pdf_extracted_once_all_references_kept(self):
        first = self.pdf()
        other = first.with_name("copia.pdf")
        shutil.copyfile(first, other)
        self.row(first)
        self.row(first, key="doc-2", case="M.10896")
        self.row(other, key="doc-3")
        with patch.object(extractor, "extract_pdf", wraps=extractor.extract_pdf) as call:
            self.assertEqual(self.run_cli(), 0)
            self.assertEqual(call.call_count, 1)
        self.assertEqual(len(self.data()["referencias"]), 3)
        self.assertEqual(len(self.documents()), 3)
        self.assertEqual(len({r["json"] for r in self.documents()}), 1)

    def test_verified_resume_does_not_extract_again(self):
        self.row(self.pdf())
        self.assertEqual(self.run_cli(), 0)
        with patch.object(extractor, "extract_pdf", side_effect=AssertionError("No debe extraer")):
            self.assertEqual(self.run_cli(), 0)
        self.assertEqual(self.documents()[0]["reutilizado"], "True")

    def test_corrupt_cached_text_is_regenerated(self):
        self.row(self.pdf())
        self.run_cli()
        next((self.out / "documentos").glob("*.txt")).write_text("corrupto")
        with patch.object(extractor, "extract_pdf", wraps=extractor.extract_pdf) as call:
            self.assertEqual(self.run_cli(), 0)
            self.assertEqual(call.call_count, 1)

    def test_changed_threshold_and_rehacer_invalidate_cache(self):
        self.row(self.pdf())
        self.run_cli()
        for options in [("--min-caracteres", "200"), ("--min-caracteres", "200", "--rehacer")]:
            with self.subTest(options=options), patch.object(extractor, "extract_pdf", wraps=extractor.extract_pdf) as call:
                self.assertEqual(self.run_cli(*options), 0)
                self.assertEqual(call.call_count, 1)

    def test_new_reference_updates_cache_without_extracting(self):
        path = self.pdf()
        self.row(path)
        self.run_cli()
        self.row(path, key="doc-2", case="M.10896")
        with patch.object(extractor, "extract_pdf", side_effect=AssertionError("No debe extraer")):
            self.assertEqual(self.run_cli(), 0)
        self.assertEqual(len(self.data()["referencias"]), 2)

    def test_mixed_scanned_and_blank_pages_are_flagged(self):
        self.row(self.pdf(pages=["The remedy removes the competition concerns.", ""], image_page=True))
        self.assertEqual(self.run_cli(), 0)
        pages = self.data()["paginas"]
        self.assertFalse(pages[0]["requiere_revision"])
        self.assertIn("sin_texto", pages[1]["alertas"])
        self.assertIn("imagen_con_texto_escaso", pages[2]["alertas"])
        self.assertTrue(pages[2]["posible_ocr"])
        self.assertEqual(self.documents()[0]["estado_extraccion"], "requiere_revision")

    # --- OCR opcional (--ocr) ---

    def run_ocr(self, *args, reconocido="(12) Texto reconocido por OCR", version="5.3.4"):
        calls = []
        motor = {"ejecutable": "tesseract", "version": version, "tessdata": None, "idiomas": ["eng", "fra"]}

        def fake_ocr(page, language, dpi, motor_ocr):
            calls.append((page.number + 1, language, dpi))
            self.assertEqual(motor_ocr, motor)
            if isinstance(reconocido, Exception):
                raise reconocido
            return reconocido
        with patch.object(extractor, "ocr_page", side_effect=fake_ocr), \
                patch.object(extractor, "tesseract_disponible", return_value=motor):
            return self.run_cli("--ocr", *args), calls

    def test_ocr_reads_only_image_or_empty_pages(self):
        self.row(self.pdf(pages=["The remedy removes the competition concerns.", ""], image_page=True), idioma="FR")
        code, calls = self.run_ocr()
        self.assertEqual(code, 0)
        self.assertEqual(calls, [(2, "fra", 300), (3, "fra", 300)])
        pages = self.data()["paginas"]
        self.assertEqual([p["origen_texto"] for p in pages], ["pdf", "ocr", "ocr"])
        self.assertIn("competition concerns", pages[0]["texto"])
        self.assertEqual(pages[2]["texto"], "(12) Texto reconocido por OCR")
        self.assertIn("texto_ocr", pages[2]["alertas"]); self.assertTrue(pages[2]["requiere_revision"])
        text = next((self.out / "documentos").glob("*.txt")).read_text()
        self.assertIn("[PÁGINA PDF 3 | etiqueta PDF: iii | texto OCR: verificar contra el PDF]", text)
        summary = json.loads((self.out / "resumen.json").read_text())
        self.assertEqual(summary["paginas_texto_ocr"], 2); self.assertTrue(summary["configuracion"]["ocr"])
        self.assertEqual(summary["configuracion"]["ocr_motor"], "tesseract 5.3.4 --psm 3 -c thresholding_method=2")
        self.assertIn("Tesseract", summary["nota"]); self.assertNotIn("No se ejecutó OCR", summary["nota"])

    def test_ocr_toggle_invalidates_cache(self):
        self.row(self.pdf(image_page=True))
        self.assertEqual(self.run_cli(), 0)
        self.assertEqual(self.data()["paginas"][1]["origen_texto"], "pdf")
        code, calls = self.run_ocr()
        self.assertEqual(code, 0); self.assertEqual(len(calls), 1)
        self.assertEqual(self.documents()[0]["reutilizado"], "False")
        self.assertEqual(self.data()["paginas"][1]["origen_texto"], "ocr")

    def test_tesseract_version_change_invalidates_cache(self):
        self.row(self.pdf(image_page=True))
        self.assertEqual(self.run_ocr()[0], 0)
        self.assertEqual(len(self.run_ocr()[1]), 0)  # misma versión: reutiliza
        code, calls = self.run_ocr(version="5.4.0")
        self.assertEqual(code, 0); self.assertEqual(len(calls), 1)

    def test_ocr_error_is_recorded_and_run_continues(self):
        self.row(self.pdf(image_page=True))
        code, _ = self.run_ocr(reconocido=RuntimeError("falta el idioma fra"))
        self.assertEqual(code, 0)
        page = self.data()["paginas"][1]
        self.assertEqual(page["origen_texto"], "pdf"); self.assertIn("error_ocr", page["alertas"])
        self.assertIn("falta el idioma", page["error"])

    def test_ocr_without_tesseract_is_a_configuration_error(self):
        self.row(self.pdf(image_page=True))
        self.report()
        with patch.object(extractor.shutil, "which", return_value=None), \
                redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()) as err:
            self.assertEqual(extractor.main(["--entrada", str(self.root), "--ocr"]), 1)
        self.assertIn("Tesseract", err.getvalue()); self.assertFalse(self.out.exists())

    @unittest.skipUnless(shutil.which("tesseract"), "Tesseract no está instalado")
    def test_real_tesseract_recovers_text_from_image_page(self):
        with pymupdf.open() as fuente:
            page = fuente.new_page(width=600, height=300)
            page.insert_text((40, 120), "(165) MARKET SHARES REMEDY", fontsize=28)
            png = page.get_pixmap(dpi=200).tobytes("png")
        path = self.root / "archivos" / "M_10646" / "imagen.pdf"
        path.parent.mkdir(parents=True, exist_ok=True)
        with pymupdf.open() as doc:
            doc.new_page(width=600, height=300).insert_image(pymupdf.Rect(0, 0, 600, 300), stream=png)
            doc.save(path)
        self.row(path)
        self.report()
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            self.assertEqual(extractor.main(["--entrada", str(self.root), "--ocr"]), 0)
        page = self.data()["paginas"][0]
        self.assertEqual(page["origen_texto"], "ocr"); self.assertIn("REMEDY", page["texto"].upper())

    @unittest.skipUnless(shutil.which("tesseract"), "Tesseract no está instalado")
    def test_real_tesseract_reads_table_cells_with_shaded_rows(self):
        # Como las tablas de cuotas de la Comisión: el OCR integrado de PyMuPDF solo leía el título.
        with pymupdf.open() as fuente:
            page = fuente.new_page(width=600, height=300)
            page.insert_text((60, 40), "Table 1 - Market shares (worldwide)", fontsize=14)
            rows = [("Supplier", "2024"), ("Safran", "[20-30]%"), ("Combined", "[60-70]%"), ("Parker", "[20-30]%")]
            for i, row in enumerate(rows):
                fill = (0.25, 0.65, 0.72) if i == 0 else (0.75, 0.75, 0.75) if row[0] == "Combined" else (0.95, 0.95, 0.95)
                for j, cell in enumerate(row):
                    x, y = 60 + j * 200, 60 + i * 40
                    page.draw_rect(pymupdf.Rect(x, y, x + 200, y + 40), color=(0, 0, 0), fill=fill, width=1)
                    page.insert_text((x + 40, y + 26), cell, fontsize=13)
            png = page.get_pixmap(dpi=150).tobytes("png")
        path = self.root / "archivos" / "M_10646" / "tabla.pdf"
        path.parent.mkdir(parents=True, exist_ok=True)
        with pymupdf.open() as doc:
            doc.new_page(width=600, height=300).insert_image(pymupdf.Rect(0, 0, 600, 300), stream=png)
            doc.save(path)
        self.row(path)
        self.report()
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            self.assertEqual(extractor.main(["--entrada", str(self.root), "--ocr"]), 0)
        text = self.data()["paginas"][0]["texto"]
        for expected in ("Safran", "Combined", "[60-70]%", "Parker"):
            self.assertIn(expected, text)

    def test_hash_mismatch_and_missing_files_reported(self):
        path = self.pdf()
        self.row(path, sha256="0" * 64)
        self.row(path, key="doc-2", archivo="archivos/no_existe.pdf")
        self.assertEqual(self.run_cli(), 2)
        self.assertEqual({r["estado_extraccion"] for r in self.documents()}, {"error_archivo"})

    def test_windows_relative_paths(self):
        row = self.row(self.pdf())
        row["archivo"] = row["archivo"].replace("/", "\\")
        self.assertEqual(self.run_cli(), 0)

    def test_report_cannot_point_outside_input(self):
        path = self.pdf()
        outside = self.root.parent / "outside.pdf"
        shutil.copyfile(path, outside)
        self.row(path, archivo="../outside.pdf")
        self.assertEqual(self.run_cli(), 2)
        self.assertIn("sale de", self.documents()[0]["detalle"])

    def test_nonpdf_and_encrypted_pdf_do_not_block_valid_file(self):
        bad = self.root / "falso.pdf"
        bad.write_text("<html>Access denied</html>")
        self.row(bad, key="html")
        self.row(self.pdf(name="protegido.pdf", encrypted=True), key="protected")
        self.row(self.pdf(name="normal.pdf"), key="good")
        self.assertEqual(self.run_cli(), 2)
        states = {r["documento_id"]: r["estado_extraccion"] for r in self.documents()}
        self.assertEqual(states, {"html": "error_extraccion", "protected": "error_extraccion", "good": "extraido"})

    def test_failed_download_and_html_are_preserved_as_omissions(self):
        path = self.pdf()
        self.row(path, estado="bloqueado", archivo="", sha256="")
        self.row(path, key="html", formato_real="html")
        self.assertEqual(self.run_cli(), 0)
        self.assertEqual({r["estado_extraccion"] for r in self.documents()}, {"omitido_descarga", "omitido_no_pdf"})

    def test_plan_has_no_output_and_does_not_extract(self):
        self.row(self.pdf())
        with patch.object(extractor, "extract_pdf", side_effect=AssertionError("No debe extraer")):
            self.assertEqual(self.run_cli("--plan"), 0)
        self.assertFalse(self.out.exists())

    def test_case_filter_and_unique_content_limit(self):
        path = self.pdf()
        self.row(path, case="M.10896")
        self.row(path, key="doc-2", case="M.10896")
        self.row(self.pdf(name="dos.pdf", pages=["Another decision with different competition concerns."]), key="doc-3", case="M.10896")
        self.row(self.pdf(name="tres.pdf"), key="doc-4")
        self.assertEqual(self.run_cli("--casos", "M.10896", "--limite", "1"), 0)
        states = Counter(r["estado_extraccion"] for r in self.documents())
        self.assertEqual(states, {"extraido": 2, "fuera_limite": 1})

    def test_invalid_report_and_unknown_case_fail(self):
        path = self.pdf()
        self.row(path)
        self.assertEqual(self.run_cli("--casos", "M.99999"), 1)
        self.row(path)
        self.assertEqual(self.run_cli(), 1)
        self.assertFalse(self.out.exists())

    def test_existing_lock_is_not_removed(self):
        self.row(self.pdf())
        self.out.mkdir()
        lock = self.out / ".extraccion.lock"
        lock.write_text("otro proceso")
        self.assertEqual(self.run_cli(), 1)
        self.assertEqual(lock.read_text(), "otro proceso")

    def test_running_downloader_is_respected(self):
        self.row(self.pdf())
        (self.root / ".descarga.lock").write_text("otro proceso")
        self.assertEqual(self.run_cli(), 1)
        self.assertFalse(self.out.exists())

    def test_image_inspection_failure_preserves_extracted_text(self):
        self.row(self.pdf())
        with patch.object(pymupdf.Page, "get_image_info", side_effect=RuntimeError("imagen inválida")):
            self.assertEqual(self.run_cli(), 0)
        page = self.data()["paginas"][0]
        self.assertIn("competition concerns", page["texto"])
        self.assertIn("error_deteccion_imagen", page["alertas"])
        self.assertFalse(page["posible_ocr"])

    def test_report_snapshot_is_identified_if_source_changes_during_run(self):
        self.row(self.pdf())
        real = extractor.extract_pdf
        original_sha = None

        def change_report(*args):
            nonlocal original_sha
            report = self.root / "reporte.csv"
            original_sha = extractor.digest(report)
            with report.open("a") as f:
                f.write("\n")
            return real(*args)

        with patch.object(extractor, "extract_pdf", side_effect=change_report):
            self.assertEqual(self.run_cli(), 2)
        summary = json.loads((self.out / "resumen.json").read_text())
        self.assertEqual(summary["sha256_reporte"], original_sha)
        self.assertTrue(summary["reporte_cambio_durante_corrida"])

    def test_active_downloader_report_is_compatible_end_to_end(self):
        # Usa el lector del inventario, el plan, la descarga y el reporte reales
        # de Claude 1.1.0. Solo sustituye la respuesta HTTP, con un PDF válido.
        spec = importlib.util.spec_from_file_location("active_downloader", Path(__file__).resolve().parents[1] / "descargar_remedios.py")
        downloader = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(downloader)
        payload = self.pdf().read_bytes()
        sha = extractor.digest(self.root / "archivos" / "M_10646" / "uno.pdf")
        inventory = self.root / "inventario.csv"
        fields = ["doc_id", "caso_id", "tipo_doc", "titulo", "url", "estado", "universo", "sha256", "paginas_compromisos", "ref"]
        base = {"caso_id": "M.10646", "titulo": "Decision with integrated commitments", "url": "https://example.org/decision.pdf",
                "estado": "localizado_pdf", "universo": "principal", "sha256": sha}
        rows = [
            {**base, "doc_id": "M.10646_DEC_01", "tipo_doc": "DEC", "sha256": "0" * 64},
            {**base, "doc_id": "M.10646_COMP_01", "tipo_doc": "COMP", "paginas_compromisos": "28-30"},
            {**base, "doc_id": "M.10646_CP_01", "tipo_doc": "CP", "url": "https://example.org/press", "ref": "IP/26/9999"},
            {**base, "doc_id": "M.11385_POST_01", "caso_id": "M.11385", "tipo_doc": "POST", "universo": "revisiones"},
        ]
        with inventory.open("w", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(f, fieldnames=fields)
            writer.writeheader()
            writer.writerows(rows)
        args = downloader.parser().parse_args(["--manifiesto", str(inventory), "--todos", "--incluir-revisiones", "--destino", str(self.root), "--pausa", "0"])
        manifest = downloader.read_manifest(inventory)
        selected, jobs, statuses = downloader.make_plan(manifest, args)
        instance = downloader.Downloader(args, selected, jobs, statuses)

        class Response(io.BytesIO):
            def __init__(self, content):
                super().__init__(content)
                self.headers = Message()
                self.headers["Content-Type"] = "application/pdf"
                self.headers["Content-Length"] = str(len(content))

            def getcode(self):
                return 200

            def geturl(self):
                return "https://example.org/decision.pdf"

        def open_response(request, **kwargs):
            if "presscorner" in request.full_url:
                raise downloader.urllib.error.HTTPError(request.full_url, 404, "not found", Message(), None)
            return Response(payload)

        with patch.object(instance.opener, "open", side_effect=open_response), redirect_stdout(io.StringIO()):
            self.assertEqual(instance.run(), 0)
        # No se reescribe el reporte: el extractor recibe el que generó Downloader.
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            self.assertEqual(extractor.main(["--entrada", str(self.root)]), 0)
        documents = {r["documento_id"]: r for r in self.documents()}
        self.assertEqual(documents["M.10646_DEC_01"]["coincide_inventario"], "no")
        self.assertEqual(documents["M.10646_DEC_01"]["estado_extraccion"], "requiere_revision")
        self.assertEqual(documents["M.10646_COMP_01"]["paginas_compromisos"], "28-30")
        self.assertEqual(documents["M.10646_CP_01"]["estado_descarga"], "sin_version_pdf")
        self.assertEqual(documents["M.10646_CP_01"]["estado_extraccion"], "omitido_descarga")
        self.assertEqual(documents["M.11385_POST_01"]["universo"], "revisiones")
        self.assertEqual(len(self.data()["referencias"]), 3)
        self.assertEqual(len(list((self.out / "documentos").glob("*.json"))), 1)
        # La referencia del anexo no recorta el archivo: también queda su página 1.
        self.assertEqual(self.data()["paginas"][0]["pagina_pdf"], 1)

    def test_interrupted_run_resumes_completed_documents(self):
        self.row(self.pdf())
        self.row(self.pdf(name="otro.pdf", pages=["Other concerns and commitments in this transaction."]), key="doc-2")
        real = extractor.extract_pdf
        calls = 0

        def interrupt(*args):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise KeyboardInterrupt
            return real(*args)

        with patch.object(extractor, "extract_pdf", side_effect=interrupt):
            self.assertEqual(self.run_cli(), 130)
        self.assertFalse((self.out / ".extraccion.lock").exists())
        self.assertEqual({r["estado_extraccion"] for r in self.documents()}, {"extraido", "interrumpido"})
        with patch.object(extractor, "extract_pdf", wraps=real) as call:
            self.assertEqual(self.run_cli(), 0)
            self.assertEqual(call.call_count, 1)


if __name__ == "__main__":
    unittest.main()
