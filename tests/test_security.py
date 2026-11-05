"""Seguridad: quién puede cancelar un pedido (autorización)"""

from datetime import datetime, timedelta, timezone

import pytest

from src.security import can_cancel

# Fecha FIJA para que las pruebas den siempre el mismo resultado.
AHORA = datetime(2026, 11, 4, 12, 0, tzinfo=timezone.utc)
DUENO, OTRO = 1, 2


def test_owner_within_24h():
    """El dueño del pedido puede cancelarlo durante las primeras 24 horas (1 h de antigüedad).
    Esperado: PERMITIDO"""
    assert can_cancel("NEW", DUENO, DUENO, False, AHORA - timedelta(hours=1), AHORA)


def test_stranger_denied():
    """Un usuario que NO es dueño ni administrador no puede cancelar un pedido ajeno.
    Esperado: DENEGADO"""
    assert not can_cancel("NEW", DUENO, OTRO, False, AHORA, AHORA)


def test_shipped_denied_even_admin():
    """Un pedido ENVIADO (SHIPPED) no se cancela, ni siquiera por un administrador.
    Esperado: DENEGADO"""
    assert not can_cancel("SHIPPED", DUENO, DUENO, True, AHORA, AHORA)


def test_expired_denied():
    """El dueño ya no puede cancelar después de 25 horas.
    Esperado: DENEGADO"""
    assert not can_cancel("NEW", DUENO, DUENO, False, AHORA - timedelta(hours=25), AHORA)


# ---------------- Evidencia E6 ----------------

def test_admin_cancela_pedido_new_de_otro_usuario():
    """Un ADMINISTRADOR puede cancelar el pedido NEW de otro usuario.
    Esperado: PERMITIDO"""
    assert can_cancel("NEW", DUENO, OTRO, True, AHORA - timedelta(hours=1), AHORA)


def test_dueno_exactamente_a_las_24_horas_se_rechaza():
    """Caso límite: el dueño intenta cancelar EXACTAMENTE a las 24 horas.
    Esperado: DENEGADO (la regla es 'menos de 24 h')"""
    assert not can_cancel("NEW", DUENO, DUENO, False, AHORA - timedelta(hours=24), AHORA)


def test_dueno_un_segundo_antes_de_24_horas():
    """Caso límite: al dueño le falta 1 segundo para cumplir 24 horas.
    Esperado: PERMITIDO"""
    creado = AHORA - timedelta(hours=24) + timedelta(seconds=1)
    assert can_cancel("NEW", DUENO, DUENO, False, creado, AHORA)


P, D = "PERMITIDO", "DENEGADO"
MATRIZ = [
    # rol,            ¿es dueño?, estado,     antigüedad (h), resultado esperado
    ("administrador", "no", "NEW",       1,  P),
    ("administrador", "no", "NEW",       72, P),
    ("administrador", "sí", "CONFIRMED", 30, P),
    ("administrador", "sí", "SHIPPED",   1,  D),
    ("cliente",       "sí", "NEW",       1,  P),
    ("cliente",       "sí", "CONFIRMED", 23, P),
    ("cliente",       "sí", "NEW",       24, D),
    ("cliente",       "sí", "SHIPPED",   1,  D),
    ("cliente",       "no", "NEW",       1,  D),
    ("cliente",       "no", "SHIPPED",   1,  D),
]


@pytest.mark.parametrize("rol,es_dueno,estado,horas,esperado", MATRIZ)
def test_matriz_de_autorizacion(rol, es_dueno, estado, horas, esperado, resultado):
    """Matriz: {rol} (¿dueño? {es_dueno}) intenta cancelar pedido {estado} de {horas} h.
    Esperado: {esperado}"""
    usuario = DUENO if es_dueno == "sí" else OTRO
    permitido = can_cancel(estado, DUENO, usuario, rol == "administrador",
                           AHORA - timedelta(hours=horas), AHORA)
    obtenido = P if permitido else D
    resultado(obtenido)
    assert obtenido == esperado


def test_sin_now_usa_la_hora_actual():
    """Si no se pasa 'now', la política usa la hora actual del sistema.
    Esperado: pedido recién creado por su dueño -> PERMITIDO"""
    assert can_cancel("NEW", DUENO, DUENO, False, datetime.now(timezone.utc))
