"""API REST de TechStore con Swagger (pruebas de punta a punta con TestClient)"""

import json
import subprocess
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from src import api
from src.techstore.fixtures import load_fixture

# Sistemas: piden JSON. Personas (Swagger, navegador): reciben texto legible.
client = TestClient(api.app, headers={"accept": "application/json"})
texto = TestClient(api.app)


@pytest.fixture(autouse=True)
def datos_limpios():
    """Antes de cada prueba se reinician pedidos y cobros, así las pruebas son independientes."""
    client.post("/reiniciar")


def test_inicio_redirige_a_swagger():
    """Abrir la raíz de la API lleva directo a la documentación Swagger.
    Esperado: redirección a /docs"""
    r = client.get("/", follow_redirects=False)
    assert r.status_code in (302, 307) and r.headers["location"] == "/docs"


def test_swagger_y_openapi_disponibles(resultado):
    """La documentación Swagger (/docs) y el contrato OpenAPI se publican.
    Esperado: 200 y aparecen las rutas de pedidos, cobro y pruebas"""
    assert client.get("/docs").status_code == 200
    rutas = client.get("/openapi.json").json()["paths"]
    resultado(f"{len(rutas)} rutas documentadas")
    assert {"/orders/{order_id}", "/orders/{order_id}/checkout", "/pruebas/ejecutar"} <= set(rutas)


def test_consultar_pedido(resultado):
    """GET /orders/O001 regresa el pedido con su descuento y una explicación en español.
    Esperado: 200, DRAFT, total 2100.00, descuento 0.10"""
    r = client.get("/orders/O001")
    body = r.json()
    resultado(f"{r.status_code}: {body['explicacion']}")
    assert r.status_code == 200
    assert (body["status"], body["total"], body["discount_rate"]) == ("DRAFT", "2100.00", "0.10")


@pytest.mark.parametrize("metodo,ruta", [("get", "/orders/NOPE"),
                                         ("post", "/orders/NOPE/confirm")])
def test_pedido_inexistente_404(metodo, ruta):
    """Un pedido que no existe responde 404 ({ruta}).
    Esperado: 404"""
    assert getattr(client, metodo)(ruta).status_code == 404


def test_confirmar_y_doble_confirmacion_409():
    """Confirmar O002 funciona; confirmarlo otra vez es un conflicto.
    Esperado: 200 y luego 409"""
    assert client.post("/orders/O002/confirm").status_code == 200
    assert client.post("/orders/O002/confirm").status_code == 409


@pytest.mark.parametrize("pedido", ["O003", "O007"])
def test_confirmar_invalido_422(pedido):
    """Confirmar {pedido} (cliente inactivo o sin artículos) son datos inválidos.
    Esperado: 422"""
    assert client.post(f"/orders/{pedido}/confirm").status_code == 422


def test_flujo_completo_y_reglas_de_envio():
    """Flujo O016 hasta DELIVERED; envío sin guía da 422; cancelar O014 enviado da 409.
    Esperado: DELIVERED, 422 y 409"""
    client.post("/orders/O016/confirm")
    client.post("/orders/O016/ship", json={"tracking_number": "G1"})
    assert client.post("/orders/O016/deliver").json()["status"] == "DELIVERED"

    client.post("/orders/O012/confirm")
    assert client.post("/orders/O012/ship", json={"tracking_number": " "}).status_code == 422

    client.post("/orders/O014/confirm")
    client.post("/orders/O014/ship", json={"tracking_number": "G1"})
    assert client.post("/orders/O014/cancel", json={"reason": "x"}).status_code == 409


def test_cancelar_y_devolver():
    """O002 se cancela con motivo; O015 se devuelve desde SHIPPED.
    Esperado: CANCELLED y RETURNED"""
    client.post("/orders/O002/confirm")
    assert client.post("/orders/O002/cancel", json={"reason": "cambio"}).json()["status"] \
        == "CANCELLED"
    client.post("/orders/O015/confirm")
    client.post("/orders/O015/ship", json={"tracking_number": "G1"})
    assert client.post("/orders/O015/return").json()["status"] == "RETURNED"


@pytest.mark.parametrize("pedido,pasarela,codigo", [
    ("O001", "aprobado", 200), ("O002", "rechazado", 402), ("O006", "timeout", 503),
    ("O007", "aprobado", 422)])
def test_checkout_con_pasarela_simulada(pedido, pasarela, codigo, resultado):
    """Swagger: cobrar {pedido} con la pasarela simulada respondiendo '{pasarela}'.
    Esperado: HTTP {codigo}"""
    r = client.post(f"/orders/{pedido}/checkout", params={"pasarela": pasarela})
    resultado(f"HTTP {r.status_code}: {r.json().get('mensaje') or r.json().get('detail')}")
    assert r.status_code == codigo


