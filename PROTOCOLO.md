# Protocolo de actualización mensual

Todo el circuito vive en la raíz del repo y gira alrededor de **un solo archivo**:
`firm.xlsx`, hoja `firmadas`, 20 columnas. No hay copias paralelas. Si alguna vez
volvés a ver un `firm4*.xlsx` suelto, es un backup, no un insumo.

Si no te acordás en qué paso quedaste:

```bash
python estado.py
```

---

## Los pasos

### 0. Ver qué falta cargar

```bash
python cotejar_res_firmadas.py
```

Cruza `firm.xlsx` contra `Res_firmadas.xlsm` y escribe `cotejo_buscador_vs_res_firmadas.xlsx`.
La solapa **`1_Faltan_en_buscador`** son las resoluciones firmadas que todavía no están
publicadas: eso es lo que hay que cargar este mes. Mirá también **`5_Discrepancias_de_datos`**,
que son expedientes cargados en los dos lados con datos distintos.

### 1. Pegar las filas nuevas y bajar los PDFs

A mano, en Excel: copiás las filas de la solapa 1 desde `Res_firmadas.xlsm` (hoja `firmadas`)
y las pegás al final de `firm.xlsx`. Las 13 primeras columnas coinciden una a una, así que
es un pegado directo.

Los PDFs van a `nuevas/`.

> **Este paso no es opcional.** El extractor deja `Mercados relevantes` vacío cuando no logra
> identificar la empresa objeto (lo hace a propósito, por precisión). Si no pegás la fila
> desde `Res_firmadas`, ese expediente entra sin mercado, sin sector y sin producto.

### 2. Normalizar los nombres de los PDFs

```bash
python renombrar_y_listar.py
```

Deja todo como `CONC-1981.pdf`. Revisá que no haya quedado ningún `_2` inesperado: eso
significa que dos archivos distintos reclamaron el mismo número.

### 3. Extraer los datos de los PDFs

```bash
python extraer_firmadas3.py nuevas firmadas3.xlsx
```

Saca carátula, fechas, decisión, números, mercados y empresas de cada PDF de `nuevas/`.
Revisá `firmadas3_no_extraibles.txt`: los que aparecen ahí son escaneados sin texto y hay
que cargarlos a mano.

> Depende de `C:\Users\Admin\Documents\ANC\descargas_cndc\extraer_firmadas2.py`, que está
> **fuera del repo**. En otra máquina este paso no arranca.

### 4. Mergear al maestro

```bash
python mergear_firmadas.py --dry-run
```

```bash
python mergear_firmadas.py
```

Completa **solo celdas vacías**: nunca pisa lo que ya cargaste a mano. Deja respaldo en
`respaldos/`. Lo que hay que leer del informe:

- **AVISOS** — una carpeta que ya existía aparece con otra resolución. Suele ser un
  incidente legítimo, pero también puede ser una carpeta mal tipeada.
- **DISCREPANCIAS** — el dato ya estaba cargado y no coincide con el del PDF. No se pisó
  nada; resolvelo a mano. Acá aparecen los errores de tipeo tipo `DISF-` contra `DISFC-`.

### 5. Empresas involucradas (usa la API, cuesta plata)

```bash
python extraer_empresas_ia.py --solo-extraer
```

Esto **no gasta**: segmenta los PDFs y te dice cuánto saldría. Recién después:

```bash
python extraer_empresas_ia.py
```

Es reanudable —los `.jsonl` son caché— así que si lo cortás, retoma donde iba. Al terminar,
mirá `empresas_ia_reporte.txt`: las marcadas `confianza=baja` hay que revisarlas, y las
"celdas pisadas" son las que corrigió sobre datos defectuosos.

### 6. Productos

```bash
python extraer_productos.py --dry-run
```

```bash
python extraer_productos.py
```

Completa `productos`, `productos_sector` y `productos_sugeridos`, **solo donde estén
vacías**. Podés editar la columna `productos` a mano sin miedo: la próxima corrida la
respeta.

> Si un expediente no tiene que mostrar productos, escribí `-` en la celda. Si la dejás
> vacía, la próxima corrida la vuelve a completar.

`productos_sugeridos` son las frases del mercado relevante que ningún patrón del catálogo
reconoció. Es el material para ampliar el catálogo (ver la sección de abajo).

### 7. Mover los PDFs a `pdf/`

