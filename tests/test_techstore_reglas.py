"""TechStore (Actividad 4): reglas de negocio del pedido (unidades, descuentos y estados)"""

from decimal import Decimal

import pytest

from src.techstore.domain import (
    Customer,
    InvalidOrderData,
    InvalidOrderTransition,
    Money,
    Order,
    OrderItem,
    OrderItemLimitExceeded,
    OrderStatus,
)
from src.techstore.fixtures import load_fixture, rows
from src.techstore.specifications import (
    MinimumAmountSpec,
    MinimumUnitsSpec,
    any_discount,
    discount_rate,
    five_percent_discount,
    ten_percent_discount,
)


@pytest.fixture
def pedidos():
    """Pedidos recién cargados de datos/techstore/*.csv (cada prueba es independiente)."""
    return load_fixture()


def _eventos(order):
    return [e.name for e in order.events]


# ===================== R1: máximo 20 unidades por pedido =====================

def test_r1_exito_20_unidades_exactas(pedidos, resultado):
    """R1 éxito: el pedido O008 con 20 unidades exactas sí se puede confirmar.
    Esperado: estado CONFIRMED"""
    o = pedidos["O008"]
    o.confirm()
    resultado(f"{o.units} unidades, estado {o.status.value}")
    assert o.status == OrderStatus.CONFIRMED


def test_r1_error_agregar_hasta_21_unidades(pedidos, resultado):
    """R1 error: O009 tiene 19 unidades y se intentan agregar 2 más (21).
    Esperado: OrderItemLimitExceeded y el pedido se queda con 19 unidades"""
    o = pedidos["O009"]
    with pytest.raises(OrderItemLimitExceeded):
        o.add_item(OrderItem("SKU003", 2, Money(Decimal("120.00"))))
    resultado(f"rechazado; el pedido sigue con {o.units} unidades")
    assert o.units == 19


def test_r1_limite_19_mas_1_llega_a_20(pedidos, resultado):
    """R1 límite: O009 tiene 19 unidades y se agrega 1 (justo 20).
    Esperado: se acepta, 20 unidades"""
    o = pedidos["O009"]
    o.add_item(OrderItem("SKU003", 1, Money(Decimal("120.00"))))
    resultado(f"{o.units} unidades")
    assert o.units == 20


def test_r1_cuenta_unidades_no_renglones(resultado):
    """R1 límite: dos renglones de 10 unidades suman 20 (permitido); uno más de 1 ya no.
    Esperado: 20 unidades aceptadas y luego OrderItemLimitExceeded"""
    o = Order(Customer("CX"), "OX")
    o.add_item(OrderItem("A", 10, Money(Decimal("1"))))
    o.add_item(OrderItem("B", 10, Money(Decimal("1"))))
    with pytest.raises(OrderItemLimitExceeded):
        o.add_item(OrderItem("C", 1, Money(Decimal("1"))))
    resultado(f"{len(o.items)} renglones, {o.units} unidades")
    assert o.units == 20


def test_r1_no_se_agregan_articulos_despues_de_confirmar(pedidos):
    """R1 error: después de confirmar ya no se pueden agregar artículos.
    Esperado: InvalidOrderTransition"""
    o = pedidos["O013"]
    o.confirm()
    with pytest.raises(InvalidOrderTransition):
        o.add_item(OrderItem("SKU001", 1, Money(Decimal("600"))))


# ===================== R2: descuentos (patrón Specification) =====================

@pytest.mark.parametrize("pedido,esperado,motivo", [
    ("O001", "10", "VIP, total $2100, 4 unidades, sin promoción"),
    ("O006", "5", "total mayor a $5000, sin promoción"),
    ("O002", "0", "no VIP y total menor a $5000"),
    ("O005", "0", "promoción activa bloquea el descuento"),
    ("O010", "0", "total EXACTAMENTE $500 (la regla es > 500)"),
    ("O011", "0", "VIP con solo 3 unidades (requiere 4)"),
])
def test_r2_descuento_por_pedido(pedidos, pedido, esperado, motivo, resultado):
    """R2: pedido {pedido} -> {motivo}.
    Esperado: descuento de {esperado} %"""
    tasa = discount_rate(pedidos[pedido])
    resultado(f"descuento de {int(tasa * 100)} %")
    assert tasa == Decimal(esperado) / 100


