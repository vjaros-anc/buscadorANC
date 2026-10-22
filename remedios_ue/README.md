# Biblioteca de remedios UE

Precedentes de la Comisión Europea para la ANC: concentraciones que la Comisión
autorizó **con condiciones**, qué problema de competencia detectó en cada una y
qué remedio aceptó.

Esta carpeta está separada del buscador de la CNDC (raíz del repo) y no lo toca.

| Etapa | Qué produce | Estado |
|---|---|---|
| 1. Universo de casos | `casos.csv`, `revisiones_remedios.csv`, `conciliacion.md` | hecha y validada |
| 2. Inventario documental | `documentos.csv` | hecha, **a validar** |
| 3. Descarga y extracción | PDF y texto (scripts propios) | pendiente |
| 4–5. Fichas problema–remedio | fichas por caso | pendiente |

---

## Etapa 1 — Universo de casos

### Criterio de inclusión

Un caso entra si cumple **todo** esto:

- **Autoridad**: Comisión Europea, Reglamento (CE) 139/2004.
- **Decisión**:
  - **fase I**: art. 6(1)(b) en relación con el 6(2) (compatible con compromisos);
  - **fase II**: art. 8(2) con condiciones y obligaciones.
- **Fecha de adopción** de esa decisión entre **22/10/2021 y 22/10/2026**, ambas inclusive.
- Una fila por número de caso (`M.xxxxx`).

### Casos límite

| Situación | Tratamiento |
|---|---|
| Compromisos dispensados o modificados después | Entra; se anota en `eventos_posteriores` |
| Operación abandonada, decisión recurrida o anulada | Entra, con la anotación |
| Compromisos ofrecidos pero la notificación se retiró, se prohibió o se autorizó sin condiciones | Queda afuera; se lista en `conciliacion.md` |
| Compromisos bajo el Reglamento de Subvenciones Extranjeras (FSR) | Queda afuera (otro régimen) |
| Autoridades nacionales | Fuera de alcance |

### Fuentes

