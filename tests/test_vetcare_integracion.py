"""VetCare 24 (PIA): persistencia de vacunas y recordatorios con notificador simulado (mock)"""

from datetime import date, datetime
from unittest.mock import Mock

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from src.repository import make_engine
from src.vetcare.domain import AplicacionVacuna
from src.vetcare.repository import AplicacionVacunaRow, SqlVacunaRepository
from src.vetcare.servicios import ServicioRecordatorios, ServicioVacunacion

DOS_DIAS_ANTES = datetime(2026, 11, 23, 0, 0)   # el refuerzo del 25/11 está a 48 h exactas


@pytest.fixture
def session():
    engine = make_engine()
    with Session(engine) as s:
        yield s
    engine.dispose()


def _quintuple(mascota=1, fecha=date(2026, 11, 4)):
    return AplicacionVacuna(mascota, "Quíntuple Canina", "L-2026-118", "Zoetis", fecha)


# ---------------------------- Persistencia (RN-03) ----------------------------

def test_vc21_vacuna_se_guarda_con_commit(session, resultado):
    """VC-21 (persistencia): registrar la Quíntuple con commit la deja en el expediente.
    Esperado: 1 aplicación guardada con lote L-2026-118 y refuerzo 25/11/2026"""
    refuerzo = ServicioVacunacion(session).registrar(_quintuple())
    filas = SqlVacunaRepository(session).de_mascota(1)
    resultado(f"{len(filas)} registro: {filas[0]!r}")
    assert refuerzo == date(2026, 11, 25)
    assert (filas[0].lote, filas[0].proximo_refuerzo) == ("L-2026-118", date(2026, 11, 25))


def test_vc22_rollback_descarta_la_aplicacion(session, resultado):
    """VC-22 (persistencia): si se hace rollback, la aplicación no queda guardada.
    Esperado: 0 registros"""
    SqlVacunaRepository(session).agregar(_quintuple())
    session.rollback()
    filas = SqlVacunaRepository(session).de_mascota(1)
    resultado(f"{len(filas)} registros")
    assert filas == []


@pytest.mark.parametrize("lote,fabricante", [("", "Zoetis"), ("L-1", "  ")])
def test_vc23_la_bd_tambien_exige_lote(session, lote, fabricante):
    """VC-23 (persistencia, defensa en BD): insertar directo en la tabla sin lote o fabricante.
    Esperado: IntegrityError por la restricción CHECK y nada guardado"""
    session.add(AplicacionVacunaRow(mascota_id=1, vacuna="X", lote=lote, fabricante=fabricante,
                                    fecha=date(2026, 11, 4), proximo_refuerzo=date(2026, 11, 25)))
    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()
    assert SqlVacunaRepository(session).de_mascota(1) == []


# ---------------------------- Recordatorios con mock (RF-05 / US08) ----------------------------

def test_vc24_recordatorio_se_envia_una_sola_vez(session, resultado):
    """VC-24 (mock éxito): a 48 h del refuerzo se envía el aviso por WhatsApp/correo (simulado).
    Esperado: 1 mensaje; al volver a ejecutar el proceso no se repite"""
    ServicioVacunacion(session).registrar(_quintuple())
    notificador = Mock()
    servicio = ServicioRecordatorios(session, notificador)
    primero = servicio.despachar(DOS_DIAS_ANTES)
    segundo = servicio.despachar(DOS_DIAS_ANTES)
    mensaje = notificador.enviar.call_args.args[1]
    resultado(f"1a corrida {primero}, 2a corrida {segundo}; mensaje: '{mensaje}'")
    notificador.enviar.assert_called_once()
    assert "25/11/2026" in mensaje and primero["enviados"] == 1 and segundo["enviados"] == 0


def test_vc25_todavia_no_toca_el_recordatorio(session):
    """VC-25 (mock límite): faltan más de 48 h (5 días) para el refuerzo.
    Esperado: el notificador no se llama"""
    ServicioVacunacion(session).registrar(_quintuple())
    notificador = Mock()
    ServicioRecordatorios(session, notificador).despachar(datetime(2026, 11, 20, 0, 0))
    notificador.enviar.assert_not_called()


def test_vc26_falla_del_proveedor_deja_pendiente(session, resultado):
    """VC-26 (mock con falla): WhatsApp no responde; el aviso queda pendiente para reintentar.
    Esperado: 1 fallido y en la siguiente corrida (proveedor ya responde) se envía"""
    ServicioVacunacion(session).registrar(_quintuple())
    notificador = Mock()
    notificador.enviar.side_effect = [TimeoutError("sin respuesta"), None]
    servicio = ServicioRecordatorios(session, notificador)
    primero = servicio.despachar(DOS_DIAS_ANTES)
    segundo = servicio.despachar(DOS_DIAS_ANTES)
    resultado(f"1a corrida {primero}, 2a corrida {segundo}")
    assert primero == {"enviados": 0, "fallidos": 1}
    assert segundo == {"enviados": 1, "fallidos": 0}
