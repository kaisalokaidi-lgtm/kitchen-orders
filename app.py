from flask import Flask, render_template, request, jsonify, session, redirect, url_for
from functools import wraps
import csv
import os
from datetime import datetime

app = Flask(__name__)
app.secret_key = "burger-order-secret-key-change-this-in-production"

CSV_FILE = "orders.csv"
PROGRESS_FILE = "order_progress.csv"
INGREDIENTS_FILE = "ingredients.csv"
USERS_FILE = "users.csv"

# Initialize CSV files
if not os.path.exists(USERS_FILE):
    with open(USERS_FILE, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["id", "username", "password", "role", "name"])
        writer.writeheader()
        # Add default admin
        writer.writerow({"id": "1", "username": "admin", "password": "admin123", "role": "admin", "name": "Administrator"})

if not os.path.exists(INGREDIENTS_FILE):
    with open(INGREDIENTS_FILE, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["id", "name", "category", "emoji"])
        writer.writeheader()
        # Add default ingredients
        default_ingredients = [
            {"id": "1", "name": "Tomatoes", "category": "salads", "emoji": "🍅"},
            {"id": "2", "name": "Saute onions", "category": "salads", "emoji": "🧅"},
            {"id": "3", "name": "Gherkins", "category": "salads", "emoji": "🥒"},
            {"id": "4", "name": "Jalapeno", "category": "salads", "emoji": "🌶️"},
            {"id": "5", "name": "Cheese", "category": "salads", "emoji": "🧀"},
            {"id": "6", "name": "Lettuce", "category": "salads", "emoji": "🥬"},
            {"id": "7", "name": "Chefs special", "category": "salads", "emoji": "👨‍🍳"},
            {"id": "8", "name": "Peri peri lemon and herb", "category": "sauces", "emoji": "🍋🌿"},
            {"id": "9", "name": "Burger sauce", "category": "sauces", "emoji": "🥫"},
            {"id": "10", "name": "Ketchup", "category": "sauces", "emoji": "🍅"},
            {"id": "11", "name": "BBQ", "category": "sauces", "emoji": "🔥"},
            {"id": "12", "name": "Mayo", "category": "sauces", "emoji": "🧴"},
            {"id": "13", "name": "Peri peri medium", "category": "sauces", "emoji": "🌶️"},
            {"id": "14", "name": "Water", "category": "drinks", "emoji": "💧"},
            {"id": "15", "name": "Coke", "category": "drinks", "emoji": "🥤"},
            {"id": "16", "name": "Tropicana", "category": "drinks", "emoji": "🍊"},
        ]
        writer.writerows(default_ingredients)

# Read ingredients to build OPTIONS dynamically
def read_ingredients():
    if not os.path.exists(INGREDIENTS_FILE):
        return []
    with open(INGREDIENTS_FILE, newline="") as f:
        return list(csv.DictReader(f))

def write_ingredients(ingredients):
    with open(INGREDIENTS_FILE, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["id", "name", "category", "emoji"])
        writer.writeheader()
        writer.writerows(ingredients)

def read_users():
    if not os.path.exists(USERS_FILE):
        return []
    with open(USERS_FILE, newline="") as f:
        return list(csv.DictReader(f))

def write_users(users):
    with open(USERS_FILE, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["id", "username", "password", "role", "name"])
        writer.writeheader()
        writer.writerows(users)

# Login decorators
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login'))
        users = read_users()
        user = next((u for u in users if u['id'] == session['user_id']), None)
        if not user or user['role'] != 'admin':
            return redirect(url_for('order_page'))
        return f(*args, **kwargs)
    return decorated_function

# Build OPTIONS from ingredients
def get_option_keys():
    ingredients = read_ingredients()
    return [ing["name"].lower().replace(" ", "_") for ing in ingredients]

OPTIONS = get_option_keys()
FIELDNAMES = ["id", "name"] + OPTIONS + ["status", "timestamp"]

