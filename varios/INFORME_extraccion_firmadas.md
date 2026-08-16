# Informe: extracción de Grupo/Empresa, Empresas involucradas, Mercado relevante y Relaciones económicas

**Fecha:** 2026-07-23 · **Alcance:** solo CONC (concentraciones) · **No se modificó `firm.xlsx`.**

Extractor analizado: `extraer_firmadas2.py` (el que llena las columnas V2).
Extractor nuevo propuesto: **`extraer_firmadas3.py`** (en esta carpeta).

---

## 1. Método

Se cruzó `firm.xlsx` (564 filas CONC) con los PDF de `pdf/` por número de expediente,
se corrió el extractor sobre cada PDF y se comparó su salida contra los PDF originales.
Se clasificaron los motivos por los que un campo queda vacío o mal.

## 2. Estado actual (qué tan lleno está cada campo, sobre CONC)

| Campo | Lleno hoy (V2) | Con el extractor original | Con el extractor nuevo (V3) |
|---|---|---|---|
| Grupo/Empresa | 94 % | 94 % | 94 % (sin cambios, ya funciona) |
| Empresas involucradas | 73 % | 72 % | **76 %** |
| Mercado relevante | 50 % | 50 % | **70 %** |
| Relaciones económicas | ~41 % | 49 % | 49 % (sin cambios; ver §6) |

> El extractor original reproduce casi exactamente lo que hay en las V2 (mercados 50 % vs 50 %),
> lo que confirma que **las V2 salen del Python**. Un puñado de celdas V2 (~16 en mercado) tienen
> datos que ni el original ni V3 pueden sacar de las tablas: se cargaron a mano o con otra herramienta.

## 3. Causas raíz de los faltantes / errores (verificadas contra PDF)

### Mercado relevante (era la peor: fallaba en ~50 % de los casos con texto)

1. **Marcador de rol inline ignorado.** Muchas tablas ponen el rol dentro de la celda del
   nombre: `GAS LINK S.A. (Objeto)`. El original solo miraba el rótulo de sección, no ese
   marcador, así que no asociaba la actividad del objeto (= el mercado). *Ej.: CONC-1304.*

2. **La fila de encabezado "Empresa" apagaba la sección.** Aunque el rótulo de la tabla fuera
   "Objeto", la fila header `Empresa | Actividad` se interpretaba como etiqueta y, al no decir
   "objeto", **cortaba la recolección**. Como casi toda tabla tiene ese header, rompía mercados
   en la mayoría de los casos. *Ej.: CONC-1256 (tabla con rótulo 'objeto' y aun así vacía).*

3. **El objeto es un activo, no una empresa.** En compras de inmuebles/activos, la sección
   "Objeto" describe el bien (`Un inmueble identificado como una fracción de campo…`). El
   original esperaba empresa + actividad y descartaba la descripción. *Ej.: CONC-1878, CONC-1889.*

4. **Actividad del objeto en tabla no reconocida como "de empresas".** Cuando la empresa objeto
   no tenía sufijo societario (S.A., S.R.L.), un filtro la excluía. *Ej.: CONC-1521 (GE WATER…).*

5. **Glifos de viñeta (`` Wingdings, Unicode Private Use Area)** se colaban al texto
   (`Fabricación de neumáticos…`). *Ej.: CONC-1256.*

### Empresas involucradas (fallaba en ~28 % de los casos con texto)

6. **Empresas sin rol se descartaban.** Cuando la tabla es una sola lista
   `Empresas involucradas | Actividad` sin dividir en comprador/objeto, ninguna empresa tenía
   rol y el código las tiraba todas (emp = 0). *Ej.: CONC-1813 (tabla perfecta, 0 empresas
   extraídas).*

### Común a mercado y empresas

7. **Dictámenes viejos en prosa pura (sin ninguna tabla).** Formato ~pre-2015: empresas y
   mercado narrados en prosa, sin estructura tabular. El extractor (basado en tablas) no puede.
   Son el **7 % de los CONC (≈40 casos)**. *Ej.: CONC-863 (Unilever), CONC-1684.*

## 4. Qué corrige el extractor nuevo (`extraer_firmadas3.py`)

Reutiliza toda la lógica del original y **reemplaza solo Empresas y Mercado**, con 6 fixes:

- **FIX 1** — lee el marcador inline `(Objeto)` / `(Grupo Comprador)`.
- **FIX 2** — la fila header ("Empresa", "Actividad", "Razón social") ya no apaga la sección.
- **FIX 3** — las empresas sin rol se conservan (rol vacío) en vez de descartarse.
- **FIX 4** — el mercado sale de la sección "Objeto"; si no hay objeto identificable, se deja
  vacío (no se mezcla comprador + objeto).
- **FIX 5** — limpia los glifos Private Use Area.
- **FIX 6** — toma también las descripciones de activos del objeto ("Un inmueble…").

**Resultado (medido sobre los 544 CONC con PDF):**

- Mercado relevante: **50 % → 70 %** (+108 casos nuevos, **0 regresiones**).
- Empresas involucradas: **72 % → 76 %** (+20 casos, **0 regresiones**).
- Se verificó una por una que las 10 regresiones que aparecían en una versión intermedia
  quedaron eliminadas en la versión final.

## 5. Qué NO se puede extraer con el código (dejar para revisión manual)

- **Dictámenes en prosa pura (≈7 %, ~40 CONC).** Sin tablas no hay de dónde sacar mercado ni
  empresas de forma fiable. El extractor nuevo los deja vacíos y **genera un archivo
  `*_no_extraibles.txt`** con la lista para revisarlos a mano.
- **Tablas sólo en imagen (PDF escaneado sin capa de texto), ≈6 casos.** Requieren OCR
  (`extraer_firmadas_ocr.py`), no el extractor de texto.
- **~16 mercados que hoy están en V2 pero no salen de tablas.** Provienen de carga manual u
  otra fuente; conviene no pisarlos al re-correr.

## 6. Relaciones económicas (diagnóstico, no modificado)

Está en 49 %. De los vacíos con tablas: ~1/3 mencionan términos de relación
(horizontal/vertical/conglomerado) que el patrón actual no capta, y ~2/3 **no tienen ninguna
frase de relación** en el texto. Mejorar los patrones recuperaría parte, **pero con riesgo de
falsos positivos por negaciones** ("no existen relaciones verticales" → clasificaría "Vertical"
por error). Recomendación: ampliar patrones **con manejo explícito de negaciones**; es un cambio
de precisión delicado y por eso se dejó fuera de esta versión.

## 7. Grupo/Empresa

Ya funciona bien (94 %). Sale de la carátula del expediente. Los pocos vacíos son justamente los
casos de prosa pura del §5.

## 8. Cómo usar el extractor nuevo

```
cd C:\Users\Admin\Documents\GitHub\buscadorANC
python extraer_firmadas3.py pdf firmadas3.xlsx
```

Genera `firmadas3.xlsx` (mismas columnas que el original) y, si hay casos sin tablas,
`firmadas3_no_extraibles.txt`. No toca `firm.xlsx`.

## 9. Recomendación de próximos pasos

1. Correr `extraer_firmadas3.py` sobre todos los CONC y volcar Empresas y Mercado a las V2
   (revisando antes de pisar los ~16 mercados cargados a mano).
2. Revisar a mano la lista de `*_no_extraibles.txt` (prosa pura) y los escaneados (OCR).
3. Decidir si vale la pena mejorar Relaciones económicas con manejo de negaciones (§6).
