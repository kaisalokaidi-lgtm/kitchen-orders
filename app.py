
from flask import Flask, render_template, request, jsonify
import csv
import os
from datetime import datetime

app = Flask(__name__)

CSV_FILE = "orders.csv"
FIELDNAMES = ["id", "name", "cheese", "status", "timestamp"]

if not os.path.exists(CSV_FILE):
    with open(CSV_FILE, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()

def read_orders():
    with open(CSV_FILE, newline="") as f:
        return list(csv.DictReader(f))

def write_orders(orders):
    with open(CSV_FILE, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(orders)

@app.route("/")
def order_page():
    return render_template("order.html")

@app.route("/kitchen")
def kitchen_page():
    return render_template("kitchen.html")

@app.route("/api/orders", methods=["GET"])
def get_orders():
    return jsonify(read_orders())

@app.route("/api/orders", methods=["POST"])
def add_order():
    data = request.json
    orders = read_orders()
    order_id = len(orders) + 1
    orders.append({
        "id": order_id,
        "name": data["name"],
        "cheese": data["cheese"],
        "status": "pending",
        "timestamp": datetime.now().isoformat()
    })
    write_orders(orders)
    return {"success": True}

@app.route("/api/orders/<int:order_id>/ready", methods=["POST"])
def mark_ready(order_id):
    orders = read_orders()
    for order in orders:
        if int(order["id"]) == order_id:
            order["status"] = "ready"
    write_orders(orders)
    return {"success": True}

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
