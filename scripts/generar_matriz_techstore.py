"""Genera datos/matriz_casos_techstore.csv (Evidencia E9) con el resultado REAL de la
última ejecución de pytest (reportes/resultados_pruebas.json).

Uso:  python -m pytest   y después   python scripts/generar_matriz_techstore.py
"""
import csv
import json
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
R, INT = "tests/test_techstore_reglas.py::", "tests/test_techstore_integracion.py::"

CASOS = [
    # id, regla, entrada, esperado, tipo, prueba
    ("TS-01", "R1 Máx. 20 unidades", "O008: 20 unidades, confirmar", "CONFIRMED", "Éxito",
     R + "test_r1_exito_20_unidades_exactas"),
    ("TS-02", "R1 Máx. 20 unidades", "O009: 19 unidades + 2", "OrderItemLimitExceeded; sigue 19",
     "Error", R + "test_r1_error_agregar_hasta_21_unidades"),
    ("TS-03", "R1 Máx. 20 unidades", "O009: 19 unidades + 1", "Aceptado; 20 unidades", "Límite",
     R + "test_r1_limite_19_mas_1_llega_a_20"),
    ("TS-04", "R2 Descuentos", "O001: VIP, $2100, 4 u., sin promo", "10 %", "Éxito",
     R + "test_r2_descuento_por_pedido[O001"),
    ("TS-05", "R2 Descuentos", "O006: $18000, sin promo", "5 %", "Éxito",
     R + "test_r2_descuento_por_pedido[O006"),
    ("TS-06", "R2 Descuentos", "O005: VIP con promoción activa", "0 %", "Error",
     R + "test_r2_descuento_por_pedido[O005"),
    ("TS-07", "R2 Descuentos", "O010: total exactamente $500", "0 % (umbral estricto)", "Límite",
     R + "test_r2_descuento_por_pedido[O010"),
    ("TS-08", "R2 Descuentos", "VIP $5500, 5 u. (cumple 10 % y 5 %)", "10 % (prioridad)",
     "Límite", R + "test_r2_limite_prioridad_10_sobre_5"),
    ("TS-09", "R3 Máquina de estados", "O016: confirmar, enviar, entregar",
     "DELIVERED + 3 eventos", "Éxito", R + "test_r3_exito_flujo_completo_hasta_entregado"),
    ("TS-10", "R3 Máquina de estados", "O014: cancelar estando SHIPPED",
     "InvalidOrderTransition; sigue SHIPPED", "Error", R + "test_r3_error_cancelar_pedido_enviado"),
    ("TS-11", "R3 Máquina de estados", "O013: confirmar dos veces",
     "2a rechazada; 1 solo evento", "Límite", R + "test_r3_limite_doble_confirmacion"),
    ("TS-12", "R3 Máquina de estados", "O003: cliente inactivo", "InvalidOrderData; DRAFT",
     "Error", R + "test_r3_no_se_confirma[O003"),
    ("TS-13", "Persistencia", "Guardar O001 + commit", "Registro visible, total $2100",
     "Integración", INT + "test_guardar_pedido_con_commit"),
    ("TS-14", "Persistencia", "Guardar O002 + rollback", "Registro ausente", "Integración",
     INT + "test_rollback_descarta_el_pedido"),
    ("TS-15", "Pasarela (mock)", "O001, pago aprobado", "charge(1890.00); CONFIRMED; guardado",
     "Mock", INT + "test_cobro_aprobado_aplica_descuento_y_guarda"),
    ("TS-16", "Pasarela (mock)", "O002, pago rechazado", "PagoRechazado; DRAFT; sin registro",
     "Mock", INT + "test_cobro_rechazado_no_confirma_ni_guarda"),
    ("TS-17", "Pasarela (mock)", "O006, pasarela en timeout", "PasarelaNoDisponible; DRAFT",
     "Mock", INT + "test_pasarela_timeout"),
]


def main():
    datos = json.loads((RAIZ / "reportes" / "resultados_pruebas.json").read_text("utf-8"))
    salida = RAIZ / "datos" / "matriz_casos_techstore.csv"
    with salida.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["ID", "Regla", "Entrada", "Resultado esperado", "Tipo", "Prueba pytest",
                    "Resultado real", "Estado"])
        for cid, regla, entrada, esperado, tipo, prueba in CASOS:
            p = next(x for x in datos["pruebas"] if x["prueba"].startswith(prueba))
            w.writerow([cid, regla, entrada, esperado, tipo, p["prueba"], p["resultado_real"],
                        p["estado"]])
    print(f"Matriz generada: {salida.relative_to(RAIZ)} ({len(CASOS)} casos)")


if __name__ == "__main__":
    main()
