# Modelo de apoyo al triaje

> **La IA es un apoyo a la decisión.** El profesional aprueba o rechaza cada reporte; el sistema nunca cambia el nivel de triaje por sí solo.

Versión del modelo: `logreg-alarmas-3cat-3.0` (`ml/modelo.py`). Se entrena al arrancar el servicio `ml` a partir de `ml/data/triaje_supervisado_limpio.csv`. Las cifras de este documento salen de `back/preprocesamiento/salida_ia/metricas_modelo.json`. Origen y filtros de los datos: `docs/DATASETS.md`.

## 1. Qué hace

Dado un paciente adulto con 12 datos (edad, sexo, llegada en ambulancia, lesión, FC, FR, PAS, PAD, temperatura, SpO₂, dolor y motivo de consulta), estima la probabilidad de tres categorías:

| Categoría | Niveles de triaje |
|---|---|
| Crítico | 1–2 |
| Medio | 3 |
| No crítico | 4–5 |

Devuelve la categoría, las probabilidades, los factores que empujaron hacia "crítico" en ese paciente y un indicador de alerta.

## 2. Por qué regresión logística

Se compararon cinco modelos con validación cruzada de 5 pliegues (7.443 registros de entrenamiento) y en el conjunto de prueba:

| Modelo | AUC crítico (CV) | AUC crítico (prueba) |
|---|---|---|
| **Regresión logística** | **0,784** | 0,765 |
| SVM RBF | 0,776 | 0,766 |
| Lineal | 0,768 | 0,743 |
| Árbol | 0,730 | 0,744 |
| KNN | 0,729 | 0,721 |

Se eligió la logística porque rinde igual o mejor y además: (a) sus probabilidades están **calibradas** (por deciles siguen la diagonal), lo que permite usar umbrales con significado clínico; (b) es **explicable**: el aporte de cada variable se puede mostrar al médico; (c) es **rápida**: 0,15 s de entrenamiento frente a 14,5 s del SVM.

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

## 3. Regla de decisión y umbrales (R20)

La categoría final no es simplemente la de mayor probabilidad. Se aplica esta regla (`U_*` en `ml/modelo.py`):

1. **Crítico** si P(crítico) ≥ **0,185** o se cumple la **red de seguridad** (SpO₂ < 88 % o PAS < 90 mmHg). El 0,185 es el umbral más alto que todavía detecta ≥ 70 % de los críticos en validación cruzada.
2. **No crítico** si P(no crítico) ≥ **0,37** y P(crítico) < **0,10** (la "guarda": nadie con 10 % o más de probabilidad crítica se etiqueta como no crítico).
3. **Medio** en los demás casos.

**Alerta en vivo (R20)**: se dispara si P(crítico) ≥ **0,38** o hay red de seguridad. El 0,38 es el umbral más bajo con valor predictivo positivo ≥ 0,50.

### Por qué un paciente puede salir "Crítico" con 30 % y "Medio" con 58 %

Porque el umbral de categoría crítica (0,185) es mucho menor que el de alerta (0,38). Se prefiere marcar "crítico" a más pacientes para no pasar por alto críticos (sensibilidad), a costa de más falsos positivos. En ese ejemplo el paciente queda clasificado "Crítico", se pide revisión médica, pero **no se dispara la alerta de R20**. No es una contradicción: son dos reglas con objetivos distintos.

## 4. Desempeño

Conjunto de prueba, 1.861 pacientes, regla final:

| Métrica | Valor |
|---|---|
| AUC crítico | **0,765** (IC 95 %: 0,735–0,794) |
| Kappa ponderado | 0,409 |
| F1 macro | 0,517 |
| Sensibilidad crítica | 0,658 |
| VPP crítico | 0,363 |
| Sensibilidad no crítico | 0,511 |
| Críticos clasificados como no críticos (subtriaje grave) | **0,091** |
| Alerta: sensibilidad | 0,371 (IC 95 %: 0,320–0,423) |
| Alerta: VPP | 0,502 |
| Pacientes que activan la alerta | 13,6 % |

Validación cruzada (entrenamiento, 5 pliegues): AUC 0,784 ± 0,013; VPP 0,384; kappa 0,437; subtriaje grave 0,110; sensibilidad 0,703; especificidad 0,746; F1 0,532; Brier 0,124.

