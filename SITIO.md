# Sitio de herramientas ANC — guía de esta rama

Esta rama (`claude/dreamy-cray-mxaf3v`) **agrega archivos nuevos** y toca solo **dos archivos existentes, únicamente para
agregar líneas**: `index.html` y `generar_pagina.py` reciben la barra común del sitio (3 líneas cada uno: el `<link>` a
`assets/anc.css`, el `<div id="anc-nav">` y el `<script src="assets/nav.js">`). Es la única excepción a «no tocar el buscador»
y se pidió expresamente. No cambia `comparar_index.py`, `estado.py`, `PROTOCOLO.md`, `.gitignore`, `firm.xlsx`, `pdf/**` ni
`pdf/lectura_opi/**`, así que el circuito mensual del buscador sigue exactamente igual (los 2.069 elementos del buscador
conservan estilos, posición y tamaño; solo bajan el alto de la barra). Se puede adoptar entera, por carpeta, o descartar.

Se comprueba con: `python -B verificar_sitio.py --aditivo` (falla si la rama modifica o borra algo que ya estaba en `main`; la
única excepción admitida es sumar líneas a `index.html` y `generar_pagina.py`, nunca perder alguna).

## Qué hay

| URL | Qué es | Cómo se genera |
|---|---|---|
| `/` | el buscador de siempre, **con la barra común** | `generar_pagina.py` (la barra son 3 líneas de su plantilla) |
| `/herramientas/` | mapa de herramientas, agrupadas | HTML estático (lee la fecha de `data/conc.json`) |
| `/opis/` | buscador de OPIs (96 dictámenes) | `python -B integrar_opis.py` |
| `/conc/` | estadísticas de resoluciones firmadas, con filtros por año, tipo y sector y CSV | `python -B generar_tablero.py` |
| `/demo-interno/` | portada del área interna (demo) | HTML estático |
| `/demo-interno/noticias/` | prototipo del Monitor M&A con **datos de ejemplo** | HTML + `demo-interno/data/monitor.sample.json` |
| `/demo-interno/seguimiento/` | concentraciones **en trámite** del Excel `Res_firmadas.xlsm` (datos reales en esta rama; si no hay `seguimiento.json`, muestra ejemplos) | HTML + `demo-interno/data/seguimiento.json`, que escribe `python -B generar_seguimiento.py` |
| `/mercados/ /participaciones/ /redes/ /informes/` | reservadas (un `README.md` cada una) | — |

Piezas de apoyo: `assets/` (`anc.css`, `nav.js`, `charts.js`, `csv.js`), `data/conc.json`, `_headers`, `robots.txt`, `404.html`,
`verificar_sitio.py`, `build_site.py`, `tests/test_sitio.py`.

**La barra.** Está en todas las páginas, también en el buscador (`/`): Buscador · OPIs · Estadísticas · Mercados (pronto) · Área
interna · Mapa; marca la sección en la que estás y «Herramientas ANC» lleva al mapa. En pantallas angostas es una sola fila que se
desliza (se reserva su alto para que la página no salte al dibujarla). No es fija: el buscador tiene encabezados de tabla pegajosos que
quedarían tapados. Los destinos y el interruptor `INTERNO` están al principio de `assets/nav.js`.

## Cómo probar

**Local** (en la raíz del repo; en Windows también sirve `py -m http.server 8000`):

```
python -B -m http.server 8000
```

Abrí `http://localhost:8000/` (el buscador, ahora con la barra), `/herramientas/`, `/opis/`, `/conc/`, `/demo-interno/`,
`/demo-interno/noticias/` y `/demo-interno/seguimiento/`.

**En Cloudflare:** al subir la rama, Pages → `buscadoranc` → Deployments muestra un *preview* de la rama (si los previews de
ramas están activos). Qué mirar:

1. `/` funciona igual que en producción (buscar «leche» da 11 resultados de 1.045) y ahora tiene la barra arriba; un PDF
   (`/pdf/CONC-1003.pdf`) sigue igual.
