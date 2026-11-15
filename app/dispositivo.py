"""Identifica el celular que arma el pedido, sin crear una cuenta."""

import re
import uuid

from flask import current_app, g, request

COOKIE = "dispositivo_id"
_FORMATO = re.compile(r"^[a-f0-9]{32}$")


def preparar_dispositivo() -> None:
    """Lee la cookie del celular o crea una nueva para esta respuesta."""
    valor = request.cookies.get(COOKIE, "")
    if _FORMATO.fullmatch(valor):
        g.dispositivo_id = valor
        g.dispositivo_nuevo = False
        return
    g.dispositivo_id = uuid.uuid4().hex
    g.dispositivo_nuevo = True


def fijar_cookie_dispositivo(response):
    if not getattr(g, "dispositivo_nuevo", False):
        return response
    response.set_cookie(
        COOKIE,
        g.dispositivo_id,
        max_age=60 * 60 * 24 * 180,
        httponly=True,
        samesite="Lax",
        secure=bool(current_app.config.get("SESSION_COOKIE_SECURE")),
        path="/",
    )
    return response


def ip_del_cliente() -> str:
    """IP que ve Flask directamente.

    No usamos X-Forwarded-For: cualquiera podría escribir esa cabecera y
    saltarse el límite de pedidos. Cuando haya un proxy de confianza, se
    configurará aparte.
    """
    return (request.remote_addr or "desconocida")[:45]
