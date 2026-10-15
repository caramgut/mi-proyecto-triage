#!/usr/bin/env python3
"""
Homologación de dos datasets de triaje de urgencias en un solo esquema común.

  1) data.csv          -> Kaggle "Emergency Service Triage Application" (KTAS, Corea del Sur)
  2) ed2022-spss.sav   -> NHAMCS 2022, Emergency Department (CDC/NCHS, EE. UU.)

Salidas (en la carpeta de salida):
  - triaje_homologado.csv        dataset unificado (una fila por visita), columna `fuente`
  - homologacion_variables.xlsx  tabla de homologación, categorías de motivo, reglas de limpieza
  - diccionario_ED2022.xlsx      diccionario de variables del .sav (nombre, etiqueta, valores)

Uso:
    python homologar_triaje.py                       # busca los archivos en la carpeta actual
    python homologar_triaje.py data.csv ed2022-spss.sav salida/

Requiere: pandas, numpy, openpyxl. El archivo sav_reader.py (lector propio de .sav)
debe estar en la misma carpeta; si tienes `pyreadstat` puedes usarlo en su lugar.
"""
import re
import sys
import os
import numpy as np
import pandas as pd

EDAD_MINIMA = 16  # edad mínima del dataset KTAS; se aplica a ambas fuentes

# ----------------------------------------------------------------------------
# Reglas de limpieza (rangos fisiológicamente plausibles; fuera de rango -> NaN)
# ----------------------------------------------------------------------------
RANGOS = {
    "fc": (20, 250),      # latidos/min
    "fr": (4, 80),        # respiraciones/min
    "pas": (40, 300),     # mmHg
    "pad": (20, 200),     # mmHg
    "temp_c": (30, 44),   # °C
    "spo2": (50, 100),    # %
}

# ----------------------------------------------------------------------------
# Categorías comunes de motivo de consulta
# ----------------------------------------------------------------------------
CATEGORIAS = {
    "cardiovascular": "Dolor torácico, palpitaciones, hipertensión/hipotensión",
    "respiratorio": "Disnea, tos, hemoptisis, COVID/infección respiratoria, saturación baja",
    "digestivo": "Dolor abdominal, vómito, náusea, diarrea, sangrado digestivo, ascitis",
    "neurologico": "Cefalea, mareo/vértigo, síncope, convulsión, déficit motor/sensitivo, lenguaje",
    "conciencia_paro": "Alteración del estado mental/conciencia, paro cardiorrespiratorio",
    "fiebre_general": "Fiebre, escalofríos, debilidad general, malestar, síntomas metabólicos",
    "trauma": "Lesiones, heridas, fracturas, quemaduras, mordeduras, cuerpo extraño, violencia",
    "musculoesqueletico": "Dolor de espalda, cuello, extremidades, articulaciones, inflamación local",
    "genitourinario_gineco": "Urinario, genital, sangrado vaginal, embarazo, dolor de flanco/pélvico",
    "psiquiatrico_sustancias": "Ansiedad, depresión, intento/ideación suicida, alucinaciones, intoxicación, alcohol",
    "piel_alergia": "Erupciones, urticaria, prurito, celulitis, alergia",
    "orl_ojos_dental": "Ojos, oídos, nariz/epistaxis, garganta, dental, boca, cara",
    "otros": "Administrativo, controles, resultados de exámenes, dispositivos, no especificado",
}