2. Cada página carga sin errores y la barra lleva a las demás y de vuelta al buscador, también desde el celular.
3. `/opis/`: buscar "participación minoritaria" da 5 resultados; filtros por ley, criterio y tipo funcionan.
4. `/conc/`: elegir año, tipo o sector recalcula todo; **Descargar CSV (N)** baja la selección; la dirección guarda los filtros
   (probá `/conc/#a=2024&t=PROSUM`); pasar el mouse por las columnas y barras muestra el detalle; **Ver como tabla** cambia el gráfico
   por su tabla. Conviene revisar «Cómo se agrupan las decisiones» (al final): los 39 textos originales y el grupo de cada uno.
5. `/demo-interno/noticias/` (datos de ejemplo) y `/demo-interno/seguimiento/` (datos reales del Excel): filtros por abogado, economista,
   estado y procedimiento, **Descargar CSV** (se abre bien en Excel) y los carteles de uso interno. Sin `seguimiento.json` la página cae al
   ejemplo con su cartel.
6. Una ruta inexistente (`/cualquier/cosa`) debe mostrar `404.html` **con código 404**. Hoy responde 200 con el buscador:
   Pages trata el sitio como una SPA mientras no exista `404.html`. Esto cambia el comportamiento global (en un commit aparte).

## Cómo adoptar o descartar

| Querés… | Hacé |
|---|---|
| Todo | mergear la rama a `main` |
| Todo menos el cambio de 404 | antes de mergear, borrar `404.html` (está en un commit aparte) |
| Sin la barra en el buscador | borrar las 3 líneas (`<link>`, `<div id="anc-nav">`, `<script src="assets/nav.js">`) en la plantilla de `generar_pagina.py` y en `index.html`: vuelve a ser idéntico a `main`. Después sacar `index.html` de `PAGINAS` y quitar `test_buscador_y_plantilla_llevan_la_barra` |
| Sin las demos del área interna | borrar `demo-interno/` y `robots.txt` y la regla de `_headers` para `/demo-interno/*`; poner `var INTERNO = false;` en `assets/nav.js` (la barra y el mapa dejan de mencionarla) |
| Sin OPIs | borrar `opis/` y `integrar_opis.py` (el original no se tocó) |
| Sin estadísticas | borrar `conc/`, `data/` y `generar_tablero.py` |
| Nada | no mergear; borrar la rama |

Si borrás una carpeta, sacala también de `PAGINAS` en `verificar_sitio.py` y del arreglo `ITEMS` de `assets/nav.js`.

**Si no usás `build_site.py`**, Pages publica la raíz tal cual y lo que mergees a `main` queda en producción, `demo-interno/` incluida
(con `noindex`, pero trae datos reales del seguimiento y `Res_firmadas.xlsm`, y no deben estar en producción): borrala, y borrá el `.xlsm`, antes de mergear, y poné `INTERNO = false`.
Con `build_site.py` eso se resuelve solo (ver abajo).

## Cómo regenerar

```
python -B generar_tablero.py     # lee firm.xlsx -> conc/index.html y data/conc.json
python -B integrar_opis.py       # copia pdf/lectura_opi/buscador_opis.html a opis/index.html (+barra)
python -B generar_seguimiento.py # lee Res_firmadas.xlsm (solo lectura) -> demo-interno/data/seguimiento.json (solo en la rama del área interna)
python -B verificar_sitio.py     # compuerta: links con mayúsculas exactas, tamaños, lista negra, ejemplo vs real, tablero al día
python -B -m unittest discover -s tests -v   # pruebas de coherencia del sitio (23 pruebas, unos 10 s)
```

Usá siempre `-B`: hay dos `.pyc` versionados que si no Python reescribiría y aparecerían como modificados.

