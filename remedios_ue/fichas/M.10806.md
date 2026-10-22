# M.10806 — Broadcom / VMware

| | |
|---|---|
| **Partes** | Broadcom, Inc. (EE. UU.), que fabrica semiconductores y software de infraestructura, adquiere el control exclusivo de VMware, Inc. (EE. UU.), líder en software de virtualización — DEC párrs. 1–2 [p. 8], 3–4 [p. 9] |
| **Decisión** | 12/07/2023, C(2023) 4654 final. **Fase II, art. 8(2).** Notificada el 15/11/2022 |
| **Sector** | C.26.1 — Componentes electrónicos; J.62.01 y J.62.09 — Programación y servicios informáticos |
| **Documentos** | `M.10806_DEC_01` (decisión, 232 p.), `M.10806_COMP_01` (compromisos, pp. 220–232 de la misma), `M.10806_MB_M01` (Merger Brief 2/2025), `M.10806_SENT_M01` a `M03` (recurso de CISPE, T-503/25; no descargados) |

## Resumen

Broadcom fabrica adaptadores de bus de host Fibre Channel (FC HBA). Es dominante, o al menos
tiene una posición muy fuerte, frente a un solo rival, Marvell (DEC párrs. 791 [p. 167], 794
[pp. 167–168]). VMware tiene poder de mercado significativo en software de virtualización de
servidores, en instalaciones propias y nube privada (DEC párr. 615 [p. 133]). Para venderse,
los FC HBA necesitan estar certificados como interoperables con el hipervisor de VMware (DEC
párr. 429 [p. 101]).

El problema era **de conglomerado**: la entidad podría demorar la certificación de los FC HBA
de Marvell y degradar su interoperabilidad (DEC párr. 830 [p. 175]). Broadcom lo resolvió
con un **remedio de interoperabilidad a 10 años**:
- acceso a las API y a la certificación en igualdad con su propia división;
- licencia abierta del código fuente de sus *drivers*;
- separación organizativa (DEC párr. 1072 [p. 216]).

La Comisión descartó dudas en:
- los solapamientos horizontales de software (DEC párr. 368 [p. 89]);
- el cierre de proveedores de adaptadores de almacenamiento, de NIC y de SmartNIC (DEC
  párrs. 888 [p. 184], 931 [p. 190], 956 [p. 195]);
- el empaquetamiento de VMware con software de Broadcom (DEC párr. 1017 [p. 205]).

## Problemas

### P1 — Cierre de Marvell en FC HBA por degradación de la interoperabilidad con VMware

- **Mercado:**
  - FC HBA, mundial;
  - software de virtualización de servidores en instalaciones propias y nube privada, de
    donde viene el apalancamiento.
- **Efecto:** conglomerado: apalancamiento por interoperabilidad.
- **Mecanismo:**
  - **El insumo crítico es la certificación.** La interoperabilidad certificada con el
    hipervisor ESXi es un factor de competencia crítico para los FC HBA. La mayoría cree que
    sin ella no se puede vender (DEC párrs. 424 [p. 100], 429 [p. 101]).
  - **Poder de VMware:** poder de mercado significativo en virtualización de servidores en
    instalaciones propias y nube privada (DEC párr. 615 [p. 133]).
  - **Capacidad:**
    - un cierre total dañaría la reputación de neutralidad de VMware (DEC párr. 627
      [p. 135]);
    - pero puede hacer un cierre parcial demorando la certificación de los productos de
      Marvell (DEC párrs. 654 [p. 140], 661 [p. 141]).
  - **Incentivo:** la entidad tendría incentivo para degradar la interoperabilidad de su
    único rival (DEC párr. 788 [pp. 166–167]).
  - **Estructura:** Broadcom tenía [60-70]% del mercado y Marvell, su único competidor
    material, [30-40]%, en baja desde [50-60]% en 2017 (DEC párr. 794 [pp. 167–168]; DEC
    tabla 22 [p. 168]).
  - **Efecto:** los fabricantes de servidores (OEM) no incluyen en su catálogo un producto
    que no llegue certificado a tiempo. Marvell perdería ventas e invertiría menos, y Broadcom
    mantendría o reforzaría su posición (DEC párrs. 823 [pp. 173–174], 829 [pp. 174–175]).
- **Conclusión de la Comisión:** cerrarle el mercado a Marvell demorando la certificación
  tendría un efecto perjudicial significativo en el mercado mundial de FC HBA (DEC párr. 830
  [p. 175]).

## Remedios

### R1 — Interoperabilidad, código abierto de *drivers* y separación organizativa, por 10 años