if not os.path.exists(CSV_FILE):
    with open(CSV_FILE, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()

if not os.path.exists(PROGRESS_FILE):
    with open(PROGRESS_FILE, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["order_id", "ingredient", "checked"])
        writer.writeheader()

def read_orders():
    if not os.path.exists(CSV_FILE):
        return []
    with open(CSV_FILE, newline="") as f:
        return list(csv.DictReader(f))

def write_orders(orders):
    # Dynamically build fieldnames from current ingredients
    current_fieldnames = ["id", "name"] + get_option_keys() + ["status", "timestamp"]
    with open(CSV_FILE, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=current_fieldnames)
        writer.writeheader()
        writer.writerows(orders)

def read_progress():
    if not os.path.exists(PROGRESS_FILE):
        return []
    with open(PROGRESS_FILE, newline="") as f:
        return list(csv.DictReader(f))

def write_progress(progress):
    with open(PROGRESS_FILE, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["order_id", "ingredient", "checked"])
        writer.writeheader()
        writer.writerows(progress)

@app.route("/")
@login_required
def order_page():
    users = read_users()
    user = next((u for u in users if u['id'] == session['user_id']), None)
    return render_template("order.html", user=user)

@app.route("/login")
def login():
    return render_template("login.html")

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.route("/admin")
@admin_required
def admin_page():
    return render_template("admin.html")

@app.route("/kitchen")
@admin_required
def kitchen_page():
    return render_template("kitchen.html")

@app.route("/api/orders", methods=["GET"])
def get_orders():
    return jsonify(read_orders())

@app.route("/api/orders", methods=["POST"])
def add_order():
    data = request.json
    orders = read_orders()
    
    # Get next order ID
    if orders:
        order_id = max([int(o.get('id', 0)) for o in orders]) + 1
    else:
        order_id = 1
    
    # Rebuild OPTIONS from current ingredients
    current_options = get_option_keys()
    # set each option to "True"/"False" string for CSV consistency
    opts = {opt: str(bool(data.get(opt, False))) for opt in current_options}
    order = {
        "id": str(order_id),
        "name": data["name"],
        **opts,
        "status": "pending",
        "timestamp": datetime.now().isoformat()
    }
    orders.append(order)
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

@app.route("/api/orders/<int:order_id>/progress", methods=["GET"])
def get_progress(order_id):
    progress = read_progress()
    order_progress = [p for p in progress if p["order_id"] == str(order_id)]
    return jsonify(order_progress)

@app.route("/api/orders/<int:order_id>/progress", methods=["POST"])
def update_progress(order_id):
    data = request.json
    ingredient = data["ingredient"]
    checked = data["checked"]
    
    # Mark order as preparing if not already
    orders = read_orders()
    for order in orders:
        if int(order["id"]) == order_id and order["status"] == "pending":
            order["status"] = "preparing"
    write_orders(orders)
    
    progress = read_progress()
    # Remove existing entry for this order+ingredient
    progress = [p for p in progress if not (p["order_id"] == str(order_id) and p["ingredient"] == ingredient)]
    
    # Add new entry if checked
    if checked:
        progress.append({
            "order_id": str(order_id),
            "ingredient": ingredient,
            "checked": "True"
        })
    
    write_progress(progress)
    return {"success": True}

@app.route("/api/orders/<int:order_id>/start", methods=["POST"])
def start_order(order_id):
    orders = read_orders()
    for order in orders:
        if int(order["id"]) == order_id:
            order["status"] = "preparing"
    write_orders(orders)
    return {"success": True}

@app.route("/api/ingredients", methods=["GET"])
def get_ingredients():
    return jsonify(read_ingredients())

@app.route("/api/ingredients", methods=["POST"])
def add_ingredient():
    data = request.json
    ingredients = read_ingredients()
    ingredient_id = len(ingredients) + 1
    new_ingredient = {
        "id": str(ingredient_id),
        "name": data["name"],
        "category": data["category"],
        "emoji": data.get("emoji", "")
    }
    ingredients.append(new_ingredient)
    write_ingredients(ingredients)
    
    # Rebuild OPTIONS and FIELDNAMES
    global OPTIONS, FIELDNAMES
    OPTIONS = get_option_keys()
    FIELDNAMES = ["id", "name"] + OPTIONS + ["status", "timestamp"]
    
    return {"success": True, "ingredient": new_ingredient}

@app.route("/api/ingredients/<int:ingredient_id>", methods=["DELETE"])
def delete_ingredient(ingredient_id):
    ingredients = read_ingredients()
    ingredients = [ing for ing in ingredients if int(ing["id"]) != ingredient_id]
    write_ingredients(ingredients)
    
    # Rebuild OPTIONS and FIELDNAMES
    global OPTIONS, FIELDNAMES
    OPTIONS = get_option_keys()
    FIELDNAMES = ["id", "name"] + OPTIONS + ["status", "timestamp"]
    
    return {"success": True}

@app.route("/api/login", methods=["POST"])
def api_login():
    data = request.json
    users = read_users()
    user = next((u for u in users if u['username'] == data['username'] and u['password'] == data['password']), None)
    
    if user:
        session['user_id'] = user['id']
        session['username'] = user['username']
        session['role'] = user['role']
        session['name'] = user['name']
        return {"success": True, "role": user['role'], "name": user['name']}
    else:
        return {"success": False, "message": "Invalid credentials"}, 401

@app.route("/api/users", methods=["GET"])
def get_users():
    users = read_users()
    # Don't send passwords to frontend
    return jsonify([{k: v for k, v in u.items() if k != 'password'} for u in users])

@app.route("/api/users", methods=["POST"])
def add_user():
    data = request.json
    users = read_users()
    user_id = len(users) + 1
    new_user = {
        "id": str(user_id),
        "username": data["username"],
        "password": data["password"],
        "role": data.get("role", "user"),
        "name": data["name"]
    }
    users.append(new_user)
    write_users(users)
    return {"success": True}

@app.route("/api/users/<int:user_id>", methods=["DELETE"])
def delete_user(user_id):
    users = read_users()
    users = [u for u in users if int(u["id"]) != user_id]
    write_users(users)
    return {"success": True}

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5001, debug=True)
