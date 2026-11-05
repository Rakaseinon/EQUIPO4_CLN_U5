"""API REST de TechStore (Actividad 4) ampliada en la Unidad 5.

Swagger: http://127.0.0.1:8000/docs
- Pedidos: las operaciones de la Actividad 4 (consultar, confirmar, enviar, cancelar...).
- Cobro: confirmar y cobrar con una pasarela SIMULADA (no se cobra dinero real).
- Pruebas: ejecuta pytest y muestra los resultados en lenguaje claro.

Cada respuesta tiene dos formatos:
- text/plain (por defecto): mensaje en español para cualquier persona.
- application/json: datos para otros sistemas (se pide con el encabezado Accept).
"""

import json
import subprocess
import sys
from decimal import Decimal
from enum import Enum
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, PlainTextResponse, RedirectResponse
from pydantic import BaseModel, Field
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from src.repository import Base, make_engine
from src.techstore.domain import (
    DomainException,
    InvalidOrderTransition,
    OrderStatus,
)
from src.techstore.fixtures import load_fixture
from src.techstore.service import (
    CheckoutService,
    PagoRechazado,
    PasarelaNoDisponible,
    importe_a_cobrar,
)
from src.techstore.specifications import discount_rate

RAIZ = Path(__file__).resolve().parent.parent
REPORTE_JSON = RAIZ / "reportes" / "resultados_pruebas.json"

DESCRIPCION = """
API de la tienda **TechStore** (Actividad 4) con las pruebas de la **Unidad 5**.

Las respuestas salen **en español y en lenguaje claro**. Si otro sistema necesita los datos
en JSON, elige `application/json` en el menú *Media type* de la respuesta.

* **Pedidos**: consultar, confirmar, enviar, cancelar, entregar y devolver.
* **Cobro simulado**: confirma y cobra con una pasarela FALSA (aprobado / rechazado / timeout).
* **Pruebas**: ejecuta todas las pruebas y responde con un resumen que cualquiera entiende.

Códigos: **200** correcto · **402** pago rechazado · **404** pedido inexistente ·
**409** operación no permitida en el estado actual · **422** datos inválidos ·
**503** servicio de pagos no disponible.
"""

app = FastAPI(title="TechStore U5 · Pruebas y Calidad", version="5.1", description=DESCRIPCION,
              swagger_ui_parameters={"syntaxHighlight": False})
orders = load_fixture()
# BD en memoria compartida por todas las peticiones (una sola conexión).
engine = make_engine("sqlite+pysqlite:///:memory:", poolclass=StaticPool,
                     connect_args={"check_same_thread": False})

ESTADOS = {
    OrderStatus.DRAFT: "Borrador (todavía no se confirma)",
    OrderStatus.CONFIRMED: "Confirmado",
    OrderStatus.SHIPPED: "Enviado",
    OrderStatus.DELIVERED: "Entregado",
    OrderStatus.CANCELLED: "Cancelado",
    OrderStatus.RETURNED: "Devuelto",
}
SIGUIENTE_PASO = {
    OrderStatus.DRAFT: "confirmarlo (o cobrarlo con el cobro simulado).",
    OrderStatus.CONFIRMED: "enviarlo con un número de guía, o cancelarlo indicando el motivo.",
    OrderStatus.SHIPPED: "marcarlo como entregado o como devuelto.",
    OrderStatus.DELIVERED: "ninguno; el pedido ya terminó su proceso.",
    OrderStatus.CANCELLED: "ninguno; el pedido fue cancelado.",
    OrderStatus.RETURNED: "ninguno; el pedido fue devuelto.",
}
EVENTOS = {
    "OrderConfirmed": "se confirmó",
    "OrderShipped": "se envió",
    "OrderDelivered": "se entregó",
    "OrderCancelled": "se canceló",
    "OrderReturned": "se devolvió",
}
MOTIVOS = {  # mensajes del dominio -> explicación para el cliente
    "Solo DRAFT puede confirmarse":
        "el pedido ya no está en borrador; solo un pedido nuevo se puede confirmar.",
    "Se requiere un número de guía válido": "falta el número de guía del envío.",
    "Solo pedidos CONFIRMED pueden enviarse": "solo se pueden enviar pedidos confirmados.",
    "Solo pedidos CONFIRMED pueden cancelarse":
        "solo se pueden cancelar pedidos confirmados que todavía no se envían.",
    "Se requiere un motivo de cancelación": "hay que escribir el motivo de la cancelación.",
    "Solo pedidos SHIPPED pueden entregarse":
        "solo se puede marcar como entregado un pedido que ya se envió.",
    "Solo pedidos SHIPPED pueden devolverse": "solo se puede devolver un pedido que ya se envió.",
}


