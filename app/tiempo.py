"""Reloj del sistema en UTC y presentación en hora de Colombia."""

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

ZONA_BOGOTA = ZoneInfo("America/Bogota")


def ahora_utc() -> datetime:
    """Hora actual sin zona horaria, interpretada siempre como UTC.

    SQLite no guarda la zona. Si mezcláramos horas 'naive' de Windows con UTC,
    la expiración de 15 minutos se correría 5 horas.
    """
    return datetime.now(timezone.utc).replace(tzinfo=None)


def a_bogota(momento: datetime) -> datetime:
    if momento.tzinfo is None:
        momento = momento.replace(tzinfo=timezone.utc)
    return momento.astimezone(ZONA_BOGOTA)


def inicio_del_dia_bogota(momento_utc: datetime) -> datetime:
    local = a_bogota(momento_utc)
    return local.replace(hour=0, minute=0, second=0, microsecond=0)


def formato_cop(valor: int) -> str:
    return "$" + f"{int(valor):,}".replace(",", ".")


def formato_hora_bogota(momento: datetime) -> str:
    local = a_bogota(momento)
    hora = local.hour % 12 or 12
    sufijo = "a. m." if local.hour < 12 else "p. m."
    return f"{hora}:{local.minute:02d} {sufijo}"
