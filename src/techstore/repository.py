"""Persistencia de pedidos TechStore con SQLAlchemy (adaptador del puerto Repository)."""

from sqlalchemy import Column, Integer, Numeric, String

from src.repository import Base


class TechStoreOrderRow(Base):
    __tablename__ = "techstore_orders"
    id = Column(String, primary_key=True)
    customer_id = Column(String, nullable=False)
    status = Column(String, nullable=False)
    units = Column(Integer, nullable=False)
    total = Column(Numeric(12, 2), nullable=False)
    charged = Column(Numeric(12, 2), nullable=True)


class SqlTechStoreRepository:
    def __init__(self, session):
        self.session = session

    def add(self, order, charged=None):
        """Inserta un pedido nuevo (si el id ya existe, la BD lo rechaza al hacer commit)."""
        self.session.add(TechStoreOrderRow(
            id=order.id, customer_id=order.customer.id, status=order.status.value,
            units=order.units, total=order.total.amount, charged=charged))

    def get(self, order_id):
        return self.session.get(TechStoreOrderRow, order_id)
