"""VetCare 24 (PIA): reglas de negocio del BRD (alergias, vacunas, expediente y alta)"""

from datetime import date, datetime, timedelta

import pytest

from src.vetcare.domain import (
    AlergiaRegistrada,
    AltaIncompleta,
    AplicacionVacuna,
    AreaHospitalizacion,
    EnmiendaInvalida,
    JaulaOcupada,
    LoteObligatorio,
    Mascota,
    NotaClinica,
    NotaFirmada,
    PesoRequerido,
    Receta,
    normalizar,
    toca_recordatorio,
)

AHORA = datetime(2026, 11, 4, 9, 0)


@pytest.fixture
def firulais():
    """Paciente de prueba: 12 kg, con alergia registrada a Penicilina (ejemplo de US04)."""
    m = Mascota(id=1, nombre="Firulais", peso_kg=12)
    m.registrar_alergia("Penicilina")
    return m


# ===================== R1 · RN-04 / US06 / RF-02: prescripción segura =====================

def test_vc01_receta_sin_alergia_calcula_dosis_por_peso(firulais, resultado):
    """VC-01 (RN-04 éxito): recetar Meloxicam a Firulais (12 kg, alérgico solo a Penicilina).
    Esperado: se agrega a la receta con dosis 12 kg x 0.1 = 1.2"""
    linea = Receta(firulais).agregar("Metacam", "Meloxicam", dosis_por_kg=0.1)
    resultado(f"agregado {linea.farmaco}, dosis total {linea.dosis_total}")
    assert linea.dosis_total == 1.2


def test_vc02_principio_activo_alergeno_se_bloquea(firulais):
    """VC-02 (RN-04 error): recetar un fármaco con Penicilina a un paciente alérgico.
    Esperado: AlergiaRegistrada y la receta queda vacía"""
    receta = Receta(firulais)
    with pytest.raises(AlergiaRegistrada):
        receta.agregar("Pen-Vet", "Penicilina", dosis_por_kg=1)
    assert receta.lineas == []


@pytest.mark.parametrize("escrito", ["PENICILINA", "  penicilina ", "Penicilína"])
def test_vc03_alergia_se_detecta_aunque_cambie_la_escritura(firulais, escrito):
    """VC-03 (RN-04 límite): el médico escribe '{escrito}' (mayúsculas, espacios o acento).
    Esperado: también se bloquea (AlergiaRegistrada)"""
    with pytest.raises(AlergiaRegistrada):
        Receta(firulais).agregar("Genérico", escrito, dosis_por_kg=1)


@pytest.mark.parametrize("peso", [None, 0])
def test_vc04_sin_peso_no_se_puede_dosificar(peso):
    """VC-04 (RF-02 límite): paciente con peso {peso} (no capturado en triaje).
    Esperado: PesoRequerido"""
    with pytest.raises(PesoRequerido):
        Receta(Mascota(2, "Michi", peso_kg=peso)).agregar("Metacam", "Meloxicam", 0.1)


def test_vc05_datos_invalidos_de_receta_y_alergia(firulais):
    """VC-05 (RN-04 error): dosis por kilo en cero o alergia sin principio activo.
    Esperado: ValueError en ambos casos"""
    with pytest.raises(ValueError):
        Receta(firulais).agregar("Metacam", "Meloxicam", dosis_por_kg=0)
    with pytest.raises(ValueError):
        firulais.registrar_alergia("   ")
    assert normalizar("  PeniCilína ") == "penicilina"


# ===================== R2 · RN-03 / RF-04 / US07: vacunación =====================

def test_vc06_vacuna_base_refuerzo_a_21_dias(resultado):
    """VC-06 (RN-03 éxito): Quíntuple Canina con lote y fabricante aplicada el 04/11/2026.
    Esperado: refuerzo el 25/11/2026 (21 días, US07)"""
    v = AplicacionVacuna(1, "Quíntuple Canina", "L-2026-118", "Zoetis", date(2026, 11, 4))
    resultado(f"refuerzo {v.proximo_refuerzo:%d/%m/%Y}")
    assert v.proximo_refuerzo == date(2026, 11, 25)


