"""Gestión básica del menú, mesas y usuarios."""

from io import BytesIO

import qrcode
from flask import Blueprint, flash, redirect, render_template, request, send_file, url_for
from sqlalchemy.exc import IntegrityError
from werkzeug.security import generate_password_hash

from app.auth import requiere_personal
from app.extensions import db
from app.models import Categoria, Mesa, Producto, ROLES_PERSONAL, Usuario
from app.qr import url_mesa

bp = Blueprint("admin", __name__, url_prefix="/admin/gestion")


@bp.get("/")
@requiere_personal("admin")
def gestion():
    return render_template(
        "admin.html",
        categorias=Categoria.query.order_by(Categoria.orden, Categoria.id).all(),
        mesas=Mesa.query.order_by(Mesa.numero).all(),
        usuarios=Usuario.query.order_by(Usuario.usuario).all(),
    )


@bp.get("/mesa/<int:mesa_id>/qr.png")
@requiere_personal("admin")
def qr_mesa(mesa_id):
    mesa = db.get_or_404(Mesa, mesa_id)
    imagen = qrcode.make(url_mesa(mesa.numero))
    archivo = BytesIO()
    imagen.save(archivo, format="PNG")
    archivo.seek(0)
    return send_file(
        archivo,
        mimetype="image/png",
        download_name=f"mesa-{mesa.numero}.png",
        max_age=0,
    )


@bp.get("/mesa/<int:mesa_id>/imprimir")
@requiere_personal("admin")
def imprimir_qr(mesa_id):
    mesa = db.get_or_404(Mesa, mesa_id)
    return render_template("imprimir_qr.html", mesa=mesa, mesa_url=url_mesa(mesa.numero))


@bp.post("/producto")
@requiere_personal("admin")
def producto():
    try:
        categoria_id = int(request.form["categoria_id"])
        precio = int(request.form["precio_cop"])
        if precio < 0:
            raise ValueError
        db.session.add(
            Producto(
                categoria_id=categoria_id,
                nombre=request.form["nombre"].strip()[:120],
                descripcion=request.form.get("descripcion", "").strip(),
                precio_cop=precio,
                disponible=True,
            )
        )
        db.session.commit()
        flash("Producto creado.", "success")
    except (KeyError, TypeError, ValueError):
        db.session.rollback()
        flash("Revisa nombre, categoría y precio.", "error")
    return redirect(url_for("admin.gestion"))


@bp.post("/producto/<int:producto_id>/disponibilidad")
@requiere_personal("admin")
def disponibilidad(producto_id):
    producto = db.get_or_404(Producto, producto_id)
    producto.disponible = not producto.disponible
    db.session.commit()
    flash("Disponibilidad actualizada.", "success")
    return redirect(url_for("admin.gestion"))


@bp.post("/mesa")
@requiere_personal("admin")
def mesa():
    try:
        numero = int(request.form["numero"])
        if numero < 1:
            raise ValueError
        db.session.add(Mesa(numero=numero, activa=True))
        db.session.commit()
        flash("Mesa creada.", "success")
    except (KeyError, TypeError, ValueError):
        db.session.rollback()
        flash("El número de mesa no es válido o ya existe.", "error")
    return redirect(url_for("admin.gestion"))


@bp.post("/mesa/<int:mesa_id>/activar")
@requiere_personal("admin")
def activar_mesa(mesa_id):
    mesa = db.get_or_404(Mesa, mesa_id)
    mesa.activa = not mesa.activa
    db.session.commit()
    return redirect(url_for("admin.gestion"))


@bp.post("/usuario")
@requiere_personal("admin")
def usuario():
    correo = request.form.get("correo", "").strip().lower()
    password = request.form.get("password", "")
    rol = request.form.get("rol", "")
    if not correo or len(password) < 10 or rol not in ROLES_PERSONAL:
        flash("Correo, contraseña de 10 caracteres y rol son obligatorios.", "error")
    else:
        try:
            db.session.add(
                Usuario(usuario=correo, password_hash=generate_password_hash(password), rol=rol)
            )
            db.session.commit()
            flash("Usuario creado.", "success")
        except IntegrityError:
            db.session.rollback()
            flash("No se pudo crear el usuario. Verifica que el correo no exista.", "error")
    return redirect(url_for("admin.gestion"))
