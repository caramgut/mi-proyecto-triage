# back/services/facturacion_ia.py
# R19: al aprobar un reporte de IA se crea sola la factura en MongoDB (R09).
# La llama routers/ia_reportes.py después de aprobar. Debe devolver un dict.

import os
from datetime import datetime, timezone

from pymongo import MongoClient

MONGO_URL = os.getenv("MONGO_URL", "mongodb://mongo:27017")   # ← ajustar a la que ya usa R09
_cliente = MongoClient(MONGO_URL)
facturas = _cliente["contabilidad"]["facturas"]               # ← misma base/colección de R09

VALOR_ANALISIS_IA = 45000   # ← tarifa que defina el equipo


def facturar_reporte_ia(paciente_id: int, reporte_id: int, usuario: int) -> dict:
    # Si ya se facturó este reporte, no se duplica
    existente = facturas.find_one({"reporte_id": reporte_id})
    if existente:
        return {"id": str(existente["_id"]), "reporte_id": reporte_id, "duplicada": True}

    doc = {
        "paciente_id": paciente_id,
        "reporte_id": reporte_id,
        "servicio": "analisis_ia",
        "descripcion": "Pretriaje con IA aprobado por el clínico",
        "valor": VALOR_ANALISIS_IA,
        "fecha": datetime.now(timezone.utc),
        "estado_pago": "pendiente",
        "origen": "automatica",
        "creada_por": usuario,
    }
    resultado = facturas.insert_one(doc)
    return {"id": str(resultado.inserted_id), "reporte_id": reporte_id, "valor": VALOR_ANALISIS_IA}