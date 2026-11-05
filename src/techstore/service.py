"""Servicio de cobro TechStore: dominio + pasarela de pago (puerto) + repositorio."""

from decimal import ROUND_HALF_UP, Decimal

from src.techstore.repository import SqlTechStoreRepository
from src.techstore.specifications import discount_rate


class PagoRechazado(RuntimeError):
    pass


class PasarelaNoDisponible(RuntimeError):
    pass


def importe_a_cobrar(order) -> Decimal:
    """Total menos el descuento que indiquen las Specifications (10 %, 5 % o 0 %)."""
    importe = order.total.amount * (Decimal("1") - discount_rate(order))
    return importe.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


class CheckoutService:
    def __init__(self, session, gateway):
        self.session = session
        self.repo = SqlTechStoreRepository(session)
        self.gateway = gateway

    def confirmar_y_cobrar(self, order) -> Decimal:
        order.ensure_can_confirm()              # 1) reglas de dominio, sin cambiar estado
        importe = importe_a_cobrar(order)
        try:
            aprobado = self.gateway.charge(order.id, importe)   # 2) servicio externo
        except TimeoutError as exc:
            raise PasarelaNoDisponible("la pasarela de pago no respondió") from exc
        if not aprobado:
            raise PagoRechazado("pago rechazado")
        order.confirm()                          # 3) solo con pago aprobado
        self.repo.add(order, charged=importe)
        try:
            self.session.commit()                # 4) persistencia
        except Exception:
            self.session.rollback()
            self.gateway.refund(order.id, importe)   # compensación: no cobrar sin registro
            raise
        return importe
