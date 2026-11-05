"""TechStore: persistencia en BD y cobro con pasarela simulada (integración + mocks)"""

from decimal import Decimal
from unittest.mock import Mock

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from src.repository import make_engine
from src.techstore.domain import InvalidOrderData, InvalidOrderTransition, OrderStatus
from src.techstore.fixtures import load_fixture
from src.techstore.repository import SqlTechStoreRepository, TechStoreOrderRow
from src.techstore.service import (
    CheckoutService,
    PagoRechazado,
    PasarelaNoDisponible,
    importe_a_cobrar,
)


@pytest.fixture
def session():
    engine = make_engine()
    with Session(engine) as s:
        yield s
    engine.dispose()


@pytest.fixture
def pedidos():
    return load_fixture()


@pytest.fixture
def pasarela():
    g = Mock()
    g.charge.return_value = True
    return g


def _filas(session):
    return session.scalar(select(func.count()).select_from(TechStoreOrderRow))


# ---------------------------- Persistencia ----------------------------

def test_guardar_pedido_con_commit(session, pedidos, resultado):
    """Un pedido de TechStore guardado con COMMIT se puede consultar después.
    Esperado: O001 en BD con total $2100.00 y 4 unidades"""
    repo = SqlTechStoreRepository(session)
    repo.add(pedidos["O001"])
    session.commit()
    fila = repo.get("O001")
    resultado(f"{fila.id}: total ${fila.total}, {fila.units} unidades, {fila.status}")
    assert fila.total == Decimal("2100.00") and fila.units == 4


def test_rollback_descarta_el_pedido(session, pedidos, resultado):
    """Con ROLLBACK el pedido no queda guardado.
    Esperado: O002 no existe en BD"""
    repo = SqlTechStoreRepository(session)
    repo.add(pedidos["O002"])
    session.rollback()
    resultado(f"registro: {repo.get('O002')}")
    assert repo.get("O002") is None


def test_id_de_pedido_duplicado_se_rechaza(session, pedidos):
    """Restricción de unicidad: no puede haber dos pedidos con el mismo id.
    Esperado: IntegrityError y solo 1 registro"""
    repo = SqlTechStoreRepository(session)
    repo.add(pedidos["O001"])
    session.commit()
    repo.add(load_fixture()["O001"])
    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()
    assert _filas(session) == 1


# ---------------------------- Cobro con mock ----------------------------

def test_cobro_aprobado_aplica_descuento_y_guarda(session, pedidos, pasarela, resultado):
    """Pago APROBADO de O001 (VIP, $2100, 10 % de descuento): se cobra $1890 y se guarda.
    Esperado: charge('O001', 1890.00), estado CONFIRMED y 1 registro en BD"""
    o = pedidos["O001"]
    cobrado = CheckoutService(session, pasarela).confirmar_y_cobrar(o)
    fila = SqlTechStoreRepository(session).get("O001")
    resultado(f"cobrado ${cobrado}, estado {o.status.value}, guardado con cargo ${fila.charged}")
    pasarela.charge.assert_called_once_with("O001", Decimal("1890.00"))
    assert o.status == OrderStatus.CONFIRMED and fila.charged == Decimal("1890.00")


def test_cobro_rechazado_no_confirma_ni_guarda(session, pedidos, pasarela, resultado):
    """Pago RECHAZADO: el pedido no se confirma y no se guarda nada.
    Esperado: PagoRechazado, O002 sigue en DRAFT y 0 registros"""
    pasarela.charge.return_value = False
    o = pedidos["O002"]
    with pytest.raises(PagoRechazado):
        CheckoutService(session, pasarela).confirmar_y_cobrar(o)
    resultado(f"estado {o.status.value}, registros en BD: {_filas(session)}")
    assert o.status == OrderStatus.DRAFT and o.events == [] and _filas(session) == 0


def test_pasarela_timeout(session, pedidos, pasarela, resultado):
    """La pasarela no responde (timeout).
    Esperado: PasarelaNoDisponible y el pedido sigue en DRAFT"""
    pasarela.charge.side_effect = TimeoutError
    o = pedidos["O006"]
    with pytest.raises(PasarelaNoDisponible):
        CheckoutService(session, pasarela).confirmar_y_cobrar(o)
    resultado(f"estado {o.status.value}")
    assert o.status == OrderStatus.DRAFT


@pytest.mark.parametrize("pedido,error", [("O003", InvalidOrderData),
                                          ("O007", InvalidOrderData)])
def test_regla_rota_no_llega_a_la_pasarela(session, pedidos, pasarela, pedido, error):
    """Si {pedido} no puede confirmarse (cliente inactivo / sin artículos) NO se intenta cobrar.
    Esperado: error de dominio y charge nunca llamado"""
    with pytest.raises(error):
        CheckoutService(session, pasarela).confirmar_y_cobrar(pedidos[pedido])
    pasarela.charge.assert_not_called()


def test_pedido_ya_confirmado_no_se_cobra_dos_veces(session, pedidos, pasarela):
    """Un pedido ya confirmado no se vuelve a cobrar.
    Esperado: InvalidOrderTransition y charge llamado solo 1 vez"""
    servicio = CheckoutService(session, pasarela)
    servicio.confirmar_y_cobrar(pedidos["O013"])
    with pytest.raises(InvalidOrderTransition):
        servicio.confirmar_y_cobrar(pedidos["O013"])
    assert pasarela.charge.call_count == 1


def test_falla_de_bd_reembolsa_el_cobro(session, pedidos, pasarela, resultado):
    """Si la BD falla después de cobrar, se hace rollback y se REEMBOLSA (compensación).
    Esperado: IntegrityError y refund('O001', 1890.00)"""
    repo = SqlTechStoreRepository(session)
    repo.add(load_fixture()["O001"])       # ya existe un O001 en la BD
    session.commit()
    with pytest.raises(IntegrityError):
        CheckoutService(session, pasarela).confirmar_y_cobrar(pedidos["O001"])
    resultado(f"refund llamado con {pasarela.refund.call_args.args}")
    pasarela.refund.assert_called_once_with("O001", Decimal("1890.00"))


@pytest.mark.parametrize("pedido,esperado", [("O001", "1890.00"), ("O006", "17100.00"),
                                             ("O002", "1050.00")])
def test_importe_a_cobrar(pedidos, pedido, esperado, resultado):
    """Importe a cobrar del pedido {pedido} (total menos descuento).
    Esperado: ${esperado}"""
    importe = importe_a_cobrar(pedidos[pedido])
    resultado(f"${importe}")
    assert importe == Decimal(esperado)
