from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum


# Excepciones de dominio
class DomainException(Exception):
    pass


class InvalidOrderData(DomainException):
    pass


class InvalidOrderTransition(DomainException):
    pass


class OrderItemLimitExceeded(DomainException):
    pass



class OrderStatus(str, Enum):
    DRAFT = "DRAFT"
    CONFIRMED = "CONFIRMED"
    SHIPPED = "SHIPPED"
    DELIVERED = "DELIVERED"
    CANCELLED = "CANCELLED"
    RETURNED = "RETURNED"

@dataclass(frozen=True)
class Money:
    amount: Decimal
    currency: str = "MXN"

    def __post_init__(self):
        if not isinstance(self.amount, Decimal):
            object.__setattr__(self, 'amount', Decimal(str(self.amount)))
        if not self.amount.is_finite() or self.amount < 0:
            raise InvalidOrderData("Monto inválido")

    def add(self, other: "Money") -> "Money":
        if self.currency != other.currency:
            raise InvalidOrderData("Monedas distintas")
        return Money(self.amount + other.amount, self.currency)

@dataclass(frozen=True)
class Customer:
    id: str
    is_vip: bool = False
    active: bool = True

@dataclass(frozen=True)
class OrderItem:
    sku: str
    quantity: int
    unit_price: Money

    def __post_init__(self):
        if not self.sku.strip() or self.quantity <= 0:
            raise InvalidOrderData("Artículo inválido")

    @property
    def subtotal(self) -> Money:
        return Money(self.unit_price.amount * Decimal(self.quantity), self.unit_price.currency)

@dataclass(frozen=True)
class DomainEvent:
    name: str
    order_id: str
    occurred_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

@dataclass
class Order:
    customer: Customer
    id: str
    has_promotion: bool = False
    status: OrderStatus = OrderStatus.DRAFT
    items: list[OrderItem] = field(default_factory=list)
    events: list[DomainEvent] = field(default_factory=list)

    @property
    def units(self) -> int:
        return sum(item.quantity for item in self.items)

    @property
    def total(self) -> Money:
        amount = sum((item.subtotal.amount for item in self.items), Decimal("0"))
        return Money(amount)

    def add_item(self, item: OrderItem):
        if self.status != OrderStatus.DRAFT:
            raise InvalidOrderTransition("Solo DRAFT admite artículos")
        if self.units + item.quantity > 20:
            raise OrderItemLimitExceeded("Máximo 20 unidades")
        if item.unit_price.currency != "MXN":
            raise InvalidOrderData("Solo MXN")
        self.items.append(item)

    def ensure_can_confirm(self):
        """Valida las reglas de confirmación SIN cambiar el estado (refactor U5)."""
        if self.status != OrderStatus.DRAFT:
            raise InvalidOrderTransition("Solo DRAFT puede confirmarse")
        if not self.items or not self.customer.active:
            raise InvalidOrderData("Requiere artículos y cliente activo")

    def confirm(self):
        self.ensure_can_confirm()
        self.status = OrderStatus.CONFIRMED
        self.events.append(DomainEvent("OrderConfirmed", self.id))

    def ship(self, tracking_number: str):
        if self.status != OrderStatus.CONFIRMED:
            raise InvalidOrderTransition("Solo pedidos CONFIRMED pueden enviarse")
        if not tracking_number or not tracking_number.strip():
            raise InvalidOrderData("Se requiere un número de guía válido")
        self.status = OrderStatus.SHIPPED
        self.events.append(DomainEvent("OrderShipped", self.id))

    def cancel(self, reason: str):
        if self.status != OrderStatus.CONFIRMED:
            raise InvalidOrderTransition("Solo pedidos CONFIRMED pueden cancelarse")
        if not reason or not reason.strip():
            raise InvalidOrderData("Se requiere un motivo de cancelación")
        self.status = OrderStatus.CANCELLED
        self.events.append(DomainEvent("OrderCancelled", self.id))

    def deliver(self):
        if self.status != OrderStatus.SHIPPED:
            raise InvalidOrderTransition("Solo pedidos SHIPPED pueden entregarse")
        self.status = OrderStatus.DELIVERED
        self.events.append(DomainEvent("OrderDelivered", self.id))

    def return_order(self):
        if self.status != OrderStatus.SHIPPED:
            raise InvalidOrderTransition("Solo pedidos SHIPPED pueden devolverse")
        self.status = OrderStatus.RETURNED
        self.events.append(DomainEvent("OrderReturned", self.id))
