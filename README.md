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

`texto_extraido/` queda ignorada en esta rama.

## Fuente y reutilización

Son documentos públicos de la Comisión Europea (decisiones, compromisos, comunicados, avisos,
Merger Briefs). La URL de origen de cada uno está en `reporte.csv`. Su reutilización está
autorizada con mención de la fuente (Decisión 2011/833/UE de la Comisión): "Fuente: Comisión
Europea".
