#!/usr/bin/env python3
"""Extrae texto por página de los PDF registrados por descargar_remedios.py.

Python 3.10+. Instalación: python -m pip install -r remedios_ue/requirements.txt
Uso: python remedios_ue/extraer_texto.py --entrada ruta/descargas_anc --limite 5
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from collections import Counter
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path, PureWindowsPath

VERSION = "1.2.0"
OPCIONES_TESSERACT = ("--psm", "3", "-c", "thresholding_method=2")  # segmentación automática, Sauvola
# Idioma del reporte -> idioma de Tesseract para el OCR opcional
IDIOMAS_OCR = {"EN": "eng", "FR": "fra", "DE": "deu", "ES": "spa", "IT": "ita", "NL": "nld", "PT": "por"}
SUCCESS = {"descargado", "ya_descargado", "contenido_reutilizado"}
REQUIRED = {"documento_id", "caso", "estado", "archivo", "sha256", "formato_real"}
DOCUMENT_FIELDS = (
    "documento_id", "caso", "universo", "titulo", "tipo_documental", "idioma", "grupo",
    "url_origen", "url_referencia", "url_final", "archivo", "estado_descarga", "sha256",
    "coincide_inventario", "paginas_compromisos",
    "estado_extraccion", "detalle", "paginas", "paginas_con_alerta",
    "paginas_posible_ocr", "json", "txt", "reutilizado",
)
PAGE_FIELDS = (
    "sha256", "casos", "documentos", "pagina_pdf", "etiqueta_pdf", "origen_texto",
    "caracteres", "caracteres_utiles", "cobertura_imagen_maxima",
    "posible_ocr", "requiere_revision", "alertas", "error", "json",
)


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def atomic_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as f:
            f.write(value)
        os.replace(name, path)
    finally:
        Path(name).unlink(missing_ok=True)


def atomic_json(path: Path, value: object) -> None:
    atomic_text(path, json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def write_csv(path: Path, fields: tuple, rows: list[dict]) -> None:
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=fields, extrasaction="ignore")
    writer.writeheader()
    writer.writerows(rows)
    atomic_text(path, "\ufeff" + output.getvalue())


def local_path(root: Path, relative: str) -> Path:
    """El reporte usa rutas relativas; admite separadores de Windows sin escapes."""
    win = PureWindowsPath(relative)
    if not relative or win.drive or win.root:
        raise ValueError("Se esperaba una ruta relativa dentro de --entrada")
    path = (root / relative.replace("\\", "/")).resolve()
    if not path.is_relative_to(root):
        raise ValueError("La ruta sale de la carpeta --entrada")
    return path


def read_report(path: Path) -> tuple[list[dict], str]:
    raw = path.read_bytes()
    reader = csv.DictReader(io.StringIO(raw.decode("utf-8-sig"), newline=""))
    missing = REQUIRED - set(reader.fieldnames or [])
    if missing:
        raise ValueError("Faltan columnas del reporte del descargador: " + ", ".join(sorted(missing)))
    rows = [{k: (v or "").strip() for k, v in row.items() if k is not None}
            for row in reader]
    ids = [row["documento_id"] for row in rows]
    if any(not key for key in ids) or len(ids) != len(set(ids)):
        raise ValueError("El reporte contiene documento_id vacíos o repetidos")
    return rows, hashlib.sha256(raw).hexdigest()


def make_plan(rows: list[dict], root: Path, cases: set[str], limit: int | None):
    """Valida el archivo contra su SHA publicado antes de relacionar sus fuentes."""
    selected = [r for r in rows if not cases or r["caso"].upper() in cases]
    if cases - {r["caso"].upper() for r in rows}:
        raise ValueError("Casos ausentes del reporte: " + ", ".join(sorted(cases - {r['caso'].upper() for r in rows})))
    if not selected:
        raise ValueError("El reporte no contiene filas para la selección")
    results, jobs, checked = {}, {}, {}
    for row in selected:
        result = {**row, "estado_descarga": row["estado"], "estado_extraccion": "omitido_descarga",
                  "detalle": "Estado de descarga: " + row["estado"]}
        results[row["documento_id"]] = result
        if row["estado"] not in SUCCESS:
            continue
        if row["formato_real"].lower() != "pdf":
            result.update(estado_extraccion="omitido_no_pdf", detalle="Esta etapa procesa PDF; se conserva la referencia")
            continue
        try:
            path = local_path(root, row["archivo"])
            if path not in checked:
                checked[path] = digest(path)
            sha = checked[path]
            if not re.fullmatch(r"[0-9a-fA-F]{64}", row["sha256"]) or sha != row["sha256"].lower():
                raise ValueError("El SHA-256 no coincide con el reporte; verificá o repetí la descarga")
        except (OSError, ValueError) as e:
            result.update(estado_extraccion="error_archivo", detalle=str(e))
            continue
        job = jobs.setdefault(sha, {"sha256": sha, "path": path, "referencias": []})
        job["referencias"].append(row)
        result.update(estado_extraccion="pendiente", detalle="")
    chosen = list(jobs.values())
    if limit is not None:
        for job in chosen[limit:]:
            for row in job["referencias"]:
                results[row["documento_id"]].update(estado_extraccion="fuera_limite", detalle="Fuera de --limite")
        chosen = chosen[:limit]
    return selected, results, chosen


def ocr_idiomas(referencias: list[dict]) -> str:
    """Idiomas de Tesseract para un PDF, según el idioma de sus filas del reporte."""
    codes = sorted({IDIOMAS_OCR[r.get("idioma", "").upper()] for r in referencias
                    if r.get("idioma", "").upper() in IDIOMAS_OCR})
    return "+".join(codes) or "eng"


def ocr_page(page, language: str, dpi: int, motor: dict) -> str:
    """Texto de la página por OCR: el ejecutable de Tesseract sobre la página renderizada.
    No se usa el OCR integrado de PyMuPDF (get_textpage_ocr) porque no lee las celdas de
    las tablas, que es lo que más hay en las páginas-imagen (cuotas de mercado). La
    binarización de Sauvola lee además las filas con fondo de color (totales, encabezados)."""
    png = page.get_pixmap(dpi=dpi).tobytes("png")
    command = [motor["ejecutable"], "stdin", "stdout", *OPCIONES_TESSERACT, "-l", language]
    if motor.get("tessdata"):
        command += ["--tessdata-dir", motor["tessdata"]]
    result = subprocess.run(command, input=png, capture_output=True, timeout=600)
    if result.returncode != 0:
        detail = result.stderr.decode("utf-8", "replace").strip()
        raise RuntimeError(detail or f"Tesseract terminó con código {result.returncode}")
    return result.stdout.decode("utf-8", "replace")


def tesseract_disponible(ejecutable: str | None, tessdata: str | None) -> dict:
    """Ubica Tesseract y el idioma eng antes de empezar: sin ellos, --ocr es un error de
    configuración. Otro idioma que falte queda como error_ocr en sus páginas."""
    help_text = ("Instalalo con los idiomas eng y fra (en Windows, el instalador de UB Mannheim) "
                 "o indicá el ejecutable con --tesseract y la carpeta de idiomas con --tessdata.")
    path = shutil.which(ejecutable or "tesseract")
    if not path:
        raise ValueError("No se encontró Tesseract para --ocr. " + help_text)
    extra = ["--tessdata-dir", tessdata] if tessdata else []
    try:
        version = subprocess.run([path, "--version"], capture_output=True, text=True, timeout=60)
        langs = subprocess.run([path, "--list-langs", *extra], capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.SubprocessError) as e:
        raise ValueError(f"No se pudo ejecutar Tesseract ({path}): {e}. " + help_text) from e
    available = set(langs.stdout.splitlines()[1:])
    if "eng" not in available:
        raise ValueError(f"Tesseract ({path}) no tiene el idioma eng. " + help_text)
    first = (version.stdout or version.stderr).split()
    return {"ejecutable": path, "version": first[1] if len(first) > 1 else "desconocida",
            "tessdata": tessdata, "idiomas": sorted(available)}


def page_data(page, minimum: int, ocr: dict | None = None) -> dict:
    label = page.get_label() or None
    record = {"pagina_pdf": page.number + 1, "etiqueta_pdf": label, "origen_texto": "pdf",
              "texto": "", "caracteres": 0, "caracteres_utiles": 0,
              "cobertura_imagen_maxima": 0.0, "posible_ocr": False,
              "requiere_revision": False, "alertas": []}
    try:
        text = page.get_text("text", sort=True)
        useful = sum(c.isalnum() for c in text)
        record.update(texto=text, caracteres=len(text), caracteres_utiles=useful)
    except Exception as e:
        record.update(requiere_revision=True, alertas=["error_pagina"], error=str(e))
        return record
    alerts = []
    coverage = 0.0
    try:
        rect = page.rect
        area = rect.width * rect.height
        coverage = max((max(0, min(rect.x1, image["bbox"][2]) - max(rect.x0, image["bbox"][0])) *
                        max(0, min(rect.y1, image["bbox"][3]) - max(rect.y0, image["bbox"][1])) / area
                        for image in page.get_image_info()), default=0.0) if area > 0 else 0.0
    except Exception as e:
        alerts.append("error_deteccion_imagen")
        record["error"] = str(e)
    quality = []
    if useful == 0:
        quality.append("sin_texto")
    elif useful < minimum:
        quality.append("texto_escaso")
    if coverage >= 0.5 and useful < 200:
        quality.append("imagen_con_texto_escaso")
    if text.count("\ufffd") / max(len(text), 1) > 0.01:
        quality.append("caracteres_dudosos")
    # OCR opcional solo para p\u00e1ginas que son imagen o no tienen texto: la Comisi\u00f3n guarda
    # como imagen p\u00e1ginas enteras de la decisi\u00f3n (p. ej. las de tablas de cuotas). Una
    # p\u00e1gina con poco texto digital y sin imagen no se reemplaza.
    if ocr and ("sin_texto" in quality or "imagen_con_texto_escaso" in quality):
        try:
            recognized = ocr_page(page, ocr["idiomas"], ocr["dpi"], ocr["motor"])
            record.update(texto=recognized, caracteres=len(recognized),
                          caracteres_utiles=sum(c.isalnum() for c in recognized),
                          origen_texto="ocr", idioma_ocr=ocr["idiomas"])
            alerts.append("texto_ocr")
        except Exception as e:
            alerts.append("error_ocr")
            record["error"] = str(e)
    record.update(cobertura_imagen_maxima=round(coverage, 4),
                  posible_ocr=bool(quality), requiere_revision=bool(alerts or quality), alertas=alerts + quality)
    return record


def extract_pdf(job: dict, config: dict, engine, motor_ocr: dict | None = None) -> dict:
    with engine.open(job["path"]) as doc:
        if not doc.is_pdf:
            raise ValueError("El archivo no es un PDF, aunque su extensión lo indique")
        if doc.needs_pass:
            raise ValueError("PDF protegido con contraseña; requiere intervención manual")
        if len(doc) == 0:
            raise ValueError("PDF sin páginas")
        ocr = None
        if config.get("ocr"):
            ocr = {"idiomas": ocr_idiomas(job["referencias"]), "dpi": config["ocr_dpi"], "motor": motor_ocr}
        pages = [page_data(page, config["min_caracteres"], ocr) for page in doc]
        warnings = ["pdf_reparado_por_motor"] if doc.is_repaired else []
        return {"version_esquema": 1, "version_extractor": VERSION, "configuracion": config,
                "sha256_pdf": job["sha256"], "extraido_utc": utcnow(),
                "metadatos_pdf": doc.metadata, "alertas_documento": warnings,
                "referencias": job["referencias"], "paginas": pages}


def rendered_text(data: dict) -> str:
    pieces = []
    for page in data["paginas"]:
        label = "" if page["etiqueta_pdf"] is None else " | etiqueta PDF: " + page["etiqueta_pdf"]
        if page.get("origen_texto") == "ocr":
            label += " | texto OCR: verificar contra el PDF"
        pieces.append(f"[PÁGINA PDF {page['pagina_pdf']}{label}]\n{page['texto']}")
    return "\n\n".join(pieces) + "\n"


@contextmanager
def output_lock(root: Path):
    root.mkdir(parents=True, exist_ok=True)
    path = root / ".extraccion.lock"
    try:
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError as e:
        raise ValueError(f"Ya existe {path}. Comprobá que no haya otro extractor activo; si terminó abruptamente, eliminá solo ese bloqueo.") from e
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump({"pid": os.getpid(), "inicio_utc": utcnow()}, f)
        yield
    finally:
        path.unlink(missing_ok=True)


def cached_document(root: Path, sha: str, config: dict, entry: dict | None) -> dict | None:
    if not isinstance(entry, dict) or entry.get("configuracion") != config:
        return None
    # Las rutas de caché se construyen; nunca se aceptan rutas desde estado.json.
    stem = root / "documentos" / sha
    try:
        if digest(stem.with_suffix(".json")) != entry["sha256_json"] or digest(stem.with_suffix(".txt")) != entry["sha256_txt"]:
            return None
        data = json.loads(stem.with_suffix(".json").read_text(encoding="utf-8"))
        if data["sha256_pdf"] != sha or data["configuracion"] != config:
            return None
        return data
    except (OSError, ValueError, KeyError, TypeError):
        return None


def run(args, selected, results, jobs, report: Path, report_sha: str, root: Path, out: Path, engine) -> int:
    # La configuración se guarda con cada salida y decide si la caché sirve: activar o
    # desactivar el OCR o cambiar la versión de Tesseract vuelve a extraer. Las rutas del
    # ejecutable y de tessdata no entran (dependen del equipo).
    motor = getattr(args, "motor_ocr", None)
    config = {"version_extractor": VERSION, "pymupdf": engine.VersionBind,
              "metodo": "get_text(text, sort=True)", "min_caracteres": args.min_caracteres,
              "ocr": bool(args.ocr), "ocr_dpi": args.ocr_dpi if args.ocr else None,
              "ocr_motor": f"tesseract {motor['version']} {' '.join(OPCIONES_TESSERACT)}" if args.ocr and motor else None}
    statepath = out / "estado.json"
    page_rows, counts = [], Counter()
    interrupted = False
    with output_lock(out):
        state = {"version": 1, "documentos": {}}
        if statepath.exists():
            state = json.loads(statepath.read_text(encoding="utf-8"))
            if not isinstance(state, dict) or state.get("version") != 1 or not isinstance(state.get("documentos"), dict):
                raise ValueError("estado.json no reconocido; conservá la salida y elegí otro --destino")
        try:
            for number, job in enumerate(jobs, 1):
                sha = job["sha256"]
                print(f"[{number}/{len(jobs)}] {job['referencias'][0]['caso']} — {job['path'].name}", flush=True)
                try:
                    data = None if args.rehacer else cached_document(out, sha, config, state["documentos"].get(sha))
                    reused = data is not None
                    if data is None:
                        data = extract_pdf(job, config, engine, motor)
                    # Una referencia nueva no obliga a volver a extraer el mismo PDF.
                    data["referencias"] = job["referencias"]
                    data["alertas_referencias"] = [
                        {"documento_id": r["documento_id"], "alerta": "sha256_distinto_inventario"}
                        for r in job["referencias"] if r.get("coincide_inventario", "").lower() == "no"]
                    if digest(job["path"]) != sha:
                        raise ValueError("El PDF cambió durante la extracción; repetí cuando termine la descarga")
                    relative = Path("documentos") / sha
                    jsonpath, txtpath = out / relative.with_suffix(".json"), out / relative.with_suffix(".txt")
                    atomic_json(jsonpath, data)
                    atomic_text(txtpath, rendered_text(data))
                    state["documentos"][sha] = {"configuracion": config, "sha256_json": digest(jsonpath), "sha256_txt": digest(txtpath)}
                    atomic_json(statepath, state)
                    flagged = sum(p["requiere_revision"] for p in data["paginas"])
                    status = "requiere_revision" if flagged or data["alertas_documento"] else "extraido"
                    counts["reutilizados" if reused else "extraidos"] += 1
                    for row in job["referencias"]:
                        inventory_changed = row.get("coincide_inventario", "").lower() == "no"
                        detail = data["alertas_documento"] + (["sha256_distinto_inventario"] if inventory_changed else [])
                        results[row["documento_id"]].update(
                            estado_extraccion="requiere_revision" if inventory_changed else status, detalle="; ".join(detail),
                            paginas=len(data["paginas"]), paginas_con_alerta=flagged,
                            paginas_posible_ocr=sum(p["posible_ocr"] for p in data["paginas"]),
                            json=relative.with_suffix(".json").as_posix(), txt=relative.with_suffix(".txt").as_posix(),
                            reutilizado=reused)
                    for page in data["paginas"]:
                        page_rows.append({**{k: page[k] for k in PAGE_FIELDS if k in page}, "sha256": sha,
                                          "casos": " | ".join(sorted({r["caso"] for r in job["referencias"]})),
                                          "documentos": " | ".join(r["documento_id"] for r in job["referencias"]),
                                          "alertas": " | ".join(page["alertas"]),
                                          "json": relative.with_suffix(".json").as_posix()})
                    print(f"  {status}: {len(data['paginas'])} páginas; {flagged} con alertas", flush=True)
                except Exception as e:
                    counts["errores_pdf"] += 1
                    for row in job["referencias"]:
                        results[row["documento_id"]].update(estado_extraccion="error_extraccion", detalle=str(e))
                    print(f"  error: {e}", file=sys.stderr, flush=True)
        except KeyboardInterrupt:
            interrupted = True
            print("Interrumpido. Volvé a ejecutar el mismo comando para reanudar.", file=sys.stderr)
        for result in results.values():
            if result["estado_extraccion"] == "pendiente":
                result.update(estado_extraccion="interrumpido", detalle="Pendiente; repetí el mismo comando")
        statuses = Counter(r["estado_extraccion"] for r in results.values())
        summary = {
            "version_extractor": VERSION, "fecha_utc": utcnow(),
            "estado_ejecucion": "interrumpida" if interrupted else "finalizada",
            "entrada": str(root), "reporte_descarga": str(report), "sha256_reporte": report_sha,
            "reporte_cambio_durante_corrida": digest(report) != report_sha,
            "configuracion": config, "casos": sorted({r["caso"] for r in selected}),
            "filas_documentales": len(selected), "pdf_unicos_seleccionados": len(jobs),
            "filas_por_universo": dict(Counter(r.get("universo", "") or "sin_informar" for r in selected)),
            "filas_sha256_distinto_inventario": sum(r.get("coincide_inventario", "").lower() == "no" for r in selected),
            "procesamiento_pdf": dict(counts), "estados_filas": dict(statuses),
            "paginas": len(page_rows), "paginas_con_alerta": sum(p["requiere_revision"] for p in page_rows),
            "paginas_posible_ocr": sum(p["posible_ocr"] for p in page_rows),
            "paginas_texto_ocr": sum(p.get("origen_texto") == "ocr" for p in page_rows),
            "nota": ("Alertas heurísticas: requieren revisión. Las páginas con origen_texto 'ocr' se leyeron "
                     "con Tesseract y pueden tener errores de reconocimiento. No hay análisis jurídico."
                     if args.ocr else
                     "Alertas heurísticas: requieren revisión. No se ejecutó OCR ni análisis jurídico."),
        }
        write_csv(out / "documentos.csv", DOCUMENT_FIELDS, list(results.values()))
        write_csv(out / "paginas.csv", PAGE_FIELDS, page_rows)
        atomic_json(out / "resumen.json", summary)
    print(f"Reportes: {out / 'documentos.csv'} y {out / 'resumen.json'}")
    return 130 if interrupted else (2 if summary["reporte_cambio_durante_corrida"] or any(k.startswith("error_") for k in statuses) else 0)


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--entrada", type=Path, default=Path("descargas_anc"), help="Carpeta del descargador, con reporte.csv y archivos/")
    p.add_argument("--destino", type=Path, help="Predeterminado: <entrada>/texto_extraido")
    p.add_argument("--casos", nargs="+", help="Ej.: M.10646 M.10896 (también admite comas)")
    p.add_argument("--limite", type=int, help="Máximo de PDF únicos, por orden del reporte")
    p.add_argument("--min-caracteres", type=int, default=30, help="Umbral de letras/dígitos por página para revisión (30)")
    p.add_argument("--rehacer", action="store_true", help="Extraer de nuevo aunque haya caché válida")
    p.add_argument("--ocr", action="store_true",
                   help="Leer con OCR (Tesseract) las páginas que son imagen o no tienen texto")
    p.add_argument("--ocr-dpi", type=int, default=300, help="Resolución del OCR (300)")
    p.add_argument("--tesseract", help="Ejecutable de Tesseract, si no está en el PATH")
    p.add_argument("--tessdata", help="Carpeta tessdata de Tesseract, si no se encuentra sola")
    p.add_argument("--plan", action="store_true", help="Validar selección y SHA-256, sin extraer ni escribir")
    p.add_argument("--version", action="version", version=VERSION)
    return p


def main(argv: list[str] | None = None) -> int:
    p = parser()
    args = p.parse_args(argv)
    if args.limite is not None and args.limite < 1:
        p.error("--limite debe ser al menos 1")
    if args.min_caracteres < 1:
        p.error("--min-caracteres debe ser al menos 1")
    if not 72 <= args.ocr_dpi <= 600:
        p.error("--ocr-dpi debe estar entre 72 y 600")
    root = args.entrada.resolve()
    out = args.destino.resolve() if args.destino else root / "texto_extraido"
    report = root / "reporte.csv"
    try:
        if out == root or out.is_relative_to(root / "archivos") or root.is_relative_to(out):
            raise ValueError("--destino debe ser otra carpeta; no puede ser la entrada, un ancestro ni estar dentro de archivos/")
        if (root / ".descarga.lock").exists():
            raise ValueError("El descargador está activo (.descarga.lock). Esperá a que termine para usar un reporte estable")
        cases = set()
        for item in args.casos or []:
            for token in item.split(","):
                token = token.strip().upper()
                if re.fullmatch(r"M\d+", token):
                    token = "M." + token[1:]
                if token:
                    cases.add(token)
        rows, report_sha = read_report(report)
        selected, results, jobs = make_plan(rows, root, cases, args.limite)
        print(f"Filas: {len(selected)}; PDF únicos a procesar: {len(jobs)}")
        if args.plan:
            print(json.dumps(dict(Counter(r["estado_extraccion"] for r in results.values())), ensure_ascii=False))
            return 2 if any(r["estado_extraccion"] == "error_archivo" for r in results.values()) else 0
        try:
            import pymupdf
        except ImportError as e:
            raise ValueError("Falta PyMuPDF. Ejecutá: python -m pip install -r remedios_ue/requirements.txt") from e
        if args.ocr:
            args.motor_ocr = tesseract_disponible(args.tesseract, args.tessdata)
        return run(args, selected, results, jobs, report, report_sha, root, out, pymupdf)
    except (OSError, ValueError) as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