Para el circuito mensual, después del paso 8 (`generar_pagina.py`, que ahora ya escribe la barra en `index.html`) se corre
`generar_tablero.py` (y, si regeneraste los OPIs, `integrar_opis.py`); el resto no cambia. El tablero lee el mismo `firm.xlsx`. Si te
olvidás, `verificar_sitio.py` avisa («data/conc.json no corresponde al index.html publicado») y la prueba
`test_el_tablero_versionado_es_el_que_sale_de_firm_xlsx` falla.

Las pruebas (`tests/test_sitio.py`) usan solo la biblioteca estándar; la última (regenerar el tablero) necesita pandas y se saltea si
no está. Cada una dice qué script volver a correr.

## `build_site.py` y la lista blanca (opcional)

Hoy Pages publica **la raíz entera del repo**: `firm.xlsx`, los `.py`, `PROTOCOLO.md`, `varios/`, `viejos/`… quedan servidos por
URL. `build_site.py` arma `dist/` con una lista blanca y deja de publicar eso, sin mover nada y sin tocar el flujo del buscador.

```
python -B build_site.py --reporte     # qué se publicaría y qué dejaría de publicarse (no arma nada)
python -B build_site.py               # arma dist/
```

Resultado hoy: en un preview se publican 1.090 archivos (855 MB: `index.html`, los PDF de primer nivel, las páginas nuevas, la demo y
dos URLs heredadas) y dejan de servirse 239 (scripts, Excel, `varios/`, `viejos/`, escaneados, CSV, `tests/`…). Las URLs heredadas
que se mantienen para no cortar nada son `productos buscador/index.html` y `pdf/lectura_opi/buscador_opis.html` (`--sin-legado` las saca).
`demo-interno/` no entra cuando la rama de Cloudflare es `main` (variable `CF_PAGES_BRANCH`): en esa salida (1.085 archivos) `assets/nav.js`
se publica con `INTERNO = false`, así la barra y el mapa tampoco mencionan un área interna que no está. La salida de `main` y la de un
preview se verificaron con el navegador (barra sin «Área interna», sección del mapa oculta, todos los enlaces responden 200,
`/demo-interno/…` da 404).

**Probarlo sin tocar el proyecto real:** crear un segundo proyecto de Pages conectado a este repo, con rama de producción
`claude/dreamy-cray-mxaf3v`, *Build command* `python3 build_site.py` y *Build output directory* `dist`. El proyecto `buscadoranc`
no cambia. Si te convence, esos dos valores son los únicos que habría que cambiar en el proyecto real.

Detalles: usa solo la biblioteca estándar (Python 3.7+); antes de armar corre `verificar_sitio.py` y aborta si falla (en Cloudflare, un
build fallido deja el deploy anterior). Como `dist/` no está en `.gitignore` y el protocolo usa `git add -A`, el script lo agrega a
`.git/info/exclude` (local, no se versiona) para que no se suba por accidente.

## Contratos de datos

Cada herramienta lee un JSON versionado (`schema_version`) y no depende de la fuente.

- `data/conc.json` (v1): agregados del tablero (año × tipo, decisiones, sectores, relaciones, tiempos, cobertura) **más el detalle por
  expediente** (`detalle`: carpeta, fecha de firma, tipo, decisión, grupo, sectores, relaciones, días ingreso→firma y qué campos están
  cargados) y los catálogos para armar los filtros. Solo trae lo que el buscador ya publica; no hay nombres de empresas. Lo escribe
  `generar_tablero.py`, un expediente por línea (diffs legibles). `corpus.huella` identifica el corpus del buscador del que sale.
  La página `/conc/` recalcula todo en el navegador a partir del detalle; los agregados que escribe Python son la referencia con la
  que se comparan (`tests/test_sitio.py` y una prueba en el navegador con 10 combinaciones de filtros dieron lo mismo).
- Monitor y seguimiento: `demo-interno/SCHEMA.md` define `operaciones` v1 y `seguimiento` v2 (campos, valores, CSV).
  `demo-interno/monitor_merge.py` junta lo exportado con `ArtifactData` en `monitor.json` + `operaciones.csv`; `generar_seguimiento.py`
  escribe `seguimiento.json`. **El `monitor.json` real sigue sin poder estar en este repo**: `verificar_sitio.py` falla si aparece uno con
  `origen` distinto de `"ejemplo"`. El **seguimiento real** (`origen: "interno"`) solo puede estar en la rama del área interna (ver abajo):
  en `main` es error.
