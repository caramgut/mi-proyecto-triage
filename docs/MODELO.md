# Modelo de apoyo al triaje

> **La IA es un apoyo a la decisión.** El profesional aprueba o rechaza cada reporte; el sistema nunca cambia el nivel de triaje por sí solo.

Este documento reúne todo lo relativo al modelo: qué hace, cómo se eligió, cómo decide, qué tan bien funciona, dónde falla y cómo se integra con el sistema (R10, R12 y R20). El origen y los filtros de los datos están en [`DATASETS.md`](DATASETS.md).

**Alcance.** El modelo no diagnostica ni reemplaza el triaje de enfermería. Su función es apoyar el pretriaje y señalar pacientes que requieren una valoración prioritaria. Se entrenó y evaluó con datos de Corea del Sur y Estados Unidos, por lo que sus resultados no demuestran que vaya a funcionar igual en pacientes de Colombia.

Versión del modelo: `logreg-alarmas-3cat-3.0` (`ml/modelo.py`). Se entrena al arrancar el servicio `ml` a partir de `ml/data/triaje_supervisado_limpio.csv`. Las cifras salen de `back/preprocesamiento/salida_ia/metricas_modelo.json`.

## 1. Qué hace y con qué datos

Dado un paciente adulto, el modelo estima la probabilidad de tres categorías y devuelve la categoría, las probabilidades, los factores que empujaron hacia «crítico» en ese paciente y un indicador de alerta.

Se usan 9.304 registros: 7.443 pacientes para entrenamiento y 1.861 para prueba. La evaluación final se hace solo sobre la prueba, que no se utilizó para ajustar el modelo.

Los cinco niveles originales de triaje se agrupan en tres categorías:

| Categoría predicha | Niveles originales | Interpretación |
| --- | --- | --- |
| Crítico | 1 y 2 | Mayor urgencia; requiere valoración inmediata o en pocos minutos |
| Medio | 3 | Urgente; puede esperar un tiempo limitado |
| No crítico | 4 y 5 | Menor urgencia relativa |

El modelo usa 12 variables clínicas (edad, sexo, llegada en ambulancia, lesión, frecuencia cardíaca, frecuencia respiratoria, presión arterial, temperatura, saturación de oxígeno, dolor y motivo de consulta) e indicadores derivados de signos de alarma.

**Etiqueta de referencia.** La etiqueta de referencia es el triaje asignado por enfermería. El modelo aprende patrones asociados a esa clasificación; no aprende una verdad clínica independiente.

## 2. Preprocesamiento y signos de alarma

**Preprocesamiento.** Numéricas: mediana + estandarización. Binarias: moda. Motivo de consulta: *one-hot* (13 categorías). Se añaden **11 signos de alarma** calculados con reglas clínicas simples; con ellos el AUC sube de 0,774 a 0,783.

| Signo de alarma | Condición |
|---|---|
| Hipoxemia | SpO₂ < 92 % |
| FR alterada | FR ≥ 24 o < 10 |
| Taquicardia / bradicardia | FC ≥ 110 / FC < 50 |
| Hipotensión / hipertensión grave | PAS < 90 / PAS ≥ 200 |
| Fiebre / hipotermia | T ≥ 38 °C / T < 35,5 °C |
| Índice de choque | FC / PAS ≥ 1 |
| Dolor intenso | ≥ 7 |
| Edad | ≥ 65 años |

Un dato faltante no cuenta como alarma.

## 3. Métricas utilizadas

La exactitud global no basta. En triaje, clasificar como no crítico a un paciente crítico es más grave que marcar como crítico a uno que finalmente no lo era.

