# -*- coding: utf-8 -*-
"""
Nomenclador y buscador de mercados relevantes (ANC).

Lee firm4.xlsx (esta carpeta), normaliza la columna "Mercados relevantes",
segmenta cada mercado y clasifica cada expediente en un nomenclador de
sectores + etiquetas (relacion economica, cadena aguas arriba/abajo, alcance
geografico).

Los PRODUCTOS de cada expediente ya no se calculan aca: se leen de la columna
`productos` del Excel, que genera extraer_productos.py y se corrige a mano.
Los sectores tambien salen del Excel (columna `productos_sector`) y solo se
calculan con SECTORES cuando esa celda esta vacia. El dict PRODUCTOS de este
archivo quedo como catalogo de deteccion para el extractor.

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

ARCHIVO = Path(__file__).parent / "firm4.xlsx"
HOJA = "Sheet1"

# Columnas que genera extraer_productos.py sobre el propio Excel y que son la
# fuente de verdad de productos y sectores (editables a mano desde Excel).
C_PRODUCTOS = "productos"
C_PROD_SECTOR = "productos_sector"


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


# marcas para decir "esta celda esta revisada y va vacia": el extractor las
# respeta (la celda no esta vacia) y el buscador las ignora.
MARCAS_VACIO = {"-", "--", "ninguno", "ninguna", "nada", "sin productos", "n/a", "s/d"}


def parse_lista(valor) -> list[str]:
    """Parte una celda con items separados por '|' (formato de las columnas
    `productos` y `productos_sector`) en una lista limpia y sin repetidos."""
    texto = clean(valor)
    if not texto:
        return []
    vistos, out = set(), []
    for parte in texto.split("|"):
        parte = parte.strip()
        k = norm(parte)
        if k and k not in vistos and k not in MARCAS_VACIO:
            vistos.add(k)
            out.append(parte)
    return out


# --------------------------------------------------------------------------- #
# Nomenclador de sectores.  Cada sector -> lista de patrones (regex sobre texto
# normalizado sin acentos).  Un expediente puede pertenecer a varios sectores.
# --------------------------------------------------------------------------- #
SECTORES: dict[str, list[str]] = {
    "Hidrocarburos (petroleo y gas)": [
        r"petroleo", r"gas natural", r"\bde gas\b", r"explotacion de petroleo",
        r"exploracion y explotacion", r"servicios petroleros", r"insumos y servicios petroleros",
        r"perforacion", r"plataforma de perforacion", r"produccion de gas",
        # --- nuevo ---
        r"exploracion y produccion de hidrocarburos", r"produccion de hidrocarburos",
        r"pozos petroleros", r"estimulacion.*pozos", r"empresas petroleras",
        # --- ampliacion cobertura ---
        r"hidrocarburos", r"fractura hidraulica", r"yacimiento",
        r"distribucion minorista de combustibles", r"lubricantes",r"glp",r"gnl",r"gas licuado de petroleo",
        r"gas natural licuado",r"gas natural comprimido",r"diesel",

    ],
    "Energia electrica": [
        r"energia electrica", r"potencia instalada", r"infraestructura electrica",
        r"energia nuclear", r"transformadores", r"autotransformadores",
        r"sistema electrico", r"alta( y extra alta)? tension", r"generacion de energia",r"distribucion de energia; electrica",
        # --- nuevo ---
        r"alquiler de generadores", r"suministro de electricidad",
        r"eolica", r"solar", r"renovable", r"hidraulica", r"geotermica", r"mareomotriz",
        r"energia eolica", r"energia solar", r"energia renovable",r"Interconexion Electrica",
        r"energia hidraulica", r"energia geotermica", r"energia mareomotriz",
        # --- ampliacion cobertura ---
        r"parque eolico", r"planta eolica", r"transporte de electricidad",
        r"transporte de energia electrica", r"generacion electrica", r"central hidroelectrica",r"distribucion de energia",
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
        r"fertilizante",r"agropecuaria", r"agroindustria", r"agroalimentario", r"agroindustrial",
        # --- ampliacion cobertura ---
        r"\briego\b", r"irrigacion", r"frutas?", r"peras|manzanas|ciruelas|duraznos",
    ],
    "Agroquimicos y fitosanitarios": [
        # --- nuevo sector ---
        r"agroquimic", r"herbicida", r"insecticida", r"fungicida",
        r"fitosanitario", r"fotosanitarios", r"coadyuvante",
    ],
    "Consultoria economica": [
     r"consultor", r"consulting", r"consultancy", r"asesor(?:ia|amiento)?", r"advisory",
    r"servicios profesionales", r"consultor(?:es)?",
    r"consultoria estrategica", r"consultoria empresarial", r"consultoria de gestion", r"consultoria economica",
    r"consultoria financiera",r"consultoria tecnologica", r"consultoria informatica", r"consultoria en negocios",
    r"servicios de consultoria",r"estudios de mercado",r"trabajo cooperativo",r"apoyo financiero",
],
    "Alimentos y bebidas": [
        r"\bmani\b", r"postres", r"caramelos", r"chocolate", r"panificados", r"\bpan\b",
        r"panaderia", r"bebidas sin alcohol", r"biscochos", r"alimentos",r"embutidos",r"bebidas", r"bebidas sin alcohol",
        r"\bvinos?\b", r"bebidas alcoholicas", r"bebidas gaseosas", r"jugos",r"fiambres", r"snacks", r"golosinas", r"confiteria", r"helados",
        # --- nuevo ---
        r"bebidas con alcohol", r"cerveza", r"leche", r"manteca", r"queso", r"yogur", r"dulce de leche",
        r"crema de leche", r"tambo", r"lacteo", r"suero(s)? de leche",r"frutos",r"productos alimenticios",
        # --- ampliacion cobertura ---
        r"pastas?", r"empanadas", r"helados", r"salsas",r"alimentacion", r"alimentos y bebidas",r"aperitivo",

    ],
    "Salud y farmaceutico": [
        r"sanatorial", r"servicios sanatoriales", r"medicina prepaga", r"analisis clinicos",
        r"diagnostico por imagenes", r"dialisis", r"medicament", r"farmaceutic",
        r"especialidades medicinales", r"laboratorio", r"\batc", r"inmunosupresores",
        r"antiepilepticos", r"equipamiento medico", r"salud", r"nutrientes",
        r"polivitaminicos", r"reguladores del calcio",r"cicatrices",r"productos medicos",r"estudios geneticos",r"enfermedades raras",
        # --- nuevo ---
        r"ensayos clinicos", r"hormona", r"principio activo", r"somatropina",r"estudios geneticos",
        r"gonadotrofina",
        # --- ampliacion cobertura ---
        r"dispositivos? medicos?",r"medico",r"medicos",r"hospitales",r"hospitalaria",r"hospitalario",r"hospitalizacion",r"hospitalizacion domiciliaria",
    ],
    "Quimica, cosmetica y limpieza": [
        r"cosmetic", r"perfumeria", r"tocador", r"limpieza e higiene",
        r"productos de limpieza", r"cuidado de la ropa", r"cuidado del aire",
        r"cuidado de superficies", r"control de plagas", r"sustancias quimicas",
        r"envases flexibles",r"acidos",r"bases",r"solventes",r"resinas",r"resinas epoxi",r"resinas poliester",r"resinas poliester",
        r"oxigeno", r"oxigeno liquido",r"shampoos",r"detergentes",r"jabon",r"jabon liquido",r"jabon en polvo",r"jabon en barra",r"jabon para lavar",
        # --- nuevo ---
        r"resinas fenolicas", r"surfactante", r"monoetilenglicol", r"\bmeg\b",
        r"etanolamina", r"\beoa\b", r"detergente", r"jabon(es)? para lavar",
        r"productos de belleza", r"cuidado personal", r"recubrimientos",
        # --- ampliacion cobertura ---
        r"revestimientos de alto rendimiento", r"repintado automotor",r"fosfatos",
        r"revestimientos en polvo", r"productos quimicos",r"petroquimicos",r"petroquimicos",r"petroquimica",r"petroquimica",

    ],
    "Mineria": [
        r"mineria", r"\bminera\b", r"actividad minera", r"litio",
        # --- ampliacion cobertura ---
        r"minerales? de", r"\bcobre\b", r"molibdeno", r"oro y plata", r"extraccion de minerales",
    ],
    "Papel, carton y envases": [
        # --- nuevo sector ---
        r"envases de carton", r"carton corrugado", r"papeles? para corruga",
        r"bag-in-box", r"envases flexibles",r"papeleria",r"papelera",r"papel y carton",
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
    "Electrodomesticos y climatizacion": [
        # --- nuevo sector ---
        r"aires acondicionados", r"electrodomestic",
        # --- ampliacion cobertura ---
        r"climatizacion", r"\bhvac\b", r"calefaccion", r"aire acondicionado",
        r"articulos para el hogar",r"acondicionamiento climatico",
    ],
    "Servicios financieros y seguros": [
        r"bancaria", r"entidades bancarias", r"fondos comunes de inversion", r"seguros",
        r"garantia reciproca", r"\bsgr\b", r"avales", r"garantias a mipymes",
        r"activos virtuales", r"psav",r"leasing", r"factoring", r"financiamiento", r"tarjetas de credito",
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
        r"abastecimiento minorista", r"venta al por menor", r"venta online",
        # --- nuevo ---
        r"alquiler de inmuebles", r"oficinas.*clase a",r"centro comercial", r"centros comerciales", r"retail", r"comercio minorista",
    ],
    "Logistica y transporte": [
        r"agenciamiento", r"gestion de cargas", r"transporte maritimo", r"contenedores",
        r"logistic", r"transporte aereo", r"\bcargas\b", r"linea regular",r"aerolineas",r"transporte de mercaderias",r"transporte de pasajeros",
        # --- nuevo ---
        r"lineas aereas", r"transporte de caudales",
        # --- ampliacion cobertura ---
        r"\bcaudales\b", r"transporte.*pasajeros", r"aerea|aereo",r"remolque", r"transporte de mercaderias",
        r"recoleccion de residuos", r"transporte de residuos", r"transporte de carga", r"transporte de valores",r"remolque",
    ],
    "Seguridad privada": [
        # --- nuevo sector ---
        r"seguridad y vigilancia", r"guardias especializados", r"monitoreo y alarmas",r"custodia",
        r"monitoreo para hogares",r"monitoreo de alarmas",r"monitoreo de seguridad",r"seguridad informatica",
    ],
    "Audiovisual, medios y entretenimiento": [
        r"pelicula", r"distribucion de peliculas", r"audiovisual", r"contenido multimedia",
        r"entradas para evento", r"eventos en vivo", r"recintos", r"promocion de eventos",r"distribucion de canales",
        # --- nuevo ---
        r"señales de tv", r"licenciamiento.*propiedad intelectual", r"\bott\b", r"\bsvod\b",
        # --- ampliacion cobertura ---
        r"casino", r"juegos de azar", r"\bestadio\b", r"canal de emision",r"telecomunicaciones",
        r"agencia de medios", r"medios de comunicacion", r"medios de comunicacion masiva", r"medios de comunicacion digital",
        r"Entretenimiento para el hogar",
        r"television por cable", r"streaming", r"contenido", r"cine",r"tv",r"redes sociales",r"medios de comunicacion",

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
    "Construccion y materiales": [
        r"cemento", r"portland", r"hormigon", r"premoldeados", r"vidrio plano",
        r"para la construccion",r"morteros industriales",r"plastico",r"fibra de carbono",r"fibra de vidrio",r"plasticos",
        r"plasticos reforzados con fibra de vidrio",r"revestimientos industriales",
        r"aceros?\b", r"acero inoxidable", r"fraccionamiento acero",r"aluminio",r"impermeabilizacion",r"caucho",
        r"revestimientos",r"construccion",r"pinturas",
        # --- nuevo ---
        r"impermeabilizantes", r"membranas solidas",
        # --- ampliacion cobertura ---
        r"obras de infraestructura", r"obra publica", r"tratamiento de aguas?",        # --- nuevo sector ---
        r"fritas", r"esmaltes", r"baldosas ceramicas", r"revestimientos.*ceramic",
        r"colores de alta calidad", r"colores de baja calidad", r"tintas digitales",
        r"caolin", r"corindon", r"wollastonita",r"placa de yeso", r"yeso", r"yesera", r"yeso en polvo", r"yeso para la construccion",
    ],
    "Pesca": [
        r"\bpesca\b", r"langostino",
        # --- ampliacion cobertura ---
        r"merluza", r"calamar", r"pesquer",
    ],
    "Tecnologia y telecomunicaciones": [
        r"tecnologicos", r"satelital", r"infraestructura satelital",
        r"servicios tecnologicos",r"telecomunicaciones", r"telefonia", r"telefonia", r"telefonia movil", r"telefonia fija",
        # --- nuevo ---
        r"desarrollo de software", r"integracion de sistemas", r"solucion(es)? como servicio",
        r"copiadoras", r"impresoras laser", r"facsimiles",r"marketplace",r"plataforma de comercio electronico",r"plataforma de e-commerce",
        # --- ampliacion cobertura ---
        r"\bsoftware\b", r"call center", r"contact center", r"\bbpo\b",r"monitoreo electronico",r"comunicaciones",
        r"business process outsourcing", r"television por cable",r"telecomunicaciones",r"hardware",
        r"redes moviles",r"redes de telecomunicaciones",r"telefonia movil",r"telefonia fija",r"telefonia celular",r"telefonia por internet",
        r"monitoreo para hogares",r"monitoreo de alarmas",r"monitoreo de seguridad",
        r"monitoreo de sistemas de seguridad",r"monitoreo de sistemas de alarma",r"seguridad informatica",
    ],
    "Textiles": [
        # --- nuevo sector ---
        r"materiales no tejidos",r"ropa",r"vestimenta",r"tejidos",r"telas",r"fibra textil",r"fibra de algodon",r"fibra de lana",
        r"fibra de poliester",
    ],
    "Hoteleria": [
        # --- nuevo sector ---
        r"\bhotel", r"apart hotel", r"apartamentos amoblados",
        r"alojamiento", r"residencial", r"residencias",
    ],
    "Reorganizacion societaria (sin mercado definido)": [
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


# --------------------------------------------------------------------------- #
# CATALOGO de productos. Ya NO lo lee el index: lo usa extraer_productos.py
# para detectar productos en "Mercados relevantes" (V1 + V2) y volcarlos a la
# columna `productos` del propio Excel, que es la fuente de verdad del buscador
# y se corrige a mano desde Excel.
#
# Cada entrada define: nombre tal como se va a mostrar en el index, en que
# sector(es) del nomenclador se lo espera, y con que palabras clave (regex
# sobre texto normalizado, igual que en SECTORES) se lo detecta.
#
# Agregar un producto aca sirve para dos cosas: que las PROXIMAS corridas del
# extractor lo detecten solas (en las filas cuya celda `productos` siga vacia),
# y que el index sepa bajo que mercado agruparlo en el desplegable (campo
# "sectores", ver productos_por_sector). Para sumarlo a un expediente puntual
# alcanza con escribirlo en la celda del Excel; para moverlo de mercado en el
# desplegable hay que editar su "sectores" aca.
# --------------------------------------------------------------------------- #
PRODUCTOS: dict[str, dict] = {
    'ALYCs': {"sectores": ['Servicios financieros y seguros'], "patrones": [r"\balyc\b"]},
    'ATC': {"sectores": ['Salud y farmaceutico'], "patrones": [r"\batc"]},
    'Abastecimiento minorista': {"sectores": ['Inmobiliario, retail y shoppings'], "patrones": [r"abastecimiento minorista"]},
    'Acero inoxidable': {"sectores": ['Construccion y materiales'], "patrones": [r"acero inoxidable"]},
    'Aceros': {"sectores": ['Construccion y materiales'], "patrones": [r"aceros?\b"]},
    'Acondicionamiento climático': {"sectores": ['Electrodomesticos y climatizacion'], "patrones": [r"acondicionamiento climatico"]},
    'Acopio': {"sectores": ['Agroindustria, granos y semillas'], "patrones": [r"acopio"]},
    'Actividad financiera': {"sectores": ['Servicios financieros y seguros'], "patrones": [r"actividad financiera"]},
    'Actividad forestal': {"sectores": ['Agroindustria, granos y semillas'], "patrones": [r"actividad forestal"]},
    'Actividad minera': {"sectores": ['Mineria'], "patrones": [r"actividad minera"]},
    'Activos virtuales': {"sectores": ['Servicios financieros y seguros'], "patrones": [r"activos virtuales"]},
    'Advisory': {"sectores": ['Consultoria economica'], "patrones": [r"advisory"]},
    'Aerea': {"sectores": ['Logistica y transporte'], "patrones": [r"aerea|aereo"]},
    'Aereo': {"sectores": ['Logistica y transporte'], "patrones": [r"aerea|aereo"]},
    'Aerolineas': {"sectores": ['Logistica y transporte'], "patrones": [r"aerolineas"]},
    'Agencia creativa': {"sectores": ['Publicidad y marketing'], "patrones": [r"agencia creativa"]},
    'Agencia de medios': {"sectores": ['Audiovisual, medios y entretenimiento'], "patrones": [r"agencia de medios"]},
    'Agenciamiento': {"sectores": ['Logistica y transporte'], "patrones": [r"agenciamiento"]},
    'Agente de liquidación y compensación': {"sectores": ['Servicios financieros y seguros'], "patrones": [r"agente de liquidacion y compensacion"]},
    'Agricola-ganadero': {"sectores": ['Agroindustria, granos y semillas'], "patrones": [r"agricola-ganadero"]},
    'Agricultura de precisión': {"sectores": ['Agroindustria, granos y semillas'], "patrones": [r"agricultura de precision"]},
    'Agroalimentario': {"sectores": ['Agroindustria, granos y semillas'], "patrones": [r"agroalimentario"]},
    'Agroindustria': {"sectores": ['Agroindustria, granos y semillas'], "patrones": [r"agroindustria"]},
    'Agroindustrial': {"sectores": ['Agroindustria, granos y semillas'], "patrones": [r"agroindustrial"]},
    'Agropecuaria': {"sectores": ['Agroindustria, granos y semillas'], "patrones": [r"agropecuaria"]},
    'Agroquimic': {"sectores": ['Agroquimicos y fitosanitarios'], "patrones": [r"agroquimic"]},
    'Aire acondicionado': {"sectores": ['Electrodomesticos y climatizacion'], "patrones": [r"aire acondicionado"]},
    'Aires acondicionados': {"sectores": ['Electrodomesticos y climatizacion'], "patrones": [r"aires acondicionados"]},
    'Alimentación': {"sectores": ['Alimentos y bebidas'], "patrones": [r"alimentacion"]},
    'Alimentos': {"sectores": ['Alimentos y bebidas'], "patrones": [r"alimentos"]},
    'Alimentos y bebidas': {"sectores": ['Alimentos y bebidas'], "patrones": [r"alimentos y bebidas"]},
    'Alojamiento': {"sectores": ['Hoteleria'], "patrones": [r"alojamiento"]},
    'Alquiler de generadores': {"sectores": ['Energia electrica'], "patrones": [r"alquiler de generadores"]},
    'Alquiler de inmuebles': {"sectores": ['Inmobiliario, retail y shoppings'], "patrones": [r"alquiler de inmuebles"]},
    'Alta y extra alta tensión': {"sectores": ['Energia electrica'], "patrones": [r"alta( y extra alta)? tension"]},
    'Aluminio': {"sectores": ['Construccion y materiales'], "patrones": [r"aluminio"]},
    'Antiepilépticos': {"sectores": ['Salud y farmaceutico'], "patrones": [r"antiepilepticos"]},
    'Análisis clínicos': {"sectores": ['Salud y farmaceutico'], "patrones": [r"analisis clinicos"]},
    'Apart hotel': {"sectores": ['Hoteleria'], "patrones": [r"apart hotel"]},
    'Apartamentos amoblados': {"sectores": ['Hoteleria'], "patrones": [r"apartamentos amoblados"]},
    'Aperitivo': {"sectores": ['Alimentos y bebidas'], "patrones": [r"aperitivo"]},
    'Apoyo financiero': {"sectores": ['Consultoria economica'], "patrones": [r"apoyo financiero"]},
    'Articulos para el hogar': {"sectores": ['Electrodomesticos y climatizacion'], "patrones": [r"articulos para el hogar"]},
    'Aseguradora': {"sectores": ['Servicios financieros y seguros'], "patrones": [r"aseguradora"]},
    'Asesoramiento': {"sectores": ['Consultoria economica'], "patrones": [r"asesor(?:ia|amiento)?"]},
    'Asesoría': {"sectores": ['Consultoria economica'], "patrones": [r"asesor(?:ia|amiento)?"]},
    'Audiovisual': {"sectores": ['Audiovisual, medios y entretenimiento'], "patrones": [r"audiovisual"]},
    'Automotriz': {"sectores": ['Automotriz y autopartes'], "patrones": [r"automotriz"]},
    'Autopartes': {"sectores": ['Automotriz y autopartes'], "patrones": [r"autopartes"]},
    'Autos': {"sectores": ['Automotriz y autopartes'], "patrones": [r"\bautos\b"]},
    'Autotransformadores': {"sectores": ['Energia electrica'], "patrones": [r"autotransformadores"]},
    'Avales': {"sectores": ['Servicios financieros y seguros'], "patrones": [r"avales"]},
    'Avícola': {"sectores": ['Carne y avicultura'], "patrones": [r"avicola"]},
    'Azúcar': {"sectores": ['Agroindustria, granos y semillas'], "patrones": [r"azucar"]},
    'Bag-in-box': {"sectores": ['Papel, carton y envases'], "patrones": [r"bag-in-box"]},
    'Bagazo': {"sectores": ['Agroindustria, granos y semillas'], "patrones": [r"bagazo"]},
    'Baldosas cerámicas': {"sectores": ['Construccion y materiales'], "patrones": [r"baldosas ceramicas"]},
    'Banca': {"sectores": ['Servicios financieros y seguros'], "patrones": [r"banca"]},
    'Bancaria': {"sectores": ['Servicios financieros y seguros'], "patrones": [r"bancaria"]},
    'Bases': {"sectores": ['Quimica, cosmetica y limpieza'], "patrones": [r"bases"]},
    'Bebidas': {"sectores": ['Alimentos y bebidas'], "patrones": [r"bebidas"]},
    'Bebidas alcoholicas': {"sectores": ['Alimentos y bebidas'], "patrones": [r"bebidas alcoholicas"]},
    'Bebidas con alcohol': {"sectores": ['Alimentos y bebidas'], "patrones": [r"bebidas con alcohol"]},
    'Bebidas gaseosas': {"sectores": ['Alimentos y bebidas'], "patrones": [r"bebidas gaseosas"]},
    'Bebidas sin alcohol': {"sectores": ['Alimentos y bebidas'], "patrones": [r"bebidas sin alcohol"]},
    'Biocombustible': {"sectores": ['Agroindustria, granos y semillas'], "patrones": [r"biocombustible"]},
    'Biscochos': {"sectores": ['Alimentos y bebidas'], "patrones": [r"biscochos"]},
    'Business process outsourcing': {"sectores": ['Tecnologia y telecomunicaciones'], "patrones": [r"business process outsourcing"]},
    'Cachaza': {"sectores": ['Agroindustria, granos y semillas'], "patrones": [r"cachaza"]},
    'Calamar': {"sectores": ['Pesca'], "patrones": [r"calamar"]},
    'Calefacción': {"sectores": ['Electrodomesticos y climatizacion'], "patrones": [r"calefaccion"]},
    'Call center': {"sectores": ['Tecnologia y telecomunicaciones'], "patrones": [r"call center"]},
    'Calzado': {"sectores": ['Indumentaria y calzado'], "patrones": [r"calzado"]},
    'Canal de emisión': {"sectores": ['Audiovisual, medios y entretenimiento'], "patrones": [r"canal de emision"]},
    'Caolín': {"sectores": ['Construccion y materiales'], "patrones": [r"caolin"]},
    'Caramelos': {"sectores": ['Alimentos y bebidas'], "patrones": [r"caramelos"]},
    'Cargas': {"sectores": ['Logistica y transporte'], "patrones": [r"\bcargas\b"]},
    'Carne': {"sectores": ['Carne y avicultura'], "patrones": [r"carne"]},
    'Carne aviar': {"sectores": ['Carne y avicultura'], "patrones": [r"carne aviar"]},
    'Cartón corrugado': {"sectores": ['Papel, carton y envases'], "patrones": [r"carton corrugado"]},
    'Casino': {"sectores": ['Audiovisual, medios y entretenimiento'], "patrones": [r"casino"]},
    'Caucho': {"sectores": ['Construccion y materiales'], "patrones": [r"caucho"]},
    'Caudales': {"sectores": ['Logistica y transporte'], "patrones": [r"\bcaudales\b"]},
    'Celulosa': {"sectores": ['Papel, carton y envases'], "patrones": [r"celulosa"]},
    'Cemento': {"sectores": ['Construccion y materiales'], "patrones": [r"cemento"]},
    'Central hidroeléctrica': {"sectores": ['Energia electrica'], "patrones": [r"central hidroelectrica"]},
    'Centro comercial': {"sectores": ['Inmobiliario, retail y shoppings'], "patrones": [r"centro comercial"]},
    'Centros comerciales': {"sectores": ['Inmobiliario, retail y shoppings'], "patrones": [r"centros comerciales"]},
    'Cerveza': {"sectores": ['Alimentos y bebidas'], "patrones": [r"cerveza"]},
    'Chapadur': {"sectores": ['Madera y muebles'], "patrones": [r"chapadur"]},
    'Chocolate': {"sectores": ['Alimentos y bebidas'], "patrones": [r"chocolate"]},
    'Cicatrices': {"sectores": ['Salud y farmaceutico'], "patrones": [r"cicatrices"]},
    'Cine': {"sectores": ['Audiovisual, medios y entretenimiento'], "patrones": [r"cine"]},
    'Ciruelas': {"sectores": ['Agroindustria, granos y semillas'], "patrones": [r"peras|manzanas|ciruelas|duraznos"]},
    'Climatización': {"sectores": ['Electrodomesticos y climatizacion'], "patrones": [r"climatizacion"]},
    'Coadyuvante': {"sectores": ['Agroquimicos y fitosanitarios'], "patrones": [r"coadyuvante"]},
    'Cobre': {"sectores": ['Mineria'], "patrones": [r"\bcobre\b"]},
    'Colores de alta calidad': {"sectores": ['Construccion y materiales'], "patrones": [r"colores de alta calidad"]},
    'Colores de baja calidad': {"sectores": ['Construccion y materiales'], "patrones": [r"colores de baja calidad"]},
    'Combustibles': {"sectores": ['Automotriz y autopartes'], "patrones": [r"combustibles"]},
    'Comercialización minorista': {"sectores": ['Inmobiliario, retail y shoppings'], "patrones": [r"comercializacion minorista"]},
    'Comercio minorista': {"sectores": ['Inmobiliario, retail y shoppings'], "patrones": [r"comercio minorista"]},
    'Comunicaciones': {"sectores": ['Tecnologia y telecomunicaciones'], "patrones": [r"comunicaciones"]},
    'Concesionarias': {"sectores": ['Automotriz y autopartes'], "patrones": [r"concesionarias"]},
    'Confitería': {"sectores": ['Alimentos y bebidas'], "patrones": [r"confiteria"]},
    'Construcción': {"sectores": ['Construccion y materiales'], "patrones": [r"construccion"]},
    'Consultancy': {"sectores": ['Consultoria economica'], "patrones": [r"consultancy"]},
    'Consulting': {"sectores": ['Consultoria economica'], "patrones": [r"consulting"]},
    'Consultor': {"sectores": ['Consultoria economica'], "patrones": [r"consultor"]},
    'Consultoria de gestión': {"sectores": ['Consultoria economica'], "patrones": [r"consultoria de gestion"]},
    'Consultoria económica': {"sectores": ['Consultoria economica'], "patrones": [r"consultoria economica"]},
    'Consultoria empresarial': {"sectores": ['Consultoria economica'], "patrones": [r"consultoria empresarial"]},
    'Consultoria en negocios': {"sectores": ['Consultoria economica'], "patrones": [r"consultoria en negocios"]},
    'Consultoria estratégica': {"sectores": ['Consultoria economica'], "patrones": [r"consultoria estrategica"]},
    'Consultoria financiera': {"sectores": ['Consultoria economica'], "patrones": [r"consultoria financiera"]},
    'Consultoria informática': {"sectores": ['Consultoria economica'], "patrones": [r"consultoria informatica"]},
    'Consultoria tecnológica': {"sectores": ['Consultoria economica'], "patrones": [r"consultoria tecnologica"]},
    'Contact center': {"sectores": ['Tecnologia y telecomunicaciones'], "patrones": [r"contact center"]},
    'Contenedores': {"sectores": ['Logistica y transporte'], "patrones": [r"contenedores"]},
    'Contenido': {"sectores": ['Audiovisual, medios y entretenimiento'], "patrones": [r"contenido"]},
    'Contenido multimedia': {"sectores": ['Audiovisual, medios y entretenimiento'], "patrones": [r"contenido multimedia"]},
    'Control de plagas': {"sectores": ['Quimica, cosmetica y limpieza'], "patrones": [r"control de plagas"]},
    'Copiadoras': {"sectores": ['Tecnologia y telecomunicaciones'], "patrones": [r"copiadoras"]},
    'Corindón': {"sectores": ['Construccion y materiales'], "patrones": [r"corindon"]},
    'Cosmetic': {"sectores": ['Quimica, cosmetica y limpieza'], "patrones": [r"cosmetic"]},
    'Crema de leche': {"sectores": ['Alimentos y bebidas'], "patrones": [r"crema de leche"]},
    'Cría y recría': {"sectores": ['Agroindustria, granos y semillas'], "patrones": [r"cria y recria"]},
    'Cuidado de la ropa': {"sectores": ['Quimica, cosmetica y limpieza'], "patrones": [r"cuidado de la ropa"]},
    'Cuidado de superficies': {"sectores": ['Quimica, cosmetica y limpieza'], "patrones": [r"cuidado de superficies"]},
    'Cuidado del aire': {"sectores": ['Quimica, cosmetica y limpieza'], "patrones": [r"cuidado del aire"]},
    'Cuidado personal': {"sectores": ['Quimica, cosmetica y limpieza'], "patrones": [r"cuidado personal"]},
    'Custodia': {"sectores": ['Seguridad privada'], "patrones": [r"custodia"]},
    'Detergente': {"sectores": ['Quimica, cosmetica y limpieza'], "patrones": [r"detergente"]},
    'Detergentes': {"sectores": ['Quimica, cosmetica y limpieza'], "patrones": [r"detergentes"]},
    'Diagnóstico por imágenes': {"sectores": ['Salud y farmaceutico'], "patrones": [r"diagnostico por imagenes"]},
    'Diesel': {"sectores": ['Hidrocarburos (petroleo y gas)'], "patrones": [r"diesel"]},
    'Dispositivos médicos': {"sectores": ['Salud y farmaceutico'], "patrones": [r"dispositivos? medicos?"]},
    'Distribución de canales': {"sectores": ['Audiovisual, medios y entretenimiento'], "patrones": [r"distribucion de canales"]},
    'Distribución de energía': {"sectores": ['Energia electrica'], "patrones": [r"distribucion de energia"]},
    'Distribución de energía eléctrica': {"sectores": ['Energia electrica'], "patrones": [r"distribucion de energia; electrica"]},
    'Distribución de películas': {"sectores": ['Audiovisual, medios y entretenimiento'], "patrones": [r"distribucion de peliculas"]},
    'Distribución minorista de combustibles': {"sectores": ['Hidrocarburos (petroleo y gas)'], "patrones": [r"distribucion minorista de combustibles"]},
    'Diálisis': {"sectores": ['Salud y farmaceutico'], "patrones": [r"dialisis"]},
    'Dulce de leche': {"sectores": ['Alimentos y bebidas'], "patrones": [r"dulce de leche"]},
    'Duraznos': {"sectores": ['Agroindustria, granos y semillas'], "patrones": [r"peras|manzanas|ciruelas|duraznos"]},
    'EOA': {"sectores": ['Quimica, cosmetica y limpieza'], "patrones": [r"\beoa\b"]},
    'Electrodoméstic': {"sectores": ['Electrodomesticos y climatizacion'], "patrones": [r"electrodomestic"]},
    'Embutidos': {"sectores": ['Alimentos y bebidas'], "patrones": [r"embutidos"]},
    'Empanadas': {"sectores": ['Alimentos y bebidas'], "patrones": [r"empanadas"]},
    'Empresas petroleras': {"sectores": ['Hidrocarburos (petroleo y gas)'], "patrones": [r"empresas petroleras"]},
    'Energía eléctrica': {"sectores": ['Energia electrica'], "patrones": [r"energia electrica"]},
    'Energía eólica': {"sectores": ['Energia electrica'], "patrones": [r"energia eolica"]},
    'Energía geotérmica': {"sectores": ['Energia electrica'], "patrones": [r"energia geotermica"]},
    'Energía hidráulica': {"sectores": ['Energia electrica'], "patrones": [r"energia hidraulica"]},
    'Energía mareomotriz': {"sectores": ['Energia electrica'], "patrones": [r"energia mareomotriz"]},
    'Energía nuclear': {"sectores": ['Energia electrica'], "patrones": [r"energia nuclear"]},
    'Energía renovable': {"sectores": ['Energia electrica'], "patrones": [r"energia renovable"]},
    'Energía solar': {"sectores": ['Energia electrica'], "patrones": [r"energia solar"]},
    'Enfermedades raras': {"sectores": ['Salud y farmaceutico'], "patrones": [r"enfermedades raras"]},
    'Ensayos clínicos': {"sectores": ['Salud y farmaceutico'], "patrones": [r"ensayos clinicos"]},
    'Entidades bancarias': {"sectores": ['Servicios financieros y seguros'], "patrones": [r"entidades bancarias"]},
    'Entradas para evento': {"sectores": ['Audiovisual, medios y entretenimiento'], "patrones": [r"entradas para evento"]},
    'Entretenimiento para el hogar': {"sectores": ['Audiovisual, medios y entretenimiento'], "patrones": [r"Entretenimiento para el hogar"]},
    'Envases de cartón': {"sectores": ['Papel, carton y envases'], "patrones": [r"envases de carton"]},
    'Envases flexibles': {"sectores": ['Quimica, cosmetica y limpieza', 'Papel, carton y envases'], "patrones": [r"envases flexibles"]},
    'Equipamiento médico': {"sectores": ['Salud y farmaceutico'], "patrones": [r"equipamiento medico"]},
    'Esmaltes': {"sectores": ['Construccion y materiales'], "patrones": [r"esmaltes"]},
    'Espacios comerciales': {"sectores": ['Inmobiliario, retail y shoppings'], "patrones": [r"espacios comerciales"]},
    'Especialidades medicinales': {"sectores": ['Salud y farmaceutico'], "patrones": [r"especialidades medicinales"]},
    'Estadio': {"sectores": ['Audiovisual, medios y entretenimiento'], "patrones": [r"\bestadio\b"]},
    'Estimulación pozos': {"sectores": ['Hidrocarburos (petroleo y gas)'], "patrones": [r"estimulacion.*pozos"]},
    'Estudios de mercado': {"sectores": ['Consultoria economica'], "patrones": [r"estudios de mercado"]},
    'Estudios genéticos': {"sectores": ['Salud y farmaceutico'], "patrones": [r"estudios geneticos"]},
    'Etanolamina': {"sectores": ['Quimica, cosmetica y limpieza'], "patrones": [r"etanolamina"]},
    'Eucalipto': {"sectores": ['Agroindustria, granos y semillas'], "patrones": [r"eucalipto"]},
    'Eventos en vivo': {"sectores": ['Audiovisual, medios y entretenimiento'], "patrones": [r"eventos en vivo"]},
    'Exploración y explotación': {"sectores": ['Hidrocarburos (petroleo y gas)'], "patrones": [r"exploracion y explotacion"]},
    'Exploración y producción de hidrocarburos': {"sectores": ['Hidrocarburos (petroleo y gas)'], "patrones": [r"exploracion y produccion de hidrocarburos"]},
    'Explotación de petróleo': {"sectores": ['Hidrocarburos (petroleo y gas)'], "patrones": [r"explotacion de petroleo"]},
    'Extracción de minerales': {"sectores": ['Mineria'], "patrones": [r"extraccion de minerales"]},
    'Eólica': {"sectores": ['Energia electrica'], "patrones": [r"eolica"]},
    'Facsímiles': {"sectores": ['Tecnologia y telecomunicaciones'], "patrones": [r"facsimiles"]},
    'Factoring': {"sectores": ['Servicios financieros y seguros'], "patrones": [r"factoring"]},
    'Farmacéutic': {"sectores": ['Salud y farmaceutico'], "patrones": [r"farmaceutic"]},
    'Fertilizante': {"sectores": ['Agroindustria, granos y semillas'], "patrones": [r"fertilizante"]},
    'Fiambres': {"sectores": ['Alimentos y bebidas'], "patrones": [r"fiambres"]},
    'Fibra de algodón': {"sectores": ['Textiles'], "patrones": [r"fibra de algodon"]},
    'Fibra de carbono': {"sectores": ['Construccion y materiales'], "patrones": [r"fibra de carbono"]},
    'Fibra de lana': {"sectores": ['Textiles'], "patrones": [r"fibra de lana"]},
    'Fibra de poliéster': {"sectores": ['Textiles'], "patrones": [r"fibra de poliester"]},
    'Fibra de vidrio': {"sectores": ['Construccion y materiales'], "patrones": [r"fibra de vidrio"]},
    'Fibra textil': {"sectores": ['Textiles'], "patrones": [r"fibra textil"]},
    'Financiamiento': {"sectores": ['Servicios financieros y seguros'], "patrones": [r"financiamiento"]},
    'Financiera': {"sectores": ['Servicios financieros y seguros'], "patrones": [r"financiera"]},
    'Financieros': {"sectores": ['Servicios financieros y seguros'], "patrones": [r"financieros"]},
    'Finanzas': {"sectores": ['Servicios financieros y seguros'], "patrones": [r"finanzas"]},
    'Fitosanitario': {"sectores": ['Agroquimicos y fitosanitarios'], "patrones": [r"fitosanitario"]},
    'Fondos comunes de inversión': {"sectores": ['Servicios financieros y seguros'], "patrones": [r"fondos comunes de inversion"]},
    'Fosfatos': {"sectores": ['Quimica, cosmetica y limpieza'], "patrones": [r"fosfatos"]},
    'Fotosanitarios': {"sectores": ['Agroquimicos y fitosanitarios'], "patrones": [r"fotosanitarios"]},
    'Fraccionamiento acero': {"sectores": ['Construccion y materiales'], "patrones": [r"fraccionamiento acero"]},
    'Fractura hidráulica': {"sectores": ['Hidrocarburos (petroleo y gas)'], "patrones": [r"fractura hidraulica"]},
    'Fritas': {"sectores": ['Construccion y materiales'], "patrones": [r"fritas"]},
    'Frutas': {"sectores": ['Agroindustria, granos y semillas'], "patrones": [r"frutas?"]},
    'Frutos': {"sectores": ['Alimentos y bebidas'], "patrones": [r"frutos"]},
    'Fungicida': {"sectores": ['Agroquimicos y fitosanitarios'], "patrones": [r"fungicida"]},
    'GLP': {"sectores": ['Hidrocarburos (petroleo y gas)'], "patrones": [r"glp"]},
    'GNL': {"sectores": ['Hidrocarburos (petroleo y gas)'], "patrones": [r"gnl"]},
    'Ganado bovino': {"sectores": ['Agroindustria, granos y semillas'], "patrones": [r"ganado bovino"]},
    'Garantía recíproca': {"sectores": ['Servicios financieros y seguros'], "patrones": [r"garantia reciproca"]},
    'Garantías a mipymes': {"sectores": ['Servicios financieros y seguros'], "patrones": [r"garantias a mipymes"]},
    'Gas licuado de petróleo': {"sectores": ['Hidrocarburos (petroleo y gas)'], "patrones": [r"gas licuado de petroleo"]},
    'Gas natural': {"sectores": ['Hidrocarburos (petroleo y gas)'], "patrones": [r"gas natural"]},
    'Gas natural comprimido': {"sectores": ['Hidrocarburos (petroleo y gas)'], "patrones": [r"gas natural comprimido"]},
    'Gas natural licuado': {"sectores": ['Hidrocarburos (petroleo y gas)'], "patrones": [r"gas natural licuado"]},
    'Generación de energía': {"sectores": ['Energia electrica'], "patrones": [r"generacion de energia"]},
    'Generación eléctrica': {"sectores": ['Energia electrica'], "patrones": [r"generacion electrica"]},
    'Geotérmica': {"sectores": ['Energia electrica'], "patrones": [r"geotermica"]},
    'Gestión de cargas': {"sectores": ['Logistica y transporte'], "patrones": [r"gestion de cargas"]},
    'Golosinas': {"sectores": ['Alimentos y bebidas'], "patrones": [r"golosinas"]},
    'Gonadotrofina': {"sectores": ['Salud y farmaceutico'], "patrones": [r"gonadotrofina"]},
    'Granos': {"sectores": ['Agroindustria, granos y semillas'], "patrones": [r"granos"]},
    'Guardias especializados': {"sectores": ['Seguridad privada'], "patrones": [r"guardias especializados"]},
    'HVAC': {"sectores": ['Electrodomesticos y climatizacion'], "patrones": [r"\bhvac\b"]},
    'Hardboard': {"sectores": ['Madera y muebles'], "patrones": [r"hardboard"]},
    'Hardware': {"sectores": ['Tecnologia y telecomunicaciones'], "patrones": [r"hardware"]},
    'Harina': {"sectores": ['Agroindustria, granos y semillas'], "patrones": [r"harina"]},
    'Helados': {"sectores": ['Alimentos y bebidas'], "patrones": [r"helados"]},
    'Herbicida': {"sectores": ['Agroquimicos y fitosanitarios'], "patrones": [r"herbicida"]},
    'Hidrocarburos': {"sectores": ['Hidrocarburos (petroleo y gas)'], "patrones": [r"hidrocarburos"]},
    'Hidráulica': {"sectores": ['Energia electrica'], "patrones": [r"hidraulica"]},
    'Hipermercados': {"sectores": ['Inmobiliario, retail y shoppings'], "patrones": [r"hipermercados"]},
    'Hormigón': {"sectores": ['Construccion y materiales'], "patrones": [r"hormigon"]},
    'Hormona': {"sectores": ['Salud y farmaceutico'], "patrones": [r"hormona"]},
    'Hospitalaria': {"sectores": ['Salud y farmaceutico'], "patrones": [r"hospitalaria"]},
    'Hospitalario': {"sectores": ['Salud y farmaceutico'], "patrones": [r"hospitalario"]},
    'Hospitales': {"sectores": ['Salud y farmaceutico'], "patrones": [r"hospitales"]},
    'Hospitalización': {"sectores": ['Salud y farmaceutico'], "patrones": [r"hospitalizacion"]},
    'Hospitalización domiciliaria': {"sectores": ['Salud y farmaceutico'], "patrones": [r"hospitalizacion domiciliaria"]},
    'Hotel': {"sectores": ['Hoteleria'], "patrones": [r"\bhotel"]},
    'Impermeabilización': {"sectores": ['Construccion y materiales'], "patrones": [r"impermeabilizacion"]},
    'Impermeabilizantes': {"sectores": ['Construccion y materiales'], "patrones": [r"impermeabilizantes"]},
    'Impresoras láser': {"sectores": ['Tecnologia y telecomunicaciones'], "patrones": [r"impresoras laser"]},
    'Indumentaria': {"sectores": ['Indumentaria y calzado'], "patrones": [r"indumentaria"]},
    'Infraestructura eléctrica': {"sectores": ['Energia electrica'], "patrones": [r"infraestructura electrica"]},
    'Infraestructura satelital': {"sectores": ['Tecnologia y telecomunicaciones'], "patrones": [r"infraestructura satelital"]},
    'Ingenio azucarero': {"sectores": ['Agroindustria, granos y semillas'], "patrones": [r"ingenio azucarero"]},
    'Inmobiliario': {"sectores": ['Inmobiliario, retail y shoppings'], "patrones": [r"inmobiliari"]},
    'Inmunosupresores': {"sectores": ['Salud y farmaceutico'], "patrones": [r"inmunosupresores"]},
    'Insecticida': {"sectores": ['Agroquimicos y fitosanitarios'], "patrones": [r"insecticida"]},
    'Insumos y servicios petroleros': {"sectores": ['Hidrocarburos (petroleo y gas)'], "patrones": [r"insumos y servicios petroleros"]},
    'Integración de sistemas': {"sectores": ['Tecnologia y telecomunicaciones'], "patrones": [r"integracion de sistemas"]},
    'Interconexión eléctrica': {"sectores": ['Energia electrica'], "patrones": [r"Interconexion Electrica"]},
    'Irrigación': {"sectores": ['Agroindustria, granos y semillas'], "patrones": [r"irrigacion"]},
    'Jabones para lavar': {"sectores": ['Quimica, cosmetica y limpieza'], "patrones": [r"jabon(es)? para lavar"]},
    'Jabón': {"sectores": ['Quimica, cosmetica y limpieza'], "patrones": [r"jabon"]},
    'Jabón en barra': {"sectores": ['Quimica, cosmetica y limpieza'], "patrones": [r"jabon en barra"]},
    'Jabón en polvo': {"sectores": ['Quimica, cosmetica y limpieza'], "patrones": [r"jabon en polvo"]},
    'Jabón líquido': {"sectores": ['Quimica, cosmetica y limpieza'], "patrones": [r"jabon liquido"]},
    'Jabón para lavar': {"sectores": ['Quimica, cosmetica y limpieza'], "patrones": [r"jabon para lavar"]},
    'Juegos de azar': {"sectores": ['Audiovisual, medios y entretenimiento'], "patrones": [r"juegos de azar"]},
    'Jugos': {"sectores": ['Alimentos y bebidas'], "patrones": [r"jugos"]},
    'Laboratorio': {"sectores": ['Salud y farmaceutico'], "patrones": [r"laboratorio"]},
    'Langostino': {"sectores": ['Pesca'], "patrones": [r"langostino"]},
    'Leasing': {"sectores": ['Servicios financieros y seguros'], "patrones": [r"leasing"]},
    'Leche': {"sectores": ['Alimentos y bebidas'], "patrones": [r"leche"]},
    'Licenciamiento propiedad intelectual': {"sectores": ['Audiovisual, medios y entretenimiento'], "patrones": [r"licenciamiento.*propiedad intelectual"]},
    'Limpieza e higiene': {"sectores": ['Quimica, cosmetica y limpieza'], "patrones": [r"limpieza e higiene"]},
    'Lineas aereas': {"sectores": ['Logistica y transporte'], "patrones": [r"lineas aereas"]},
    'Litio': {"sectores": ['Mineria'], "patrones": [r"litio"]},
    'Logístic': {"sectores": ['Logistica y transporte'], "patrones": [r"logistic"]},
    'Lubricantes': {"sectores": ['Hidrocarburos (petroleo y gas)'], "patrones": [r"lubricantes"]},
    'Lácteo': {"sectores": ['Alimentos y bebidas'], "patrones": [r"lacteo"]},
    'Línea regular': {"sectores": ['Logistica y transporte'], "patrones": [r"linea regular"]},
    'MEG': {"sectores": ['Quimica, cosmetica y limpieza'], "patrones": [r"\bmeg\b"]},
    'Mani': {"sectores": ['Alimentos y bebidas'], "patrones": [r"\bmani\b"]},
    'Manteca': {"sectores": ['Alimentos y bebidas'], "patrones": [r"manteca"]},
    'Manzanas': {"sectores": ['Agroindustria, granos y semillas'], "patrones": [r"peras|manzanas|ciruelas|duraznos"]},
    'Maquinaria agricola': {"sectores": ['Agroindustria, granos y semillas'], "patrones": [r"maquinaria agricola"]},
    'Mareomotriz': {"sectores": ['Energia electrica'], "patrones": [r"mareomotriz"]},
    'Marketing digital': {"sectores": ['Publicidad y marketing'], "patrones": [r"marketing digital"]},
    'Marketplace': {"sectores": ['Tecnologia y telecomunicaciones'], "patrones": [r"marketplace"]},
    'Materiales no tejidos': {"sectores": ['Textiles'], "patrones": [r"materiales no tejidos"]},
    'Maíz': {"sectores": ['Agroindustria, granos y semillas'], "patrones": [r"\bmaiz\b"]},
    'Medicament': {"sectores": ['Salud y farmaceutico'], "patrones": [r"medicament"]},
    'Medicina prepaga': {"sectores": ['Salud y farmaceutico'], "patrones": [r"medicina prepaga"]},
    'Medios de comunicación': {"sectores": ['Audiovisual, medios y entretenimiento'], "patrones": [r"medios de comunicacion"]},
    'Medios de comunicación digital': {"sectores": ['Audiovisual, medios y entretenimiento'], "patrones": [r"medios de comunicacion digital"]},
    'Medios de comunicación masiva': {"sectores": ['Audiovisual, medios y entretenimiento'], "patrones": [r"medios de comunicacion masiva"]},
    'Melaza': {"sectores": ['Agroindustria, granos y semillas'], "patrones": [r"melaza"]},
    'Membranas sólidas': {"sectores": ['Construccion y materiales'], "patrones": [r"membranas solidas"]},
    'Menudencias': {"sectores": ['Carne y avicultura'], "patrones": [r"menudencias"]},
    'Mercado de capitales': {"sectores": ['Servicios financieros y seguros'], "patrones": [r"mercado de capitales"]},
    'Merluza': {"sectores": ['Pesca'], "patrones": [r"merluza"]},
    'Minera': {"sectores": ['Mineria'], "patrones": [r"\bminera\b"]},
    'Minerales': {"sectores": ['Mineria'], "patrones": [r"minerales? de"]},
    'Minería': {"sectores": ['Mineria'], "patrones": [r"mineria"]},
    'Molibdeno': {"sectores": ['Mineria'], "patrones": [r"molibdeno"]},
    'Molienda': {"sectores": ['Agroindustria, granos y semillas'], "patrones": [r"molienda"]},
    'Monitoreo de alarmas': {"sectores": ['Seguridad privada', 'Tecnologia y telecomunicaciones'], "patrones": [r"monitoreo de alarmas"]},
    'Monitoreo de seguridad': {"sectores": ['Seguridad privada', 'Tecnologia y telecomunicaciones'], "patrones": [r"monitoreo de seguridad"]},
    'Monitoreo de sistemas de alarma': {"sectores": ['Tecnologia y telecomunicaciones'], "patrones": [r"monitoreo de sistemas de alarma"]},
    'Monitoreo de sistemas de seguridad': {"sectores": ['Tecnologia y telecomunicaciones'], "patrones": [r"monitoreo de sistemas de seguridad"]},
    'Monitoreo electrónico': {"sectores": ['Tecnologia y telecomunicaciones'], "patrones": [r"monitoreo electronico"]},
    'Monitoreo para hogares': {"sectores": ['Seguridad privada', 'Tecnologia y telecomunicaciones'], "patrones": [r"monitoreo para hogares"]},
    'Monitoreo y alarmas': {"sectores": ['Seguridad privada'], "patrones": [r"monitoreo y alarmas"]},
    'Monoetilenglicol': {"sectores": ['Quimica, cosmetica y limpieza'], "patrones": [r"monoetilenglicol"]},
    'Morteros industriales': {"sectores": ['Construccion y materiales'], "patrones": [r"morteros industriales"]},
    'Muebles de madera': {"sectores": ['Madera y muebles'], "patrones": [r"muebles de madera"]},
    'Médico': {"sectores": ['Salud y farmaceutico'], "patrones": [r"medico"]},
    'Médicos': {"sectores": ['Salud y farmaceutico'], "patrones": [r"medicos"]},
    'Nutrientes': {"sectores": ['Salud y farmaceutico'], "patrones": [r"nutrientes"]},
    'OTT': {"sectores": ['Audiovisual, medios y entretenimiento'], "patrones": [r"\bott\b"]},
    'Obra pública': {"sectores": ['Construccion y materiales'], "patrones": [r"obra publica"]},
    'Obras de infraestructura': {"sectores": ['Construccion y materiales'], "patrones": [r"obras de infraestructura"]},
    'Oficinas clase a': {"sectores": ['Inmobiliario, retail y shoppings'], "patrones": [r"oficinas.*clase a"]},
    'Oleaginosa': {"sectores": ['Agroindustria, granos y semillas'], "patrones": [r"oleaginosa"]},
    'Oro y plata': {"sectores": ['Mineria'], "patrones": [r"oro y plata"]},
    'Oxígeno': {"sectores": ['Quimica, cosmetica y limpieza'], "patrones": [r"oxigeno"]},
    'Oxígeno líquido': {"sectores": ['Quimica, cosmetica y limpieza'], "patrones": [r"oxigeno liquido"]},
    'PSAV': {"sectores": ['Servicios financieros y seguros'], "patrones": [r"psav"]},
    'Pan': {"sectores": ['Alimentos y bebidas'], "patrones": [r"\bpan\b"]},
    'Panaderia': {"sectores": ['Alimentos y bebidas'], "patrones": [r"panaderia"]},
    'Panificados': {"sectores": ['Alimentos y bebidas'], "patrones": [r"panificados"]},
    'Papel y cartón': {"sectores": ['Papel, carton y envases'], "patrones": [r"papel y carton"]},
    'Papelera': {"sectores": ['Papel, carton y envases'], "patrones": [r"papelera"]},
    'Papelería': {"sectores": ['Papel, carton y envases'], "patrones": [r"papeleria"]},
    'Papeles': {"sectores": ['Papel, carton y envases'], "patrones": [r"papel(es)?\b"]},
    'Papeles para corruga': {"sectores": ['Papel, carton y envases'], "patrones": [r"papeles? para corruga"]},
    'Parque eólico': {"sectores": ['Energia electrica'], "patrones": [r"parque eolico"]},
    'Pastas': {"sectores": ['Alimentos y bebidas'], "patrones": [r"pastas?"]},
    'Película': {"sectores": ['Audiovisual, medios y entretenimiento'], "patrones": [r"pelicula"]},
    'Peras': {"sectores": ['Agroindustria, granos y semillas'], "patrones": [r"peras|manzanas|ciruelas|duraznos"]},
    'Perforacion': {"sectores": ['Hidrocarburos (petroleo y gas)'], "patrones": [r"perforacion"]},
    'Perfumeria': {"sectores": ['Quimica, cosmetica y limpieza'], "patrones": [r"perfumeria"]},
    'Pesca': {"sectores": ['Pesca'], "patrones": [r"\bpesca\b"]},
    'Pesquer': {"sectores": ['Pesca'], "patrones": [r"pesquer"]},
    'Petroquímica': {"sectores": ['Quimica, cosmetica y limpieza'], "patrones": [r"petroquimica"]},
    'Petroquímicos': {"sectores": ['Quimica, cosmetica y limpieza'], "patrones": [r"petroquimicos"]},
    'Petróleo': {"sectores": ['Hidrocarburos (petroleo y gas)'], "patrones": [r"petroleo"]},
    'Pino': {"sectores": ['Agroindustria, granos y semillas'], "patrones": [r"\bpino\b"]},
    'Pinturas': {"sectores": ['Construccion y materiales'], "patrones": [r"pinturas"]},
    'Placa de yeso': {"sectores": ['Construccion y materiales'], "patrones": [r"placa de yeso"]},
    'Planta eólica': {"sectores": ['Energia electrica'], "patrones": [r"planta eolica"]},
    'Plantacion forestal': {"sectores": ['Agroindustria, granos y semillas'], "patrones": [r"plantacion de"]},
    'Plastico': {"sectores": ['Construccion y materiales'], "patrones": [r"plastico"]},
    'Plasticos': {"sectores": ['Construccion y materiales'], "patrones": [r"plasticos"]},
    'Plasticos reforzados con fibra de vidrio': {"sectores": ['Construccion y materiales'], "patrones": [r"plasticos reforzados con fibra de vidrio"]},
    'Plataforma de comercio electrónico': {"sectores": ['Tecnologia y telecomunicaciones'], "patrones": [r"plataforma de comercio electronico"]},
    'Plataforma de e-commerce': {"sectores": ['Tecnologia y telecomunicaciones'], "patrones": [r"plataforma de e-commerce"]},
    'Plataforma de perforacion': {"sectores": ['Hidrocarburos (petroleo y gas)'], "patrones": [r"plataforma de perforacion"]},
    'Polivitamínicos': {"sectores": ['Salud y farmaceutico'], "patrones": [r"polivitaminicos"]},
    'Pollo': {"sectores": ['Carne y avicultura'], "patrones": [r"\bpollo\b"]},
    'Portland': {"sectores": ['Construccion y materiales'], "patrones": [r"portland"]},
    'Postres': {"sectores": ['Alimentos y bebidas'], "patrones": [r"postres"]},
    'Potencia instalada': {"sectores": ['Energia electrica'], "patrones": [r"potencia instalada"]},
    'Pozos petroleros': {"sectores": ['Hidrocarburos (petroleo y gas)'], "patrones": [r"pozos petroleros"]},
    'Premoldeados': {"sectores": ['Construccion y materiales'], "patrones": [r"premoldeados"]},
    'Principio activo': {"sectores": ['Salud y farmaceutico'], "patrones": [r"principio activo"]},
    'Procesamiento transaccional': {"sectores": ['Servicios financieros y seguros'], "patrones": [r"procesamiento transaccional"]},
    'Producción de gas': {"sectores": ['Hidrocarburos (petroleo y gas)'], "patrones": [r"produccion de gas"]},
    'Producción de hidrocarburos': {"sectores": ['Hidrocarburos (petroleo y gas)'], "patrones": [r"produccion de hidrocarburos"]},
    'Productos alimenticios': {"sectores": ['Alimentos y bebidas'], "patrones": [r"productos alimenticios"]},
    'Productos de belleza': {"sectores": ['Quimica, cosmetica y limpieza'], "patrones": [r"productos de belleza"]},
    'Productos de limpieza': {"sectores": ['Quimica, cosmetica y limpieza'], "patrones": [r"productos de limpieza"]},
    'Productos médicos': {"sectores": ['Salud y farmaceutico'], "patrones": [r"productos medicos"]},
    'Productos químicos': {"sectores": ['Quimica, cosmetica y limpieza'], "patrones": [r"productos quimicos"]},
    'Promoción de eventos': {"sectores": ['Audiovisual, medios y entretenimiento'], "patrones": [r"promocion de eventos"]},
    'Publicidad': {"sectores": ['Publicidad y marketing'], "patrones": [r"publicidad"]},
    'Pulpa de celulosa': {"sectores": ['Papel, carton y envases'], "patrones": [r"pulpa de"]},
    'Queso': {"sectores": ['Alimentos y bebidas'], "patrones": [r"queso"]},
    'Recintos': {"sectores": ['Audiovisual, medios y entretenimiento'], "patrones": [r"recintos"]},
    'Recolección de residuos': {"sectores": ['Logistica y transporte'], "patrones": [r"recoleccion de residuos"]},
    'Recubrimientos': {"sectores": ['Quimica, cosmetica y limpieza'], "patrones": [r"recubrimientos"]},
    'Redes de telecomunicaciones': {"sectores": ['Tecnologia y telecomunicaciones'], "patrones": [r"redes de telecomunicaciones"]},
    'Redes móviles': {"sectores": ['Tecnologia y telecomunicaciones'], "patrones": [r"redes moviles"]},
    'Redes sociales': {"sectores": ['Audiovisual, medios y entretenimiento'], "patrones": [r"redes sociales"]},
    'Reguladores del calcio': {"sectores": ['Salud y farmaceutico'], "patrones": [r"reguladores del calcio"]},
    'Remolque': {"sectores": ['Logistica y transporte'], "patrones": [r"remolque"]},
    'Renovable': {"sectores": ['Energia electrica'], "patrones": [r"renovable"]},
    'Reorganización societaria': {"sectores": ['Reorganizacion societaria (sin mercado definido)'], "patrones": [r"reorganizacion societaria"]},
    'Repintado automotor': {"sectores": ['Quimica, cosmetica y limpieza', 'Automotriz y autopartes'], "patrones": [r"repintado automotor"]},
    'Residencial': {"sectores": ['Hoteleria'], "patrones": [r"residencial"]},
    'Residencias': {"sectores": ['Hoteleria'], "patrones": [r"residencias"]},
    'Resinas': {"sectores": ['Quimica, cosmetica y limpieza'], "patrones": [r"resinas"]},
    'Resinas epoxi': {"sectores": ['Quimica, cosmetica y limpieza'], "patrones": [r"resinas epoxi"]},
    'Resinas fenólicas': {"sectores": ['Quimica, cosmetica y limpieza'], "patrones": [r"resinas fenolicas"]},
    'Resinas poliéster': {"sectores": ['Quimica, cosmetica y limpieza'], "patrones": [r"resinas poliester"]},
    'Retail': {"sectores": ['Inmobiliario, retail y shoppings'], "patrones": [r"retail"]},
    'Revestimientos': {"sectores": ['Construccion y materiales'], "patrones": [r"revestimientos"]},
    'Revestimientos cerámicos': {"sectores": ['Construccion y materiales'], "patrones": [r"revestimientos.*ceramic"]},
    'Revestimientos de alto rendimiento': {"sectores": ['Quimica, cosmetica y limpieza'], "patrones": [r"revestimientos de alto rendimiento"]},
    'Revestimientos en polvo': {"sectores": ['Quimica, cosmetica y limpieza'], "patrones": [r"revestimientos en polvo"]},
    'Revestimientos industriales': {"sectores": ['Construccion y materiales'], "patrones": [r"revestimientos industriales"]},
    'Riego': {"sectores": ['Agroindustria, granos y semillas'], "patrones": [r"\briego\b"]},
    'Riesgos del trabajo': {"sectores": ['Servicios financieros y seguros'], "patrones": [r"riesgos del trabajo"]},
    'Ropa': {"sectores": ['Textiles'], "patrones": [r"ropa"]},
    'Ruedas de aluminio': {"sectores": ['Automotriz y autopartes'], "patrones": [r"ruedas de aluminio"]},
    'SGR': {"sectores": ['Servicios financieros y seguros'], "patrones": [r"\bsgr\b"]},
    'SVOD': {"sectores": ['Audiovisual, medios y entretenimiento'], "patrones": [r"\bsvod\b"]},
    'Salsas': {"sectores": ['Alimentos y bebidas'], "patrones": [r"salsas"]},
    'Salud': {"sectores": ['Salud y farmaceutico'], "patrones": [r"salud"]},
    'Sanatorial': {"sectores": ['Salud y farmaceutico'], "patrones": [r"sanatorial"]},
    'Satelital': {"sectores": ['Tecnologia y telecomunicaciones'], "patrones": [r"satelital"]},
    'Seguridad informática': {"sectores": ['Seguridad privada', 'Tecnologia y telecomunicaciones'], "patrones": [r"seguridad informatica"]},
    'Seguridad y vigilancia': {"sectores": ['Seguridad privada'], "patrones": [r"seguridad y vigilancia"]},
    'Seguros': {"sectores": ['Servicios financieros y seguros'], "patrones": [r"seguros"]},
    'Semillas': {"sectores": ['Agroindustria, granos y semillas'], "patrones": [r"semillas"]},
    'Servicios de consultoria': {"sectores": ['Consultoria economica'], "patrones": [r"servicios de consultoria"]},
    'Servicios petroleros': {"sectores": ['Hidrocarburos (petroleo y gas)'], "patrones": [r"servicios petroleros"]},
    'Servicios profesionales': {"sectores": ['Consultoria economica'], "patrones": [r"servicios profesionales"]},
    'Servicios sanatoriales': {"sectores": ['Salud y farmaceutico'], "patrones": [r"servicios sanatoriales"]},
    'Servicios tecnológicos': {"sectores": ['Tecnologia y telecomunicaciones'], "patrones": [r"servicios tecnologicos"]},
    'Señales de TV': {"sectores": ['Audiovisual, medios y entretenimiento'], "patrones": [r"señales de tv"]},
    'Shampoos': {"sectores": ['Quimica, cosmetica y limpieza'], "patrones": [r"shampoos"]},
    'Shopping': {"sectores": ['Inmobiliario, retail y shoppings'], "patrones": [r"shopping"]},
    'Sistema eléctrico': {"sectores": ['Energia electrica'], "patrones": [r"sistema electrico"]},
    'Sistemas de propulsión': {"sectores": ['Automotriz y autopartes'], "patrones": [r"sistemas de propulsion"]},
    'Snacks': {"sectores": ['Alimentos y bebidas'], "patrones": [r"snacks"]},
    'Software': {"sectores": ['Tecnologia y telecomunicaciones'], "patrones": [r"\bsoftware\b"]},
    'Soja': {"sectores": ['Agroindustria, granos y semillas'], "patrones": [r"\bsoja\b"]},
    'Solar': {"sectores": ['Energia electrica'], "patrones": [r"solar"]},
    'Solventes': {"sectores": ['Quimica, cosmetica y limpieza'], "patrones": [r"solventes"]},
    'Somatropina': {"sectores": ['Salud y farmaceutico'], "patrones": [r"somatropina"]},
    'Streaming': {"sectores": ['Audiovisual, medios y entretenimiento'], "patrones": [r"streaming"]},
    'Sueros de leche': {"sectores": ['Alimentos y bebidas'], "patrones": [r"suero(s)? de leche"]},
    'Suministro de electricidad': {"sectores": ['Energia electrica'], "patrones": [r"suministro de electricidad"]},
    'Supermercados': {"sectores": ['Inmobiliario, retail y shoppings'], "patrones": [r"supermercados"]},
    'Surfactante': {"sectores": ['Quimica, cosmetica y limpieza'], "patrones": [r"surfactante"]},
    'Sustancias químicas': {"sectores": ['Quimica, cosmetica y limpieza'], "patrones": [r"sustancias quimicas"]},
    'Tableros de fibra': {"sectores": ['Madera y muebles'], "patrones": [r"tableros de fibra"]},
    'Tambo': {"sectores": ['Alimentos y bebidas'], "patrones": [r"tambo"]},
    'Tanques de combustible': {"sectores": ['Automotriz y autopartes'], "patrones": [r"tanques.*combustible"]},
    'Tarjetas de crédito': {"sectores": ['Servicios financieros y seguros'], "patrones": [r"tarjetas de credito"]},
    'Tecnológicos': {"sectores": ['Tecnologia y telecomunicaciones'], "patrones": [r"tecnologicos"]},
    'Tejidos': {"sectores": ['Textiles'], "patrones": [r"tejidos"]},
    'Telas': {"sectores": ['Textiles'], "patrones": [r"telas"]},
    'Telecomunicaciones': {"sectores": ['Audiovisual, medios y entretenimiento', 'Tecnologia y telecomunicaciones'], "patrones": [r"telecomunicaciones"]},
    'Telefonía': {"sectores": ['Tecnologia y telecomunicaciones'], "patrones": [r"telefonia"]},
    'Telefonía celular': {"sectores": ['Tecnologia y telecomunicaciones'], "patrones": [r"telefonia celular"]},
    'Telefonía fija': {"sectores": ['Tecnologia y telecomunicaciones'], "patrones": [r"telefonia fija"]},
    'Telefonía móvil': {"sectores": ['Tecnologia y telecomunicaciones'], "patrones": [r"telefonia movil"]},
    'Telefonía por internet': {"sectores": ['Tecnologia y telecomunicaciones'], "patrones": [r"telefonia por internet"]},
    'Televisión por cable': {"sectores": ['Audiovisual, medios y entretenimiento', 'Tecnologia y telecomunicaciones'], "patrones": [r"television por cable"]},
    'Textil': {"sectores": ['Indumentaria y calzado'], "patrones": [r"textil\b"]},
    'Tierras': {"sectores": ['Agroindustria, granos y semillas'], "patrones": [r"tierras"]},
    'Tintas digitales': {"sectores": ['Construccion y materiales'], "patrones": [r"tintas digitales"]},
    'Tissue': {"sectores": ['Papel, carton y envases'], "patrones": [r"\btissue\b"]},
    'Tocador': {"sectores": ['Quimica, cosmetica y limpieza'], "patrones": [r"tocador"]},
    'Trabajo cooperativo': {"sectores": ['Consultoria economica'], "patrones": [r"trabajo cooperativo"]},
    'Transformadores': {"sectores": ['Energia electrica'], "patrones": [r"transformadores"]},
    'Transporte aereo': {"sectores": ['Logistica y transporte'], "patrones": [r"transporte aereo"]},
    'Transporte de carga': {"sectores": ['Logistica y transporte'], "patrones": [r"transporte de carga"]},
    'Transporte de caudales': {"sectores": ['Logistica y transporte'], "patrones": [r"transporte de caudales"]},
    'Transporte de electricidad': {"sectores": ['Energia electrica'], "patrones": [r"transporte de electricidad"]},
    'Transporte de energía eléctrica': {"sectores": ['Energia electrica'], "patrones": [r"transporte de energia electrica"]},
    'Transporte de mercaderías': {"sectores": ['Logistica y transporte'], "patrones": [r"transporte de mercaderias"]},
    'Transporte de pasajeros': {"sectores": ['Logistica y transporte'], "patrones": [r"transporte de pasajeros"]},
    'Transporte de residuos': {"sectores": ['Logistica y transporte'], "patrones": [r"transporte de residuos"]},
    'Transporte de valores': {"sectores": ['Logistica y transporte'], "patrones": [r"transporte de valores"]},
    'Transporte marítimo': {"sectores": ['Logistica y transporte'], "patrones": [r"transporte maritimo"]},
    'Transporte pasajeros': {"sectores": ['Logistica y transporte'], "patrones": [r"transporte.*pasajeros"]},
    'Tratamiento de aguas': {"sectores": ['Construccion y materiales'], "patrones": [r"tratamiento de aguas?"]},
    'Trigo': {"sectores": ['Agroindustria, granos y semillas'], "patrones": [r"\btrigo\b"]},
    'Uso agricola': {"sectores": ['Agroindustria, granos y semillas'], "patrones": [r"uso agricola"]},
    'Vehículos': {"sectores": ['Automotriz y autopartes'], "patrones": [r"vehiculos"]},
    'Vehículos automotores': {"sectores": ['Automotriz y autopartes'], "patrones": [r"vehiculos automotores"]},
    'Vehículos comerciales': {"sectores": ['Automotriz y autopartes'], "patrones": [r"vehiculos comerciales"]},
    'Vehículos de pasajeros': {"sectores": ['Automotriz y autopartes'], "patrones": [r"vehiculos de pasajeros"]},
    'Venta al por menor': {"sectores": ['Inmobiliario, retail y shoppings'], "patrones": [r"venta al por menor"]},
    'Venta online': {"sectores": ['Inmobiliario, retail y shoppings'], "patrones": [r"venta online"]},
    'Vestimenta': {"sectores": ['Textiles'], "patrones": [r"vestimenta"]},
    'Vidrio plano': {"sectores": ['Construccion y materiales'], "patrones": [r"vidrio plano"]},
    'Vino': {"sectores": ['Alimentos y bebidas'], "patrones": [r"vino"]},
    'Wollastonita': {"sectores": ['Construccion y materiales'], "patrones": [r"wollastonita"]},
    'Yacimiento': {"sectores": ['Hidrocarburos (petroleo y gas)'], "patrones": [r"yacimiento"]},
    'Yesera': {"sectores": ['Construccion y materiales'], "patrones": [r"yesera"]},
    'Yeso': {"sectores": ['Construccion y materiales'], "patrones": [r"yeso"]},
    'Yeso en polvo': {"sectores": ['Construccion y materiales'], "patrones": [r"yeso en polvo"]},
    'Yeso para la construcción': {"sectores": ['Construccion y materiales'], "patrones": [r"yeso para la construccion"]},
    'Yogur': {"sectores": ['Alimentos y bebidas'], "patrones": [r"yogur"]},
    'Ácidos': {"sectores": ['Quimica, cosmetica y limpieza'], "patrones": [r"acidos"]},
}


def productos_por_sector(registros: list[dict]) -> dict[str, list[str]]:
    """sector -> [productos, ...] para el desplegable de busqueda avanzada.

    QUE productos hay sale del Excel (columna `productos`): solo se listan los
    que estan cargados en algun expediente, asi ninguna opcion del desplegable
    devuelve cero resultados.

    BAJO QUE mercado se agrupa cada uno lo dice el campo "sectores" del
    catalogo PRODUCTOS: 'Aceros' cuelga de "Construccion y materiales" aunque
    lo mencione un expediente de agroindustria. Agrupar por los sectores del
    expediente no sirve: los expedientes suelen estar en varios mercados a la
    vez y cada producto terminaba contagiado a todos.

    Un producto escrito a mano en el Excel que no este en el catalogo se
    agrupa, como respaldo, bajo los sectores de su expediente; para fijarle un
    mercado propio hay que darlo de alta en PRODUCTOS."""
    cat = {norm(nombre): info["sectores"] for nombre, info in PRODUCTOS.items()}
    out: dict[str, set[str]] = {}
    for r in registros:
        for prod in r.get("productos") or []:
            sectores = cat.get(norm(prod)) or r.get("sectores") or []
            for sector in sectores:
                out.setdefault(sector, set()).add(prod)
    return {sec: sorted(prods, key=norm) for sec, prods in sorted(out.items())}


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
        tags.append("Exportacion")
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
        "productos": norm(C_PRODUCTOS),
        "prod_sector": norm(C_PROD_SECTOR),
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

        # productos y sectores salen del Excel (columnas de extraer_productos.py,
        # editables a mano). Si la fila todavia no las tiene, se calculan.
        productos = parse_lista(row.get(col["productos"]))
        sectores = parse_lista(row.get(col["prod_sector"]))
        if not sectores:
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
            " ".join(sectores), " ".join(productos), " ".join(relaciones),
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
            "productos": productos,
            "sinonimos": sinonimos,
            "search": blob,
        })
    return registros


def build_dataframe() -> pd.DataFrame:
    recs = build_records()
    df = pd.DataFrame(recs)
    for c in ["segmentos", "relaciones", "cadena", "geografia", "sectores", "productos", "sinonimos"]:
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