def test_vc07_vacuna_anual_refuerzo_a_365_dias(resultado):
    """VC-07 (RF-04 éxito): vacuna antirrábica con esquema anual aplicada el 04/11/2026.
    Esperado: refuerzo el 04/11/2027 (365 días)"""
    v = AplicacionVacuna(1, "Antirrábica", "AR-55", "Biozoo", date(2026, 11, 4), "anual")
    resultado(f"refuerzo {v.proximo_refuerzo:%d/%m/%Y}")
    assert v.proximo_refuerzo == date(2027, 11, 4)


@pytest.mark.parametrize("lote,fabricante", [("", "Zoetis"), ("L-1", ""), ("   ", "Zoetis")])
def test_vc08_vacuna_sin_lote_o_fabricante_se_rechaza(lote, fabricante):
    """VC-08 (RN-03 error/límite): lote '{lote}' y fabricante '{fabricante}'.
    Esperado: LoteObligatorio (no se guarda la aplicación)"""
    with pytest.raises(LoteObligatorio):
        AplicacionVacuna(1, "Quíntuple Canina", lote, fabricante, date(2026, 11, 4))


def test_vc09_esquema_desconocido():
    """VC-09 (RF-04 error): esquema de vacunación que no existe en el catálogo.
    Esperado: ValueError"""
    with pytest.raises(ValueError):
        AplicacionVacuna(1, "X", "L-1", "Fab", date(2026, 11, 4), esquema="mensual")


@pytest.mark.parametrize("horas_antes,toca", [(48, True), (47, True), (49, False), (0, False)])
def test_vc10_recordatorio_48_horas_antes(horas_antes, toca, resultado):
    """VC-10 (RF-05 límite): faltan {horas_antes} h para el refuerzo.
    Esperado: ¿enviar recordatorio? {toca}"""
    refuerzo = date(2026, 11, 25)
    ahora = datetime(2026, 11, 25) - timedelta(hours=horas_antes)
    obtenido = toca_recordatorio(refuerzo, ahora)
    resultado(obtenido)
    assert obtenido is toca


# ===================== R3 · RN-01 / US05 / US13: expediente inmutable =====================

@pytest.fixture
def nota_firmada():
    nota = NotaClinica(1, "Otitis externa; limpieza y tratamiento tópico.")
    nota.firmar("Dra. Ruiz", "CED-123456", AHORA)
    return nota


def test_vc11_nota_sin_firmar_se_edita_y_luego_se_firma(resultado):
    """VC-11 (RN-01 éxito): una nota en borrador se puede corregir y después se firma.
    Esperado: texto corregido y nota firmada por la Dra. Ruiz"""
    nota = NotaClinica(1, "Borrador")
    nota.editar("Otitis externa")
    nota.firmar("Dra. Ruiz", "CED-123456", AHORA)
    resultado(f"'{nota.texto}', firmada por {nota.firmada_por}")
    assert nota.firmada and nota.texto == "Otitis externa"


def test_vc12_nota_firmada_no_se_edita_ni_borra(nota_firmada, resultado):
    """VC-12 (RN-01 error): intentar editar o borrar una nota ya firmada.
    Esperado: NotaFirmada en ambos casos y el texto original intacto"""
    original = nota_firmada.texto
    with pytest.raises(NotaFirmada):
        nota_firmada.editar("Texto alterado")
    with pytest.raises(NotaFirmada):
        nota_firmada.eliminar()
    with pytest.raises(NotaFirmada):
        nota_firmada.firmar("Otro", "CED-1", AHORA)
    resultado(f"texto intacto: {nota_firmada.texto == original}")
    assert nota_firmada.texto == original


def test_vc13_enmienda_con_motivo_conserva_el_original(nota_firmada, resultado):
    """VC-13 (US13 éxito): el director médico agrega una nota de enmienda justificada.
    Esperado: 1 enmienda con autor, fecha y motivo; el texto original no cambia"""
    original = nota_firmada.texto
    e = nota_firmada.agregar_enmienda("Dr. Director", "Omisión de dosis", "Agregar dosis",
                                      AHORA + timedelta(days=2))
    resultado(f"{len(nota_firmada.enmiendas)} enmienda de {e.autor}: {e.motivo}")
    assert nota_firmada.texto == original and nota_firmada.enmiendas == [e]