| Métrica | Qué mide | Interesa |
| --- | --- | --- |
| AUC crítico | Capacidad de ordenar a los pacientes críticos por encima de los demás, sin depender de un umbral | Más alto |
| Sensibilidad crítica | Proporción de pacientes críticos reales que el modelo identifica como críticos | Más alta |
| VPP crítico | De los pacientes marcados como críticos, proporción que realmente lo es según la referencia | Más alto |
| Especificidad crítica | Proporción de pacientes no críticos que no se marcan como críticos | Más alta |
| Kappa ponderado | Acuerdo con el triaje de referencia, considerando que las categorías tienen orden | Más alto |
| F1 macro | Equilibrio entre precisión y sensibilidad, promediado entre las tres categorías | Más alto |
| Brier | Acierto de las probabilidades estimadas | Más bajo |
| Subtriaje grave | Proporción de críticos que el modelo clasifica como no críticos | Más bajo |

El subtriaje grave es el error de seguridad más preocupante. El sobretriaje (asignar una urgencia mayor que la de referencia) aumenta las revisiones y la carga de trabajo, pero no todo sobretriaje es clínicamente innecesario.

## 4. Selección del modelo

Se compararon cinco modelos con validación cruzada de cinco particiones. Todos usan la misma regla general de clasificación y un objetivo de sensibilidad crítica cercano al 70 %, para que la comparación no favorezca al modelo que simplemente marca más pacientes como críticos.

**Validación cruzada** (media ± desviación entre particiones):

| Modelo | AUC crítico | VPP crítico | Kappa ponderado | Subtriaje grave | F1 macro |
| --- | --- | --- | --- | --- | --- |
| Regresión logística | 0,784 ± 0,013 | 0,384 ± 0,020 | 0,437 ± 0,018 | 0,110 ± 0,005 | 0,532 ± 0,012 |
| SVM con kernel RBF | 0,776 ± 0,013 | 0,379 ± 0,017 | 0,438 ± 0,018 | 0,132 ± 0,031 | 0,523 ± 0,012 |
| Regresión lineal | 0,768 ± 0,015 | 0,371 ± 0,012 | 0,438 ± 0,017 | 0,089 ± 0,007 | 0,514 ± 0,016 |
| Árbol de decisión | 0,730 ± 0,037 | 0,323 ± 0,024 | 0,349 ± 0,053 | 0,187 ± 0,029 | 0,459 ± 0,022 |
| KNN | 0,729 ± 0,008 | 0,288 ± 0,004 | 0,315 ± 0,023 | 0,111 ± 0,014 | 0,452 ± 0,011 |

- **Regresión logística:** mejor AUC, VPP y F1 macro. Produce probabilidades interpretables y calibrables, útiles para fijar umbrales clínicos.
- **SVM:** desempeño muy cercano al de la logística, pero más lenta de entrenar y más difícil de explicar al personal clínico. Su subtriaje grave varía más entre particiones.
- **Regresión lineal:** menor subtriaje grave, pero no entrega probabilidades clínicas directas, lo que limita su uso para mostrar riesgos y activar alertas.
- **Árbol de decisión:** se explica como una secuencia de preguntas, pero rinde menos y varía más entre particiones.
- **KNN:** AUC y VPP inferiores; comparar pacientes por distancias en muchas variables rinde menos que los modelos lineales.

**Conjunto de prueba:**

| Modelo | AUC crítico | VPP crítico | Kappa ponderado | Subtriaje grave | Sensibilidad crítica |
| --- | --- | --- | --- | --- | --- |
| Regresión logística | 0,765 | 0,365 | 0,417 | 0,132 | 65,8 % |
| SVM con kernel RBF | 0,766 | 0,366 | 0,433 | 0,164 | 67,3 % |
| Regresión lineal | 0,743 | 0,352 | 0,418 | 0,099 | 64,6 % |
| Árbol de decisión | 0,744 | 0,335 | 0,395 | 0,167 | 73,4 % |
| KNN | 0,721 | 0,301 | 0,330 | 0,120 | 74,3 % |