```bash
python estado.py
```

Te dice cuáles ya están cargados en el maestro y por lo tanto listos para mover, y te arma
el `Move-Item`. **El movimiento lo hacés vos**; ningún script toca archivos.

Tiene que ir **antes** del paso 8: `generar_pagina.py` solo enlaza PDFs que estén en `pdf/`.
(En cambio `extraer_empresas_ia.py` lee de `pdf/` y de `nuevas/`, por eso el paso 5 funciona
antes de mover.)

### 8. Generar la página

```bash
python generar_pagina.py
```

Antes, guardá el index anterior para poder compararlo:

```bash
cp index.html respaldos/index_previo.html
```

### 9. Verificar antes de subir

```bash
python comparar_index.py respaldos/index_previo.html index.html
```

**`PERDIDOS` tiene que dar 0.** Si da cualquier otra cosa, no subas: casi siempre es una
`Carpeta` mal escrita en alguna de las filas nuevas. El script devuelve código de salida 1
en ese caso.

Mirá también que `Links a PDF que no existen` dé 0 y que los conteos por sector y por
producto se muevan para arriba.

```bash
python cotejar_res_firmadas.py
```

La solapa `1_Faltan_en_buscador` tiene que quedar solo con lo que está en proceso o
esperando PDF.

### 10. Publicar

```bash
git add -A && git commit -m "act $(date +%d-%m)"
```

```bash
git push
```

---

## Orden que no se puede alterar

```
3 → 4        mergear necesita firmadas3.xlsx
4 → 5 → 6    empresas y productos leen lo que dejó el merge
7 → 8        el index solo enlaza PDFs que ya estén en pdf/
8 → 9 → 10   nunca pushear sin comparar
```

---

## Ampliar el catálogo de productos

El catálogo vive en el dict `PRODUCTOS` de `nomenclador_mercados.py`. Es lo que hace que un
producto se detecte solo en los expedientes que vengan el mes que viene.

Escribir un producto a mano en la columna `productos` de `firm.xlsx` arregla **ese**
expediente, pero no enseña nada al catálogo. Para que se detecte solo hay que agregarlo al
nomenclador. La materia prima está en la columna `productos_sugeridos` que deja el paso 6.

`revision_productos.xlsx` es un volcado del catálogo (un renglón por patrón) pensado para
revisarlo en Excel. Hoy ningún script lo lee ni lo escribe: el circuito de ida y vuelta
está sin construir.

---

## Qué es cada archivo

| archivo | qué es |
|---|---|
| `firm.xlsx` | **el maestro**, hoja `firmadas`, 20 columnas. Único insumo del buscador. |
| `index.html` | la página publicada. Se genera, no se edita. |
| `Res_firmadas.xlsm` | seguimiento del área. Fuente de las filas nuevas. No lo toca ningún script. |
| `nuevas/` | los PDFs del mes, antes de procesarlos. |
| `pdf/` | los PDFs publicados. El buscador enlaza acá. |
| `respaldos/` | copias automáticas antes de cada escritura. No va al repo. |
| `varios/` | archivo muerto: versiones viejas, pruebas, informes. |
| `firmadas3.xlsx` | salida temporal del paso 3. Se pisa todos los meses. |
| `revision_productos.xlsx` | volcado del catálogo de productos, para revisar a ojo. |

### Scripts

| script | qué hace |
|---|---|
| `cotejar_res_firmadas.py` | qué falta cargar (9 solapas de control) |
| `renombrar_y_listar.py` | normaliza nombres de PDF en `nuevas/` |
| `extraer_firmadas3.py` | PDFs → `firmadas3.xlsx` |
| `mergear_firmadas.py` | `firmadas3.xlsx` → `firm.xlsx` |
| `extraer_empresas_ia.py` | completa empresas con la API (lo único que cuesta plata) |
| `extraer_productos.py` | completa las 3 columnas de productos |
| `generar_pagina.py` | `firm.xlsx` → `index.html` |
| `comparar_index.py` | compuerta: ¿se perdió algún expediente? |
| `estado.py` | en qué paso del mes estás |
| `nomenclador_mercados.py` | catálogos de sectores y productos. No se ejecuta solo. |
| `unificar_maestro.py` | **uso único**: fundió las 4 copias del maestro en `firm.xlsx`. Ya cumplió. |
