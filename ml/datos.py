
from pathlib import Path

import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import FunctionTransformer, OneHotEncoder, StandardScaler

RUTA = Path(__file__).parent / "data" / "triaje_supervisado_limpio.csv"
SEMILLA = 42

# Los 12 predictores. Ninguno identifica a la persona (R12).
NUM = ["edad", "fc", "fr", "pas", "pad", "temp_c", "spo2", "dolor_nrs"]
BIN = ["llegada_ambulancia", "lesion", "sexo_M"]
CAT = ["motivo_categoria"]
PREDICTORES = NUM + BIN + CAT

MOTIVOS = ["cardiovascular", "respiratorio", "digestivo", "neurologico", "conciencia_paro",
           "fiebre_general", "trauma", "musculoesqueletico", "genitourinario_gineco",
           "psiquiatrico_sustancias", "piel_alergia", "orl_ojos_dental", "otros"]

# Signos de alarma: zonas de peligro de las escalas de triaje (cuaderno, Bloque 3)
# 11 alarmas SIN redundancias: variantes más extremas (SpO2 < 88, FC ≥ 130...) se repartían el peso
# con signos opuestos y producían explicaciones incoherentes (cuaderno, Bloque 3).
ALARMAS = ["spo2_baja", "fr_alterada", "fc_alta", "fc_baja", "pas_baja", "pas_muy_alta",
           "fiebre", "hipotermia", "choque", "dolor_intenso", "mayor_65"]
NOMBRE_ALARMA = {
    "spo2_baja": "SpO2 < 92 %", "fr_alterada": "FR ≥ 24 o < 10 rpm", "fc_alta": "FC ≥ 110 lpm",
    "fc_baja": "FC < 50 lpm", "pas_baja": "PAS < 90 mmHg", "pas_muy_alta": "PAS ≥ 200 mmHg",
    "fiebre": "temperatura ≥ 38 °C", "hipotermia": "temperatura < 35,5 °C",
    "choque": "índice de shock (FC/PAS) ≥ 1", "dolor_intenso": "dolor ≥ 7/10", "mayor_65": "edad ≥ 65 años",
}

# Rango plausible y decimales de cada variable numérica (hoja Rangos_plausibles del biomédico)
LIMITES = {"edad": (18, 100, 0), "fc": (20, 250, 0), "fr": (4, 80, 0), "pas": (40, 300, 0),
           "pad": (20, 200, 0), "temp_c": (30, 44, 1), "spo2": (50, 100, 0), "dolor_nrs": (0, 10, 0)}

NOMBRE = {"edad": "edad", "fc": "frecuencia cardiaca", "fr": "frecuencia respiratoria",
          "pas": "presión sistólica", "pad": "presión diastólica", "temp_c": "temperatura",
          "spo2": "SpO2", "dolor_nrs": "dolor", "llegada_ambulancia": "llegada en ambulancia",
          "lesion": "lesión", "sexo_M": "sexo masculino", "motivo_categoria": "motivo de consulta"}
UNIDAD = {"edad": " años", "fc": " lpm", "fr": " rpm", "pas": " mmHg", "pad": " mmHg",
          "temp_c": " °C", "spo2": " %", "dolor_nrs": "/10"}

_cache = {}


def cargar():
    """Lee el CSV una sola vez y deja las columnas como las espera el modelo."""
    if "d" not in _cache:
        d = pd.read_csv(RUTA)
        d["sexo_M"] = (d["sexo"] == "M").astype(int)
        d["motivo_categoria"] = d["motivo_categoria"].fillna("otros")
        d["pam"] = (d["pas"] + 2 * d["pad"]) / 3
        _cache["d"] = d
    return _cache["d"]


def dividir():
    """La MISMA partición train/test que preparó el biomédico (columna split)."""
    d = cargar()
    return d[d["split"] == "train"].reset_index(drop=True), d[d["split"] == "test"].reset_index(drop=True)


def signos_alarma(X):
    """Un dato faltante NO cuenta como alarma (comparar NaN da False)."""
    X = pd.DataFrame(X, columns=NUM).astype(float)
    f = pd.DataFrame(index=X.index)
    f["spo2_baja"] = X.spo2 < 92
    f["fr_alterada"] = (X.fr >= 24) | (X.fr < 10)
    f["fc_alta"], f["fc_baja"] = X.fc >= 110, X.fc < 50
    f["pas_baja"], f["pas_muy_alta"] = X.pas < 90, X.pas >= 200
    f["fiebre"], f["hipotermia"] = X.temp_c >= 38, X.temp_c < 35.5
    f["choque"] = X.fc / X.pas >= 1
    f["dolor_intenso"], f["mayor_65"] = X.dolor_nrs >= 7, X.edad >= 65
    return f[ALARMAS].astype(float).values


def red_seguridad(X: pd.DataFrame):
    """Signos que disparan la alerta sin importar la probabilidad del modelo."""
    motivos = []
    fila = X.iloc[0]
    if pd.notna(fila["spo2"]) and fila["spo2"] < 88:
        motivos.append("SpO2 < 88 %")
    if pd.notna(fila["pas"]) and fila["pas"] < 90:
        motivos.append("PAS < 90 mmHg")
    return motivos


def preprocesador():
    """Mediana + escala para numéricas, moda para binarias, one-hot para el motivo y signos de alarma.
    Sin indicadores de faltante: delatan el país de origen (cuaderno, Bloque 2)."""
    return ColumnTransformer([
        ("num", make_pipeline(SimpleImputer(strategy="median"), StandardScaler()), NUM),
        ("bin", SimpleImputer(strategy="most_frequent"), BIN),
        ("cat", OneHotEncoder(categories=[MOTIVOS], handle_unknown="ignore", sparse_output=False), CAT),
        ("alarma", make_pipeline(FunctionTransformer(signos_alarma), StandardScaler()), NUM),
    ])
