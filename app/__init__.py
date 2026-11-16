"""Fábrica de la aplicación. run.py y las pruebas entran por aquí."""

from pathlib import Path

from flask import Flask

from app.config import Config
from app.dispositivo import fijar_cookie_dispositivo, preparar_dispositivo
from app.extensions import csrf, db
from app.models import ETIQUETA_ESTADO
from app.services.pedidos import expirar_pedidos_vencidos
from app.tiempo import formato_cop, formato_hora_bogota


def create_app(config_object=None) -> Flask:
    app = Flask(__name__)
    app.config.from_object(config_object or Config)
    _asegurar_carpeta_sqlite(app)

    db.init_app(app)
    csrf.init_app(app)

    from app import models  # noqa: F401  (registra las tablas en SQLAlchemy)
    from app.routes.publico import bp
    from app.routes.personal import bp as personal_bp
    from app.routes.admin import bp as admin_bp

    app.register_blueprint(bp)
    app.register_blueprint(personal_bp)
    app.register_blueprint(admin_bp)

    @app.before_request
    def preparar_cada_peticion():
        preparar_dispositivo()
        # Sin un reloj de fondo: cada visita actualiza los pendientes vencidos.
        expirar_pedidos_vencidos()

    @app.after_request
    def ajustar_respuesta(response):
        response = fijar_cookie_dispositivo(response)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "same-origin"
        if response.mimetype == "text/html":
            response.headers["Cache-Control"] = "no-store"
        return response

    @app.context_processor
    def inyectar_plantillas():
        return {
            "nombre_restaurante": app.config["RESTAURANTE_NOMBRE"],
            "etiqueta_estado": ETIQUETA_ESTADO,
            "usuario_actual": __import__("app.auth", fromlist=["usuario_actual"]).usuario_actual(),
            "modo_demo": app.config.get("MODO_DEMO", False),
        }

    @app.template_filter("cop")
    def filtro_cop(valor):
        return formato_cop(valor)

    @app.template_filter("hora_bogota")
    def filtro_hora(valor):
        return formato_hora_bogota(valor)

    @app.errorhandler(404)
    def no_encontrado(_error):
        return render_no_encontrado(), 404

    @app.errorhandler(400)
    def solicitud_invalida(_error):
        return (
            render_no_encontrado(
                "No se pudo enviar el formulario. Recarga la página e intenta otra vez."
            ),
            400,
        )

    if not app.config.get("TESTING") and app.config["SECRET_KEY"] == "dev-cambia-esta-clave":
        raise RuntimeError("SECRET_KEY de desarrollo no permitida fuera de TESTING.")

    @app.cli.command("iniciar-db")
    def iniciar_db():
        """Crea las tablas y, si están vacías, carga el menú de demostración."""
        db.create_all()
        from app.seed import cargar_demo

        cargar_demo()
        print("Base lista.")

    return app


def render_no_encontrado(mensaje: str | None = None):
    from flask import render_template

    return render_template("no_disponible.html", mensaje=mensaje)


def _asegurar_carpeta_sqlite(app: Flask) -> None:
    uri = app.config["SQLALCHEMY_DATABASE_URI"]
    if not uri.startswith("sqlite:///") or uri.endswith(":memory:"):
        return
    Path(uri.removeprefix("sqlite:///")).parent.mkdir(parents=True, exist_ok=True)
