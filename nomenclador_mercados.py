# -*- coding: utf-8 -*-
"""
Nomenclador y buscador de mercados relevantes (ANC).

Lee la hoja `firmadas` de Res_firmadas.xlsx, normaliza la columna
"Mercados relevantes", segmenta cada mercado y clasifica cada expediente
en un nomenclador de sectores + etiquetas (relacion economica, cadena
aguas arriba/abajo, alcance geografico).

Uso:
    import nomenclador_mercados as nm
    registros = nm.build_records()          # lista de dicts (para el .qmd)
    df = nm.build_dataframe()               # DataFrame

    python nomenclador_mercados.py          # escribe CSV + JSON
"""
from __future__ import annotations

import json
import re
import unicodedata
from pathlib import Path

import pandas as pd

ARCHIVO = Path(__file__).with_name("firm.xlsx")
HOJA = "firmadas"


# --------------------------------------------------------------------------- #
# Utilidades de texto
# --------------------------------------------------------------------------- #
def _strip_accents(s: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c)
    )


def norm(s) -> str:
    """minusculas, sin acentos, espacios colapsados. Para matching y busqueda."""
    if s is None:
        return ""
    s = str(s)
    s = _strip_accents(s).lower()
    s = re.sub(r"\s+", " ", s)
    return s.strip()


def clean(s) -> str:
    """Limpia para mostrar: colapsa saltos de linea y espacios, sin recortar acentos."""
    if s is None:
        return ""
    s = str(s)
    if s.strip().lower() == "nan":
        return ""
    s = s.replace("\r", " ").replace("\n", " ")
    s = re.sub(r"\s+", " ", s)
    return s.strip()