def test_r2_limite_prioridad_10_sobre_5(resultado):
    """R2 límite: un VIP con $5,500 y 5 unidades cumple AMBAS reglas.
    Esperado: se aplica el 10 % (tiene prioridad)"""
    o = Order(Customer("CX", is_vip=True), "OX")
    o.add_item(OrderItem("SKU", 5, Money(Decimal("1100"))))
    assert ten_percent_discount.is_satisfied_by(o) and five_percent_discount.is_satisfied_by(o)
    resultado(f"descuento de {int(discount_rate(o) * 100)} %")
    assert discount_rate(o) == Decimal("0.10")


def test_r2_limite_umbrales(pedidos, resultado):
    """R2 límite: $500 exactos NO superan el mínimo; 4 unidades exactas SÍ cumplen el mínimo.
    Esperado: monto mínimo = No, unidades mínimas = Sí"""
    monto = MinimumAmountSpec(Decimal("500")).is_satisfied_by(pedidos["O010"])
    unidades = MinimumUnitsSpec(4).is_satisfied_by(pedidos["O001"])
    resultado(f"monto mínimo = {'Sí' if monto else 'No'}, "
              f"unidades mínimas = {'Sí' if unidades else 'No'}")
    assert (monto, unidades) == (False, True)


def test_r2_or_algun_descuento(pedidos):
    """R2: la combinación OR detecta si el pedido tiene algún descuento.
    Esperado: O001 sí, O006 sí, O002 no"""
    assert any_discount.is_satisfied_by(pedidos["O001"])
    assert any_discount.is_satisfied_by(pedidos["O006"])
    assert not any_discount.is_satisfied_by(pedidos["O002"])


def test_r2_specification_no_modifica_el_pedido(pedidos):
    """R2: evaluar un descuento no cambia nada del pedido (solo consulta).
    Esperado: estado, unidades, total y eventos iguales"""
    o = pedidos["O001"]
    antes = (o.status, o.units, o.total.amount, len(o.events))
    ten_percent_discount.is_satisfied_by(o)
    assert antes == (o.status, o.units, o.total.amount, len(o.events))


# ===================== R3: máquina de estados del pedido =====================

def test_r3_exito_flujo_completo_hasta_entregado(pedidos, resultado):
    """R3 éxito: O016 pasa por DRAFT -> CONFIRMED -> SHIPPED -> DELIVERED.
    Esperado: DELIVERED con 3 eventos"""
    o = pedidos["O016"]
    o.confirm()
    o.ship("GUIA1")
    o.deliver()
    resultado(f"{o.status.value}, eventos {_eventos(o)}")
    assert o.status == OrderStatus.DELIVERED
    assert _eventos(o) == ["OrderConfirmed", "OrderShipped", "OrderDelivered"]


def test_r3_error_cancelar_pedido_enviado(pedidos, resultado):
    """R3 error: O014 ya fue enviado y se intenta cancelar.
    Esperado: InvalidOrderTransition y sigue en SHIPPED"""
    o = pedidos["O014"]
    o.confirm()
    o.ship("GUIA123")
    with pytest.raises(InvalidOrderTransition):
        o.cancel("ya no lo quiero")
    resultado(f"rechazado; estado {o.status.value}")
    assert o.status == OrderStatus.SHIPPED


def test_r3_limite_doble_confirmacion_sin_evento_extra(pedidos, resultado):
    """R3 límite: O013 se confirma dos veces; la segunda se rechaza.
    Esperado: InvalidOrderTransition y solo 1 evento OrderConfirmed"""
    o = pedidos["O013"]
    o.confirm()
    with pytest.raises(InvalidOrderTransition):
        o.confirm()
    resultado(f"eventos {_eventos(o)}")
    assert _eventos(o) == ["OrderConfirmed"]


@pytest.mark.parametrize("guia", ["", "   "])
def test_r3_envio_sin_guia(pedidos, guia):
    """R3 error: enviar O012 con guía vacía ('{guia}').
    Esperado: InvalidOrderData y sigue CONFIRMED"""
    o = pedidos["O012"]
    o.confirm()
    with pytest.raises(InvalidOrderData):
        o.ship(guia)
    assert o.status == OrderStatus.CONFIRMED


@pytest.mark.parametrize("pedido,motivo", [("O003", "cliente inactivo"),
                                           ("O007", "pedido sin artículos")])
def test_r3_no_se_confirma(pedidos, pedido, motivo):
    """R3 error: no se confirma {pedido} ({motivo}).
    Esperado: InvalidOrderData, sigue en DRAFT y sin eventos"""
    o = pedidos[pedido]
    with pytest.raises(InvalidOrderData):
        o.confirm()
    assert o.status == OrderStatus.DRAFT and o.events == []


