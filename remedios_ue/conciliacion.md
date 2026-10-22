# Conciliación del universo de casos (etapa 1)

Período: autorizaciones condicionadas adoptadas entre **22/10/2021 y 22/10/2026**, inclusive.
Datos: JSON de DG COMP descargado el 22/10/2026 y comunicados de Presscorner consultados ese mismo día.

## Resultado

**47 casos**: 36 de fase I y 11 de fase II.

| Lista | Casos | Diferencias |
|---|---|---|
| A — JSON de DG COMP | 47 | — |
| C — comunicados "subject to conditions" | 47 | ninguna: A y C coinciden caso por caso |

La búsqueda de comunicados trajo 8 resultados más dentro del período, y ninguno cumple
el criterio:

- **5 autorizaciones sin condiciones.** Su título dice "unconditionally".
  - M.11602 SES/Intelsat
  - M.11902 Omnicom/IPG
  - M.12076 RTL/Sky DACH
  - M.12078 Suzano/Kimberly-Clark IFP
  - M.12115 Arla/DMK
- **3 decisiones del Reglamento de Subvenciones Extranjeras (FSR)**, otro régimen y sin número M:
  - e&/PPF Telecom (24/09/2024)
  - ADNOC/Covestro (14/11/2025)
  - línea ferroviaria de Lisboa (21/04/2026)

## Comparación con las estadísticas oficiales

