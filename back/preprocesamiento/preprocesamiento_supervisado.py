#!/usr/bin/env python3
"""
Preprocesamiento para aprendizaje supervisado del dataset de triaje homologado
(KTAS Corea + NHAMCS EE. UU. 2022).

Entrada : triaje_homologado.csv  (salida de homologar_triaje.py)
Salidas : (en la carpeta de salida)
  triaje_supervisado_limpio.csv   filas filtradas, solo variables compartidas, SIN imputar,
                                  con columna `split` (train/test) para que todo el equipo use la misma partición
  triaje_train_listo.csv          entrenamiento ya transformado (imputado, escalado, one-hot)
  triaje_test_listo.csv           prueba transformada con las estadísticas del entrenamiento
  preprocesador.joblib            pipeline ajustado (para aplicarlo igual a un paciente nuevo en la API)
  trazabilidad_filtros.csv        cuántas filas se quitaron en cada paso y por qué

Uso:
    python preprocesamiento_supervisado.py triaje_homologado.csv salida_supervisado/

Para validación cruzada NO uses los CSV ya transformados: usa `construir_preprocesador()` dentro de un
Pipeline de scikit-learn, así la imputación y el escalado se recalculan en cada partición.
"""
import sys
import os
import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer, MissingIndicator
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler, OneHotEncoder
from sklearn.model_selection import train_test_split

EDAD_MINIMA = 18
SEMILLA = 42
TAMANO_PRUEBA = 0.20
MAX_SIGNOS_VITALES_FALTANTES = 2   # se descartan filas con 3 o más de los 6 signos vitales faltantes

SIGNOS_VITALES = ["fc", "fr", "pas", "pad", "temp_c", "spo2"]
CONTINUAS = ["edad", "fc", "fr", "pas", "pad", "temp_c", "spo2", "dolor_nrs"]
BINARIAS = ["llegada_ambulancia", "lesion"]
CON_INDICADOR = ["spo2", "dolor_nrs", "lesion"]   # >5 % de faltantes en alguna fuente
CATEGORIAS_MOTIVO = [
    "cardiovascular", "respiratorio", "digestivo", "neurologico", "conciencia_paro", "fiebre_general",
    "trauma", "musculoesqueletico", "genitourinario_gineco", "psiquiatrico_sustancias",
    "piel_alergia", "orl_ojos_dental", "otros",
]
PREDICTORES_CRUDOS = ["edad", "sexo", "llegada_ambulancia", "lesion", "fc", "fr", "pas", "pad",
                      "temp_c", "spo2", "dolor_nrs", "motivo_categoria"]
OBJETIVOS = {"triaje_enfermeria": "y_triaje", "emergencia": "y_emergencia", "hospitalizado": "y_hospitalizado"}


def construir_preprocesador():
    """ColumnTransformer sin ajustar. Úsalo dentro de un Pipeline: Pipeline([('prep', construir_preprocesador()), ('modelo', ...)])."""
    continuas = Pipeline([("imputar", SimpleImputer(strategy="median")), ("escalar", StandardScaler())])
    binarias = SimpleImputer(strategy="most_frequent")
    indicadores = MissingIndicator(features="all")
    sexo = OneHotEncoder(drop="if_binary", handle_unknown="ignore", sparse_output=False)
    motivo = Pipeline([("rellenar", SimpleImputer(strategy="constant", fill_value="otros")),
                       ("onehot", OneHotEncoder(categories=[CATEGORIAS_MOTIVO], handle_unknown="ignore",
                                                sparse_output=False))])
    ct = ColumnTransformer(
        [("continuas", continuas, CONTINUAS),
         ("binarias", binarias, BINARIAS),
         ("sexo", sexo, ["sexo"]),
         ("faltante", indicadores, CON_INDICADOR),
         ("motivo", motivo, ["motivo_categoria"])],
        verbose_feature_names_out=False)
    ct.set_output(transform="pandas")
    return ct


def renombrar(cols):
    nuevas = []
    for c in cols:
        if c.startswith("missingindicator_"):
            nuevas.append(c.replace("missingindicator_", "") + "_faltante")
        elif c.startswith("motivo_categoria_"):
            nuevas.append("motivo_" + c[len("motivo_categoria_"):])
        else:
            nuevas.append(c)
    return nuevas


def transformar(prep, df):
    """Aplica el preprocesador ajustado a un DataFrame con las columnas PREDICTORES_CRUDOS (uno o varios pacientes)
    y devuelve las 27 columnas con los nombres finales (los mismos de los CSV *_listo)."""
    X = prep.transform(df[PREDICTORES_CRUDOS])
    X.columns = renombrar(X.columns)
    for c in BINARIAS + [c + "_faltante" for c in CON_INDICADOR] + ["sexo_M"] + ["motivo_" + m for m in CATEGORIAS_MOTIVO]:
        X[c] = X[c].round().astype(int)
    return X.reset_index(drop=True)


