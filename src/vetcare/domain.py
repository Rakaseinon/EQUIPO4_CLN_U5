"""Dominio de VetCare 24 (PIA · Equipo 4).

Reglas tomadas del BRD y las User Stories del caso:
- RN-04 / US06 / RF-02: no recetar un principio activo registrado como alergia; la dosis
  se calcula con el peso del paciente (peso indispensable para dosificar).
- RN-03 / RF-04 / US07: una vacuna no se guarda sin lote y fabricante; el refuerzo se
  calcula a 21 días (esquema base) o 365 días (anual).
- RF-05 / US08: el recordatorio se envía 48 horas antes del refuerzo.
- RN-01 / US05 / US13: una nota firmada es inmutable; solo admite notas de enmienda con
  autor, fecha y motivo.
- RN-06 / US09 / US11: la jaula se libera solo con alta médica del veterinario Y
  confirmación de precuenta en recepción.

Dominio puro: no importa SQLAlchemy ni servicios de mensajería.
"""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

DIAS_REFUERZO = {"base": 21, "anual": 365}        # BRD 3.1 y US07
ANTICIPACION_RECORDATORIO = timedelta(hours=48)    # RF-05 y US08


class ReglaVetCare(Exception):
    """Base de los errores de negocio de VetCare."""


class AlergiaRegistrada(ReglaVetCare):
    pass


class PesoRequerido(ReglaVetCare):
    pass


class LoteObligatorio(ReglaVetCare):
    pass


class NotaFirmada(ReglaVetCare):
    pass


class EnmiendaInvalida(ReglaVetCare):
    pass


class JaulaOcupada(ReglaVetCare):
    pass


class AltaIncompleta(ReglaVetCare):
    pass


def normalizar(texto: str) -> str:
    """'  PeniCilína ' -> 'penicilina' (sin acentos, minúsculas, sin espacios extra)."""
    sin_acentos = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    return " ".join(sin_acentos.lower().split())


# ============================ RN-04: prescripción segura ============================
@dataclass
class Mascota:
    id: int
    nombre: str
    peso_kg: float | None = None
    alergias: set[str] = field(default_factory=set)

    def registrar_alergia(self, principio_activo: str) -> None:
        if not principio_activo.strip():
            raise ValueError("la alergia debe indicar un principio activo")
        self.alergias.add(normalizar(principio_activo))

    def es_alergico_a(self, principio_activo: str) -> bool:
        return normalizar(principio_activo) in self.alergias


@dataclass(frozen=True)
class LineaReceta:
    farmaco: str
    principio_activo: str
    dosis_total: float


@dataclass
class Receta:
    mascota: Mascota
    lineas: list[LineaReceta] = field(default_factory=list)

    def agregar(self, farmaco: str, principio_activo: str, dosis_por_kg: float) -> LineaReceta:
        if self.mascota.peso_kg is None or self.mascota.peso_kg <= 0:
            raise PesoRequerido("registre el peso del paciente antes de dosificar")
        if dosis_por_kg <= 0:
            raise ValueError("la dosis por kilo debe ser positiva")
        if self.mascota.es_alergico_a(principio_activo):
            raise AlergiaRegistrada(
                f"{self.mascota.nombre} tiene alergia registrada a {principio_activo}")
        linea = LineaReceta(farmaco, principio_activo,
                            round(dosis_por_kg * self.mascota.peso_kg, 2))
        self.lineas.append(linea)
        return linea


# ======================== RN-03 / RF-04 / RF-05: vacunación ========================
@dataclass(frozen=True)
class AplicacionVacuna:
    mascota_id: int
    vacuna: str
    lote: str
    fabricante: str
    fecha: date
    esquema: str = "base"

    def __post_init__(self):
        if not self.lote.strip() or not self.fabricante.strip():
            raise LoteObligatorio("el lote y el fabricante son obligatorios")
        if self.esquema not in DIAS_REFUERZO:
            raise ValueError(f"esquema desconocido: {self.esquema}")

    @property
    def proximo_refuerzo(self) -> date:
        return self.fecha + timedelta(days=DIAS_REFUERZO[self.esquema])


