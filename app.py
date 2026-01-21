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
ORDER_SETTINGS_FILE = "order_settings.csv"

# Initialize CSV files
if not os.path.exists(USERS_FILE):
    with open(USERS_FILE, "w", newline="", encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=["id", "username", "password", "role", "name", "gender", "is_delivery"])
        writer.writeheader()
        # Add default admin
        writer.writerow({"id": "1", "username": "admin", "password": "admin123", "role": "admin", "name": "Administrator", "gender": "admin", "is_delivery": "False"})

if not os.path.exists(ORDER_SETTINGS_FILE):
    with open(ORDER_SETTINGS_FILE, "w", newline="", encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=["setting", "value"])
        writer.writeheader()
        # Only user-specific settings will be stored

if not os.path.exists(INGREDIENTS_FILE):
    with open(INGREDIENTS_FILE, "w", newline="", encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=["id", "name", "category", "emoji", "image_url"])
        writer.writeheader()
        # Add default ingredients
        default_ingredients = [
            {"id": "1", "name": "Tomatoes", "category": "salads", "emoji": "🍅", "image_url": ""},
            {"id": "2", "name": "Saute onions", "category": "salads", "emoji": "🧅", "image_url": ""},
            {"id": "3", "name": "Gherkins", "category": "salads", "emoji": "🥒", "image_url": ""},
            {"id": "4", "name": "Jalapeno", "category": "salads", "emoji": "🌶️", "image_url": ""},
            {"id": "5", "name": "Cheese", "category": "salads", "emoji": "🧀", "image_url": ""},
            {"id": "6", "name": "Lettuce", "category": "salads", "emoji": "🥬", "image_url": ""},
            {"id": "7", "name": "Chefs special", "category": "salads", "emoji": "👨‍🍳", "image_url": ""},
            {"id": "8", "name": "Peri peri lemon and herb", "category": "sauces", "emoji": "🍋🌿", "image_url": ""},
            {"id": "9", "name": "Burger sauce", "category": "sauces", "emoji": "🥫", "image_url": ""},
            {"id": "10", "name": "Ketchup", "category": "sauces", "emoji": "🍅", "image_url": ""},
            {"id": "11", "name": "BBQ", "category": "sauces", "emoji": "🔥", "image_url": ""},
            {"id": "12", "name": "Mayo", "category": "sauces", "emoji": "🧴", "image_url": ""},
            {"id": "13", "name": "Peri peri medium", "category": "sauces", "emoji": "🌶️", "image_url": ""},
            {"id": "14", "name": "Water", "category": "drinks", "emoji": "💧", "image_url": ""},
            {"id": "15", "name": "Coke", "category": "drinks", "emoji": "🥤", "image_url": ""},
            {"id": "16", "name": "Tropicana", "category": "drinks", "emoji": "🍊", "image_url": ""},
        ]
        writer.writerows(default_ingredients)

# Read ingredients to build OPTIONS dynamically
def read_ingredients():
    if not os.path.exists(INGREDIENTS_FILE):
        return []
    with open(INGREDIENTS_FILE, newline="", encoding='utf-8') as f:
        return list(csv.DictReader(f))

def write_ingredients(ingredients):
    with open(INGREDIENTS_FILE, "w", newline="", encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=["id", "name", "category", "emoji", "image_url"])
        writer.writeheader()
        writer.writerows(ingredients)

def read_users():
    if not os.path.exists(USERS_FILE):
        return []
    with open(USERS_FILE, newline="", encoding='utf-8') as f:
        return list(csv.DictReader(f))

def write_users(users):
    with open(USERS_FILE, "w", newline="", encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=["id", "username", "password", "role", "name", "gender", "is_delivery"])
        writer.writeheader()
        writer.writerows(users)

def read_order_settings():
    if not os.path.exists(ORDER_SETTINGS_FILE):
        return {}
    with open(ORDER_SETTINGS_FILE, newline="", encoding='utf-8') as f:
        rows = list(csv.DictReader(f))
        return {row["setting"]: row["value"] for row in rows}

def write_order_settings(settings_dict):
    with open(ORDER_SETTINGS_FILE, "w", newline="", encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=["setting", "value"])
        writer.writeheader()
        for key, value in settings_dict.items():
            writer.writerow({"setting": key, "value": value})

def can_user_order(user_id):
    """Check if a user can place an order"""
    users = read_users()
    user = next((u for u in users if u['id'] == user_id), None)
    if not user:
        return False

    settings = read_order_settings()

    # Only check if specific user is enabled
    if settings.get(f"user_{user_id}") == "True":
        return True

    return False

