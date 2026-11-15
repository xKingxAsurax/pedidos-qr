"""Tablas del restaurante.

La Fase 1 usa mesas, categorías, productos, pedidos e ítems.
Incluye usuarios y auditoría para que el panel operativo pueda proteger
acciones sensibles.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.extensions import db
from app.tiempo import ahora_utc

ESTADO_PENDIENTE = "pendiente_confirmacion"
ESTADO_CONFIRMADO = "confirmado"
ESTADO_EN_PREPARACION = "en_preparacion"
ESTADO_LISTO = "listo"
ESTADO_ENTREGADO = "entregado"
ESTADO_CANCELADO = "cancelado"
ESTADO_EXPIRADO = "expirado"

ESTADOS_PEDIDO = (
    ESTADO_PENDIENTE,
    ESTADO_CONFIRMADO,
    ESTADO_EN_PREPARACION,
    ESTADO_LISTO,
    ESTADO_ENTREGADO,
    ESTADO_CANCELADO,
    ESTADO_EXPIRADO,
)

# Lo que cocina debe ver. Pendiente, expirado y cancelado no entran.
ESTADOS_EN_COCINA = (ESTADO_CONFIRMADO, ESTADO_EN_PREPARACION, ESTADO_LISTO)

ETIQUETA_ESTADO = {
    ESTADO_PENDIENTE: "Pendiente de confirmación",
    ESTADO_CONFIRMADO: "Confirmado",
    ESTADO_EN_PREPARACION: "En preparación",
    ESTADO_LISTO: "Listo",
    ESTADO_ENTREGADO: "Entregado",
    ESTADO_CANCELADO: "Cancelado",
    ESTADO_EXPIRADO: "Expirado",
}

ORIGEN_CLIENTE_QR = "cliente_qr"
ORIGEN_DOMICILIO_WEB = "domicilio_web"
TIPO_MESA = "mesa"
TIPO_LLEVAR = "llevar"
TIPO_DOMICILIO = "domicilio"
ORIGEN_CAJA = "caja"
ORIGEN_MESERO = "mesero"
ROLES_PERSONAL = ("admin", "caja", "mesero")


class Usuario(db.Model):
    __tablename__ = "usuarios"

    id: Mapped[int] = mapped_column(primary_key=True)
    usuario: Mapped[str] = mapped_column(String(80), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    rol: Mapped[str] = mapped_column(String(20), nullable=False)


class Mesa(db.Model):
    __tablename__ = "mesas"

    id: Mapped[int] = mapped_column(primary_key=True)
    numero: Mapped[int] = mapped_column(Integer, unique=True, nullable=False)
    activa: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    pedidos: Mapped[list[Pedido]] = relationship(back_populates="mesa")


class Categoria(db.Model):
    __tablename__ = "categorias"

    id: Mapped[int] = mapped_column(primary_key=True)
    nombre: Mapped[str] = mapped_column(String(80), nullable=False)
    orden: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    productos: Mapped[list[Producto]] = relationship(
        back_populates="categoria",
        order_by="Producto.nombre",
    )


class Producto(db.Model):
    __tablename__ = "productos"

    id: Mapped[int] = mapped_column(primary_key=True)
    categoria_id: Mapped[int] = mapped_column(ForeignKey("categorias.id"), nullable=False)
    nombre: Mapped[str] = mapped_column(String(120), nullable=False)
    descripcion: Mapped[str] = mapped_column(Text, default="", nullable=False)
    precio_cop: Mapped[int] = mapped_column(Integer, nullable=False)
    disponible: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    imagen_url: Mapped[str | None] = mapped_column(String(300), nullable=True)

    categoria: Mapped[Categoria] = relationship(back_populates="productos")


class Pedido(db.Model):
    __tablename__ = "pedidos"

    id: Mapped[int] = mapped_column(primary_key=True)
    tipo: Mapped[str] = mapped_column(String(16), nullable=False)
    origen: Mapped[str] = mapped_column(String(20), nullable=False)
    mesa_id: Mapped[int | None] = mapped_column(ForeignKey("mesas.id"), nullable=True)
    codigo: Mapped[str | None] = mapped_column(String(4), nullable=True, index=True)
    estado: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    nombre_cliente: Mapped[str | None] = mapped_column(String(120), nullable=True)
    telefono: Mapped[str | None] = mapped_column(String(20), nullable=True)
    direccion: Mapped[str | None] = mapped_column(Text, nullable=True)
    metodo_pago: Mapped[str | None] = mapped_column(String(20), nullable=True)
    costo_domicilio_cop: Mapped[int | None] = mapped_column(Integer, nullable=True)
    total_cop: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    creado_por: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"), nullable=True)
    creado_en: Mapped[datetime] = mapped_column(DateTime, default=ahora_utc, nullable=False)
    expira_en: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    confirmado_en: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    confirmado_por: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"), nullable=True)
    # No están en el modelo inicial. Sirven para el tope de 3 pedidos pendientes.
    ip_cliente: Mapped[str | None] = mapped_column(String(45), nullable=True)
    dispositivo_id: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)

    mesa: Mapped[Mesa | None] = relationship(back_populates="pedidos")
    items: Mapped[list[PedidoItem]] = relationship(
        back_populates="pedido",
        cascade="all, delete-orphan",
        order_by="PedidoItem.id",
    )
    cambios: Mapped[list[PedidoCambio]] = relationship(back_populates="pedido")
    creador: Mapped[Usuario | None] = relationship(foreign_keys=[creado_por])
    confirmador: Mapped[Usuario | None] = relationship(foreign_keys=[confirmado_por])


class PedidoItem(db.Model):
    __tablename__ = "pedido_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    pedido_id: Mapped[int] = mapped_column(ForeignKey("pedidos.id"), nullable=False, index=True)
    producto_id: Mapped[int] = mapped_column(ForeignKey("productos.id"), nullable=False)
    nombre_snapshot: Mapped[str] = mapped_column(String(120), nullable=False)
    precio_snapshot_cop: Mapped[int] = mapped_column(Integer, nullable=False)
    cantidad: Mapped[int] = mapped_column(Integer, nullable=False)
    nota: Mapped[str | None] = mapped_column(String(200), nullable=True)
    ronda: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    agregado_por: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"), nullable=True)
    agregado_en: Mapped[datetime] = mapped_column(DateTime, default=ahora_utc, nullable=False)

    pedido: Mapped[Pedido] = relationship(back_populates="items")
    producto: Mapped[Producto] = relationship()


class PedidoCambio(db.Model):
    __tablename__ = "pedido_cambios"

    id: Mapped[int] = mapped_column(primary_key=True)
    pedido_id: Mapped[int] = mapped_column(ForeignKey("pedidos.id"), nullable=False, index=True)
    usuario_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"), nullable=False)
    accion: Mapped[str] = mapped_column(String(50), nullable=False)
    detalle: Mapped[str] = mapped_column(Text, default="", nullable=False)
    motivo: Mapped[str | None] = mapped_column(Text, nullable=True)
    creado_en: Mapped[datetime] = mapped_column(DateTime, default=ahora_utc, nullable=False)

    pedido: Mapped[Pedido] = relationship(back_populates="cambios")
    usuario: Mapped[Usuario] = relationship()