La regresión logística, la SVM y la regresión lineal quedan alrededor de un AUC de 0,77–0,78 en validación cruzada, frente a 0,73 del árbol y KNN. Entre los tres mejores las diferencias son pequeñas respecto a la variabilidad entre particiones. En la prueba, la SVM tiene AUC y VPP ligeramente superiores y la regresión lineal menos subtriaje grave, así que no hay un ganador absoluto en cada métrica.

Se elige la **regresión logística** por el equilibrio entre rendimiento, interpretabilidad, rapidez y posibilidad de usar sus probabilidades en la guarda de seguridad y en la alerta. Las cifras finales de la sección 7, calculadas con la guarda y la red de seguridad, difieren ligeramente de las de esta comparación.

Además, la regresión logística es **explicable** (el aporte de cada variable se puede mostrar al médico), **rápida** (0,15 s de entrenamiento frente a 14,5 s del SVM) y sus probabilidades son razonablemente interpretables, aunque no perfectas (calibración en la sección 7).

## 5. Regla de decisión, umbrales y seguridad (R20)

Un modelo puede generar buenas probabilidades, pero el resultado clínico cambia según el punto a partir del cual se clasifica a un paciente como crítico.

**Por qué no se elige simplemente la categoría más probable.** La categoría «medio» es muy frecuente. Si el sistema eligiera siempre la categoría con mayor probabilidad, podría dejar de identificar a pacientes críticos con un riesgo relevante pero inferior al de la categoría media. Por eso se usan umbrales de probabilidad.

| Parámetro | Valor | Función |
| --- | --- | --- |
| `U_CRITICO` | 0,185 | Umbral para clasificar como crítico por probabilidad |
| `GUARDA` | 0,10 | Impide clasificar como no crítico a un paciente con probabilidad crítica de 10 % o más |
| `U_NO_CRITICO` | 0,37 | Probabilidad de no crítico necesaria para asignar esa categoría |
| `U_ALERTA` | 0,38 | Umbral para activar la alerta en vivo |

Los valores se seleccionan con datos de entrenamiento y validación cruzada, no buscando el mejor resultado en la prueba final.

**Umbral crítico (0,185).** Es el umbral más alto que permite detectar al menos el 70 % de los pacientes críticos en validación cruzada. Un umbral más alto genera menos alertas, pero deja escapar más críticos. Uno más bajo identifica más críticos, pero marca como críticos a más pacientes medios o no críticos. No es una probabilidad biológica universal: es un punto de decisión del modelo que debe validarse clínicamente.

**Guarda y red de seguridad.**
- *Guarda de probabilidad:* con probabilidad crítica de 10 % o más, el paciente no puede quedar como «no crítico»; queda como crítico o medio según las demás reglas.
- *Red de seguridad clínica:* si la saturación de oxígeno es inferior al 88 % o la presión arterial sistólica es inferior a 90 mmHg, el sistema fuerza la clasificación crítica y activa la alerta, sin importar la probabilidad calculada.

La guarda no elimina todos los errores: un paciente crítico con signos aparentemente normales y un motivo de consulta que el modelo interpreta como leve puede seguir clasificado como no crítico.

**Umbral de alerta (0,38).** Una clasificación aparece en el reporte que revisa el médico, mientras que una alerta puede interrumpir el flujo de trabajo y exigir una respuesta. Por eso se elige el umbral más bajo que alcanza un VPP de al menos 0,50 en validación: que al menos la mitad de las alertas correspondan a pacientes críticos reales según la referencia. Esto limita las falsas alarmas y la fatiga por alertas, a costa de detectar menos críticos mediante la alerta inmediata.

> Estos umbrales son criterios de diseño del sistema, no puntos de corte clínicos validados para el Hospital San Andrés de Tumaco.

### Cómo se aplica la regla en el sistema

La categoría final no es simplemente la de mayor probabilidad. Se aplica esta regla (`U_*` en `ml/modelo.py`):

