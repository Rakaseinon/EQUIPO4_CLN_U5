"""Carga los datos de TechStore (Actividad 4) desde datos/techstore/*.csv."""

import csv
from decimal import Decimal
from pathlib import Path

from src.techstore.domain import Customer, Money, Order, OrderItem

BASE = Path(__file__).resolve().parents[2] / "datos" / "techstore"


def rows(filename):
    with (BASE / filename).open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def load_fixture():
    clients = {
        x["cliente_id"]: Customer(x["cliente_id"], bool(int(x["es_vip"])), bool(int(x["activo"])))
        for x in rows("clientes.csv")
    }
    prices = {x["sku"]: Decimal(x["precio_mxn"]) for x in rows("productos.csv")}
    orders = {
        x["pedido_id"]: Order(customer=clients[x["cliente_id"]], id=x["pedido_id"],
                              has_promotion=bool(int(x["tiene_promocion"])))
        for x in rows("pedidos.csv")
    }
    for x in rows("detalle_pedidos.csv"):
        orders[x["pedido_id"]].add_item(
            OrderItem(x["sku"], int(x["cantidad"]), Money(prices[x["sku"]])))
    return orders
