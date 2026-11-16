"""Operaciones del panel que deben ejecutarse con un usuario autenticado."""

from __future__ import annotations

from sqlalchemy import String, cast, or_

from app.errores import ErrorPedido
from app.extensions import db
from app.models import (
    ESTADO_CANCELADO,
    ESTADO_CONFIRMADO,
    ESTADO_ENTREGADO,
    ESTADO_EN_PREPARACION,
    ESTADO_LISTO,
    ESTADO_PENDIENTE,
    ESTADOS_EN_COCINA,
    ORIGEN_CAJA,
    ORIGEN_MESERO,
    Pedido,
    PedidoCambio,
    PedidoItem,
    Producto,
    TIPO_DOMICILIO,
    TIPO_LLEVAR,
    TIPO_MESA,
    Usuario,
)
from app.services.pedidos import puede_confirmar
from app.tiempo import ahora_utc

TRANSICIONES = {
    ESTADO_CONFIRMADO: {ESTADO_EN_PREPARACION},
    ESTADO_EN_PREPARACION: {ESTADO_LISTO},
    ESTADO_LISTO: {ESTADO_ENTREGADO},
}


def buscar_pedidos(consulta: str = "") -> list[Pedido]:
    query = Pedido.query.order_by(Pedido.creado_en.desc())
    consulta = consulta.strip()
    if consulta:
        query = query.filter(
            or_(
                Pedido.codigo == consulta,
                cast(Pedido.id, String) == consulta,
            )
        )
    else:
        query = query.filter(
            Pedido.estado.in_((ESTADO_PENDIENTE, *ESTADOS_EN_COCINA))
        )
    return query.all()


def confirmar_por_codigo(codigo: str, usuario: Usuario) -> Pedido:
    ahora = ahora_utc()
    pedido = Pedido.query.filter(
        Pedido.codigo == codigo.strip(),
        Pedido.estado == ESTADO_PENDIENTE,
        Pedido.expira_en > ahora,
    ).first()
    if pedido is None or not puede_confirmar(pedido):
        raise ErrorPedido("El pedido no existe, venció o ya fue procesado.")
    pedido.estado = ESTADO_CONFIRMADO
    pedido.confirmado_en = ahora_utc()
    pedido.confirmado_por = usuario.id
    _registrar(pedido, usuario, "confirmar", "Pedido confirmado en caja")
    db.session.commit()
    return pedido


def cambiar_estado(pedido: Pedido, estado: str, usuario: Usuario) -> None:
    if estado not in TRANSICIONES.get(pedido.estado, set()):
        raise ErrorPedido("Ese cambio de estado no está permitido.")
    pedido.estado = estado
    _registrar(pedido, usuario, "cambiar_estado", f"Nuevo estado: {estado}")
    db.session.commit()


def cancelar_pedido(pedido: Pedido, usuario: Usuario, motivo: str) -> None:
    if not motivo.strip():
        raise ErrorPedido("El motivo es obligatorio.")
    if pedido.estado in {ESTADO_ENTREGADO, ESTADO_CANCELADO}:
        raise ErrorPedido("Este pedido ya no se puede cancelar.")
    pedido.estado = ESTADO_CANCELADO
    _registrar(pedido, usuario, "cancelar", "Pedido cancelado", motivo.strip())
    db.session.commit()


def crear_pedido_personal(
    *,
    tipo: str,
    mesa_id: int | None,
    lineas: list[dict],
    usuario: Usuario,
    nombre_cliente: str = "",
    telefono: str = "",
    direccion: str = "",
) -> Pedido:
    if tipo not in {TIPO_MESA, TIPO_LLEVAR, TIPO_DOMICILIO}:
        raise ErrorPedido("Tipo de pedido no válido.")
    congeladas = _congelar_lineas(lineas)
    pedido = Pedido(
        tipo=tipo,
        origen=ORIGEN_MESERO if usuario.rol == "mesero" else ORIGEN_CAJA,
        mesa_id=mesa_id if tipo == TIPO_MESA else None,
        estado=ESTADO_CONFIRMADO,
        nombre_cliente=nombre_cliente.strip()[:120] or None,
        telefono=telefono.strip()[:20] or None,
        direccion=direccion.strip()[:500] or None,
        total_cop=sum(x["precio_snapshot_cop"] * x["cantidad"] for x in congeladas),
        creado_por=usuario.id,
        confirmado_por=usuario.id,
        creado_en=ahora_utc(),
        confirmado_en=ahora_utc(),
    )
    for linea in congeladas:
        pedido.items.append(PedidoItem(**linea, ronda=1))
    db.session.add(pedido)
    db.session.flush()
    _registrar(pedido, usuario, "crear", "Pedido tomado por personal")
    db.session.commit()
    return pedido


def agregar_items(pedido: Pedido, lineas: list[dict], usuario: Usuario) -> None:
    if pedido.estado not in {ESTADO_CONFIRMADO, ESTADO_EN_PREPARACION, ESTADO_LISTO}:
        raise ErrorPedido("Solo se pueden agregar ítems a un pedido activo.")
    congeladas = _congelar_lineas(lineas)
    ronda = max((item.ronda for item in pedido.items), default=1) + 1
    for linea in congeladas:
        pedido.items.append(PedidoItem(**linea, ronda=ronda, agregado_por=usuario.id))
    pedido.total_cop = sum(item.precio_snapshot_cop * item.cantidad for item in pedido.items)
    _registrar(pedido, usuario, "agregar_items", f"Ronda {ronda}: {len(congeladas)} ítems")
    db.session.commit()


def quitar_item(pedido: Pedido, item: PedidoItem, usuario: Usuario, motivo: str) -> None:
    if usuario.rol != "admin":
        raise ErrorPedido("Solo un administrador puede quitar ítems.")
    if not motivo.strip():
        raise ErrorPedido("El motivo es obligatorio.")
    if item not in pedido.items:
        raise ErrorPedido("El ítem no pertenece a este pedido.")
    pedido.items.remove(item)
    pedido.total_cop = sum(x.precio_snapshot_cop * x.cantidad for x in pedido.items)
    _registrar(pedido, usuario, "quitar_item", f"Ítem {item.nombre_snapshot}", motivo.strip())
    db.session.commit()


def _congelar_lineas(lineas: list[dict]) -> list[dict]:
    if not lineas:
        raise ErrorPedido("Agrega al menos un producto.")
    resultado = []
    for cruda in lineas:
        try:
            producto = db.session.get(Producto, int(cruda["producto_id"]))
            cantidad = int(cruda["cantidad"])
        except (KeyError, TypeError, ValueError):
            raise ErrorPedido("Hay un producto inválido.") from None
        if producto is None or not producto.disponible:
            raise ErrorPedido("Todos los productos deben estar disponibles.")
        if cantidad < 1 or cantidad > 50:
            raise ErrorPedido("La cantidad debe estar entre 1 y 50.")
        resultado.append(
            {
                "producto_id": producto.id,
                "nombre_snapshot": producto.nombre,
                "precio_snapshot_cop": producto.precio_cop,
                "cantidad": cantidad,
                "nota": str(cruda.get("nota") or "").strip()[:200] or None,
            }
        )
    return resultado


def _registrar(pedido, usuario, accion: str, detalle: str, motivo: str | None = None):
    pedido.cambios.append(
        PedidoCambio(
            usuario_id=usuario.id,
            accion=accion,
            detalle=detalle,
            motivo=motivo,
        )
    )
