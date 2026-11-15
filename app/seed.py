"""Datos para probar el menú y para la base vacía del piloto."""

from app.extensions import db
from app.models import Categoria, Mesa, Producto, Usuario
from werkzeug.security import generate_password_hash

MENU_DEMO = (
    (
        "Entradas",
        1,
        (
            ("Empanadas", "Tres empanadas de carne con ají", 7000),
            ("Patacones con hogao", "Plátano verde aplastado y hogao", 9000),
        ),
    ),
    (
        "Platos",
        2,
        (
            ("Bandeja paisa", "Frijoles, arroz, carne molida, chicharrón, huevo, aguacate y arepa", 32000),
            ("Ajiaco", "Sopa de pollo y papa, con alcaparras y crema de leche", 28000),
            ("Sancocho de gallina", "Con plátano, yuca y arroz aparte", 26000),
        ),
    ),
    (
        "Bebidas",
        3,
        (
            ("Limonada de coco", "Limonada natural con coco", 8000),
            ("Jugo de lulo", "En agua", 7000),
            ("Café", "Tinto", 3000),
        ),
    ),
    (
        "Postres",
        4,
        (
            ("Postre de natas", "Porción", 8000),
            ("Arroz con leche", "Porción", 7000),
        ),
    ),
)


def cargar_demo() -> None:
    """Carga el menú de ejemplo solo si la base todavía no tiene categorías."""
    if Categoria.query.first() is not None:
        if Usuario.query.first() is None:
            _crear_usuarios_demo()
            db.session.commit()
        return
    for nombre, orden, productos in MENU_DEMO:
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
    _crear_usuarios_demo()
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
