"""Servicio de IA del proyecto de triaje.

Responsabilidad ÚNICA: el modelo. Recibe variables clínicas sin identidad y devuelve
predicciones, grupos y la cohorte sintética. No toca la base de datos: los reportes,
las alertas, la auditoría y las notificaciones los maneja la API.
"""
from typing import Literal

import pandas as pd

from fastapi import Depends, FastAPI
from pydantic import BaseModel, Field

import clusters
import cohorte
import modelo
from datos import MOTIVOS
from seguridad import solo_api

app = FastAPI(title="Triaje · Servicio de IA", version="1.0")

Motivo = Literal[tuple(MOTIVOS)]


class VariablesClinicas(BaseModel):
    """Las 12 variables del modelo. Ningún campo identifica a la persona (R12)."""
    edad: float = Field(ge=18, le=120)
    sexo_M: int = Field(ge=0, le=1)
    fc: float | None = Field(default=None, ge=20, le=250)
    fr: float | None = Field(default=None, ge=4, le=80)
    pas: float | None = Field(default=None, ge=40, le=300)
    pad: float | None = Field(default=None, ge=20, le=200)
    temp_c: float | None = Field(default=None, ge=30, le=44)
    spo2: float | None = Field(default=None, ge=50, le=100)
    dolor_nrs: float | None = Field(default=None, ge=0, le=10)
    llegada_ambulancia: int | None = Field(default=None, ge=0, le=1)
    lesion: int | None = Field(default=None, ge=0, le=1)
    motivo_categoria: Motivo = "otros"


class SolicitudPrediccion(BaseModel):
    seudonimo: str = Field(min_length=8, max_length=64)
    variables: VariablesClinicas


@app.on_event("startup")
def entrenar_al_arrancar():
    # Como en la semana 9: el modelo se reconstruye desde los datos reales al arrancar.
    # Misma semilla y misma partición -> mismo modelo y mismos grupos que el cuaderno.
    modelo.entrenar()
    clusters.entrenar()


@app.get("/health", tags=["Sistema"])
def health():
    return {"status": "ok", "servicio": "ml", "modelo": modelo.VERSION}


@app.get("/modelo", tags=["Modelo"], dependencies=[Depends(solo_api)])
def ver_modelo():
    return modelo.metricas()


@app.get("/clusters", tags=["Clusters"], dependencies=[Depends(solo_api)])
def ver_clusters():
    return clusters.describir()


@app.post("/cohorte", tags=["Clusters"], dependencies=[Depends(solo_api)])
def generar_cohorte():
    return cohorte.generar()


@app.post("/predecir", tags=["Modelo"], dependencies=[Depends(solo_api)])
def predecir(solicitud: SolicitudPrediccion):
    variables = solicitud.variables.model_dump()
    resultado = modelo.predecir(variables)
    grupo = int(clusters.asignar(pd.DataFrame([variables]))[0])
    return {"seudonimo": solicitud.seudonimo, **resultado,
            "cluster": grupo, "grupo": clusters.nombre(grupo)}
