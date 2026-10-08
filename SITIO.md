# Sitio de herramientas ANC — guía de esta rama

Esta rama (`claude/dreamy-cray-mxaf3v`) **solo agrega archivos nuevos**. No cambia `index.html`, `generar_pagina.py`,
`comparar_index.py`, `estado.py`, `PROTOCOLO.md`, `.gitignore`, `firm.xlsx`, `pdf/**` ni `pdf/lectura_opi/**`, así que
el circuito mensual del buscador sigue exactamente igual. Se puede adoptar entera, por carpeta, o descartar.

Se comprueba con: `python -B verificar_sitio.py --aditivo` (falla si la rama modifica o borra algo que ya estaba en `main`).

## Qué hay

| URL | Qué es | Cómo se genera |
|---|---|---|
| `/` | el buscador de siempre | **sin cambios** (`generar_pagina.py`) |
| `/herramientas/` | mapa de herramientas, agrupadas | HTML estático (lee la fecha de `data/conc.json`) |
| `/opis/` | buscador de OPIs (96 dictámenes) | `python -B integrar_opis.py` |
| `/conc/` | tablero público de resoluciones firmadas | `python -B generar_tablero.py` |
| `/demo-interno/noticias/` | prototipo del Monitor M&A con **datos de ejemplo** | HTML + `demo-interno/data/monitor.sample.json` |
| `/mercados/ /participaciones/ /redes/ /informes/` | reservadas (un `README.md` cada una) | — |

Piezas de apoyo: `assets/` (`anc.css`, `nav.js`, `charts.js`), `data/conc.json`, `_headers`, `robots.txt`, `404.html`,
`verificar_sitio.py`, `build_site.py`.

El buscador **no** enlaza a las páginas nuevas (no se tocó). Las páginas nuevas sí llevan una barra que vuelve a `/`.
`/herramientas/` se alcanza por URL; sumar un link desde el buscador es una decisión aparte.

## Cómo probar

**Local** (en la raíz del repo; en Windows también sirve `py -m http.server 8000`):

```
python -B -m http.server 8000
```

Abrí `http://localhost:8000/herramientas/`, `/opis/`, `/conc/` y `/demo-interno/noticias/`.

**En Cloudflare:** al subir la rama, Pages → `buscadoranc` → Deployments muestra un *preview* de la rama (si los previews de
ramas están activos). Qué mirar:

1. `/` y un PDF (`/pdf/CONC-1003.pdf`) siguen igual que en producción.
2. Cada página nueva carga sin errores y la barra lleva a las demás y de vuelta al buscador.
3. `/opis/`: buscar "participación minoritaria" da 5 resultados; filtros por ley, criterio y tipo funcionan.
4. `/conc/`: pasar el mouse por las columnas y barras muestra el detalle; **Ver como tabla** cambia el gráfico por su tabla.
5. `/demo-interno/noticias/`: filtros, **Descargar CSV** (se abre bien en Excel) y el cartel de datos de ejemplo.
6. Una ruta inexistente (`/cualquier/cosa`) debe mostrar `404.html` **con código 404**. Hoy responde 200 con el buscador:
   Pages trata el sitio como una SPA mientras no exista `404.html`. Esto es lo único que cambia el comportamiento global.

## Cómo adoptar o descartar

| Querés… | Hacé |
|---|---|
| Todo | mergear la rama a `main` |
| Todo menos el cambio de 404 | antes de mergear, borrar `404.html` (está en un commit aparte) |
| Sin el prototipo del monitor | borrar `demo-interno/` y `robots.txt` y la regla de `_headers` para `/demo-interno/*` |
| Sin OPIs | borrar `opis/` y `integrar_opis.py` (el original no se tocó) |
| Sin tablero | borrar `conc/`, `data/` y `generar_tablero.py` |
| Nada | no mergear; borrar la rama |

Si borrás una carpeta, sacala también de `PAGINAS_NUEVAS` en `verificar_sitio.py` y del arreglo `ITEMS` de `assets/nav.js`.

## Cómo regenerar

```
python -B generar_tablero.py     # lee firm.xlsx -> conc/index.html y data/conc.json
python -B integrar_opis.py       # copia pdf/lectura_opi/buscador_opis.html a opis/index.html (+barra)
python -B verificar_sitio.py     # compuerta: links con mayúsculas exactas, tamaños, lista negra, ejemplo vs real
```

Usá siempre `-B`: hay dos `.pyc` versionados que si no Python reescribiría y aparecerían como modificados.

Para el circuito mensual, después del paso 8 (`generar_pagina.py`) se corre `generar_tablero.py` (y, si regeneraste los OPIs,
`integrar_opis.py`); el resto no cambia. El tablero lee el mismo `firm.xlsx`.