- Clave común de expediente: `tipo-número` normalizado (`nm.parse_carpeta`). Ojo: `(tipo, número)` no es único (OPI-232, INC-1663);
  `(tipo, número, resolución)` sí.

## Área interna: Cloudflare con Access, desde esta rama

**Decisión (9/10/2026).** El área interna se publica en **Cloudflare Pages detrás de Cloudflare Access**, desde una rama distinta de `main`
(esta, `claude/dreamy-cray-mxaf3v`); `main` sigue siendo el sitio público (el buscador). Se aceptó que el repositorio de GitHub siga siendo
**público**: Access protege la dirección de Cloudflare, **no** el repositorio, y la rama (con `Res_firmadas.xlsm` y `seguimiento.json`) se
puede leer en GitHub. Quien quiera cerrar eso más adelante tiene el camino de siempre: repo privado aparte y segundo proyecto de Pages.

**Qué hay en la rama y qué lo protege**

| Pieza | Qué hace |
|---|---|
| `Res_firmadas.xlsm` (subido el 9/10) | fuente del seguimiento; `generar_seguimiento.py` lo abre en solo lectura |
| `demo-interno/data/seguimiento.json` | lo que lee la página; trae carátulas resumidas y apellidos del equipo |
| `build_site.py` | publica una lista blanca: el `.xlsm` **no** sale en `dist/`; el JSON sí |
| `verificar_sitio.py` | corre antes de armar `dist/`. En `main` (o con `CF_PAGES_BRANCH=main`) es **ERROR** que exista el JSON real o un dato interno (`*.xlsm`, `Res_firmadas*`, `cotejo_*`, `evol_conc*`): el build falla y queda el sitio anterior. En la rama del área interna son solo notas (INFO). En un `dist/` armado, el `.xlsm` es siempre error |
| `demo-interno/*` | `noindex`, `Cache-Control: no-store` y sin Analytics (`_headers`) |

**Qué no hay que hacer.** Mergear esta rama a `main` con esos archivos: si el sitio público se sirve sin `build_site.py` (GitHub Pages desde
`main`, o Cloudflare sin build), publica la raíz tal cual, `.xlsm` incluido. La compuerta lo frena solo si corre (`build_site.py`).

**Pasos en Cloudflare** (no se pudo abrir su documentación: confirmar en el panel):

1. Un proyecto de Pages **aparte** conectado a este repo, con *Production branch* = `claude/dreamy-cray-mxaf3v`, *Build command*
   `python3 build_site.py` y *Build output directory* `dist`. Un proyecto aparte, porque *Enable access policy* alcanza a **todo** el
   proyecto: si se activa en el que sirve `main`, el buscador público pediría login.
2. En ese proyecto: Settings → General → *Enable access policy*. Crea **dos** políticas, una para producción (`<proyecto>.pages.dev`) y otra
   para las vistas previas (`*.<proyecto>.pages.dev`); se configuran y se prueban por separado, con la lista de mails autorizados.
3. Probar en una ventana de incógnito: la página pide login, un mail no autorizado es rechazado, y `/data/seguimiento.json` y
   `/demo-interno/data/seguimiento.json` directos también.
4. **Revisar el proyecto que ya existe** (`buscadoranc`): si está conectado a este repo y tiene vistas previas de ramas, la rama ya pudo
   desplegarse **sin lista blanca** (publica la raíz: `/Res_firmadas.xlsm` se descarga). Deployments → buscar la vista previa de esta rama;
   borrar ese deployment, o desactivar las vistas previas de ramas (Settings → Builds → *Branch control*) hasta tener Access.
5. Cuando exista el área interna definitiva, `interno` en `ITEMS` de `assets/nav.js` apuntará a su dirección y `INTERNO` quedará en `true`.

