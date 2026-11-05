"""Genera datos/matriz_casos_vetcare.csv (Evidencia E9 · PIA VetCare 24) con el resultado
REAL de la última ejecución de pytest (reportes/resultados_pruebas.json).

Uso:  python -m pytest   y después   python scripts/generar_matriz_vetcare.py
"""
import csv
import json
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
U, INT = "tests/test_vetcare_reglas.py::", "tests/test_vetcare_integracion.py::"

CASOS = [
    # id, regla (BRD), entrada, resultado esperado, tipo, prueba (prefijo)
    ("VC-01", "RN-04 Bloqueo por alergia",
     "Firulais 12 kg, alérgico a Penicilina; receta Meloxicam 0.1/kg",
     "Se agrega; dosis 1.2", "Éxito", U + "test_vc01_"),
    ("VC-02", "RN-04 Bloqueo por alergia", "Receta con principio activo Penicilina",
     "AlergiaRegistrada; receta vacía", "Error", U + "test_vc02_"),
    ("VC-03", "RN-04 Bloqueo por alergia", "'PENICILINA', '  penicilina ', 'Penicilína'",
     "También se bloquea", "Límite", U + "test_vc03_"),
    ("VC-04", "RF-02 Peso para dosificar", "Paciente sin peso o con peso 0",
     "PesoRequerido", "Límite", U + "test_vc04_"),
    ("VC-05", "RN-04 Datos de receta", "Dosis 0 por kg; alergia vacía",
     "ValueError", "Error", U + "test_vc05_"),
    ("VC-06", "RN-03 / US07 Vacuna base", "Quíntuple Canina con lote, 04/11/2026",
     "Refuerzo 25/11/2026 (21 días)", "Éxito", U + "test_vc06_"),
    ("VC-07", "RF-04 Vacuna anual", "Antirrábica anual, 04/11/2026",
     "Refuerzo 04/11/2027 (365 días)", "Éxito", U + "test_vc07_"),
    ("VC-08", "RN-03 Lote obligatorio", "Lote vacío, fabricante vacío o lote '   '",
     "LoteObligatorio", "Error / Límite", U + "test_vc08_"),
    ("VC-09", "RF-04 Esquema de vacuna", "Esquema 'mensual'", "ValueError", "Error",
     U + "test_vc09_"),
    ("VC-10", "RF-05 Recordatorio 48 h", "Faltan 48, 47, 49 y 0 horas",
     "Sí, Sí, No, No", "Límite", U + "test_vc10_"),
    ("VC-11", "RN-01 Nota clínica", "Editar borrador y firmar con cédula",
     "Texto corregido y nota firmada", "Éxito", U + "test_vc11_"),
    ("VC-12", "RN-01 Inmutabilidad", "Editar, borrar o volver a firmar nota firmada",
     "NotaFirmada; texto intacto", "Error", U + "test_vc12_"),
    ("VC-13", "RN-01 / US13 Enmienda", "Enmienda con autor y motivo",
     "1 enmienda; original sin cambios", "Éxito", U + "test_vc13_"),
    ("VC-14", "RN-01 Enmienda", "Enmienda sin motivo, sin autor o motivo '   '",
     "EnmiendaInvalida", "Límite", U + "test_vc14_"),
    ("VC-15", "RN-01 Enmienda", "Enmendar nota sin firmar; firmar sin cédula",
     "EnmiendaInvalida y ValueError", "Límite", U + "test_vc15_"),
    ("VC-16", "US09 Ingreso a hospitalización", "Mascota 1 a jaula J1 libre",
     "J1 ocupada; libre J2", "Éxito", U + "test_vc16_"),
    ("VC-17", "US09 Ingreso a hospitalización", "Jaula ocupada / mascota ya internada / jaula J9",
     "JaulaOcupada / ValueError", "Error", U + "test_vc17_"),
    ("VC-18", "RN-06 Alta cruzada", "Alta médica + precuenta confirmada",
     "Jaula liberada", "Éxito", U + "test_vc18_"),
    ("VC-19", "RN-06 Alta cruzada", "Solo una firma o ninguna",
     "AltaIncompleta; jaula ocupada", "Límite", U + "test_vc19_"),
    ("VC-20", "RN-06 Alta cruzada", "Firmar alta en jaula vacía o inexistente",
     "ValueError", "Error", U + "test_vc20_"),
    ("VC-21", "Persistencia (RN-03)", "Registrar vacuna + commit",
     "Registro visible con lote y refuerzo", "Integración", INT + "test_vc21_"),
    ("VC-22", "Persistencia (RN-03)", "Agregar vacuna + rollback", "0 registros",
     "Integración", INT + "test_vc22_"),
    ("VC-23", "Persistencia (RN-03)", "INSERT directo sin lote/fabricante",
     "IntegrityError (CHECK)", "Integración", INT + "test_vc23_"),
    ("VC-24", "RF-05 / US08 Recordatorio", "Refuerzo a 48 h; correr proceso 2 veces",
     "1 mensaje, no se repite", "Mock", INT + "test_vc24_"),
    ("VC-25", "RF-05 / US08 Recordatorio", "Faltan 5 días", "No se envía", "Mock",
     INT + "test_vc25_"),
    ("VC-26", "RF-05 / US08 Recordatorio", "Proveedor en timeout y luego disponible",
     "1 fallido; se envía en la siguiente corrida", "Mock", INT + "test_vc26_"),
]


def main():
    datos = json.loads((RAIZ / "reportes" / "resultados_pruebas.json").read_text("utf-8"))
    salida = RAIZ / "datos" / "matriz_casos_vetcare.csv"
    with salida.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["ID", "Regla (BRD)", "Entrada", "Resultado esperado", "Tipo",
                    "Prueba pytest", "Resultado real", "Estado"])
        for cid, regla, entrada, esperado, tipo, prefijo in CASOS:
            pruebas = [p for p in datos["pruebas"] if p["prueba"].startswith(prefijo)]
            ok = sum(p["estado"] == "PASÓ" for p in pruebas)
            real = (pruebas[0]["resultado_real"] if len(pruebas) == 1
                    else f"{ok} de {len(pruebas)} variantes correctas")
            estado = "PASÓ" if pruebas and ok == len(pruebas) else "FALLÓ"
            w.writerow([cid, regla, entrada, esperado, tipo, prefijo.split("::")[1].rstrip("_"),
                        real, estado])
    print(f"Matriz generada: {salida.relative_to(RAIZ)} ({len(CASOS)} casos)")


if __name__ == "__main__":
    main()