def is_user_delivery(user_id):
    """Check if a user has delivery role"""
    users = read_users()
    user = next((u for u in users if u['id'] == user_id), None)
    return user and user.get('is_delivery', 'False') == 'True'

def get_user_current_order(user_id):
    """Get user's current order if they have one (excluding delivered orders)"""
    users = read_users()
    user = next((u for u in users if u['id'] == user_id), None)
    if not user:
        return None

    orders = read_orders()
    # Find the most recent order for this user (excluding delivered orders)
    user_orders = [o for o in orders if o.get("name") == user.get("name") and o.get("status") != "delivered"]
    if user_orders:
        return user_orders[-1]  # Return most recent
    return None

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
FIELDNAMES = ["id", "name"] + OPTIONS + ["status", "timestamp", "collected_by", "collected_at", "delivered_at"]

if not os.path.exists(CSV_FILE):
    with open(CSV_FILE, "w", newline="", encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()

if not os.path.exists(PROGRESS_FILE):
    with open(PROGRESS_FILE, "w", newline="", encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=["order_id", "ingredient", "checked"])
        writer.writeheader()

def read_orders():
    if not os.path.exists(CSV_FILE):
        return []
    with open(CSV_FILE, newline="", encoding='utf-8') as f:
        return list(csv.DictReader(f))

def write_orders(orders):
    # Dynamically build fieldnames from current ingredients
    current_fieldnames = ["id", "name"] + get_option_keys() + ["status", "timestamp", "collected_by", "collected_at", "delivered_at"]
    with open(CSV_FILE, "w", newline="", encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=current_fieldnames)
        writer.writeheader()
        writer.writerows(orders)

def read_progress():
    if not os.path.exists(PROGRESS_FILE):
        return []
    with open(PROGRESS_FILE, newline="", encoding='utf-8') as f:
        return list(csv.DictReader(f))

def write_progress(progress):
    with open(PROGRESS_FILE, "w", newline="", encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=["order_id", "ingredient", "checked"])
        writer.writeheader()
        writer.writerows(progress)

@app.route("/")
@login_required
def order_page():
    users = read_users()
    user = next((u for u in users if u['id'] == session['user_id']), None)
    can_order = can_user_order(session['user_id'])
    current_order = get_user_current_order(session['user_id'])
    is_delivery = is_user_delivery(session['user_id'])
    return render_template("order.html", user=user, can_order=can_order, current_order=current_order, is_delivery=is_delivery)

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
    # Check if user can order
    if not can_user_order(session.get('user_id')):
        return {"success": False, "message": "You don't have permission to order right now"}, 403
    
    # Check if user already has an order (any status)
    current_order = get_user_current_order(session.get('user_id'))
    if current_order:
        return {"success": False, "message": "You already have an order. Please wait for admin to clear it."}, 400
    
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

@app.route("/api/delivery/ready-orders", methods=["GET"])
@login_required
def get_ready_orders_for_delivery():
    """Get all orders that are ready for delivery"""
    orders = read_orders()
    ready_orders = [o for o in orders if o.get("status") == "ready"]
    return jsonify(ready_orders)

@app.route("/api/delivery/my-deliveries", methods=["GET"])
@login_required
def get_my_deliveries():
    """Get orders currently being delivered by this user"""
    users = read_users()
    user = next((u for u in users if u['id'] == session['user_id']), None)
    if not user:
        return {"error": "User not found"}, 404

    orders = read_orders()
    my_deliveries = [o for o in orders if o.get("status") == "out_for_delivery" and o.get("collected_by") == user.get("name")]
    return jsonify(my_deliveries)

@app.route("/api/orders/<int:order_id>/collect", methods=["POST"])
@login_required
def collect_order(order_id):
    """Mark an order as collected for delivery"""
    orders = read_orders()
    users = read_users()
    user = next((u for u in users if u['id'] == session['user_id']), None)

    if not user:
        return {"error": "User not found"}, 404

    if not is_user_delivery(session['user_id']):
        return {"error": "Only delivery users can collect orders"}, 403

    for order in orders:
        if int(order["id"]) == order_id:
            order["status"] = "out_for_delivery"
            order["collected_by"] = user.get("name")
            order["collected_at"] = datetime.now().isoformat()
            break

    write_orders(orders)
    return {"success": True}

@app.route("/api/orders/<int:order_id>/deliver", methods=["POST"])
@login_required
def deliver_order(order_id):
    """Mark an order as delivered"""
    orders = read_orders()
    users = read_users()

    order_to_deliver = None
    for order in orders:
        if int(order["id"]) == order_id:
            order["status"] = "delivered"
            order["delivered_at"] = datetime.now().isoformat()
            order_to_deliver = order
            break

    if order_to_deliver:
        write_orders(orders)

        # Re-enable ordering for this user
        user = next((u for u in users if u['name'] == order_to_deliver['name']), None)
        if user:
            settings = read_order_settings()
            settings[f"user_{user['id']}"] = "True"
            write_order_settings(settings)

    return {"success": True}

@app.route("/api/orders/delivered", methods=["GET"])
@login_required
def get_delivered_orders():
    """Get all delivered orders"""
    orders = read_orders()
    delivered_orders = [o for o in orders if o.get("status") == "delivered"]
    # Return most recent 20
    return jsonify(delivered_orders[-20:] if len(delivered_orders) > 20 else delivered_orders)

@app.route("/api/user/order-history", methods=["GET"])
@login_required
def get_user_order_history():
    """Get current user's order history"""
    users = read_users()
    user = next((u for u in users if u['id'] == session['user_id']), None)
    if not user:
        return {"error": "User not found"}, 404

    orders = read_orders()
    user_delivered_orders = [o for o in orders if o.get("name") == user.get("name") and o.get("status") == "delivered"]
    return jsonify(user_delivered_orders)

@app.route("/api/user/order-status", methods=["GET"])
def get_user_order_status():
    """Get current user's order status and permission to order"""
    user_id = session.get('user_id')
    if not user_id:
        return {"error": "Not authenticated"}, 401
    
    users = read_users()
    user = next((u for u in users if u['id'] == user_id), None)
    if not user:
        return {"error": "User not found"}, 404
    
    can_order = can_user_order(user_id)
    current_order = get_user_current_order(user_id)
    
    return jsonify({
        "can_order": can_order,
        "current_order": current_order,
        "user_name": user.get("name")
    })

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
        "emoji": data.get("emoji", ""),
        "image_url": data.get("image_url", "")
    }
    ingredients.append(new_ingredient)
    write_ingredients(ingredients)

    # Rebuild OPTIONS and FIELDNAMES
    global OPTIONS, FIELDNAMES
    OPTIONS = get_option_keys()
    FIELDNAMES = ["id", "name"] + OPTIONS + ["status", "timestamp"]

    return {"success": True, "ingredient": new_ingredient}

