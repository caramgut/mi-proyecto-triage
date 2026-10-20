# ==========================================================
# ROUTER DE AUTENTICACIÓN Y SEGURIDAD
# ==========================================================
#
# Este módulo define los endpoints relacionados con:
#
# - Inicio de sesión (login)
# - Consulta del usuario autenticado
# - Auditoría de autenticaciones
# - Desbloqueo de cuentas por administradores
#
# Un router es un conjunto de rutas agrupadas por funcionalidad.
# Posteriormente este router es registrado en main.py mediante:
#
# app.include_router(auth_router)
# ==========================================================


# ==========================================================
# IMPORTACIONES DE FASTAPI
# ==========================================================

# APIRouter:
# Permite crear un conjunto de endpoints agrupados.
#
# Depends:
# Sistema de inyección de dependencias de FastAPI.
# Permite ejecutar funciones automáticamente antes
# de entrar a un endpoint.
#
# Query:
# Permite validar parámetros enviados en la URL.
from fastapi import APIRouter, Depends, Query


# ==========================================================
# IMPORTACIONES DE PYDANTIC
# ==========================================================

# BaseModel:
# Se utiliza para definir modelos de datos.
#
# Field:
# Permite agregar validaciones y restricciones
# a los atributos del modelo.
from pydantic import BaseModel, Field


# ==========================================================
# CONEXIÓN A BASE DE DATOS
# ==========================================================

# Función que proporciona una conexión activa
# a PostgreSQL.
from core.database import get_db


# ==========================================================
# SERVICIOS DE AUTENTICACIÓN
# ==========================================================

from auth.service import (

    # Verifica usuario y contraseña.
    autenticar_usuario,

    # Desbloquea una cuenta de usuario.
    desbloquear_usuario,

    # Genera el JSON de respuesta del login.
    generar_respuesta_login,

    # Consulta historial de autenticaciones.
    listar_auth_logs,

    # Verifica roles del usuario.
    requerir_roles,

    # Obtiene el usuario autenticado actualmente.
    usuario_actual
)


# ==========================================================
# CREACIÓN DEL ROUTER
# ==========================================================

# No se define un prefix global porque:
#
# /auth/login
# /auth/me
#
# deben mantenerse exactamente con esas rutas.
#
# También se conserva:
#
# /usuarios/{documento}/desbloquear
#
# para no alterar compatibilidad con el frontend.
router = APIRouter()


# ==========================================================
# MODELO DE ENTRADA DEL LOGIN
# ==========================================================

class LoginIn(BaseModel):

    # Nombre de usuario.
    #
    # Restricciones:
    # - mínimo 3 caracteres
    # - máximo 50 caracteres
    # - solo letras, números, puntos,
    #   guiones y guión bajo
    username: str = Field(
        min_length=3,
        max_length=50,
        pattern=r"^[A-Za-z0-9._-]+$"
    )

    # Contraseña.
    #
    # Únicamente exige que tenga al menos
    # un carácter.
    password: str = Field(
        min_length=1
    )


# ==========================================================
# LOGIN
# ==========================================================

# Endpoint:
#
# POST /auth/login
#
# Se utiliza para iniciar sesión.
#
# Recibe:
# {
#   "username":"admin",
#   "password":"123456"
# }
@router.post(
    "/auth/login",
    tags=["Autenticación"]
)
def login(

    # Datos del cuerpo de la petición.
    datos: LoginIn,

    # FastAPI ejecuta automáticamente get_db()
    # y proporciona una conexión activa.
    db=Depends(get_db)
):

    # Verifica si el usuario existe
    # y si la contraseña es correcta.
    usuario = autenticar_usuario(
        datos.username,
        datos.password,
        db
    )

    # Genera la respuesta final
    # (normalmente token JWT, datos del usuario, etc.)
    return generar_respuesta_login(usuario)


# ==========================================================
# USUARIO ACTUAL
# ==========================================================

# Endpoint:
#
# GET /auth/me
#
# Devuelve información del usuario
# actualmente autenticado.
@router.get(
    "/auth/me",
    tags=["Autenticación"]
)
def me(

    # FastAPI ejecuta usuario_actual()
    # antes de entrar al endpoint.
    #
    # Si el token es inválido,
    # la petición será rechazada.
    usuario=Depends(usuario_actual)
):

    # Devuelve el usuario autenticado.
    return usuario


# ==========================================================
# AUDITORÍA DE AUTENTICACIÓN
# ==========================================================

# Endpoint:
#
# GET /auth/logs
#
# Permite consultar registros de:
#
# - Logins exitosos
# - Logins fallidos
# - Bloqueos de cuenta
# - Eventos de autenticación
#
# Solo los administradores tienen acceso.
@router.get(
    "/auth/logs",
    tags=["Autenticación"]
)
def auth_logs(

    # Número máximo de registros
    # a devolver.
    #
    # Valor por defecto: 100
    #
    # Restricciones:
    # mínimo: 1
    # máximo: 500
    limite: int = Query(
        100,
        ge=1,
        le=500
    ),

    # Conexión a PostgreSQL.
    db=Depends(get_db),

    # Verifica automáticamente
    # que el usuario tenga rol Admin.
    admin=Depends(
        requerir_roles("Admin")
    )
):

    # Obtiene los logs de autenticación.
    return listar_auth_logs(
        db,
        limite
    )


# ==========================================================
# DESBLOQUEO DE CUENTAS
# ==========================================================

# Endpoint:
#
# PATCH /usuarios/123456/desbloquear
#
# Utilizado cuando una cuenta fue bloqueada
# por demasiados intentos fallidos de login.
#
# Solo puede ejecutarlo un administrador.
@router.patch(
    "/usuarios/{documento}/desbloquear",
    tags=["Usuarios"]
)
def desbloquear(

    # Documento de identidad del usuario
    # que será desbloqueado.
    documento: int,

    # Conexión a PostgreSQL.
    db=Depends(get_db),

    # Verifica rol de administrador.
    admin=Depends(
        requerir_roles("Admin")
    )
):

    # Ejecuta la lógica de desbloqueo.
    return desbloquear_usuario(
        documento,
        admin,
        db
    )
