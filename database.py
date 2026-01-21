import sqlite3

DB_FILE = "kitchen.db"

def get_db_connection():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn

def create_table(conn, create_table_sql):
    """ create a table from the create_table_sql statement
    :param conn: Connection object
    :param create_table_sql: a CREATE TABLE statement
    :return:
    """
    try:
        c = conn.cursor()
        c.execute(create_table_sql)
    except sqlite3.Error as e:
        print(e)

def setup_database():
    conn = get_db_connection()

    if conn is not None:
        # Create tables
        create_users_table_sql = """ CREATE TABLE IF NOT EXISTS users (
                                        id integer PRIMARY KEY,
                                        username text NOT NULL UNIQUE,
                                        password text NOT NULL,
                                        role text,
                                        name text,
                                        gender text,
                                        is_delivery integer
                                    ); """

        create_ingredients_table_sql = """CREATE TABLE IF NOT EXISTS ingredients (
                                    id integer PRIMARY KEY,
                                    name text NOT NULL,
                                    category text,
                                    emoji text,
                                    image_url text
                                );"""

        create_orders_table_sql = """CREATE TABLE IF NOT EXISTS orders (
                                    id integer PRIMARY KEY AUTOINCREMENT,
                                    name text,
                                    person_type text,
                                    order_count integer,
                                    additional_instructions text,
                                    status text,
                                    timestamp text,
                                    collected_by text,
                                    collected_at text,
                                    delivered_at text
                                );"""

        create_order_ingredients_table_sql = """CREATE TABLE IF NOT EXISTS order_ingredients (
                                            order_id integer,
                                            ingredient_id text,
                                            FOREIGN KEY (order_id) REFERENCES orders (id),
                                            FOREIGN KEY (ingredient_id) REFERENCES ingredients (id),
                                            PRIMARY KEY (order_id, ingredient_id)
                                        );"""

        create_order_settings_table_sql = """CREATE TABLE IF NOT EXISTS order_settings (
                                            setting text PRIMARY KEY,
                                            value integer
                                        );"""

        create_order_progress_table_sql = """CREATE TABLE IF NOT EXISTS order_progress (
                                            order_id integer,
                                            ingredient text,
                                            checked integer,
                                            PRIMARY KEY (order_id, ingredient)
                                        );"""

        create_table(conn, create_users_table_sql)
        create_table(conn, create_ingredients_table_sql)
        create_table(conn, create_orders_table_sql)
        create_table(conn, create_order_ingredients_table_sql)
        create_table(conn, create_order_settings_table_sql)
        create_table(conn, create_order_progress_table_sql)

        # Check if database is empty
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM users")
        user_count = cursor.fetchone()[0]

        if user_count == 0:
            # Add default admin
            conn.execute("INSERT INTO users (id, username, password, role, name, gender, is_delivery) VALUES (?, ?, ?, ?, ?, ?, ?)",
                         (1, "admin", "admin123", "admin", "Administrator", "admin", 0))

        cursor.execute("SELECT COUNT(*) FROM ingredients")
        ingredient_count = cursor.fetchone()[0]
        if ingredient_count == 0:
            # Add default ingredients
            default_ingredients = [
                (1, "Tomatoes", "salads", "🍅", ""),
                (2, "Saute onions", "salads", "🧅", ""),
                (3, "Gherkins", "salads", "🥒", ""),
                (4, "Jalapeno", "salads", "🌶️", ""),
                (5, "Cheese", "salads", "🧀", ""),
                (6, "Lettuce", "salads", "🥬", ""),
                (7, "Chefs special", "salads", "👨‍🍳", ""),
                (8, "Peri peri lemon and herb", "sauces", "🍋🌿", ""),
                (9, "Burger sauce", "sauces", "🥫", ""),
                (10, "Ketchup", "sauces", "🍅", ""),
                (11, "BBQ", "sauces", "🔥", ""),
                (12, "Mayo", "sauces", "🧴", ""),
                (13, "Peri peri medium", "sauces", "🌶️", ""),
                (14, "Water", "drinks", "💧", ""),
                (15, "Coke", "drinks", "🥤", ""),
                (16, "Tropicana", "drinks", "🍊", ""),
            ]
            conn.executemany("INSERT INTO ingredients (id, name, category, emoji, image_url) VALUES (?, ?, ?, ?, ?)", default_ingredients)

        conn.commit()
        conn.close()

