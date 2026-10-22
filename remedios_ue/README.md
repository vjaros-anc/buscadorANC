# Biblioteca de remedios UE

Precedentes de la Comisión Europea para la ANC: concentraciones que la Comisión
autorizó **con condiciones**, qué problema de competencia detectó en cada una y
qué remedio aceptó.

Esta carpeta está separada del buscador de la CNDC (raíz del repo) y no lo toca.

| Etapa | Qué produce | Estado |
|---|---|---|
| 1. Universo de casos | `casos.csv`, `conciliacion.md` | hecha, **a validar** |
| 2. Inventario documental | `documentos.csv` | pendiente |
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
| `eventos_posteriores` | Aprobación de comprador, implementación o revisión de remedios, modificaciones, multas, causas judiciales; con fecha | JSON |
| `url_caso` | Ficha oficial del caso | Armada con el número |
| `url_comunicado` | Comunicado de la autorización | Presscorner |
| `fuentes_identificacion` | En qué listas apareció: `A;C` o `A` | Cruce |
| `notas` | Antecedentes del procedimiento (remisiones, notificaciones retiradas) + notas manuales | JSON + manual |

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
