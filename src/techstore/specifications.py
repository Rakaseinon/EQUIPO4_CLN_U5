from decimal import Decimal

from src.techstore.domain import Order


class Specification:
    def is_satisfied_by(self, order: Order) -> bool:
        raise NotImplementedError

    def __and__(self, other):
        return AndSpec(self, other)

    def __or__(self, other):
        return OrSpec(self, other)

    def __invert__(self):
        return NotSpec(self)


class AndSpec(Specification):
    def __init__(self, left: Specification, right: Specification):
        self.left = left
        self.right = right

    def is_satisfied_by(self, order: Order) -> bool:
        return self.left.is_satisfied_by(order) and self.right.is_satisfied_by(order)


class OrSpec(Specification):
    def __init__(self, left: Specification, right: Specification):
        self.left = left
        self.right = right

    def is_satisfied_by(self, order: Order) -> bool:
        return self.left.is_satisfied_by(order) or self.right.is_satisfied_by(order)


class NotSpec(Specification):
    def __init__(self, spec: Specification):
        self.spec = spec

    def is_satisfied_by(self, order: Order) -> bool:
        return not self.spec.is_satisfied_by(order)


class MinimumAmountSpec(Specification):
    """Total ESTRICTAMENTE mayor al mínimo (>, no >=)."""

    def __init__(self, min_amount: Decimal):
        self.min_amount = min_amount

    def is_satisfied_by(self, order: Order) -> bool:
        return order.total.amount > self.min_amount


class VIPCustomerSpec(Specification):
    def is_satisfied_by(self, order: Order) -> bool:
        return order.customer.is_vip


class MinimumUnitsSpec(Specification):
    """Suma de unidades (no renglones) mayor o igual al mínimo."""

    def __init__(self, min_units: int):
        self.min_units = min_units

    def is_satisfied_by(self, order: Order) -> bool:
        return order.units >= self.min_units


class ActivePromotionSpec(Specification):
    def is_satisfied_by(self, order: Order) -> bool:
        return order.has_promotion


# ---------------------------------------------------------------
# Reglas de descuento
# ---------------------------------------------------------------
# 10 %: VIP, total > 500, >= 4 unidades y SIN promoción activa.
ten_percent_discount = (
    MinimumAmountSpec(Decimal("500"))
    & VIPCustomerSpec()
    & MinimumUnitsSpec(4)
    & ~ActivePromotionSpec()
)

# 5 %: total > 5000 y SIN promoción activa.
five_percent_discount = (
    MinimumAmountSpec(Decimal("5000"))
    & ~ActivePromotionSpec()
)

# Combinación con OR: el pedido tiene algún descuento si cumple cualquiera.
any_discount = ten_percent_discount | five_percent_discount


def discount_rate(order: Order) -> Decimal:
    """Devuelve la tasa de descuento aplicable.

    Si se cumplen ambas reglas, tiene prioridad el 10 %.
    """
    if ten_percent_discount.is_satisfied_by(order):
        return Decimal("0.10")
    if five_percent_discount.is_satisfied_by(order):
        return Decimal("0.05")
    return Decimal("0")