def get_ingredients():
    conn = get_db_connection()
    ingredients = conn.execute('SELECT * FROM ingredients').fetchall()
    conn.close()
    return [dict(row) for row in ingredients]

def get_users():
    conn = get_db_connection()
    users = conn.execute('SELECT * FROM users').fetchall()
    conn.close()
    return [dict(row) for row in users]

def get_user_by_id(user_id):
    conn = get_db_connection()
    user = conn.execute('SELECT * FROM users WHERE id = ?', (user_id,)).fetchone()
    conn.close()
    return dict(user) if user else None

def get_user_by_username_and_password(username, password):
    conn = get_db_connection()
    user = conn.execute('SELECT * FROM users WHERE username = ? AND password = ?', (username, password)).fetchone()
    conn.close()
    return dict(user) if user else None

def get_orders():
    conn = get_db_connection()
    orders = conn.execute('SELECT * FROM orders').fetchall()
    
    orders_list = []
    for o in orders:
        order_dict = dict(o)
        ingredients = get_order_ingredients(o['id'])
        for ingredient in ingredients:
            order_dict[ingredient['name'].lower().replace(' ', '_')] = "True"
        orders_list.append(order_dict)
    conn.close()
    return orders_list

def get_order_ingredients(order_id):
    conn = get_db_connection()
    ingredients = conn.execute('SELECT i.name FROM ingredients i JOIN order_ingredients oi ON i.id = oi.ingredient_id WHERE oi.order_id = ?', (order_id,)).fetchall()
    conn.close()
    return [dict(row) for row in ingredients]

def get_order_by_id(order_id):
    conn = get_db_connection()
    order = conn.execute('SELECT * FROM orders WHERE id = ?', (order_id,)).fetchone()
    conn.close()
    return dict(order) if order else None

def get_order_settings():
    conn = get_db_connection()
    settings = conn.execute('SELECT * FROM order_settings').fetchall()
    conn.close()
    return {row['setting']: bool(row['value']) for row in settings}

def get_user_current_order(user_id):
    user = get_user_by_id(user_id)
    if not user:
        return None
    conn = get_db_connection()
    order = conn.execute('SELECT * FROM orders WHERE name = ? AND status != "delivered" ORDER BY timestamp DESC', (user['name'],)).fetchone()
    conn.close()
    return dict(order) if order else None

def can_user_order(user_id):
    user = get_user_by_id(user_id)
    if not user:
        return False
    settings = get_order_settings()
    return settings.get(f"user_{user_id}", False)

def is_user_delivery(user_id):
    user = get_user_by_id(user_id)
    return user and user.get('is_delivery')

def get_option_keys():
    ingredients = get_ingredients()
    return [ing["name"].lower().replace(" ", "_") for ing in ingredients]

def get_progress(order_id):
    conn = get_db_connection()
    progress = conn.execute('SELECT * FROM order_progress WHERE order_id = ?', (order_id,)).fetchall()
    conn.close()
    return [dict(row) for row in progress]

def get_ready_orders_for_delivery():
    conn = get_db_connection()
    orders = conn.execute('SELECT * FROM orders WHERE status = "ready"').fetchall()
    conn.close()
    return [dict(row) for row in orders]

def get_my_deliveries(user_id):
    user = get_user_by_id(user_id)
    if not user:
        return []
    conn = get_db_connection()
    orders = conn.execute('SELECT * FROM orders WHERE status = "out_for_delivery" AND collected_by = ?', (user['name'],)).fetchall()
    conn.close()
    return [dict(row) for row in orders]

def get_delivered_orders():
    conn = get_db_connection()
    orders = conn.execute('SELECT * FROM orders WHERE status = "delivered" ORDER BY delivered_at DESC LIMIT 20').fetchall()
    conn.close()
    return [dict(row) for row in orders]

def get_user_order_history(user_id):
    user = get_user_by_id(user_id)
    if not user:
        return []
    conn = get_db_connection()
    orders = conn.execute('SELECT * FROM orders WHERE name = ? AND status = "delivered"', (user['name'],)).fetchall()
    conn.close()
    return [dict(row) for row in orders]
