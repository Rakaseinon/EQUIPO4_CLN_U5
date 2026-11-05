# Unidad 5 CLN · Integración, Pruebas y Calidad — Equipo 4

Laboratorio guiado de la Unidad 5 de **Componentes de Lógica de Negocios** (FIME · UANL).
Parte del proyecto base `Proyecto_Python_Base_U5` (pedidos con descuento VIP), aplica lo
aprendido a la empresa del PIA, **VetCare 24** (paso 9 / E9), y como ampliación a **TechStore**,
el núcleo de negocio de la **Actividad 4**.

## Aplicación al PIA: VetCare 24 (E9)

| Regla | Fuente (BRD / US) | Código | Casos |
| --- | --- | --- | --- |
| Bloqueo por alergia registrada y peso para dosificar | RN-04, RF-02, US04, US06 | `Receta.agregar()` | VC-01 a VC-05 |
| Lote obligatorio, refuerzo 21/365 días y recordatorio 48 h | RN-03, RF-04, RF-05, US07, US08 | `AplicacionVacuna`, `ServicioRecordatorios` | VC-06 a VC-10, VC-21 a VC-26 |
| Nota clínica inmutable con enmiendas | RN-01, US05, US13 | `NotaClinica` | VC-11 a VC-15 |
| Alta hospitalaria con doble firma | RN-06, US09, US11 | `AreaHospitalizacion` | VC-16 a VC-20 |

Matriz: `datos/matriz_casos_vetcare.csv` (26 casos, se regenera con
`python scripts/generar_matriz_vetcare.py`). Cobertura de `src/vetcare`: 100 %.

* 185 pruebas automatizadas (unitarias, integración con BD, mocks, seguridad y API).
* Cobertura de `src/` ≈ 99 % (mínimo exigido: 80 %).
* **Salida legible en español**: cada prueba se muestra como una frase
  (`[PASÓ] Un cliente VIP con pedido de $200 paga $170 ...`) y al final aparece un
  *Resumen en lenguaje claro*.
* API con **Swagger** (`/docs`) que **responde en español y en lenguaje claro** (no en código):
  cada respuesta dice qué pasó, el estado del pedido y el siguiente paso. También puede
  **ejecutar las pruebas** y mostrar el resultado. Para otros sistemas, la misma respuesta está en
  JSON eligiendo `application/json` en *Media type* (encabezado `Accept`).
* Pipeline de GitHub Actions: Ruff → pytest + cobertura → build → resumen legible.

## Instalación

```powershell
# Windows PowerShell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

```bash
# macOS / Linux
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

## Comandos

| Qué quiero hacer | Comando |
| --- | --- |
| Correr las pruebas con salida legible | `python -m pytest` |
| Ver la salida técnica de pytest | `python -m pytest -v` |
| Solo un archivo | `python -m pytest tests/test_order.py` |
| Lint | `python -m ruff check src tests` |
| Cobertura (terminal + HTML) | `python -m pytest --cov=src --cov-report=term-missing --cov-report=html --cov-fail-under=80` |
| Abrir la cobertura | abrir `htmlcov/index.html` en el navegador |
| Levantar la API / Swagger | `python -m uvicorn src.api:app --reload` → http://127.0.0.1:8000/docs |
| Regenerar la matriz del PIA (VetCare) | `python scripts/generar_matriz_vetcare.py` |
| Regenerar la matriz de TechStore | `python scripts/generar_matriz_techstore.py` |

Cada ejecución de pytest genera la **matriz de resultados reales vs. esperados** en
`reportes/resultados_pruebas.csv`, `.md` y `.json`.

### Probar desde Swagger

1. `python -m uvicorn src.api:app --reload` y abrir http://127.0.0.1:8000/docs
2. Sección **Pruebas** → `POST /pruebas/ejecutar` → *Try it out* → *Execute*.
   La respuesta trae la `conclusion` en español, el resultado por módulo y el detalle de cada prueba.
3. `POST /reiniciar` regresa los 16 pedidos a su estado inicial sin apagar el servidor.
4. Sección **Cobro simulado** → `POST /orders/{order_id}/checkout` con `O001` y la pasarela en
   `aprobado`, `rechazado` o `timeout` (no se cobra dinero real).

## Arquitectura

```
Usuario / API (src/api.py, FastAPI + Swagger)
        │
Servicios de aplicación ── src/application.py (OrderService)
        │                  src/techstore/service.py (CheckoutService)
        ▼
Dominio (sin dependencias de infraestructura)
   src/domain.py · src/security.py · src/techstore/domain.py · src/techstore/specifications.py
        │ puertos
        ▼
Adaptadores: SQLAlchemy (src/repository.py, src/techstore/repository.py) · Pasarela de pago (mock)
```

## Tipos de prueba

| Nivel | Qué interviene | Archivos | Pruebas |
| --- | --- | --- | --- |
| Unitaria | Solo reglas del dominio | `test_order.py`, `test_security.py`, `test_vetcare_reglas.py`, `test_techstore_reglas.py`, CP01–CP12 de `test_casos_csv.py` | 114 |
| Integración | SQLAlchemy/SQLite en memoria o servicio externo simulado con mock | `test_repository.py`, `test_service.py`, `test_vetcare_integracion.py`, `test_techstore_integracion.py`, CP13–CP15 | 36 |
| API (cercana a E2E) | Peticiones HTTP con `TestClient` | `test_api.py` | 35 |
| E2E | Navegador real + interfaz + BD + sandbox de pagos | No implementada (el proyecto no tiene interfaz); escenario propuesto en el reporte | 0 |

## Estructura

```
src/
  domain.py, application.py, repository.py, security.py   proyecto base U5 (modificado con TDD)
  vetcare/          PIA VetCare 24: reglas del BRD, repositorio de vacunas y recordatorios
  techstore/        dominio de la Actividad 4 + repositorio SQLAlchemy + servicio de cobro
  api.py            API REST + Swagger + endpoints de pruebas
tests/
  conftest.py       plugin que traduce los resultados a lenguaje claro y genera la matriz
  test_order.py, test_repository.py, test_service.py, test_security.py   pasos 2 a 6
  test_casos_csv.py           CP01–CP15 leídos de datos/casos_de_prueba.csv
  test_techstore_reglas.py    R1 unidades, R2 descuentos, R3 estados + escenarios E01–E15
  test_techstore_integracion.py  persistencia y pasarela (mock) de TechStore
  test_api.py                 API y Swagger (TestClient)
datos/              CSV del laboratorio, CSV de TechStore y matriz_casos_techstore.csv
evidencias/         salidas de terminal y capturas E1–E9
.github/workflows/ci.yml
```

## Cambios hechos al proyecto base (y por qué)

1. **TDD – no confirmar dos veces** (`src/domain.py`): RED → GREEN → REFACTOR. El caso CP08 del
   CSV cambia de `CONFIRMED` a `ValueError` a propósito.
2. **Consistencia del cobro** (`src/application.py`): antes el pedido quedaba `CONFIRMED` aunque
   el pago fuera rechazado. Ahora se valida, se cobra y **solo con pago aprobado** se confirma.
   También se maneja el *timeout* de la pasarela (`PaymentUnavailable`).
3. `SqlOrderRepository.get()` para consultar pedidos en las pruebas de integración.

**Importante:** la regla de cancelación impide cancelar pedidos enviados incluso al
administrador. Los datos son ficticios. El pipeline verifica build (`compileall`), no despliega.