def test_r3_cancelacion_valida_y_sin_motivo(pedidos):
    """R3: cancelar sin motivo se rechaza; con motivo, el pedido queda CANCELLED.
    Esperado: InvalidOrderData y luego CANCELLED"""
    o = pedidos["O002"]
    o.confirm()
    with pytest.raises(InvalidOrderData):
        o.cancel("")
    o.cancel("cambio de opinión")
    assert o.status == OrderStatus.CANCELLED


def test_r3_devolucion_y_entrega_desde_draft(pedidos):
    """R3: O015 se devuelve desde SHIPPED; O016 no puede entregarse estando en DRAFT.
    Esperado: RETURNED e InvalidOrderTransition"""
    o = pedidos["O015"]
    o.confirm()
    o.ship("G1")
    o.return_order()
    assert o.status == OrderStatus.RETURNED
    with pytest.raises(InvalidOrderTransition):
        pedidos["O016"].deliver()
    with pytest.raises(InvalidOrderTransition):
        pedidos["O002"].ship("G1")
    with pytest.raises(InvalidOrderTransition):
        pedidos["O002"].return_order()


# ===================== Value Objects =====================

def test_value_objects_invalidos():
    """Money no acepta montos negativos ni sumar monedas distintas; un artículo no tiene 0 piezas.
    Esperado: InvalidOrderData en los tres casos"""
    with pytest.raises(InvalidOrderData):
        Money(Decimal("-10"))
    with pytest.raises(InvalidOrderData):
        Money(Decimal("1"), "MXN").add(Money(Decimal("1"), "USD"))
    with pytest.raises(InvalidOrderData):
        OrderItem("SKU001", 0, Money(Decimal("10")))
    assert Money(Decimal("1")).add(Money(Decimal("2"))).amount == 3


def test_solo_se_aceptan_pesos_mexicanos():
    """Un artículo con precio en dólares no se puede agregar al pedido.
    Esperado: InvalidOrderData"""
    with pytest.raises(InvalidOrderData):
        Order(Customer("CX"), "OX").add_item(OrderItem("A", 1, Money(Decimal("5"), "USD")))


# ===================== Escenarios E01-E15 de la Actividad 4 =====================

def _correr(accion, o):
    confirmar = ("confirmar", o.confirm)
    enviar = ("enviar", lambda: o.ship("GUIA-001"))
    pasos = {
        "confirmar": [confirmar],
        "agregar SKU003 x2": [("agregar", lambda: o.add_item(
            OrderItem("SKU003", 2, Money(Decimal("120.00")))))],
        "confirmar y enviar sin guia": [confirmar, ("enviar sin guia", lambda: o.ship(""))],
        "confirmar dos veces": [confirmar, ("segunda confirmacion", o.confirm)],
        "confirmar, enviar y cancelar": [confirmar, enviar, ("cancelar", lambda: o.cancel("x"))],
        "confirmar, enviar y devolver": [confirmar, enviar, ("devolver", o.return_order)],
        "confirmar, enviar y entregar": [confirmar, enviar, ("entregar", o.deliver)],
    }
    for i, (_, paso) in enumerate(pasos[accion]):
        try:
            paso()
        except (InvalidOrderData, InvalidOrderTransition, OrderItemLimitExceeded):
            return "rechazo" if i == 0 or accion.startswith("agregar") else "rechazo posterior"
    return "exito"


ESCENARIOS = rows("escenarios.csv")


@pytest.mark.parametrize("caso", ESCENARIOS, ids=[c["caso_id"] for c in ESCENARIOS])
def test_escenarios_actividad4(caso, resultado):
    """Escenario de la Actividad 4 (datos/techstore/escenarios.csv)."""
    o = load_fixture()[caso["pedido_id"]]
    if caso["accion"] == "evaluar_descuento":
        real = f"{int(discount_rate(o) * 100)}%"
        esperado = caso["objetivo"]
    else:
        real = _correr(caso["accion"], o)
        esperado = {"rechazo envio": "rechazo posterior", "rechazo segunda": "rechazo posterior",
                    "rechazo cancelacion": "rechazo posterior"}.get(caso["objetivo"],
                                                                    caso["objetivo"])
    resultado(f"{real} (estado final {o.status.value})", esperado=esperado,
              descripcion=f"{caso['caso_id']}: {caso['pedido_id']} - {caso['accion']} "
                          f"({caso['pista']})")
    assert real == esperado