def test_checkout_de_pedido_ya_confirmado_409():
    """Cobrar un pedido que ya está confirmado es un conflicto.
    Esperado: 409"""
    client.post("/orders/O013/confirm")
    assert client.post("/orders/O013/checkout").status_code == 409


# ---------------- Endpoints de pruebas (texto legible en Swagger) ----------------

REPORTE = {"resumen": {"fecha": "2026-11-04 10:00", "total": 2, "pasaron": 1, "fallaron": 1},
           "pruebas": [
               {"modulo": "Demo", "que_se_verifica": "Regla A", "resultado_esperado": "ok",
                "resultado_real": "ok", "estado": "PASÓ"},
               {"modulo": "Demo", "que_se_verifica": "Regla B", "resultado_esperado": "10",
                "resultado_real": "5", "estado": "FALLÓ"}]}


def test_resultados_sin_ejecucion_previa(tmp_path, monkeypatch):
    """Si nunca se han corrido las pruebas, la API lo explica en español.
    Esperado: 404 con instrucción de usar POST /pruebas/ejecutar"""
    monkeypatch.setattr(api, "REPORTE_JSON", tmp_path / "no_existe.json")
    r = client.get("/pruebas/resultados")
    assert r.status_code == 404 and "/pruebas/ejecutar" in r.json()["detail"]


def test_resultados_legibles(tmp_path, monkeypatch, resultado):
    """GET /pruebas/resultados traduce el reporte a frases que cualquiera entiende.
    Esperado: conclusión con '1 de 2 pruebas FALLARON' y detalle Esperado/Real"""
    archivo = tmp_path / "r.json"
    archivo.write_text(json.dumps(REPORTE), encoding="utf-8")
    monkeypatch.setattr(api, "REPORTE_JSON", archivo)
    body = client.get("/pruebas/resultados").json()
    resultado(body["conclusion"])
    assert "1 de 2 pruebas FALLARON" in body["conclusion"]
    assert body["pruebas_con_falla"] == ["Regla B | Esperado: 10 | Real: 5"]


def test_ejecutar_pruebas_desde_swagger(tmp_path, monkeypatch, resultado):
    """POST /pruebas/ejecutar corre pytest y responde el resumen (aquí pytest se simula).
    Esperado: conclusión 'Las 1 pruebas pasaron' y código de salida 0"""
    archivo = tmp_path / "r.json"
    ok = {"resumen": {**REPORTE["resumen"], "total": 1, "pasaron": 1, "fallaron": 0},
          "pruebas": REPORTE["pruebas"][:1]}

    def pytest_falso(*args, **kwargs):
        archivo.write_text(json.dumps(ok), encoding="utf-8")
        return SimpleNamespace(returncode=0, stdout="")

    monkeypatch.setattr(api, "REPORTE_JSON", archivo)
    monkeypatch.setattr(subprocess, "run", pytest_falso)
    body = client.post("/pruebas/ejecutar").json()
    resultado(body["conclusion"])
    assert body["conclusion"].startswith("Las 1 pruebas pasaron")
    assert body["codigo_salida_pytest"] == 0


def test_ejecutar_pruebas_sin_reporte(tmp_path, monkeypatch):
    """Si pytest no logra generar el reporte, la API lo informa.
    Esperado: 500"""
    monkeypatch.setattr(api, "REPORTE_JSON", tmp_path / "nada.json")
    monkeypatch.setattr(subprocess, "run",
                        lambda *a, **k: SimpleNamespace(returncode=4, stdout="error"))
    assert client.post("/pruebas/ejecutar").status_code == 500


# ---------------- Respuestas en texto legible (lo que ve una persona en Swagger) ----------------

def test_texto_consultar_pedido(resultado):
    """Swagger muestra el pedido O001 como texto en español, no como código.
    Esperado: texto con estado Borrador, total $2,100.00 y descuento 10 %"""
    r = texto.get("/orders/O001")
    resultado(r.text.splitlines()[0] + " ... " + r.text.splitlines()[5])
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/plain")
    assert "Estado: Borrador" in r.text
    assert "Total: $2,100.00 MXN" in r.text
    assert "Descuento: 10 % (cliente VIP" in r.text


def test_texto_confirmar_y_explicar_conflicto(resultado):
    """Confirmar dos veces da un mensaje claro con el motivo y el estado actual.
    Esperado: 200 '✅ Pedido confirmado.' y luego 409 con 'Motivo:'"""
    assert texto.post("/orders/O002/confirm").text.startswith("✅ Pedido confirmado.")
    r = texto.post("/orders/O002/confirm")
    resultado(r.text.replace("\n", " | ").strip())
    assert r.status_code == 409
    assert "Motivo: el pedido ya no está en borrador" in r.text
    assert "Estado actual del pedido: Confirmado" in r.text


