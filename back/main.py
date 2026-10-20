# ==========================================
# IMPORTACIONES DE FASTAPI
# ==========================================

# FastAPI: clase principal que crea la aplicación web.
# Depends: mecanismo de inyección de dependencias.
from fastapi import Depends, FastAPI

# Middleware que controla qué páginas web pueden consumir la API.
from fastapi.middleware.cors import CORSMiddleware

# Librería estándar de Python para programación asíncrona.
# Permite ejecutar tareas en segundo plano sin bloquear la API.
import asyncio

# ==========================================
# AUTENTICACIÓN Y SEGURIDAD
# ==========================================

# Router que contiene todas las rutas relacionadas con login,
# autenticación y validación de usuarios.
from auth.router import router as auth_router

# Función utilizada para verificar roles de usuario.
# Ejemplo: Admin, Médico, Enfermero.
from auth.service import requerir_roles

# ==========================================
# NÚCLEO DEL SISTEMA
# ==========================================

# Función que devuelve una conexión a PostgreSQL.
from core.database import get_db

# Configura el sistema interno de eventos asíncronos.
from core.eventos import configurar_loop

# ==========================================
# IMPORTACIÓN DE TODOS LOS MÓDULOS (ROUTERS)
# ==========================================

# Gestión de usuarios del sistema.
from routers.usuarios import router as usuarios_router

# Gestión de pacientes.
from routers.pacientes import router as pacientes_router

# Antecedentes clínicos de pacientes.
from routers.antecedentes import router as antecedentes_router

# Reportes médicos previos.
from routers.reportes_previos import router as reportes_previos_router

# Encuentros o consultas médicas.
from routers.encuentros import router as encuentros_router

# Observaciones clínicas.
from routers.observaciones import router as observaciones_router

# Diagnósticos médicos.
from routers.diagnosticos import router as diagnosticos_router

# Notas clínicas y evoluciones.
from routers.notas_clinicas import router as notas_clinicas_router

# Exámenes de laboratorio e imagenología.
from routers.examenes import router as examenes_router

# Catálogo de medicamentos.
from routers.medicamentos import router as medicamentos_router

# Fórmulas o prescripciones médicas.
from routers.prescripciones import router as prescripciones_router

# Facturación y componentes administrativos.
from routers.facturas import router as facturas_router

# Auditoría del sistema (trazabilidad).
from routers.auditoria import router as auditoria_router

# Interoperabilidad mediante estándar FHIR.
from routers.fhir import router as fhir_router

# Integración PACS/DICOM (Orthanc).
from routers.pacs import router as pacs_router

# Catálogos auxiliares.
from routers.catalogos import router as catalogos_router

# Remisiones de pacientes.
from routers.remisiones import router as remisiones_router

# Eventos clínicos.
from routers.eventos import router as eventos_router

# Suscripciones FHIR.
from routers.fhir_suscripcion import (
    router as fhir_suscripcion_router,
    iniciar_registro_suscripcion
)

# Servicios de Inteligencia Artificial.
from routers.ia import router as ia_router

# Generación de reportes mediante IA.
from routers.ia_reportes import router as ia_reportes_router

# Sistema de alertas clínicas.
from routers.alertas import (
    router as alertas_router,
    iniciar_escalamiento
)

# Papelera lógica para recuperación de registros.
from routers.papelera import router as papelera_router


# ==========================================
# CREACIÓN DE LA APLICACIÓN FASTAPI
# ==========================================

app = FastAPI(

    # Nombre visible en Swagger/OpenAPI.
    title="API de Triaje Hospitalario",

    # Versión actual del sistema.
    version="2.1.0",

    # Descripción general de la plataforma.
    description=(
        "API clínica y administrativa modularizada, "
        "con interoperabilidad FHIR R4 e integración "
        "PACS/DICOM mediante Orthanc."
    ),
)


# ==========================================
# CONFIGURACIÓN DE CORS
# ==========================================

# Lista de orígenes permitidos para acceder a la API
# desde un navegador web.
#
# Esto evita que sitios externos no autorizados
# consuman la API.
ORIGENES_PERMITIDOS = [

    # Frontend local usando localhost.
    "http://localhost:5500",

    # Frontend local usando dirección IP.
    "http://127.0.0.1:5500",
]


