import importlib
from datetime import timedelta

import pytest
from werkzeug.security import generate_password_hash

from app import create_app
from app.config import Config
from app.extensions import db
from app.models import (
    ESTADO_CANCELADO,
    ESTADO_CONFIRMADO,
    ESTADO_ENTREGADO,
    ESTADO_EXPIRADO,
    ESTADO_PENDIENTE,
    Pedido,
    Usuario,
)
from app.seed import cargar_demo
from app.services.personal import TRANSICIONES, buscar_pedidos, confirmar_por_codigo
from app.tiempo import ahora_utc
from app.errores import ErrorPedido


def _crear_usuario(rol="admin", correo="admin@reparaciones.test"):
    usuario = Usuario(
        usuario=correo,
        password_hash=generate_password_hash("una-clave-segura"),
        rol=rol,
    )
    db.session.add(usuario)
    db.session.commit()
    return usuario


def _login(client, correo="admin@reparaciones.test", siguiente=None):
    ruta = "/admin/login"
    if siguiente is not None:
        ruta += f"?siguiente={siguiente}"
    return client.post(
        ruta,
        data={"correo": correo, "password": "una-clave-segura"},
    )


def test_domicilio_conserva_sus_urls_y_redirige_al_domicilio(client, app):
    with app.app_context():
        producto_id = 1
    respuesta = client.post(
        "/domicilio/agregar",
        data={"producto_id": producto_id, "cantidad": "1"},
        follow_redirects=True,
    )
    html = respuesta.get_data(as_text=True)
    assert respuesta.request.path == "/domicilio"
    assert 'action="/domicilio/agregar"' in html
    assert 'action="/domicilio/enviar"' in html


def test_nuevo_pedido_ignora_cantidades_vacias_y_cero(client, app):
    with app.app_context():
        _crear_usuario()
    _login(client)
    respuesta = client.post(
        "/admin/pedidos/nuevo",
        data={
            "tipo": "llevar",
            "producto_id": ["1", "1", "1"],
            "cantidad": ["", "0", "2"],
            "nota": ["vacía", "cero", "válida"],
        },
    )
    assert respuesta.status_code == 302
    with app.app_context():
        pedido = Pedido.query.one()
        assert [(item.cantidad, item.nota) for item in pedido.items] == [(2, "válida")]


def test_agregar_ignora_cantidades_vacias_y_cero(client, app):
    with app.app_context():
        usuario = _crear_usuario()
        pedido = Pedido(
            tipo="llevar",
            origen="caja",
            estado=ESTADO_CONFIRMADO,
            total_cop=8000,
            creado_por=usuario.id,
            confirmado_por=usuario.id,
        )
        from app.models import PedidoItem

        pedido.items.append(
            PedidoItem(
                producto_id=1,
                nombre_snapshot="Limonada",
                precio_snapshot_cop=8000,
                cantidad=1,
            )
        )
        db.session.add(pedido)
        db.session.commit()
        pedido_id = pedido.id
    _login(client)
    respuesta = client.post(
        f"/admin/pedidos/{pedido_id}/agregar",
        data={
            "producto_id": ["1", "1", "1"],
            "cantidad": ["", "0", "2"],
            "nota": ["vacía", "cero", "válida"],
        },
    )
    assert respuesta.status_code == 302
    with app.app_context():
        pedido = db.session.get(Pedido, pedido_id)
        assert [(item.cantidad, item.nota) for item in pedido.items] == [
            (1, None),
            (2, "válida"),
        ]


def test_confirmar_por_codigo_ignora_un_pendiente_expirado(app):
    with app.app_context():
        usuario = _crear_usuario(rol="caja")
        ahora = ahora_utc()
        expirado = Pedido(
            tipo="llevar",
            origen="cliente_qr",
            codigo="1234",
            estado=ESTADO_PENDIENTE,
            total_cop=0,
            creado_en=ahora - timedelta(minutes=20),
            expira_en=ahora - timedelta(minutes=1),
        )
        vigente = Pedido(
            tipo="llevar",
            origen="cliente_qr",
            codigo="1234",
            estado=ESTADO_PENDIENTE,
            total_cop=0,
            creado_en=ahora,
            expira_en=ahora + timedelta(minutes=10),
        )
        db.session.add_all([expirado, vigente])
        db.session.commit()
        confirmar_por_codigo("1234", usuario)
        assert db.session.get(Pedido, vigente.id).estado == ESTADO_CONFIRMADO
        assert db.session.get(Pedido, expirado.id).estado == ESTADO_PENDIENTE


def test_admin_mesa_muestra_mensaje_si_el_numero_ya_existe(client, app):
    with app.app_context():
        _crear_usuario()
    _login(client)
    respuesta = client.post("/admin/gestion/mesa", data={"numero": "1"})
    assert respuesta.status_code == 302
    pagina = client.get(respuesta.headers["Location"], follow_redirects=True)
    assert "no es válido o ya existe" in pagina.get_data(as_text=True)


def test_la_app_no_arranca_con_la_clave_de_desarrollo(monkeypatch):
    monkeypatch.setattr(Config, "SECRET_KEY", "dev-cambia-esta-clave")
    with pytest.raises(RuntimeError, match="SECRET_KEY"):
        create_app()


