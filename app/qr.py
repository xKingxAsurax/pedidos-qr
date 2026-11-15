"""Construcción de códigos QR para las mesas."""

from flask import current_app, url_for


def url_mesa(numero: int) -> str:
    base = current_app.config.get("PUBLIC_BASE_URL", "").strip().rstrip("/")
    if base:
        return f"{base}{url_for('publico.menu_mesa', numero=numero)}"
    return url_for("publico.menu_mesa", numero=numero, _external=True)
