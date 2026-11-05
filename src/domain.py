"""Reglas de negocio del pedido (dominio puro: no importa SQLAlchemy ni pagos)."""

from dataclasses import dataclass

VIP_DISCOUNT_RATE = 0.15
STATUS_NEW = "NEW"
STATUS_CONFIRMED = "CONFIRMED"


class CustomerHasDebt(Exception):
    pass


@dataclass
class Order:
    total: float
    vip: bool = False
    status: str = STATUS_NEW
    discount: float = 0.0

    # ---- REFACTOR (TDD): validaciones extraídas a un método privado ----
    def _validate_can_confirm(self, customer_debt: float) -> None:
        if self.status == STATUS_CONFIRMED:
            raise ValueError("already confirmed")
        if self.total <= 0:
            raise ValueError("total must be positive")
        if customer_debt > 0:
            raise CustomerHasDebt("outstanding debt")

    def _calculate_discount(self) -> float:
        return round(self.total * VIP_DISCOUNT_RATE, 2) if self.vip else 0.0

    def amount_to_charge(self, customer_debt: float = 0) -> float:
        """Valida las reglas y calcula el importe SIN cambiar el estado del pedido."""
        self._validate_can_confirm(customer_debt)
        return round(self.total - self._calculate_discount(), 2)

    def confirm(self, customer_debt: float = 0) -> float:
        amount = self.amount_to_charge(customer_debt)
        self.discount = self._calculate_discount()
        self.status = STATUS_CONFIRMED
        return amount
