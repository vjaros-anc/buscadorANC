# lectura_opi — extracción de causas y preguntas de las OPI

Pipeline de 3 pasos que va de los PDF de Opinión Consultiva a un Excel con
la **pregunta de las partes**, la **respuesta de la CNDC** y la **causa de la
decisión** (ratio decidendi).

## Instalación (una vez)

```bash
pip install -r requirements.txt
```

Para el paso 2 hace falta la clave de API en el entorno:

```bash
setx ANTHROPIC_API_KEY "sk-ant-..."
```

(Cerrá y reabrí la terminal después de `setx`. Para la sesión actual en
PowerShell: `$env:ANTHROPIC_API_KEY="sk-ant-..."`)

---

## Paso 1 — Segmentar (determinístico, sin costo)

Lee los `OPI-*.pdf` de la carpeta padre, saca el texto, limpia el ruido GEDO
(membretes, `IF-2024-…`, paginado, firmas digitales) y corta el dictamen en
5 secciones canónicas: `hechos`, `partes`, `procedimiento`, `analisis`,
`conclusion`.

```bash
python 01_segmentar.py ..
```

Salida: `opi_segmentado.jsonl` (una línea por PDF).
Verificado sobre las 96 OPI actuales: **96/96 con conclusión detectada.**

Si algún día hay OPI en otra carpeta:
`python 01_segmentar.py C:\ruta\a\pdfs -o otro.jsonl`

## Paso 2 — Extraer con LLM (tiene costo)

```bash
python 02_extraer.py --limite 15      # primero una muestra de calibración
python 02_extraer.py                  # después, todas
```

Salida: `opi_extraido.jsonl`. Es **reanudable**: si lo cortás y lo volvés a
correr, saltea las OPI ya hechas. Para rehacer todo, `--rehacer`.

Opciones útiles:

| Flag | Para qué |
|---|---|
| `--limite 15` | procesar solo las primeras N |
| `--solo 350,312,373` | OPI puntuales, por número |
| `--hilos 6` | más paralelismo (subir con cuidado por rate limits) |
| `--rehacer` | ignorar lo ya extraído y empezar de cero |

Al terminar imprime tokens consumidos y costo estimado. Referencia real:
las 96 OPI son ~750k tokens de texto total, y el script manda solo las
secciones relevantes recortadas.

## Paso 3 — Excel

```bash
python 03_excel.py
```

Salida: `opi_causas.xlsx`, con 4 hojas:

- **CAUSAS** — una fila por OPI. Es la hoja de trabajo para la validación.
  Las filas con alertas quedan pintadas de amarillo. Las últimas 3 columnas
  (`VAL_ok`, `VAL_causa_corregida`, `VAL_notas`) están vacías a propósito,
  para que las completes a mano.
- **RESUMEN** — conteos por sentido de la respuesta, tipo de pregunta y
  criterio de la causa. Sirve para ver si la taxonomía está bien calibrada:
  si `otro` se lleva más del 15-20%, hay que agregar categorías al esquema.
- **NORMAS** — un renglón por artículo citado, con la Referencia GEDO al lado
  para cruzar a ojo.
- **CONTROLES** — el tablero de qué revisar primero.

---

## Protocolo de validación sugerido

El script ya corre solo estos controles automáticos y marca la fila:

| Control | Qué detecta |
|---|---|
| `ratio parece ser el resultado, no la causa` | el error más común: devuelve "no está sujeta a notificación" en vez del porqué |
| `CONTRADICE Referencia` | el sentido extraído choca con lo que dice el campo `Referencia:` de la Hoja de Firmas (etiqueta independiente, control cruzado gratis) |
| `criterio = otro` | la taxonomía no cubre ese caso |
| `sin parrafos citados` | no hay trazabilidad al texto |
| `confianza baja` / `voto particular` | el modelo se auto-marcó |

Sobre eso, el orden de revisión humana que recomiendo:

1. Todas las filas amarillas (empezando por `CONTRADICE Referencia`).
2. Una muestra aleatoria de 20 filas limpias, para estimar la tasa de error
   real del resto.
3. Chequeo de coherencia: en la hoja RESUMEN, ver si dos criterios distintos
   están describiendo lo mismo con nombres diferentes.

Si en el paso 1 la tasa de error es alta para un tipo de caso concreto,
conviene ajustar `esquema_opi.json` (agregar categorías a `criterio`) y volver
a correr solo esas OPI con `--solo`.

---

## Advertencias sobre el corpus

- **Un PDF no siempre es un solo dictamen.** Varios traen concatenados el
  dictamen original, uno complementario y votos particulares (OPI 175, 298,
  305, 306, 310). El campo `piezas` del paso 1 los cuenta, y el prompt del
  paso 2 le pide al modelo extraer el voto de la **mayoría** y marcar
  `requiere_revision_humana`. Esas filas hay que mirarlas sí o sí.
- **Dos regímenes legales.** El corpus cruza Ley 25.156 (arts. 8 y 10) y
  Ley 27.442 (arts. 9 y 11). Antes de agregar o contar causas, normalizá el
  artículo o vas a contar la misma causa dos veces. La columna `ley` está
  para eso.

## Archivos

| Archivo | Qué es |
|---|---|
| `01_segmentar.py` | extracción de texto y segmentación |
| `02_extraer.py` | extracción semántica con LLM |
| `03_excel.py` | consolidación a Excel |
| `esquema_opi.json` | esquema de salida y taxonomías cerradas |
| `requirements.txt` | dependencias |
