"""Errores de negocio que la pantalla puede mostrar tal cual."""


class ErrorPedido(Exception):
    def __init__(self, mensaje: str):
        self.mensaje = mensaje
        super().__init__(mensaje)
