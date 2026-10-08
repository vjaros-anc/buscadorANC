#!/usr/bin/env python3
"""Genera las páginas nuevas sin regenerar ni modificar los buscadores fuente.

El tablero parte del JSON del index publicado. Solo los tiempos se completan
desde Fecha_Ingreso de firm.xlsx, verificando el id y Carpeta de cada fila.
"""
from __future__ import annotations

import hashlib
import html
import json
import re
from datetime import date
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OPI_SOURCE = ROOT / "pdf/lectura_opi/buscador_opis.html"


def write(path: str, content: str) -> None:
    target = ROOT / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")


def nav(current: str) -> str:
    links = [("herramientas", "Portal", "../herramientas/"), ("buscador", "Buscador", "../"),
             ("opis", "OPIs", "../opis/"), ("conc", "Resoluciones", "../conc/"),
             ("noticias", "Noticias · demo", "../noticias/"),
             ("seguimiento", "Seguimiento · demo", "../seguimiento/")]
    items = "".join(f'<a href="{url}"' + (' aria-current="page"' if key == current else '')
                    + f'>{label}</a>' for key, label, url in links)
    return ('<nav class="anc-nav" aria-label="Herramientas ANC"><div class="anc-nav-inner">'
            '<a class="anc-brand" href="../herramientas/"><span class="anc-brand-mark">ANC</span>'
            'Herramientas de concentraciones</a><div class="anc-nav-links">'
            + items + '</div><span class="anc-pill">Versión de prueba</span></div></nav>')


def page(section: str, title: str, lead: str, content: str, meta: str = "") -> str:
    return f'''<!doctype html>
<html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex,nofollow"><title>{html.escape(title)} · Herramientas ANC</title>
<link rel="stylesheet" href="../assets/portal.css"><script defer src="../assets/portal.js"></script></head>
<body class="anc-page" data-section="{section}"><a class="anc-skip" href="#contenido">Saltar al contenido</a>
{nav(section)}<main id="contenido" class="anc-wrap"><div class="anc-hero"><div>
<p class="anc-eyebrow">Concentraciones económicas</p><h1 class="anc-title">{title}</h1>
<p class="anc-lead">{lead}</p>{meta}</div></div>{content}
<footer class="anc-footer">Herramientas ANC · Versión de prueba para evaluar las nuevas herramientas.</footer></main></body></html>'''


def stats(labels: list[tuple[str, str, str]]) -> str:
    return '<div class="anc-stats" aria-live="polite">' + ''.join(
        f'<div class="anc-stat"><span class="anc-stat-label">{label}</span>'
        f'<strong class="anc-stat-value" id="{key}">—</strong>'
        f'<span class="anc-stat-detail" id="{key}-detail">{detail}</span></div>'
        for key, label, detail in labels) + '</div>'


def filters(fields: list[tuple[str, str, str]], search: bool = False, export: bool = False) -> str:
    result = '<form class="anc-filters" id="filters" aria-label="Filtros">'
    if search:
        result += ('<label class="anc-field anc-field-wide">Buscar'
                   '<input type="search" id="q" placeholder="Operación, empresa o mercado" autocomplete="off"></label>')
    for key, label, default in fields:
        result += f'<label class="anc-field">{label}<select id="{key}"><option value="">{default}</option></select></label>'
    result += '<button class="anc-button" type="reset">Limpiar filtros</button>'
    if export:
        result += '<button class="anc-button" id="export" type="button">Descargar CSV</button>'
    return result + '</form>'


def panel(title: str, note: str, target: str) -> str:
    return f'<section class="anc-panel"><h2>{title}</h2><p class="anc-note">{note}</p><div id="{target}"></div></section>'