@pytest.mark.parametrize("pedido,motivo", [("O003", "el cliente está inactivo"),
                                           ("O007", "el pedido no tiene artículos")])
def test_texto_motivo_especifico(pedido, motivo):
    """Al confirmar {pedido} el mensaje dice exactamente por qué no se puede.
    Esperado: 422 con 'Motivo: {motivo}'"""
    r = texto.post(f"/orders/{pedido}/confirm")
    assert r.status_code == 422 and f"Motivo: {motivo}" in r.text


def test_texto_flujo_y_pedido_inexistente():
    """Enviar, entregar y un pedido inexistente también responden con frases claras.
    Esperado: guía en el mensaje, 'Entregado' y 404 'No encontramos el pedido'"""
    texto.post("/orders/O016/confirm")
    enviado = texto.post("/orders/O016/ship", json={"tracking_number": "GUIA-1"}).text
    assert "Número de guía: GUIA-1" in enviado
    assert "Estado actual: Entregado" in texto.post("/orders/O016/deliver").text
    r = texto.get("/orders/O999")
    assert r.status_code == 404 and "No encontramos el pedido O999" in r.text
    historial = texto.get("/orders/O016").text
    assert "Historial: Se confirmó, luego se envió, luego se entregó" in historial


def test_texto_datos_invalidos():
    """Si falta un dato obligatorio (la guía), se indica qué campo revisar.
    Esperado: 422 'Revisa este campo: tracking_number'"""
    r = texto.post("/orders/O002/ship", json={})
    assert r.status_code == 422 and "Revisa este campo: tracking_number" in r.text


@pytest.mark.parametrize("pedido,pasarela,frase", [
    ("O001", "aprobado", "Cobrado: $1,890.00 MXN"),
    ("O002", "rechazado", "El banco rechazó el pago"),
    ("O006", "timeout", "El servicio de pagos no respondió"),
    ("O007", "aprobado", "No se intentó ningún cargo")])
def test_texto_cobro(pedido, pasarela, frase, resultado):
    """Cobro de {pedido} con pasarela '{pasarela}' explicado en español.
    Esperado: el mensaje incluye '{frase}'"""
    r = texto.post(f"/orders/{pedido}/checkout", params={"pasarela": pasarela})
    resultado(r.text.splitlines()[0])
    assert frase in r.text


def test_texto_resultados_de_pruebas(tmp_path, monkeypatch):
    """El resumen de pruebas también sale como texto con íconos y fallas explicadas.
    Esperado: '❌ 1 de 2 pruebas FALLARON' y la regla B con Esperado/Real"""
    archivo = tmp_path / "r.json"
    archivo.write_text(json.dumps(REPORTE), encoding="utf-8")
    monkeypatch.setattr(api, "REPORTE_JSON", archivo)
    r = texto.get("/pruebas/resultados").text
    assert "❌ 1 de 2 pruebas FALLARON" in r
    assert "❌ Regla B | Esperado: 10 | Real: 5" in r
    monkeypatch.setattr(api, "REPORTE_JSON", tmp_path / "no.json")
    assert "Aún no se han ejecutado" in texto.get("/pruebas/resultados").text


def test_reiniciar_datos(resultado):
    """POST /reiniciar devuelve los pedidos a su estado inicial sin apagar el servidor.
    Esperado: O002 vuelve a Borrador después de confirmarlo"""
    texto.post("/orders/O002/confirm")
    mensaje = texto.post("/reiniciar").text.strip()
    resultado(mensaje)
    assert mensaje.startswith("✅ Datos reiniciados: 16 pedidos")
    assert "Estado: Borrador" in texto.get("/orders/O002").text


def test_cobro_duplicado_en_bd_se_explica():
    """Si el pedido ya estaba guardado como cobrado, se explica y se reembolsa (no error 500).
    Esperado: 409 'ya estaba registrado como cobrado'"""
    texto.post("/orders/O001/checkout")
    api.orders.update(load_fixture())  # vuelve a DRAFT; la BD conserva el cobro
    r = texto.post("/orders/O001/checkout")
    assert r.status_code == 409 and "ya estaba registrado como cobrado" in r.text


@pytest.mark.parametrize("pedido,motivo", [
    ("O006", "Descuento: 5 % (compra mayor a $5,000)"),
    ("O005", "Descuento: 0 % (no aplica porque el pedido ya tiene una promoción activa)"),
    ("O002", "Descuento: 0 % (no aplica; no cumple las condiciones de descuento)")])
def test_texto_motivo_del_descuento(pedido, motivo):
    """El cliente lee por qué su pedido {pedido} tiene (o no) descuento.
    Esperado: '{motivo}'"""
    assert motivo in texto.get(f"/orders/{pedido}").text