# --------------------------------------------------------------------------- #
# Nomenclador de sectores.  Cada sector -> lista de patrones (regex sobre texto
# normalizado sin acentos).  Un expediente puede pertenecer a varios sectores.
# --------------------------------------------------------------------------- #
SECTORES: dict[str, list[str]] = {
    "Hidrocarburos (petróleo y gas)": [
        r"petroleo", r"gas natural", r"\bde gas\b", r"explotacion de petroleo",
        r"exploracion y explotacion", r"servicios petroleros", r"insumos y servicios petroleros",
        r"perforacion", r"plataforma de perforacion", r"produccion de gas",
        # --- nuevo ---
        r"exploracion y produccion de hidrocarburos", r"produccion de hidrocarburos",
        r"pozos petroleros", r"estimulacion.*pozos", r"empresas petroleras",
        # --- ampliacion cobertura ---
        r"hidrocarburos", r"fractura hidraulica", r"yacimiento",
        r"distribucion minorista de combustibles", r"lubricantes",
    ],
    "Energía eléctrica": [
        r"energia electrica", r"potencia instalada", r"infraestructura electrica",
        r"energia nuclear", r"transformadores", r"autotransformadores",
        r"sistema electrico", r"alta( y extra alta)? tension", r"generacion de energia",
        # --- nuevo ---
        r"alquiler de generadores", r"suministro de electricidad",
        r"eolica", r"solar", r"renovable", r"hidraulica", r"geotermica", r"mareomotriz",
        r"energia eolica", r"energia solar", r"energia renovable",
        r"energia hidraulica", r"energia geotermica", r"energia mareomotriz",
        # --- ampliacion cobertura ---
        r"parque eolico", r"planta eolica", r"transporte de electricidad",
        r"transporte de energia electrica", r"generacion electrica", r"central hidroelectrica",
    ],
    "Gases industriales": [
        r"oxigeno", r"oxigeno liquido",
    ],
    "Carne y avicultura": [
        r"carne aviar", r"\bpollo\b", r"avicola", r"menudencias", r"carne",
    ],
    "Agroindustria, granos y semillas": [
        r"\bsoja\b", r"\bmaiz\b", r"\btrigo\b", r"granos", r"semillas", r"oleaginosa",
        r"molienda", r"harina", r"acopio", r"agricola-ganadero", r"uso agricola",
        r"maquinaria agricola", r"agricultura de precision", r"tierras", r"biocombustible",
        r"ganado bovino", r"cria y recria", r"ingenio azucarero", r"azucar", r"melaza", r"bagazo", r"cachaza",
        # --- nuevo ---
        r"actividad forestal", r"plantacion de", r"eucalipto", r"\bpino\b",
        r"fertilizante",
        # --- ampliacion cobertura ---
        r"\briego\b", r"irrigacion", r"frutas?", r"peras|manzanas|ciruelas|duraznos",
    ],
    "Agroquímicos y fitosanitarios": [
        # --- nuevo sector ---
        r"agroquimic", r"herbicida", r"insecticida", r"fungicida",
        r"fitosanitario", r"fosanitario", r"coadyuvante",
    ],
    "Alimentos y bebidas": [
        r"\bmani\b", r"postres", r"caramelos", r"chocolate", r"panificados", r"\bpan\b",
        r"panaderia", r"bebidas sin alcohol", r"biscochos", r"alimentos",
        r"vino", r"bebidas alcoholicas", r"bebidas gaseosas", r"jugos",
        # --- nuevo ---
        r"bebidas con alcohol", r"cerveza", r"leche", r"manteca", r"queso", r"yogur", r"dulce de leche",
        r"crema de leche", r"tambo", r"lacteo", r"suero(s)? de leche",
        # --- ampliacion cobertura ---
        r"pastas?", r"empanadas", r"helados", r"salsas",
    ],
    "Salud y farmacéutico": [
        r"sanatorial", r"servicios sanatoriales", r"medicina prepaga", r"analisis clinicos",
        r"diagnostico por imagenes", r"dialisis", r"medicament", r"farmaceutic",
        r"especialidades medicinales", r"laboratorio", r"\batc", r"inmunosupresores",
        r"antiepilepticos", r"equipamiento medico", r"salud", r"nutrientes",
        r"polivitaminicos", r"reguladores del calcio",
        # --- nuevo ---
        r"ensayos clinicos", r"hormona", r"principio activo", r"somatropina",
        r"gonadotrofina",
        # --- ampliacion cobertura ---
        r"dispositivos? medicos?",
    ],
    "Química, cosmética y limpieza": [
        r"cosmetic", r"perfumeria", r"tocador", r"limpieza e higiene",
        r"productos de limpieza", r"cuidado de la ropa", r"cuidado del aire",
        r"cuidado de superficies", r"control de plagas", r"sustancias quimicas",
        r"envases flexibles",
        # --- nuevo ---
        r"resinas fenolicas", r"surfactante", r"monoetilenglicol", r"\bmeg\b",
        r"etanolamina", r"\beoa\b", r"detergente", r"jabon(es)? para lavar",
        r"productos de belleza", r"cuidado personal", r"recubrimientos",
        # --- ampliacion cobertura ---
        r"revestimientos de alto rendimiento", r"repintado automotor",
        r"revestimientos en polvo", r"productos quimicos",
    ],
    "Minería": [
        r"mineria", r"\bminera\b", r"actividad minera", r"litio",
        # --- ampliacion cobertura ---
        r"minerales? de", r"\bcobre\b", r"molibdeno", r"oro y plata", r"extraccion de minerales",
    ],
    "Metalurgia y siderurgia": [
        # --- nuevo sector ---
        r"aceros?\b", r"acero inoxidable", r"fraccionamiento.*acero",
    ],
    "Papel, cartón y envases": [
        # --- nuevo sector ---
        r"envases de carton", r"carton corrugado", r"papeles? para corruga",
        r"bag-in-box", r"envases flexibles",
        # --- ampliacion cobertura ---
        r"papel(es)?\b", r"\btissue\b", r"pulpa de", r"celulosa",
    ],
    "Madera y muebles": [
        # --- nuevo sector ---
        r"tableros de fibra", r"hardboard", r"chapadur", r"muebles de madera",
    ],
    "Indumentaria y calzado": [
        # --- nuevo sector ---
        r"calzado", r"indumentaria", r"textil\b",
    ],
    "Electrodomésticos y climatización": [
        # --- nuevo sector ---
        r"aires acondicionados", r"electrodomestic",
        # --- ampliacion cobertura ---
        r"climatizacion", r"\bhvac\b", r"calefaccion", r"aire acondicionado",
        r"articulos para el hogar",
    ],
    "Servicios financieros y seguros": [
        r"bancaria", r"entidades bancarias", r"fondos comunes de inversion", r"seguros",
        r"garantia reciproca", r"\bsgr\b", r"avales", r"garantias a mipymes",
        r"activos virtuales", r"psav",
        r"financieros", r"financiera", r"banca", r"aseguradora", r"finanzas",
        # --- nuevo ---
        r"tarjetas de credito", r"procesamiento transaccional",
        r"agente de liquidacion y compensacion", r"\balyc\b",
        r"riesgos del trabajo", r"actividad financiera",
        # --- ampliacion cobertura ---
        r"mercado de capitales", r"\balyc",
    ],
    "Inmobiliario, retail y shoppings": [
        r"inmobiliari", r"espacios comerciales", r"shopping", r"centros comerciales",
        r"hipermercados", r"supermercados", r"comercializacion minorista",
        r"abastecimiento minorista", r"venta al por menor",
        # --- nuevo ---
        r"alquiler de inmuebles", r"oficinas.*clase a",
    ],
    "Logística y transporte": [
        r"agenciamiento", r"gestion de cargas", r"transporte maritimo", r"contenedores",
        r"logistic", r"transporte aereo", r"\bcargas\b", r"linea regular",
        # --- nuevo ---
        r"lineas aereas", r"transporte de caudales",
        # --- ampliacion cobertura ---
        r"\bcaudales\b", r"transporte.*pasajeros", r"aerea|aereo",
    ],
    "Seguridad privada": [
        # --- nuevo sector ---
        r"seguridad y vigilancia", r"guardias especializados", r"monitoreo y alarmas",
    ],
    "Audiovisual, medios y entretenimiento": [
        r"pelicula", r"distribucion de peliculas", r"audiovisual", r"contenido multimedia",
        r"entradas para evento", r"eventos en vivo", r"recintos", r"promocion de eventos",
        # --- nuevo ---
        r"señales de tv", r"licenciamiento.*propiedad intelectual", r"\bott\b", r"\bsvod\b",
        # --- ampliacion cobertura ---
        r"casino", r"juegos de azar", r"\bestadio\b", r"canal de emision",
    ],
    "Publicidad y marketing": [
        # --- nuevo sector ---
        r"publicidad", r"marketing digital", r"agencia creativa",
    ],
    "Automotriz y autopartes": [
        r"vehiculos comerciales", r"vehiculos de pasajeros", r"ruedas de aluminio",
        r"autopartes", r"automotriz", r"concesionarias",
        # --- nuevo ---
        r"tanques.*combustible", r"vehiculos automotores", r"sistemas de propulsion",
        r"combustibles", r"vehiculos", r"\bautos\b",
        # --- ampliacion cobertura ---
        r"repintado automotor",
    ],
    "Construcción y materiales": [
        r"cemento", r"portland", r"hormigon", r"premoldeados", r"vidrio plano",
        r"para la construccion",
        # --- nuevo ---
        r"impermeabilizantes", r"membranas solidas",
        # --- ampliacion cobertura ---
        r"obras de infraestructura", r"obra publica", r"tratamiento de aguas?",        # --- nuevo sector ---
        r"fritas", r"esmaltes", r"baldosas ceramicas", r"revestimientos.*ceramic",
        r"colores de alta calidad", r"colores de baja calidad", r"tintas digitales",
        r"caolin", r"corindon", r"wollastonita",
    ],
    "Pesca": [
        r"\bpesca\b", r"langostino",
        # --- ampliacion cobertura ---
        r"merluza", r"calamar", r"pesquer",
    ],
    "Tecnología y telecomunicaciones": [
        r"tecnologicos", r"satelital", r"infraestructura satelital",
        r"servicios tecnologicos",
        # --- nuevo ---
        r"desarrollo de software", r"integracion de sistemas", r"solucion(es)? como servicio",
        r"copiadoras", r"impresoras laser", r"facsimiles",
        # --- ampliacion cobertura ---
        r"\bsoftware\b", r"call center", r"contact center", r"\bbpo\b",
        r"business process outsourcing", r"television por cable",
    ],
    "Textiles no tejidos": [
        # --- nuevo sector ---
        r"materiales no tejidos",
    ],
    "Hotelería": [
        # --- nuevo sector ---
        r"\bhotel", r"apart hotel", r"apartamentos amoblados",
        r"alojamiento", r"residencial", r"residencias",
    ],
    "Reorganización societaria (sin mercado definido)": [
        # --- nuevo sector: casos art. 7, sin overlap de mercado ---
        r"reorganizacion societaria",
    ],
}
# --------------------------------------------------------------------------- #
# Diccionario de sinonimos: termino de busqueda coloquial -> se agrega al blob
# de busqueda de las filas cuyo texto normalizado matchea el patron fuente.
# Permite que un analista encuentre "lacteos" aunque el texto diga "leche", etc.
# --------------------------------------------------------------------------- #
SINONIMOS: dict[str, list[str]] = {
    r"carne aviar|pollo|avicola": ["avicultura", "aves", "carne de pollo"],
    r"azucar|ingenio": ["azucarero", "cania", "endulzante"],
    r"petroleo|gas natural|servicios petroleros|pozos petroleros|exploracion y produccion de hidrocarburos": [
        "hidrocarburos", "oil and gas", "upstream", "combustibles", "petrolero",
    ],
    r"energia electrica|potencia instalada|generacion de energia|energia eolica|energia solar|energia renovable": [
        "electricidad", "generadora", "electrico", "energetico", "renovables",
    ],
    r"medicina prepaga|sanatorial|analisis clinicos|dialisis|ensayos clinicos": [
        "salud", "clinica", "hospital", "sanatorio",
    ],
    r"medicament|farmaceutic|especialidades medicinales|principio activo|hormona": [
        "farma", "farmacia", "laboratorios medicinales", "pharma",
    ],
    r"soja|maiz|trigo|granos|semillas": ["agro", "agricola", "cereales", "oleaginosas", "campo"],
    r"actividad forestal|plantacion de|eucalipto|\bpino\b": ["forestal", "silvicultura", "madera en pie"],
    r"agroquimic|herbicida|insecticida|fungicida|fitosanitario|fosanitario": [
        "agroquimicos", "fitosanitarios", "productos para el agro",
    ],
    r"leche|manteca|queso|yogur|dulce de leche|crema de leche|tambo|lacteo": [
        "lacteos", "lecheria", "industria lactea",
    ],
    r"cosmetic|perfumeria|tocador|productos de belleza|cuidado personal": [
        "cosmetica", "belleza", "higiene personal",
    ],
    r"pelicula|audiovisual|contenido multimedia|señales de tv|\bott\b|\bsvod\b": [
        "cine", "medios", "streaming", "contenido", "television",
    ],
    r"publicidad|marketing digital|agencia creativa": ["publicidad", "marketing", "medios digitales"],
    r"contenedores|transporte maritimo|agenciamiento": ["shipping", "naviero", "puerto", "flete"],
    r"lineas aereas": ["aerolineas", "transporte aereo", "aviacion comercial"],
    r"transporte de caudales": ["caudales", "logistica de valores", "traslado de dinero"],
    r"cemento|hormigon|premoldeados": ["materiales de construccion", "cementera"],
    r"impermeabilizantes|membranas solidas": ["impermeabilizacion", "membranas"],
    r"vidrio plano": ["cristales", "vidrieria"],
    r"langostino|pesca": ["pesquera", "mariscos", "marisco"],
    r"litio|minera|mineria": ["mineral", "extractivo"],
    r"aceros?\b|acero inoxidable": ["siderurgia", "metalurgia", "acero"],
    r"fritas|esmaltes|baldosas ceramicas|colores de alta calidad|colores de baja calidad|tintas digitales": [
        "ceramica", "revestimientos ceramicos", "insumos ceramicos",
    ],
    r"envases de carton|carton corrugado|papeles? para corruga|bag-in-box": [
        "packaging", "cartonera", "envases",
    ],
    r"tableros de fibra|hardboard|chapadur|muebles de madera": ["mueblera", "industria maderera"],
    r"calzado|indumentaria|textil\b": ["moda", "vestimenta", "retail de moda"],
    r"aires acondicionados|electrodomestic": ["linea blanca", "electro", "climatizacion"],
    r"bancaria|fondos comunes|seguros|tarjetas de credito|agente de liquidacion y compensacion|\balyc\b": [
        "financiero", "banca", "aseguradora", "finanzas", "mercado de capitales",
    ],
    r"riesgos del trabajo|\bart\b(?!iculo)": ["aseguradora de riesgos del trabajo", "cobertura laboral"],
    r"vehiculos|automotriz|autopartes|ruedas de aluminio|tanques.*combustible|sistemas de propulsion": [
        "autos", "automotor", "vehicular",
    ],
    r"limpieza e higiene|productos de limpieza|control de plagas": ["hogar", "cuidado del hogar"],
    r"seguridad y vigilancia|guardias especializados|monitoreo y alarmas": [
        "seguridad privada", "vigilancia",
    ],
    r"alquiler de inmuebles|oficinas.*clase a": ["real estate", "oficinas corporativas"],
    r"mani|postres|caramelos|chocolate": ["golosinas", "confiteria", "snacks"],
    r"panificados|pan|panaderia|harina": ["panaderia", "molienda", "harinas"],
    r"transformadores|alta tension|sistema electrico": ["transmision electrica", "red electrica"],
    r"desarrollo de software|integracion de sistemas|solucion(es)? como servicio": [
        "software", "\\bit\\b", "tecnologia", "saas",
    ],
    r"materiales no tejidos": ["nonwovens", "textiles no tejidos"],
    r"reorganizacion societaria": ["reorganizacion", "restructuracion societaria"],
}


