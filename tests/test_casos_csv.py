"""Casos de prueba del profesor (CP01-CP15) leídos desde datos/casos_de_prueba.csv"""

import csv
from pathlib import Path
from unittest.mock import Mock

import pytest
from sqlalchemy.orm import Session

from src.application import OrderService
from src.domain import CustomerHasDebt, Order
from src.repository import SqlOrderRepository, make_engine

DATOS = Path(__file__).resolve().parent.parent / "datos"

# CP08 cambió de expectativa a propósito: tras el ciclo TDD (Evidencia E3) ya no se permite
# confirmar dos veces. El CSV original documenta el comportamiento ANTERIOR.
AJUSTES_TDD = {"CP08": "ValueError"}


def _leer(nombre):
    with (DATOS / nombre).open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


PEDIDOS = {fila["pedido_id"]: fila for fila in _leer("pedidos_prueba.csv")}
CASOS = _leer("casos_de_prueba.csv")
CASOS_DOMINIO = [c for c in CASOS if c["accion"] == "confirmar"]


def _ejecutar(pedido_csv):
    """Construye el pedido con los datos del CSV, lo confirma y devuelve lo que pasó."""
    pedido = Order(float(pedido_csv["total"]), vip=pedido_csv["es_vip"] == "1",
                   status=pedido_csv["estado_inicial"])
    try:
        cobro = pedido.confirm(customer_debt=float(pedido_csv["deuda_cliente"]))
        return f"{pedido.status}, cobro {cobro:.2f}"
    except (ValueError, CustomerHasDebt) as error:
        return type(error).__name__


@pytest.mark.parametrize(
    "caso", CASOS_DOMINIO, ids=[c["caso_id"] for c in CASOS_DOMINIO])
def test_caso_confirmar_desde_csv(caso, resultado):
    """Caso del CSV: confirmar un pedido con los datos de pedidos_prueba.csv."""
    pedido = PEDIDOS[caso["pedido_id"]]
    esperado = AJUSTES_TDD.get(caso["caso_id"], caso["resultado_esperado"])
    tipo = "VIP" if pedido["es_vip"] == "1" else "regular"
    descripcion = (f"{caso['caso_id']}: cliente {tipo} confirma pedido de ${pedido['total']} "
                   f"(deuda ${pedido['deuda_cliente']}, estado inicial "
                   f"{pedido['estado_inicial']}, escenario {pedido['escenario']})")
    real = _ejecutar(pedido)
    resultado(real, esperado=esperado, descripcion=descripcion)
    assert real == esperado


def test_cp13_pago_rechazado_con_mock(resultado):
    """CP13: la pasarela (mock) rechaza el pago del pedido 1.
    Esperado: RuntimeError: payment rejected"""
    gateway = Mock()
    gateway.charge.return_value = False
    with pytest.raises(RuntimeError, match="payment rejected") as error:
        OrderService(gateway).checkout(Order(float(PEDIDOS["1"]["total"])))
    resultado(f"RuntimeError: {error.value}")


def test_cp14_persistencia_commit(resultado):
    """CP14: un pedido guardado con COMMIT es visible después.
    Esperado: Registro visible después de commit"""
    engine = make_engine()
    with Session(engine) as session:
        repo = SqlOrderRepository(session)
        repo.save(1, Order(float(PEDIDOS["1"]["total"])))
        session.commit()
        fila = repo.get(1)
    engine.dispose()
    resultado(f"registro visible: {fila}")
    assert fila is not None


def test_cp15_persistencia_rollback(resultado):
    """CP15: un pedido revertido con ROLLBACK no queda guardado.
    Esperado: Registro ausente después de rollback"""
    engine = make_engine()
    with Session(engine) as session:
        repo = SqlOrderRepository(session)
        repo.save(1, Order(float(PEDIDOS["1"]["total"])))
        session.rollback()
        fila = repo.get(1)
    engine.dispose()
    resultado(f"registro: {fila}")
    assert fila is None