Antes de mostrar datos reales a otras personas sigue valiendo la autorización institucional del área para alojarlos en estos servicios.

Sincronización del monitor: hoy a demanda (pedirle a Claude que exporte con `ArtifactData` y corra `monitor_merge.py`). El monitor sigue con
datos de ejemplo.

## Seguimiento (etapa 3): versión real en la rama del área interna

`/demo-interno/seguimiento/` ya trabaja con el Excel: `generar_seguimiento.py` lee la hoja `evol_conc` de `Res_firmadas.xlsm` y escribe
`demo-interno/data/seguimiento.json` (contrato `seguimiento` v2, en `demo-interno/SCHEMA.md`). Cada vez que se actualiza el Excel:
abrirlo y **guardarlo** (para que sus fórmulas estén calculadas), `python -B generar_seguimiento.py`, `python -B -m unittest discover -s tests`,
commit y push de la rama del área interna.

- **En trámite** = la definición del propio Excel (`General!C26`): Pendiente de presentación, Observado, En análisis, En instrucción,
  Suspendida, IT circulando, Para resolución o TDC. Al 9/10/2026: **45** (35 En instrucción, 6 Suspendida, 4 TDC). El script compara con el
  total que el Excel guardó y avisa si difieren.
- **Procedimiento**: `ES FT` = SÍ → PROSUM (14), NO → Ordinario (31).
- **Carátula resumida**: sin comillas, sin «S/ NOTIFICACIÓN ART. 9 DE LA LEY 27.442» (ni el art. 8 de la 25.156) ni «(CONC nnnn)»; se
  conserva un paréntesis que aclare una parte y se corta en 120 caracteres.
- **Equipo**: abogados (`Abogado_1/2`) y economistas (`Economista_1/2`) por separado, un expediente suma a cada persona asignada. Los
  apellidos se unifican (tildes, mayúsculas) y `ALIAS_APELLIDOS` en `generar_seguimiento.py` corrige tipeos (`ROSOZKA` y `ROZOSKA` →
  `ROSOSZKA`: **confirmar**).
- **Antigüedad** al corte (por defecto, el día de la generación): días corridos desde `Fecha_Ingreso`; no es plazo legal. La página avisa
  si el Excel se calculó hace más de 7 días (`excel_corte`: hoy 1/10/2026).

| Indicador | Columnas | Estado |
|---|---|---|
| Concentraciones en trámite por estado | `ESTADO` | Hecho |
| Antigüedad (hasta 90, 91-180, 181-365, más de 365 días) | `Fecha_Ingreso` | Hecho |
| Carga por abogado y por economista | `Abogado_1/2`, `Economista_1/2` | Hecho |
| Ordinario vs PROSUM en trámite | `ES FT` | Hecho |
| Tiempos de resolución, ordinarios vs PROSUM | `tipo`, `Fecha_Ingreso`, `Fecha_firma` | Ya está en `/conc/` |
| Evolución mensual del stock | `Fecha_Ingreso`, `Fecha_firma` | Pendiente: `evol_conc` guarda el estado de hoy, el histórico se reconstruye con ingreso y firma |
| Próximos a vencer | inicio del plazo, suspensiones | **Falta**: no está estructurado (`Revisión` trae notas de auditoría, no una fecha; los vencimientos están como texto libre en `Dictamen a revisar (SI/NO)` y `Observaciones`, que no se publican) y desde el 17/11/2026 rige el control previo |

**Para revisar en el Excel** (la página y el script lo muestran en «Notas»): 4 filas sin `ESTADO` (CONC-748, 998, 1457 y 1663: el Excel no las
cuenta); CONC-1955 figura En instrucción pero con fecha de firma (el Excel la cuenta); la columna `Dictamen a revisar (SI/NO)` se usa como
nota libre (15 de las 45 activas); apellidos con variantes (`ZUVIRIA`/`ZUVIRÍA`, `ROSOSZKA`/`ROSOZKA`/`ROZOSKA`/`Rososzka`).

