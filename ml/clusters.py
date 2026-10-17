"""Clustering NO supervisado de los pacientes reales (R07): k-means con k = 5.
Se agrupa con edad, FC, FR, PAM, temperatura y SpO2, sin la etiqueta ni el país.
"""
import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.impute import SimpleImputer
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from datos import NUM, SEMILLA, cargar, dividir

K = 5
VARS = ["edad", "fc", "fr", "pam", "temp_c", "spo2"]

DESCRIPCION = {
    "Compromiso respiratorio": "Hipoxemia y taquipnea; el grupo más grave",
    "Taquicardia / febril": "Frecuencia cardiaca alta y temperatura algo elevada en adultos (zona de confusión entre niveles 2 y 3)",
    "Adultos mayores estables": "Signos normales; el riesgo viene de la edad y el motivo (zona de confusión entre niveles 2 y 3)",
    "Hipertensión arterial": "Presión arterial elevada sin otros signos de alarma (zona de confusión entre niveles 2 y 3)",
    "Jóvenes con signos estables": "El grupo más grande y menos grave; zona de confusión principal: el modelo subtriaja a sus pocos críticos",
}

_estado = {"escala": None, "kmeans": None, "nombre": None}


def _con_pam(df: pd.DataFrame) -> pd.DataFrame:
    if "pam" not in df:
        df = df.assign(pam=(df["pas"] + 2 * df["pad"]) / 3)
    return df


def entrenar():
    train, _ = dividir()
    escala = make_pipeline(SimpleImputer(strategy="median"), StandardScaler()).fit(train[VARS])
    kmeans = KMeans(n_clusters=K, n_init=10, random_state=SEMILLA).fit(escala.transform(train[VARS]))

    # Los números de k-means son arbitrarios: se nombran según su perfil (igual que en el cuaderno)
    med = train.assign(c=kmeans.labels_).groupby("c")[NUM].median()
    nombre = {med["spo2"].idxmin(): "Compromiso respiratorio"}
    for col, fn, etiqueta in [("edad", "idxmin", "Jóvenes con signos estables"),
                              ("pas", "idxmax", "Hipertensión arterial"),
                              ("edad", "idxmax", "Adultos mayores estables")]:
        resto = med.drop(index=list(nombre))
        nombre[getattr(resto[col], fn)()] = etiqueta
    nombre[med.drop(index=list(nombre)).index[0]] = "Taquicardia / febril"
    _estado.update(escala=escala, kmeans=kmeans, nombre={int(k): v for k, v in nombre.items()})


def _listo():
    if _estado["kmeans"] is None:
        entrenar()


def transformar(df: pd.DataFrame) -> np.ndarray:
    _listo()
    return _estado["escala"].transform(_con_pam(df)[VARS])


def asignar(df: pd.DataFrame) -> np.ndarray:
    """Grupo de cada fila (sirve para pacientes reales, sintéticos o nuevos)."""
    return _estado["kmeans"].predict(transformar(df))


def nombre(cluster: int) -> str:
    _listo()
    return _estado["nombre"][int(cluster)]


def describir():
    """Grupos con su descripción y los pacientes REALES del dataset que caen en cada uno."""
    _listo()
    d = cargar().copy()
    d["cluster"] = asignar(d)
    grupos = []
    for c in range(K):
        g = d[d["cluster"] == c]
        n = _estado["nombre"][c]
        grupos.append({
            "cluster": c,
            "nombre": n,
            "descripcion": DESCRIPCION[n],
            "reales": int(len(g)),
            "pct_critico": round(float((g["y_triaje"] <= 2).mean() * 100), 1),
            "mediana": {v: round(float(g[v].median()), 1) for v in NUM},
        })
    return {"algoritmo": "k-means", "k": K, "variables": VARS,
            "criterio_k": "máximo local de silueta, estabilidad bootstrap (ARI ≈ 0,9) y grupos clínicamente distintos",
            "grupos": grupos}