# KTAS: texto libre -> categoría (primera regla que coincide). Texto en minúsculas.
REGLAS_KTAS = [
    ("conciencia_paro", r"mental|confus|loss of consc|\bloc\b|loc -|drows|delirium|cpr|arrest|sleeping tend|mentality|behavior change|decreased activity"),
    ("trauma", r"injur|lacer|\blac\b|lac\.|wound|burn|sting|bite|trauma|concussion|needle stick|dislocation|fracture|scratch|sexual (violence|abuse)|foreign body|\bfb\b"),
    ("psiquiatrico_sustancias", r"anxi|depress|suicid|halluc|delusion|intoxic|alcohol|drunk|mood|\bdi,"),
    ("cardiovascular", r"chest|palpit|tachycard|hypertension|blood pressure"),
    ("respiratorio", r"dyspn|cough|hemopt|sputum|orthopnea|desaturation|hyperventil|pneumothorax|\bptx\b"),
    ("digestivo", r"abd|epigastr|\bruq\b|\bllq\b|\brlq\b|\bluq\b|periumbilical|vomit|nausea|diarrhea|\bv - |hematemesis|melena|hematochezia|ascites|anal bleeding|\?nus|peg tube|l-tube|hiccup|ptbd"),
    ("genitourinario_gineco", r"flank|dysuria|hematuria|vaginal|pprom|menstr|voiding|urinary|testis|scrotal|erection|oliguria|bladder|pelvic|penile"),
    ("fiebre_general", r"general weakness|g/w|^weakness$|fever|f/c|chill|^cold$|general ache|hypoglyc"),
    ("neurologico", r"dizz|\bdz\b|vertigo|headache|\bha\b|head pain|syncope|dysarthria|seizure|convuls|sezure|weakness|paresis|palsy|numb|paresth|tingl|amnesia|aphasia|light headness|involuntary|sensory"),
    ("piel_alergia", r"rash|urticar|eczema|skin|itch|erythem|cellulitis|allerg|redness|papule|lesion"),
    ("orl_ojos_dental", r"eye|ocular|vision|visual|diplopia|\bear\b|ear pain|otalgia|hearing|nasal|epistaxis|nose|throat|pharynx|voice|tooth|dental|gingiv|oral|jaw|mandib|tmj|facial|eyelid|eyebrow|cheek"),
    ("musculoesqueletico", r"back|lbp|leg|arm|knee|hip|joint|shoulder|wrist|foot|toe|finger|hand|elbow|neck|myalgia|femur|buttock|coccyg|thigh|swelling|ankle|forearm|chin"),
]


def categoria_ktas(texto):
    if not isinstance(texto, str):
        return np.nan
    t = texto.lower().strip()
    if t == "" or re.fullmatch(r"[\?\s]+", t) or t.startswith("?"):
        return "otros"
    for cat, patron in REGLAS_KTAS:
        if re.search(patron, t):
            return cat
    return "otros"


# NHAMCS: código RFV (categoría amplia, RFV13D) -> categoría común. Primera coincidencia.
REGLAS_RFV = [
    ("conciencia_paro", [(5835, 5842)]),
    ("psiquiatrico_sustancias", [(1100, 1165), (2300, 2330), (3130, 3130), (4518, 4518), (5818, 5820), (5900, 5925)]),
    ("trauma", [(5005, 5830)]),
    ("neurologico", [(1030, 1030), (1095, 1095), (1200, 1240), (2350, 2370), (2525, 2525)]),
    ("cardiovascular", [(1050, 1050), (1260, 1280), (2500, 2540), (2550, 2550)]),
    ("respiratorio", [(1415, 1445), (1470, 1485), (2600, 2640)]),
    ("fiebre_general", [(1005, 1025), (1035, 1035), (1045, 1045), (1085, 1085), (1450, 1450), (2015, 2035)]),
    ("digestivo", [(1520, 1615), (2545, 2545), (2650, 2675)]),
    ("genitourinario_gineco", [(1640, 1680), (1700, 1720), (1730, 1810), (2700, 2736), (3200, 3205)]),
    ("piel_alergia", [(1090, 1090), (1830, 1895), (2800, 2825)]),
    ("orl_ojos_dental", [(1305, 1365), (1400, 1410), (1455, 1460), (1500, 1515), (2400, 2455)]),
    ("musculoesqueletico", [(1900, 1980), (2900, 2910)]),
]


def categoria_rfv(codigo):
    if pd.isna(codigo) or codigo <= 0:
        return np.nan
    for cat, rangos in REGLAS_RFV:
        for lo, hi in rangos:
            if lo <= codigo <= hi:
                return cat
    return "otros"


# ----------------------------------------------------------------------------
# Utilidades
# ----------------------------------------------------------------------------
def limpiar_rango(serie, lo, hi):
    return serie.where((serie >= lo) & (serie <= hi))


