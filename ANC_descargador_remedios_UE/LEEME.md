# Descargador de documentos — Biblioteca de remedios UE / ANC

Versión 1.0.0. Inventario de referencia: 22 de octubre de 2026.

## Inicio rápido

1. Descargá y descomprimí el ZIP. Abrí una terminal en la carpeta extraída.
2. Necesitás Python 3.10 o posterior y acceso a Internet. No hay que instalar librerías ni conectar Google Drive.
3. Revisá el plan del piloto:

```bash
python descargar_remedios.py --piloto --plan
```

4. Descargá el piloto:

```bash
python descargar_remedios.py --piloto
```

5. Cuando hayas revisado el reporte, descargá los demás casos:

```bash
python descargar_remedios.py --todos
```

En macOS/Linux podés necesitar `python3` en lugar de `python`. En Windows, `py -3` también sirve. Para comprobar la instalación: `python --version`.

El modo predeterminado es el piloto. `--todos` amplía a los 47 casos; no agrega documentos o enlaces que falten en el inventario.

## Qué incluye el paquete

- `descargar_remedios.py`: programa principal, sin dependencias externas.
- `manifiesto.csv`: 321 entradas documentales del inventario, clasificadas y con sus fuentes originales.
- `manifiesto_piloto.csv`: las 35 entradas de los cinco casos del piloto; se incluye como referencia. El programa usa `manifiesto.csv` y filtra los casos con `--piloto`.
- `inventario_documental.csv`: copia de la pestaña Documentos utilizada para preparar el manifiesto.
- `casos.csv`: los 47 casos y sus datos de identificación.
- `referencias_y_faltantes.csv`: páginas, fuentes complementarias, índices del Diario Oficial y documentos sin enlace individual.
- `pendientes_fuente.csv`: los pendientes documentales del relevamiento previo. No es el reporte de descarga.
- `preparar_manifiesto.py`: permite regenerar el manifiesto desde una nueva exportación CSV de Documentos.
- `METADATOS.json` y `FUENTES.md`: procedencia, alcance y controles del paquete.
- `tests/`: 23 pruebas funcionales, sin consultas a sitios públicos.
- `SHA256SUMS.txt`: controles de integridad de los archivos distribuidos.

## Selección del piloto

| Caso | Expediente | Qué permite probar |
|---|---|---|
| Prince/Ferro | M.10341 | Decisión y compromisos en un mismo PDF; comprador |
| Meta/Kustomer | M.10262 | Decisión de fase II y dispensa posterior |
| Microsoft/Activision Blizzard | M.10646 | Decisión extensa y documentos de procedimiento |
| Orange/MásMóvil | M.10896 | PDF grande y compromisos integrados |
| Safran/Collins | M.11253 | Decisión con compromisos integrados |

Con el manifiesto incluido, el piloto solicita **15 URL únicas de PDF**, que corresponden a 18 entradas documentales. La selección completa solicita **119 URL únicas de PDF**, que corresponden a 145 entradas. Un mismo PDF puede contener decisión y compromisos: se conserva una sola descarga y varias filas en el reporte.

Estas cifras son solicitudes previstas, no descargas ya realizadas ni garantía de accesibilidad. El paquete contiene código y metadatos; no trae los PDF europeos descargados.

## Qué descarga por defecto

Incluye los grupos `nucleo`, `actos_posteriores`, `procedimiento` y `comunicados`, cuando tienen URL de PDF localizada. Excluye por defecto los grupos `referencia` y `secundaria` y las páginas HTML.

Las entradas sin URL quedan como `sin_url`. Los enlaces a índices o volúmenes completos del Diario Oficial quedan como `requiere_url_individual`: el programa no los trata como si fueran el aviso o la decisión individual. Las páginas HTML se registran como `html_no_solicitado`.

Para intentar guardar también páginas HTML individuales:

```bash
python descargar_remedios.py --todos --incluir-html
```

Para incluir además las fuentes complementarias y secundarias:

```bash
python descargar_remedios.py --todos --grupos todos --incluir-html
```

Las fuentes secundarias conservan su clasificación; no sustituyen la decisión original. El script no inventa URLs PDF, no ejecuta JavaScript ni resuelve CAPTCHA. Los bloqueos se registran para revisión manual.

## Dónde quedan los archivos

Por defecto crea `descargas_anc` en el directorio desde el que ejecutaste el comando:

```text
descargas_anc/
  archivos/
    M_10341/             PDF de ese caso
    M_10262/
    compartidos/        URL que corresponde a varios casos
  reporte.csv           Una fila por entrada documental seleccionada
  resumen.json          Conteos de la última ejecución y controles
  estado.json           Índice de archivos completos para reanudar
  historial.jsonl       Historial acumulado de solicitudes y resultados
  _parciales/           Temporales de la descarga en curso
  _corruptos/           Copias alteradas sustituidas durante una recuperación
```

Si dos URL producen exactamente los mismos bytes, el script reutiliza el archivo ya comprobado por SHA-256. El reporte conserva las dos URL y la relación con todos los casos y documentos correspondientes. Por eso el archivo físico puede estar en una carpeta compartida o en la del primer caso descargado.

Para elegir otro destino:

```bash
python descargar_remedios.py --piloto --destino "C:\ANC\remedios_ue"
```

En macOS/Linux, por ejemplo:

```bash
python3 descargar_remedios.py --piloto --destino "./mis_documentos_ue"
```

## Reanudación y versiones