def build_dashboard() -> tuple[int, str]:
    raw = (ROOT / "index.html").read_bytes()
    match = re.search(r'<script id="bm-data" type="application/json">(.*?)</script>', raw.decode(), re.S)
    if not match:
        raise ValueError("No se encontró el corpus del buscador publicado")
    original = json.loads(match.group(1))
    frame = pd.read_excel(ROOT / "firm.xlsx")
    rows = []
    for record in original:
        signed = str(record.get("fsort") or "")
        signed_date = date(int(signed[:4]), int(signed[4:6]), int(signed[6:8])) if len(signed) == 8 else None
        row_id = record["id"]
        source = frame.iloc[row_id]
        carpeta = "" if pd.isna(source.get("Carpeta")) else " ".join(str(source["Carpeta"]).split())
        if carpeta != record["carpeta"]:
            raise ValueError(f"firm.xlsx no coincide con el index publicado en la fila {row_id}")
        elapsed = None
        start = pd.to_datetime(source.get("Fecha_Ingreso"), errors="coerce")
        excel_signed = pd.to_datetime(source.get("Fecha_firma"), errors="coerce")
        if signed_date and pd.notna(start) and pd.notna(excel_signed) and excel_signed.date() == signed_date:
            value = (signed_date - start.date()).days
            if value >= 0:
                elapsed = value
        rows.append({"fecha": signed_date.isoformat() if signed_date else "", "anio": signed_date.year if signed_date else None,
                     "tipo": record["tipo_cat"], "decision": record["decision"], "sectores": record["sectores"],
                     "relaciones": record["rel_tags"], "dias": elapsed,
                     "mercado": bool(record["merc_v1"] or record["merc_v2"])})
    latest = max(r["fecha"] for r in rows)
    data = {"schema_version": 1, "fuente": "Corpus del buscador publicado; Fecha_Ingreso de firm.xlsx para los tiempos",
            "actualizado_al": latest, "index_sha256": hashlib.sha256(raw).hexdigest(), "registros": rows}
    write("data/conc.json", json.dumps(data, ensure_ascii=False, separators=(",", ":")) + "\n")
    return len(rows), latest


def build_opis() -> int:
    original = OPI_SOURCE.read_text(encoding="utf-8")
    match = re.search(r'const DATA = (\[.*?\]);', original, re.S)
    if not match:
        raise ValueError("No se encontró DATA en el HTML de OPIs")
    total = len(json.loads(match.group(1)))
    result = original.replace('</head>', '<meta name="robots" content="noindex,nofollow">\n'
                              '<link rel="stylesheet" href="../assets/portal.css">\n</head>', 1)
    note = ('<div class="anc-opi-note">Buscador independiente de opiniones consultivas. '
            'Extracción automática: los criterios y textos están pendientes de validación. '
            '<a href="../herramientas/">Volver al portal</a></div>')
    result = result.replace('<body>', '<body>\n' + nav("opis") + '\n' + note, 1)
    write("opis/index.html", result)
    return total


