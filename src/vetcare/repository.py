"""Persistencia de aplicaciones de vacuna (VetCare) con SQLAlchemy."""

from sqlalchemy import Boolean, CheckConstraint, Column, Date, Integer, String, select

from src.repository import Base
from src.vetcare.domain import AplicacionVacuna


class AplicacionVacunaRow(Base):
    __tablename__ = "vet_aplicaciones_vacuna"
    __table_args__ = (
        # Respaldo de RN-03 en la base de datos: aunque alguien se salte el dominio,
        # no se puede guardar una vacuna sin lote ni fabricante.
        CheckConstraint("length(trim(lote)) > 0", name="ck_lote_obligatorio"),
        CheckConstraint("length(trim(fabricante)) > 0", name="ck_fabricante_obligatorio"),
    )
    id = Column(Integer, primary_key=True, autoincrement=True)
    mascota_id = Column(Integer, nullable=False)
    vacuna = Column(String, nullable=False)
    lote = Column(String, nullable=False)
    fabricante = Column(String, nullable=False)
    fecha = Column(Date, nullable=False)
    proximo_refuerzo = Column(Date, nullable=False)
    recordatorio_enviado = Column(Boolean, nullable=False, default=False)

    def __repr__(self) -> str:
        return (f"Vacuna(mascota={self.mascota_id}, {self.vacuna}, lote={self.lote}, "
                f"refuerzo={self.proximo_refuerzo})")


class SqlVacunaRepository:
    def __init__(self, session):
        self.session = session

    def agregar(self, aplicacion: AplicacionVacuna) -> AplicacionVacunaRow:
        fila = AplicacionVacunaRow(
            mascota_id=aplicacion.mascota_id, vacuna=aplicacion.vacuna,
            lote=aplicacion.lote, fabricante=aplicacion.fabricante, fecha=aplicacion.fecha,
            proximo_refuerzo=aplicacion.proximo_refuerzo, recordatorio_enviado=False)
        self.session.add(fila)
        return fila

    def de_mascota(self, mascota_id: int) -> list[AplicacionVacunaRow]:
        return list(self.session.scalars(
            select(AplicacionVacunaRow).where(AplicacionVacunaRow.mascota_id == mascota_id)))

    def sin_recordatorio(self) -> list[AplicacionVacunaRow]:
        return list(self.session.scalars(
            select(AplicacionVacunaRow).where(AplicacionVacunaRow.recordatorio_enviado.is_(False))))
