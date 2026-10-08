# Contrato de datos del monitor — `operaciones` v1

Es lo que lee `noticias/index.html` y lo que produce `monitor_merge.py`. La idea es que **bot, dashboard y
exportaciones usen una sola fuente**: un `monitor.json` versionado. Hoy esa fuente se genera a partir del
artefacto de Claude; más adelante puede escribirla directamente la Rutina, o pasar a una base (D1), sin
cambiar la página.

> **Privacidad.** El `monitor.json` real contiene el análisis interno del área (qué operaciones conviene
> verificar y el resultado). **No va nunca a este repo público.** Vive en el repo privado del área interna.
> En este repo solo está `data/monitor.sample.json`, con datos ficticios.

## Archivo

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

## `operaciones[]`

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

## `informes[]`

`id` (= `fecha`), `fecha`, `desde`, `hasta`, `total` (operaciones nuevas), `relevantes` (cuántas con `relevanteANC`),
`resumen` (3 a 5 oraciones).

## `parametros`

`anio`, `unidadMovil`, `art9`, `art11e12m`, `art11e36m` (umbrales en pesos), `tipoCambio`, `tipoCambioFecha`,
`norma`, `normaUrl`, `nota`. Los umbrales se recalculan cada enero con la resolución que actualiza la unidad móvil.

## Reglas de contenido

- "No encontrada en el registro" **nunca** equivale a "no notificada": el valor `no_notificada` solo lo carga una persona.
- Rumor y operación confirmada se distinguen siempre (`estado`).
- El análisis de umbrales es una estimación con datos públicos; verificar contra la fuente.

## CSV (`operaciones.csv` y botón **Descargar CSV**)

Separador `;`, UTF-8 con BOM (se abre bien en Excel con configuración regional es-AR). Columnas:
`fecha, partes, tipo, sector, alcance, vinculoAR, estado, etapa, prioridad, relevanteANC, umbralArt9, excepcion11e,
analisisUmbral, motivoANC, verificacion, verificadoEl, fuente, links`. Los textos que empiezan con `= + - @` se
prefijan con `'` para que Excel no los ejecute como fórmula.

## Cómo se genera `monitor.json` (sincronización a demanda)

1. En una sesión de Claude con acceso al artefacto, exportar con `ArtifactData` (`action: "list"`) las colecciones
   `operaciones`, `informes` y `parametros`, con `out_dir` en una carpeta de trabajo **fuera del repo**.
2. `python -B demo-interno/monitor_merge.py CARPETA --salida RUTA_DEL_REPO_PRIVADO/data`
   escribe `monitor.json` y `operaciones.csv` y avisa de campos faltantes o valores desconocidos.
3. Commit en el repo privado; Cloudflare Pages despliega el área interna.

## Hacia una fuente única

| Hoy | Después |
|---|---|
| La Rutina escribe en la base del artefacto; un export manual genera `monitor.json` | La Rutina escribe `monitor.json` en el repo privado |
| La verificación se registra en el artefacto | La verificación se registra en el sitio (Workers + D1, solo si hace falta escribir desde el sitio) |
| El artefacto es el sistema de registro | El artefacto pasa a ser opcional |
