"""Autenticación de personal y autorización por rol."""

from functools import wraps

from flask import abort, g, redirect, request, session, url_for
from werkzeug.security import check_password_hash

from app.extensions import db
from app.models import Usuario


def usuario_actual() -> Usuario | None:
    usuario_id = session.get("usuario_id")
    if not usuario_id:
        return None
    return db.session.get(Usuario, usuario_id)


def requiere_personal(*roles: str):
    def decorador(func):
        @wraps(func)
        def protegida(*args, **kwargs):
            usuario = usuario_actual()
            if usuario is None:
                return redirect(url_for("personal.login", siguiente=request.path))
            if roles and usuario.rol not in roles:
                abort(403)
            g.usuario = usuario
            return func(*args, **kwargs)

        return protegida

    return decorador


def autenticar(usuario: str, password: str) -> Usuario | None:
    candidato = Usuario.query.filter_by(usuario=usuario.strip().lower()).first()
    if candidato is None or not check_password_hash(candidato.password_hash, password):
        return None
    return candidato