def aplicar_rangos(df):
    n_fuera = {}
    for col, (lo, hi) in RANGOS.items():
        antes = df[col].notna().sum()
        df[col] = limpiar_rango(df[col], lo, hi)
        n_fuera[col] = int(antes - df[col].notna().sum())
    return df, n_fuera


# ----------------------------------------------------------------------------
# KTAS (Corea)
# ----------------------------------------------------------------------------
def preparar_ktas(ruta):
    k = pd.read_csv(ruta, sep=";", decimal=",", encoding="latin-1")
    for c in ["NRS_pain", "SBP", "DBP", "HR", "RR", "BT", "Saturation"]:
        k[c] = pd.to_numeric(k[c], errors="coerce")  # '??' y '#BOÞ!' -> NaN
    k.loc[k["Pain"] == 0, "NRS_pain"] = 0  # sin dolor = 0 en la escala

    out = pd.DataFrame(index=k.index)
    out["fuente"] = "KTAS_Corea"
    out["id_original"] = k.index + 1
    out["edad"] = k["Age"]
    out["sexo"] = k["Sex"].map({1: "F", 2: "M"})
    out["llegada_ambulancia"] = k["Arrival mode"].map({1: 0, 3: 0, 2: 1, 4: 1})  # 5,6,7 = otro -> NaN
    out["lesion"] = k["Injury"].map({1: 0, 2: 1})
    out["fc"], out["fr"], out["pas"], out["pad"] = k["HR"], k["RR"], k["SBP"], k["DBP"]
    out["temp_c"], out["spo2"] = k["BT"], k["Saturation"]
    out["dolor_nrs"] = k["NRS_pain"]
    out["dolor_si"] = k["Pain"].map({0: 0, 1: 1})
    out["motivo_original"] = k["Chief_complain"].str.lower().str.strip()
    out["motivo_categoria"] = out["motivo_original"].map(categoria_ktas)
    out["triaje_enfermeria"] = k["KTAS_RN"]
    out["triaje_experto"] = k["KTAS_expert"]
    # Desenlace: 2 sala, 3 UCI, 7 cirugía = hospitalizado; 1 y 4 = alta; 5 traslado y 6 muerte = excluidos
    out["hospitalizado"] = k["Disposition"].map({1: 0, 4: 0, 2: 1, 3: 1, 7: 1})
    out["mental_avpu"] = k["Mental"]            # solo existe en KTAS
    out["peso_encuesta"] = np.nan               # KTAS no es muestra con pesos
    return out


# ----------------------------------------------------------------------------
# NHAMCS 2022 (EE. UU.)
# ----------------------------------------------------------------------------
def preparar_nhamcs(df, vl):
    def num(col):
        return pd.to_numeric(df[col], errors="coerce")

    def sin_codigos(col, extra=()):
        s = num(col).copy()
        s[s < 0] = np.nan  # -9 en blanco, -8 desconocido, -7 no aplica
        for e in extra:
            s[s == e] = np.nan
        return s

    out = pd.DataFrame(index=df.index)
    out["fuente"] = "NHAMCS_EEUU_2022"
    out["id_original"] = df.index + 1
    out["edad"] = num("AGE")
    out["sexo"] = num("SEX").map({1: "F", 2: "M"})
    out["llegada_ambulancia"] = num("ARREMS").map({1: 1, 2: 0})
    out["lesion"] = num("INJURY").map({0: 0, 1: 1})  # 2 = dudosa -> NaN
    out["fc"] = sin_codigos("PULSE", extra=(998,))            # 998 = Doppler
    out["fr"] = sin_codigos("RESPR")
    out["pas"] = sin_codigos("BPSYS")
    out["pad"] = sin_codigos("BPDIAS", extra=(998,))          # 998 = palpación/Doppler
    out["temp_c"] = (sin_codigos("TEMPF") / 10 - 32) * 5 / 9   # décimas de °F -> °C
    out["spo2"] = sin_codigos("POPCT")
    out["dolor_nrs"] = sin_codigos("PAINSCALE")
    out["dolor_si"] = (out["dolor_nrs"] > 0).astype(float).where(out["dolor_nrs"].notna())
    etiquetas = vl.get("RFV13D", {})
    cod = num("RFV13D")
    out["motivo_original"] = cod.map(lambda c: etiquetas.get(int(c), "") if pd.notna(c) else "")
    out["motivo_categoria"] = cod.map(categoria_rfv)
    imm = num("IMMEDR")
    out["triaje_enfermeria"] = imm.where(imm.isin([1, 2, 3, 4, 5]))  # 0,7,-8,-9 = sin triaje/desconocido
    out["triaje_experto"] = np.nan                                   # NHAMCS no tiene reevaluación experta
    # Desenlace
    hosp = (num("ADMITHOS") == 1) | (num("OBSHOS") == 1)
    excluidos = np.zeros(len(df), dtype=bool)
    for c in ["TRANOTH", "TRANPSYC", "TRANNH", "DIEDED", "DOA", "LWBS", "LBTC", "LEFTAMA", "NODISP", "OTHDISP"]:
        if c in df.columns:
            excluidos |= (num(c) == 1).to_numpy()
    h = pd.Series(np.where(hosp, 1.0, 0.0), index=df.index)
    h[(~hosp) & excluidos] = np.nan
    out["hospitalizado"] = h
    out["mental_avpu"] = np.nan                  # NHAMCS no registra AVPU
    out["peso_encuesta"] = num("PATWT")          # visita ponderada a nivel nacional
    return out


