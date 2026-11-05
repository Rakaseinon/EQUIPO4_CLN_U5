"""Adaptador de persistencia con SQLAlchemy (Repository)."""

from sqlalchemy import Column, Float, Integer, String, create_engine
from sqlalchemy.orm import DeclarativeBase, Session


class Base(DeclarativeBase):
    pass


class OrderRow(Base):
    __tablename__ = "orders"
    id = Column(Integer, primary_key=True)
    total = Column(Float, nullable=False)
    status = Column(String, nullable=False)

    def __repr__(self) -> str:
        return f"OrderRow(id={self.id}, total={self.total}, status={self.status})"


class SqlOrderRepository:
    def __init__(self, session: Session):
        self.session = session

    def save(self, order_id, order):
        self.session.add(OrderRow(id=order_id, total=order.total, status=order.status))

    def get(self, order_id):
        return self.session.get(OrderRow, order_id)


def make_engine(url="sqlite+pysqlite:///:memory:", **kwargs):
    engine = create_engine(url, **kwargs)
    Base.metadata.create_all(engine)
    return engine