1. **Crítico** si P(crítico) ≥ **0,185** o se cumple la **red de seguridad** (SpO₂ < 88 % o PAS < 90 mmHg). El 0,185 es el umbral más alto que todavía detecta ≥ 70 % de los críticos en validación cruzada.
2. **No crítico** si P(no crítico) ≥ **0,37** y P(crítico) < **0,10** (la "guarda": nadie con 10 % o más de probabilidad crítica se etiqueta como no crítico).
3. **Medio** en los demás casos.

La alerta en vivo (R20) se dispara si P(crítico) ≥ **0,38** o se cumple la red de seguridad.

### Por qué un paciente puede salir «Crítico» con 30 % y «Medio» con 58 %

Porque el umbral de categoría crítica (0,185) es mucho menor que el de alerta (0,38). Se prefiere marcar "crítico" a más pacientes para no pasar por alto críticos (sensibilidad), a costa de más falsos positivos. En ese ejemplo el paciente queda clasificado "Crítico", se pide revisión médica, pero **no se dispara la alerta de R20**. No es una contradicción: son dos reglas con objetivos distintos.

## 6. Matriz de confusión del modelo final

Conjunto de prueba (n = 1.861). Filas: categoría real según enfermería. Columnas: categoría predicha.

| Real ↓ / Predicha → | Crítico | Medio | No crítico | Total real |
| --- | --- | --- | --- | --- |
| Crítico | **225** | 86 | 31 | 342 |
| Medio | 324 | **473** | 182 | 979 |
| No crítico | 71 | 193 | **276** | 540 |
| Total predicho | 620 | 752 | 489 | 1.861 |

- **Críticos (342):** 225 identificados correctamente (sensibilidad 225/342 ≈ 65,8 %), 86 clasificados como medios y 31 como no críticos. Estos 31 (9,1 % de los críticos) son el error más preocupante, porque pueden recibir menos prioridad de la que necesitan. Los 86 clasificados como medios también merecen revisión.
- **Medios (979):** 473 correctos, 324 marcados como críticos y 182 como no críticos. Los 324 son el principal origen del sobretriaje y pueden aumentar las valoraciones prioritarias y la carga de trabajo. No debe asumirse que sean clínicamente innecesarios: la referencia es la etiqueta de enfermería y el modelo no tiene acceso a toda la valoración clínica.
- **No críticos (540):** 276 correctos, 71 marcados como críticos y 193 como medios. El modelo conserva cierto margen de precaución: reduce el riesgo de dar baja prioridad a algunos pacientes, a cambio de más revisiones.

En conjunto, el modelo identifica aproximadamente dos de cada tres pacientes críticos; el error individual más grave es clasificar a un crítico como no crítico, y el más numeroso es clasificar a pacientes medios como críticos. Una buena capacidad para ordenar el riesgo (AUC) no garantiza que las decisiones tomadas con un umbral sean suficientemente seguras.

## 7. Resultados finales de la regresión logística

Evaluación sobre los 1.861 pacientes de prueba con la regla completa (guarda y red de seguridad). Los intervalos de confianza del 95 % se calculan por bootstrap, con 2.000 remuestreos de la prueba.

| Métrica | Resultado | IC 95 % | Interpretación |
| --- | --- | --- | --- |
| AUC crítico | 0,765 | 0,735–0,794 | Discriminación razonable, con margen de mejora |
| Sensibilidad crítica | 65,8 % | 60,6–70,7 % | Identifica cerca de dos tercios de los críticos |
| VPP crítico | 36,3 % | 32,5–40,2 % | Unos 36 de cada 100 marcados como críticos lo son según la referencia |
| Kappa ponderado | 0,409 | 0,371–0,448 | Acuerdo moderado |
| F1 macro | 0,517 | 0,494–0,539 | Desempeño agregado entre las tres categorías |
| Sensibilidad de no crítico | 51,1 % | 46,7–55,3 % | Proporción de no críticos reales que se clasifican como tales |
| Críticos clasificados como no críticos | 9,1 % | 6,1–12,0 % | Error relevante para la seguridad |
| Sensibilidad de la alerta en vivo | 37,1 % | 32,0–42,3 % | La alerta detecta algo más de un tercio de los críticos |
| VPP de la alerta en vivo | 50,2 % | 43,7–56,3 % | Cerca de la mitad de las alertas son críticos reales |
| Pacientes que activan la alerta | 13,6 % | 12,0–15,2 % | Proporción de la cohorte de prueba con alerta |