# ------------------------------------------------------------------ respuestas legibles
class Problema(Exception):
    """Error de negocio con su explicación para personas y su versión para sistemas."""

    def __init__(self, status: int, texto: str, detalle: str):
        self.status, self.texto, self.detalle = status, texto, detalle


def _quiere_json(request: Request) -> bool:
    return "application/json" in request.headers.get("accept", "")


def responder(request: Request, texto: str, datos: dict, status: int = 200):
    if _quiere_json(request):
        return JSONResponse(datos, status_code=status)
    return PlainTextResponse(texto.strip() + "\n", status_code=status)


@app.exception_handler(Problema)
def _manejar_problema(request: Request, exc: Problema):
    return responder(request, exc.texto, {"detail": exc.detalle}, exc.status)


@app.exception_handler(RequestValidationError)
def _manejar_validacion(request: Request, exc: RequestValidationError):
    campos = ", ".join(str(e["loc"][-1]) for e in exc.errors()) or "desconocido"
    texto = (f"❌ Los datos enviados no son válidos.\n"
             f"Revisa este campo: {campos}.")
    return responder(request, texto, {"detail": exc.errors()}, 422)


def _dinero(valor) -> str:
    return f"${Decimal(valor):,.2f} MXN"


ERRORES = {
    402: "Pago rechazado por el banco (simulado)",
    404: "El pedido no existe",
    409: "La operación no se permite en el estado actual del pedido",
    422: "Datos inválidos o el pedido no cumple una regla",
    503: "El servicio de pagos no respondió",
}


def _formatos(ejemplo: str, errores=(404, 409, 422)) -> dict:
    """Documenta en Swagger los dos formatos de respuesta (texto primero) y los errores."""
    docs = {200: {"content": {"text/plain": {"example": ejemplo}, "application/json": {}}}}
    docs.update({c: {"description": ERRORES[c], "content": {"text/plain": {}}} for c in errores})
    return docs


def _motivo_descuento(order, tasa) -> str:
    if tasa == Decimal("0.10"):
        return "cliente VIP, compra mayor a $500 y al menos 4 unidades"
    if tasa == Decimal("0.05"):
        return "compra mayor a $5,000"
    if order.has_promotion:
        return "no aplica porque el pedido ya tiene una promoción activa"
    return "no aplica; no cumple las condiciones de descuento"


def _get_order_or_404(order_id: str):
    order = orders.get(order_id)
    if order is None:
        raise Problema(404, f"❌ No encontramos el pedido {order_id}.\n"
                            "Revisa que el número esté bien escrito (ejemplo: O001).",
                       f"El pedido {order_id} no existe")
    return order


def _explicar(order, exc: Exception) -> str:
    mensaje = str(exc)
    if mensaje == "Requiere artículos y cliente activo":
        if not order.items:
            return "el pedido no tiene artículos."
        return "el cliente está inactivo."
    return MOTIVOS.get(mensaje, mensaje)


def _run(order, accion: str, action):
    """Ejecuta una operación del dominio y traduce sus errores a mensajes claros (409 / 422)."""
    try:
        action()
    except DomainException as exc:
        status = 409 if isinstance(exc, InvalidOrderTransition) else 422
        texto = (f"❌ No se pudo {accion} el pedido {order.id}.\n"
                 f"Motivo: {_explicar(order, exc)}\n"
                 f"Estado actual del pedido: {ESTADOS[order.status]}.")
        raise Problema(status, texto, str(exc)) from exc


def _ok(request: Request, order, titulo: str, extra: str = ""):
    texto = (f"✅ {titulo}\n"
             f"Pedido: {order.id}\n"
             f"Estado actual: {ESTADOS[order.status]}\n"
             f"{extra}"
             f"Siguiente paso posible: {SIGUIENTE_PASO[order.status]}")
    datos = {"id": order.id, "status": order.status.value, "mensaje": titulo}
    return responder(request, texto, datos)


# ------------------------------------------------------------------ inicio
@app.get("/", include_in_schema=False)
def inicio():
    return RedirectResponse("/docs")


# ------------------------------------------------------------------ pedidos (Actividad 4)
EJEMPLO_PEDIDO = """PEDIDO O001
Cliente: C001
Estado: Borrador (todavía no se confirma)
Artículos: 4 unidades
Total: $2,100.00 MXN
Descuento: 10 % (cliente VIP, compra mayor a $500 y al menos 4 unidades)
Importe a cobrar: $1,890.00 MXN
Promoción activa: No
Historial: sin movimientos todavía"""