# ----------------------------------------------------------------------------
# Principal
# ----------------------------------------------------------------------------
def main(ruta_csv, ruta_sav, salida):
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from sav_reader import read_sav, to_frames

    os.makedirs(salida, exist_ok=True)
    print("Leyendo KTAS...")
    ktas = preparar_ktas(ruta_csv)
    print("Leyendo NHAMCS (.sav)...")
    df_sav, meta, vl = to_frames(read_sav(ruta_sav))
    nh = preparar_nhamcs(df_sav, vl)

    resumen_filtros = {}
    partes = []
    for nombre, d in [("KTAS_Corea", ktas), ("NHAMCS_EEUU_2022", nh)]:
        n0 = len(d)
        d = d[d["edad"] >= EDAD_MINIMA].copy()
        resumen_filtros[nombre] = {"filas_originales": n0, f"filas_edad>={EDAD_MINIMA}": len(d)}
        d, fuera = aplicar_rangos(d)
        resumen_filtros[nombre]["valores_fuera_de_rango_a_NaN"] = fuera
        partes.append(d)
    comb = pd.concat(partes, ignore_index=True)
    comb["emergencia"] = np.where(comb["triaje_enfermeria"].isna(), np.nan,
                                  (comb["triaje_enfermeria"] <= 3).astype(float))
    cols = ["fuente", "id_original", "edad", "sexo", "llegada_ambulancia", "lesion", "fc", "fr", "pas", "pad",
            "temp_c", "spo2", "dolor_nrs", "dolor_si", "motivo_categoria", "motivo_original",
            "triaje_enfermeria", "emergencia", "triaje_experto", "hospitalizado", "mental_avpu", "peso_encuesta"]
    comb = comb[cols]
    ruta_out = os.path.join(salida, "triaje_homologado.csv")
    comb.round({"temp_c": 1, "peso_encuesta": 3}).to_csv(ruta_out, index=False, encoding="utf-8")
    print(f"Guardado: {ruta_out}  {comb.shape}")

    # ---- Excel de homologación ----
    exportar_homologacion(os.path.join(salida, "homologacion_variables.xlsx"), ktas, nh, meta, vl, resumen_filtros, comb)
    exportar_diccionario(os.path.join(salida, "diccionario_ED2022.xlsx"), meta, vl)
    return comb