- **Tipo:** conductual: interoperabilidad, licencia y separación.
- **Obligaciones:**
  - **Acceso abierto a las API y a la certificación** (COMP cl. 1–2 [p. 222]; DEC párrs.
    1030–1031 [pp. 208–209]):
    - dar a Marvell las API de interoperabilidad, el kit de desarrollo de *drivers*, los
      materiales previos al lanzamiento y la suite de certificación, al mismo tiempo y del
      mismo modo que a la división de FC HBA de Broadcom;
    - dar el mismo nivel de soporte técnico y de certificación, con la misma rapidez;
    - no diseñar ni cambiar el software de virtualización para favorecer los HBA de Broadcom;
    - certificar salvo justificación objetiva, y listar los productos en la guía de
      compatibilidad de VMware.
  - **Licencia de código fuente:** dentro de los 30 días del cierre, entregar a Marvell el
    código de los *drivers* de los FC HBA de Broadcom, actuales y futuros, con una licencia
    Apache 2.0 irrevocable (COMP cl. 4 [p. 224]; DEC párr. 1033 [p. 209]).
  - **Separación organizativa y confidencialidad:** la información de Marvell recibida en la
    certificación y el soporte se maneja solo por personal autorizado, con barreras físicas y
    de sistemas (COMP cl. 5–6 [p. 224]; DEC párr. 1035 [pp. 209–210]).
  - **Tarifas:** mínimas y en línea con la práctica previa (DEC párr. 1074 [p. 216]).
- **Beneficiarios:** Marvell y **cualquier nuevo entrante** en FC HBA (COMP cl. 7 [p. 225];
  DEC párr. 1070 [pp. 215–216]).
- **Duración:** **10 años** desde la decisión (COMP cl. 53 [p. 232]).
- **Control:**
  - *trustee* de monitoreo nombrado antes del cierre, con informes trimestrales los dos
    primeros años (COMP cl. 8 [p. 225]; DEC párr. 1068 [p. 215]);
  - **arbitraje rápido** si Marvell denuncia un incumplimiento (COMP cl. 26 [p. 228]).
- **Cláusula de revisión:** dispensa, modificación o sustitución en circunstancias
  excepcionales. La Comisión no puede extender la duración de 10 años (COMP cl. 54–55
  [p. 232]).

## Relación problema–remedio y suficiencia

R1 resuelve P1 con tres compromisos que se refuerzan:
- **el acceso en igualdad y a tiempo** elimina el riesgo de demorar la certificación o el
  soporte (DEC párr. 1073 [p. 216]);
- **el código fuente** le permite a Marvell verificar que tiene la misma información que
  Broadcom y reutilizarla (DEC párr. 1076 [pp. 216–217]);
- **la separación** evita el uso de información confidencial de Marvell (DEC párr. 1072
  [p. 216]).

El *market test* fue positivo: nadie planteó objeciones de fondo (DEC párr. 1055
[pp. 213–214]).

**Qué cambió tras el *market test*** (DEC párrs. 1057–1064 [p. 214], 1068 [p. 215], 1070
[pp. 215–216]):
- se eliminó la cláusula que permitía a VMware desarrollar API para uso interno "de prueba".
  Con ella, la entidad podía adaptar las API a sus propios HBA;
- el acceso tiene que ser a tiempo para que Marvell lance funciones sin demora, y no según el
  ciclo de innovación de Broadcom;
- el soporte técnico, con la misma calidad y rapidez;
- la guía de compatibilidad, neutral;
- tarifas acotadas a la práctica previa;
- un *trustee* más fuerte;
- la extensión a nuevos entrantes.

No hizo falta un segundo *market test* (DEC párr. 1071 [p. 216]).

## Implementación y cambios posteriores

- **Recurso:** CISPE pidió la anulación de la autorización ante el Tribunal General (T-503/25).
  Al 22/10/2026 está pendiente (`M.10806_MB_M01` [p. 2]; filas `M.10806_SENT_M01` a `M03` de
  `documentos.csv`, no verificadas por el bloqueo de EUR-Lex y Curia).
- No hay en el corpus decisiones de dispensa ni de modificación.

## Para la ANC (análisis propio, no de la Comisión)

- **Un remedio de interoperabilidad puede bastar en un caso de conglomerado**, si el problema
  está bien acotado: un solo rival identificado, un proceso técnico concreto (la
  certificación) y obligaciones verificables. El Merger Brief lo presenta como un escenario
  excepcional (`M.10806_MB_M01` [p. 1]).
- **La entrega de código fuente con licencia abierta** es una herramienta original: reduce la
  asimetría de información y le da al rival una base para verificar el cumplimiento.
- **Cuidado con las excepciones "de desarrollo y prueba":** pueden vaciar la obligación de
  igualdad. La Comisión las eliminó.
- **Lo que no es efecto de la operación no se remedia.** Las quejas por subas de precios y
  cambios de licencias de VMware se refieren a un poder de mercado que VMware ya tenía. No
  son un cambio estructural causado por la operación, que es lo que mira el control de
  concentraciones (`M.10806_MB_M01` [p. 2]). Para la ANC: separar el análisis de fusiones de
  las conductas explotativas, que van por otra vía.
- **Remedios de comportamiento a 10 años** necesitan un *trustee* técnico y un arbitraje
  rápido. Si no, el único beneficiario (Marvell) carga con todo el control.

## Dudas y pendientes

- Seguir el recurso T-503/25 de CISPE: su alcance y su resultado.
- Los compromisos se aplican a los FC HBA. Los de NIC y SmartNIC y las licencias a clientes
  quedaron fuera del remedio porque no se encontró un problema de competencia.