@app.get("/orders/{order_id}", tags=["Pedidos"], summary="Consultar un pedido",
         response_class=PlainTextResponse, responses=_formatos(EJEMPLO_PEDIDO, (404,)))
def get_order(order_id: str, request: Request):
    order = _get_order_or_404(order_id)
    tasa = discount_rate(order)
    importe = importe_a_cobrar(order)
    eventos = [EVENTOS.get(e.name, e.name) for e in order.events]
    historial = ", luego ".join(eventos).capitalize() if eventos else "sin movimientos todavía"
    texto = (f"PEDIDO {order.id}\n"
             f"Cliente: {order.customer.id}\n"
             f"Estado: {ESTADOS[order.status]}\n"
             f"Artículos: {order.units} unidades\n"
             f"Total: {_dinero(order.total.amount)}\n"
             f"Descuento: {int(tasa * 100)} % ({_motivo_descuento(order, tasa)})\n"
             f"Importe a cobrar: {_dinero(importe)}\n"
             f"Promoción activa: {'Sí' if order.has_promotion else 'No'}\n"
             f"Historial: {historial}")
    datos = {
        "id": order.id,
        "customer_id": order.customer.id,
        "status": order.status.value,
        "units": order.units,
        "total": str(order.total.amount),
        "discount_rate": str(tasa),
        "importe_a_cobrar": str(importe),
        "has_promotion": order.has_promotion,
        "events": [e.name for e in order.events],
        "explicacion": (f"Pedido de {order.units} unidades por ${order.total.amount} MXN; "
                        f"descuento aplicable {int(tasa * 100)} %."),
    }
    return responder(request, texto, datos)


EJEMPLO_ACCION = """✅ Pedido confirmado.
Pedido: O002
Estado actual: Confirmado
Siguiente paso posible: enviarlo con un número de guía, o cancelarlo indicando el motivo."""


class ShipPayload(BaseModel):
    tracking_number: str = Field(examples=["GUIA-12345"])


class CancelPayload(BaseModel):
    reason: str = Field(examples=["El cliente cambió de opinión"])


@app.post("/orders/{order_id}/confirm", tags=["Pedidos"], summary="Confirmar pedido",
          response_class=PlainTextResponse, responses=_formatos(EJEMPLO_ACCION))
def confirm_order(order_id: str, request: Request):
    order = _get_order_or_404(order_id)
    _run(order, "confirmar", order.confirm)
    return _ok(request, order, "Pedido confirmado.")


@app.post("/orders/{order_id}/ship", tags=["Pedidos"], summary="Enviar pedido (requiere guía)",
          response_class=PlainTextResponse, responses=_formatos(EJEMPLO_ACCION))
def ship_order(order_id: str, payload: ShipPayload, request: Request):
    order = _get_order_or_404(order_id)
    _run(order, "enviar", lambda: order.ship(payload.tracking_number))
    return _ok(request, order, "Pedido enviado.",
               f"Número de guía: {payload.tracking_number}\n")


@app.post("/orders/{order_id}/cancel", tags=["Pedidos"],
          summary="Cancelar pedido (requiere motivo)",
          response_class=PlainTextResponse, responses=_formatos(EJEMPLO_ACCION))
def cancel_order(order_id: str, payload: CancelPayload, request: Request):
    order = _get_order_or_404(order_id)
    _run(order, "cancelar", lambda: order.cancel(payload.reason))
    return _ok(request, order, "Pedido cancelado.", f"Motivo: {payload.reason}\n")


@app.post("/orders/{order_id}/deliver", tags=["Pedidos"], summary="Marcar como entregado",
          response_class=PlainTextResponse, responses=_formatos(EJEMPLO_ACCION))
def deliver_order(order_id: str, request: Request):
    order = _get_order_or_404(order_id)
    _run(order, "marcar como entregado", order.deliver)
    return _ok(request, order, "Pedido entregado al cliente.")


@app.post("/orders/{order_id}/return", tags=["Pedidos"], summary="Marcar como devuelto",
          response_class=PlainTextResponse, responses=_formatos(EJEMPLO_ACCION))
def return_order(order_id: str, request: Request):
    order = _get_order_or_404(order_id)
    _run(order, "devolver", order.return_order)
    return _ok(request, order, "Pedido devuelto.")


@app.post("/reiniciar", tags=["Pedidos"], summary="Volver a los datos iniciales",
          description="Recarga los 16 pedidos desde los CSV y borra los cobros guardados.",
          response_class=PlainTextResponse,
          responses=_formatos("✅ Datos reiniciados: 16 pedidos en Borrador y 0 cobros.", ()))