@pytest.mark.parametrize("autor,motivo", [("Dr. Director", ""), ("", "Omisión"),
                                          ("Dr. Director", "   ")])
def test_vc14_enmienda_sin_autor_o_motivo(nota_firmada, autor, motivo):
    """VC-14 (RN-01 límite): enmienda con autor '{autor}' y motivo '{motivo}'.
    Esperado: EnmiendaInvalida y ninguna enmienda registrada"""
    with pytest.raises(EnmiendaInvalida):
        nota_firmada.agregar_enmienda(autor, motivo, "texto", AHORA)
    assert nota_firmada.enmiendas == []


def test_vc15_enmienda_a_nota_sin_firmar_y_firma_incompleta():
    """VC-15 (RN-01 límite): no se enmienda una nota sin firmar; firmar sin cédula no vale.
    Esperado: EnmiendaInvalida y ValueError"""
    nota = NotaClinica(1, "Borrador")
    nota.eliminar()                      # un borrador sí puede descartarse
    with pytest.raises(EnmiendaInvalida):
        nota.agregar_enmienda("Dr. X", "motivo", "texto", AHORA)
    with pytest.raises(ValueError):
        nota.firmar("Dra. Ruiz", "  ", AHORA)
    assert not nota.firmada


# ===================== R4 · RN-06 / US09 / US11: hospitalización y alta =====================

@pytest.fixture
def area():
    return AreaHospitalizacion.con_jaulas("J1", "J2")


def test_vc16_internar_en_jaula_libre(area, resultado):
    """VC-16 (US09 éxito): internar a la mascota 1 en la jaula J1.
    Esperado: J1 ocupada y solo J2 libre"""
    area.internar(1, "J1")
    resultado(f"jaulas libres: {area.jaulas_libres}")
    assert area.jaulas_libres == ["J2"]


def test_vc17_jaula_ocupada_o_mascota_ya_internada(area):
    """VC-17 (US09 error): usar una jaula ocupada, internar dos veces o una jaula que no existe.
    Esperado: JaulaOcupada y ValueError"""
    area.internar(1, "J1")
    with pytest.raises(JaulaOcupada):
        area.internar(2, "J1")
    with pytest.raises(ValueError):
        area.internar(1, "J2")
    with pytest.raises(ValueError):
        area.internar(3, "J9")


def test_vc18_alta_con_las_dos_firmas_libera_la_jaula(area, resultado):
    """VC-18 (RN-06 éxito): alta médica del veterinario + precuenta confirmada en recepción.
    Esperado: la jaula J1 queda libre y se devuelve la mascota 1"""
    area.internar(1, "J1")
    area.firmar_alta_medica("J1", "Dra. Ruiz")
    area.confirmar_precuenta("J1", "Recepción turno noche")
    mascota = area.liberar("J1")
    resultado(f"mascota {mascota} egresada; libres {area.jaulas_libres}")
    assert mascota == 1 and area.jaulas_libres == ["J1", "J2"]


@pytest.mark.parametrize("firma", ["solo_medico", "solo_recepcion", "ninguna"])
def test_vc19_alta_con_una_sola_firma_no_libera(area, firma, resultado):
    """VC-19 (RN-06 límite): intento de alta con '{firma}'.
    Esperado: AltaIncompleta y la jaula sigue ocupada"""
    area.internar(1, "J1")
    if firma == "solo_medico":
        area.firmar_alta_medica("J1", "Dra. Ruiz")
    if firma == "solo_recepcion":
        area.confirmar_precuenta("J1", "Recepción")
    with pytest.raises(AltaIncompleta) as error:
        area.liberar("J1")
    resultado(f"AltaIncompleta: {error.value}")
    assert "J1" not in area.jaulas_libres


def test_vc20_operar_sobre_jaula_vacia_o_inexistente(area):
    """VC-20 (RN-06 error): firmar alta en una jaula vacía o que no existe.
    Esperado: ValueError"""
    with pytest.raises(ValueError):
        area.firmar_alta_medica("J2", "Dra. Ruiz")
    with pytest.raises(ValueError):
        area.confirmar_precuenta("J9", "Recepción")
