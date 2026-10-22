#!/usr/bin/env python3
"""Convierte la exportación CSV de la pestaña Documentos en un manifiesto.

Uso: python preparar_manifiesto.py documentos_exportados.csv --destino manifiesto.csv
No hace solicitudes de red ni inventa enlaces PDF.
"""
from __future__ import annotations
import argparse
import csv
import re
import urllib.parse
from collections import Counter
from pathlib import Path

FIELDS = ["documento_id", "caso", "titulo", "tipo_documental", "grupo", "formato", "url",
          "url_referencia", "idioma", "fecha_registrada", "naturaleza_fecha", "version_o_notas",
          "componente_integrado", "localizacion", "verificacion_origen", "fecha_consulta", "motivo_clasificacion"]
CORE = {"clearance_decision", "decision_complete", "decision_autorizacion", "decision_publica_completa",
        "final_commitments", "commitments_integrated", "commitments", "commitments_final_public_interim",
        "compromisos_finales", "compromisos_finales_pasajeros", "compromisos_finales_carga", "compromisos_version_provisional"}
POST = {"purchaser_approval", "aprobacion_comprador", "waiver", "extension", "modificacion_plazo", "decision_implementacion"}
PRESS = {"press_release", "clearance_press_release", "comunicado", "comunicado_autorizacion",
         "press_release_republication", "comunicado_representacion_CE", "comunicado_autoridad_remitente",
         "comunicado_aprobacion_comprador", "press_release_landing_page", "official_news"}
REFERENCE = {"decision_metadata", "decision_metadata_access_attempt", "full_decision_record", "registro_decision",
             "registro_caso", "case_register", "related_case", "related_authority_status", "annual_report",
             "official_control_infographic", "official_news_listing", "referencia_actos_relacionados", "court_case_record"}


def classify(row: dict[str, str]) -> dict[str, str]:
    kind = row.get("Tipo original", "").strip()
    original = row.get("URL del documento", "").strip()
    cited = row.get("Fuente que lo cita", "").strip()
    notes = row.get("Notas", "").strip()
    if any(s in kind.lower() for s in ("secondary", "secundaria", "mirror")):
        group = "secundaria"
    elif kind in CORE:
        group = "nucleo"
    elif kind in POST:
        group = "actos_posteriores"
    elif kind in PRESS:
        group = "comunicados"
    elif kind in REFERENCE or "merger_brief" in kind:
        group = "referencia"
    else:
        group = "procedimiento"
    reason = "Enlace transcrito del inventario; no se comprobó en esta preparación"
    url = original
    if not original:
        fmt = "sin_url"
        reason = "Documento citado sin URL individual localizada"
    else:
        p = urllib.parse.urlsplit(original)
        q = urllib.parse.parse_qs(p.query)
        uri = next((v[0] for k, v in q.items() if k.lower() == "uri" and v), "")
        if p.hostname == "eur-lex.europa.eu" and re.search(r"(?:[:_])(?:TOC|FULL)$", uri, re.I):
            fmt, url = "indice_do", ""
            reason = "URL de índice o volumen DO; requiere localizar el aviso individual"
        elif (p.path.lower().endswith(".pdf") or "/txt/pdf" in p.path.lower()
              or ("/document/download/" in p.path and any(v.lower().endswith(".pdf") for values in q.values() for v in values))):
            fmt = "pdf"
            reason = "URL de PDF localizada en el inventario; la descarga verificará su contenido"
        else:
            fmt = "html"
            reason = "Página o ficha HTML; no se convierte automáticamente en un enlace PDF"
    if group == "secundaria":
        reason += "; fuente secundaria, excluida de la descarga predeterminada"
    return {
        "documento_id": row["Documento ID"], "caso": row["Caso"], "titulo": row["Título"],
        "tipo_documental": row.get("Tipo documental", ""), "grupo": group, "formato": fmt,
        "url": url, "url_referencia": original or cited, "idioma": row.get("Idioma", ""),
        "fecha_registrada": row.get("Fecha registrada", ""), "naturaleza_fecha": row.get("Naturaleza de fecha", ""),
        "version_o_notas": notes, "componente_integrado": row.get("Componente integrado", ""),
        "localizacion": row.get("Páginas / localización", ""),
        "verificacion_origen": row.get("Evidencia original", ""), "fecha_consulta": row.get("Consulta", ""),
        "motivo_clasificacion": reason,
    }


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("documentos", type=Path)
    p.add_argument("--destino", type=Path, default=Path("manifiesto.csv"))
    args = p.parse_args(argv)
    with args.documentos.open(encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        required = {"Documento ID", "Caso", "Título", "URL del documento", "Tipo original"}
        if not required.issubset(reader.fieldnames or []):
            p.error("Usá la exportación de la pestaña Documentos, con sus encabezados originales")
        rows = [classify({k: (v or "").strip() for k, v in row.items() if k}) for row in reader]
    args.destino.parent.mkdir(parents=True, exist_ok=True)
    with args.destino.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)
    print(f"Manifiesto: {args.destino}; {len(rows)} entradas")
    print("Formatos:", dict(Counter(r["formato"] for r in rows)))
    print("Grupos:", dict(Counter(r["grupo"] for r in rows)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
