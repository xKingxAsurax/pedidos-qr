"""Creación del pedido del cliente, código de 4 dígitos y expiración.

Un pedido de QR nace en pendiente_confirmacion. No entra a cocina hasta que
caja lo confirme (eso es la Fase 2). Si nadie lo confirma, pasa a expirado.
"""

from __future__ import annotations

import secrets
from datetime import timedelta

from flask import current_app
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.errores import ErrorPedido
from app.extensions import db
from app.models import (
    ESTADOS_EN_COCINA,
    ESTADO_EXPIRADO,
    ESTADO_PENDIENTE,
    ORIGEN_CLIENTE_QR,
    ORIGEN_DOMICILIO_WEB,
    TIPO_LLEVAR,
    TIPO_MESA,
    Mesa,
    Pedido,
    PedidoItem,
    Producto,
)
from app.tiempo import ahora_utc, inicio_del_dia_bogota, a_bogota


def expirar_pedidos_vencidos(ahora=None) -> int:
    """Pasa a expirado los pendientes cuyo plazo ya se cumplió.

    No toca un pedido confirmado: ese ya es responsabilidad de cocina.
    """
    ahora = ahora or ahora_utc()
    vencidos = Pedido.query.filter(
        Pedido.estado == ESTADO_PENDIENTE,
        Pedido.expira_en.is_not(None),
        Pedido.expira_en <= ahora,
    ).all()
    for pedido in vencidos:
        pedido.estado = ESTADO_EXPIRADO
    if vencidos:
        db.session.commit()
    return len(vencidos)


def visible_en_cocina(pedido: Pedido) -> bool:
    return pedido.estado in ESTADOS_EN_COCINA


def puede_confirmar(pedido: Pedido, ahora=None) -> bool:
    """Regla que usará caja en la Fase 2: solo lo de hoy y todavía vigente.

    Se comprueba la hora, no únicamente el estado. Así un pendiente cuyo
    reloj ya venció no se confirma aunque el barrido todavía no haya corrido.
    """
    ahora = ahora or ahora_utc()
    if pedido.estado != ESTADO_PENDIENTE:
        return False
    if pedido.expira_en is None or pedido.expira_en <= ahora:
        return False
    if a_bogota(pedido.creado_en) < inicio_del_dia_bogota(ahora):
        return False
    return True


def crear_pedido_cliente_qr(
    *,
    tipo: str,
    mesa: Mesa | None,
    lineas_entrada: list[dict],
    ip: str,
    dispositivo_id: str,
    nombre_cliente: str = "",
    telefono: str = "",
    direccion: str = "",
) -> Pedido:
    if tipo == TIPO_MESA:
        if mesa is None or not mesa.activa:
            raise ErrorPedido("La mesa no está disponible.")
    elif tipo == TIPO_LLEVAR or tipo == "domicilio":
        if mesa is not None:
            raise ErrorPedido("Un pedido para llevar no lleva número de mesa.")
    else:
        raise ErrorPedido("Este tipo de pedido no está disponible.")
    if tipo == "domicilio" and (
        not nombre_cliente.strip() or not telefono.strip() or not direccion.strip()
    ):
        raise ErrorPedido("Para domicilio necesitamos nombre, teléfono y dirección.")

    ahora = ahora_utc()
    expirar_pedidos_vencidos(ahora)
    lineas = _congelar_lineas(lineas_entrada)
    minutos = int(
        current_app.config[
            "PEDIDO_DOMICILIO_EXPIRA_MINUTOS"
            if tipo == "domicilio"
            else "PEDIDO_EXPIRA_MINUTOS"
        ]
    )
    for _ in range(5):
        _bloquear_generacion_codigo()
        _exigir_cupo(ip, dispositivo_id, ahora)
        pedido = Pedido(
            tipo=tipo,
            origen=ORIGEN_DOMICILIO_WEB if tipo == "domicilio" else ORIGEN_CLIENTE_QR,
            mesa_id=mesa.id if mesa else None,
            codigo=generar_codigo_unico(ahora),
            estado=ESTADO_PENDIENTE,
            total_cop=sum(linea["precio_cop"] * linea["cantidad"] for linea in lineas),
            creado_en=ahora,
            expira_en=ahora + timedelta(minutes=minutos),
            ip_cliente=ip,
            dispositivo_id=dispositivo_id,
            nombre_cliente=nombre_cliente.strip()[:120] or None,
            telefono=telefono.strip()[:20] or None,
            direccion=direccion.strip()[:500] or None,
        )
        for linea in lineas:
            pedido.items.append(
                PedidoItem(
                    producto_id=linea["producto_id"],
                    nombre_snapshot=linea["nombre"],
                    precio_snapshot_cop=linea["precio_cop"],
                    cantidad=linea["cantidad"],
                    nota=linea["nota"],
                    ronda=1,
                    agregado_en=ahora,
                )
            )
        db.session.add(pedido)
        try:
            db.session.commit()
            return pedido
        except IntegrityError:
            # Ante un conflicto inesperado, se reintenta con otra reserva.
            db.session.rollback()
    raise ErrorPedido("No se pudo reservar un código único. Intenta otra vez.")


