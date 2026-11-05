"""Servicio de aplicación: orquesta el dominio y la pasarela de pago (puerto externo)."""


class PaymentUnavailable(RuntimeError):
    """La pasarela de pago no respondió (timeout / caída del proveedor)."""


class OrderService:
    def __init__(self, gateway):
        self.gateway = gateway

    def checkout(self, order, customer_debt=0):
        # 1) Validar reglas y calcular importe SIN confirmar todavía.
        amount = order.amount_to_charge(customer_debt)
        # 2) Intentar el cobro en el servicio externo.
        try:
            approved = self.gateway.charge(amount)
        except TimeoutError as exc:
            raise PaymentUnavailable("payment gateway unavailable") from exc
        if not approved:
            raise RuntimeError("payment rejected")
        # 3) Solo con pago aprobado el pedido pasa a CONFIRMED (evita confirmado sin pago).
        return order.confirm(customer_debt)
