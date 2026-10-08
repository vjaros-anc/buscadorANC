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
| `/demo-interno/seguimiento/` | prototipo del seguimiento de expedientes con **datos de ejemplo** | HTML + `demo-interno/data/seguimiento.sample.json` |
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
5. `/demo-interno/noticias/` y `/demo-interno/seguimiento/`: filtros, **Descargar CSV** (se abre bien en Excel) y el cartel de datos
   de ejemplo.
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
(son datos de ejemplo, con `noindex`, pero igual no deberían estar en producción): borrala antes de mergear y poné `INTERNO = false`.
Con `build_site.py` eso se resuelve solo (ver abajo).

## Cómo regenerar

```
python -B generar_tablero.py     # lee firm.xlsx -> conc/index.html y data/conc.json
python -B integrar_opis.py       # copia pdf/lectura_opi/buscador_opis.html a opis/index.html (+barra)
python -B verificar_sitio.py     # compuerta: links con mayúsculas exactas, tamaños, lista negra, ejemplo vs real, tablero al día
python -B -m unittest discover -s tests -v   # pruebas de coherencia del sitio (14 pruebas, unos 10 s)
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
- Monitor y seguimiento: `demo-interno/SCHEMA.md` define `operaciones` v1 y `seguimiento` v1 (campos, valores, CSV).
  `demo-interno/monitor_merge.py` junta lo exportado con `ArtifactData` en `monitor.json` + `operaciones.csv`. **El `monitor.json` y el
  seguimiento reales nunca van a este repo público**: `verificar_sitio.py` falla si aparece uno con `origen` distinto de `"ejemplo"`.
- Clave común de expediente: `tipo-número` normalizado (`nm.parse_carpeta`). Ojo: `(tipo, número)` no es único (OPI-232, INC-1663);
  `(tipo, número, resolución)` sí.

## Área interna (cuando se haga)

Lo que use datos internos (monitor real, seguimiento de `Res_firmadas.xlsm`) **no puede vivir en este repo**: es público y Pages sirve
todo lo que hay en él. Camino previsto:

1. Repo **privado** aparte (p. ej. `anc-interno`) y **segundo proyecto de Pages** conectado a él.
2. Cloudflare Access sobre ese proyecto: *Enable access policy* del proyecto crea **dos** políticas, una para producción
   (`<proyecto>.pages.dev`) y otra para los previews (`*.<proyecto>.pages.dev`). Se configuran y se prueban por separado.
3. Probar en una ventana de incógnito: la página pide login, un mail no autorizado es rechazado y `/data/monitor.json` directo también.
4. Recién ahí se sincroniza el monitor real (`monitor_merge.py`) al repo privado.
5. Antes de cargar datos reales: autorización institucional del área para alojarlos en estos servicios, y un segundo administrador.

No hace falta privatizar este repo: privatizarlo no oculta nada (Pages sirve la raíz) y rompería el botón "Archivo (PDFs)" del
buscador, que apunta a GitHub (`generar_pagina.py:57`). Access por *ruta* dentro de `pages.dev` no está documentado para Pages:
por eso se propone un proyecto aparte.

Sincronización del monitor: hoy a demanda (pedirle a Claude que exporte con `ArtifactData` y corra `monitor_merge.py`). Para
automatizarla, la Rutina (días 1 y 15, 08:50) tendría que escribir el JSON en el repo privado; hay que probar si la sesión de la
Rutina puede hacerlo (hoy no tiene repo adjunto).

Cuando exista el área interna real, `interno` en `ITEMS` de `assets/nav.js` apuntará a su dirección (otro proyecto de Pages) y el
interruptor `INTERNO` quedará en `true` también en producción.

## Seguimiento (etapa 3): demo hecha, versión real pendiente

Ya hay una demo (`/demo-interno/seguimiento/`, con expedientes ficticios): carga por analista, estados en el orden del trámite,
antigüedad por tramos (hasta 90, 91 a 180, 181 a 365 y más de 365 días), revisiones en 15 días y vencidas, tabla y CSV. Mide la
antigüedad al **corte** del archivo (no a «hoy») y aclara que ni la antigüedad ni la revisión son plazos legales. Lo que sigue es el
diseño de la versión real: indicadores para dirección, calculados automáticamente desde `Res_firmadas.xlsm` (hojas `firmadas` y
`evol_conc`, las mismas que ya lee `cotejar_res_firmadas.py`) con un `generar_seguimiento.py` local. Nada se carga a mano.

| Indicador | Columnas | Estado |
|---|---|---|
| Stock de concentraciones activas y evolución mensual | `Fecha_Ingreso`, `Fecha_firma`, `ESTADO` | Disponible; confirmar los valores de ESTADO "en proceso" |
| Antigüedad de los expedientes (0–3, 3–6, 6–12, >12 meses) | `Fecha_Ingreso`, `MESES` | Disponible |
| Tiempos de resolución, ordinarios vs PROSUM | `tipo`, `Fecha_Ingreso`, `Fecha_firma` | Disponible (ya está en `/conc/`) |
| Ingresos, resoluciones y productividad por período | `Fecha_Ingreso`, `Fecha_firma` | Disponible |
| Expedientes por analista y por estado | columna de analista + `ESTADO` | **No confirmado**: ningún script nombra una columna de analista |
| Próximos a vencer | inicio del plazo, procedimiento, suspensiones | **Falta**: `DIAS`/`meses` son tiempo corrido, no plazo legal; además desde el 17/11/2026 rige el control previo |

Hacen falta los encabezados reales de `Res_firmadas.xlsm` (no están en el repo) para cerrar este diseño; el contrato `seguimiento` v1
de `demo-interno/SCHEMA.md` ya tiene los campos que la demo necesita (`id`, `operacion`, `analista`, `tipo`, `estado`, `ingreso`,
`revision`). Los estados de la demo son de ejemplo: los reales salen de la columna `ESTADO`.

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