def _match_any(texto_norm: str, patrones: list[str]) -> bool:
    return any(re.search(p, texto_norm) for p in patrones)


def clasificar_sectores(texto_norm: str) -> list[str]:
    return [sec for sec, pats in SECTORES.items() if _match_any(texto_norm, pats)]


def extraer_sinonimos(texto_norm: str) -> list[str]:
    extra: list[str] = []
    for patron, syns in SINONIMOS.items():
        if re.search(patron, texto_norm):
            extra.extend(syns)
    return sorted(set(extra))


# --------------------------------------------------------------------------- #
# Relaciones economicas -> etiquetas normalizadas
# --------------------------------------------------------------------------- #
def normalizar_relaciones(rel_raw: str) -> list[str]:
    n = norm(rel_raw)
    etiquetas = []
    if "horizontal" in n:
        etiquetas.append("Horizontal")
    if "vertical" in n:
        etiquetas.append("Vertical")
    if "conglomerado" in n:
        etiquetas.append("Conglomerado")
    if "cartera" in n:
        etiquetas.append("Efectos de cartera")
    return etiquetas


def etiquetas_cadena(texto_norm: str) -> list[str]:
    tags = []
    if "aguas arriba" in texto_norm:
        tags.append("Aguas arriba")
    if "aguas abajo" in texto_norm:
        tags.append("Aguas abajo")
    return tags


