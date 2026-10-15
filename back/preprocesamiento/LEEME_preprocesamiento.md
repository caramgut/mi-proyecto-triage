# Preprocesamiento para aprendizaje supervisado

Entrada: `../triaje_homologado.csv`. Reproducir: `python preprocesamiento_supervisado.py ../triaje_homologado.csv salida/` (pandas, numpy, scikit-learn).

## Qué archivo usar
| Archivo | Para qué |
|---|---|
| `triaje_train_listo.csv` / `triaje_test_listo.csv` | Entrenar y evaluar de inmediato (sin nulos, escalado, one-hot). 7.443 y 1.861 filas |
| `triaje_supervisado_limpio.csv` | Versión sin imputar y con texto; columna `split` (train/test) para que todos usen la misma partición |
| `preprocesador.joblib` | Pipeline ajustado con el entrenamiento, para un paciente nuevo en la API: `transformar(joblib.load(...), df)` (función del .py; mismo scikit-learn 1.8). Hay que pasar las 12 columnas crudas, con vacíos como `NaN` |
| `preprocesamiento_supervisado.py` | Reproduce todo; `construir_preprocesador()` para usarlo dentro de `Pipeline` y validación cruzada |
| `trazabilidad_filtros.csv` | Filas quitadas en cada paso |

**Validación cruzada:** no uses los CSV ya transformados; usa `Pipeline([("prep", construir_preprocesador()), ("modelo", ...)])` para que mediana y escala se recalculen en cada partición.

## Pasos y filas
14.266 de partida → 13.852 (se quitan 414 menores de 18) → 9.415 (se quitan 4.437 sin nivel de triaje: sin etiqueta no hay aprendizaje supervisado) → 9.317 (98 con 3 o más de 6 signos vitales faltantes) → 9.304 (13 duplicados exactos).

## Columnas
**Objetivos** (no usar como predictores): `y_triaje` (1–5, 1 = más urgente), `y_emergencia` (1 si triaje 1–3), `y_hospitalizado` (0/1; vacío en 8,8 % de las filas: quitar esas filas solo al entrenar este objetivo).
**Metadatos:** `fuente` (no es predictor), `peso_fuente` (solo en train; opcional, hace que KTAS y NHAMCS pesen igual).

| Predictor | Tratamiento |
|---|---|
| `edad`, `fc`, `fr`, `pas`, `pad`, `temp_c`, `spo2`, `dolor_nrs` | Mediana del entrenamiento para faltantes, luego estandarizar (media 0, desviación 1) |
| `llegada_ambulancia`, `lesion` | 0/1; faltantes con el valor más frecuente |
| `sexo_M` | 1 = hombre, 0 = mujer |
| `spo2_faltante`, `dolor_nrs_faltante`, `lesion_faltante` | 1 si el dato original faltaba (más de 5 % de faltantes en alguna fuente) |
| `motivo_*` (13 columnas) | One-hot de la categoría de motivo de consulta; sin dato = `otros` |

Excluidas por no estar en ambos datasets o por ser redundantes: `triaje_experto`, `mental_avpu`, `peso_encuesta`, `motivo_original` (texto), `id_original`, `dolor_si`.