def build_pages(total: int, latest: str, opis: int) -> None:
    icon_paths = ['<circle cx="10" cy="10" r="6"/><path d="m15 15 5 5"/>',
                  '<path d="M6 3h9l4 4v14H6zM14 3v5h5M9 12h7M9 16h7"/>',
                  '<path d="M4 20h17M7 17v-5M12 17V5M17 17V9"/>',
                  '<path d="M4 4h16v16H4zM8 8h8M8 12h8M8 16h4"/>',
                  '<path d="M5 4h14v17H5zM9 4V2M15 4V2M8 10h8M8 14h5M8 18h7"/>']
    tools = [
        ("Buscador de mercados y resoluciones", "Buscar expedientes, empresas y mercados relevantes en el buscador habitual.", "../", "Abrir buscador", "Disponible"),
        ("Buscador de OPIs", f"Explorar {opis} opiniones consultivas por pregunta, respuesta, criterio y fundamento normativo.", "../opis/", "Abrir OPIs", "Independiente"),
        ("Tablero de resoluciones", f"Explorar {total:,} registros publicados: firmas por año, tipos, sectores y tiempos con datos disponibles.".replace(",", "."), "../conc/", "Ver tablero", "Datos del corpus"),
        ("Monitor de noticias", "Explorar operaciones, filtrar mercados y consultar su estado de verificación.", "../noticias/", "Probar monitor", "Demo · datos ficticios"),
        ("Seguimiento de concentraciones", "Probar indicadores de carga por analista, estados, antigüedad y próximas revisiones.", "../seguimiento/", "Probar seguimiento", "Demo · datos ficticios")]
    cards = []
    for i, (title, desc, url, action, badge) in enumerate(tools):
        cards.append(f'<article class="anc-tool"><div class="anc-tool-top"><span class="anc-icon" aria-hidden="true">'
                     f'<svg viewBox="0 0 24 24">{icon_paths[i]}</svg></span><span class="anc-pill'
                     + (' anc-demo-pill' if i >= 3 else '') + f'">{badge}</span></div><h2>{title}</h2>'
                     f'<p>{desc}</p><a href="{url}">{action}<svg aria-hidden="true" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M5 12h14m-6-6 6 6-6 6"/></svg></a></article>')
    latest_display = date.fromisoformat(latest).strftime("%d/%m/%Y")
    write("herramientas/index.html", page("herramientas", "Herramientas para analizar<br>concentraciones económicas",
        "Buscadores, antecedentes e indicadores reunidos en un mismo lugar, con cada herramienta en su propio espacio.",
        '<div class="anc-grid">' + ''.join(cards) + '</div>' +
        '<h2 class="anc-section-label">Una plataforma en construcción</h2><div class="anc-panel">'
        '<p class="anc-note" style="margin:0">El tablero utiliza el corpus publicado. Noticias y seguimiento son demos con datos ficticios; '
        'su conexión con las fuentes reales se preparará para el área interna.</p></div>',
        f'<p class="anc-meta">Corpus: {total:,} registros · Última firma: {latest_display} · OPIs: {opis} dictámenes</p>'.replace(',', '.')))

    content = '<div id="error" role="alert"></div>' + filters([("year", "Año de firma", "Todos los años"), ("type", "Tipo de procedimiento", "Todos los tipos")], export=True)
    content += stats([("total", "Registros seleccionados", "Corpus publicado"), ("median", "Mediana ingreso → firma", "Días corridos · registros con ambas fechas"),
                      ("coverage", "Cobertura de tiempos", "Registros con fechas válidas"), ("decisions", "Decisión informada", "Sin completar los campos faltantes")])
    content += '<div class="anc-charts">' + panel("Firmas por año", "Distribución de los registros seleccionados.", "years")
    content += panel("Tipos de procedimiento", "Incluye OPIs y otros tipos cuando no se aplica un filtro.", "types")
    content += panel("Sectores", "Un registro puede pertenecer a varios sectores; las barras no suman el total del corpus.", "sectors")
    content += panel("Relaciones económicas", "Etiquetas disponibles en los registros. Puede haber más de una por expediente.", "relations") + '</div>'
    content += panel("Decisiones registradas", "Texto original de la fuente, sin reinterpretar ni agrupar categorías jurídicas.", "decision-table")
    content += '<p class="anc-meta" id="source-note"></p><noscript><p class="anc-error">Activá JavaScript para cargar los indicadores y filtros.</p></noscript>'
    write("conc/index.html", page("conc", "Tablero de resoluciones", "Una lectura del corpus publicado y de la cobertura de sus datos. Filtrá por año y tipo para explorar los indicadores.", content))

    demo_notice = '<div class="anc-notice anc-notice-demo"><strong>Demo con datos ficticios.</strong> Los nombres, operaciones y estados son ejemplos para probar la herramienta.</div>'
    content = demo_notice + '<div id="error" role="alert"></div>' + filters([("state", "Verificación", "Todos los estados"), ("sector", "Mercado", "Todos los mercados")], search=True, export=True)
    content += stats([("total", "Operaciones seleccionadas", "Datos ficticios"), ("pending", "A verificar", "Requieren consulta de antecedentes"), ("notified", "Notificadas", "Estado de ejemplo"), ("markets", "Mercados", "En la selección actual")])
    content += panel("Registro de operaciones", "El estado se consulta en modo de lectura. Una noticia sin notificación encontrada no implica una operación no notificada.", "operations")
    content += '<noscript><p class="anc-error">Activá JavaScript para cargar la demo.</p></noscript>'
    write("noticias/index.html", page("noticias", "Monitor de noticias", "Operaciones de M&A, mercados y estados de verificación en un registro consultable.", content))

    content = demo_notice + '<div id="error" role="alert"></div>' + filters([("analyst", "Analista", "Todos los analistas"), ("state", "Estado", "Todos los estados"), ("type", "Procedimiento", "Todos los tipos")], export=True)
    content += stats([("total", "Expedientes activos", "En la selección actual"), ("age", "Antigüedad mediana", "Días corridos desde el ingreso"), ("reviews", "Revisiones en 15 días", "Fechas de gestión de ejemplo"), ("old", "Más de 180 días", "Indicador de antigüedad")])
    content += '<div class="anc-charts">' + panel("Carga por analista", "Cantidad de expedientes en la selección.", "analysts") + panel("Estado de los expedientes", "Distribución de la selección actual.", "states") + '</div>'
    content += panel("Expedientes de la demo", "Las fechas de revisión son hitos de gestión, no vencimientos legales. La antigüedad se calcula al corte de la demo.", "cases")
    content += '<p class="anc-meta" id="source-note"></p><noscript><p class="anc-error">Activá JavaScript para cargar la demo.</p></noscript>'
    write("seguimiento/index.html", page("seguimiento", "Seguimiento de concentraciones", "Carga de trabajo, estados y antigüedad para acompañar la gestión del área.", content))


def main() -> None:
    total, latest = build_dashboard()
    opis = build_opis()
    build_pages(total, latest, opis)
    print(f"Portal generado: {total} registros, {opis} OPIs independientes. Buscadores fuente intactos.")


if __name__ == "__main__":
    main()
