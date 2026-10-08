# Portal ANC · rama de pruebas

Rama: `test/portal-anc`, creada desde `main` en `f7e4ce9f826cc8d24ad13fa35727a8341c5ec6e4`.

La entrada del portal es **`/herramientas/`**. `/` continúa siendo el buscador existente.
No se modifican `index.html`, `generar_pagina.py`, `firm.xlsx`, el HTML fuente de OPIs,
los PDFs ni el circuito mensual. Productos faltantes y correcciones de OPIs quedan pendientes.

| Ruta | Contenido | Fuente |
| --- | --- | --- |
| `/` | Buscador de mercados y resoluciones existente | `index.html`, sin regenerar |
| `/herramientas/` | Portal con acceso a cada herramienta | Nueva página |
| `/opis/` | **Buscador independiente de OPIs**, con sus propios filtros | Copia del HTML `pdf/lectura_opi/buscador_opis.html`; solo se agrega navegación y aviso |
| `/conc/` | Tablero público con filtros por año y tipo, cobertura y CSV | JSON del buscador publicado; fechas de ingreso de `firm.xlsx` |
| `/noticias/` | Monitor de lectura y exportación CSV | Ocho operaciones completamente ficticias |
| `/seguimiento/` | Carga por analista, estados, antigüedad y revisiones | Doce expedientes completamente ficticios |

El tablero no agrupa ni interpreta las decisiones jurídicas: muestra el texto original.
Su universo incluye todos los tipos del corpus, incluidas OPIs; se pueden filtrar los tipos.
Las etiquetas de sectores y relaciones pueden repetirse por expediente y no suman el total.
Los tiempos son días corridos entre ingreso y firma; no descuentan suspensiones ni representan
plazos legales. Solo se incorporan pares de fechas válidos cuya fila y fecha de firma coinciden
con el HTML publicado. Los campos vacíos no se completan.

Las demos no importan el artefacto de Claude ni `Res_firmadas.xlsm`. El monitor real requiere
una exportación y adaptar el código del artefacto. El seguimiento real requiere el Excel maestro.
Ambas conexiones corresponden a un área interna con autenticación validada, fuera del repo público.

## Prueba local

```bash
python -m pip install -r requirements-portal.txt
python scripts/generar_portal.py
python scripts/preparar_preview.py
python -m http.server 8000 --directory public
```

Abrir `http://localhost:8000/herramientas/`. Los dos primeros comandos solo generan archivos
nuevos. `preparar_preview.py` reemplaza únicamente la carpeta generada `public/`, ignorada por Git.
El servidor es exclusivamente de prueba local.

## Cloudflare: preview aislado

No cambiar la configuración del proyecto de producción `buscadoranc` para probar `public/`.
Crear un proyecto Pages de prueba separado, conectado a este repositorio y a la rama
`test/portal-anc`:

- Framework: ninguno.
- Build command: `python -m pip install -r requirements-portal.txt && python scripts/generar_portal.py && python scripts/preparar_preview.py`.
- Build output directory: `public`.
- Entrada a probar: `<URL-del-proyecto-de-prueba>/herramientas/`.

Si el proyecto actual ya tiene previews por rama y sirve la raíz, las páginas nuevas también
se pueden probar en `<URL-real-del-preview>/herramientas/`, sin cambiar sus settings. Ese
preview conserva la publicación de raíz existente; no equivale a publicar solo `public/`.
No asumir ni inventar una URL: obtenerla del deployment de Cloudflare/GitHub.

La salida `public/` usa una lista explícita de archivos: HTML, CSS, JS, los tres JSON previstos,
verificación de Search Console y PDFs de la carpeta principal con nombres de expedientes.
Excluye Excel, scripts Python, históricos, insumos internos y claves. Se conservan los nombres
actuales de PDFs y los enlaces del buscador; sus problemas previos quedan fuera de esta entrega.
La salida de prueba agrega `404.html` y cabeceras `noindex` para evitar indexar el preview.
`noindex` no es un control de acceso. Los dos JSON de demos deben declarar `demo: true`.

## Qué evaluar

1. Abrir cada tarjeta del portal y volver con la navegación de las páginas nuevas.
2. En OPIs, buscar y combinar filtros. Los 96 dictámenes y su lógica siguen siendo los del HTML fuente.
3. En resoluciones, probar filtros individuales y combinados y limpiar la selección.
4. Revisar que el total sin filtros sea 1.045, con 566 pares de fechas válidos.
5. Descargar los CSV y comprobar que respetan los filtros activos.
6. En noticias, combinar búsqueda, mercado y estado; todos los nombres son ficticios.
7. En seguimiento, combinar analista, estado y procedimiento; las revisiones son fechas de gestión de ejemplo, no plazos legales.
8. Probar en pantalla ancha y móvil; las tablas anchas tienen desplazamiento horizontal.

Las compuertas de contenido se ejecutan con `python -m unittest discover -s tests -v`
después de generar el portal y preparar `public/`. Comparan los archivos existentes con
el commit base, verifican el corpus del tablero, la lógica intacta de OPIs y la lista de
archivos publicables.

Esta entrega no se fusiona a `main` ni cambia la configuración de producción. La aceptación
de las herramientas y su incorporación al sitio habitual requieren la decisión del usuario.
