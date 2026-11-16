"""Menú y pedido del cliente: mesa, para llevar y pantalla del código."""

from flask import (
    Blueprint,
    abort,
    current_app,
    flash,
    g,
    redirect,
    render_template,
    request,
    session,
    url_for,
)

from app.dispositivo import ip_del_cliente
from app.errores import ErrorPedido
from app.extensions import db
from app.models import Categoria, Mesa, Pedido
from app.services.carrito import aplicar_accion, agregar, asegurar_contexto, enriquecer, vaciar
from app.services.pedidos import crear_pedido_cliente_qr

bp = Blueprint("publico", __name__)


@bp.get("/")
def inicio():
    mesas = []
    if current_app.config["MOSTRAR_INDICE_DEMO"]:
        mesas = Mesa.query.filter_by(activa=True).order_by(Mesa.numero).all()
    return render_template("inicio.html", mesas=mesas)


@bp.get("/mesa/<int:numero>")
def menu_mesa(numero: int):
    return _render_menu("mesa", _mesa_activa(numero))


@bp.get("/llevar")
def menu_llevar():
    return _render_menu("llevar", None)


@bp.get("/domicilio")
def menu_domicilio():
    return _render_menu("domicilio", None)


@bp.post("/mesa/<int:numero>/agregar")
def agregar_mesa(numero: int):
    return _agregar("mesa", _mesa_activa(numero))


@bp.post("/llevar/agregar")
def agregar_llevar():
    return _agregar("llevar", None)


@bp.post("/mesa/<int:numero>/linea/<int:indice>")
def linea_mesa(numero: int, indice: int):
    return _linea("mesa", _mesa_activa(numero), indice)


@bp.post("/llevar/linea/<int:indice>")
def linea_llevar(indice: int):
    return _linea("llevar", None, indice)


@bp.post("/mesa/<int:numero>/enviar")
def enviar_mesa(numero: int):
    return _enviar("mesa", _mesa_activa(numero))


@bp.post("/llevar/enviar")
def enviar_llevar():
    return _enviar("llevar", None)


@bp.post("/domicilio/agregar")
def agregar_domicilio():
    return _agregar("domicilio", None)


@bp.post("/domicilio/linea/<int:indice>")
def linea_domicilio(indice: int):
    return _linea("domicilio", None, indice)


@bp.post("/domicilio/enviar")
def enviar_domicilio():
    return _enviar("domicilio", None)


@bp.get("/pedido/<int:pedido_id>")
def ver_pedido(pedido_id: int):
    # El número de pedido es fácil de adivinar. Solo el navegador que lo creó
    # tiene ese id en la sesión; los demás reciben 404, igual que si no existiera.
    propios = session.get("pedidos_propios", [])
    if pedido_id not in propios:
        abort(404)
    pedido = db.session.get(Pedido, pedido_id)
    if pedido is None:
        abort(404)
    whatsapp_url = None
    if pedido.tipo == "domicilio" and current_app.config["WHATSAPP_NUMERO"]:
        from urllib.parse import quote

        texto = f"Hola, hice el pedido #{pedido.id}, código {pedido.codigo}"
        whatsapp_url = f"https://wa.me/{current_app.config['WHATSAPP_NUMERO']}?text={quote(texto)}"
    return render_template("pedido_codigo.html", pedido=pedido, whatsapp_url=whatsapp_url)


def _mesa_activa(numero: int) -> Mesa:
    mesa = Mesa.query.filter_by(numero=numero).first()
    if mesa is None or not mesa.activa:
        abort(404)
    return mesa


def _bloques_menu():
    bloques = []
    categorias = Categoria.query.order_by(Categoria.orden, Categoria.id).all()
    for categoria in categorias:
        productos = [producto for producto in categoria.productos if producto.disponible]
        if productos:
            bloques.append({"categoria": categoria, "productos": productos})
    return bloques


def _render_menu(tipo: str, mesa: Mesa | None):
    carrito, reinicio = asegurar_contexto(tipo, mesa)
    if reinicio:
        flash("Se vació el carrito porque cambiaste de mesa o de tipo de pedido.", "error")
    return render_template(
        "menu.html",
        **_urls(tipo, mesa),
        lugar=_lugar(tipo, mesa),
        bloques=_bloques_menu(),
        carrito=enriquecer(carrito),
    )


