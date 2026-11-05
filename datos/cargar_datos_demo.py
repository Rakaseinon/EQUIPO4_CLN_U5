"""Crea una base SQLite de demostración a partir de los CSV. No altera src/repository.py."""
import csv, sqlite3
from pathlib import Path
p=Path(__file__).resolve().parent
with sqlite3.connect(p/'pedidos_prueba.sqlite3') as db:
    db.execute('PRAGMA foreign_keys=ON')
    db.execute('DROP TABLE IF EXISTS orders')
    db.execute('DROP TABLE IF EXISTS customers')
    db.execute('CREATE TABLE customers (id INTEGER PRIMARY KEY, name TEXT, vip INTEGER, debt REAL)')
    db.execute('CREATE TABLE orders (id INTEGER PRIMARY KEY, customer_id INTEGER REFERENCES customers(id), total REAL, status TEXT)')
    with (p/'clientes_prueba.csv').open(encoding='utf-8-sig',newline='') as f:
        for row in csv.DictReader(f):
            db.execute('INSERT INTO customers VALUES (?,?,?,?)',(row['cliente_id'],row['nombre_ficticio'],row['es_vip'],row['deuda']))
    with (p/'pedidos_prueba.csv').open(encoding='utf-8-sig',newline='') as f:
        for row in csv.DictReader(f):
            db.execute('INSERT INTO orders VALUES (?,?,?,?)',(row['pedido_id'],row['cliente_id'],row['total'],row['estado_inicial']))
print('Base de demostración generada: pedidos_prueba.sqlite3')
