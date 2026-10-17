# Cliente del servicio de IA (contenedor "ml").
# La API es la ÚNICA que habla con él, y se identifica con el secreto ML_SERVICE_TOKEN.

import requests
from fastapi import HTTPException

from core.config import ML_SERVICE_TOKEN, ML_URL

# Código LOINC, nombre y unidad UCUM de cada signo vital que usa el modelo.
# La API guarda así las observaciones y así las vuelve a leer para el análisis.
LOINC_SIGNOS = {
    "fc":     ("8867-4",  "Frecuencia cardiaca",         "/min"),
    "fr":     ("9279-1",  "Frecuencia respiratoria",     "/min"),
    "pas":    ("8480-6",  "Presión arterial sistólica",  "mm[Hg]"),
    "pad":    ("8462-4",  "Presión arterial diastólica", "mm[Hg]"),
    "temp_c": ("8310-5",  "Temperatura corporal",        "Cel"),
    "spo2":   ("59408-5", "Saturación de oxígeno (oximetría de pulso)", "%"),
}


def llamar_ml(metodo: str, ruta: str, json: dict | None = None, timeout: int = 60):
    if not ML_SERVICE_TOKEN:
        raise HTTPException(status_code=503, detail="Falta configurar ML_SERVICE_TOKEN")
    try:
        r = requests.request(
            metodo, f"{ML_URL}{ruta}", json=json, timeout=timeout,
            headers={"X-Servicio-Token": ML_SERVICE_TOKEN},
        )
    except requests.RequestException as e:
        raise HTTPException(status_code=503, detail=f"El servicio de IA no está disponible: {e}")
    if r.status_code != 200:
        try:
            detalle = r.json()
        except Exception:
            detalle = r.text
        raise HTTPException(status_code=502, detail={"mensaje": "El servicio de IA rechazó la petición",
                                                     "status_code": r.status_code, "respuesta": detalle})
    return r.json()