**Lectura honesta de estas cifras.** El modelo ordena el riesgo razonablemente (AUC 0,77), pero **no es un detector de críticos**: la alerta solo detecta cerca de 4 de cada 10 críticos (0,371) y la mitad de los avisos son falsos (VPP 0,502). Por eso la alerta complementa, y no reemplaza, la observación clínica.

**Comparación con una regla simple de signos vitales.** Marcando el mismo porcentaje de pacientes (15,3 %), el modelo detecta 41,2 % de los críticos y la regla simple 26,6 %.

**Comparación con expertos (KTAS, 243 pacientes).** Frente al nivel asignado por un médico experto, la concordancia (kappa) de la enfermera de triaje es 0,898 y la del modelo 0,520. El modelo no iguala a una enfermera entrenada; su valor es de apoyo.

## 5. Sesgo

Resultados de prueba por subgrupo:

| Subgrupo | n | AUC | Sensibilidad crítica | Crítico → no crítico |
|---|---|---|---|---|
| Fuente KTAS | 246 | 0,845 | 0,791 | 0,047 |
| Fuente NHAMCS | 1.615 | 0,754 | 0,639 | 0,097 |
| Mujeres | 979 | 0,751 | 0,643 | — |
| Hombres | 882 | 0,766 | 0,668 | — |
| 18–39 años | 683 | 0,750 | **0,489** | **0,205** |
| 40–64 años | 672 | — | 0,688 | 0,064 |
| ≥ 65 años | 506 | — | 0,744 | 0,039 (especificidad 0,557) |

- **Hallazgo principal:** en adultos jóvenes el modelo subestima: de cada 5 críticos de 18–39 años, uno se clasifica "no crítico". Son pacientes críticos con signos vitales estables, que el modelo no distingue con solo 12 variables (ver "Jóvenes con signos estables" en `DATASETS.md`). **En jóvenes el criterio del médico pesa más que el del modelo.**
- En mayores de 65 el modelo es sensible pero poco específico (más falsos positivos).
- Las diferencias entre mujeres y hombres son pequeñas.
- El modelo rinde mejor en KTAS (n = 246) que en NHAMCS, pero KTAS es una muestra pequeña y su intervalo de confianza es amplio; no se debe concluir que funciona mejor con un tipo de paciente.

## 6. Limitaciones

1. **Etiqueta = triaje de enfermería**, no desenlace clínico. El modelo reproduce a la enfermera, con sus errores.
2. Datos de Corea y EE. UU.; **no validados en Tumaco**.
3. Solo adultos (≥ 18).
4. Solo 12 variables: sin antecedentes, sin nivel de conciencia, sin síntomas detallados.
5. Equivalencia ESI/KTAS asumida.
6. Sin indicadores de faltantes por diseño (delatan el país). Si falta la SpO₂ se imputa; el sistema avisa qué datos faltaron.
7. Un sexo no registrado se trata como femenino y se muestra un aviso.

## 7. Alcance de la validación clínica

Los puntos de corte y las categorías se definieron con criterios estadísticos del equipo de datos y no se han contrastado con profesionales clínicos del hospital. Por eso no se presentan como clínicamente validados:

- Las tres categorías (crítico / medio / no crítico).
- Los puntos de corte de los 11 signos de alarma.
- La red de seguridad (SpO₂ < 88 %, PAS < 90 mmHg).
- Los criterios de los umbrales: 70 % de sensibilidad para "crítico" y VPP ≥ 0,50 para la alerta.

Esto es coherente con el uso del modelo: es un apoyo y la decisión final es del profesional.

## 8. Cómo se usa en el sistema (R10, R12)

1. `POST /ia/analizar/{documento}` lee las 12 variables de la historia (la edad se calcula desde la fecha de nacimiento).
2. **Minimización y seudonimización:** el payload solo contiene los campos de una lista blanca y un identificador seudónimo (HMAC-SHA256, `pac-…`); no viaja nombre ni documento. El payload exacto se guarda en `ia_payloads` y se puede ver en `GET /ia/reportes/{id}/payload`.
3. La API llama al servicio `ml` (`/predecir`) con el encabezado `X-Servicio-Token`.
4. Se crea un **reporte `pendiente`**; si corresponde, se crea una alerta y se publican los eventos tras confirmar la transacción.
5. Médico o especialista **aprueba o rechaza** (`PATCH /ia/reportes/{id}/aprobar|rechazar`). Solo la IA aprobada aparece en la historia clínica y en el PDF. Al aprobar se genera la factura de IA (ver `CONTABILIDAD.md`).

Las alertas y contadores solo consideran encuentros no finalizados.