El Brier crítico es 0,124; debe interpretarse junto con la prevalencia de críticos.

Los intervalos expresan la incertidumbre estadística en la prueba. La sensibilidad crítica, por ejemplo, es compatible con valores entre 60,6 % y 70,7 %. Aunque el VPP de la alerta cumple el objetivo de 50 % como estimación puntual, su intervalo muestra que ese objetivo no está garantizado con la misma precisión en todas las muestras posibles.

**Calibración.** Las probabilidades estimadas son, en general, razonablemente interpretables, pero no perfectas: por ejemplo, para una probabilidad media de 7,9 %, la proporción real de críticos fue 11,8 %.

## 8. Valor frente a reglas simples y frente al triaje experto

Para una comparación justa, el modelo marca el mismo porcentaje de pacientes que cada regla.

| Método | % de pacientes marcados | Sensibilidad crítica | Especificidad crítica | VPP |
| --- | --- | --- | --- | --- |
| Regla de signos vitales | 15,3 % | 26,6 % | 87,2 % | 31,9 % |
| Modelo, mismo % marcado | 15,3 % | 41,2 % | 90,5 % | 49,5 % |
| Regla + conciencia + ambulancia | 33,7 % | 55,6 % | 71,2 % | 30,3 % |
| Modelo, mismo % marcado | 33,7 % | 67,0 % | 73,7 % | 36,5 % |

Con el mismo porcentaje de pacientes marcados, el modelo identifica más críticos y obtiene un VPP superior. Esto sugiere que el motivo de consulta, la edad y la combinación de variables aportan información adicional a los umbrales aislados de signos vitales. No implica reemplazar un protocolo clínico: indica una señal complementaria que merece evaluación prospectiva.

**Comparación con el triaje experto** (muestra de 243 pacientes de Corea):

| Indicador frente al experto | Enfermera | Modelo |
| --- | --- | --- |
| Kappa ponderado | 0,898 | 0,520 |
| Subtriaje grave | 0,062 | 0,066 |
| Sensibilidad crítica | 92,7 % | 82,9 % |

El acuerdo de la enfermera con el experto es mucho mayor que el del modelo, lo esperable porque ella puede valorar al paciente de forma más completa. El AUC del modelo fue 0,842 con la etiqueta de enfermería y 0,875 frente a la referencia experta, lo que sugiere que parte de los errores medidos contra enfermería puede reflejar discrepancias entre ambas etiquetas. La muestra es pequeña y coreana: no basta para demostrar que el sistema funcione igual con profesionales, protocolos y pacientes de Colombia.

## 9. Análisis de sesgo por subgrupo

Aquí «sesgo» significa diferencias de rendimiento entre subgrupos. Una diferencia no demuestra por sí sola una discriminación injusta: puede reflejar la prevalencia, la distribución clínica, diferencias en las etiquetas o problemas de representatividad. Aun así, es una señal que requiere investigación. Se evaluaron dos dimensiones: sexo y edad.

### 9.1. Por sexo

| Sexo registrado | n | % críticos | AUC | Sensibilidad crítica | Especificidad crítica | Kappa | Críticos como no críticos |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Femenino | 979 | 14,3 % | 0,751 | 64,3 % | 76,0 % | 0,368 | 9,3 % |
| Masculino | 882 | 22,9 % | 0,766 | 66,8 % | 71,5 % | 0,445 | 8,9 % |

