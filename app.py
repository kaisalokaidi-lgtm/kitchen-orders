from flask import Flask, render_template, request, jsonify, session, redirect, url_for
from flask_socketio import SocketIO, emit
from functools import wraps
from datetime import datetime
import sqlite3

import database as db

app = Flask(__name__)
app.secret_key = "burger-order-secret-key-change-this-in-production"
socketio = SocketIO(app)

# Setup the database
db.setup_database()

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
        user = db.get_user_by_id(session['user_id'])
        if not user or user['role'] != 'admin':
            return redirect(url_for('order_page'))
        return f(*args, **kwargs)
    return decorated_function

def notify_clients(order_id=None):
    """Notifies clients about order updates."""
    if order_id:
        socketio.emit('order_updated', {'order_id': order_id})
    else:
        socketio.emit('update_orders')

@app.route("/")
@login_required
def order_page():
    user = db.get_user_by_id(session['user_id'])
    can_order = db.can_user_order(session['user_id'])
    current_order = db.get_user_current_order(session['user_id'])
    is_delivery = db.is_user_delivery(session['user_id'])
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
    orders = db.get_orders()
    return jsonify(orders)

@app.route("/api/orders", methods=["POST"])
@login_required
def add_order():
    if not db.can_user_order(session.get('user_id')):
        return {"success": False, "message": "You don't have permission to order right now"}, 403
    
    current_order = db.get_user_current_order(session.get('user_id'))
    if current_order:
        return {"success": False, "message": "You already have an order. Please wait for it to be delivered."}, 400
    
    data = request.json
    user = db.get_user_by_id(session.get('user_id'))
    if not user:
        return {"success": False, "message": "User not found"}, 404
    
    gender_map = {"male": "Male", "female": "Female", "kid": "Child"}
    person_type = gender_map.get(user.get('gender', 'male'), 'Male')
    
    user_delivered_orders = db.get_user_order_history(user['id'])
    order_count = len(user_delivered_orders) + 1
    
    conn = db.get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute(
        "INSERT INTO orders (name, person_type, order_count, additional_instructions, status, timestamp) VALUES (?, ?, ?, ?, ?, ?)",
        (data["name"], person_type, order_count, data.get("additional_instructions", ""), "pending", datetime.now().isoformat())
    )
    order_id = cursor.lastrowid
    
    current_options = db.get_option_keys()
    for option in current_options:
        if data.get(option):
            # We need to get the ingredient id from the name
            ingredient_name = option.replace('_', ' ')
            ingredient = conn.execute('SELECT id FROM ingredients WHERE name LIKE ?', (f'%{ingredient_name}%',)).fetchone()
            if ingredient:
                cursor.execute("INSERT INTO order_ingredients (order_id, ingredient_id) VALUES (?, ?)", (order_id, ingredient['id']))

    conn.commit()
    conn.close()
    notify_clients(order_id) # Emit specific order update
    
    return {"success": True}


@app.route("/api/orders/<int:order_id>/ready", methods=["POST"])
def mark_ready(order_id):
    conn = db.get_db_connection()
    conn.execute('UPDATE orders SET status = "ready" WHERE id = ?', (order_id,))
    conn.commit()
    conn.close()
    notify_clients(order_id) # Emit specific order update
    return {"success": True}

@app.route("/api/orders/<int:order_id>/progress", methods=["GET"])
def get_progress(order_id):
    progress = db.get_progress(order_id)
    return jsonify(progress)

@app.route("/api/orders/<int:order_id>/progress", methods=["POST"])
def update_progress(order_id):
    data = request.json
    ingredient = data["ingredient"]
    checked = data["checked"]
    
    conn = db.get_db_connection()
    order = db.get_order_by_id(order_id)
    if order and order['status'] == 'pending':
        conn.execute('UPDATE orders SET status = "preparing" WHERE id = ?', (order_id,))
    
    conn.execute('DELETE FROM order_progress WHERE order_id = ? AND ingredient = ?', (order_id, ingredient))
    if checked:
        conn.execute('INSERT INTO order_progress (order_id, ingredient, checked) VALUES (?, ?, ?)', (order_id, ingredient, 1))
        
    conn.commit()
    conn.close()
    notify_clients(order_id) # Emit specific order update
    return {"success": True}

