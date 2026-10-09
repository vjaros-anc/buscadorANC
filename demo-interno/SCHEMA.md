# Contratos de datos del área interna

Cada herramienta lee un JSON versionado (`schema_version`) y no depende de dónde sale: hoy un Excel o el artefacto de
Claude, mañana una base. Hay dos contratos:

1. [Monitor de concentraciones — `operaciones` v1](#1-monitor-de-concentraciones--operaciones-v1): lo lee `noticias/index.html`.
2. [Seguimiento de expedientes — `seguimiento` v1](#2-seguimiento-de-expedientes--seguimiento-v1): lo lee `seguimiento/index.html`.

Hay **fixtures de ejemplo** (`data/*.sample.json`, todo marcado como ejemplo). `verificar_sitio.py` falla si aparece un `monitor*.json`
con `origen` distinto de `"ejemplo"`. El **seguimiento real** (`seguimiento.json`, `origen: "interno"`) es la excepción: puede estar en la
rama del área interna, que se publica detrás de Cloudflare Access, y es **error en `main`** y en cualquier `dist/` de `main`.

## 1. Monitor de concentraciones — `operaciones` v1

Es lo que lee `noticias/index.html` y lo que produce `monitor_merge.py`. La idea es que **bot, dashboard y
exportaciones usen una sola fuente**: un `monitor.json` versionado. Hoy esa fuente se genera a partir del
artefacto de Claude; más adelante puede escribirla directamente la Rutina, o pasar a una base (D1), sin
cambiar la página.

> **Privacidad.** El `monitor.json` real contiene el análisis interno del área (qué operaciones conviene
> verificar y el resultado). **No va nunca a este repo público.** Vive en el repo privado del área interna.
> En este repo solo está `data/monitor.sample.json`, con datos ficticios.

### Archivo

```json
{
  "schema_version": 1,
  "origen": "artefacto",        // "ejemplo" en el fixture; la página muestra el cartel de ejemplo
  "exportado_el": "AAAA-MM-DD", // la página avisa si tiene más de 20 días
  "operaciones": [ … ],
  "informes": [ … ],
  "parametros": { … }
}
```

### `operaciones[]`

| Campo | Tipo | Obligatorio | Valores / formato |
|---|---|---|---|
| `id` | texto | sí | slug en minúsculas y guiones; es el `doc_id` del artefacto |
| `fecha` | texto | sí | `AAAA-MM-DD` (anuncio, cierre o ejecución) |
| `partes` | texto | sí | libre |
| `tipo` | texto | sí | Fusión · Adquisición · Joint venture · Cambio de control · Otra |
| `estado` | texto | sí | `confirmada` · `rumor` |
| `sector`, `alcance`, `vinculoAR` | texto | no | libres |
| `etapa` | texto | no | Anunciada · Cerrada · Ejecutada · En revisión regulatoria |
| `fuente`, `url` | texto | no | fuente principal; la URL solo se enlaza si es `http(s)` |
| `links` | lista de `{fuente, url}` | no | 2 a 4 fuentes; se descartan las que no sean `http(s)` |
| `umbralArt9` | texto | no | Supera · Supera (probable) · No supera · No supera (probable) · A confirmar |
| `excepcion11e` | texto | no | Aplica · Aplica (probable) · No aplica · No aplica (probable) · A confirmar |
| `analisisUmbral` | texto | no | 2 a 4 oraciones: cifras usadas y qué falta confirmar |
| `relevanteANC` | booleano | sí | `true` = para verificar ante la ANC |
| `motivoANC` | texto | no | vacío si no aplica |
| `informe` | texto | no | `id` del informe que la detectó |
| `detectadaEl` | texto | no | `AAAA-MM-DD` |
| `verificacion` | texto | si `relevanteANC` | `pendiente` · `notificada` · `no_notificada` · `descartada`. **La edita el analista, nunca el bot.** |
| `verificadoEl` | texto | no | `AAAA-MM-DD` |
| `prioridad` | texto | no | Alta · Media/Alta · Media · Baja |
| `seguimiento` | texto | no | Nueva · Seguimiento · Nueva (histórica) |

`prioridad` y `seguimiento` aparecen en el artefacto vivo pero no en el prompt de la Rutina: son opcionales.

### `informes[]`

`id` (= `fecha`), `fecha`, `desde`, `hasta`, `total` (operaciones nuevas), `relevantes` (cuántas con `relevanteANC`),
`resumen` (3 a 5 oraciones).

### `parametros`

`anio`, `unidadMovil`, `art9`, `art11e12m`, `art11e36m` (umbrales en pesos), `tipoCambio`, `tipoCambioFecha`,
`norma`, `normaUrl`, `nota`. Los umbrales se recalculan cada enero con la resolución que actualiza la unidad móvil.

### Reglas de contenido

- "No encontrada en el registro" **nunca** equivale a "no notificada": el valor `no_notificada` solo lo carga una persona.
- Rumor y operación confirmada se distinguen siempre (`estado`).
- El análisis de umbrales es una estimación con datos públicos; verificar contra la fuente.

### CSV (`operaciones.csv` y botón **Descargar CSV**)

Separador `;`, UTF-8 con BOM (se abre bien en Excel con configuración regional es-AR). Columnas:
`fecha, partes, tipo, sector, alcance, vinculoAR, estado, etapa, prioridad, relevanteANC, umbralArt9, excepcion11e,
analisisUmbral, motivoANC, verificacion, verificadoEl, fuente, links`. Los textos que empiezan con `= + - @` se
prefijan con `'` para que Excel no los ejecute como fórmula.

### Cómo se genera `monitor.json` (sincronización a demanda)

1. En una sesión de Claude con acceso al artefacto, exportar con `ArtifactData` (`action: "list"`) las colecciones
   `operaciones`, `informes` y `parametros`, con `out_dir` en una carpeta de trabajo **fuera del repo**.
2. `python -B demo-interno/monitor_merge.py CARPETA --salida RUTA_DEL_REPO_PRIVADO/data`
   escribe `monitor.json` y `operaciones.csv` y avisa de campos faltantes o valores desconocidos.
3. Commit en el repo privado; Cloudflare Pages despliega el área interna.

### Hacia una fuente única

| Hoy | Después |
|---|---|
| La Rutina escribe en la base del artefacto; un export manual genera `monitor.json` | La Rutina escribe `monitor.json` en el repo privado |
| La verificación se registra en el artefacto | La verificación se registra en el sitio (Workers + D1, solo si hace falta escribir desde el sitio) |
| El artefacto es el sistema de registro | El artefacto pasa a ser opcional |


## 2. Seguimiento de expedientes — `seguimiento` v2

Es lo que lee `seguimiento/index.html` y lo que escribe `generar_seguimiento.py` a partir de la hoja `evol_conc` de
`Res_firmadas.xlsm`. La página pide primero `data/seguimiento.json` (real) y, si no existe (404), muestra `data/seguimiento.sample.json`
(ejemplo). Rechaza cualquier otra `schema_version`.

> **Privacidad.** El seguimiento real son concentraciones **en trámite**, con carátula y nombres del personal. Solo se publica detrás de
> Cloudflare Access (ver «Área interna» en `SITIO.md`). Está en la rama del área interna; **no se mergea a `main`**: ahí
> `verificar_sitio.py` lo rechaza.

### Archivo

```json
{
  "schema_version": 2,
  "origen": "interno",            // "ejemplo" en el fixture
  "aviso": "USO INTERNO: …",      // el fixture empieza con "DATOS DE EJEMPLO"
  "fuente": "Res_firmadas.xlsm › evol_conc",
  "corte": "AAAA-MM-DD",          // fecha a la que se mide la antigüedad (por defecto, el día de la generación)
  "excel_corte": "AAAA-MM-DD",    // «Fecha de corte» que el Excel tenía guardada (General!C5); la página avisa si es >7 días anterior al corte
  "estados": ["Pendiente de presentación", …, "TDC"],   // orden del trámite: ordena el gráfico de estados
  "avisos": ["…"],                // problemas de carga del Excel que conviene revisar (se muestran en «Notas»)
  "expedientes": [ … ]
}
```

### `expedientes[]`

| Campo | Tipo | Obligatorio | Origen en `evol_conc` / formato |
|---|---|---|---|
| `id` | texto | sí | `Clave` con guion: `CONC-2005` |
| `operacion` | texto | sí | `Caratula` **resumida**: sin comillas, sin «S/ NOTIFICACIÓN ART. 9 DE LA LEY 27.442» (ni el art. 8 de la ley 25.156), sin «(CONC nnnn)»; se conserva un paréntesis que aclare una parte, y se corta en 120 caracteres |
| `abogados` | lista de texto | sí (puede ser `[]`) | `Abogado_1`, `Abogado_2`; apellido normalizado (sin duplicados, tildes unificadas, tipeos corregidos con `ALIAS_APELLIDOS`) |
| `economistas` | lista de texto | sí (puede ser `[]`) | `Economista_1`, `Economista_2`, igual que los abogados |
| `tipo` | texto | sí | `ES FT`: SI → `PROSUM`, NO → `Ordinario`; vacío → `Sin dato` |
| `estado` | texto | sí | `ESTADO`; uno de `estados` (si no está en la lista, la página lo agrega al final) |
| `ingreso` | texto | sí | `Fecha_Ingreso`, `AAAA-MM-DD`; si no es una fecha válida el expediente se descarta (y `avisos` lo dice) |

### Qué es «en trámite»

La misma definición del tablero `General` del Excel (celda `C26`, «TOTAL ACTIVAS»): `ESTADO` en **Pendiente de presentación, Observado,
En análisis, En instrucción, Suspendida, IT circulando, Para resolución o TDC**. Las demás (Firmada, Subordinada en cumplimiento, Apelada,
Acumulado, Archivo, Desistida) son «cerradas». El script compara su conteo con el que el Excel guardó y lo informa en `avisos` si difieren.
Las filas sin `ESTADO` no se cuentan (se informan). Un expediente en trámite con `Fecha_firma` cargada se cuenta, como hace el Excel, y se informa.

### Qué calcula la página

- **Antigüedad** = días corridos entre `ingreso` y `corte`. No descuenta suspensiones ni es el plazo legal.
- **Cohortes**: hasta 90 · 91 a 180 · 181 a 365 · más de 365 días.
- **Carga por abogado / economista**: un expediente suma a cada persona asignada (por eso las barras suman más que el total); sin nadie, «Sin asignar».
- Filtros por abogado, economista, estado y procedimiento; todo se recalcula en el navegador, y el CSV baja la selección.

### Lo que el Excel no tiene (y por eso la página no lo muestra)

- **Próxima revisión / vencimientos**: no hay una columna con esa fecha (`Revisión` trae notas de auditoría y está vacía en las activas). La
  v1 de la demo la mostraba con datos de ejemplo; se sacó. Los vencimientos aparecen como texto libre en `Dictamen a revisar (SI/NO)` y
  `Observaciones`; no se publican.
- **Plazo legal**: ni el inicio del plazo ni las suspensiones están estructurados (y desde el 17/11/2026 rige el control previo). La
  antigüedad es tiempo corrido.

### Cómo se genera

```
python -B generar_seguimiento.py                      # lee Res_firmadas.xlsm (junto al script) → demo-interno/data/seguimiento.json
python -B generar_seguimiento.py --corte 2026-10-09   # medir la antigüedad a otra fecha
```

Abre el Excel en solo lectura (sin ejecutar macros) y escribe un expediente por línea. Hay que abrir y guardar el Excel antes de generar para
que sus fórmulas (`Clave`, `MESES`, `General`) estén calculadas; si `excel_corte` es anterior al corte, la página lo avisa. Después: commit en la
rama del área interna; Cloudflare Pages despliega.

### CSV (botón **Descargar CSV**)

Separador `;`, UTF-8 con BOM. Columnas: `Expediente, Operación, Abogados, Economistas, Procedimiento, Estado, Ingreso, Antigüedad (días), Corte`.
Varios abogados o economistas se separan con ` / `. Los textos que empiezan con `= + - @` se prefijan con `'`.
