"""Servicios de aplicación de VetCare: registrar vacunas y despachar recordatorios.

El notificador (WhatsApp / correo, US08) es un servicio externo: en las pruebas se
sustituye por un Mock, así que nunca se envían mensajes reales.
"""

from datetime import datetime

from src.vetcare.domain import AplicacionVacuna, toca_recordatorio
from src.vetcare.repository import SqlVacunaRepository


class ServicioVacunacion:
    def __init__(self, session):
        self.session = session
        self.repo = SqlVacunaRepository(session)

    def registrar(self, aplicacion: AplicacionVacuna):
        """RN-03 ya se validó al crear la AplicacionVacuna; aquí se guarda con commit."""
        self.repo.agregar(aplicacion)
        self.session.commit()
        return aplicacion.proximo_refuerzo


class ServicioRecordatorios:
    def __init__(self, session, notificador):
        self.session = session
        self.repo = SqlVacunaRepository(session)
        self.notificador = notificador

    def despachar(self, ahora: datetime) -> dict:
        """RF-05: avisa 48 h antes del refuerzo, una sola vez por aplicación."""
        enviados, fallidos = 0, 0
        for fila in self.repo.sin_recordatorio():
            if not toca_recordatorio(fila.proximo_refuerzo, ahora):
                continue
            mensaje = (f"VetCare 24: el refuerzo de {fila.vacuna} es el "
                       f"{fila.proximo_refuerzo:%d/%m/%Y}. Confirme o reagende su cita.")
            try:
                self.notificador.enviar(fila.mascota_id, mensaje)
            except Exception:  # noqa: BLE001 - si el proveedor falla se reintenta después
                fallidos += 1
                continue
            fila.recordatorio_enviado = True
            enviados += 1
        self.session.commit()
        return {"enviados": enviados, "fallidos": fallidos}
