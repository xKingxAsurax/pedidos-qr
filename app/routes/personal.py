"""Login y panel operativo del personal."""

from collections import defaultdict
from time import monotonic

from flask import Blueprint, flash, g, redirect, render_template, request, session, url_for

from app.auth import autenticar, requiere_personal
from app.errores import ErrorPedido
from app.extensions import db
from app.models import (
    ESTADO_CONFIRMADO,
    ESTADO_EN_PREPARACION,
    ESTADO_LISTO,
    ESTADOS_EN_COCINA,
    Categoria,
    Mesa,
    Pedido,
    PedidoItem,
    Producto,
)
from app.services.personal import (
    agregar_items,
    buscar_pedidos,
    cambiar_estado,
    cancelar_pedido,
    confirmar_por_codigo,
    crear_pedido_personal,
    quitar_item,
)

bp = Blueprint("personal", __name__, url_prefix="/admin")
_intentos: defaultdict[str, list[float]] = defaultdict(list)


@bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        ahora = monotonic()
        ip = request.remote_addr or "desconocida"
        _intentos[ip] = [marca for marca in _intentos[ip] if ahora - marca < 60]
        if len(_intentos[ip]) >= 5:
            flash("Demasiados intentos. Espera un minuto e intenta otra vez.", "error")
            return render_template("login.html"), 429
        _intentos[ip].append(ahora)
        usuario = autenticar(request.form.get("correo", ""), request.form.get("password", ""))
        if usuario is None:
            flash("Correo o contraseña incorrectos.", "error")
            return render_template("login.html"), 401
        session.clear()
        session["usuario_id"] = usuario.id
        _intentos.pop(ip, None)
        siguiente = request.args.get("siguiente")
        destino = url_for("admin.gestion") if usuario.rol == "admin" else url_for("personal.panel")
        if not siguiente or not siguiente.startswith("/") or siguiente.startswith("//"):
            siguiente = destino
        return redirect(siguiente)
    return render_template("login.html")


@bp.post("/logout")
def logout():
    session.clear()
    return redirect(url_for("personal.login"))


@bp.get("/")
@requiere_personal()
def panel():
    pedidos = buscar_pedidos(request.args.get("q", ""))
    columnas = {
        estado: [pedido for pedido in pedidos if pedido.estado == estado]
        for estado in (ESTADO_CONFIRMADO, ESTADO_EN_PREPARACION, ESTADO_LISTO)
    }
    pendientes = [pedido for pedido in pedidos if pedido.estado == "pendiente_confirmacion"]
    return render_template("panel.html", columnas=columnas, pendientes=pendientes, busqueda=request.args.get("q", ""))


@bp.post("/pedidos/confirmar")
@requiere_personal("admin", "caja", "mesero")
def confirmar():
    try:
        confirmar_por_codigo(request.form.get("codigo", ""), g.usuario)
        flash("Pedido confirmado y enviado a preparación.", "success")
    except ErrorPedido as exc:
        flash(exc.mensaje, "error")
    return redirect(url_for("personal.panel"))


@bp.post("/pedidos/<int:pedido_id>/estado")
@requiere_personal("admin", "caja", "mesero")
def estado(pedido_id):
    pedido = db.get_or_404(Pedido, pedido_id)
    try:
        cambiar_estado(pedido, request.form.get("estado", ""), g.usuario)
        flash("Estado actualizado.", "success")
    except ErrorPedido as exc:
        flash(exc.mensaje, "error")
    return redirect(url_for("personal.panel"))


@bp.route("/pedidos/nuevo", methods=["GET", "POST"])
@requiere_personal("admin", "caja", "mesero")
def nuevo_pedido():
    if request.method == "POST":
        try:
            tipo = request.form.get("tipo", "")
            producto_ids = request.form.getlist("producto_id")
            cantidades = request.form.getlist("cantidad")
            notas = request.form.getlist("nota")
            lineas = [
                {"producto_id": pid, "cantidad": cantidad, "nota": nota}
                for pid, cantidad, nota in zip(producto_ids, cantidades, notas)
                if _cantidad_informada(cantidad)
            ]
            crear_pedido_personal(
                tipo=tipo,
                mesa_id=int(request.form["mesa_id"]) if request.form.get("mesa_id") else None,
                lineas=lineas,
                usuario=g.usuario,
                nombre_cliente=request.form.get("nombre_cliente", ""),
                telefono=request.form.get("telefono", ""),
                direccion=request.form.get("direccion", ""),
            )
            flash("Pedido creado y enviado a preparación.", "success")
            return redirect(url_for("personal.panel"))
        except (ErrorPedido, ValueError) as exc:
            flash(str(exc), "error")
    return render_template(
        "nuevo_pedido.html",
        categorias=Categoria.query.order_by(Categoria.orden).all(),
        mesas=Mesa.query.filter_by(activa=True).order_by(Mesa.numero).all(),
    )


@bp.get("/pedidos/<int:pedido_id>")
@requiere_personal()
def detalle(pedido_id):
    pedido = db.get_or_404(Pedido, pedido_id)
    return render_template(
        "detalle_pedido.html",
        pedido=pedido,
        productos=Producto.query.filter_by(disponible=True).order_by(Producto.nombre).all(),
    )


@bp.post("/pedidos/<int:pedido_id>/cancelar")
@requiere_personal("admin", "caja")
def cancelar(pedido_id):
    pedido = db.get_or_404(Pedido, pedido_id)
    try:
        cancelar_pedido(pedido, g.usuario, request.form.get("motivo", ""))
        flash("Pedido cancelado.", "success")
    except ErrorPedido as exc:
        flash(exc.mensaje, "error")
    return redirect(url_for("personal.detalle", pedido_id=pedido.id))


@bp.post("/pedidos/<int:pedido_id>/agregar")
@requiere_personal("admin", "caja", "mesero")
def agregar(pedido_id):
    pedido = db.get_or_404(Pedido, pedido_id)
    try:
        lineas = [
            {"producto_id": pid, "cantidad": cantidad, "nota": nota}
            for pid, cantidad, nota in zip(
                request.form.getlist("producto_id"),
                request.form.getlist("cantidad"),
                request.form.getlist("nota"),
            )
            if _cantidad_informada(cantidad)
        ]
        agregar_items(pedido, lineas, g.usuario)
        flash("Ítems agregados como nueva ronda.", "success")
    except (ErrorPedido, ValueError) as exc:
        flash(str(exc), "error")
    ancla = next(
        (valor for valor in request.form.getlist("producto_id") if valor.isdigit()),
        None,
    )
    destino = url_for("personal.detalle", pedido_id=pedido.id)
    return redirect(destino + (f"#producto-{ancla}" if ancla else ""))


@bp.post("/pedidos/<int:pedido_id>/items/<int:item_id>/quitar")
@requiere_personal("admin")
def quitar(pedido_id, item_id):
    pedido = db.get_or_404(Pedido, pedido_id)
    item = db.get_or_404(PedidoItem, item_id)
    try:
        quitar_item(pedido, item, g.usuario, request.form.get("motivo", ""))
        flash("Ítem quitado.", "success")
    except ErrorPedido as exc:
        flash(exc.mensaje, "error")
    return redirect(url_for("personal.detalle", pedido_id=pedido.id))


def _cantidad_informada(valor: str) -> bool:
    if not valor or not valor.strip():
        return False
    try:
        return int(valor) != 0
    except ValueError:
        return True