def etiquetas_geografia(texto_norm: str) -> list[str]:
    tags = []
    if "amba" in texto_norm:
        tags.append("AMBA")
    if "exportacion" in texto_norm:
        tags.append("Exportación")
    if "internacional" in texto_norm:
        tags.append("Internacional")
    return tags


# --------------------------------------------------------------------------- #
# Segmentacion de mercados: parte por // y luego por / conservando frases
# --------------------------------------------------------------------------- #
def segmentar_mercados(texto: str) -> list[str]:
    if not texto:
        return []
    partes = re.split(r"//+", texto)
    segs: list[str] = []
    for p in partes:
        # partir tambien por " / " pero cuidando no romper "y/o"
        for q in re.split(r"\s*/\s*", p):
            q = clean(q)
            if len(q) >= 3:
                segs.append(q)
    # dedup conservando orden
    vistos, out = set(), []
    for s in segs:
        k = norm(s)
        if k and k not in vistos:
            vistos.add(k)
            out.append(s)
    return out


# --------------------------------------------------------------------------- #
# Identificador de expediente
# --------------------------------------------------------------------------- #
def parse_carpeta(carpeta: str) -> tuple[str, str, str]:
    """Devuelve (tipo_expediente, numero, prosum_flag) a partir de la Carpeta."""
    c = clean(carpeta)
    prosum = "PROSUM" if re.search(r"prosum", c, re.I) else ""
    tipo = "CONC"
    if re.search(r"^\s*inc", c, re.I):
        tipo = "INC"
    elif re.search(r"opi", c, re.I):
        tipo = "OPI"
    elif re.search(r"\bdp\b", c, re.I):
        tipo = "DP"
    m = re.search(r"(\d{3,4})", c)
    numero = m.group(1) if m else ""
    return tipo, numero, prosum


