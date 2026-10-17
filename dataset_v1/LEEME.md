# Homologación de datasets de triaje (KTAS Corea + NHAMCS EE. UU. 2022)

**Archivos**
- `triaje_homologado.csv`: 14.266 visitas (1.267 KTAS + 12.999 NHAMCS, edad >= 16) con el mismo esquema. Columna `fuente` indica el origen.
- `homologacion_variables.xlsx`: tabla variable a variable, categorías de motivo de consulta (y cómo se asignó cada texto/código), rangos de limpieza y comparación entre fuentes.
- `diccionario_ED2022.xlsx`: diccionario del `.sav` (913 variables con etiqueta y significado de cada código). Es la descripción que faltaba.
- `homologar_triaje.py` + `sav_reader.py`: reproducen todo. Ejecutar: `python homologar_triaje.py data.csv ed2022-spss.sav salida/` (necesita pandas, numpy, openpyxl).
- `pruebas/`: los dos experimentos que respaldan la recomendación de cómo combinar (necesitan scikit-learn y que exista `salida/triaje_homologado.csv`).

**Datos faltantes esperados (no son error)**
- `triaje_enfermeria`/`emergencia`: NaN en ~35 % de NHAMCS (hospitales sin triaje o dato desconocido).
- `mental_avpu`: solo existe en KTAS. `triaje_experto`: solo KTAS. `peso_encuesta`: solo NHAMCS.
- `dolor_nrs`: ~40 % desconocido en NHAMCS. `spo2`: ~55 % faltante en KTAS.