Fuente: [*Merger cases statistics*](https://competition-policy.ec.europa.eu/mergers/statistics_en), PDF con datos al 30/09/2026.
Las filas usadas son "Art 6.1 (b) in conjunction with Art 6.2 (compatible w. commitments)" y "Art 8.2 compatible with commitments".

El conteo es por año calendario y abarca todo el JSON, no solo el período.

| Año | Fase I (JSON) | Fase I (estadística) | Fase II (JSON) | Fase II (estadística) | ¿Coincide? |
|---|---|---|---|---|---|
| 2019 | 10 | 10 | 6 | 6 | sí |
| 2020 | 13 | 13 | 3 | 3 | sí |
| 2021 | 7 | 7 | 4 | 4 | sí |
| 2022 | 10 | 10 | 2 | 2 | sí |
| 2023 | 4 | 4 | 5 | 5 | sí |
| 2024 | 5 | 5 | 3 | 3 | sí |
| 2025 | 9 | 9 | 0 | 0 | sí |
| 2026 (ene–sep) | 4 | 4 | 1 | 1 | sí |

En 2026 el JSON suma un caso posterior al cierre de la estadística: M.12330 Kimberly-Clark/Kenvue (13/10/2026). Las cifras citadas al inicio del proyecto (11, 12, 9, 8 y 9 para 2021–2025, y 5 para enero–septiembre de 2026) quedan confirmadas.

### De años calendario al período

| Año | En el período | Detalle |
|---|---|---|
| 2021 | 3 de 11 | M.10108 S&P Global/IHS Markit (22/10), M.9969 Veolia/Suez (14/12), M.10249 Derichebourg/Ecore (16/12) |
| 2022 | 12 | año completo |
| 2023 | 9 | año completo |
| 2024 | 8 | año completo |
| 2025 | 9 | año completo |
| 2026 | 6 | enero a 22/10 |
| **Total** | **47** | |

## Controles

- **Casos de la muestra inicial.** Los 6 están, con su fecha correcta:
  - M.9969 (14/12/2021)
  - M.10262 (27/01/2022)
  - M.10646 (15/05/2023)
  - M.10896 (20/02/2024)
  - M.11253 (04/04/2025)
  - M.11956 (13/02/2026)
- **Revisión manual de 3 casos al azar contra el documento oficial**:
  - M.10507: la decisión dice "Brussels, 30.10.2023, Article 6(1)(b) in conjunction with Article 6(2)". Coincide.
  - M.11485: la decisión dice "Bruxelles, le 17.7.2025, article 6, paragraphe 1, point b), en combinaison avec l'article 6, paragraphe 2". Coincide. La decisión está publicada solo en francés.
  - M.12201: la decisión todavía no está publicada; el comunicado IP/26/1338 del 12/06/2026 confirma la aprobación condicionada. Coincide.
- **Chequeos automáticos del script**: sin duplicados, todas las fechas dentro del período, solo las dos bases legales y sin campos obligatorios vacíos. Todo OK.

## Casos límite incluidos

| Caso | Situación | Tratamiento |
|---|---|---|
| M.10108 S&P Global/IHS Markit | Adoptado el primer día del período (22/10/2021) | Entra (período inclusive). Con período exclusivo serían 46 casos |
| M.10262 Meta/Kustomer | "Decisión sobre implementación de remedios" del 10/11/2023: sería la dispensa total de los compromisos | Entra; se confirma con el documento en la etapa 2 |
| M.10149 Korean Air/Asiana | Decisión sobre implementación de remedios (15/11/2024) | Entra, anotado |
| M.11936 Naspers/Just Eat Takeaway | Decisión por cláusula de revisión (29/05/2026) | Entra, anotado |
| M.10262, M.11485, M.11956 | Llegaron a la Comisión por remisión del art. 22 | Entran, anotado en `notas` |
| M.10560, M.10507, M.10860, M.11159, M.11485 | Notificación anterior retirada y luego renotificada | Entran, anotado en `notas` |
| M.11830 UniCredit/Banco BPM | La Comisión rechazó la remisión pedida por Italia (art. 9(3)) | Entra, anotado |

`casos.csv` no registra causas judiciales: el JSON no lista ninguna para estos 47 casos.
Esto se revisa en la etapa 2 con la búsqueda de sentencias, aunque `curia.europa.eu`
no es accesible desde este entorno.

## Excluidos: compromisos ofrecidos sin autorización condicionada en el período

Surgen del JSON: casos con "Commitments submitted" y una decisión final en el período que no es una autorización condicionada.

| Caso | Qué pasó |
|---|---|
| M.9637 IAG/Air Europa | Notificación retirada (16/12/2021) |
| M.9987 Nvidia/Arm | Operación abandonada (08/02/2022) |
| M.10188 Illumina/Grail | Prohibida (06/09/2022); prohibición luego retirada tras la sentencia del TJUE (06/09/2024) |
| M.10325 Kronospan/Pfleiderer Polska | Notificación retirada (29/11/2022) |
| M.10615 Booking/eTraveli | Prohibida (25/09/2023) |
| M.11109 IAG/Air Europa | Notificación retirada (02/08/2024) |
| M.11241 EEX/Nasdaq Power | Notificación retirada (26/06/2024) |
| M.11751 TPG/Techem | Notificación retirada (07/05/2025) |
| M.12076 RTL/Sky DACH | Ofreció compromisos en fase I (27/03/2026), pero se autorizó **sin condiciones** (22/04/2026) |

Caso en curso: **M.11944 MMG/negocio de níquel de Anglo American**. Está en fase II, con
compromisos presentados en fase I y pliego de cargos del 16/09/2026; todavía no hay
decisión.

## Anexo: revisiones de remedios de casos anteriores

En el período hubo decisiones que revisaron o aplicaron remedios de casos autorizados
**antes** de 2021-10-22. No entran en el universo principal porque la autorización es
anterior, pero muestran cómo se modifican los remedios con el tiempo. Van en un anexo
aparte, `revisiones_remedios.csv`, que genera `inventario_casos.py`:

| Caso | Autorizado | Decisiones en el período |
|---|---|---|
| M.3280 Air France/KLM | 2004 | cláusula de revisión (24/02/2023) |
| M.3770 Lufthansa/Swiss | 2005 | cláusula de revisión (19/11/2024) |
| M.4180 Gaz de France/Suez | 2006 | cláusula de revisión (16/06/2022) |
| M.5364 Iberia/Vueling/Clickair | 2009 | implementación de remedios (15/11/2021) |
| M.6447 IAG/BMI | 2012 | implementación de remedios (5 decisiones, 2021–2024) |
| M.8444 ArcelorMittal/Ilva | 2018 | implementación de remedios (28/11/2024) |
| M.8744 Daimler/BMW car sharing | 2018 | cláusula de revisión (31/01/2022) |
| M.9041 Hutchison/Wind Tre | 2018 | cláusula de revisión (09/09/2022) |
| M.8674 BASF/Solvay EP y P&I | 2019 | cláusula de revisión (29/02/2024 y 16/05/2025) |
| M.8947 Nidec/Embraco | 2019 | cláusula de revisión (21/10/2024) |
| M.9064 Telia/Bonnier | 2019 | cláusula de revisión (16/12/2025) |
| M.9546 Gategroup/LSG | 2020 | cláusula de revisión (29/10/2021 y 31/01/2022) |

## Validación

Validado por la ANC el 22/10/2026:

1. **M.10108 entra**: el período es inclusive. El universo queda en 47 casos.
2. **Los casos FSR quedan afuera** (e&/PPF, ADNOC/Covestro, línea de Lisboa): son otro régimen.
3. **Las 12 revisiones de remedios de casos anteriores van a un anexo aparte**, `revisiones_remedios.csv`, con sus documentos en `documentos.csv` (`universo = revisiones`).

Pendiente: revisar la clasificación preliminar de remedios en `casos.csv` (37 estructurales, 4 conductuales y 6 mixtos). Se confirma en la etapa 4.
