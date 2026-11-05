"""Persistencia con base de datos (pruebas de integración con SQLAlchemy + SQLite en memoria)"""

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from src.domain import Order
from src.repository import OrderRow, SqlOrderRepository, make_engine


@pytest.fixture
def session():
    """Cada prueba recibe su propia base de datos vacía en memoria (no toca datos reales)."""
    engine = make_engine()
    with Session(engine) as s:
        yield s
    engine.dispose()


def test_repository_commit(session, resultado):
    """Un pedido guardado y confirmado con COMMIT queda registrado en la base de datos.
    Esperado: el pedido id=1 existe con total $120"""
    SqlOrderRepository(session).save(1, Order(120))
    session.commit()
    fila = session.scalar(select(OrderRow).where(OrderRow.id == 1))
    resultado(f"id={fila.id}, total=${fila.total:.2f}")
    assert fila.total == 120


def test_repository_rollback(session, resultado):
    """Si se hace ROLLBACK, el pedido que se iba a guardar se descarta.
    Esperado: al buscar el pedido id=1 no existe (None)"""
    SqlOrderRepository(session).save(1, Order(120))
    session.rollback()
    fila = session.scalar(select(OrderRow).where(OrderRow.id == 1))
    resultado(f"registro encontrado: {fila}")
    assert fila is None


# ---------------- Evidencia E4 ----------------

def test_guardar_pedido_250_con_commit(session, resultado):
    """Un pedido de $250 confirmado se guarda con id=2 y conserva total y estado.
    Esperado: id=2, total $250.00, estado CONFIRMED"""
    pedido = Order(250)
    pedido.confirm()
    repo = SqlOrderRepository(session)
    repo.save(2, pedido)
    session.commit()

    fila = repo.get(2)
    resultado(f"id={fila.id}, total=${fila.total:.2f}, estado {fila.status}")
    assert (fila.id, fila.total, fila.status) == (2, 250, "CONFIRMED")


def test_commit_sobrevive_a_un_rollback_posterior(session, resultado):
    """Lo que ya se confirmó con COMMIT no se pierde si después se hace ROLLBACK de otro cambio.
    Esperado: el pedido 1 sigue existiendo y el pedido 2 no"""
    repo = SqlOrderRepository(session)
    repo.save(1, Order(100))
    session.commit()
    repo.save(2, Order(300))
    session.rollback()
    resultado(f"pedido 1: {repo.get(1) is not None}, pedido 2: {repo.get(2) is not None}")
    assert repo.get(1) is not None
    assert repo.get(2) is None


def test_id_duplicado_se_rechaza_y_se_revierte(session, resultado):
    """Restricción de unicidad: no se pueden guardar dos pedidos con el mismo id.
    Esperado: error IntegrityError y el pedido original ($100) queda intacto"""
    repo = SqlOrderRepository(session)
    repo.save(1, Order(100))
    session.commit()

    repo.save(1, Order(999))
    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()
    fila = repo.get(1)
    resultado(f"IntegrityError; pedido 1 conserva total ${fila.total:.2f}")
    assert fila.total == 100


def test_buscar_pedido_inexistente(session):
    """Buscar un pedido que nunca se guardó regresa vacío (no truena).
    Esperado: None"""
    assert SqlOrderRepository(session).get(404) is None