# --------------------------------------------------------------------------- #
# Construccion del dataset
# --------------------------------------------------------------------------- #
def build_records() -> list[dict]:
    df = pd.read_excel(ARCHIVO, sheet_name=HOJA, header=0)
    df.columns = [norm(c) for c in df.columns]

    col = {
        "carpeta": "carpeta",
        "caratula": "caratula",
        "fecha": "fecha_firma",
        "decision": "decision",
        "res": "numero de resolucion",
        "dict": "numero de dictamen",
        "mercado": "mercados relevantes",
        "rel": "relaciones economicas",
    }

    registros: list[dict] = []
    for i, row in df.iterrows():
        mercado_raw = clean(row.get(col["mercado"]))
        caratula = clean(row.get(col["caratula"]))
        carpeta = clean(row.get(col["carpeta"]))
        if not carpeta and not mercado_raw:
            continue

        tipo, numero, prosum = parse_carpeta(carpeta)

        fecha = row.get(col["fecha"])
        try:
            fecha_str = pd.to_datetime(fecha).strftime("%d/%m/%Y")
        except Exception:
            fecha_str = ""

        # texto base para clasificar/buscar = mercado + caratula
        base_norm = norm(mercado_raw + " " + caratula)

        sectores = clasificar_sectores(base_norm)
        if not sectores:
            sectores = ["Otros / sin clasificar"]

        relaciones = normalizar_relaciones(row.get(col["rel"]))
        cadena = etiquetas_cadena(base_norm)
        geografia = etiquetas_geografia(base_norm)
        segmentos = segmentar_mercados(mercado_raw)
        sinonimos = extraer_sinonimos(base_norm)

        # blob de busqueda (todo lo indexable, normalizado)
        blob = norm(" ".join([
            carpeta, caratula, mercado_raw,
            " ".join(sectores), " ".join(relaciones),
            " ".join(cadena), " ".join(geografia),
            " ".join(sinonimos),
        ]))

        registros.append({
            "id": int(i),
            "carpeta": carpeta,
            "tipo": tipo,
            "numero": numero,
            "prosum": bool(prosum),
            "caratula": caratula,
            "fecha_firma": fecha_str,
            "decision": clean(row.get(col["decision"])),
            "resolucion": clean(row.get(col["res"])),
            "dictamen": clean(row.get(col["dict"])),
            "mercado_raw": mercado_raw,
            "segmentos": segmentos,
            "relaciones": relaciones,
            "relacion_raw": clean(row.get(col["rel"])),
            "cadena": cadena,
            "geografia": geografia,
            "sectores": sectores,
            "sinonimos": sinonimos,
            "search": blob,
        })
    return registros


def build_dataframe() -> pd.DataFrame:
    recs = build_records()
    df = pd.DataFrame(recs)
    for c in ["segmentos", "relaciones", "cadena", "geografia", "sectores", "sinonimos"]:
        df[c] = df[c].apply(lambda x: " | ".join(x))
    return df


if __name__ == "__main__":
    recs = build_records()
    # JSON (para el buscador)
    Path("mercados_nomenclador.json").write_text(
        json.dumps(recs, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    # CSV (para revision en Excel)
    df = build_dataframe()
    df.to_csv("mercados_nomenclador.csv", index=False, encoding="utf-8-sig")

    # Resumen por sector
    from collections import Counter
    cont = Counter()
    for r in recs:
        for s in r["sectores"]:
            cont[s] += 1
    print(f"Registros: {len(recs)}")
    print("Sectores:")
    for s, n in cont.most_common():
        print(f"  {n:2d}  {s}")
