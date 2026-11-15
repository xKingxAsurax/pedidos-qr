from werkzeug.security import generate_password_hash

from app.extensions import db
from app.models import ESTADO_CONFIRMADO, Pedido, Usuario


def _crear_usuario(rol="caja", correo="caja@test.local"):
    usuario = Usuario(
        usuario=correo,
        password_hash=generate_password_hash("una-clave-segura"),
        rol=rol,
    )
    db.session.add(usuario)
    db.session.commit()
    return usuario


def test_login_protege_panel_y_confirma_pedido(client, app):
    with app.app_context():
        _crear_usuario()

    assert client.get("/admin/").status_code == 302
    login = client.post(
        "/admin/login",
        data={"correo": "caja@test.local", "password": "una-clave-segura"},
    )
    assert login.status_code == 302
    assert client.get("/admin/").status_code == 200


def test_personal_crea_pedido_confirmado(client, app):
    with app.app_context():
        _crear_usuario()
        producto_id = 1

    client.post(
        "/admin/login",
        data={"correo": "caja@test.local", "password": "una-clave-segura"},
    )
    respuesta = client.post(
        "/admin/pedidos/nuevo",
        data={
            "tipo": "llevar",
            "producto_id": [producto_id],
            "cantidad": ["2"],
            "nota": ["sin hielo"],
        },
    )
    assert respuesta.status_code == 302
    with app.app_context():
        pedido = Pedido.query.one()
        assert pedido.estado == ESTADO_CONFIRMADO
        assert pedido.total_cop == 16000
        assert pedido.creado_por is not None


def test_domicilio_guarda_datos_y_expira_en_30_minutos(client, app):
    with app.app_context():
        producto_id = 1

    client.post(
        "/domicilio/agregar",
        data={"producto_id": producto_id, "cantidad": 1},
    )
    respuesta = client.post(
        "/domicilio/enviar",
        data={
            "nombre_cliente": "Ana",
            "telefono": "3001234567",
            "direccion": "Calle 1 # 2-3",
        },
    )
    assert respuesta.status_code == 302
    with app.app_context():
        pedido = Pedido.query.one()
        assert pedido.tipo == "domicilio"
        assert pedido.nombre_cliente == "Ana"
        assert (pedido.expira_en - pedido.creado_en).total_seconds() == 1800


def test_admin_puede_generar_png_qr_de_mesa(client, app):
    with app.app_context():
        _crear_usuario("admin", "admin@test.local")

    client.post(
        "/admin/login",
        data={"correo": "admin@test.local", "password": "una-clave-segura"},
    )
    respuesta = client.get("/admin/gestion/mesa/1/qr.png")
    assert respuesta.status_code == 200
    assert respuesta.mimetype == "image/png"
    assert respuesta.data.startswith(b"\x89PNG")
