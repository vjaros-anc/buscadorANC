#!/usr/bin/env python3
"""Descarga reproducible de documentos públicos. Python 3.10+, sin dependencias.

Ejemplos:
  python descargar_remedios.py --piloto --plan
  python descargar_remedios.py --piloto
  python descargar_remedios.py --todos
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import http.client
import json
import os
import re
import socket
import ssl
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

VERSION = "1.0.0"
PILOTO = ("M.10341", "M.10262", "M.10646", "M.10896", "M.11253")
GRUPOS = ("nucleo", "actos_posteriores", "procedimiento", "comunicados")
REQUIRED = {"documento_id", "caso", "titulo", "grupo", "formato", "url"}
REPORT_FIELDS = (
    "documento_id", "caso", "titulo", "tipo_documental", "grupo", "idioma",
    "formato_esperado", "url_origen", "url_referencia", "estado", "archivo",
    "sha256", "bytes", "formato_real", "content_type", "http_status", "url_final",
    "intentos", "fecha_utc", "detalle", "ejecucion_id",
)
BLOCK_MARKERS = (
    b"verify that you're not a robot", b"verify that you are not a robot",
    b"verify you are human", b"checking your browser", b"cf-chl-",
    b"javascript is disabled", b"enable javascript and then reload",
    b"access denied", b"unusual traffic", b"captcha-container",
    b"g-recaptcha", b"hcaptcha", b"request blocked", b"just a moment...",
)


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def atomic_json(path: Path, value: object) -> None:
    fd, name = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(value, f, ensure_ascii=False, indent=2)
            f.write("\n")
        os.replace(name, path)
    finally:
        Path(name).unlink(missing_ok=True)


def canonical_url(url: str) -> str:
    p = urllib.parse.urlsplit(url.strip())
    if p.scheme not in {"http", "https"} or not p.hostname or p.username or p.password:
        raise ValueError("Se requiere una URL HTTP(S) sin credenciales incorporadas")
    # QID y UTM identifican búsquedas/seguimiento, no versiones documentales.
    query = [(k, v) for k, v in urllib.parse.parse_qsl(p.query, keep_blank_values=True)
             if k.lower() != "qid" and not k.lower().startswith("utm_")]
    return urllib.parse.urlunsplit((p.scheme.lower(), p.netloc.lower(), p.path,
                                   urllib.parse.urlencode(sorted(query)), ""))


def request_url(url: str) -> str:
    p = urllib.parse.urlsplit(url)
    path = urllib.parse.quote(p.path, safe="/%:@!$&'()*+,;=-._~")
    query = urllib.parse.quote(p.query, safe="%=&/:?+@!$'()*;,.-_~")
    return urllib.parse.urlunsplit((p.scheme, p.netloc, path, query, ""))


def url_key(url: str) -> str:
    return hashlib.sha256(canonical_url(url).encode("utf-8")).hexdigest()


class DownloadError(Exception):
    def __init__(self, status: str, detail: str, *, retry: bool = False,
                 http_status: int | str = "", wait: float | None = None,
                 final_url: str = "", content_type: str = ""):
        super().__init__(detail)
        self.status, self.retry, self.http_status = status, retry, http_status
        self.wait, self.final_url, self.content_type = wait, final_url, content_type


def check_pdf(path: Path) -> None:
    size = path.stat().st_size
    with path.open("rb") as f:
        first = f.read(1024).lstrip(b"\xef\xbb\xbf \t\r\n\x00")
        f.seek(max(0, size - 4096))
        tail = f.read()
    if size < 40 or not first.startswith(b"%PDF-"):
        raise DownloadError("pdf_invalido", "El archivo no tiene firma PDF válida")
    if b"%%EOF" not in tail:
        raise DownloadError("pdf_incompleto", "Falta el marcador final %%EOF; posible descarga truncada", retry=True)


def retry_after(value: str | None, cap: float) -> float | None:
    if not value:
        return None
    try:
        seconds = float(value)
    except ValueError:
        try:
            date = parsedate_to_datetime(value)
            if date.tzinfo is None:
                date = date.replace(tzinfo=timezone.utc)
            seconds = (date - datetime.now(timezone.utc)).total_seconds()
        except (ValueError, TypeError, OverflowError):
            return None
    return min(cap, max(0.0, seconds))


def read_manifest(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        if not REQUIRED.issubset(reader.fieldnames or []):
            raise ValueError("El manifiesto no tiene las columnas necesarias: " + ", ".join(sorted(REQUIRED)))
        rows = [{k: (v or "").strip() for k, v in r.items() if k is not None} for r in reader]
    seen: set[str] = set()
    for row in rows:
        if not row["documento_id"] or row["documento_id"] in seen:
            raise ValueError("Identificador documental vacío o duplicado: " + row["documento_id"])
        seen.add(row["documento_id"])
        if not re.fullmatch(r"M\.\d+", row["caso"]):
            raise ValueError("Número de caso inválido: " + row["caso"])
        if row["formato"] not in {"pdf", "html", "sin_url", "indice_do"}:
            raise ValueError("Formato no reconocido: " + row["formato"])
    if not rows:
        raise ValueError("El manifiesto está vacío")
    return rows


def make_plan(rows: list[dict[str, str]], args: argparse.Namespace):
    available = {r["caso"] for r in rows}
    if args.todos:
        cases = available
    elif args.casos:
        cases = set()
        for item in args.casos:
            for token in item.split(","):
                token = token.strip().upper()
                if re.fullmatch(r"M\d+", token):
                    token = "M." + token[1:]
                if token:
                    cases.add(token)
        if not cases:
            raise ValueError("Indicá al menos un caso")
    else:
        cases = set(PILOTO)
    unknown = cases - available
    if unknown:
        raise ValueError("Casos ausentes del manifiesto: " + ", ".join(sorted(unknown)))
    groups = None if "todos" in args.grupos else set(args.grupos)
    selected = [r for r in rows if r["caso"] in cases]
    jobs: dict[str, dict] = {}
    statuses: dict[str, tuple[str, str]] = {}
    priority = {g: i for i, g in enumerate(GRUPOS)}
    for row in sorted(selected, key=lambda r: (priority.get(r["grupo"], 9), r["caso"], r["documento_id"])):
        rid = row["documento_id"]
        if groups is not None and row["grupo"] not in groups:
            statuses[rid] = ("fuera_grupo", "Grupo no solicitado; se conserva la referencia")
        elif row["formato"] == "indice_do":
            statuses[rid] = ("requiere_url_individual", "Índice o volumen del Diario Oficial; no es un documento individual")
        elif not row["url"] or row["formato"] == "sin_url":
            statuses[rid] = ("sin_url", "No hay URL individual; ver url_referencia y pendientes_fuente.csv")
        elif row["formato"] == "html" and not args.incluir_html:
            statuses[rid] = ("html_no_solicitado", "Referencia HTML; agregar --incluir-html para intentar guardarla")
        else:
            try:
                key = url_key(row["url"])
            except ValueError as e:
                statuses[rid] = ("url_invalida", str(e))
                continue
            if key not in jobs:
                jobs[key] = {"key": key, "url": row["url"], "format": row["formato"], "rows": []}
            jobs[key]["rows"].append(row)
            statuses[rid] = ("pendiente", "")
    joblist = list(jobs.values())
    if args.limite is not None:
        for job in joblist[args.limite:]:
            for row in job["rows"]:
                statuses[row["documento_id"]] = ("fuera_limite", "Límite de URLs solicitado")
        joblist = joblist[:args.limite]
    return selected, joblist, statuses


class Downloader:
    def __init__(self, args: argparse.Namespace, rows: list[dict[str, str]],
                 jobs: list[dict], statuses: dict[str, tuple[str, str]]):
        self.args, self.rows, self.jobs = args, rows, jobs
        self.out = args.destino.resolve()
        self.run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S") + f"-{os.getpid()}"
        self.state = {"version": 1, "urls": {}}
        self.checked: dict[str, dict | None] = {}
        self.hashes: dict[str, dict] = {}
        self.results: dict[str, dict] = {}
        self.completed_jobs: Counter = Counter()
        self.opener = urllib.request.build_opener()
        for row in rows:
            status, detail = statuses[row["documento_id"]]
            self.results[row["documento_id"]] = {
                "documento_id": row["documento_id"], "caso": row["caso"], "titulo": row["titulo"],
                "tipo_documental": row.get("tipo_documental", ""), "grupo": row["grupo"],
                "idioma": row.get("idioma", ""), "formato_esperado": row["formato"],
                "url_origen": row["url"], "url_referencia": row.get("url_referencia", ""),
                "estado": status, "detalle": detail, "ejecucion_id": self.run_id,
            }

    def cache(self, entry: dict | None, expected: str | None = None) -> dict | None:
        if not isinstance(entry, dict):
            return None
        try:
            rel = entry["archivo"]
            if expected == "pdf" and entry.get("formato_real") != "pdf":
                return None
            if rel not in self.checked:
                path = (self.out / rel).resolve()
                path.relative_to(self.out)
                good = path.is_file() and path.stat().st_size == entry["bytes"] and digest(path) == entry["sha256"]
                if good and entry.get("formato_real") == "pdf":
                    check_pdf(path)
                self.checked[rel] = dict(entry) if good else None
            result = self.checked[rel]
            if result:
                self.hashes[result["sha256"]] = result
            return result
        except (ValueError, KeyError, OSError, DownloadError):
            return None

    def save_report(self, exit_status: str = "en_curso") -> None:
        report = self.out / "reporte.csv"
        fd, name = tempfile.mkstemp(prefix="reporte.", suffix=".tmp", dir=self.out)
        try:
            with os.fdopen(fd, "w", encoding="utf-8-sig", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=REPORT_FIELDS, extrasaction="ignore")
                writer.writeheader()
                writer.writerows(self.results[r["documento_id"]] for r in self.rows)
            os.replace(name, report)
        finally:
            Path(name).unlink(missing_ok=True)
        summary = {
            "version_script": VERSION, "ejecucion_id": self.run_id, "fecha_utc": utcnow(),
            "estado_ejecucion": exit_status, "manifiesto": str(self.args.manifiesto.resolve()),
            "sha256_manifiesto": digest(self.args.manifiesto),
            "casos": sorted({r["caso"] for r in self.rows}), "filas_documentales": len(self.rows),
            "urls_en_cola": len(self.jobs), "resultados_por_url": dict(self.completed_jobs),
            "resultados_por_documento": dict(Counter(r["estado"] for r in self.results.values())),
            "validacion": "Firma PDF, marcador EOF, tamaño transmitido y SHA-256; no es validación jurídica ni análisis completo del PDF",
        }
        atomic_json(self.out / "resumen.json", summary)

    def log(self, event: dict) -> None:
        with (self.out / "historial.jsonl").open("a", encoding="utf-8") as f:
            f.write(json.dumps({"ejecucion_id": self.run_id, "fecha_utc": utcnow(), **event}, ensure_ascii=False) + "\n")

    def fetch_once(self, job: dict) -> dict:
        req = urllib.request.Request(request_url(job["url"]), headers={
            "User-Agent": self.args.user_agent, "Accept-Encoding": "identity",
            "Accept": "application/pdf,text/html;q=0.8,*/*;q=0.5",
        })
        temporary: Path | None = None
        final_url, ctype, http_status = "", "", ""
        try:
            with self.opener.open(req, timeout=self.args.timeout) as response:
                status = response.getcode()
                http_status = status
                final_url = response.geturl()
                ctype = response.headers.get("Content-Type", "")
                if status != 200:
                    raise DownloadError("http_inesperado", f"Respuesta HTTP {status}; se esperaba 200", http_status=status)
                encoding = response.headers.get("Content-Encoding", "identity").lower()
                if encoding not in {"", "identity"}:
                    raise DownloadError("codificacion_no_admitida", "El servidor no respetó Accept-Encoding: identity")
                try:
                    length = int(response.headers.get("Content-Length", ""))
                except ValueError:
                    length = None
                maximum = int(self.args.max_mb * 1024 * 1024)
                if length is not None and length > maximum:
                    raise DownloadError("excede_tamano", f"El servidor anuncia {length} bytes; supera --max-mb")
                partials = self.out / "_parciales"
                partials.mkdir(exist_ok=True)
                fd, name = tempfile.mkstemp(prefix=job["key"][:12] + "_", suffix=".part", dir=partials)
                temporary = Path(name)
                total, sample = 0, b""
                sha = hashlib.sha256()
                start = time.monotonic()
                with os.fdopen(fd, "wb") as f:
                    while True:
                        if time.monotonic() - start > self.args.timeout_total:
                            raise DownloadError("timeout_total", "Se excedió el tiempo total de transferencia", retry=True)
                        block = response.read(64 * 1024)
                        if not block:
                            break
                        total += len(block)
                        if total > maximum:
                            raise DownloadError("excede_tamano", "La respuesta supera --max-mb")
                        if len(sample) < 65536:
                            sample += block[:65536-len(sample)]
                        lower = sample.lower()
                        is_pdf = sample.lstrip(b"\xef\xbb\xbf \t\r\n\x00").startswith(b"%PDF-")
                        if not is_pdf and any(marker in lower for marker in BLOCK_MARKERS):
                            raise DownloadError("bloqueado", "Se recibió una pantalla de bloqueo o verificación humana")
                        if job["format"] == "pdf" and not is_pdf and (b"<html" in lower or b"<!doctype html" in lower):
                            raise DownloadError("html_en_lugar_pdf", "Se recibió HTML donde se esperaba un PDF; no se guardó como PDF")
                        f.write(block)
                        sha.update(block)
                if length is not None and total != length:
                    raise DownloadError("transferencia_incompleta", f"Content-Length={length}, recibidos={total}", retry=True)
                is_pdf = sample.lstrip(b"\xef\xbb\xbf \t\r\n\x00").startswith(b"%PDF-")
                if is_pdf:
                    check_pdf(temporary)
                    actual = "pdf"
                elif job["format"] == "html" and (b"<html" in sample.lower() or b"<!doctype html" in sample.lower()):
                    if total < 20:
                        raise DownloadError("html_invalido", "Página HTML vacía o demasiado corta")
                    actual = "html"
                else:
                    raise DownloadError("formato_inesperado", "No se recibió un PDF ni una página HTML admitida")
                hexdigest = sha.hexdigest()
                existing = self.hashes.get(hexdigest)
                if existing and self.cache(existing):
                    relative = existing["archivo"]
                    content_duplicate = True
                else:
                    cases = sorted({r["caso"] for r in job["rows"]})
                    folder = cases[0].replace(".", "_") if len(cases) == 1 else "compartidos"
                    target = self.out / "archivos" / folder / f"{job['key'][:12]}_{hexdigest[:16]}.{actual}"
                    target.parent.mkdir(parents=True, exist_ok=True)
                    if target.exists() and digest(target) != hexdigest:
                        corrupt = self.out / "_corruptos"
                        corrupt.mkdir(exist_ok=True)
                        backup = corrupt / (target.name + "." + digest(target)[:16])
                        os.replace(target, backup)
                    os.replace(temporary, target)
                    temporary = None
                    relative = target.relative_to(self.out).as_posix()
                    content_duplicate = False
                return {
                    "archivo": relative, "sha256": hexdigest, "bytes": total,
                    "formato_real": actual, "content_type": ctype, "http_status": status,
                    "url_final": final_url, "fecha_utc": utcnow(),
                    "etag": response.headers.get("ETag", ""),
                    "last_modified": response.headers.get("Last-Modified", ""),
                    "detalle": "Contenido idéntico a otro archivo; se reutilizó" if content_duplicate else "Validación técnica básica correcta",
                    "content_duplicate": content_duplicate,
                }
        except urllib.error.HTTPError as e:
            retryable = e.code in {408, 425, 429, 500, 502, 503, 504}
            kind = "bloqueado" if e.code in {401, 403, 429} else "error_http"
            wait = retry_after(e.headers.get("Retry-After") if e.headers else None, self.args.max_espera)
            code = e.code
            endpoint = e.geturl()
            e.close()
            raise DownloadError(kind, f"Respuesta HTTP {code}", retry=retryable, http_status=code, wait=wait, final_url=endpoint) from e
        except (urllib.error.URLError, TimeoutError, socket.timeout, ConnectionError, http.client.HTTPException) as e:
            certificate = isinstance(getattr(e, "reason", None), ssl.SSLCertVerificationError)
            raise DownloadError("error_tls" if certificate else "error_red", str(e), retry=not certificate) from e
        except DownloadError as e:
            e.final_url = e.final_url or final_url
            e.content_type = e.content_type or ctype
            e.http_status = e.http_status or http_status
            raise
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)

    def perform(self, job: dict) -> dict:
        old = self.state["urls"].get(job["key"])
        if not self.args.forzar:
            cached = self.cache(old, job["format"])
            if cached:
                return {**cached, "estado": "ya_descargado", "intentos": 0,
                        "fecha_utc": utcnow(), "detalle": "Archivo existente; tamaño, SHA-256 y formato comprobados"}
        for attempt in range(1, self.args.intentos + 1):
            try:
                result = self.fetch_once(job)
                result["estado"] = "contenido_reutilizado" if result.pop("content_duplicate") else "descargado"
                result["intentos"] = attempt
                self.state["urls"][job["key"]] = result
                self.hashes[result["sha256"]] = result
                self.checked[result["archivo"]] = result
                atomic_json(self.out / "estado.json", self.state)
                return result
            except DownloadError as e:
                self.log({"url": job["url"], "intento": attempt, "estado": e.status, "detalle": str(e), "http_status": e.http_status})
                if not e.retry or attempt == self.args.intentos:
                    return {"estado": e.status, "detalle": str(e), "intentos": attempt,
                            "http_status": e.http_status, "url_final": e.final_url,
                            "content_type": e.content_type, "fecha_utc": utcnow()}
                delay = e.wait if e.wait is not None else min(self.args.max_espera, self.args.reintento_base * 2 ** (attempt - 1))
                if delay:
                    time.sleep(delay)
            except (OSError, ValueError) as e:
                return {"estado": "error_local", "detalle": str(e), "intentos": attempt, "fecha_utc": utcnow()}
        raise AssertionError("Bucle de reintentos agotado sin resultado")

    def run(self) -> int:
        self.out.mkdir(parents=True, exist_ok=True)
        lock = self.out / ".descarga.lock"
        try:
            fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError:
            raise ValueError(f"Ya existe {lock}. No ejecutes dos procesos en la misma carpeta. Si el anterior terminó abruptamente, comprobá que no siga activo y eliminá ese archivo de bloqueo.")
        interrupted = False
        current: dict | None = None
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump({"pid": os.getpid(), "inicio_utc": utcnow()}, f)
            statefile = self.out / "estado.json"
            if statefile.exists():
                self.state = json.loads(statefile.read_text(encoding="utf-8"))
                if self.state.get("version") != 1 or not isinstance(self.state.get("urls"), dict):
                    raise ValueError("estado.json tiene una estructura no reconocida; conservá el archivo y usá otra carpeta de destino")
            # Valida una vez cada archivo conocido para deduplicar contenido entre ejecuciones.
            for entry in self.state["urls"].values():
                self.cache(entry)
            self.save_report()
            for number, job in enumerate(self.jobs, 1):
                current = job
                print(f"[{number}/{len(self.jobs)}] {job['rows'][0]['caso']} — {job['rows'][0]['titulo'][:90]}", flush=True)
                result = self.perform(job)
                for row in job["rows"]:
                    self.results[row["documento_id"]].update({k: v for k, v in result.items() if k in REPORT_FIELDS})
                self.completed_jobs[result["estado"]] += 1
                self.log({"url": job["url"], "documentos": [r["documento_id"] for r in job["rows"]], **result})
                self.save_report()
                print(f"  {result['estado']}: {result.get('detalle', '')}", flush=True)
                current = None
                if number < len(self.jobs) and result["estado"] != "ya_descargado" and self.args.pausa:
                    time.sleep(self.args.pausa)
        except KeyboardInterrupt:
            interrupted = True
            if current:
                for row in current["rows"]:
                    self.results[row["documento_id"]].update(estado="interrumpido", detalle="Volvé a ejecutar el mismo comando para reanudar")
            print("\nInterrumpido. Se conservan los archivos completos y el estado de reanudación.", file=sys.stderr)
        finally:
            lock.unlink(missing_ok=True)
        self.save_report("interrumpida" if interrupted else "finalizada")
        success = {"descargado", "contenido_reutilizado", "ya_descargado"}
        errors = sum(n for status, n in self.completed_jobs.items() if status not in success)
        print(f"\nReporte: {self.out / 'reporte.csv'}")
        print(f"Resumen: {self.out / 'resumen.json'}")
        print(f"URLs resueltas: {sum(n for s, n in self.completed_jobs.items() if s in success)}; con error: {errors}")
        return 130 if interrupted else (2 if errors or any(r["estado"] == "url_invalida" for r in self.results.values()) else 0)


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--manifiesto", type=Path, default=Path(__file__).resolve().with_name("manifiesto.csv"))
    scope = p.add_mutually_exclusive_group()
    scope.add_argument("--piloto", action="store_true", help="Cinco casos predefinidos; es el modo predeterminado")
    scope.add_argument("--todos", action="store_true", help="Todos los casos del manifiesto")
    scope.add_argument("--casos", nargs="+", metavar="M.10341", help="Casos separados por espacio o coma")
    p.add_argument("--destino", type=Path, default=Path("descargas_anc"))
    p.add_argument("--grupos", nargs="+", choices=GRUPOS + ("referencia", "secundaria", "todos"), default=list(GRUPOS))
    p.add_argument("--incluir-html", action="store_true", help="Guardar también páginas HTML individuales; detecta bloqueos básicos")
    p.add_argument("--plan", action="store_true", help="Mostrar selección sin descargar ni crear archivos")
    p.add_argument("--forzar", action="store_true", help="Volver a consultar URLs; conserva versiones distintas de archivos")
    p.add_argument("--limite", type=int, help="Máximo de URLs únicas por ejecución")
    p.add_argument("--timeout", type=float, default=45, help="Timeout de conexión/lectura en segundos (45)")
    p.add_argument("--timeout-total", type=float, default=300, help="Tiempo máximo de transferencia por intento (300 s)")
    p.add_argument("--intentos", type=int, default=3, help="Intentos ante errores temporales (3)")
    p.add_argument("--pausa", type=float, default=1.0, help="Pausa entre URLs, en segundos (1)")
    p.add_argument("--reintento-base", type=float, default=2.0)
    p.add_argument("--max-espera", type=float, default=60.0, help="Espera máxima por reintento/Retry-After (60 s)")
    p.add_argument("--max-mb", type=float, default=100.0, help="Tamaño máximo por respuesta, en MiB (100)")
    p.add_argument("--user-agent", default=f"ANC-Remedios-Downloader/{VERSION} (Python urllib; public-document research)")
    p.add_argument("--version", action="version", version=VERSION)
    return p


def main(argv: list[str] | None = None) -> int:
    p = parser()
    args = p.parse_args(argv)
    if args.intentos < 1 or args.intentos > 10:
        p.error("--intentos debe estar entre 1 y 10")
    if min(args.timeout, args.timeout_total, args.max_mb) <= 0 or min(args.pausa, args.reintento_base, args.max_espera) < 0:
        p.error("Tiempos/tamaño deben ser positivos; pausas y esperas no pueden ser negativas")
    if args.limite is not None and args.limite < 1:
        p.error("--limite debe ser al menos 1")
    try:
        rows = read_manifest(args.manifiesto)
        selected, jobs, statuses = make_plan(rows, args)
        print(f"Casos: {len({r['caso'] for r in selected})}; filas documentales: {len(selected)}; URLs a solicitar: {len(jobs)}")
        print("Selección: " + json.dumps(dict(Counter(s[0] for s in statuses.values())), ensure_ascii=False))
        if args.plan:
            print("Sin solicitudes HTTP ni escritura de archivos.")
            return 0
        return Downloader(args, selected, jobs, statuses).run()
    except (ValueError, OSError, json.JSONDecodeError) as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
