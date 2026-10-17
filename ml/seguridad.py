"""El servicio de IA solo atiende a la API.

No se publica hacia afuera (no tiene puertos en el compose ni ruta en Nginx). Aun así,
cada petición debe traer el secreto compartido ML_SERVICE_TOKEN en la cabecera
X-Servicio-Token: la misma idea del secreto que comparten HAPI y la API en R21.
"""
import hmac
import os

from fastapi import Header, HTTPException

ML_SERVICE_TOKEN = os.getenv("ML_SERVICE_TOKEN")


def solo_api(x_servicio_token: str | None = Header(default=None)):
    if not ML_SERVICE_TOKEN or not x_servicio_token or \
            not hmac.compare_digest(x_servicio_token, ML_SERVICE_TOKEN):
        raise HTTPException(status_code=401, detail="Token de servicio inválido")