@app.route("/api/orders/<int:order_id>/start", methods=["POST"])
def start_order(order_id):
    conn = db.get_db_connection()
    conn.execute('UPDATE orders SET status = "preparing" WHERE id = ?', (order_id,))
    conn.commit()
    conn.close()
    notify_clients(order_id) # Emit specific order update
    return {"success": True}

@app.route("/api/delivery/ready-orders", methods=["GET"])
@login_required
def get_ready_orders_for_delivery():
    orders = db.get_ready_orders_for_delivery()
    return jsonify(orders)

@app.route("/api/delivery/my-deliveries", methods=["GET"])
@login_required
def get_my_deliveries():
    deliveries = db.get_my_deliveries(session['user_id'])
    return jsonify(deliveries)

@app.route("/api/orders/<int:order_id>/collect", methods=["POST"])
@login_required
def collect_order(order_id):
    user = db.get_user_by_id(session['user_id'])
    if not user:
        return {"error": "User not found"}, 404

    if not db.is_user_delivery(session['user_id']):
        return {"error": "Only delivery users can collect orders"}, 403

    conn = db.get_db_connection()
    conn.execute('UPDATE orders SET status = "out_for_delivery", collected_by = ?, collected_at = ? WHERE id = ?',
                 (user['name'], datetime.now().isoformat(), order_id))
    conn.commit()
    conn.close()
    notify_clients(order_id) # Emit specific order update
    return {"success": True}

@app.route("/api/orders/<int:order_id>/deliver", methods=["POST"])
@login_required
def deliver_order(order_id):
    conn = db.get_db_connection()
    conn.execute('UPDATE orders SET status = "delivered", delivered_at = ? WHERE id = ?',
                 (datetime.now().isoformat(), order_id))
    
    order_to_deliver = db.get_order_by_id(order_id)
    if order_to_deliver:
        users = db.get_users()
        user = next((u for u in users if u['name'] == order_to_deliver['name']), None)
        if user:
            conn.execute("INSERT OR REPLACE INTO order_settings (setting, value) VALUES (?, ?)", (f"user_{user['id']}", 1))

    conn.commit()
    conn.close()
    notify_clients(order_id) # Emit specific order update
    notify_clients() # Emit general update as well, as delivered orders might affect overall counts or history
    return {"success": True}

@app.route("/api/orders/delivered", methods=["GET"])
@login_required
def get_delivered_orders():
    orders = db.get_delivered_orders()
    return jsonify(orders)

@app.route("/api/user/order-history", methods=["GET"])
@login_required
def get_user_order_history():
    history = db.get_user_order_history(session['user_id'])
    return jsonify(history)

@app.route("/api/user/order-status", methods=["GET"])
def get_user_order_status():
    user_id = session.get('user_id')
    if not user_id:
        return {"error": "Not authenticated"}, 401
    
    user = db.get_user_by_id(user_id)
    if not user:
        return {"error": "User not found"}, 404
    
    can_order = db.can_user_order(user_id)
    current_order = db.get_user_current_order(user_id)
    
    return jsonify({
        "can_order": can_order,
        "current_order": current_order,
        "user_name": user.get("name")
    })

@app.route("/api/ingredients", methods=["GET"])
def get_ingredients():
    return jsonify(db.get_ingredients())

@app.route("/api/ingredients", methods=["POST"])
@admin_required
def add_ingredient():
    data = request.json
    conn = db.get_db_connection()
    cursor = conn.cursor()
    cursor.execute("INSERT INTO ingredients (name, category, emoji, image_url) VALUES (?, ?, ?, ?)",
                   (data["name"], data["category"], data.get("emoji", ""), data.get("image_url", "")))
    new_id = cursor.lastrowid
    conn.commit()
    conn.close()
    
    new_ingredient = db.get_ingredients() # a bit inefficient but fine for now
    new_ingredient = next((ing for ing in new_ingredient if ing['id'] == new_id), None)
    notify_clients()

    return {"success": True, "ingredient": new_ingredient}

