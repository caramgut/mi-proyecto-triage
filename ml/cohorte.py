"""Cohorte sintética creada por AUMENTO DE DATOS dentro de cada grupo (R07).

Este módulo solo produce variables clínicas: la identidad (nombre, documento) la inventa la API.
"""
import numpy as np
import pandas as pd
from sklearn.neighbors import NearestNeighbors

import clusters
from datos import LIMITES, NUM, cargar, dividir

COHORTE = "triaje-sint-2026"
N_PACIENTES = 200
K_VECINOS = 5
SEMILLA_COHORTE = 2026


def _clave(df):
    return df[NUM].astype(float).round(1).fillna(-999).apply(lambda f: "|".join(map(str, f)), axis=1)


def generar(n=N_PACIENTES, semilla=SEMILLA_COHORTE):
    _, base = dividir()
    base = base.copy()
    base["cluster"] = clusters.asignar(base)
    Z = clusters.transformar(base)          # mismo espacio en que se agrupó (edad, FC, FR, PAM, T°, SpO2)
    reales = set(_clave(cargar()))

    train, _ = dividir()
    proporcion = pd.Series(clusters.asignar(train)).value_counts(normalize=True).sort_index()
    cuota = np.maximum(10, np.round(proporcion * n)).astype(int)
    cuota.iloc[cuota.argmax()] -= cuota.sum() - n                    # que sumen exactamente n

    rng = np.random.default_rng(semilla)
    nuevos = []
    for c, q in cuota.items():
        grupo = base[base["cluster"] == c]
        for _ in range(q):
            i = rng.choice(grupo.index)
            fila = grupo.loc[i]
            candidatos = grupo[(grupo["y_triaje"] == fila["y_triaje"]) & (grupo.index != i)]
            if len(candidatos) == 0:                                 # nivel muy raro en ese grupo
                candidatos = grupo[grupo.index != i]
            nn = NearestNeighbors(n_neighbors=min(K_VECINOS, len(candidatos))).fit(Z[candidatos.index])
            _, idx = nn.kneighbors(Z[[i]])
            vecino = candidatos.iloc[rng.choice(idx[0])]
            for _intento in range(20):                               # si sale idéntico a un real, se repite
                u = rng.random()
                nuevo = fila.copy()
                for v in NUM:
                    if pd.notna(fila[v]) and pd.notna(vecino[v]):
                        lo, hi, dec = LIMITES[v]
                        nuevo[v] = round(float(np.clip(fila[v] + u * (vecino[v] - fila[v]), lo, hi)), dec)
                if _clave(nuevo.to_frame().T).iloc[0] not in reales:
                    break
            nuevos.append({
                "indice": len(nuevos) + 1,
                "cluster": int(c),
                "grupo": clusters.nombre(c),
                "nivel_triaje_referencia": int(fila["y_triaje"]),
                "fila_base": int(i),
                "u": round(float(u), 3),
                **{v: (None if pd.isna(nuevo[v]) else float(nuevo[v])) for v in NUM},
                "sexo": fila["sexo"],
                "llegada_ambulancia": None if pd.isna(fila["llegada_ambulancia"]) else int(fila["llegada_ambulancia"]),
                "lesion": None if pd.isna(fila["lesion"]) else int(fila["lesion"]),
                "motivo_categoria": fila["motivo_categoria"],
            })
    return {"cohorte": COHORTE, "n": len(nuevos), "pacientes": nuevos}
