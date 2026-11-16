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
        nombre = request.form.get("nombre", "").strip()
        if precio < 0 or not nombre or db.session.get(Categoria, categoria_id) is None:
            raise ValueError
        db.session.add(
            Producto(
                categoria_id=categoria_id,
                nombre=nombre[:120],
                descripcion=request.form.get("descripcion", "").strip()[:2000],
                precio_cop=precio,
                disponible=True,
            )
        )
        db.session.commit()
        flash("Producto creado.", "success")
    except (KeyError, TypeError, ValueError, IntegrityError):
        db.session.rollback()
        flash("Revisa nombre, categoría y precio.", "error")
    return redirect(url_for("admin.gestion"))


@bp.post("/producto/<int:producto_id>/editar")
@requiere_personal("admin")
def editar_producto(producto_id):
    producto = db.get_or_404(Producto, producto_id)
    try:
        categoria_id = int(request.form["categoria_id"])
        precio = int(request.form["precio_cop"])
        nombre = request.form.get("nombre", "").strip()
        if not nombre or precio < 0 or db.session.get(Categoria, categoria_id) is None:
            raise ValueError
        producto.categoria_id = categoria_id
        producto.nombre = nombre[:120]
        producto.descripcion = request.form.get("descripcion", "").strip()[:2000]
        producto.precio_cop = precio
        db.session.commit()
        flash("Producto actualizado.", "success")
    except (KeyError, TypeError, ValueError, IntegrityError):
        db.session.rollback()
        flash("Revisa nombre, categoría y precio.", "error")
    return redirect(url_for("admin.gestion"))


@bp.post("/categoria")
@requiere_personal("admin")
def categoria():
    nombre = request.form.get("nombre", "").strip()
    try:
        orden = int(request.form.get("orden", "0"))
        if not nombre:
            raise ValueError
        db.session.add(Categoria(nombre=nombre[:80], orden=orden))
        db.session.commit()
        flash("Categoría creada.", "success")
    except (TypeError, ValueError, IntegrityError):
        db.session.rollback()
        flash("Escribe un nombre y un orden válido.", "error")
    return redirect(url_for("admin.gestion"))


@bp.post("/categoria/<int:categoria_id>/editar")
@requiere_personal("admin")
def editar_categoria(categoria_id):
    categoria = db.get_or_404(Categoria, categoria_id)
    nombre = request.form.get("nombre", "").strip()
    try:
        orden = int(request.form.get("orden", "0"))
        if not nombre:
            raise ValueError
        categoria.nombre = nombre[:80]
        categoria.orden = orden
        db.session.commit()
        flash("Categoría actualizada.", "success")
    except (TypeError, ValueError, IntegrityError):
        db.session.rollback()
        flash("Escribe un nombre y un orden válido.", "error")
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
    except (KeyError, TypeError, ValueError, IntegrityError):
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
