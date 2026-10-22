# Corpus de la biblioteca de remedios UE (PDF)

Esta rama contiene **solo los documentos descargados** para la biblioteca de remedios de la
ANC: 276 PDF (~193 MB) de los 47 casos de concentraciones que la Comisión Europea autorizó
con condiciones entre el 22/10/2021 y el 22/10/2026. Es independiente: no comparte historia
con `main` y **no se fusiona**, para no agregar peso al sitio del buscador (GitHub Pages).

El código, el inventario (`documentos.csv`) y la documentación están en `remedios_ue/` de
la rama de trabajo, `claude/gallant-bardeen-y00h2a`.

## Contenido

| Archivo | Qué es |
|---|---|
| `archivos/M_xxxxx/` | Los PDF de cada caso: `M.10341_DEC_01_<hash>.pdf` = decisión, etc. |
| `archivos/compartidos/` | PDF que sirven a varios casos (p. ej. un Merger Brief) |
| `reporte.csv` | Una fila por documento: `documento_id` (= `doc_id` de `documentos.csv`), estado, archivo, SHA-256, `coincide_inventario`, `paginas_compromisos`, URL de origen |
| `resumen.json` | Conteos de la corrida |
| `estado.json` | Índice que usa el descargador para reanudar |
| `historial.jsonl` | Historial de solicitudes |
| `texto_extraido/` | Texto por página de cada PDF, con OCR (ver abajo) |
| `datos_crudos/` | Insumos de las etapas 1 y 2 (ver abajo) |

### `datos_crudos/`: para reproducir el inventario exacto

| Archivo | Qué es |
|---|---|
| `case-data-M.json` (42 MB) | Copia del 22/10/2026 del dataset de concentraciones de DG COMP. Se actualiza a diario: `casos.csv` y `documentos.csv` salen de **esta** copia (sha256 `d135029e…57b459`, también en `case-data-M.meta.json`) |
| `comunicados.json` | Lista C de la etapa 1: comunicados "subject to conditions" de Presscorner |
| `verificaciones.json`, `analisis_pdf.json` | Cachés de `relevar_documentos.py`: verificación de enlaces y análisis de PDF (páginas, SHA-256, inicio del anexo de compromisos) |

Para usarlos, copiarlos a `remedios_ue/datos_crudos/` de la rama de trabajo y correr
`inventario_casos.py --sin-descarga` y `relevar_documentos.py`: dan los mismos CSV sin
consultar la red.

Lo generó `descargar_remedios.py` 1.1.0 (`--todos`) el 22/10/2026:
- 276 PDF descargados y verificados;
- las 44 decisiones publicadas coinciden con el SHA-256 de `documentos.csv`;
- 3 comunicados no tienen versión PDF en Presscorner (`sin_version_pdf`).

## Cómo usarla

Bajar solo esta rama a una carpeta `descargas_anc` (la que esperan los scripts):

```bash
git clone --branch corpus-remedios-ue --single-branch https://github.com/vjaros-anc/buscadorANC.git descargas_anc
```

Desde la raíz del repo de trabajo:

```bash
python remedios_ue/descargar_remedios.py --todos --destino descargas_anc   # reconoce todo como ya_descargado
python remedios_ue/extraer_texto.py --entrada descargas_anc                # texto por página
```

## Texto extraído (`texto_extraido/`)

Salida de `extraer_texto.py` 1.2.0 con `--ocr` (PyMuPDF 2.0 y Tesseract 5.3.4 con `--psm 3`
y binarización de Sauvola, 22/10/2026), para no tener que repetir la extracción ni instalar
Tesseract. La versión 1.2.0 reemplazó a la 1.1.0, cuyo OCR no leía las celdas de las tablas
de cuotas:

| Archivo | Qué es |
|---|---|
| `documentos/<sha256>.json` | Texto por página de cada PDF, con `pagina_pdf`, `origen_texto` (`pdf` u `ocr`), alertas y las filas del reporte que apuntan a ese PDF |
| `documentos/<sha256>.txt` | El mismo texto con separadores de página; las páginas OCR dicen "texto OCR: verificar contra el PDF" |
| `documentos.csv` | Una fila por documento: `documento_id`, caso, estado de extracción y rutas al JSON y al TXT |
| `paginas.csv` | Una fila por página (9.100), con su origen y alertas |
| `resumen.json`, `estado.json` | Conteos y caché de la corrida |

505 páginas de decisiones son imagen y se leyeron por OCR, con sus tablas. Esas páginas
tienen errores de reconocimiento: **una cifra tomada de una página `ocr` se verifica contra
la imagen del PDF**. La
validación completa está en `remedios_ue/EXTRACCION_TEXTO.md` de la rama de trabajo.

## Fuente y reutilización

Son documentos públicos de la Comisión Europea (decisiones, compromisos, comunicados, avisos,
Merger Briefs). La URL de origen de cada uno está en `reporte.csv`. Su reutilización está
autorizada con mención de la fuente (Decisión 2011/833/UE de la Comisión): "Fuente: Comisión
Europea".
