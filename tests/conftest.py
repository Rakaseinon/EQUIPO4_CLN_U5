"""Plugin de pytest que traduce los resultados a lenguaje claro (español).

Cómo funciona:
- Cada prueba tiene un docstring. La primera línea dice QUÉ se verifica y una línea
  que empieza con "Esperado:" dice el resultado esperado. Los parámetros de las pruebas
  parametrizadas se pueden usar como {nombre} dentro del docstring.
- La fixture ``resultado`` permite que la prueba anote el resultado REAL obtenido.
- Al terminar se imprime un resumen legible y se generan en ``reportes/``:
  resultados_pruebas.csv, resultados_pruebas.md y resultados_pruebas.json
  (matriz de resultados reales vs esperados).
"""

from __future__ import annotations

import csv
import json
from datetime import datetime
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
CARPETA_REPORTES = RAIZ / "reportes"

ESTADOS = {
    "passed": "PASÓ",
    "failed": "FALLÓ",
    "skipped": "OMITIDA",
    "xfailed": "FALLA ESPERADA",
    "xpassed": "PASÓ (se esperaba falla)",
}

_registros: list[dict] = []
_items: dict[str, pytest.Item] = {}


def _formatear(texto: str, item: pytest.Item) -> str:
    params = getattr(getattr(item, "callspec", None), "params", {})
    try:
        return texto.format(**params)
    except (KeyError, IndexError, ValueError):
        return texto


def _describir(item: pytest.Item) -> tuple[str, str]:
    """Devuelve (descripción, resultado esperado) a partir del docstring de la prueba."""
    doc = (getattr(item, "function", None).__doc__ or "").strip()
    if not doc:
        return item.name.replace("_", " "), "-"
    lineas = [linea.strip() for linea in doc.splitlines() if linea.strip()]
    esperado = "-"
    descripcion = []
    for linea in lineas:
        if linea.lower().startswith("esperado:"):
            esperado = linea.split(":", 1)[1].strip()
        else:
            descripcion.append(linea)
    return _formatear(" ".join(descripcion), item), _formatear(esperado, item)


def _modulo(item: pytest.Item) -> str:
    doc = (item.module.__doc__ or "").strip()
    return doc.splitlines()[0] if doc else item.module.__name__


@pytest.fixture
def resultado(request):
    """Anota el resultado real que obtuvo la prueba: resultado("cobro $170.00")."""

    def anotar(texto, esperado=None, descripcion=None) -> None:
        props = request.node.user_properties
        props.append(("resultado_real", str(texto)))
        if esperado is not None:
            props.append(("resultado_esperado", str(esperado)))
        if descripcion is not None:
            props.append(("descripcion", str(descripcion)))

    return anotar


def pytest_collection_modifyitems(items):
    for item in items:
        _items[item.nodeid] = item


@pytest.hookimpl(trylast=True)
def pytest_configure(config):
    # En modo normal (sin -v) quitamos la ruta del archivo y los puntos "....";
    # en su lugar se imprimen líneas legibles. Con -v se ve la salida técnica de pytest.
    tr = config.pluginmanager.get_plugin("terminalreporter")
    if tr is not None and config.option.verbose <= 0:
        tr.showfspath = False
        if hasattr(tr, "_show_progress_info"):
            tr._show_progress_info = False


def pytest_report_teststatus(report, config):
    if config.option.verbose <= 0 and report.when == "call" and not hasattr(report, "wasxfail"):
        if report.passed:
            return "passed", "", "PASÓ"
        if report.failed:
            return "failed", "", "FALLÓ"
    return None