## Qué se tomó de la rama `test/portal-anc` (ChatGPT)

Esa rama es otra versión de prueba del mismo portal. **No se mergeó nada de ella** (sigue intacta en el remoto y se puede borrar si
adoptás esta): pisaba cuatro rutas (`/conc/`, `/opis/`, `/herramientas/`, `data/conc.json`) con un diseño paralelo (`portal.css`,
`portal.js`, otras barras). Se revisó y se incorporó, adaptado al sistema de diseño de esta rama:

| Su idea | Qué se hizo acá |
|---|---|
| Tablero con filtros por año y tipo y CSV de la selección | Sí, en `/conc/`: año, tipo y **sector**; todo se recalcula (tarjetas, gráficos, tablas); CSV con protección contra fórmulas de Excel; los filtros viajan en la URL (`#a=2024&t=PROSUM`) |
| Demo de seguimiento (carga por analista, estados, antigüedad, revisiones) | Sí, como `/demo-interno/seguimiento/` (área interna, no pública), con contrato `seguimiento` v1 y tramos de antigüedad |
| Pruebas de contenido (`tests/test_portal.py`) | Sí, `tests/test_sitio.py`; en vez de comparar con un commit fijo (dejaría de valer al mergear) comprueban coherencias que valen siempre |
| Accesibilidad: «Saltar al contenido», aviso sin JavaScript, región de estado, controles de 38 px | Sí: salto al contenido en la barra (donde la página tiene `#contenido`), aviso `noscript` y línea de estado con `aria-live` en el tablero y el seguimiento, filtros de 38 px |
| Control de que el tablero corresponde al HTML publicado (`index_sha256`) | Sí, con una huella del corpus (carpeta, fecha, decisión) en lugar del hash del archivo entero, que cambia con cualquier retoque del HTML |
| Datos de demo con `demo: true`, y la página los exige | Sí, equivalente: `origen: "ejemplo"`, que exigen la página de seguimiento y `verificar_sitio.py` |
| Aviso en OPIs («pendientes de validación») | Disponible y apagado: `python -B integrar_opis.py --aviso`. Se enciende cuando se decida cómo comunicar el estado de los OPIs |
| Salida `public/` con lista explícita | Ya cubierta por `build_site.py` (lista blanca, URLs heredadas, sin demo en `main`) |
| Decisiones como texto original, sin agrupar | Las dos vistas: gráfico agrupado y, en «Cómo se agrupan las decisiones», las 39 variantes originales con su grupo |
| Barra y estilos propios; `/noticias/` y `/seguimiento/` públicas; `noindex` en todo | No: un solo sistema de diseño; el monitor de esta rama es más completo (port del artefacto) y el seguimiento va en el área interna; las herramientas públicas deben poder encontrarse (solo el área interna lleva `noindex`) |

Detalles que no se copiaron por ser errores de esa versión: el título de `/herramientas/` se escapaba con un `<br>` literal, y
reemplazaba todas las comas por puntos en frases enteras para dar formato a los miles.

## Pendientes (documentados, no se tocan en esta rama)

- **Productos.** El `index.html` del 1-oct no tiene productos (`index.html:298`; el 16-ago tenía 596 expedientes con productos). El
  `firm.xlsx` versionado tiene 17 columnas, no las 20 del protocolo, y nada lo detecta (`generar_pagina.py:175`,
  `comparar_index.py:162-166`). Hace falta el maestro de 20 columnas (`firm_unificado.xlsx`, ignorado).
- **PDFs `.PDF`.** CONC-1237, 1383, 1492, 1503, 1538, 1553, 1554, 1582 y 1606 fallan en Cloudflare (distingue mayúsculas); en Windows
  `generar_pagina.py:215` y `comparar_index.py:118` no lo ven.
