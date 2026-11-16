"""Arranque local. Desde el celular, usa la IP de este computador y el puerto 5000."""

import os

from app import create_app
from app.extensions import db
from app.seed import cargar_demo

app = create_app()


def preparar_base() -> None:
    with app.app_context():
        db.create_all()
        cargar_demo(modo_demo=app.config.get("MODO_DEMO", False))


if __name__ == "__main__":
    preparar_base()
    puerto = int(os.environ.get("PORT", "5000"))
    print(f"En este computador: http://127.0.0.1:{puerto}")
    print("En el celular, misma red Wi-Fi: http://IP-DE-ESTE-PC:" + str(puerto))
    app.run(
        host="0.0.0.0",
        port=puerto,
        debug=os.environ.get("FLASK_DEBUG") == "1",
    )
