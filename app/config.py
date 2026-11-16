"""Valores que cambian entre el computador de desarrollo, las pruebas y el piloto."""

import os
from pathlib import Path

from sqlalchemy.pool import StaticPool

BASE_DIR = Path(__file__).resolve().parent.parent


def _uri_sqlite(ruta: Path) -> str:
    return "sqlite:///" + ruta.resolve().as_posix()


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-cambia-esta-clave")
    SQLALCHEMY_DATABASE_URI = _uri_sqlite(BASE_DIR / "instance" / "pedidos.db")
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    RESTAURANTE_NOMBRE = os.environ.get("RESTAURANTE_NOMBRE", "Sabores del Patio")
    # En el piloto local conviene ver las mesas sin imprimir QR. En público, apágalo.
    MOSTRAR_INDICE_DEMO = os.environ.get("MOSTRAR_INDICE_DEMO", "1") == "1"
    MODO_DEMO = os.environ.get("MODO_DEMO", "1") == "1"
    MAX_INTENTOS_LOGIN = 5
    VENTANA_LOGIN_SEGUNDOS = 60
    WHATSAPP_NUMERO = os.environ.get("WHATSAPP_NUMERO", "")
    PUBLIC_BASE_URL = os.environ.get("PUBLIC_BASE_URL", "")

    PEDIDO_EXPIRA_MINUTOS = 15
    PEDIDO_DOMICILIO_EXPIRA_MINUTOS = 30
    # El límite por IP puede ajustarse cuando varios clientes comparten una red.
    MAX_PENDIENTES_POR_DISPOSITIVO = 3
    MAX_PENDIENTES_POR_IP = int(os.environ.get("MAX_PENDIENTES_POR_IP", "30"))
    MAX_CANTIDAD_POR_LINEA = 50
    MAX_LINEAS_POR_PEDIDO = 40

    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = os.environ.get("SESSION_COOKIE_SECURE") == "1"


class TestConfig(Config):
    TESTING = True
    SECRET_KEY = "test-secret-key"
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    SQLALCHEMY_ENGINE_OPTIONS = {
        "connect_args": {"check_same_thread": False},
        "poolclass": StaticPool,
    }
    # Las pruebas llaman las reglas de negocio. El token CSRF se prueba
    # comprobando que el HTML lo incluye; aquí no bloquea el cliente de prueba.
    WTF_CSRF_ENABLED = False
    SESSION_COOKIE_SECURE = False
    MOSTRAR_INDICE_DEMO = True
