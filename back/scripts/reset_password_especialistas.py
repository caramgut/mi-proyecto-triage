import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import psycopg2

from core.config import PG_CONNECTION_STRING
from core.security import hash_password


NUEVA_PASSWORD = "Especialista123*"

ESPECIALISTAS = [
    "especialista.1000000101",
    "m.interna1.66749669",
    "m.ortopedia.129345873",
]


def main():
    nuevo_hash = hash_password(NUEVA_PASSWORD)

    conn = psycopg2.connect(PG_CONNECTION_STRING)

    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE usuarios
                SET
                    password_hash = %s,
                    intentos_fallidos = 0,
                    bloqueado = FALSE,
                    bloqueado_at = NULL,
                    updated_at = NOW()
                WHERE username = ANY(%s)
                RETURNING
                    numero_documento_usuario,
                    username,
                    nombres,
                    apellidos;
                """,
                (nuevo_hash, ESPECIALISTAS),
            )

            actualizados = cur.fetchall()

        conn.commit()

        print("\nEspecialistas actualizados:\n")

        for documento, username, nombres, apellidos in actualizados:
            print(
                f"- {documento} | {username} | "
                f"{nombres} {apellidos}"
            )

        print(f"\nTotal actualizados: {len(actualizados)}")

        if len(actualizados) == 3:
            print("\n✅ Las 3 contraseñas fueron actualizadas correctamente.")
            print("✅ Contraseña nueva: Especialista123*")
        else:
            print(
                "\n⚠️ Se esperaban 3 especialistas, "
                f"pero se actualizaron {len(actualizados)}."
            )

    except Exception:
        conn.rollback()
        raise

    finally:
        conn.close()


if __name__ == "__main__":
    main()