# Texto de decisiones y compromisos de la Unión Europea

Este paso transforma los PDF descargados en texto verificable por página para
la biblioteca de remedios de la ANC. Trabaja localmente, sin claves de API ni
servicios externos. Conserva las decisiones y los compromisos tal como llegan:
no resume, traduce ni identifica todavía problemas competitivos o remedios.

## Instalación

Desde la raíz de `buscadorANC`, con Python 3.10 o superior:

```bash
python -m pip install -r remedios_ue/requirements.txt
```

En Windows también se puede usar `py -3`; en macOS/Linux, `python3`.
PyMuPDF es la misma biblioteca de lectura de PDF utilizada por el circuito OPI.

## Entrada y primera corrida

Esperá a que termine el descargador. La entrada es **su carpeta de salida**,
que contiene `reporte.csv` y `archivos/`. No es la carpeta del ZIP ni el
manifiesto original. Se admite mover la carpeta completa entre computadoras,
porque el reporte conserva rutas relativas.

```text
descargas_anc/
  reporte.csv
  archivos/
    M_10646/
      <archivo>.pdf
```

Comprobá primero la selección y los SHA-256 sin generar salidas:

```bash
python remedios_ue/extraer_texto.py --entrada "C:/ruta/descargas_anc" --plan
```

Luego procesá cinco PDF únicos:

```bash
python remedios_ue/extraer_texto.py --entrada "C:/ruta/descargas_anc" --limite 5
```

Quitá `--limite 5` para procesar todos. También podés elegir expedientes:

```bash
python remedios_ue/extraer_texto.py --entrada "C:/ruta/descargas_anc" --casos M.10646 M.10896
```

Si `descargas_anc` está en el directorio desde donde ejecutás Python,
podés omitir `--entrada`. Las rutas relativas se resuelven desde ese directorio.

## Salidas

Por defecto se escriben en `<entrada>/texto_extraido/`. `--destino RUTA`
permite elegir otra carpeta.

| Archivo | Contenido |
|---|---|
| `documentos/<sha256>.json` | Texto por página, metadatos del PDF y todas las filas del reporte que apuntan a ese contenido. |
| `documentos/<sha256>.txt` | Texto UTF-8 con separadores explícitos de página física del PDF. |
| `documentos.csv` | Una fila por documento lógico del reporte seleccionado: expediente, URL, resultado, alertas y rutas a las salidas. |
| `paginas.csv` | Una fila por página de cada PDF único: cantidad de texto y alertas para revisión. |
| `resumen.json` | Conteos, alcance de la corrida, versión del motor y configuración. |
| `estado.json` | Caché para reanudación; registra los SHA-256 de las salidas completas. |

El JSON de cada PDF contiene `referencias` con los datos originales del reporte,
incluidos `documento_id`, `caso`, título, idioma, tipo, grupo, `url_origen`,
`url_final`, ruta local y SHA-256. Un PDF puede servir a varias entradas o
expedientes: se extrae una sola vez por contenido y conserva todas sus
referencias **dentro de la selección de esa corrida**. No se deduce el tipo
documental a partir del nombre del archivo.

Cada página tiene `pagina_pdf` (posición física, empezando en **1**),
`etiqueta_pdf` (etiqueta interna del PDF, si existe), `texto`, medidas de texto
y alertas. La etiqueta interna puede ser `i`, `ii`, `1` o no existir; **no se
infiere la numeración impresa**. Para citar usá el PDF original y la página
física. Los anexos integrados conservan la numeración física del archivo completo.

Se conserva el texto devuelto por `get_text("text", sort=True)`, incluidos
encabezados, pies, numeración y saltos. El orden de lectura, las columnas,
tablas, fórmulas y caracteres especiales deben contrastarse con el original.
La extracción técnica no verifica que una URL corresponda a la versión
definitiva de los compromisos.

## Páginas que requieren revisión y OCR

El programa marca páginas sin texto, con menos de 30 letras/dígitos,
con muchos caracteres de sustitución o con una imagen grande y poco texto.
Esto también detecta documentos mixtos con páginas digitales y escaneadas.
`--min-caracteres 50` cambia el primer umbral. La regla de imagen usa una
cobertura de al menos el 50 % y menos de 200 letras/dígitos.

`posible_ocr` es una **alerta heurística**: una portada breve o una página
en blanco también pueden activarla. Puede pasar por alto escaneos con mucho
texto digital superpuesto o imágenes fragmentadas. No mide exactitud jurídica
ni garantiza que el resto esté completo. Un error del motor en una página queda
registrado como `error_pagina`.

### OCR (`--ocr`)

En el corpus real, la Comisión guarda como **imagen páginas enteras de las
decisiones**: texto normal y tablas de cuotas de mercado. Pasa en 505 de las 9.100
páginas, sobre todo en las que tienen datos confidenciales. Sin OCR faltan 1.124
párrafos numerados (3,7 %) de 22 decisiones.

```bash
python remedios_ue/extraer_texto.py --entrada descargas_anc --ocr
```

- **Qué páginas lee:** solo las que son imagen o no tienen texto (`sin_texto` o
  `imagen_con_texto_escaso`). Una página con poco texto digital y sin imagen no se toca.
- **Cómo lo lee:** Tesseract, vía PyMuPDF, a 300 dpi (`--ocr-dpi`). El idioma se elige
  según el `idioma` del reporte (EN → `eng`, FR → `fra`, …).
