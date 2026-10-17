"""Es la regresión logística + signos de alarma elegida en el cuaderno
ia_triaje_supervisado_y_clusters.ipynb. 
"""
import datetime as dt

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import cohen_kappa_score, roc_auc_score
from sklearn.pipeline import Pipeline

from datos import (ALARMAS, BIN, NOMBRE, NOMBRE_ALARMA, NUM, PREDICTORES, UNIDAD, dividir,
                   preprocesador, red_seguridad, signos_alarma)

VERSION = "logreg-alarmas-3cat-3.0"
CATEGORIAS = ["critico", "medio", "no_critico"]          # códigos 0, 1, 2

# Regla de decisión (cuaderno, Bloque 11). Criterios escritos antes de mirar la prueba:
U_CRITICO = 0.185      # el umbral más alto que todavía detecta >= 70 % de los críticos
GUARDA = 0.10          # nadie con P(crítico) >= 10 % se etiqueta "no crítico"
U_NO_CRITICO = 0.37    # maximiza el kappa con la guarda puesta
U_ALERTA = 0.38        # el más bajo con VPP >= 0,50 de la alerta completa (modelo + red de seguridad) (R20)

_estado = {"modelo": None, "metricas": None, "peso_critico": None, "nombres": None}


def categoria_de_nivel(nivel):
    nivel = np.asarray(nivel)
    return np.where(nivel <= 2, 0, np.where(nivel == 3, 1, 2))


def construir():
    return Pipeline([("prep", preprocesador()), ("modelo", LogisticRegression(max_iter=5000))])


def clasificar(P, X):
    """0 = crítico, 1 = medio, 2 = no crítico. La red de seguridad fuerza 'crítico'."""
    cat = np.where(P[:, 0] >= U_CRITICO, 0, np.where((P[:, 2] >= U_NO_CRITICO) & (P[:, 0] < GUARDA), 2, 1))
    seguridad = ((X["spo2"] < 88) | (X["pas"] < 90)).values
    return np.where(seguridad, 0, cat)


def alerta(P, X):
    return (P[:, 0] >= U_ALERTA) | ((X["spo2"] < 88) | (X["pas"] < 90)).values


def entrenar():
    train, test = dividir()
    modelo = construir().fit(train[PREDICTORES], categoria_de_nivel(train["y_triaje"]))
    y = categoria_de_nivel(test["y_triaje"])
    P = modelo.predict_proba(test[PREDICTORES])
    cat, al = clasificar(P, test), alerta(P, test)
    metricas = {
        "version": VERSION,
        "algoritmo": "Regresión logística multinomial + 11 signos de alarma clínicos (scikit-learn)",
        "categorias": {"critico": "niveles 1-2", "medio": "nivel 3", "no_critico": "niveles 4-5"},
        "entrenado": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "n_entrenamiento": int(len(train)),
        "n_prueba": int(len(test)),
        "regla": {"U_CRITICO": U_CRITICO, "GUARDA": GUARDA, "U_NO_CRITICO": U_NO_CRITICO, "U_ALERTA": U_ALERTA,
                  "red_seguridad": "SpO2 < 88 % o PAS < 90 mmHg"},
        "prueba": {
            "auc_critico": round(float(roc_auc_score(y == 0, P[:, 0])), 3),
            "kappa_ponderado": round(float(cohen_kappa_score(y, cat, weights="quadratic")), 3),
            "sensibilidad_critica": round(float(np.mean(cat[y == 0] == 0)), 3),
            "vpp_critico": round(float(np.mean(y[cat == 0] == 0)), 3),
            "criticos_como_no_criticos": round(float(np.mean(cat[y == 0] == 2)), 3),
            "alerta_sensibilidad": round(float(np.mean(al[y == 0])), 3),
            "alerta_vpp": round(float(np.mean(y[al] == 0)), 3),
        },
    }
    # Peso de cada columna transformada hacia "crítico" frente a las otras dos categorías: sirve para explicar
    prep = modelo.named_steps["prep"]
    coef = modelo.named_steps["modelo"].coef_
    nombres = NUM + BIN + [f"motivo={m}" for m in prep.named_transformers_["cat"].categories_[0]] + \
        [f"alarma={a}" for a in ALARMAS]
    _estado.update(modelo=modelo, metricas=metricas, nombres=nombres,
                   peso_critico=coef[0] - coef[1:].mean(axis=0))
    return metricas


def metricas():
    if _estado["metricas"] is None:
        entrenar()
    return _estado["metricas"]