@app.route("/api/ingredients/<int:ingredient_id>", methods=["PUT"])
def update_ingredient(ingredient_id):
    data = request.json
    ingredients = read_ingredients()

    # Find and update the ingredient
    for ing in ingredients:
        if int(ing["id"]) == ingredient_id:
            ing["name"] = data.get("name", ing["name"])
            ing["category"] = data.get("category", ing["category"])
            ing["emoji"] = data.get("emoji", ing.get("emoji", ""))
            ing["image_url"] = data.get("image_url", ing.get("image_url", ""))
            break

    write_ingredients(ingredients)

    # Rebuild OPTIONS and FIELDNAMES
    global OPTIONS, FIELDNAMES
    OPTIONS = get_option_keys()
    FIELDNAMES = ["id", "name"] + OPTIONS + ["status", "timestamp"]

    return {"success": True}

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
        "name": data["name"],
        "gender": data.get("gender", "male"),
        "is_delivery": data.get("is_delivery", "False")
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

@app.route("/api/order-settings", methods=["GET"])
def get_order_settings():
    settings = read_order_settings()
    users = read_users()
    # Include user-specific settings
    user_settings = []
    for user in users:
        if user['role'] != 'admin':
            user_settings.append({
                "id": user["id"],
                "name": user["name"],
                "gender": user.get("gender", ""),
                "can_order": settings.get(f"user_{user['id']}") == "True"
            })
    return jsonify({
        "users": user_settings
    })

@app.route("/api/order-settings", methods=["POST"])
def update_order_settings():
    data = request.json
    settings = read_order_settings()
    users = read_users()

    # Handle category toggles - toggle all users of that category
    if "toggle_category" in data:
        category = data["toggle_category"]  # "male", "female", "kid", or "all"
        enabled = data.get("enabled", False)

        if category == "all":
            # Toggle all non-admin users
            for user in users:
                if user['role'] != 'admin':
                    settings[f"user_{user['id']}"] = str(enabled)
        else:
            # Toggle all users of specific gender
            for user in users:
                if user['role'] != 'admin' and user.get('gender') == category:
                    settings[f"user_{user['id']}"] = str(enabled)

    # Update individual user-specific settings
    if "user_id" in data:
        settings[f"user_{data['user_id']}"] = str(data.get("enabled", False))

    write_order_settings(settings)
    return {"success": True}


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5001, debug=True)