La sensibilidad es 2,5 puntos mayor en hombres y la especificidad 4,5 puntos mayor en mujeres. La proporción de críticos también difiere (14,3 % en mujeres y 22,9 % en hombres), lo que importa porque el VPP y otras métricas dependen de la frecuencia de la categoría crítica en cada grupo. Las diferencias son moderadas y no bastan para afirmar discriminación por sexo, pero justifican calcular los intervalos de confianza por grupo, las tasas de falsos negativos y el rendimiento en pacientes con perfiles clínicos similares.

### 9.2. Por edad (hallazgo más preocupante)

| Grupo de edad | n | % críticos | AUC | Sensibilidad crítica | Especificidad crítica | Kappa | Críticos como no críticos |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 18–39 años | 683 | 12,9 % | 0,750 | 48,9 % | 85,7 % | 0,373 | 20,5 % |
| 40–64 años | 672 | 18,6 % | 0,756 | 68,8 % | 73,9 % | 0,426 | 6,4 % |
| 65 años o más | 506 | 25,5 % | 0,747 | 74,4 % | 55,7 % | 0,276 | 3,9 % |

- **18–39 años:** la sensibilidad crítica cae a 48,9 %: el modelo identifica aproximadamente la mitad de los críticos de este grupo, y el 20,5 % de los críticos jóvenes termina clasificado como no crítico. Su AUC (0,750) es similar al de los otros grupos, lo que muestra que un AUC estable no garantiza que el umbral elegido dé una sensibilidad adecuada en todos los subgrupos. Una explicación plausible es que, en los datos de entrenamiento, la edad aumenta la probabilidad de recibir una clasificación crítica; así, un paciente joven con signos vitales aparentemente estables puede quedar por debajo del umbral aunque tenga una necesidad clínica importante.
- **40–64 años:** rendimiento intermedio (sensibilidad 68,8 %; críticos como no críticos 6,4 %).
- **65 años o más:** la sensibilidad más alta (74,4 %) y la menor tasa de críticos como no críticos (3,9 %), pero la especificidad cae a 55,7 %: una parte considerable de los no críticos de este grupo se marca como crítica.

En la práctica, el equilibrio cambia con la edad: el modelo es más propenso a dejar escapar críticos jóvenes y a generar falsas alarmas en adultos mayores.

**En jóvenes el criterio del médico pesa más que el del modelo.**

## 10. Variables que más influyen

Los coeficientes de la regresión logística muestran qué variables empujan la predicción hacia la categoría crítica o la alejan de ella.

- **Hacia crítico:** motivos de alteración de conciencia o paro, motivo cardiovascular, psiquiátricos o relacionados con sustancias, llegada en ambulancia, motivo neurológico, edad y signos de alarma (presión arterial baja, frecuencia respiratoria alterada).
- **Hacia no crítico:** motivos musculoesqueléticos, de ojos/oído/dental, piel/alergia, trauma, digestivos y fiebre general.

Esto no significa que esos motivos nunca puedan ser una urgencia: indica que, en los datos usados, el triaje de referencia asignó con menor frecuencia la categoría crítica a esos motivos, dadas las demás variables. Los coeficientes representan asociaciones, no relaciones causales, y no reemplazan el juicio clínico.

## 11. Limitaciones y alcance de la validación clínica

- La sensibilidad crítica final (65,8 %) es inferior al objetivo aproximado de 70 % fijado en validación cruzada.
- La alerta en vivo detecta solo el 37,1 % de los críticos (VPP puntual 50,2 %); no puede ser el único mecanismo para reconocer urgencias.
- Hay falsos positivos: pacientes que recibirían una categoría de mayor urgencia.
- La sensibilidad es particularmente baja en pacientes jóvenes.
- Los datos provienen de Corea y Estados Unidos, no de una cohorte validada del hospital colombiano.
- El modelo reproduce la etiqueta de enfermería, que puede diferir de la valoración experta y de la evolución clínica posterior.
- Los signos de alarma, las categorías y los umbrales son criterios estadísticos del equipo de datos y no se han contrastado con el equipo clínico del hospital.
- Las métricas dependen de la calidad, representatividad y distribución de los datos disponibles.
- La prueba es una evaluación interna: no reemplaza una validación prospectiva con pacientes reales y un protocolo de supervisión definido.
- Solo adultos (≥ 18) y solo 12 variables: sin antecedentes ni nivel de conciencia.
- La equivalencia entre las escalas ESI y KTAS es un supuesto.
- Sin indicadores de faltantes por diseño (delatan el país). Si falta la SpO₂ se imputa y el sistema avisa qué datos faltaron.
- Un sexo no registrado se trata como femenino y se muestra un aviso.