def _agregar(tipo: str, mesa: Mesa | None):
    carrito, reinicio = asegurar_contexto(tipo, mesa)
    if reinicio:
        flash("Se vació el carrito porque cambiaste de mesa o de tipo de pedido.", "error")
    try:
        agregar(
            carrito,
            _entero(request.form.get("producto_id")),
            _entero(request.form.get("cantidad")),
            request.form.get("nota", ""),
        )
    except ErrorPedido as exc:
        flash(exc.mensaje, "error")
    return redirect(_url_menu(tipo, mesa))


def _linea(tipo: str, mesa: Mesa | None, indice: int):
    carrito, reinicio = asegurar_contexto(tipo, mesa)
    if reinicio:
        flash("Se vació el carrito porque cambiaste de mesa o de tipo de pedido.", "error")
        return redirect(_url_menu(tipo, mesa))
    accion = request.form.get("accion", "")
    nota = None if accion == "quitar" else request.form.get("nota")
    try:
        aplicar_accion(carrito, indice, accion, nota)
    except ErrorPedido as exc:
        flash(exc.mensaje, "error")
    return redirect(_url_menu(tipo, mesa) + "#carrito")


def _enviar(tipo: str, mesa: Mesa | None):
    carrito, reinicio = asegurar_contexto(tipo, mesa)
    if reinicio:
        flash("Se vació el carrito porque cambiaste de mesa o de tipo de pedido.", "error")
        return redirect(_url_menu(tipo, mesa))
    try:
        pedido = crear_pedido_cliente_qr(
            tipo=tipo,
            mesa=mesa,
            lineas_entrada=list(carrito.get("lineas", [])),
            ip=ip_del_cliente(),
            dispositivo_id=g.dispositivo_id,
            nombre_cliente=request.form.get("nombre_cliente", ""),
            telefono=request.form.get("telefono", ""),
            direccion=request.form.get("direccion", ""),
        )
    except ErrorPedido as exc:
        flash(exc.mensaje, "error")
        return redirect(_url_menu(tipo, mesa) + "#carrito")

    vaciar(tipo, mesa)
    propios = list(session.get("pedidos_propios", []))
    propios.append(pedido.id)
    session["pedidos_propios"] = propios[-10:]
    return redirect(url_for("publico.ver_pedido", pedido_id=pedido.id))


def _lugar(tipo: str, mesa: Mesa | None) -> str:
    if tipo == "mesa" and mesa is not None:
        return f"Mesa {mesa.numero}"
    if tipo == "domicilio":
        return "Domicilio"
    return "Para llevar"


def _url_menu(tipo: str, mesa: Mesa | None) -> str:
    if tipo == "mesa" and mesa is not None:
        return url_for("publico.menu_mesa", numero=mesa.numero)
    if tipo == "domicilio":
        return url_for("publico.menu_domicilio")
    return url_for("publico.menu_llevar")


def _urls(tipo: str, mesa: Mesa | None) -> dict:
    if tipo == "domicilio":
        return {
            "endpoint_agregar": "publico.agregar_domicilio",
            "endpoint_linea": "publico.linea_domicilio",
            "endpoint_enviar": "publico.enviar_domicilio",
            "url_kwargs": {},
        }
    if tipo == "mesa" and mesa is not None:
        return {
            "endpoint_agregar": "publico.agregar_mesa",
            "endpoint_linea": "publico.linea_mesa",
            "endpoint_enviar": "publico.enviar_mesa",
            "url_kwargs": {"numero": mesa.numero},
        }
    return {
        "endpoint_agregar": "publico.agregar_llevar",
        "endpoint_linea": "publico.linea_llevar",
        "endpoint_enviar": "publico.enviar_llevar",
        "url_kwargs": {},
    }


def _entero(valor) -> int:
    try:
        return int(valor)
    except (TypeError, ValueError):
        raise ErrorPedido("Ese dato no es válido.") from None
