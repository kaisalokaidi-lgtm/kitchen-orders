from flask import Flask, render_template, request, jsonify, session, redirect, url_for, send_file
from flask_socketio import SocketIO, emit
from functools import wraps
from datetime import datetime, timedelta
from itsdangerous import URLSafeTimedSerializer
import sqlite3
import qrcode
from io import BytesIO
import os

import database as db

app = Flask(__name__)
app.secret_key = "burger-order-secret-key-change-this-in-production"
s = URLSafeTimedSerializer(app.secret_key)
socketio = SocketIO(app)

# Load BASE_URL from config.properties
def load_config():
    config = {}
    config_file = os.path.join(os.path.dirname(__file__), 'config.properties')
    if os.path.exists(config_file):
        with open(config_file, 'r') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    config[key.strip()] = value.strip()
    return config

config = load_config()
BASE_URL = config.get('BASE_URL', 'http://localhost:5001')

# Setup the database
db.setup_database()

def setup_admin_user():
    with app.app_context():
        admin = db.get_user_by_username('admin')
        if not admin:
            conn = db.get_db_connection()
            conn.execute("INSERT INTO users (id, username, role, name, gender, is_delivery) VALUES (?, ?, ?, ?, ?, ?)",
                         (1, "admin", "admin", "Administrator", "admin", 0))
            conn.commit()
            conn.close()
            admin = db.get_user_by_username('admin')

        token = s.dumps("admin", salt='magic-link')
        
        conn = db.get_db_connection()
        # Delete existing tokens for admin user to avoid duplicates
        conn.execute("DELETE FROM magic_links WHERE user_id = ?", (admin['id'],))
        conn.execute("INSERT INTO magic_links (user_id, token, expires_at) VALUES (?, ?, ?)",
                     (admin['id'], token, (datetime.now() + timedelta(days=365)).isoformat()))
        conn.commit()
        conn.close()
        
        print("====================================================")
        print("INITIAL ADMIN LOGIN")
        print("Use the following link to log in as the admin user:")
        print(f"{BASE_URL}/magic-login/{token}")
        print("====================================================")

setup_admin_user()

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
                   (data["username"], "", data.get("role", "user"), data["name"], data.get("gender", "male"), is_delivery))
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


@app.route("/api/user/<int:user_id>/generate-qr")
@admin_required
def generate_qr(user_id):
    user = db.get_user_by_id(user_id)
    if not user:
        return "User not found", 404

    # Generate a magic link
    token = s.dumps(user['username'], salt='magic-link')
    magic_link = f"{BASE_URL}/magic-login/{token}"

    # Delete existing tokens for this user and store the new token (60 minutes expiration)
    conn = db.get_db_connection()
    conn.execute("DELETE FROM magic_links WHERE user_id = ?", (user_id,))
    conn.execute("INSERT INTO magic_links (user_id, token, expires_at) VALUES (?, ?, ?)",
                 (user_id, token, (datetime.now() + timedelta(minutes=60)).isoformat()))
    conn.commit()
    conn.close()

    # Generate QR code
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=10,
        border=4,
    )
    qr.add_data(magic_link)
    qr.make(fit=True)

    img = qr.make_image(fill_color="black", back_color="white")
    
    # Save QR code to a bytes buffer
    buf = BytesIO()
    img.save(buf)
    buf.seek(0)

    return send_file(buf, mimetype='image/png')


@app.route("/api/user/<int:user_id>/magic-link")
@admin_required
def get_magic_link(user_id):
    user = db.get_user_by_id(user_id)
    if not user:
        return {"error": "User not found"}, 404

    # Generate a magic link
    token = s.dumps(user['username'], salt='magic-link')
    magic_link = f"{BASE_URL}/magic-login/{token}"

    # Delete existing tokens for this user and store the new token (60 minutes expiration)
    conn = db.get_db_connection()
    conn.execute("DELETE FROM magic_links WHERE user_id = ?", (user_id,))
    conn.execute("INSERT INTO magic_links (user_id, token, expires_at) VALUES (?, ?, ?)",
                 (user_id, token, (datetime.now() + timedelta(minutes=60)).isoformat()))
    conn.commit()
    conn.close()

    return {"magic_link": magic_link, "user_name": user['name']}

    # Generate QR code
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=10,
        border=4,
    )
    qr.add_data(magic_link)
    qr.make(fit=True)

    img = qr.make_image(fill_color="black", back_color="white")
    
    # Save QR code to a bytes buffer
    buf = BytesIO()
    img.save(buf)
    buf.seek(0)

    return send_file(buf, mimetype='image/png')


@app.route('/magic-login/<token>')
def magic_login(token):
    try:
        username = s.loads(token, salt='magic-link', max_age=3600)  # 60 minutes
    except:
        return 'The magic link is expired or invalid.', 403

    conn = db.get_db_connection()
    magic_link_record = conn.execute('SELECT * FROM magic_links WHERE token = ?', (token,)).fetchone()
    
    if not magic_link_record:
        conn.close()
        return 'Invalid magic link.', 403

    # Delete the token after validating it (one-time use)
    conn.execute('DELETE FROM magic_links WHERE token = ?', (token,))
    conn.commit()
    conn.close()

    user = db.get_user_by_username(username)

    if user:
        session['user_id'] = user['id']
        session['username'] = user['username']
        session['role'] = user['role']
        session['name'] = user['name']
        return redirect(url_for('order_page'))
    else:
        return 'User not found.', 404

@app.route("/api/order-settings", methods=["GET"])
@admin_required
def get_order_settings():
    settings = db.get_order_settings()
    users = db.get_users()
    user_settings = []
    for user in users:
        # Include all users (admins included) so they appear in the individual controls
        user_settings.append({
            "id": user["id"],
            "name": user["name"],
            "gender": user.get("gender", ""),
            "role": user.get("role", ""),                # added role for UI clarity
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
            # Apply to ALL users, including admins
            for user in users:
                conn.execute("INSERT OR REPLACE INTO order_settings (setting, value) VALUES (?, ?)", (f"user_{user['id']}", enabled))
        else:
            # Apply to all users matching the gender category (including admins)
            for user in users:
                if user.get('gender') == category:
                    conn.execute("INSERT OR REPLACE INTO order_settings (setting, value) VALUES (?, ?)", (f"user_{user['id']}", enabled))

    if "user_id" in data:
        enabled = 1 if data.get("enabled", False) else 0
        conn.execute("INSERT OR REPLACE INTO order_settings (setting, value) VALUES (?, ?)", (f"user_{data['user_id']}", enabled))

    conn.commit()
    conn.close()
    notify_clients()
    return {"success": True}

@app.route("/api/orders/clear-all", methods=["POST"])
@admin_required
def clear_all_orders():
    try:
        conn = db.get_db_connection()
        
        # Delete all order-related data
        conn.execute("DELETE FROM order_progress")
        conn.execute("DELETE FROM order_ingredients")
        conn.execute("DELETE FROM orders")
        
        # Reset the auto-increment counter for orders table
        conn.execute("DELETE FROM sqlite_sequence WHERE name='orders'")
        
        conn.commit()
        conn.close()
        
        notify_clients()
        return {"success": True, "message": "All orders cleared successfully"}
    except Exception as e:
        return {"success": False, "message": str(e)}, 500

@socketio.on('connect')
def handle_connect():
    print('Client connected')

@socketio.on('disconnect')
def handle_disconnect():
    print('Client disconnected')

if __name__ == "__main__":
    socketio.run(app, host="0.0.0.0", port=5001, debug=True, allow_unsafe_werkzeug=True)