Las categorías, los puntos de corte y los criterios de los umbrales se definieron con criterios estadísticos y no se presentan como clínicamente validados:

- Las tres categorías (crítico / medio / no crítico).
- Los puntos de corte de los 11 signos de alarma.
- La red de seguridad (SpO₂ < 88 %, PAS < 90 mmHg).
- Los criterios de los umbrales: 70 % de sensibilidad para "crítico" y VPP ≥ 0,50 para la alerta.

Esto es coherente con el uso del modelo: es un apoyo y la decisión final es del profesional.

## 12. Cómo se usa en el sistema (R10, R12)

1. `POST /ia/analizar/{documento}` lee las 12 variables de la historia (la edad se calcula desde la fecha de nacimiento).
2. **Minimización y seudonimización:** el payload solo contiene los campos de una lista blanca y un identificador seudónimo (HMAC-SHA256, `pac-…`); no viaja nombre ni documento. El payload exacto se guarda en `ia_payloads` y se puede ver en `GET /ia/reportes/{id}/payload`.
3. La API llama al servicio `ml` (`/predecir`) con el encabezado `X-Servicio-Token`.
4. Se crea un **reporte `pendiente`**; si corresponde, se crea una alerta y se publican los eventos tras confirmar la transacción (ver [`EVENTOS.md`](EVENTOS.md)).
5. Médico o especialista **aprueba o rechaza** (`PATCH /ia/reportes/{id}/aprobar|rechazar`). Solo la IA aprobada aparece en la historia clínica y en el PDF. Al aprobar se genera la factura de IA (ver [`CONTABILIDAD.md`](CONTABILIDAD.md)).

Las alertas y contadores solo consideran encuentros no finalizados.

## 13. Conclusión

La regresión logística con signos de alarma es una alternativa razonable para seguir investigando como herramienta de apoyo al pretriaje. En validación cruzada obtuvo un AUC crítico de 0,784, un VPP de 0,384 y un kappa ponderado de 0,437; en la prueba, un AUC de 0,765, una sensibilidad crítica de 65,8 % y un VPP de 36,3 %. El umbral se justifica explícitamente (sensibilidad crítica de aproximadamente 70 % en validación cruzada), la guarda evita enviar a «no crítico» a pacientes con probabilidad crítica apreciable y la red de seguridad fuerza la clasificación crítica ante saturación baja o hipotensión. Aun así, el rendimiento final cae ligeramente respecto a la validación y persisten falsos negativos.

La principal limitación es la edad: los pacientes de 18 a 39 años tienen una sensibilidad crítica de solo 48,9 %, frente a 74,4 % en mayores de 65 años, grupo en el que la especificidad baja a 55,7 % (más falsas alarmas). También hay diferencias moderadas por sexo.

El modelo debe considerarse un sistema de apoyo que requiere validación clínica local, evaluación de seguridad por subgrupo y supervisión del personal sanitario. No hay evidencia suficiente para usarlo como sustituto autónomo del triaje profesional: su implementación debe condicionarse a una validación local, centrada en los falsos negativos críticos y en los pacientes jóvenes.

## Documentos relacionados

[`DATASETS.md`](DATASETS.md) (origen y filtros de los datos) · [`EVENTOS.md`](EVENTOS.md) · [`CONTABILIDAD.md`](CONTABILIDAD.md) · [`LEYES.md`](LEYES.md) · [README](../README.md)