TABLA_HOMOLOGACION = [
    # variable común, KTAS (origen), NHAMCS (origen), transformación, comentario
    ("fuente", "—", "—", "Etiqueta de origen", "Úsala para validar por fuente y para análisis de sesgo"),
    ("edad", "Age", "AGE", "Se filtra edad >= 16", "NHAMCS top-codifica 94+; KTAS es adulto"),
    ("sexo", "Sex (1=F, 2=M)", "SEX (1=F, 2=M)", "Recodificar a F/M", "Codificación idéntica"),
    ("llegada_ambulancia", "Arrival mode", "ARREMS", "KTAS: 2,4 -> 1; 1,3 -> 0; 5,6,7 -> NaN. NHAMCS: 1 -> 1; 2 -> 0", "KTAS distingue vehículo propio/caminando; aquí se colapsa a sí/no"),
    ("lesion", "Injury (1=No, 2=Sí)", "INJURY (0=No, 1=Sí, 2=dudosa)", "Recodificar a 0/1; dudosa -> NaN", ""),
    ("fc", "HR", "PULSE", "998 (Doppler) -> NaN; rango 20-250", "lat/min"),
    ("fr", "RR", "RESPR", "Rango 4-80", "resp/min"),
    ("pas", "SBP", "BPSYS", "Rango 40-300", "mmHg"),
    ("pad", "DBP", "BPDIAS", "998 (palpación/Doppler) -> NaN; rango 20-200", "mmHg"),
    ("temp_c", "BT (°C)", "TEMPF (décimas de °F)", "NHAMCS: (TEMPF/10 - 32)·5/9; rango 30-44", "Unidades distintas"),
    ("spo2", "Saturation", "POPCT", "Rango 50-100", "Faltante alto en ambos"),
    ("dolor_nrs", "NRS_pain", "PAINSCALE", "KTAS: Pain=0 -> 0. NHAMCS: -8/-9 -> NaN", "NHAMCS ~39 % desconocido"),
    ("dolor_si", "Pain", "derivada de PAINSCALE > 0", "", ""),
    ("motivo_categoria", "Chief_complain (texto libre)", "RFV13D (código RFV)", "Reglas de palabras clave (KTAS) y rangos de código (NHAMCS) a 13 categorías", "Ver hoja Categorias_motivo"),
    ("triaje_enfermeria", "KTAS_RN (1-5)", "IMMEDR (1-5)", "NHAMCS: 0, 7, -8, -9 -> NaN", "Ambas: 1 = más urgente. Escalas NO idénticas (KTAS vs. escala de triaje de EE. UU.)"),
    ("emergencia", "derivada", "derivada", "1 si triaje_enfermeria <= 3 (1-3 emergencia; 4-5 no emergencia)", "Definición oficial de KTAS aplicada a ambas"),
    ("triaje_experto", "KTAS_expert", "(no existe)", "Solo KTAS", "Etiqueta de referencia 'gold' solo en Corea"),
    ("hospitalizado", "Disposition (2,3,7=1; 1,4=0; 5,6 excluidos)", "ADMITHOS o OBSHOS = 1; excluye traslados, muertes, abandonos", "Ver reglas", "Comparable, no idéntica"),
    ("mental_avpu", "Mental (1-4)", "(no existe)", "Solo KTAS", "Quedaría vacía para toda la parte de EE. UU."),
    ("peso_encuesta", "(no aplica)", "PATWT", "Solo NHAMCS", "NHAMCS es muestra compleja; el peso extrapola a nivel nacional"),
]


