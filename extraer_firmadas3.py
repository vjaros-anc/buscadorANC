#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
extraer_firmadas3.py  —  Extractor CNDC mejorado (solo CONC).

Versión 3 del extractor de dictámenes. Reutiliza EXACTAMENTE las utilidades de
`extraer_firmadas2.py` (se importa como módulo, no se copia) y REEMPLAZA solo la
extracción de "Empresas involucradas" y "Mercados relevantes", que eran las que
más fallaban. Diagnóstico y correcciones (ver informe):

  FIX 1 — Marcador de rol inline. Cuando la tabla marca el rol dentro de la
          celda del nombre, p.ej. "GAS LINK S.A. (Objeto)", ahora ese marcador
          se usa también para el mercado (antes solo lo leía 'empresas').

  FIX 2 — Fila de encabezado. Una fila de una sola celda que NO es un rótulo de
          rol reconocido (p.ej. "Empresa", "Actividad", "Razón social") ya NO
          apaga la sección 'objeto' activa. Antes, ese header reseteaba la
          recolección y el mercado quedaba vacío aunque el rótulo fuera 'objeto'.

  FIX 3 — Empresas sin rol. Si la tabla de empresas no se divide en
          comprador/objeto y no hay marcador de rol, las empresas ya NO se
          descartan: se listan con rol vacío (rol=null). Antes se perdían todas.

  FIX 4 — Mercado = actividad del 'objeto'. Si NO se puede identificar ninguna
          empresa 'objeto', el mercado se deja VACÍO (no se inventa mezclando
          comprador + objeto). Decisión de precisión sobre completitud.

  FIX 5 — Limpieza de glifos de la Private Use Area (U+E000..U+F8FF), típicos de
          viñetas Wingdings ("") que se colaban al texto de mercados/empresas.

  Formato viejo en prosa (0 tablas, dictámenes ~pre-2015): NO se intenta
  adivinar por prosa. Se deja vacío y esos casos se listan aparte en un .txt
  ("*_no_extraibles.txt") para revisión manual.

El resto de campos (Carátula, Grupo/Empresa, fechas, Decisión, Nº Resolución,
Nº Dictamen, Relaciones económicas) usa la misma lógica del original.

Uso:
    python extraer_firmadas3.py                 # ./pdf  -> firmadas3.xlsx
    python extraer_firmadas3.py <carpeta>       # carpeta con PDFs
    python extraer_firmadas3.py <carpeta> <salida.xlsx>