# Se añade el middleware de CORS.
app.add_middleware(

    # Middleware encargado de aplicar reglas CORS.
    CORSMiddleware,

    # Lista de dominios permitidos.
    allow_origins=ORIGENES_PERMITIDOS,

    # No permite compartir credenciales del navegador.
    allow_credentials=False,

    # Métodos HTTP autorizados.
    allow_methods=[
        "GET",      # Consultar
        "POST",     # Crear
        "PUT",      # Reemplazar
        "PATCH",    # Modificar parcialmente
        "DELETE",   # Eliminar
        "OPTIONS"   # Negociación CORS
    ],

    # Encabezados HTTP permitidos.
    allow_headers=[
        "Authorization",
        "Content-Type",
        "Accept"
    ],
)


# ==========================================
# REGISTRO DE MÓDULOS DEL SISTEMA
# ==========================================

# Cada include_router registra rutas en la API.

app.include_router(auth_router)

app.include_router(usuarios_router)
app.include_router(pacientes_router)

app.include_router(antecedentes_router)
app.include_router(reportes_previos_router)
app.include_router(encuentros_router)
app.include_router(observaciones_router)
app.include_router(diagnosticos_router)
app.include_router(notas_clinicas_router)
app.include_router(examenes_router)
app.include_router(medicamentos_router)
app.include_router(prescripciones_router)
app.include_router(facturas_router)

app.include_router(auditoria_router)
app.include_router(fhir_router)
app.include_router(pacs_router)
app.include_router(catalogos_router)
app.include_router(remisiones_router)
app.include_router(eventos_router)
app.include_router(fhir_suscripcion_router)
app.include_router(ia_router)
app.include_router(ia_reportes_router)
app.include_router(alertas_router)
app.include_router(papelera_router)

# Ejemplo:
#
# Si el router de pacientes tiene:
#
# @router.get("/pacientes")
#
# entonces al incluirlo aquí queda disponible:
#
# GET /pacientes


# ==========================================
# EVENTO DE INICIO DEL SISTEMA
# ==========================================

# Esta función se ejecuta automáticamente
# una única vez cuando la API arranca.
@app.on_event("startup")
async def _iniciar_bus_eventos():

    # Obtiene el loop asíncrono actualmente activo
    # y lo registra para el sistema de eventos.
    configurar_loop(asyncio.get_running_loop())

    # Registra las suscripciones FHIR.
    iniciar_registro_suscripcion()

    # Inicia el proceso automático de escalamiento
    # de alertas clínicas.
    #
    # Según el comentario del proyecto:
    # revisa cada 30 segundos las alertas
    # pendientes de reconocimiento.
    iniciar_escalamiento()


# ==========================================
# ENDPOINT RAÍZ DEL SISTEMA
# ==========================================

# Ruta:
# GET /
@app.get("/", tags=["Sistema"])
def raiz():

    # Devuelve información básica de la API.
    return {
        "mensaje": "API de Triaje Hospitalario",
        "version": "2.1.0",
    }


# ==========================================
# ENDPOINT DE DIAGNÓSTICO DE BASE DE DATOS
# ==========================================

# Ruta:
# GET /estado-bd
@app.get("/estado-bd", tags=["Sistema"])
def estado_bd(

    # Obtiene una conexión activa a PostgreSQL.
    db=Depends(get_db),

    # Solo administradores pueden ejecutar este endpoint.
    usuario=Depends(requerir_roles("Admin")),
):

    # Crea un cursor SQL.
    #
    # El cursor es el objeto encargado de enviar
    # consultas a PostgreSQL.
    cur = db.cursor()

    try:

        # Consulta SQL ejecutada sobre PostgreSQL.
        #
        # current_database() -> nombre de la base activa
        # current_user       -> usuario de conexión
        cur.execute(
            "SELECT current_database(), current_user;"
        )

        # Recupera una única fila de resultados.
        #
        # Ejemplo:
        # ("triaje","admin")
        bd, usuario_bd = cur.fetchone()

        # Respuesta JSON enviada al cliente.
        return {
            "estado": "ok",
            "base_datos": bd,
            "usuario": usuario_bd,
        }

    finally:

        # Se ejecuta siempre, incluso si ocurre un error.
        #
        # Libera recursos y evita fugas de memoria
        # o conexiones abiertas.
        cur.close()