def test_seed_no_crea_usuarios_demo_fuera_de_modo_demo(app, monkeypatch):
    monkeypatch.setenv("MODO_DEMO", "0")
    monkeypatch.delenv("ADMIN_EMAIL", raising=False)
    monkeypatch.delenv("ADMIN_PASSWORD", raising=False)
    with app.app_context():
        db.drop_all()
        db.create_all()
        cargar_demo()
        assert Usuario.query.count() == 0


def test_seed_crea_admin_configurado(monkeypatch, app):
    monkeypatch.setenv("MODO_DEMO", "0")
    monkeypatch.setenv("ADMIN_EMAIL", "dueño@restaurante.test")
    monkeypatch.setenv("ADMIN_PASSWORD", "una-clave-de-admin-segura")
    with app.app_context():
        db.drop_all()
        db.create_all()
        cargar_demo()
        admin = Usuario.query.one()
        assert admin.usuario == "dueño@restaurante.test"
        assert admin.rol == "admin"


def test_seed_crea_admin_configurado_aunque_ya_haya_usuarios(monkeypatch, app):
    monkeypatch.setenv("MODO_DEMO", "0")
    monkeypatch.delenv("ADMIN_EMAIL", raising=False)
    monkeypatch.delenv("ADMIN_PASSWORD", raising=False)
    with app.app_context():
        db.drop_all()
        db.create_all()
        cargar_demo()
        db.session.add(
            Usuario(
                usuario="caja@existente.test",
                password_hash=generate_password_hash("una-clave-segura"),
                rol="caja",
            )
        )
        db.session.commit()
        monkeypatch.setenv("ADMIN_EMAIL", "dueño@restaurante.test")
        monkeypatch.setenv("ADMIN_PASSWORD", "una-clave-de-admin-segura")
        cargar_demo()
        assert Usuario.query.filter_by(usuario="dueño@restaurante.test").one().rol == "admin"


def test_login_rechaza_siguiente_externo_y_con_doble_barra(client, app):
    with app.app_context():
        _crear_usuario()
    for siguiente in ("https://ejemplo.test", "//ejemplo.test"):
        respuesta = _login(client, siguiente=siguiente)
        assert respuesta.headers["Location"].endswith("/admin/gestion/")


def test_cancelar_no_es_transicion_generica():
    assert ESTADO_CANCELADO not in TRANSICIONES[ESTADO_CONFIRMADO]
    assert ESTADO_CANCELADO not in TRANSICIONES["en_preparacion"]


def test_busqueda_sin_filtro_no_limita_y_solo_devuelve_activos(app):
    with app.app_context():
        ahora = ahora_utc()
        db.session.add_all(
            [
                Pedido(
                    tipo="llevar",
                    origen="caja",
                    estado=ESTADO_CONFIRMADO,
                    total_cop=0,
                    creado_en=ahora + timedelta(seconds=i),
                )
                for i in range(101)
            ]
        )
        cerrado = Pedido(
            tipo="llevar",
            origen="caja",
            estado=ESTADO_ENTREGADO,
            total_cop=0,
            creado_en=ahora + timedelta(seconds=200),
        )
        db.session.add(cerrado)
        db.session.commit()
        activos = buscar_pedidos()
        assert len(activos) == 101
        assert all(pedido.estado != ESTADO_ENTREGADO for pedido in activos)
        assert buscar_pedidos(str(cerrado.id)) == [cerrado]


def test_limite_por_ip_por_defecto_es_30(monkeypatch):
    monkeypatch.delenv("MAX_PENDIENTES_POR_IP", raising=False)
    modulo = importlib.import_module("app.config")
    importlib.reload(modulo)
    assert modulo.Config.MAX_PENDIENTES_POR_IP == 30


def test_limite_por_ip_se_puede_configurar(monkeypatch):
    monkeypatch.setenv("MAX_PENDIENTES_POR_IP", "7")
    modulo = importlib.import_module("app.config")
    importlib.reload(modulo)
    assert modulo.Config.MAX_PENDIENTES_POR_IP == 7


def test_panel_tiene_un_solo_contenido_y_no_recarga_con_codigo_en_foco(client, app):
    with app.app_context():
        _crear_usuario()
    _login(client)
    html = client.get("/admin/").get_data(as_text=True)
    assert html.count('id="contenido"') == 1
    assert "document.activeElement" in html
    assert 'name !== "codigo"' in html


def test_agregar_producto_redirige_a_su_ancla(client, app):
    with app.app_context():
        usuario = _crear_usuario()
        pedido = Pedido(
            tipo="llevar",
            origen="caja",
            estado=ESTADO_CONFIRMADO,
            total_cop=8000,
            creado_por=usuario.id,
            confirmado_por=usuario.id,
        )
        from app.models import PedidoItem

        pedido.items.append(
            PedidoItem(
                producto_id=1,
                nombre_snapshot="Limonada",
                precio_snapshot_cop=8000,
                cantidad=1,
            )
        )
        db.session.add(pedido)
        db.session.commit()
        pedido_id = pedido.id
    _login(client)
    respuesta = client.post(
        f"/admin/pedidos/{pedido_id}/agregar",
        data={"producto_id": ["1"], "cantidad": ["2"], "nota": [""]},
    )
    assert respuesta.headers["Location"].endswith("#producto-1")