- **OPIs.** 3 mal numeradas (`01_segmentar.py:36` no admite el guion de `OPI-288.pdf`; basta sumar `\-_` a la clase de caracteres),
  96 PDFs duplicados en `pdf/lectura_opi/opis/`, datos sin validar (criterio "otro" 41,7 %). El buscador principal ya enlaza el PDF de
  97 de sus 98 fichas OPI, incluidas las 11 con medidas de confidencialidad y 11 con DNI en el texto: confirmar que son versiones públicas.
- **Higiene.** `PROTOCOLO.md:164` usa `git add -A` y `nuevas/` no está ignorado; `extraer_empresas_ia.py:492` busca la clave de API
  dentro del árbol publicable; `PROTOCOLO.md:59` depende de un script fuera del repo; `.gitignore:35` dice `viejas/` y la carpeta es
  `viejos/`; hay copias viejas del buscador con Analytics (`productos buscador/`, `varios/`, `viejos/`).
- **Buscador.** Compuertas (productos, mayúsculas), Analytics solo en producción y `?q=`. Ya pasaba antes de esta rama: a 360 px o
  menos el buscador desborda en horizontal (la tabla del nomenclador `.bm-tabla` y un chip); no se tocó.

## Mapeo de tu esquema de tres repos (para después)

| Hoy (este repo) | Destino |
|---|---|
| `index.html`, `opis/`, `conc/`, `assets/`, `data/`, `pdf/`, `_headers`, `404.html` | `herramientas-anc` (el repo del sitio; renombrar es cosmético: la URL depende del nombre del *proyecto* Pages) |
| `generar_*.py`, `comparar_index.py`, `estado.py`, `extraer_*.py`, `mergear_firmadas.py`, `cotejar_res_firmadas.py`, `renombrar_y_listar.py`, `nomenclador_mercados.py`, `integrar_opis.py`, `verificar_sitio.py`, `pdf/lectura_opi/0*.py`, `pdf/escaneados/*.py`, `PROTOCOLO.md` | `anc-data-processing` (privado): `ocr/`, `pdfs/`, `excel/`, `sitio/` |
| `firm.xlsx`, `productos buscador/`, `viejos/`, `varios/*.xlsx`, `pdf/CONC_*.csv`, `pdf/escaneados/res_firmadas_ocr.xlsx` | `anc-data-processing/data/` (privado): el maestro sale del repo público |
| `bot noticias/`, `varios/INFORME_extraccion*`, `varios/Untitled-1.ipynb`, salidas `*_qmd` | `antitrust-research` (privado): `notebooks/`, `output/` |

Separar los repos parte el circuito mensual en dos commits: antes hay que traer al repo el script que hoy está afuera
(`PROTOCOLO.md:59`) y sumar un `publicar` que corra las compuertas. Los PDFs (≈894 MB) se quedan con el sitio.

## Límites conocidos

- Solo modo claro, igual que el buscador. Los colores de series están definidos como variables (`--anc-s1…`) por si se agrega modo oscuro.
- Los gráficos con 2 o más series no tienen la textura opcional para impresión o daltonismo extremo; la leyenda con totales, el
  tooltip y la **vista en tabla** cubren esa necesidad. Turquesa y amarillo quedan por debajo de 3:1 de contraste sobre el fondo
  (aviso esperado de la paleta): por eso siempre hay etiquetas visibles y tabla.
- Sin Analytics en las páginas nuevas (a propósito, para no mezclar pruebas con los reportes). Sumarlo si se adopta. El buscador
  conserva el suyo.
- `data/conc.json` pesa unos 250 KB (trae el detalle por expediente); `/herramientas/` lo pide solo para leer la fecha de corte
  (se cachea 5 minutos). Si molesta, la fecha puede pasar a un archivo chico aparte.
- El tablero muestra los datos tal como están cargados: 29 % de decisiones vacías, 39 % de sectores sin clasificar y solo 54 % de
  expedientes con fecha de ingreso. No se completa nada.
- No pude abrir las páginas de documentación de Cloudflare desde donde se desarrolló: el comportamiento de `404.html`, de Access y del
  build con Python de Cloudflare está sin verificar y se confirma en el panel.