| | Fuente | Para qué |
|---|---|---|
| **A** | Datos abiertos de DG COMP: [`case-data-M.json`](https://data.europa.eu/data/datasets/cc7e224e-6569-40f0-8037-d3389aa0fae7) (data.europa.eu, se actualiza a diario) | Fuente principal: tipo y fecha de cada decisión |
| **C** | API pública de [Presscorner](https://ec.europa.eu/commission/presscorner/) | Lista independiente: comunicados cuyo título dice "subject to conditions" o similar |
| | [Estadísticas oficiales de concentraciones](https://competition-policy.ec.europa.eu/mergers/statistics_en) (PDF) | Totales de control por año |

**Fuente B no usada.** El buscador de casos (competition-cases.ec.europa.eu) consulta
la misma base que el JSON, así que no sería una lista independiente. Además, su API
(`webgate.ec.europa.eu`) no es accesible desde el entorno donde se armó esto.

### Cómo reproducir

```bash
python remedios_ue/inventario_casos.py                 # baja el JSON y los comunicados, actualiza casos.csv
python remedios_ue/inventario_casos.py --sin-descarga  # reusa remedios_ue/datos_crudos/
```

Solo usa la biblioteca estándar de Python. Lo que baja va a `datos_crudos/`, que no
se versiona (el JSON pesa ~42 MB); la fecha y el sha256 de la copia quedan en
`datos_crudos/case-data-M.meta.json`.

El script **solo completa celdas vacías**, igual que `mergear_firmadas.py`: lo que se
carga a mano en `casos.csv` no se pisa. Si un dato automático deja de coincidir con
el cargado, lo informa como DISCREPANCIA. Correrlo dos veces seguidas deja el archivo
idéntico.

Copia usada para la versión actual de `casos.csv`: descargada el 22/10/2026,
sha256 `d135029e…57b459`.

### Columnas de `casos.csv`

CSV en UTF-8 con BOM (Excel lo abre con los acentos bien). Las columnas marcadas
"manual" no las calcula el script.

| Columna | Contenido | Origen |
|---|---|---|
| `caso_id` | Número de caso, p. ej. `M.10646` | JSON |
| `titulo` | Título oficial | JSON |
| `adquirentes` / `objetivos` | Partes, separadas por `;` | Título partido en `/` (convención de la Comisión: adquirente primero). Corregido a mano en empresas en participación y control conjunto |
| `fecha_notificacion` | AAAA-MM-DD | JSON |
| `fecha_decision` | Adopción de la decisión condicionada | JSON |
| `fase` | `I` / `II` | JSON |
| `base_legal` | `6(1)(b)+6(2)` / `8(2)` | JSON |
| `sector_nace` | Códigos NACE asignados por la Comisión | JSON |
| `tipo_remedio_preliminar` | `estructural` / `conductual` / `mixto` | **Manual**, según el comunicado. Se confirma en la etapa 4 |
| `resena_remedio` | Una línea sobre el remedio, orientativa | "Reseña orientativa del remedio" del inventario ANC en Excel (`importar_inventario_xlsx.py`) |
| `eventos_posteriores` | Aprobación de comprador, implementación o revisión de remedios, modificaciones, multas, causas judiciales; con fecha | JSON |
| `url_caso` | Ficha oficial del caso | Armada con el número |
| `url_comunicado` | Comunicado de la autorización | Presscorner |
| `fuentes_identificacion` | En qué listas apareció: `A;C` o `A` | Cruce |
| `notas` | Antecedentes del procedimiento (remisiones, notificaciones retiradas) + notas manuales | JSON + manual |

### Anexo: `revisiones_remedios.csv`

Son los casos autorizados con condiciones **antes** del 22/10/2021 que, dentro del
período, tuvieron una decisión que revisó, modificó o aplicó sus remedios: cláusula de
revisión, implementación de remedios o modificación de compromisos. No forman parte de
los 47, pero muestran cómo se flexibilizan o terminan los remedios con el tiempo. Hoy
son 12 casos.

| Columna | Contenido |
|---|---|
| `caso_id`, `titulo` | Del JSON |
| `fecha_autorizacion_original`, `base_legal_original` | La última autorización condicionada del caso |
| `decisiones_en_periodo` | Tipo y fecha de cada decisión de remedios del período |
| `url_caso` | Ficha oficial |
| `notas` | Manual |

### Criterio para `tipo_remedio_preliminar`

- **estructural**: desinversión de un negocio, de plantas, marcas o participaciones. Los
  servicios transitorios al comprador no cambian la clasificación.
- **conductual**: acceso, licencias, interoperabilidad, suministro u otras obligaciones
  de comportamiento, sin desinversión.
- **mixto**: las dos cosas. Las cesiones de slots o de derechos de tráfico aéreo combinadas
  con acuerdos con rivales se tratan como mixtas.

### Qué trae el JSON (útil para las etapas 2 y 3)

- Es un diccionario por número de caso: `{metadata, caseAttachments, decisions}`.
- `decisions[].metadata.decisionTypes` trae `{code, label}`. Cada tipo aparece con **dos
  códigos** (p. ej. `DecisionType440` y `DecisionType20212` para fase I con
  compromisos), por eso el filtro es por etiqueta.
- `decisions[].decisionAttachments[]` trae el PDF de la decisión ("Decision - web
  publication") con su idioma.
- `caseAttachments[]` trae el aviso de notificación previa ("Description of the
  concentration"), el dictamen del Comité Consultivo, el informe del Consejero Auditor y
  "Other document for publication" (p. ej. datos del trustee).
- `caseTimelineEvents` registra cuándo se presentaron compromisos ("Commitments
  submitted"). Con eso se arma la lista de excluidos de `conciliacion.md`.

**Advertencias:**

- Aunque el dataset dice que los enlaces son a documentos en inglés, algunas decisiones
  están **solo en el idioma auténtico**. Por ejemplo, M.11485 está en francés.
- La fecha de los comunicados dentro del JSON no siempre es correcta: IP/23/2705 figura
  14/08/2023 pero es del 15/05/2023. Por eso la fecha y la referencia del comunicado se
  toman de Presscorner.
- `caseCompanies` viene vacío; por eso las partes salen del título.

---

## Etapa 2 — Inventario documental

`documentos.csv` tiene una fila por documento de cada caso de `casos.csv` y del anexo de
revisiones, con su enlace verificado y su estado. Es la entrada para el descargador de la
etapa 3.

### Cómo reproducir

```bash
python remedios_ue/inventario_casos.py                         # etapa 1 (también guarda los comunicados)
python remedios_ue/relevar_documentos.py                       # arma documentos.csv, baja las decisiones y verifica enlaces
python remedios_ue/importar_inventario_xlsx.py <inventario.xlsx>  # suma lo del inventario ANC en Excel
```

Dependencias: `pip install pymupdf openpyxl`. Las dos primeras opciones de
`relevar_documentos.py` son `--sin-descarga` (no baja PDF) y `--sin-verificar` (no consulta
la red). Lo que baja y verifica queda en `datos_crudos/` (no se versiona), así que volver a
correrlo no repite descargas. Correr los tres scripts dos veces seguidas deja los CSV
idénticos.

El Excel es un insumo interno y no se versiona.

### Tipos de documento

| `tipo_doc` | Prioridad | Qué es | De dónde sale |
|---|---|---|---|
| `DEC` | núcleo | Decisión condicionada, versión pública | JSON de DG COMP |
| `COMP` | núcleo | Compromisos. Casi siempre son un **anexo dentro del PDF de la `DEC`**: la fila apunta al mismo PDF y `paginas_compromisos` dice dónde está. A veces hay además una versión no confidencial aparte | Ubicados con PyMuPDF; algunos separados vienen del JSON o del Excel |
| `CP` | complementario | Comunicado de la autorización (y otros relevantes) | Presscorner |
| `CP_APERTURA` | complementario | Comunicado de apertura de fase II | Presscorner, con la referencia del JSON |
| `RES_DO` | complementario | Resumen o aviso en el Diario Oficial | EUR-Lex: URL armada con la referencia del JSON, más los enlaces precisos del Excel |
| `POST` | complementario | Decisiones posteriores: aprobación de comprador, implementación o revisión de remedios | JSON |
| `NOT_PREVIA` | contexto | Aviso de notificación previa | JSON |
| `DICT` | contexto | Dictamen del Comité Consultivo e informe del Consejero Auditor (solo fase II) | JSON |
| `MB` | contexto | Artículo del Competition Merger Brief sobre el caso | Excel + revisión manual de los números |
| `SENT` | contexto | Sentencias, autos y recursos ante el Tribunal General o el TJUE | Excel + búsqueda web |
| `OTRO` | contexto | Datos del trustee y otros documentos publicados | JSON |

### Columnas de `documentos.csv`

| Columna | Contenido |
|---|---|
| `doc_id` | `<caso>_<tipo>_<nn>` para las filas automáticas; `<caso>_<tipo>_M<nn>` para las manuales |
| `caso_id`, `universo` | Caso y universo: `principal` (los 47) o `revisiones` (anexo) |
| `tipo_doc`, `prioridad` | Según la tabla anterior |
| `titulo`, `fecha_doc`, `idioma`, `otros_idiomas`, `version` | Del JSON, de Presscorner o del Excel |
| `url`, `fuente`, `ref` | Enlace, de dónde salió y referencia (comunicado o Diario Oficial) |
| `estado` | `localizado_verificado`, `localizado_no_verificado`, `no_publicado_aun`, `no_publico`, `no_encontrado`, `no_aplica` |
| `http_status`, `tipo_contenido`, `tamano_bytes`, `verificado_el` | Resultado de la verificación |
| `archivo_local` | **Vacía**: la completa el descargador de la etapa 3 |
| `sha256`, `paginas` | De las `DEC` (y `COMP` separados) ya bajadas, para que el descargador compruebe lo que baja |
| `paginas_compromisos` | Rango de páginas del PDF donde están los compromisos |
| `notas` | Aclaraciones; en las filas del Excel, el tipo original y su nota |

### Reglas

- **Filas manuales**: las de `fuente` que empieza con "manual" o "Inventario ANC", y todas las
  `MB` y `SENT`. `relevar_documentos.py` no las toca. El resto se recalcula, completando
  solo celdas vacías; si un dato cambia en la fuente, se informa como DISCREPANCIA.
- **Anexo de compromisos**: se ubica buscando su título ("COMMITMENTS TO THE EUROPEAN
  COMMISSION", "ENGAGEMENTS À L'ÉGARD DE LA COMMISSION" y equivalentes en otros idiomas).
  En las decisiones viejas sin anexo (2004–2009, solo en el anexo de revisiones), las
  páginas se cargaron a mano y el script las respeta.
- **Copias**: el importador del Excel no suma copias de documentos que ya figuran, como la
  versión EUR-Lex de una decisión, aviso o dictamen que el JSON ya trae, o el mismo
  comunicado en otro idioma o en el sitio de una representación de la Comisión.
- **Idioma**: el del JSON. Si hay varios, se prefiere el inglés y el resto va a `otros_idiomas`.

### Cobertura al 22/10/2026

| | Resultado |
|---|---|
| Casos con decisión verificada | **44 de 47**. Faltan M.12237, M.12201 y M.12330 (2026): la Comisión todavía no publicó la versión pública |
| Casos con compromisos ubicados, con páginas | **44 de 47** (los mismos 3 faltan) |
| Documentos | 524 filas: 482 del universo principal y 42 del anexo de revisiones |
| Merger Briefs | 21 casos con artículo (16 del Excel y 5 hallados revisando los números completos) |
| Recursos judiciales | 8 filas en 4 casos: Vivendi/Lagardère, Broadcom/VMware, Lufthansa/ITA, Brasserie Nationale/Heintz |
| Tamaño a descargar | ~186 MB las `DEC` y `COMP` separados; ~227 MB con todo lo que es PDF |

Control manual: en 3 decisiones al azar (Veolia/Suez en francés, Advent/GfK y UniCredit/BPM)
los compromisos empiezan en la página registrada. Donde el Excel informa la página de inicio
de los compromisos, coincide con la ubicada (6 de 6).

### Limitaciones

- **EUR-Lex** responde con un desafío anti-bots: los `RES_DO` y los documentos judiciales
  quedan `localizado_no_verificado`. En 7 casos no hay referencia al Diario Oficial ni en
  el JSON ni en el Excel; en 2026 es esperable porque se publica después.
- **curia.europa.eu** no es accesible desde el entorno donde se armó esto; los números de
  causa salen de EUR-Lex, del Excel o de prensa especializada (anotado en cada fila).
- **M.5364 Iberia/Vueling** (anexo): el PDF que el JSON registra como decisión es la
  traducción al inglés de los compromisos.
- Las decisiones de apertura de fase II (art. 6(1)(c)) no tienen PDF en el JSON; la
  apertura queda documentada con su comunicado.

### Para el descargador de la etapa 3

Recorrer `documentos.csv` filtrando por `estado` (`localizado_verificado`, y
`localizado_no_verificado` si se quiere intentar EUR-Lex) y por `prioridad` o `tipo_doc`.
Las filas `COMP` con `version = anexo de la decisión` apuntan al mismo PDF que su `DEC`: no
hace falta bajarlo dos veces, alcanza con usar `paginas_compromisos`. Completar
`archivo_local` y comparar con `sha256`.