def _bloquear_generacion_codigo() -> None:
    """Serializa la reserva para mantener únicos los códigos pendientes vigentes."""
    dialecto = db.session.get_bind().dialect.name
    if dialecto == "sqlite":
        # SQLite adquiere el bloqueo de escritura antes de consultar los códigos.
        db.session.connection().exec_driver_sql("BEGIN IMMEDIATE")
    elif dialecto == "postgresql":
        # El bloqueo advisory se comparte entre procesos y servicios con la misma BD.
        db.session.execute(text("SELECT pg_advisory_xact_lock(:clave)"), {"clave": 74201984})
    else:
        raise RuntimeError(f"Motor de base de datos no soportado: {dialecto}")


def generar_codigo_unico(ahora=None) -> str:
    """Código libre de 4 dígitos entre pendientes que aún no vencen.

    0042 y 42 son distintos: el código se guarda como texto para conservar
    los ceros. El bloqueo transaccional serializa la consulta y la reserva.
    Pedidos expirados o procesados pueden reutilizar su código.
    """
    ahora = ahora or ahora_utc()
    for _ in range(30):
        codigo = _codigo_aleatorio()
        if not _codigo_reservado(codigo, ahora):
            return codigo
    raise ErrorPedido("No se pudo generar un código único. Intenta otra vez.")


def _codigo_aleatorio() -> str:
    return f"{secrets.randbelow(10000):04d}"


def _codigo_reservado(codigo: str, ahora) -> bool:
    return (
        db.session.query(Pedido.id)
        .filter(
            Pedido.codigo == codigo,
            Pedido.estado == ESTADO_PENDIENTE,
            Pedido.expira_en > ahora,
        )
        .first()
        is not None
    )


def _exigir_cupo(ip: str, dispositivo_id: str, ahora) -> None:
    max_dispositivo = int(current_app.config["MAX_PENDIENTES_POR_DISPOSITIVO"])
    max_ip = int(current_app.config["MAX_PENDIENTES_POR_IP"])
    minutos = int(current_app.config["PEDIDO_EXPIRA_MINUTOS"])
    if _contar_pendientes(ahora, dispositivo_id=dispositivo_id) >= max_dispositivo:
        raise ErrorPedido(
            f"Ya tienes {max_dispositivo} pedidos sin confirmar. "
            f"Confírmalos en caja o espera a que venzan ({minutos} minutos)."
        )
    if _contar_pendientes(ahora, ip=ip) >= max_ip:
        raise ErrorPedido(
            f"Desde esta red ya hay {max_ip} pedidos sin confirmar. "
            "Espera a que venzan o confírmalos en caja."
        )


def _contar_pendientes(ahora, *, ip: str | None = None, dispositivo_id: str | None = None) -> int:
    consulta = Pedido.query.filter(
        Pedido.estado == ESTADO_PENDIENTE,
        Pedido.expira_en > ahora,
    )
    if dispositivo_id is not None:
        consulta = consulta.filter(Pedido.dispositivo_id == dispositivo_id)
    if ip is not None:
        consulta = consulta.filter(Pedido.ip_cliente == ip)
    return consulta.count()


def _congelar_lineas(lineas_entrada: list[dict]) -> list[dict]:
    """Copia nombre y precio desde la base. Ignora cualquier precio del navegador."""
    if not lineas_entrada:
        raise ErrorPedido("Agrega al menos un producto.")

    max_lineas = int(current_app.config["MAX_LINEAS_POR_PEDIDO"])
    max_cantidad = int(current_app.config["MAX_CANTIDAD_POR_LINEA"])
    if len(lineas_entrada) > max_lineas:
        raise ErrorPedido("El pedido ya tiene demasiados productos distintos.")

    congeladas = []
    for cruda in lineas_entrada:
        try:
            producto_id = int(cruda["producto_id"])
            cantidad = int(cruda["cantidad"])
        except (KeyError, TypeError, ValueError):
            raise ErrorPedido(
                "Hay un dato del carrito que no se puede leer. "
                "Quita los productos y vuelve a agregarlos."
            ) from None
        if cantidad < 1 or cantidad > max_cantidad:
            raise ErrorPedido(f"La cantidad debe estar entre 1 y {max_cantidad}.")

        producto = db.session.get(Producto, producto_id)
        if producto is None or not producto.disponible:
            raise ErrorPedido("Un producto del carrito ya no está disponible.")

        nota = str(cruda.get("nota") or "").strip()[:200]
        congeladas.append(
            {
                "producto_id": producto.id,
                "nombre": producto.nombre,
                "precio_cop": int(producto.precio_cop),
                "cantidad": cantidad,
                "nota": nota or None,
            }
        )
    return congeladas
