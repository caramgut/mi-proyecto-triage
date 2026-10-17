"""Borra la cohorte sintética (R07) para volver a cargarla, por ejemplo tras cambiar el modelo.

Solo toca pacientes con origen = 'sintetico' (documentos 99000000xx). Los pacientes reales no se tocan.
Uso, desde la carpeta back:
    python scripts/limpiar_cohorte_sintetica.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import psycopg2

from core.config import PG_CONNECTION_STRING

SINTETICOS = "SELECT numero_documento_paciente FROM pacientes WHERE origen = 'sintetico'"
ENCUENTROS = f"SELECT id_encuentro FROM encuentros WHERE id_paciente IN ({SINTETICOS})"

# Orden inverso a las llaves foráneas: primero lo que depende de los pacientes
PASOS = [
    ("observaciones", f"DELETE FROM observaciones WHERE id_encuentro IN ({ENCUENTROS})"),
    ("encuentros", f"DELETE FROM encuentros WHERE id_paciente IN ({SINTETICOS})"),
    ("ia_cohorte", f"DELETE FROM ia_cohorte WHERE numero_documento_paciente IN ({SINTETICOS})"),
    ("pacientes", "DELETE FROM pacientes WHERE origen = 'sintetico'"),
]

if __name__ == "__main__":
    with psycopg2.connect(PG_CONNECTION_STRING) as conn, conn.cursor() as cur:
        cur.execute(f"SELECT count(*) FROM ({SINTETICOS}) s")
        n = cur.fetchone()[0]
        if n == 0:
            print("No hay pacientes sintéticos: nada que borrar.")
            sys.exit(0)
        if input(f"Se borrarán {n} pacientes sintéticos y sus datos. Escribe SI para continuar: ") != "SI":
            print("Cancelado.")
            sys.exit(0)
        for tabla, sql in PASOS:
            cur.execute(sql)
            print(f"{tabla}: {cur.rowcount} filas borradas")
    print("Listo. Ya puedes volver a llamar POST /ia/cohorte.")
