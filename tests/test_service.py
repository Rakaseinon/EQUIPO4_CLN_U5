"""Cobro con pasarela de pago simulada (mocks: no se cobra dinero real)"""

from unittest.mock import Mock

import pytest

from src.application import OrderService, PaymentUnavailable
from src.domain import CustomerHasDebt, Order


@pytest.fixture
def gateway():
    """Pasarela de pago FALSA controlada por la prueba (Mock)."""
    return Mock()


def test_gateway_approved(gateway, resultado):
    """Si la pasarela APRUEBA el pago, el servicio devuelve el importe cobrado.
    Esperado: se cobra $100 una sola vez"""
    gateway.charge.return_value = True
    monto = OrderService(gateway).checkout(Order(100))
    resultado(f"cobro ${monto:.2f}; llamadas a charge: {gateway.charge.call_args_list}")
    assert monto == 100
    gateway.charge.assert_called_once_with(100)


def test_gateway_rejected(gateway):
    """Si la pasarela RECHAZA el pago, el servicio lanza un error.
    Esperado: RuntimeError "payment rejected\""""
    gateway.charge.return_value = False
    with pytest.raises(RuntimeError, match="payment rejected"):
        OrderService(gateway).checkout(Order(100))


# ---------------- Evidencia E5 ----------------

def test_vip_200_rechazado_intenta_cobrar_170(gateway, resultado):
    """Pago RECHAZADO de un pedido VIP de $200: se intentó cobrar $170 y se lanzó error.
    Esperado: charge(170) llamado una vez y RuntimeError"""
    gateway.charge.return_value = False
    with pytest.raises(RuntimeError, match="payment rejected"):
        OrderService(gateway).checkout(Order(200, vip=True))
    resultado(f"charge llamado con {gateway.charge.call_args.args}; RuntimeError")
    gateway.charge.assert_called_once_with(170)


def test_pago_rechazado_no_deja_pedido_confirmado(gateway, resultado):
    """Mejora de consistencia (TDD): si el pago se rechaza, el pedido NO debe quedar confirmado.
    Esperado: el pedido sigue en estado NEW"""
    gateway.charge.return_value = False
    pedido = Order(200, vip=True)
    with pytest.raises(RuntimeError):
        OrderService(gateway).checkout(pedido)
    resultado(f"estado del pedido: {pedido.status}")
    assert pedido.status == "NEW"


def test_pasarela_no_responde_timeout(gateway, resultado):
    """Si la pasarela no responde (timeout), se informa 'servicio no disponible' y no se confirma.
    Esperado: PaymentUnavailable y pedido en NEW"""
    gateway.charge.side_effect = TimeoutError("gateway timeout")
    pedido = Order(100)
    with pytest.raises(PaymentUnavailable):
        OrderService(gateway).checkout(pedido)
    resultado(f"PaymentUnavailable; estado {pedido.status}")
    assert pedido.status == "NEW"


def test_cliente_con_deuda_no_llega_a_la_pasarela(gateway):
    """Si el cliente tiene deuda, el pedido se rechaza ANTES de intentar cobrar.
    Esperado: CustomerHasDebt y la pasarela nunca se llama"""
    with pytest.raises(CustomerHasDebt):
        OrderService(gateway).checkout(Order(150), customer_debt=500)
    gateway.charge.assert_not_called()


def test_total_invalido_no_llega_a_la_pasarela(gateway):
    """Un pedido con total $0 se rechaza sin intentar cobrar.
    Esperado: ValueError y la pasarela nunca se llama"""
    with pytest.raises(ValueError):
        OrderService(gateway).checkout(Order(0))
    gateway.charge.assert_not_called()