def exportar_homologacion(ruta, ktas, nh, meta, vl, filtros, comb):
    h = pd.DataFrame(TABLA_HOMOLOGACION, columns=["variable_comun", "origen_KTAS", "origen_NHAMCS", "transformacion", "comentario"])
    cats = pd.DataFrame([(k, v) for k, v in CATEGORIAS.items()], columns=["categoria", "descripcion"])
    reglas_ktas = pd.DataFrame(REGLAS_KTAS, columns=["categoria", "patron_regex_sobre_texto_KTAS"])
    et = vl.get("RFV13D", {})
    filas = []
    for cod in sorted(k for k in et if isinstance(k, int) and k > 0):
        filas.append((cod, et[cod], categoria_rfv(cod)))
    rfv = pd.DataFrame(filas, columns=["codigo_RFV13D", "etiqueta", "categoria_comun"])
    ktas_texto = (ktas.groupby(["motivo_original", "motivo_categoria"]).size().reset_index(name="n")
                  .sort_values("n", ascending=False))
    limp = pd.DataFrame([(k, v[0], v[1]) for k, v in RANGOS.items()], columns=["variable", "min_plausible", "max_plausible"])
    comp = comb.groupby("fuente").agg(
        n=("edad", "size"), edad_media=("edad", "mean"), pct_mujer=("sexo", lambda s: (s == "F").mean() * 100),
        pct_ambulancia=("llegada_ambulancia", "mean"), pct_lesion=("lesion", "mean"),
        triaje_valido=("triaje_enfermeria", "count"), pct_emergencia=("emergencia", "mean"),
        hospitalizado_valido=("hospitalizado", "count"), pct_hospitalizado=("hospitalizado", "mean"),
        faltante_spo2=("spo2", lambda s: s.isna().mean() * 100), faltante_dolor=("dolor_nrs", lambda s: s.isna().mean() * 100),
        faltante_pas=("pas", lambda s: s.isna().mean() * 100)).round(3).reset_index()
    with pd.ExcelWriter(ruta, engine="openpyxl") as w:
        h.to_excel(w, sheet_name="Homologacion", index=False)
        cats.to_excel(w, sheet_name="Categorias", index=False)
        rfv.to_excel(w, sheet_name="NHAMCS_RFV_a_categoria", index=False)
        reglas_ktas.to_excel(w, sheet_name="KTAS_reglas_texto", index=False)
        ktas_texto.to_excel(w, sheet_name="KTAS_texto_a_categoria", index=False)
        limp.to_excel(w, sheet_name="Rangos_plausibles", index=False)
        comp.to_excel(w, sheet_name="Comparacion_fuentes", index=False)
        for ws in w.book.worksheets:
            for col in ws.columns:
                ancho = min(70, max(len(str(c.value)) if c.value is not None else 0 for c in col) + 2)
                ws.column_dimensions[col[0].column_letter].width = ancho
    print("Guardado:", ruta)


def exportar_diccionario(ruta, meta, vl):
    """Diccionario del .sav. Las variables que comparten exactamente las mismas etiquetas
    (p. ej. RFV1..RFV5, DIAG1..DIAG5) se listan juntas en la hoja Valores para no repetir miles de filas."""
    filas_v, grupos = [], {}
    for _, m in meta.iterrows():
        etiquetas = vl.get(m["var"], {})
        utiles = {k: v for k, v in etiquetas.items() if not re.fullmatch(r"-?[\d\.,]+", str(v).strip())}
        filas_v.append((m["var"], m["tipo"], m["etiqueta"], len(etiquetas),
                        "; ".join(f"{k}={v}" for k, v in list(utiles.items())[:8])))
        if utiles:
            grupos.setdefault(tuple(utiles.items()), []).append(m["var"])
    filas_val = []
    for items, nombres in grupos.items():
        etiqueta_grupo = ", ".join(nombres[:6]) + (f" (+{len(nombres) - 6} más)" if len(nombres) > 6 else "")
        for k, v in items:
            filas_val.append((etiqueta_grupo, k, v))
    dv = pd.DataFrame(filas_v, columns=["variable", "tipo", "etiqueta", "n_valores_etiquetados", "primeros_valores"])
    dval = pd.DataFrame(filas_val, columns=["variables_con_estas_etiquetas", "codigo", "significado"])
    with pd.ExcelWriter(ruta, engine="openpyxl") as w:
        dv.to_excel(w, sheet_name="Variables", index=False)
        dval.to_excel(w, sheet_name="Valores", index=False)
        w.sheets["Variables"].column_dimensions["A"].width = 16
        w.sheets["Variables"].column_dimensions["C"].width = 80
        w.sheets["Variables"].column_dimensions["E"].width = 80
        w.sheets["Valores"].column_dimensions["A"].width = 40
        w.sheets["Valores"].column_dimensions["C"].width = 80
    print("Guardado:", ruta)


if __name__ == "__main__":
    args = sys.argv[1:]
    csv = args[0] if len(args) > 0 else "data.csv"
    sav = args[1] if len(args) > 1 else "ed2022-spss.sav"
    out = args[2] if len(args) > 2 else "salida_homologada"
    main(csv, sav, out)
