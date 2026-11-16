"""Datos para probar el menú y para la base vacía del piloto."""

import os

from app.extensions import db
from app.models import Categoria, Mesa, PedidoItem, Producto, Usuario
from werkzeug.security import generate_password_hash

MENU_VILLA_DOG = (
    (
        "Perros calientes",
        1,
        (
            ("Perro Sencillo", "", 3500),
            ("Perro Gratinado", "", 4500),
            (
                "Perro Especial (opción 1 · confirmar precio)",
                'El menú recibido indica $5.500 y también $7.000 para "Perro Especial". Confirmar con el dueño o gerente.',
                5500,
            ),
            (
                "Perro Sencillo Doble Salchicha",
                'También aparece como "Perro Doble Salchicha". Confirmar si ambos nombres son el mismo producto.',
                5000,
            ),
            (
                "Perro Gratinado Doble Salchicha",
                'También aparece como "Perro Doble Salchicha Gratinado".',
                6000,
            ),
            ("Perro Especial Doble Salchicha", "", 7000),
            (
                "Perro Especial (opción 2 · confirmar precio)",
                'El menú recibido indica $7.000 y también $5.500 para "Perro Especial". Confirmar con el dueño o gerente.',
                7000,
            ),
        ),
    ),
    (
        "Hamburguesas",
        2,
        (
            ("Hamburguesa Sencilla", "", 5000),
            ("Hamburguesa Gratinada", "", 6000),
            ("Hamburguesa Doble", "", 7000),
            ("Hamburguesa Especial", "", 7000),
            ("Hamburguesa Doble Gratinada", "", 8000),
            ("Hamburguesa Especial Doble Carne", "", 9000),
        ),
    ),
    (
        "Gaseosas",
        3,
        (
            ("Coca Cola · vidrio 250 ml", "", 2500),
            ("Colombiana · vidrio 250 ml", "", 2500),
            ("Manzana · vidrio 250 ml", "", 2500),
            ("Uva · vidrio 250 ml", "", 2500),
            ("Naranjada · vidrio 250 ml", "", 2500),
            ("Coca Cola · 400 ml", "", 4000),
            ("Coca Cola Zero · 400 ml", "", 4000),
            ("Manzana Postobón · 400 ml", "", 4000),
            ("Kola Román · 400 ml", "", 4000),
            ("Colombiana · 400 ml", "", 4000),
            ("Coca Cola · 1.5 L", "", 8000),
            ("Kola Román · 1.5 L", "", 8000),
            ("Colombiana · 1.5 L", "", 8000),
            ("Manzana Postobón · 1.5 L", "", 8000),
            ("Coca Cola · 2.5 L", "", 10000),
            ("Manzana Postobón · 2.5 L", "", 10000),
            ("Colombiana · 2.5 L", "", 10000),
        ),
    ),
    (
        "Jugos",
        4,
        (
            ("Hit Mango · 400 ml", "", 4000),
            ("Hit Tropical · 400 ml", "", 4000),
            ("Hit Mora · 400 ml", "", 4000),
            ("Hit Naranja Piña · 400 ml", "", 4000),
            ("Agua · 300 ml", "", 1000),
        ),
    ),
)

# Categorías del menú de muestra que se cargó en la primera versión del piloto.
MENU_ANTERIOR = ("Entradas", "Platos", "Bebidas", "Postres")


def cargar_demo(modo_demo: bool | None = None) -> None:
    """Carga Villa Dog en una base vacía y migra el menú inicial del piloto una vez."""
    if modo_demo is None:
        modo_demo = os.environ.get("MODO_DEMO", "0") == "1"
    if Categoria.query.first() is not None:
        _migrar_menu_inicial()
        if Usuario.query.first() is None:
            if modo_demo:
                _crear_usuarios_demo()
        _crear_admin_configurado()
        if db.session.new:
            db.session.commit()
        return
    for nombre, orden, productos in MENU_VILLA_DOG:
        categoria = Categoria(nombre=nombre, orden=orden)
        db.session.add(categoria)
        db.session.flush()
        for nombre_producto, descripcion, precio in productos:
            db.session.add(
                Producto(
                    categoria_id=categoria.id,
                    nombre=nombre_producto,
                    descripcion=descripcion,
                    precio_cop=precio,
                    disponible=True,
                )
            )
    for numero in range(1, 9):
        db.session.add(Mesa(numero=numero, activa=True))
    if modo_demo:
        _crear_usuarios_demo()
    _crear_admin_configurado()
    db.session.commit()


def _migrar_menu_inicial() -> None:
    """Sustituye el menú de muestra conocido sin borrar productos ligados a pedidos."""
    categorias = Categoria.query.order_by(Categoria.orden, Categoria.id).all()
    if tuple(categoria.nombre for categoria in categorias) != MENU_ANTERIOR:
        return
    # La disponibilidad evita repetir la migración si alguien reutiliza los nombres
    # de las categorías después de que el menú antiguo ya se haya archivado.
    menu_antiguo_activo = any(
        producto.nombre == "Bandeja paisa" and producto.disponible
        for categoria in categorias
        for producto in categoria.productos
    )
    if not menu_antiguo_activo:
        return

    for categoria, (nombre, orden, productos) in zip(categorias, MENU_VILLA_DOG):
        categoria.nombre = nombre
        categoria.orden = orden
        for producto in list(categoria.productos):
            if PedidoItem.query.filter_by(producto_id=producto.id).first() is None:
                db.session.delete(producto)
            else:
                # Conserva las referencias y snapshots de pedidos anteriores.
                producto.disponible = False
        for nombre_producto, descripcion, precio in productos:
            db.session.add(
                Producto(
                    categoria_id=categoria.id,
                    nombre=nombre_producto,
                    descripcion=descripcion,
                    precio_cop=precio,
                    disponible=True,
                )
            )
    db.session.commit()


def _crear_usuarios_demo() -> None:
    usuarios = (
        ("admin@demo.local", "Demo-Admin-2026!", "admin"),
        ("caja@demo.local", "Demo-Caja-2026!", "caja"),
        ("mesero@demo.local", "Demo-Mesero-2026!", "mesero"),
    )
    for correo, password, rol in usuarios:
        db.session.add(
            Usuario(
                usuario=correo,
                password_hash=generate_password_hash(password),
                rol=rol,
            )
        )


def _crear_admin_configurado() -> None:
    correo = os.environ.get("ADMIN_EMAIL", "").strip().lower()
    password = os.environ.get("ADMIN_PASSWORD", "")
    if not correo or not password or Usuario.query.filter_by(usuario=correo).first() is not None:
        return
    db.session.add(
        Usuario(
            usuario=correo,
            password_hash=generate_password_hash(password),
            rol="admin",
        )
    )


def sembrar_prueba() -> None:
    """Menú mínimo y predecible para las pruebas automáticas."""
    bebidas = Categoria(nombre="Bebidas", orden=1)
    db.session.add(bebidas)
    db.session.flush()
    db.session.add(
        Producto(
            categoria_id=bebidas.id,
            nombre="Limonada",
            descripcion="Natural",
            precio_cop=8000,
            disponible=True,
        )
    )
    db.session.add(
        Producto(
            categoria_id=bebidas.id,
            nombre="Agua",
            descripcion="Sin gas",
            precio_cop=3000,
            disponible=False,
        )
    )
    db.session.add(Mesa(numero=1, activa=True))
    db.session.add(Mesa(numero=9, activa=False))
    db.session.commit()
