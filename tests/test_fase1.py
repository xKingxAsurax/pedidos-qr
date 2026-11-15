"""Fase 1: el precio lo pone el servidor, el código no se repite y lo vencido expira."""

import re
from datetime import timedelta

import pytest

from app.errores import ErrorPedido
from app.extensions import db
from app.models import (
    ESTADO_CONFIRMADO,
    ESTADO_EXPIRADO,
    ESTADO_PENDIENTE,
    ORIGEN_CLIENTE_QR,
    Pedido,
    Producto,
)
from app.services.pedidos import (
    crear_pedido_cliente_qr,
    expirar_pedidos_vencidos,
    puede_confirmar,
    visible_en_cocina,
)
from app.tiempo import ahora_utc


def _id(nombre):
    return Producto.query.filter_by(nombre=nombre).one().id


def _pedir(dispositivo=None, ip="203.0.113.10", cantidad=1, nota=""):
    producto_id = _id("Limonada")
    return crear_pedido_cliente_qr(
        tipo="llevar",
        mesa=None,
        lineas_entrada=[
            {
                "producto_id": producto_id,
                "cantidad": cantidad,
                "nota": nota,
                "precio_cop": 1,
            }
        ],
        ip=ip,
        dispositivo_id=dispositivo or "a" * 32,
    )


def _agregar(client, producto_id, cantidad=1, nota="", ruta="/llevar/agregar", seguir=False):
    return client.post(
        ruta,
        data={"producto_id": producto_id, "cantidad": cantidad, "nota": nota, "precio_cop": "1"},
        follow_redirects=seguir,
    )


def test_el_precio_y_el_nombre_salen_de_la_base(client, app):
    with app.app_context():
        producto_id = _id("Limonada")

    agregado = _agregar(client, producto_id, cantidad=2)
    assert agregado.status_code == 302

    with app.app_context():
        producto = db.session.get(Producto, producto_id)
        producto.precio_cop = 9500
        producto.nombre = "Limonada grande"
        db.session.commit()

    respuesta = client.post("/llevar/enviar", data={"precio_cop": "1", "total_cop": "1"})
    assert respuesta.status_code == 302

    with app.app_context():
        pedido = Pedido.query.one()
        item = pedido.items[0]
        assert item.precio_snapshot_cop == 9500
        assert item.nombre_snapshot == "Limonada grande"
        assert item.cantidad == 2
        assert pedido.total_cop == 19000
        assert pedido.estado == ESTADO_PENDIENTE
        assert pedido.origen == ORIGEN_CLIENTE_QR
        assert re.fullmatch(r"\d{4}", pedido.codigo)
        assert timedelta(minutes=14) < (pedido.expira_en - pedido.creado_en) < timedelta(minutes=16)

        producto = db.session.get(Producto, producto_id)
        producto.nombre = "Otro"
        producto.precio_cop = 1
        db.session.commit()
        db.session.refresh(item)
        assert item.nombre_snapshot == "Limonada grande"
        assert item.precio_snapshot_cop == 9500

    pagina = client.get(respuesta.headers["Location"])
    assert pagina.status_code == 200
    assert "$19.000" in pagina.get_data(as_text=True)
    assert "Dile este código en caja" in pagina.get_data(as_text=True)


def test_el_codigo_no_se_repite_entre_pendientes(app, monkeypatch):
    codigos = iter(["1111", "1111", "2222"])
    monkeypatch.setattr("app.services.pedidos._codigo_aleatorio", lambda: next(codigos))

    with app.app_context():
        primero = _pedir(dispositivo="b" * 32)
        segundo = _pedir(dispositivo="c" * 32, ip="203.0.113.20")
        assert primero.codigo == "1111"
        assert segundo.codigo == "2222"
        assert primero.items[0].precio_snapshot_cop == 8000