@app.route("/api/ingredients/<int:ingredient_id>", methods=["PUT"])
@admin_required
def update_ingredient(ingredient_id):
    data = request.json
    conn = db.get_db_connection()
    conn.execute("UPDATE ingredients SET name = ?, category = ?, emoji = ?, image_url = ? WHERE id = ?",
                   (data["name"], data["category"], data.get("emoji", ""), data.get("image_url", ""), ingredient_id))
    conn.commit()
    conn.close()
    notify_clients()
    return {"success": True}

@app.route("/api/ingredients/<int:ingredient_id>", methods=["DELETE"])
@admin_required
def delete_ingredient(ingredient_id):
    conn = db.get_db_connection()
    conn.execute("DELETE FROM ingredients WHERE id = ?", (ingredient_id,))
    conn.commit()
    conn.close()
    notify_clients()
    return {"success": True}

@app.route("/api/login", methods=["POST"])
def api_login():
    data = request.json
    user = db.get_user_by_username_and_password(data['username'], data['password'])
    
    if user:
        session['user_id'] = user['id']
        session['username'] = user['username']
        session['role'] = user['role']
        session['name'] = user['name']
        return {"success": True, "role": user['role'], "name": user['name']}
    else:
        return {"success": False, "message": "Invalid credentials"}, 401

@app.route("/api/users", methods=["GET"])
@admin_required
def get_users():
    users = db.get_users()
    return jsonify([{k: v for k, v in u.items() if k != 'password'} for u in users])

@app.route("/api/users", methods=["POST"])
@admin_required
def add_user():
    data = request.json
    is_delivery = 1 if data.get("is_delivery") == 'True' else 0
    conn = db.get_db_connection()
    conn.execute("INSERT INTO users (username, password, role, name, gender, is_delivery) VALUES (?, ?, ?, ?, ?, ?)",
                   (data["username"], data["password"], data.get("role", "user"), data["name"], data.get("gender", "male"), is_delivery))
    conn.commit()
    conn.close()
    notify_clients()
    return {"success": True}

@app.route("/api/users/<int:user_id>", methods=["DELETE"])
@admin_required
def delete_user(user_id):
    conn = db.get_db_connection()
    conn.execute("DELETE FROM users WHERE id = ?", (user_id,))
    conn.commit()
    conn.close()
    notify_clients()
    return {"success": True}

@app.route("/api/order-settings", methods=["GET"])
@admin_required
def get_order_settings():
    settings = db.get_order_settings()
    users = db.get_users()
    user_settings = []
    for user in users:
        if user['role'] != 'admin':
            user_settings.append({
                "id": user["id"],
                "name": user["name"],
                "gender": user.get("gender", ""),
                "can_order": settings.get(f"user_{user['id']}", False)
            })
    return jsonify({
        "users": user_settings
    })

@app.route("/api/order-settings", methods=["POST"])
@admin_required
def update_order_settings():
    data = request.json
    conn = db.get_db_connection()
    
    if "toggle_category" in data:
        category = data["toggle_category"]
        enabled = 1 if data.get("enabled", False) else 0
        users = db.get_users()

        if category == "all":
            for user in users:
                if user['role'] != 'admin':
                    conn.execute("INSERT OR REPLACE INTO order_settings (setting, value) VALUES (?, ?)", (f"user_{user['id']}", enabled))
        else:
            for user in users:
                if user['role'] != 'admin' and user.get('gender') == category:
                    conn.execute("INSERT OR REPLACE INTO order_settings (setting, value) VALUES (?, ?)", (f"user_{user['id']}", enabled))

    if "user_id" in data:
        enabled = 1 if data.get("enabled", False) else 0
        conn.execute("INSERT OR REPLACE INTO order_settings (setting, value) VALUES (?, ?)", (f"user_{data['user_id']}", enabled))

    conn.commit()
    conn.close()
    notify_clients()
    return {"success": True}

@socketio.on('connect')
def handle_connect():
    print('Client connected')

@socketio.on('disconnect')
def handle_disconnect():
    print('Client disconnected')

if __name__ == "__main__":
    socketio.run(app, host="0.0.0.0", port=5001, debug=False, allow_unsafe_werkzeug=True)
