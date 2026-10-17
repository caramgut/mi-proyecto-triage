# Persistencia de facturación en MongoDB (R09) y factura automática de IA (R19).

import os
from datetime import datetime, timezone
from urllib.parse import urlparse

from bson import ObjectId
from pymongo import ASCENDING, DESCENDING, MongoClient
from pymongo.errors import DuplicateKeyError, PyMongoError

MONGO_CONNECTION_STRING = os.getenv(
    "MONGO_CONNECTION_STRING",
    "mongodb://mongodb:27017/triaje",
)

_cliente = MongoClient(MONGO_CONNECTION_STRING, serverSelectionTimeoutMS=5000)


def _nombre_bd() -> str:
    try:
        nombre = urlparse(MONGO_CONNECTION_STRING).path.lstrip("/")
    except Exception:
        nombre = ""
    return nombre or os.getenv("MONGO_DB_NAME", "triaje")


_bd = _cliente[_nombre_bd()]
facturas = _bd["facturas"]

VALOR_ANALISIS_IA = 45000


def asegurar_indices() -> None:
    """Índices idempotentes: una factura IA por reporte y número manual único."""
    facturas.create_index([("fecha", DESCENDING)])
    facturas.create_index([("paciente_id", ASCENDING), ("fecha", DESCENDING)])
    facturas.create_index(
        [("reporte_id", ASCENDING)],
        unique=True,
        partialFilterExpression={"reporte_id": {"$exists": True}},
    )
    facturas.create_index(
        [("numero_factura", ASCENDING)],
        unique=True,
        partialFilterExpression={"numero_factura": {"$type": "string"}},
    )


def _serializar(doc: dict | None) -> dict | None:
    if doc is None:
        return None
    salida = dict(doc)
    salida["id"] = str(salida.pop("_id"))
    fecha = salida.get("fecha")
    if isinstance(fecha, datetime):
        # PyMongo devuelve por defecto los Date de BSON como datetime ingenuos,
        # aunque BSON representa instantes UTC. Marcamos explícitamente UTC
        # para que el frontend pueda convertirlos correctamente a America/Bogota.
        if fecha.tzinfo is None:
            fecha = fecha.replace(tzinfo=timezone.utc)
        salida["fecha"] = fecha.astimezone(timezone.utc).isoformat()

    updated_at = salida.get("updated_at")
    if isinstance(updated_at, datetime):
        if updated_at.tzinfo is None:
            updated_at = updated_at.replace(tzinfo=timezone.utc)
        salida["updated_at"] = updated_at.astimezone(timezone.utc).isoformat()
    return salida


def ping_mongo() -> bool:
    _cliente.admin.command("ping")
    return True


def crear_factura_manual(
    *,
    paciente_id: int,
    servicio: str,
    valor: float,
    usuario: int,
    descripcion: str | None = None,
    estado_pago: str = "pendiente",
    numero_factura: str | None = None,
    id_encuentro: int | None = None,
) -> dict:
    asegurar_indices()
    ahora = datetime.now(timezone.utc)
    doc = {
        "paciente_id": int(paciente_id),
        "servicio": servicio,
        "descripcion": descripcion,
        "valor": float(valor),
        "fecha": ahora,
        "estado_pago": estado_pago,
        "origen": "manual",
        "creada_por": int(usuario),
    }
    if numero_factura:
        doc["numero_factura"] = numero_factura
    if id_encuentro is not None:
        doc["id_encuentro"] = int(id_encuentro)

    try:
        resultado = facturas.insert_one(doc)
    except DuplicateKeyError as exc:
        raise ValueError("El número de factura ya existe") from exc
    except PyMongoError:
        raise

    creado = facturas.find_one({"_id": resultado.inserted_id})
    return _serializar(creado)


def facturar_reporte_ia(paciente_id: int, reporte_id: int, usuario: int, id_encuentro: int | None = None) -> dict:
    """Crea una sola factura automática por reporte de IA aprobado."""
    asegurar_indices()
    existente = facturas.find_one({"reporte_id": int(reporte_id)})
    if existente:
        salida = _serializar(existente)
        salida["duplicada"] = True
        return salida

    doc = {
        "paciente_id": int(paciente_id),
        "reporte_id": int(reporte_id),
        "numero_factura": f"IA-{int(reporte_id):06d}",
        "servicio": "analisis_ia",
        "descripcion": "Análisis de apoyo al triaje con IA aprobado por el clínico",
        "valor": float(VALOR_ANALISIS_IA),
        "fecha": datetime.now(timezone.utc),
        "estado_pago": "pendiente",
        "origen": "automatica",
        "creada_por": int(usuario),
    }
    if id_encuentro is not None:
        doc["id_encuentro"] = int(id_encuentro)

    try:
        resultado = facturas.insert_one(doc)
        creado = facturas.find_one({"_id": resultado.inserted_id})
        salida = _serializar(creado)
        salida["duplicada"] = False
        return salida
    except DuplicateKeyError:
        # Protege contra dos aprobaciones concurrentes del mismo reporte.
        existente = facturas.find_one({"reporte_id": int(reporte_id)})
        salida = _serializar(existente)
        salida["duplicada"] = True
        return salida


def listar_facturas() -> list[dict]:
    asegurar_indices()
    return [_serializar(d) for d in facturas.find({}).sort("fecha", DESCENDING)]


def obtener_factura(id_factura: str) -> dict | None:
    asegurar_indices()
    try:
        oid = ObjectId(id_factura)
    except Exception:
        return None
    return _serializar(facturas.find_one({"_id": oid}))


def actualizar_estado_factura(id_factura: str, estado_pago: str, usuario: int) -> dict | None:
    asegurar_indices()
    try:
        oid=ObjectId(id_factura)
    except Exception:
        return None
    ahora=datetime.now(timezone.utc)
    facturas.update_one(
        {"_id":oid},
        {"$set":{"estado_pago":estado_pago,"actualizada_por":int(usuario),"updated_at":ahora}}
    )
    return _serializar(facturas.find_one({"_id":oid}))