## `build_site.py` y la lista blanca (opcional)

Hoy Pages publica **la raíz entera del repo**: `firm.xlsx`, los `.py`, `PROTOCOLO.md`, `varios/`, `viejos/`… quedan servidos por
URL. `build_site.py` arma `dist/` con una lista blanca y deja de publicar eso, sin mover nada y sin tocar el flujo del buscador.

```
python -B build_site.py --reporte     # qué se publicaría y qué dejaría de publicarse (no arma nada)
python -B build_site.py               # arma dist/
```

Resultado hoy: se publican 1.083 archivos (854 MB: `index.html`, los PDF de primer nivel, las páginas nuevas y dos URLs heredadas) y
dejan de servirse 237 (scripts, Excel, `varios/`, `viejos/`, escaneados, CSV…). Las URLs heredadas que se mantienen para no
cortar nada son `productos buscador/index.html` y `pdf/lectura_opi/buscador_opis.html` (`--sin-legado` las saca).
`demo-interno/` no entra cuando la rama de Cloudflare es `main` (variable `CF_PAGES_BRANCH`), así que la demo nunca llega a producción.

**Probarlo sin tocar el proyecto real:** crear un segundo proyecto de Pages conectado a este repo, con rama de producción
`claude/dreamy-cray-mxaf3v`, *Build command* `python3 build_site.py` y *Build output directory* `dist`. El proyecto `buscadoranc`
no cambia. Si te convence, esos dos valores son los únicos que habría que cambiar en el proyecto real.

Detalles: usa solo la biblioteca estándar (Python 3.7+); antes de armar corre `verificar_sitio.py` y aborta si falla (en Cloudflare, un
build fallido deja el deploy anterior). Como `dist/` no está en `.gitignore` y el protocolo usa `git add -A`, el script lo agrega a
`.git/info/exclude` (local, no se versiona) para que no se suba por accidente.

## Contratos de datos

Cada herramienta lee un JSON versionado (`schema_version`) y no depende de la fuente.

- `data/conc.json` (v1): agregados del tablero. Lo escribe `generar_tablero.py`.
- Monitor: `demo-interno/SCHEMA.md` define `operaciones` v1 (campos, valores, CSV). `demo-interno/monitor_merge.py` junta lo exportado
  con `ArtifactData` en `monitor.json` + `operaciones.csv`. **El `monitor.json` real nunca va a este repo público.**
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

## Diseño del seguimiento (etapa 3)

Indicadores para dirección, calculados automáticamente desde `Res_firmadas.xlsm` (hojas `firmadas` y `evol_conc`, las mismas que ya
lee `cotejar_res_firmadas.py`) con un `generar_seguimiento.py` local. Nada se carga a mano.

| Indicador | Columnas | Estado |
|---|---|---|
| Stock de concentraciones activas y evolución mensual | `Fecha_Ingreso`, `Fecha_firma`, `ESTADO` | Disponible; confirmar los valores de ESTADO "en proceso" |
| Antigüedad de los expedientes (0–3, 3–6, 6–12, >12 meses) | `Fecha_Ingreso`, `MESES` | Disponible |
| Tiempos de resolución, ordinarios vs PROSUM | `tipo`, `Fecha_Ingreso`, `Fecha_firma` | Disponible (ya está en `/conc/`) |
| Ingresos, resoluciones y productividad por período | `Fecha_Ingreso`, `Fecha_firma` | Disponible |
| Expedientes por analista y por estado | columna de analista + `ESTADO` | **No confirmado**: ningún script nombra una columna de analista |
| Próximos a vencer | inicio del plazo, procedimiento, suspensiones | **Falta**: `DIAS`/`meses` son tiempo corrido, no plazo legal; además desde el 17/11/2026 rige el control previo |

Hacen falta los encabezados reales de `Res_firmadas.xlsm` (no están en el repo) para cerrar este diseño.

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
- **Buscador.** Compuertas (productos, mayúsculas), Analytics solo en producción, `?q=` y barra común.

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
- Sin Analytics en las páginas nuevas (a propósito, para no mezclar pruebas con los reportes). Sumarlo si se adopta.
- El tablero muestra los datos tal como están cargados: 29 % de decisiones vacías, 39 % de sectores sin clasificar y solo 54 % de
  expedientes con fecha de ingreso. No se completa nada.
- No pude abrir las páginas de documentación de Cloudflare desde donde se desarrolló: el comportamiento de `404.html`, de Access y del
  build con Python de Cloudflare está sin verificar y se confirma en el panel.