def reiniciar(request: Request):
    orders.clear()
    orders.update(load_fixture())
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    return responder(request,
                     f"✅ Datos reiniciados: {len(orders)} pedidos en Borrador y 0 cobros.",
                     {"pedidos": len(orders), "mensaje": "Datos reiniciados"})


# ------------------------------------------------------------------ cobro simulado (U5)
class RespuestaPasarela(str, Enum):
    aprobado = "aprobado"
    rechazado = "rechazado"
    timeout = "timeout"


class PasarelaSimulada:
    """Doble de prueba de la pasarela: responde lo que el usuario elige en Swagger."""

    def __init__(self, respuesta: RespuestaPasarela):
        self.respuesta = respuesta
        self.reembolsos = []

    def charge(self, order_id, amount):
        if self.respuesta == RespuestaPasarela.timeout:
            raise TimeoutError("sin respuesta")
        return self.respuesta == RespuestaPasarela.aprobado

    def refund(self, order_id, amount):
        self.reembolsos.append((order_id, amount))


EJEMPLO_COBRO = """✅ Pago aprobado.
Pedido O001 confirmado y guardado.
Total del pedido: $2,100.00 MXN
Descuento aplicado: 10 % (-$210.00 MXN)
Cobrado: $1,890.00 MXN
Nota: es un pago simulado; no se cobró dinero real."""


@app.post("/orders/{order_id}/checkout", tags=["Cobro simulado"],
          summary="Confirmar y cobrar con pasarela simulada",
          description="Elige cómo responde la pasarela falsa. No se transmite dinero real.",
          response_class=PlainTextResponse,
          responses=_formatos(EJEMPLO_COBRO, (402, 404, 409, 422, 503)))
def checkout(order_id: str, request: Request,
             pasarela: RespuestaPasarela = RespuestaPasarela.aprobado):
    order = _get_order_or_404(order_id)
    with Session(engine) as session:
        try:
            importe = CheckoutService(session, PasarelaSimulada(pasarela)).confirmar_y_cobrar(order)
        except PagoRechazado as exc:
            raise Problema(402, f"❌ El banco rechazó el pago.\n"
                                f"El pedido {order_id} NO se confirmó y sigue en "
                                f"{ESTADOS[order.status]}.\n"
                                "No se hizo ningún cargo.",
                           f"Pago rechazado: el pedido {order_id} sigue en "
                           f"{order.status.value} y no se guardó") from exc
        except PasarelaNoDisponible as exc:
            raise Problema(503, f"⚠️ El servicio de pagos no respondió.\n"
                                f"El pedido {order_id} sigue en {ESTADOS[order.status]}.\n"
                                "Intenta de nuevo en unos minutos.",
                           "La pasarela no respondió (timeout); intenta más tarde") from exc
        except IntegrityError as exc:
            raise Problema(409, f"❌ El pedido {order_id} ya estaba registrado como cobrado.\n"
                                "Se reembolsó el cargo para no cobrar dos veces.",
                           f"El pedido {order_id} ya existe en la base de datos") from exc
        except DomainException as exc:
            status = 409 if isinstance(exc, InvalidOrderTransition) else 422
            raise Problema(status, f"❌ No se pudo cobrar el pedido {order_id}.\n"
                                   f"Motivo: {_explicar(order, exc)}\n"
                                   "No se intentó ningún cargo.", str(exc)) from exc
    descuento = order.total.amount - importe
    tasa = int(discount_rate(order) * 100)
    texto = (f"✅ Pago aprobado.\n"
             f"Pedido {order.id} confirmado y guardado.\n"
             f"Total del pedido: {_dinero(order.total.amount)}\n"
             f"Descuento aplicado: {tasa} % (-{_dinero(descuento)})\n"
             f"Cobrado: {_dinero(importe)}\n"
             "Nota: es un pago simulado; no se cobró dinero real.")
    datos = {"id": order.id, "status": order.status.value,
             "mensaje": f"Pago aprobado por ${importe} MXN y pedido guardado",
             "cobrado": str(importe)}
    return responder(request, texto, datos)


