"""Carrito guardado en la sesión del navegador.

No guarda precios. Al enviar, el servidor vuelve a leer el menú.
"""

from __future__ import annotations

from flask import current_app, session

from app.errores import ErrorPedido
from app.extensions import db
from app.models import Mesa, Producto

CLAVE = "carrito"


def guardar(carrito: dict) -> None:
    session[CLAVE] = carrito
    session.modified = True


def asegurar_contexto(tipo: str, mesa: Mesa | None) -> tuple[dict, bool]:
    """Deja el carrito alineado con la mesa o con 'para llevar'.

    Si la persona abre otro QR, se vacía el carrito anterior para no mezclar
    la mesa 2 con la mesa 5. El segundo valor dice si había productos y se perdieron.
    """
    mesa_id = mesa.id if mesa else None
    actual = session.get(CLAVE)
    if (
        isinstance(actual, dict)
        and actual.get("tipo") == tipo
        and actual.get("mesa_id") == mesa_id
        and isinstance(actual.get("lineas"), list)
    ):
        return actual, False

    habia_productos = isinstance(actual, dict) and bool(actual.get("lineas"))
    nuevo = {
        "tipo": tipo,
        "mesa_id": mesa_id,
        "mesa_numero": mesa.numero if mesa else None,
        "lineas": [],
    }
    guardar(nuevo)
    return nuevo, habia_productos


def agregar(carrito: dict, producto_id: int, cantidad: int, nota: str) -> None:
    max_cantidad = current_app.config["MAX_CANTIDAD_POR_LINEA"]
    max_lineas = current_app.config["MAX_LINEAS_POR_PEDIDO"]
    if cantidad < 1 or cantidad > max_cantidad:
        raise ErrorPedido(f"La cantidad debe estar entre 1 y {max_cantidad}.")

    producto = db.session.get(Producto, producto_id)
    if producto is None or not producto.disponible:
        raise ErrorPedido("Ese producto no está disponible.")

    nota_limpia = _limpiar_nota(nota)
    for linea in carrito["lineas"]:
        if linea["producto_id"] == producto_id and linea["nota"] == nota_limpia:
            linea["cantidad"] = min(max_cantidad, int(linea["cantidad"]) + cantidad)
            guardar(carrito)
            return

    if len(carrito["lineas"]) >= max_lineas:
        raise ErrorPedido("El pedido ya tiene demasiados productos distintos.")

    carrito["lineas"].append(
        {"producto_id": producto_id, "cantidad": cantidad, "nota": nota_limpia}
    )
    guardar(carrito)


def aplicar_accion(carrito: dict, indice: int, accion: str, nota: str | None) -> None:
    lineas = carrito["lineas"]
    if indice < 0 or indice >= len(lineas):
        raise ErrorPedido("Esa línea ya no está en el carrito.")

    max_cantidad = current_app.config["MAX_CANTIDAD_POR_LINEA"]
    if accion == "quitar":
        lineas.pop(indice)
    elif accion == "mas":
        lineas[indice]["cantidad"] = min(max_cantidad, int(lineas[indice]["cantidad"]) + 1)
        if nota is not None:
            lineas[indice]["nota"] = _limpiar_nota(nota)
    elif accion == "menos":
        lineas[indice]["cantidad"] = int(lineas[indice]["cantidad"]) - 1
        if lineas[indice]["cantidad"] < 1:
            lineas.pop(indice)
        elif nota is not None:
            lineas[indice]["nota"] = _limpiar_nota(nota)
    elif accion == "nota":
        lineas[indice]["nota"] = _limpiar_nota(nota)
    else:
        raise ErrorPedido("Acción no válida.")
    guardar(carrito)


def vaciar(tipo: str, mesa: Mesa | None) -> None:
    guardar(
        {
            "tipo": tipo,
            "mesa_id": mesa.id if mesa else None,
            "mesa_numero": mesa.numero if mesa else None,
            "lineas": [],
        }
    )


def enriquecer(carrito: dict) -> dict:
    """Arma lo que ve la plantilla, con el precio vigente del menú."""
    vista = []
    total = 0
    unidades = 0
    for indice, linea in enumerate(carrito.get("lineas", [])):
        try:
            producto_id = int(linea["producto_id"])
            cantidad = int(linea["cantidad"])
            nota = str(linea.get("nota") or "")
        except (KeyError, TypeError, ValueError):
            vista.append(_linea_rota(indice))
            continue

        producto = db.session.get(Producto, producto_id)
        if producto is None:
            vista.append(_linea_rota(indice))
            continue

        disponible = bool(producto.disponible) and cantidad > 0
        subtotal = producto.precio_cop * cantidad if disponible else 0
        if disponible:
            total += subtotal
            unidades += cantidad
        vista.append(
            {
                "indice": indice,
                "nombre": producto.nombre,
                "precio_cop": producto.precio_cop,
                "cantidad": cantidad,
                "nota": nota,
                "subtotal_cop": subtotal,
                "disponible": disponible,
            }
        )

    return {
        "lineas": vista,
        "total_cop": total,
        "unidades": unidades,
        "puede_enviar": bool(vista) and all(linea["disponible"] for linea in vista),
    }


def _linea_rota(indice: int) -> dict:
    return {
        "indice": indice,
        "nombre": "Ya no está en el menú",
        "precio_cop": 0,
        "cantidad": 0,
        "nota": "",
        "subtotal_cop": 0,
        "disponible": False,
    }


def _limpiar_nota(nota: str | None) -> str:
    return (nota or "").strip()[:200]