def test_si_no_hay_codigo_libre_no_crea_otro_pedido(app, monkeypatch):
    monkeypatch.setattr("app.services.pedidos._codigo_aleatorio", lambda: "1111")
    with app.app_context():
        _pedir()
        with pytest.raises(ErrorPedido):
            _pedir(dispositivo="d" * 32, ip="203.0.113.21")
        assert Pedido.query.count() == 1


def test_al_vencer_el_codigo_queda_libre_y_no_entra_a_cocina(app, monkeypatch):
    monkeypatch.setattr("app.services.pedidos._codigo_aleatorio", lambda: "4242")
    with app.app_context():
        primero = _pedir()
        assert puede_confirmar(primero) is True
        assert visible_en_cocina(primero) is False

        primero.expira_en = ahora_utc() - timedelta(minutes=1)
        db.session.commit()
        assert puede_confirmar(primero) is False
        assert primero.estado == ESTADO_PENDIENTE

        segundo = _pedir(dispositivo="e" * 32, ip="203.0.113.30")
        db.session.refresh(primero)
        assert expirar_pedidos_vencidos() == 0
        assert primero.estado == ESTADO_EXPIRADO
        assert primero.codigo == segundo.codigo == "4242"
        assert segundo.estado == ESTADO_PENDIENTE
        assert visible_en_cocina(primero) is False
        assert puede_confirmar(primero) is False
        assert puede_confirmar(segundo) is True


def test_un_pedido_confirmado_no_se_marca_expirado(app):
    with app.app_context():
        pedido = _pedir()
        pedido.estado = ESTADO_CONFIRMADO
        pedido.expira_en = ahora_utc() - timedelta(minutes=5)
        db.session.commit()
        assert expirar_pedidos_vencidos() == 0
        db.session.refresh(pedido)
        assert pedido.estado == ESTADO_CONFIRMADO
        assert visible_en_cocina(pedido) is True
        assert puede_confirmar(pedido) is False


def test_un_pedido_de_otro_dia_no_se_podria_confirmar(app):
    with app.app_context():
        pedido = _pedir()
        pedido.creado_en = ahora_utc() - timedelta(days=2)
        pedido.expira_en = ahora_utc() + timedelta(minutes=10)
        db.session.commit()
        assert puede_confirmar(pedido) is False


def test_maximo_tres_pendientes_por_dispositivo(client, app):
    app.config["MAX_PENDIENTES_POR_IP"] = 50
    with app.app_context():
        producto_id = _id("Limonada")

    for _ in range(3):
        _agregar(client, producto_id)
        assert client.post("/llevar/enviar").status_code == 302

    _agregar(client, producto_id)
    rechazo = client.post("/llevar/enviar", follow_redirects=True)
    assert "Ya tienes 3 pedidos sin confirmar" in rechazo.get_data(as_text=True)
    with app.app_context():
        assert Pedido.query.count() == 3


def test_maximo_tres_pendientes_por_ip(app):
    app.config["MAX_PENDIENTES_POR_DISPOSITIVO"] = 50
    app.config["MAX_PENDIENTES_POR_IP"] = 3
    uno = app.test_client()
    otro = app.test_client()
    with app.app_context():
        producto_id = _id("Limonada")

    _agregar(uno, producto_id)
    assert uno.post("/llevar/enviar").status_code == 302
    _agregar(uno, producto_id)
    assert uno.post("/llevar/enviar").status_code == 302
    _agregar(otro, producto_id)
    assert otro.post("/llevar/enviar").status_code == 302

    _agregar(otro, producto_id)
    rechazo = otro.post("/llevar/enviar", follow_redirects=True)
    assert "Desde esta red ya hay 3 pedidos" in rechazo.get_data(as_text=True)
    with app.app_context():
        assert Pedido.query.count() == 3