- **Cómo queda marcado:** la página tiene `origen_texto = "ocr"` y la alerta `texto_ocr`,
  y sigue marcada para revisión. El TXT la señala con
  `[PÁGINA PDF n | texto OCR: verificar contra el PDF]`. Las demás páginas tienen
  `origen_texto = "pdf"`.
- **Calidad:** el OCR recupera los párrafos pero comete errores ("combmed",
  "[80-901 %") y lee mal las tablas. **Una cifra tomada de una página OCR se
  verifica contra el PDF.**
- **Errores:** si falla en una página, queda la alerta `error_ocr` y la corrida sigue.
- **Caché:** activar o desactivar `--ocr` cambia la configuración y vuelve a extraer.
- **Sin Tesseract:** `--ocr` termina con código 1 y un mensaje.
- **Instalación:** Tesseract con los idiomas `eng` y `fra`. En Windows, el
  instalador de UB Mannheim. Si no se encuentra solo, se indica la carpeta con
  `--tessdata RUTA` o con la variable `TESSDATA_PREFIX`.

Una salida `requiere_revision` contiene lo que se pudo extraer y necesita
control humano. `error_archivo` indica un problema de ruta, archivo ausente o
SHA-256 distinto del reporte. `error_extraccion` incluye PDF cifrados, archivos
ilegibles o formatos que no son PDF. Cada error queda en `documentos.csv` y
el resto del lote continúa. HTML y descargas fallidas permanecen registrados
como omisiones; no se convierten en texto ni se cuentan como PDF extraídos.

## Reanudación y alcance

Repetí el mismo comando tras un corte. Se verifican el SHA-256 del PDF y los
SHA-256 de sus JSON y TXT antes de reutilizar una extracción. Una salida
alterada, un cambio de motor o un cambio de umbral provocan una nueva
extracción. `--rehacer` fuerza ese paso. Las versiones distintas de un PDF
tienen SHA distintos y generan salidas separadas. Las rutas del reporte se
validan para que no salgan de la carpeta de entrada.

Los informes agregados describen **la última selección**: una corrida con
`--casos` o `--limite` reemplaza esos informes. Los JSON/TXT anteriores y la
caché permanecen; una corrida completa vuelve a incluirlos tras comprobarlos.
Se escribe cada archivo de forma atómica y se guarda el estado después de cada
PDF. No ejecutes dos extractores con el mismo destino. Si hubo un cierre
forzado y quedó `.extraccion.lock`, comprobá que el proceso haya terminado
antes de borrar solo ese bloqueo. Se rechaza una entrada con `.descarga.lock`.

Los códigos de salida son `0` (corrida terminada, puede haber alertas u
omisiones), `2` (errores de archivo o extracción), `1` (configuración o error
local) y `130` (interrupción). Leé siempre `resumen.json` y `documentos.csv`;
un código `0` no significa que el inventario documental esté completo.

Las carpetas llamadas `descargas_anc` y `texto_extraido` están ignoradas por Git.
Si elegís otro nombre de salida, agregalo a tu exclusión local antes de
versionar archivos. El corpus y los reportes de trabajo no son parte del código.

## Validación y siguiente paso

```bash
python -m unittest discover -s remedios_ue/tests -v
```

Las pruebas generan PDF pequeños y comprueban páginas, fuentes, deduplicación,
reanudación, integridad, interrupciones y alertas de escaneo. No necesitan red.
Después del piloto, revisar `documentos.csv`, `paginas.csv`, `resumen.json` y
una muestra de JSON contra los PDF originales. Ese corpus permite construir
las fichas problema competitivo → remedio, con citas verificables.

## Compatibilidad con el descargador activo

Integrado con `descargar_remedios.py` 1.1.0 de la rama
`claude/gallant-bardeen-y00h2a` (commit `3e01ab4`). También admite el reporte
del ZIP original. No depende del nombre físico del PDF: utiliza `archivo`
y su SHA-256, por lo que admite tanto los nombres nuevos como los anteriores.

Conserva en JSON y CSV `universo`, `coincide_inventario`, `url_referencia`
y `paginas_compromisos`. La separación entre casos principales y revisiones
queda registrada en el resumen. Si `coincide_inventario` dice `no`, se
extrae el PDF descargado y se marca la referencia para revisión de versión.
Esto es distinto de un SHA que no coincide con el **reporte de descarga**:
ese último caso es un error de integridad y no se extrae.

`paginas_compromisos` se conserva tal como viene del inventario y no se usa
para recortar: se extrae el archivo completo, incluidos los anexos integrados.
Esas páginas **son físicas** (posición en el PDF, desde 1), porque
`relevar_documentos.py` las ubicó con PyMuPDF sobre el mismo archivo. Coinciden
con `pagina_pdf` y sirven para separar el texto de los compromisos. En el corpus
real, en las 44 decisiones el título del anexo aparece en la página de inicio
indicada. Los Merger Briefs y
comunicados que el descargador entrega como PDF siguen el mismo circuito.
`sin_version_pdf`, `sitio_bloqueado` y otros estados sin archivo quedan como
omisiones con su URL de referencia.

La prueba de integración genera el reporte mediante el descargador activo,
con una respuesta HTTP simulada que contiene un PDF válido, y lo entrega al
extractor sin adaptar sus columnas. Cubre decisión con anexo compartido,
revisión de remedios, diferencia de SHA contra el inventario y comunicado
sin versión PDF. El corpus real de la UE sigue pendiente de validación.

El resumen conserva el SHA-256 de la instantánea del reporte leída al inicio.
Si el reporte cambia durante la extracción, lo señala en
`reporte_cambio_durante_corrida` y devuelve código `2`: repetí la corrida
cuando haya terminado el descargador.