def toca_recordatorio(refuerzo: date, ahora: datetime) -> bool:
    """RF-05: avisar cuando faltan 48 h o menos para el refuerzo (y aún no llega)."""
    inicio_refuerzo = datetime.combine(refuerzo, datetime.min.time())
    faltan = inicio_refuerzo - ahora
    return timedelta(0) < faltan <= ANTICIPACION_RECORDATORIO


# ============================ RN-01: expediente inmutable ============================
@dataclass(frozen=True)
class Enmienda:
    autor: str
    motivo: str
    texto: str
    fecha: datetime


@dataclass
class NotaClinica:
    mascota_id: int
    texto: str
    firmada_por: str | None = None
    cedula: str | None = None
    fecha_firma: datetime | None = None
    enmiendas: list[Enmienda] = field(default_factory=list)

    @property
    def firmada(self) -> bool:
        return self.firmada_por is not None

    def editar(self, nuevo_texto: str) -> None:
        if self.firmada:
            raise NotaFirmada("la nota está firmada; registre una nota de enmienda")
        self.texto = nuevo_texto

    def eliminar(self) -> None:
        if self.firmada:
            raise NotaFirmada("las notas firmadas no se pueden borrar")

    def firmar(self, medico: str, cedula: str, cuando: datetime) -> None:
        if self.firmada:
            raise NotaFirmada("la nota ya fue firmada")
        if not medico.strip() or not cedula.strip():
            raise ValueError("la firma requiere nombre y cédula del médico")
        self.firmada_por, self.cedula, self.fecha_firma = medico, cedula, cuando

    def agregar_enmienda(self, autor: str, motivo: str, texto: str,
                         cuando: datetime) -> Enmienda:
        if not self.firmada:
            raise EnmiendaInvalida("la nota aún no está firmada; puede editarse directamente")
        if not autor.strip() or not motivo.strip():
            raise EnmiendaInvalida("la enmienda requiere autor y motivo")
        enmienda = Enmienda(autor, motivo, texto, cuando)
        self.enmiendas.append(enmienda)
        return enmienda


# ======================== RN-06: hospitalización y alta cruzada ========================
@dataclass
class Internamiento:
    mascota_id: int
    alta_medica_por: str | None = None
    precuenta_por: str | None = None


@dataclass
class AreaHospitalizacion:
    jaulas: dict[str, Internamiento | None]

    @classmethod
    def con_jaulas(cls, *nombres: str) -> "AreaHospitalizacion":
        return cls({n: None for n in nombres})

    @property
    def jaulas_libres(self) -> list[str]:
        return [j for j, ocupante in self.jaulas.items() if ocupante is None]

    def _internamiento(self, jaula: str) -> Internamiento:
        if jaula not in self.jaulas:
            raise ValueError(f"la jaula {jaula} no existe")
        ocupante = self.jaulas[jaula]
        if ocupante is None:
            raise ValueError(f"la jaula {jaula} está vacía")
        return ocupante

    def internar(self, mascota_id: int, jaula: str) -> None:
        if jaula not in self.jaulas:
            raise ValueError(f"la jaula {jaula} no existe")
        if self.jaulas[jaula] is not None:
            raise JaulaOcupada(f"la jaula {jaula} está ocupada")
        if any(i and i.mascota_id == mascota_id for i in self.jaulas.values()):
            raise ValueError("la mascota ya está hospitalizada")
        self.jaulas[jaula] = Internamiento(mascota_id)

    def firmar_alta_medica(self, jaula: str, veterinario: str) -> None:
        self._internamiento(jaula).alta_medica_por = veterinario

    def confirmar_precuenta(self, jaula: str, recepcionista: str) -> None:
        self._internamiento(jaula).precuenta_por = recepcionista

    def liberar(self, jaula: str) -> int:
        internamiento = self._internamiento(jaula)
        faltan = []
        if not internamiento.alta_medica_por:
            faltan.append("alta médica del veterinario")
        if not internamiento.precuenta_por:
            faltan.append("confirmación de precuenta en recepción")
        if faltan:
            raise AltaIncompleta("falta: " + " y ".join(faltan))
        self.jaulas[jaula] = None
        return internamiento.mascota_id
