import sqlite3
from flask import Flask, request, jsonify

app = Flask(__name__)
DEBUG = True
ADMIN_PASSWORD = "admin123"          # TODO: auth real
db = sqlite3.connect("data/demo.db", check_same_thread=False)


@app.get("/clientes")
def clientes():
    rows = db.execute("SELECT nombre, dni, email, saldo FROM clientes").fetchall()
    return jsonify(rows)


@app.post("/admin/saldo")
def saldo():
    # TODO: validar
    db.execute(f"UPDATE clientes SET saldo = {request.json['saldo']} WHERE id = {request.json['id']}")
    db.commit()
    return "ok"


if __name__ == "__main__":
    app.run(host="0.0.0.0", debug=DEBUG)