def test_cuando_vencen_se_puede_crear_otro(client, app):
    app.config["MAX_PENDIENTES_POR_IP"] = 50
    with app.app_context():
        producto_id = _id("Limonada")
    for _ in range(3):
        _agregar(client, producto_id)
        client.post("/llevar/enviar")

    with app.app_context():
        for pedido in Pedido.query.all():
            pedido.expira_en = ahora_utc() - timedelta(minutes=1)
        db.session.commit()

    _agregar(client, producto_id)
    assert client.post("/llevar/enviar").status_code == 302
    with app.app_context():
        assert Pedido.query.filter_by(estado=ESTADO_EXPIRADO).count() == 3
        assert Pedido.query.filter_by(estado=ESTADO_PENDIENTE).count() == 1


def test_otro_navegador_no_ve_el_codigo(client, app):
    with app.app_context():
        producto_id = _id("Limonada")
    _agregar(client, producto_id)
    creado = client.post("/llevar/enviar")
    pagina = client.get(creado.headers["Location"])
    with app.app_context():
        codigo = Pedido.query.one().codigo
    assert codigo in pagina.get_data(as_text=True)

    extrano = app.test_client()
    oculto = extrano.get(creado.headers["Location"])
    assert oculto.status_code == 404
    assert codigo not in oculto.get_data(as_text=True)


def test_notas_distintas_no_se_mezclan(client, app):
    with app.app_context():
        producto_id = _id("Limonada")
    _agregar(client, producto_id, nota="sin hielo")
    _agregar(client, producto_id, nota="con hielo")
    _agregar(client, producto_id, nota="sin hielo")
    client.post("/llevar/enviar")
    with app.app_context():
        notas = sorted((item.nota, item.cantidad) for item in Pedido.query.one().items)
    assert notas == [("con hielo", 1), ("sin hielo", 2)]


def test_producto_agotado_no_se_pide_ni_se_muestra(client, app):
    pagina = client.get("/llevar")
    html = pagina.get_data(as_text=True)
    assert "Limonada" in html
    assert "Agua" not in html
    assert 'name="csrf_token"' in html
    assert "no-store" in pagina.headers["Cache-Control"]

    with app.app_context():
        agua_id = _id("Agua")
    rechazo = _agregar(client, agua_id, seguir=True)
    assert "no está disponible" in rechazo.get_data(as_text=True)
    with app.app_context():
        assert Pedido.query.count() == 0


def test_cantidad_en_cero_no_crea_pedido(client, app):
    with app.app_context():
        producto_id = _id("Limonada")
    _agregar(client, producto_id)
    with client.session_transaction() as sesion:
        carrito = sesion["carrito"]
        carrito["lineas"][0]["cantidad"] = 0
        sesion["carrito"] = carrito
    rechazo = client.post("/llevar/enviar", follow_redirects=True)
    assert "cantidad" in rechazo.get_data(as_text=True).lower()
    with app.app_context():
        assert Pedido.query.count() == 0


def test_mesa_inactiva_o_inexistente_responde_404(client):
    assert client.get("/mesa/9").status_code == 404
    assert client.get("/mesa/100").status_code == 404
    assert "mesa ya no está activa" in client.get("/mesa/9").get_data(as_text=True)


def test_el_pedido_de_mesa_guarda_la_mesa(client, app):
    with app.app_context():
        producto_id = _id("Limonada")
    _agregar(client, producto_id, ruta="/mesa/1/agregar")
    assert client.post("/mesa/1/enviar").status_code == 302
    with app.app_context():
        pedido = Pedido.query.one()
        assert pedido.tipo == "mesa"
        assert pedido.mesa.numero == 1
        assert pedido.origen == ORIGEN_CLIENTE_QR


def test_cambiar_de_mesa_vacia_el_carrito(client, app):
    with app.app_context():
        producto_id = _id("Limonada")
    _agregar(client, producto_id, ruta="/mesa/1/agregar")
    pagina = client.get("/llevar")
    html = pagina.get_data(as_text=True)
    assert "Se vació el carrito" in html
    assert "Aún no has agregado productos" in html


def test_el_inicio_muestra_la_mesa_activa(client):
    html = client.get("/").get_data(as_text=True)
    assert "Para llevar" in html
    assert 'href="/mesa/1"' in html
    assert 'href="/mesa/9"' not in html