def main(ruta, salida):
    os.makedirs(salida, exist_ok=True)
    d = pd.read_csv(ruta)
    traza = [("filas de partida", len(d), "")]

    # 1. Solo adultos
    n = len(d); d = d[d["edad"] >= EDAD_MINIMA].copy()
    traza.append((f"se quitan menores de {EDAD_MINIMA} años", n - len(d), f"quedan {len(d)}"))

    # 2. Solo variables presentes en ambos datasets (se descartan triaje_experto, mental_avpu, peso_encuesta,
    #    motivo_original (texto), id_original y dolor_si, que es redundante con dolor_nrs)
    d["emergencia"] = np.where(d["triaje_enfermeria"].isna(), np.nan, (d["triaje_enfermeria"] <= 3).astype(float))
    d = d[["fuente"] + PREDICTORES_CRUDOS + list(OBJETIVOS)].copy()

    # 3. Sin etiqueta de triaje no hay aprendizaje supervisado
    n = len(d); d = d[d["triaje_enfermeria"].notna()].copy()
    traza.append(("se quitan filas sin nivel de triaje (sin etiqueta)", n - len(d), f"quedan {len(d)}"))

    # 4. Filas casi sin información clínica
    n = len(d); falt = d[SIGNOS_VITALES].isna().sum(axis=1)
    d = d[falt <= MAX_SIGNOS_VITALES_FALTANTES].copy()
    traza.append((f"se quitan filas con >= {MAX_SIGNOS_VITALES_FALTANTES + 1} de 6 signos vitales faltantes", n - len(d), f"quedan {len(d)}"))

    # 5. Duplicados exactos
    n = len(d); d = d.drop_duplicates().copy()
    traza.append(("se quitan duplicados exactos", n - len(d), f"quedan {len(d)}"))

    d = d.rename(columns=OBJETIVOS).reset_index(drop=True)
    d["y_triaje"] = d["y_triaje"].astype(int)
    d["y_emergencia"] = d["y_emergencia"].astype(int)

    # 6. Partición estratificada por fuente x nivel de triaje (misma semilla = misma partición para todos)
    estrato = d["fuente"] + "_" + d["y_triaje"].astype(str)
    idx_tr, idx_te = train_test_split(d.index, test_size=TAMANO_PRUEBA, stratify=estrato, random_state=SEMILLA)
    d["split"] = "train"
    d.loc[idx_te, "split"] = "test"
    d.to_csv(os.path.join(salida, "triaje_supervisado_limpio.csv"), index=False)

    # 7. Ajustar SOLO con entrenamiento y transformar ambos
    train, test = d[d["split"] == "train"], d[d["split"] == "test"]
    prep = construir_preprocesador().fit(train[PREDICTORES_CRUDOS])

    def listo(df):
        X = transformar(prep, df)
        meta = df[["fuente", "y_triaje", "y_emergencia", "y_hospitalizado"]].reset_index(drop=True)
        return pd.concat([X.reset_index(drop=True), meta], axis=1)

    tr, te = listo(train), listo(test)
    # peso opcional para equilibrar las dos fuentes en el entrenamiento (cada fuente aporta el mismo peso total)
    n_k = (tr["fuente"] == "KTAS_Corea").sum(); n_n = (tr["fuente"] != "KTAS_Corea").sum()
    tr["peso_fuente"] = np.where(tr["fuente"] == "KTAS_Corea", n_n / n_k, 1.0).round(4)
    tr.to_csv(os.path.join(salida, "triaje_train_listo.csv"), index=False)
    te.to_csv(os.path.join(salida, "triaje_test_listo.csv"), index=False)
    try:
        import joblib
        joblib.dump(prep, os.path.join(salida, "preprocesador.joblib"))
    except Exception as e:  # joblib viene con scikit-learn
        print("No se pudo guardar el preprocesador:", e)
    pd.DataFrame(traza, columns=["paso", "filas_afectadas", "detalle"]).to_csv(
        os.path.join(salida, "trazabilidad_filtros.csv"), index=False)

    print(pd.DataFrame(traza, columns=["paso", "filas", "detalle"]).to_string(index=False))
    print(f"\ntrain {tr.shape} | test {te.shape}")
    print(tr.drop(columns=["fuente", "peso_fuente"]).columns.tolist())
    return tr, te


if __name__ == "__main__":
    ruta = sys.argv[1] if len(sys.argv) > 1 else "triaje_homologado.csv"
    salida = sys.argv[2] if len(sys.argv) > 2 else "salida_supervisado"
    main(ruta, salida)