Volvé a ejecutar el mismo comando, usando la misma carpeta de destino. Los archivos completos se verifican por tamaño, SHA-256 y formato antes de marcarlos `ya_descargado`. Los fallos se intentan nuevamente. La reanudación es **por archivo**: una transferencia interrumpida se comienza de nuevo; no se retoman rangos parciales de bytes.

Para pasar del piloto a todos los casos, usá el mismo destino. Se reutilizarán los archivos ya descargados.

Con `--forzar` se vuelven a consultar las URL. Si cambió el contenido, se conserva una versión nueva con otro hash; la anterior permanece y el historial permite rastrearla. Un archivo local alterado se vuelve a descargar; la copia incompatible se conserva en `_corruptos`.

Podés detener el proceso con Ctrl+C. Se conserva lo terminado y se actualiza el reporte. No ejecutes dos procesos en la misma carpeta. Si un cierre abrupto deja `.descarga.lock`, comprobá que el proceso anterior terminó antes de eliminar ese archivo de bloqueo.

## Cómo leer el reporte

Abrí `reporte.csv` como CSV UTF-8 con delimitador coma. Tiene identificador documental, caso, título, grupo, idioma, URL de origen, estado, ruta del archivo, SHA-256, bytes, MIME, código HTTP, URL final, intentos, fecha UTC y detalle.

| Estado | Significado |
|---|---|
| `descargado` | Archivo recibido y validado técnicamente |
| `ya_descargado` | Archivo anterior comprobado; no se volvió a solicitar |
| `contenido_reutilizado` | Otra URL entregó el mismo contenido; archivo físico compartido |
| `sin_url` | Falta un enlace individual en el inventario |
| `requiere_url_individual` | El enlace original apunta a un índice o volumen del Diario Oficial |
| `html_no_solicitado` | Hay referencia HTML; no se pidió guardarla |
| `fuera_grupo` / `fuera_limite` | Entrada excluida por las opciones de esta ejecución |
| `bloqueado` | HTTP 401/403/429 o pantalla de verificación detectada |
| `html_en_lugar_pdf` | El servidor entregó HTML en una URL que debía ser PDF |
| `pdf_incompleto` / `transferencia_incompleta` | Faltan bytes o el cierre del PDF |
| `error_http` / `error_red` / `error_tls` | Fallo registrado con detalle |
| `excede_tamano` | Supera el máximo solicitado |
| `pendiente` / `interrumpido` | No se terminó de procesar; volver a ejecutar |

La validación comprueba firma PDF, marcador de cierre, tamaño transmitido cuando el servidor lo informa y hash SHA-256. No sustituye abrir el archivo con un lector/parser PDF ni verificar que su contenido sea el documento jurídico esperado.

Los reportes reflejan la última selección; `historial.jsonl` conserva las ejecuciones anteriores. Códigos de salida: `0`, solicitudes elegibles resueltas; `2`, hay fallos de descarga o URL inválidas; `1`, error de configuración o archivo local; `130`, interrupción. El código `0` puede coexistir con referencias sin URL o HTML no solicitados: revisar siempre el resumen.

## Opciones útiles

```bash
# Ver el plan completo, sin tráfico de red ni archivos nuevos
python descargar_remedios.py --todos --plan

# Casos específicos
python descargar_remedios.py --casos M.10341 M.10646

# Solo decisiones y compromisos
python descargar_remedios.py --todos --grupos nucleo

# Solo dos URL, para una prueba corta
python descargar_remedios.py --piloto --limite 2

# Más tiempo de conexión/lectura para un servidor lento
python descargar_remedios.py --todos --timeout 90 --timeout-total 600

# Ayuda completa
python descargar_remedios.py --help
```

De forma predeterminada realiza solicitudes secuenciales, pausa un segundo entre URL y reintenta hasta tres veces ante fallos temporales, respetando `Retry-After` hasta un máximo de 60 segundos. Los límites y la pausa son configurables. La verificación TLS permanece activada y se respeta la configuración de proxy del equipo.

## Actualizar el manifiesto

Si corregís o ampliás la planilla, exportá la pestaña **Documentos** como CSV conservando sus encabezados y ejecutá:

```bash
python preparar_manifiesto.py documentos_exportados.csv --destino manifiesto_actualizado.csv
python descargar_remedios.py --manifiesto manifiesto_actualizado.csv --todos --plan
```

Después podés ejecutar sin `--plan`, reutilizando el destino anterior. El manifiesto incluido es una **copia del inventario al 22/10/2026**; no se sincroniza automáticamente con Google Sheets ni descubre por sí mismo documentos nuevos.

## Pruebas realizadas

Pasaron 23 pruebas funcionales: reanudación y corrupción local, URL duplicadas, contenido duplicado, versiones, bloqueos, HTML en lugar de PDF, redirecciones, reintentos, transferencias truncadas, tamaño máximo, selección, bloqueo de ejecución simultánea y depuración de índices del Diario Oficial.

En el entorno de preparación se usó transporte HTTP en memoria porque no permite sockets locales ni la descarga masiva desde los sitios europeos. No se afirma una prueba de descarga real de los 119 enlaces. La primera verificación con esos servidores es el piloto en tu equipo.

Para ejecutar las pruebas del paquete:

```bash
python -m unittest discover -s tests -v
```

Cuando el equipo permite sockets, las mismas pruebas utilizan un servidor local. No consultan sitios públicos.

## Qué compartir después de la prueba

Compartí `reporte.csv` y `resumen.json`. Si hay un error que necesite seguimiento, agregá `historial.jsonl`. Para revisar el resultado inicial no hace falta enviar todos los PDF.