# Cada signo vital se explica JUNTO con sus alarmas: para el médico, "PAS 75 mmHg" es un solo dato.
# Separados, el término lineal ("más PAS, más urgencia") y la alarma ("PAS < 90") se contradicen.
GRUPOS_VITALES = {
    "edad": ["edad", "alarma=mayor_65"],
    "fc": ["fc", "alarma=fc_alta", "alarma=fc_baja"],
    "fr": ["fr", "alarma=fr_alterada"],
    "pas": ["pas", "pad", "alarma=pas_baja", "alarma=pas_muy_alta"],   # la presión es UN dato: PAS/PAD
    "temp_c": ["temp_c", "alarma=fiebre", "alarma=hipotermia"],
    "spo2": ["spo2", "alarma=spo2_baja"],
    "dolor_nrs": ["dolor_nrs", "alarma=dolor_intenso"],
}


def _factores(fila):
    """Qué variables empujaron hacia (o lejos de) lo crítico en ESTE paciente."""
    x = _estado["modelo"].named_steps["prep"].transform(fila)[0]
    aporte = dict(zip(_estado["nombres"], x * _estado["peso_critico"]))
    alarmas = dict(zip(ALARMAS, signos_alarma(fila[NUM])[0]))
    p = fila.iloc[0]
    factores = []

    for variable, columnas in GRUPOS_VITALES.items():
        if pd.isna(p[variable]):
            continue              # un dato imputado no se presenta como factor del paciente
        presentes = [NOMBRE_ALARMA[c.split("=")[1]] for c in columnas
                     if c.startswith("alarma=") and alarmas[c.split("=")[1]]]
        if variable == "pas" and pd.notna(p["pad"]):
            texto = f"presión arterial {p['pas']:g}/{p['pad']:g} mmHg"
        else:
            texto = f"{NOMBRE[variable]} {p[variable]:g}{UNIDAD.get(variable, '')}"
        if presentes:
            texto += f" (alarma: {', '.join(presentes)})"
        columnas = [c for c in columnas if c.startswith("alarma=") or pd.notna(p[c])]
        factores.append({"variable": variable, "texto": texto, "aporte": sum(aporte[c] for c in columnas)})

    if alarmas["choque"]:
        factores.append({"variable": "choque", "texto": f"índice de shock (FC/PAS) {p['fc'] / p['pas']:.2f} ≥ 1",
                         "aporte": aporte["alarma=choque"]})
    for variable in BIN:
        if pd.notna(p[variable]):
            factores.append({"variable": variable, "texto": NOMBRE[variable] + (": sí" if p[variable] else ": no"),
                             "aporte": aporte[variable]})
    factores.append({"variable": "motivo_categoria",
                     "texto": f"motivo de consulta: {p['motivo_categoria'].replace('_', ' ')}",
                     "aporte": aporte[f"motivo={p['motivo_categoria']}"]})

    factores = [{**f, "aporte": round(float(f["aporte"]), 3)} for f in factores if abs(f["aporte"]) >= 0.05]
    return sorted(factores, key=lambda f: -abs(f["aporte"]))


def predecir(variables: dict):
    """Recibe SOLO las 12 variables clínicas (sin identidad) y devuelve la categoría propuesta."""
    if _estado["modelo"] is None:
        entrenar()
    fila = pd.DataFrame([variables])[PREDICTORES]
    # Con un solo paciente, una columna vacía (None) quedaría como texto: se fuerza a número
    fila[NUM + BIN] = fila[NUM + BIN].astype(float)
    P = _estado["modelo"].predict_proba(fila)
    p_critico = float(P[0, 0])
    seguridad = red_seguridad(fila)
    motivo_alerta = ([f"P(crítico) {p_critico:.0%} ≥ {U_ALERTA:.0%}"] if p_critico >= U_ALERTA else []) + \
        [f"red de seguridad: {m}" for m in seguridad]
    factores = _factores(fila)
    alarmas = signos_alarma(fila[NUM])[0]
    return {
        "modelo_version": VERSION,
        "categoria": CATEGORIAS[int(clasificar(P, fila)[0])],
        "probabilidades": {c: round(float(p), 4) for c, p in zip(CATEGORIAS, P[0])},
        "p_critico": round(p_critico, 4),
        "alerta_critica": bool(motivo_alerta),
        "motivo_alerta": motivo_alerta,
        "red_seguridad": seguridad,
        "signos_alarma": [NOMBRE_ALARMA[a] for a, v in zip(ALARMAS, alarmas) if v],
        "factores_suben": [f for f in factores if f["aporte"] > 0][:3],
        "factores_bajan": [f for f in factores if f["aporte"] < 0][:3],
        "faltantes": [v for v in NUM if pd.isna(fila.iloc[0][v])],
    }
