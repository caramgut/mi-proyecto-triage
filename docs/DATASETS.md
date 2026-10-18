# Datasets del proyecto

## Imagen

**Estado:** dataset público real en selección.

La fuente definitiva, URL, licencia, número de imágenes cargadas y justificación clínica se completarán antes de la entrega. Las imágenes seleccionadas se cargarán en Orthanc PACS y se vincularán a pacientes para cumplir R06.

## Tabular

Se usa una base homologada de triaje construida a partir de **KTAS (Corea)** y **NHAMCS 2022 (Estados Unidos)**. La base homologada contiene 14.266 visitas antes de filtros y 9.304 registros finales para el modelado supervisado.

- Archivo homologado: `dataset_v1/triaje_homologado.csv`.
- Entrenamiento: 7.443 registros.
- Prueba: 1.861 registros.
- Variables clínicas principales: edad, frecuencia cardiaca, frecuencia respiratoria, presión arterial, temperatura, SpO2, dolor, ambulancia, lesión, sexo y motivo de consulta.
- Clustering: k-means con **k = 5**.
- Criterio de k: silueta, estabilidad bootstrap (ARI aproximado 0,9) y separación clínica interpretable.
- Los pacientes generados por aumento quedan identificados con `origen = sintetico` y asociados a su cluster.

> Pendiente documental: agregar las URLs y licencias exactas de KTAS y NHAMCS utilizadas por el equipo.
