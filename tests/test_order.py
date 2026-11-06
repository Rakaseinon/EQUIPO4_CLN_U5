"""Reglas del pedido (pruebas unitarias del dominio)"""

import pytest

from src.domain import CustomerHasDebt, Order


def test_vip_discount(resultado):
    """Un cliente VIP con pedido de $100 recibe 15% de descuento.
    Esperado: cobro de $85.00 y estado CONFIRMED"""
    o = Order(100, vip=True)               # Arrange
    cobro = o.confirm()                    # Act
    resultado(f"cobro ${cobro:.2f}, estado {o.status}")
    assert cobro == 85                     # Assert
    assert o.status == "CONFIRMED"


def test_regular_no_discount(resultado):
    """Un cliente regular con pedido de $100 NO recibe descuento.
    Esperado: cobro de $100.00"""
    cobro = Order(100).confirm()
    resultado(f"cobro ${cobro:.2f}")
    assert cobro == 100


def test_customer_debt():
    """Un cliente con deuda pendiente no puede confirmar su pedido.
    Esperado: error CustomerHasDebt (pedido rechazado)"""
    with pytest.raises(CustomerHasDebt):
        Order(100).confirm(customer_debt=50)


@pytest.mark.parametrize("total", [0, -1])
def test_invalid_total(total):
    """Un pedido con total de ${total} (cero o negativo) se rechaza.
    Esperado: error ValueError (total inválido)"""
    with pytest.raises(ValueError):
        Order(total).confirm()


# ---------------- Evidencia E2: nuevas pruebas ----------------

def test_vip_200_paga_170(resultado):
    """Un cliente VIP con pedido de $200 paga $170 (15% de descuento = $30).
    Esperado: cobro de $170.00 y descuento de $30.00"""
    pedido = Order(200, vip=True)
    cobro = pedido.confirm()
    resultado(f"cobro ${cobro:.2f}, descuento ${pedido.discount:.2f}")
    assert cobro == 999
    assert pedido.discount == 30
    assert pedido.status == "CONFIRMED"


def test_regular_200_paga_200(resultado):
    """Un cliente regular con pedido de $200 paga el total completo.
    Esperado: cobro de $200.00 y descuento de $0.00"""
    pedido = Order(200)
    cobro = pedido.confirm()
    resultado(f"cobro ${cobro:.2f}, descuento ${pedido.discount:.2f}")
    assert cobro == 200
    assert pedido.discount == 0


def test_total_minimo_valido(resultado):
    """Caso límite: el total más pequeño posible ($0.01) sí se acepta.
    Esperado: cobro de $0.01"""
    cobro = Order(0.01).confirm()
    resultado(f"cobro ${cobro:.2f}")
    assert cobro == pytest.approx(0.01)


def test_deuda_cero_si_permite(resultado):
    """Caso límite: deuda exactamente de $0 NO bloquea la confirmación.
    Esperado: pedido CONFIRMED"""
    pedido = Order(100)
    pedido.confirm(customer_debt=0)
    resultado(f"estado {pedido.status}")
    assert pedido.status == "CONFIRMED"


def test_total_invalido_tiene_prioridad_sobre_deuda():
    """Si el total es inválido y además hay deuda, primero se reporta el total inválido.
    Esperado: error ValueError (no CustomerHasDebt)"""
    with pytest.raises(ValueError, match="total must be positive"):
        Order(0).confirm(customer_debt=500)


# ---------------- Evidencia E3: TDD (RED -> GREEN -> REFACTOR) ----------------

def test_cannot_confirm_twice():
    """TDD: un pedido que ya fue confirmado NO puede confirmarse otra vez.
    Esperado: error ValueError "already confirmed\""""
    order = Order(100)
    order.confirm()
    with pytest.raises(ValueError, match="already confirmed"):
        order.confirm()