# ------------------------------------------------------------------ pruebas (U5)
def _resumen_legible(datos: dict) -> dict:
    r = datos["resumen"]
    if r["fallaron"] == 0:
        conclusion = (f"Las {r['total']} pruebas pasaron: todas las reglas de negocio "
                      "verificadas funcionan como se esperaba.")
    else:
        conclusion = (f"{r['fallaron']} de {r['total']} pruebas FALLARON. Revisa la lista "
                      "'pruebas_con_falla' para ver qué regla no se cumple.")
    por_modulo: dict[str, dict] = {}
    for p in datos["pruebas"]:
        m = por_modulo.setdefault(p["modulo"], {"correctas": 0, "total": 0})
        m["total"] += 1
        m["correctas"] += p["estado"] == "PASÓ"
    return {
        "conclusion": conclusion,
        "fecha": r["fecha"],
        "total": r["total"], "pasaron": r["pasaron"], "fallaron": r["fallaron"],
        "por_modulo": [f"{'OK' if v['correctas'] == v['total'] else '!!'} {k}: "
                       f"{v['correctas']} de {v['total']} correctas"
                       for k, v in por_modulo.items()],
        "pruebas_con_falla": [
            f"{p['que_se_verifica']} | Esperado: {p['resultado_esperado']} | "
            f"Real: {p['resultado_real']}" for p in datos["pruebas"] if p["estado"] != "PASÓ"],
        "detalle": [f"[{p['estado']}] {p['que_se_verifica']}" for p in datos["pruebas"]],
    }


def _texto_resumen(resumen: dict) -> str:
    icono = "✅" if resumen["fallaron"] == 0 else "❌"
    lineas = [f"RESULTADO DE LAS PRUEBAS ({resumen['fecha']})",
              f"{icono} {resumen['conclusion']}",
              f"Total: {resumen['total']} · Pasaron: {resumen['pasaron']} · "
              f"Fallaron: {resumen['fallaron']}", "", "Por módulo:"]
    lineas += [f"  {m.replace('OK ', '✅ ', 1).replace('!! ', '❌ ', 1)}"
               for m in resumen["por_modulo"]]
    if resumen["pruebas_con_falla"]:
        lineas += ["", "Pruebas que fallaron:"]
        lineas += [f"  ❌ {p}" for p in resumen["pruebas_con_falla"]]
    lineas += ["", "Detalle de cada prueba:"] + [f"  {d}" for d in resumen["detalle"]]
    return "\n".join(lineas)


def _sin_reporte(mensaje_texto: str, mensaje_json: str, status: int):
    return Problema(status, mensaje_texto, mensaje_json)


EJEMPLO_PRUEBAS = """RESULTADO DE LAS PRUEBAS (2026-11-04 10:00)
✅ Las 130 pruebas pasaron: todas las reglas de negocio verificadas funcionan como se esperaba.
Total: 130 · Pasaron: 130 · Fallaron: 0

Por módulo:
  ✅ Reglas del pedido (pruebas unitarias del dominio): 11 de 11 correctas
  ..."""


@app.get("/pruebas/resultados", tags=["Pruebas"],
         summary="Ver el resultado de la última ejecución de pruebas",
         response_class=PlainTextResponse, responses=_formatos(EJEMPLO_PRUEBAS, ()))
def ultimos_resultados(request: Request):
    if not REPORTE_JSON.exists():
        raise _sin_reporte("⚠️ Aún no se han ejecutado las pruebas.\n"
                           "Usa POST /pruebas/ejecutar para correrlas.",
                           "Aún no se han ejecutado las pruebas. Usa POST /pruebas/ejecutar", 404)
    resumen = _resumen_legible(json.loads(REPORTE_JSON.read_text(encoding="utf-8")))
    return responder(request, _texto_resumen(resumen), resumen)


@app.post("/pruebas/ejecutar", tags=["Pruebas"],
          summary="Ejecutar todas las pruebas ahora y ver el resultado en español",
          description="Corre `pytest` sobre el proyecto (tarda unos segundos) y regresa un "
                      "resumen que cualquier persona puede leer.",
          response_class=PlainTextResponse, responses=_formatos(EJEMPLO_PRUEBAS, ()))
def ejecutar_pruebas(request: Request):
    proceso = subprocess.run([sys.executable, "-m", "pytest", "-p", "no:cacheprovider"],
                             check=False, cwd=RAIZ, capture_output=True, text=True, timeout=300)
    if not REPORTE_JSON.exists():
        raise _sin_reporte("❌ No se pudieron ejecutar las pruebas.\n" + proceso.stdout[-500:],
                           "pytest no generó el reporte: " + proceso.stdout[-500:], 500)
    resumen = _resumen_legible(json.loads(REPORTE_JSON.read_text(encoding="utf-8")))
    resumen["codigo_salida_pytest"] = proceso.returncode
    return responder(request, _texto_resumen(resumen), resumen)
