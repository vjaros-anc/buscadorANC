# Fichas problema–remedio: plantilla y reglas

Cada caso tiene una ficha legible (`fichas/M.xxxxx.md`) y una o más filas en
`fichas/relaciones.csv`, una por cada par problema–remedio. La ficha es para leer y
revisar; el CSV, para filtrar y comparar casos.

**Estado:** plantilla aprobada por la ANC junto con las dos fichas modelo (M.11253
Safran/Collins y M.10646 Microsoft/Activision). Piloto de 9 casos en curso.
`validar_fichas.py` controla el formato, los vocabularios y las citas.

## Estructura de la ficha

1. **Encabezado:** caso, partes, decisión (fecha, fase, base legal), sector y documentos
   fuente por `doc_id` de `documentos.csv`.
2. **Resumen** en 3–4 líneas.
3. **Problemas (P1, P2…):** mercado de producto y geográfico, tipo de efecto, mecanismo
   de daño y evidencia clave.
4. **Remedios (R1, R2…):** tipo y subtipo, obligación concreta, alcance, duración,
   comprador, trustee y cláusula de revisión.
5. **Relación problema–remedio** y por qué la Comisión consideró suficiente el remedio,
   incluido lo que cambió tras el *market test*.
6. **Implementación y cambios posteriores:** comprador aprobado, dispensas, recursos.
7. **Para la ANC:** qué condiciones habría que examinar para usarlo como precedente.
   **Es análisis propio, no texto de la Comisión**, y va marcado así.
8. **Dudas y pendientes.**

Lo que no es problema de competencia (mercados donde la Comisión descartó dudas) se
menciona en una línea en el resumen, para dar contexto.

## Citas

Cada afirmación lleva su fuente, con la página física del PDF (desde 1) entre corchetes:

| Fuente | Formato | Ejemplo |
|---|---|---|
| Decisión | `DEC párr. n [p. x]` | `DEC párr. 192 [p. 50]` |
| Compromisos | `COMP cl. n [p. x]` | `COMP cl. 4 [p. 84]` |
| Tabla de la decisión | `DEC tabla n [p. x]` | `DEC tabla 3 [p. 43]` |
| Otro documento | `doc_id [p. x]` o `doc_id cl. n [p. x]` | `M.11253_POST_01 [p. 1]` |

- Varios párrafos o páginas: `DEC párrs. 166–172 [pp. 45–47], 177 [p. 48]` o
  `DEC párrs. 317, 327 [pp. 78, 80]`. Cada párrafo citado tiene que estar (al menos en
  parte) en alguna de las páginas indicadas.
- `COMP` es el anexo de compromisos dentro de la decisión (`paginas_compromisos`). Si los
  compromisos están publicados aparte, se citan por su `doc_id`.
- La **página física** es la posición en el PDF (la de `pagina_pdf` del extractor), no el
  número impreso al pie.
- Las cifras con rangos (`[80-90]%`) se transcriben tal cual. Si salen de una página
  con `origen_texto = ocr`, se verifican contra la imagen del PDF.
- El comunicado y el Merger Brief se usan para orientarse; la fuente de la ficha es la
  decisión y sus compromisos.

## Vocabularios controlados

Usados en `relaciones.csv` (columna entre paréntesis). Si un caso no encaja, se agrega
el valor acá antes de usarlo: `validar_fichas.py` lee las listas de este archivo. Si a un
par problema–remedio le corresponden dos valores de la misma lista, van separados por `;`
(p. ej. `acceso;no_discriminacion`).

**Tipo de efecto (`tipo_efecto`)**
- `horizontal_no_coordinado`: pérdida de competencia entre las partes (unilateral).
- `horizontal_coordinado`: más probabilidad de coordinación entre competidores.
- `vertical_cierre_insumos`: la entidad puede negar o encarecer un insumo a rivales.
- `vertical_cierre_clientes`: la entidad puede dejar de comprar a proveedores rivales.
- `conglomerado`: empaquetamiento, ventas atadas o apalancamiento entre mercados vecinos.
- `competencia_potencial`: desaparece un entrante probable o un competidor potencial.
- `innovacion`: menos incentivos o capacidad de innovar.
- `informacion_sensible`: acceso a información comercial confidencial de rivales.

**Tipo de remedio (`tipo_remedio`):** `estructural`, `conductual`, `mixto`.

**Subtipo de remedio (`subtipo_remedio`)**
- `desinversion_negocio`: un negocio completo y autónomo.
- `desinversion_activos`: plantas, marcas, sucursales u otros activos sueltos.
- `cesion_espectro_slots`: espectro, slots aeroportuarios, derechos de tráfico.
- `reduccion_participacion`: venta de una participación minoritaria o salida de una empresa común.
- `acceso`: acceso a red, infraestructura, plataforma o API.
- `licencia`: licencia de propiedad intelectual o de contenidos.
- `interoperabilidad`: garantizar que productos de terceros funcionen con los propios.
- `no_discriminacion`: trato igual a rivales y clientes.
- `separacion`: separación organizativa, cortafuegos de información.
- `suministro`: obligación de suministrar a terceros.
- `abstencion`: no ejercer votos, no designar directores, no hacer algo por un plazo.

**Comprador previo (`comprador_previo`)**
- `upfront_buyer`: la operación no se ejecuta hasta aprobar al comprador.
- `fix_it_first`: el comprador se identifica y aprueba en la propia decisión.
- `no`: el comprador se aprueba después.
- `no_aplica`: el remedio no es una venta.

**Trustee (`trustee`):** `monitoreo`, `monitoreo_y_desinversion`, `no`.

**Cláusula de revisión (`clausula_revision`):** `si`, `no`.

## Columnas de `relaciones.csv`

| Columna | Contenido |
|---|---|
| `caso_id` | M.xxxxx |
| `problema_id`, `remedio_id` | P1, R1… (los mismos de la ficha) |
| `mercado`, `ambito_geografico` | Mercado del problema y su alcance geográfico |
| `tipo_efecto`, `mecanismo` | Vocabulario y mecanismo de daño en una línea |
| `tipo_remedio`, `subtipo_remedio`, `obligacion` | Vocabulario y obligación concreta en una línea |
| `duracion` | Plazo de la obligación o de las restricciones asociadas |
| `comprador_previo`, `trustee`, `clausula_revision` | Vocabularios |
| `cita_problema`, `cita_remedio`, `cita_suficiencia` | Citas en el formato de arriba |
| `notas` | Aclaraciones |