Dependencias: pip install pymupdf openpyxl
"""
import os, re, sys, glob, json, importlib.util

# --- Importar el extractor original como base de utilidades ------------------
SCRIPT_ORIG = r"C:\Users\Admin\Documents\ANC\descargas_cndc\extraer_firmadas2.py"

def _cargar_base():
    spec = importlib.util.spec_from_file_location("extraer_firmadas2", SCRIPT_ORIG)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

ext = _cargar_base()


# --- FIX 5: limpieza de glifos Private Use Area (viñetas Wingdings, etc.) -----
_RE_PUA = re.compile("[-]")

def _limpiar_pua(s):
    if not s:
        return s
    s = _RE_PUA.sub(" ", s)
    return re.sub(r"\s+", " ", s).strip(" -–·•\t")


# --- Extracción unificada empresas + actividades -----------------------------
def _empresas_y_actividades(ctx):
    """Recorre las tablas UNA vez y devuelve [{rol, nombre, actividad}].
    rol ∈ {'comprador','objeto', None}.  Aplica FIX 1/2/3/5."""
    res = []
    for tabla in ctx["tablas"]:
        heading = tabla.get("heading")     # rótulo suelto sobre la tabla (rol de sección)
        rol_sec = heading                  # arrastra el rol de sección
        activo = ext._es_tabla_empresas(tabla["rows"])
        for row in tabla["rows"]:
            if not row:
                continue
            cells = [(c or "").replace("\n", " ").strip() for c in row]
            nov = [(i, c) for i, c in enumerate(cells) if c]
            if not nov:
                continue
            # FIX 2: el header "Empresa/Actividad" activa la tabla pero NO cambia el rol
            if ext._es_header_empresas(cells):
                activo = True
                continue
            hay_prosa = any(ext._es_prosa(c) for _, c in nov)
            if not hay_prosa and ext._es_fila_participacion(cells):
                activo = False
                continue
            first_i, first_c = nov[0]
            lbl = ext._label_de_seccion(first_c, len(nov) == 1)
            if lbl:                        # rótulo de rol -> cambia sección
                rol_sec, activo = lbl, True
                resto = nov[1:]
                if not resto:
                    continue               # fila-etiqueta pura
                name_c = resto[0][1]
                act_cells = [c for _, c in resto[1:]]
            else:
                name_c = first_c
                act_cells = [c for _, c in nov[1:]]
            if not activo:
                continue
            nombre = _limpiar_pua(ext._limpiar_empresa(name_c))
            valido = any(ext._es_prosa(c) for c in act_cells) or bool(ext._RE_LEGAL.search(nombre))
            if not valido or not ext._parece_empresa(nombre):
                continue
            # FIX 1: el marcador inline "(Objeto)" gana sobre el rol de sección
            rol = ext._rol_parentesis(name_c) or rol_sec
            act = " ".join(a for a in act_cells if a and not ext._celda_numerica(a)).strip()
            act = _limpiar_pua(act)
            res.append({"rol": rol, "nombre": nombre, "actividad": act})

    # Fallback por geometría (tablas sin bordes): ya trae (rol, nombre, actividad)
    if not res:
        for rol, nombre, act in ctx.get("geo", []):
            for n in ext._split_multi_empresa(_limpiar_pua(ext._limpiar_empresa(nombre))):
                if ext._parece_empresa(n):
                    res.append({"rol": rol, "nombre": n, "actividad": _limpiar_pua(act)})

    # dedup por (rol, nombre)
    vistos, out = set(), []
    for e in res:
        k = (e["rol"], ext.strip_acentos(e["nombre"]).lower())
        if k not in vistos:
            vistos.add(k)
            out.append(e)
    return out


def ex_empresas3(ctx):
    """FIX 3: se listan TODAS las empresas de la tabla, con rol si se conoce
    (rol=null si no)."""
    emp = ctx.get("_empresas") or _empresas_y_actividades(ctx)
    return json.dumps([{"rol": e["rol"], "nombre": e["nombre"]} for e in emp],
                      ensure_ascii=False) if emp else None


def ex_mercados3(ctx):
    """Mercado relevante = descripción/actividad de la sección 'Objeto'.

    Paso independiente (NO se gatilla por la tabla de empresas): recorre las
    tablas arrastrando el estado 'recolectando' que abre la sección 'objeto'.
    Mejoras sobre el original:
      FIX 2 — una fila-etiqueta que NO es un rol reconocido (p.ej. 'Empresa',
              'Actividad', un nombre suelto) NO apaga la recolección.
      FIX 1 — un marcador inline '(Objeto)' recolecta esa fila aunque la sección
              sea de comprador; '(Comprador)' la excluye.
      FIX 5 — limpieza de glifos PUA.
      FIX 6 — al tomar la fila completa de 'rest', quedan cubiertas también las
              descripciones de activos ('Un inmueble...') que no son empresas.
    FIX 4 — si nunca se abre una sección 'objeto', devuelve None (no mezcla)."""
    descs = []
    recolectando = False
    for tabla in ctx["tablas"]:
        heading = tabla.get("heading")
        if heading is not None:                      # rótulo suelto sobre la tabla
            recolectando = (heading == "objeto")
        for row in tabla["rows"]:
            if not row:
                continue
            cells = [_limpiar_pua((c or "").replace("\n", " ").strip()) for c in row]
            first = cells[0] if cells else ""
            rest = cells[1:]
            rest_txt = " ".join(x for x in rest if x).strip()
            es_label = bool(first) and not rest_txt
            if es_label:                             # fila de una sola celda
                r = ext._clasificar_label(first)     # 'objeto'/'comprador'/None
                if r == "objeto":
                    recolectando = True
                elif r == "comprador":
                    recolectando = False
                # FIX 2: header ('Empresa'...) o nombre suelto -> NO cambia estado
                continue
            rp = ext._rol_parentesis(first)          # FIX 1: marcador inline
            if rp == "comprador":
                continue
            en_objeto = recolectando or (rp == "objeto")
            if not en_objeto:
                continue
            if ext._es_fila_participacion(cells) and rp != "objeto":
                recolectando = False                 # tabla de participaciones/IHH corta
                continue
            desc = " ".join(x for x in rest if x and not ext._celda_numerica(x)).strip()
            desc = _limpiar_pua(desc)
            if desc and re.search(r"[A-Za-zÁÉÍÓÚáéíóúÑñ]{3,}", desc):
                descs.append(re.sub(r"\s+", " ", desc).strip())
    # Fallback por geometría (tablas sin bordes)
    if not descs:
        for rol, _n, act in ctx.get("geo", []):
            if rol == "objeto" and act and re.search(r"[A-Za-zÁÉÍÓÚáéíóúÑñ]{3,}", act):
                descs.append(_limpiar_pua(re.sub(r"\s+", " ", act).strip()))
    if not descs:
        return None
    return "; ".join(dict.fromkeys(descs))[:400].strip(" ;")


# --- Lista de extractores (igual al original, salvo empresas y mercados) -----
EXTRACTORES = [
    ("tipo",                  ext.ex_tipo),
    ("Carpeta",               ext.ex_carpeta),
    ("Carátula",              ext.ex_caratula),
    ("Grupo/Empresa",         ext.ex_grupo),
    ("Empresas involucradas", ex_empresas3),          # <-- nuevo
    ("Fecha_Ingreso",         ext.ex_fecha_ingreso),
    ("Fecha_firma",           ext.ex_fecha_firma),
    ("Decisión",              ext.ex_decision),
    ("Número de Resolución",  ext.ex_num_resolucion),
    ("Número de Dictamen",    ext.ex_num_dictamen),
    ("Mercados relevantes",   ex_mercados3),           # <-- nuevo
    ("Relaciones económicas", ext.ex_relaciones),
]


def procesar_pdf(path):
    raw, tablas, geo = ext.leer_pdf(path)
    reso_raw, dict_raw = ext.segmentar(raw)
    ctx = {
        "raw": raw, "flat": ext.flat(raw),
        "reso_raw": reso_raw, "reso_flat": ext.flat(reso_raw),
        "dict_raw": dict_raw, "dict_flat": ext.flat(dict_raw),
        "tablas": tablas, "geo": geo,
        "archivo": os.path.basename(path),
    }
    # se calcula UNA sola vez y lo comparten empresas y mercados
    ctx["_empresas"] = _empresas_y_actividades(ctx)
    fila = {"Excluible": None, "_sin_tablas": (not tablas and not geo)}
    for nombre, fn in EXTRACTORES:
        try:
            val = fn(ctx)
        except Exception as e:
            val = None
            print(f"    [warn] {ctx['archivo']}: fallo en '{nombre}': {e}")
        fila[nombre] = val
        if nombre == "Carátula":
            ctx["caratula"] = val
    return fila


def main():
    carpeta = sys.argv[1] if len(sys.argv) > 1 else "pdf"
    salida = sys.argv[2] if len(sys.argv) > 2 else "firmadas3.xlsx"
    pdfs = sorted(glob.glob(os.path.join(carpeta, "*.pdf")))
    # solo CONC
    pdfs = [p for p in pdfs if os.path.basename(p).upper().startswith("CONC")]
    if not pdfs:
        print(f"No se encontraron PDFs CONC en '{carpeta}'.")
        sys.exit(1)

    filas, resumen, sin_tablas = [], [], []
    for p in pdfs:
        print(f"[proc] {os.path.basename(p)}")
        try:
            fila = procesar_pdf(p)
        except Exception as e:
            print(f"    [ERROR] no se pudo procesar: {e}")
            continue
        if fila.pop("_sin_tablas", False):
            sin_tablas.append(os.path.basename(p))
        filas.append(fila)
        vacios = [n for n in ext.COLUMNS if n not in ("Excluible", "meses") and not fila.get(n)]
        resumen.append((fila.get("Carpeta") or os.path.basename(p), vacios))

    def keyn(f):
        m = re.search(r"(\d+)", f.get("Carpeta") or "")
        return int(m.group(1)) if m else 0
    filas.sort(key=keyn)

    ext.escribir_excel(filas, salida)
    print(f"\nOK -> {salida}  ({len(filas)} filas)")

    # PDFs sin ninguna tabla (formato viejo en prosa): no extraíbles por tablas
    if sin_tablas:
        noext = os.path.splitext(salida)[0] + "_no_extraibles.txt"
        with open(noext, "w", encoding="utf-8") as fh:
            fh.write("PDFs sin tablas (formato viejo en prosa) - revisar a mano:\n")
            for n in sorted(sin_tablas):
                fh.write(f"  {n}\n")
        print(f"\n{len(sin_tablas)} PDFs sin tablas (prosa pura) -> {noext}")

    print("\nCampos en blanco por caso (para revisar a mano):")
    for carpeta_id, vacios in resumen:
        print(f"  {carpeta_id}: {', '.join(vacios) if vacios else '— completo —'}")


if __name__ == "__main__":
    main()