def pytest_runtest_logreport(report):
    item = _items.get(report.nodeid)
    if item is None:
        return
    terminado = report.when == "call" or (report.when == "setup" and not report.passed)
    if not terminado:
        return
    if hasattr(report, "wasxfail"):
        estado = "xfailed" if report.skipped else "xpassed"
    else:
        estado = report.outcome
    descripcion, esperado = _describir(item)
    props = dict(report.user_properties)
    descripcion = props.get("descripcion", descripcion)
    esperado = props.get("resultado_esperado", esperado)
    real = props.get("resultado_real")
    mensaje = ""
    if estado == "failed":
        crash = getattr(report.longrepr, "reprcrash", None)
        mensaje = (crash.message if crash else str(report.longrepr)).splitlines()[0][:160]
    if real is None:
        real = {"passed": "Igual al esperado", "failed": mensaje}.get(estado, "-")
    elif mensaje:
        real = f"{real}  ->  la verificación falló: {mensaje}"
    registro = {
        "n": len(_registros) + 1,
        "modulo": _modulo(item),
        "prueba": item.nodeid,
        "que_se_verifica": descripcion,
        "resultado_esperado": esperado,
        "resultado_real": real,
        "estado": ESTADOS.get(estado, estado.upper()),
        "duracion_ms": round(report.duration * 1000, 1),
    }
    _registros.append(registro)

    tr = item.config.pluginmanager.get_plugin("terminalreporter")
    if tr is None or item.config.option.verbose > 0:
        return
    if len(_registros) == 1 or _registros[-2]["modulo"] != registro["modulo"]:
        tr.write_line("")
        tr.write_line(f"  >> {registro['modulo']}", bold=True, cyan=True)
    color = {"passed": "green", "failed": "red"}.get(estado, "yellow")
    etiqueta = f"[{ESTADOS.get(estado, estado)}]".ljust(10)
    tr.write("     ")
    tr.write(etiqueta, **{color: True, "bold": True})
    tr.write_line(f" {descripcion}")
    if estado != "passed":
        tr.write_line(f"                Esperado: {esperado}")
        tr.write_line(f"                Real:     {real}")


def pytest_terminal_summary(terminalreporter, exitstatus, config):
    if not _registros:
        return
    tr = terminalreporter
    total = len(_registros)
    pasaron = sum(r["estado"] == "PASÓ" for r in _registros)
    fallaron = sum(r["estado"] == "FALLÓ" for r in _registros)

    tr.write_sep("=", "RESUMEN EN LENGUAJE CLARO")
    modulos: dict[str, list[dict]] = {}
    for r in _registros:
        modulos.setdefault(r["modulo"], []).append(r)
    for nombre, regs in modulos.items():
        ok = sum(r["estado"] == "PASÓ" for r in regs)
        marca = "OK " if ok == len(regs) else "!! "
        tr.write_line(f"  {marca} {nombre}: {ok} de {len(regs)} pruebas correctas")
    tr.write_line("")
    if fallaron == 0:
        tr.write_line(
            f"  CONCLUSIÓN: las {total} pruebas pasaron. Todas las reglas de negocio "
            "verificadas se comportan como se esperaba.", green=True, bold=True)
    else:
        tr.write_line(
            f"  CONCLUSIÓN: {fallaron} de {total} pruebas FALLARON. Revisa arriba qué regla "
            "no se cumple (Esperado vs Real).", red=True, bold=True)
    _guardar_reportes(total, pasaron, fallaron)
    tr.write_line(f"  Matriz de resultados guardada en: {CARPETA_REPORTES.name}/"
                  "resultados_pruebas.(csv|md|json)")


def _guardar_reportes(total: int, pasaron: int, fallaron: int) -> None:
    CARPETA_REPORTES.mkdir(exist_ok=True)
    campos = list(_registros[0].keys())
    with (CARPETA_REPORTES / "resultados_pruebas.csv").open(
            "w", newline="", encoding="utf-8-sig") as f:
        escritor = csv.DictWriter(f, fieldnames=campos)
        escritor.writeheader()
        escritor.writerows(_registros)

    fecha = datetime.now().strftime("%Y-%m-%d %H:%M")
    resumen = {"fecha": fecha, "total": total, "pasaron": pasaron, "fallaron": fallaron,
               "otras": total - pasaron - fallaron}
    (CARPETA_REPORTES / "resultados_pruebas.json").write_text(
        json.dumps({"resumen": resumen, "pruebas": _registros}, ensure_ascii=False, indent=2),
        encoding="utf-8")

    filas = ["| # | Módulo | Qué se verifica | Esperado | Real | Estado |",
             "|---|---|---|---|---|---|"]
    for r in _registros:
        celdas = [str(r["n"]), r["modulo"], r["que_se_verifica"], r["resultado_esperado"],
                  r["resultado_real"], r["estado"]]
        filas.append("| " + " | ".join(c.replace("|", "/") for c in celdas) + " |")
    md = (f"# Matriz de resultados de pruebas\n\nGenerada: {fecha}  \n"
          f"Total: {total} · Pasaron: {pasaron} · Fallaron: {fallaron}\n\n" + "\n".join(filas))
    (CARPETA_REPORTES / "resultados_pruebas.md").write_text(md + "\n", encoding="utf-8")
