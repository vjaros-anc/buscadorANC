# Contratos de datos del área interna

Cada herramienta lee un JSON versionado (`schema_version`) y no depende de dónde sale: hoy un Excel o el artefacto de
Claude, mañana una base. Hay dos contratos:

1. [Monitor de concentraciones — `operaciones` v1](#1-monitor-de-concentraciones--operaciones-v1): lo lee `noticias/index.html`.
2. [Seguimiento de expedientes — `seguimiento` v1](#2-seguimiento-de-expedientes--seguimiento-v1): lo lee `seguimiento/index.html`.

En este repo público solo hay **fixtures de ejemplo** (`data/*.sample.json`, todo marcado como ejemplo). `verificar_sitio.py` falla
si aparece un `monitor*.json` o un `seguimiento*.json` con `origen` distinto de `"ejemplo"`.

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


## 2. Seguimiento de expedientes — `seguimiento` v1

Es lo que lee `seguimiento/index.html`. La idea de fondo es la misma que en el monitor: la página no sabe de dónde salen los datos.
Más adelante un script local (`generar_seguimiento.py`, etapa 3) lo escribirá a partir de `Res_firmadas.xlsm`; hoy solo existe
`data/seguimiento.sample.json`, con expedientes ficticios.

> **Privacidad.** El seguimiento real son expedientes **en trámite**, con analista y estado. **No va nunca a este repo público**:
> vive en el repo privado del área interna, y solo después de la autorización institucional.

### Archivo

```json
{
  "schema_version": 1,
  "origen": "ejemplo",          // "ejemplo" en el fixture; la demo se niega a mostrar cualquier otro valor
  "aviso": "DATOS DE EJEMPLO: …",
  "corte": "AAAA-MM-DD",        // fecha a la que están medidos los datos (no es «hoy»: los números se pueden reproducir)
  "estados": ["Ingreso", "Análisis", …],   // orden del trámite: ordena el gráfico de estados
  "expedientes": [ … ]
}
```

### `expedientes[]`

| Campo | Tipo | Obligatorio | Valores / formato |
|---|---|---|---|
| `id` | texto | sí | identificador; en datos reales, `tipo-número` normalizado (`CONC-2005`) |
| `operacion` | texto | sí | nombre de la operación (en datos reales, decidir si corresponde mostrarlo) |
| `analista` | texto | no | si falta, «Sin asignar». Hoy no se sabe qué columna del Excel lo trae |
| `tipo` | texto | sí | Ordinario · PROSUM |
| `estado` | texto | sí | uno de `estados`; si no está en la lista, la página lo agrega al final |
| `ingreso` | texto | sí | `AAAA-MM-DD`; si no es una fecha válida el expediente se descarta |
| `revision` | texto | no | `AAAA-MM-DD`: próxima revisión, un **hito de gestión, no un vencimiento legal** |

### Qué calcula la página

- **Antigüedad** = días corridos entre `ingreso` y `corte`. No descuenta suspensiones ni es el plazo legal.
- **Cohortes**: hasta 90 · 91 a 180 · 181 a 365 · más de 365 días.
- **Revisión en 15 días** = `0 ≤ revision − corte ≤ 15`; **vencida** = `revision < corte` (solo dice que la fecha es anterior al corte).
- Filtros por analista, estado y procedimiento; todo se recalcula en el navegador, y el CSV baja la selección.

### Qué falta para la versión real

Los encabezados reales de `Res_firmadas.xlsm`: qué columna trae el analista, cuáles son los valores de `ESTADO` que significan
«en trámite», y desde cuándo corre el plazo legal (el ingreso no siempre es el inicio: hay suspensiones y, desde el 17/11/2026,
rige el control previo). Con eso se cierra el contrato; ver «Diseño del seguimiento» en `SITIO.md`.

### CSV (botón **Descargar CSV**)

Separador `;`, UTF-8 con BOM. Columnas: `Expediente, Operación, Analista, Procedimiento, Estado, Ingreso, Antigüedad (días),
Próxima revisión, Días hasta la revisión, Corte`. Los textos que empiezan con `= + - @` se prefijan con `'`.
